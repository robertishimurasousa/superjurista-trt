#!/usr/bin/env python3
"""Fail closed unless claims, reasoning, dispositions, and draft are congruent."""

from __future__ import annotations

import re
from pathlib import Path

from schema_validation import ContractError, load_json, validate_schema_value


DEFAULT_REPORT_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "pipelines"
    / "decision-congruence-report.v1.schema.json"
)
CLAIM_ID_PATTERN = re.compile(r"CLM-[0-9]{3,}")
ANALYSIS_ID_PATTERN = re.compile(r"ANL-[0-9]{3,}")
DISPOSITION_ID_PATTERN = re.compile(r"DSP-[0-9]{3,}")
OUTCOMES = {
    "granted",
    "denied",
    "granted_in_part",
    "dismissed_without_merits",
    "procedural_resolution",
    "pending_human_review",
    "abstained",
}


class DecisionCongruenceError(ValueError):
    """Raised when a decision artifact cannot pass the congruence gate."""


def validate_decision_congruence(
    known_claim_ids: tuple[str, ...],
    claim_analysis: dict,
    disposition_matrix: dict,
    judgment_draft: str,
    *,
    report_schema: Path = DEFAULT_REPORT_SCHEMA,
) -> dict:
    """Return a passing custody report or raise on the first unsafe divergence."""
    claims = _known_claims(known_claim_ids)
    analyses = _index_analyses(claim_analysis, claims)
    dispositions = _index_dispositions(disposition_matrix, claims, analyses)
    _validate_draft(judgment_draft, claims, analyses, dispositions)

    total = len(claims)
    complete = {"covered": total, "total": total, "percent": 100}
    report = {
        "schema_version": 1,
        "status": "passed",
        "claim_count": total,
        "coverage": {
            "analysis": dict(complete),
            "disposition": dict(complete),
            "draft": dict(complete),
        },
        "links": [
            {
                "claim_id": claim_id,
                "analysis_id": analyses[claim_id]["analysis_id"],
                "disposition_id": dispositions[claim_id]["disposition_id"],
                "outcome": analyses[claim_id]["proposed_outcome"],
            }
            for claim_id in sorted(claims)
        ],
    }
    try:
        schema = load_json(report_schema, "decision congruence report schema")
    except ContractError as error:
        raise DecisionCongruenceError(str(error)) from error
    errors = validate_schema_value(report, schema)
    if errors:
        raise DecisionCongruenceError(
            "decision congruence report contract failed: " + "; ".join(errors)
        )
    return report


def _known_claims(values: object) -> set[str]:
    if not isinstance(values, tuple) or not values:
        raise DecisionCongruenceError("known claim identifiers must be a non-empty tuple")
    claims = set()
    for value in values:
        claim_id = _identifier(value, CLAIM_ID_PATTERN, "claim identifier")
        if claim_id in claims:
            raise DecisionCongruenceError(f"duplicate known claim: {claim_id}")
        claims.add(claim_id)
    return claims


def _index_analyses(artifact: object, claims: set[str]) -> dict:
    items = _artifact_items(artifact, "analyses", "claim analysis")
    by_claim = {}
    analysis_ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise DecisionCongruenceError("claim analysis item must be an object")
        claim_id = _identifier(item.get("claim_id"), CLAIM_ID_PATTERN, "claim_id")
        analysis_id = _identifier(
            item.get("analysis_id"), ANALYSIS_ID_PATTERN, "analysis_id"
        )
        if claim_id not in claims:
            raise DecisionCongruenceError(
                f"analysis references unknown claim {claim_id}"
            )
        if claim_id in by_claim:
            raise DecisionCongruenceError(f"duplicate analysis claim: {claim_id}")
        if analysis_id in analysis_ids:
            raise DecisionCongruenceError(f"duplicate analysis identifier: {analysis_id}")
        reasoning = item.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise DecisionCongruenceError(
                f"analysis reasoning must be non-empty for {claim_id}"
            )
        if item.get("proposed_outcome") not in OUTCOMES:
            raise DecisionCongruenceError(
                f"analysis outcome is unsupported for {claim_id}"
            )
        by_claim[claim_id] = item
        analysis_ids.add(analysis_id)
    missing = sorted(claims - set(by_claim))
    if missing:
        raise DecisionCongruenceError(f"missing analysis for claim {missing[0]}")
    return by_claim


def _index_dispositions(
    artifact: object,
    claims: set[str],
    analyses: dict,
) -> dict:
    items = _artifact_items(artifact, "items", "disposition matrix")
    by_claim = {}
    disposition_ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise DecisionCongruenceError("disposition item must be an object")
        claim_id = _identifier(item.get("claim_id"), CLAIM_ID_PATTERN, "claim_id")
        disposition_id = _identifier(
            item.get("disposition_id"),
            DISPOSITION_ID_PATTERN,
            "disposition_id",
        )
        source_analysis_id = _identifier(
            item.get("source_analysis_id"),
            ANALYSIS_ID_PATTERN,
            "source_analysis_id",
        )
        if claim_id not in claims:
            raise DecisionCongruenceError(
                f"disposition references unknown claim {claim_id}"
            )
        if claim_id in by_claim:
            raise DecisionCongruenceError(f"duplicate disposition claim: {claim_id}")
        if disposition_id in disposition_ids:
            raise DecisionCongruenceError(
                f"duplicate disposition identifier: {disposition_id}"
            )
        analysis = analyses[claim_id]
        if source_analysis_id != analysis["analysis_id"]:
            raise DecisionCongruenceError(
                f"source analysis {source_analysis_id} does not match claim {claim_id}"
            )
        if item.get("outcome") != analysis["proposed_outcome"]:
            raise DecisionCongruenceError(
                f"disposition outcome does not match analysis for {claim_id}"
            )
        by_claim[claim_id] = item
        disposition_ids.add(disposition_id)
    missing = sorted(claims - set(by_claim))
    if missing:
        raise DecisionCongruenceError(f"missing disposition for claim {missing[0]}")
    return by_claim


def _artifact_items(artifact: object, field: str, label: str) -> list:
    if not isinstance(artifact, dict):
        raise DecisionCongruenceError(f"{label} must be an object")
    if artifact.get("schema_version") != 1:
        raise DecisionCongruenceError(f"{label} schema_version must be 1")
    items = artifact.get(field)
    if not isinstance(items, list) or not items:
        raise DecisionCongruenceError(f"{label} must contain {field}")
    return items


def _validate_draft(
    draft: object,
    claims: set[str],
    analyses: dict,
    dispositions: dict,
) -> None:
    if not isinstance(draft, str) or not draft.strip():
        raise DecisionCongruenceError("judgment draft must be a non-empty string")
    expected_ids = {
        "claim": claims,
        "analysis": {item["analysis_id"] for item in analyses.values()},
        "disposition": {
            item["disposition_id"] for item in dispositions.values()
        },
    }
    patterns = {
        "claim": CLAIM_ID_PATTERN,
        "analysis": ANALYSIS_ID_PATTERN,
        "disposition": DISPOSITION_ID_PATTERN,
    }
    for label, pattern in patterns.items():
        unknown = sorted(set(pattern.findall(draft)) - expected_ids[label])
        if unknown:
            raise DecisionCongruenceError(
                f"draft contains unknown {label} identifier {unknown[0]}"
            )
    for claim_id in sorted(claims):
        analysis_id = analyses[claim_id]["analysis_id"]
        disposition_id = dispositions[claim_id]["disposition_id"]
        _require_line_once(draft, f"### {claim_id}", f"foundation for {claim_id}")
        _require_line_once(
            draft,
            f"Análise: {analysis_id}",
            f"analysis reference for {analysis_id}",
        )
        _require_line_once(
            draft,
            f"### {disposition_id} — {claim_id}",
            f"disposition for {disposition_id}",
        )
        _require_line_once(
            draft,
            f"Análise de origem: {analysis_id}",
            f"source analysis reference for {analysis_id}",
        )


def _require_line_once(draft: str, line: str, label: str) -> None:
    occurrences = sum(1 for candidate in draft.splitlines() if candidate == line)
    if occurrences != 1:
        raise DecisionCongruenceError(
            f"draft {label} must occur exactly once; found {occurrences}"
        )


def _identifier(value: object, pattern: re.Pattern, label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise DecisionCongruenceError(f"{label} is invalid")
    return value
