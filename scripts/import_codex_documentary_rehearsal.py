#!/usr/bin/env python3
"""Importa um ensaio documental fictício do Codex para o checkpoint TRT12."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from build_conditional_work_plan import build_conditional_work_plan, iter_dispatches
from build_documentary_work_records import build_documentary_work_records
from prepare_source_evidence_packet import build_source_evidence_packet
from resumable_pipeline import plan_resume
from run_codex_documentary_rehearsal import (
    AGENT,
    CLAIM_ID,
    EVIDENCE_IDS,
    RESULT_SCHEMA,
    _synthetic_evidence,
    _synthetic_pdf,
)
from run_documentary_conditional_stage import accept_documentary_conditional_stage
from schema_validation import load_json, validate_schema_value
from segment_pje_pdf import segment_pje_pdf
from trt12_pipeline_gates import make_trt12_gate_validator
from validate_documentary_observations import validate_documentary_observations


ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "synthetic-source.pdf", "pje-pdf-segments.json", "evidence-matrix.json",
    "source-evidence-packet.md", "documentary-observations.json",
    "evidence-review-fragment.json", "conditional-work-result-fragment.json",
    "documentary-rehearsal-summary.json",
}


class DocumentaryRehearsalImportError(ValueError):
    """Indica que o ensaio não pode ser incorporado ao checkpoint."""


def _private_workspace(path: Path, label: str) -> Path:
    if not isinstance(path, Path) or path.is_symlink() or not path.is_dir():
        raise DocumentaryRehearsalImportError(f"{label} inválido")
    resolved = path.resolve()
    if resolved == ROOT or resolved.is_relative_to(ROOT):
        raise DocumentaryRehearsalImportError(f"{label} não pode ficar no repositório")
    if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise DocumentaryRehearsalImportError(f"{label} deve ser privado")
    return resolved


def _read_rehearsal(workspace: Path) -> dict[str, bytes]:
    if {item.name for item in workspace.iterdir()} != FILES:
        raise DocumentaryRehearsalImportError("arquivos do ensaio divergentes")
    contents = {}
    for name in FILES:
        path = workspace / name
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise DocumentaryRehearsalImportError("arquivo do ensaio ausente ou desprotegido")
        contents[name] = path.read_bytes()
    return contents


def _json_file(contents: dict[str, bytes], name: str) -> dict:
    value = json.loads(contents[name].decode("utf-8"))
    if not isinstance(value, dict):
        raise DocumentaryRehearsalImportError("JSON do ensaio inválido")
    return value


def _checked_bundle(contents: dict[str, bytes], expected_model_id: str, workspace: Path) -> dict:
    summary = _json_file(contents, "documentary-rehearsal-summary.json")
    if (
        validate_schema_value(summary, load_json(RESULT_SCHEMA, "esquema do ensaio"))
        or summary["model_id"] != expected_model_id
        or summary["agent_sha256"] != hashlib.sha256(AGENT.read_bytes()).hexdigest()
    ):
        raise DocumentaryRehearsalImportError("identidade do ensaio diverge")
    source = contents["synthetic-source.pdf"]
    evidence = _json_file(contents, "evidence-matrix.json")
    segments = _json_file(contents, "pje-pdf-segments.json")
    observations = _json_file(contents, "documentary-observations.json")
    packet = contents["source-evidence-packet.md"].decode("utf-8")
    if source != _synthetic_pdf() or evidence != _synthetic_evidence():
        raise DocumentaryRehearsalImportError("o ensaio não contém a fonte fictícia fixa")
    hashes = {
        "source_pdf_sha256": "synthetic-source.pdf",
        "source_packet_sha256": "source-evidence-packet.md",
        "observations_sha256": "documentary-observations.json",
        "review_fragment_sha256": "evidence-review-fragment.json",
        "receipt_fragment_sha256": "conditional-work-result-fragment.json",
    }
    if any(
        hashlib.sha256(contents[name]).hexdigest() != summary[key]
        for key, name in hashes.items()
    ) or observations.get("status") != summary["status"]:
        raise DocumentaryRehearsalImportError("resumos do ensaio divergem dos arquivos")
    source_path = workspace / "synthetic-source.pdf"
    if source_path.exists() or source_path.is_symlink():
        raise DocumentaryRehearsalImportError("a fonte sintética já existe no caso")
    return {
        "source": source, "evidence": evidence, "segments": segments,
        "observations": observations, "packet": packet,
        "review_fragment": _json_file(contents, "evidence-review-fragment.json"),
        "receipt_fragment": _json_file(contents, "conditional-work-result-fragment.json"),
    }


def import_codex_documentary_rehearsal(
    *, rehearsal_workspace: Path, workspace: Path, plan: dict, state: dict,
    source_fingerprint: str, context: dict[str, str],
    authorization_scope_digest: str, payload_dir: Path, other_results: dict,
    expected_model_id: str, attempt: int, state_output: Path | None = None,
) -> dict:
    """Aceita apenas fonte fictícia íntegra e devolve o checkpoint compartilhado."""
    source_workspace = _private_workspace(rehearsal_workspace, "espaço do ensaio")
    target = _private_workspace(workspace, "espaço do processo")
    if source_workspace == target:
        raise DocumentaryRehearsalImportError("origem e destino devem ser distintos")
    try:
        validator = make_trt12_gate_validator(
            target, plan, authorization_scope_digest, payload_dir
        )
        if plan_resume(
            plan, workspace=target, state=state,
            source_fingerprint=source_fingerprint, context=context,
            gate_validator=validator,
        )["next_stage"] != "execute-conditional-tracks":
            raise DocumentaryRehearsalImportError("a etapa documental não é a próxima")
        contents = _read_rehearsal(source_workspace)
        bundle = _checked_bundle(contents, expected_model_id, target)
        if load_json(target / "evidence-matrix.json", "matriz probatória") != bundle["evidence"]:
            raise DocumentaryRehearsalImportError("matriz do processo diverge do ensaio")
        routes = load_json(target / "issue-route.json", "rotas do processo")
        work_plan = build_conditional_work_plan(routes)
        evidence_claims = {
            item.claim_id for item in iter_dispatches(work_plan)
            if item.track == "evidence_analysis"
        }
        if evidence_claims != {CLAIM_ID}:
            raise DocumentaryRehearsalImportError("pedidos probatórios divergem do ensaio")
        destination = target / "synthetic-source.pdf"
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(bundle["source"])
            if segment_pje_pdf(destination) != bundle["segments"]:
                raise DocumentaryRehearsalImportError("segmentos do ensaio divergentes")
            expected_packet = build_source_evidence_packet(
                destination, bundle["segments"], bundle["evidence"],
                claim_id=CLAIM_ID, evidence_ids=EVIDENCE_IDS,
            )
            if bundle["packet"] != expected_packet:
                raise DocumentaryRehearsalImportError("pacote do ensaio diverge")
            validate_documentary_observations(
                bundle["observations"], packet=expected_packet,
                pdf_path=destination, segments=bundle["segments"],
                evidence_matrix=bundle["evidence"],
                claim_id=CLAIM_ID, evidence_ids=EVIDENCE_IDS,
            )
            review, receipt = build_documentary_work_records(
                work_plan, bundle["observations"], packet=expected_packet,
                pdf_path=destination, segments=bundle["segments"],
                evidence_matrix=bundle["evidence"],
                claim_id=CLAIM_ID, evidence_ids=EVIDENCE_IDS,
            )
            if review != bundle["review_fragment"] or receipt != bundle["receipt_fragment"]:
                raise DocumentaryRehearsalImportError("fragmentos do ensaio divergentes")
            return accept_documentary_conditional_stage(
                workspace=target, plan=plan, state=state,
                source_fingerprint=source_fingerprint, context=context,
                authorization_scope_digest=authorization_scope_digest,
                payload_dir=payload_dir,
                documentary_bundles={CLAIM_ID: {
                    "observations": bundle["observations"], "packet": expected_packet,
                    "pdf_path": destination, "segments": bundle["segments"],
                    "evidence_ids": EVIDENCE_IDS,
                }},
                other_results=other_results, attempt=attempt, state_output=state_output,
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as error:
        if isinstance(error, DocumentaryRehearsalImportError):
            raise
        raise DocumentaryRehearsalImportError("o ensaio documental não foi incorporado") from error
