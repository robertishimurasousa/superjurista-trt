#!/usr/bin/env python3
"""Reconfere o resultado técnico do piloto pela API, sem julgar o mérito."""

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
from datetime import datetime
from pathlib import Path

from run_openai_pilot import RESULT_NAME, RESULT_SCHEMA, _authorization_digest
from schema_validation import ContractError, load_json, validate_schema_value
from trt12_handoff_gate import make_handoff_gate
from validate_openai_api_authorization import (
    OpenAIAPIAuthorizationError,
    _protected_record,
    validate_openai_api_authorization,
)
from validate_pilot_preflight import ROOT


class OpenAIPilotResultError(ValueError):
    """Indica resultado sem vínculo ou custódia técnica demonstrável."""


def _private_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise OpenAIPilotResultError("artefato protegido ausente ou vínculo simbólico")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise OpenAIPilotResultError("artefato sem proteção local")


def _digest(path: Path) -> str:
    _private_file(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_binding(summary: dict, preflight: dict, authorization: dict, report: dict) -> None:
    finished = datetime.fromisoformat(summary["finished_at"].replace("Z", "+00:00"))
    validate_openai_api_authorization(authorization, preflight, now=finished)
    expected = {
        "pilot_id": preflight["pilot_id"],
        "case_reference_digest": preflight["case"]["reference_digest"],
        "authorization_scope_digest": preflight["case"]["authorization_scope_digest"],
        "api_authorization_digest": _authorization_digest(authorization),
        "provider_terms_digest": authorization["provider_terms_digest"],
        "development_commit": preflight["evidence"]["development_commit"],
        "endpoint_map_digest": preflight["evidence"]["endpoint_map_digest"],
        "model_id": authorization["model_id"],
    }
    if any(summary[field] != value for field, value in expected.items()):
        raise OpenAIPilotResultError("resumo diverge da autorização protegida")
    case = report["case_context"]
    if (
        case["case_number"] != preflight["case"]["case_number"]
        or case["court"] != "TRT12"
        or case["instance"] != 1
        or case["confidentiality"] != preflight["case"]["access_classification"]
    ):
        raise OpenAIPilotResultError("relatório diverge do processo autorizado")


def verify_openai_pilot_result(
    workspace: Path, preflight: dict, authorization: dict
) -> dict:
    """Confere fontes, autorização e três checkpoints sem alterar arquivos."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise OpenAIPilotResultError("diretório protegido inválido")
    root = workspace.resolve()
    if root.is_relative_to(ROOT.resolve()) or stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise OpenAIPilotResultError("diretório deve ser privado e externo ao Git")
    try:
        summary_path = root / RESULT_NAME
        _private_file(summary_path)
        summary_bytes = summary_path.read_bytes()
        summary = load_json(summary_path, "resumo do piloto pela API")
        if validate_schema_value(summary, load_json(RESULT_SCHEMA, "esquema do resultado")):
            raise OpenAIPilotResultError("resumo do piloto pela API inválido")
        report_path = root / "labor-report.json"
        if _digest(report_path) != summary["input_artifact_sha256"]["report"]:
            raise OpenAIPilotResultError("SHA-256 do relatório diverge")
        report = load_json(report_path, "relatório trabalhista")
        _check_binding(summary, preflight, authorization, report)
        case_number = report["case_context"]["case_number"]
        paths = (
            ("input_artifact_sha256", "report", report_path),
            ("input_artifact_sha256", "matrix", root / "claim-matrix.json"),
            ("input_artifact_sha256", "triage_input", root / "triage-input.md"),
            ("generated_artifact_sha256", "narrative", root / "report-narrative.md"),
            ("generated_artifact_sha256", "triage", root / f"{case_number}-triagem.md"),
            ("generated_artifact_sha256", "sources", root / "fontes-triagem.json"),
            ("generated_artifact_sha256", "routes", root / "issue-route.json"),
        )
        for section, role, path in paths:
            if _digest(path) != summary[section][role]:
                raise OpenAIPilotResultError("SHA-256 de artefato diverge do resumo")

        gate = make_handoff_gate(root)
        stages = (
            ("prepare-triage-input", "triage-input-custody", (paths[2][2],)),
            ("narrate-record", "report-narrative-coverage", (paths[3][2],)),
            ("route-claims", "route-coverage", tuple(item[2] for item in paths[4:])),
        )
        for stage_id, gate_name, outputs in stages:
            if not gate({"id": stage_id, "gate": gate_name}, outputs):
                raise OpenAIPilotResultError("controle de transferência reprovado")
        if summary_path.read_bytes() != summary_bytes or any(
            _digest(path) != summary[section][role] for section, role, path in paths
        ):
            raise OpenAIPilotResultError("artefato mudou durante a verificação")
        return {
            "integrity": "passed",
            "status": "pending_legal_review",
            "passed_handoff_gates": 3,
            "pilot_id": summary["pilot_id"],
        }
    except (ContractError, OpenAIAPIAuthorizationError, OSError, UnicodeError,
            KeyError, TypeError, ValueError) as error:
        if isinstance(error, OpenAIPilotResultError):
            raise
        raise OpenAIPilotResultError("não foi possível verificar o resultado protegido") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconfere a integridade técnica do piloto TRT12 pela API."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--api-authorization", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify_openai_pilot_result(
            args.workspace,
            _protected_record(args.preflight),
            _protected_record(args.api_authorization),
        )
    except (OpenAIPilotResultError, OpenAIAPIAuthorizationError, OSError) as error:
        print(f"[NO-GO] Verificação do piloto pela API: {error}", file=sys.stderr)
        return 2
    print(f"[OK] Integridade técnica conferida para {result['pilot_id']}.")
    print("Revisão jurídica humana ainda pendente; nenhum ato judicial foi autorizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
