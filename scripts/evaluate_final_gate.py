#!/usr/bin/env python3
"""Evaluate and enforce the pipeline's deterministic final acceptance gate."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from schema_validation import ContractError, load_json, validate_schema_value


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLAIM_ANALYSIS_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "claim-analysis.v1.schema.json"
)
DEFAULT_DISPOSITION_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "disposition-matrix.v1.schema.json"
)
DEFAULT_CONGRUENCE_SCHEMA = (
    ROOT / "runtime" / "pipelines" / "decision-congruence-report.v1.schema.json"
)
DEFAULT_FINAL_REVIEW_SCHEMA = (
    ROOT / "runtime" / "pipelines" / "final-review.v1.schema.json"
)
DEFAULT_GLOBAL_GATE_SCHEMA = (
    ROOT / "runtime" / "pipelines" / "global-gate.v1.schema.json"
)
QUOTE_PATTERN = re.compile(r'"([^"]+)"|“([^”]+)”', re.DOTALL)
MINIMUM_QUOTE_LENGTH = 60


class FinalGateContractError(ValueError):
    """Raised when the final gate inputs or output violate their contracts."""


class FinalGateRejected(RuntimeError):
    """Raised when a valid global-gate report does not authorize continuation."""


def evaluate_final_gate(
    claim_analysis: dict,
    disposition_matrix: dict,
    judgment_draft: str,
    congruence_report: dict,
    final_review: dict,
    *,
    claim_analysis_schema: Path = DEFAULT_CLAIM_ANALYSIS_SCHEMA,
    disposition_schema: Path = DEFAULT_DISPOSITION_SCHEMA,
    congruence_schema: Path = DEFAULT_CONGRUENCE_SCHEMA,
    final_review_schema: Path = DEFAULT_FINAL_REVIEW_SCHEMA,
    global_gate_schema: Path = DEFAULT_GLOBAL_GATE_SCHEMA,
) -> dict:
    """Produce a deterministic report without silently accepting gate failures."""
    _validate_contract(claim_analysis, claim_analysis_schema, "claim analysis")
    _validate_contract(disposition_matrix, disposition_schema, "disposition matrix")
    _validate_contract(final_review, final_review_schema, "final review")
    if not isinstance(judgment_draft, str) or not judgment_draft.strip():
        raise FinalGateContractError("judgment draft must be a non-empty string")

    analyses = _unique_index(claim_analysis["analyses"], "claim_id", "analysis")
    dispositions = _unique_index(
        disposition_matrix["items"], "claim_id", "disposition"
    )
    sources = _unique_index(final_review["sources"], "source_id", "source review")
    calculations = _unique_index(
        final_review["calculations"], "claim_id", "calculation review"
    )
    _validate_review_states(sources, calculations)

    issues = []
    issues.extend(
        _congruence_issues(
            congruence_report,
            congruence_schema,
            analyses,
            dispositions,
        )
    )
    quotations = _regulated_quotations(judgment_draft)
    issues.extend(_citation_issues(quotations, sources))
    issues.extend(_source_issues(analyses, sources))
    issues.extend(_calculation_issues(dispositions, calculations))

    checks = {
        "congruence": _check_status(issues, {"congruence_not_passed"}),
        "citations": _check_status(issues, {"unsupported_quotation"}),
        "sources": _check_status(
            issues,
            {"missing_source_review"},
            blocked={"source_unavailable"},
        ),
        "calculations": _check_status(
            issues,
            {
                "missing_calculation_review",
                "calculation_mismatch",
                "calculation_status_mismatch",
            },
            blocked={"calculation_unavailable"},
        ),
    }
    status = "passed"
    if any(value == "blocked" for value in checks.values()):
        status = "blocked"
    elif any(value == "failed" for value in checks.values()):
        status = "failed"
    report = {
        "schema_version": 1,
        "status": status,
        "checks": checks,
        "quotation_count": len(quotations),
        "issues": issues,
    }
    _validate_contract(report, global_gate_schema, "global gate")
    return report


def require_final_acceptance(report: dict) -> None:
    """Reject pipeline continuation unless a schema-valid report passed."""
    _validate_contract(report, DEFAULT_GLOBAL_GATE_SCHEMA, "global gate")
    if report["status"] != "passed" or any(
        status != "passed" for status in report["checks"].values()
    ):
        codes = ", ".join(issue["code"] for issue in report["issues"])
        raise FinalGateRejected(f"final gate {report['status']}: {codes}")


def _validate_contract(value: object, schema_path: Path, label: str) -> None:
    try:
        schema = load_json(schema_path, f"{label} schema")
    except ContractError as error:
        raise FinalGateContractError(str(error)) from error
    errors = validate_schema_value(value, schema)
    if errors:
        raise FinalGateContractError(f"{label} contract failed: {'; '.join(errors)}")


def _unique_index(items: list, field: str, label: str) -> dict:
    index = {}
    for item in items:
        identifier = item[field]
        if identifier in index:
            raise FinalGateContractError(f"duplicate {label}: {identifier}")
        index[identifier] = item
    return index


def _validate_review_states(sources: dict, calculations: dict) -> None:
    for source_id, source in sources.items():
        status = source["status"]
        excerpt = source["verbatim_excerpt"].strip()
        reason = source["unavailability_reason"].strip()
        if status == "available" and (not excerpt or reason):
            raise FinalGateContractError(
                f"source {source_id} available state requires excerpt and no reason"
            )
        if status == "unavailable" and (excerpt or not reason):
            raise FinalGateContractError(
                f"source {source_id} unavailable state requires reason and no excerpt"
            )
    for claim_id, calculation in calculations.items():
        status = calculation["status"]
        criteria = calculation["criteria"]
        reason = calculation["unavailability_reason"].strip()
        valid = (
            (status == "completed" and bool(criteria) and not reason)
            or (status == "not_required" and not criteria and not reason)
            or (status == "unavailable" and not criteria and bool(reason))
        )
        if not valid:
            raise FinalGateContractError(
                f"calculation {claim_id} state is inconsistent"
            )


def _congruence_issues(
    report: object,
    schema_path: Path,
    analyses: dict,
    dispositions: dict,
) -> list[dict]:
    try:
        schema = load_json(schema_path, "decision congruence report schema")
        errors = validate_schema_value(report, schema)
    except ContractError as error:
        errors = [str(error)]
    if errors or not isinstance(report, dict) or report.get("status") != "passed":
        return [_issue("congruence_not_passed", "global", "Upstream report failed")]
    if set(analyses) != set(dispositions):
        return [
            _issue(
                "congruence_not_passed",
                "global",
                "Analysis and disposition claims do not match",
            )
        ]
    expected_links = [
        {
            "claim_id": claim_id,
            "analysis_id": analyses[claim_id]["analysis_id"],
            "disposition_id": dispositions[claim_id]["disposition_id"],
            "outcome": analyses[claim_id]["proposed_outcome"],
        }
        for claim_id in sorted(analyses)
    ]
    if report["links"] != expected_links:
        return [
            _issue(
                "congruence_not_passed",
                "global",
                "Upstream links do not match final artifacts",
            )
        ]
    return []


def _regulated_quotations(draft: str) -> list[str]:
    quotations = []
    for match in QUOTE_PATTERN.finditer(draft):
        quotation = match.group(1) or match.group(2)
        if len(_normalize(quotation)) >= MINIMUM_QUOTE_LENGTH:
            quotations.append(quotation)
    return quotations


def _citation_issues(quotations: list[str], sources: dict) -> list[dict]:
    corpus = [
        _normalize(source["verbatim_excerpt"])
        for source in sources.values()
        if source["status"] == "available"
    ]
    issues = []
    for index, quotation in enumerate(quotations, start=1):
        normalized = _normalize(quotation)
        if not any(normalized in excerpt for excerpt in corpus):
            issues.append(
                _issue(
                    "unsupported_quotation",
                    f"QUOTE-{index:03d}",
                    "Quotation is absent from every available verbatim source",
                )
            )
    return issues


def _source_issues(analyses: dict, sources: dict) -> list[dict]:
    referenced = sorted(
        {
            source_id
            for analysis in analyses.values()
            for source_id in analysis["precedent_source_ids"]
        }
    )
    issues = []
    for source_id in referenced:
        review = sources.get(source_id)
        if review is None:
            issues.append(
                _issue(
                    "missing_source_review",
                    source_id,
                    "Referenced source has no final review record",
                )
            )
        elif review["status"] == "unavailable":
            issues.append(
                _issue(
                    "source_unavailable",
                    source_id,
                    review["unavailability_reason"],
                )
            )
    return issues


def _calculation_issues(dispositions: dict, calculations: dict) -> list[dict]:
    issues = []
    for claim_id in sorted(dispositions):
        review = calculations.get(claim_id)
        if review is None:
            issues.append(
                _issue(
                    "missing_calculation_review",
                    claim_id,
                    "Claim has no final calculation review",
                )
            )
            continue
        if review["status"] == "unavailable":
            issues.append(
                _issue(
                    "calculation_unavailable",
                    claim_id,
                    review["unavailability_reason"],
                )
            )
        expected = sorted(dispositions[claim_id]["calculation_criteria"])
        actual = sorted(review["criteria"])
        if actual != expected:
            issues.append(
                _issue(
                    "calculation_mismatch",
                    claim_id,
                    "Review criteria differ from the disposition",
                )
            )
        expected_status = "completed" if expected else "not_required"
        if review["status"] not in {expected_status, "unavailable"}:
            issues.append(
                _issue(
                    "calculation_status_mismatch",
                    claim_id,
                    f"Expected calculation status {expected_status}",
                )
            )
    for claim_id in sorted(set(calculations) - set(dispositions)):
        issues.append(
            _issue(
                "calculation_status_mismatch",
                claim_id,
                "Calculation review references an unknown disposition claim",
            )
        )
    return issues


def _check_status(
    issues: list[dict],
    failed: set[str],
    *,
    blocked: set[str] = frozenset(),
) -> str:
    codes = {issue["code"] for issue in issues}
    if codes & blocked:
        return "blocked"
    if codes & failed:
        return "failed"
    return "passed"


def _issue(code: str, subject_id: str, detail: str) -> dict:
    return {"code": code, "subject_id": subject_id, "detail": detail}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFD", value)
    without_marks = "".join(
        character
        for character in value
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"\s+", " ", without_marks).casefold().strip()
