#!/usr/bin/env python3
"""Validate Python versions, invocations, and dependency declarations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


AMBIGUOUS_PYTHON = re.compile(
    r"(?<![A-Za-z0-9_])python(?=[ \t]+(?:-c\b|-m\b|--[A-Za-z0-9_-]+|[\"'$./~<]|"
    r"[A-Za-z_][A-Za-z0-9_./-]*\.py\b))"
)
DIRECT_PIP = re.compile(r"(?<![A-Za-z0-9_.-])pip(?=[ \t]+(?:install|uninstall|freeze|check|list)\b)")
PYTHON_COMMAND_VALUE = re.compile(
    r"[\"']command[\"']\s*:\s*[\"']python[\"']"
)


class ContractError(ValueError):
    """Raised when the Python contract cannot be evaluated."""


def load_contract(path: Path) -> dict:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"contract not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid contract JSON: {error.msg}") from error
    if contract.get("schema_version") != 1:
        raise ContractError("contract schema_version must be 1")
    if contract.get("executable") != "python3":
        raise ContractError("contract executable must be python3")
    if not isinstance(contract.get("environments"), dict):
        raise ContractError("contract environments must be an object")
    if not isinstance(contract.get("command_scan"), dict):
        raise ContractError("contract command_scan must be an object")
    return contract


def parse_version(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", value)
    if not match:
        raise ContractError(f"invalid Python version: {value}")
    return int(match.group(1)), int(match.group(2))


def format_version(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def iter_scan_files(root: Path, patterns: list[str]) -> list[Path]:
    files = set()
    for pattern in patterns:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def find_command_issues(root: Path, patterns: list[str]) -> list[str]:
    issues = []
    for path in iter_scan_files(root, patterns):
        relative = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as error:
            issues.append(f"{relative}: unreadable UTF-8: {error}")
            continue
        for number, line in enumerate(lines, 1):
            if AMBIGUOUS_PYTHON.search(line):
                issues.append(f"{relative}:{number}: use python3")
            line_without_module_pip = line.replace("python3 -m pip", "")
            if DIRECT_PIP.search(line_without_module_pip):
                issues.append(f"{relative}:{number}: use python3 -m pip")
            if PYTHON_COMMAND_VALUE.search(line):
                issues.append(f"{relative}:{number}: configure command as python3")
    return issues


def requirement_lines(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as error:
        raise ContractError(f"requirements file not found: {path}") from error
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def validate_dependencies(root: Path, environment: dict) -> list[str]:
    issues = []
    required_files = environment.get("requirements", {})
    if not isinstance(required_files, dict):
        raise ContractError("environment requirements must be an object")
    for relative, expected in required_files.items():
        actual = requirement_lines(root / relative)
        if actual != expected:
            issues.append(f"{relative}: dependency declarations differ from contract")

    requirement_globs = environment.get("requirements_globs")
    required_constraint = environment.get("required_constraint")
    if requirement_globs or required_constraint:
        if (
            not isinstance(requirement_globs, list)
            or not requirement_globs
            or not all(isinstance(item, str) for item in requirement_globs)
            or not isinstance(required_constraint, str)
        ):
            raise ContractError(
                "requirements_globs must be a non-empty list and required_constraint a string"
            )
        matched = sorted(
            {path for pattern in requirement_globs for path in root.glob(pattern) if path.is_file()}
        )
        if not matched:
            issues.append(f"{', '.join(requirement_globs)}: no requirements files found")
        for path in matched:
            if required_constraint not in requirement_lines(path):
                relative = path.relative_to(root).as_posix()
                issues.append(f"{relative}: requires {required_constraint}")
    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the SuperJurista Python contract.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("core", "mcp"))
    parser.add_argument("--python-version")
    parser.add_argument("--scan-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    try:
        contract = load_contract(args.contract)
        patterns = contract["command_scan"].get("include")
        if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
            raise ContractError("command_scan include must be a list of patterns")
        command_issues = find_command_issues(root, patterns)
        if command_issues:
            for issue in command_issues:
                print(f"[ERRO] {issue}")
            return 1
        print("[OK] command references use python3 and python3 -m pip")
        if args.scan_only:
            return 0

        environment = contract["environments"].get(args.mode)
        if not isinstance(environment, dict):
            raise ContractError(f"unknown environment contract: {args.mode}")
        minimum = parse_version(environment.get("minimum_version", ""))
        current = parse_version(args.python_version) if args.python_version else sys.version_info[:2]
        if current < minimum:
            print(
                f"[ERRO] {args.mode} requires Python {format_version(minimum)}+; "
                f"received {format_version(current)}"
            )
            return 1
        print(f"[OK] {args.mode} Python {format_version(current)}")

        dependency_issues = validate_dependencies(root, environment)
        if dependency_issues:
            for issue in dependency_issues:
                print(f"[ERRO] {issue}")
            return 1
        print("[OK] dependency contract")
        return 0
    except (ContractError, KeyError, TypeError) as error:
        print(f"[ERRO] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
