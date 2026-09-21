#!/usr/bin/env python3
"""Build a deterministic claim-linked evidence matrix with explicit conflicts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple


DOCUMENT_ID_PATTERN = re.compile(r"DOC-[0-9]{3,}")
CLAIM_ID_PATTERN = re.compile(r"CLM-[0-9]{3,}")
EVIDENCE_ID_PATTERN = re.compile(r"EVD-[0-9]{3,}")
LABEL_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
RELATIONS = {"supports_claim", "opposes_claim", "neutral_context"}
ANALYSIS_STATUSES = {"pending", "reviewed", "disputed", "insufficient"}


class EvidenceMatrixContractViolation(ValueError):
    """Raised when evidence inputs violate source or graph integrity."""


@dataclass(frozen=True)
class SourceReference:
    document_id: str
    locator: str


@dataclass(frozen=True)
class EvidenceCandidate:
    evidence_id: str
    claim_ids: Tuple[str, ...]
    evidence_type: str
    proposition: str
    relation: str
    limitations: Tuple[str, ...]
    analysis_status: str
    conflicts_with_evidence_ids: Tuple[str, ...]
    source: SourceReference


def _require_identifier(value: object, pattern: re.Pattern, label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise EvidenceMatrixContractViolation(f"{label} is invalid")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceMatrixContractViolation(f"{label} must be a non-empty string")
    return value


def _require_known_ids(value: object, pattern: re.Pattern, label: str) -> set:
    if not isinstance(value, tuple) or not value:
        raise EvidenceMatrixContractViolation(f"{label} must be a non-empty tuple")
    for identifier in value:
        _require_identifier(identifier, pattern, label)
    if len(value) != len(set(value)):
        raise EvidenceMatrixContractViolation(f"{label} values must be unique")
    return set(value)


def _require_string_tuple(
    value: object,
    label: str,
    *,
    pattern: re.Pattern | None = None,
    minimum: int = 0,
) -> Tuple[str, ...]:
    if not isinstance(value, tuple) or len(value) < minimum:
        raise EvidenceMatrixContractViolation(
            f"{label} must be a tuple with at least {minimum} item(s)"
        )
    for item in value:
        if pattern is None:
            _require_text(item, label)
        else:
            _require_identifier(item, pattern, label)
    if len(value) != len(set(value)):
        raise EvidenceMatrixContractViolation(f"{label} values must be unique")
    return value


def _source_fields(source: object, known_documents: set, label: str) -> dict:
    if not isinstance(source, SourceReference):
        raise EvidenceMatrixContractViolation(f"{label} source reference is invalid")
    _require_identifier(source.document_id, DOCUMENT_ID_PATTERN, f"{label} document_id")
    if source.document_id not in known_documents:
        raise EvidenceMatrixContractViolation(
            f"{label} references unknown document {source.document_id}"
        )
    _require_text(source.locator, f"{label} source locator")
    return {
        "source_document_id": source.document_id,
        "source_locator": source.locator,
    }


def _validate_candidates(
    values: object,
    known_documents: set,
    known_claims: set,
) -> dict:
    if not isinstance(values, tuple):
        raise EvidenceMatrixContractViolation("evidence candidates must be a tuple")
    candidates = {}
    for candidate in values:
        if not isinstance(candidate, EvidenceCandidate):
            raise EvidenceMatrixContractViolation("evidence candidate has an invalid type")
        _require_identifier(candidate.evidence_id, EVIDENCE_ID_PATTERN, "evidence_id")
        if candidate.evidence_id in candidates:
            raise EvidenceMatrixContractViolation("evidence_id values must be unique")
        claim_ids = _require_string_tuple(
            candidate.claim_ids,
            "claim_ids",
            pattern=CLAIM_ID_PATTERN,
            minimum=1,
        )
        unknown_claims = sorted(set(claim_ids) - known_claims)
        if unknown_claims:
            raise EvidenceMatrixContractViolation(
                f"evidence references unknown claim {unknown_claims[0]}"
            )
        _require_identifier(candidate.evidence_type, LABEL_PATTERN, "evidence_type")
        _require_text(candidate.proposition, "proposition")
        if candidate.relation not in RELATIONS:
            raise EvidenceMatrixContractViolation("evidence relation is unsupported")
        limitations = _require_string_tuple(candidate.limitations, "limitations")
        if candidate.analysis_status not in ANALYSIS_STATUSES:
            raise EvidenceMatrixContractViolation("analysis_status is unsupported")
        conflicts = _require_string_tuple(
            candidate.conflicts_with_evidence_ids,
            "conflicts_with_evidence_ids",
            pattern=EVIDENCE_ID_PATTERN,
        )
        if candidate.evidence_id in conflicts:
            raise EvidenceMatrixContractViolation("evidence cannot conflict with itself")
        source = _source_fields(candidate.source, known_documents, candidate.evidence_id)
        candidates[candidate.evidence_id] = {
            "evidence_id": candidate.evidence_id,
            "claim_ids": sorted(claim_ids),
            "type": candidate.evidence_type,
            "source_document_id": source["source_document_id"],
            "source_locator": source["source_locator"],
            "proposition": candidate.proposition,
            "relation": candidate.relation,
            "limitations": sorted(limitations),
            "analysis_status": candidate.analysis_status,
            "conflicts_with_evidence_ids": set(conflicts),
        }
    return candidates


def _normalize_conflicts(candidates: dict) -> None:
    known_evidence = set(candidates)
    for evidence_id, item in candidates.items():
        unknown = sorted(item["conflicts_with_evidence_ids"] - known_evidence)
        if unknown:
            raise EvidenceMatrixContractViolation(
                f"evidence {evidence_id} references unknown conflict {unknown[0]}"
            )
    for evidence_id, item in candidates.items():
        for conflicting_id in tuple(item["conflicts_with_evidence_ids"]):
            candidates[conflicting_id]["conflicts_with_evidence_ids"].add(evidence_id)
    for evidence_id, item in candidates.items():
        if item["conflicts_with_evidence_ids"] and item["analysis_status"] != "disputed":
            raise EvidenceMatrixContractViolation(
                f"evidence {evidence_id} with conflicts must have disputed analysis_status"
            )


def build_evidence_matrix(
    known_document_ids: Tuple[str, ...],
    known_claim_ids: Tuple[str, ...],
    candidates: Tuple[EvidenceCandidate, ...],
) -> dict:
    """Assemble source-linked evidence and expose uncovered claims explicitly."""
    known_documents = _require_known_ids(
        known_document_ids,
        DOCUMENT_ID_PATTERN,
        "known_document_ids",
    )
    known_claims = _require_known_ids(
        known_claim_ids,
        CLAIM_ID_PATTERN,
        "known_claim_ids",
    )
    evidence = _validate_candidates(candidates, known_documents, known_claims)
    _normalize_conflicts(evidence)
    covered_claims = {
        claim_id
        for item in evidence.values()
        for claim_id in item["claim_ids"]
    }
    output = []
    for evidence_id in sorted(evidence):
        item = evidence[evidence_id]
        output.append(
            {
                **{key: value for key, value in item.items() if key != "conflicts_with_evidence_ids"},
                "conflicts_with_evidence_ids": sorted(item["conflicts_with_evidence_ids"]),
            }
        )
    return {
        "schema_version": 1,
        "evidence_items": output,
        "uncovered_claim_ids": sorted(known_claims - covered_claims),
    }
