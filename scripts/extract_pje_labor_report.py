#!/usr/bin/env python3
"""Extract a protected partial labor report from a consolidated PJe PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PyPDF2 import PdfReader

from build_labor_report import (
    PartyCandidate,
    PhaseAssessment,
    SourceReference,
    TimelineEventCandidate,
    build_labor_report,
)
from schema_validation import load_json, validate_schema_value
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEGMENT_SCHEMA = ROOT / "runtime" / "providers" / "pje-pdf-segments.v1.schema.json"
DEFAULT_CLASSIFICATION_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "document-classification.v1.schema.json"
)
DEFAULT_TIMELINE_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "procedural-timeline.v1.schema.json"
)
DEFAULT_LABOR_REPORT_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "labor-report.v1.schema.json"
)


CASE_NUMBER = re.compile(
    r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}"
)
SUBJECT_PARTIES = re.compile(
    r"RECLAMANTE:\s*(?P<claimant>.*?)\s*;\s*RECLAMADO:\s*(?P<respondent>.*?)(?:;|$)",
    re.IGNORECASE,
)
RESPONDENT_QUALIFICATION = re.compile(
    r"(?:em\s+face\s+de|,\s*e)\s+"
    r"(?P<name>[A-ZÀ-ÖØ-Þ0-9][A-ZÀ-ÖØ-Þ0-9 .&/'-]*?"
    r"(?:LTDA|EIRELI|S\.?\s*A\.?|MEI|EPP))\s*"
    r"(?:-\s*(?:EPP|ME))?\s*,\s*Pessoa\s+Jur[ií]dica",
    re.IGNORECASE,
)
COURT_UNIT = re.compile(
    r"(?:AO\s+JU[IÍ]ZO\s+DA\s+)?"
    r"(?P<unit>(?:[0-9]+\s*[ªº]\s+)?VARA\s+DO\s+TRABALHO\s+DE\s+"
    r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ /-]*?)"
    r"(?=\s*[.,;]|$)",
    re.IGNORECASE,
)


class PJeLaborReportExtractionError(ValueError):
    """Raised when the authorized PDF cannot support a bounded extraction."""


@dataclass(frozen=True)
class ContextCandidates:
    case_context: dict
    parties: tuple[PartyCandidate, ...]
    phase: PhaseAssessment


@dataclass(frozen=True)
class SourceDocuments:
    initial: dict
    court: dict
    phase: dict


def _squash(value: str) -> str:
    return " ".join(value.split())


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).upper()


def _identity(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", " ", _fold(value)).strip()
    return re.sub(r"\s+(?:EPP|ME)$", "", normalized)


def _procedure(title: str) -> str:
    normalized = _fold(title)
    if "RITO SUMARISSIMO" in normalized:
        return "summary"
    if "RITO ORDINARIO" in normalized:
        return "ordinary"
    raise PJeLaborReportExtractionError("PJe title procedure is unsupported")


def _party_names(subject: str, initial_page_text: str) -> tuple[str, tuple[str, ...]]:
    subject_match = SUBJECT_PARTIES.search(_squash(subject))
    if subject_match is None:
        raise PJeLaborReportExtractionError("PJe subject parties are missing")
    claimant = _squash(subject_match.group("claimant")).strip(" ,.;")
    primary_respondent = _squash(subject_match.group("respondent")).strip(" ,.;")
    initial_text = _squash(initial_page_text)
    if _identity(claimant) not in _identity(initial_text):
        raise PJeLaborReportExtractionError(
            "claimant metadata is not present in the initial pleading"
        )

    respondents = tuple(
        _squash(match.group("name")).strip(" ,.;")
        for match in RESPONDENT_QUALIFICATION.finditer(initial_text)
    )
    if not respondents:
        raise PJeLaborReportExtractionError(
            "initial pleading respondent qualifications are missing"
        )
    primary_identity = _identity(primary_respondent)
    if all(_identity(name) != primary_identity for name in respondents):
        raise PJeLaborReportExtractionError(
            "primary respondent metadata is not present in the initial pleading"
        )
    if len({_identity(name) for name in respondents}) != len(respondents):
        raise PJeLaborReportExtractionError(
            "initial pleading respondent qualifications are duplicated"
        )
    return claimant, respondents


def extract_context_candidates(
    *,
    title: str,
    subject: str,
    initial_page_text: str,
    court_page_text: str,
    initial_document_id: str,
    initial_page: int,
    phase_document_id: str,
    phase_page: int,
    tribunal: str,
    instance: int,
    confidentiality: str,
    source_manifest: str,
) -> ContextCandidates:
    """Extract context candidates while retaining page-level source custody."""
    title_text = _squash(title)
    case_match = CASE_NUMBER.search(title_text)
    if case_match is None:
        raise PJeLaborReportExtractionError("PJe title case number is missing")
    case_number = case_match.group(0)
    region = case_number.split(".")[3]
    expected_tribunal = f"TRT{int(region)}"
    if tribunal != expected_tribunal:
        raise PJeLaborReportExtractionError(
            "requested tribunal does not match the case number"
        )

    court_match = COURT_UNIT.search(_squash(court_page_text))
    if court_match is None:
        raise PJeLaborReportExtractionError("court unit is missing")
    court_unit = _squash(court_match.group("unit")).strip(" ,.;")
    claimant, respondents = _party_names(subject, initial_page_text)
    source = SourceReference(
        document_id=initial_document_id,
        locator=f"page {initial_page}, party qualification",
    )
    parties = (
        PartyCandidate(
            party_id="PTY-001",
            role="claimant",
            display_name=claimant,
            source=source,
        ),
        *(
            PartyCandidate(
                party_id=f"PTY-{index:03d}",
                role="respondent",
                display_name=name,
                source=source,
            )
            for index, name in enumerate(respondents, 2)
        ),
    )
    return ContextCandidates(
        case_context={
            "schema_version": 1,
            "case_number": case_number,
            "court": tribunal,
            "instance": instance,
            "phase": "knowledge",
            "procedure": _procedure(title_text),
            "court_unit": court_unit,
            "confidentiality": confidentiality,
            "source_manifest": source_manifest,
        },
        parties=parties,
        phase=PhaseAssessment(
            phase="knowledge",
            status="identified",
            source=SourceReference(
                document_id=phase_document_id,
                locator=f"page {phase_page}, procedural document",
            ),
        ),
    )


def select_source_documents(segments: dict, classification: dict) -> SourceDocuments:
    """Select source documents without relying on provider-specific labels."""
    segment_ids = [item["document_id"] for item in segments["documents"]]
    classification_ids = [
        item["document_id"] for item in classification["documents"]
    ]
    if len(segment_ids) != len(set(segment_ids)):
        raise PJeLaborReportExtractionError(
            "segment document identifiers must be unique"
        )
    if len(classification_ids) != len(set(classification_ids)):
        raise PJeLaborReportExtractionError(
            "classification document identifiers must be unique"
        )
    if set(segment_ids) != set(classification_ids):
        raise PJeLaborReportExtractionError(
            "segment and classification document sets must match exactly"
        )

    documents_by_id = {
        item["document_id"]: item for item in segments["documents"]
    }
    ids_by_type: dict[str, list[str]] = {}
    for item in classification["documents"]:
        if item["classification_status"] == "classified":
            ids_by_type.setdefault(item["document_type"], []).append(
                item["document_id"]
            )
    initial_ids = sorted(ids_by_type.get("initial_pleading", []))
    if len(initial_ids) != 1:
        raise PJeLaborReportExtractionError(
            "exactly one classified initial pleading is required"
        )
    defense_ids = sorted(ids_by_type.get("defense", []))
    hearing_ids = sorted(ids_by_type.get("hearing_record", []))
    initial = documents_by_id[initial_ids[0]]
    court = documents_by_id[defense_ids[0]] if defense_ids else initial
    if hearing_ids:
        phase = documents_by_id[hearing_ids[-1]]
    elif defense_ids:
        phase = documents_by_id[defense_ids[-1]]
    else:
        phase = initial
    return SourceDocuments(initial=initial, court=court, phase=phase)


def timeline_candidates(timeline: dict) -> tuple[TimelineEventCandidate, ...]:
    """Convert a validated procedural timeline without weakening source custody."""
    return tuple(
        TimelineEventCandidate(
            event_id=event["event_id"],
            event_date=event["event_date"],
            event_type=event["event_type"],
            summary=event["summary"],
            source=SourceReference(
                document_id=event["source_document_id"],
                locator=event["source_locator"],
            ),
        )
        for event in sorted(
            timeline["events"],
            key=lambda item: (item["event_date"], item["event_id"]),
        )
    )


def build_partial_labor_report(
    context: ContextCandidates,
    *,
    known_document_ids: tuple[str, ...],
    timeline: dict,
    schema_path: Path,
) -> dict:
    """Build a report that abstains from claim and defense extraction."""
    report = build_labor_report(
        context.case_context,
        known_document_ids,
        context.parties,
        context.phase,
        timeline_candidates(timeline),
        (),
    )
    schema = load_json(schema_path, "labor report schema")
    issues = validate_schema_value(report, schema)
    if issues:
        raise PJeLaborReportExtractionError(
            "labor report contract failed: " + "; ".join(issues)
        )
    return report


def _validate_artifact(
    value: dict,
    schema_path: Path,
    label: str,
    *,
    semantic: bool = False,
) -> None:
    schema = load_json(schema_path, f"{label} schema")
    issues = (
        validate_document(value, schema)
        if semantic
        else validate_schema_value(value, schema)
    )
    if issues:
        raise PJeLaborReportExtractionError(
            f"{label} contract failed: " + "; ".join(issues)
        )


def _page_text(reader: PdfReader, page_number: int, label: str) -> str:
    if page_number < 1 or page_number > len(reader.pages):
        raise PJeLaborReportExtractionError(f"{label} page is outside the PDF")
    text = reader.pages[page_number - 1].extract_text() or ""
    if not text.strip():
        raise PJeLaborReportExtractionError(f"{label} page has no extractable text")
    return text


def extract_pdf_labor_report(
    pdf_path: Path,
    segments: dict,
    classification: dict,
    timeline: dict,
    *,
    tribunal: str,
    instance: int,
    confidentiality: str,
    source_manifest: str,
    segment_schema_path: Path,
    classification_schema_path: Path,
    timeline_schema_path: Path,
    labor_report_schema_path: Path,
) -> dict:
    """Extract a schema-valid partial report from one custodied PJe PDF."""
    _validate_artifact(segments, segment_schema_path, "PJe PDF segments")
    _validate_artifact(
        classification,
        classification_schema_path,
        "document classification",
    )
    _validate_artifact(
        timeline,
        timeline_schema_path,
        "procedural timeline",
        semantic=True,
    )

    source = pdf_path.resolve()
    if not source.is_file():
        raise PJeLaborReportExtractionError(f"PJe PDF not found: {source}")
    reader = PdfReader(str(source))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    source_pdf = segments["source_pdf"]
    if digest != source_pdf["sha256"] or len(reader.pages) != source_pdf["page_count"]:
        raise PJeLaborReportExtractionError(
            "PDF custody does not match the segment artifact"
        )

    selected = select_source_documents(segments, classification)
    metadata = reader.metadata or {}
    title = metadata.get("/Title")
    subject = metadata.get("/Subject")
    if not isinstance(title, str) or not title.strip():
        raise PJeLaborReportExtractionError("PJe PDF title metadata is missing")
    if not isinstance(subject, str) or not subject.strip():
        raise PJeLaborReportExtractionError("PJe PDF subject metadata is missing")
    context = extract_context_candidates(
        title=title,
        subject=subject,
        initial_page_text=_page_text(
            reader,
            selected.initial["page_start"],
            "initial pleading",
        ),
        court_page_text=_page_text(
            reader,
            selected.court["page_start"],
            "court unit source",
        ),
        initial_document_id=selected.initial["document_id"],
        initial_page=selected.initial["page_start"],
        phase_document_id=selected.phase["document_id"],
        phase_page=selected.phase["page_start"],
        tribunal=tribunal,
        instance=instance,
        confidentiality=confidentiality,
        source_manifest=source_manifest,
    )
    return build_partial_labor_report(
        context,
        known_document_ids=tuple(
            sorted(item["document_id"] for item in segments["documents"])
        ),
        timeline=timeline,
        schema_path=labor_report_schema_path,
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def write_labor_report_artifact(
    report: dict,
    *,
    output_dir: Path,
    repository_root: Path,
) -> Path:
    """Write one protected report without allowing repository-local case data."""
    destination = output_dir.resolve()
    repository = repository_root.resolve()
    if destination == repository or _is_within(destination, repository):
        raise PJeLaborReportExtractionError(
            "labor report output must stay outside repository"
        )
    if not destination.is_dir():
        raise PJeLaborReportExtractionError(
            "labor report output directory must already exist"
        )

    path = destination / "labor-report.json"
    if path.exists():
        raise PJeLaborReportExtractionError("labor report output already exists")
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a protected partial labor report from one PJe PDF.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--classification", required=True, type=Path)
    parser.add_argument("--timeline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--tribunal", required=True)
    parser.add_argument("--instance", required=True, type=int, choices=(1, 2))
    parser.add_argument(
        "--confidentiality",
        required=True,
        choices=(
            "public_or_authorized",
            "restricted_authorized",
            "sealed_authorized",
        ),
    )
    parser.add_argument("--source-manifest", default="document-segments.json")
    parser.add_argument("--segment-schema", type=Path, default=DEFAULT_SEGMENT_SCHEMA)
    parser.add_argument(
        "--classification-schema",
        type=Path,
        default=DEFAULT_CLASSIFICATION_SCHEMA,
    )
    parser.add_argument("--timeline-schema", type=Path, default=DEFAULT_TIMELINE_SCHEMA)
    parser.add_argument(
        "--labor-report-schema",
        type=Path,
        default=DEFAULT_LABOR_REPORT_SCHEMA,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = extract_pdf_labor_report(
            args.input,
            load_json(args.segments, "PJe PDF segments"),
            load_json(args.classification, "document classification"),
            load_json(args.timeline, "procedural timeline"),
            tribunal=args.tribunal,
            instance=args.instance,
            confidentiality=args.confidentiality,
            source_manifest=args.source_manifest,
            segment_schema_path=args.segment_schema,
            classification_schema_path=args.classification_schema,
            timeline_schema_path=args.timeline_schema,
            labor_report_schema_path=args.labor_report_schema,
        )
        write_labor_report_artifact(
            report,
            output_dir=args.output,
            repository_root=args.repository_root,
        )
    except (KeyError, OSError, PJeLaborReportExtractionError, TypeError, ValueError) as error:
        print(f"[ERROR] PJe labor report: {error}", file=sys.stderr)
        return 1

    print(
        "[OK] PJe labor report: "
        f"parties={len(report['parties'])} "
        f"events={len(report['timeline'])} "
        f"positions={len(report['positions'])} "
        f"gaps={len(report['review_gaps'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
