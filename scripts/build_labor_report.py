#!/usr/bin/env python3
"""Build a deterministic, source-linked Labor Justice procedural report."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple


DOCUMENT_ID_PATTERN = re.compile(r"DOC-[0-9]{3,}")
PARTY_ID_PATTERN = re.compile(r"PTY-[0-9]{3,}")
EVENT_ID_PATTERN = re.compile(r"EVT-[0-9]{3,}")
POSITION_ID_PATTERN = re.compile(r"POS-[0-9]{3,}")
LABEL_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
CASE_NUMBER_PATTERN = re.compile(
    r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}"
)
COURT_PATTERN = re.compile(r"TRT[1-9][0-9]?")
SOURCE_MANIFEST_PATTERN = re.compile(r"[A-Za-z0-9._/-]+\.json")

CASE_CONTEXT_FIELDS = {
    "schema_version",
    "case_number",
    "court",
    "instance",
    "phase",
    "procedure",
    "court_unit",
    "confidentiality",
    "source_manifest",
}
PHASES = {"knowledge", "liquidation", "execution", "provisional_relief", "unknown"}
PHASE_STATUSES = {"identified", "needs_human_review"}
PARTY_ROLES = {
    "claimant",
    "respondent",
    "interested_party",
    "public_entity",
    "union",
    "prosecutor",
    "unknown",
}
POSITION_KINDS = {"claim", "defense"}
CONFIDENTIALITY_LEVELS = {
    "public_or_authorized",
    "restricted_authorized",
    "sealed_authorized",
}


class LaborReportContractViolation(ValueError):
    """Raised when report inputs cannot satisfy the source-custody contract."""


@dataclass(frozen=True)
class SourceReference:
    document_id: str
    locator: str


@dataclass(frozen=True)
class PartyCandidate:
    party_id: str
    role: str
    display_name: str
    source: SourceReference


@dataclass(frozen=True)
class PhaseAssessment:
    phase: str
    status: str
    source: Optional[SourceReference]


@dataclass(frozen=True)
class TimelineEventCandidate:
    event_id: str
    event_date: Optional[str]
    event_type: str
    summary: str
    source: SourceReference


@dataclass(frozen=True)
class PositionCandidate:
    position_id: str
    kind: str
    label: str
    summary: str
    source: SourceReference


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LaborReportContractViolation(f"{label} must be a non-empty string")
    return value


def _validate_case_context(value: object) -> dict:
    if not isinstance(value, dict):
        raise LaborReportContractViolation("case_context must be an object")
    missing = sorted(CASE_CONTEXT_FIELDS - set(value))
    unknown = sorted(set(value) - CASE_CONTEXT_FIELDS)
    if missing:
        raise LaborReportContractViolation(
            f"case_context missing field(s): {', '.join(missing)}"
        )
    if unknown:
        raise LaborReportContractViolation(
            f"case_context has unknown field(s): {', '.join(unknown)}"
        )
    if value["schema_version"] != 1:
        raise LaborReportContractViolation("case_context schema_version must be 1")
    if not isinstance(value["case_number"], str) or CASE_NUMBER_PATTERN.fullmatch(
        value["case_number"]
    ) is None:
        raise LaborReportContractViolation("case_context case_number is invalid")
    if not isinstance(value["court"], str) or COURT_PATTERN.fullmatch(value["court"]) is None:
        raise LaborReportContractViolation("case_context court is invalid")
    if (
        isinstance(value["instance"], bool)
        or not isinstance(value["instance"], int)
        or value["instance"] not in (1, 2)
    ):
        raise LaborReportContractViolation("case_context instance is invalid")
    if value["phase"] not in PHASES - {"unknown"}:
        raise LaborReportContractViolation("case_context phase is invalid")
    if not isinstance(value["procedure"], str) or LABEL_PATTERN.fullmatch(
        value["procedure"]
    ) is None:
        raise LaborReportContractViolation("case_context procedure is invalid")
    _require_text(value["court_unit"], "case_context court_unit")
    if value["confidentiality"] not in CONFIDENTIALITY_LEVELS:
        raise LaborReportContractViolation("case_context confidentiality is invalid")
    if not isinstance(value["source_manifest"], str) or SOURCE_MANIFEST_PATTERN.fullmatch(
        value["source_manifest"]
    ) is None:
        raise LaborReportContractViolation("case_context source_manifest is invalid")
    return value


def _validate_known_documents(value: object) -> set:
    if not isinstance(value, tuple) or not value:
        raise LaborReportContractViolation("known_document_ids must be a non-empty tuple")
    for document_id in value:
        if not isinstance(document_id, str) or DOCUMENT_ID_PATTERN.fullmatch(document_id) is None:
            raise LaborReportContractViolation("known_document_ids contains an invalid document_id")
    if len(value) != len(set(value)):
        raise LaborReportContractViolation("known_document_ids must be unique")
    return set(value)


def _validate_source(source: object, known_documents: set, label: str) -> SourceReference:
    if not isinstance(source, SourceReference):
        raise LaborReportContractViolation(f"{label} source reference is invalid")
    if DOCUMENT_ID_PATTERN.fullmatch(source.document_id) is None:
        raise LaborReportContractViolation(f"{label} document_id is invalid")
    if source.document_id not in known_documents:
        raise LaborReportContractViolation(
            f"{label} references unknown document {source.document_id}"
        )
    _require_text(source.locator, f"{label} source locator")
    return source


def _validate_unique_id(identifier: object, pattern: re.Pattern, seen: set, label: str) -> str:
    if not isinstance(identifier, str) or pattern.fullmatch(identifier) is None:
        raise LaborReportContractViolation(f"{label} is invalid")
    if identifier in seen:
        raise LaborReportContractViolation(f"{label} values must be unique")
    seen.add(identifier)
    return identifier


def _serialize_source(source: SourceReference) -> dict:
    return {
        "source_document_id": source.document_id,
        "source_locator": source.locator,
    }


def _serialize_parties(values: object, known_documents: set) -> list:
    if not isinstance(values, tuple):
        raise LaborReportContractViolation("parties must be a tuple")
    seen = set()
    items = []
    for candidate in values:
        if not isinstance(candidate, PartyCandidate):
            raise LaborReportContractViolation("party candidate has an invalid type")
        _validate_unique_id(candidate.party_id, PARTY_ID_PATTERN, seen, "party_id")
        if candidate.role not in PARTY_ROLES:
            raise LaborReportContractViolation("party role is unsupported")
        _require_text(candidate.display_name, "party display_name")
        source = _validate_source(candidate.source, known_documents, candidate.party_id)
        items.append(
            {
                "party_id": candidate.party_id,
                "role": candidate.role,
                "display_name": candidate.display_name,
                **_serialize_source(source),
            }
        )
    return sorted(items, key=lambda item: item["party_id"])


def _serialize_phase(
    assessment: object,
    known_documents: set,
    case_context: dict,
) -> dict:
    if not isinstance(assessment, PhaseAssessment):
        raise LaborReportContractViolation("phase assessment has an invalid type")
    if assessment.phase not in PHASES:
        raise LaborReportContractViolation("procedural phase is unsupported")
    if assessment.status not in PHASE_STATUSES:
        raise LaborReportContractViolation("procedural phase status is unsupported")
    if assessment.status == "identified" and assessment.source is None:
        raise LaborReportContractViolation("identified phase requires a source reference")
    if assessment.phase == "unknown" and assessment.status != "needs_human_review":
        raise LaborReportContractViolation("unknown phase requires human review")
    if assessment.status == "identified" and assessment.phase != case_context["phase"]:
        raise LaborReportContractViolation("identified phase conflicts with case_context")
    if assessment.source is None:
        source_fields = {"source_document_id": None, "source_locator": None}
    else:
        source_fields = _serialize_source(
            _validate_source(assessment.source, known_documents, "procedural phase")
        )
    return {
        "phase": assessment.phase,
        "status": assessment.status,
        **source_fields,
    }


def _validate_date(value: object, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise LaborReportContractViolation(f"{label} event_date must be a string or null")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise LaborReportContractViolation(f"{label} event_date must use YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise LaborReportContractViolation(f"{label} event_date must use YYYY-MM-DD")


def _serialize_timeline(values: object, known_documents: set) -> list:
    if not isinstance(values, tuple):
        raise LaborReportContractViolation("timeline must be a tuple")
    seen = set()
    items = []
    for candidate in values:
        if not isinstance(candidate, TimelineEventCandidate):
            raise LaborReportContractViolation("timeline event has an invalid type")
        _validate_unique_id(candidate.event_id, EVENT_ID_PATTERN, seen, "event_id")
        _validate_date(candidate.event_date, candidate.event_id)
        if not isinstance(candidate.event_type, str) or LABEL_PATTERN.fullmatch(
            candidate.event_type
        ) is None:
            raise LaborReportContractViolation("event_type is invalid")
        _require_text(candidate.summary, "timeline summary")
        source = _validate_source(candidate.source, known_documents, candidate.event_id)
        items.append(
            {
                "event_id": candidate.event_id,
                "event_date": candidate.event_date,
                "event_type": candidate.event_type,
                "summary": candidate.summary,
                **_serialize_source(source),
            }
        )
    return sorted(
        items,
        key=lambda item: (
            item["event_date"] is None,
            item["event_date"] or "",
            item["event_id"],
        ),
    )


def _serialize_positions(values: object, known_documents: set) -> list:
    if not isinstance(values, tuple):
        raise LaborReportContractViolation("positions must be a tuple")
    seen = set()
    items = []
    for candidate in values:
        if not isinstance(candidate, PositionCandidate):
            raise LaborReportContractViolation("position candidate has an invalid type")
        _validate_unique_id(candidate.position_id, POSITION_ID_PATTERN, seen, "position_id")
        if candidate.kind not in POSITION_KINDS:
            raise LaborReportContractViolation("position kind is unsupported")
        if not isinstance(candidate.label, str) or LABEL_PATTERN.fullmatch(candidate.label) is None:
            raise LaborReportContractViolation("position label is invalid")
        _require_text(candidate.summary, "position summary")
        source = _validate_source(candidate.source, known_documents, candidate.position_id)
        items.append(
            {
                "position_id": candidate.position_id,
                "kind": candidate.kind,
                "label": candidate.label,
                "summary": candidate.summary,
                **_serialize_source(source),
            }
        )
    return sorted(items, key=lambda item: item["position_id"])


def _review_gaps(parties: list, phase: dict, timeline: list, positions: list) -> list:
    gaps = set()
    if not parties:
        gaps.add("missing_parties")
    if any(party["role"] == "unknown" for party in parties):
        gaps.add("unknown_party_role")
    if phase["phase"] == "unknown":
        gaps.add("unknown_phase")
    if any(event["event_date"] is None for event in timeline):
        gaps.add("undated_event")
    kinds = {position["kind"] for position in positions}
    if "claim" not in kinds:
        gaps.add("missing_claim_position")
    if "defense" not in kinds:
        gaps.add("missing_defense_position")
    return sorted(gaps)


def build_labor_report(
    case_context: dict,
    known_document_ids: Tuple[str, ...],
    parties: Tuple[PartyCandidate, ...],
    phase: PhaseAssessment,
    timeline: Tuple[TimelineEventCandidate, ...],
    positions: Tuple[PositionCandidate, ...],
) -> dict:
    """Build a stable report without inventing missing procedural information."""
    validated_context = _validate_case_context(case_context)
    known_documents = _validate_known_documents(known_document_ids)
    serialized_parties = _serialize_parties(parties, known_documents)
    serialized_phase = _serialize_phase(phase, known_documents, validated_context)
    serialized_timeline = _serialize_timeline(timeline, known_documents)
    serialized_positions = _serialize_positions(positions, known_documents)
    return {
        "schema_version": 1,
        "case_context": copy.deepcopy(validated_context),
        "parties": serialized_parties,
        "procedural_phase": serialized_phase,
        "timeline": serialized_timeline,
        "positions": serialized_positions,
        "review_gaps": _review_gaps(
            serialized_parties,
            serialized_phase,
            serialized_timeline,
            serialized_positions,
        ),
    }
