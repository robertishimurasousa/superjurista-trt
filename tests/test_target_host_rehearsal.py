from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class TargetHostRehearsalTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("rehearse_target_host")
        except ModuleNotFoundError as error:
            self.fail(f"target-host rehearsal module is missing: {error}")

    def valid_evidence(self):
        return {
            "python_version": "3.12.14",
            "packages": {
                "beautifulsoup4": "4.15.0",
                "mcp": "1.30.0",
                "pdf2image": "1.17.0",
                "pdfplumber": "0.11.10",
                "pytesseract": "0.3.13",
                "PyPDF2": "3.0.1",
                "pyotp": "2.10.0",
                "requests": "2.34.2",
                "urllib3": "1.26.20",
            },
            "executables": {
                "pdftoppm": {"available": True, "version": "26.05.0"},
                "tesseract": {"available": True, "version": "5.5.3"},
            },
            "tesseract_languages": ["eng", "osd", "por"],
            "mcp_servers": [
                "bnp-api",
                "cjf-jurisprudencia",
                "tcu-jurisprudencia",
                "tjsc-eproc",
                "tnu-eproc",
            ],
            "ocr": {
                "pages": 1,
                "recognized_phrases": [
                    "Horas extras reconhecidas",
                    "JUSTIÇA DO TRABALHO",
                ],
                "text_sha256": "a" * 64,
            },
        }

    def test_complete_target_host_evidence_is_ready_and_deterministic(self) -> None:
        api = self.api()

        first = api.assess_host_evidence(self.valid_evidence())
        second = api.assess_host_evidence(self.valid_evidence())

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["python_version"], "3.12.14")
        self.assertEqual(first["mcp_server_count"], 5)
        self.assertEqual(first["ocr_pages"], 1)
        self.assertRegex(first["evidence_digest"], r"^[0-9a-f]{64}$")

    def test_python_and_mcp_versions_must_satisfy_runtime_boundaries(self) -> None:
        api = self.api()
        cases = (("python_version", "3.9.6"), ("mcp", "2.0.0"))
        for field, value in cases:
            evidence = self.valid_evidence()
            if field == "python_version":
                evidence[field] = value
            else:
                evidence["packages"][field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(api.HostRehearsalError, field):
                    api.assess_host_evidence(evidence)

    def test_required_packages_executables_and_portuguese_data_cannot_be_missing(self) -> None:
        api = self.api()
        missing_package = self.valid_evidence()
        del missing_package["packages"]["pytesseract"]
        missing_executable = self.valid_evidence()
        missing_executable["executables"]["pdftoppm"]["available"] = False
        missing_language = self.valid_evidence()
        missing_language["tesseract_languages"].remove("por")

        for evidence, expected in (
            (missing_package, "pytesseract"),
            (missing_executable, "pdftoppm"),
            (missing_language, "Portuguese"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(api.HostRehearsalError, expected):
                    api.assess_host_evidence(evidence)

    def test_all_mcp_servers_and_both_ocr_phrases_are_mandatory(self) -> None:
        api = self.api()
        missing_server = self.valid_evidence()
        missing_server["mcp_servers"].remove("tnu-eproc")
        incomplete_ocr = self.valid_evidence()
        incomplete_ocr["ocr"]["recognized_phrases"].pop()

        with self.assertRaisesRegex(api.HostRehearsalError, "MCP server"):
            api.assess_host_evidence(missing_server)
        with self.assertRaisesRegex(api.HostRehearsalError, "OCR phrase"):
            api.assess_host_evidence(incomplete_ocr)

    def test_unknown_evidence_fields_fail_closed(self) -> None:
        api = self.api()
        evidence = self.valid_evidence()
        evidence["unreviewed_override"] = True

        with self.assertRaisesRegex(api.HostRehearsalError, "unknown"):
            api.assess_host_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
