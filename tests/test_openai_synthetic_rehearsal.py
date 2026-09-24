from __future__ import annotations

import importlib
import importlib.util
import json
import stat
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


class FakeResponse:
    status = 200

    def __init__(self, text: str) -> None:
        self.body = json.dumps({
            "object": "response", "status": "completed", "error": None,
            "incomplete_details": None, "tools": [], "tool_choice": "none", "store": False,
            "output": [{
                "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }],
        }).encode("utf-8")

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class FakeConnection:
    def __init__(self, text: str) -> None:
        self.response = FakeResponse(text)
        self.request_details = None
        self.closed = False

    def request(self, method: str, path: str, body: bytes, headers: dict) -> None:
        self.request_details = (method, path, json.loads(body), headers)

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


class OpenAISyntheticRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("run_openai_synthetic_rehearsal") is None:
            self.fail("o ensaio sintético pela API não existe")
        self.runner = importlib.import_module("run_openai_synthetic_rehearsal")
        self.transport = importlib.import_module("openai_tool_free_transport")
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        importlib.import_module("prepare_codex_agent_rehearsal").prepare_codex_agent_rehearsal(
            self.workspace
        )

    def test_two_agent_outputs_use_the_existing_validators_and_no_tool_requests(self) -> None:
        connections = [
            FakeConnection(self.fixture["report-narrative.md"]),
            FakeConnection(self.fixture["triage.md"]),
        ]
        stages = []
        real_gate_factory = importlib.import_module("trt12_handoff_gate").make_handoff_gate

        def observed_gate(workspace: Path):
            real_gate = real_gate_factory(workspace)

            def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
                stages.append(stage["id"])
                return real_gate(stage, outputs)

            return validate

        with patch.object(
            self.transport.http.client, "HTTPSConnection", side_effect=connections
        ) as connect, patch.object(
            self.runner, "make_handoff_gate", side_effect=observed_gate, create=True
        ):
            outputs = self.runner.run_openai_synthetic_rehearsal(
                self.workspace, "modelo-exemplo", "chave-de-teste"
            )

        self.assertEqual(connect.call_count, 2)
        self.assertEqual(stages, ["prepare-triage-input", "narrate-record", "route-claims"])
        self.assertEqual(
            tuple(path.name for path in outputs),
            ("report-narrative.md", f"{CASE_NUMBER}-triagem.md", "fontes-triagem.json", "issue-route.json"),
        )
        self.assertEqual(outputs[0].read_text(encoding="utf-8"), self.fixture["report-narrative.md"])
        self.assertEqual(outputs[1].read_text(encoding="utf-8"), self.fixture["triage.md"])
        self.assertEqual(json.loads(outputs[3].read_text(encoding="utf-8")), self.fixture["issue-route.json"])
        for connection in connections:
            method, path, body, headers = connection.request_details
            self.assertEqual((method, path), ("POST", "/v1/responses"))
            self.assertEqual(body["tools"], [])
            self.assertEqual(body["tool_choice"], "none")
            self.assertIs(body["store"], False)
            self.assertEqual(body["model"], "modelo-exemplo")
            self.assertEqual(headers["Authorization"], "Bearer chave-de-teste")
            self.assertTrue(connection.closed)
        self.assertIn("relator-marmelstein-trt12", connections[0].request_details[2]["input"])
        self.assertIn("triador-processual-trt12", connections[1].request_details[2]["input"])

    def test_modified_synthetic_case_is_rejected_before_any_request(self) -> None:
        report_path = self.workspace / "labor-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["positions"][0]["summary"] = "Outra alegação"
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        with patch.object(self.transport.http.client, "HTTPSConnection") as connect:
            with self.assertRaises(self.runner.OpenAISyntheticRehearsalError):
                self.runner.run_openai_synthetic_rehearsal(
                    self.workspace, "modelo-exemplo", "chave-de-teste"
                )
        connect.assert_not_called()
        self.assertFalse((self.workspace / "report-narrative.md").exists())

    def test_invalid_first_response_stops_before_second_request(self) -> None:
        connection = FakeConnection("relatório sem estrutura")
        with patch.object(
            self.transport.http.client, "HTTPSConnection", return_value=connection
        ) as connect:
            with self.assertRaises(self.runner.OpenAISyntheticRehearsalError):
                self.runner.run_openai_synthetic_rehearsal(
                    self.workspace, "modelo-exemplo", "chave-de-teste"
                )
        self.assertEqual(connect.call_count, 1)
        self.assertFalse((self.workspace / "report-narrative.md").exists())

    def test_failed_input_checkpoint_prevents_the_first_request(self) -> None:
        with patch.object(
            self.runner, "make_handoff_gate", return_value=lambda stage, outputs: False,
            create=True,
        ), patch.object(self.transport.http.client, "HTTPSConnection") as connect:
            with self.assertRaisesRegex(
                self.runner.OpenAISyntheticRehearsalError, "custódia"
            ):
                self.runner.run_openai_synthetic_rehearsal(
                    self.workspace, "modelo-exemplo", "chave-de-teste"
                )
        connect.assert_not_called()

    def test_existing_output_is_preserved_without_a_request(self) -> None:
        output = self.workspace / "report-narrative.md"
        output.write_text("preservar", encoding="utf-8")
        with patch.object(self.transport.http.client, "HTTPSConnection") as connect:
            with self.assertRaises(self.runner.OpenAISyntheticRehearsalError):
                self.runner.run_openai_synthetic_rehearsal(
                    self.workspace, "modelo-exemplo", "chave-de-teste"
                )
        connect.assert_not_called()
        self.assertEqual(output.read_text(encoding="utf-8"), "preservar")

    def test_non_private_workspace_is_rejected_before_a_request(self) -> None:
        self.workspace.chmod(0o755)
        with patch.object(self.transport.http.client, "HTTPSConnection") as connect:
            with self.assertRaisesRegex(
                self.runner.OpenAISyntheticRehearsalError, "privado"
            ):
                self.runner.run_openai_synthetic_rehearsal(
                    self.workspace, "modelo-exemplo", "chave-de-teste"
                )
        connect.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.workspace.stat().st_mode), 0o755)

    def test_existing_triage_output_blocks_the_first_request(self) -> None:
        output = self.workspace / "issue-route.json"
        output.write_text("preservar", encoding="utf-8")
        with patch.object(self.transport.http.client, "HTTPSConnection") as connect:
            with self.assertRaises(self.runner.OpenAISyntheticRehearsalError):
                self.runner.run_openai_synthetic_rehearsal(
                    self.workspace, "modelo-exemplo", "chave-de-teste"
                )
        connect.assert_not_called()
        self.assertEqual(output.read_text(encoding="utf-8"), "preservar")

    def test_cli_requires_explicit_synthetic_mode_before_reading_credentials(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "run_openai_synthetic_rehearsal.py"),
                "--workspace", str(self.workspace), "--model", "modelo-exemplo",
            ],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--synthetic-rehearsal", result.stderr)
        self.assertFalse((self.workspace / "report-narrative.md").exists())


if __name__ == "__main__":
    unittest.main()
