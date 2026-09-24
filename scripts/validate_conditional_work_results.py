#!/usr/bin/env python3
"""Check source custody for work dispatched by inherited claim triage."""

from __future__ import annotations

from pathlib import Path

from build_conditional_work_plan import ConditionalWorkPlanError, iter_dispatches
from schema_validation import ContractError, load_json, validate_schema_value
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
RESULTS_SCHEMA = ROOT / "runtime/pipelines/conditional-work-results.v1.schema.json"
EVIDENCE_SCHEMA = ROOT / "runtime/contracts/schemas/evidence-matrix.v1.schema.json"
PRECEDENT_SCHEMA = ROOT / "runtime/contracts/schemas/precedent-corpus.v1.schema.json"


class ConditionalWorkResultsError(ValueError):
    """Raised when a routed work item lacks trustworthy source custody."""


def _require_contract(value: dict, schema_path: Path, label: str) -> None:
    issues = validate_document(value, load_json(schema_path, f"esquema {label}"))
    if issues:
        raise ConditionalWorkResultsError(f"{label} inválido: {issues[0]}")


def validate_conditional_work_results(
    work_plan: dict,
    results: dict,
    *,
    evidence_matrix: dict,
    precedent_corpus: dict,
    known_document_ids: tuple[str, ...],
) -> None:
    """Require one source-linked result or explicit gap per enabled work item."""
    try:
        dispatches = iter_dispatches(work_plan)
        _require_contract(results, RESULTS_SCHEMA, "resultado condicional")
        _require_contract(evidence_matrix, EVIDENCE_SCHEMA, "matriz de provas")
        _require_contract(precedent_corpus, PRECEDENT_SCHEMA, "corpus de precedentes")
    except (ConditionalWorkPlanError, ContractError) as error:
        raise ConditionalWorkResultsError(str(error)) from error
    if not isinstance(known_document_ids, tuple) or (
        len(set(known_document_ids)) != len(known_document_ids)
        or any(not isinstance(item, str) or not item for item in known_document_ids)
    ):
        raise ConditionalWorkResultsError("documentos conhecidos inválidos")
    expected = {item.work_id: item for item in dispatches}
    if len(expected) != len(dispatches):
        raise ConditionalWorkResultsError("despachos duplicados")
    received = {}
    for result in results["results"]:
        work_id = result["work_id"]
        if work_id in received:
            raise ConditionalWorkResultsError(f"resultado duplicado: {work_id}")
        received[work_id] = result
    if set(received) != set(expected):
        raise ConditionalWorkResultsError("cobertura dos trabalhos encaminhados diverge")
    evidence_items = evidence_matrix["evidence_items"]
    evidence = {item["evidence_id"]: item for item in evidence_items}
    precedents = {item["source_id"] for item in precedent_corpus["sources"]}
    if len(evidence) != len(evidence_items) or len(precedents) != len(precedent_corpus["sources"]):
        raise ConditionalWorkResultsError("fontes duplicadas nos artefatos")
    documents = set(known_document_ids)
    for work_id, result in received.items():
        dispatch = expected[work_id]
        if result["claim_id"] != dispatch.claim_id or result["track"] != dispatch.track:
            raise ConditionalWorkResultsError(f"resultado {work_id} diverge do despacho")
        source_ids = result["source_ids"]
        if result["custody_status"] == "linked" and not source_ids:
            raise ConditionalWorkResultsError(f"fonte ausente em {work_id}")
        if result["custody_status"] == "gap" and not result["limitations"]:
            raise ConditionalWorkResultsError(f"lacuna sem motivo em {work_id}")
        if dispatch.track == "legal_research":
            if not set(source_ids) <= precedents:
                raise ConditionalWorkResultsError(f"fonte jurídica desconhecida em {work_id}")
        elif dispatch.track == "evidence_analysis":
            for source_id in source_ids:
                item = evidence.get(source_id)
                if item is None:
                    raise ConditionalWorkResultsError(f"fonte probatória desconhecida em {work_id}")
                if dispatch.claim_id not in item["claim_ids"]:
                    raise ConditionalWorkResultsError(f"fonte probatória fora do pedido em {work_id}")
        elif not set(source_ids) <= documents:
            raise ConditionalWorkResultsError(f"fonte documental desconhecida em {work_id}")
