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
    PositionCandidate,
    SourceReference,
    TimelineEventCandidate,
    build_labor_report,
)
from extract_labor_defenses import extract_defense_positions
from extract_labor_positions import extract_claim_positions
from schema_validation import load_json, validate_schema_value
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEGMENT_SCHEMA = ROOT / "runtime" / "providers" / "pje-pdf-segments.v1.schema.json"
DEFAULT_CLASSIFICATION_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "document-classification.v2.schema.json"
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
    defenses: tuple[dict, ...]


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
    raise PJeLaborReportExtractionError("rito informado no título do PJe não é suportado")


def _party_names(subject: str, initial_page_text: str) -> tuple[str, tuple[str, ...]]:
    subject_match = SUBJECT_PARTIES.search(_squash(subject))
    if subject_match is None:
        raise PJeLaborReportExtractionError("partes ausentes nos metadados do PJe")
    claimant = _squash(subject_match.group("claimant")).strip(" ,.;")
    primary_respondent = _squash(subject_match.group("respondent")).strip(" ,.;")
    initial_text = _squash(initial_page_text)
    if _identity(claimant) not in _identity(initial_text):
        raise PJeLaborReportExtractionError(
            "reclamante dos metadados não consta da petição inicial"
        )

    respondents = tuple(
        _squash(match.group("name")).strip(" ,.;")
        for match in RESPONDENT_QUALIFICATION.finditer(initial_text)
    )
    if not respondents:
        raise PJeLaborReportExtractionError(
            "qualificações das reclamadas ausentes na petição inicial"
        )
    primary_identity = _identity(primary_respondent)
    if all(_identity(name) != primary_identity for name in respondents):
        raise PJeLaborReportExtractionError(
            "reclamada principal dos metadados não consta da petição inicial"
        )
    if len({_identity(name) for name in respondents}) != len(respondents):
        raise PJeLaborReportExtractionError(
            "qualificações das reclamadas estão duplicadas na petição inicial"
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
        raise PJeLaborReportExtractionError("número do processo ausente no título do PJe")
    case_number = case_match.group(0)
    region = case_number.split(".")[3]
    expected_tribunal = f"TRT{int(region)}"
    if tribunal != expected_tribunal:
        raise PJeLaborReportExtractionError(
            "tribunal solicitado não corresponde ao número do processo"
        )

    court_match = COURT_UNIT.search(_squash(court_page_text))
    if court_match is None:
        raise PJeLaborReportExtractionError("unidade judiciária não identificada")
    court_unit = _squash(court_match.group("unit")).strip(" ,.;")
    claimant, respondents = _party_names(subject, initial_page_text)
    source = SourceReference(
        document_id=initial_document_id,
        locator=f"página {initial_page}, qualificação das partes",
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
                locator=f"página {phase_page}, documento processual",
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
            "identificadores dos documentos segmentados devem ser únicos"
        )
    if len(classification_ids) != len(set(classification_ids)):
        raise PJeLaborReportExtractionError(
            "identificadores dos documentos classificados devem ser únicos"
        )
    if set(segment_ids) != set(classification_ids):
        raise PJeLaborReportExtractionError(
            "documentos da segmentação e classificação devem corresponder exatamente"
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
            "é necessária exatamente uma petição inicial classificada"
        )
    defense_ids = sorted(ids_by_type.get("defense", []))
    hearing_ids = sorted(ids_by_type.get("hearing_record", []))
    initial = documents_by_id[initial_ids[0]]
    defenses = tuple(documents_by_id[document_id] for document_id in defense_ids)
    court = defenses[0] if defenses else initial
    if hearing_ids:
        phase = documents_by_id[hearing_ids[-1]]
    elif defense_ids:
        phase = documents_by_id[defense_ids[-1]]
    else:
        phase = initial
    return SourceDocuments(
        initial=initial,
        court=court,
        phase=phase,
        defenses=defenses,
    )


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
    positions: tuple[PositionCandidate, ...] = (),
) -> dict:
    """Build a report while preserving every position that remains absent."""
    report = build_labor_report(
        context.case_context,
        known_document_ids,
        context.parties,
        context.phase,
        timeline_candidates(timeline),
        positions,
    )
    schema = load_json(schema_path, "esquema do relatório trabalhista")
    issues = validate_schema_value(report, schema)
    if issues:
        raise PJeLaborReportExtractionError(
            "contrato do relatório trabalhista inválido: " + "; ".join(issues)
        )
    return report


def _validate_artifact(
    value: dict,
    schema_path: Path,
    label: str,
    *,
    semantic: bool = False,
) -> None:
    schema = load_json(schema_path, f"esquema de {label}")
    issues = (
        validate_document(value, schema)
        if semantic
        else validate_schema_value(value, schema)
    )
    if issues:
        raise PJeLaborReportExtractionError(
            f"contrato de {label} inválido: " + "; ".join(issues)
        )


def _page_text(reader: PdfReader, page_number: int, label: str) -> str:
    if page_number < 1 or page_number > len(reader.pages):
        raise PJeLaborReportExtractionError(f"página de {label} fora do PDF")
    text = reader.pages[page_number - 1].extract_text() or ""
    if not text.strip():
        raise PJeLaborReportExtractionError(f"página de {label} sem texto extraível")
    return text


def _document_page_texts(
    reader: PdfReader,
    document: dict,
    label: str,
) -> tuple[tuple[int, str], ...]:
    return tuple(
        (page_number, _page_text(reader, page_number, label))
        for page_number in range(document["page_start"], document["page_end"] + 1)
    )


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
    _validate_artifact(segments, segment_schema_path, "segmentos do PDF do PJe")
    _validate_artifact(
        classification,
        classification_schema_path,
        "classificação documental",
    )
    _validate_artifact(
        timeline,
        timeline_schema_path,
        "linha do tempo processual",
        semantic=True,
    )

    source = pdf_path.resolve()
    if not source.is_file():
        raise PJeLaborReportExtractionError("PDF do PJe não encontrado")
    reader = PdfReader(str(source))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    source_pdf = segments["source_pdf"]
    if digest != source_pdf["sha256"] or len(reader.pages) != source_pdf["page_count"]:
        raise PJeLaborReportExtractionError(
            "custódia do PDF não corresponde ao artefato de segmentação"
        )

    selected = select_source_documents(segments, classification)
    metadata = reader.metadata or {}
    title = metadata.get("/Title")
    subject = metadata.get("/Subject")
    if not isinstance(title, str) or not title.strip():
        raise PJeLaborReportExtractionError("metadado de título ausente no PDF do PJe")
    if not isinstance(subject, str) or not subject.strip():
        raise PJeLaborReportExtractionError("metadado de assunto ausente no PDF do PJe")
    initial_pages = _document_page_texts(
        reader,
        selected.initial,
        "petição inicial",
    )
    context = extract_context_candidates(
        title=title,
        subject=subject,
        initial_page_text=initial_pages[0][1],
        court_page_text=_page_text(
            reader,
            selected.court["page_start"],
            "fonte da unidade judiciária",
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
    claim_positions = extract_claim_positions(
        initial_document_id=selected.initial["document_id"],
        page_texts=initial_pages,
    )
    defense_positions = tuple(
        position
        for group, document in enumerate(selected.defenses, 1)
        for position in extract_defense_positions(
            defense_document_id=document["document_id"],
            page_texts=_document_page_texts(reader, document, "contestação"),
            position_group=group,
        )
    )
    return build_partial_labor_report(
        context,
        known_document_ids=tuple(
            sorted(item["document_id"] for item in segments["documents"])
        ),
        timeline=timeline,
        schema_path=labor_report_schema_path,
        positions=claim_positions + defense_positions,
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
            "saída do relatório trabalhista deve ficar fora do repositório"
        )
    if not destination.is_dir():
        raise PJeLaborReportExtractionError(
            "diretório de saída do relatório trabalhista deve existir previamente"
        )

    path = destination / "labor-report.json"
    if path.exists():
        raise PJeLaborReportExtractionError("saída do relatório trabalhista já existe")
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai um relatório trabalhista protegido e vinculado às fontes de um PDF do PJe.",
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
            load_json(args.segments, "segmentos do PDF do PJe"),
            load_json(args.classification, "classificação documental"),
            load_json(args.timeline, "linha do tempo processual"),
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
        print(f"[ERRO] Relatório trabalhista do PJe: {error}", file=sys.stderr)
        return 1

    print(
        "[OK] Relatório trabalhista do PJe: "
        f"partes={len(report['parties'])} "
        f"eventos={len(report['timeline'])} "
        f"posições={len(report['positions'])} "
        f"lacunas={len(report['review_gaps'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
