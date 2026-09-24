from __future__ import annotations

import importlib
import hashlib
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import tests.test_pilot_preflight as pilot_fixtures


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class CodexPilotHandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        self.api = importlib.import_module("prepare_codex_pilot_handoff")
        self.helpers = pilot_fixtures.PilotPreflightTest()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.workspace = base / "workspace"
        self.output = base / "output"
        self.workspace.mkdir(mode=0o700)
        self.output.mkdir(mode=0o700)
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        report = fixture["artifacts"]["labor-report.json"]
        matrix = fixture["artifacts"]["claim-matrix.json"]
        input_text = importlib.import_module(
            "build_superjurista_triage_input"
        ).build_triage_input(report, matrix)
        for name, content in (
            ("labor-report.json", json.dumps(report, ensure_ascii=False)),
            ("claim-matrix.json", json.dumps(matrix, ensure_ascii=False)),
            ("triage-input.md", input_text),
        ):
            (self.workspace / name).write_text(content, encoding="utf-8")
        self.map = self.helpers.endpoint_map()
        self.preflight = self.helpers.preflight(self.map)
        self.preflight["case"]["case_number"] = report["case_context"]["case_number"]

    def prepare(self) -> tuple[Path, Path, Path]:
        with patch.object(self.api, "_git_value") as git:
            git.side_effect = ["development", self.helpers.current_commit(), ""]
            return self.api.prepare_codex_pilot_handoff(
                preflight=self.preflight,
                endpoint_map=self.map,
                workspace=self.workspace,
                output=self.output,
                report_path=self.workspace / "labor-report.json",
                matrix_path=self.workspace / "claim-matrix.json",
                input_path=self.workspace / "triage-input.md",
                now=datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
            )

    def run_simulated_pilot(self) -> None:
        dispatcher = importlib.import_module("run_codex_pilot")
        narrator = importlib.import_module("run_codex_narrator")
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        replies = [
            subprocess.CompletedProcess([], 0, artifacts["report-narrative.md"], ""),
            subprocess.CompletedProcess([], 0, artifacts["triage.md"], ""),
        ]
        commit = self.helpers.current_commit()
        with patch.object(
            self.api, "_git_value", side_effect=["development", commit, ""] * 4
        ), patch.object(
            dispatcher, "_now",
            return_value=datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
        ), patch.object(narrator.subprocess, "run", side_effect=replies):
            dispatcher.run_codex_pilot(
                preflight=self.preflight,
                endpoint_map=self.map,
                workspace=self.workspace,
                output=self.output,
                report_path=self.workspace / "labor-report.json",
                matrix_path=self.workspace / "claim-matrix.json",
                input_path=self.workspace / "triage-input.md",
            )

    def test_go_prepares_only_three_bound_private_inputs(self) -> None:
        paths = self.prepare()
        self.assertEqual(
            {path.name for path in paths},
            {"labor-report.json", "claim-matrix.json", "triage-input.md"},
        )
        self.assertEqual({path.name for path in self.output.iterdir()}, {path.name for path in paths})
        for path in paths:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.read_bytes(), (self.workspace / path.name).read_bytes())

    def test_no_go_or_mismatched_case_never_stages_data(self) -> None:
        for change in ("sealed", "case", "expired"):
            with self.subTest(change=change):
                self.preflight = self.helpers.preflight(self.map)
                report = json.loads((self.workspace / "labor-report.json").read_text())
                self.preflight["case"]["case_number"] = report["case_context"]["case_number"]
                if change == "sealed":
                    self.preflight["case"]["access_classification"] = "sealed_authorized"
                elif change == "case":
                    self.preflight["case"]["case_number"] = "0000001-00.2026.5.12.0000"
                else:
                    self.preflight["valid_until"] = "2026-09-21T12:00:00Z"
                with self.assertRaises(self.api.CodexPilotHandoffError):
                    self.prepare()
                self.assertEqual(list(self.output.iterdir()), [])

    def test_divergent_input_and_symlink_are_rejected_without_output(self) -> None:
        input_path = self.workspace / "triage-input.md"
        input_path.write_text("entrada divergente", encoding="utf-8")
        with self.assertRaises(self.api.CodexPilotHandoffError):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])
        input_path.unlink()
        input_path.symlink_to(self.workspace / "labor-report.json")
        with self.assertRaises(self.api.CodexPilotHandoffError):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_nonempty_or_nonprivate_output_is_rejected(self) -> None:
        existing = self.output / "preservar.txt"
        existing.write_text("manter", encoding="utf-8")
        with self.assertRaises(self.api.CodexPilotHandoffError):
            self.prepare()
        self.assertEqual(existing.read_text(encoding="utf-8"), "manter")
        existing.unlink()
        self.output.chmod(0o755)
        with self.assertRaises(self.api.CodexPilotHandoffError):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_analysis_operation_and_classification_must_match_authorization(self) -> None:
        self.preflight["controls"]["requested_operations"].remove("analyze")
        with self.assertRaises(self.api.CodexPilotHandoffError):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])
        self.preflight["controls"]["requested_operations"].append("analyze")
        self.preflight["case"]["access_classification"] = "restricted_authorized"
        with self.assertRaises(self.api.CodexPilotHandoffError):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_codex_provider_must_be_explicitly_authorized(self) -> None:
        self.preflight["controls"]["model_providers_authorized"] = ["claude"]
        with self.assertRaisesRegex(self.api.CodexPilotHandoffError, "Codex"):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_codex_model_must_be_explicitly_recorded(self) -> None:
        del self.preflight["controls"]["codex_model_id"]
        with self.assertRaisesRegex(self.api.CodexPilotHandoffError, "modelo Codex"):
            self.prepare()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_protected_preflight_file_cannot_be_inside_repository(self) -> None:
        with self.assertRaises(self.api.CodexPilotHandoffError):
            self.api._protected_preflight(ROOT / "README.md")
        protected = self.workspace / "pilot-preflight.json"
        protected.write_text(json.dumps(self.preflight), encoding="utf-8")
        protected.chmod(0o600)
        self.assertEqual(
            self.api._protected_preflight(protected)["pilot_id"], "PILOT-001"
        )

    def test_authorized_pilot_dispatches_narrator_then_triager(self) -> None:
        try:
            dispatcher = importlib.import_module("run_codex_pilot")
        except ModuleNotFoundError:
            self.fail("o orquestrador do piloto Codex não existe")
        narrator = importlib.import_module("run_codex_narrator")
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        replies = [
            subprocess.CompletedProcess([], 0, artifacts["report-narrative.md"], ""),
            subprocess.CompletedProcess([], 0, artifacts["triage.md"], ""),
        ]
        commit = self.helpers.current_commit()
        fixed_now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
        with patch.object(
            self.api, "_git_value",
            side_effect=[
                "development", commit, "",
                "development", commit, "",
                "development", commit, "",
                "development", commit, "",
            ],
        ), \
             patch.object(dispatcher, "_now", return_value=fixed_now), \
             patch.object(narrator.subprocess, "run", side_effect=replies) as model:
            outputs = dispatcher.run_codex_pilot(
                preflight=self.preflight,
                endpoint_map=self.map,
                workspace=self.workspace,
                output=self.output,
                report_path=self.workspace / "labor-report.json",
                matrix_path=self.workspace / "claim-matrix.json",
                input_path=self.workspace / "triage-input.md",
            )
        self.assertEqual(model.call_count, 2)
        for call in model.call_args_list:
            self.assertIn("--model", call.args[0])
            self.assertEqual(
                call.args[0][call.args[0].index("--model") + 1], "test-codex-model"
            )
        self.assertEqual(outputs[0].read_text(encoding="utf-8"), artifacts["report-narrative.md"])
        self.assertEqual(outputs[1].read_text(encoding="utf-8"), artifacts["triage.md"])
        self.assertEqual(json.loads(outputs[3].read_text()), artifacts["issue-route.json"])
        self.assertEqual(len(list(self.output.iterdir())), 8)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in outputs))
        summary_path = self.output / "pilot-run-summary.json"
        self.assertTrue(summary_path.is_file())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "pending_legal_review")
        self.assertEqual(summary["model_id"], "test-codex-model")
        self.assertEqual(summary["passed_handoff_gates"], 3)
        self.assertFalse(summary["external_actions_allowed"])
        self.assertEqual(
            summary["generated_artifact_sha256"]["narrative"],
            hashlib.sha256(artifacts["report-narrative.md"].encode("utf-8")).hexdigest(),
        )
        self.assertNotIn(self.preflight["case"]["case_number"], summary_path.read_text())
        self.assertEqual(stat.S_IMODE(summary_path.stat().st_mode), 0o600)

    def test_pilot_dispatch_never_calls_model_without_case_go(self) -> None:
        try:
            dispatcher = importlib.import_module("run_codex_pilot")
        except ModuleNotFoundError:
            self.fail("o orquestrador do piloto Codex não existe")
        narrator = importlib.import_module("run_codex_narrator")
        self.preflight["case"]["case_number"] = "0000001-00.2026.5.12.0000"
        commit = self.helpers.current_commit()
        fixed_now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
        with patch.object(self.api, "_git_value", side_effect=["development", commit, ""]), \
             patch.object(dispatcher, "_now", return_value=fixed_now), \
             patch.object(narrator.subprocess, "run") as model:
            with self.assertRaises(dispatcher.CodexPilotError):
                dispatcher.run_codex_pilot(
                    preflight=self.preflight,
                    endpoint_map=self.map,
                    workspace=self.workspace,
                    output=self.output,
                    report_path=self.workspace / "labor-report.json",
                    matrix_path=self.workspace / "claim-matrix.json",
                    input_path=self.workspace / "triage-input.md",
                )
        model.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_pilot_rejects_non_synthetic_content_before_staging_or_model_call(self) -> None:
        dispatcher = importlib.import_module("run_codex_pilot")
        report_path = self.workspace / "labor-report.json"
        matrix_path = self.workspace / "claim-matrix.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        changed_summary = "Alegação alterada fora da amostra sintética aprovada."
        report["positions"][0]["summary"] = changed_summary
        matrix["claims"][0]["claimant_position"]["summary"] = changed_summary
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        matrix_path.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
        triage_input = importlib.import_module("build_superjurista_triage_input")
        (self.workspace / "triage-input.md").write_text(
            triage_input.build_triage_input(report, matrix), encoding="utf-8"
        )
        commit = self.helpers.current_commit()
        with patch.object(
            self.api, "_git_value", side_effect=["development", commit, ""] * 4
        ), patch.object(
            dispatcher, "_now",
            return_value=datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
        ), patch.object(
            importlib.import_module("run_codex_narrator").subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, "", ""),
        ) as model:
            with self.assertRaisesRegex(dispatcher.CodexPilotError, "sintética"):
                dispatcher.run_codex_pilot(
                    preflight=self.preflight,
                    endpoint_map=self.map,
                    workspace=self.workspace,
                    output=self.output,
                    report_path=report_path,
                    matrix_path=matrix_path,
                    input_path=self.workspace / "triage-input.md",
                )
        model.assert_not_called()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_preexisting_summary_is_not_overwritten_after_model_outputs(self) -> None:
        dispatcher = importlib.import_module("run_codex_pilot")
        narrator = importlib.import_module("run_codex_narrator")
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        commit = self.helpers.current_commit()

        def reply(*args, **kwargs):
            if "relator" in kwargs["input"]:
                return subprocess.CompletedProcess([], 0, artifacts["report-narrative.md"], "")
            (self.output / "pilot-run-summary.json").write_text("preservar", encoding="utf-8")
            return subprocess.CompletedProcess([], 0, artifacts["triage.md"], "")

        with patch.object(
            self.api, "_git_value", side_effect=["development", commit, ""] * 4
        ), patch.object(
            dispatcher, "_now",
            return_value=datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
        ), patch.object(narrator.subprocess, "run", side_effect=reply):
            with self.assertRaises(dispatcher.CodexPilotError):
                dispatcher.run_codex_pilot(
                    preflight=self.preflight,
                    endpoint_map=self.map,
                    workspace=self.workspace,
                    output=self.output,
                    report_path=self.workspace / "labor-report.json",
                    matrix_path=self.workspace / "claim-matrix.json",
                    input_path=self.workspace / "triage-input.md",
                )
        self.assertEqual(
            (self.output / "pilot-run-summary.json").read_text(encoding="utf-8"),
            "preservar",
        )

    def test_expiration_during_preparation_blocks_first_model_call(self) -> None:
        dispatcher = importlib.import_module("run_codex_pilot")
        narrator = importlib.import_module("run_codex_narrator")
        commit = self.helpers.current_commit()
        before = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
        after = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        with patch.object(self.api, "_git_value", side_effect=["development", commit, ""]), \
             patch.object(dispatcher, "_now", side_effect=[before, after]), \
             patch.object(narrator.subprocess, "run") as model:
            with self.assertRaises(dispatcher.CodexPilotError):
                dispatcher.run_codex_pilot(
                    preflight=self.preflight,
                    endpoint_map=self.map,
                    workspace=self.workspace,
                    output=self.output,
                    report_path=self.workspace / "labor-report.json",
                    matrix_path=self.workspace / "claim-matrix.json",
                    input_path=self.workspace / "triage-input.md",
                )
        model.assert_not_called()
        self.assertEqual(len(list(self.output.iterdir())), 3)

    def test_expiration_during_triage_blocks_final_acceptance(self) -> None:
        dispatcher = importlib.import_module("run_codex_pilot")
        narrator = importlib.import_module("run_codex_narrator")
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        replies = [
            subprocess.CompletedProcess([], 0, artifacts["report-narrative.md"], ""),
            subprocess.CompletedProcess([], 0, artifacts["triage.md"], ""),
        ]
        commit = self.helpers.current_commit()
        before = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
        after = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        with patch.object(
            self.api, "_git_value",
            side_effect=["development", commit, ""] * 4,
        ), patch.object(
            dispatcher, "_now", side_effect=[before, before, before, after]
        ), patch.object(narrator.subprocess, "run", side_effect=replies):
            with self.assertRaisesRegex(dispatcher.CodexPilotError, "venceu"):
                dispatcher.run_codex_pilot(
                    preflight=self.preflight,
                    endpoint_map=self.map,
                    workspace=self.workspace,
                    output=self.output,
                    report_path=self.workspace / "labor-report.json",
                    matrix_path=self.workspace / "claim-matrix.json",
                    input_path=self.workspace / "triage-input.md",
                )

    def test_independent_verifier_accepts_untouched_pilot_bundle(self) -> None:
        self.run_simulated_pilot()
        try:
            verifier = importlib.import_module("verify_codex_pilot_result")
        except ModuleNotFoundError:
            self.fail("o verificador independente do piloto não existe")
        with patch.object(subprocess, "run") as external:
            result = verifier.verify_codex_pilot_result(self.output, self.preflight)
        external.assert_not_called()
        self.assertEqual(result["integrity"], "passed")
        self.assertEqual(result["status"], "pending_legal_review")
        self.assertEqual(result["passed_handoff_gates"], 3)

    def test_independent_verifier_cli_reports_no_case_number(self) -> None:
        self.run_simulated_pilot()
        protected = self.workspace / "pilot-preflight.json"
        protected.write_text(json.dumps(self.preflight), encoding="utf-8")
        protected.chmod(0o600)
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "verify_codex_pilot_result.py"),
                "--workspace", str(self.output),
                "--preflight", str(protected),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Revisão jurídica humana ainda pendente", result.stdout)
        self.assertNotIn(self.preflight["case"]["case_number"], result.stdout + result.stderr)

    def test_independent_verifier_rejects_changed_route(self) -> None:
        self.run_simulated_pilot()
        verifier = importlib.import_module("verify_codex_pilot_result")
        (self.output / "issue-route.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(verifier.CodexPilotResultError, "SHA-256"):
            verifier.verify_codex_pilot_result(self.output, self.preflight)

    def test_independent_verifier_binds_summary_to_protected_authorization(self) -> None:
        self.run_simulated_pilot()
        verifier = importlib.import_module("verify_codex_pilot_result")
        summary_path = self.output / "pilot-run-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["model_id"] = "outro-modelo"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(verifier.CodexPilotResultError, "modelo"):
            verifier.verify_codex_pilot_result(self.output, self.preflight)

    def test_independent_verifier_rejects_symlink_even_with_matching_bytes(self) -> None:
        self.run_simulated_pilot()
        verifier = importlib.import_module("verify_codex_pilot_result")
        source = self.output / "fontes-triagem.json"
        backup = self.output / "copia-fontes.json"
        backup.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(backup)
        with self.assertRaisesRegex(verifier.CodexPilotResultError, "vínculo simbólico"):
            verifier.verify_codex_pilot_result(self.output, self.preflight)


if __name__ == "__main__":
    unittest.main()
