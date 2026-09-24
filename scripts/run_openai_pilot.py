#!/usr/bin/env python3
"""Despacha o piloto TRT12 pela API somente após dois controles independentes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import prepare_codex_pilot_handoff as handoff
from openai_tool_free_transport import generate_tool_free_text
from run_codex_narrator import CodexNarratorError, _run_codex_narrator
from run_codex_triager import CodexTriagerError, _run_codex_triager
from schema_validation import ContractError, load_json, validate_schema_value
from trt12_handoff_gate import make_handoff_gate
from validate_openai_api_authorization import (
    OpenAIAPIAuthorizationError,
    _protected_record,
    validate_openai_api_authorization,
)
from validate_pilot_preflight import (
    DEFAULT_MAP_REVIEW_CONTRACT,
    DEFAULT_SANITIZATION_CONTRACT,
    DEFAULT_SCHEMA,
    PilotPreflightError,
    validate_pilot_preflight,
)


ROOT = handoff.ROOT
RESULT_SCHEMA = ROOT / "runtime/operations/openai-api-pilot-result.v1.schema.json"
RESULT_NAME = "pilot-run-summary.json"
REAL_CASE_DISPATCH_ENABLED = False


class OpenAIPilotError(ValueError):
    """Indica que o piloto pela API foi recusado ou interrompido."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise OpenAIPilotError("insumo protegido ausente ou alterado")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authorization_digest(authorization: dict) -> str:
    content = json.dumps(
        authorization, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _still_authorized(
    preflight: dict, authorization: dict, originals: dict[Path, str]
) -> datetime:
    checked_at = _now()
    validate_openai_api_authorization(authorization, preflight, now=checked_at)
    if (
        handoff._git_value(ROOT, "branch", "--show-current") != "development"
        or handoff._git_value(ROOT, "rev-parse", "HEAD")
        != preflight["evidence"]["development_commit"]
        or handoff._git_value(ROOT, "status", "--porcelain", "--untracked-files=all")
    ):
        raise OpenAIPilotError("o checkout mudou durante o piloto")
    if any(_digest(path) != digest for path, digest in originals.items()):
        raise OpenAIPilotError("um insumo protegido mudou durante o piloto")
    return checked_at


def _publish_result(
    output: Path,
    preflight: dict,
    authorization: dict,
    prepared: tuple[Path, ...],
    produced: tuple[Path, ...],
    finished_at: datetime,
) -> None:
    summary = {
        "schema_version": 1,
        "status": "pending_legal_review",
        "pilot_id": preflight["pilot_id"],
        "case_reference_digest": preflight["case"]["reference_digest"],
        "authorization_scope_digest": preflight["case"]["authorization_scope_digest"],
        "api_authorization_digest": _authorization_digest(authorization),
        "provider_terms_digest": authorization["provider_terms_digest"],
        "development_commit": preflight["evidence"]["development_commit"],
        "endpoint_map_digest": preflight["evidence"]["endpoint_map_digest"],
        "model_provider": "openai_api",
        "model_id": authorization["model_id"],
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
    if validate_schema_value(summary, load_json(RESULT_SCHEMA, "resumo do piloto pela API")):
        raise OpenAIPilotError("o resumo do piloto pela API não respeita o contrato")
    destination = output / RESULT_NAME
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    except (OSError, UnicodeError):
        destination.unlink(missing_ok=True)
        raise


def run_openai_pilot(
    *,
    preflight: dict,
    authorization: dict,
    endpoint_map: dict,
    workspace: Path,
    output: Path,
    report_path: Path,
    matrix_path: Path,
    input_path: Path,
    api_key: str,
) -> tuple[Path, Path, Path, Path]:
    """Reusa relator e triador após GO do processo e autorização específica da API."""
    if not REAL_CASE_DISPATCH_ENABLED:
        raise OpenAIPilotError("o despacho real pela API está desabilitado nesta versão")
    if not isinstance(api_key, str) or not api_key.strip():
        raise OpenAIPilotError("chave da API ausente")
    try:
        handoff._private_directory(workspace, "espaço de origem")
        handoff._private_directory(output, "espaço de saída")
        checked_at = _now()
        linked = validate_openai_api_authorization(
            authorization, preflight, now=checked_at
        )
        go = validate_pilot_preflight(
            preflight=preflight,
            endpoint_map=endpoint_map,
            schema_path=DEFAULT_SCHEMA,
            sanitization_contract_path=DEFAULT_SANITIZATION_CONTRACT,
            map_review_contract_path=DEFAULT_MAP_REVIEW_CONTRACT,
            repository_root=ROOT,
            workspace_path=workspace,
            output_path=output,
            current_branch=handoff._git_value(ROOT, "branch", "--show-current"),
            current_commit=handoff._git_value(ROOT, "rev-parse", "HEAD"),
            working_tree_clean=not handoff._git_value(
                ROOT, "status", "--porcelain", "--untracked-files=all"
            ),
            now=checked_at,
        )
        if go["status"] != "go_controlled_pilot" or (
            linked["status"] != "authorization_linked_not_pilot_go"
        ):
            raise OpenAIPilotError("o processo não passou nos dois controles")
        originals = {
            path: _digest(path) for path in (report_path, matrix_path, input_path)
        }
        prepared = handoff._stage_case_inputs(
            preflight, workspace, output, report_path, matrix_path, input_path
        )
        originals.update({path: _digest(path) for path in prepared})
        gate = make_handoff_gate(output)
        if not gate(
            {"id": "prepare-triage-input", "gate": "triage-input-custody"},
            (prepared[2].resolve(),),
        ):
            raise OpenAIPilotError("a entrada reprovou o controle de custódia")

        def generate(prompt: str) -> str:
            return generate_tool_free_text(prompt, authorization["model_id"], api_key)

        _still_authorized(preflight, authorization, originals)
        narrative = _run_codex_narrator(
            output, require_fixture=False, text_generator=generate
        )
        if not gate(
            {"id": "narrate-record", "gate": "report-narrative-coverage"},
            (narrative,),
        ):
            raise OpenAIPilotError("a narrativa reprovou o controle de cobertura")
        originals[narrative] = _digest(narrative)

        _still_authorized(preflight, authorization, originals)
        triage = _run_codex_triager(
            output, require_fixture=False, text_generator=generate
        )
        finished_at = _still_authorized(preflight, authorization, originals)
        if not gate({"id": "route-claims", "gate": "route-coverage"}, triage):
            raise OpenAIPilotError("a triagem reprovou o controle de rotas")
        _publish_result(
            output, preflight, authorization, prepared, (narrative, *triage), finished_at
        )
        return narrative, *triage
    except (
        handoff.CodexPilotHandoffError, OpenAIAPIAuthorizationError,
        PilotPreflightError, CodexNarratorError, CodexTriagerError,
        ContractError, OSError, UnicodeError, KeyError, TypeError, ValueError,
    ) as error:
        if isinstance(error, OpenAIPilotError):
            raise
        raise OpenAIPilotError(
            "o piloto pela API foi interrompido; revisar os arquivos protegidos"
        ) from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa o piloto TRT12 pela Responses API somente após os dois controles."
    )
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--api-authorization", required=True, type=Path)
    parser.add_argument("--endpoint-map", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        run_openai_pilot(
            preflight=_protected_record(args.preflight),
            authorization=_protected_record(args.api_authorization),
            endpoint_map=load_json(args.endpoint_map, "mapa de endpoints"),
            workspace=args.workspace,
            output=args.output,
            report_path=args.report,
            matrix_path=args.matrix,
            input_path=args.input,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
        )
    except (OpenAIPilotError, OpenAIAPIAuthorizationError, ContractError, OSError) as error:
        print(f"[NO-GO] Piloto pela API: {error}", file=sys.stderr)
        return 2
    print("[OK] Narrativa e triagem protegidas passaram nos três controles técnicos.")
    print("Revisão jurídica humana obrigatória; nenhum ato judicial externo foi realizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
