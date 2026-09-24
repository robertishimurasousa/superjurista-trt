#!/usr/bin/env python3
"""Confere a custódia de observações documentais por pedido."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from PyPDF2 import PdfReader

from prepare_source_evidence_packet import (
    SourceEvidencePacketError,
    build_source_evidence_packet,
)
from schema_validation import load_json
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
RESULT_SCHEMA = ROOT / "runtime/pipelines/documentary-observations.v1.schema.json"


class DocumentaryObservationsError(ValueError):
    """Indica observações sem cobertura ou citação verificável."""


def validate_documentary_observations(
    result: dict, *, packet: str, pdf_path: Path, segments: dict,
    evidence_matrix: dict, claim_id: str, evidence_ids: tuple[str, ...],
) -> None:
    """Confere cobertura e literalidade, sem validar a interpretação jurídica."""
    issues = validate_document(result, load_json(RESULT_SCHEMA, "esquema de observações"))
    if issues:
        raise DocumentaryObservationsError("contrato de observações inválido")
    try:
        expected_packet = build_source_evidence_packet(
            pdf_path, segments, evidence_matrix,
            claim_id=claim_id, evidence_ids=evidence_ids,
        )
    except SourceEvidencePacketError as error:
        raise DocumentaryObservationsError(str(error)) from error
    if packet != expected_packet:
        raise DocumentaryObservationsError("pacote de fontes diverge do PDF e da seleção")
    if result["source_packet_sha256"] != hashlib.sha256(packet.encode("utf-8")).hexdigest():
        raise DocumentaryObservationsError("resumo do pacote de fontes diverge")
    if result["claim_id"] != claim_id:
        raise DocumentaryObservationsError("pedido da observação diverge")

    received = {}
    for observation in result["observations"]:
        evidence_id = observation["evidence_id"]
        if evidence_id in received:
            raise DocumentaryObservationsError("evidência duplicada no resultado")
        received[evidence_id] = observation
    if set(received) != set(evidence_ids):
        raise DocumentaryObservationsError("cobertura de evidências selecionadas diverge")

    evidence = {item["evidence_id"]: item for item in evidence_matrix["evidence_items"]}
    documents = {item["document_id"]: item for item in segments["documents"]}
    reader = PdfReader(str(pdf_path))
    page_texts: dict[int, str] = {}
    has_missing_excerpt = False
    for evidence_id, observation in received.items():
        source_document_id = evidence[evidence_id]["source_document_id"]
        if observation["source_document_id"] != source_document_id:
            raise DocumentaryObservationsError("documento da observação diverge da evidência")
        document = documents[source_document_id]
        excerpts = observation["excerpts"]
        if not excerpts:
            has_missing_excerpt = True
            if result["status"] != "insufficient" or not observation["limitations"]:
                raise DocumentaryObservationsError("fonte sem trecho exige limitação e estado insufficient")
        for excerpt in excerpts:
            page = excerpt["pdf_page"]
            if not document["page_start"] <= page <= document["page_end"]:
                raise DocumentaryObservationsError("página fora do documento da evidência")
            if page not in page_texts:
                page_texts[page] = reader.pages[page - 1].extract_text() or ""
            literal = excerpt["text"]
            if not literal.strip() or literal not in page_texts[page]:
                raise DocumentaryObservationsError("trecho não é citação literal da página")
    if result["status"] == "insufficient" and not has_missing_excerpt:
        raise DocumentaryObservationsError("estado insufficient sem fonte lacunar")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confere observações documentais sem emitir conclusão jurídica."
    )
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--evidence-id", required=True, action="append")
    args = parser.parse_args()
    try:
        if args.packet.is_symlink() or not args.packet.is_file():
            raise DocumentaryObservationsError("pacote de fontes ausente ou vínculo simbólico")
        validate_documentary_observations(
            load_json(args.result, "observações documentais"),
            packet=args.packet.read_text(encoding="utf-8"),
            pdf_path=args.pdf,
            segments=load_json(args.segments, "segmentos do PDF"),
            evidence_matrix=load_json(args.evidence, "matriz de provas"),
            claim_id=args.claim_id,
            evidence_ids=tuple(args.evidence_id),
        )
    except (OSError, TypeError, ValueError) as error:
        detail = str(error) if isinstance(error, DocumentaryObservationsError) else "entrada inválida"
        print(f"[ERRO] Observações documentais: {detail}", file=sys.stderr)
        return 2
    print("[OK] Citações e cobertura conferidas; interpretação jurídica pendente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
