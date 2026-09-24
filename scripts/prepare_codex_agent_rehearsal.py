#!/usr/bin/env python3
"""Prepara somente os insumos protegidos do ensaio sintético dos agentes Codex."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path

from build_superjurista_triage_input import (
    TriageInputError,
    build_triage_input,
    write_triage_input,
)
from require_codex_rehearsal import FIXTURE
from schema_validation import ContractError, load_json


ROOT = Path(__file__).resolve().parents[1]


class CodexRehearsalError(ValueError):
    """Indica que o espaço não pode receber o ensaio sintético."""


def prepare_codex_agent_rehearsal(workspace: Path) -> tuple[Path, Path, Path]:
    """Cria entrada, relatório e matriz em diretório externo vazio e privado."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise CodexRehearsalError("o espaço de trabalho deve ser um diretório real")
    workspace = workspace.resolve()
    if workspace == ROOT or workspace.is_relative_to(ROOT):
        raise CodexRehearsalError("o espaço de trabalho deve ficar fora do repositório")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise CodexRehearsalError("o diretório do ensaio deve ser privado")
    if any(workspace.iterdir()):
        raise CodexRehearsalError("o diretório do ensaio deve estar vazio")
    try:
        fixture = load_json(FIXTURE, "amostra sintética do TRT12")
        report = fixture["artifacts"]["labor-report.json"]
        matrix = fixture["artifacts"]["claim-matrix.json"]
        triage_input = build_triage_input(report, matrix)
        contents = (
            ("labor-report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
            ("claim-matrix.json", json.dumps(matrix, ensure_ascii=False, indent=2) + "\n"),
            ("triage-input.md", triage_input),
        )
        created = []
        try:
            for name, content in contents:
                created.append(write_triage_input(content, workspace / name))
        except (TriageInputError, OSError):
            for path in reversed(created):
                path.unlink()
            raise
        return tuple(created)
    except (ContractError, TriageInputError, OSError, KeyError, TypeError) as error:
        raise CodexRehearsalError("não foi possível preparar a amostra sintética") from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara o ensaio sintético dos agentes Codex.")
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        paths = prepare_codex_agent_rehearsal(args.workspace)
    except CodexRehearsalError as error:
        print(f"[ERRO] Ensaio Codex: {error}", file=sys.stderr)
        return 2
    print(f"[OK] Insumos sintéticos protegidos: {paths[0].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
