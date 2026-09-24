#!/usr/bin/env python3
"""Monta linha do tempo processual com fontes dos documentos do PJe."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from schema_validation import load_json, validate_schema_value


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "procedural-timeline.v1.schema.json"
)


EVENT_PRESENTATION = {
    "initial_pleading": ("case_filed", "Petição inicial protocolada."),
    "defense": ("defense_filed", "Contestação protocolada."),
    "reply": ("reply_filed", "Réplica protocolada."),
    "hearing_record": ("hearing_held", "Ata de audiência registrada."),
    "expert_report": ("expert_report_filed", "Laudo pericial juntado."),
    "documentary_evidence": ("evidence_filed", "Documento probatório juntado."),
    "calculations": ("calculations_filed", "Cálculos juntados."),
    "settlement": ("settlement_filed", "Termo de acordo juntado."),
    "procedural_order": ("procedural_order_issued", "Despacho registrado."),
    "interlocutory_decision": (
        "interlocutory_decision_issued",
        "Decisão interlocutória registrada.",
    ),
    "judgment": ("judgment_issued", "Sentença registrada."),
    "appeal": ("appeal_filed", "Recurso ou contrarrazões juntados."),
    "other_petition": ("petition_filed", "Petição juntada."),
    "procedural_certificate": (
        "procedural_certificate_recorded",
        "Certidão registrada.",
    ),
    "procedural_communication": (
        "procedural_communication_recorded",
        "Comunicação processual registrada.",
    ),
}
UNCLASSIFIED_EVENT = (
    "unclassified_document_filed",
    "Documento sem classificação; revisão humana necessária.",
)


class ProceduralTimelineError(ValueError):
    """Indica segmentos ou classificação incompatíveis com a linha do tempo."""


def _source_locator(document: dict) -> str:
    start = document["page_start"]
    end = document["page_end"]
    return f"página {start}" if start == end else f"páginas {start}-{end}"


def build_procedural_timeline(
    segments: dict,
    classification: dict,
    *,
    schema_path: Path,
) -> dict:
    """Cria um evento determinístico para cada documento segmentado."""
    segment_ids = [item["document_id"] for item in segments["documents"]]
    classification_ids = [
        item["document_id"] for item in classification["documents"]
    ]
    if len(segment_ids) != len(set(segment_ids)):
        raise ProceduralTimelineError("identificadores dos documentos segmentados devem ser únicos")
    if len(classification_ids) != len(set(classification_ids)):
        raise ProceduralTimelineError("identificadores dos documentos classificados devem ser únicos")
    if set(segment_ids) != set(classification_ids):
        raise ProceduralTimelineError("documentos segmentados e classificados devem coincidir")
    classified_by_id = {
        item["document_id"]: item for item in classification["documents"]
    }
    events = []
    gaps = []
    for document in segments["documents"]:
        document_id = document["document_id"]
        classified = classified_by_id[document_id]
        classification_status = classified["classification_status"]
        document_type = classified["document_type"]
        if classification_status not in {"classified", "conflict", "unknown"}:
            raise ProceduralTimelineError("estado da classificação não suportado")
        if document_type not in {*EVENT_PRESENTATION, "unknown"}:
            raise ProceduralTimelineError("tipo documental não suportado")
        if (classification_status == "classified") != (document_type != "unknown"):
            raise ProceduralTimelineError("estado e tipo da classificação são incompatíveis")
        presentation = EVENT_PRESENTATION.get(
            document_type,
            UNCLASSIFIED_EVENT,
        )
        if classification_status != "classified":
            reason_code = (
                "classification_conflict"
                if classification_status == "conflict"
                else "unclassified_document"
            )
            gaps.append(
                {
                    "subject_id": document_id,
                    "reason_code": reason_code,
                }
            )
        events.append(
            {
                "event_id": f"EVT-{document_id.removeprefix('DOC-')}",
                "event_date": document["filed_on"],
                "event_type": presentation[0],
                "summary": presentation[1],
                "source_document_id": document_id,
                "source_locator": _source_locator(document),
            }
        )

    result = {
        "schema_version": 1,
        "status": "partial" if gaps else "complete",
        "events": sorted(
            events,
            key=lambda item: (item["event_date"], item["event_id"]),
        ),
        "gaps": sorted(gaps, key=lambda item: item["subject_id"]),
    }
    schema = load_json(schema_path, "esquema da linha do tempo processual")
    issues = validate_schema_value(result, schema)
    if issues:
        raise ProceduralTimelineError("contrato da linha do tempo processual inválido")
    return result


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def write_timeline_artifact(
    timeline: dict,
    *,
    output_dir: Path,
    repository_root: Path,
) -> Path:
    """Grava linha do tempo protegida fora do repositório."""
    if output_dir.is_symlink():
        raise ProceduralTimelineError("diretório de saída não pode ser vínculo simbólico")
    destination = output_dir.resolve()
    repository = repository_root.resolve()
    if destination == repository or _is_within(destination, repository):
        raise ProceduralTimelineError("saída da linha do tempo deve ficar fora do repositório")
    if not destination.is_dir():
        raise ProceduralTimelineError("diretório de saída deve existir previamente")
    if stat.S_IMODE(destination.stat().st_mode) & 0o077:
        raise ProceduralTimelineError("diretório de saída deve ser privado")

    path = destination / "procedural-timeline.json"
    if path.exists() or path.is_symlink():
        raise ProceduralTimelineError("linha do tempo já existe; arquivo preservado")
    payload = (json.dumps(timeline, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monta linha do tempo protegida a partir dos segmentos classificados do PJe.",
    )
    parser.add_argument("--segments", required=True, type=Path, help="Mapa de segmentos do PDF")
    parser.add_argument("--classification", required=True, type=Path, help="Classificação documental")
    parser.add_argument("--output", required=True, type=Path, help="Diretório privado existente")
    parser.add_argument("--repository-root", type=Path, default=ROOT, help="Raiz do repositório")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Esquema da linha do tempo")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        segments = load_json(args.segments, "segmentos do PDF do PJe")
        classification = load_json(
            args.classification,
            "classificação documental",
        )
        timeline = build_procedural_timeline(
            segments,
            classification,
            schema_path=args.schema,
        )
        write_timeline_artifact(
            timeline,
            output_dir=args.output,
            repository_root=args.repository_root,
        )
    except (KeyError, OSError, ProceduralTimelineError, TypeError, ValueError) as error:
        print(f"[ERRO] Linha do tempo processual: {error}", file=sys.stderr)
        return 1

    print(
        f"[OK] Linha do tempo processual: {len(timeline['events'])} evento(s), "
        f"{len(timeline['gaps'])} lacuna(s), estado {timeline['status']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
