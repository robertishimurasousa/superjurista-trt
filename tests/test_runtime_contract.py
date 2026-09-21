from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = ROOT / "scripts" / "verify_runtime_contract.py"
MANIFEST = ROOT / "runtime" / "pipelines" / "smoke.json"
CASE_ID = "0000001-00.2026.5.12.0001"


class RuntimeContractTest(unittest.TestCase):
    def run_gate(self, runtime: str, workspace: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VERIFY_SCRIPT),
                "--runtime",
                runtime,
                "--manifest",
                str(MANIFEST),
                "--workspace",
                str(workspace),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def write_artifact(self, workspace: Path, body: str) -> None:
        (workspace / f"{CASE_ID}-runtime-smoke.md").write_text(body, encoding="utf-8")

    def test_claude_and_codex_accept_the_same_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix=f"{CASE_ID}-") as directory:
            workspace = Path(directory)
            self.write_artifact(
                workspace,
                "RUNTIME SMOKE\n\n"
                "Este artefato confirma que Claude Code e Codex executam o mesmo "
                "shared deterministic gate sobre o mesmo contrato versionado. "
                "A validação preserva rastreabilidade, retomada e falha explícita.\n\n"
                "Runtime contract validated.\n",
            )

            results = {runtime: self.run_gate(runtime, workspace) for runtime in ("claude", "codex")}

            for runtime, result in results.items():
                with self.subTest(runtime=runtime):
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("[OK] runtime-smoke", result.stdout)
            self.assertEqual(results["claude"].stdout, results["codex"].stdout)

    def test_claude_and_codex_reject_the_same_invalid_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix=f"{CASE_ID}-") as directory:
            workspace = Path(directory)
            self.write_artifact(
                workspace,
                "RUNTIME SMOKE\n\n"
                "Este documento tem acentuação, mas omite deliberadamente a seção exigida.\n\n"
                "Runtime contract validated.\n",
            )

            results = {runtime: self.run_gate(runtime, workspace) for runtime in ("claude", "codex")}

            for runtime, result in results.items():
                with self.subTest(runtime=runtime):
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("[INVALIDA] runtime-smoke", result.stdout)
                    self.assertIn("shared deterministic gate", result.stdout)
            self.assertEqual(results["claude"].stdout, results["codex"].stdout)

    def test_runtime_adapter_cannot_override_legal_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory) / "unsafe-adapter.json"
            adapter.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runtime": "codex",
                        "instruction_file": "AGENTS.md",
                        "skills_dir": ".agents/skills",
                        "legal_rules": {"authority_order": ["unreviewed-source"]},
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_SCRIPT),
                    "--runtime",
                    "codex",
                    "--adapter",
                    str(adapter),
                    "--manifest",
                    str(MANIFEST),
                    "--validate-only",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("forbidden adapter field: legal_rules", result.stdout)


if __name__ == "__main__":
    unittest.main()
