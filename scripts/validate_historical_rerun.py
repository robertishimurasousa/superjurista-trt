#!/usr/bin/env python3
"""Validate corrections and the untouched TRT12 historical holdout run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from schema_validation import ContractError, load_json, validate_schema_value
from validate_historical_protocol import (
    HistoricalProtocolError,
    validate_historical_protocol,
)


SEVERITIES = ("critical", "high", "medium", "low")


class HistoricalRerunError(ValueError):
    """Raised when correction or untouched-holdout evidence is incomplete."""


def validate_historical_rerun(
    *,
    development_report: dict,
    holdout_report: dict,
    correction_register: dict,
    protocol_path: Path,
    protocol_schema_path: Path,
    reviewer_form_path: Path,
    scoring_report_schema_path: Path,
    correction_schema_path: Path,
    rerun_report_schema_path: Path,
) -> dict:
    """Bind development defects, closed corrections, and one passing holdout."""
    try:
        protocol = load_json(protocol_path, "historical validation protocol")
        protocol_evidence = validate_historical_protocol(
            protocol_path,
            protocol_schema_path,
            reviewer_form_path,
        )
        scoring_schema = load_json(
            scoring_report_schema_path,
            "historical scoring report schema",
        )
        correction_schema = load_json(
            correction_schema_path,
            "historical correction register schema",
        )
        rerun_schema = load_json(
            rerun_report_schema_path,
            "historical rerun report schema",
        )
    except (ContractError, HistoricalProtocolError) as error:
        raise HistoricalRerunError(str(error)) from error

    _validate_contract(development_report, scoring_schema, "development report")
    _validate_contract(holdout_report, scoring_schema, "holdout report")
    _validate_contract(correction_register, correction_schema, "correction register")
    _validate_protocol_binding(
        (development_report, holdout_report, correction_register),
        protocol_evidence,
    )
    _validate_scoring_report(
        development_report,
        phase="development",
        expected_case_count=protocol["sampling"]["development_cases"],
        protocol=protocol,
    )
    _validate_scoring_report(
        holdout_report,
        phase="untouched_holdout",
        expected_case_count=protocol["sampling"]["untouched_holdout_cases"],
        protocol=protocol,
    )
    if holdout_report["status"] != "passed":
        raise HistoricalRerunError("untouched holdout must pass every frozen gate")
    if development_report["review_batch_digest"] == holdout_report["review_batch_digest"]:
        raise HistoricalRerunError(
            "development and holdout must use distinct review batches"
        )

    development_digest = _digest(development_report)
    if correction_register["development_report_digest"] != development_digest:
        raise HistoricalRerunError("correction register does not bind the development report")
    if correction_register["baseline_revision"] != development_report["system_revision"]:
        raise HistoricalRerunError("baseline revision does not match development evidence")
    if correction_register["corrected_revision"] != holdout_report["system_revision"]:
        raise HistoricalRerunError("corrected revision does not match holdout evidence")

    development_defects = {
        defect["defect_id"]: defect
        for defect in development_report["partitions"][0]["defect_inventory"]
    }
    corrections = _corrections_by_id(correction_register["corrections"])
    for defect_id, correction in corrections.items():
        defect = development_defects.get(defect_id)
        if defect is None:
            raise HistoricalRerunError("correction references an unknown development defect")
        for field in ("severity", "stage", "defect_code"):
            if correction[field] != defect[field]:
                raise HistoricalRerunError(
                    "correction does not preserve development defect custody"
                )
        if correction["status"] != "closed":
            raise HistoricalRerunError("every registered correction must be closed")
        if correction["regression_result"] != "passed":
            raise HistoricalRerunError("every correction regression test must have passed")

    required_ids = {
        defect_id
        for defect_id, defect in development_defects.items()
        if defect["severity"] in ("critical", "high")
    }
    if not required_ids.issubset(corrections):
        raise HistoricalRerunError(
            "every critical or high material defect requires one closed correction"
        )
    if required_ids and (
        correction_register["baseline_revision"]
        == correction_register["corrected_revision"]
    ):
        raise HistoricalRerunError(
            "material corrections require a new corrected revision"
        )

    report = {
        "schema_version": 1,
        "protocol_id": protocol_evidence["protocol_id"],
        "protocol_digest": protocol_evidence["protocol_digest"],
        "status": "passed",
        "development_report_digest": development_digest,
        "holdout_report_digest": _digest(holdout_report),
        "baseline_revision": correction_register["baseline_revision"],
        "corrected_revision": correction_register["corrected_revision"],
        "required_correction_count": len(required_ids),
        "closed_correction_count": len(corrections),
        "development_case_count": development_report["case_count"],
        "holdout_case_count": holdout_report["case_count"],
    }
    _validate_contract(report, rerun_schema, "historical rerun report")
    return report


def _validate_contract(value: dict, schema: dict, label: str) -> None:
    issues = validate_schema_value(value, schema)
    if issues:
        raise HistoricalRerunError(f"{label} contract failed: " + "; ".join(issues))


def _validate_protocol_binding(values: tuple[dict, ...], evidence: dict) -> None:
    for value in values:
        if value["protocol_id"] != evidence["protocol_id"]:
            raise HistoricalRerunError("historical evidence protocol identifier changed")
        if value["protocol_digest"] != evidence["protocol_digest"]:
            raise HistoricalRerunError("historical evidence protocol digest changed")


def _validate_scoring_report(
    report: dict,
    *,
    phase: str,
    expected_case_count: int,
    protocol: dict,
) -> None:
    if report["phase"] != phase:
        label = "development" if phase == "development" else "holdout"
        raise HistoricalRerunError(f"{label} phase is not preserved")
    if report["case_count"] != expected_case_count:
        raise HistoricalRerunError(f"{phase} case count changed")
    if len(report["partitions"]) != 1:
        raise HistoricalRerunError("each scoring report must contain exactly one phase")
    partition = report["partitions"][0]
    if partition["name"] != phase:
        raise HistoricalRerunError("scoring partition does not match its phase")
    if partition["case_count"] != report["case_count"]:
        raise HistoricalRerunError("scoring case counts are inconsistent")
    if partition["claim_review_count"] != report["claim_review_count"]:
        raise HistoricalRerunError("scoring claim counts are inconsistent")

    thresholds = protocol["analysis_plan"]["acceptance_thresholds"]
    expected_thresholds = {
        "claim_recall": thresholds["claim_recall"],
        "claim_coverage": thresholds["claim_coverage"],
        "quotation_support": thresholds["quotation_support"],
        "source_locator_traceability": thresholds["source_locator_traceability"],
        "outcome_congruence": None,
        "calculation_criteria_consistency": None,
    }
    metric_acceptance = True
    for name, metric in partition["metrics"].items():
        if metric["threshold"] != expected_thresholds[name]:
            raise HistoricalRerunError("scoring metric threshold changed")
        if metric["numerator"] > metric["eligible_count"]:
            raise HistoricalRerunError("scoring metric numerator exceeds its denominator")
        if metric["eligible_count"]:
            expected_percent = (
                metric["numerator"] * 100
            ) // metric["eligible_count"]
            if metric["percent"] != expected_percent:
                raise HistoricalRerunError("scoring metric percentage is inconsistent")
        if metric["threshold"] is None:
            if metric["accepted"] is not None:
                raise HistoricalRerunError("diagnostic metric cannot claim acceptance")
            continue
        expected_accepted = (
            metric["percent"] is not None
            and metric["percent"] >= metric["threshold"]
        )
        if metric["accepted"] != expected_accepted:
            raise HistoricalRerunError("scoring metric acceptance is inconsistent")
        metric_acceptance = metric_acceptance and expected_accepted

    inventory = partition["defect_inventory"]
    expected_severities = {
        severity: sum(defect["severity"] == severity for defect in inventory)
        for severity in SEVERITIES
    }
    if partition["defects"] != expected_severities:
        raise HistoricalRerunError("defect severity totals do not match the inventory")
    stage_totals = {
        defect["stage"]: sum(item["stage"] == defect["stage"] for item in inventory)
        for defect in inventory
    }
    reported_stages = {
        item["stage"]: item["count"] for item in partition["defects_by_stage"]
    }
    if reported_stages != stage_totals:
        raise HistoricalRerunError("defect stage totals do not match the inventory")
    maximum_defects = protocol["analysis_plan"]["maximum_defects"]
    defect_acceptance = all(
        expected_severities[severity] <= maximum_defects[severity]
        for severity in SEVERITIES
    )
    if partition["accepted"] != (metric_acceptance and defect_acceptance):
        raise HistoricalRerunError("partition acceptance is inconsistent")
    expected_status = "passed" if partition["accepted"] else "failed"
    if report["status"] != expected_status:
        raise HistoricalRerunError("scoring status does not match its acceptance result")


def _corrections_by_id(corrections: list[dict]) -> dict[str, dict]:
    by_id = {}
    for correction in corrections:
        defect_id = correction["defect_id"]
        if defect_id in by_id:
            raise HistoricalRerunError("correction register repeats a defect identifier")
        by_id[defect_id] = correction
    return by_id


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Validate corrected development evidence and untouched holdout results.",
    )
    parser.add_argument("--development-report", required=True, type=Path)
    parser.add_argument("--holdout-report", required=True, type=Path)
    parser.add_argument("--correction-register", required=True, type=Path)
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
        "--scoring-report-schema",
        type=Path,
        default=root / "runtime" / "validation" / "historical-review-report.v1.schema.json",
    )
    parser.add_argument(
        "--correction-schema",
        type=Path,
        default=(
            root
            / "runtime"
            / "validation"
            / "historical-correction-register.v1.schema.json"
        ),
    )
    parser.add_argument(
        "--rerun-report-schema",
        type=Path,
        default=root / "runtime" / "validation" / "historical-rerun-report.v1.schema.json",
    )
    return parser


def main(argv: list[str] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        development = load_json(args.development_report, "development review report")
        holdout = load_json(args.holdout_report, "untouched holdout report")
        corrections = load_json(args.correction_register, "correction register")
        report = validate_historical_rerun(
            development_report=development,
            holdout_report=holdout,
            correction_register=corrections,
            protocol_path=args.protocol,
            protocol_schema_path=args.protocol_schema,
            reviewer_form_path=args.reviewer_form,
            scoring_report_schema_path=args.scoring_report_schema,
            correction_schema_path=args.correction_schema,
            rerun_report_schema_path=args.rerun_report_schema,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (ContractError, HistoricalRerunError, OSError) as error:
        print(f"[ERROR] historical rerun validation: {error}", file=sys.stderr)
        return 2
    print(
        "[OK] historical rerun validation: "
        f"{report['closed_correction_count']} correction(s); holdout passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
