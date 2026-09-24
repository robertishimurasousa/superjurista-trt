from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class FinalHumanReviewPacketTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name) / "case"
        self.workspace.mkdir(mode=0o700)
        runner = importlib.import_module("run_synthetic_pipeline")
        runner.run_synthetic_pipeline("codex", FIXTURE, self.workspace)
        context = json.loads((self.workspace / "case-context.json").read_text(encoding="utf-8"))
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
        index = {
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
        }
        (self.workspace / "document-index.json").write_text(
            json.dumps(index), encoding="utf-8"
        )

    def packet_api(self):
        try:
            return importlib.import_module("prepare_final_human_review")
        except ModuleNotFoundError as error:
            self.fail(f"preparador do roteiro final ausente: {error}")

    def review_api(self):
        try:
            return importlib.import_module("validate_final_human_review")
        except ModuleNotFoundError as error:
            self.fail(f"validador da revisão final ausente: {error}")

    def complete_review(self, *, decision: str = "agree") -> dict:
        record_path = self.workspace / "final-human-review.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["reviewer_name"] = "Revisor jurídico sintético"
        record["reviewed_at"] = "2026-09-24T12:00:00Z"
        record["blind_inventory_frozen"] = True
        record["original_pdf_checked"] = True
        for claim in record["claims"]:
            claim["source_checked"] = True
            claim["law_checked"] = True
            claim["draft_checked"] = True
            claim["decision"] = decision
            claim["reason"] = "Justificativa sintética para conferência do contrato."
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return record

    def validate_with_synthetic_outcome(self, outcome: str) -> dict:
        """Isola a classificação do estado sem simular aprovação jurídica."""
        self.packet_api().prepare_final_human_review(self.workspace)
        self.complete_review()
        api = self.review_api()
        sources = self.packet_api().current_review_sources(self.workspace)
        analysis = json.loads(json.dumps(sources[3]))
        analysis["analyses"][0]["proposed_outcome"] = outcome
        record_path = self.workspace / "final-human-review.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["claims"][0]["proposed_outcome"] = outcome
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        with patch.object(api, "current_review_sources", return_value=(*sources[:3], analysis, sources[4])):
            return api.validate_final_human_review(self.workspace)

    def test_packet_binds_current_artifacts_without_approving_judgment(self) -> None:
        api = self.packet_api()

        path = api.prepare_final_human_review(self.workspace)
        content = path.read_text(encoding="utf-8")
        draft_hash = hashlib.sha256(
            (self.workspace / "judgment-draft.md").read_bytes()
        ).hexdigest()

        self.assertEqual(path.name, "final-human-review.md")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        record_path = self.workspace / "final-human-review.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(record_path.stat().st_mode), 0o600)
        self.assertEqual(record["claims"][0]["decision"], "pending")
        self.assertEqual(record["reviewer_name"], "")
        self.assertFalse(record["blind_inventory_frozen"])
        self.assertEqual(
            next(item["sha256"] for item in record["source_hashes"]
                 if item["name"] == "judgment-draft.md"),
            draft_hash,
        )
        self.assertIn("CLM-001", content)
        self.assertIn("judgment-draft.md", content)
        self.assertIn(draft_hash, content)
        self.assertIn("PDF original", content)
        self.assertIn("não constitui aprovação jurídica", content)
        self.assertIn("Revisor(a): [preencher em `final-human-review.json`]", content)
        self.assertNotIn("[x]", content)

    def test_changed_draft_is_refused_before_publication(self) -> None:
        api = self.packet_api()
        draft = self.workspace / "judgment-draft.md"
        draft.write_text(draft.read_text(encoding="utf-8") + "\nAlteração.\n")

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "controle da minuta"):
            api.prepare_final_human_review(self.workspace)

        self.assertFalse((self.workspace / "final-human-review.md").exists())
        self.assertFalse((self.workspace / "final-human-review.json").exists())

    def test_symlinked_source_is_refused_before_publication(self) -> None:
        api = self.packet_api()
        source = self.workspace / "source-manifest.json"
        original = self.workspace / "original.json"
        source.rename(original)
        source.symlink_to(original)

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "vínculo simbólico"):
            api.prepare_final_human_review(self.workspace)

        self.assertFalse((self.workspace / "final-human-review.md").exists())
        self.assertFalse((self.workspace / "final-human-review.json").exists())

    def test_existing_packet_is_preserved(self) -> None:
        api = self.packet_api()
        path = api.prepare_final_human_review(self.workspace)
        original = path.read_bytes()
        review_path = self.workspace / "final-human-review.json"
        original_review = review_path.read_bytes()

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "já existe"):
            api.prepare_final_human_review(self.workspace)

        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(review_path.read_bytes(), original_review)

    def test_existing_review_record_prevents_partial_packet(self) -> None:
        api = self.packet_api()
        record_path = self.workspace / "final-human-review.json"
        record_path.write_text("registro anterior", encoding="utf-8")

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "já existe"):
            api.prepare_final_human_review(self.workspace)

        self.assertEqual(record_path.read_text(encoding="utf-8"), "registro anterior")
        self.assertFalse((self.workspace / "final-human-review.md").exists())

    def test_public_workspace_is_refused(self) -> None:
        api = self.packet_api()
        os.chmod(self.workspace, 0o755)

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "privado"):
            api.prepare_final_human_review(self.workspace)

        self.assertFalse((self.workspace / "final-human-review.md").exists())
        self.assertFalse((self.workspace / "final-human-review.json").exists())

    def test_case_number_cannot_make_a_source_path_escape_the_workspace(self) -> None:
        api = self.packet_api()
        context_path = self.workspace / "case-context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["case_number"] = "../outside"
        context_path.write_text(json.dumps(context), encoding="utf-8")

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "número do processo"):
            api.prepare_final_human_review(self.workspace)

        self.assertFalse((self.workspace / "final-human-review.md").exists())
        self.assertFalse((self.workspace / "final-human-review.json").exists())

    def test_unfilled_record_cannot_be_reported_as_reviewed(self) -> None:
        self.packet_api().prepare_final_human_review(self.workspace)
        api = self.review_api()

        with self.assertRaisesRegex(api.FinalHumanReviewError, "pendente"):
            api.validate_final_human_review(self.workspace)

    def test_agreement_cannot_resolve_pending_proposed_outcome(self) -> None:
        self.packet_api().prepare_final_human_review(self.workspace)
        self.complete_review()
        api = self.review_api()

        result = api.validate_final_human_review(self.workspace)

        self.assertEqual(result["status"], "requires_followup")
        self.assertEqual(result["claim_count"], 1)
        self.assertFalse(result["authorizes_external_action"])

    def test_agreement_on_abstention_still_requires_followup(self) -> None:
        result = self.validate_with_synthetic_outcome("abstained")

        self.assertEqual(result["status"], "requires_followup")
        self.assertFalse(result["authorizes_external_action"])

    def test_agreement_on_resolved_outcome_is_only_for_consideration(self) -> None:
        result = self.validate_with_synthetic_outcome("denied")

        self.assertEqual(result["status"], "reviewed_for_consideration")
        self.assertFalse(result["authorizes_external_action"])

    def test_correction_remains_followup_not_acceptance(self) -> None:
        self.packet_api().prepare_final_human_review(self.workspace)
        self.complete_review(decision="requires_correction")
        api = self.review_api()

        self.assertEqual(
            api.validate_final_human_review(self.workspace)["status"],
            "requires_followup",
        )

    def test_changed_source_invalidates_completed_review(self) -> None:
        self.packet_api().prepare_final_human_review(self.workspace)
        self.complete_review()
        source = self.workspace / "source-manifest.json"
        source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        api = self.review_api()

        with self.assertRaisesRegex(api.FinalHumanReviewError, "fontes divergem"):
            api.validate_final_human_review(self.workspace)

    def test_duplicate_claim_cannot_hide_missing_review(self) -> None:
        self.packet_api().prepare_final_human_review(self.workspace)
        record = self.complete_review()
        record["claims"].append(dict(record["claims"][0]))
        (self.workspace / "final-human-review.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        api = self.review_api()

        with self.assertRaisesRegex(api.FinalHumanReviewError, "cobertura dos pedidos"):
            api.validate_final_human_review(self.workspace)


if __name__ == "__main__":
    unittest.main()
