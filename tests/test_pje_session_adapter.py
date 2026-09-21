from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = ROOT / "runtime" / "providers" / "pje-session-contract.json"


class FakeSessionProbe:
    def __init__(
        self,
        api,
        observation,
        *,
        capabilities=("validate_session",),
        secret="private-session-value-that-must-not-leak",
    ) -> None:
        self.api = api
        self.observation = observation
        self.secret = secret
        self.descriptor = api.AdapterDescriptor(
            provider_id="fake-session",
            interface_id="pje_case_acquisition",
            interface_version=1,
            capabilities=capabilities,
            supported_tribunals=("TRT99",),
        )

    def probe_session(self, request):
        return self.observation


class PJeSessionAdapterTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("pje_session_adapter")
        except ModuleNotFoundError as error:
            self.fail(f"PJe session adapter module is missing: {error}")

    def check(self, api):
        return api.SessionCheck(
            tribunal_code="TRT99",
            instance=1,
            authorization_scope="authorized_synthetic_fixture",
        )

    def assess(self, api, observation, **probe_options):
        contract = api.load_session_contract(CONTRACT)
        return api.assess_pje_session(
            contract,
            FakeSessionProbe(api, observation, **probe_options),
            self.check(api),
        )

    def test_authenticated_marker_and_session_cookie_are_valid(self) -> None:
        api = self.api()
        result = self.assess(
            api,
            api.SessionObservation(
                http_status=200,
                markers=("authenticated",),
                cookie_names=("JSESSIONID",),
                header_names=(),
            ),
        )

        self.assertEqual(
            result,
            {
                "status": "valid",
                "reason_code": "authenticated",
                "provider_id": "fake-session",
                "tribunal_code": "TRT99",
                "instance": 1,
                "evidence": {
                    "http_status": 200,
                    "markers": ["authenticated"],
                    "cookie_names": ["JSESSIONID"],
                    "header_names": [],
                },
            },
        )

    def test_expired_marker_is_classified_without_retrying_login(self) -> None:
        api = self.api()
        result = self.assess(
            api,
            api.SessionObservation(
                http_status=200,
                markers=("session_expired",),
                cookie_names=(),
                header_names=(),
            ),
        )

        self.assertEqual(result["status"], "expired")
        self.assertEqual(result["reason_code"], "session_expired")

    def test_mfa_marker_is_classified_as_pending_mfa(self) -> None:
        api = self.api()
        result = self.assess(
            api,
            api.SessionObservation(
                http_status=200,
                markers=("mfa_required",),
                cookie_names=(),
                header_names=(),
            ),
        )

        self.assertEqual(result["status"], "mfa_required")
        self.assertEqual(result["reason_code"], "mfa_required")

    def test_forbidden_http_status_overrides_authenticated_marker(self) -> None:
        api = self.api()
        result = self.assess(
            api,
            api.SessionObservation(
                http_status=403,
                markers=("authenticated",),
                cookie_names=("JSESSIONID",),
                header_names=(),
            ),
        )

        self.assertEqual(result["status"], "unauthorized")
        self.assertEqual(result["reason_code"], "http_403")

    def test_conflicting_markers_fail_closed_as_unknown(self) -> None:
        api = self.api()
        result = self.assess(
            api,
            api.SessionObservation(
                http_status=200,
                markers=("authenticated", "mfa_required"),
                cookie_names=("JSESSIONID",),
                header_names=(),
            ),
        )

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason_code"], "conflicting_markers")

    def test_authenticated_marker_without_session_evidence_fails_closed(self) -> None:
        api = self.api()
        result = self.assess(
            api,
            api.SessionObservation(
                http_status=200,
                markers=("authenticated",),
                cookie_names=(),
                header_names=(),
            ),
        )

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason_code"], "missing_session_evidence")

    def test_unrecognized_marker_is_rejected_without_leaking_its_value(self) -> None:
        api = self.api()
        secret = "private-marker-value-1234567890"
        observation = api.SessionObservation(
            http_status=200,
            markers=(secret,),
            cookie_names=(),
            header_names=(),
        )

        with self.assertRaises(api.SessionContractViolation) as raised:
            self.assess(api, observation, secret=secret)

        self.assertNotIn(secret, str(raised.exception))

    def test_probe_without_validate_session_capability_is_rejected(self) -> None:
        api = self.api()
        observation = api.SessionObservation(
            http_status=200,
            markers=("authenticated",),
            cookie_names=("JSESSIONID",),
            header_names=(),
        )

        with self.assertRaisesRegex(api.SessionContractViolation, "validate_session"):
            self.assess(api, observation, capabilities=())

    def test_assessment_never_serializes_probe_secret(self) -> None:
        api = self.api()
        secret = "private-probe-secret-1234567890"
        contract = api.load_session_contract(CONTRACT)
        probe = FakeSessionProbe(
            api,
            api.SessionObservation(
                http_status=200,
                markers=("authenticated",),
                cookie_names=("JSESSIONID",),
                header_names=(),
            ),
            secret=secret,
        )

        result = api.assess_pje_session(contract, probe, self.check(api))

        self.assertNotIn(secret, json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
