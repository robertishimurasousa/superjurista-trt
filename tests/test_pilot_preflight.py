from __future__ import annotations

import copy
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tests.test_pje_har_map_review as har_fixtures


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
VALIDATOR = SCRIPTS / "validate_pilot_preflight.py"
SCHEMA = ROOT / "runtime" / "operations" / "pilot-preflight.v4.schema.json"
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
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        plan = importlib.import_module("run_synthetic_pipeline")._resolve_plan("codex")
        return {
            "artifact_count": sum(
                len(stage["outputs"]) for stage in plan["contract"]["stages"]
            ),
            "global_gate_status": "passed",
            "contract_digest": plan["contract_digest"],
            "shared_artifact_digest": "e" * 64,
        }

    def preflight(self, endpoint_map: dict) -> dict:
        return {
            "schema_version": 4,
            "pilot_id": "PILOT-001",
            "created_at": "2026-09-21T12:00:00Z",
            "valid_until": "2026-09-30T12:00:00Z",
            "tribunal_code": "TRT12",
            "instance": 1,
            "case": {
                "case_number": "0000000-00.2026.5.12.0000",
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
                "model_providers_authorized": ["codex"],
                "codex_model_id": "test-codex-model",
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

    def validate(
        self, preflight: dict, endpoint_map: dict, workspace: Path, output: Path,
        now: datetime = datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
    ):
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
            now=now,
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
        self.assertNotIn("0000000-00.2026.5.12.0000", json.dumps(result))

    def test_protected_case_number_must_be_a_trt12_first_instance_number(self) -> None:
        endpoint_map = self.endpoint_map()
        invalid = self.preflight(endpoint_map)
        invalid["case"]["case_number"] = "0000000-00.2026.5.02.0000"
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            with self.assertRaisesRegex(self.api().PilotPreflightError, "case_number"):
                self.validate(invalid, endpoint_map, workspace, output)

    def test_expired_or_future_preflight_is_no_go(self) -> None:
        endpoint_map = self.endpoint_map()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            preflight = self.preflight(endpoint_map)
            with self.assertRaisesRegex(self.api().PilotPreflightError, "vencida"):
                self.validate(
                    preflight, endpoint_map, workspace, output,
                    now=datetime(2026, 10, 1, tzinfo=timezone.utc),
                )
            preflight["created_at"] = "2026-09-22T12:00:00Z"
            with self.assertRaisesRegex(self.api().PilotPreflightError, "futura"):
                self.validate(preflight, endpoint_map, workspace, output)

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
            for document, expected in ((sealed, "sigilo"), (exceptional, "acesso excepcional")):
                with self.subTest(expected=expected):
                    with self.assertRaisesRegex(self.api().PilotPreflightError, expected):
                        self.validate(document, endpoint_map, workspace, output)

    def test_retention_deadlines_cannot_exceed_approved_limits(self) -> None:
        endpoint_map = self.endpoint_map()
        cases = (
            ("raw_har_delete_by", "2026-09-22T12:00:01Z", "captura HAR"),
            ("raw_documents_delete_by", "2026-10-30T12:00:01Z", "documentos originais"),
            ("derived_artifacts_delete_by", "2026-12-29T12:00:01Z", "artefatos derivados"),
            ("incident_summary_delete_by", "2027-03-20T12:00:01Z", "resumo de incidente"),
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
            with self.assertRaisesRegex(self.api().PilotPreflightError, "captura HAR"):
                self.validate(document, endpoint_map, workspace, output)

    def test_runtime_evidence_must_be_passing_and_identical(self) -> None:
        endpoint_map = self.endpoint_map()
        cases = []
        failed_gate = self.preflight(endpoint_map)
        failed_gate["evidence"]["quality_gate_status"] = "failed"
        cases.append((failed_gate, "controle de qualidade"))
        drifted = self.preflight(endpoint_map)
        drifted["evidence"]["codex_summary"]["shared_artifact_digest"] = "f" * 64
        cases.append((drifted, "resumos de execução"))
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

    def test_current_runtime_summaries_pass_the_preflight_contract(self) -> None:
        self.api()
        pipeline = importlib.import_module("run_synthetic_pipeline")
        endpoint_map = self.endpoint_map()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            summaries = {}
            for runtime in ("claude", "codex"):
                rehearsal = base / runtime
                rehearsal.mkdir(mode=0o700)
                summaries[runtime] = pipeline.run_synthetic_pipeline(
                    runtime,
                    ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json",
                    rehearsal,
                )
            self.assertEqual(summaries["claude"]["artifact_count"], 24)
            preflight = self.preflight(endpoint_map)
            preflight["evidence"]["claude_summary"] = {
                key: summaries["claude"][key] for key in self.runtime_summary()
            }
            preflight["evidence"]["codex_summary"] = {
                key: summaries["codex"][key] for key in self.runtime_summary()
            }
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()

            try:
                result = self.validate(preflight, endpoint_map, workspace, output)
            except self.api().PilotPreflightError as error:
                self.fail(f"os resumos atuais foram recusados: {error}")

        self.assertEqual(result["status"], "go_controlled_pilot")

    def test_matching_but_stale_runtime_count_or_contract_is_rejected(self) -> None:
        endpoint_map = self.endpoint_map()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()
            for field, value in (("artifact_count", 19), ("contract_digest", "d" * 64)):
                preflight = self.preflight(endpoint_map)
                for runtime in ("claude_summary", "codex_summary"):
                    preflight["evidence"][runtime][field] = value
                with self.subTest(field=field):
                    with self.assertRaisesRegex(self.api().PilotPreflightError, "execução"):
                        self.validate(preflight, endpoint_map, workspace, output)

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
            with self.assertRaisesRegex(self.api().PilotPreflightError, "resumo criptográfico do mapa de endpoints"):
                self.validate(wrong_digest, endpoint_map, workspace, output)
            with self.assertRaisesRegex(self.api().PilotPreflightError, "lacunas no mapa de endpoints"):
                self.validate(incomplete, incomplete_map, workspace, output)

    def test_unobserved_failures_remain_visible_without_requiring_induced_errors(self) -> None:
        endpoint_map = self.endpoint_map()
        endpoint_map["endpoints"] = [
            item for item in endpoint_map["endpoints"] if item["failure_state"] is None
        ]
        endpoint_map["endpoint_count"] = len(endpoint_map["endpoints"])
        endpoint_map["capture"]["entry_count"] = len(endpoint_map["endpoints"])
        endpoint_map["coverage"]["process_discovery"] = 1
        endpoint_map["failure_states"] = {}
        endpoint_map = har_fixtures.PJeHarMapReviewTest().seal(endpoint_map)
        preflight = self.preflight(endpoint_map)
        preflight["evidence"]["endpoint_map_digest"] = endpoint_map["sanitized_digest"]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            workspace = base / "workspace"
            output = base / "output"
            workspace.mkdir()
            output.mkdir()

            result = self.validate(preflight, endpoint_map, workspace, output)

        self.assertEqual(result["status"], "go_controlled_pilot")
        self.assertEqual(
            result["unobserved_failure_groups"],
            [
                "failure_group:authentication_failure",
                "failure_group:provider_failure",
            ],
        )

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
            with self.assertRaisesRegex(self.api().PilotPreflightError, "fora do repositório"):
                self.validate(self.preflight(endpoint_map), endpoint_map, ROOT / "workspace", output)

            with self.assertRaisesRegex(self.api().PilotPreflightError, "árvore de trabalho"):
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
            with self.assertRaisesRegex(self.api().PilotPreflightError, "diretório de saída deve estar vazio"):
                self.validate(self.preflight(endpoint_map), endpoint_map, workspace, output)

            (output / "stale.json").unlink()
            with self.assertRaisesRegex(self.api().PilotPreflightError, "devem ser diferentes"):
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
            with self.assertRaisesRegex(self.api().PilotPreflightError, "campo desconhecido"):
                self.validate(document, endpoint_map, workspace, output)

    def test_cli_help_explains_preflight_in_portuguese(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validar a verificação prévia do piloto controlado", result.stdout)

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
            current = datetime.now(timezone.utc)
            created = current - timedelta(hours=1)
            review_close = current + timedelta(days=1)
            def timestamp(value: datetime) -> str:
                return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            preflight["created_at"] = timestamp(created)
            preflight["valid_until"] = timestamp(current + timedelta(hours=1))
            preflight["retention"].update({
                "raw_har_captured_at": timestamp(created),
                "planned_review_close_by": timestamp(review_close),
                "raw_har_delete_by": timestamp(created + timedelta(hours=24)),
                "raw_documents_delete_by": timestamp(review_close + timedelta(days=30)),
                "derived_artifacts_delete_by": timestamp(review_close + timedelta(days=90)),
                "incident_summary_delete_by": timestamp(created + timedelta(days=180)),
            })
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
            self.assertIn("[GO] verificação prévia do piloto controlado", result.stdout)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "go_controlled_pilot")
            serialized = json.dumps(summary)
            self.assertNotIn(str(workspace), serialized)
            self.assertNotIn("authorization_scope_digest", serialized)


if __name__ == "__main__":
    unittest.main()
