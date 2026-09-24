from __future__ import annotations

import hashlib
import importlib
import json
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


class DocumentaryObservationsTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        self.validator = importlib.import_module("validate_documentary_observations")
        self.packet_builder = importlib.import_module("prepare_source_evidence_packet")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.pdf = Path(temporary.name) / "fonte.pdf"
        writer = PdfWriter()
        for number, content in enumerate(("REGISTRO DE JORNADA", "RECIBO DE PAGAMENTO"), start=1):
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
        with self.pdf.open("wb") as output:
            writer.write(output)
        self.segments = {
            "schema_version": 1,
            "segmentation_method": "pje_pdf_outline",
            "source_pdf": {
                "sha256": hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
                "page_count": 2,
            },
            "documents": [
                {
                    "document_id": f"DOC-{number:03d}",
                    "provider_reference": f"abc000{number}",
                    "provider_type": "Documento sintético",
                    "filed_on": "2026-09-24",
                    "page_start": number,
                    "page_end": number,
                }
                for number in (1, 2)
            ],
        }
        self.evidence = {
            "schema_version": 1,
            "evidence_items": [
                {
                    "evidence_id": f"EVD-{number:03d}",
                    "claim_ids": ["CLM-001"],
                    "type": "time_record" if number == 1 else "payment_receipt",
                    "source_document_id": f"DOC-{number:03d}",
                    "source_locator": f"DOC-{number:03d}, página {number}",
                    "proposition": "Proposição sintética",
                    "relation": "supports_claim",
                    "limitations": [],
                    "analysis_status": "pending",
                    "conflicts_with_evidence_ids": [],
                }
                for number in (1, 2)
            ],
            "uncovered_claim_ids": [],
        }
        self.selected = ("EVD-001", "EVD-002")
        self.packet = self.packet_builder.build_source_evidence_packet(
            self.pdf, self.segments, self.evidence,
            claim_id="CLM-001", evidence_ids=self.selected,
        )
        self.result = {
            "schema_version": 1,
            "claim_id": "CLM-001",
            "source_packet_sha256": hashlib.sha256(self.packet.encode("utf-8")).hexdigest(),
            "status": "pending_human_review",
            "observations": [
                {
                    "evidence_id": f"EVD-{number:03d}",
                    "source_document_id": f"DOC-{number:03d}",
                    "excerpts": [{"pdf_page": number, "text": content}],
                    "observation": "O texto citado aparece na página indicada.",
                    "limitations": ["Autenticidade não verificada."],
                }
                for number, content in enumerate(
                    ("REGISTRO DE JORNADA", "RECIBO DE PAGAMENTO"), start=1
                )
            ],
        }

    def validate(self) -> None:
        self.validator.validate_documentary_observations(
            self.result, packet=self.packet, pdf_path=self.pdf,
            segments=self.segments, evidence_matrix=self.evidence,
            claim_id="CLM-001", evidence_ids=self.selected,
        )

    def test_accepts_literal_excerpts_for_every_selected_evidence(self) -> None:
        self.validate()

    def test_rejects_excerpt_that_is_only_a_matrix_proposition(self) -> None:
        self.result["observations"][0]["excerpts"][0]["text"] = "Proposição sintética"
        with self.assertRaisesRegex(self.validator.DocumentaryObservationsError, "literal"):
            self.validate()

    def test_rejects_excerpt_from_other_page_even_if_in_selected_packet(self) -> None:
        self.result["observations"][0]["excerpts"][0]["text"] = "RECIBO DE PAGAMENTO"
        with self.assertRaisesRegex(self.validator.DocumentaryObservationsError, "literal"):
            self.validate()

    def test_rejects_missing_selected_evidence(self) -> None:
        self.result["observations"].pop()
        with self.assertRaisesRegex(self.validator.DocumentaryObservationsError, "cobertura"):
            self.validate()

    def test_rejects_duplicate_evidence(self) -> None:
        self.result["observations"].append(dict(self.result["observations"][0]))
        with self.assertRaisesRegex(self.validator.DocumentaryObservationsError, "duplicada"):
            self.validate()

    def test_rejects_wrong_document_for_evidence(self) -> None:
        self.result["observations"][0]["source_document_id"] = "DOC-002"
        with self.assertRaisesRegex(self.validator.DocumentaryObservationsError, "documento"):
            self.validate()

    def test_rejects_changed_packet_even_with_updated_result_hash(self) -> None:
        self.packet += "\nTEXTO INJETADO"
        self.result["source_packet_sha256"] = hashlib.sha256(
            self.packet.encode("utf-8")
        ).hexdigest()
        with self.assertRaisesRegex(self.validator.DocumentaryObservationsError, "pacote"):
            self.validate()

    def test_rejects_status_reviewed(self) -> None:
        self.result["status"] = "reviewed"
        with self.assertRaises(self.validator.DocumentaryObservationsError):
            self.validate()

    def test_insufficient_requires_limitations_when_excerpt_missing(self) -> None:
        self.result["status"] = "insufficient"
        self.result["observations"][0]["excerpts"] = []
        self.result["observations"][0]["limitations"] = []
        with self.assertRaisesRegex(self.validator.DocumentaryObservationsError, "limitação"):
            self.validate()

    def test_insufficient_allows_explicit_gap_without_excerpt(self) -> None:
        self.result["status"] = "insufficient"
        self.result["observations"][0]["excerpts"] = []
        self.validate()

    def test_insufficient_requires_at_least_one_missing_excerpt(self) -> None:
        self.result["status"] = "insufficient"
        with self.assertRaisesRegex(self.validator.DocumentaryObservationsError, "insufficient"):
            self.validate()

    def test_cli_does_not_print_unexpected_result_text(self) -> None:
        directory = self.pdf.parent
        paths = {
            "result": directory / "resultado.json",
            "packet": directory / "pacote.md",
            "segments": directory / "segmentos.json",
            "evidence": directory / "evidencias.json",
        }
        self.result["status"] = "TEXTO SIGILOSO INESPERADO"
        paths["result"].write_text(json.dumps(self.result), encoding="utf-8")
        paths["packet"].write_text(self.packet, encoding="utf-8")
        paths["segments"].write_text(json.dumps(self.segments), encoding="utf-8")
        paths["evidence"].write_text(json.dumps(self.evidence), encoding="utf-8")

        completed = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "validate_documentary_observations.py"),
                "--result", str(paths["result"]), "--packet", str(paths["packet"]),
                "--pdf", str(self.pdf), "--segments", str(paths["segments"]),
                "--evidence", str(paths["evidence"]), "--claim-id", "CLM-001",
                "--evidence-id", "EVD-001", "--evidence-id", "EVD-002",
            ], capture_output=True, text=True, check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("TEXTO SIGILOSO INESPERADO", completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
