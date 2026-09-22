#!/usr/bin/env python3
"""Validate one fail-closed TRT12 controlled-pilot preflight."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sanitize_pje_har import load_sanitization_contract
from schema_validation import ContractError, load_json, validate_schema_value
from validate_pje_har_map import MapReviewError, load_review_contract, validate_map


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "runtime" / "operations" / "pilot-preflight.v1.schema.json"
DEFAULT_SANITIZATION_CONTRACT = (
    ROOT / "runtime" / "providers" / "har-sanitization-contract.json"
)
DEFAULT_MAP_REVIEW_CONTRACT = (
    ROOT / "runtime" / "providers" / "har-map-review-contract.json"
)


class PilotPreflightError(ValueError):
    """Raised when a real-case pilot must remain no-go."""


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
) -> dict:
    """Return a secret-free GO record only when every mandatory control passes."""
    try:
        schema = load_json(schema_path, "pilot preflight schema")
        sanitization_contract = load_sanitization_contract(
            sanitization_contract_path
        )
        map_review_contract = load_review_contract(map_review_contract_path)
    except ContractError as error:
        raise PilotPreflightError(str(error)) from error
    issues = validate_schema_value(preflight, schema)
    if issues:
        raise PilotPreflightError("preflight contract failed: " + "; ".join(issues))

    case = preflight["case"]
    if case["access_classification"] == "sealed_authorized":
        raise PilotPreflightError("sealed cases are forbidden for the initial pilot")
    if case["exceptional_access_required"]:
        raise PilotPreflightError(
            "exceptional access handling is forbidden for the initial pilot"
        )

    evidence = preflight["evidence"]
    if current_branch != "development" or evidence["branch"] != current_branch:
        raise PilotPreflightError("preflight branch must match development")
    if evidence["development_commit"] != current_commit:
        raise PilotPreflightError("preflight commit does not match the current checkout")
    if not working_tree_clean:
        raise PilotPreflightError("preflight requires a clean Git working tree")
    if evidence["host_readiness_status"] != "ready":
        raise PilotPreflightError("target host is not ready")
    if evidence["quality_gate_status"] != "passed":
        raise PilotPreflightError("quality gate did not pass")
    claude = evidence["claude_summary"]
    codex = evidence["codex_summary"]
    if claude != codex:
        raise PilotPreflightError("Claude and Codex runtime summaries do not match")

    try:
        map_result = validate_map(
            endpoint_map,
            sanitization_contract,
            map_review_contract,
            "TRT12",
            1,
        )
    except MapReviewError as error:
        raise PilotPreflightError(f"endpoint map is invalid: {error}") from error
    if evidence["endpoint_map_digest"] != endpoint_map.get("sanitized_digest"):
        raise PilotPreflightError("endpoint map digest does not match the reviewed map")
    if map_result["status"] != "review_ready":
        raise PilotPreflightError(
            "endpoint map gaps remain: " + ", ".join(map_result["gaps"])
        )

    _validate_retention(preflight)
    workspace = _validate_local_directory(
        workspace_path,
        repository_root,
        "workspace",
    )
    output = _validate_local_directory(
        output_path,
        repository_root,
        "output",
    )
    if workspace == output:
        raise PilotPreflightError("workspace and output directories must be distinct")
    if any(output.iterdir()):
        raise PilotPreflightError("output directory must be empty before the pilot")

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
        "external_actions_allowed": False,
    }


def _validate_retention(preflight: dict) -> None:
    created = _timestamp(preflight["created_at"], "created_at")
    retention = preflight["retention"]
    captured = _timestamp(
        retention["raw_har_captured_at"],
        "raw HAR capture",
    )
    review_close = _timestamp(
        retention["planned_review_close_by"],
        "planned review close",
    )
    deadlines = {
        "raw HAR": (
            _timestamp(retention["raw_har_delete_by"], "raw HAR deletion"),
            captured + timedelta(hours=24),
        ),
        "raw documents": (
            _timestamp(
                retention["raw_documents_delete_by"],
                "raw document deletion",
            ),
            review_close + timedelta(days=30),
        ),
        "derived artifacts": (
            _timestamp(
                retention["derived_artifacts_delete_by"],
                "derived artifact deletion",
            ),
            review_close + timedelta(days=90),
        ),
        "incident summary": (
            _timestamp(
                retention["incident_summary_delete_by"],
                "incident summary deletion",
            ),
            created + timedelta(days=180),
        ),
    }
    if review_close < created:
        raise PilotPreflightError("planned review close cannot predate preflight creation")
    if captured > created:
        raise PilotPreflightError("raw HAR capture cannot postdate preflight creation")
    for label, (deadline, maximum) in deadlines.items():
        minimum = captured if label == "raw HAR" else created
        if deadline < minimum:
            raise PilotPreflightError(f"{label} deletion cannot predate its retention period")
        if deadline > maximum:
            raise PilotPreflightError(f"{label} retention exceeds the approved maximum")


def _timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise PilotPreflightError(f"{label} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise PilotPreflightError(f"{label} must include a timezone")
    return parsed


def _validate_local_directory(path: Path, repository_root: Path, label: str) -> Path:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        pass
    else:
        raise PilotPreflightError(f"{label} must remain outside the repository")
    if not resolved.exists() or not resolved.is_dir():
        raise PilotPreflightError(f"{label} directory does not exist")
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
        raise PilotPreflightError("cannot inspect the current Git checkout") from error
    return result.stdout.strip()


def _require_outside_repository(path: Path, repository_root: Path, label: str) -> None:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return
    raise PilotPreflightError(f"{label} must remain outside the repository")


def _write_json_atomic(path: Path, value: Any) -> None:
    if path.exists():
        raise PilotPreflightError("preflight summary already exists")
    if not path.parent.exists() or not path.parent.is_dir():
        raise PilotPreflightError("preflight summary directory does not exist")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one TRT12 first-instance controlled-pilot preflight.",
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
        _require_outside_repository(args.preflight, repository_root, "preflight record")
        _require_outside_repository(args.summary, repository_root, "preflight summary")
        preflight = load_json(args.preflight, "pilot preflight")
        endpoint_map = load_json(args.endpoint_map, "sanitized endpoint map")
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
        print(f"[NO-GO] pilot preflight: {error}", file=sys.stderr)
        return 2
    print(
        "[GO] controlled pilot preflight: "
        f"pilot={result['pilot_id']}; commit={result['development_commit']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
