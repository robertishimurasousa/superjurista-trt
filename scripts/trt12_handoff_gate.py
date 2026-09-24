#!/usr/bin/env python3
"""Verifica checkpoints de entrada, narrativa e triagem do TRT12."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from build_superjurista_triage_input import TriageInputError, build_triage_input
from import_superjurista_triage import TriageImportError, import_triage
from schema_validation import ContractError, load_json
from validate_superjurista_report import validate_report_narrative


def make_handoff_gate(workspace: Path) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Cria o controle de conteúdo para as três etapas, recusando outras."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()

    def source_path(name: str) -> Path:
        declared = root / name
        if declared.is_symlink():
            raise ValueError("o insumo não pode ser um vínculo simbólico")
        path = declared.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("o insumo não pertence ao espaço de trabalho")
        return path

    def read_text(name: str) -> str:
        return source_path(name).read_text(encoding="utf-8")

    def read_json(name: str, label: str) -> dict:
        return load_json(source_path(name), label)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        stage_id = stage.get("id")
        if stage_id == "route-claims":
            if stage.get("gate") != "route-coverage":
                return False
            try:
                report = read_json("labor-report.json", "relatório trabalhista")
                case_number = report["case_context"]["case_number"]
                expected_outputs = (
                    (root / f"{case_number}-triagem.md").resolve(),
                    (root / "fontes-triagem.json").resolve(),
                    (root / "issue-route.json").resolve(),
                )
                if outputs != expected_outputs:
                    return False
                matrix = read_json("claim-matrix.json", "matriz de pedidos")
                input_text = read_text("triage-input.md")
                if input_text != build_triage_input(report, matrix):
                    return False
                imported = import_triage(
                    read_text(f"{case_number}-triagem.md"),
                    matrix,
                    read_json("fontes-triagem.json", "fontes da triagem"),
                    case_number,
                    hashlib.sha256(input_text.encode("utf-8")).hexdigest(),
                )
                return imported == read_json("issue-route.json", "rotas por pedido")
            except (
                ContractError, TriageInputError, TriageImportError, ValueError,
                OSError, UnicodeError, KeyError, TypeError,
            ):
                return False
        expected = {
            "prepare-triage-input": ("triage-input-custody", "triage-input.md"),
            "narrate-record": ("report-narrative-coverage", "report-narrative.md"),
        }.get(stage_id)
        if expected is None or stage.get("gate") != expected[0]:
            return False
        if (root / expected[1]).is_symlink():
            return False
        if outputs != ((root / expected[1]).resolve(),):
            return False
        try:
            report = read_json("labor-report.json", "relatório trabalhista")
            matrix = read_json("claim-matrix.json", "matriz de pedidos")
            input_text = read_text("triage-input.md")
            if stage_id == "prepare-triage-input":
                return input_text == build_triage_input(report, matrix)
            validate_report_narrative(
                report,
                matrix,
                input_text,
                read_text("report-narrative.md"),
            )
            return True
        except (ContractError, TriageInputError, ValueError, OSError, UnicodeError):
            return False

    return validate
