#!/usr/bin/env python3
"""Validar a minuta e o dispositivo contra a análise aceita do pedido."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from build_claim_decisions import (
    ClaimDecisionContractViolation,
    render_judgment_draft,
)
from schema_validation import ContractError, load_json
from trt12_claim_analysis_gate import make_claim_analysis_gate
from validate_artifact_contracts import load_catalog, validate_document
from validate_decision_congruence import (
    DecisionCongruenceError,
    validate_decision_congruence,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "runtime/contracts/catalog.json"
NO_COMMAND_PENDING = "Nenhum comando dispositivo pode ser emitido antes da revisão humana."
NO_COMMAND_ABSTAINED = "Nenhum comando dispositivo foi produzido devido à abstenção."


def validate_draft_content(
    claims: dict,
    analysis: dict,
    dispositions: dict,
    draft: str,
) -> dict:
    """Exigir congruência integral e ausência de comando para resultado não decidido."""
    claim_ids = tuple(item["claim_id"] for item in claims["claims"])
    congruence = validate_decision_congruence(claim_ids, analysis, dispositions, draft)
    for item in dispositions["items"]:
        outcome = item["outcome"]
        if outcome in ("pending_human_review", "abstained"):
            expected = (
                NO_COMMAND_PENDING if outcome == "pending_human_review" else NO_COMMAND_ABSTAINED
            )
            if (
                item["command"] != expected
                or item["period"] != "not_applicable"
                or item["effects"]
                or item["calculation_criteria"]
            ):
                raise ValueError("resultado não decidido contém comando ou efeitos")
    if draft != render_judgment_draft(analysis, dispositions):
        raise ValueError("minuta diverge da renderização determinística dos artefatos")
    return congruence


def make_draft_gate(workspace: Path) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Compor o controle da análise com a validação protegida do dispositivo."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()
    prior_gate = make_claim_analysis_gate(root)

    def read_json(name: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("artefato ausente ou vínculo simbólico")
        return load_json(path, name)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if stage.get("id") != "draft-judgment" or stage.get("gate") != "draft-congruence":
            return False
        if outputs != (
            (root / "disposition-matrix.json").resolve(),
            (root / "judgment-draft.md").resolve(),
        ):
            return False
        if not prior_gate(
            {"id": "analyze-claims", "gate": "claim-analysis-coverage"},
            ((root / "claim-analysis.json").resolve(),),
        ):
            return False
        try:
            _, contracts = load_catalog(CATALOG)
            claims = read_json("claim-matrix.json")
            analysis = read_json("claim-analysis.json")
            dispositions = read_json("disposition-matrix.json")
            if validate_document(dispositions, contracts["disposition-matrix"][0]):
                return False
            draft_path = root / "judgment-draft.md"
            if draft_path.is_symlink() or not draft_path.is_file():
                return False
            draft = draft_path.read_text(encoding="utf-8")
            validate_draft_content(claims, analysis, dispositions, draft)
            return True
        except (
            ClaimDecisionContractViolation, ContractError, DecisionCongruenceError,
            ValueError, OSError, UnicodeError, KeyError, TypeError,
        ):
            return False

    return validate
