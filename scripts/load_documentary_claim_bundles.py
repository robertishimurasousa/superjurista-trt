#!/usr/bin/env python3
"""Carrega pacotes e observações documentais de um caso privado por pedido."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

from build_conditional_work_plan import build_conditional_work_plan, iter_dispatches
from prepare_documentary_claim_packets import INDEX_NAME, SEGMENTS_NAME
from prepare_source_evidence_packet import EVIDENCE_SCHEMA, SEGMENT_SCHEMA
from schema_validation import load_json
from validate_artifact_contracts import validate_document
from validate_documentary_observations import validate_documentary_observations


ROOT = Path(__file__).resolve().parents[1]


class DocumentaryClaimBundlesError(ValueError):
    """Indica divergência entre rotas, fontes e observações protegidas."""


def _read_json(workspace: Path, name: str) -> dict:
    path = workspace / name
    if path.is_symlink() or not path.is_file():
        raise DocumentaryClaimBundlesError(f"insumo ausente ou vinculado: {name}")
    return load_json(path, name)


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_documentary_claim_bundles(workspace: Path) -> dict[str, dict]:
    """Revalida o lote inteiro antes de entregá-lo ao compositor existente."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise DocumentaryClaimBundlesError("espaço de trabalho inválido")
    workspace = workspace.resolve()
    if workspace == ROOT or workspace.is_relative_to(ROOT):
        raise DocumentaryClaimBundlesError("os autos não podem estar no repositório")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise DocumentaryClaimBundlesError("espaço de trabalho deve ser privado")
    try:
        index = _read_json(workspace, INDEX_NAME)
        routes = _read_json(workspace, "issue-route.json")
        evidence = _read_json(workspace, "evidence-matrix.json")
        segments = _read_json(workspace, SEGMENTS_NAME)
        if validate_document(evidence, load_json(EVIDENCE_SCHEMA, "esquema probatório")):
            raise DocumentaryClaimBundlesError("matriz probatória inválida")
        if validate_document(segments, load_json(SEGMENT_SCHEMA, "esquema de segmentos")):
            raise DocumentaryClaimBundlesError("segmentos do PDF inválidos")
        claim_ids = sorted({
            item.claim_id for item in iter_dispatches(build_conditional_work_plan(routes))
            if item.track == "evidence_analysis"
        })
        if not claim_ids or not isinstance(index, dict) or set(index) != {
            "schema_version", "source_pdf_name", "source_pdf_sha256",
            "segments_name", "records",
        } or index["schema_version"] != 1 or index["segments_name"] != SEGMENTS_NAME:
            raise DocumentaryClaimBundlesError("índice documental incompatível")
        name = index["source_pdf_name"]
        if not isinstance(name, str) or Path(name).name != name or name in {"", ".", ".."}:
            raise DocumentaryClaimBundlesError("nome do PDF original inválido")
        pdf_path = workspace / name
        if pdf_path.is_symlink() or not pdf_path.is_file():
            raise DocumentaryClaimBundlesError("PDF original ausente ou vinculado")
        if (
            _digest(pdf_path) != index["source_pdf_sha256"]
            or segments["source_pdf"]["sha256"] != index["source_pdf_sha256"]
        ):
            raise DocumentaryClaimBundlesError("PDF original diverge do lote")
        records = index["records"]
        if not isinstance(records, list) or len(records) != len(claim_ids):
            raise DocumentaryClaimBundlesError("cobertura do lote incompleta")
        by_claim = {}
        for record in records:
            if not isinstance(record, dict) or set(record) != {
                "claim_id", "evidence_ids", "packet_name", "source_packet_sha256",
            }:
                raise DocumentaryClaimBundlesError("registro documental inválido")
            claim_id = record["claim_id"]
            if not isinstance(claim_id, str) or claim_id in by_claim:
                raise DocumentaryClaimBundlesError("pedido documental duplicado ou inválido")
            by_claim[claim_id] = record
        if set(by_claim) != set(claim_ids):
            raise DocumentaryClaimBundlesError("pedidos do lote divergem das rotas")
        expected_observation_names = {
            f"{claim_id}-documentary-observations.json" for claim_id in claim_ids
        }
        found_observation_names = {
            path.name for path in workspace.glob("CLM-*-documentary-observations.json")
        }
        if found_observation_names != expected_observation_names:
            raise DocumentaryClaimBundlesError("cobertura dos arquivos de observação diverge")

        bundles = {}
        for claim_id in claim_ids:
            record = by_claim[claim_id]
            evidence_ids = tuple(sorted({
                item["evidence_id"] for item in evidence["evidence_items"]
                if claim_id in item["claim_ids"]
            }))
            if (
                not evidence_ids
                or claim_id in evidence["uncovered_claim_ids"]
                or record["evidence_ids"] != list(evidence_ids)
                or record["packet_name"] != f"{claim_id}-source-evidence-packet.md"
            ):
                raise DocumentaryClaimBundlesError("evidências do pedido divergem do lote")
            packet_path = workspace / record["packet_name"]
            if packet_path.is_symlink() or not packet_path.is_file():
                raise DocumentaryClaimBundlesError("pacote de fontes ausente ou vinculado")
            packet = packet_path.read_text(encoding="utf-8")
            if hashlib.sha256(packet.encode("utf-8")).hexdigest() != record["source_packet_sha256"]:
                raise DocumentaryClaimBundlesError("pacote de fontes alterado")
            observations = _read_json(
                workspace, f"{claim_id}-documentary-observations.json"
            )
            validate_documentary_observations(
                observations, packet=packet, pdf_path=pdf_path,
                segments=segments, evidence_matrix=evidence,
                claim_id=claim_id, evidence_ids=evidence_ids,
            )
            bundles[claim_id] = {
                "pdf_path": pdf_path,
                "segments": segments,
                "packet": packet,
                "evidence_ids": evidence_ids,
                "observations": observations,
            }
        return bundles
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, DocumentaryClaimBundlesError):
            raise
        raise DocumentaryClaimBundlesError("lote de observações documentais recusado") from error
