from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_pje_har_map.py"


class PJeHarMapReviewTest(unittest.TestCase):
    def endpoint(
        self,
        classification: str,
        path: str,
        *,
        method: str = "GET",
        status: int = 200,
        failure_state=None,
        headers=None,
        cookies=None,
    ) -> dict:
        return {
            "method": method,
            "origin": "https://pje.example.test",
            "path_template": path,
            "query_keys": [],
            "request_header_names": headers or [],
            "request_cookie_names": cookies or [],
            "response_cookie_names": [],
            "response_status": status,
            "response_content_type": "application/json",
            "classification": classification,
            "failure_state": failure_state,
        }

    def seal(self, report: dict) -> dict:
        unsigned = copy.deepcopy(report)
        unsigned.pop("sanitized_digest", None)
        canonical = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        unsigned["sanitized_digest"] = hashlib.sha256(canonical).hexdigest()
        return unsigned

    def valid_map(self) -> dict:
        endpoints = [
            self.endpoint(
                "authentication",
                "/pje/login",
                method="POST",
                headers=["authorization"],
                cookies=["JSESSIONID"],
            ),
            self.endpoint("task_listing", "/pje/api/tarefas"),
            self.endpoint("process_discovery", "/pje/api/processos"),
            self.endpoint("document_index", "/pje/api/documentos"),
            self.endpoint(
                "document_download",
                "/pje/api/documentos/{numeric_id}/conteudo",
                status=200,
            ),
            self.endpoint(
                "process_discovery",
                "/pje/api/processos",
                status=401,
                failure_state="unauthorized",
            ),
            self.endpoint(
                "process_discovery",
                "/pje/api/processos",
                status=500,
                failure_state="provider_error",
            ),
        ]
        return self.seal(
            {
                "schema_version": 1,
                "tribunal_code": "TRT99",
                "instance": 1,
                "authorization_acknowledgement": "operator_confirmed",
                "capture": {
                    "format": "HAR",
                    "har_version": "1.2",
                    "entry_count": 7,
                },
                "endpoint_count": 7,
                "endpoints": endpoints,
                "coverage": {
                    "authentication": 1,
                    "task_listing": 1,
                    "process_discovery": 3,
                    "document_index": 1,
                    "document_download": 1,
                    "other": 0,
                },
                "failure_states": {
                    "provider_error": 1,
                    "unauthorized": 1,
                },
                "redaction": {
                    "query_values_removed": 0,
                    "request_header_values_removed": 1,
                    "request_cookie_values_removed": 1,
                    "request_bodies_removed": 0,
                    "response_header_values_removed": 0,
                    "response_cookie_values_removed": 0,
                    "response_bodies_removed": 0,
                },
            }
        )

    def run_validator(self, map_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--map",
                str(map_path),
                "--tribunal-code",
                "TRT99",
                "--instance",
                "1",
                "--format",
                "json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def write_map(self, path: Path, report: dict) -> None:
        path.write_text(json.dumps(report), encoding="utf-8")

    def test_complete_map_is_ready_for_human_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / "map.json"
            self.write_map(map_path, self.valid_map())

            result = self.run_validator(map_path)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "endpoint_count": 7,
                    "instance": 1,
                    "observed_failure_states": ["provider_error", "unauthorized"],
                    "status": "review_ready",
                    "tribunal_code": "TRT99",
                },
            )

    def test_missing_capability_is_reported_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / "map.json"
            report = self.valid_map()
            report["endpoints"] = [
                endpoint
                for endpoint in report["endpoints"]
                if endpoint["classification"] != "document_download"
            ]
            report["endpoint_count"] = 6
            report["capture"]["entry_count"] = 6
            report["coverage"]["document_download"] = 0
            self.write_map(map_path, self.seal(report))

            result = self.run_validator(map_path)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            response = json.loads(result.stdout)
            self.assertEqual(response["status"], "incomplete")
            self.assertEqual(response["gaps"], ["classification:document_download"])

    def test_missing_authentication_artifacts_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / "map.json"
            report = self.valid_map()
            report["endpoints"][0]["request_header_names"] = []
            report["endpoints"][0]["request_cookie_names"] = []
            self.write_map(map_path, self.seal(report))

            result = self.run_validator(map_path)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            response = json.loads(result.stdout)
            self.assertEqual(
                response["gaps"],
                ["authentication:cookie_name", "authentication:header_name"],
            )

    def test_missing_provider_failure_is_a_review_limitation_not_a_capture_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / "map.json"
            report = self.valid_map()
            report["endpoints"] = [
                endpoint
                for endpoint in report["endpoints"]
                if endpoint["failure_state"] != "provider_error"
            ]
            report["endpoint_count"] = 6
            report["capture"]["entry_count"] = 6
            report["coverage"]["process_discovery"] = 2
            report["failure_states"] = {"unauthorized": 1}
            self.write_map(map_path, self.seal(report))

            result = self.run_validator(map_path)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            response = json.loads(result.stdout)
            self.assertEqual(response["status"], "review_ready")
            self.assertEqual(
                response["observed_failure_gaps"],
                ["failure_group:provider_failure"],
            )

    def test_digest_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / "map.json"
            report = self.valid_map()
            report["endpoint_count"] = 999
            self.write_map(map_path, report)

            result = self.run_validator(map_path)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("digest", result.stderr)

    def test_unredacted_dynamic_path_identifier_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / "map.json"
            report = self.valid_map()
            report["endpoints"][4]["path_template"] = (
                "/pje/api/documentos/987654321/conteudo"
            )
            self.write_map(map_path, self.seal(report))

            result = self.run_validator(map_path)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("dynamic identifier", result.stderr)

    def test_tribunal_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            map_path = Path(directory) / "map.json"
            report = self.valid_map()
            report["tribunal_code"] = "TRT98"
            self.write_map(map_path, self.seal(report))

            result = self.run_validator(map_path)

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("tribunal_code", result.stderr)


if __name__ == "__main__":
    unittest.main()
