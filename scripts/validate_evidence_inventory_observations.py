#!/usr/bin/env python3
"""Confere fonte e cobertura das observações do inventariador probatório."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from PyPDF2 import PdfReader

from prepare_evidence_inventory_packets import (
    EvidenceInventoryPacketsError,
    build_evidence_inventory_packet,
)
from schema_validation import load_json, validate_schema_value


ROOT = Path(__file__).resolve().parents[1]
RESULT_SCHEMA = ROOT / "runtime/pipelines/evidence-inventory-observations.v1.schema.json"


class EvidenceInventoryObservationsError(ValueError):
    """Indica observação fora da fonte ou sem estado explícito de cobertura."""


def validate_evidence_inventory_observations(
    result: dict,
    *,
    packet: str,
    pdf_path: Path,
    segments: dict,
    claim_matrix: dict,
    document_id: str,
) -> None:
    """Verifica IDs e trechos literais sem julgar relevância ou valor probatório."""
    try:
        if validate_schema_value(
            result, load_json(RESULT_SCHEMA, "esquema do inventário probatório")
        ):
            raise EvidenceInventoryObservationsError("contrato de observações inválido")
        expected_packet = build_evidence_inventory_packet(
            pdf_path, segments, claim_matrix, document_id
        )
        if packet != expected_packet:
            raise EvidenceInventoryObservationsError("pacote diverge do PDF e da matriz")
        if result["source_document_id"] != document_id:
            raise EvidenceInventoryObservationsError("documento da observação diverge")
        if result["source_packet_sha256"] != hashlib.sha256(packet.encode("utf-8")).hexdigest():
            raise EvidenceInventoryObservationsError("resumo do pacote diverge")
        items = result["items"]
        if (result["coverage_status"] == "items_identified") != bool(items):
            raise EvidenceInventoryObservationsError("cobertura declarada diverge dos itens")
        if (not items or result["status"] == "insufficient") and not result["limitations"]:
            raise EvidenceInventoryObservationsError("lacuna exige limitação explícita")
        document = next(
            item for item in segments["documents"] if item["document_id"] == document_id
        )
        known_claims = {item["claim_id"] for item in claim_matrix["claims"]}
        reader = PdfReader(str(pdf_path))
        page_texts: dict[int, str] = {}
        for number, item in enumerate(items, start=1):
            if item["item_id"] != f"INV-{document_id}-{number:03d}":
                raise EvidenceInventoryObservationsError("ID de item fora da sequência documental")
            if not set(item["claim_ids"]) <= known_claims:
                raise EvidenceInventoryObservationsError("item vinculado a pedido desconhecido")
            page = item["excerpt"]["pdf_page"]
            if not document["page_start"] <= page <= document["page_end"]:
                raise EvidenceInventoryObservationsError("trecho fora do documento-fonte")
            if page not in page_texts:
                page_texts[page] = reader.pages[page - 1].extract_text() or ""
            excerpt = item["excerpt"]["text"]
            if not excerpt.strip() or excerpt not in page_texts[page]:
                raise EvidenceInventoryObservationsError("trecho não é literal na página")
    except (EvidenceInventoryPacketsError, OSError, TypeError, ValueError, KeyError, IndexError) as error:
        if isinstance(error, EvidenceInventoryObservationsError):
            raise
        raise EvidenceInventoryObservationsError("observações do inventário recusadas") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confere citações do inventário probatório sem avaliar a prova."
    )
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--document-id", required=True)
    args = parser.parse_args()
    try:
        for path in (args.result, args.packet, args.segments, args.matrix):
            if path.is_symlink() or not path.is_file():
                raise EvidenceInventoryObservationsError("insumo ausente ou vinculado")
        validate_evidence_inventory_observations(
            load_json(args.result, "observações do inventário"),
            packet=args.packet.read_text(encoding="utf-8"),
            pdf_path=args.pdf,
            segments=load_json(args.segments, "segmentos do PDF"),
            claim_matrix=load_json(args.matrix, "matriz de pedidos"),
            document_id=args.document_id,
        )
    except (OSError, TypeError, ValueError) as error:
        detail = (
            str(error) if isinstance(error, EvidenceInventoryObservationsError)
            else "entrada inválida"
        )
        print(f"[ERRO] Inventário probatório: {detail}", file=sys.stderr)
        return 2
    print("[OK] Trechos e IDs conferidos; seleção da matriz e revisão humana pendentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
