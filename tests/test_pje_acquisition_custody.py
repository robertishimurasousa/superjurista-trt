from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class PJeAcquisitionCustodyTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("verify_pje_acquisition_custody") is None:
            self.fail("o verificador de custódia da aquisição não existe")
        self.custody = importlib.import_module("verify_pje_acquisition_custody")
        self.payload = b"documento sintetico de teste"
        self.context = {
            "case_number": "0000000-00.2026.5.12.0000",
            "court": "TRT12",
            "instance": 1,
            "court_unit": "Unidade sintetica",
        }
        self.index = {
            "schema_version": 1,
            "case": {
                "case_number": self.context["case_number"],
                "tribunal_code": "TRT12",
                "instance": 1,
                "court_unit": "Unidade sintetica",
                "task_id": "TASK-001",
            },
            "status": "complete",
            "page_count": 1,
            "documents": [{
                "document_id": "DOC-001",
                "filename": "doc-001.pdf",
                "mime_type": "application/pdf",
                "sha256": hashlib.sha256(self.payload).hexdigest(),
                "source_locator": "evento sintetico 1",
                "download_status": "downloaded",
                "byte_count": len(self.payload),
            }],
            "gaps": [],
        }

    def test_complete_index_with_exact_payload_is_accepted(self):
        self.custody.verify_acquisition_custody(
            self.index, {"DOC-001": self.payload}, self.context
        )

    def test_index_for_another_case_is_rejected(self):
        self.index["case"]["case_number"] = "0000001-00.2026.5.12.0000"
        with self.assertRaises(self.custody.AcquisitionCustodyError):
            self.custody.verify_acquisition_custody(
                self.index, {"DOC-001": self.payload}, self.context
            )

    def test_partial_acquisition_cannot_back_a_complete_checkpoint(self):
        self.index["status"] = "partial"
        self.index["gaps"] = [{"subject_id": "DOC-002", "reason_code": "not_listed"}]
        with self.assertRaises(self.custody.AcquisitionCustodyError):
            self.custody.verify_acquisition_custody(
                self.index, {"DOC-001": self.payload}, self.context
            )

    def test_indexed_but_not_downloaded_document_is_rejected(self):
        self.index["documents"][0]["download_status"] = "not_requested"
        with self.assertRaises(self.custody.AcquisitionCustodyError):
            self.custody.verify_acquisition_custody(
                self.index, {"DOC-001": self.payload}, self.context
            )

    def test_duplicate_document_id_cannot_hide_behind_payload_set(self):
        self.index["documents"].append(dict(self.index["documents"][0]))
        with self.assertRaises(self.custody.AcquisitionCustodyError):
            self.custody.verify_acquisition_custody(
                self.index, {"DOC-001": self.payload}, self.context
            )

    def test_unsafe_index_filename_is_rejected(self):
        self.index["documents"][0]["filename"] = "../outro-processo.pdf"
        with self.assertRaises(self.custody.AcquisitionCustodyError):
            self.custody.verify_acquisition_custody(
                self.index, {"DOC-001": self.payload}, self.context
            )


if __name__ == "__main__":
    unittest.main()
