from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class DocumentaryWorkRecordsTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        self.bridge = importlib.import_module("build_documentary_work_records")
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        segmenter = importlib.import_module("segment_pje_pdf")
        packet_builder = importlib.import_module("prepare_source_evidence_packet")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.pdf = Path(temporary.name) / "fonte-sintetica.pdf"
        self.pdf.write_bytes(rehearsal._synthetic_pdf())
        self.segments = segmenter.segment_pje_pdf(self.pdf)
        self.evidence = rehearsal._synthetic_evidence()
        self.packet = packet_builder.build_source_evidence_packet(
            self.pdf, self.segments, self.evidence,
            claim_id="CLM-001", evidence_ids=("EVD-001",),
        )
        self.observations = {
            "schema_version": 1,
            "claim_id": "CLM-001",
            "source_packet_sha256": hashlib.sha256(self.packet.encode("utf-8")).hexdigest(),
            "status": "pending_human_review",
            "observations": [{
                "evidence_id": "EVD-001",
                "source_document_id": "DOC-002",
                "excerpts": [{"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"}],
                "observation": "A página contém o título citado.",
                "limitations": ["O conteúdo integral não foi examinado."],
            }],
        }
        self.artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        planner = importlib.import_module("build_conditional_work_plan")
        self.plan = planner.build_conditional_work_plan(self.artifacts["issue-route.json"])

    def build(self, *, evidence_ids: tuple[str, ...] = ("EVD-001",)) -> tuple[dict, dict]:
        return self.bridge.build_documentary_work_records(
            self.plan, self.observations,
            packet=self.packet, pdf_path=self.pdf,
            segments=self.segments, evidence_matrix=self.evidence,
            claim_id="CLM-001", evidence_ids=evidence_ids,
        )

    def test_pending_observations_feed_existing_evidence_track_without_assessment(self) -> None:
        review, receipt = self.build()

        self.assertEqual(review["status"], "pending_human_review")
        self.assertEqual(review["evidence_ids"], ["EVD-001"])
        self.assertEqual(review["assessment"], "")
        self.assertTrue(review["limitations"])
        self.assertEqual(receipt["work_id"], "WRK-CLM-001-EVIDENCE")
        self.assertEqual(receipt["custody_status"], "linked")
        self.assertEqual(receipt["source_ids"], ["EVD-001"])
        results = {
            "schema_version": 1,
            "results": [self.artifacts["conditional-work-results.json"]["results"][0], receipt],
        }
        validator = importlib.import_module("validate_conditional_work_results")
        validator.validate_conditional_work_results(
            self.plan, results,
            evidence_matrix=self.evidence,
            precedent_corpus=self.artifacts["precedent-corpus.json"],
            known_document_ids=("DOC-001", "DOC-002"),
        )

    def test_missing_excerpt_remains_insufficient_with_gap_receipt(self) -> None:
        self.observations["status"] = "insufficient"
        self.observations["observations"][0]["excerpts"] = []
        review, receipt = self.build()

        self.assertEqual(review["status"], "insufficient")
        self.assertEqual(review["assessment"], "")
        self.assertEqual(receipt["custody_status"], "gap")
        self.assertEqual(receipt["source_ids"], ["EVD-001"])
        self.assertTrue(receipt["limitations"])

    def test_rejects_partial_claim_evidence_coverage(self) -> None:
        additional = copy.deepcopy(self.evidence["evidence_items"][0])
        additional["evidence_id"] = "EVD-002"
        self.evidence["evidence_items"].append(additional)

        with self.assertRaisesRegex(self.bridge.DocumentaryWorkRecordsError, "cobertura"):
            self.build()

    def test_rejects_claim_without_evidence_dispatch(self) -> None:
        routes = copy.deepcopy(self.artifacts["issue-route.json"])
        routes["routes"][0]["requires_evidence_analysis"] = False
        routes["routes"][0]["evidence_questions"] = []
        self.plan = importlib.import_module(
            "build_conditional_work_plan"
        ).build_conditional_work_plan(routes)

        with self.assertRaisesRegex(self.bridge.DocumentaryWorkRecordsError, "encaminhad"):
            self.build()

    def test_fabricated_excerpt_cannot_enter_conditional_track(self) -> None:
        self.observations["observations"][0]["excerpts"][0]["text"] = "NÃO EXISTE"
        with self.assertRaises(self.bridge.DocumentaryWorkRecordsError):
            self.build()


if __name__ == "__main__":
    unittest.main()
