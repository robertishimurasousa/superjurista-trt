from __future__ import annotations

import copy
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tests.test_pje_har_map_review as har_fixtures


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
VALIDATOR = SCRIPTS / "validate_pilot_preflight.py"
SCHEMA = ROOT / "runtime" / "operations" / "pilot-preflight.v1.schema.json"
SANITIZATION_CONTRACT = (
    ROOT / "runtime" / "providers" / "har-sanitization-contract.json"
)
MAP_REVIEW_CONTRACT = ROOT / "runtime" / "providers" / "har-map-review-contract.json"


class PilotPreflightTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("validate_pilot_preflight")
        except ModuleNotFoundError as error:
            self.fail(f"pilot preflight validator is missing: {error}")

    def current_commit(self) -> str:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def endpoint_map(self) -> dict:
        fixture = har_fixtures.PJeHarMapReviewTest()
        report = fixture.valid_map()
        report["tribunal_code"] = "TRT12"
        return fixture.seal(report)

    def runtime_summary(self) -> dict:
        return {
            "artifact_count": 19,
            "global_gate_status": "passed",
            "contract_digest": "d" * 64,
            "shared_artifact_digest": "e" * 64,
        }

    def preflight(self, endpoint_map: dict) -> dict:
        return {
            "schema_version": 1,
            "pilot_id": "PILOT-001",
            "created_at": "2026-09-21T12:00:00Z",
            "tribunal_code": "TRT12",
            "instance": 1,
            "case": {
                "reference_digest": "a" * 64,
                "authorization_scope_digest": "b" * 64,
                "authorized": True,
                "access_classification": "public_or_authorized",
                "exceptional_access_required": False,
            },
            "roles": {
                "operator_id": "REPOSITORY-OWNER",
                "legal_reviewer_id": "LEGAL-REVIEWER-01",
                "incident_owner_id": "REPOSITORY-OWNER",
                "data_steward_id": "REPOSITORY-OWNER",
            },
            "evidence": {
                "development_commit": self.current_commit(),
                "branch": "development",
                "host_readiness_status": "ready",
                "host_readiness_digest": "c" * 64,
                "quality_gate_status": "passed",
                "claude_summary": self.runtime_summary(),
                "codex_summary": self.runtime_summary(),
                "endpoint_map_digest": endpoint_map["sanitized_digest"],
                "endpoint_map_reviewed_by": "ENDPOINT-REVIEWER-01",
                "endpoint_map_review_date": "2026-09-21",
            },
            "retention": {
                "raw_har_captured_at": "2026-09-21T12:00:00Z",
                "planned_review_close_by": "2026-09-30T12:00:00Z",
                "raw_har_delete_by": "2026-09-22T12:00:00Z",
                "raw_documents_delete_by": "2026-10-30T12:00:00Z",
                "derived_artifacts_delete_by": "2026-12-29T12:00:00Z",
                "incident_summary_delete_by": "2027-03-20T12:00:00Z",
            },
            "controls": {
                "one_case_only": True,
                "external_actions_allowed": False,
                "global_gate_enforced": True,
                "requested_operations": [
                    "acquire",
                    "classify",
                    "analyze",
                    "research",
                    "draft",
                    "review",
                ],
                "stop_conditions_acknowledged": True,
            },
        }

    def validate(self, preflight: dict, endpoint_map: dict, workspace: Path, output: Path):
        return self.api().validate_pilot_preflight(
            preflight=preflight,
            endpoint_map=endpoint_map,
            schema_path=SCHEMA,
            sanitization_contract_path=SANITIZATION_CONTRACT,
            map_review_contract_path=MAP_REVIEW_CONTRACT,
            repository_root=ROOT,
            workspace_path=workspace,
            output_path=output,
            current_branch="development",
            current_commit=self.current_commit(),
            working_tree_clean=True,
        )

    def test_complete_preflight_authorizes_only_a_local_controlled_pilot(self) -> None:
        endpoint_map = self.endpoint_map()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()

            result = self.validate(self.preflight(endpoint_map), endpoint_map, workspace, output)

        self.assertEqual(result["status"], "go_controlled_pilot")
        self.assertEqual(result["pilot_id"], "PILOT-001")
        self.assertFalse(result["external_actions_allowed"])
        self.assertEqual(result["case_reference_digest"], "a" * 64)
        self.assertNotIn(str(workspace), json.dumps(result))

    def test_sealed_or_exceptional_access_case_is_no_go(self) -> None:
        endpoint_map = self.endpoint_map()
        sealed = self.preflight(endpoint_map)
        sealed["case"]["access_classification"] = "sealed_authorized"
        exceptional = self.preflight(endpoint_map)
        exceptional["case"]["exceptional_access_required"] = True
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            for document, expected in ((sealed, "sealed"), (exceptional, "exceptional")):
                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(self.api().PilotPreflightError, expected):
                        self.validate(document, endpoint_map, workspace, output)

    def test_retention_deadlines_cannot_exceed_approved_limits(self) -> None:
        endpoint_map = self.endpoint_map()
        cases = (
            ("raw_har_delete_by", "2026-09-22T12:00:01Z", "raw HAR"),
            ("raw_documents_delete_by", "2026-10-30T12:00:01Z", "raw documents"),
            ("derived_artifacts_delete_by", "2026-12-29T12:00:01Z", "derived"),
            ("incident_summary_delete_by", "2027-03-20T12:00:01Z", "incident"),
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            for field, value, expected in cases:
                document = self.preflight(endpoint_map)
                document["retention"][field] = value
                with self.subTest(field=field):
                    with self.assertRaisesRegex(self.api().PilotPreflightError, expected):
                        self.validate(document, endpoint_map, workspace, output)

    def test_raw_har_retention_is_measured_from_capture_not_preflight(self) -> None:
        endpoint_map = self.endpoint_map()
        document = self.preflight(endpoint_map)
        document["retention"]["raw_har_captured_at"] = "2026-09-21T10:00:00Z"
        document["retention"]["raw_har_delete_by"] = "2026-09-22T11:00:00Z"
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            with self.assertRaisesRegex(self.api().PilotPreflightError, "raw HAR"):
                self.validate(document, endpoint_map, workspace, output)

    def test_runtime_evidence_must_be_passing_and_identical(self) -> None:
        endpoint_map = self.endpoint_map()
        cases = []
        failed_gate = self.preflight(endpoint_map)
        failed_gate["evidence"]["quality_gate_status"] = "failed"
        cases.append((failed_gate, "quality gate"))
        drifted = self.preflight(endpoint_map)
        drifted["evidence"]["codex_summary"]["shared_artifact_digest"] = "f" * 64
        cases.append((drifted, "runtime summaries"))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            for document, expected in cases:
                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(self.api().PilotPreflightError, expected):
                        self.validate(document, endpoint_map, workspace, output)

    def test_endpoint_map_must_be_review_ready_and_digest_bound(self) -> None:
        endpoint_map = self.endpoint_map()
        wrong_digest = self.preflight(endpoint_map)
        wrong_digest["evidence"]["endpoint_map_digest"] = "0" * 64
        incomplete_map = copy.deepcopy(endpoint_map)
        incomplete_map["endpoints"] = [
            item
            for item in incomplete_map["endpoints"]
            if item["classification"] != "document_download"
        ]
        incomplete_map["endpoint_count"] -= 1
        incomplete_map["capture"]["entry_count"] -= 1
        incomplete_map["coverage"]["document_download"] = 0
        incomplete_map = har_fixtures.PJeHarMapReviewTest().seal(incomplete_map)
        incomplete = self.preflight(incomplete_map)
        incomplete["evidence"]["endpoint_map_digest"] = incomplete_map["sanitized_digest"]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            with self.assertRaisesRegex(self.api().PilotPreflightError, "endpoint map digest"):
                self.validate(wrong_digest, endpoint_map, workspace, output)
            with self.assertRaisesRegex(self.api().PilotPreflightError, "endpoint map gaps"):
                self.validate(incomplete, incomplete_map, workspace, output)

    def test_commit_branch_and_local_paths_are_bound(self) -> None:
        endpoint_map = self.endpoint_map()
        wrong_commit = self.preflight(endpoint_map)
        wrong_commit["evidence"]["development_commit"] = "0" * 40
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            with self.assertRaisesRegex(self.api().PilotPreflightError, "commit"):
                self.validate(wrong_commit, endpoint_map, workspace, output)
            with self.assertRaisesRegex(self.api().PilotPreflightError, "outside the repository"):
                self.validate(self.preflight(endpoint_map), endpoint_map, ROOT / "workspace", output)

            with self.assertRaisesRegex(self.api().PilotPreflightError, "working tree"):
                self.api().validate_pilot_preflight(
                    preflight=self.preflight(endpoint_map),
                    endpoint_map=endpoint_map,
                    schema_path=SCHEMA,
                    sanitization_contract_path=SANITIZATION_CONTRACT,
                    map_review_contract_path=MAP_REVIEW_CONTRACT,
                    repository_root=ROOT,
                    workspace_path=workspace,
                    output_path=output,
                    current_branch="development",
                    current_commit=self.current_commit(),
                    working_tree_clean=False,
                )

    def test_output_workspace_must_be_empty_and_separate(self) -> None:
        endpoint_map = self.endpoint_map()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            (output / "stale.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(self.api().PilotPreflightError, "output directory must be empty"):
                self.validate(self.preflight(endpoint_map), endpoint_map, workspace, output)

            (output / "stale.json").unlink()
            with self.assertRaisesRegex(self.api().PilotPreflightError, "must be distinct"):
                self.validate(self.preflight(endpoint_map), endpoint_map, workspace, workspace)

    def test_schema_rejects_unreviewed_controls(self) -> None:
        endpoint_map = self.endpoint_map()
        document = self.preflight(endpoint_map)
        document["controls"]["allow_task_movement"] = True
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            with self.assertRaisesRegex(self.api().PilotPreflightError, "unknown field"):
                self.validate(document, endpoint_map, workspace, output)

    def test_cli_writes_only_a_secret_free_go_summary(self) -> None:
        endpoint_map = self.endpoint_map()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            subprocess.run(
                ["git", "init", "-b", "development"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Preflight Test"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "preflight@example.test"],
                cwd=repository,
                check=True,
            )
            (repository / "marker.txt").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "marker.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-m", "test: create clean checkout"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            preflight_path = base / "preflight.json"
            endpoint_map_path = base / "endpoint-map.json"
            summary_path = base / "summary.json"
            preflight = self.preflight(endpoint_map)
            preflight["evidence"]["development_commit"] = commit
            preflight_path.write_text(json.dumps(preflight), encoding="utf-8")
            endpoint_map_path.write_text(json.dumps(endpoint_map), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--preflight",
                    str(preflight_path),
                    "--endpoint-map",
                    str(endpoint_map_path),
                    "--workspace",
                    str(workspace),
                    "--output",
                    str(output),
                    "--summary",
                    str(summary_path),
                    "--repository-root",
                    str(repository),
                    "--schema",
                    str(SCHEMA),
                    "--sanitization-contract",
                    str(SANITIZATION_CONTRACT),
                    "--map-review-contract",
                    str(MAP_REVIEW_CONTRACT),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "go_controlled_pilot")
            serialized = json.dumps(summary)
            self.assertNotIn(str(workspace), serialized)
            self.assertNotIn("authorization_scope_digest", serialized)


if __name__ == "__main__":
    unittest.main()
