from __future__ import annotations

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


class TRT12HandoffGateTest(unittest.TestCase):
    def modules(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("trt12_handoff_gate") is None:
            self.fail("o validador de checkpoints do TRT12 não existe")
        return (
            importlib.import_module("trt12_handoff_gate"),
            importlib.import_module("resumable_pipeline"),
            importlib.import_module("resolve_runtime_pipeline"),
            importlib.import_module("run_synthetic_pipeline"),
        )

    def plan(self, resolver, include_route=False):
        stages = [
            {
                "id": "prepare-triage-input",
                "capability": "build-source-linked-agent-input",
                "depends_on": [],
                "condition": "always",
                "outputs": ["{workspace}/triage-input.md"],
                "gate": "triage-input-custody",
            },
            {
                "id": "narrate-record",
                "capability": "narrate-source-linked-record",
                "depends_on": ["prepare-triage-input"],
                "condition": "always",
                "outputs": ["{workspace}/report-narrative.md"],
                "gate": "report-narrative-coverage",
            },
        ]
        gates = {
            "triage-input-custody": {"kind": "deterministic", "target": "triage-input"},
            "report-narrative-coverage": {
                "kind": "deterministic", "target": "report-narrative"
            },
        }
        if include_route:
            gates["route-coverage"] = {"kind": "contract", "target": "issue-route"}
            stages.append({
                "id": "route-claims",
                "capability": "route-claim-work",
                "depends_on": ["narrate-record"],
                "condition": "always",
                "outputs": [
                    "{workspace}/{case_number}-triagem.md",
                    "{workspace}/fontes-triagem.json",
                    "{workspace}/issue-route.json",
                ],
                "gate": "route-coverage",
            })
        contract = resolver.normalize_manifest({
            "schema_version": 1,
            "pipeline": "ensaio-handoff-trt12",
            "profile": "trt12",
            "retry_policy": {"max_attempts": 2, "on_exhausted": "stop"},
            "gates": gates,
            "stages": stages,
        })
        return {
            "schema_version": 1,
            "runtime": "codex",
            "runtime_adapter": {"dispatch": "agent"},
            "contract_digest": resolver.contract_digest(contract),
            "contract": contract,
        }

    def test_synthetic_handoff_can_be_checkpointed_and_resumed(self):
        gate_module, resume, resolver, runner = self.modules()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            runner.run_synthetic_pipeline("codex", FIXTURE, workspace)
            plan = self.plan(resolver)
            state = resume.new_execution_state(plan, SOURCE_FINGERPRINT)
            validator = gate_module.make_handoff_gate(workspace)
            context = {"case_number": "0000000-00.2026.5.12.0000"}

            for stage_id in ("prepare-triage-input", "narrate-record"):
                state = resume.record_stage_acceptance(
                    plan,
                    workspace=workspace,
                    state=state,
                    stage_id=stage_id,
                    source_fingerprint=SOURCE_FINGERPRINT,
                    context=context,
                    gate_validator=validator,
                    attempt=1,
                )
            result = resume.plan_resume(
                plan,
                workspace=workspace,
                state=state,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=context,
                gate_validator=validator,
            )

        self.assertEqual(
            result["reused_stages"], ["prepare-triage-input", "narrate-record"]
        )
        self.assertEqual(result["pending_stages"], [])

    def test_route_claims_can_be_checkpointed_from_inherited_triage(self):
        gate_module, resume, resolver, runner = self.modules()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            runner.run_synthetic_pipeline("codex", FIXTURE, workspace)
            plan = self.plan(resolver, include_route=True)
            state = resume.new_execution_state(plan, SOURCE_FINGERPRINT)
            validator = gate_module.make_handoff_gate(workspace)
            context = {"case_number": "0000000-00.2026.5.12.0000"}

            for stage_id in ("prepare-triage-input", "narrate-record", "route-claims"):
                state = resume.record_stage_acceptance(
                    plan,
                    workspace=workspace,
                    state=state,
                    stage_id=stage_id,
                    source_fingerprint=SOURCE_FINGERPRINT,
                    context=context,
                    gate_validator=validator,
                    attempt=1,
                )

        self.assertEqual(
            [record["id"] for record in state["stages"]],
            ["prepare-triage-input", "narrate-record", "route-claims"],
        )

    def test_route_claims_rejects_artifact_divergent_from_triage(self):
        gate_module, resume, resolver, runner = self.modules()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            runner.run_synthetic_pipeline("codex", FIXTURE, workspace)
            route_path = workspace / "issue-route.json"
            route = json.loads(route_path.read_text(encoding="utf-8"))
            route["routes"][0]["route_reason"] = "Justificativa adulterada."
            route_path.write_text(json.dumps(route), encoding="utf-8")
            plan = self.plan(resolver, include_route=True)
            state = resume.new_execution_state(plan, SOURCE_FINGERPRINT)
            validator = gate_module.make_handoff_gate(workspace)
            context = {"case_number": "0000000-00.2026.5.12.0000"}

            for stage_id in ("prepare-triage-input", "narrate-record"):
                state = resume.record_stage_acceptance(
                    plan,
                    workspace=workspace,
                    state=state,
                    stage_id=stage_id,
                    source_fingerprint=SOURCE_FINGERPRINT,
                    context=context,
                    gate_validator=validator,
                    attempt=1,
                )
            with self.assertRaisesRegex(resume.ResumeContractError, "content gate failed"):
                resume.record_stage_acceptance(
                    plan,
                    workspace=workspace,
                    state=state,
                    stage_id="route-claims",
                    source_fingerprint=SOURCE_FINGERPRINT,
                    context=context,
                    gate_validator=validator,
                    attempt=1,
                )

    def test_symlinked_source_report_cannot_back_protected_input(self):
        gate_module, resume, resolver, runner = self.modules()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            runner.run_synthetic_pipeline("codex", FIXTURE, workspace)
            report_path = workspace / "labor-report.json"
            copied = workspace / "copied-report.json"
            copied.write_bytes(report_path.read_bytes())
            report_path.unlink()
            report_path.symlink_to(copied)
            plan = self.plan(resolver)
            state = resume.new_execution_state(plan, SOURCE_FINGERPRINT)

            with self.assertRaisesRegex(resume.ResumeContractError, "content gate failed"):
                resume.record_stage_acceptance(
                    plan,
                    workspace=workspace,
                    state=state,
                    stage_id="prepare-triage-input",
                    source_fingerprint=SOURCE_FINGERPRINT,
                    context={"case_number": "0000000-00.2026.5.12.0000"},
                    gate_validator=gate_module.make_handoff_gate(workspace),
                    attempt=1,
                )


if __name__ == "__main__":
    unittest.main()
