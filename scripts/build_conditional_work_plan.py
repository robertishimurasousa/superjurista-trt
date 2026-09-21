#!/usr/bin/env python3
"""Build claim-scoped conditional work without dispatching unrequested tracks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from schema_validation import ContractError, load_json, validate_schema_value


DEFAULT_ISSUE_ROUTE_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "contracts"
    / "schemas"
    / "issue-route.v1.schema.json"
)
DEFAULT_WORK_PLAN_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "pipelines"
    / "conditional-work-plan.v1.schema.json"
)
TRACKS = (
    ("requires_legal_research", "legal_research", "LEGAL", "research_questions"),
    (
        "requires_evidence_analysis",
        "evidence_analysis",
        "EVIDENCE",
        "evidence_questions",
    ),
    (
        "requires_calculation_review",
        "calculation_review",
        "CALCULATION",
        None,
    ),
    (
        "requires_procedural_review",
        "procedural_review",
        "PROCEDURAL",
        None,
    ),
)


class ConditionalWorkPlanError(ValueError):
    """Raised when claim routing cannot safely produce conditional work."""


@dataclass(frozen=True)
class WorkDispatch:
    work_id: str
    claim_id: str
    track: str
    questions: tuple[str, ...]
    route_reason: str


def build_conditional_work_plan(
    issue_routes: dict,
    *,
    issue_route_schema: Path = DEFAULT_ISSUE_ROUTE_SCHEMA,
    work_plan_schema: Path = DEFAULT_WORK_PLAN_SCHEMA,
) -> dict:
    """Convert every routed flag into one work item and preserve abstentions."""
    try:
        input_schema = load_json(issue_route_schema, "issue-route schema")
        output_schema = load_json(work_plan_schema, "conditional work plan schema")
    except ContractError as error:
        raise ConditionalWorkPlanError(str(error)) from error
    errors = validate_schema_value(issue_routes, input_schema)
    if errors:
        raise ConditionalWorkPlanError(
            "issue-route contract failed: " + "; ".join(errors)
        )
    claims = {}
    for route in issue_routes["routes"]:
        claim_id = route["claim_id"]
        if claim_id in claims:
            raise ConditionalWorkPlanError(f"duplicate claim route: {claim_id}")
        claims[claim_id] = _claim_plan(route)
    result = {
        "schema_version": 1,
        "claims": [claims[claim_id] for claim_id in sorted(claims)],
    }
    output_errors = validate_schema_value(result, output_schema)
    if output_errors:
        raise ConditionalWorkPlanError(
            "conditional work plan contract failed: " + "; ".join(output_errors)
        )
    return result


def iter_dispatches(work_plan: dict) -> tuple[WorkDispatch, ...]:
    """Return only executable work items; abstained claims yield no dispatch."""
    errors = validate_schema_value(
        work_plan,
        load_json(DEFAULT_WORK_PLAN_SCHEMA, "conditional work plan schema"),
    )
    if errors:
        raise ConditionalWorkPlanError(
            "conditional work plan contract failed: " + "; ".join(errors)
        )
    dispatches = []
    for claim in work_plan["claims"]:
        if claim["route_status"] == "abstained":
            if claim["work_items"]:
                raise ConditionalWorkPlanError(
                    f"abstained claim {claim['claim_id']} cannot be dispatched"
                )
            if not claim["abstention_reasons"]:
                raise ConditionalWorkPlanError(
                    f"abstained claim {claim['claim_id']} requires reasons"
                )
            continue
        if not claim["work_items"]:
            raise ConditionalWorkPlanError(
                f"routed claim {claim['claim_id']} requires work items"
            )
        if claim["abstention_reasons"]:
            raise ConditionalWorkPlanError(
                f"routed claim {claim['claim_id']} cannot contain abstention reasons"
            )
        seen_tracks = set()
        for item in claim["work_items"]:
            if item["track"] in seen_tracks:
                raise ConditionalWorkPlanError(
                    f"routed claim {claim['claim_id']} repeats a track"
                )
            if not item["work_id"].startswith(f"WRK-{claim['claim_id']}-"):
                raise ConditionalWorkPlanError(
                    f"work item does not belong to claim {claim['claim_id']}"
                )
            seen_tracks.add(item["track"])
            dispatches.append(
                WorkDispatch(
                    work_id=item["work_id"],
                    claim_id=claim["claim_id"],
                    track=item["track"],
                    questions=tuple(item["questions"]),
                    route_reason=item["route_reason"],
                )
            )
    return tuple(dispatches)


def _claim_plan(route: dict) -> dict:
    enabled_tracks = [track for track in TRACKS if route[track[0]]]
    expected_status = "routed" if enabled_tracks else "abstained"
    if route["route_status"] != expected_status:
        raise ConditionalWorkPlanError(
            f"route_status for {route['claim_id']} must be {expected_status}"
        )
    _validate_questions(route)
    abstention_reasons = route["abstention_reasons"]
    if expected_status == "abstained":
        if not abstention_reasons:
            raise ConditionalWorkPlanError(
                f"abstention for {route['claim_id']} requires reasons"
            )
        if route["research_questions"] or route["evidence_questions"]:
            raise ConditionalWorkPlanError(
                f"abstention for {route['claim_id']} cannot contain questions"
            )
    elif abstention_reasons:
        raise ConditionalWorkPlanError(
            f"routed claim {route['claim_id']} cannot contain abstention reasons"
        )
    work_items = []
    for _, track, suffix, question_field in enabled_tracks:
        work_items.append(
            {
                "work_id": f"WRK-{route['claim_id']}-{suffix}",
                "track": track,
                "questions": (
                    sorted(route[question_field]) if question_field is not None else []
                ),
                "route_reason": route["route_reason"],
            }
        )
    return {
        "claim_id": route["claim_id"],
        "route_status": expected_status,
        "work_items": work_items,
        "abstention_reasons": sorted(abstention_reasons),
    }


def _validate_questions(route: dict) -> None:
    pairs = (
        ("requires_legal_research", "research_questions"),
        ("requires_evidence_analysis", "evidence_questions"),
    )
    for flag, questions in pairs:
        if route[flag] and not route[questions]:
            raise ConditionalWorkPlanError(
                f"{questions} must contain work for enabled {flag}"
            )
        if not route[flag] and route[questions]:
            raise ConditionalWorkPlanError(
                f"{questions} must be empty when {flag} is disabled"
            )
