#!/usr/bin/env python3
"""Validate routed-work custody without certifying legal conclusions."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from build_conditional_work_plan import build_conditional_work_plan, iter_dispatches
from documentary_source_custody import validate_source_register
from schema_validation import ContractError, load_json, validate_schema_value
from validate_artifact_contracts import load_catalog, validate_document
from validate_conditional_work_results import validate_conditional_work_results
from verify_pje_acquisition_custody import INDEX_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "runtime/contracts/catalog.json"
EVIDENCE_REVIEW_SCHEMA = ROOT / "runtime/pipelines/evidence-review.v1.schema.json"
CALCULATION_REVIEW_SCHEMA = ROOT / "runtime/pipelines/calculation-review.v1.schema.json"
OUTPUTS = (
    "precedent-corpus.json", "evidence-review.json",
    "calculation-review.json", "conditional-work-results.json",
)


def _exact_claim_records(items: list[dict], claim_ids: set[str]) -> dict[str, dict] | None:
    records = {item["claim_id"]: item for item in items}
    if len(records) != len(items) or set(records) != claim_ids:
        return None
    return records


def _review_states_match_routes(
    routes: dict,
    evidence: dict,
    evidence_review: dict,
    calculation_review: dict,
    work_results: dict,
) -> bool:
    route_by_claim = {item["claim_id"]: item for item in routes["routes"]}
    claim_ids = set(route_by_claim)
    reviews = _exact_claim_records(evidence_review["reviews"], claim_ids)
    calculations = _exact_claim_records(calculation_review["calculations"], claim_ids)
    if reviews is None or calculations is None:
        return False
    results = {item["work_id"]: item for item in work_results["results"]}
    evidence_by_id = {item["evidence_id"]: item for item in evidence["evidence_items"]}
    for claim_id, route in route_by_claim.items():
        review = reviews[claim_id]
        calculation = calculations[claim_id]
        if route["requires_evidence_analysis"]:
            receipt = results[f"WRK-{claim_id}-EVIDENCE"]
            if review["status"] == "not_required":
                return False
            if set(review["evidence_ids"]) != set(receipt["source_ids"]):
                return False
            if any(
                evidence_id not in evidence_by_id
                or claim_id not in evidence_by_id[evidence_id]["claim_ids"]
                for evidence_id in review["evidence_ids"]
            ):
                return False
            if review["status"] == "reviewed":
                if (
                    receipt["custody_status"] != "linked"
                    or not review["evidence_ids"]
                    or not review["assessment"].strip()
                ):
                    return False
            elif not review["limitations"]:
                return False
        elif (
            review["status"] != "not_required"
            or review["evidence_ids"] or review["assessment"] or review["limitations"]
        ):
            return False
        if route["requires_calculation_review"]:
            if calculation["status"] == "not_required":
                return False
            if calculation["status"] == "criteria_reviewed":
                receipt = results[f"WRK-{claim_id}-CALCULATION"]
                if (
                    receipt["custody_status"] != "linked"
                    or not calculation["criteria"]
                    or calculation["unavailability_reason"]
                ):
                    return False
            elif not calculation["unavailability_reason"].strip():
                return False
        elif (
            calculation["status"] != "not_required"
            or calculation["criteria"] or calculation["unavailability_reason"]
        ):
            return False
    return True


def make_conditional_tracks_gate(workspace: Path) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Return a fail-closed content gate for dispatched work and review state."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()

    def read_json(name: str, label: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("insumo ausente ou vínculo simbólico")
        return load_json(path, label)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if (
            stage.get("id") != "execute-conditional-tracks"
            or stage.get("gate") != "conditional-track-custody"
        ):
            return False
        if outputs != tuple((root / name).resolve() for name in OUTPUTS):
            return False
        try:
            context = read_json("case-context.json", "contexto do processo")
            index = read_json("document-index.json", "índice PJe")
            if validate_schema_value(index, load_json(INDEX_SCHEMA, "esquema do índice PJe")):
                return False
            if index["status"] != "complete" or index["gaps"]:
                return False
            if any(index["case"][key] != context[context_key] for key, context_key in (
                ("case_number", "case_number"),
                ("tribunal_code", "court"),
                ("instance", "instance"),
                ("court_unit", "court_unit"),
            )):
                return False
            document_ids = tuple(item["document_id"] for item in index["documents"])
            _, contracts = load_catalog(CATALOG)
            artifacts = {}
            for name, contract_id in (
                ("claim-matrix.json", "claim-matrix"),
                ("issue-route.json", "issue-route"),
                ("evidence-matrix.json", "evidence-matrix"),
                ("precedent-corpus.json", "precedent-corpus"),
            ):
                value = read_json(name, contract_id)
                if validate_document(value, contracts[contract_id][0]):
                    return False
                artifacts[name] = value
            claims = artifacts["claim-matrix.json"]["claims"]
            routes = artifacts["issue-route.json"]
            claim_ids = [item["claim_id"] for item in claims]
            route_ids = [item["claim_id"] for item in routes["routes"]]
            if (
                len(claim_ids) != len(set(claim_ids))
                or len(route_ids) != len(set(route_ids))
                or set(claim_ids) != set(route_ids)
            ):
                return False
            work_plan = build_conditional_work_plan(routes)
            dispatches = iter_dispatches(work_plan)
            corpus = artifacts["precedent-corpus.json"]
            if not any(item.track == "legal_research" for item in dispatches) and corpus["sources"]:
                return False
            results = read_json("conditional-work-results.json", "resultados condicionais")
            evidence = artifacts["evidence-matrix.json"]
            validate_conditional_work_results(
                work_plan, results,
                evidence_matrix=evidence,
                precedent_corpus=corpus,
                known_document_ids=document_ids,
            )
            evidence_review = read_json("evidence-review.json", "revisão probatória")
            calculation_review = read_json("calculation-review.json", "revisão de cálculos")
            if (
                validate_schema_value(evidence_review, load_json(
                    EVIDENCE_REVIEW_SCHEMA, "esquema da revisão probatória"
                ))
                or validate_schema_value(calculation_review, load_json(
                    CALCULATION_REVIEW_SCHEMA, "esquema da revisão de cálculos"
                ))
            ):
                return False
            validate_source_register(root, evidence, evidence_review)
            return _review_states_match_routes(
                routes, evidence, evidence_review, calculation_review, results
            )
        except (ContractError, ValueError, OSError, UnicodeError, KeyError, TypeError):
            return False

    return validate
