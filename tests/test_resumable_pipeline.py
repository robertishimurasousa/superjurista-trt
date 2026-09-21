from __future__ import annotations

import copy
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SOURCE_FINGERPRINT = "a" * 64
STATE_SCHEMA = ROOT / "runtime" / "pipelines" / "execution-state.v1.schema.json"


class ResumablePipelineTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("resumable_pipeline")
        except ModuleNotFoundError as error:
            self.fail(f"resumable pipeline module is missing: {error}")

    def resolver(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("resolve_runtime_pipeline")

    def contract(self):
        resolver = self.resolver()
        return resolver.normalize_manifest(
            {
                "schema_version": 1,
                "pipeline": "resume-fixture",
                "profile": "trt12",
                "retry_policy": {"max_attempts": 2, "on_exhausted": "stop"},
                "gates": {
                    "gate-a": {"kind": "contract", "target": "artifact-a"},
                    "gate-b": {"kind": "contract", "target": "artifact-b"},
                    "gate-c": {"kind": "deterministic", "target": "artifact-c"},
                },
                "stages": [
                    {
                        "id": "stage-a",
                        "capability": "prepare",
                        "depends_on": [],
                        "condition": "always",
                        "outputs": ["{workspace}/artifact-a.json"],
                        "gate": "gate-a",
                    },
                    {
                        "id": "stage-b",
                        "capability": "analyze",
                        "depends_on": ["stage-a"],
                        "condition": "always",
                        "outputs": ["{workspace}/artifact-b.json"],
                        "gate": "gate-b",
                    },
                    {
                        "id": "stage-c",
                        "capability": "finish",
                        "depends_on": ["stage-b"],
                        "condition": "always",
                        "outputs": ["{workspace}/{case_number}-artifact-c.md"],
                        "gate": "gate-c",
                    },
                ],
            }
        )

    def plan(self, runtime):
        resolver = self.resolver()
        contract = self.contract()
        return {
            "schema_version": 1,
            "runtime": runtime,
            "runtime_adapter": {
                "dispatch": "Task" if runtime == "claude" else "agent",
            },
            "contract_digest": resolver.contract_digest(contract),
            "contract": contract,
        }

    def context(self):
        return {"case_number": "0000001-00.2026.5.12.0001"}

    def gate(self, stage, outputs):
        return all(path.read_text(encoding="utf-8").startswith("accepted:") for path in outputs)

    def write(self, workspace, name, content):
        path = workspace / name
        path.write_text(content, encoding="utf-8")
        return path

    def accept(self, module, plan, workspace, state, stage_id, attempt=1):
        return module.record_stage_acceptance(
            plan,
            workspace=workspace,
            state=state,
            stage_id=stage_id,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=self.context(),
            gate_validator=self.gate,
            attempt=attempt,
        )

    def test_interrupted_fixture_reuses_only_the_accepted_stage(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("codex")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)
            self.write(workspace, "artifact-a.json", "accepted: a")
            state = self.accept(module, plan, workspace, state, "stage-a")

            resume = module.plan_resume(
                plan,
                workspace=workspace,
                state=state,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=self.context(),
                gate_validator=self.gate,
            )

        self.assertEqual(resume["reused_stages"], ["stage-a"])
        self.assertEqual(resume["pending_stages"], ["stage-b", "stage-c"])
        self.assertEqual(resume["next_stage"], "stage-b")

    def test_claude_and_codex_share_resume_state_but_keep_dispatch(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            claude = self.plan("claude")
            codex = self.plan("codex")
            self.assertEqual(claude["contract_digest"], codex["contract_digest"])
            state = module.new_execution_state(claude, SOURCE_FINGERPRINT)
            self.write(workspace, "artifact-a.json", "accepted: a")
            state = self.accept(module, claude, workspace, state, "stage-a")

            results = {
                runtime: module.plan_resume(
                    plan,
                    workspace=workspace,
                    state=state,
                    source_fingerprint=SOURCE_FINGERPRINT,
                    context=self.context(),
                    gate_validator=self.gate,
                )
                for runtime, plan in (("claude", claude), ("codex", codex))
            }

        self.assertEqual(results["claude"]["reused_stages"], ["stage-a"])
        self.assertEqual(results["codex"]["reused_stages"], ["stage-a"])
        self.assertEqual(results["claude"]["dispatch"], "Task")
        self.assertEqual(results["codex"]["dispatch"], "agent")

    def test_modified_output_invalidates_the_stage_and_every_dependent_stage(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("codex")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)
            self.write(workspace, "artifact-a.json", "accepted: a")
            state = self.accept(module, plan, workspace, state, "stage-a")
            self.write(workspace, "artifact-b.json", "accepted: b")
            state = self.accept(module, plan, workspace, state, "stage-b")
            self.write(workspace, "artifact-a.json", "accepted: changed")

            resume = module.plan_resume(
                plan,
                workspace=workspace,
                state=state,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=self.context(),
                gate_validator=self.gate,
            )

        self.assertEqual(resume["reused_stages"], [])
        self.assertIn("output fingerprint changed", resume["stale_reasons"]["stage-a"])
        self.assertEqual(
            resume["stale_reasons"]["stage-b"],
            "dependency stage-a is not reusable",
        )

    def test_current_gate_failure_invalidates_unchanged_output(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("codex")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)
            output = self.write(workspace, "artifact-a.json", "accepted: a")
            state = self.accept(module, plan, workspace, state, "stage-a")

            def failing_gate(stage, outputs):
                self.assertEqual(outputs, (output.resolve(),))
                return False

            resume = module.plan_resume(
                plan,
                workspace=workspace,
                state=state,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=self.context(),
                gate_validator=failing_gate,
            )

        self.assertEqual(resume["reused_stages"], [])
        self.assertEqual(
            resume["stale_reasons"]["stage-a"],
            "current content gate failed",
        )

    def test_changed_source_fingerprint_invalidates_all_prior_acceptance(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("codex")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)
            self.write(workspace, "artifact-a.json", "accepted: a")
            state = self.accept(module, plan, workspace, state, "stage-a")

            resume = module.plan_resume(
                plan,
                workspace=workspace,
                state=state,
                source_fingerprint="b" * 64,
                context=self.context(),
                gate_validator=self.gate,
            )

        self.assertEqual(resume["reused_stages"], [])
        self.assertEqual(
            resume["stale_reasons"]["stage-a"],
            "source fingerprint changed",
        )

    def test_changed_contract_digest_invalidates_all_prior_acceptance(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("codex")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)
            self.write(workspace, "artifact-a.json", "accepted: a")
            state = self.accept(module, plan, workspace, state, "stage-a")
            changed_plan = copy.deepcopy(plan)
            changed_plan["contract"]["pipeline"] = "resume-fixture-v2"
            changed_plan["contract_digest"] = self.resolver().contract_digest(
                changed_plan["contract"]
            )

            resume = module.plan_resume(
                changed_plan,
                workspace=workspace,
                state=state,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=self.context(),
                gate_validator=self.gate,
            )

        self.assertEqual(resume["reused_stages"], [])
        self.assertEqual(
            resume["stale_reasons"]["stage-a"],
            "pipeline contract changed",
        )

    def test_stage_cannot_be_accepted_before_its_dependency(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("codex")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)
            self.write(workspace, "artifact-b.json", "accepted: b")

            with self.assertRaisesRegex(module.ResumeContractError, "dependency stage-a"):
                self.accept(module, plan, workspace, state, "stage-b")

    def test_stage_acceptance_requires_outputs_and_current_gate(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("codex")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)

            with self.assertRaisesRegex(module.ResumeContractError, "output is missing"):
                self.accept(module, plan, workspace, state, "stage-a")

            self.write(workspace, "artifact-a.json", "rejected: a")
            with self.assertRaisesRegex(module.ResumeContractError, "content gate"):
                self.accept(module, plan, workspace, state, "stage-a")

    def test_attempt_must_stay_inside_the_manifest_retry_limit(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("codex")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)
            self.write(workspace, "artifact-a.json", "accepted: a")

            with self.assertRaisesRegex(module.ResumeContractError, "attempt"):
                self.accept(module, plan, workspace, state, "stage-a", attempt=3)

    def test_state_round_trip_is_atomic_and_runtime_neutral(self) -> None:
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self.plan("claude")
            state = module.new_execution_state(plan, SOURCE_FINGERPRINT)
            self.write(workspace, "artifact-a.json", "accepted: a")
            state = self.accept(module, plan, workspace, state, "stage-a")
            state_path = workspace / "execution-state.json"

            module.save_execution_state(state_path, state)
            loaded = json.loads(state_path.read_text(encoding="utf-8"))

            schema_api = importlib.import_module("schema_validation")
            schema = schema_api.load_json(STATE_SCHEMA, "execution state schema")

        self.assertEqual(loaded, state)
        self.assertNotIn("runtime", loaded)
        self.assertNotIn("dispatch", loaded)
        self.assertEqual(schema_api.validate_schema_value(loaded, schema), [])


if __name__ == "__main__":
    unittest.main()
