#!/usr/bin/env python3
"""Validate a shared pipeline contract through a runtime-specific adapter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD_SCRIPTS = ROOT / "scaffold" / "scripts"
sys.path.insert(0, str(SCAFFOLD_SCRIPTS))

from verificar_pipeline import inferir_id, verificar_etapa  # noqa: E402


SUPPORTED_RUNTIMES = ("claude", "codex")
ALLOWED_ADAPTER_FIELDS = {
    "schema_version",
    "runtime",
    "instruction_file",
    "skills_dir",
    "command_dir",
    "dispatch",
    "progress",
    "tool_bindings",
}
FORBIDDEN_ADAPTER_FIELDS = {
    "artifact_schemas",
    "gates",
    "legal_rules",
    "tribunal_profiles",
}


class ContractError(ValueError):
    """Raised when a runtime or pipeline contract is unsafe or malformed."""


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid JSON in {path}: {error.msg}") from error
    if not isinstance(data, dict):
        raise ContractError(f"JSON root must be an object: {path}")
    return data


def validate_adapter(adapter: dict, runtime: str) -> None:
    forbidden = sorted(FORBIDDEN_ADAPTER_FIELDS.intersection(adapter))
    if forbidden:
        raise ContractError(f"forbidden adapter field: {forbidden[0]}")
    unknown = sorted(set(adapter).difference(ALLOWED_ADAPTER_FIELDS))
    if unknown:
        raise ContractError(f"unknown adapter field: {unknown[0]}")
    if adapter.get("schema_version") != 1:
        raise ContractError("adapter schema_version must be 1")
    if adapter.get("runtime") != runtime:
        raise ContractError(f"adapter runtime must be {runtime}")
    for field in ("instruction_file", "skills_dir", "dispatch", "progress", "tool_bindings"):
        if not adapter.get(field):
            raise ContractError(f"missing adapter field: {field}")


def load_stage(manifest: dict) -> tuple[str, tuple]:
    if manifest.get("schema_version") != 1:
        raise ContractError("manifest schema_version must be 1")
    stages = manifest.get("stages")
    if not isinstance(stages, list) or len(stages) != 1:
        raise ContractError("smoke manifest must declare exactly one stage")
    stage = stages[0]
    gate = stage.get("gate", {})
    required = ("id", "artifact_suffix")
    for field in required:
        if not stage.get(field):
            raise ContractError(f"missing stage field: {field}")
    for field in ("start", "end", "contains", "minimum_characters"):
        if field not in gate:
            raise ContractError(f"missing gate field: {field}")
    if not isinstance(gate["contains"], list) or not gate["contains"]:
        raise ContractError("gate contains must be a non-empty list")
    if not isinstance(gate["minimum_characters"], int) or gate["minimum_characters"] < 1:
        raise ContractError("gate minimum_characters must be a positive integer")
    definition = (
        stage["artifact_suffix"],
        gate["start"],
        gate["end"],
        gate["contains"],
        gate["minimum_characters"],
    )
    return stage["id"], definition


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the shared SuperJurista runtime contract.")
    parser.add_argument("--runtime", required=True, choices=SUPPORTED_RUNTIMES)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--id", dest="identifier")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    adapter_path = args.adapter or ROOT / "runtime" / "adapters" / f"{args.runtime}.json"
    try:
        adapter = load_json(adapter_path)
        validate_adapter(adapter, args.runtime)
        manifest = load_json(args.manifest)
        stage_id, stage_definition = load_stage(manifest)
    except ContractError as error:
        print(f"[ERRO] {error}")
        return 2

    if args.validate_only:
        print("[OK] runtime adapter and shared manifest")
        return 0
    if args.workspace is None or not args.workspace.is_dir():
        print("[ERRO] workspace is required and must exist")
        return 2

    identifier = args.identifier or inferir_id(str(args.workspace))
    result = verificar_etapa(
        str(args.workspace),
        identifier,
        stage_id,
        {stage_id: stage_definition},
    )
    if result is None:
        print(f"[AUSENTE] {stage_id}")
        return 1
    if result:
        print(f"[INVALIDA] {stage_id}: " + "; ".join(result))
        return 1
    print(f"[OK] {stage_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
