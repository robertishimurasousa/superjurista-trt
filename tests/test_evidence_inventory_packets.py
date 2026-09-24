from __future__ import annotations

import copy
import importlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class EvidenceInventoryPacketsTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        os.chmod(self.workspace, 0o700)
        self.pdf = self.workspace / "fonte-sintetica.pdf"
        self.pdf.write_bytes(rehearsal._synthetic_pdf())
        matrix = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]["claim-matrix.json"]
        matrix["claims"][0]["claimant_position"]["source_locator"] = "DOC-001, página 1"
        matrix["claims"][0]["respondent_positions"][0]["source_locator"] = "DOC-002, página 2"
        (self.workspace / "claim-matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
        )

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("prepare_evidence_inventory_packets"))
        return importlib.import_module("prepare_evidence_inventory_packets")

    def assert_no_outputs(self) -> None:
        for name in (
            "evidence-inventory-index.json", "inventory-pje-pdf-segments.json",
            "DOC-001-inventory-source.md", "DOC-002-inventory-source.md",
        ):
            self.assertFalse((self.workspace / name).exists())

    def test_prepares_each_pdf_document_without_crossing_its_page_boundary(self) -> None:
        api = self.api()

        index = api.prepare_evidence_inventory_packets(self.workspace, self.pdf)

        self.assertEqual([item["document_id"] for item in index["records"]], [
            "DOC-001", "DOC-002",
        ])
        first = (self.workspace / "DOC-001-inventory-source.md").read_text(encoding="utf-8")
        second = (self.workspace / "DOC-002-inventory-source.md").read_text(encoding="utf-8")
        self.assertIn("CAPA SINTÉTICA", first)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", first)
        self.assertIn("REGISTRO DE JORNADA SINTÉTICO", second)
        self.assertNotIn("CAPA SINTÉTICA", second)
        self.assertIn("CLM-001", first)
        self.assertIn("CLM-001", second)
        self.assertIn("não é decisão jurídica", first)
        self.assertEqual(
            {stat.S_IMODE((self.workspace / name).stat().st_mode) for name in (
                "evidence-inventory-index.json", "inventory-pje-pdf-segments.json",
                "DOC-001-inventory-source.md", "DOC-002-inventory-source.md",
            )},
            {0o600},
        )

    def test_missing_text_in_any_document_prevents_partial_inventory(self) -> None:
        api = self.api()
        source = PdfReader(str(self.pdf))
        writer = PdfWriter()
        writer.add_page(source.pages[0])
        writer.add_blank_page(width=612, height=792)
        for number in (1, 2):
            writer.add_outline_item(
                f"{number}. 24/09/2026 - Documento sintético - abc000{number}",
                number - 1,
            )
        output = io.BytesIO()
        writer.write(output)
        self.pdf.write_bytes(output.getvalue())

        with self.assertRaises(api.EvidenceInventoryPacketsError):
            api.prepare_evidence_inventory_packets(self.workspace, self.pdf)

        self.assert_no_outputs()

    def test_existing_inventory_output_is_preserved(self) -> None:
        api = self.api()
        old = b"arquivo anterior"
        (self.workspace / "DOC-002-inventory-source.md").write_bytes(old)

        with self.assertRaises(api.EvidenceInventoryPacketsError):
            api.prepare_evidence_inventory_packets(self.workspace, self.pdf)

        self.assertEqual((self.workspace / "DOC-002-inventory-source.md").read_bytes(), old)
        self.assertFalse((self.workspace / "DOC-001-inventory-source.md").exists())
        self.assertFalse((self.workspace / "evidence-inventory-index.json").exists())

    def test_cli_prepares_inventory_without_printing_process_text(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "prepare_evidence_inventory_packets.py"),
                "--workspace", str(self.workspace), "--pdf", str(self.pdf),
            ],
            text=True, capture_output=True, check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.workspace / "evidence-inventory-index.json").is_file())
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", result.stdout + result.stderr)

    def test_rebuilt_packet_rejects_claim_position_outside_pdf_documents(self) -> None:
        api = self.api()
        segmenter = importlib.import_module("segment_pje_pdf")
        segments = segmenter.segment_pje_pdf(self.pdf)
        matrix = json.loads((self.workspace / "claim-matrix.json").read_text(encoding="utf-8"))
        matrix["claims"][0]["claimant_position"]["source_document_id"] = "DOC-999"

        with self.assertRaises(api.EvidenceInventoryPacketsError):
            api.build_evidence_inventory_packet(
                self.pdf, segments, matrix, "DOC-002"
            )

    def test_duplicate_claim_cannot_enter_inventory_context(self) -> None:
        api = self.api()
        matrix_path = self.workspace / "claim-matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        matrix["claims"].append(copy.deepcopy(matrix["claims"][0]))
        matrix_path.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(api.EvidenceInventoryPacketsError):
            api.prepare_evidence_inventory_packets(self.workspace, self.pdf)

        self.assert_no_outputs()


if __name__ == "__main__":
    unittest.main()
