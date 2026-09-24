#!/usr/bin/env python3
"""Resolve one shared pipeline manifest for Claude Code or Codex."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from verify_runtime_contract import (
    ROOT,
    SUPPORTED_RUNTIMES,
    ContractError,
    load_json,
    validate_adapter,
)


ALLOWED_MANIFEST_FIELDS = {
    "schema_version",
    "pipeline",
    "profile",
    "retry_policy",
    "gates",
    "stages",
}
RUNTIME_SPECIFIC_FIELDS = {
    "adapter",
    "claude",
    "codex",
    "dispatch",
    "progress",
    "runtime",
    "runtime_overrides",
    "tool_bindings",
}
ALLOWED_STAGE_FIELDS = {
    "id",
    "capability",
    "depends_on",
    "condition",
    "outputs",
    "gate",
    "agent",
}
REQUIRED_STAGE_FIELDS = ALLOWED_STAGE_FIELDS - {"agent"}
ALLOWED_GATE_KINDS = {"composite", "contract", "deterministic"}


def reject_runtime_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in RUNTIME_SPECIFIC_FIELDS:
                raise ContractError(f"runtime-specific field is forbidden: {key}")
            reject_runtime_fields(child)
    elif isinstance(value, list):
        for child in value:
            reject_runtime_fields(child)


def validate_retry_policy(policy: object) -> dict:
    if not isinstance(policy, dict):
        raise ContractError("retry_policy must be an object")
    if set(policy) != {"max_attempts", "on_exhausted"}:
        raise ContractError("retry_policy must contain max_attempts and on_exhausted")
    max_attempts = policy["max_attempts"]
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise ContractError("retry_policy max_attempts must be a positive integer")
    if policy["on_exhausted"] != "stop":
        raise ContractError("retry_policy on_exhausted must be stop")
    return {"max_attempts": max_attempts, "on_exhausted": "stop"}


def validate_gates(gates: object) -> dict:
    if not isinstance(gates, dict) or not gates:
        raise ContractError("gates must be a non-empty object")
    normalized = {}
    for gate_id, gate in gates.items():
        if not isinstance(gate_id, str) or not gate_id:
            raise ContractError("gate id must be a non-empty string")
        if not isinstance(gate, dict) or set(gate) != {"kind", "target"}:
            raise ContractError(f"gate {gate_id} must contain kind and target")
        if gate["kind"] not in ALLOWED_GATE_KINDS:
            raise ContractError(f"gate {gate_id} has unsupported kind: {gate['kind']}")
        if not isinstance(gate["target"], str) or not gate["target"]:
            raise ContractError(f"gate {gate_id} target must be a non-empty string")
        normalized[gate_id] = {"kind": gate["kind"], "target": gate["target"]}
    return normalized


def topological_stage_ids(stages: list[dict]) -> list[str]:
    order = [stage["id"] for stage in stages]
    dependencies = {stage["id"]: stage["depends_on"] for stage in stages}
    state = {stage_id: 0 for stage_id in order}
    result = []

    def visit(stage_id: str, trail: list[str]) -> None:
        if state[stage_id] == 1:
            cycle = " -> ".join(trail + [stage_id])
            raise ContractError(f"pipeline dependency cycle: {cycle}")
        if state[stage_id] == 2:
            return
        state[stage_id] = 1
        for dependency in dependencies[stage_id]:
            visit(dependency, trail + [stage_id])
        state[stage_id] = 2
        result.append(stage_id)

    for stage_id in order:
        visit(stage_id, [])
    return result


def validate_agent_path(value: object, stage_id: str) -> tuple[str, str]:
    if not isinstance(value, str) or not value:
        raise ContractError(f"stage {stage_id} agent must be a repository-relative path")
    path = Path(value)
    if (
        path.is_absolute()
        or path.parts[:2] != ("scaffold", "agents")
        or ".." in path.parts
        or path.suffix != ".md"
    ):
        raise ContractError(f"stage {stage_id} agent must be under scaffold/agents")
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to((ROOT / "scaffold" / "agents").resolve()) or not resolved.is_file():
        raise ContractError(f"stage {stage_id} agent file is missing or unsafe: {value}")
    return path.as_posix(), hashlib.sha256(resolved.read_bytes()).hexdigest()


def validate_stages(stages: object, gates: dict, max_attempts: int) -> list[dict]:
    if not isinstance(stages, list) or not stages:
        raise ContractError("stages must be a non-empty list")
    normalized = []
    seen_ids = set()
    seen_outputs = set()
    for stage in stages:
        if not isinstance(stage, dict):
            raise ContractError("each stage must be an object")
        unknown = sorted(set(stage).difference(ALLOWED_STAGE_FIELDS))
        if unknown:
            raise ContractError(f"unknown stage field: {unknown[0]}")
        missing = sorted(REQUIRED_STAGE_FIELDS.difference(stage))
        if missing:
            raise ContractError(f"missing stage field: {missing[0]}")
        stage_id = stage["id"]
        if not isinstance(stage_id, str) or not stage_id:
            raise ContractError("stage id must be a non-empty string")
        if stage_id in seen_ids:
            raise ContractError(f"duplicate stage id: {stage_id}")
        seen_ids.add(stage_id)
        if not isinstance(stage["capability"], str) or not stage["capability"]:
            raise ContractError(f"stage {stage_id} capability must be a non-empty string")
        if not isinstance(stage["depends_on"], list) or not all(
            isinstance(item, str) and item for item in stage["depends_on"]
        ):
            raise ContractError(f"stage {stage_id} depends_on must be a list of stage ids")
        if stage["condition"] not in {"always", "routed"}:
            raise ContractError(f"stage {stage_id} has unsupported condition")
        if not isinstance(stage["outputs"], list) or not stage["outputs"]:
            raise ContractError(f"stage {stage_id} outputs must be a non-empty list")
        for output in stage["outputs"]:
            if not isinstance(output, str) or not output.startswith("{workspace}/"):
                raise ContractError(f"stage {stage_id} output must start with {{workspace}}/")
            if output in seen_outputs:
                raise ContractError(f"duplicate pipeline output: {output}")
            seen_outputs.add(output)
        if stage["gate"] not in gates:
            raise ContractError(f"stage {stage_id} references unknown gate: {stage['gate']}")
        normalized_stage = {
            "id": stage_id,
            "capability": stage["capability"],
            "depends_on": stage["depends_on"],
            "condition": stage["condition"],
            "outputs": stage["outputs"],
            "gate": stage["gate"],
            "max_attempts": max_attempts,
        }
        if "agent" in stage:
            normalized_stage["agent"], normalized_stage["agent_digest"] = validate_agent_path(
                stage["agent"], stage_id
            )
        normalized.append(normalized_stage)

    known = {stage["id"] for stage in normalized}
    for stage in normalized:
        for dependency in stage["depends_on"]:
            if dependency not in known:
                raise ContractError(f"stage {stage['id']} has unknown dependency: {dependency}")
    order = topological_stage_ids(normalized)
    by_id = {stage["id"]: stage for stage in normalized}
    return [by_id[stage_id] for stage_id in order]


def normalize_manifest(manifest: dict) -> dict:
    reject_runtime_fields(manifest)
    unknown = sorted(set(manifest).difference(ALLOWED_MANIFEST_FIELDS))
    if unknown:
        raise ContractError(f"unknown manifest field: {unknown[0]}")
    missing = sorted(ALLOWED_MANIFEST_FIELDS.difference(manifest))
    if missing:
        raise ContractError(f"missing manifest field: {missing[0]}")
    if manifest["schema_version"] != 1:
        raise ContractError("manifest schema_version must be 1")
    for field in ("pipeline", "profile"):
        if not isinstance(manifest[field], str) or not manifest[field]:
            raise ContractError(f"manifest {field} must be a non-empty string")
    retry_policy = validate_retry_policy(manifest["retry_policy"])
    gates = validate_gates(manifest["gates"])
    stages = validate_stages(manifest["stages"], gates, retry_policy["max_attempts"])
    return {
        "schema_version": 1,
        "pipeline": manifest["pipeline"],
        "profile": manifest["profile"],
        "retry_policy": retry_policy,
        "gates": gates,
        "stages": stages,
    }


def contract_digest(contract: dict) -> str:
    canonical = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve a shared SuperJurista pipeline.")
    parser.add_argument("--runtime", required=True, choices=SUPPORTED_RUNTIMES)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--adapter", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    adapter_path = args.adapter or ROOT / "runtime" / "adapters" / f"{args.runtime}.json"
    try:
        adapter = load_json(adapter_path)
        validate_adapter(adapter, args.runtime)
        contract = normalize_manifest(load_json(args.manifest))
    except ContractError as error:
        print(f"[ERRO] {error}", file=sys.stderr)
        return 2

    runtime_adapter = {
        key: adapter[key]
        for key in (
            "instruction_file",
            "skills_dir",
            "command_dir",
            "dispatch",
            "progress",
            "tool_bindings",
        )
    }
    plan = {
        "schema_version": 1,
        "runtime": args.runtime,
        "runtime_adapter": runtime_adapter,
        "contract_digest": contract_digest(contract),
        "contract": contract,
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
