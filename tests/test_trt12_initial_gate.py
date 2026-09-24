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


class TRT12InitialGateTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("trt12_initial_gate") is None:
            self.fail("o controle inicial do TRT12 não existe")
        self.gate = importlib.import_module("trt12_initial_gate")
        self.resume = importlib.import_module("resumable_pipeline")
        runner = importlib.import_module("run_synthetic_pipeline")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        runner.run_synthetic_pipeline("codex", FIXTURE, self.workspace)
        self.plan = runner._resolve_plan("codex")
        self.fingerprint = hashlib.sha256(
            (self.workspace / "source-manifest.json").read_bytes()
        ).hexdigest()

    def test_current_profile_checkpoint_is_reusable_in_the_full_pipeline(self):
        state = self.resume.new_execution_state(self.plan, self.fingerprint)
        validator = self.gate.make_initial_gate(self.workspace, self.plan)
        state = self.resume.record_stage_acceptance(
            self.plan,
            workspace=self.workspace,
            state=state,
            stage_id="prepare-profile",
            source_fingerprint=self.fingerprint,
            context={"case_number": "0000000-00.2026.5.12.0000"},
            gate_validator=validator,
            attempt=1,
        )
        resume = self.resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=state,
            source_fingerprint=self.fingerprint,
            context={"case_number": "0000000-00.2026.5.12.0000"},
            gate_validator=validator,
        )
        self.assertEqual(resume["reused_stages"], ["prepare-profile"])
        self.assertEqual(resume["next_stage"], "acquire-case")

    def test_cross_tribunal_case_cannot_receive_profile_checkpoint(self):
        path = self.workspace / "case-context.json"
        context = json.loads(path.read_text(encoding="utf-8"))
        context["court"] = "TRT2"
        path.write_text(json.dumps(context), encoding="utf-8")
        validator = self.gate.make_initial_gate(self.workspace, self.plan)
        state = self.resume.new_execution_state(self.plan, self.fingerprint)
        with self.assertRaisesRegex(self.resume.ResumeContractError, "content gate failed"):
            self.resume.record_stage_acceptance(
                self.plan,
                workspace=self.workspace,
                state=state,
                stage_id="prepare-profile",
                source_fingerprint=self.fingerprint,
                context={"case_number": "0000000-00.2026.5.12.0000"},
                gate_validator=validator,
                attempt=1,
            )

    def test_profile_accepts_a_safe_segment_manifest_name(self):
        path = self.workspace / "case-context.json"
        context = json.loads(path.read_text(encoding="utf-8"))
        context["source_manifest"] = "document-segments.json"
        path.write_text(json.dumps(context), encoding="utf-8")
        stage = self.plan["contract"]["stages"][0]
        outputs = (
            (self.workspace / "case-context.json").resolve(),
            (self.workspace / "execution-manifest.json").resolve(),
        )
        self.assertTrue(self.gate.make_initial_gate(self.workspace, self.plan)(stage, outputs))


if __name__ == "__main__":
    unittest.main()
