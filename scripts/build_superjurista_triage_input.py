#!/usr/bin/env python3
"""Conecta relatórios do TRT vinculados às fontes ao triador herdado."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
from collections import Counter
from pathlib import Path

from schema_validation import ContractError, load_json
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = ROOT / "runtime/contracts/schemas/labor-report.v1.schema.json"
MATRIX_SCHEMA = ROOT / "runtime/contracts/schemas/claim-matrix.v1.schema.json"


class TriageInputError(ValueError):
    """Indica perda ou atribuição incorreta de pedido na entrada da triagem."""


def _validate(value: dict, schema_path: Path, name: str) -> None:
    issues = validate_document(value, load_json(schema_path, f"{name} schema"))
    if issues:
        raise TriageInputError(f"{name} inválido: {issues[0]}")


def _source(value: dict) -> str:
    return f"{value['source_document_id']}, {value['source_locator']}"


def _position_key(value: dict) -> tuple[str, str, str]:
    return value["label"], value["source_document_id"], value["source_locator"]


def _validate_custody(report: dict, matrix: dict) -> None:
    report_claims = [item for item in report["positions"] if item["kind"] == "claim"]
    claims_by_id = {item["claim_id"]: item for item in matrix["claims"]}
    position_ids = [item["position_id"] for item in report_claims]
    claim_ids = [item["claim_id"] for item in matrix["claims"]]
    expected_ids = {item.replace("POS-", "CLM-", 1) for item in position_ids}
    if (
        len(position_ids) != len(set(position_ids))
        or len(claim_ids) != len(claims_by_id)
        or expected_ids != set(claims_by_id)
    ):
        raise TriageInputError("cobertura dos pedidos diverge entre relatório e matriz")

    for position in report_claims:
        claim_id = position["position_id"].replace("POS-", "CLM-", 1)
        claim = claims_by_id[claim_id]
        if _position_key(position) != _position_key({
            "label": claim["label"], **claim["claimant_position"]
        }):
            raise TriageInputError(f"fonte do pedido {claim_id} diverge")
        if position["summary"] != claim["claimant_position"]["summary"]:
            raise TriageInputError(f"resumo do pedido {claim_id} diverge")

    report_defenses = Counter(
        _position_key(item)
        for item in report["positions"] if item["kind"] == "defense"
    )
    matrix_defenses = Counter(
        (claim["label"], defense["source_document_id"], defense["source_locator"])
        for claim in matrix["claims"] for defense in claim["respondent_positions"]
    )
    if report_defenses != matrix_defenses:
        raise TriageInputError("fonte da defesa diverge entre relatório e matriz")
    report_defense_summaries = Counter(
        (*_position_key(item), item["summary"])
        for item in report["positions"] if item["kind"] == "defense"
    )
    matrix_defense_summaries = Counter(
        (claim["label"], defense["source_document_id"],
         defense["source_locator"], defense["summary"])
        for claim in matrix["claims"] for defense in claim["respondent_positions"]
    )
    if report_defense_summaries != matrix_defense_summaries:
        raise TriageInputError("resumo da defesa diverge entre relatório e matriz")

    respondents = {
        item["party_id"] for item in report["parties"] if item["role"] == "respondent"
    }
    for claim in matrix["claims"]:
        for defense in claim["respondent_positions"]:
            if defense["respondent_party_id"] not in respondents:
                raise TriageInputError("parte da defesa não consta entre os reclamados do relatório")


def build_triage_input(report: dict, matrix: dict) -> str:
    """Gera entrada do agente herdado sem decidir norma, prova ou resultado."""
    _validate(report, REPORT_SCHEMA, "relatório trabalhista")
    _validate(matrix, MATRIX_SCHEMA, "matriz de pedidos")
    _validate_custody(report, matrix)
    context = report["case_context"]
    respondents = {
        item["party_id"]: item["display_name"] for item in report["parties"]
    }
    lines = [
        "# Relatório estruturado para triagem processual",
        "",
        f"**Processo**: {context['case_number']}",
        f"**Tribunal**: {context['court']} — {context['instance']}º grau",
        f"**Unidade**: {context['court_unit']}",
        "**Insumos**: labor-report.json + claim-matrix.json",
        "",
        "Este documento reproduz posições estruturadas e suas fontes. Códigos não são conclusões jurídicas.",
        "Não presumir procedência, improcedência, concordância ou ausência de pedido por lacuna.",
        "",
        "## Linha do tempo",
        "",
    ]
    for event in report["timeline"]:
        date = event["event_date"] or "data não identificada"
        lines.append(f"- {date}: {event['summary']} ({_source(event)})")
    if not report["timeline"]:
        lines.append("- Sem eventos estruturados; consultar os autos.")

    lines.extend(["", "## Pedidos e defesas", ""])
    for claim in matrix["claims"]:
        lines.extend([
            f"### {claim['claim_id']} — {claim['label']}",
            f"- Posição da parte autora: {claim['claimant_position']['summary']}",
            f"- Fonte da parte autora: {_source(claim['claimant_position'])}",
            "- Providências pedidas (códigos): "
            + (", ".join(claim["requested_remedies"]) or "não estruturadas"),
        ])
        if claim["respondent_positions"]:
            for defense in claim["respondent_positions"]:
                party = respondents[defense["respondent_party_id"]]
                lines.append(
                    f"- Defesa {defense['defense_id']} — {party}: "
                    f"{defense['summary']} ({_source(defense)})"
                )
        else:
            lines.append("- Sem defesa vinculada; não presumir concordância.")
        lines.extend([
            "- Fatos controvertidos (códigos): "
            + (", ".join(claim["contested_facts"]) or "não estruturados"),
            "- Questões jurídicas (códigos): "
            + (", ".join(claim["legal_issues"]) or "não estruturadas"),
            "- Lacunas de revisão: "
            + (", ".join(claim["review_gaps"]) or "nenhuma registrada"),
            "",
        ])
    lines.extend([
        "## Lacunas gerais",
        "",
        ", ".join(report["review_gaps"]) or "Nenhuma registrada no relatório estruturado.",
        "",
    ])
    return "\n".join(lines)


def write_triage_input(content: str, output: Path, repository_root: Path = ROOT) -> Path:
    """Grava texto confidencial uma vez, fora da árvore de fontes."""
    if output.parent.is_symlink():
        raise TriageInputError("o diretório de saída não pode ser vínculo simbólico")
    destination = output.parent.resolve()
    repository = repository_root.resolve()
    if destination == repository or repository in destination.parents:
        raise TriageInputError("a saída da triagem deve ficar fora do repositório")
    if not destination.is_dir():
        raise TriageInputError("o diretório de saída da triagem deve existir antes da execução")
    if stat.S_IMODE(destination.stat().st_mode) & 0o077:
        raise TriageInputError("o diretório de saída da triagem deve ser privado")
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise TriageInputError("o arquivo de saída já existe") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara a entrada do triador herdado do SuperJurista.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = load_json(args.report, "relatório trabalhista")
        matrix = load_json(args.matrix, "matriz de pedidos")
        content = build_triage_input(report, matrix)
        write_triage_input(content, args.output)
    except (ContractError, TriageInputError, OSError) as error:
        print(f"[ERRO] Entrada de triagem do SuperJurista: {error}", file=sys.stderr)
        return 2
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    print(f"[OK] Entrada de triagem criada. SHA-256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
