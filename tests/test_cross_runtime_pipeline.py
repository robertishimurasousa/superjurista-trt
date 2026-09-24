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
    "triage-input.md",
    "report-narrative.md",
    f"{CASE_NUMBER}-triagem.md",
    "fontes-triagem.json",
    "issue-route.json",
    "precedent-corpus.json",
    "evidence-review.json",
    "calculation-review.json",
    "conditional-work-results.json",
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
                workspace.mkdir(mode=0o700)
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
            self.assertEqual(summaries["claude"]["artifact_count"], 24)
            self.assertEqual(summaries["codex"]["artifact_count"], 24)

    def test_only_execution_manifest_contains_runtime_specific_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspaces = {}
            for runtime in ("claude", "codex"):
                workspace = base / runtime
                workspace.mkdir(mode=0o700)
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

    def test_synthetic_bundle_presents_human_readable_content_in_portuguese(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            result = self.run_fixture("codex", workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((workspace / "labor-report.json").read_text(encoding="utf-8"))
            evidence = json.loads((workspace / "evidence-matrix.json").read_text(encoding="utf-8"))
            precedent = json.loads((workspace / "precedent-corpus.json").read_text(encoding="utf-8"))
            review = json.loads((workspace / "review-report.json").read_text(encoding="utf-8"))

            self.assertEqual(report["case_context"]["court_unit"], "Vara do Trabalho sintética")
            self.assertEqual(report["parties"][0]["display_name"], "Parte autora sintética")
            self.assertEqual(report["timeline"][0]["summary"], "Ação sintética ajuizada.")
            self.assertEqual(report["positions"][0]["source_locator"], "páginas 4-5")
            self.assertEqual(
                evidence["evidence_items"][0]["proposition"],
                "Os cartões de ponto sintéticos contêm registros uniformes.",
            )
            self.assertEqual(
                precedent["sources"][0]["verbatim_excerpt"],
                "Trecho sintético; não é citação de decisão real.",
            )
            self.assertEqual(
                review["sources"][0]["verbatim_excerpt"],
                precedent["sources"][0]["verbatim_excerpt"],
            )
            for name in (
                "triage-input.md", "report-narrative.md",
                f"{CASE_NUMBER}-triagem.md", "judgment-draft.md",
            ):
                content = (workspace / name).read_text(encoding="utf-8")
                for english in ("Synthetic ", "page 1", "pages 4-5", "pages 2-3"):
                    self.assertNotIn(english, content, name)

    def test_runner_refuses_to_overwrite_a_nonempty_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "keep.txt").write_text("preserve", encoding="utf-8")

            result = self.run_fixture("codex", workspace)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("diretório de execução deve estar vazio", result.stderr)
            self.assertEqual((workspace / "keep.txt").read_text(), "preserve")

    def test_contract_or_gate_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
            fixture["artifacts"]["claim-analysis.json"]["analyses"] = []
            tampered = base / "tampered.json"
            tampered.write_text(json.dumps(fixture), encoding="utf-8")
            workspace = base / "workspace"
            workspace.mkdir(mode=0o700)

            result = self.run_fixture("claude", workspace, tampered)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("contrato claim-analysis inválido", result.stderr)
            self.assertNotIn("global-gate.json", {path.name for path in workspace.iterdir()})

    def test_report_and_claim_matrix_must_agree_before_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
            fixture["artifacts"]["labor-report.json"]["positions"][0]["summary"] = (
                "Alegação sintética divergente."
            )
            tampered = base / "divergent.json"
            tampered.write_text(json.dumps(fixture), encoding="utf-8")
            workspace = base / "workspace"
            workspace.mkdir(mode=0o700)

            result = self.run_fixture("codex", workspace, tampered)

            self.assertEqual(result.returncode, 2)
            self.assertIn("resumo do pedido", result.stderr)
            self.assertEqual(list(workspace.iterdir()), [])

    def test_narrative_with_stale_input_digest_blocks_all_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
            fixture["artifacts"]["report-narrative.md"] = fixture["artifacts"][
                "report-narrative.md"
            ].replace(
                "ea2c24c3b59d9c390c0b0709ae1fa0478be8abfa0bac4a9b331f202b32670748",
                "b" * 64,
            )
            tampered = base / "stale-narrative.json"
            tampered.write_text(json.dumps(fixture), encoding="utf-8")
            workspace = base / "workspace"
            workspace.mkdir(mode=0o700)

            result = self.run_fixture("claude", workspace, tampered)

            self.assertEqual(result.returncode, 2)
            self.assertIn("resumo da entrada", result.stderr)
            self.assertEqual(list(workspace.iterdir()), [])

    def test_route_must_match_the_inherited_triage_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
            fixture["artifacts"]["issue-route.json"]["routes"][0]["route_reason"] = (
                "Justificativa divergente da triagem."
            )
            tampered = base / "divergent-route.json"
            tampered.write_text(json.dumps(fixture), encoding="utf-8")
            workspace = base / "workspace"
            workspace.mkdir(mode=0o700)

            result = self.run_fixture("codex", workspace, tampered)

            self.assertEqual(result.returncode, 2)
            self.assertIn("rota derivada da triagem diverge", result.stderr)
            self.assertEqual(list(workspace.iterdir()), [])

    def test_fixture_runner_rejects_extra_merits_text_in_unresolved_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
            fixture["artifacts"]["judgment-draft.md"] += "\nJulgo procedente o pedido.\n"
            tampered = base / "unresolved-draft.json"
            tampered.write_text(json.dumps(fixture), encoding="utf-8")
            workspace = base / "workspace"
            workspace.mkdir(mode=0o700)

            result = self.run_fixture("codex", workspace, tampered)

            self.assertEqual(result.returncode, 2)
            self.assertIn("minuta diverge", result.stderr)
            self.assertEqual(list(workspace.iterdir()), [])

    def test_runner_reports_missing_fixture_without_exposing_its_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            workspace.mkdir(mode=0o700)
            missing_fixture = base / "private-case-fixture.json"

            result = self.run_fixture("codex", workspace, missing_fixture)

            self.assertEqual(result.returncode, 2)
            self.assertIn("[ERRO] amostra sintética não encontrada", result.stderr)
            self.assertNotIn(str(missing_fixture), result.stderr)
            self.assertEqual(list(workspace.iterdir()), [])

    def test_runner_reports_invalid_fixture_json_in_portuguese(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            workspace.mkdir(mode=0o700)
            invalid_fixture = base / "invalid.json"
            invalid_fixture.write_text("{", encoding="utf-8")

            result = self.run_fixture("codex", workspace, invalid_fixture)

            self.assertEqual(result.returncode, 2)
            self.assertIn("[ERRO] JSON da amostra sintética inválido", result.stderr)
            self.assertEqual(list(workspace.iterdir()), [])

    def test_runner_help_explains_the_synthetic_rehearsal_in_portuguese(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Executa a amostra sintética do fluxo", result.stdout)


if __name__ == "__main__":
    unittest.main()
