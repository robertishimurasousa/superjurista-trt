from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = ROOT / "scripts" / "check_python_contract.py"
CONTRACT = ROOT / "runtime" / "python-contract.json"


class PythonContractTest(unittest.TestCase):
    def check(
        self,
        mode: str,
        *,
        version: str | None = None,
        root: Path = ROOT,
        scan_only: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(CHECK_SCRIPT),
            "--root",
            str(root),
            "--contract",
            str(CONTRACT),
            "--mode",
            mode,
        ]
        if version:
            command.extend(["--python-version", version])
        if scan_only:
            command.append("--scan-only")
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_current_macos_python_satisfies_core_contract(self) -> None:
        result = self.check("core")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[OK] core Python", result.stdout)
        self.assertIn("[OK] command references", result.stdout)
        self.assertIn("[OK] dependency contract", result.stdout)

    def test_core_rejects_python_38(self) -> None:
        result = self.check("core", version="3.8")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("core requires Python 3.9+", result.stdout)

    def test_mcp_requires_python_310(self) -> None:
        incompatible = self.check("mcp", version="3.9")
        compatible = self.check("mcp", version="3.10")

        self.assertEqual(incompatible.returncode, 1, incompatible.stdout + incompatible.stderr)
        self.assertIn("mcp requires Python 3.10+", incompatible.stdout)
        self.assertEqual(compatible.returncode, 0, compatible.stdout + compatible.stderr)
        self.assertIn("[OK] mcp Python 3.10", compatible.stdout)

    def test_mcp_contract_accepts_installed_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / ".claude" / "mcp-servers" / "test-provider" / "requirements.txt"
            requirements.parent.mkdir(parents=True)
            requirements.write_text("mcp>=1.28,<2\n", encoding="utf-8")

            result = self.check("mcp", version="3.10", root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[OK] dependency contract", result.stdout)

    def test_command_scan_rejects_ambiguous_python_and_pip_executables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed_commands = root / ".claude" / "commands"
            installed_commands.mkdir(parents=True)
            (root / "README.md").write_text(
                "python scripts/run.py\n"
                "pip install -r requirements/runtime.txt\n"
                '{"command": "python"}\n',
                encoding="utf-8",
            )
            (installed_commands / "run.md").write_text(
                "python scripts/run.py\n",
                encoding="utf-8",
            )

            result = self.check("core", root=root, scan_only=True)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("README.md:1: use python3", result.stdout)
            self.assertIn("README.md:2: use python3 -m pip", result.stdout)
            self.assertIn("README.md:3: configure command as python3", result.stdout)
            self.assertIn(".claude/commands/run.md:1: use python3", result.stdout)

    def test_command_scan_accepts_explicit_python3_invocations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "python3 scripts/run.py\n"
                "python3 -m pip install -r requirements/runtime.txt\n",
                encoding="utf-8",
            )

            result = self.check("core", root=root, scan_only=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[OK] command references", result.stdout)


if __name__ == "__main__":
    unittest.main()
