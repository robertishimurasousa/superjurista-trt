#!/usr/bin/env python3
"""Runtime-neutral, fail-closed resume state for the TRT12 pipeline graph."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable

from resolve_runtime_pipeline import contract_digest


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SUPPORTED_RUNTIMES = {"claude", "codex"}


class ResumeContractError(ValueError):
    """Raised when resume evidence cannot safely authorize stage reuse."""


GateValidator = Callable[[dict, tuple[Path, ...]], bool]


def new_execution_state(plan: dict, source_fingerprint: str) -> dict:
    """Create an empty runtime-neutral checkpoint for one resolved contract."""
    _validate_plan(plan)
    _validate_fingerprint(source_fingerprint, "source_fingerprint")
    return {
        "schema_version": 1,
        "pipeline": plan["contract"]["pipeline"],
        "contract_digest": plan["contract_digest"],
        "source_fingerprint": source_fingerprint,
        "stages": [],
    }


def record_stage_acceptance(
    plan: dict,
    *,
    workspace: Path,
    state: dict,
    stage_id: str,
    source_fingerprint: str,
    context: dict[str, str],
    gate_validator: GateValidator,
    attempt: int,
) -> dict:
    """Record one accepted stage only after dependencies, outputs, and gate pass."""
    _validate_plan(plan)
    _validate_state(state)
    _validate_fingerprint(source_fingerprint, "source_fingerprint")
    workspace = _validate_workspace(workspace)
    if state["contract_digest"] != plan["contract_digest"]:
        raise ResumeContractError("execution state uses a different pipeline contract")
    if state["pipeline"] != plan["contract"]["pipeline"]:
        raise ResumeContractError("execution state uses a different pipeline")
    if state["source_fingerprint"] != source_fingerprint:
        raise ResumeContractError("execution state uses a different source fingerprint")
    stages = _stages_by_id(plan)
    stage = stages.get(stage_id)
    if stage is None:
        raise ResumeContractError(f"unknown stage: {stage_id}")
    if (
        isinstance(attempt, bool)
        or not isinstance(attempt, int)
        or not 1 <= attempt <= stage["max_attempts"]
    ):
        raise ResumeContractError(
            f"attempt must be between 1 and {stage['max_attempts']} for {stage_id}"
        )

    reusable = set()
    state_records = _state_records(state)
    for candidate in plan["contract"]["stages"]:
        if candidate["id"] == stage_id:
            break
        reason = _reuse_failure(
            plan,
            candidate,
            workspace,
            state,
            state_records,
            reusable,
            source_fingerprint,
            context,
            gate_validator,
        )
        if reason is None:
            reusable.add(candidate["id"])
    for dependency in stage["depends_on"]:
        if dependency not in reusable:
            raise ResumeContractError(
                f"dependency {dependency} is not currently reusable"
            )

    outputs = _resolve_outputs(stage, workspace, context)
    fingerprints = _fingerprint_outputs(outputs, workspace)
    passed = gate_validator(stage, outputs)
    if not isinstance(passed, bool):
        raise ResumeContractError("content gate validator must return a boolean")
    if not passed:
        raise ResumeContractError(f"content gate failed for stage {stage_id}")
    dependency_digests = {
        dependency: state_records[dependency]["output_digest"]
        for dependency in stage["depends_on"]
    }
    record = {
        "id": stage_id,
        "status": "accepted",
        "attempt": attempt,
        "input_fingerprint": _input_fingerprint(
            plan["contract_digest"],
            source_fingerprint,
            dependency_digests,
        ),
        "output_digest": _output_digest(fingerprints),
        "output_fingerprints": fingerprints,
        "gate": stage["gate"],
        "gate_contract_digest": plan["contract_digest"],
    }
    updated = copy.deepcopy(state)
    by_id = _state_records(updated)
    by_id[stage_id] = record
    order = [item["id"] for item in plan["contract"]["stages"]]
    updated["stages"] = [by_id[item] for item in order if item in by_id]
    _validate_state(updated)
    return updated


def plan_resume(
    plan: dict,
    *,
    workspace: Path,
    state: dict,
    source_fingerprint: str,
    context: dict[str, str],
    gate_validator: GateValidator,
) -> dict:
    """Revalidate every checkpoint and return the runtime-specific next dispatch."""
    _validate_plan(plan)
    _validate_state(state)
    _validate_fingerprint(source_fingerprint, "source_fingerprint")
    workspace = _validate_workspace(workspace)
    records = _state_records(state)
    reusable = set()
    reused = []
    pending = []
    stale_reasons = {}
    for stage in plan["contract"]["stages"]:
        reason = _reuse_failure(
            plan,
            stage,
            workspace,
            state,
            records,
            reusable,
            source_fingerprint,
            context,
            gate_validator,
        )
        if reason is None:
            reusable.add(stage["id"])
            reused.append(stage["id"])
        else:
            pending.append(stage["id"])
            stale_reasons[stage["id"]] = reason
    return {
        "schema_version": 1,
        "runtime": plan["runtime"],
        "dispatch": plan["runtime_adapter"]["dispatch"],
        "contract_digest": plan["contract_digest"],
        "reused_stages": reused,
        "pending_stages": pending,
        "stale_reasons": stale_reasons,
        "next_stage": pending[0] if pending else None,
    }


def save_execution_state(path: Path, state: dict) -> None:
    """Atomically persist a validated execution checkpoint."""
    _validate_state(state)
    if not isinstance(path, Path):
        raise ResumeContractError("state path must be a Path")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def _reuse_failure(
    plan: dict,
    stage: dict,
    workspace: Path,
    state: dict,
    records: dict[str, dict],
    reusable: set[str],
    source_fingerprint: str,
    context: dict[str, str],
    gate_validator: GateValidator,
) -> str | None:
    if state["contract_digest"] != plan["contract_digest"]:
        return "pipeline contract changed"
    if state["pipeline"] != plan["contract"]["pipeline"]:
        return "pipeline identity changed"
    if state["source_fingerprint"] != source_fingerprint:
        return "source fingerprint changed"
    for dependency in stage["depends_on"]:
        if dependency not in reusable:
            return f"dependency {dependency} is not reusable"
    record = records.get(stage["id"])
    if record is None:
        return "stage has no accepted checkpoint"
    if record["gate"] != stage["gate"]:
        return "stage gate changed"
    if record["gate_contract_digest"] != plan["contract_digest"]:
        return "gate contract changed"
    dependency_digests = {
        dependency: records[dependency]["output_digest"]
        for dependency in stage["depends_on"]
    }
    expected_input = _input_fingerprint(
        plan["contract_digest"],
        source_fingerprint,
        dependency_digests,
    )
    if record["input_fingerprint"] != expected_input:
        return "dependency freshness changed"
    try:
        outputs = _resolve_outputs(stage, workspace, context)
        fingerprints = _fingerprint_outputs(outputs, workspace)
    except ResumeContractError as error:
        return str(error)
    if record["output_fingerprints"] != fingerprints:
        return "output fingerprint changed"
    if record["output_digest"] != _output_digest(fingerprints):
        return "output aggregate fingerprint changed"
    passed = gate_validator(stage, outputs)
    if not isinstance(passed, bool):
        raise ResumeContractError("content gate validator must return a boolean")
    if not passed:
        return "current content gate failed"
    return None


def _validate_plan(plan: object) -> None:
    if not isinstance(plan, dict):
        raise ResumeContractError("resolved plan must be an object")
    required = {
        "schema_version",
        "runtime",
        "runtime_adapter",
        "contract_digest",
        "contract",
    }
    if not required.issubset(plan):
        raise ResumeContractError("resolved plan is incomplete")
    if plan["schema_version"] != 1 or plan["runtime"] not in SUPPORTED_RUNTIMES:
        raise ResumeContractError("resolved plan identity is unsupported")
    if not isinstance(plan["runtime_adapter"], dict) or not isinstance(
        plan["runtime_adapter"].get("dispatch"), str
    ):
        raise ResumeContractError("resolved plan dispatch is missing")
    _validate_fingerprint(plan["contract_digest"], "contract_digest")
    if not isinstance(plan["contract"], dict):
        raise ResumeContractError("resolved plan contract is invalid")
    if contract_digest(plan["contract"]) != plan["contract_digest"]:
        raise ResumeContractError("resolved plan contract digest does not match")
    stages = plan["contract"].get("stages")
    if not isinstance(stages, list) or not stages:
        raise ResumeContractError("resolved plan stages are missing")


def _validate_state(state: object) -> None:
    if not isinstance(state, dict):
        raise ResumeContractError("execution state must be an object")
    if set(state) != {
        "schema_version",
        "pipeline",
        "contract_digest",
        "source_fingerprint",
        "stages",
    }:
        raise ResumeContractError("execution state fields are invalid")
    if state["schema_version"] != 1:
        raise ResumeContractError("execution state schema_version must be 1")
    if not isinstance(state["pipeline"], str) or not state["pipeline"]:
        raise ResumeContractError("execution state pipeline is invalid")
    _validate_fingerprint(state["contract_digest"], "contract_digest")
    _validate_fingerprint(state["source_fingerprint"], "source_fingerprint")
    if not isinstance(state["stages"], list):
        raise ResumeContractError("execution state stages must be a list")
    seen = set()
    for record in state["stages"]:
        _validate_stage_record(record)
        if record["id"] in seen:
            raise ResumeContractError("execution state repeats a stage")
        seen.add(record["id"])


def _validate_stage_record(record: object) -> None:
    required = {
        "id",
        "status",
        "attempt",
        "input_fingerprint",
        "output_digest",
        "output_fingerprints",
        "gate",
        "gate_contract_digest",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise ResumeContractError("execution stage checkpoint fields are invalid")
    if not isinstance(record["id"], str) or not record["id"]:
        raise ResumeContractError("execution stage id is invalid")
    if record["status"] != "accepted":
        raise ResumeContractError("execution stage status must be accepted")
    if (
        isinstance(record["attempt"], bool)
        or not isinstance(record["attempt"], int)
        or record["attempt"] < 1
    ):
        raise ResumeContractError("execution stage attempt is invalid")
    for field in ("input_fingerprint", "output_digest", "gate_contract_digest"):
        _validate_fingerprint(record[field], field)
    if not isinstance(record["gate"], str) or not record["gate"]:
        raise ResumeContractError("execution stage gate is invalid")
    if not isinstance(record["output_fingerprints"], list) or not record[
        "output_fingerprints"
    ]:
        raise ResumeContractError("execution stage output_fingerprints are invalid")
    paths = set()
    for item in record["output_fingerprints"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ResumeContractError("output fingerprint fields are invalid")
        if not isinstance(item["path"], str) or not item["path"]:
            raise ResumeContractError("output fingerprint path is invalid")
        _validate_fingerprint(item["sha256"], "output sha256")
        if item["path"] in paths:
            raise ResumeContractError("output fingerprint path is duplicated")
        paths.add(item["path"])


def _validate_fingerprint(value: object, label: str) -> None:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ResumeContractError(f"{label} must be a lowercase SHA-256 digest")


def _validate_workspace(workspace: object) -> Path:
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ResumeContractError("workspace must be an existing directory Path")
    return workspace.resolve()


def _stages_by_id(plan: dict) -> dict[str, dict]:
    return {stage["id"]: stage for stage in plan["contract"]["stages"]}


def _state_records(state: dict) -> dict[str, dict]:
    return {record["id"]: record for record in state["stages"]}


def _resolve_outputs(
    stage: dict,
    workspace: Path,
    context: dict[str, str],
) -> tuple[Path, ...]:
    if not isinstance(context, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in context.items()
    ):
        raise ResumeContractError("output context must contain string values")
    values = {"workspace": str(workspace), **context}
    outputs = []
    for template in stage["outputs"]:
        try:
            rendered = template.format(**values)
        except KeyError as error:
            raise ResumeContractError(
                f"output context is missing placeholder {error.args[0]}"
            ) from error
        path = Path(rendered).resolve()
        try:
            path.relative_to(workspace)
        except ValueError as error:
            raise ResumeContractError("stage output resolves outside the workspace") from error
        outputs.append(path)
    return tuple(outputs)


def _fingerprint_outputs(
    outputs: tuple[Path, ...],
    workspace: Path,
) -> list[dict[str, str]]:
    fingerprints = []
    for path in outputs:
        if not path.is_file():
            raise ResumeContractError(
                f"stage output is missing: {path.relative_to(workspace)}"
            )
        fingerprints.append(
            {
                "path": path.relative_to(workspace).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return fingerprints


def _input_fingerprint(
    pipeline_digest: str,
    source_fingerprint: str,
    dependency_digests: dict[str, str],
) -> str:
    value = {
        "contract_digest": pipeline_digest,
        "source_fingerprint": source_fingerprint,
        "dependencies": dependency_digests,
    }
    return _canonical_digest(value)


def _output_digest(fingerprints: list[dict[str, str]]) -> str:
    return _canonical_digest(fingerprints)


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
