from __future__ import annotations

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


class EvidenceInventoryBatchTest(unittest.TestCase):
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
        matrix = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]["claim-matrix.json"]
        (self.workspace / "claim-matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
        )
        index = preparer.prepare_evidence_inventory_packets(self.workspace, self.pdf)
        for record in index["records"]:
            document_id = record["document_id"]
            result = {
                "schema_version": 1,
                "source_document_id": document_id,
                "source_packet_sha256": record["packet_sha256"],
                "status": "pending_human_review",
                "coverage_status": "no_item_identified",
                "items": [],
                "limitations": ["Nenhum item foi identificado automaticamente; conferir o PDF."],
            }
            if document_id == "DOC-002":
                result["coverage_status"] = "items_identified"
                result["items"] = [{
                    "item_id": "INV-DOC-002-001",
                    "claim_ids": ["CLM-001"],
                    "type": "time_record",
                    "excerpt": {"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"},
                    "description": "A página contém o título citado.",
                    "limitations": ["O conteúdo integral exige conferência humana."],
                }]
                result["limitations"] = []
            (self.workspace / f"{document_id}-inventory-observations.json").write_text(
                json.dumps(result, ensure_ascii=False), encoding="utf-8"
            )

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("validate_evidence_inventory_batch"))
        return importlib.import_module("validate_evidence_inventory_batch")

    def test_accepts_only_complete_document_coverage(self) -> None:
        summary = self.api().validate_evidence_inventory_batch(self.workspace)
        self.assertEqual(summary, {
            "document_count": 2,
            "item_count": 1,
            "no_item_identified_count": 1,
            "insufficient_count": 0,
        })

    def test_missing_observation_rejects_global_coverage(self) -> None:
        (self.workspace / "DOC-001-inventory-observations.json").unlink()
        with self.assertRaises(self.api().EvidenceInventoryBatchError):
            self.api().validate_evidence_inventory_batch(self.workspace)

    def test_extra_observation_rejects_global_coverage(self) -> None:
        (self.workspace / "DOC-999-inventory-observations.json").write_text("{}")
        with self.assertRaises(self.api().EvidenceInventoryBatchError):
            self.api().validate_evidence_inventory_batch(self.workspace)

    def test_altered_index_packet_record_is_rejected(self) -> None:
        path = self.workspace / "evidence-inventory-index.json"
        index = json.loads(path.read_text(encoding="utf-8"))
        index["records"][0]["packet_sha256"] = "0" * 64
        path.write_text(json.dumps(index), encoding="utf-8")
        with self.assertRaises(self.api().EvidenceInventoryBatchError):
            self.api().validate_evidence_inventory_batch(self.workspace)

    def test_empty_index_and_segments_cannot_claim_coverage(self) -> None:
        index_path = self.workspace / "evidence-inventory-index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["records"] = []
        index_path.write_text(json.dumps(index), encoding="utf-8")
        segments_path = self.workspace / "inventory-pje-pdf-segments.json"
        segments = json.loads(segments_path.read_text(encoding="utf-8"))
        segments["documents"] = []
        segments_path.write_text(json.dumps(segments), encoding="utf-8")
        for path in self.workspace.glob("DOC-*-inventory-source.md"):
            path.unlink()
        for path in self.workspace.glob("DOC-*-inventory-observations.json"):
            path.unlink()
        with self.assertRaises(self.api().EvidenceInventoryBatchError):
            self.api().validate_evidence_inventory_batch(self.workspace)

    def test_altered_claim_matrix_is_rejected(self) -> None:
        path = self.workspace / "claim-matrix.json"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(self.api().EvidenceInventoryBatchError):
            self.api().validate_evidence_inventory_batch(self.workspace)

    def test_symlinked_observation_is_rejected(self) -> None:
        path = self.workspace / "DOC-001-inventory-observations.json"
        other = self.workspace / "observacao-copiada.json"
        path.rename(other)
        path.symlink_to(other)
        with self.assertRaises(self.api().EvidenceInventoryBatchError):
            self.api().validate_evidence_inventory_batch(self.workspace)

    def test_symlinked_index_is_rejected_before_loading(self) -> None:
        path = self.workspace / "evidence-inventory-index.json"
        other = self.workspace / "indice-externo.json"
        path.rename(other)
        other.write_text("não é JSON", encoding="utf-8")
        path.symlink_to(other)
        with self.assertRaisesRegex(
            self.api().EvidenceInventoryBatchError, "insumo ausente ou vinculado"
        ):
            self.api().validate_evidence_inventory_batch(self.workspace)

    def test_cli_reports_counts_without_printing_process_text(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_evidence_inventory_batch.py"),
             "--workspace", str(self.workspace)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 documento(s)", result.stdout)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
