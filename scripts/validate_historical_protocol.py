#!/usr/bin/env python3
"""Validate the frozen historical-review protocol before outcomes are observed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from schema_validation import ContractError, load_json, validate_schema_value


MINIMUM_THRESHOLDS = {
    "claim_recall": 95,
    "claim_coverage": 100,
    "quotation_support": 100,
    "source_locator_traceability": 100,
}


class HistoricalProtocolError(ValueError):
    """Raised when the validation design is incomplete or can drift post hoc."""


def validate_historical_protocol(
    protocol_path: Path,
    schema_path: Path,
    reviewer_form_path: Path,
) -> dict:
    """Validate protocol semantics, form coverage, and return its frozen digest."""
    try:
        protocol = load_json(protocol_path, "historical validation protocol")
        schema = load_json(schema_path, "historical validation protocol schema")
    except ContractError as error:
        raise HistoricalProtocolError(str(error)) from error
    issues = validate_schema_value(protocol, schema)
    if issues:
        raise HistoricalProtocolError("protocol contract failed: " + "; ".join(issues))
    _validate_sampling(protocol["sampling"])
    _validate_review_design(protocol["review_design"])
    _validate_analysis_plan(protocol["analysis_plan"])
    _validate_reviewer_form(protocol["reviewer_form_fields"], reviewer_form_path)
    digest = hashlib.sha256(
        json.dumps(
            protocol,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "status": "valid",
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": digest,
        "total_cases": protocol["sampling"]["total_cases"],
        "untouched_holdout_cases": protocol["sampling"]["untouched_holdout_cases"],
        "review_field_count": len(protocol["reviewer_form_fields"]),
    }


def _validate_sampling(sampling: dict) -> None:
    total = sampling["total_cases"]
    development = sampling["development_cases"]
    holdout = sampling["untouched_holdout_cases"]
    if development + holdout != total:
        raise HistoricalProtocolError("sample partition must equal total_cases")
    if holdout * 4 < total:
        raise HistoricalProtocolError(
            "untouched holdout must contain at least one quarter of the sample"
        )
    categories = sampling["claim_categories"]
    if len(categories) != len(set(categories)):
        raise HistoricalProtocolError("claim categories must be unique")


def _validate_review_design(review: dict) -> None:
    if review["reviewer_blinded_to_system_output_origin"] is not True:
        raise HistoricalProtocolError("reviewer blinding must remain enabled")
    if not review["disagreement_resolution"].strip():
        raise HistoricalProtocolError("disagreement adjudication must be defined")


def _validate_analysis_plan(plan: dict) -> None:
    thresholds = plan["acceptance_thresholds"]
    for metric, minimum in MINIMUM_THRESHOLDS.items():
        if thresholds[metric] < minimum:
            raise HistoricalProtocolError(
                f"acceptance threshold for {metric} must be at least {minimum}"
            )
    defects = plan["maximum_defects"]
    for severity in ("critical", "high"):
        if defects[severity] != 0:
            raise HistoricalProtocolError(
                f"maximum {severity} defects must remain zero"
            )
    if plan["no_posthoc_threshold_changes"] is not True:
        raise HistoricalProtocolError("posthoc threshold changes are forbidden")


def _validate_reviewer_form(fields: list[str], form_path: Path) -> None:
    try:
        form = form_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise HistoricalProtocolError(f"review form not found: {form_path}") from error
    missing = [field for field in fields if f"<!-- field:{field} -->" not in form]
    if missing:
        raise HistoricalProtocolError(
            "review form is missing frozen field: " + missing[0]
        )
