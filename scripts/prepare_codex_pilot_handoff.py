#!/usr/bin/env python3
"""Prepara insumos reais somente após GO específico do processo no piloto."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from build_superjurista_triage_input import TriageInputError, build_triage_input
from schema_validation import ContractError, load_json
from validate_pilot_preflight import (
    DEFAULT_MAP_REVIEW_CONTRACT,
    DEFAULT_SANITIZATION_CONTRACT,
    DEFAULT_SCHEMA,
    ROOT,
    PilotPreflightError,
    _git_value,
    validate_pilot_preflight,
)


class CodexPilotHandoffError(ValueError):
    """Indica que o despacho de insumos reais permanece bloqueado."""


def _private_directory(path: Path, label: str) -> None:
    if not isinstance(path, Path) or path.is_symlink() or not path.is_dir():
        raise CodexPilotHandoffError(f"{label} deve ser um diretório real")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise CodexPilotHandoffError(f"{label} deve ter acesso privado")


def _protected_preflight(path: Path) -> dict:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.resolve().is_relative_to(ROOT.resolve())
        or stat.S_IMODE(path.stat().st_mode) & 0o077
    ):
        raise CodexPilotHandoffError("registro protegido da verificação prévia inválido")
    return load_json(path, "verificação prévia")


def _source(path: Path, workspace: Path, label: str) -> str:
    if not isinstance(path, Path) or path.is_symlink() or not path.is_file():
        raise CodexPilotHandoffError(f"{label} ausente ou vínculo simbólico")
    resolved = path.resolve()
    if not resolved.is_relative_to(workspace.resolve()):
        raise CodexPilotHandoffError(f"{label} deve estar no espaço autorizado")
    for parent in path.parents:
        if parent == workspace:
            break
        if parent.is_symlink():
            raise CodexPilotHandoffError(f"{label} contém vínculo simbólico")
    return path.read_text(encoding="utf-8")


def _publish(output: Path, contents: tuple[tuple[str, str], ...]) -> tuple[Path, ...]:
    created = []
    try:
        for name, content in contents:
            path = output / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
        return tuple(created)
    except (OSError, UnicodeError):
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def _stage_case_inputs(
    preflight: dict, workspace: Path, output: Path,
    report_path: Path, matrix_path: Path, input_path: Path,
) -> tuple[Path, ...]:
    """Confere a identidade do processo e copia a entrada já construída."""
    report_text = _source(report_path, workspace, "relatório")
    matrix_text = _source(matrix_path, workspace, "matriz")
    input_text = _source(input_path, workspace, "entrada de triagem")
    report = json.loads(report_text)
    matrix = json.loads(matrix_text)
    case = report["case_context"]
    if (
        case["case_number"] != preflight["case"]["case_number"]
        or case["court"] != "TRT12"
        or case["instance"] != 1
        or case["confidentiality"] != preflight["case"]["access_classification"]
    ):
        raise CodexPilotHandoffError("relatório diverge do processo autorizado")
    if input_text != build_triage_input(report, matrix):
        raise CodexPilotHandoffError("entrada diverge do relatório e da matriz")
    return _publish(output, (
        ("labor-report.json", report_text),
        ("claim-matrix.json", matrix_text),
        ("triage-input.md", input_text),
    ))


def prepare_codex_pilot_handoff(
    *,
    preflight: dict,
    endpoint_map: dict,
    workspace: Path,
    output: Path,
    report_path: Path,
    matrix_path: Path,
    input_path: Path,
    now: Optional[datetime] = None,
) -> tuple[Path, ...]:
    """Valida GO, identidade e custódia antes de copiar três arquivos privados."""
    _private_directory(workspace, "espaço de origem")
    _private_directory(output, "espaço de saída")
    try:
        go = validate_pilot_preflight(
            preflight=preflight,
            endpoint_map=endpoint_map,
            schema_path=DEFAULT_SCHEMA,
            sanitization_contract_path=DEFAULT_SANITIZATION_CONTRACT,
            map_review_contract_path=DEFAULT_MAP_REVIEW_CONTRACT,
            repository_root=ROOT,
            workspace_path=workspace,
            output_path=output,
            current_branch=_git_value(ROOT, "branch", "--show-current"),
            current_commit=_git_value(ROOT, "rev-parse", "HEAD"),
            working_tree_clean=not _git_value(
                ROOT, "status", "--porcelain", "--untracked-files=all"
            ),
            now=now,
        )
        if go["status"] != "go_controlled_pilot" or (
            "analyze" not in preflight["controls"]["requested_operations"]
        ):
            raise CodexPilotHandoffError("operação de análise não autorizada")
        if "codex" not in preflight["controls"]["model_providers_authorized"]:
            raise CodexPilotHandoffError("processamento pelo Codex não autorizado")
        if not preflight["controls"].get("codex_model_id"):
            raise CodexPilotHandoffError("modelo Codex não registrado")
        return _stage_case_inputs(
            preflight, workspace, output, report_path, matrix_path, input_path
        )
    except (PilotPreflightError, ContractError, TriageInputError, OSError,
            UnicodeError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, CodexPilotHandoffError):
            raise
        raise CodexPilotHandoffError("os insumos do piloto não foram preparados") from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara insumos reais do piloto TRT12 após GO.")
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--endpoint-map", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        paths = prepare_codex_pilot_handoff(
            preflight=_protected_preflight(args.preflight),
            endpoint_map=load_json(args.endpoint_map, "mapa de endpoints"),
            workspace=args.workspace,
            output=args.output,
            report_path=args.report,
            matrix_path=args.matrix,
            input_path=args.input,
        )
    except (ContractError, CodexPilotHandoffError, OSError) as error:
        print(f"[NO-GO] Preparação do piloto Codex: {error}", file=sys.stderr)
        return 2
    print(f"[GO] Três insumos privados preparados em {paths[0].parent}")
    print("O despacho de dados reais ao modelo continua desabilitado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
