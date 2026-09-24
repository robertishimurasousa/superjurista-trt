from __future__ import annotations

import importlib
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


class CodexNarratorTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        self.runner = importlib.import_module("run_synthetic_pipeline")
        self.narrator = importlib.import_module("run_codex_narrator")
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.runner.run_synthetic_pipeline("codex", FIXTURE, self.workspace)
        (self.workspace / "report-narrative.md").unlink()

    def test_valid_codex_response_is_accepted_without_overwriting_inputs(self):
        narrative = self.fixture["artifacts"]["report-narrative.md"]
        report_before = (self.workspace / "labor-report.json").read_bytes()
        response = subprocess.CompletedProcess([], 0, narrative, "")
        with patch.object(self.narrator.subprocess, "run", return_value=response) as run:
            result = self.narrator.run_codex_narrator(self.workspace, synthetic_rehearsal=True)

        self.assertEqual(result, (self.workspace / "report-narrative.md").resolve())
        self.assertEqual(result.read_text(encoding="utf-8"), narrative)
        self.assertEqual((self.workspace / "labor-report.json").read_bytes(), report_before)
        args = run.call_args.args[0]
        self.assertEqual(
            args[:6],
            ["codex", "--ask-for-approval", "never", "exec", "--sandbox", "read-only"],
        )
        self.assertIn("--ephemeral", args)
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
        self.assertEqual(args[-1], "-")
        self.assertNotEqual(run.call_args.kwargs["cwd"], self.workspace.resolve())
        prompt = run.call_args.kwargs["input"]
        self.assertIn("relator-marmelstein-trt12", prompt)
        self.assertIn("RELATÓRIO", prompt)
        self.assertIn("triage-input.md", prompt)

    def test_codex_starts_in_an_empty_isolated_directory(self):
        narrative = self.fixture["artifacts"]["report-narrative.md"]

        def inspect_directory(*args, **kwargs):
            cwd = Path(kwargs["cwd"])
            self.assertTrue(cwd.is_dir())
            self.assertEqual(list(cwd.iterdir()), [])
            self.assertNotEqual(cwd.resolve(), self.workspace.resolve())
            return subprocess.CompletedProcess(args[0], 0, narrative, "")

        with patch.object(self.narrator.subprocess, "run", side_effect=inspect_directory):
            self.narrator.run_codex_narrator(self.workspace, synthetic_rehearsal=True)

    def test_invalid_response_is_rejected_before_publishing(self):
        response = subprocess.CompletedProcess([], 0, "relatório OK | report-narrative.md", "")
        with patch.object(self.narrator.subprocess, "run", return_value=response):
            with self.assertRaises(self.narrator.CodexNarratorError):
                self.narrator.run_codex_narrator(self.workspace, synthetic_rehearsal=True)
        self.assertFalse((self.workspace / "report-narrative.md").exists())

    def test_existing_output_is_rejected_before_model_invocation(self):
        (self.workspace / "report-narrative.md").write_text("preservar", encoding="utf-8")
        with patch.object(self.narrator.subprocess, "run") as run:
            with self.assertRaises(self.narrator.CodexNarratorError):
                self.narrator.run_codex_narrator(self.workspace, synthetic_rehearsal=True)
        run.assert_not_called()
        self.assertEqual((self.workspace / "report-narrative.md").read_text(), "preservar")

    def test_divergent_input_is_rejected_before_model_invocation(self):
        (self.workspace / "triage-input.md").write_text("divergente", encoding="utf-8")
        with patch.object(self.narrator.subprocess, "run") as run:
            with self.assertRaises(self.narrator.CodexNarratorError):
                self.narrator.run_codex_narrator(self.workspace, synthetic_rehearsal=True)
        run.assert_not_called()

    def test_symlinked_report_is_rejected_before_reading_or_invocation(self):
        report_path = self.workspace / "labor-report.json"
        copy_path = self.workspace / "copia-relatorio.json"
        copy_path.write_text("not json", encoding="utf-8")
        report_path.unlink()
        report_path.symlink_to(copy_path)
        with patch.object(self.narrator.subprocess, "run") as run:
            with self.assertRaisesRegex(
                self.narrator.CodexNarratorError, "vínculos simbólicos"
            ):
                self.narrator.run_codex_narrator(self.workspace, synthetic_rehearsal=True)
        run.assert_not_called()

    def test_nonzero_exit_does_not_publish_an_output(self):
        response = subprocess.CompletedProcess([], 1, "qualquer conteúdo", "detalhes privados")
        with patch.object(self.narrator.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(self.narrator.CodexNarratorError, "falhou"):
                self.narrator.run_codex_narrator(self.workspace, synthetic_rehearsal=True)
        self.assertFalse((self.workspace / "report-narrative.md").exists())

    def test_direct_dispatch_without_pilot_authorization_is_refused(self):
        with patch.object(self.narrator.subprocess, "run") as run:
            with self.assertRaisesRegex(self.narrator.CodexNarratorError, "autorização"):
                self.narrator.run_codex_narrator(self.workspace)
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
        (self.workspace / "triage-input.md").write_text(
            build_triage_input(report, matrix), encoding="utf-8"
        )
        with patch.object(self.narrator.subprocess, "run") as run:
            with self.assertRaisesRegex(self.narrator.CodexNarratorError, "sintética"):
                self.narrator.run_codex_narrator(self.workspace, synthetic_rehearsal=True)
            with self.assertRaisesRegex(self.narrator.CodexNarratorError, "sintética"):
                self.narrator._run_codex_narrator_for_pilot(self.workspace, "test-codex-model")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
