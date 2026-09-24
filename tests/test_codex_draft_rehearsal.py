from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class CodexDraftRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "analise"
        self.output = Path(self.temporary.name) / "minuta"
        for directory in (self.source, self.output):
            directory.mkdir(mode=0o700)
            os.chmod(directory, 0o700)
        analyzer = importlib.import_module("run_codex_claim_analysis_rehearsal")
        analyzer.run_codex_claim_analysis_rehearsal(
            self.source, synthetic_rehearsal=True,
            text_generator=self.analysis_response, model_id="modelo-analise-teste",
        )
        self.prompts = []

    @staticmethod
    def analysis_response(_prompt: str) -> str:
        return json.dumps({
            "schema_version": 1,
            "analyses": [{
                "analysis_id": "ANL-001", "claim_id": "CLM-001",
                "facts_found": [], "evidence_ids": ["EVD-001"],
                "evidence_assessment": ["O registro sintético ainda não foi revisado."],
                "applicable_rules": [], "precedent_source_ids": [],
                "reasoning": "As alegações são divergentes e falta revisão das fontes.",
                "proposed_outcome": "pending_human_review",
                "limitations": ["Falta revisão probatória e jurídica."],
            }],
        }, ensure_ascii=False)

    def disposition_response(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps({
            "schema_version": 1,
            "items": [{
                "disposition_id": "DSP-001", "claim_id": "CLM-001",
                "outcome": "pending_human_review",
                "command": "Nenhum comando dispositivo pode ser emitido antes da revisão humana.",
                "period": "not_applicable", "effects": [],
                "calculation_criteria": [], "source_analysis_id": "ANL-001",
            }],
        }, ensure_ascii=False)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("run_codex_draft_rehearsal"))
        return importlib.import_module("run_codex_draft_rehearsal")

    def run_rehearsal(self, generator=None):
        return self.api().run_codex_draft_rehearsal(
            self.output, analysis_workspace=self.source,
            synthetic_rehearsal=True, model_id="modelo-minuta-teste",
            expected_analysis_model_id="modelo-analise-teste",
            expected_analysis_mode="simulated",
            text_generator=generator or self.disposition_response,
        )

    def test_publishes_linked_pending_disposition_and_rendered_draft_privately(self):
        result = self.run_rehearsal()

        self.assertEqual(result, (self.output / "disposition-matrix.json").resolve())
        self.assertEqual(len(self.prompts), 1)
        self.assertIn("<claim-analysis.json>", self.prompts[0])
        self.assertIn("<claim-matrix.json>", self.prompts[0])
        self.assertIn("pending_human_review", self.prompts[0])
        self.assertEqual(
            {path.name for path in self.output.iterdir()},
            {"disposition-matrix.json", "judgment-draft.md", "draft-rehearsal-summary.json"},
        )
        self.assertEqual({stat.S_IMODE(path.stat().st_mode) for path in self.output.iterdir()}, {0o600})
        draft = (self.output / "judgment-draft.md").read_text(encoding="utf-8")
        self.assertIn("Nenhum comando dispositivo pode ser emitido antes da revisão humana.", draft)
        self.assertNotIn("Condeno", draft)
        summary = json.loads((self.output / "draft-rehearsal-summary.json").read_text())
        self.assertEqual(summary["execution_mode"], "simulated")
        self.assertEqual(summary["gate_status"], "passed")
        self.assertEqual(summary["analysis_sha256"], hashlib.sha256(
            (self.source / "claim-analysis.json").read_bytes()
        ).hexdigest())

    def test_refuses_merits_command_without_publishing_any_output(self):
        def invalid(prompt: str) -> str:
            value = json.loads(self.disposition_response(prompt))
            value["items"][0]["outcome"] = "granted"
            value["items"][0]["command"] = "Condeno a reclamada ao pagamento."
            return json.dumps(value, ensure_ascii=False)

        with self.assertRaises(self.api().CodexDraftRehearsalError):
            self.run_rehearsal(invalid)
        self.assertFalse(any(self.output.iterdir()))

    def test_malformed_disposition_is_rejected_without_leaving_output(self):
        with self.assertRaises(self.api().CodexDraftRehearsalError):
            self.run_rehearsal(lambda _: '{"schema_version": 1, "items": ["inválido"]}')
        self.assertFalse(any(self.output.iterdir()))

    def test_refuses_changed_analysis_before_model_dispatch(self):
        path = self.source / "claim-analysis.json"
        path.write_bytes(path.read_bytes() + b" ")

        with self.assertRaises(self.api().CodexDraftRehearsalError):
            self.run_rehearsal()
        self.assertEqual(self.prompts, [])
        self.assertFalse(any(self.output.iterdir()))

    def test_requires_explicit_synthetic_mode_before_model_dispatch(self):
        with self.assertRaises(self.api().CodexDraftRehearsalError):
            self.api().run_codex_draft_rehearsal(
                self.output, analysis_workspace=self.source,
                model_id="modelo-minuta-teste",
                expected_analysis_model_id="modelo-analise-teste",
                expected_analysis_mode="simulated",
                text_generator=self.disposition_response,
            )
        self.assertEqual(self.prompts, [])
        self.assertFalse(any(self.output.iterdir()))

    def test_import_refuses_changed_draft_before_publishing_checkpoint(self):
        from tests.test_trt12_extraction_gate import (
            SCOPE_DIGEST, SOURCE_FINGERPRINT, TRT12ExtractionGateTest,
        )

        case = TRT12ExtractionGateTest()
        case.setUp()
        try:
            state, context, payload_dir = case.prepare_fixture_claim_analysis_checkpoint()
            claim_importer = importlib.import_module("import_codex_claim_analysis_rehearsal")
            state = claim_importer.import_codex_claim_analysis_rehearsal(
                rehearsal_workspace=self.source, workspace=case.workspace,
                plan=case.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, authorization_scope_digest=SCOPE_DIGEST,
                payload_dir=payload_dir, expected_model_id="modelo-analise-teste",
                expected_execution_mode="simulated", attempt=1,
            )
            (case.workspace / "disposition-matrix.json").unlink()
            (case.workspace / "judgment-draft.md").unlink()
            self.run_rehearsal()
            draft_path = self.output / "judgment-draft.md"
            draft_path.write_bytes(draft_path.read_bytes() + b"\n")
            importer = importlib.import_module("import_codex_draft_rehearsal")

            with self.assertRaises(importer.CodexDraftImportError):
                importer.import_codex_draft_rehearsal(
                    rehearsal_workspace=self.output, analysis_workspace=self.source,
                    workspace=case.workspace, plan=case.plan, state=state,
                    source_fingerprint=SOURCE_FINGERPRINT, context=context,
                    authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                    expected_model_id="modelo-minuta-teste",
                    expected_analysis_model_id="modelo-analise-teste",
                    expected_execution_mode="simulated", expected_analysis_mode="simulated",
                    attempt=1,
                )
            self.assertFalse((case.workspace / "disposition-matrix.json").exists())
            self.assertFalse((case.workspace / "judgment-draft.md").exists())
        finally:
            case.doCleanups()


if __name__ == "__main__":
    unittest.main()
