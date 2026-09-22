#!/usr/bin/env python3
"""Validate and score one frozen TRT12 historical blind-review batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from schema_validation import ContractError, load_json, validate_schema_value
from validate_historical_protocol import (
    HistoricalProtocolError,
    validate_historical_protocol,
)


PARTITIONS = ("development", "untouched_holdout")
SEVERITIES = ("critical", "high", "medium", "low")
DEFECT_STAGES = (
    "acquisition",
    "classification",
    "labor_report",
    "claim_matrix",
    "evidence_matrix",
    "issue_routing",
    "legal_research",
    "claim_analysis",
    "disposition",
    "drafting",
    "calculation",
    "global_gate",
)
UNAVAILABLE_FIELDS = (
    "claim_present_reference",
    "source_locator_correct",
    "reasoning_congruent",
    "disposition_congruent",
    "calculation_criteria_consistent",
)


class HistoricalReviewError(ValueError):
    """Raised when a blind-review batch cannot be scored without guessing."""


def score_review_batch(
    *,
    batch: dict,
    protocol_path: Path,
    protocol_schema_path: Path,
    reviewer_form_path: Path,
    batch_schema_path: Path,
    report_schema_path: Path,
) -> dict:
    """Validate a complete frozen sample and return deterministic partition metrics."""
    try:
        protocol_evidence = validate_historical_protocol(
            protocol_path,
            protocol_schema_path,
            reviewer_form_path,
        )
        protocol = load_json(protocol_path, "historical validation protocol")
        batch_schema = load_json(batch_schema_path, "historical review batch schema")
        report_schema = load_json(report_schema_path, "historical review report schema")
    except (ContractError, HistoricalProtocolError) as error:
        raise HistoricalReviewError(str(error)) from error

    issues = validate_schema_value(batch, batch_schema)
    if issues:
        raise HistoricalReviewError("review batch contract failed: " + "; ".join(issues))
    if batch["protocol_id"] != protocol_evidence["protocol_id"]:
        raise HistoricalReviewError("review batch protocol identifier does not match")
    if batch["protocol_digest"] != protocol_evidence["protocol_digest"]:
        raise HistoricalReviewError("review batch protocol digest does not match")

    ordered_reviews = sorted(
        batch["reviews"],
        key=lambda review: (
            PARTITIONS.index(review["sample_partition"]),
            review["case_id"],
            review["claim_id"],
            review["reviewer_id"],
        ),
    )
    ordered_manifest = sorted(
        batch["case_manifest"],
        key=lambda case: (
            PARTITIONS.index(case["sample_partition"]),
            case["case_id"],
        ),
    )
    _validate_review_semantics(ordered_reviews, protocol)
    phase = batch["phase"]
    _validate_sample(ordered_reviews, ordered_manifest, protocol, phase)

    partitions = [
        _score_partition(
            phase,
            ordered_reviews,
            protocol,
        )
    ]
    canonical_batch = {
        "schema_version": batch["schema_version"],
        "protocol_id": batch["protocol_id"],
        "protocol_digest": batch["protocol_digest"],
        "system_revision": batch["system_revision"],
        "phase": phase,
        "case_manifest": ordered_manifest,
        "reviews": ordered_reviews,
    }
    report = {
        "schema_version": 1,
        "protocol_id": batch["protocol_id"],
        "protocol_digest": batch["protocol_digest"],
        "review_batch_digest": _digest(canonical_batch),
        "system_revision": batch["system_revision"],
        "phase": phase,
        "status": "passed" if all(item["accepted"] for item in partitions) else "failed",
        "case_count": len(ordered_manifest),
        "claim_review_count": len(ordered_reviews),
        "partitions": partitions,
    }
    report_issues = validate_schema_value(report, report_schema)
    if report_issues:
        raise HistoricalReviewError(
            "historical review report contract failed: " + "; ".join(report_issues)
        )
    return report


def _validate_review_semantics(reviews: list[dict], protocol: dict) -> None:
    categories = set(protocol["sampling"]["claim_categories"])
    seen_reviews = set()
    case_reviewers: dict[str, set[str]] = {}
    case_outputs: dict[str, set[str]] = {}
    case_partitions: dict[str, set[str]] = {}

    for review in reviews:
        key = (review["case_id"], review["claim_id"])
        if key in seen_reviews:
            raise HistoricalReviewError("duplicate review for the same case and claim")
        seen_reviews.add(key)
        if review["claim_category"] not in categories:
            raise HistoricalReviewError("review uses a claim category outside the frozen protocol")
        if not review["blind_scoring_completed"] or not review["output_origin_withheld"]:
            raise HistoricalReviewError("blind review attestations must both be true")

        unavailable = any(review[field] == "unavailable" for field in UNAVAILABLE_FIELDS)
        reason = review["unavailable_reason"].strip()
        if unavailable and not reason:
            raise HistoricalReviewError("every unavailable value requires an unavailable reason")
        if not unavailable and reason:
            raise HistoricalReviewError(
                "unavailable reason is forbidden when every reviewed value is available"
            )

        severity = review["severity"]
        defect_code = review["defect_code"].strip()
        defect_description = review["defect_description"].strip()
        if severity == "none":
            if (
                review["defect_stage"] != "none"
                or defect_code
                or defect_description
                or review["adjudication_required"] != "no"
            ):
                raise HistoricalReviewError(
                    "severity none forbids defect stage, defect fields, and adjudication"
                )
        else:
            if review["defect_stage"] == "none":
                raise HistoricalReviewError("a recorded defect requires a defect stage")
            if not defect_code or not defect_description:
                raise HistoricalReviewError("a recorded defect requires code and description")
            if severity in ("critical", "high") and review["adjudication_required"] != "yes":
                raise HistoricalReviewError(
                    "critical and high defects require adjudication"
                )

        case_id = review["case_id"]
        case_reviewers.setdefault(case_id, set()).add(review["reviewer_id"])
        case_outputs.setdefault(case_id, set()).add(review["blind_output_id"])
        case_partitions.setdefault(case_id, set()).add(review["sample_partition"])

    required_reviewers = protocol["review_design"]["independent_reviewers_per_case"]
    for case_id in sorted(case_reviewers):
        if len(case_reviewers[case_id]) != required_reviewers:
            raise HistoricalReviewError(
                "each case must have the frozen number of independent reviewers"
            )
        if len(case_outputs[case_id]) != 1:
            raise HistoricalReviewError("one case cannot reference multiple blind outputs")
        if len(case_partitions[case_id]) != 1:
            raise HistoricalReviewError("one case cannot cross sample partitions")


def _validate_sample(
    reviews: list[dict],
    case_manifest: list[dict],
    protocol: dict,
    phase: str,
) -> None:
    by_case = {}
    blind_outputs = set()
    for case in case_manifest:
        case_id = case["case_id"]
        if case_id in by_case:
            raise HistoricalReviewError("case manifest contains a duplicate case")
        if case["blind_output_id"] in blind_outputs:
            raise HistoricalReviewError("blind output identifiers must be unique by case")
        blind_outputs.add(case["blind_output_id"])
        by_case[case_id] = case

    expected_case_count = {
        "development": protocol["sampling"]["development_cases"],
        "untouched_holdout": protocol["sampling"]["untouched_holdout_cases"],
    }[phase]
    if any(case["sample_partition"] != phase for case in case_manifest):
        raise HistoricalReviewError(
            "one review batch must contain a single frozen phase"
        )
    if len(case_manifest) != expected_case_count:
        raise HistoricalReviewError("phase case count does not match the frozen protocol")

    actual_claims: dict[str, set[str]] = {}
    for review in reviews:
        case = by_case.get(review["case_id"])
        if case is None:
            raise HistoricalReviewError("review references a case outside the frozen manifest")
        if review["sample_partition"] != case["sample_partition"]:
            raise HistoricalReviewError("review partition does not match the case manifest")
        if review["blind_output_id"] != case["blind_output_id"]:
            raise HistoricalReviewError("review output does not match the case manifest")
        if review["reviewer_id"] != case["reviewer_id"]:
            raise HistoricalReviewError("reviewer does not match the case manifest")
        actual_claims.setdefault(review["case_id"], set()).add(review["claim_id"])

    for case_id, case in by_case.items():
        expected_claims = set(case["expected_claim_ids"])
        if actual_claims.get(case_id, set()) != expected_claims:
            raise HistoricalReviewError(
                "reviews must cover the complete frozen claim inventory for every case"
            )


def _score_partition(name: str, reviews: list[dict], protocol: dict) -> dict:
    thresholds = protocol["analysis_plan"]["acceptance_thresholds"]
    metrics = {
        "claim_recall": _metric(
            reviews,
            _claim_recall_state,
            thresholds["claim_recall"],
        ),
        "claim_coverage": _metric(
            reviews,
            _claim_coverage_state,
            thresholds["claim_coverage"],
        ),
        "quotation_support": _metric(
            reviews,
            lambda review: _direct_state(review["quotation_supported"]),
            thresholds["quotation_support"],
            empty_not_applicable_passes=True,
        ),
        "source_locator_traceability": _metric(
            reviews,
            lambda review: _direct_state(review["source_locator_correct"]),
            thresholds["source_locator_traceability"],
        ),
        "outcome_congruence": _metric(reviews, _outcome_state, None),
        "calculation_criteria_consistency": _metric(
            reviews,
            lambda review: _direct_state(review["calculation_criteria_consistent"]),
            None,
        ),
    }
    defects = {
        severity: sum(review["severity"] == severity for review in reviews)
        for severity in SEVERITIES
    }
    maximum_defects = protocol["analysis_plan"]["maximum_defects"]
    defects_by_stage = [
        {
            "stage": stage,
            "count": sum(
                review["severity"] != "none" and review["defect_stage"] == stage
                for review in reviews
            ),
        }
        for stage in DEFECT_STAGES
    ]
    defects_by_stage = [item for item in defects_by_stage if item["count"]]
    defect_inventory = sorted(
        (
            {
                "defect_id": _defect_id(review),
                "case_id": review["case_id"],
                "claim_id": review["claim_id"],
                "severity": review["severity"],
                "stage": review["defect_stage"],
                "defect_code": review["defect_code"],
            }
            for review in reviews
            if review["severity"] != "none"
        ),
        key=lambda defect: defect["defect_id"],
    )
    metrics_accepted = all(
        metric["accepted"] is not False
        for metric in metrics.values()
        if metric["threshold"] is not None
    )
    defects_accepted = all(
        defects[severity] <= maximum_defects[severity]
        for severity in SEVERITIES
    )
    return {
        "name": name,
        "case_count": len({review["case_id"] for review in reviews}),
        "claim_review_count": len(reviews),
        "unavailable_review_count": sum(
            any(review[field] == "unavailable" for field in UNAVAILABLE_FIELDS)
            for review in reviews
        ),
        "metrics": metrics,
        "defects": defects,
        "defects_by_stage": defects_by_stage,
        "defect_inventory": defect_inventory,
        "accepted": metrics_accepted and defects_accepted,
    }


def _metric(
    reviews: list[dict],
    classifier: Callable[[dict], str],
    threshold: Optional[int],
    *,
    empty_not_applicable_passes: bool = False,
) -> dict:
    states = [classifier(review) for review in reviews]
    numerator = states.count("pass")
    failures = states.count("fail")
    eligible = numerator + failures
    excluded = states.count("unavailable")
    not_applicable = states.count("not_applicable")
    percent = (numerator * 100) // eligible if eligible else None
    if eligible == 0 and empty_not_applicable_passes and not_applicable:
        percent = 100
    accepted = None if threshold is None else percent is not None and percent >= threshold
    return {
        "numerator": numerator,
        "eligible_count": eligible,
        "excluded_count": excluded,
        "not_applicable_count": not_applicable,
        "percent": percent,
        "threshold": threshold,
        "accepted": accepted,
    }


def _claim_recall_state(review: dict) -> str:
    reference = review["claim_present_reference"]
    if reference == "unavailable":
        return "unavailable"
    if reference == "no":
        return "not_applicable"
    return "pass" if review["claim_present_system"] == "yes" else "fail"


def _claim_coverage_state(review: dict) -> str:
    reference = review["claim_present_reference"]
    if reference == "unavailable":
        return "unavailable"
    if reference == "no":
        return "not_applicable"
    if review["claim_present_system"] == "no":
        return "fail"
    values = (review["reasoning_congruent"], review["disposition_congruent"])
    if "unavailable" in values:
        return "unavailable"
    return "pass" if values == ("yes", "yes") else "fail"


def _outcome_state(review: dict) -> str:
    reference = review["claim_present_reference"]
    if reference == "unavailable":
        return "unavailable"
    if reference == "no":
        return "not_applicable"
    values = (review["reasoning_congruent"], review["disposition_congruent"])
    if "unavailable" in values:
        return "unavailable"
    return "pass" if values == ("yes", "yes") else "fail"


def _direct_state(value: str) -> str:
    return {
        "yes": "pass",
        "no": "fail",
        "not_applicable": "not_applicable",
        "unavailable": "unavailable",
    }[value]


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _defect_id(review: dict) -> str:
    identity = {
        "case_id": review["case_id"],
        "claim_id": review["claim_id"],
        "reviewer_id": review["reviewer_id"],
        "stage": review["defect_stage"],
        "defect_code": review["defect_code"],
    }
    return "DEFECT-" + _digest(identity)[:16].upper()


def _parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Validate and score one frozen historical blind-review batch.",
    )
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=root / "runtime" / "validation" / "historical-validation-protocol.v1.json",
    )
    parser.add_argument(
        "--protocol-schema",
        type=Path,
        default=(
            root
            / "runtime"
            / "validation"
            / "historical-validation-protocol.v1.schema.json"
        ),
    )
    parser.add_argument(
        "--reviewer-form",
        type=Path,
        default=root / "spec" / "validation" / "historical-blind-review-form.md",
    )
    parser.add_argument(
        "--batch-schema",
        type=Path,
        default=root / "runtime" / "validation" / "historical-review-batch.v1.schema.json",
    )
    parser.add_argument(
        "--report-schema",
        type=Path,
        default=root / "runtime" / "validation" / "historical-review-report.v1.schema.json",
    )
    return parser


def main(argv: list[str] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        batch = load_json(args.batch, "historical review batch")
        report = score_review_batch(
            batch=batch,
            protocol_path=args.protocol,
            protocol_schema_path=args.protocol_schema,
            reviewer_form_path=args.reviewer_form,
            batch_schema_path=args.batch_schema,
            report_schema_path=args.report_schema,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (ContractError, HistoricalReviewError, OSError) as error:
        print(f"[ERROR] historical review scoring: {error}", file=sys.stderr)
        return 2
    print(
        "[OK] historical review scoring: "
        f"{report['case_count']} cases; status={report['status']}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
