#!/usr/bin/env python3
"""Publica dispositivo e minuta determinística no checkpoint do TRT12."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from build_claim_decisions import render_judgment_draft
from resumable_pipeline import (
    ResumeContractError, plan_resume, record_stage_acceptance,
    save_execution_state_once,
)
from schema_validation import load_json
from trt12_pipeline_gates import make_trt12_gate_validator


ROOT = Path(__file__).resolve().parents[1]
STAGE_ID = "draft-judgment"
OUTPUTS = ("disposition-matrix.json", "judgment-draft.md")


class DraftJudgmentStageError(ValueError):
    """Indica que o dispositivo e a minuta não podem ser aceitos."""


def _write_once(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def accept_draft_judgment_stage(
    *, workspace: Path, plan: dict, state: dict,
    source_fingerprint: str, context: dict[str, str],
    authorization_scope_digest: str, payload_dir: Path,
    dispositions: dict, attempt: int, state_output: Path | None = None,
) -> dict:
    """Exige a etapa correta, renderiza e registra o controle sem sobrescrever."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise DraftJudgmentStageError("espaço do processo inválido")
    target = workspace.resolve()
    if target == ROOT or target.is_relative_to(ROOT):
        raise DraftJudgmentStageError("o processo não pode ser executado no repositório")
    if stat.S_IMODE(target.stat().st_mode) & 0o077:
        raise DraftJudgmentStageError("espaço do processo deve ser privado")
    outputs = tuple(target / name for name in OUTPUTS)
    if any(path.exists() or path.is_symlink() for path in outputs):
        raise DraftJudgmentStageError("saída já existente não será sobrescrita")
    if state_output is not None and (
        not isinstance(state_output, Path)
        or state_output.is_symlink()
        or state_output.parent.resolve() != target
        or state_output.exists()
        or state_output in outputs
    ):
        raise DraftJudgmentStageError("destino do estado inválido ou ocupado")

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
            raise DraftJudgmentStageError("a minuta não é a próxima etapa do manifesto")
        analysis_path = target / "claim-analysis.json"
        if analysis_path.is_symlink() or not analysis_path.is_file():
            raise DraftJudgmentStageError("análise aceita ausente ou inválida")
        analysis = load_json(analysis_path, "análise aceita")
        draft = render_judgment_draft(analysis, dispositions)
        contents = (
            (json.dumps(dispositions, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            draft.encode("utf-8"),
        )
        created = []
        try:
            for path, content in zip(outputs, contents):
                _write_once(path, content)
                created.append(path)
            updated = record_stage_acceptance(
                plan, workspace=target, state=state, stage_id=STAGE_ID,
                source_fingerprint=source_fingerprint, context=context,
                gate_validator=validator, attempt=attempt,
            )
            if state_output is not None:
                save_execution_state_once(state_output, updated)
            return updated
        except Exception:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            raise
    except (ResumeContractError, OSError, ValueError, TypeError, KeyError) as error:
        if isinstance(error, DraftJudgmentStageError):
            raise
        raise DraftJudgmentStageError("a etapa de minuta não foi aceita") from error
