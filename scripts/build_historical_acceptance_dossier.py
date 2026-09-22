#!/usr/bin/env python3
"""Build a source-bound TRT12 historical acceptance dossier."""

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


class HistoricalDossierError(ValueError):
    """Raised when historical evidence cannot support the requested recommendation."""


def build_acceptance_dossier(
    *,
    development_report: dict,
    holdout_report: dict,
    rerun_report: dict,
    dossier_review: dict,
    protocol_path: Path,
    protocol_schema_path: Path,
    reviewer_form_path: Path,
    scoring_report_schema_path: Path,
    rerun_report_schema_path: Path,
    dossier_review_schema_path: Path,
    dossier_schema_path: Path,
) -> dict:
    """Build one deterministic go/no-go dossier without granting external actions."""
    try:
        protocol_evidence = validate_historical_protocol(
            protocol_path,
            protocol_schema_path,
            reviewer_form_path,
        )
        scoring_schema = load_json(
            scoring_report_schema_path,
            "historical scoring report schema",
        )
        rerun_schema = load_json(
            rerun_report_schema_path,
            "historical rerun report schema",
        )
        review_schema = load_json(
            dossier_review_schema_path,
            "historical dossier review schema",
        )
        dossier_schema = load_json(
            dossier_schema_path,
            "historical acceptance dossier schema",
        )
    except (ContractError, HistoricalProtocolError) as error:
        raise HistoricalDossierError(str(error)) from error

    _validate_contract(development_report, scoring_schema, "development report")
    _validate_contract(holdout_report, scoring_schema, "holdout report")
    _validate_contract(rerun_report, rerun_schema, "rerun report")
    _validate_contract(dossier_review, review_schema, "dossier review")
    _validate_protocol_binding(
        (development_report, holdout_report, rerun_report),
        protocol_evidence,
    )
    if development_report["phase"] != "development":
        raise HistoricalDossierError("development phase is not preserved")
    if holdout_report["phase"] != "untouched_holdout":
        raise HistoricalDossierError("holdout phase is not preserved")

    development_digest = _digest(development_report)
    holdout_digest = _digest(holdout_report)
    if rerun_report["development_report_digest"] != development_digest:
        raise HistoricalDossierError("rerun development digest does not match")
    if rerun_report["holdout_report_digest"] != holdout_digest:
        raise HistoricalDossierError("rerun holdout digest does not match")
    if rerun_report["baseline_revision"] != development_report["system_revision"]:
        raise HistoricalDossierError("dossier baseline revision does not match")
    if rerun_report["corrected_revision"] != holdout_report["system_revision"]:
        raise HistoricalDossierError("dossier corrected revision does not match")

    development_partition = development_report["partitions"][0]
    holdout_partition = holdout_report["partitions"][0]
    material_holdout_defects = (
        holdout_partition["defects"]["critical"]
        + holdout_partition["defects"]["high"]
    )
    recommendation = dossier_review["recommendation"]
    if recommendation == "go_controlled_pilot":
        if holdout_report["status"] != "passed" or material_holdout_defects:
            raise HistoricalDossierError(
                "go recommendation is forbidden with a failed or material holdout defect"
            )
        if rerun_report["status"] != "passed":
            raise HistoricalDossierError("go recommendation requires a passing rerun report")

    approval = dossier_review["approval"]
    _validate_approval(approval)
    status = _dossier_status(recommendation, approval["status"])
    dossier = {
        "schema_version": 1,
        "protocol_id": protocol_evidence["protocol_id"],
        "protocol_digest": protocol_evidence["protocol_digest"],
        "scope": "trt12_first_instance_local_human_supervised",
        "external_actions_allowed": False,
        "status": status,
        "source_evidence": {
            "development_report_digest": development_digest,
            "holdout_report_digest": holdout_digest,
            "rerun_report_digest": _digest(rerun_report),
            "baseline_revision": rerun_report["baseline_revision"],
            "corrected_revision": rerun_report["corrected_revision"],
        },
        "development_results": _phase_results(
            development_report,
            development_partition,
        ),
        "holdout_results": _phase_results(holdout_report, holdout_partition),
        "correction_results": {
            "required_count": rerun_report["required_correction_count"],
            "closed_count": rerun_report["closed_correction_count"],
        },
        "limitations": dossier_review["limitations"],
        "failure_modes": dossier_review["failure_modes"],
        "recommendation": recommendation,
        "recommendation_reasons": dossier_review["recommendation_reasons"],
        "reviewer_id": dossier_review["reviewer_id"],
        "approval": approval,
    }
    _validate_contract(dossier, dossier_schema, "historical acceptance dossier")
    return dossier


def _phase_results(report: dict, partition: dict) -> dict:
    return {
        "status": report["status"],
        "case_count": report["case_count"],
        "claim_review_count": report["claim_review_count"],
        "metrics": partition["metrics"],
        "defects": partition["defects"],
    }


def _validate_contract(value: dict, schema: dict, label: str) -> None:
    issues = validate_schema_value(value, schema)
    if issues:
        raise HistoricalDossierError(f"{label} contract failed: " + "; ".join(issues))


def _validate_protocol_binding(values: tuple[dict, ...], evidence: dict) -> None:
    for value in values:
        if value["protocol_id"] != evidence["protocol_id"]:
            raise HistoricalDossierError("historical dossier protocol identifier changed")
        if value["protocol_digest"] != evidence["protocol_digest"]:
            raise HistoricalDossierError("historical dossier protocol digest changed")


def _validate_approval(approval: dict) -> None:
    decided = approval["status"] in ("approved", "rejected")
    identity = approval["approver"].strip()
    decision_date = approval["decision_date"].strip()
    if decided and (not identity or not decision_date):
        raise HistoricalDossierError(
            "approval identity and decision date are required for a decision"
        )
    if not decided and (identity or decision_date):
        raise HistoricalDossierError(
            "pending approval cannot contain an approver or decision date"
        )


def _dossier_status(recommendation: str, approval_status: str) -> str:
    if recommendation == "no_go" or approval_status == "rejected":
        return "no_go"
    if approval_status == "approved":
        return "approved_for_controlled_pilot"
    return "pending_approval"


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
    validation = root / "runtime" / "validation"
    parser = argparse.ArgumentParser(
        description="Build a source-bound historical validation acceptance dossier.",
    )
    parser.add_argument("--development-report", required=True, type=Path)
    parser.add_argument("--holdout-report", required=True, type=Path)
    parser.add_argument("--rerun-report", required=True, type=Path)
    parser.add_argument("--dossier-review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=validation / "historical-validation-protocol.v1.json",
    )
    parser.add_argument(
        "--protocol-schema",
        type=Path,
        default=validation / "historical-validation-protocol.v1.schema.json",
    )
    parser.add_argument(
        "--reviewer-form",
        type=Path,
        default=root / "spec" / "validation" / "historical-blind-review-form.md",
    )
    parser.add_argument(
        "--scoring-report-schema",
        type=Path,
        default=validation / "historical-review-report.v1.schema.json",
    )
    parser.add_argument(
        "--rerun-report-schema",
        type=Path,
        default=validation / "historical-rerun-report.v1.schema.json",
    )
    parser.add_argument(
        "--dossier-review-schema",
        type=Path,
        default=validation / "historical-dossier-review.v1.schema.json",
    )
    parser.add_argument(
        "--dossier-schema",
        type=Path,
        default=validation / "historical-acceptance-dossier.v1.schema.json",
    )
    return parser


def main(argv: list[str] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        development = load_json(args.development_report, "development report")
        holdout = load_json(args.holdout_report, "holdout report")
        rerun = load_json(args.rerun_report, "rerun report")
        review = load_json(args.dossier_review, "dossier review")
        dossier = build_acceptance_dossier(
            development_report=development,
            holdout_report=holdout,
            rerun_report=rerun,
            dossier_review=review,
            protocol_path=args.protocol,
            protocol_schema_path=args.protocol_schema,
            reviewer_form_path=args.reviewer_form,
            scoring_report_schema_path=args.scoring_report_schema,
            rerun_report_schema_path=args.rerun_report_schema,
            dossier_review_schema_path=args.dossier_review_schema,
            dossier_schema_path=args.dossier_schema,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(dossier, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (ContractError, HistoricalDossierError, OSError) as error:
        print(f"[ERROR] historical dossier: {error}", file=sys.stderr)
        return 2
    print(f"[OK] historical dossier: status={dossier['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
