#!/usr/bin/env python3
"""Despacha o fundamentador Codex com análise documental fictícia atual."""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from build_claim_decisions import render_judgment_draft
from codex_restricted_command import codex_restricted_command
from import_codex_documentary_rehearsal import _private_workspace
from resumable_pipeline import plan_resume
from run_codex_claim_analysis_rehearsal import (
    AGENT as ANALYSIS_AGENT, EXPECTED_FIXTURE_SHA256, MODEL_ID,
    _prompt as _analysis_prompt, _require_synthetic_pending_analysis,
)
from run_codex_claim_analysis_stage import (
    RECEIPT as ANALYSIS_RECEIPT, RECEIPT_SCHEMA as ANALYSIS_RECEIPT_SCHEMA,
    _current_inputs, _sha256, _verify_synthetic_custody,
)
from run_codex_draft_rehearsal import (
    AGENT, _prompt, _require_pending_disposition,
)
from run_draft_judgment_stage import _write_once, accept_draft_judgment_stage
from schema_validation import load_json, validate_schema_value
from trt12_pipeline_gates import make_trt12_gate_validator


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "draft-stage-receipt.json"
RECEIPT_SCHEMA = ROOT / "runtime/operations/draft-stage-receipt.v1.schema.json"


class CodexDraftStageError(ValueError):
    """Indica que a minuta atual não possui origem fictícia comprovada."""


def _read_analysis_receipt(source: Path) -> tuple[dict, bytes]:
    if {path.name for path in source.iterdir()} != {ANALYSIS_RECEIPT}:
        raise CodexDraftStageError("recibo anterior ausente ou espaço ocupado")
    path = source / ANALYSIS_RECEIPT
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise CodexDraftStageError("recibo anterior desprotegido")
    content = path.read_bytes()
    receipt = json.loads(content.decode("utf-8"))
    if validate_schema_value(
        receipt, load_json(ANALYSIS_RECEIPT_SCHEMA, "esquema do recibo de análise")
    ):
        raise CodexDraftStageError("recibo anterior inválido")
    return receipt, content


def run_codex_draft_stage(
    *, receipt_workspace: Path, analysis_receipt_workspace: Path,
    workspace: Path, plan: dict, state: dict,
    source_fingerprint: str, context: dict[str, str],
    authorization_scope_digest: str, payload_dir: Path,
    model_id: str, expected_analysis_model_id: str,
    expected_analysis_mode: str, synthetic_rehearsal: bool = False,
    text_generator: Optional[Callable[[str], str]] = None,
    attempt: int, state_output: Path | None = None,
) -> dict:
    """Confere custódia da análise, despacha e aceita o dispositivo pendente."""
    if synthetic_rehearsal is not True:
        raise CodexDraftStageError("despacho exige ensaio sintético explícito")
    if (
        not isinstance(model_id, str) or MODEL_ID.fullmatch(model_id) is None
        or not isinstance(expected_analysis_model_id, str)
        or MODEL_ID.fullmatch(expected_analysis_model_id) is None
        or expected_analysis_mode not in {"codex_cli", "simulated"}
    ):
        raise CodexDraftStageError("identidade do modelo ou modo anterior inválida")
    try:
        target = _private_workspace(workspace, "espaço do processo")
        source = _private_workspace(analysis_receipt_workspace, "espaço do recibo de análise")
        receipt_dir = _private_workspace(receipt_workspace, "espaço do recibo da minuta")
        if (
            len({target, source, receipt_dir}) != 3
            or any(receipt_dir.iterdir())
            or target.is_relative_to(source) or source.is_relative_to(target)
            or target.is_relative_to(receipt_dir) or receipt_dir.is_relative_to(target)
        ):
            raise CodexDraftStageError("espaços do processo e dos recibos devem ser separados")
        if not isinstance(plan, dict) or plan.get("runtime") != "codex":
            raise CodexDraftStageError("o despacho exige plano Codex")
        stages = plan.get("contract", {}).get("stages", [])
        draft_stage = next((item for item in stages if item.get("id") == "draft-judgment"), None)
        if (
            draft_stage is None or isinstance(attempt, bool)
            or not isinstance(attempt, int)
            or not 1 <= attempt <= draft_stage["max_attempts"]
        ):
            raise CodexDraftStageError("tentativa de minuta inválida")
        if any(
            (target / name).exists() or (target / name).is_symlink()
            for name in ("disposition-matrix.json", "judgment-draft.md")
        ):
            raise CodexDraftStageError("minuta existente não será sobrescrita")
        if state_output is not None and (
            not isinstance(state_output, Path) or state_output.is_symlink()
            or state_output.parent.resolve() != target or state_output.exists()
            or state_output.name in {"disposition-matrix.json", "judgment-draft.md"}
        ):
            raise CodexDraftStageError("destino do estado inválido ou ocupado")
        validator = make_trt12_gate_validator(
            target, plan, authorization_scope_digest, payload_dir
        )
        if plan_resume(
            plan, workspace=target, state=state,
            source_fingerprint=source_fingerprint, context=context,
            gate_validator=validator,
        )["next_stage"] != "draft-judgment":
            raise CodexDraftStageError("a minuta não é a próxima etapa")
        values, input_hashes = _current_inputs(target)
        pdf_digest, register_digest = _verify_synthetic_custody(target, payload_dir, values)
        analysis_path = target / "claim-analysis.json"
        if analysis_path.is_symlink() or not analysis_path.is_file():
            raise CodexDraftStageError("análise atual ausente")
        analysis_bytes = analysis_path.read_bytes()
        analysis = json.loads(analysis_bytes.decode("utf-8"))
        _require_synthetic_pending_analysis(analysis)
        analysis_receipt, analysis_receipt_bytes = _read_analysis_receipt(source)
        if (
            analysis_receipt["model_id"] != expected_analysis_model_id
            or analysis_receipt["execution_mode"] != expected_analysis_mode
            or analysis_receipt["agent_sha256"] != _sha256(ANALYSIS_AGENT.read_bytes())
            or analysis_receipt["fixture_sha256"] != EXPECTED_FIXTURE_SHA256
            or analysis_receipt["source_pdf_sha256"] != pdf_digest
            or analysis_receipt["source_register_sha256"] != register_digest
            or analysis_receipt["input_sha256"] != input_hashes
            or analysis_receipt["prompt_sha256"] != _sha256(
                _analysis_prompt(values, ANALYSIS_AGENT.read_text(encoding="utf-8")).encode(
                    "utf-8"
                )
            )
            or analysis_receipt["analysis_sha256"] != _sha256(analysis_bytes)
        ):
            raise CodexDraftStageError("análise atual diverge do recibo anterior")
        agent_bytes = AGENT.read_bytes()
        prompt = _prompt(values, analysis, agent_bytes.decode("utf-8"))
        if text_generator is None:
            with tempfile.TemporaryDirectory(prefix="trt12-minuta-atual-") as directory:
                result = subprocess.run(
                    codex_restricted_command(model_id), input=prompt,
                    text=True, capture_output=True, cwd=directory,
                    timeout=600, check=False,
                )
            if result.returncode != 0:
                raise CodexDraftStageError("o despacho do Codex falhou")
            response = result.stdout
        else:
            response = text_generator(prompt)
        dispositions = json.loads(response)
        _require_pending_disposition(dispositions)
        _, current_hashes = _current_inputs(target)
        if current_hashes != input_hashes or (
            _verify_synthetic_custody(target, payload_dir, values) != (pdf_digest, register_digest)
        ):
            raise CodexDraftStageError("insumos mudaram durante o despacho")
        if (
            analysis_path.read_bytes() != analysis_bytes
            or _read_analysis_receipt(source)[1] != analysis_receipt_bytes
            or AGENT.read_bytes() != agent_bytes
        ):
            raise CodexDraftStageError("análise, recibo ou instruções mudaram")
        disposition_bytes = (json.dumps(dispositions, ensure_ascii=False, indent=2) + "\n").encode()
        draft_bytes = render_judgment_draft(analysis, dispositions).encode("utf-8")
        receipt = {
            "schema_version": 1,
            "execution_mode": "codex_cli" if text_generator is None else "simulated",
            "model_id": model_id,
            "agent_sha256": _sha256(agent_bytes),
            "fixture_sha256": EXPECTED_FIXTURE_SHA256,
            "source_pdf_sha256": pdf_digest,
            "source_register_sha256": register_digest,
            "input_sha256": input_hashes,
            "analysis_sha256": _sha256(analysis_bytes),
            "analysis_receipt_sha256": _sha256(analysis_receipt_bytes),
            "prompt_sha256": _sha256(prompt.encode("utf-8")),
            "disposition_sha256": _sha256(disposition_bytes),
            "draft_sha256": _sha256(draft_bytes),
            "gate_status": "passed",
            "review_status": "pending_human_review",
            "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"
            ),
        }
        if validate_schema_value(receipt, load_json(RECEIPT_SCHEMA, "esquema da minuta")):
            raise CodexDraftStageError("recibo da minuta inválido")
        receipt_path = receipt_dir / RECEIPT
        _write_once(
            receipt_path, (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode()
        )
        try:
            return accept_draft_judgment_stage(
                workspace=target, plan=plan, state=state,
                source_fingerprint=source_fingerprint, context=context,
                authorization_scope_digest=authorization_scope_digest,
                payload_dir=payload_dir, dispositions=dispositions,
                attempt=attempt, state_output=state_output,
            )
        except Exception:
            receipt_path.unlink(missing_ok=True)
            raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError,
            subprocess.TimeoutExpired) as error:
        if isinstance(error, CodexDraftStageError):
            raise
        raise CodexDraftStageError("o despacho da minuta atual foi recusado") from error
