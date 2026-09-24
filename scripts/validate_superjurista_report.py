#!/usr/bin/env python3
"""Confere a visão narrativa do relator trabalhista herdado."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from build_superjurista_triage_input import TriageInputError, build_triage_input
from schema_validation import ContractError, load_json

ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD_SCRIPTS = ROOT / "scaffold/scripts"
if str(SCAFFOLD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_SCRIPTS))
from verificar_sentenca import ETAPAS, _conferir  # noqa: E402


def _records(value: object, fields: set[str], label: str) -> Counter[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, dict)
        or set(item) != fields
        or not all(isinstance(item[field], str) and item[field] for field in fields)
        for item in value
    ):
        raise ValueError(f"{label} têm campos inválidos")
    return Counter(json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value)


def validate_report_narrative(report: dict, matrix: dict, input_text: str, narrative: str) -> None:
    """Confere a cobertura da narrativa contra os insumos estruturados atuais."""
    expected_input = build_triage_input(report, matrix)
    if input_text != expected_input:
        raise ValueError("a entrada protegida diverge do relatório e da matriz atuais")
    _, beginning, ending, contains, minimum = ETAPAS["relatorio"]
    format_issues = _conferir(narrative, beginning, ending, contains, minimum)
    if format_issues:
        raise ValueError(f"formato herdado do relatório inválido: {format_issues[0]}")
    if not narrative.startswith("RELATÓRIO\n") or not narrative.rstrip().endswith(
        "\nÉ o que havia de relevante a relatar."
    ):
        raise ValueError("o relatório não respeita os marcadores exatos de abertura e fecho")
    digests = re.findall(r"^Insumo SHA-256: ([0-9a-f]{64})$", narrative, re.MULTILINE)
    if digests != [hashlib.sha256(expected_input.encode("utf-8")).hexdigest()]:
        raise ValueError("o resumo da entrada na narrativa diverge da entrada protegida")
    case_numbers = re.findall(r"^Processo: (\S+)$", narrative, re.MULTILINE)
    if case_numbers != [report["case_context"]["case_number"]]:
        raise ValueError("o número do processo na narrativa diverge do relatório")
    headings = list(re.finditer(r"^REFERÊNCIAS DE COBERTURA$", narrative, re.MULTILINE))
    blocks = list(re.finditer(r"```json\s*(.*?)```", narrative, re.DOTALL))
    if len(blocks) != 1:
        raise ValueError("a cobertura exige exatamente um bloco JSON")
    if len(headings) != 1 or headings[0].end() > blocks[0].start() or narrative[
        headings[0].end():blocks[0].start()
    ].strip():
        raise ValueError("o bloco JSON deve seguir as referências de cobertura")
    try:
        coverage = json.loads(blocks[0].group(1))
    except json.JSONDecodeError as error:
        raise ValueError("o bloco JSON da cobertura é inválido") from error
    if not isinstance(coverage, dict) or "events" not in coverage:
        raise ValueError("cobertura dos eventos ausente")
    if set(coverage) != {"events", "claims", "defenses", "unanswered_claim_ids"}:
        raise ValueError("a cobertura tem campos inválidos")
    expected_events = [
        {
            "event_id": event["event_id"],
            "source_document_id": event["source_document_id"],
            "source_locator": event["source_locator"],
        }
        for event in report["timeline"]
    ]
    event_fields = {"event_id", "source_document_id", "source_locator"}
    if _records(coverage["events"], event_fields, "eventos") != _records(
        expected_events, event_fields, "eventos esperados"
    ):
        raise ValueError("a cobertura dos eventos diverge do relatório")
    expected_claims = [
        {
            "claim_id": claim["claim_id"],
            "source_document_id": claim["claimant_position"]["source_document_id"],
            "source_locator": claim["claimant_position"]["source_locator"],
        }
        for claim in matrix["claims"]
    ]
    claim_fields = {"claim_id", "source_document_id", "source_locator"}
    if _records(coverage["claims"], claim_fields, "pedidos") != _records(
        expected_claims, claim_fields, "pedidos esperados"
    ):
        raise ValueError("a cobertura dos pedidos diverge da matriz")
    expected_defenses = [
        {
            "defense_id": defense["defense_id"],
            "claim_id": claim["claim_id"],
            "respondent_party_id": defense["respondent_party_id"],
            "source_document_id": defense["source_document_id"],
            "source_locator": defense["source_locator"],
        }
        for claim in matrix["claims"]
        for defense in claim["respondent_positions"]
    ]
    defense_fields = {
        "defense_id", "claim_id", "respondent_party_id",
        "source_document_id", "source_locator",
    }
    if _records(coverage["defenses"], defense_fields, "defesas") != _records(
        expected_defenses, defense_fields, "defesas esperadas"
    ):
        raise ValueError("a cobertura das defesas diverge da matriz")
    unanswered = coverage["unanswered_claim_ids"]
    if not isinstance(unanswered, list) or not all(
        isinstance(item, str) for item in unanswered
    ):
        raise ValueError("pedidos sem defesa têm formato inválido")
    expected_unanswered = [
        claim["claim_id"] for claim in matrix["claims"]
        if not claim["respondent_positions"]
    ]
    if Counter(unanswered) != Counter(expected_unanswered):
        raise ValueError("pedidos sem defesa divergem da matriz")


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida o relatório narrativo trabalhista.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--narrative", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = load_json(args.report, "relatório trabalhista")
        matrix = load_json(args.matrix, "matriz de pedidos")
        validate_report_narrative(
            report,
            matrix,
            args.input.read_text(encoding="utf-8"),
            args.narrative.read_text(encoding="utf-8"),
        )
    except (ContractError, TriageInputError, ValueError, OSError, UnicodeError) as error:
        print(f"[ERRO] Relatório narrativo: {error}", file=sys.stderr)
        return 2
    print("[OK] Relatório narrativo validado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
