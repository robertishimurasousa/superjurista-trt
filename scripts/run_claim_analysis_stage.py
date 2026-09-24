#!/usr/bin/env python3
"""Publica uma análise por pedido apenas no próximo checkpoint do TRT12."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from resumable_pipeline import (
    ResumeContractError, plan_resume, record_stage_acceptance,
    save_execution_state_once,
)
from trt12_pipeline_gates import make_trt12_gate_validator


ROOT = Path(__file__).resolve().parents[1]
STAGE_ID = "analyze-claims"
OUTPUT = "claim-analysis.json"


class ClaimAnalysisStageError(ValueError):
    """Indica que a análise não pode ser publicada ou aceita."""


def accept_claim_analysis_stage(
    *, workspace: Path, plan: dict, state: dict,
    source_fingerprint: str, context: dict[str, str],
    authorization_scope_digest: str, payload_dir: Path,
    analysis: dict, attempt: int, state_output: Path | None = None,
) -> dict:
    """Confere a ordem, publica uma vez e registra o controle já existente."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise ClaimAnalysisStageError("espaço do processo inválido")
    target = workspace.resolve()
    if target == ROOT or target.is_relative_to(ROOT):
        raise ClaimAnalysisStageError("o processo não pode ser executado no repositório")
    if stat.S_IMODE(target.stat().st_mode) & 0o077:
        raise ClaimAnalysisStageError("espaço do processo deve ser privado")
    output = target / OUTPUT
    if output.exists() or output.is_symlink():
        raise ClaimAnalysisStageError("análise já existente não será sobrescrita")
    if state_output is not None and (
        not isinstance(state_output, Path)
        or state_output.is_symlink()
        or state_output.parent.resolve() != target
        or state_output.exists()
    ):
        raise ClaimAnalysisStageError("destino do estado inválido ou ocupado")

    try:
        validator = make_trt12_gate_validator(
            target, plan, authorization_scope_digest, payload_dir
        )
        resume = plan_resume(
            plan, workspace=target, state=state,
            source_fingerprint=source_fingerprint, context=context,
            gate_validator=validator,
        )
        if resume["next_stage"] != STAGE_ID:
            raise ClaimAnalysisStageError("a análise não é a próxima etapa do manifesto")
        content = (json.dumps(analysis, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            updated = record_stage_acceptance(
                plan, workspace=target, state=state, stage_id=STAGE_ID,
                source_fingerprint=source_fingerprint, context=context,
                gate_validator=validator, attempt=attempt,
            )
            if state_output is not None:
                save_execution_state_once(state_output, updated)
            return updated
        except Exception:
            output.unlink(missing_ok=True)
            raise
    except (ResumeContractError, OSError, ValueError, TypeError) as error:
        if isinstance(error, ClaimAnalysisStageError):
            raise
        raise ClaimAnalysisStageError("a etapa de análise não foi aceita") from error
