from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class EvidenceInventoryObservationsTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        preparer = importlib.import_module("prepare_evidence_inventory_packets")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        os.chmod(self.workspace, 0o700)
        self.pdf = self.workspace / "fonte-sintetica.pdf"
        self.pdf.write_bytes(rehearsal._synthetic_pdf())
        self.matrix = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]["claim-matrix.json"]
        (self.workspace / "claim-matrix.json").write_text(
            json.dumps(self.matrix, ensure_ascii=False), encoding="utf-8"
        )
        preparer.prepare_evidence_inventory_packets(self.workspace, self.pdf)
        self.segments = json.loads((self.workspace / "inventory-pje-pdf-segments.json").read_text())
        self.packet = (self.workspace / "DOC-002-inventory-source.md").read_text(encoding="utf-8")
        self.result = {
            "schema_version": 1,
            "source_document_id": "DOC-002",
            "source_packet_sha256": hashlib.sha256(self.packet.encode("utf-8")).hexdigest(),
            "status": "pending_human_review",
            "coverage_status": "items_identified",
            "items": [{
                "item_id": "INV-DOC-002-001",
                "claim_ids": ["CLM-001"],
                "type": "time_record",
                "excerpt": {"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"},
                "description": "A página contém o título citado.",
                "limitations": ["O conteúdo integral exige conferência humana."],
            }],
            "limitations": [],
        }

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("validate_evidence_inventory_observations"))
        return importlib.import_module("validate_evidence_inventory_observations")

    def validate(self) -> None:
        self.api().validate_evidence_inventory_observations(
            self.result, packet=self.packet, pdf_path=self.pdf,
            segments=self.segments, claim_matrix=self.matrix,
            document_id="DOC-002",
        )

    def test_accepts_literal_item_for_known_claim_in_its_document(self) -> None:
        self.validate()

    def test_rejects_excerpt_not_present_in_source_page(self) -> None:
        self.result["items"][0]["excerpt"]["text"] = "TRECHO INVENTADO"
        with self.assertRaises(self.api().EvidenceInventoryObservationsError):
            self.validate()

    def test_rejects_excerpt_from_another_document(self) -> None:
        self.result["items"][0]["excerpt"] = {"pdf_page": 1, "text": "CAPA SINTÉTICA"}
        with self.assertRaises(self.api().EvidenceInventoryObservationsError):
            self.validate()

    def test_rejects_unknown_claim_even_with_literal_excerpt(self) -> None:
        self.result["items"][0]["claim_ids"] = ["CLM-999"]
        with self.assertRaises(self.api().EvidenceInventoryObservationsError):
            self.validate()

    def test_empty_document_observation_requires_explicit_limitation(self) -> None:
        self.result["coverage_status"] = "no_item_identified"
        self.result["items"] = []
        with self.assertRaises(self.api().EvidenceInventoryObservationsError):
            self.validate()
        self.result["limitations"] = ["Nenhum item foi identificado automaticamente; conferir o PDF."]
        self.validate()

    def test_changed_packet_cannot_validate_old_observation(self) -> None:
        self.packet += "\nTexto acrescentado fora do PDF."
        self.result["source_packet_sha256"] = hashlib.sha256(self.packet.encode("utf-8")).hexdigest()
        with self.assertRaises(self.api().EvidenceInventoryObservationsError):
            self.validate()

    def test_cli_checks_observation_without_printing_source_text(self) -> None:
        result_path = self.workspace / "DOC-002-inventory-observations.json"
        result_path.write_text(json.dumps(self.result, ensure_ascii=False), encoding="utf-8")
        command = [
            sys.executable, str(SCRIPTS / "validate_evidence_inventory_observations.py"),
            "--result", str(result_path),
            "--packet", str(self.workspace / "DOC-002-inventory-source.md"),
            "--pdf", str(self.pdf),
            "--segments", str(self.workspace / "inventory-pje-pdf-segments.json"),
            "--matrix", str(self.workspace / "claim-matrix.json"),
            "--document-id", "DOC-002",
        ]

        accepted = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("[OK]", accepted.stdout)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", accepted.stdout + accepted.stderr)

        self.result["items"][0]["excerpt"]["text"] = "TRECHO INVENTADO"
        result_path.write_text(json.dumps(self.result, ensure_ascii=False), encoding="utf-8")
        rejected = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", rejected.stdout + rejected.stderr)


if __name__ == "__main__":
    unittest.main()
