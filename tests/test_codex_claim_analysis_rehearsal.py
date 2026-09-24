from __future__ import annotations

import hashlib
import importlib
import json
import os
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


class CodexClaimAnalysisRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        os.chmod(self.workspace, 0o700)
        self.prompts: list[str] = []

    def api(self):
        return importlib.import_module("run_codex_claim_analysis_rehearsal")

    def response(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps({
            "schema_version": 1,
            "analyses": [{
                "analysis_id": "ANL-001",
                "claim_id": "CLM-001",
                "facts_found": [],
                "evidence_ids": ["EVD-001"],
                "evidence_assessment": [
                    "O cartão de ponto sintético não teve seu valor probatório revisto."
                ],
                "applicable_rules": [],
                "precedent_source_ids": [],
                "reasoning": (
                    "A parte autora alega horas extras e a reclamada sustenta quitação; "
                    "a prova e a fonte jurídica ainda dependem de conferência."
                ),
                "proposed_outcome": "pending_human_review",
                "limitations": ["Revisão probatória e jurídica pendente."],
            }],
        }, ensure_ascii=False)

    def test_accepts_only_protected_synthetic_pending_analysis(self) -> None:
        output = self.api().run_codex_claim_analysis_rehearsal(
            self.workspace, synthetic_rehearsal=True,
            text_generator=self.response, model_id="modelo-teste",
        )

        self.assertEqual(output, (self.workspace / "claim-analysis.json").resolve())
        self.assertEqual(len(self.prompts), 1)
        self.assertIn("analisador-marmelstein-trt12", self.prompts[0])
        self.assertIn("CLM-001", self.prompts[0])
        self.assertNotIn("<claim-analysis.json>", self.prompts[0])
        instructions = self.prompts[0].split("<instrucoes_do_agente>", 1)[1].split(
            "</instrucoes_do_agente>", 1
        )[0]
        self.assertIn("fonte sintética", instructions)
        self.assertEqual(
            {path.name for path in self.workspace.iterdir()},
            {"claim-analysis.json", "claim-analysis-rehearsal-summary.json"},
        )
        self.assertEqual(
            {stat.S_IMODE(path.stat().st_mode) for path in self.workspace.iterdir()},
            {0o600},
        )
        summary = json.loads(
            (self.workspace / "claim-analysis-rehearsal-summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["execution_mode"], "simulated")
        self.assertEqual(summary["review_status"], "pending_human_review")
        self.assertEqual(summary["gate_status"], "passed")
        self.assertEqual(summary["fixture_sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        self.assertEqual(summary["analysis_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())

    def test_merits_conclusion_is_rejected_before_publication(self) -> None:
        def merits(prompt: str) -> str:
            value = json.loads(self.response(prompt))
            value["analyses"][0]["proposed_outcome"] = "granted"
            value["analyses"][0]["facts_found"] = ["Jornada comprovada."]
            return json.dumps(value, ensure_ascii=False)

        with self.assertRaises(self.api().CodexClaimAnalysisRehearsalError):
            self.api().run_codex_claim_analysis_rehearsal(
                self.workspace, synthetic_rehearsal=True,
                text_generator=merits, model_id="modelo-teste",
            )
        self.assertFalse(any(self.workspace.iterdir()))

    def test_unknown_evidence_is_rejected_before_publication(self) -> None:
        def unknown(prompt: str) -> str:
            value = json.loads(self.response(prompt))
            value["analyses"][0]["evidence_ids"] = ["EVD-999"]
            return json.dumps(value, ensure_ascii=False)

        with self.assertRaises(self.api().CodexClaimAnalysisRehearsalError):
            self.api().run_codex_claim_analysis_rehearsal(
                self.workspace, synthetic_rehearsal=True,
                text_generator=unknown, model_id="modelo-teste",
            )
        self.assertFalse(any(self.workspace.iterdir()))

    def test_without_synthetic_flag_or_with_existing_output_no_dispatch(self) -> None:
        with self.assertRaises(self.api().CodexClaimAnalysisRehearsalError):
            self.api().run_codex_claim_analysis_rehearsal(
                self.workspace, text_generator=self.response, model_id="modelo-teste",
            )
        self.assertEqual(self.prompts, [])
        existing = self.workspace / "preservar.txt"
        existing.write_text("manter", encoding="utf-8")
        with self.assertRaises(self.api().CodexClaimAnalysisRehearsalError):
            self.api().run_codex_claim_analysis_rehearsal(
                self.workspace, synthetic_rehearsal=True,
                text_generator=self.response, model_id="modelo-teste",
            )
        self.assertEqual(existing.read_text(encoding="utf-8"), "manter")
        self.assertEqual(self.prompts, [])

    def test_changed_fixture_is_refused_before_model_dispatch(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        fixture["artifacts"]["claim-matrix.json"]["claims"][0][
            "claimant_position"
        ]["summary"] = "Texto não pertencente à amostra sintética fixada."
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "altered-fixture.json"
            altered.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
            with patch.object(self.api(), "FIXTURE", altered):
                with self.assertRaises(self.api().CodexClaimAnalysisRehearsalError):
                    self.api().run_codex_claim_analysis_rehearsal(
                        self.workspace, synthetic_rehearsal=True,
                        text_generator=self.response, model_id="modelo-teste",
                    )
        self.assertEqual(self.prompts, [])
        self.assertFalse(any(self.workspace.iterdir()))

    def test_cli_requires_synthetic_flag(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_codex_claim_analysis_rehearsal.py"),
             "--workspace", str(self.workspace), "--model", "modelo-teste"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--synthetic-rehearsal", result.stderr)
        self.assertFalse(any(self.workspace.iterdir()))


if __name__ == "__main__":
    unittest.main()
