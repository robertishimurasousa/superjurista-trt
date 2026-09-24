#!/usr/bin/env python3
"""Deterministic baseline classifier for normalized Labor Justice documents."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from schema_validation import ContractError, load_json


DOCUMENT_ID_PATTERN = re.compile(r"DOC-[0-9]{3,}")
TYPE_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
RULE_ID_PATTERN = re.compile(r"[a-z][a-z0-9-]*")


class ClassificationContractViolation(ValueError):
    """Raised when a classification input violates the shared domain contract."""


@dataclass(frozen=True)
class DocumentCandidate:
    document_id: str
    provider_type: str
    title: str
    text_excerpt: str


def _expect_exact_keys(value: dict, expected: set, label: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise ContractError(f"{label} missing field(s): {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{label} has unknown field(s): {', '.join(unknown)}")


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    unaccented = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", unaccented.lower()).split())


def _validate_contract(contract: object) -> Dict[str, object]:
    if not isinstance(contract, dict):
        raise ContractError("labor document classification contract root must be an object")
    _expect_exact_keys(
        contract,
        {"schema_version", "classifier_version", "document_types", "rules"},
        "labor document classification contract",
    )
    if contract["schema_version"] != 2:
        raise ContractError("classification schema_version must be 2")
    if contract["classifier_version"] != 2:
        raise ContractError("classifier_version must be 2")

    document_types = contract["document_types"]
    if not isinstance(document_types, list) or not document_types:
        raise ContractError("document_types must be a non-empty list")
    if any(
        not isinstance(document_type, str)
        or TYPE_PATTERN.fullmatch(document_type) is None
        for document_type in document_types
    ):
        raise ContractError("document_types contains an invalid value")
    if len(document_types) != len(set(document_types)):
        raise ContractError("document_types must contain unique values")
    if "unknown" not in document_types:
        raise ContractError("document_types must include unknown")

    rules = contract["rules"]
    if not isinstance(rules, list) or not rules:
        raise ContractError("classification rules must be a non-empty list")
    seen_rule_ids = set()
    for index, rule in enumerate(rules):
        label = f"rules[{index}]"
        if not isinstance(rule, dict):
            raise ContractError(f"{label} must be an object")
        expected = {"rule_id", "document_type", "priority", "phrases"}
        if "match_fields" in rule:
            expected.add("match_fields")
        _expect_exact_keys(rule, expected, label)
        rule_id = rule["rule_id"]
        if not isinstance(rule_id, str) or RULE_ID_PATTERN.fullmatch(rule_id) is None:
            raise ContractError(f"{label}.rule_id is invalid")
        if rule_id in seen_rule_ids:
            raise ContractError("classification rule_id values must be unique")
        seen_rule_ids.add(rule_id)
        if rule["document_type"] not in document_types or rule["document_type"] == "unknown":
            raise ContractError(f"{label}.document_type is unsupported")
        priority = rule["priority"]
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 1:
            raise ContractError(f"{label}.priority must be a positive integer")
        match_fields = rule.get(
            "match_fields", ["provider_type", "title", "text_excerpt"]
        )
        if (
            not isinstance(match_fields, list)
            or not match_fields
            or any(
                not isinstance(field, str)
                or field not in {"provider_type", "title", "text_excerpt"}
                for field in match_fields
            )
            or len(match_fields) != len(set(match_fields))
        ):
            raise ContractError(f"{label}.match_fields is invalid")
        phrases = rule["phrases"]
        if not isinstance(phrases, list) or not phrases:
            raise ContractError(f"{label}.phrases must be a non-empty list")
        normalized_phrases = []
        for phrase in phrases:
            if not isinstance(phrase, str) or not _normalize(phrase):
                raise ContractError(f"{label}.phrases contains an invalid value")
            normalized_phrases.append(_normalize(phrase))
        if len(normalized_phrases) != len(set(normalized_phrases)):
            raise ContractError(f"{label}.phrases must be unique after normalization")
    return contract


def load_classification_contract(path: Path) -> Dict[str, object]:
    """Load and strictly validate the versioned labor-document taxonomy."""
    return _validate_contract(load_json(path, "labor document classification contract"))


def _validate_candidate(candidate: object) -> DocumentCandidate:
    if not isinstance(candidate, DocumentCandidate):
        raise ClassificationContractViolation("document candidate has an invalid type")
    if DOCUMENT_ID_PATTERN.fullmatch(candidate.document_id) is None:
        raise ClassificationContractViolation("document_id must use DOC-NNN format")
    for field, value in (
        ("provider_type", candidate.provider_type),
        ("title", candidate.title),
        ("text_excerpt", candidate.text_excerpt),
    ):
        if not isinstance(value, str):
            raise ClassificationContractViolation(f"{field} must be a string")
    return candidate


def _matching_rules(contract: dict, candidate: DocumentCandidate) -> list:
    fields = {
        "provider_type": _normalize(candidate.provider_type),
        "title": _normalize(candidate.title),
        "text_excerpt": _normalize(candidate.text_excerpt),
    }
    matches = []
    for rule in contract["rules"]:
        phrases = tuple(_normalize(phrase) for phrase in rule["phrases"])
        match_fields = rule.get("match_fields", fields)
        if any(
            phrase in fields[name]
            for phrase in phrases
            for name in match_fields
            if fields[name]
        ):
            matches.append(rule)
    return matches


def _classify_candidate(contract: dict, candidate: DocumentCandidate) -> dict:
    matches = _matching_rules(contract, candidate)
    if not matches:
        return {
            "document_id": candidate.document_id,
            "document_type": "unknown",
            "classification_status": "unknown",
            "matched_rule_ids": [],
            "reason_code": "no_matching_rule",
        }

    top_priority = max(rule["priority"] for rule in matches)
    top_matches = [rule for rule in matches if rule["priority"] == top_priority]
    matched_rule_ids = sorted(rule["rule_id"] for rule in top_matches)
    matched_types = {rule["document_type"] for rule in top_matches}
    if len(matched_types) != 1:
        return {
            "document_id": candidate.document_id,
            "document_type": "unknown",
            "classification_status": "conflict",
            "matched_rule_ids": matched_rule_ids,
            "reason_code": "conflicting_rules",
        }
    return {
        "document_id": candidate.document_id,
        "document_type": next(iter(matched_types)),
        "classification_status": "classified",
        "matched_rule_ids": matched_rule_ids,
        "reason_code": "matched_rule",
    }


def classify_documents(contract: dict, candidates: Tuple[DocumentCandidate, ...]) -> dict:
    """Classify normalized documents without copying source metadata or text to output."""
    _validate_contract(contract)
    if not isinstance(candidates, tuple):
        raise ClassificationContractViolation("document candidates must be a tuple")
    validated = {}
    for value in candidates:
        candidate = _validate_candidate(value)
        if candidate.document_id in validated:
            raise ClassificationContractViolation("document_id values must be unique")
        validated[candidate.document_id] = candidate

    return {
        "schema_version": contract["schema_version"],
        "classifier_version": contract["classifier_version"],
        "documents": [
            _classify_candidate(contract, validated[document_id])
            for document_id in sorted(validated)
        ],
    }
