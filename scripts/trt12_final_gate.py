#!/usr/bin/env python3
"""Conferir o relatório técnico final sem liberar pedidos em revisão humana."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from evaluate_final_gate import (
    FinalGateContractError,
    FinalGateRejected,
    evaluate_final_gate,
    require_final_acceptance,
)
from schema_validation import ContractError, load_json
from trt12_draft_gate import validate_draft_content
from trt12_merge_gate import make_merge_gate


def make_final_gate(workspace: Path) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Recalcular os controles e exigir saída explícita para cada pedido."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()
    merge_gate = make_merge_gate(root)

    def read_json(name: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("artefato ausente ou vínculo simbólico")
        return load_json(path, name)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if stage.get("id") != "review-and-gate" or stage.get("gate") != "global-acceptance":
            return False
        if outputs != (
            (root / "review-report.json").resolve(),
            (root / "global-gate.json").resolve(),
        ):
            return False
        try:
            context = read_json("case-context.json")
            merged_name = f"{context['case_number']}-labor-judgment.md"
            if not merge_gate(
                {"id": "merge-judgment", "gate": "deterministic-merge"},
                ((root / merged_name).resolve(),),
            ):
                return False
            claims = read_json("claim-matrix.json")
            analysis = read_json("claim-analysis.json")
            dispositions = read_json("disposition-matrix.json")
            corpus = read_json("precedent-corpus.json")
            review = read_json("review-report.json")
            actual_report = read_json("global-gate.json")
            if any(
                item["proposed_outcome"] == "pending_human_review"
                for item in analysis["analyses"]
            ):
                return False
            reviewed_sources = {item["source_id"]: item for item in review["sources"]}
            referenced_sources = {
                source_id
                for item in analysis["analyses"]
                for source_id in item["precedent_source_ids"]
            }
            corpus_sources = {item["source_id"]: item for item in corpus["sources"]}
            if set(reviewed_sources) != referenced_sources:
                return False
            if any(
                item["status"] == "available"
                and item["verbatim_excerpt"] != corpus_sources[source_id]["verbatim_excerpt"]
                for source_id, item in reviewed_sources.items()
            ):
                return False
            calculation_states = {
                item["claim_id"]: item
                for item in read_json("calculation-review.json")["calculations"]
            }
            final_calculations = {item["claim_id"]: item for item in review["calculations"]}
            if set(calculation_states) != set(final_calculations):
                return False
            for claim_id, state in calculation_states.items():
                final = final_calculations[claim_id]
                if state["status"] == "not_required":
                    if final["status"] != "not_required":
                        return False
                elif state["status"] == "criteria_reviewed":
                    if final["status"] != "completed" or final["criteria"] != state["criteria"]:
                        return False
                else:
                    return False
            draft = (root / "judgment-draft.md").read_text(encoding="utf-8")
            congruence = validate_draft_content(claims, analysis, dispositions, draft)
            expected_report = evaluate_final_gate(
                analysis, dispositions, draft, congruence, review
            )
            if actual_report != expected_report:
                return False
            require_final_acceptance(expected_report)
            return True
        except (
            ContractError, FinalGateContractError, FinalGateRejected,
            ValueError, OSError, UnicodeError, KeyError, TypeError,
        ):
            return False

    return validate
