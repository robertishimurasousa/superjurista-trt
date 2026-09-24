from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfWriter
from PyPDF2._page import PageObject
from PyPDF2.generic import DecodedStreamObject, DictionaryObject, NameObject


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class SourceEvidencePacketTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("prepare_source_evidence_packet") is None:
            self.fail("o preparador do pacote probatório não existe")
        self.api = importlib.import_module("prepare_source_evidence_packet")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.pdf = self.directory / "fonte.pdf"
        self._write_pdf(("TEXTO FONTE UM", "TEXTO FONTE DOIS", "TEXTO NAO SELECIONADO"))
        digest = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.segments = {
            "schema_version": 1, "segmentation_method": "pje_pdf_outline",
            "source_pdf": {"sha256": digest, "page_count": 3},
            "documents": [
                {
                    "document_id": f"DOC-{number:03d}",
                    "provider_reference": f"abc000{number}",
                    "provider_type": "Documento sintético", "filed_on": "2026-09-24",
                    "page_start": number, "page_end": number,
                }
                for number in (1, 2, 3)
            ],
        }
        self.evidence = {
            "schema_version": 1,
            "evidence_items": [
                {
                    "evidence_id": "EVD-001", "claim_ids": ["CLM-001"],
                    "type": "time_record", "source_document_id": "DOC-001",
                    "source_locator": "DOC-001, página 1", "proposition": "Registro de jornada",
                    "relation": "supports_claim", "limitations": ["Autenticidade pendente"],
                    "analysis_status": "pending", "conflicts_with_evidence_ids": [],
                },
                {
                    "evidence_id": "EVD-002", "claim_ids": ["CLM-002"],
                    "type": "payment_receipt", "source_document_id": "DOC-002",
                    "source_locator": "DOC-002, página 2", "proposition": "Recibo de pagamento",
                    "relation": "opposes_claim", "limitations": [],
                    "analysis_status": "pending", "conflicts_with_evidence_ids": [],
                },
            ],
            "uncovered_claim_ids": [],
        }

    def _write_pdf(self, texts: tuple[str, ...]) -> None:
        writer = PdfWriter()
        for number, content in enumerate(texts, start=1):
            page = PageObject.create_blank_page(width=612, height=792)
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
            })
            stream = DecodedStreamObject()
            stream.set_data(f"BT\n/F1 10 Tf\n30 720 Td\n({content}) Tj\nET\n".encode("ascii"))
            page[NameObject("/Contents")] = stream
            writer.add_page(page)
            writer.add_outline_item(
                f"{number}. 24/09/2026 - Documento sintético - abc000{number}",
                number - 1,
            )
        with self.pdf.open("wb") as destination:
            writer.write(destination)

    def test_selected_claim_contains_only_its_source_pages_and_custody(self) -> None:
        packet = self.api.build_source_evidence_packet(
            self.pdf, self.segments, self.evidence,
            claim_id="CLM-001", evidence_ids=("EVD-001",),
        )

        self.assertIn("CLM-001", packet)
        self.assertIn("EVD-001", packet)
        self.assertIn("DOC-001, página 1", packet)
        self.assertIn("TEXTO FONTE UM", packet)
        self.assertIn(self.segments["source_pdf"]["sha256"], packet)
        self.assertIn("não é citação literal", packet)
        self.assertNotIn("EVD-002", packet)
        self.assertNotIn("TEXTO FONTE DOIS", packet)
        self.assertNotIn("TEXTO NAO SELECIONADO", packet)

    def test_pdf_custody_mismatch_blocks_packet(self) -> None:
        self.segments["source_pdf"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(self.api.SourceEvidencePacketError, "SHA-256"):
            self.api.build_source_evidence_packet(
                self.pdf, self.segments, self.evidence,
                claim_id="CLM-001", evidence_ids=("EVD-001",),
            )

    def test_changed_page_mapping_is_rejected_against_pdf_outline(self) -> None:
        self.segments["documents"][0]["page_start"] = 2
        self.segments["documents"][0]["page_end"] = 2
        with self.assertRaisesRegex(self.api.SourceEvidencePacketError, "sumário"):
            self.api.build_source_evidence_packet(
                self.pdf, self.segments, self.evidence,
                claim_id="CLM-001", evidence_ids=("EVD-001",),
            )

    def test_evidence_from_another_claim_is_rejected(self) -> None:
        with self.assertRaisesRegex(self.api.SourceEvidencePacketError, "pedido"):
            self.api.build_source_evidence_packet(
                self.pdf, self.segments, self.evidence,
                claim_id="CLM-001", evidence_ids=("EVD-002",),
            )

    def test_missing_extractable_text_is_rejected(self) -> None:
        self._write_pdf(("", "TEXTO FONTE DOIS", "TEXTO NAO SELECIONADO"))
        self.segments["source_pdf"]["sha256"] = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        with self.assertRaisesRegex(self.api.SourceEvidencePacketError, "texto"):
            self.api.build_source_evidence_packet(
                self.pdf, self.segments, self.evidence,
                claim_id="CLM-001", evidence_ids=("EVD-001",),
            )

    def test_protected_write_is_exclusive_and_refuses_repository(self) -> None:
        packet = self.api.build_source_evidence_packet(
            self.pdf, self.segments, self.evidence,
            claim_id="CLM-001", evidence_ids=("EVD-001",),
        )
        output = self.directory / "pacote.md"
        result = self.api.write_source_evidence_packet(packet, output)
        self.assertEqual(result, output)
        self.assertEqual(output.read_text(encoding="utf-8"), packet)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        with self.assertRaises(self.api.SourceEvidencePacketError):
            self.api.write_source_evidence_packet("substituir", output)
        self.assertEqual(output.read_text(encoding="utf-8"), packet)
        with self.assertRaises(self.api.SourceEvidencePacketError):
            self.api.write_source_evidence_packet(packet, ROOT / "pacote.md")

    def test_cli_writes_selected_packet_without_printing_source_text(self) -> None:
        segments_path = self.directory / "segmentos.json"
        evidence_path = self.directory / "provas.json"
        segments_path.write_text(json.dumps(self.segments), encoding="utf-8")
        evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        output = self.directory / "pacote.md"

        result = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "prepare_source_evidence_packet.py"),
                "--pdf", str(self.pdf), "--segments", str(segments_path),
                "--evidence", str(evidence_path), "--claim-id", "CLM-001",
                "--evidence-id", "EVD-001", "--output", str(output),
            ],
            text=True, capture_output=True, check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())
        self.assertIn("TEXTO FONTE UM", output.read_text(encoding="utf-8"))
        self.assertNotIn("TEXTO FONTE UM", result.stdout + result.stderr)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
