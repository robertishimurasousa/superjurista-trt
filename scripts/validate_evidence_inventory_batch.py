#!/usr/bin/env python3
"""Confere a cobertura técnica de todo o inventário probatório de um caso."""

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
from pathlib import Path

from prepare_evidence_inventory_packets import INDEX_NAME, SEGMENTS_NAME
from schema_validation import load_json
from validate_evidence_inventory_observations import validate_evidence_inventory_observations


ROOT = Path(__file__).resolve().parents[1]
MATRIX_NAME = "claim-matrix.json"


class EvidenceInventoryBatchError(ValueError):
    """Indica documento ausente, fonte alterada ou observação sem custódia."""


def _read_file(workspace: Path, name: str) -> bytes:
    path = workspace / name
    if path.is_symlink() or not path.is_file():
        raise EvidenceInventoryBatchError(f"insumo ausente ou vinculado: {name}")
    return path.read_bytes()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(name: object) -> str:
    if not isinstance(name, str) or name in {"", ".", ".."} or Path(name).name != name:
        raise EvidenceInventoryBatchError("nome do PDF original inválido")
    return name


def validate_evidence_inventory_batch(workspace: Path) -> dict[str, int]:
    """Revalida cada documento sem interpretar itens nem estabelecer exaustividade."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise EvidenceInventoryBatchError("espaço de trabalho inválido")
    workspace = workspace.resolve()
    if workspace == ROOT or workspace.is_relative_to(ROOT):
        raise EvidenceInventoryBatchError("os autos não podem estar no repositório")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise EvidenceInventoryBatchError("espaço de trabalho deve ser privado")
    try:
        _read_file(workspace, INDEX_NAME)
        index = load_json(workspace / INDEX_NAME, "índice do inventário")
        if not isinstance(index, dict) or set(index) != {
            "schema_version", "source_pdf_name", "source_pdf_sha256",
            "claim_matrix_sha256", "segments_name", "records",
        } or index["schema_version"] != 1 or index["segments_name"] != SEGMENTS_NAME:
            raise EvidenceInventoryBatchError("índice do inventário incompatível")
        pdf_name = _safe_name(index["source_pdf_name"])
        pdf_bytes = _read_file(workspace, pdf_name)
        matrix_bytes = _read_file(workspace, MATRIX_NAME)
        _read_file(workspace, SEGMENTS_NAME)
        if (_digest(pdf_bytes) != index["source_pdf_sha256"]
                or _digest(matrix_bytes) != index["claim_matrix_sha256"]):
            raise EvidenceInventoryBatchError("PDF ou matriz de pedidos diverge do índice")
        segments = load_json(workspace / SEGMENTS_NAME, "segmentos do PDF")
        matrix = load_json(workspace / MATRIX_NAME, "matriz de pedidos")
        documents = {item["document_id"]: item for item in segments["documents"]}
        records = index["records"]
        if (not isinstance(records, list) or not documents
                or len(records) != len(documents)
                or len(documents) != len(segments["documents"])):
            raise EvidenceInventoryBatchError("cobertura dos documentos incompleta")
        by_document = {}
        for record in records:
            if not isinstance(record, dict) or set(record) != {
                "document_id", "page_start", "page_end", "packet_name", "packet_sha256",
            }:
                raise EvidenceInventoryBatchError("registro documental inválido")
            document_id = record["document_id"]
            if not isinstance(document_id, str) or document_id in by_document:
                raise EvidenceInventoryBatchError("documento duplicado ou inválido")
            by_document[document_id] = record
        if set(by_document) != set(documents):
            raise EvidenceInventoryBatchError("índice diverge dos documentos do PDF")
        expected_packets = {
            f"{document_id}-inventory-source.md" for document_id in documents
        }
        expected_observations = {
            f"{document_id}-inventory-observations.json" for document_id in documents
        }
        if ({path.name for path in workspace.glob("DOC-*-inventory-source.md")}
                != expected_packets
                or {path.name for path in workspace.glob("DOC-*-inventory-observations.json")}
                != expected_observations):
            raise EvidenceInventoryBatchError("arquivos do inventário não cobrem apenas o PDF")

        summary = {
            "document_count": len(documents),
            "item_count": 0,
            "no_item_identified_count": 0,
            "insufficient_count": 0,
        }
        for document_id in sorted(documents):
            record = by_document[document_id]
            document = documents[document_id]
            packet_name = f"{document_id}-inventory-source.md"
            if (record["packet_name"] != packet_name
                    or record["page_start"] != document["page_start"]
                    or record["page_end"] != document["page_end"]):
                raise EvidenceInventoryBatchError("registro do pacote diverge do PDF")
            packet_bytes = _read_file(workspace, packet_name)
            if _digest(packet_bytes) != record["packet_sha256"]:
                raise EvidenceInventoryBatchError("pacote documental alterado")
            packet = packet_bytes.decode("utf-8")
            observation_name = f"{document_id}-inventory-observations.json"
            _read_file(workspace, observation_name)
            result = load_json(workspace / observation_name, "observação do inventário")
            validate_evidence_inventory_observations(
                result, packet=packet, pdf_path=workspace / pdf_name,
                segments=segments, claim_matrix=matrix, document_id=document_id,
            )
            summary["item_count"] += len(result["items"])
            summary["no_item_identified_count"] += result["coverage_status"] == "no_item_identified"
            summary["insufficient_count"] += result["status"] == "insufficient"
        return summary
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, EvidenceInventoryBatchError):
            raise
        raise EvidenceInventoryBatchError("lote do inventário probatório recusado") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confere todos os arquivos do inventário sem avaliar a prova."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        summary = validate_evidence_inventory_batch(args.workspace)
    except EvidenceInventoryBatchError as error:
        print(f"[ERRO] Lote do inventário probatório: {error}", file=sys.stderr)
        return 2
    print(
        f"[OK] Cobertura técnica de {summary['document_count']} documento(s), "
        f"{summary['item_count']} item(ns), "
        f"{summary['no_item_identified_count']} sem item identificado, "
        f"{summary['insufficient_count']} insuficiente(s); revisão humana pendente."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
