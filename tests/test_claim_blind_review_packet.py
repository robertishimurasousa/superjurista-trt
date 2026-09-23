from __future__ import annotations

import hashlib
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class ClaimBlindReviewPacketTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("prepare_claim_blind_review")

    def inputs(self, directory: Path):
        pdf_path = directory / "synthetic.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=72, height=72)
        writer.add_metadata({"/Title": "Synthetic case"})
        with pdf_path.open("wb") as stream:
            writer.write(stream)
        segments = {
            "schema_version": 1,
            "segmentation_method": "pje_pdf_outline",
            "source_pdf": {
                "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "page_count": 3,
            },
            "documents": [
                {
                    "document_id": "DOC-001",
                    "provider_reference": "0000001",
                    "provider_type": "Initial",
                    "filed_on": "2026-01-01",
                    "page_start": 1,
                    "page_end": 2,
                },
                {
                    "document_id": "DOC-002",
                    "provider_reference": "0000002",
                    "provider_type": "Defense",
                    "filed_on": "2026-01-02",
                    "page_start": 3,
                    "page_end": 3,
                },
            ],
        }
        return pdf_path, segments

    def test_packet_uses_only_source_custody_and_leaves_inventory_blank(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            pdf_path, segments = self.inputs(Path(directory))
            packet = api.prepare_review_packet(
                pdf_path, segments, document_id="DOC-001", case_id="PILOT-001"
            )
        self.assertIn("PILOT-001", packet)
        self.assertIn("DOC-001", packet)
        self.assertIn("páginas 1-2", packet)
        self.assertIn("sem consultar a matriz", packet)
        self.assertIn("[preencher]", packet)
        self.assertNotIn("CLM-", packet)
        self.assertNotIn("POS-", packet)
        self.assertNotIn("8 pedidos", packet)
        self.assertNotIn("16 vínculos", packet)

    def test_rejects_pdf_custody_mismatch_and_out_of_range_segment(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            pdf_path, segments = self.inputs(Path(directory))
            segments["source_pdf"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(api.BlindReviewPacketError, "custody"):
                api.prepare_review_packet(
                    pdf_path, segments, document_id="DOC-001", case_id="PILOT-001"
                )
            segments["source_pdf"]["sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            segments["documents"][0]["page_end"] = 4
            with self.assertRaisesRegex(api.BlindReviewPacketError, "page range"):
                api.prepare_review_packet(
                    pdf_path, segments, document_id="DOC-001", case_id="PILOT-001"
                )

    def test_rejects_unknown_document_and_invalid_pseudonym(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            pdf_path, segments = self.inputs(Path(directory))
            with self.assertRaisesRegex(api.BlindReviewPacketError, "document"):
                api.prepare_review_packet(
                    pdf_path, segments, document_id="DOC-999", case_id="PILOT-001"
                )
            with self.assertRaisesRegex(api.BlindReviewPacketError, "pseudonymous"):
                api.prepare_review_packet(
                    pdf_path, segments, document_id="DOC-001", case_id="0000000-00.2026.5.12.0000"
                )

    def test_protected_output_is_exclusive_and_rejects_repository_path(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = api.write_review_packet(
                "Synthetic blank form\n", output_dir=output, repository_root=ROOT
            )
            self.assertEqual(path.read_text(encoding="utf-8"), "Synthetic blank form\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(api.BlindReviewPacketError, "exists"):
                api.write_review_packet(
                    "Synthetic blank form\n", output_dir=output, repository_root=ROOT
                )
            with self.assertRaisesRegex(api.BlindReviewPacketError, "outside repository"):
                api.write_review_packet(
                    "Synthetic blank form\n", output_dir=ROOT, repository_root=ROOT
                )
