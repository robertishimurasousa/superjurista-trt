#!/usr/bin/env python3
"""Funde a minuta aceita no arquivo do processo e registra o checkpoint."""

from __future__ import annotations

import re
import stat
from pathlib import Path

from resumable_pipeline import (
    ResumeContractError, plan_resume, record_stage_acceptance,
    save_execution_state_once,
)
from run_draft_judgment_stage import _write_once
from schema_validation import load_json
from trt12_pipeline_gates import make_trt12_gate_validator


ROOT = Path(__file__).resolve().parents[1]
STAGE_ID = "merge-judgment"
CASE_NUMBER = re.compile(r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}")


class MergeJudgmentStageError(ValueError):
    """Indica que a fusão não pode ser publicada ou aceita."""


def accept_merge_judgment_stage(
    *, workspace: Path, plan: dict, state: dict,
    source_fingerprint: str, context: dict[str, str],
    authorization_scope_digest: str, payload_dir: Path,
    attempt: int, state_output: Path | None = None,
) -> dict:
    """Copia exatamente os bytes da minuta aceita, sem sobrescrever arquivos."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise MergeJudgmentStageError("espaço do processo inválido")
    target = workspace.resolve()
    if target == ROOT or target.is_relative_to(ROOT):
        raise MergeJudgmentStageError("o processo não pode ser executado no repositório")
    if stat.S_IMODE(target.stat().st_mode) & 0o077:
        raise MergeJudgmentStageError("espaço do processo deve ser privado")
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
            raise MergeJudgmentStageError("a fusão não é a próxima etapa do manifesto")
        context_path = target / "case-context.json"
        if context_path.is_symlink() or not context_path.is_file():
            raise MergeJudgmentStageError("contexto do processo ausente")
        case_number = load_json(context_path, "contexto do processo")["case_number"]
        if (
            not isinstance(case_number, str)
            or CASE_NUMBER.fullmatch(case_number) is None
            or not isinstance(context, dict)
            or context.get("case_number") != case_number
        ):
            raise MergeJudgmentStageError("número do processo divergente ou inválido")
        output = target / f"{case_number}-labor-judgment.md"
        draft = target / "judgment-draft.md"
        if output.exists() or output.is_symlink():
            raise MergeJudgmentStageError("sentença já existente não será sobrescrita")
        if draft.is_symlink() or not draft.is_file():
            raise MergeJudgmentStageError("minuta aceita ausente ou inválida")
        if state_output is not None and (
            not isinstance(state_output, Path)
            or state_output.is_symlink()
            or state_output.parent.resolve() != target
            or state_output.exists()
            or state_output == output
        ):
            raise MergeJudgmentStageError("destino do estado inválido ou ocupado")
        _write_once(output, draft.read_bytes())
        try:
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
    except (ResumeContractError, OSError, ValueError, TypeError, KeyError) as error:
        if isinstance(error, MergeJudgmentStageError):
            raise
        raise MergeJudgmentStageError("a etapa de fusão não foi aceita") from error
