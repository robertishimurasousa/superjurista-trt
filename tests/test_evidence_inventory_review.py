from __future__ import annotations

import importlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REVIEW_NAME = "evidence-inventory-review.json"


class EvidenceInventoryReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        rehearsal = importlib.import_module("run_codex_inventory_rehearsal")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        os.chmod(self.workspace, 0o700)

        def observations(prompt: str) -> str:
            document_id = next(
                line.split(": ", 1)[1] for line in prompt.splitlines()
                if line.startswith("Documento: ")
            )
            digest = next(
                line.split(": ", 1)[1] for line in prompt.splitlines()
                if line.startswith("SHA-256 UTF-8 do pacote informado pelo orquestrador: ")
            )
            item = {
                "item_id": "INV-DOC-002-001",
                "claim_ids": ["CLM-001"],
                "type": "time_record",
                "excerpt": {"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"},
                "description": "A página contém o título citado.",
                "limitations": ["Conteúdo integral não conferido."],
            }
            return json.dumps({
                "schema_version": 1,
                "source_document_id": document_id,
                "source_packet_sha256": digest,
                "status": "pending_human_review",
                "coverage_status": "items_identified" if document_id == "DOC-002" else "no_item_identified",
                "items": [item] if document_id == "DOC-002" else [],
                "limitations": [] if document_id == "DOC-002" else [
                    "Nenhum item identificado automaticamente; conferir o PDF."
                ],
            }, ensure_ascii=False)

        rehearsal.run_codex_inventory_rehearsal(
            self.workspace, synthetic_rehearsal=True,
            text_generator=observations, model_id="modelo-teste",
        )

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("review_evidence_inventory"))
        return importlib.import_module("review_evidence_inventory")

    def packet_api(self):
        self.assertIsNotNone(importlib.util.find_spec("prepare_evidence_inventory_review_packet"))
        return importlib.import_module("prepare_evidence_inventory_review_packet")

    def _prepared_review(self) -> dict:
        self.api().prepare_evidence_inventory_review(self.workspace)
        return json.loads((self.workspace / REVIEW_NAME).read_text(encoding="utf-8"))

    def _complete_review(self) -> dict:
        review = self._prepared_review()
        review["reviewer_name"] = "Revisora técnica fictícia"
        review["reviewed_at"] = "2026-09-24T12:00:00Z"
        for document in review["documents"]:
            document["all_pages_reviewed"] = True
        item = review["items"][0]
        item.update({
            "decision": "include",
            "selected_type": "document_title",
            "selected_claim_ids": ["CLM-001"],
            "relation": "neutral_context",
            "proposition": "O documento contém o título transcrito.",
            "reason": "Seleção fictícia para testar o fluxo de revisão.",
            "limitations": ["Somente o título foi extraído."],
        })
        (self.workspace / REVIEW_NAME).write_text(
            json.dumps(review, ensure_ascii=False), encoding="utf-8"
        )
        return review

    def test_prepares_one_pending_decision_per_item_and_each_document(self) -> None:
        review = self._prepared_review()

        self.assertEqual([item["document_id"] for item in review["documents"]], [
            "DOC-001", "DOC-002",
        ])
        self.assertEqual([item["item_id"] for item in review["items"]], [
            "INV-DOC-002-001",
        ])
        self.assertEqual(review["items"][0]["decision"], "pending")
        self.assertEqual(review["items"][0]["proposed_claim_ids"], ["CLM-001"])
        self.assertIn("source_type", review["items"][0])
        self.assertEqual(review["items"][0]["source_type"], "time_record")
        self.assertEqual(review["items"][0]["selected_type"], "")
        self.assertEqual(review["items"][0]["selected_claim_ids"], [])
        self.assertTrue(all(not item["all_pages_reviewed"] for item in review["documents"]))
        self.assertFalse((self.workspace / "evidence-matrix.json").exists())
        self.assertEqual(stat.S_IMODE((self.workspace / REVIEW_NAME).stat().st_mode), 0o600)

    def test_final_review_requires_explicit_selection_and_source_check(self) -> None:
        self._complete_review()

        result = self.api().validate_evidence_inventory_review(self.workspace)

        self.assertEqual(result, {
            "document_count": 2, "item_count": 1, "included_count": 1,
            "excluded_count": 0, "deferred_count": 0, "missing_item_note_count": 0,
            "status": "reviewed_for_selection",
        })
        self.assertFalse((self.workspace / "evidence-matrix.json").exists())

    def test_pending_item_does_not_pass_as_completed_review(self) -> None:
        review = self._prepared_review()
        review["reviewer_name"] = "Revisora fictícia"
        review["reviewed_at"] = "2026-09-24T12:00:00Z"
        for document in review["documents"]:
            document["all_pages_reviewed"] = True
        (self.workspace / REVIEW_NAME).write_text(json.dumps(review), encoding="utf-8")

        with self.assertRaises(self.api().EvidenceInventoryReviewError):
            self.api().validate_evidence_inventory_review(self.workspace)

    def test_unread_document_does_not_pass_as_completed_review(self) -> None:
        review = self._complete_review()
        review["documents"][0]["all_pages_reviewed"] = False
        (self.workspace / REVIEW_NAME).write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(self.api().EvidenceInventoryReviewError):
            self.api().validate_evidence_inventory_review(self.workspace)

    def test_tampered_excerpt_cannot_be_silently_approved(self) -> None:
        review = self._complete_review()
        review["items"][0]["excerpt"] = "TRECHO INVENTADO"
        (self.workspace / REVIEW_NAME).write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(self.api().EvidenceInventoryReviewError):
            self.api().validate_evidence_inventory_review(self.workspace)

    def test_unknown_selected_claim_is_rejected(self) -> None:
        review = self._complete_review()
        review["items"][0]["selected_claim_ids"] = ["CLM-999"]
        (self.workspace / REVIEW_NAME).write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(self.api().EvidenceInventoryReviewError):
            self.api().validate_evidence_inventory_review(self.workspace)

    def test_included_item_requires_type_selected_by_reviewer(self) -> None:
        review = self._complete_review()
        review["items"][0]["selected_type"] = ""
        (self.workspace / REVIEW_NAME).write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(self.api().EvidenceInventoryReviewError):
            self.api().validate_evidence_inventory_review(self.workspace)

    def test_deferred_item_is_reported_as_followup_not_selection(self) -> None:
        review = self._complete_review()
        review["items"][0].update({
            "decision": "defer", "selected_type": "", "selected_claim_ids": [], "relation": "",
            "proposition": "", "reason": "Conferir original físico.", "limitations": [],
        })
        (self.workspace / REVIEW_NAME).write_text(json.dumps(review), encoding="utf-8")
        result = self.api().validate_evidence_inventory_review(self.workspace)
        self.assertEqual(result["deferred_count"], 1)
        self.assertEqual(result["status"], "requires_followup")

    def test_insufficient_source_stays_visible_as_followup(self) -> None:
        source = self.workspace / "DOC-001-inventory-observations.json"
        observation = json.loads(source.read_text(encoding="utf-8"))
        observation["status"] = "insufficient"
        source.write_text(json.dumps(observation, ensure_ascii=False), encoding="utf-8")
        self._complete_review()

        result = self.api().validate_evidence_inventory_review(self.workspace)

        self.assertEqual(result["status"], "requires_followup")

    def test_existing_review_is_preserved_without_overwrite(self) -> None:
        path = self.workspace / REVIEW_NAME
        path.write_text("manter", encoding="utf-8")
        with self.assertRaises(self.api().EvidenceInventoryReviewError):
            self.api().prepare_evidence_inventory_review(self.workspace)
        self.assertEqual(path.read_text(encoding="utf-8"), "manter")

    def test_cli_reports_counts_without_exposing_source_text(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "review_evidence_inventory.py"),
             "prepare", "--workspace", str(self.workspace)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 documento(s)", result.stdout)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", result.stdout + result.stderr)

    def test_review_packet_guides_page_and_item_checks_without_deciding(self) -> None:
        self._prepared_review()

        path = self.packet_api().prepare_evidence_inventory_review_packet(self.workspace)

        content = path.read_text(encoding="utf-8")
        self.assertIn("DOC-001 — páginas 1–1", content)
        self.assertIn("DOC-002 — páginas 2–2", content)
        self.assertIn("INV-DOC-002-001", content)
        self.assertIn("REGISTRO DE JORNADA SINTÉTICO", content)
        self.assertIn("synthetic-source.pdf", content)
        self.assertIn("CLM-001", content)
        self.assertIn("- [ ]", content)
        self.assertIn("não substitui a leitura do PDF original", content)
        self.assertNotIn("Decisão: include", content)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertFalse((self.workspace / "evidence-matrix.json").exists())

    def test_review_packet_refuses_changed_pending_template(self) -> None:
        review = self._prepared_review()
        review["items"][0]["excerpt"] = "TRECHO ALTERADO"
        (self.workspace / REVIEW_NAME).write_text(
            json.dumps(review, ensure_ascii=False), encoding="utf-8"
        )

        with self.assertRaises(self.packet_api().EvidenceInventoryReviewPacketError):
            self.packet_api().prepare_evidence_inventory_review_packet(self.workspace)
        self.assertFalse((self.workspace / "evidence-inventory-review-packet.md").exists())

    def test_review_packet_preserves_existing_output(self) -> None:
        self._prepared_review()
        path = self.workspace / "evidence-inventory-review-packet.md"
        path.write_text("preservar", encoding="utf-8")

        with self.assertRaises(self.packet_api().EvidenceInventoryReviewPacketError):
            self.packet_api().prepare_evidence_inventory_review_packet(self.workspace)
        self.assertEqual(path.read_text(encoding="utf-8"), "preservar")

    def test_review_packet_cli_reports_counts_without_source_text(self) -> None:
        self._prepared_review()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "prepare_evidence_inventory_review_packet.py"),
             "--workspace", str(self.workspace)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 documento(s)", result.stdout)
        self.assertIn("1 item(ns)", result.stdout)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
