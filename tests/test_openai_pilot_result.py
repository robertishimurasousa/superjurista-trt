from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import tests.test_openai_pilot as pilot_cases


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class OpenAIPilotResultTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("verify_openai_pilot_result") is None:
            self.fail("o verificador independente do piloto pela API não existe")
        self.verifier = importlib.import_module("verify_openai_pilot_result")
        self.pilot = pilot_cases.OpenAIPilotTest()
        self.pilot.setUp()
        self.addCleanup(self.pilot.doCleanups)
        replies = iter((
            self.pilot.artifacts["report-narrative.md"],
            self.pilot.artifacts["triage.md"],
        ))
        self.pilot.run_pilot(lambda prompt, model, key: next(replies))

    def test_valid_simulated_result_is_integrity_passed_but_pending_review(self) -> None:
        result = self.verifier.verify_openai_pilot_result(
            self.pilot.output, self.pilot.preflight, self.pilot.authorization
        )
        self.assertEqual(result, {
            "integrity": "passed",
            "status": "pending_legal_review",
            "passed_handoff_gates": 3,
            "pilot_id": "PILOT-001",
        })

    def test_changed_authorization_record_is_rejected(self) -> None:
        self.pilot.authorization["provider_terms_digest"] = "f" * 64
        with self.assertRaises(self.verifier.OpenAIPilotResultError):
            self.verifier.verify_openai_pilot_result(
                self.pilot.output, self.pilot.preflight, self.pilot.authorization
            )

    def test_changed_generated_text_is_rejected(self) -> None:
        path = self.pilot.output / "report-narrative.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nAlteração posterior", encoding="utf-8")
        with self.assertRaises(self.verifier.OpenAIPilotResultError):
            self.verifier.verify_openai_pilot_result(
                self.pilot.output, self.pilot.preflight, self.pilot.authorization
            )

    def test_summary_cannot_claim_another_model(self) -> None:
        path = self.pilot.output / "pilot-run-summary.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["model_id"] = "modelo-diferente"
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(self.verifier.OpenAIPilotResultError):
            self.verifier.verify_openai_pilot_result(
                self.pilot.output, self.pilot.preflight, self.pilot.authorization
            )

    def test_symlinked_generated_artifact_is_rejected(self) -> None:
        path = self.pilot.output / "report-narrative.md"
        target = self.pilot.workspace / "triage-input.md"
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(self.verifier.OpenAIPilotResultError):
            self.verifier.verify_openai_pilot_result(
                self.pilot.output, self.pilot.preflight, self.pilot.authorization
            )


if __name__ == "__main__":
    unittest.main()
