#!/usr/bin/env python3
"""Run the sanitized first-instance acceptance fixture through shared gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from evaluate_final_gate import evaluate_final_gate, require_final_acceptance
from resolve_runtime_pipeline import contract_digest, normalize_manifest
from validate_artifact_contracts import load_catalog, validate_document
from validate_decision_congruence import validate_decision_congruence
from verify_runtime_contract import (
    SUPPORTED_RUNTIMES,
    ContractError,
    load_json,
    validate_adapter,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "runtime" / "pipelines" / "trt12-first-instance.json"
CATALOG = ROOT / "runtime" / "contracts" / "catalog.json"
ARTIFACT_CONTRACTS = {
    "case-context.json": "case-context",
    "claim-matrix.json": "claim-matrix",
    "evidence-matrix.json": "evidence-matrix",
    "issue-route.json": "issue-route",
    "precedent-corpus.json": "precedent-corpus",
    "claim-analysis.json": "claim-analysis",
    "disposition-matrix.json": "disposition-matrix",
    "document-classification.json": "document-classification",
    "procedural-timeline.json": "procedural-timeline",
    "labor-report.json": "labor-report",
}
FIXTURE_ARTIFACTS = {
    "case-context.json",
    "document-index.json",
    "source-manifest.json",
    "document-classification.json",
    "procedural-timeline.json",
    "labor-report.json",
    "claim-matrix.json",
    "evidence-matrix.json",
    "issue-route.json",
    "precedent-corpus.json",
    "evidence-review.json",
    "calculation-review.json",
    "claim-analysis.json",
    "disposition-matrix.json",
    "judgment-draft.md",
    "review-report.json",
}


class SyntheticPipelineError(ValueError):
    """Raised when the acceptance fixture or clean execution is invalid."""


def run_synthetic_pipeline(runtime: str, fixture_path: Path, workspace: Path) -> dict:
    """Validate and materialize one complete, local-only acceptance rehearsal."""
    _require_clean_workspace(workspace)
    fixture = _load_fixture(fixture_path)
    plan = _resolve_plan(runtime)
    artifacts = fixture["artifacts"]
    _validate_contract_artifacts(artifacts)

    case_number = fixture["case_number"]
    if artifacts["case-context.json"]["case_number"] != case_number:
        raise SyntheticPipelineError("fixture case number does not match case context")
    claim_ids = tuple(
        item["claim_id"] for item in artifacts["claim-matrix.json"]["claims"]
    )
    draft = artifacts["judgment-draft.md"]
    congruence = validate_decision_congruence(
        claim_ids,
        artifacts["claim-analysis.json"],
        artifacts["disposition-matrix.json"],
        draft,
    )
    global_gate = evaluate_final_gate(
        artifacts["claim-analysis.json"],
        artifacts["disposition-matrix.json"],
        draft,
        congruence,
        artifacts["review-report.json"],
    )
    require_final_acceptance(global_gate)

    files = {
        name: _serialize_artifact(value)
        for name, value in artifacts.items()
    }
    files["execution-manifest.json"] = _serialize_artifact(plan)
    files[f"{case_number}-labor-judgment.md"] = draft.encode("utf-8")
    files["global-gate.json"] = _serialize_artifact(global_gate)
    _require_manifest_outputs(plan["contract"], files, case_number)
    shared_digest = _shared_digest(files)
    for name, content in sorted(files.items()):
        descriptor = os.open(workspace / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
    return {
        "schema_version": 1,
        "runtime": runtime,
        "fixture_id": fixture["fixture_id"],
        "contract_digest": plan["contract_digest"],
        "shared_artifact_digest": shared_digest,
        "artifact_count": len(files),
        "global_gate_status": global_gate["status"],
    }


def _require_clean_workspace(workspace: Path) -> None:
    if workspace.is_symlink():
        raise SyntheticPipelineError("diretório de execução não pode ser vínculo simbólico")
    if not workspace.is_dir():
        raise SyntheticPipelineError("diretório de execução deve existir")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise SyntheticPipelineError("diretório de execução deve ser privado")
    if any(workspace.iterdir()):
        raise SyntheticPipelineError("diretório de execução deve estar vazio")


def _load_fixture(path: Path) -> dict:
    try:
        fixture = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SyntheticPipelineError(f"fixture not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SyntheticPipelineError(f"invalid fixture JSON: {error.msg}") from error
    if not isinstance(fixture, dict) or set(fixture) != {
        "schema_version",
        "fixture_id",
        "case_number",
        "artifacts",
    }:
        raise SyntheticPipelineError("fixture root fields are invalid")
    if fixture["schema_version"] != 1:
        raise SyntheticPipelineError("fixture schema_version must be 1")
    if not isinstance(fixture["fixture_id"], str) or not fixture["fixture_id"]:
        raise SyntheticPipelineError("fixture_id must be a non-empty string")
    if not isinstance(fixture["case_number"], str) or not fixture["case_number"]:
        raise SyntheticPipelineError("case_number must be a non-empty string")
    artifacts = fixture["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != FIXTURE_ARTIFACTS:
        raise SyntheticPipelineError("fixture artifacts do not match pipeline inputs")
    if not isinstance(artifacts["judgment-draft.md"], str):
        raise SyntheticPipelineError("judgment draft fixture must be text")
    return fixture


def _resolve_plan(runtime: str) -> dict:
    adapter_path = ROOT / "runtime" / "adapters" / f"{runtime}.json"
    adapter = load_json(adapter_path)
    validate_adapter(adapter, runtime)
    contract = normalize_manifest(load_json(MANIFEST))
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
    return {
        "schema_version": 1,
        "runtime": runtime,
        "runtime_adapter": runtime_adapter,
        "contract_digest": contract_digest(contract),
        "contract": contract,
    }


def _validate_contract_artifacts(artifacts: dict) -> None:
    _, contracts = load_catalog(CATALOG)
    for filename, contract_id in ARTIFACT_CONTRACTS.items():
        schema, _ = contracts[contract_id]
        issues = validate_document(artifacts[filename], schema)
        if issues:
            raise SyntheticPipelineError(
                f"{contract_id.replace('-', ' ')} contract failed: "
                + "; ".join(issues)
            )


def _serialize_artifact(value: object) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _require_manifest_outputs(contract: dict, files: dict, case_number: str) -> None:
    expected = set()
    for stage in contract["stages"]:
        for output in stage["outputs"]:
            expected.add(
                output.removeprefix("{workspace}/").replace(
                    "{case_number}", case_number
                )
            )
    missing = sorted(expected - set(files))
    unexpected = sorted(set(files) - expected)
    if missing or unexpected:
        detail = f"missing={missing}; unexpected={unexpected}"
        raise SyntheticPipelineError(f"pipeline output coverage failed: {detail}")


def _shared_digest(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(set(files) - {"execution-manifest.json"}):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[name])
        digest.update(b"\0")
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the sanitized pipeline fixture.")
    parser.add_argument("--runtime", required=True, choices=SUPPORTED_RUNTIMES)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = run_synthetic_pipeline(
            args.runtime,
            args.fixture.resolve(),
            args.workspace,
        )
    except (ContractError, SyntheticPipelineError, ValueError, RuntimeError) as error:
        print(f"[ERRO] {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
