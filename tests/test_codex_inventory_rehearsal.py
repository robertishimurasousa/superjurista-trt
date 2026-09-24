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


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class CodexInventoryRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        os.chmod(self.workspace, 0o700)
        self.prompts: list[str] = []

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("run_codex_inventory_rehearsal"))
        return importlib.import_module("run_codex_inventory_rehearsal")

    def _synthetic_response(self, prompt: str) -> str:
        self.prompts.append(prompt)
        document_id = next(
            line.split(": ", 1)[1] for line in prompt.splitlines()
            if line.startswith("Documento: ")
        )
        digest = next(
            line.split(": ", 1)[1] for line in prompt.splitlines()
            if line.startswith("SHA-256 UTF-8 do pacote informado pelo orquestrador: ")
        )
        result = {
            "schema_version": 1,
            "source_document_id": document_id,
            "source_packet_sha256": digest,
            "status": "pending_human_review",
            "coverage_status": "no_item_identified",
            "items": [],
            "limitations": ["Nenhum item identificado; conferir o PDF fictício."],
        }
        if document_id == "DOC-002":
            result["coverage_status"] = "items_identified"
            result["items"] = [{
                "item_id": "INV-DOC-002-001",
                "claim_ids": ["CLM-001"],
                "type": "time_record",
                "excerpt": {"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"},
                "description": "A página contém o título citado.",
                "limitations": ["O conteúdo integral exige revisão humana."],
            }]
            result["limitations"] = []
        return json.dumps(result, ensure_ascii=False)

    def test_validates_both_synthetic_documents_before_protected_publication(self) -> None:
        output = self.api().run_codex_inventory_rehearsal(
            self.workspace, synthetic_rehearsal=True,
            text_generator=self._synthetic_response, model_id="modelo-teste",
        )

        self.assertEqual(output, (self.workspace / "inventory-rehearsal-summary.json").resolve())
        self.assertEqual(len(self.prompts), 2)
        first_packet = self.prompts[0].split("<pacote_de_fontes>", 1)[1]
        second_packet = self.prompts[1].split("<pacote_de_fontes>", 1)[1]
        self.assertIn("CAPA SINTÉTICA", first_packet)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", first_packet)
        self.assertIn("REGISTRO DE JORNADA SINTÉTICO", second_packet)
        self.assertNotIn("CAPA SINTÉTICA", second_packet)
        self.assertTrue(all("inventariador-probatica-trt12" in prompt for prompt in self.prompts))
        self.assertNotIn(
            "REGISTRO DE JORNADA SINTÉTICO",
            self.prompts[0].split("<pacote_de_fontes>", 1)[0],
        )
        self.assertEqual(
            {path.name for path in self.workspace.iterdir()},
            {
                "synthetic-source.pdf", "claim-matrix.json",
                "inventory-pje-pdf-segments.json", "evidence-inventory-index.json",
                "DOC-001-inventory-source.md", "DOC-002-inventory-source.md",
                "DOC-001-inventory-observations.json", "DOC-002-inventory-observations.json",
                "inventory-rehearsal-summary.json",
            },
        )
        self.assertEqual(
            {stat.S_IMODE(path.stat().st_mode) for path in self.workspace.iterdir()},
            {0o600},
        )
        batch = importlib.import_module("validate_evidence_inventory_batch")
        self.assertEqual(batch.validate_evidence_inventory_batch(self.workspace), {
            "document_count": 2, "item_count": 1,
            "no_item_identified_count": 1, "insufficient_count": 0,
        })
        summary = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(summary["execution_mode"], "simulated")
        self.assertEqual(summary["model_id"], "modelo-teste")
        self.assertEqual(summary["document_count"], 2)
        self.assertEqual(summary["item_count"], 1)
        self.assertEqual(
            summary["observations_sha256"]["DOC-002"],
            hashlib.sha256(
                (self.workspace / "DOC-002-inventory-observations.json").read_bytes()
            ).hexdigest(),
        )

    def test_invalid_second_response_publishes_nothing(self) -> None:
        def invalid(prompt: str) -> str:
            result = json.loads(self._synthetic_response(prompt))
            if result["source_document_id"] == "DOC-002":
                result["items"][0]["excerpt"]["text"] = "TRECHO INVENTADO"
            return json.dumps(result, ensure_ascii=False)

        with self.assertRaises(self.api().CodexInventoryRehearsalError):
            self.api().run_codex_inventory_rehearsal(
                self.workspace, synthetic_rehearsal=True,
                text_generator=invalid, model_id="modelo-teste",
            )
        self.assertEqual(len(self.prompts), 2)
        self.assertFalse(any(self.workspace.iterdir()))

    def test_empty_observation_for_known_synthetic_record_is_not_a_successful_rehearsal(self) -> None:
        def omitted(prompt: str) -> str:
            result = json.loads(self._synthetic_response(prompt))
            result["coverage_status"] = "no_item_identified"
            result["items"] = []
            result["limitations"] = ["Nenhum item identificado; conferir o PDF fictício."]
            return json.dumps(result, ensure_ascii=False)

        with self.assertRaises(self.api().CodexInventoryRehearsalError):
            self.api().run_codex_inventory_rehearsal(
                self.workspace, synthetic_rehearsal=True,
                text_generator=omitted, model_id="modelo-teste",
            )
        self.assertFalse(any(self.workspace.iterdir()))

    def test_missing_synthetic_flag_blocks_dispatch(self) -> None:
        with self.assertRaises(self.api().CodexInventoryRehearsalError):
            self.api().run_codex_inventory_rehearsal(
                self.workspace, text_generator=self._synthetic_response,
                model_id="modelo-teste",
            )
        self.assertEqual(self.prompts, [])
        self.assertFalse(any(self.workspace.iterdir()))

    def test_existing_file_is_preserved_without_dispatch(self) -> None:
        existing = self.workspace / "preservar.txt"
        existing.write_text("manter", encoding="utf-8")
        with self.assertRaises(self.api().CodexInventoryRehearsalError):
            self.api().run_codex_inventory_rehearsal(
                self.workspace, synthetic_rehearsal=True,
                text_generator=self._synthetic_response,
                model_id="modelo-teste",
            )
        self.assertEqual(existing.read_text(encoding="utf-8"), "manter")
        self.assertEqual(self.prompts, [])

    def test_cli_requires_synthetic_flag(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_codex_inventory_rehearsal.py"),
             "--workspace", str(self.workspace), "--model", "modelo-teste"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--synthetic-rehearsal", result.stderr)
        self.assertFalse(any(self.workspace.iterdir()))


if __name__ == "__main__":
    unittest.main()
