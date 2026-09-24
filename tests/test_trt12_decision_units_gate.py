from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from copy import deepcopy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class TRT12DecisionUnitsGateTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("trt12_decision_units_gate") is None:
            self.fail("o controle de matrizes TRT12 não existe")
        self.gate = importlib.import_module("trt12_decision_units_gate")
        runner = importlib.import_module("run_synthetic_pipeline")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        runner.run_synthetic_pipeline("codex", FIXTURE, self.workspace)
        self.stage = runner._resolve_plan("codex")["contract"]["stages"][3]
        self.outputs = tuple(
            (self.workspace / name).resolve()
            for name in ("claim-matrix.json", "evidence-matrix.json")
        )
        context = self.load("case-context.json")
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
        self.save("document-index.json", {
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
        })

    def load(self, name):
        return json.loads((self.workspace / name).read_text(encoding="utf-8"))

    def save(self, name, value):
        (self.workspace / name).write_text(json.dumps(value), encoding="utf-8")

    def accepts(self):
        return self.gate.make_decision_units_gate(self.workspace)(self.stage, self.outputs)

    def test_accepts_matrices_linked_to_report_and_acquired_documents(self):
        self.assertTrue(self.accepts())

    def test_rejects_inventory_based_matrix_without_verified_promotion(self):
        self.save("evidence-inventory-index.json", {"schema_version": 1})
        self.assertFalse(self.accepts())

    def test_rejects_unverified_promotion_receipt(self):
        self.save("evidence-matrix-promotion.json", {"schema_version": 1})
        self.assertFalse(self.accepts())

    def test_rejects_claim_source_changed_from_report(self):
        matrix = self.load("claim-matrix.json")
        matrix["claims"][0]["claimant_position"]["source_locator"] = "page 99"
        self.save("claim-matrix.json", matrix)
        self.assertFalse(self.accepts())

    def test_rejects_defense_missing_from_matrix(self):
        matrix = self.load("claim-matrix.json")
        matrix["claims"][0]["respondent_positions"] = []
        matrix["claims"][0]["status"] = "needs_human_review"
        matrix["claims"][0]["review_gaps"] = ["missing_respondent_position"]
        self.save("claim-matrix.json", matrix)
        self.assertFalse(self.accepts())

    def test_rejects_evidence_with_unknown_claim(self):
        matrix = self.load("evidence-matrix.json")
        matrix["evidence_items"][0]["claim_ids"] = ["CLM-999"]
        self.save("evidence-matrix.json", matrix)
        self.assertFalse(self.accepts())

    def test_rejects_uncovered_claim_when_evidence_exists(self):
        matrix = self.load("evidence-matrix.json")
        matrix["uncovered_claim_ids"] = ["CLM-001"]
        self.save("evidence-matrix.json", matrix)
        self.assertFalse(self.accepts())

    def test_rejects_unrecognized_source_document(self):
        matrix = self.load("evidence-matrix.json")
        matrix["evidence_items"][0]["source_document_id"] = "DOC-999"
        self.save("evidence-matrix.json", matrix)
        self.assertFalse(self.accepts())

    def test_rejects_mapped_status_for_unsupported_remedy(self):
        matrix = self.load("claim-matrix.json")
        matrix["claims"][0]["requested_remedies"].append("unsupported_payment")
        self.save("claim-matrix.json", matrix)
        self.assertFalse(self.accepts())

    def test_rejects_conflict_with_unknown_evidence(self):
        matrix = self.load("evidence-matrix.json")
        matrix["evidence_items"][0]["conflicts_with_evidence_ids"] = ["EVD-999"]
        matrix["evidence_items"][0]["analysis_status"] = "disputed"
        self.save("evidence-matrix.json", matrix)
        self.assertFalse(self.accepts())

    def test_rejects_ambiguous_respondent_party_identifier(self):
        report = self.load("labor-report.json")
        report["parties"][0]["party_id"] = "PTY-002"
        self.save("labor-report.json", report)
        self.assertFalse(self.accepts())

    def test_rejects_defense_linked_to_ambiguous_same_label_claims(self):
        report = self.load("labor-report.json")
        additional_position = deepcopy(report["positions"][0])
        additional_position["position_id"] = "POS-003"
        additional_position["summary"] = "A separate overtime period is claimed."
        additional_position["source_locator"] = "page 6"
        report["positions"].append(additional_position)
        self.save("labor-report.json", report)
        matrix = self.load("claim-matrix.json")
        additional_claim = deepcopy(matrix["claims"][0])
        additional_claim["claim_id"] = "CLM-002"
        additional_claim["claimant_position"] = {
            "summary": additional_position["summary"],
            "source_document_id": additional_position["source_document_id"],
            "source_locator": additional_position["source_locator"],
        }
        additional_claim["respondent_positions"] = []
        additional_claim["status"] = "needs_human_review"
        additional_claim["review_gaps"] = ["missing_respondent_position"]
        matrix["claims"].append(additional_claim)
        self.save("claim-matrix.json", matrix)
        evidence = self.load("evidence-matrix.json")
        evidence["uncovered_claim_ids"] = ["CLM-002"]
        self.save("evidence-matrix.json", evidence)
        self.assertFalse(self.accepts())

    def test_rejects_claim_identifier_incompatible_with_inherited_triage(self):
        matrix = self.load("claim-matrix.json")
        matrix["claims"][0]["claim_id"] = "CLM-777"
        self.save("claim-matrix.json", matrix)
        evidence = self.load("evidence-matrix.json")
        evidence["evidence_items"][0]["claim_ids"] = ["CLM-777"]
        self.save("evidence-matrix.json", evidence)
        self.assertFalse(self.accepts())

    def test_rejects_claim_sources_swapped_between_stable_identifiers(self):
        report = self.load("labor-report.json")
        report["positions"] = [report["positions"][0]]
        additional_position = deepcopy(report["positions"][0])
        additional_position["position_id"] = "POS-003"
        additional_position["summary"] = "A separate overtime period is claimed."
        additional_position["source_locator"] = "page 6"
        report["positions"].append(additional_position)
        self.save("labor-report.json", report)
        matrix = self.load("claim-matrix.json")
        first = matrix["claims"][0]
        second = deepcopy(first)
        second["claim_id"] = "CLM-003"
        second["claimant_position"] = {
            "summary": additional_position["summary"],
            "source_document_id": additional_position["source_document_id"],
            "source_locator": additional_position["source_locator"],
        }
        for claim in (first, second):
            claim["respondent_positions"] = []
            claim["status"] = "needs_human_review"
            claim["review_gaps"] = ["missing_respondent_position"]
        first["claimant_position"], second["claimant_position"] = (
            second["claimant_position"], first["claimant_position"]
        )
        matrix["claims"].append(second)
        self.save("claim-matrix.json", matrix)
        evidence = self.load("evidence-matrix.json")
        evidence["uncovered_claim_ids"] = ["CLM-003"]
        self.save("evidence-matrix.json", evidence)
        self.assertFalse(self.accepts())


if __name__ == "__main__":
    unittest.main()
