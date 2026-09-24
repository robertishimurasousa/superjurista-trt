from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class ConditionalWorkResultsTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("validate_conditional_work_results") is None:
            self.fail("o validador de resultados condicionais não existe")
        self.validator = importlib.import_module("validate_conditional_work_results")
        planner = importlib.import_module("build_conditional_work_plan")
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        self.plan = planner.build_conditional_work_plan(artifacts["issue-route.json"])
        self.evidence = artifacts["evidence-matrix.json"]
        self.precedents = artifacts["precedent-corpus.json"]
        self.documents = ("DOC-001", "DOC-002")
        self.results = {
            "schema_version": 1,
            "results": [
                {
                    "work_id": "WRK-CLM-001-LEGAL",
                    "claim_id": "CLM-001",
                    "track": "legal_research",
                    "custody_status": "linked",
                    "source_ids": ["TST-001"],
                    "limitations": [],
                },
                {
                    "work_id": "WRK-CLM-001-EVIDENCE",
                    "claim_id": "CLM-001",
                    "track": "evidence_analysis",
                    "custody_status": "linked",
                    "source_ids": ["EVD-001"],
                    "limitations": ["A análise jurídica da prova depende de revisão humana."],
                },
            ],
        }

    def validate(self, results=None):
        return self.validator.validate_conditional_work_results(
            self.plan,
            self.results if results is None else results,
            evidence_matrix=self.evidence,
            precedent_corpus=self.precedents,
            known_document_ids=self.documents,
        )

    def test_accepts_exact_source_linked_results_for_enabled_tracks(self):
        self.assertIsNone(self.validate())

    def test_rejects_missing_enabled_work_item(self):
        results = copy.deepcopy(self.results)
        results["results"].pop()
        with self.assertRaisesRegex(ValueError, "cobertura"):
            self.validate(results)

    def test_rejects_result_for_disabled_calculation_track(self):
        results = copy.deepcopy(self.results)
        results["results"].append({
            "work_id": "WRK-CLM-001-CALCULATION",
            "claim_id": "CLM-001",
            "track": "calculation_review",
            "custody_status": "linked",
            "source_ids": ["DOC-001"],
            "limitations": [],
        })
        with self.assertRaisesRegex(ValueError, "cobertura"):
            self.validate(results)

    def test_rejects_unknown_precedent_source(self):
        results = copy.deepcopy(self.results)
        results["results"][0]["source_ids"] = ["TST-999"]
        with self.assertRaisesRegex(ValueError, "fonte"):
            self.validate(results)

    def test_rejects_evidence_not_linked_to_claim(self):
        results = copy.deepcopy(self.results)
        self.evidence["evidence_items"][0]["claim_ids"] = ["CLM-002"]
        with self.assertRaisesRegex(ValueError, "pedido"):
            self.validate(results)

    def test_rejects_unexplained_gap(self):
        results = copy.deepcopy(self.results)
        results["results"][0]["custody_status"] = "gap"
        results["results"][0]["source_ids"] = []
        with self.assertRaisesRegex(ValueError, "lacuna"):
            self.validate(results)

    def test_rejects_duplicate_result(self):
        results = copy.deepcopy(self.results)
        results["results"].append(copy.deepcopy(results["results"][0]))
        with self.assertRaisesRegex(ValueError, "duplicad"):
            self.validate(results)


if __name__ == "__main__":
    unittest.main()
