#!/usr/bin/env python3
"""Executa os agentes herdados somente na amostra sintética pela Responses API."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from openai_tool_free_transport import generate_tool_free_text
from require_codex_rehearsal import SyntheticRehearsalError, require_synthetic_rehearsal
from run_codex_narrator import ROOT, CodexNarratorError, _run_codex_narrator
from run_codex_triager import CodexTriagerError, _run_codex_triager
from schema_validation import ContractError, load_json
from trt12_handoff_gate import make_handoff_gate


class OpenAISyntheticRehearsalError(ValueError):
    """Indica que o ensaio sintético não pode ser publicado."""


def run_openai_synthetic_rehearsal(
    workspace: Path, model_id: str, api_key: str
) -> tuple[Path, Path, Path, Path]:
    """Produz narrativa, triagem e rotas validadas da fixture versionada."""
    if not isinstance(model_id, str) or not model_id.strip():
        raise OpenAISyntheticRehearsalError("modelo da API não informado")
    if not isinstance(api_key, str) or not api_key.strip():
        raise OpenAISyntheticRehearsalError("chave de API não informada")
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise OpenAISyntheticRehearsalError("espaço do ensaio inválido")
    workspace = workspace.resolve()
    if workspace == ROOT or workspace.is_relative_to(ROOT):
        raise OpenAISyntheticRehearsalError("o ensaio deve ficar fora do repositório")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise OpenAISyntheticRehearsalError("o espaço do ensaio deve ser privado")
    try:
        report_path = workspace / "labor-report.json"
        matrix_path = workspace / "claim-matrix.json"
        if report_path.is_symlink() or matrix_path.is_symlink():
            raise OpenAISyntheticRehearsalError("insumos não podem ser vínculos simbólicos")
        report = load_json(report_path, "relatório sintético")
        matrix = load_json(matrix_path, "matriz sintética")
        require_synthetic_rehearsal(report, matrix)
        case_number = report["case_context"]["case_number"]
        output_names = (
            "report-narrative.md", f"{case_number}-triagem.md",
            "fontes-triagem.json", "issue-route.json",
        )
        if any(
            (workspace / name).exists() or (workspace / name).is_symlink()
            for name in output_names
        ):
            raise OpenAISyntheticRehearsalError("uma saída já existe e não será sobrescrita")
    except (ContractError, SyntheticRehearsalError, OSError, KeyError, TypeError) as error:
        raise OpenAISyntheticRehearsalError("entrada sintética inválida") from error

    def generate(prompt: str) -> str:
        return generate_tool_free_text(prompt, model_id, api_key)

    gate = make_handoff_gate(workspace)
    if not gate(
        {"id": "prepare-triage-input", "gate": "triage-input-custody"},
        ((workspace / "triage-input.md").resolve(),),
    ):
        raise OpenAISyntheticRehearsalError("a entrada reprovou o controle de custódia")
    try:
        narrative = _run_codex_narrator(
            workspace, require_fixture=True, text_generator=generate
        )
        if not gate(
            {"id": "narrate-record", "gate": "report-narrative-coverage"},
            (narrative,),
        ):
            raise OpenAISyntheticRehearsalError("a narrativa reprovou o controle de cobertura")
        triage = _run_codex_triager(
            workspace, require_fixture=True, text_generator=generate
        )
        if not gate({"id": "route-claims", "gate": "route-coverage"}, triage):
            raise OpenAISyntheticRehearsalError("a triagem reprovou o controle de rotas")
    except (CodexNarratorError, CodexTriagerError) as error:
        raise OpenAISyntheticRehearsalError(str(error)) from error
    return narrative, *triage


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensaia relator e triador TRT12 somente com a amostra sintética."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--synthetic-rehearsal", action="store_true")
    args = parser.parse_args()
    if not args.synthetic_rehearsal:
        print("[NO-GO] Informe --synthetic-rehearsal.", file=sys.stderr)
        return 2
    try:
        outputs = run_openai_synthetic_rehearsal(
            args.workspace, args.model, os.environ.get("OPENAI_API_KEY", "")
        )
    except OpenAISyntheticRehearsalError as error:
        print(f"[NO-GO] Ensaio sintético pela API: {error}", file=sys.stderr)
        return 2
    print(f"[OK] Saídas sintéticas validadas em {outputs[0].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
