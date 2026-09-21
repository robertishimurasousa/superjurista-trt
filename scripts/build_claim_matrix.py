#!/usr/bin/env python3
"""Build a deterministic, source-linked Labor Justice claim matrix."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from schema_validation import ContractError, load_json


DOCUMENT_ID_PATTERN = re.compile(r"DOC-[0-9]{3,}")
CLAIM_ID_PATTERN = re.compile(r"CLM-[0-9]{3,}")
DEFENSE_ID_PATTERN = re.compile(r"DEF-[0-9]{3,}")
PARTY_ID_PATTERN = re.compile(r"PTY-[0-9]{3,}")
LABEL_PATTERN = re.compile(r"[a-z][a-z0-9_]*")


class ClaimMatrixContractViolation(ValueError):
    """Raised when claim-matrix inputs violate taxonomy or custody rules."""


@dataclass(frozen=True)
class SourceReference:
    document_id: str
    locator: str


@dataclass(frozen=True)
class ClaimCandidate:
    claim_id: str
    label: str
    claimant_position: str
    requested_remedies: Tuple[str, ...]
    contested_facts: Tuple[str, ...]
    legal_issues: Tuple[str, ...]
    source: SourceReference


@dataclass(frozen=True)
class DefenseCandidate:
    defense_id: str
    claim_id: str
    respondent_party_id: str
    respondent_position: str
    source: SourceReference


def _require_exact_keys(value: dict, expected: set, label: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise ClaimMatrixContractViolation(f"{label} missing field(s): {', '.join(missing)}")
    if unknown:
        raise ClaimMatrixContractViolation(f"{label} has unknown field(s): {', '.join(unknown)}")


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClaimMatrixContractViolation(f"{label} must be a non-empty string")
    return value


def _require_identifier(value: object, pattern: re.Pattern, label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ClaimMatrixContractViolation(f"{label} is invalid")
    return value


def _require_label(value: object, label: str) -> str:
    return _require_identifier(value, LABEL_PATTERN, label)


def _require_unique_tuple(value: object, label: str) -> Tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ClaimMatrixContractViolation(f"{label} must be a tuple")
    for item in value:
        _require_label(item, label)
    if len(value) != len(set(value)):
        raise ClaimMatrixContractViolation(f"{label} values must be unique")
    return value


def _validate_taxonomy(value: object) -> dict:
    if not isinstance(value, dict):
        raise ClaimMatrixContractViolation("claim taxonomy root must be an object")
    _require_exact_keys(
        value,
        {"schema_version", "taxonomy_version", "claim_types"},
        "claim taxonomy",
    )
    if value["schema_version"] != 1:
        raise ClaimMatrixContractViolation("claim taxonomy schema_version must be 1")
    if value["taxonomy_version"] != 1:
        raise ClaimMatrixContractViolation("claim taxonomy taxonomy_version must be 1")
    claim_types = value["claim_types"]
    if not isinstance(claim_types, list) or not claim_types:
        raise ClaimMatrixContractViolation("claim taxonomy claim_types must be a non-empty list")
    seen_labels = set()
    for index, claim_type in enumerate(claim_types):
        label = f"claim_types[{index}]"
        if not isinstance(claim_type, dict):
            raise ClaimMatrixContractViolation(f"{label} must be an object")
        _require_exact_keys(claim_type, {"label", "allowed_remedies"}, label)
        claim_label = _require_label(claim_type["label"], f"{label}.label")
        if claim_label in seen_labels:
            raise ClaimMatrixContractViolation("claim taxonomy label values must be unique")
        seen_labels.add(claim_label)
        remedies = claim_type["allowed_remedies"]
        if not isinstance(remedies, list) or not remedies:
            raise ClaimMatrixContractViolation(
                f"{label}.allowed_remedies must be a non-empty list"
            )
        for remedy in remedies:
            _require_label(remedy, f"{label}.allowed_remedies")
        if len(remedies) != len(set(remedies)):
            raise ClaimMatrixContractViolation(
                f"{label}.allowed_remedies values must be unique"
            )
    return value


def load_claim_taxonomy(path: Path) -> dict:
    """Load and validate the versioned Labor Justice claim taxonomy."""
    try:
        value = load_json(path, "labor claim taxonomy")
    except ContractError as error:
        raise ClaimMatrixContractViolation(str(error)) from error
    return _validate_taxonomy(value)


def _known_documents(value: object) -> set:
    if not isinstance(value, tuple) or not value:
        raise ClaimMatrixContractViolation("known_document_ids must be a non-empty tuple")
    for document_id in value:
        _require_identifier(document_id, DOCUMENT_ID_PATTERN, "document_id")
    if len(value) != len(set(value)):
        raise ClaimMatrixContractViolation("known_document_ids must be unique")
    return set(value)


def _source_fields(source: object, known_documents: set, label: str) -> dict:
    if not isinstance(source, SourceReference):
        raise ClaimMatrixContractViolation(f"{label} source reference is invalid")
    _require_identifier(source.document_id, DOCUMENT_ID_PATTERN, f"{label} document_id")
    if source.document_id not in known_documents:
        raise ClaimMatrixContractViolation(
            f"{label} references unknown document {source.document_id}"
        )
    _require_text(source.locator, f"{label} source locator")
    return {
        "source_document_id": source.document_id,
        "source_locator": source.locator,
    }


def _taxonomy_map(taxonomy: dict) -> dict:
    return {
        item["label"]: set(item["allowed_remedies"])
        for item in taxonomy["claim_types"]
    }


def _validate_claims(value: object, known_documents: set) -> dict:
    if not isinstance(value, tuple) or not value:
        raise ClaimMatrixContractViolation("claims must be a non-empty tuple")
    claims = {}
    for candidate in value:
        if not isinstance(candidate, ClaimCandidate):
            raise ClaimMatrixContractViolation("claim candidate has an invalid type")
        _require_identifier(candidate.claim_id, CLAIM_ID_PATTERN, "claim_id")
        if candidate.claim_id in claims:
            raise ClaimMatrixContractViolation("claim_id values must be unique")
        _require_label(candidate.label, "claim label")
        _require_text(candidate.claimant_position, "claimant_position")
        _require_unique_tuple(candidate.requested_remedies, "requested_remedies")
        _require_unique_tuple(candidate.contested_facts, "contested_facts")
        _require_unique_tuple(candidate.legal_issues, "legal_issues")
        source = _source_fields(candidate.source, known_documents, candidate.claim_id)
        claims[candidate.claim_id] = (candidate, source)
    return claims


def _validate_defenses(value: object, known_documents: set, claim_ids: set) -> dict:
    if not isinstance(value, tuple):
        raise ClaimMatrixContractViolation("defenses must be a tuple")
    defenses = {}
    grouped = {claim_id: [] for claim_id in claim_ids}
    for candidate in value:
        if not isinstance(candidate, DefenseCandidate):
            raise ClaimMatrixContractViolation("defense candidate has an invalid type")
        _require_identifier(candidate.defense_id, DEFENSE_ID_PATTERN, "defense_id")
        if candidate.defense_id in defenses:
            raise ClaimMatrixContractViolation("defense_id values must be unique")
        _require_identifier(candidate.claim_id, CLAIM_ID_PATTERN, "defense claim_id")
        if candidate.claim_id not in claim_ids:
            raise ClaimMatrixContractViolation(
                f"defense references unknown claim {candidate.claim_id}"
            )
        _require_identifier(
            candidate.respondent_party_id,
            PARTY_ID_PATTERN,
            "respondent_party_id",
        )
        _require_text(candidate.respondent_position, "respondent_position")
        source = _source_fields(candidate.source, known_documents, candidate.defense_id)
        item = {
            "defense_id": candidate.defense_id,
            "respondent_party_id": candidate.respondent_party_id,
            "summary": candidate.respondent_position,
            **source,
        }
        defenses[candidate.defense_id] = item
        grouped[candidate.claim_id].append(item)
    for items in grouped.values():
        items.sort(key=lambda item: item["defense_id"])
    return grouped


def _review_gaps(candidate: ClaimCandidate, defenses: list, taxonomy: dict) -> list:
    gaps = set()
    allowed_remedies = taxonomy.get(candidate.label)
    if allowed_remedies is None:
        gaps.add("unsupported_claim_label")
    elif any(remedy not in allowed_remedies for remedy in candidate.requested_remedies):
        gaps.add("unsupported_requested_remedy")
    if not candidate.requested_remedies:
        gaps.add("missing_requested_remedy")
    if not defenses:
        gaps.add("missing_respondent_position")
    return sorted(gaps)


def build_claim_matrix(
    taxonomy: dict,
    known_document_ids: Tuple[str, ...],
    claims: Tuple[ClaimCandidate, ...],
    defenses: Tuple[DefenseCandidate, ...],
) -> dict:
    """Assemble claims without guessing labels, remedies, or absent defenses."""
    validated_taxonomy = _validate_taxonomy(taxonomy)
    known_documents = _known_documents(known_document_ids)
    validated_claims = _validate_claims(claims, known_documents)
    grouped_defenses = _validate_defenses(
        defenses,
        known_documents,
        set(validated_claims),
    )
    labels = _taxonomy_map(validated_taxonomy)
    output = []
    for claim_id in sorted(validated_claims):
        candidate, source = validated_claims[claim_id]
        respondent_positions = grouped_defenses[claim_id]
        review_gaps = _review_gaps(candidate, respondent_positions, labels)
        output.append(
            {
                "claim_id": candidate.claim_id,
                "label": candidate.label,
                "claimant_position": {
                    "summary": candidate.claimant_position,
                    **source,
                },
                "respondent_positions": respondent_positions,
                "requested_remedies": sorted(candidate.requested_remedies),
                "contested_facts": sorted(candidate.contested_facts),
                "legal_issues": sorted(candidate.legal_issues),
                "status": "needs_human_review" if review_gaps else "mapped",
                "review_gaps": review_gaps,
            }
        )
    return {
        "schema_version": 1,
        "taxonomy_version": validated_taxonomy["taxonomy_version"],
        "claims": output,
    }
