#!/usr/bin/env python3
"""Converte a triagem global herdada em rotas verificadas por pedido."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from build_issue_routes import (
    IssueRouteCandidate,
    IssueRouteContractViolation,
    build_issue_routes,
)
from build_superjurista_triage_input import (
    TriageInputError,
    build_triage_input,
    write_triage_input,
)
from schema_validation import ContractError, load_json
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD_SCRIPTS = ROOT / "scaffold/scripts"
if str(SCAFFOLD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_SCRIPTS))
from verificar_sentenca import ETAPAS, RE_BLOCO_JSON, _conferir, validar_rota  # noqa: E402


MATRIX_SCHEMA = ROOT / "runtime/contracts/schemas/claim-matrix.v1.schema.json"
ROUTE_SCHEMA = ROOT / "runtime/contracts/schemas/issue-route.v1.schema.json"
CASE_LINE = re.compile(r"^\*\*Processo\*\*:\s*`?([0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4})`?\s*$", re.MULTILINE)
INPUT_DIGEST_LINE = re.compile(r"^\*\*Insumo SHA-256\*\*:\s*`?([0-9a-f]{64})`?\s*$", re.MULTILINE)
CLAIM_ROUTE_FIELDS = {
    "claim_id", "requires_legal_research", "requires_evidence_analysis",
    "requires_calculation_review", "requires_procedural_review",
    "research_questions", "evidence_questions", "route_reason", "abstention_reasons",
}


class TriageImportError(ValueError):
    """Indica que a triagem herdada não pode gerar tarefas seguras por pedido."""


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TriageImportError(f"{field} deve ser uma lista de textos")
    return tuple(value)


def _claim_candidates(value: object) -> tuple[IssueRouteCandidate, ...]:
    if not isinstance(value, list):
        raise TriageImportError("rotas_por_pedido deve ser uma lista")
    candidates = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != CLAIM_ROUTE_FIELDS:
            raise TriageImportError(f"rota do pedido no índice {index} tem campos inválidos")
        if item["requires_calculation_review"] is not False or item["requires_procedural_review"] is not False:
            raise TriageImportError("trilha não suportada na triagem herdada")
        candidates.append(IssueRouteCandidate(
            claim_id=item["claim_id"],
            requires_legal_research=item["requires_legal_research"],
            requires_evidence_analysis=item["requires_evidence_analysis"],
            requires_calculation_review=False,
            requires_procedural_review=False,
            research_questions=_string_tuple(item["research_questions"], "research_questions"),
            evidence_questions=_string_tuple(item["evidence_questions"], "evidence_questions"),
            route_reason=item["route_reason"],
            abstention_reasons=_string_tuple(item["abstention_reasons"], "abstention_reasons"),
        ))
    return tuple(candidates)


def import_triage(
    triage_text: str, matrix: dict, sources: dict, case_number: str | None = None,
    input_digest: str | None = None,
) -> dict:
    """Reusa o controle C2 e exige cobertura exata das rotas por pedido."""
    if not isinstance(input_digest, str) or re.fullmatch(r"[0-9a-f]{64}", input_digest) is None:
        raise TriageImportError("o resumo validado da entrada de triagem é obrigatório")
    if not isinstance(sources, dict) or set(sources) != {"fontes"} or sources["fontes"] != []:
        raise TriageImportError("as fontes do TRT12 devem ficar vazias até integrar a custódia oficial")
    issues = validate_document(matrix, load_json(MATRIX_SCHEMA, "esquema da matriz de pedidos"))
    if issues:
        raise TriageImportError(f"matriz de pedidos inválida: {issues[0]}")
    suffix, beginning, ending, contains, minimum = ETAPAS["triagem"]
    del suffix
    format_issues = _conferir(triage_text, beginning, ending, contains, minimum)
    if format_issues:
        raise TriageImportError(f"formato da triagem inválido: {format_issues[0]}")
    found_case = CASE_LINE.search(triage_text)
    if found_case is None or (case_number is not None and found_case.group(1) != case_number):
        raise TriageImportError("o número do processo na triagem diverge do relatório")
    found_digests = INPUT_DIGEST_LINE.findall(triage_text)
    if len(found_digests) != 1 or found_digests[0] != input_digest:
        raise TriageImportError("o resumo da entrada de triagem diverge da entrada protegida")
    blocks = RE_BLOCO_JSON.findall(triage_text)
    if len(blocks) != 1:
        raise TriageImportError("a triagem exige exatamente um bloco JSON")
    try:
        decision = json.loads(blocks[0])
    except json.JSONDecodeError as error:
        raise TriageImportError(f"JSON da triagem inválido: {error.msg}") from error
    error = validar_rota(decision)
    if error:
        raise TriageImportError(f"rota herdada inválida: {error}")
    if not decision["rota"]:
        raise TriageImportError("rota direta exige custódia de fontes oficiais antes de usar no TRT12")
    if "rotas_por_pedido" not in decision:
        raise TriageImportError("faltam rotas por pedido na triagem herdada")
    try:
        routes = build_issue_routes(
            tuple(claim["claim_id"] for claim in matrix["claims"]),
            _claim_candidates(decision["rotas_por_pedido"]),
        )
    except IssueRouteContractViolation as error:
        raise TriageImportError(f"rotas dos pedidos inválidas: {error}") from error
    expected_global = set()
    if any(route["requires_legal_research"] for route in routes["routes"]):
        expected_global.add("pesquisa")
    if any(route["requires_evidence_analysis"] for route in routes["routes"]):
        expected_global.add("probatica")
    if set(decision["rota"]) != expected_global or len(decision["rota"]) != len(expected_global):
        raise TriageImportError("rota global diverge das rotas por pedido")
    expected_research = {
        question for route in routes["routes"] for question in route["research_questions"]
    }
    expected_evidence = {
        question for route in routes["routes"] for question in route["evidence_questions"]
    }
    themes = _string_tuple(decision.get("temas_pesquisa"), "temas_pesquisa")
    facts = _string_tuple(decision.get("fatos_probatorios"), "fatos_probatorios")
    if (
        set(themes) != expected_research or len(themes) != len(expected_research)
        or set(facts) != expected_evidence or len(facts) != len(expected_evidence)
    ):
        raise TriageImportError("perguntas globais divergem das rotas por pedido")
    route_issues = validate_document(routes, load_json(ROUTE_SCHEMA, "esquema das rotas por pedido"))
    if route_issues:
        raise TriageImportError(f"rotas por pedido inválidas: {route_issues[0]}")
    return routes


def write_issue_route(value: dict, output: Path, repository_root: Path = ROOT) -> Path:
    """Mantém a rota derivada protegida e sem sobrescrita."""
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    try:
        return write_triage_input(payload, output, repository_root)
    except TriageInputError as error:
        raise TriageImportError(str(error)) from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa a triagem herdada para rotas por pedido no TRT.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--triage", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = load_json(args.report, "relatório trabalhista")
        matrix = load_json(args.matrix, "matriz de pedidos")
        sources = load_json(args.sources, "fontes da triagem")
        expected_input = build_triage_input(report, matrix)
        if args.input.read_text(encoding="utf-8") != expected_input:
            raise TriageImportError("a entrada protegida diverge do relatório e da matriz atuais")
        input_digest = hashlib.sha256(expected_input.encode("utf-8")).hexdigest()
        triage_text = args.triage.read_text(encoding="utf-8")
        routes = import_triage(
            triage_text, matrix, sources, report["case_context"]["case_number"],
            input_digest,
        )
        write_issue_route(routes, args.output)
    except (ContractError, TriageInputError, TriageImportError, OSError, UnicodeError) as error:
        print(f"[ERRO] Importação da triagem do SuperJurista: {error}", file=sys.stderr)
        return 2
    print("[OK] Rotas de triagem criadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
