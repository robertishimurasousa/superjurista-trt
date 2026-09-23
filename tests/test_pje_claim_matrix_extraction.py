from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/contracts/valid/labor-report.json"
TAXONOMY = ROOT / "runtime/domain/labor-claim-taxonomy.json"


class PJeClaimMatrixExtractionTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("extract_pje_claim_matrix")

    def inputs(self):
        report = json.loads(FIXTURE.read_text(encoding="utf-8"))
        report["parties"].append({**report["parties"][1], "party_id": "PTY-003"})
        report["positions"] = [
            {**report["positions"][0], "source_locator": "page 4"},
            {
                **report["positions"][0],
                "position_id": "POS-002",
                "label": "unmapped_joint_liability",
                "source_locator": "page 5",
            },
            {
                **report["positions"][1],
                "position_id": "POS-101",
                "source_locator": "page 2",
            },
        ]
        segments = {
            "schema_version": 1,
            "segmentation_method": "pje_pdf_outline",
            "source_pdf": {"sha256": "0" * 64, "page_count": 6},
            "documents": [
                {
                    "document_id": f"DOC-{number:03d}",
                    "provider_reference": f"{number:07x}",
                    "provider_type": "synthetic",
                    "filed_on": "2026-01-01",
                    "page_start": start,
                    "page_end": end,
                }
                for number, start, end in ((1, 4, 5), (2, 1, 3))
            ],
        }
        return report, segments

    def build(self, report, segments, bindings):
        api = self.api()
        return api.extract_claim_matrix(report, segments, api.load_claim_taxonomy(TAXONOMY), bindings)

    def test_links_only_explicitly_bound_defense_and_marks_missing_information(self):
        report, segments = self.inputs()
        result = self.build(report, segments, {"DOC-002": "PTY-002"})
        first, second = result["claims"]
        self.assertEqual((first["claim_id"], second["claim_id"]), ("CLM-001", "CLM-002"))
        self.assertEqual(first["respondent_positions"][0]["defense_id"], "DEF-101")
        self.assertEqual(first["respondent_positions"][0]["respondent_party_id"], "PTY-002")
        self.assertEqual(first["review_gaps"], ["missing_requested_remedy"])
        self.assertEqual(second["respondent_positions"], [])
        self.assertEqual(second["review_gaps"], [
            "missing_requested_remedy", "missing_respondent_position", "unsupported_claim_label"
        ])
        self.assertEqual(first["claimant_position"]["source_locator"], "page 4")

    def test_requires_binding_for_every_defense_document(self):
        report, segments = self.inputs()
        with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "binding"):
            self.build(report, segments, {})

    def test_keeps_distinct_defense_documents_and_parties(self):
        report, segments = self.inputs()
        report["positions"].append({
            **report["positions"][2],
            "position_id": "POS-102",
            "source_document_id": "DOC-003",
            "source_locator": "page 6",
        })
        segments["documents"].append({
            **segments["documents"][1],
            "document_id": "DOC-003",
            "provider_reference": "0000003",
            "page_start": 6,
            "page_end": 6,
        })
        result = self.build(report, segments, {"DOC-002": "PTY-002", "DOC-003": "PTY-003"})
        defenses = result["claims"][0]["respondent_positions"]
        self.assertEqual(
            [(item["defense_id"], item["respondent_party_id"]) for item in defenses],
            [("DEF-101", "PTY-002"), ("DEF-102", "PTY-003")],
        )

    def test_pdf_custody_requires_exact_digest_and_case_number(self):
        api = self.api()
        report, segments = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_metadata({"/Title": "0000000-00.2026.5.12.0000"})
            with path.open("wb") as stream:
                writer.write(stream)
            segments["source_pdf"] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "page_count": 1,
            }
            api.verify_pdf_custody(path, segments, report)
            report["case_context"]["case_number"] = "0000001-00.2026.5.12.0000"
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "case"):
                api.verify_pdf_custody(path, segments, report)
            segments["source_pdf"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "custody"):
                api.verify_pdf_custody(path, segments, report)

    def test_rejects_nonrespondent_and_unknown_binding(self):
        report, segments = self.inputs()
        for party_id in ("PTY-001", "PTY-999"):
            with self.subTest(party_id=party_id):
                with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "respondent"):
                    self.build(report, segments, {"DOC-002": party_id})

    def test_rejects_ambiguous_and_orphan_defense_labels(self):
        report, segments = self.inputs()
        ambiguous = copy.deepcopy(report)
        ambiguous["positions"][1]["label"] = "overtime"
        with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "ambiguous"):
            self.build(ambiguous, segments, {"DOC-002": "PTY-002"})
        orphan = copy.deepcopy(report)
        orphan["positions"][2]["label"] = "moral_damages"
        with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "no claim"):
            self.build(orphan, segments, {"DOC-002": "PTY-002"})

    def test_rejects_position_outside_document_pages(self):
        report, segments = self.inputs()
        report["positions"][2]["source_locator"] = "page 6"
        with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "outside"):
            self.build(report, segments, {"DOC-002": "PTY-002"})

    def test_protected_writer_is_exclusive_and_outside_repository(self):
        api = self.api()
        report, segments = self.inputs()
        matrix = self.build(report, segments, {"DOC-002": "PTY-002"})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = api.write_claim_matrix_artifact(matrix, output_dir=output, repository_root=ROOT)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), matrix)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "exists"):
                api.write_claim_matrix_artifact(matrix, output_dir=output, repository_root=ROOT)
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "outside repository"):
                api.write_claim_matrix_artifact(matrix, output_dir=ROOT, repository_root=ROOT)
