from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SANITIZER = ROOT / "scripts" / "sanitize_pje_har.py"


class PJeHarSanitizerTest(unittest.TestCase):
    def sample_har(self) -> dict:
        return {
            "log": {
                "version": "1.2",
                "entries": [
                    {
                        "request": {
                            "method": "GET",
                            "url": (
                                "https://pje.example.test/pje/api/tarefas/12345678"
                                "?numeroProcesso=0000000-00.2026.5.99.0001"
                            ),
                            "headers": [
                                {
                                    "name": "Authorization",
                                    "value": "Bearer private-access-token-1234567890",
                                },
                                {
                                    "name": "X-pje-usuario-localizacao",
                                    "value": "987654321",
                                },
                            ],
                            "cookies": [
                                {
                                    "name": "JSESSIONID",
                                    "value": "private-session-cookie-1234567890",
                                }
                            ],
                            "queryString": [
                                {
                                    "name": "numeroProcesso",
                                    "value": "0000000-00.2026.5.99.0001",
                                }
                            ],
                            "postData": {
                                "mimeType": "application/json",
                                "text": '{"cpf":"11122233344"}',
                            },
                        },
                        "response": {
                            "status": 200,
                            "headers": [
                                {
                                    "name": "Content-Type",
                                    "value": "application/json; charset=utf-8",
                                },
                                {
                                    "name": "Set-Cookie",
                                    "value": "ROUTER_ID=private-router-cookie-1234567890",
                                },
                            ],
                            "cookies": [
                                {
                                    "name": "ROUTER_ID",
                                    "value": "private-router-cookie-1234567890",
                                }
                            ],
                            "content": {
                                "size": 128,
                                "mimeType": "application/json",
                                "text": '{"party":"Synthetic Person"}',
                            },
                        },
                    },
                    {
                        "request": {
                            "method": "GET",
                            "url": (
                                "https://pje.example.test/pje/api/documentos/9876543210/"
                                "conteudo"
                            ),
                            "headers": [],
                            "cookies": [],
                            "queryString": [],
                        },
                        "response": {
                            "status": 200,
                            "headers": [],
                            "cookies": [],
                            "content": {
                                "size": 2048,
                                "mimeType": "application/pdf",
                                "text": "private-document-body",
                            },
                        },
                    },
                    {
                        "request": {
                            "method": "POST",
                            "url": "https://pje.example.test/pje/api/processos",
                            "headers": [],
                            "cookies": [],
                            "queryString": [],
                        },
                        "response": {
                            "status": 401,
                            "headers": [],
                            "cookies": [],
                            "content": {
                                "size": 32,
                                "mimeType": "application/json",
                                "text": "private-failure-body",
                            },
                        },
                    },
                ],
            }
        }

    def run_sanitizer(
        self,
        input_path: Path,
        output_path: Path,
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SANITIZER),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--tribunal-code",
                "TRT99",
                "--instance",
                "1",
                *extra,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def write_har(self, path: Path, document: dict) -> None:
        path.write_text(json.dumps(document), encoding="utf-8")

    def test_maps_endpoints_without_retaining_sensitive_values_or_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "authorized.har"
            output = root / "sanitized-map.json"
            self.write_har(raw, self.sample_har())

            result = self.run_sanitizer(raw, output, "--authorized-capture")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["tribunal_code"], "TRT99")
            self.assertEqual(report["instance"], 1)
            self.assertEqual(report["capture"]["entry_count"], 3)
            self.assertEqual(report["endpoint_count"], 3)
            self.assertEqual(
                report["endpoints"][0],
                {
                    "method": "GET",
                    "origin": "https://pje.example.test",
                    "path_template": "/pje/api/tarefas/{numeric_id}",
                    "query_keys": ["numeroProcesso"],
                    "request_header_names": [
                        "authorization",
                        "x-pje-usuario-localizacao",
                    ],
                    "request_cookie_names": ["JSESSIONID"],
                    "response_cookie_names": ["ROUTER_ID"],
                    "response_status": 200,
                    "response_content_type": "application/json",
                    "classification": "task_listing",
                    "failure_state": None,
                },
            )
            serialized = output.read_text(encoding="utf-8")
            for sensitive_value in (
                "private-access-token-1234567890",
                "987654321",
                "private-session-cookie-1234567890",
                "0000000-00.2026.5.99.0001",
                "11122233344",
                "private-router-cookie-1234567890",
                "Synthetic Person",
                "private-document-body",
                "private-failure-body",
            ):
                self.assertNotIn(sensitive_value, serialized)

    def test_classifies_document_download_and_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "authorized.har"
            output = root / "sanitized-map.json"
            self.write_har(raw, self.sample_har())

            result = self.run_sanitizer(raw, output, "--authorized-capture")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["coverage"]["task_listing"], 1)
            self.assertEqual(report["coverage"]["document_download"], 1)
            self.assertEqual(report["coverage"]["process_discovery"], 1)
            self.assertEqual(report["failure_states"], {"unauthorized": 1})
            self.assertEqual(
                report["endpoints"][1]["path_template"],
                "/pje/api/documentos/{numeric_id}/conteudo",
            )

    def test_same_capture_produces_byte_identical_map(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "authorized.har"
            first = root / "first.json"
            second = root / "second.json"
            self.write_har(raw, self.sample_har())

            first_result = self.run_sanitizer(raw, first, "--authorized-capture")
            second_result = self.run_sanitizer(raw, second, "--authorized-capture")

            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            report = json.loads(first.read_text(encoding="utf-8"))
            self.assertRegex(report["sanitized_digest"], r"^[0-9a-f]{64}$")

    def test_requires_explicit_authorized_capture_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "capture.har"
            output = root / "sanitized-map.json"
            self.write_har(raw, self.sample_har())

            result = self.run_sanitizer(raw, output)

            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())
            self.assertIn("--authorized-capture", result.stderr)

    def test_invalid_har_fails_closed_without_echoing_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "invalid.har"
            output = root / "sanitized-map.json"
            secret = "private-invalid-capture-value-1234567890"
            self.write_har(raw, {"log": {"entries": {"secret": secret}}})

            result = self.run_sanitizer(raw, output, "--authorized-capture")

            combined = result.stdout + result.stderr
            self.assertEqual(result.returncode, 2, combined)
            self.assertFalse(output.exists())
            self.assertIn("HAR entries must be an array", combined)
            self.assertNotIn(secret, combined)

    def test_rejects_non_https_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "capture.har"
            output = root / "sanitized-map.json"
            har = self.sample_har()
            har["log"]["entries"][0]["request"]["url"] = (
                "http://pje.example.test/pje/api/tarefas"
            )
            self.write_har(raw, har)

            result = self.run_sanitizer(raw, output, "--authorized-capture")

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse(output.exists())
            self.assertIn("HTTPS", result.stderr)


if __name__ == "__main__":
    unittest.main()
