from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import tests.test_pilot_preflight as pilot_fixtures


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCHEMA = ROOT / "runtime/operations/openai-api-authorization.v1.schema.json"
NOW = datetime(2026, 9, 21, 13, tzinfo=timezone.utc)


class OpenAIAPIAuthorizationTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("validate_openai_api_authorization") is None:
            self.fail("o verificador de autorização da API não existe")
        self.api = importlib.import_module("validate_openai_api_authorization")
        self.fixture = pilot_fixtures.PilotPreflightTest()
        self.preflight = self.fixture.preflight(self.fixture.endpoint_map())
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

    def test_valid_separate_record_is_linked_but_not_a_pilot_go(self) -> None:
        result = self.api.validate_openai_api_authorization(
            self.authorization, self.preflight, now=NOW
        )
        self.assertEqual(result, {
            "status": "authorization_linked_not_pilot_go",
            "provider": "openai_api",
            "surface": "responses",
            "pilot_id": "PILOT-001",
            "case_reference_digest": "a" * 64,
            "model_id": "modelo-exemplo",
        })

    def test_codex_cli_permission_cannot_replace_explicit_api_record(self) -> None:
        record = dict(self.authorization)
        record["provider"] = "codex"
        with self.assertRaises(self.api.OpenAIAPIAuthorizationError):
            self.api.validate_openai_api_authorization(record, self.preflight, now=NOW)

    def test_other_case_scope_or_classification_is_rejected(self) -> None:
        for field, value in (
            ("pilot_id", "PILOT-OTHER"),
            ("case_reference_digest", "f" * 64),
            ("authorization_scope_digest", "f" * 64),
            ("access_classification", "restricted_authorized"),
        ):
            with self.subTest(field=field):
                record = json.loads(json.dumps(self.authorization))
                record[field] = value
                with self.assertRaises(self.api.OpenAIAPIAuthorizationError):
                    self.api.validate_openai_api_authorization(record, self.preflight, now=NOW)

    def test_expired_or_out_of_preflight_window_is_rejected(self) -> None:
        for field, value in (
            ("approved_at", "2026-09-21T11:59:59Z"),
            ("approved_at", "2026-09-21T13:00:01Z"),
            ("valid_until", "2026-09-21T13:00:00Z"),
            ("valid_until", "2026-10-01T12:00:00Z"),
        ):
            with self.subTest(field=field):
                record = json.loads(json.dumps(self.authorization))
                record[field] = value
                with self.assertRaises(self.api.OpenAIAPIAuthorizationError):
                    self.api.validate_openai_api_authorization(record, self.preflight, now=NOW)

    def test_missing_review_or_tool_free_controls_is_rejected(self) -> None:
        for path, value in (
            (("provider_terms_digest",), None),
            (("request_controls", "tools_allowed"), True),
            (("request_controls", "response_storage_allowed"), True),
            (("request_controls", "external_actions_allowed"), True),
        ):
            with self.subTest(path=path):
                record = json.loads(json.dumps(self.authorization))
                target = record
                for field in path[:-1]:
                    target = target[field]
                if value is None:
                    del target[path[-1]]
                else:
                    target[path[-1]] = value
                with self.assertRaises(self.api.OpenAIAPIAuthorizationError):
                    self.api.validate_openai_api_authorization(record, self.preflight, now=NOW)

    def test_only_recorded_data_steward_can_attest_api_authorization(self) -> None:
        for field in ("authorized_by", "provider_terms_reviewed_by"):
            with self.subTest(field=field):
                record = json.loads(json.dumps(self.authorization))
                record[field] = "OTHER-ACTOR"
                with self.assertRaises(self.api.OpenAIAPIAuthorizationError):
                    self.api.validate_openai_api_authorization(record, self.preflight, now=NOW)

    def test_case_analysis_must_be_in_requested_operations(self) -> None:
        self.preflight["controls"]["requested_operations"].remove("analyze")
        with self.assertRaises(self.api.OpenAIAPIAuthorizationError):
            self.api.validate_openai_api_authorization(
                self.authorization, self.preflight, now=NOW
            )

    def test_cli_refuses_unprotected_records_without_printing_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            preflight_path = base / "preflight.json"
            authorization_path = base / "authorization.json"
            preflight_path.write_text(json.dumps(self.preflight), encoding="utf-8")
            authorization_path.write_text(json.dumps(self.authorization), encoding="utf-8")
            preflight_path.chmod(0o600)
            authorization_path.chmod(0o644)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPTS / "validate_openai_api_authorization.py"),
                    "--preflight", str(preflight_path),
                    "--authorization", str(authorization_path),
                ],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("[NO-GO]", result.stderr)
            self.assertNotIn(self.authorization["authorization_scope_digest"], result.stderr)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
