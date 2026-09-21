#!/usr/bin/env python3
"""Build deterministic claim-level work routes with explicit abstention."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple


CLAIM_ID_PATTERN = re.compile(r"CLM-[0-9]{3,}")


class IssueRouteContractViolation(ValueError):
    """Raised when issue-routing inputs violate coverage or explanation rules."""


@dataclass(frozen=True)
class IssueRouteCandidate:
    claim_id: str
    requires_legal_research: bool
    requires_evidence_analysis: bool
    requires_calculation_review: bool
    requires_procedural_review: bool
    research_questions: Tuple[str, ...]
    evidence_questions: Tuple[str, ...]
    route_reason: str
    abstention_reasons: Tuple[str, ...]


def _require_claim_id(value: object, label: str) -> str:
    if not isinstance(value, str) or CLAIM_ID_PATTERN.fullmatch(value) is None:
        raise IssueRouteContractViolation(f"{label} is invalid")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IssueRouteContractViolation(f"{label} must be a non-empty string")
    return value


def _require_boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise IssueRouteContractViolation(f"{label} must be a boolean")
    return value


def _require_text_tuple(value: object, label: str) -> Tuple[str, ...]:
    if not isinstance(value, tuple):
        raise IssueRouteContractViolation(f"{label} must be a tuple")
    for item in value:
        _require_text(item, label)
    if len(value) != len(set(value)):
        raise IssueRouteContractViolation(f"{label} values must be unique")
    return value


def _known_claims(value: object) -> set:
    if not isinstance(value, tuple) or not value:
        raise IssueRouteContractViolation("known_claim_ids must be a non-empty tuple")
    for claim_id in value:
        _require_claim_id(claim_id, "known claim_id")
    if len(value) != len(set(value)):
        raise IssueRouteContractViolation("known claim_id values must be unique")
    return set(value)


def _validate_question_track(
    required: bool,
    questions: Tuple[str, ...],
    *,
    track_label: str,
    question_label: str,
) -> None:
    if required and not questions:
        raise IssueRouteContractViolation(
            f"{track_label} requires at least one {question_label} question"
        )
    if not required and questions:
        raise IssueRouteContractViolation(
            f"{question_label}_questions must be empty when {track_label} is false"
        )


def _route_item(candidate: IssueRouteCandidate) -> dict:
    flags = {
        "requires_legal_research": _require_boolean(
            candidate.requires_legal_research,
            "requires_legal_research",
        ),
        "requires_evidence_analysis": _require_boolean(
            candidate.requires_evidence_analysis,
            "requires_evidence_analysis",
        ),
        "requires_calculation_review": _require_boolean(
            candidate.requires_calculation_review,
            "requires_calculation_review",
        ),
        "requires_procedural_review": _require_boolean(
            candidate.requires_procedural_review,
            "requires_procedural_review",
        ),
    }
    research_questions = _require_text_tuple(
        candidate.research_questions,
        "research_questions",
    )
    evidence_questions = _require_text_tuple(
        candidate.evidence_questions,
        "evidence_questions",
    )
    abstention_reasons = _require_text_tuple(
        candidate.abstention_reasons,
        "abstention_reasons",
    )
    _validate_question_track(
        flags["requires_legal_research"],
        research_questions,
        track_label="requires_legal_research",
        question_label="research",
    )
    _validate_question_track(
        flags["requires_evidence_analysis"],
        evidence_questions,
        track_label="requires_evidence_analysis",
        question_label="evidence",
    )
    routed = any(flags.values())
    if routed and abstention_reasons:
        raise IssueRouteContractViolation(
            "routed claim cannot contain abstention reasons"
        )
    if not routed and not abstention_reasons:
        raise IssueRouteContractViolation(
            "claim without a route requires at least one abstention reason"
        )
    return {
        "claim_id": candidate.claim_id,
        "route_status": "routed" if routed else "abstained",
        **flags,
        "research_questions": sorted(research_questions),
        "evidence_questions": sorted(evidence_questions),
        "route_reason": _require_text(candidate.route_reason, "route_reason"),
        "abstention_reasons": sorted(abstention_reasons),
    }


def build_issue_routes(
    known_claim_ids: Tuple[str, ...],
    candidates: Tuple[IssueRouteCandidate, ...],
) -> dict:
    """Build one explainable route or explicit abstention for every known claim."""
    known_claims = _known_claims(known_claim_ids)
    if not isinstance(candidates, tuple):
        raise IssueRouteContractViolation("route candidates must be a tuple")
    routes = {}
    for candidate in candidates:
        if not isinstance(candidate, IssueRouteCandidate):
            raise IssueRouteContractViolation("route candidate has an invalid type")
        claim_id = _require_claim_id(candidate.claim_id, "claim_id")
        if claim_id in routes:
            raise IssueRouteContractViolation("claim_id route values must be unique")
        if claim_id not in known_claims:
            raise IssueRouteContractViolation(
                f"route references unknown claim {claim_id}"
            )
        routes[claim_id] = _route_item(candidate)
    missing_claims = sorted(known_claims - set(routes))
    if missing_claims:
        raise IssueRouteContractViolation(
            f"route is missing known claim {missing_claims[0]}"
        )
    return {
        "schema_version": 1,
        "routes": [routes[claim_id] for claim_id in sorted(routes)],
    }
