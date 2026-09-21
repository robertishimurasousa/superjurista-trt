from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUALITY_GATE = ROOT / "scripts" / "quality_gate.py"
LEDGER_BUILDER = ROOT / "scripts" / "build_reuse_ledger.py"


class QualityGateTest(unittest.TestCase):
    def run_gate(self, root: Path, *checks: str) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(QUALITY_GATE), "--root", str(root)]
        for check in checks:
            command.extend(["--check", check])
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_python_syntax_check_rejects_invalid_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.py").write_text("def incomplete(\n", encoding="utf-8")

            result = self.run_gate(root, "python-syntax")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[FAIL] python-syntax", result.stdout)
            self.assertIn("broken.py", result.stdout)

    def test_json_check_rejects_invalid_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "broken.json").write_text('{"missing": }\n', encoding="utf-8")

            result = self.run_gate(root, "json")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[FAIL] json", result.stdout)
            self.assertIn("runtime/broken.json", result.stdout)

    def test_text_format_check_rejects_trailing_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.py").write_text("value = 1 \n", encoding="utf-8")

            result = self.run_gate(root, "text-format")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[FAIL] text-format", result.stdout)
            self.assertIn("bad.py:1: trailing whitespace", result.stdout)

    def test_reuse_ledger_check_rejects_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            inventory = root / "spec" / "inventory"
            commands = root / "commands"
            scripts.mkdir()
            inventory.mkdir(parents=True)
            commands.mkdir()
            shutil.copy2(LEDGER_BUILDER, scripts / LEDGER_BUILDER.name)
            (commands / "sample.md").write_text("# Sample\n", encoding="utf-8")
            (inventory / "superjurista-fork-reuse-ledger.json").write_text(
                "{}\n",
                encoding="utf-8",
            )

            result = self.run_gate(root, "reuse-ledger")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[FAIL] reuse-ledger", result.stdout)
            self.assertIn("stale", result.stdout)

    def test_unit_test_check_propagates_test_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_failure.py").write_text(
                "import unittest\n\n"
                "class FailureTest(unittest.TestCase):\n"
                "    def test_failure(self):\n"
                "        self.fail('controlled failure')\n",
                encoding="utf-8",
            )

            result = self.run_gate(root, "unit-tests")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("[FAIL] unit-tests", result.stdout)
            self.assertIn("controlled failure", result.stdout + result.stderr)

    def test_repository_static_checks_pass_together(self) -> None:
        result = self.run_gate(
            ROOT,
            "python-contract",
            "data-hygiene",
            "tribunal-profile",
            "artifact-contracts",
            "text-format",
            "python-syntax",
            "json",
            "reuse-ledger",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[OK] python-contract", result.stdout)
        self.assertIn("[OK] data-hygiene", result.stdout)
        self.assertIn("[OK] tribunal-profile", result.stdout)
        self.assertIn("[OK] artifact-contracts", result.stdout)
        self.assertIn("[OK] text-format", result.stdout)
        self.assertIn("[OK] python-syntax", result.stdout)
        self.assertIn("[OK] json", result.stdout)
        self.assertIn("[OK] reuse-ledger", result.stdout)


if __name__ == "__main__":
    unittest.main()
