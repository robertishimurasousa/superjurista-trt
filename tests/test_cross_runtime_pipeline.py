from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_synthetic_pipeline.py"
FIXTURE = ROOT / "tests" / "fixtures" / "pipeline" / "synthetic-first-instance.json"
CASE_NUMBER = "0000000-00.2026.5.12.0000"
EXPECTED_OUTPUTS = {
    "case-context.json",
    "execution-manifest.json",
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
    f"{CASE_NUMBER}-labor-judgment.md",
    "review-report.json",
    "global-gate.json",
}


class CrossRuntimePipelineTest(unittest.TestCase):
    def run_fixture(self, runtime: str, workspace: Path, fixture: Path = FIXTURE):
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--runtime",
                runtime,
                "--fixture",
                str(fixture),
                "--workspace",
                str(workspace),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_claude_and_codex_complete_the_same_clean_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            results = {}
            summaries = {}
            for runtime in ("claude", "codex"):
                workspace = base / runtime
                workspace.mkdir()
                result = self.run_fixture(runtime, workspace)
                results[runtime] = (workspace, result)
                self.assertEqual(
                    result.returncode,
                    0,
                    result.stdout + result.stderr,
                )
                summaries[runtime] = json.loads(result.stdout)
                self.assertEqual(
                    {path.name for path in workspace.iterdir()},
                    EXPECTED_OUTPUTS,
                )
                gate = json.loads((workspace / "global-gate.json").read_text())
                self.assertEqual(gate["status"], "passed")
                self.assertTrue(all(value == "passed" for value in gate["checks"].values()))

            self.assertEqual(
                summaries["claude"]["contract_digest"],
                summaries["codex"]["contract_digest"],
            )
            self.assertEqual(
                summaries["claude"]["shared_artifact_digest"],
                summaries["codex"]["shared_artifact_digest"],
            )
            self.assertEqual(summaries["claude"]["artifact_count"], 19)
            self.assertEqual(summaries["codex"]["artifact_count"], 19)

    def test_only_execution_manifest_contains_runtime_specific_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspaces = {}
            for runtime in ("claude", "codex"):
                workspace = base / runtime
                workspace.mkdir()
                result = self.run_fixture(runtime, workspace)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                workspaces[runtime] = workspace

            for name in EXPECTED_OUTPUTS - {"execution-manifest.json"}:
                self.assertEqual(
                    (workspaces["claude"] / name).read_bytes(),
                    (workspaces["codex"] / name).read_bytes(),
                    name,
                )
            claude_manifest = json.loads(
                (workspaces["claude"] / "execution-manifest.json").read_text()
            )
            codex_manifest = json.loads(
                (workspaces["codex"] / "execution-manifest.json").read_text()
            )
            self.assertEqual(claude_manifest["runtime"], "claude")
            self.assertEqual(codex_manifest["runtime"], "codex")
            self.assertEqual(claude_manifest["runtime_adapter"]["dispatch"], "Task")
            self.assertEqual(codex_manifest["runtime_adapter"]["dispatch"], "agent")

    def test_runner_refuses_to_overwrite_a_nonempty_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "keep.txt").write_text("preserve", encoding="utf-8")

            result = self.run_fixture("codex", workspace)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("workspace must be empty", result.stderr)
            self.assertEqual((workspace / "keep.txt").read_text(), "preserve")

    def test_contract_or_gate_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
            fixture["artifacts"]["claim-analysis.json"]["analyses"] = []
            tampered = base / "tampered.json"
            tampered.write_text(json.dumps(fixture), encoding="utf-8")
            workspace = base / "workspace"
            workspace.mkdir()

            result = self.run_fixture("claude", workspace, tampered)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("claim analysis contract failed", result.stderr)
            self.assertNotIn("global-gate.json", {path.name for path in workspace.iterdir()})


if __name__ == "__main__":
    unittest.main()
