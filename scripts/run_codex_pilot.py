#!/usr/bin/env python3
"""Ensaios sintéticos dos agentes Codex sob controles do piloto TRT12."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import prepare_codex_pilot_handoff as handoff
from require_codex_rehearsal import SyntheticRehearsalError, require_synthetic_rehearsal
from run_codex_narrator import CodexNarratorError, _run_codex_narrator_for_pilot
from run_codex_triager import CodexTriagerError, _run_codex_triager_for_pilot
from schema_validation import ContractError, load_json, validate_schema_value
from trt12_handoff_gate import make_handoff_gate


class CodexPilotError(ValueError):
    """Indica que uma etapa do piloto real deve permanecer interrompida."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


RESULT_SCHEMA = handoff.ROOT / "runtime/operations/codex-pilot-result.v1.schema.json"
RESULT_NAME = "pilot-run-summary.json"


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CodexPilotError("insumo preparado ausente ou alterado")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _still_authorized(preflight: dict, originals: dict[Path, str]) -> datetime:
    valid_until = datetime.fromisoformat(preflight["valid_until"].replace("Z", "+00:00"))
    checked_at = _now()
    if checked_at >= valid_until:
        raise CodexPilotError("a autorização venceu antes da triagem")
    if (
        handoff._git_value(handoff.ROOT, "branch", "--show-current") != "development"
        or handoff._git_value(handoff.ROOT, "rev-parse", "HEAD")
        != preflight["evidence"]["development_commit"]
        or handoff._git_value(
            handoff.ROOT, "status", "--porcelain", "--untracked-files=all"
        )
    ):
        raise CodexPilotError("o checkout mudou durante o piloto")
    for path, expected in originals.items():
        if _digest(path) != expected:
            raise CodexPilotError("um insumo preparado mudou durante o piloto")
    return checked_at


def _publish_result(
    output: Path,
    preflight: dict,
    model_id: str,
    prepared: tuple[Path, ...],
    produced: tuple[Path, ...],
    finished_at: datetime,
) -> None:
    record = {
        "schema_version": 1,
        "status": "pending_legal_review",
        "pilot_id": preflight["pilot_id"],
        "case_reference_digest": preflight["case"]["reference_digest"],
        "development_commit": preflight["evidence"]["development_commit"],
        "endpoint_map_digest": preflight["evidence"]["endpoint_map_digest"],
        "model_provider": "codex",
        "model_id": model_id,
        "passed_handoff_gates": 3,
        "input_artifact_sha256": dict(zip(
            ("report", "matrix", "triage_input"),
            (_digest(path) for path in prepared),
        )),
        "generated_artifact_sha256": dict(zip(
            ("narrative", "triage", "sources", "routes"),
            (_digest(path) for path in produced),
        )),
        "finished_at": finished_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "external_actions_allowed": False,
    }
    if validate_schema_value(record, load_json(RESULT_SCHEMA, "esquema do resultado")):
        raise CodexPilotError("o resumo do piloto não respeita o contrato")
    destination = output / RESULT_NAME
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    except (OSError, UnicodeError):
        destination.unlink(missing_ok=True)
        raise


def run_codex_pilot(
    *,
    preflight: dict,
    endpoint_map: dict,
    workspace: Path,
    output: Path,
    report_path: Path,
    matrix_path: Path,
    input_path: Path,
) -> tuple[Path, Path, Path, Path]:
    """Ensaios sintéticos: prepara insumos e aplica os controles herdados."""
    try:
        handoff._private_directory(workspace, "espaço de origem")
        report = json.loads(handoff._source(report_path, workspace, "relatório"))
        matrix = json.loads(handoff._source(matrix_path, workspace, "matriz"))
        require_synthetic_rehearsal(report, matrix)
        prepared = handoff.prepare_codex_pilot_handoff(
            preflight=preflight,
            endpoint_map=endpoint_map,
            workspace=workspace,
            output=output,
            report_path=report_path,
            matrix_path=matrix_path,
            input_path=input_path,
            now=_now(),
        )
        originals = {path: _digest(path) for path in prepared}
        gate = make_handoff_gate(output)
        if not gate(
            {"id": "prepare-triage-input", "gate": "triage-input-custody"},
            (prepared[2].resolve(),),
        ):
            raise CodexPilotError("a entrada preparada reprovou o controle de custódia")

        _still_authorized(preflight, originals)
        model_id = preflight["controls"]["codex_model_id"]
        narrative = _run_codex_narrator_for_pilot(output, model_id)
        if not gate(
            {"id": "narrate-record", "gate": "report-narrative-coverage"},
            (narrative,),
        ):
            raise CodexPilotError("a narrativa reprovou o controle de cobertura")

        _still_authorized(preflight, originals)
        triage = _run_codex_triager_for_pilot(output, model_id)
        finished_at = _still_authorized(preflight, originals)
        if not gate(
            {"id": "route-claims", "gate": "route-coverage"}, triage
        ):
            raise CodexPilotError("a triagem reprovou o controle de rotas")
        _publish_result(output, preflight, model_id, prepared, (narrative, *triage), finished_at)
        return (narrative, *triage)
    except SyntheticRehearsalError as error:
        raise CodexPilotError(
            "o despacho pelo Codex CLI permanece limitado à amostra sintética"
        ) from error
    except (handoff.CodexPilotHandoffError, CodexNarratorError,
            CodexTriagerError, ContractError, OSError, TypeError, ValueError) as error:
        if isinstance(error, CodexPilotError):
            raise
        raise CodexPilotError("o piloto Codex foi interrompido; revisar saídas protegidas") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa relator e triador Codex somente na amostra sintética, sob GO vigente."
    )
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--endpoint-map", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        run_codex_pilot(
            preflight=handoff._protected_preflight(args.preflight),
            endpoint_map=load_json(args.endpoint_map, "mapa de endpoints"),
            workspace=args.workspace,
            output=args.output,
            report_path=args.report,
            matrix_path=args.matrix,
            input_path=args.input,
        )
    except (CodexPilotError, handoff.CodexPilotHandoffError, ContractError, OSError) as error:
        print(f"[NO-GO] Piloto Codex: {error}", file=sys.stderr)
        return 2
    print("[OK] Narrativa e triagem protegidas passaram nos três controles de transferência.")
    print("Revisão jurídica humana obrigatória; nenhum ato judicial externo foi realizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
