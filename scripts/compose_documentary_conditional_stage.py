#!/usr/bin/env python3
"""Compõe a etapa condicional a partir da ponte documental já validada."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from build_conditional_work_plan import build_conditional_work_plan, iter_dispatches
from build_documentary_work_records import build_documentary_work_records
from documentary_source_custody import (
    OBSERVATIONS_MARKER,
    REGISTER_NAME,
    make_source_record,
)
from schema_validation import load_json, validate_schema_value
from trt12_conditional_tracks_gate import (
    EVIDENCE_REVIEW_SCHEMA,
    OUTPUTS,
    make_conditional_tracks_gate,
)
from validate_conditional_work_results import validate_conditional_work_results


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_NAMES = (
    "evidence-review.json", "conditional-work-results.json", REGISTER_NAME,
)


class DocumentaryConditionalStageError(ValueError):
    """Indica que a etapa documental completa não pode ser publicada."""


def _read_input(workspace: Path, name: str) -> dict:
    path = workspace / name
    if path.is_symlink() or not path.is_file():
        raise DocumentaryConditionalStageError(f"insumo ausente ou vinculado: {name}")
    return load_json(path, name)


def _encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _publish(workspace: Path, review: dict, results: dict, register: dict) -> tuple[Path, ...]:
    created: list[Path] = []
    try:
        for name, value in zip(OUTPUT_NAMES, (review, results, register)):
            path = workspace / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "wb") as output:
                output.write(_encode(value))
        gate = make_conditional_tracks_gate(workspace)
        outputs = tuple(workspace / name for name in OUTPUTS)
        if not gate(
            {"id": "execute-conditional-tracks", "gate": "conditional-track-custody"},
            outputs,
        ):
            raise DocumentaryConditionalStageError("checkpoint condicional recusou os artefatos")
        return tuple(created)
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def publish_documentary_conditional_stage(
    workspace: Path,
    documentary_bundles: dict[str, dict],
    *,
    other_results: dict,
) -> tuple[Path, ...]:
    """Publica os registros probatórios sem converter observação em juízo jurídico."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise DocumentaryConditionalStageError("espaço de trabalho inválido")
    workspace = workspace.resolve()
    if workspace == ROOT or workspace.is_relative_to(ROOT):
        raise DocumentaryConditionalStageError("artefatos do caso não podem entrar no repositório")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise DocumentaryConditionalStageError("espaço de trabalho deve ser privado")
    if not isinstance(documentary_bundles, dict) or not isinstance(other_results, dict):
        raise DocumentaryConditionalStageError("insumos documentais inválidos")
    if any((workspace / name).exists() or (workspace / name).is_symlink() for name in OUTPUT_NAMES):
        raise DocumentaryConditionalStageError("artefato de saída já existe")

    try:
        routes = _read_input(workspace, "issue-route.json")
        evidence = _read_input(workspace, "evidence-matrix.json")
        corpus = _read_input(workspace, "precedent-corpus.json")
        index = _read_input(workspace, "document-index.json")
        plan = build_conditional_work_plan(routes)
        evidence_claims = {
            item.claim_id for item in iter_dispatches(plan)
            if item.track == "evidence_analysis"
        }
        if set(documentary_bundles) != evidence_claims:
            raise DocumentaryConditionalStageError("cobertura dos pedidos probatórios incompleta")
        if other_results.get("schema_version") != 1 or not isinstance(
            other_results.get("results"), list
        ):
            raise DocumentaryConditionalStageError("resultados das outras trilhas inválidos")
        if any(
            not isinstance(item, dict) or item.get("track") == "evidence_analysis"
            for item in other_results["results"]
        ):
            raise DocumentaryConditionalStageError("resultado probatório externo não permitido")

        reviews = []
        receipts = []
        source_records = []
        for claim_id in sorted({item["claim_id"] for item in routes["routes"]}):
            if claim_id not in evidence_claims:
                reviews.append({
                    "claim_id": claim_id, "status": "not_required",
                    "evidence_ids": [], "assessment": "", "limitations": [],
                })
                continue
            bundle = documentary_bundles[claim_id]
            review, receipt = build_documentary_work_records(
                plan, bundle["observations"],
                packet=bundle["packet"], pdf_path=bundle["pdf_path"],
                segments=bundle["segments"], evidence_matrix=evidence,
                claim_id=claim_id, evidence_ids=bundle["evidence_ids"],
            )
            source_record = make_source_record(workspace, claim_id, bundle)
            review["limitations"].append(
                OBSERVATIONS_MARKER + source_record["observations_sha256"]
            )
            source_records.append(source_record)
            reviews.append(review)
            receipts.append(receipt)
        review_artifact = {"schema_version": 1, "reviews": reviews}
        result_artifact = {
            "schema_version": 1,
            "results": [*other_results["results"], *receipts],
        }
        if validate_schema_value(
            review_artifact, load_json(EVIDENCE_REVIEW_SCHEMA, "revisão probatória")
        ):
            raise DocumentaryConditionalStageError("revisão probatória inválida")
        validate_conditional_work_results(
            plan, result_artifact,
            evidence_matrix=evidence, precedent_corpus=corpus,
            known_document_ids=tuple(item["document_id"] for item in index["documents"]),
        )
        source_register = {"schema_version": 1, "records": source_records}
        return _publish(workspace, review_artifact, result_artifact, source_register)
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as error:
        if isinstance(error, DocumentaryConditionalStageError):
            raise
        raise DocumentaryConditionalStageError("composição documental recusada") from error
