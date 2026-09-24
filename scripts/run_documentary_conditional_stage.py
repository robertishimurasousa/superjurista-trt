#!/usr/bin/env python3
"""Registra a etapa documental no mecanismo compartilhado de retomada TRT12."""

from __future__ import annotations

import stat
from pathlib import Path

from compose_documentary_conditional_stage import (
    DocumentaryConditionalStageError,
    publish_documentary_conditional_stage,
)
from load_documentary_claim_bundles import (
    DocumentaryClaimBundlesError,
    load_documentary_claim_bundles,
)
from resumable_pipeline import (
    ResumeContractError,
    plan_resume,
    record_stage_acceptance,
    save_execution_state_once,
)
from trt12_pipeline_gates import make_trt12_gate_validator


ROOT = Path(__file__).resolve().parents[1]
STAGE_ID = "execute-conditional-tracks"


class DocumentaryStageRunnerError(ValueError):
    """Indica que a etapa probatória não pode avançar no manifesto."""


def accept_documentary_conditional_stage(
    *,
    workspace: Path,
    plan: dict,
    state: dict,
    source_fingerprint: str,
    context: dict[str, str],
    authorization_scope_digest: str,
    payload_dir: Path,
    documentary_bundles: dict[str, dict],
    other_results: dict,
    attempt: int,
    state_output: Path | None = None,
) -> dict:
    """Compõe a prova validada e opcionalmente grava o checkpoint aceito."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise DocumentaryStageRunnerError("espaço de trabalho inválido")
    workspace = workspace.resolve()
    if workspace == ROOT or workspace.is_relative_to(ROOT):
        raise DocumentaryStageRunnerError("o processo não pode ser executado no repositório")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise DocumentaryStageRunnerError("espaço de trabalho deve ser privado")
    if state_output is not None:
        if (
            not isinstance(state_output, Path)
            or state_output.is_symlink()
            or state_output.parent.resolve() != workspace
            or state_output.exists()
        ):
            raise DocumentaryStageRunnerError("destino do estado inválido ou ocupado")

    try:
        validator = make_trt12_gate_validator(
            workspace, plan, authorization_scope_digest, payload_dir
        )
        resume = plan_resume(
            plan, workspace=workspace, state=state,
            source_fingerprint=source_fingerprint, context=context,
            gate_validator=validator,
        )
        if resume["next_stage"] != STAGE_ID:
            raise DocumentaryStageRunnerError(
                "a etapa documental não é a próxima etapa reutilizável do manifesto"
            )
        published = publish_documentary_conditional_stage(
            workspace, documentary_bundles, other_results=other_results
        )
        try:
            updated = record_stage_acceptance(
                plan, workspace=workspace, state=state, stage_id=STAGE_ID,
                source_fingerprint=source_fingerprint, context=context,
                gate_validator=validator, attempt=attempt,
            )
            if state_output is not None:
                save_execution_state_once(state_output, updated)
            return updated
        except Exception:
            for path in reversed(published):
                path.unlink(missing_ok=True)
            raise
    except (DocumentaryConditionalStageError, ResumeContractError, OSError, ValueError) as error:
        if isinstance(error, DocumentaryStageRunnerError):
            raise
        raise DocumentaryStageRunnerError("a etapa documental não foi aceita") from error


def accept_documentary_conditional_stage_from_files(
    *,
    workspace: Path,
    plan: dict,
    state: dict,
    source_fingerprint: str,
    context: dict[str, str],
    authorization_scope_digest: str,
    payload_dir: Path,
    other_results: dict,
    attempt: int,
    state_output: Path | None = None,
) -> dict:
    """Carrega observações protegidas e aplica o checkpoint existente."""
    try:
        bundles = load_documentary_claim_bundles(workspace)
    except DocumentaryClaimBundlesError as error:
        raise DocumentaryStageRunnerError("o lote documental não foi aceito") from error
    return accept_documentary_conditional_stage(
        workspace=workspace, plan=plan, state=state,
        source_fingerprint=source_fingerprint, context=context,
        authorization_scope_digest=authorization_scope_digest,
        payload_dir=payload_dir, documentary_bundles=bundles,
        other_results=other_results, attempt=attempt,
        state_output=state_output,
    )
