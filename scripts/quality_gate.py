#!/usr/bin/env python3
"""Run the repository's deterministic local and CI quality gate."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


CHECK_ORDER = (
    "python-contract",
    "data-hygiene",
    "tribunal-profile",
    "artifact-contracts",
    "text-format",
    "python-syntax",
    "json",
    "reuse-ledger",
    "unit-tests",
)
EXCLUDED_PYTHON = {
    "skills/criar-mcp-precedente/references/template-server.py",
}
EXCLUDED_PARTS = {".git", ".venv", "__pycache__"}


class CheckFailure(RuntimeError):
    """Raised when one quality check does not satisfy its contract."""


def run_command(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def command_output(result: subprocess.CompletedProcess[str]) -> str:
    return "".join(part for part in (result.stdout, result.stderr) if part).strip()


def require_success(command: list[str], root: Path) -> str:
    result = run_command(command, root)
    output = command_output(result)
    if result.returncode:
        raise CheckFailure(output or f"command exited with {result.returncode}: {' '.join(command)}")
    return output


def check_python_contract(root: Path) -> str:
    checker = root / "scripts" / "check_python_contract.py"
    contract = root / "runtime" / "python-contract.json"
    if not checker.is_file() or not contract.is_file():
        raise CheckFailure("Python checker or contract is missing")
    base = [
        sys.executable,
        str(checker),
        "--root",
        str(root),
        "--contract",
        str(contract),
        "--mode",
    ]
    core_output = require_success([*base, "core"], root)
    mcp_output = require_success([*base, "mcp", "--python-version", "3.10"], root)
    return f"core and MCP boundaries valid\n{core_output}\n{mcp_output}"


def check_data_hygiene(root: Path) -> str:
    checker = root / "scripts" / "check_data_hygiene.py"
    contract = root / "runtime" / "data-hygiene-contract.json"
    if not checker.is_file() or not contract.is_file():
        raise CheckFailure("data-hygiene checker or contract is missing")
    return require_success(
        [
            sys.executable,
            str(checker),
            "--root",
            str(root),
            "--contract",
            str(contract),
        ],
        root,
    )


def check_tribunal_profile(root: Path) -> str:
    validator = root / "scripts" / "validate_tribunal_profile.py"
    profiles = root / "runtime" / "profiles"
    schema = profiles / "schema.json"
    registry = profiles / "registry.json"
    profile = profiles / "trt12.json"
    if not all(path.is_file() for path in (validator, schema, registry, profile)):
        raise CheckFailure("tribunal profile validator or contract file is missing")
    return require_success(
        [
            sys.executable,
            str(validator),
            "--schema",
            str(schema),
            "--registry",
            str(registry),
            "--profile",
            str(profile),
        ],
        root,
    )


def check_artifact_contracts(root: Path) -> str:
    validator = root / "scripts" / "validate_artifact_contracts.py"
    catalog = root / "runtime" / "contracts" / "catalog.json"
    fixtures = root / "tests" / "fixtures" / "contracts"
    if not validator.is_file() or not catalog.is_file() or not fixtures.is_dir():
        raise CheckFailure("artifact contract validator, catalog, or fixtures are missing")
    return require_success(
        [
            sys.executable,
            str(validator),
            "--catalog",
            str(catalog),
            "--fixtures-root",
            str(fixtures),
        ],
        root,
    )


def iter_python_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if relative.as_posix() in EXCLUDED_PYTHON:
            continue
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def check_python_syntax(root: Path) -> str:
    files = iter_python_files(root)
    issues = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=relative)
        except (SyntaxError, UnicodeDecodeError) as error:
            issues.append(f"{relative}: {error}")
    if issues:
        raise CheckFailure("\n".join(issues))
    return f"parsed {len(files)} executable Python files"


def iter_format_files(root: Path) -> list[Path]:
    files = set(iter_python_files(root))
    files.update(iter_json_files(root))
    files.update(path for path in (root / ".github").glob("**/*.yml") if path.is_file())
    files.update(path for path in (root / ".github").glob("**/*.yaml") if path.is_file())
    files.update(path for path in (root / "requirements").glob("*.txt") if path.is_file())
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def check_text_format(root: Path) -> str:
    files = iter_format_files(root)
    issues = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            issues.append(f"{relative}: invalid UTF-8: {error}")
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if line.endswith((" ", "\t")):
                issues.append(f"{relative}:{number}: trailing whitespace")
        if text and not text.endswith("\n"):
            issues.append(f"{relative}: missing final newline")
    if issues:
        raise CheckFailure("\n".join(issues))
    return f"validated {len(files)} source and configuration files"


def iter_json_files(root: Path) -> list[Path]:
    patterns = (
        ".claude-plugin/*.json",
        "runtime/**/*.json",
        "spec/inventory/**/*.json",
    )
    files = {path for pattern in patterns for path in root.glob(pattern) if path.is_file()}
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def check_json(root: Path) -> str:
    files = iter_json_files(root)
    issues = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            issues.append(f"{relative}: {error}")
    if issues:
        raise CheckFailure("\n".join(issues))
    return f"parsed {len(files)} JSON files"


def check_reuse_ledger(root: Path) -> str:
    builder = root / "scripts" / "build_reuse_ledger.py"
    expected = root / "spec" / "inventory" / "superjurista-fork-reuse-ledger.json"
    if not builder.is_file() or not expected.is_file():
        raise CheckFailure("reuse ledger builder or committed snapshot is missing")
    with tempfile.TemporaryDirectory() as directory:
        actual = Path(directory) / "reuse-ledger.json"
        output = require_success(
            [
                sys.executable,
                str(builder),
                "--root",
                str(root),
                "--output",
                str(actual),
            ],
            root,
        )
        if actual.read_bytes() != expected.read_bytes():
            raise CheckFailure(
                "reuse ledger is stale; run "
                "python3 scripts/build_reuse_ledger.py --root . "
                "--output spec/inventory/superjurista-fork-reuse-ledger.json"
            )
    return output


def check_unit_tests(root: Path) -> str:
    if not (root / "tests").is_dir():
        raise CheckFailure("tests directory is missing")
    return require_success(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        root,
    )


CHECKS: dict[str, Callable[[Path], str]] = {
    "python-contract": check_python_contract,
    "data-hygiene": check_data_hygiene,
    "tribunal-profile": check_tribunal_profile,
    "artifact-contracts": check_artifact_contracts,
    "text-format": check_text_format,
    "python-syntax": check_python_syntax,
    "json": check_json,
    "reuse-ledger": check_reuse_ledger,
    "unit-tests": check_unit_tests,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SuperJurista quality gate.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--check",
        action="append",
        choices=CHECK_ORDER,
        help="Run only the selected check; repeat to select multiple checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    selected = args.check or list(CHECK_ORDER)
    failed = False
    for name in selected:
        try:
            detail = CHECKS[name](root)
            print(f"[OK] {name}: {detail}")
        except CheckFailure as error:
            failed = True
            print(f"[FAIL] {name}: {error}")
    if failed:
        print("[FAIL] quality-gate")
        return 1
    print("[OK] quality-gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
