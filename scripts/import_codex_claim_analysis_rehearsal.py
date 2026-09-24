#!/usr/bin/env python3
"""Importa análise fictícia do Codex ao checkpoint compartilhado do TRT12."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from resumable_pipeline import plan_resume
from run_claim_analysis_stage import accept_claim_analysis_stage
from run_codex_claim_analysis_rehearsal import (
    AGENT, EXPECTED_FIXTURE_SHA256, FIXTURE, INPUTS, MODEL_ID,
    OUTPUT, RESULT_SCHEMA, SUMMARY, _require_synthetic_pending_analysis,
    _synthetic_document_index,
)
from schema_validation import load_json, validate_schema_value
from trt12_pipeline_gates import make_trt12_gate_validator


ROOT = Path(__file__).resolve().parents[1]
REHEARSAL_FILES = {OUTPUT, SUMMARY}


class CodexClaimAnalysisImportError(ValueError):
    """Indica que o ensaio não corresponde ao checkpoint atual."""


def _private_directory(path: Path, label: str) -> Path:
    if not isinstance(path, Path) or path.is_symlink() or not path.is_dir():
        raise CodexClaimAnalysisImportError(f"{label} inválido")
    resolved = path.resolve()
    if resolved == ROOT or resolved.is_relative_to(ROOT):
        raise CodexClaimAnalysisImportError(f"{label} não pode ficar no repositório")
    if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise CodexClaimAnalysisImportError(f"{label} deve ser privado")
    return resolved


def _read_rehearsal(source: Path) -> tuple[dict, dict, bytes]:
    if {path.name for path in source.iterdir()} != REHEARSAL_FILES:
        raise CodexClaimAnalysisImportError("arquivos do ensaio divergentes")
    contents = {}
    for name in REHEARSAL_FILES:
        path = source / name
        if (
            path.is_symlink() or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) & 0o077
        ):
            raise CodexClaimAnalysisImportError("arquivo do ensaio desprotegido")
        contents[name] = path.read_bytes()
    summary = json.loads(contents[SUMMARY].decode("utf-8"))
    analysis = json.loads(contents[OUTPUT].decode("utf-8"))
    if not isinstance(summary, dict) or not isinstance(analysis, dict):
        raise CodexClaimAnalysisImportError("JSON do ensaio inválido")
    return summary, analysis, contents[OUTPUT]


def _verify_synthetic_target(target: Path, payload_dir: Path) -> None:
    fixture_bytes = FIXTURE.read_bytes()
    if hashlib.sha256(fixture_bytes).hexdigest() != EXPECTED_FIXTURE_SHA256:
        raise CodexClaimAnalysisImportError("amostra sintética versionada alterada")
    artifacts = load_json(FIXTURE, "amostra sintética do TRT12")["artifacts"]
    for name in ("case-context.json", *INPUTS):
        path = target / name
        if path.is_symlink() or load_json(path, name) != artifacts[name]:
            raise CodexClaimAnalysisImportError(
                f"insumo atual não corresponde ao enviado ao modelo: {name}"
            )
    index_path = target / "document-index.json"
    if index_path.is_symlink() or load_json(index_path, "índice PJe") != (
        _synthetic_document_index(artifacts["case-context.json"])
    ):
        raise CodexClaimAnalysisImportError("índice do processo não é a amostra fictícia")
    if (
        not isinstance(payload_dir, Path) or payload_dir.is_symlink()
        or payload_dir.resolve() != (target / "pje-payloads").resolve()
        or not payload_dir.is_dir()
    ):
        raise CodexClaimAnalysisImportError("cargas sintéticas do PJe inválidas")
    if {path.name for path in payload_dir.iterdir()} != {"DOC-001.bin", "DOC-002.bin"}:
        raise CodexClaimAnalysisImportError("cargas sintéticas do PJe divergentes")
    for document_id in ("DOC-001", "DOC-002"):
        path = payload_dir / f"{document_id}.bin"
        if path.is_symlink() or path.read_bytes() != f"conteudo sintetico {document_id}".encode():
            raise CodexClaimAnalysisImportError("carga sintética do PJe diverge")


def import_codex_claim_analysis_rehearsal(
    *, rehearsal_workspace: Path, workspace: Path,
    plan: dict, state: dict, source_fingerprint: str,
    context: dict[str, str], authorization_scope_digest: str,
    payload_dir: Path, expected_model_id: str, attempt: int,
    expected_execution_mode: str = "codex_cli",
    state_output: Path | None = None,
) -> dict:
    """Confere resposta e insumos fixos antes de aceitar a etapa de análise."""
    source = _private_directory(rehearsal_workspace, "espaço do ensaio")
    target = _private_directory(workspace, "espaço do processo")
    if source == target:
        raise CodexClaimAnalysisImportError("origem e destino devem ser distintos")
    if not isinstance(plan, dict) or plan.get("runtime") != "codex":
        raise CodexClaimAnalysisImportError("o ensaio Codex exige plano do ambiente Codex")
    if (
        not isinstance(expected_model_id, str)
        or MODEL_ID.fullmatch(expected_model_id) is None
        or expected_execution_mode not in {"codex_cli", "simulated"}
    ):
        raise CodexClaimAnalysisImportError("identidade esperada do ensaio inválida")
    try:
        validator = make_trt12_gate_validator(
            target, plan, authorization_scope_digest, payload_dir
        )
        if plan_resume(
            plan, workspace=target, state=state,
            source_fingerprint=source_fingerprint, context=context,
            gate_validator=validator,
        )["next_stage"] != "analyze-claims":
            raise CodexClaimAnalysisImportError("a análise não é a próxima etapa")
        summary, analysis, analysis_bytes = _read_rehearsal(source)
        if (
            validate_schema_value(
                summary, load_json(RESULT_SCHEMA, "esquema do ensaio de análise")
            )
            or summary["model_id"] != expected_model_id
            or summary["execution_mode"] != expected_execution_mode
            or summary["agent_sha256"] != hashlib.sha256(AGENT.read_bytes()).hexdigest()
            or summary["fixture_sha256"] != EXPECTED_FIXTURE_SHA256
            or summary["analysis_sha256"] != hashlib.sha256(analysis_bytes).hexdigest()
        ):
            raise CodexClaimAnalysisImportError("resumo ou identidade do ensaio diverge")
        _require_synthetic_pending_analysis(analysis)
        _verify_synthetic_target(target, payload_dir)
        return accept_claim_analysis_stage(
            workspace=target, plan=plan, state=state,
            source_fingerprint=source_fingerprint, context=context,
            authorization_scope_digest=authorization_scope_digest,
            payload_dir=payload_dir, analysis=analysis, attempt=attempt,
            state_output=state_output,
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        if isinstance(error, CodexClaimAnalysisImportError):
            raise
        raise CodexClaimAnalysisImportError("o ensaio de análise não foi importado") from error
