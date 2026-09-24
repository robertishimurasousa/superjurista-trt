from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOLVE_SCRIPT = ROOT / "scripts" / "resolve_runtime_pipeline.py"
MANIFEST = ROOT / "runtime" / "pipelines" / "trt12-first-instance.json"


class PipelineResolutionTest(unittest.TestCase):
    def minimal_manifest(self) -> dict:
        return {
            "schema_version": 1,
            "pipeline": "test-pipeline",
            "profile": "trt12",
            "retry_policy": {"max_attempts": 2, "on_exhausted": "stop"},
            "gates": {
                "stage-a-gate": {"kind": "contract", "target": "artifact-a"},
                "stage-b-gate": {"kind": "contract", "target": "artifact-b"},
            },
            "stages": [
                {
                    "id": "stage-a",
                    "capability": "prepare",
                    "depends_on": [],
                    "condition": "always",
                    "outputs": ["{workspace}/artifact-a.json"],
                    "gate": "stage-a-gate",
                },
                {
                    "id": "stage-b",
                    "capability": "finish",
                    "depends_on": ["stage-a"],
                    "condition": "always",
                    "outputs": ["{workspace}/artifact-b.json"],
                    "gate": "stage-b-gate",
                },
            ],
        }

    def resolve(
        self,
        runtime: str,
        manifest: Path = MANIFEST,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(RESOLVE_SCRIPT),
                "--runtime",
                runtime,
                "--manifest",
                str(manifest),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_both_runtimes_resolve_the_same_pipeline_contract(self) -> None:
        results = {runtime: self.resolve(runtime) for runtime in ("claude", "codex")}

        self.assertEqual(
            results["claude"].returncode,
            0,
            results["claude"].stdout + results["claude"].stderr,
        )
        self.assertEqual(
            results["codex"].returncode,
            0,
            results["codex"].stdout + results["codex"].stderr,
        )

        claude = json.loads(results["claude"].stdout)
        codex = json.loads(results["codex"].stdout)
        self.assertEqual(claude["contract_digest"], codex["contract_digest"])
        self.assertEqual(claude["contract"], codex["contract"])
        self.assertEqual(claude["runtime"], "claude")
        self.assertEqual(codex["runtime"], "codex")
        self.assertEqual(claude["runtime_adapter"]["dispatch"], "Task")
        self.assertEqual(codex["runtime_adapter"]["dispatch"], "agent")

    def test_resolved_contract_preserves_graph_retries_artifacts_and_gates(self) -> None:
        result = self.resolve("codex")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        contract = json.loads(result.stdout)["contract"]

        self.assertEqual(contract["pipeline"], "trt12-first-instance")
        self.assertEqual(contract["profile"], "trt12")
        self.assertEqual(contract["retry_policy"], {"max_attempts": 2, "on_exhausted": "stop"})
        self.assertEqual(
            [stage["id"] for stage in contract["stages"]],
            [
                "prepare-profile",
                "acquire-case",
                "extract-record",
                "build-decision-units",
                "prepare-triage-input",
                "narrate-record",
                "route-claims",
                "execute-conditional-tracks",
                "analyze-claims",
                "draft-judgment",
                "merge-judgment",
                "review-and-gate",
            ],
        )
        self.assertEqual(
            [stage["max_attempts"] for stage in contract["stages"]],
            [2] * 12,
        )

        stages = {stage["id"]: stage for stage in contract["stages"]}
        self.assertEqual(stages["prepare-profile"]["depends_on"], [])
        self.assertEqual(stages["acquire-case"]["depends_on"], ["prepare-profile"])
        self.assertEqual(
            stages["execute-conditional-tracks"]["depends_on"],
            ["route-claims"],
        )
        self.assertEqual(
            stages["review-and-gate"]["depends_on"],
            ["merge-judgment"],
        )
        self.assertEqual(
            stages["extract-record"]["outputs"],
            [
                "{workspace}/document-classification.json",
                "{workspace}/procedural-timeline.json",
                "{workspace}/labor-report.json",
            ],
        )
        self.assertEqual(
            stages["build-decision-units"]["outputs"],
            [
                "{workspace}/claim-matrix.json",
                "{workspace}/evidence-matrix.json",
            ],
        )
        self.assertEqual(
            stages["prepare-triage-input"]["depends_on"],
            ["build-decision-units"],
        )
        self.assertEqual(
            stages["prepare-triage-input"]["outputs"],
            ["{workspace}/triage-input.md"],
        )
        self.assertEqual(stages["narrate-record"]["depends_on"], ["prepare-triage-input"])
        self.assertEqual(
            stages["narrate-record"]["agent"],
            "scaffold/agents/extracao/relator-marmelstein-trt12.md",
        )
        self.assertEqual(stages["narrate-record"]["outputs"], ["{workspace}/report-narrative.md"])
        self.assertEqual(stages["route-claims"]["depends_on"], ["narrate-record"])
        self.assertEqual(
            stages["route-claims"]["outputs"],
            [
                "{workspace}/{case_number}-triagem.md",
                "{workspace}/fontes-triagem.json",
                "{workspace}/issue-route.json",
            ],
        )
        self.assertEqual(
            stages["merge-judgment"]["outputs"],
            ["{workspace}/{case_number}-labor-judgment.md"],
        )
        self.assertEqual(stages["route-claims"]["gate"], "route-coverage")
        self.assertEqual(
            stages["route-claims"]["agent"],
            "scaffold/agents/analise/triador-processual-trt12.md",
        )
        self.assertEqual(
            stages["route-claims"]["agent_digest"],
            hashlib.sha256((ROOT / stages["route-claims"]["agent"]).read_bytes()).hexdigest(),
        )
        self.assertEqual(
            stages["analyze-claims"].get("agent"),
            "scaffold/agents/analise/analisador-marmelstein-trt12.md",
        )
        self.assertEqual(
            stages["analyze-claims"]["agent_digest"],
            hashlib.sha256((ROOT / stages["analyze-claims"]["agent"]).read_bytes()).hexdigest(),
        )
        self.assertEqual(
            stages["draft-judgment"].get("agent"),
            "scaffold/agents/analise/fundamentador-marmelstein-trt12.md",
        )
        self.assertEqual(
            stages["draft-judgment"]["agent_digest"],
            hashlib.sha256((ROOT / stages["draft-judgment"]["agent"]).read_bytes()).hexdigest(),
        )
        self.assertNotIn("agent", stages["build-decision-units"])
        self.assertEqual(stages["review-and-gate"]["gate"], "global-acceptance")

    def test_agent_binding_rejects_missing_or_escaping_files(self) -> None:
        for agent in (
            "scaffold/agents/analise/missing-agent.md",
            "../scaffold/agents/analise/triador-processual-trt12.md",
            "/tmp/triador-processual-trt12.md",
        ):
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as directory:
                manifest = self.minimal_manifest()
                manifest["stages"][1]["agent"] = agent
                invalid = Path(directory) / "invalid-agent.json"
                invalid.write_text(json.dumps(manifest), encoding="utf-8")

                result = self.resolve("codex", invalid)

                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("agent", result.stderr)

    def test_manifest_rejects_dependency_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.minimal_manifest()
            manifest["stages"][0]["depends_on"] = ["stage-b"]
            invalid = Path(directory) / "cycle.json"
            invalid.write_text(json.dumps(manifest), encoding="utf-8")

            result = self.resolve("claude", invalid)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("pipeline dependency cycle", result.stderr)

    def test_shared_manifest_rejects_runtime_specific_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.minimal_manifest()
            manifest["runtime_overrides"] = {"codex": {"retry_policy": {"max_attempts": 5}}}
            invalid = Path(directory) / "runtime-override.json"
            invalid.write_text(json.dumps(manifest), encoding="utf-8")

            result = self.resolve("codex", invalid)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("runtime-specific field is forbidden: runtime_overrides", result.stderr)


if __name__ == "__main__":
    unittest.main()
