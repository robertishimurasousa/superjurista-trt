#!/usr/bin/env python3
"""Controlar cobertura e custódia da análise sem certificar o mérito jurídico."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from build_claim_decisions import MERITS_OUTCOMES, PROCEDURAL_OUTCOMES
from schema_validation import ContractError, load_json
from trt12_conditional_tracks_gate import make_conditional_tracks_gate
from validate_artifact_contracts import load_catalog, validate_document


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "runtime/contracts/catalog.json"
PRIOR_OUTPUTS = (
    "precedent-corpus.json", "evidence-review.json",
    "calculation-review.json", "conditional-work-results.json",
)


def make_claim_analysis_gate(workspace: Path) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Exigir um resultado por pedido e bloquear conclusões sem revisão de origem."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()
    prior_gate = make_conditional_tracks_gate(root)

    def read_json(name: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("insumo ausente ou vínculo simbólico")
        return load_json(path, name)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if stage.get("id") != "analyze-claims" or stage.get("gate") != "claim-analysis-coverage":
            return False
        if outputs != ((root / "claim-analysis.json").resolve(),):
            return False
        if not prior_gate(
            {"id": "execute-conditional-tracks", "gate": "conditional-track-custody"},
            tuple((root / name).resolve() for name in PRIOR_OUTPUTS),
        ):
            return False
        try:
            _, contracts = load_catalog(CATALOG)
            artifacts = {}
            for name, contract_id in (
                ("claim-matrix.json", "claim-matrix"),
                ("issue-route.json", "issue-route"),
                ("evidence-matrix.json", "evidence-matrix"),
                ("precedent-corpus.json", "precedent-corpus"),
                ("claim-analysis.json", "claim-analysis"),
            ):
                value = read_json(name)
                if validate_document(value, contracts[contract_id][0]):
                    return False
                artifacts[name] = value
            claims = artifacts["claim-matrix.json"]["claims"]
            analyses = artifacts["claim-analysis.json"]["analyses"]
            claim_ids = {item["claim_id"] for item in claims}
            if len(claim_ids) != len(claims) or {item["claim_id"] for item in analyses} != claim_ids:
                return False
            routes = {
                item["claim_id"]: item for item in artifacts["issue-route.json"]["routes"]
            }
            reviews = {item["claim_id"]: item for item in read_json("evidence-review.json")["reviews"]}
            calculations = {
                item["claim_id"]: item for item in read_json("calculation-review.json")["calculations"]
            }
            receipts = {
                item["work_id"]: item for item in read_json("conditional-work-results.json")["results"]
            }
            evidence = {
                item["evidence_id"]: item
                for item in artifacts["evidence-matrix.json"]["evidence_items"]
            }
            precedents = {
                item["source_id"] for item in artifacts["precedent-corpus.json"]["sources"]
            }
            claim_by_id = {item["claim_id"]: item for item in claims}
            for analysis in analyses:
                claim_id = analysis["claim_id"]
                claim = claim_by_id[claim_id]
                route = routes[claim_id]
                review = reviews[claim_id]
                calculation = calculations[claim_id]
                outcome = analysis["proposed_outcome"]
                if route["route_status"] == "abstained" and outcome != "abstained":
                    return False
                if any(
                    evidence_id not in evidence or claim_id not in evidence[evidence_id]["claim_ids"]
                    for evidence_id in analysis["evidence_ids"]
                ):
                    return False
                if not set(analysis["precedent_source_ids"]) <= precedents:
                    return False
                if analysis["precedent_source_ids"] and (
                    not route["requires_legal_research"]
                    or not set(analysis["precedent_source_ids"]) <= set(
                        receipts[f"WRK-{claim_id}-LEGAL"]["source_ids"]
                    )
                ):
                    return False
                if analysis["evidence_ids"] and (
                    not route["requires_evidence_analysis"]
                    or not set(analysis["evidence_ids"]) <= set(review["evidence_ids"])
                ):
                    return False
                if analysis["facts_found"] and review["status"] != "reviewed":
                    return False
                if outcome in MERITS_OUTCOMES | PROCEDURAL_OUTCOMES:
                    if (
                        route["route_status"] != "routed"
                        or claim["status"] != "mapped"
                        or claim["review_gaps"]
                    ):
                        return False
                if outcome in MERITS_OUTCOMES:
                    if review["status"] != "reviewed":
                        return False
                    if route["requires_calculation_review"] and calculation["status"] != "criteria_reviewed":
                        return False
                    if any(
                        receipt["claim_id"] == claim_id and receipt["custody_status"] != "linked"
                        for receipt in receipts.values()
                    ):
                        return False
                if outcome in PROCEDURAL_OUTCOMES and (
                    not route["requires_procedural_review"]
                    or receipts[f"WRK-{claim_id}-PROCEDURAL"]["custody_status"] != "linked"
                ):
                    return False
            return True
        except (ContractError, ValueError, OSError, UnicodeError, KeyError, TypeError):
            return False

    return validate
