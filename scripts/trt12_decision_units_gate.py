#!/usr/bin/env python3
"""Validate decision matrices against the accepted, source-linked record."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable

from promote_reviewed_evidence_matrix import verify_promoted_evidence_matrix
from build_claim_matrix import (
    ClaimCandidate,
    DefenseCandidate,
    SourceReference,
    build_claim_matrix,
    load_claim_taxonomy,
)
from schema_validation import ContractError, load_json, validate_schema_value
from validate_artifact_contracts import load_catalog, validate_document
from verify_pje_acquisition_custody import INDEX_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "runtime/contracts/catalog.json"
TAXONOMY = ROOT / "runtime/domain/labor-claim-taxonomy.json"
CONTRACTS = {
    "labor-report.json": "labor-report",
    "claim-matrix.json": "claim-matrix",
    "evidence-matrix.json": "evidence-matrix",
}
OUTPUTS = ("claim-matrix.json", "evidence-matrix.json")
INVENTORY_PROMOTION_MARKERS = (
    "evidence-inventory-index.json",
    "evidence-matrix-candidates.json",
    "evidence-selection-provenance.json",
    "evidence-matrix-approval.json",
    "evidence-matrix-promotion.json",
)


def _claims_match_report(report: dict, matrix: dict, known_documents: set[str]) -> bool:
    positions = report["positions"]
    def signature(position: dict) -> tuple[str, str, str, str]:
        return (
            position["label"], position["summary"],
            position["source_document_id"], position["source_locator"],
        )

    claim_positions = {
        position["position_id"].replace("POS-", "CLM-", 1): signature(position)
        for position in positions if position["kind"] == "claim"
    }
    defense_positions = Counter(
        signature(position) for position in positions if position["kind"] == "defense"
    )
    claim_labels = Counter(
        position["label"] for position in positions if position["kind"] == "claim"
    )
    claims = matrix["claims"]
    if (
        not claim_positions
        or len({position["position_id"] for position in positions}) != len(positions)
        or len({party["party_id"] for party in report["parties"]}) != len(report["parties"])
        or len({claim["claim_id"] for claim in claims}) != len(claims)
        or {claim["claim_id"] for claim in claims} != set(claim_positions)
        or any(claim_labels[label] != 1 for label, *_ in defense_positions)
    ):
        return False
    respondents = {
        party["party_id"] for party in report["parties"] if party["role"] == "respondent"
    }
    used_defenses = set()
    for claim in claims:
        claimant = claim["claimant_position"]
        claim_source = (
            claim["label"], claimant["summary"],
            claimant["source_document_id"], claimant["source_locator"],
        )
        if (
            claim_source != claim_positions[claim["claim_id"]]
            or claimant["source_document_id"] not in known_documents
        ):
            return False
        for defense in claim["respondent_positions"]:
            defense_id = defense["defense_id"]
            defense_source = (
                claim["label"], defense["summary"],
                defense["source_document_id"], defense["source_locator"],
            )
            if (
                not defense_positions[defense_source]
                or defense_id in used_defenses
                or defense["respondent_party_id"] not in respondents
                or defense["source_document_id"] not in known_documents
            ):
                return False
            defense_positions[defense_source] -= 1
            used_defenses.add(defense_id)
    return all(count == 0 for count in defense_positions.values())


def _evidence_matches_claims(evidence: dict, claim_ids: set[str], known_documents: set[str]) -> bool:
    items = evidence["evidence_items"]
    by_id = {item["evidence_id"]: item for item in items}
    if len(by_id) != len(items):
        return False
    covered = set()
    for item in items:
        if item["source_document_id"] not in known_documents:
            return False
        if not set(item["claim_ids"]) <= claim_ids:
            return False
        covered.update(item["claim_ids"])
        conflicts = item["conflicts_with_evidence_ids"]
        if conflicts and item["analysis_status"] != "disputed":
            return False
        for conflict_id in conflicts:
            if (
                conflict_id == item["evidence_id"]
                or conflict_id not in by_id
                or item["evidence_id"] not in by_id[conflict_id]["conflicts_with_evidence_ids"]
            ):
                return False
    return set(evidence["uncovered_claim_ids"]) == claim_ids - covered


def _matches_claim_builder(matrix: dict, known_documents: set[str]) -> bool:
    claims = []
    defenses = []
    for item in matrix["claims"]:
        claimant = item["claimant_position"]
        claims.append(ClaimCandidate(
            claim_id=item["claim_id"],
            label=item["label"],
            claimant_position=claimant["summary"],
            requested_remedies=tuple(item["requested_remedies"]),
            contested_facts=tuple(item["contested_facts"]),
            legal_issues=tuple(item["legal_issues"]),
            source=SourceReference(
                claimant["source_document_id"], claimant["source_locator"]
            ),
        ))
        for defense in item["respondent_positions"]:
            defenses.append(DefenseCandidate(
                defense_id=defense["defense_id"],
                claim_id=item["claim_id"],
                respondent_party_id=defense["respondent_party_id"],
                respondent_position=defense["summary"],
                source=SourceReference(
                    defense["source_document_id"], defense["source_locator"]
                ),
            ))
    rebuilt = build_claim_matrix(
        load_claim_taxonomy(TAXONOMY),
        tuple(sorted(known_documents)),
        tuple(claims),
        tuple(defenses),
    )
    return rebuilt == matrix


def make_decision_units_gate(workspace: Path) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Return a fail-closed gate for the claim and evidence matrix stage."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()

    def read_json(name: str, label: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("insumo ausente ou vínculo simbólico")
        return load_json(path, label)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if stage.get("id") != "build-decision-units" or stage.get("gate") != "decision-unit-coverage":
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
            known_documents = {document["document_id"] for document in index["documents"]}
            if not known_documents or len(known_documents) != len(index["documents"]):
                return False
            _, contracts = load_catalog(CATALOG)
            artifacts = {}
            for name, contract_id in CONTRACTS.items():
                value = read_json(name, contract_id)
                if validate_document(value, contracts[contract_id][0]):
                    return False
                artifacts[name] = value
            report = artifacts["labor-report.json"]
            claims = artifacts["claim-matrix.json"]
            evidence = artifacts["evidence-matrix.json"]
            if report["case_context"] != context:
                return False
            if not _claims_match_report(report, claims, known_documents):
                return False
            if not _matches_claim_builder(claims, known_documents):
                return False
            claim_ids = {claim["claim_id"] for claim in claims["claims"]}
            if not _evidence_matches_claims(evidence, claim_ids, known_documents):
                return False
            if any(
                (root / name).exists() or (root / name).is_symlink()
                for name in INVENTORY_PROMOTION_MARKERS
            ):
                verify_promoted_evidence_matrix(root)
            return True
        except (ContractError, ValueError, OSError, UnicodeError, KeyError, TypeError):
            return False

    return validate
