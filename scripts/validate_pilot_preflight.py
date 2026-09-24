#!/usr/bin/env python3
"""Valida a verificação prévia, com bloqueio por padrão, do piloto TRT12."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from resolve_runtime_pipeline import contract_digest, normalize_manifest
from sanitize_pje_har import load_sanitization_contract
from schema_validation import ContractError, load_json, validate_schema_value
from validate_pje_har_map import MapReviewError, load_review_contract, validate_map


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "runtime" / "operations" / "pilot-preflight.v4.schema.json"
DEFAULT_SANITIZATION_CONTRACT = (
    ROOT / "runtime" / "providers" / "har-sanitization-contract.json"
)
DEFAULT_MAP_REVIEW_CONTRACT = (
    ROOT / "runtime" / "providers" / "har-map-review-contract.json"
)


class PilotPreflightError(ValueError):
    """Indica que o piloto com processo real deve permanecer bloqueado."""


def validate_pilot_preflight(
    *,
    preflight: dict,
    endpoint_map: dict,
    schema_path: Path,
    sanitization_contract_path: Path,
    map_review_contract_path: Path,
    repository_root: Path,
    workspace_path: Path,
    output_path: Path,
    current_branch: str,
    current_commit: str,
    working_tree_clean: bool,
    now: Optional[datetime] = None,
) -> dict:
    """Retorna um registro GO sem segredos somente após todos os controles."""
    try:
        schema = load_json(schema_path, "esquema da verificação prévia do piloto")
        sanitization_contract = load_sanitization_contract(
            sanitization_contract_path
        )
        map_review_contract = load_review_contract(map_review_contract_path)
    except ContractError as error:
        raise PilotPreflightError(str(error)) from error
    issues = validate_schema_value(preflight, schema)
    if issues:
        raise PilotPreflightError("contrato da verificação prévia inválido: " + "; ".join(issues))

    case = preflight["case"]
    if case["access_classification"] == "sealed_authorized":
        raise PilotPreflightError("processos sob sigilo não são permitidos no piloto inicial")
    if case["exceptional_access_required"]:
        raise PilotPreflightError(
            "tratamento de acesso excepcional não é permitido no piloto inicial"
        )

    evidence = preflight["evidence"]
    if current_branch != "development" or evidence["branch"] != current_branch:
        raise PilotPreflightError("a branch da verificação prévia deve ser development")
    if evidence["development_commit"] != current_commit:
        raise PilotPreflightError("o commit da verificação prévia não corresponde à revisão atual")
    if not working_tree_clean:
        raise PilotPreflightError("a verificação prévia exige uma árvore de trabalho Git limpa")
    if evidence["host_readiness_status"] != "ready":
        raise PilotPreflightError("o ambiente de execução não está pronto")
    if evidence["quality_gate_status"] != "passed":
        raise PilotPreflightError("o controle de qualidade não foi aprovado")
    claude = evidence["claude_summary"]
    codex = evidence["codex_summary"]
    if claude != codex:
        raise PilotPreflightError("os resumos de execução do Claude e do Codex divergem")
    manifest_path = schema_path.resolve().parents[1] / "pipelines/trt12-first-instance.json"
    try:
        current_contract = normalize_manifest(load_json(manifest_path, "pipeline atual"))
    except (ContractError, OSError) as error:
        raise PilotPreflightError("não foi possível validar o contrato de execução atual") from error
    expected_count = sum(len(stage["outputs"]) for stage in current_contract["stages"])
    if (
        claude["artifact_count"] != expected_count
        or claude["contract_digest"] != contract_digest(current_contract)
    ):
        raise PilotPreflightError("o resumo de execução não corresponde ao pipeline atual")

    try:
        map_result = validate_map(
            endpoint_map,
            sanitization_contract,
            map_review_contract,
            "TRT12",
            1,
        )
    except MapReviewError as error:
        raise PilotPreflightError(f"mapa de endpoints inválido: {error}") from error
    if evidence["endpoint_map_digest"] != endpoint_map.get("sanitized_digest"):
        raise PilotPreflightError("o resumo criptográfico do mapa de endpoints não corresponde ao mapa revisado")
    if map_result["status"] != "review_ready":
        raise PilotPreflightError(
            "persistem lacunas no mapa de endpoints: " + ", ".join(map_result["gaps"])
        )

    _validate_retention(preflight, now or datetime.now(timezone.utc))
    workspace = _validate_local_directory(
        workspace_path,
        repository_root,
        "área de trabalho",
    )
    output = _validate_local_directory(
        output_path,
        repository_root,
        "saída",
    )
    if workspace == output:
        raise PilotPreflightError("os diretórios de trabalho e saída devem ser diferentes")
    if any(output.iterdir()):
        raise PilotPreflightError("o diretório de saída deve estar vazio antes do piloto")

    return {
        "schema_version": 1,
        "status": "go_controlled_pilot",
        "pilot_id": preflight["pilot_id"],
        "tribunal_code": "TRT12",
        "instance": 1,
        "case_reference_digest": case["reference_digest"],
        "development_commit": current_commit,
        "host_readiness_digest": evidence["host_readiness_digest"],
        "contract_digest": claude["contract_digest"],
        "shared_artifact_digest": claude["shared_artifact_digest"],
        "endpoint_map_digest": evidence["endpoint_map_digest"],
        "unobserved_failure_groups": map_result.get(
            "observed_failure_gaps",
            [],
        ),
        "external_actions_allowed": False,
    }


def _validate_retention(preflight: dict, now: datetime) -> None:
    created = _timestamp(preflight["created_at"], "created_at")
    valid_until = _timestamp(preflight["valid_until"], "valid_until")
    if now.tzinfo is None:
        raise PilotPreflightError("a hora atual deve incluir o fuso horário")
    if created > now:
        raise PilotPreflightError("verificação prévia com criação futura")
    if valid_until <= created or now >= valid_until:
        raise PilotPreflightError("verificação prévia vencida")
    retention = preflight["retention"]
    captured = _timestamp(
        retention["raw_har_captured_at"],
        "captura HAR original",
    )
    review_close = _timestamp(
        retention["planned_review_close_by"],
        "encerramento planejado da revisão",
    )
    deadlines = {
        "captura HAR": (
            _timestamp(retention["raw_har_delete_by"], "exclusão da captura HAR"),
            captured + timedelta(hours=24),
        ),
        "documentos originais": (
            _timestamp(
                retention["raw_documents_delete_by"],
                "exclusão dos documentos originais",
            ),
            review_close + timedelta(days=30),
        ),
        "artefatos derivados": (
            _timestamp(
                retention["derived_artifacts_delete_by"],
                "exclusão dos artefatos derivados",
            ),
            review_close + timedelta(days=90),
        ),
        "resumo de incidente": (
            _timestamp(
                retention["incident_summary_delete_by"],
                "exclusão do resumo de incidente",
            ),
            created + timedelta(days=180),
        ),
    }
    if review_close < created:
        raise PilotPreflightError("o encerramento da revisão não pode anteceder a criação da verificação prévia")
    if captured > created:
        raise PilotPreflightError("a captura HAR não pode ocorrer após a criação da verificação prévia")
    for label, (deadline, maximum) in deadlines.items():
        minimum = captured if label == "captura HAR" else created
        if deadline < minimum:
            raise PilotPreflightError(f"a exclusão de {label} não pode anteceder o período de retenção")
        if deadline > maximum:
            raise PilotPreflightError(f"a retenção de {label} excede o limite aprovado")


def _timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise PilotPreflightError(f"{label} deve ser uma data e hora ISO-8601") from error
    if parsed.tzinfo is None:
        raise PilotPreflightError(f"{label} deve incluir o fuso horário")
    return parsed


def _validate_local_directory(path: Path, repository_root: Path, label: str) -> Path:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        pass
    else:
        raise PilotPreflightError(f"{label} deve permanecer fora do repositório")
    if not resolved.exists() or not resolved.is_dir():
        raise PilotPreflightError(f"o diretório de {label} não existe")
    return resolved


def _git_value(repository_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PilotPreflightError("não foi possível inspecionar a revisão Git atual") from error
    return result.stdout.strip()


def _require_outside_repository(path: Path, repository_root: Path, label: str) -> None:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return
    raise PilotPreflightError(f"{label} deve permanecer fora do repositório")


def _write_json_atomic(path: Path, value: Any) -> None:
    if path.exists():
        raise PilotPreflightError("o resumo da verificação prévia já existe")
    if not path.parent.exists() or not path.parent.is_dir():
        raise PilotPreflightError("o diretório do resumo da verificação prévia não existe")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validar a verificação prévia do piloto controlado de 1º grau do TRT12.",
    )
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--endpoint-map", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--sanitization-contract",
        type=Path,
        default=DEFAULT_SANITIZATION_CONTRACT,
    )
    parser.add_argument(
        "--map-review-contract",
        type=Path,
        default=DEFAULT_MAP_REVIEW_CONTRACT,
    )
    return parser


def main(argv: list[str] = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = args.repository_root.resolve()
    try:
        _require_outside_repository(args.preflight, repository_root, "registro da verificação prévia")
        _require_outside_repository(args.summary, repository_root, "resumo da verificação prévia")
        preflight = load_json(args.preflight, "verificação prévia do piloto")
        endpoint_map = load_json(args.endpoint_map, "mapa de endpoints sanitizado")
        result = validate_pilot_preflight(
            preflight=preflight,
            endpoint_map=endpoint_map,
            schema_path=args.schema,
            sanitization_contract_path=args.sanitization_contract,
            map_review_contract_path=args.map_review_contract,
            repository_root=repository_root,
            workspace_path=args.workspace,
            output_path=args.output,
            current_branch=_git_value(repository_root, "branch", "--show-current"),
            current_commit=_git_value(repository_root, "rev-parse", "HEAD"),
            working_tree_clean=not _git_value(
                repository_root,
                "status",
                "--porcelain",
                "--untracked-files=all",
            ),
        )
        _write_json_atomic(args.summary.resolve(), result)
    except (ContractError, PilotPreflightError, OSError) as error:
        print(f"[NO-GO] verificação prévia do piloto: {error}", file=sys.stderr)
        return 2
    print(
        "[GO] verificação prévia do piloto controlado: "
        f"piloto={result['pilot_id']}; commit={result['development_commit']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
