#!/usr/bin/env python3
"""Reject tracked or commit-ready credentials and case data without printing secrets."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path


class ContractError(ValueError):
    """Raised when the data-hygiene contract cannot be evaluated."""


def load_contract(path: Path) -> dict:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"contract not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid contract JSON: {error.msg}") from error
    if contract.get("schema_version") != 1:
        raise ContractError("contract schema_version must be 1")
    for field in (
        "required_ignore_patterns",
        "allowed_paths",
        "forbidden_paths",
        "content_rules",
        "scan_filenames",
        "scan_extensions",
    ):
        if field not in contract:
            raise ContractError(f"contract field is required: {field}")
    if not isinstance(contract["required_ignore_patterns"], dict):
        raise ContractError("required_ignore_patterns must be an object")
    conditional = contract.get("conditional_ignore_patterns", {})
    if not isinstance(conditional, dict):
        raise ContractError("conditional_ignore_patterns must be an object")
    for field in (
        "allowed_paths",
        "forbidden_paths",
        "content_rules",
        "scan_filenames",
        "scan_extensions",
    ):
        if not isinstance(contract[field], list):
            raise ContractError(f"{field} must be a list")
    if not isinstance(contract.get("max_file_bytes"), int) or contract["max_file_bytes"] <= 0:
        raise ContractError("max_file_bytes must be a positive integer")
    return contract


def git_candidate_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ContractError("root must be a Git worktree")
    relative_paths = [os.fsdecode(item) for item in result.stdout.split(b"\0") if item]
    return [root / relative for relative in sorted(set(relative_paths))]


def path_matches(relative: str, pattern: str) -> bool:
    if fnmatch.fnmatchcase(relative, pattern):
        return True
    return pattern.startswith("**/") and fnmatch.fnmatchcase(relative, pattern[3:])


def validate_ignore_contract(root: Path, required: dict, *, missing_allowed: bool = False) -> list[str]:
    issues = []
    for relative, patterns in required.items():
        if not isinstance(relative, str) or not isinstance(patterns, list):
            raise ContractError("required ignore entries must map paths to pattern lists")
        path = root / relative
        if not path.is_file():
            if not missing_allowed:
                issues.append(f"{relative}: missing ignore file")
            continue
        lines = {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for pattern in patterns:
            if not isinstance(pattern, str):
                raise ContractError("ignore patterns must be strings")
            if pattern not in lines:
                issues.append(f"{relative}: missing ignore pattern {pattern}")
    return issues


def compile_content_rules(rules: list[dict]) -> list[tuple[str, re.Pattern[str]]]:
    compiled = []
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
            raise ContractError("content rules require string id and pattern fields")
        pattern = rule.get("pattern")
        if not isinstance(pattern, str):
            raise ContractError("content rules require string id and pattern fields")
        try:
            compiled.append((rule["id"], re.compile(pattern)))
        except re.error as error:
            raise ContractError(f"invalid content rule {rule['id']}: {error}") from error
    return compiled


def validate_candidate_files(root: Path, contract_path: Path, contract: dict) -> list[str]:
    issues = []
    allowed_paths = contract["allowed_paths"]
    forbidden_paths = contract["forbidden_paths"]
    filenames = set(contract["scan_filenames"])
    extensions = set(contract["scan_extensions"])
    content_rules = compile_content_rules(contract["content_rules"])
    max_bytes = contract["max_file_bytes"]

    for path in git_candidate_paths(root):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        allowed = any(path_matches(relative, pattern) for pattern in allowed_paths)
        if not allowed:
            for rule in forbidden_paths:
                if not isinstance(rule, dict) or not isinstance(rule.get("id"), str):
                    raise ContractError("forbidden path rules require string id and glob fields")
                pattern = rule.get("glob")
                if not isinstance(pattern, str):
                    raise ContractError("forbidden path rules require string id and glob fields")
                if path_matches(relative, pattern):
                    issues.append(f"{relative}: rule={rule['id']}")

        is_scannable = path.name in filenames or path.suffix.lower() in extensions
        if path.resolve() == contract_path.resolve() or not is_scannable:
            continue
        if path.stat().st_size > max_bytes:
            issues.append(f"{relative}: rule=file-too-large")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(f"{relative}: rule=invalid-utf8")
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for rule_id, pattern in content_rules:
                if pattern.search(line):
                    issues.append(f"{relative}:{number}: rule={rule_id}")
    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate credential and case-data hygiene.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    contract_path = args.contract.resolve()
    try:
        contract = load_contract(contract_path)
        issues = validate_ignore_contract(root, contract["required_ignore_patterns"])
        issues.extend(
            validate_ignore_contract(
                root,
                contract.get("conditional_ignore_patterns", {}),
                missing_allowed=True,
            )
        )
        issues.extend(validate_candidate_files(root, contract_path, contract))
        if issues:
            for issue in issues:
                print(f"[ERRO] {issue}")
            return 1
        print("[OK] data hygiene: ignored local secrets excluded; commit-ready files sanitized")
        return 0
    except (ContractError, OSError) as error:
        print(f"[ERRO] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
