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

    def test_packet_binds_current_artifacts_without_approving_judgment(self) -> None:
        api = self.packet_api()

        path = api.prepare_final_human_review(self.workspace)
        content = path.read_text(encoding="utf-8")
        draft_hash = hashlib.sha256(
            (self.workspace / "judgment-draft.md").read_bytes()
        ).hexdigest()

        self.assertEqual(path.name, "final-human-review.md")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn("CLM-001", content)
        self.assertIn("judgment-draft.md", content)
        self.assertIn(draft_hash, content)
        self.assertIn("PDF original", content)
        self.assertIn("não constitui aprovação jurídica", content)
        self.assertIn("Revisor(a): [preencher]", content)
        self.assertNotIn("[x]", content)

    def test_changed_draft_is_refused_before_publication(self) -> None:
        api = self.packet_api()
        draft = self.workspace / "judgment-draft.md"
        draft.write_text(draft.read_text(encoding="utf-8") + "\nAlteração.\n")

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "controle da minuta"):
            api.prepare_final_human_review(self.workspace)

        self.assertFalse((self.workspace / "final-human-review.md").exists())

    def test_symlinked_source_is_refused_before_publication(self) -> None:
        api = self.packet_api()
        source = self.workspace / "source-manifest.json"
        original = self.workspace / "original.json"
        source.rename(original)
        source.symlink_to(original)

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "vínculo simbólico"):
            api.prepare_final_human_review(self.workspace)

        self.assertFalse((self.workspace / "final-human-review.md").exists())

    def test_existing_packet_is_preserved(self) -> None:
        api = self.packet_api()
        path = api.prepare_final_human_review(self.workspace)
        original = path.read_bytes()

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "já existe"):
            api.prepare_final_human_review(self.workspace)

        self.assertEqual(path.read_bytes(), original)

    def test_public_workspace_is_refused(self) -> None:
        api = self.packet_api()
        os.chmod(self.workspace, 0o755)

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "privado"):
            api.prepare_final_human_review(self.workspace)

        self.assertFalse((self.workspace / "final-human-review.md").exists())

    def test_case_number_cannot_make_a_source_path_escape_the_workspace(self) -> None:
        api = self.packet_api()
        context_path = self.workspace / "case-context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["case_number"] = "../outside"
        context_path.write_text(json.dumps(context), encoding="utf-8")

        with self.assertRaisesRegex(api.FinalHumanReviewPacketError, "número do processo"):
            api.prepare_final_human_review(self.workspace)

        self.assertFalse((self.workspace / "final-human-review.md").exists())


if __name__ == "__main__":
    unittest.main()
