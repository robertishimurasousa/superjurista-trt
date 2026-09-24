from __future__ import annotations

import hashlib
import importlib
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class CodexDocumentaryRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        self.runner = importlib.import_module("run_codex_documentary_rehearsal")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)

    def _synthetic_response(self, prompt: str) -> str:
        self.assertIn("analista-documental-trt12", prompt)
        self.assertIn("REGISTRO DE JORNADA SINTÉTICO", prompt)
        self.assertNotRegex(
            prompt,
            r"Processo_[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}",
        )
        digest_line = next(
            line for line in prompt.splitlines()
            if line.startswith("SHA-256 UTF-8 do pacote informado pelo orquestrador: ")
        )
        return json.dumps({
            "schema_version": 1,
            "claim_id": "CLM-001",
            "source_packet_sha256": digest_line.rsplit(": ", 1)[1],
            "status": "pending_human_review",
            "observations": [{
                "evidence_id": "EVD-001",
                "source_document_id": "DOC-002",
                "excerpts": [{"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"}],
                "observation": "A página contém o registro citado.",
                "limitations": ["Autenticidade não conferida."],
            }],
        }, ensure_ascii=False)

    def test_generates_only_synthetic_source_and_publishes_validated_observation(self) -> None:
        output = self.runner.run_codex_documentary_rehearsal(
            self.workspace, synthetic_rehearsal=True,
            text_generator=self._synthetic_response,
            model_id="modelo-teste",
        )

        self.assertEqual(output, (self.workspace / "documentary-observations.json").resolve())
        result = json.loads(output.read_text(encoding="utf-8"))
        packet = (self.workspace / "source-evidence-packet.md").read_text(encoding="utf-8")
        self.assertEqual(
            result["source_packet_sha256"], hashlib.sha256(packet.encode("utf-8")).hexdigest()
        )
        self.assertEqual(result["observations"][0]["excerpts"][0]["pdf_page"], 2)
        reader = PdfReader(str(self.workspace / "synthetic-source.pdf"))
        self.assertIn("CAPA SINTÉTICA", reader.pages[0].extract_text())
        self.assertIn("REGISTRO DE JORNADA SINTÉTICO", reader.pages[1].extract_text())
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(
            {path.name for path in self.workspace.iterdir()},
            {
                "synthetic-source.pdf", "pje-pdf-segments.json", "evidence-matrix.json",
                "source-evidence-packet.md", "documentary-observations.json",
                "documentary-rehearsal-summary.json",
                "evidence-review-fragment.json", "conditional-work-result-fragment.json",
            },
        )
        review_path = self.workspace / "evidence-review-fragment.json"
        receipt_path = self.workspace / "conditional-work-result-fragment.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(review["status"], "pending_human_review")
        self.assertEqual(review["assessment"], "")
        self.assertEqual(receipt["work_id"], "WRK-CLM-001-EVIDENCE")
        self.assertEqual(receipt["source_ids"], ["EVD-001"])
        summary_path = self.workspace / "documentary-rehearsal-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["model_id"], "modelo-teste")
        self.assertEqual(summary["execution_mode"], "simulated")
        self.assertEqual(
            summary["observations_sha256"], hashlib.sha256(output.read_bytes()).hexdigest()
        )
        self.assertEqual(summary["source_packet_sha256"], result["source_packet_sha256"])
        self.assertEqual(
            summary["review_fragment_sha256"], hashlib.sha256(review_path.read_bytes()).hexdigest()
        )
        self.assertEqual(
            summary["receipt_fragment_sha256"], hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        )
        self.assertEqual(stat.S_IMODE(summary_path.stat().st_mode), 0o600)

    def test_fabricated_excerpt_cannot_be_published(self) -> None:
        def fabricated(prompt: str) -> str:
            result = json.loads(self._synthetic_response(prompt))
            result["observations"][0]["excerpts"][0]["text"] = "TRECHO INVENTADO"
            return json.dumps(result, ensure_ascii=False)

        with self.assertRaises(self.runner.CodexDocumentaryRehearsalError):
            self.runner.run_codex_documentary_rehearsal(
                self.workspace, synthetic_rehearsal=True, text_generator=fabricated,
                model_id="modelo-teste",
            )
        self.assertFalse((self.workspace / "documentary-observations.json").exists())

    def test_existing_file_blocks_dispatch_and_is_preserved(self) -> None:
        existing = self.workspace / "preservar.txt"
        existing.write_text("manter", encoding="utf-8")

        def forbidden(_prompt: str) -> str:
            self.fail("o agente não deveria ser despachado")

        with self.assertRaises(self.runner.CodexDocumentaryRehearsalError):
            self.runner.run_codex_documentary_rehearsal(
                self.workspace, synthetic_rehearsal=True, text_generator=forbidden,
                model_id="modelo-teste",
            )
        self.assertEqual(existing.read_text(encoding="utf-8"), "manter")
        self.assertEqual(list(self.workspace.iterdir()), [existing])

    def test_no_synthetic_flag_blocks_dispatch(self) -> None:
        with self.assertRaises(self.runner.CodexDocumentaryRehearsalError):
            self.runner.run_codex_documentary_rehearsal(
                self.workspace, model_id="modelo-teste"
            )
        self.assertFalse(any(self.workspace.iterdir()))

    def test_missing_model_id_blocks_dispatch(self) -> None:
        with self.assertRaisesRegex(self.runner.CodexDocumentaryRehearsalError, "modelo"):
            self.runner.run_codex_documentary_rehearsal(
                self.workspace, synthetic_rehearsal=True,
                text_generator=self._synthetic_response,
            )
        self.assertFalse(any(self.workspace.iterdir()))

    def test_invalid_model_id_blocks_dispatch(self) -> None:
        with self.assertRaisesRegex(self.runner.CodexDocumentaryRehearsalError, "modelo"):
            self.runner.run_codex_documentary_rehearsal(
                self.workspace, synthetic_rehearsal=True,
                text_generator=self._synthetic_response, model_id="--versão",
            )
        self.assertFalse(any(self.workspace.iterdir()))

    def test_cli_requires_synthetic_flag(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_codex_documentary_rehearsal.py"),
             "--workspace", str(self.workspace), "--model", "modelo-teste"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--synthetic-rehearsal", completed.stderr)
        self.assertFalse(any(self.workspace.iterdir()))


if __name__ == "__main__":
    unittest.main()
