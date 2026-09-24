from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"
CASE_NUMBER = "0000000-00.2026.5.12.0000"


class CodexTriagerTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("run_codex_triager") is None:
            self.fail("o despachante do triador Codex não existe")
        self.triager = importlib.import_module("run_codex_triager")
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.artifacts = fixture["artifacts"]
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        importlib.import_module("run_synthetic_pipeline").run_synthetic_pipeline(
            "codex", FIXTURE, self.workspace
        )
        for name in (f"{CASE_NUMBER}-triagem.md", "fontes-triagem.json", "issue-route.json"):
            (self.workspace / name).unlink()

    def test_valid_inherited_triage_publishes_source_and_derived_routes(self):
        response = subprocess.CompletedProcess([], 0, self.artifacts["triage.md"], "")
        with patch.object(self.triager.subprocess, "run", return_value=response) as run:
            outputs = self.triager.run_codex_triager(self.workspace, synthetic_rehearsal=True)

        self.assertEqual(
            outputs,
            (
                self.workspace.resolve() / f"{CASE_NUMBER}-triagem.md",
                self.workspace.resolve() / "fontes-triagem.json",
                self.workspace.resolve() / "issue-route.json",
            ),
        )
        self.assertEqual(outputs[0].read_text(encoding="utf-8"), self.artifacts["triage.md"])
        self.assertEqual(json.loads(outputs[1].read_text(encoding="utf-8")), {"fontes": []})
        self.assertEqual(
            json.loads(outputs[2].read_text(encoding="utf-8")),
            self.artifacts["issue-route.json"],
        )
        self.assertEqual(
            run.call_args.args[0][:6],
            ["codex", "--ask-for-approval", "never", "exec", "--sandbox", "read-only"],
        )
        self.assertIn("--ephemeral", run.call_args.args[0])
        args = run.call_args.args[0]
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--strict-config", args)
        self.assertIn(("--disable", "shell_tool"), list(zip(args, args[1:])))
        self.assertIn(("--disable", "multi_agent"), list(zip(args, args[1:])))
        for feature in (
            "apps", "browser_use", "browser_use_external",
            "browser_use_full_cdp_access", "computer_use", "code_mode_host",
        ):
            self.assertIn(("--disable", feature), list(zip(args, args[1:])))
        self.assertIn(("--config", 'web_search="disabled"'), list(zip(args, args[1:])))
        self.assertIn(("--config", "apps._default.enabled=false"), list(zip(args, args[1:])))
        self.assertNotEqual(run.call_args.kwargs["cwd"], self.workspace.resolve())
        self.assertIn("triador-processual-trt12", run.call_args.kwargs["input"])
        self.assertIn("triage-input.md", run.call_args.kwargs["input"])

    def test_unvalidated_narrative_blocks_model_invocation(self):
        (self.workspace / "report-narrative.md").write_text("texto inválido", encoding="utf-8")
        with patch.object(self.triager.subprocess, "run") as run:
            with self.assertRaises(self.triager.CodexTriagerError):
                self.triager.run_codex_triager(self.workspace, synthetic_rehearsal=True)
        run.assert_not_called()
        self.assertFalse((self.workspace / "issue-route.json").exists())

    def test_invalid_model_triage_publishes_no_bundle(self):
        response = subprocess.CompletedProcess([], 0, "triagem OK | arquivo.md", "")
        with patch.object(self.triager.subprocess, "run", return_value=response):
            with self.assertRaises(self.triager.CodexTriagerError):
                self.triager.run_codex_triager(self.workspace, synthetic_rehearsal=True)
        for name in (f"{CASE_NUMBER}-triagem.md", "fontes-triagem.json", "issue-route.json"):
            self.assertFalse((self.workspace / name).exists())

    def test_existing_output_blocks_model_invocation_and_is_preserved(self):
        existing = self.workspace / "issue-route.json"
        existing.write_text("preservar", encoding="utf-8")
        with patch.object(self.triager.subprocess, "run") as run:
            with self.assertRaises(self.triager.CodexTriagerError):
                self.triager.run_codex_triager(self.workspace, synthetic_rehearsal=True)
        run.assert_not_called()
        self.assertEqual(existing.read_text(encoding="utf-8"), "preservar")

    def test_nonzero_exit_publishes_no_bundle(self):
        response = subprocess.CompletedProcess([], 1, "", "informação privada")
        with patch.object(self.triager.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(self.triager.CodexTriagerError, "falhou"):
                self.triager.run_codex_triager(self.workspace, synthetic_rehearsal=True)
        self.assertFalse((self.workspace / "issue-route.json").exists())

    def test_model_starts_without_case_files_in_its_working_directory(self):
        def inspect_directory(*args, **kwargs):
            cwd = Path(kwargs["cwd"])
            self.assertEqual(list(cwd.iterdir()), [])
            self.assertNotEqual(cwd.resolve(), self.workspace.resolve())
            return subprocess.CompletedProcess(args[0], 0, self.artifacts["triage.md"], "")

        with patch.object(self.triager.subprocess, "run", side_effect=inspect_directory):
            self.triager.run_codex_triager(self.workspace, synthetic_rehearsal=True)

    def test_direct_dispatch_without_pilot_authorization_is_refused(self):
        with patch.object(self.triager.subprocess, "run") as run:
            with self.assertRaisesRegex(self.triager.CodexTriagerError, "autorização"):
                self.triager.run_codex_triager(self.workspace)
        run.assert_not_called()

    def test_synthetic_rehearsal_rejects_changed_case_before_dispatch(self):
        report_path = self.workspace / "labor-report.json"
        matrix_path = self.workspace / "claim-matrix.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        summary = "Outra alegação que não consta da amostra sintética aprovada."
        report["positions"][0]["summary"] = summary
        matrix["claims"][0]["claimant_position"]["summary"] = summary
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        matrix_path.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
        from build_superjurista_triage_input import build_triage_input
        triage_input = build_triage_input(report, matrix)
        (self.workspace / "triage-input.md").write_text(triage_input, encoding="utf-8")
        import hashlib
        narrative_path = self.workspace / "report-narrative.md"
        narrative = narrative_path.read_text(encoding="utf-8")
        old_digest = hashlib.sha256(
            build_triage_input(
                self.artifacts["labor-report.json"], self.artifacts["claim-matrix.json"]
            ).encode("utf-8")
        ).hexdigest()
        narrative_path.write_text(
            narrative.replace(old_digest, hashlib.sha256(triage_input.encode("utf-8")).hexdigest()),
            encoding="utf-8",
        )
        with patch.object(self.triager.subprocess, "run") as run:
            with self.assertRaisesRegex(self.triager.CodexTriagerError, "sintética"):
                self.triager.run_codex_triager(self.workspace, synthetic_rehearsal=True)
            with self.assertRaisesRegex(self.triager.CodexTriagerError, "sintética"):
                self.triager._run_codex_triager_for_pilot(self.workspace, "test-codex-model")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
