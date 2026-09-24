from __future__ import annotations

import importlib
import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import tests.test_pilot_preflight as pilot_fixtures


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"
NOW = datetime(2026, 9, 21, 13, tzinfo=timezone.utc)


class OpenAIPilotTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("run_openai_pilot") is None:
            self.fail("o despachante do piloto pela API não existe")
        self.runner = importlib.import_module("run_openai_pilot")
        self.helpers = pilot_fixtures.PilotPreflightTest()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.workspace = base / "origem"
        self.output = base / "saida"
        self.workspace.mkdir(mode=0o700)
        self.output.mkdir(mode=0o700)
        self.artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        report = self.artifacts["labor-report.json"]
        matrix = self.artifacts["claim-matrix.json"]
        triage_input = importlib.import_module(
            "build_superjurista_triage_input"
        ).build_triage_input(report, matrix)
        for name, content in (
            ("labor-report.json", json.dumps(report, ensure_ascii=False)),
            ("claim-matrix.json", json.dumps(matrix, ensure_ascii=False)),
            ("triage-input.md", triage_input),
        ):
            path = self.workspace / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o600)
        self.endpoint_map = self.helpers.endpoint_map()
        self.preflight = self.helpers.preflight(self.endpoint_map)
        self.authorization = {
            "schema_version": 1,
            "provider": "openai_api",
            "surface": "responses",
            "pilot_id": "PILOT-001",
            "case_reference_digest": "a" * 64,
            "authorization_scope_digest": "b" * 64,
            "access_classification": "public_or_authorized",
            "model_id": "modelo-exemplo",
            "authorized_by": "REPOSITORY-OWNER",
            "approved_at": "2026-09-21T12:30:00Z",
            "valid_until": "2026-09-22T12:00:00Z",
            "provider_terms_digest": "d" * 64,
            "provider_terms_reviewed_by": "REPOSITORY-OWNER",
            "request_controls": {
                "tools_allowed": False,
                "response_storage_allowed": False,
                "external_actions_allowed": False,
            },
        }

    def _git_value(self, root: Path, *args: str) -> str:
        if args[0] == "branch":
            return "development"
        if args[0] == "rev-parse":
            return self.helpers.current_commit()
        return ""

    def run_pilot(self, generator, *, simulate_enabled: bool = True):
        permission = (
            patch.object(self.runner, "REAL_CASE_DISPATCH_ENABLED", True)
            if simulate_enabled else nullcontext()
        )
        with permission, patch.object(self.runner, "_now", return_value=NOW), patch.object(
            self.runner.handoff, "_git_value", side_effect=self._git_value
        ), patch.object(self.runner, "generate_tool_free_text", side_effect=generator) as send:
            result = self.runner.run_openai_pilot(
                preflight=self.preflight,
                authorization=self.authorization,
                endpoint_map=self.endpoint_map,
                workspace=self.workspace,
                output=self.output,
                report_path=self.workspace / "labor-report.json",
                matrix_path=self.workspace / "claim-matrix.json",
                input_path=self.workspace / "triage-input.md",
                api_key="chave-de-teste",
            )
            return result, send.call_args_list

    def test_authorized_flow_reuses_agents_and_publishes_private_review_result(self) -> None:
        replies = iter((self.artifacts["report-narrative.md"], self.artifacts["triage.md"]))
        outputs, calls = self.run_pilot(lambda prompt, model, key: next(replies))
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call.args[1:] == ("modelo-exemplo", "chave-de-teste") for call in calls))
        self.assertEqual(
            tuple(path.name for path in outputs),
            ("report-narrative.md", "0000000-00.2026.5.12.0000-triagem.md",
             "fontes-triagem.json", "issue-route.json"),
        )
        self.assertEqual(outputs[0].read_text(encoding="utf-8"), self.artifacts["report-narrative.md"])
        self.assertEqual(outputs[1].read_text(encoding="utf-8"), self.artifacts["triage.md"])
        summary = json.loads((self.output / "pilot-run-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["model_provider"], "openai_api")
        self.assertEqual(summary["model_id"], "modelo-exemplo")
        self.assertEqual(summary["status"], "pending_legal_review")
        self.assertEqual(summary["passed_handoff_gates"], 3)
        self.assertFalse(summary["external_actions_allowed"])
        self.assertEqual(summary["authorization_scope_digest"], "b" * 64)
        for path in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_real_case_dispatch_remains_disabled_even_with_declared_go(self) -> None:
        with self.assertRaisesRegex(self.runner.OpenAIPilotError, "desabilitado"):
            self.run_pilot(
                lambda prompt, model, key: self.fail("rede bloqueada"),
                simulate_enabled=False,
            )
        self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_api_authorization_prevents_staging_and_network(self) -> None:
        self.authorization = None
        with self.assertRaises(self.runner.OpenAIPilotError):
            self.run_pilot(lambda prompt, model, key: self.fail("rede não autorizada"))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_expired_api_authorization_prevents_staging_and_network(self) -> None:
        self.authorization["valid_until"] = "2026-09-21T13:00:00Z"
        with self.assertRaises(self.runner.OpenAIPilotError):
            self.run_pilot(lambda prompt, model, key: self.fail("rede não autorizada"))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_case_mismatch_prevents_network(self) -> None:
        self.preflight["case"]["case_number"] = "0000001-00.2026.5.12.0000"
        with self.assertRaises(self.runner.OpenAIPilotError):
            self.run_pilot(lambda prompt, model, key: self.fail("rede não autorizada"))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_existing_output_prevents_network_without_overwrite(self) -> None:
        existing = self.output / "preservar.txt"
        existing.write_text("manter", encoding="utf-8")
        with self.assertRaises(self.runner.OpenAIPilotError):
            self.run_pilot(lambda prompt, model, key: self.fail("rede não autorizada"))
        self.assertEqual(existing.read_text(encoding="utf-8"), "manter")

    def test_arbitrary_valid_case_is_not_forced_to_synthetic_fixture(self) -> None:
        report_path = self.workspace / "labor-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["positions"][0]["summary"] = "Alegação trabalhista de teste"
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        matrix = json.loads((self.workspace / "claim-matrix.json").read_text(encoding="utf-8"))
        matrix["claims"][0]["claimant_position"]["summary"] = report["positions"][0]["summary"]
        (self.workspace / "claim-matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
        )
        triage_input = importlib.import_module("build_superjurista_triage_input").build_triage_input(
            report, matrix
        )
        (self.workspace / "triage-input.md").write_text(triage_input, encoding="utf-8")
        with self.assertRaises(self.runner.OpenAIPilotError):
            self.run_pilot(lambda prompt, model, key: "narrativa inválida")
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"labor-report.json", "claim-matrix.json", "triage-input.md"},
        )


if __name__ == "__main__":
    unittest.main()
