#!/usr/bin/env python3
"""Despacha ensaio documental fictício e registra a etapa compartilhada."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from build_conditional_work_plan import build_conditional_work_plan, iter_dispatches
from import_codex_documentary_rehearsal import (
    DocumentaryRehearsalImportError,
    _private_workspace,
    import_codex_documentary_rehearsal,
)
from resumable_pipeline import plan_resume
from run_codex_documentary_rehearsal import (
    CLAIM_ID,
    MODEL_ID,
    CodexDocumentaryRehearsalError,
    _synthetic_evidence,
    run_codex_documentary_rehearsal,
)
from schema_validation import load_json
from trt12_pipeline_gates import make_trt12_gate_validator


class CodexDocumentaryStageError(ValueError):
    """Indica que o despacho documental sintético não pode ocorrer."""


def run_codex_documentary_stage(
    *, rehearsal_workspace: Path, workspace: Path, plan: dict, state: dict,
    source_fingerprint: str, context: dict[str, str],
    authorization_scope_digest: str, payload_dir: Path, other_results: dict,
    model_id: str, synthetic_rehearsal: bool = False,
    text_generator: Optional[Callable[[str], str]] = None,
    attempt: int, state_output: Path | None = None,
) -> dict:
    """Executa o Codex só com fonte fictícia após todos os controles anteriores."""
    if synthetic_rehearsal is not True:
        raise CodexDocumentaryStageError("despacho exige ensaio sintético explícito")
    if not isinstance(model_id, str) or MODEL_ID.fullmatch(model_id) is None:
        raise CodexDocumentaryStageError("modelo Codex ausente ou inválido")
    try:
        target = _private_workspace(workspace, "espaço do processo")
        source = _private_workspace(rehearsal_workspace, "espaço do ensaio")
        if source == target or any(source.iterdir()):
            raise CodexDocumentaryStageError("espaço do ensaio deve estar vazio e separado")
        if any(
            (target / name).exists() or (target / name).is_symlink()
            for name in (
                "synthetic-source.pdf", "evidence-review.json",
                "conditional-work-results.json", "documentary-source-register.json",
            )
        ):
            raise CodexDocumentaryStageError("saída documental já existe")
        if state_output is not None and (
            not isinstance(state_output, Path)
            or state_output.is_symlink()
            or state_output.parent.resolve() != target
            or state_output.exists()
        ):
            raise CodexDocumentaryStageError("destino do estado inválido ou ocupado")
        validator = make_trt12_gate_validator(
            target, plan, authorization_scope_digest, payload_dir
        )
        if plan_resume(
            plan, workspace=target, state=state,
            source_fingerprint=source_fingerprint, context=context,
            gate_validator=validator,
        )["next_stage"] != "execute-conditional-tracks":
            raise CodexDocumentaryStageError("a etapa documental não é a próxima")
        if load_json(target / "evidence-matrix.json", "matriz probatória") != _synthetic_evidence():
            raise CodexDocumentaryStageError("matriz probatória não é a amostra fictícia")
        routes = load_json(target / "issue-route.json", "rotas do processo")
        evidence_claims = {
            item.claim_id for item in iter_dispatches(build_conditional_work_plan(routes))
            if item.track == "evidence_analysis"
        }
        if evidence_claims != {CLAIM_ID}:
            raise CodexDocumentaryStageError("encaminhamentos probatórios incompatíveis")

        run_codex_documentary_rehearsal(
            source, synthetic_rehearsal=True,
            text_generator=text_generator, model_id=model_id,
        )
        return import_codex_documentary_rehearsal(
            rehearsal_workspace=source, workspace=target,
            plan=plan, state=state, source_fingerprint=source_fingerprint,
            context=context, authorization_scope_digest=authorization_scope_digest,
            payload_dir=payload_dir, other_results=other_results,
            expected_model_id=model_id, attempt=attempt, state_output=state_output,
        )
    except (DocumentaryRehearsalImportError, CodexDocumentaryRehearsalError,
            OSError, ValueError, TypeError) as error:
        if isinstance(error, CodexDocumentaryStageError):
            raise
        raise CodexDocumentaryStageError("despacho documental interrompido") from error
