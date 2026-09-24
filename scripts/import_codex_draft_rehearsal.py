#!/usr/bin/env python3
"""Importa dispositivo fictício do Codex ao checkpoint compartilhado do TRT12."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from build_claim_decisions import render_judgment_draft
from import_codex_claim_analysis_rehearsal import (
    _private_directory, _verify_synthetic_target,
)
from resumable_pipeline import plan_resume
from run_codex_claim_analysis_rehearsal import EXPECTED_FIXTURE_SHA256, MODEL_ID
from run_codex_draft_rehearsal import (
    AGENT, DRAFT, OUTPUT, RESULT_SCHEMA, SUMMARY,
    _require_pending_disposition, _verified_analysis,
)
from run_draft_judgment_stage import accept_draft_judgment_stage
from schema_validation import load_json, validate_schema_value
from trt12_pipeline_gates import make_trt12_gate_validator


REHEARSAL_FILES = {OUTPUT, DRAFT, SUMMARY}


class CodexDraftImportError(ValueError):
    """Indica que a minuta do ensaio não corresponde ao checkpoint atual."""


def _read_draft_rehearsal(source: Path) -> tuple[dict, dict, bytes, bytes]:
    if {path.name for path in source.iterdir()} != REHEARSAL_FILES:
        raise CodexDraftImportError("arquivos do ensaio de minuta divergentes")
    contents = {}
    for name in REHEARSAL_FILES:
        path = source / name
        if (
            path.is_symlink() or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) & 0o077
        ):
            raise CodexDraftImportError("arquivo da minuta desprotegido")
        contents[name] = path.read_bytes()
    summary = json.loads(contents[SUMMARY].decode("utf-8"))
    dispositions = json.loads(contents[OUTPUT].decode("utf-8"))
    if not isinstance(summary, dict) or not isinstance(dispositions, dict):
        raise CodexDraftImportError("JSON do ensaio de minuta inválido")
    return summary, dispositions, contents[OUTPUT], contents[DRAFT]


def import_codex_draft_rehearsal(
    *, rehearsal_workspace: Path, analysis_workspace: Path, workspace: Path,
    plan: dict, state: dict, source_fingerprint: str,
    context: dict[str, str], authorization_scope_digest: str,
    payload_dir: Path, expected_model_id: str,
    expected_analysis_model_id: str, attempt: int,
    expected_execution_mode: str = "codex_cli",
    expected_analysis_mode: str = "codex_cli",
    state_output: Path | None = None,
) -> dict:
    """Confere resposta, recibos e insumos atuais antes de aceitar a minuta."""
    target = _private_directory(workspace, "espaço do processo")
    source = _private_directory(rehearsal_workspace, "espaço do ensaio de minuta")
    analysis_source = _private_directory(analysis_workspace, "espaço da análise")
    if len({target, source, analysis_source}) != 3:
        raise CodexDraftImportError("origem, análise e processo devem ser distintos")
    if not isinstance(plan, dict) or plan.get("runtime") != "codex":
        raise CodexDraftImportError("o ensaio Codex exige plano do ambiente Codex")
    if (
        not isinstance(expected_model_id, str) or MODEL_ID.fullmatch(expected_model_id) is None
        or not isinstance(expected_analysis_model_id, str)
        or MODEL_ID.fullmatch(expected_analysis_model_id) is None
        or expected_execution_mode not in {"codex_cli", "simulated"}
        or expected_analysis_mode not in {"codex_cli", "simulated"}
    ):
        raise CodexDraftImportError("identidade esperada do ensaio inválida")
    try:
        validator = make_trt12_gate_validator(
            target, plan, authorization_scope_digest, payload_dir
        )
        if plan_resume(
            plan, workspace=target, state=state,
            source_fingerprint=source_fingerprint, context=context,
            gate_validator=validator,
        )["next_stage"] != "draft-judgment":
            raise CodexDraftImportError("a minuta não é a próxima etapa")
        analysis, analysis_bytes, receipt_bytes = _verified_analysis(
            analysis_source, expected_analysis_model_id, expected_analysis_mode
        )
        current_analysis = target / "claim-analysis.json"
        if current_analysis.is_symlink() or current_analysis.read_bytes() != analysis_bytes:
            raise CodexDraftImportError("análise atual difere da enviada ao fundamentador")
        _verify_synthetic_target(target, payload_dir)
        summary, dispositions, disposition_bytes, draft_bytes = _read_draft_rehearsal(source)
        if (
            validate_schema_value(
                summary, load_json(RESULT_SCHEMA, "esquema do ensaio de minuta")
            )
            or summary["model_id"] != expected_model_id
            or summary["execution_mode"] != expected_execution_mode
            or summary["agent_sha256"] != hashlib.sha256(AGENT.read_bytes()).hexdigest()
            or summary["fixture_sha256"] != EXPECTED_FIXTURE_SHA256
            or summary["analysis_sha256"] != hashlib.sha256(analysis_bytes).hexdigest()
            or summary["analysis_receipt_sha256"] != hashlib.sha256(receipt_bytes).hexdigest()
            or summary["disposition_sha256"] != hashlib.sha256(disposition_bytes).hexdigest()
            or summary["draft_sha256"] != hashlib.sha256(draft_bytes).hexdigest()
        ):
            raise CodexDraftImportError("resumo ou identidade da minuta diverge")
        _require_pending_disposition(dispositions)
        if draft_bytes != render_judgment_draft(analysis, dispositions).encode("utf-8"):
            raise CodexDraftImportError("minuta difere da renderização determinística")
        return accept_draft_judgment_stage(
            workspace=target, plan=plan, state=state,
            source_fingerprint=source_fingerprint, context=context,
            authorization_scope_digest=authorization_scope_digest,
            payload_dir=payload_dir, dispositions=dispositions,
            attempt=attempt, state_output=state_output,
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        if isinstance(error, CodexDraftImportError):
            raise
        raise CodexDraftImportError("o ensaio de minuta não foi importado") from error
