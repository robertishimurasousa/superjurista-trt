#!/usr/bin/env python3
"""Prepara pacotes documentais separados para todos os pedidos probatórios."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from build_conditional_work_plan import build_conditional_work_plan, iter_dispatches
from prepare_source_evidence_packet import EVIDENCE_SCHEMA, build_source_evidence_packet
from schema_validation import load_json
from segment_pje_pdf import segment_pje_pdf
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
INDEX_NAME = "documentary-packet-index.json"
SEGMENTS_NAME = "documentary-pje-pdf-segments.json"


class DocumentaryClaimPacketsError(ValueError):
    """Indica que o lote de fontes não pode ser publicado integralmente."""


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def prepare_documentary_claim_packets(workspace: Path, pdf_path: Path) -> dict:
    """Publica pacotes por pedido, sem despachar modelo ou produzir juízo jurídico."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise DocumentaryClaimPacketsError("espaço de trabalho inválido")
    workspace = workspace.resolve()
    if workspace == ROOT or workspace.is_relative_to(ROOT):
        raise DocumentaryClaimPacketsError("os pacotes não podem entrar no repositório")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise DocumentaryClaimPacketsError("espaço de trabalho deve ser privado")
    if (
        not isinstance(pdf_path, Path) or pdf_path.is_symlink()
        or not pdf_path.is_file() or pdf_path.resolve().parent != workspace
    ):
        raise DocumentaryClaimPacketsError("PDF original fora do espaço privado do caso")

    created: list[Path] = []
    try:
        for name in ("issue-route.json", "evidence-matrix.json"):
            path = workspace / name
            if path.is_symlink() or not path.is_file():
                raise DocumentaryClaimPacketsError(f"insumo ausente ou vinculado: {name}")
        routes = load_json(workspace / "issue-route.json", "rotas do processo")
        evidence = load_json(workspace / "evidence-matrix.json", "matriz probatória")
        if validate_document(
            evidence, load_json(EVIDENCE_SCHEMA, "esquema da matriz probatória")
        ):
            raise DocumentaryClaimPacketsError("matriz probatória inválida")
        plan = build_conditional_work_plan(routes)
        claim_ids = sorted({
            item.claim_id for item in iter_dispatches(plan)
            if item.track == "evidence_analysis"
        })
        if not claim_ids:
            raise DocumentaryClaimPacketsError("não há pedido encaminhado à prova")
        segments = segment_pje_pdf(pdf_path)
        records = []
        payloads = [(SEGMENTS_NAME, _encode(segments))]
        for claim_id in claim_ids:
            evidence_ids = tuple(sorted({
                item["evidence_id"] for item in evidence["evidence_items"]
                if claim_id in item["claim_ids"]
            }))
            if not evidence_ids or claim_id in evidence["uncovered_claim_ids"]:
                raise DocumentaryClaimPacketsError("pedido probatório sem cobertura de evidências")
            packet = build_source_evidence_packet(
                pdf_path, segments, evidence,
                claim_id=claim_id, evidence_ids=evidence_ids,
            )
            packet_name = f"{claim_id}-source-evidence-packet.md"
            payloads.append((packet_name, packet.encode("utf-8")))
            records.append({
                "claim_id": claim_id,
                "evidence_ids": list(evidence_ids),
                "packet_name": packet_name,
                "source_packet_sha256": hashlib.sha256(packet.encode("utf-8")).hexdigest(),
            })
        if _digest(pdf_path) != segments["source_pdf"]["sha256"]:
            raise DocumentaryClaimPacketsError("PDF original mudou durante o preparo")
        index = {
            "schema_version": 1,
            "source_pdf_name": pdf_path.name,
            "source_pdf_sha256": segments["source_pdf"]["sha256"],
            "segments_name": SEGMENTS_NAME,
            "records": records,
        }
        payloads.append((INDEX_NAME, _encode(index)))
        if any((workspace / name).exists() or (workspace / name).is_symlink()
               for name, _ in payloads):
            raise DocumentaryClaimPacketsError("saída documental já existe")
        for name, content in payloads:
            path = workspace / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
        return index
    except (OSError, TypeError, ValueError, KeyError, UnicodeError) as error:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        if isinstance(error, DocumentaryClaimPacketsError):
            raise
        raise DocumentaryClaimPacketsError("preparo documental em lote recusado") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepara pacotes privados por pedido probatório, sem chamar modelo."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    args = parser.parse_args()
    try:
        index = prepare_documentary_claim_packets(args.workspace, args.pdf)
    except DocumentaryClaimPacketsError as error:
        print(f"[ERRO] Pacotes documentais: {error}", file=sys.stderr)
        return 2
    print(f"[OK] Pacotes privados preparados para {len(index['records'])} pedido(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
