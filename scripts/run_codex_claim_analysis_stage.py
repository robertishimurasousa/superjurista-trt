#!/usr/bin/env python3
"""Despacha análise Codex com insumos documentais sintéticos atuais."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from build_conditional_work_plan import build_conditional_work_plan
from build_documentary_work_records import build_documentary_work_records
from codex_restricted_command import codex_restricted_command
from documentary_source_custody import OBSERVATIONS_MARKER, REGISTER_NAME
from import_codex_documentary_rehearsal import _private_workspace
from prepare_source_evidence_packet import build_source_evidence_packet
from resumable_pipeline import plan_resume
from run_claim_analysis_stage import accept_claim_analysis_stage
from run_codex_claim_analysis_rehearsal import (
    AGENT, EXPECTED_FIXTURE_SHA256, FIXTURE, INPUTS, MODEL_ID,
    _prompt, _require_synthetic_pending_analysis, _synthetic_document_index,
)
from run_codex_documentary_rehearsal import _synthetic_evidence, _synthetic_pdf
from run_draft_judgment_stage import _write_once
from schema_validation import load_json, validate_schema_value
from trt12_pipeline_gates import make_trt12_gate_validator


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "claim-analysis-stage-receipt.json"
RECEIPT_SCHEMA = ROOT / "runtime/operations/claim-analysis-stage-receipt.v1.schema.json"
FIXED_INPUTS = (
    "case-context.json", "claim-matrix.json", "issue-route.json",
    "precedent-corpus.json", "calculation-review.json",
)


class CodexClaimAnalysisStageError(ValueError):
    """Indica que o despacho atual não comprova origem fictícia ou custódia."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _current_inputs(target: Path) -> tuple[dict, dict[str, str]]:
    values = {}
    hashes = {}
    for name in ("case-context.json", *INPUTS):
        path = target / name
        if path.is_symlink() or not path.is_file():
            raise CodexClaimAnalysisStageError(f"insumo ausente ou vinculado: {name}")
        content = path.read_bytes()
        values[name] = json.loads(content.decode("utf-8"))
        hashes[name] = _sha256(content)
    return values, hashes


def _verify_synthetic_custody(target: Path, payload_dir: Path, values: dict) -> tuple[str, str]:
    fixture_bytes = FIXTURE.read_bytes()
    if _sha256(fixture_bytes) != EXPECTED_FIXTURE_SHA256:
        raise CodexClaimAnalysisStageError("amostra fictícia versionada alterada")
    fixture = load_json(FIXTURE, "amostra sintética TRT12")
    if fixture.get("fixture_id") != "synthetic-trt12-first-instance-v1":
        raise CodexClaimAnalysisStageError("identidade da amostra fictícia divergente")
    reference = fixture["artifacts"]
    if any(values[name] != reference[name] for name in FIXED_INPUTS):
        raise CodexClaimAnalysisStageError("insumo fixo difere da amostra fictícia")
    if values["evidence-matrix.json"] != _synthetic_evidence():
        raise CodexClaimAnalysisStageError("matriz de provas não é a amostra fictícia")
    index_path = target / "document-index.json"
    if index_path.is_symlink() or load_json(index_path, "índice sintético") != (
        _synthetic_document_index(reference["case-context.json"])
    ):
        raise CodexClaimAnalysisStageError("índice do processo não é fictício")
    if (
        not isinstance(payload_dir, Path) or payload_dir.is_symlink()
        or payload_dir.resolve() != (target / "pje-payloads").resolve()
        or not payload_dir.is_dir()
        or {item.name for item in payload_dir.iterdir()} != {"DOC-001.bin", "DOC-002.bin"}
    ):
        raise CodexClaimAnalysisStageError("cargas do processo não são fictícias")
    for document_id in ("DOC-001", "DOC-002"):
        path = payload_dir / f"{document_id}.bin"
        if path.is_symlink() or path.read_bytes() != f"conteudo sintetico {document_id}".encode():
            raise CodexClaimAnalysisStageError("carga do processo divergente")
    pdf = target / "synthetic-source.pdf"
    pdf_bytes = _synthetic_pdf()
    if pdf.is_symlink() or not pdf.is_file() or pdf.read_bytes() != pdf_bytes:
        raise CodexClaimAnalysisStageError("PDF documental não é a fonte fictícia")
    register_path = target / REGISTER_NAME
    if register_path.is_symlink() or not register_path.is_file():
        raise CodexClaimAnalysisStageError("registro documental ausente")
    register_bytes = register_path.read_bytes()
    register = json.loads(register_bytes.decode("utf-8"))
    records = register.get("records") if isinstance(register, dict) else None
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise CodexClaimAnalysisStageError("registro documental fictício inválido")
    record = records[0]
    if record.get("claim_id") != "CLM-001" or record.get("source_pdf_name") != pdf.name:
        raise CodexClaimAnalysisStageError("registro documental não aponta à fonte fictícia")
    packet = build_source_evidence_packet(
        pdf, record["segments"], values["evidence-matrix.json"],
        claim_id="CLM-001", evidence_ids=("EVD-001",),
    )
    work_plan = build_conditional_work_plan(values["issue-route.json"])
    review, evidence_receipt = build_documentary_work_records(
        work_plan, record["observations"], packet=packet, pdf_path=pdf,
        segments=record["segments"], evidence_matrix=values["evidence-matrix.json"],
        claim_id="CLM-001", evidence_ids=("EVD-001",),
    )
    review["limitations"].append(OBSERVATIONS_MARKER + record["observations_sha256"])
    if values["evidence-review.json"] != {"schema_version": 1, "reviews": [review]}:
        raise CodexClaimAnalysisStageError("revisão documental não deriva da fonte fictícia")
    fixed_other_results = [
        item for item in reference["conditional-work-results.json"]["results"]
        if item["track"] != "evidence_analysis"
    ]
    expected_results = {"schema_version": 1, "results": [*fixed_other_results, evidence_receipt]}
    if values["conditional-work-results.json"] != expected_results:
        raise CodexClaimAnalysisStageError("recibos condicionais não derivam da fonte fictícia")
    return _sha256(pdf_bytes), _sha256(register_bytes)


def run_codex_claim_analysis_stage(
    *, receipt_workspace: Path, workspace: Path, plan: dict, state: dict,
    source_fingerprint: str, context: dict[str, str],
    authorization_scope_digest: str, payload_dir: Path,
    model_id: str, synthetic_rehearsal: bool = False,
    text_generator: Optional[Callable[[str], str]] = None,
    attempt: int, state_output: Path | None = None,
) -> dict:
    """Envia somente artefatos fictícios atuais e aceita a análise pendente."""
    if synthetic_rehearsal is not True:
        raise CodexClaimAnalysisStageError("despacho exige ensaio sintético explícito")
    if not isinstance(model_id, str) or MODEL_ID.fullmatch(model_id) is None:
        raise CodexClaimAnalysisStageError("modelo Codex ausente ou inválido")
    try:
        target = _private_workspace(workspace, "espaço do processo")
        receipt_dir = _private_workspace(receipt_workspace, "espaço do recibo")
        if target == receipt_dir or any(receipt_dir.iterdir()):
            raise CodexClaimAnalysisStageError("espaço do recibo deve estar vazio e separado")
        if not isinstance(plan, dict) or plan.get("runtime") != "codex":
            raise CodexClaimAnalysisStageError("o despacho exige plano Codex")
        contract = plan.get("contract")
        stages = contract.get("stages") if isinstance(contract, dict) else None
        analysis_stage = next(
            (item for item in stages if isinstance(item, dict) and item.get("id") == "analyze-claims"),
            None,
        ) if isinstance(stages, list) else None
        if (
            analysis_stage is None or isinstance(attempt, bool)
            or not isinstance(attempt, int)
            or not isinstance(analysis_stage.get("max_attempts"), int)
            or not 1 <= attempt <= analysis_stage["max_attempts"]
        ):
            raise CodexClaimAnalysisStageError("tentativa de análise inválida")
        if (target / "claim-analysis.json").exists() or (target / "claim-analysis.json").is_symlink():
            raise CodexClaimAnalysisStageError("análise já existente não será sobrescrita")
        if state_output is not None and (
            not isinstance(state_output, Path)
            or state_output.is_symlink()
            or state_output.parent.resolve() != target
            or state_output.exists()
        ):
            raise CodexClaimAnalysisStageError("destino do estado inválido ou ocupado")
        validator = make_trt12_gate_validator(
            target, plan, authorization_scope_digest, payload_dir
        )
        if plan_resume(
            plan, workspace=target, state=state,
            source_fingerprint=source_fingerprint, context=context,
            gate_validator=validator,
        )["next_stage"] != "analyze-claims":
            raise CodexClaimAnalysisStageError("a análise não é a próxima etapa")
        values, input_hashes = _current_inputs(target)
        pdf_digest, register_digest = _verify_synthetic_custody(target, payload_dir, values)
        agent_bytes = AGENT.read_bytes()
        prompt = _prompt(values, agent_bytes.decode("utf-8"))
        if text_generator is None:
            with tempfile.TemporaryDirectory(prefix="trt12-analise-atual-") as directory:
                result = subprocess.run(
                    codex_restricted_command(model_id), input=prompt,
                    text=True, capture_output=True, cwd=directory,
                    timeout=600, check=False,
                )
            if result.returncode != 0:
                raise CodexClaimAnalysisStageError("o despacho do Codex falhou")
            response = result.stdout
        else:
            response = text_generator(prompt)
        analysis = json.loads(response)
        items = analysis.get("analyses") if isinstance(analysis, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise CodexClaimAnalysisStageError("resposta de análise inválida")
        _require_synthetic_pending_analysis(analysis)
        _, current_hashes = _current_inputs(target)
        if current_hashes != input_hashes:
            raise CodexClaimAnalysisStageError("insumos mudaram durante o despacho")
        if _verify_synthetic_custody(target, payload_dir, values) != (pdf_digest, register_digest):
            raise CodexClaimAnalysisStageError("origem fictícia mudou durante o despacho")
        analysis_bytes = (json.dumps(analysis, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        receipt = {
            "schema_version": 1,
            "execution_mode": "codex_cli" if text_generator is None else "simulated",
            "model_id": model_id,
            "agent_sha256": _sha256(agent_bytes),
            "fixture_sha256": EXPECTED_FIXTURE_SHA256,
            "source_pdf_sha256": pdf_digest,
            "source_register_sha256": register_digest,
            "input_sha256": input_hashes,
            "prompt_sha256": _sha256(prompt.encode("utf-8")),
            "analysis_sha256": _sha256(analysis_bytes),
            "gate_status": "passed",
            "review_status": "pending_human_review",
            "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"
            ),
        }
        if validate_schema_value(
            receipt, load_json(RECEIPT_SCHEMA, "esquema do recibo de análise")
        ):
            raise CodexClaimAnalysisStageError("recibo de análise inválido")
        receipt_path = receipt_dir / RECEIPT
        _write_once(
            receipt_path, (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        try:
            return accept_claim_analysis_stage(
                workspace=target, plan=plan, state=state,
                source_fingerprint=source_fingerprint, context=context,
                authorization_scope_digest=authorization_scope_digest,
                payload_dir=payload_dir, analysis=analysis, attempt=attempt,
                state_output=state_output,
            )
        except Exception:
            receipt_path.unlink(missing_ok=True)
            raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            subprocess.TimeoutExpired) as error:
        if isinstance(error, CodexClaimAnalysisStageError):
            raise
        raise CodexClaimAnalysisStageError("o despacho da análise atual foi recusado") from error
