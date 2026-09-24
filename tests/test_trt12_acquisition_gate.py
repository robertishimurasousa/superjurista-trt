from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"
SOURCE_FINGERPRINT = "a" * 64
SCOPE_DIGEST = hashlib.sha256(b"escopo sintetico autorizado").hexdigest()


class TRT12AcquisitionGateTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("trt12_acquisition_gate") is None:
            self.fail("o controle de aquisição TRT12 não existe")
        self.gate = importlib.import_module("trt12_acquisition_gate")
        self.initial = importlib.import_module("trt12_initial_gate")
        self.resume = importlib.import_module("resumable_pipeline")
        self.recovery = importlib.import_module("recover_pje_acquisition")
        runner = importlib.import_module("run_synthetic_pipeline")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        runner.run_synthetic_pipeline("codex", FIXTURE, self.workspace)
        self.plan = runner._resolve_plan("codex")
        self.payload = b"documento sintetico do PJe"
        self.payload_dir = self.workspace / "pje-payloads"
        self.payload_dir.mkdir()
        (self.payload_dir / "DOC-001.bin").write_bytes(self.payload)
        sha256 = hashlib.sha256(self.payload).hexdigest()
        self.index = {
            "schema_version": 1,
            "case": {
                "case_number": "0000000-00.2026.5.12.0000",
                "tribunal_code": "TRT12",
                "instance": 1,
                "court_unit": "Vara do Trabalho sintética",
                "task_id": "TASK-001",
            },
            "status": "complete",
            "page_count": 1,
            "documents": [{
                "document_id": "DOC-001",
                "filename": "doc-001.pdf",
                "mime_type": "application/pdf",
                "sha256": sha256,
                "source_locator": "evento sintetico 1",
                "download_status": "downloaded",
                "byte_count": len(self.payload),
            }],
            "gaps": [],
        }
        self.state = {
            "schema_version": 1,
            "case": {
                "case_number": "0000000-00.2026.5.12.0000",
                "tribunal_code": "TRT12",
                "instance": 1,
            },
            "authorization_scope_digest": SCOPE_DIGEST,
            "selection_mode": "all",
            "requested_document_ids": [],
            "max_attempts": 2,
            "catalog_digest": self.recovery._catalog_digest(self.index),
            "status": "complete",
            "acquisition_cycles": 1,
            "successful_documents": 1,
            "documents": [{
                "document_id": "DOC-001",
                "sha256": sha256,
                "attempt_count": 1,
                "status": "accepted",
                "relative_path": "DOC-001.bin",
                "byte_count": len(self.payload),
                "last_error": None,
            }],
        }
        self.save_inputs()

    def save_inputs(self):
        (self.workspace / "document-index.json").write_text(
            json.dumps(self.index), encoding="utf-8"
        )
        (self.workspace / "source-manifest.json").write_text(
            json.dumps(self.state), encoding="utf-8"
        )

    def validator(self):
        initial = self.initial.make_initial_gate(self.workspace, self.plan)
        acquisition = self.gate.make_acquisition_gate(
            self.workspace, SCOPE_DIGEST, self.payload_dir
        )
        return lambda stage, outputs: initial(stage, outputs) or acquisition(stage, outputs)

    def test_complete_verified_acquisition_records_second_global_checkpoint(self):
        validator = self.validator()
        state = self.resume.new_execution_state(self.plan, SOURCE_FINGERPRINT)
        for stage_id in ("prepare-profile", "acquire-case"):
            state = self.resume.record_stage_acceptance(
                self.plan,
                workspace=self.workspace,
                state=state,
                stage_id=stage_id,
                source_fingerprint=SOURCE_FINGERPRINT,
                context={"case_number": "0000000-00.2026.5.12.0000"},
                gate_validator=validator,
                attempt=1,
            )
        resumed = self.resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context={"case_number": "0000000-00.2026.5.12.0000"},
            gate_validator=validator,
        )
        self.assertEqual(resumed["reused_stages"], ["prepare-profile", "acquire-case"])
        self.assertEqual(resumed["next_stage"], "extract-record")

    def test_changed_payload_invalidates_acquisition(self):
        (self.payload_dir / "DOC-001.bin").write_bytes(b"conteudo alterado")
        stage = self.plan["contract"]["stages"][1]
        outputs = (
            (self.workspace / "document-index.json").resolve(),
            (self.workspace / "source-manifest.json").resolve(),
        )
        self.assertFalse(self.validator()(stage, outputs))

    def test_different_authorization_scope_invalidates_acquisition(self):
        stage = self.plan["contract"]["stages"][1]
        outputs = (
            (self.workspace / "document-index.json").resolve(),
            (self.workspace / "source-manifest.json").resolve(),
        )
        wrong_scope = self.gate.make_acquisition_gate(
            self.workspace, "b" * 64, self.payload_dir
        )
        self.assertFalse(wrong_scope(stage, outputs))

    def test_legacy_synthetic_manifest_does_not_claim_complete_acquisition(self):
        (self.workspace / "source-manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "authorization": "synthetic_fixture",
                "contains_personal_data": False,
                "contains_real_case_data": False,
            }),
            encoding="utf-8",
        )
        stage = self.plan["contract"]["stages"][1]
        outputs = (
            (self.workspace / "document-index.json").resolve(),
            (self.workspace / "source-manifest.json").resolve(),
        )
        self.assertFalse(self.validator()(stage, outputs))


if __name__ == "__main__":
    unittest.main()
