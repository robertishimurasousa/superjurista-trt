import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_reuse_ledger.py"


class ReuseLedgerTest(unittest.TestCase):
    def test_inventory_classifies_every_existing_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ledger.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--root",
                    str(ROOT),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            ledger = json.loads(output.read_text(encoding="utf-8"))
            components = ledger["components"]
            self.assertEqual(len(components), 107)
            self.assertEqual(len({item["path"] for item in components}), 107)
            self.assertEqual(ledger["unclassified_count"], 0)
            self.assertEqual(
                {item["disposition"] for item in components},
                {"preserve", "adapt", "replace", "retire"},
            )
            for item in components:
                self.assertTrue(item["rationale"])
                self.assertIsInstance(item["runtime_dependencies"], list)

    def test_inventory_records_representative_migration_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "ledger.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--root",
                    str(ROOT),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            components = {
                item["path"]: item for item in json.loads(output.read_text(encoding="utf-8"))["components"]
            }

            self.assertEqual(components["scaffold/scripts/verificar_pipeline.py"]["disposition"], "preserve")
            self.assertEqual(
                components["scaffold/agents/extracao/linha-tempo-processual.md"]["disposition"],
                "adapt",
            )
            self.assertEqual(components["scaffold/agents/lista-trf/01-extracao.md"]["disposition"], "retire")
            self.assertEqual(components["scaffold/mcp-servers/bnp-api/server.py"]["disposition"], "adapt")
            self.assertEqual(
                components["scaffold/mcp-servers/cjf-jurisprudencia/server.py"]["disposition"],
                "retire",
            )
            self.assertIn("claude_paths", components["commands/criar-team.md"]["runtime_dependencies"])
            self.assertEqual(
                components["scaffold/scripts/verificar_pipeline.py"]["runtime_dependencies"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
