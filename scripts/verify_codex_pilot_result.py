#!/usr/bin/env python3
"""Confere a integridade técnica de um piloto Codex, sem julgar o mérito."""

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
from datetime import datetime
from pathlib import Path

from prepare_codex_pilot_handoff import _protected_preflight
from run_codex_pilot import RESULT_NAME, RESULT_SCHEMA
from schema_validation import ContractError, load_json, validate_schema_value
from trt12_handoff_gate import make_handoff_gate
from validate_pilot_preflight import DEFAULT_SCHEMA, ROOT


class CodexPilotResultError(ValueError):
    """Indica resultado técnico inconsistente ou sem custódia verificável."""


def _private_file(path: Path) -> None:
    if path.is_symlink():
        raise CodexPilotResultError("artefato contém vínculo simbólico")
    if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise CodexPilotResultError("artefato ausente ou sem proteção local")


def _digest(path: Path) -> str:
    _private_file(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _check_summary_binding(summary: dict, preflight: dict, report: dict) -> None:
    if summary["model_id"] != preflight["controls"].get("codex_model_id"):
        raise CodexPilotResultError("modelo do resumo diverge da autorização")
    if "codex" not in preflight["controls"]["model_providers_authorized"] or (
        "analyze" not in preflight["controls"]["requested_operations"]
    ):
        raise CodexPilotResultError("despacho Codex não consta da autorização")
    bindings = (
        ("pilot_id", preflight["pilot_id"]),
        ("case_reference_digest", preflight["case"]["reference_digest"]),
        ("development_commit", preflight["evidence"]["development_commit"]),
        ("endpoint_map_digest", preflight["evidence"]["endpoint_map_digest"]),
    )
    if any(summary[field] != expected for field, expected in bindings):
        raise CodexPilotResultError("resumo diverge da autorização protegida")
    case = report["case_context"]
    if (
        case["case_number"] != preflight["case"]["case_number"]
        or case["court"] != "TRT12"
        or case["instance"] != 1
        or case["confidentiality"] != preflight["case"]["access_classification"]
    ):
        raise CodexPilotResultError("processo diverge da autorização protegida")
    finished = _timestamp(summary["finished_at"])
    if not _timestamp(preflight["created_at"]) <= finished < _timestamp(
        preflight["valid_until"]
    ):
        raise CodexPilotResultError("resultado fora da validade da autorização")


def verify_codex_pilot_result(workspace: Path, preflight: dict) -> dict:
    """Reconfere hashes, autorização e três checkpoints, sem modificar arquivos."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise CodexPilotResultError("diretório protegido do piloto inválido")
    root = workspace.resolve()
    if root.is_relative_to(ROOT.resolve()) or stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise CodexPilotResultError("diretório do piloto deve ser privado e externo ao Git")
    try:
        if validate_schema_value(preflight, load_json(DEFAULT_SCHEMA, "esquema do piloto")):
            raise CodexPilotResultError("registro da autorização não respeita o contrato")
        summary_path = root / RESULT_NAME
        _private_file(summary_path)
        summary_bytes = summary_path.read_bytes()
        summary = load_json(summary_path, "resumo do piloto Codex")
        if validate_schema_value(summary, load_json(RESULT_SCHEMA, "esquema do resultado")):
            raise CodexPilotResultError("resumo do piloto não respeita o contrato")

        report_path = root / "labor-report.json"
        if _digest(report_path) != summary["input_artifact_sha256"]["report"]:
            raise CodexPilotResultError("SHA-256 do relatório diverge do resumo")
        report = load_json(report_path, "relatório trabalhista")
        _check_summary_binding(summary, preflight, report)
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
                raise CodexPilotResultError(f"SHA-256 de {role} diverge do resumo")

        gate = make_handoff_gate(root)
        stages = (
            ("prepare-triage-input", "triage-input-custody", (paths[2][2],)),
            ("narrate-record", "report-narrative-coverage", (paths[3][2],)),
            ("route-claims", "route-coverage", tuple(item[2] for item in paths[4:])),
        )
        for stage_id, gate_name, outputs in stages:
            if not gate({"id": stage_id, "gate": gate_name}, outputs):
                raise CodexPilotResultError("controle de transferência reprovado")
        if summary_path.read_bytes() != summary_bytes or any(
            _digest(path) != summary[section][role] for section, role, path in paths
        ):
            raise CodexPilotResultError("artefato mudou durante a verificação")
        return {
            "integrity": "passed",
            "status": "pending_legal_review",
            "passed_handoff_gates": 3,
            "pilot_id": summary["pilot_id"],
        }
    except (ContractError, OSError, UnicodeError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, CodexPilotResultError):
            raise
        raise CodexPilotResultError("não foi possível verificar o resultado protegido") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verifica a integridade técnica do resultado de um piloto Codex TRT12."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify_codex_pilot_result(args.workspace, _protected_preflight(args.preflight))
    except (CodexPilotResultError, ContractError, OSError, ValueError) as error:
        print(f"[NO-GO] Verificação do piloto Codex: {error}", file=sys.stderr)
        return 2
    print(f"[OK] Integridade técnica conferida para {result['pilot_id']}.")
    print("Revisão jurídica humana ainda pendente; nenhum ato judicial foi autorizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
