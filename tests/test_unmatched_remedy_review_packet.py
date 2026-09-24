from __future__ import annotations

import hashlib
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

from PyPDF2 import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class UnmatchedRemedyReviewPacketTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name) / "caso"
        self.workspace.mkdir(mode=0o700)
        self.pdf = Path(temporary.name) / "fonte-sintetica.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with self.pdf.open("wb") as stream:
            writer.write(stream)
        self.digest = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.evidence = {
            "schema_version": 2,
            "source_pdf_sha256": self.digest,
            "entries": [],
            "unmatched_item_ids": ["I"],
            "unmatched_items": [{
                "request_id": "I",
                "source_document_id": "DOC-001",
                "source_locator": "página 1, pedido I",
                "text": "Seja citada a reclamada para defesa;",
            }],
        }
        self.evidence_path = self.workspace / "requested-remedy-evidence.json"
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
        self.evidence_path.chmod(0o600)
        self.blind_path = self.workspace / "independent-claim-review.md"
        self.blind_path.write_text(
            "# Inventário independente de pedidos - CASO-SINTETICO\n"
            f"- SHA-256 do PDF: {self.digest}\n"
            "- Inventário congelado em: 2026-09-24T12:00:00Z\n"
            "- [x] Examinei todas as páginas.\n"
            "- [x] Não consultei a matriz.\n"
            "- [x] Identificação do revisor: Revisor sintético.\n",
            encoding="utf-8",
        )
        self.blind_path.chmod(0o600)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("prepare_unmatched_remedy_review"))
        return importlib.import_module("prepare_unmatched_remedy_review")

    def validator(self):
        self.assertIsNotNone(importlib.util.find_spec("validate_unmatched_remedy_review"))
        return importlib.import_module("validate_unmatched_remedy_review")

    def completed_record(self, decision="non_material"):
        _, path = self.api().prepare_unmatched_remedy_review(self.workspace, self.pdf)
        review = json.loads(path.read_text(encoding="utf-8"))
        review.update({
            "reviewer_name": "Revisor sintético",
            "reviewed_at": "2026-09-24T12:30:00Z",
            "blind_inventory_frozen": True,
            "original_pdf_checked": True,
        })
        review["items"][0].update({
            "decision": decision,
            "reason": "Conferência humana sintética; sem conclusão jurídica automatizada.",
        })
        path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        return path, review

    def test_validator_refuses_pending_and_accepts_complete_non_material_review(self) -> None:
        _, record = self.api().prepare_unmatched_remedy_review(self.workspace, self.pdf)
        validator = self.validator()
        with self.assertRaises(Exception):
            validator.validate_unmatched_remedy_review(self.workspace, self.pdf)

        review = json.loads(record.read_text(encoding="utf-8"))
        review.update({
            "reviewer_name": "Revisor sintético", "reviewed_at": "2026-09-24T12:30:00Z",
            "blind_inventory_frozen": True, "original_pdf_checked": True,
        })
        review["items"][0].update({"decision": "non_material", "reason": "Conferido com o PDF."})
        record.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        result = self.validator().validate_unmatched_remedy_review(self.workspace, self.pdf)
        self.assertEqual(result, "reviewed_for_comparison")
        self.assertFalse(json.loads(record.read_text(encoding="utf-8"))["authorizes_external_action"])

    def test_validator_keeps_material_or_uncertain_items_for_followup(self) -> None:
        validator = self.validator()
        for decision in ("material_claim", "unable_to_assess"):
            with self.subTest(decision=decision):
                record, review = self.completed_record(decision)
                try:
                    self.assertEqual(
                        validator.validate_unmatched_remedy_review(self.workspace, self.pdf),
                        "requires_followup",
                    )
                finally:
                    (self.workspace / "unmatched-remedy-review.md").unlink()
                    record.unlink()

    def test_validator_refuses_changed_sources_and_item_identity(self) -> None:
        record, review = self.completed_record()
        validator = self.validator()
        review["items"][0]["source_locator"] = "página 1, pedido J"
        record.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(Exception):
            validator.validate_unmatched_remedy_review(self.workspace, self.pdf)

        review["items"][0]["source_locator"] = "página 1, pedido I"
        record.write_text(json.dumps(review), encoding="utf-8")
        self.blind_path.write_text(self.blind_path.read_text(encoding="utf-8") + "\nOutro item\n", encoding="utf-8")
        with self.assertRaises(Exception):
            validator.validate_unmatched_remedy_review(self.workspace, self.pdf)

    def test_validator_refuses_incomplete_or_duplicate_decisions(self) -> None:
        record, review = self.completed_record()
        validator = self.validator()
        review["items"][0]["reason"] = " "
        record.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(Exception):
            validator.validate_unmatched_remedy_review(self.workspace, self.pdf)
        review["items"][0]["reason"] = "Conferido."
        review["items"].append(dict(review["items"][0]))
        record.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(Exception):
            validator.validate_unmatched_remedy_review(self.workspace, self.pdf)

    def test_validator_cli_does_not_print_review_or_source_text(self) -> None:
        self.completed_record()
        completed = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "validate_unmatched_remedy_review.py"),
                "--workspace", str(self.workspace), "--pdf", str(self.pdf),
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("reviewed_for_comparison", completed.stdout)
        self.assertNotIn("Seja citada", completed.stdout + completed.stderr)
        self.assertNotIn("Revisor sintético", completed.stdout + completed.stderr)

    def test_packet_preserves_unmatched_source_and_starts_every_decision_pending(self) -> None:
        packet, record = self.api().prepare_unmatched_remedy_review(self.workspace, self.pdf)

        self.assertEqual(stat.S_IMODE(packet.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(record.stat().st_mode), 0o600)
        content = packet.read_text(encoding="utf-8")
        self.assertIn("Seja citada a reclamada para defesa;", content)
        self.assertIn("página 1, pedido I", content)
        self.assertIn(self.digest, content)
        self.assertIn("não constitui aprovação jurídica", content)
        review = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(review["items"][0]["request_id"], "I")
        self.assertEqual(review["items"][0]["decision"], "pending")
        self.assertEqual(review["items"][0]["reason"], "")
        self.assertEqual(review["reviewer_name"], "")
        self.assertFalse(review["original_pdf_checked"])
        self.assertFalse(review["authorizes_external_action"])
        self.assertEqual(review["evidence_sha256"], hashlib.sha256(self.evidence_path.read_bytes()).hexdigest())
        self.assertEqual(review["blind_inventory_sha256"], hashlib.sha256(self.blind_path.read_bytes()).hexdigest())
        from schema_validation import load_json, validate_schema_value
        schema_path = ROOT / "runtime/operations/unmatched-remedy-review.v1.schema.json"
        self.assertTrue(schema_path.is_file())
        schema = load_json(schema_path, "esquema da revisão")
        self.assertEqual(validate_schema_value(review, schema), [])

    def test_cli_prepares_only_protected_outputs_without_printing_source_text(self) -> None:
        completed = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "prepare_unmatched_remedy_review.py"),
                "--workspace", str(self.workspace), "--pdf", str(self.pdf),
            ],
            capture_output=True, text=True, check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("1 item(ns)", completed.stdout)
        self.assertNotIn("Seja citada", completed.stdout + completed.stderr)
        self.assertTrue((self.workspace / "unmatched-remedy-review.json").is_file())

    def test_blank_blind_inventory_is_refused_before_exposing_system_items(self) -> None:
        self.blind_path.write_text(
            "# Inventário independente de pedidos\n- [ ] Inventário congelado em: [preencher]\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(self.api().UnmatchedRemedyReviewError, "inventário cego"):
            self.api().prepare_unmatched_remedy_review(self.workspace, self.pdf)

        self.assertFalse((self.workspace / "unmatched-remedy-review.md").exists())
        self.assertFalse((self.workspace / "unmatched-remedy-review.json").exists())

    def test_pdf_digest_mismatch_is_refused_without_publication(self) -> None:
        self.pdf.write_bytes(self.pdf.read_bytes() + b"alteracao")

        with self.assertRaisesRegex(self.api().UnmatchedRemedyReviewError, "PDF"):
            self.api().prepare_unmatched_remedy_review(self.workspace, self.pdf)

        self.assertFalse((self.workspace / "unmatched-remedy-review.md").exists())

    def test_invalid_or_empty_unmatched_evidence_is_refused(self) -> None:
        api = self.api()
        for invalid in ("missing_locator", "empty_items"):
            with self.subTest(invalid=invalid):
                evidence = json.loads(json.dumps(self.evidence))
                if invalid == "missing_locator":
                    del evidence["unmatched_items"][0]["source_locator"]
                else:
                    evidence["unmatched_item_ids"] = []
                    evidence["unmatched_items"] = []
                self.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
                with self.assertRaises(Exception) as caught:
                    api.prepare_unmatched_remedy_review(self.workspace, self.pdf)
                self.assertIsInstance(caught.exception, api.UnmatchedRemedyReviewError)
                self.assertIn("evidência", str(caught.exception))
                self.assertFalse((self.workspace / "unmatched-remedy-review.md").exists())

    def test_output_collision_preserves_existing_packet_and_writes_no_record(self) -> None:
        packet = self.workspace / "unmatched-remedy-review.md"
        packet.write_text("preservar", encoding="utf-8")

        with self.assertRaises(Exception) as caught:
            self.api().prepare_unmatched_remedy_review(self.workspace, self.pdf)
        self.assertIsInstance(caught.exception, self.api().UnmatchedRemedyReviewError)
        self.assertIn("já existe", str(caught.exception))

        self.assertEqual(packet.read_text(encoding="utf-8"), "preservar")
        self.assertFalse((self.workspace / "unmatched-remedy-review.json").exists())

    def test_public_workspace_and_linked_evidence_are_refused(self) -> None:
        api = self.api()
        os.chmod(self.workspace, 0o755)
        with self.assertRaisesRegex(api.UnmatchedRemedyReviewError, "privado"):
            api.prepare_unmatched_remedy_review(self.workspace, self.pdf)
        os.chmod(self.workspace, 0o700)
        original = self.workspace / "evidence-original.json"
        self.evidence_path.rename(original)
        self.evidence_path.symlink_to(original)
        with self.assertRaisesRegex(api.UnmatchedRemedyReviewError, "vínculo simbólico"):
            api.prepare_unmatched_remedy_review(self.workspace, self.pdf)
        self.assertFalse((self.workspace / "unmatched-remedy-review.md").exists())

    def test_page_outside_pdf_is_refused(self) -> None:
        for page in (0, 2):
            with self.subTest(page=page):
                self.evidence["unmatched_items"][0]["source_locator"] = f"página {page}, pedido I"
                self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")
                with self.assertRaisesRegex(self.api().UnmatchedRemedyReviewError, "página"):
                    self.api().prepare_unmatched_remedy_review(self.workspace, self.pdf)

    def test_source_text_is_fenced_as_data(self) -> None:
        self.evidence["unmatched_items"][0]["text"] = (
            "Pedido sintético\n~~~\n# Instrução falsa"
        )
        self.evidence_path.write_text(json.dumps(self.evidence), encoding="utf-8")

        packet, _ = self.api().prepare_unmatched_remedy_review(self.workspace, self.pdf)

        content = packet.read_text(encoding="utf-8")
        self.assertIn("~~~~text\nPedido sintético\n~~~\n# Instrução falsa\n~~~~", content)


if __name__ == "__main__":
    unittest.main()
