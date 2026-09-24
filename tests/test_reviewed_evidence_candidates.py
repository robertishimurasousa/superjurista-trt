from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REVIEW_NAME = "evidence-inventory-review.json"
MATRIX_NAME = "evidence-matrix-candidates.json"
PROVENANCE_NAME = "evidence-selection-provenance.json"
APPROVAL_NAME = "evidence-matrix-approval.json"
CANONICAL_NAME = "evidence-matrix.json"
PROMOTION_NAME = "evidence-matrix-promotion.json"


class ReviewedEvidenceCandidatesTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        rehearsal = importlib.import_module("run_codex_inventory_rehearsal")
        review_api = importlib.import_module("review_evidence_inventory")
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
            return json.dumps({
                "schema_version": 1,
                "source_document_id": document_id,
                "source_packet_sha256": digest,
                "status": "pending_human_review",
                "coverage_status": "items_identified" if document_id == "DOC-002" else "no_item_identified",
                "items": [{
                    "item_id": "INV-DOC-002-001",
                    "claim_ids": [],
                    "type": "time_record",
                    "excerpt": {"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"},
                    "description": "A página contém o título citado.",
                    "limitations": ["Somente o título foi extraído."],
                }] if document_id == "DOC-002" else [],
                "limitations": [] if document_id == "DOC-002" else [
                    "Nenhum item identificado; conferir o PDF."
                ],
            }, ensure_ascii=False)

        rehearsal.run_codex_inventory_rehearsal(
            self.workspace, synthetic_rehearsal=True,
            text_generator=observations, model_id="modelo-teste",
        )
        review_api.prepare_evidence_inventory_review(self.workspace)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("build_reviewed_evidence_candidates"))
        return importlib.import_module("build_reviewed_evidence_candidates")

    def verifier(self):
        self.assertIsNotNone(importlib.util.find_spec("verify_reviewed_evidence_candidates"))
        return importlib.import_module("verify_reviewed_evidence_candidates")

    def promoter(self):
        self.assertIsNotNone(importlib.util.find_spec("promote_reviewed_evidence_matrix"))
        return importlib.import_module("promote_reviewed_evidence_matrix")

    def _review(self, decision: str = "include") -> dict:
        path = self.workspace / REVIEW_NAME
        review = json.loads(path.read_text(encoding="utf-8"))
        review["reviewer_name"] = "Revisora jurídica fictícia"
        review["reviewed_at"] = "2026-09-24T12:00:00Z"
        for document in review["documents"]:
            document["all_pages_reviewed"] = True
        item = review["items"][0]
        item["decision"] = decision
        item["reason"] = "Decisão fictícia para testar a seleção."
        if decision == "include":
            item.update({
                "selected_type": "document_title",
                "selected_claim_ids": ["CLM-001"],
                "relation": "neutral_context",
                "proposition": "O documento contém o título transcrito.",
                "limitations": ["Somente o título foi extraído."],
            })
        path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        return review

    def assert_no_candidate_outputs(self) -> None:
        self.assertFalse((self.workspace / MATRIX_NAME).exists())
        self.assertFalse((self.workspace / PROVENANCE_NAME).exists())
        self.assertFalse((self.workspace / "evidence-matrix.json").exists())

    def _approval(self, *, acknowledged_claims: list[str] | None = None) -> dict:
        candidate = self.workspace / MATRIX_NAME
        provenance_path = self.workspace / PROVENANCE_NAME
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        matrix = json.loads(candidate.read_text(encoding="utf-8"))
        approval = {
            "schema_version": 1,
            "candidate_matrix_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            "provenance_sha256": hashlib.sha256(provenance_path.read_bytes()).hexdigest(),
            "source_pdf_sha256": provenance["source_pdf_sha256"],
            "review_sha256": provenance["review_sha256"],
            "reviewer_name": "Revisora jurídica fictícia",
            "reviewer_role": "Profissional jurídica fictícia",
            "approved_at": "2026-09-24T13:00:00Z",
            "approval_for_pipeline": True,
            "acknowledged_uncovered_claim_ids": (
                matrix["uncovered_claim_ids"] if acknowledged_claims is None else acknowledged_claims
            ),
        }
        approval_path = self.workspace / APPROVAL_NAME
        approval_path.write_text(
            json.dumps(approval, ensure_ascii=False), encoding="utf-8"
        )
        approval_path.chmod(0o600)
        return approval

    def test_canonical_matrix_requires_explicit_approval_after_candidate_verification(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)

        with self.assertRaises(self.promoter().EvidenceMatrixPromotionError):
            self.promoter().promote_reviewed_evidence_matrix(self.workspace)

        self.assertFalse((self.workspace / CANONICAL_NAME).exists())
        self.assertFalse((self.workspace / PROMOTION_NAME).exists())

    def test_approved_candidates_become_protected_canonical_matrix_with_receipt(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        self._approval()

        matrix_path, receipt_path = self.promoter().promote_reviewed_evidence_matrix(
            self.workspace
        )

        self.assertEqual(matrix_path.read_bytes(), (self.workspace / MATRIX_NAME).read_bytes())
        self.assertEqual(
            {stat.S_IMODE(path.stat().st_mode) for path in (matrix_path, receipt_path)},
            {0o600},
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "declared_approval")
        self.assertEqual(receipt["candidate_matrix_sha256"], hashlib.sha256(matrix_path.read_bytes()).hexdigest())
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(
            self.promoter().verify_promoted_evidence_matrix(self.workspace)["evidence_count"], 1
        )

    def test_promotion_rejects_digest_or_uncovered_claim_mismatch(self) -> None:
        self._review("exclude")
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        approval = self._approval(acknowledged_claims=[])
        with self.assertRaises(self.promoter().EvidenceMatrixPromotionError):
            self.promoter().promote_reviewed_evidence_matrix(self.workspace)
        self.assertFalse((self.workspace / CANONICAL_NAME).exists())
        approval["acknowledged_uncovered_claim_ids"] = ["CLM-001"]
        approval["candidate_matrix_sha256"] = "0" * 64
        (self.workspace / APPROVAL_NAME).write_text(json.dumps(approval), encoding="utf-8")
        with self.assertRaises(self.promoter().EvidenceMatrixPromotionError):
            self.promoter().promote_reviewed_evidence_matrix(self.workspace)
        self.assertFalse((self.workspace / CANONICAL_NAME).exists())

    def test_promoted_matrix_fails_verification_after_source_or_canonical_change(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        self._approval()
        self.promoter().promote_reviewed_evidence_matrix(self.workspace)
        approval_path = self.workspace / APPROVAL_NAME
        original = approval_path.read_bytes()
        approval_path.write_text(original.decode("utf-8") + " ", encoding="utf-8")
        with self.assertRaises(self.promoter().EvidenceMatrixPromotionError):
            self.promoter().verify_promoted_evidence_matrix(self.workspace)
        approval_path.write_bytes(original)
        (self.workspace / CANONICAL_NAME).write_text("{}", encoding="utf-8")
        with self.assertRaises(self.promoter().EvidenceMatrixPromotionError):
            self.promoter().verify_promoted_evidence_matrix(self.workspace)

    def test_promoted_synthetic_matrix_passes_inherited_decision_units_gate(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        self._approval()
        self.promoter().promote_reviewed_evidence_matrix(self.workspace)
        runner = importlib.import_module("run_synthetic_pipeline")
        gate = importlib.import_module("trt12_decision_units_gate")

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            runner.run_synthetic_pipeline(
                "codex", ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json", target
            )
            for source in self.workspace.iterdir():
                if source.name not in {"claim-matrix.json", CANONICAL_NAME}:
                    shutil.copy2(source, target / source.name)
            (target / CANONICAL_NAME).unlink()
            shutil.copy2(self.workspace / CANONICAL_NAME, target / CANONICAL_NAME)
            context = json.loads((target / "case-context.json").read_text(encoding="utf-8"))
            documents = []
            for document_id in ("DOC-001", "DOC-002"):
                content = f"conteudo sintetico {document_id}".encode()
                documents.append({
                    "document_id": document_id,
                    "filename": f"{document_id}.pdf",
                    "mime_type": "application/pdf",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "source_locator": f"evento {document_id}",
                    "download_status": "downloaded",
                    "byte_count": len(content),
                })
            (target / "document-index.json").write_text(json.dumps({
                "schema_version": 1,
                "case": {
                    "case_number": context["case_number"],
                    "tribunal_code": context["court"],
                    "instance": context["instance"],
                    "court_unit": context["court_unit"],
                    "task_id": "TASK-001",
                },
                "status": "complete",
                "page_count": 1,
                "documents": documents,
                "gaps": [],
            }), encoding="utf-8")
            stage = runner._resolve_plan("codex")["contract"]["stages"][3]
            outputs = tuple(
                (target / name).resolve() for name in ("claim-matrix.json", CANONICAL_NAME)
            )

            self.assertEqual(
                self.promoter().verify_promoted_evidence_matrix(target)["evidence_count"], 1
            )
            self.assertTrue(gate.make_decision_units_gate(target)(stage, outputs))
            (target / PROMOTION_NAME).unlink()
            self.assertFalse(gate.make_decision_units_gate(target)(stage, outputs))

    def test_selected_item_uses_existing_builder_and_keeps_source_provenance(self) -> None:
        self._review()

        matrix_path, provenance_path = self.api().publish_reviewed_evidence_candidates(
            self.workspace
        )

        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(len(matrix["evidence_items"]), 1)
        candidate = matrix["evidence_items"][0]
        self.assertEqual(candidate["evidence_id"], "EVD-001")
        self.assertEqual(candidate["type"], "document_title")
        self.assertEqual(candidate["claim_ids"], ["CLM-001"])
        self.assertEqual(candidate["source_document_id"], "DOC-002")
        self.assertEqual(candidate["source_locator"], "DOC-002, página 2")
        self.assertEqual(candidate["relation"], "neutral_context")
        self.assertEqual(candidate["analysis_status"], "pending")
        self.assertEqual(candidate["conflicts_with_evidence_ids"], [])
        self.assertEqual(matrix["uncovered_claim_ids"], [])
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        self.assertEqual(provenance["status"], "candidate_only")
        self.assertEqual(provenance["selections"][0]["item_id"], "INV-DOC-002-001")
        self.assertEqual(provenance["selections"][0]["evidence_id"], "EVD-001")
        self.assertEqual(
            provenance["selections"][0]["excerpt"], "REGISTRO DE JORNADA SINTÉTICO"
        )
        self.assertEqual(
            provenance["candidate_matrix_sha256"], hashlib.sha256(matrix_path.read_bytes()).hexdigest()
        )
        self.assertEqual(
            {stat.S_IMODE(path.stat().st_mode) for path in (matrix_path, provenance_path)},
            {0o600},
        )
        self.assertFalse((self.workspace / "evidence-matrix.json").exists())

    def test_excluded_item_yields_empty_matrix_and_explicit_uncovered_claim(self) -> None:
        self._review("exclude")

        matrix_path, provenance_path = self.api().publish_reviewed_evidence_candidates(
            self.workspace
        )

        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        self.assertEqual(matrix["evidence_items"], [])
        self.assertEqual(matrix["uncovered_claim_ids"], ["CLM-001"])
        self.assertEqual(provenance["excluded_item_ids"], ["INV-DOC-002-001"])
        self.assertEqual(provenance["selections"], [])

    def test_unreviewed_item_cannot_be_promoted(self) -> None:
        with self.assertRaises(self.api().ReviewedEvidenceCandidatesError):
            self.api().publish_reviewed_evidence_candidates(self.workspace)
        self.assert_no_candidate_outputs()

    def test_deferred_item_cannot_be_promoted(self) -> None:
        self._review("defer")
        with self.assertRaises(self.api().ReviewedEvidenceCandidatesError):
            self.api().publish_reviewed_evidence_candidates(self.workspace)
        self.assert_no_candidate_outputs()

    def test_reported_missing_item_cannot_be_promoted(self) -> None:
        review = self._review()
        review["documents"][0]["missing_item_note"] = "Há um item a conferir na página 1."
        (self.workspace / REVIEW_NAME).write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaises(self.api().ReviewedEvidenceCandidatesError):
            self.api().publish_reviewed_evidence_candidates(self.workspace)
        self.assert_no_candidate_outputs()

    def test_existing_candidate_file_is_preserved(self) -> None:
        self._review()
        existing = self.workspace / MATRIX_NAME
        existing.write_text("manter", encoding="utf-8")
        with self.assertRaises(self.api().ReviewedEvidenceCandidatesError):
            self.api().publish_reviewed_evidence_candidates(self.workspace)
        self.assertEqual(existing.read_text(encoding="utf-8"), "manter")
        self.assertFalse((self.workspace / PROVENANCE_NAME).exists())

    def test_cli_reports_counts_without_printing_source(self) -> None:
        self._review()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_reviewed_evidence_candidates.py"),
             "--workspace", str(self.workspace)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 candidato(s)", result.stdout)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", result.stdout + result.stderr)
        self.assertFalse((self.workspace / "evidence-matrix.json").exists())

    def test_independent_verifier_rebuilds_published_candidate_bundle(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)

        result = self.verifier().verify_reviewed_evidence_candidates(self.workspace)

        self.assertEqual(result, {
            "candidate_count": 1, "uncovered_claim_count": 0,
            "excluded_count": 0,
        })

    def test_verifier_rejects_tampered_candidate_matrix(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        path = self.workspace / MATRIX_NAME
        matrix = json.loads(path.read_text(encoding="utf-8"))
        matrix["evidence_items"][0]["proposition"] = "Proposição alterada."
        path.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(self.verifier().ReviewedEvidenceVerificationError):
            self.verifier().verify_reviewed_evidence_candidates(self.workspace)
        self.assertFalse((self.workspace / "evidence-matrix.json").exists())

    def test_verifier_rejects_tampered_provenance(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        path = self.workspace / PROVENANCE_NAME
        provenance = json.loads(path.read_text(encoding="utf-8"))
        provenance["selections"][0]["item_id"] = "INV-DOC-001-999"
        path.write_text(json.dumps(provenance, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(self.verifier().ReviewedEvidenceVerificationError):
            self.verifier().verify_reviewed_evidence_candidates(self.workspace)

    def test_verifier_rejects_review_changed_after_candidate_publication(self) -> None:
        review = self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        review["items"][0]["reason"] = "Justificativa posterior, sem republicação."
        (self.workspace / REVIEW_NAME).write_text(
            json.dumps(review, ensure_ascii=False), encoding="utf-8"
        )

        with self.assertRaises(self.verifier().ReviewedEvidenceVerificationError):
            self.verifier().verify_reviewed_evidence_candidates(self.workspace)

    def test_verifier_rejects_missing_candidate_file(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        (self.workspace / PROVENANCE_NAME).unlink()

        with self.assertRaises(self.verifier().ReviewedEvidenceVerificationError):
            self.verifier().verify_reviewed_evidence_candidates(self.workspace)

    def test_verifier_rejects_linked_candidate_file(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        path = self.workspace / MATRIX_NAME
        original = self.workspace / "candidate-original.json"
        path.rename(original)
        path.symlink_to(original)

        with self.assertRaises(self.verifier().ReviewedEvidenceVerificationError):
            self.verifier().verify_reviewed_evidence_candidates(self.workspace)

    def test_verifier_rejects_changed_source_pdf(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        index = json.loads(
            (self.workspace / "evidence-inventory-index.json").read_text(encoding="utf-8")
        )
        source = self.workspace / index["source_pdf_name"]
        source.write_bytes(source.read_bytes() + b"\n")

        with self.assertRaises(self.verifier().ReviewedEvidenceVerificationError):
            self.verifier().verify_reviewed_evidence_candidates(self.workspace)

    def test_verifier_cli_does_not_print_source_text(self) -> None:
        self._review()
        self.api().publish_reviewed_evidence_candidates(self.workspace)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "verify_reviewed_evidence_candidates.py"),
             "--workspace", str(self.workspace)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 candidato(s)", result.stdout)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
