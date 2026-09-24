from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class TRT12ConditionalTracksGateTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("trt12_conditional_tracks_gate") is None:
            self.fail("o controle de trilhas condicionais TRT12 não existe")
        self.gate = importlib.import_module("trt12_conditional_tracks_gate")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        for name in (
            "case-context.json", "claim-matrix.json", "evidence-matrix.json",
            "issue-route.json", "precedent-corpus.json", "calculation-review.json",
        ):
            self.save(name, artifacts[name])
        context = artifacts["case-context.json"]
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
        self.save("evidence-review.json", {
            "schema_version": 1,
            "reviews": [{
                "claim_id": "CLM-001",
                "status": "pending_human_review",
                "evidence_ids": ["EVD-001"],
                "assessment": "",
                "limitations": ["A avaliação probatória depende de revisão humana."],
            }],
        })
        self.save("conditional-work-results.json", {
            "schema_version": 1,
            "results": [
                {
                    "work_id": "WRK-CLM-001-LEGAL",
                    "claim_id": "CLM-001",
                    "track": "legal_research",
                    "custody_status": "linked",
                    "source_ids": ["TST-001"],
                    "limitations": ["Fonte sintética; não representa pesquisa real."],
                },
                {
                    "work_id": "WRK-CLM-001-EVIDENCE",
                    "claim_id": "CLM-001",
                    "track": "evidence_analysis",
                    "custody_status": "linked",
                    "source_ids": ["EVD-001"],
                    "limitations": ["A prova exige revisão humana."],
                },
            ],
        })
        self.stage = {"id": "execute-conditional-tracks", "gate": "conditional-track-custody"}
        self.outputs = tuple(
            (self.workspace / name).resolve()
            for name in (
                "precedent-corpus.json", "evidence-review.json",
                "calculation-review.json", "conditional-work-results.json",
            )
        )

    def save(self, name, value):
        (self.workspace / name).write_text(json.dumps(value), encoding="utf-8")

    def load(self, name):
        return json.loads((self.workspace / name).read_text(encoding="utf-8"))

    def accepts(self):
        return self.gate.make_conditional_tracks_gate(self.workspace)(self.stage, self.outputs)

    def test_accepts_exact_routed_work_with_explicit_review_state(self):
        self.assertTrue(self.accepts())

    def test_rejects_unrequested_calculation_as_reviewed(self):
        calculations = self.load("calculation-review.json")
        calculations["calculations"][0]["status"] = "criteria_reviewed"
        calculations["calculations"][0]["criteria"] = ["Critério sintético."]
        self.save("calculation-review.json", calculations)
        self.assertFalse(self.accepts())

    def test_rejects_review_for_another_claim(self):
        review = self.load("evidence-review.json")
        review["reviews"][0]["claim_id"] = "CLM-999"
        self.save("evidence-review.json", review)
        self.assertFalse(self.accepts())

    def test_rejects_evidence_review_divergent_from_work_receipt(self):
        review = self.load("evidence-review.json")
        review["reviews"][0]["evidence_ids"] = []
        self.save("evidence-review.json", review)
        self.assertFalse(self.accepts())

    def test_rejects_documentary_observation_hash_without_packet_custody(self):
        review = self.load("evidence-review.json")
        review["reviews"][0]["limitations"].append(
            "Observações documentais SHA-256: " + "a" * 64
        )
        self.save("evidence-review.json", review)

        self.assertFalse(self.accepts())

    def test_rejects_symlinked_work_receipt(self):
        path = self.workspace / "conditional-work-results.json"
        copied = self.workspace / "copied-work-results.json"
        copied.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(copied)
        self.assertFalse(self.accepts())

    def test_full_pipeline_dispatches_conditional_work_gate(self):
        gates = importlib.import_module("trt12_pipeline_gates")
        runner = importlib.import_module("run_synthetic_pipeline")
        payload_dir = self.workspace / "pje-payloads"
        payload_dir.mkdir()
        validator = gates.make_trt12_gate_validator(
            self.workspace, runner._resolve_plan("codex"), "a" * 64, payload_dir
        )
        self.assertTrue(validator(self.stage, self.outputs))

    def test_explicit_abstention_accepts_no_op_without_unrequested_sources(self):
        routes = self.load("issue-route.json")
        route = routes["routes"][0]
        route["route_status"] = "abstained"
        for flag in (
            "requires_legal_research", "requires_evidence_analysis",
            "requires_calculation_review", "requires_procedural_review",
        ):
            route[flag] = False
        route["research_questions"] = []
        route["evidence_questions"] = []
        route["abstention_reasons"] = ["As fontes disponíveis não autorizam encaminhamento."]
        self.save("issue-route.json", routes)
        corpus = self.load("precedent-corpus.json")
        corpus["sources"] = []
        self.save("precedent-corpus.json", corpus)
        review = self.load("evidence-review.json")
        review["reviews"][0].update({
            "status": "not_required", "evidence_ids": [],
            "assessment": "", "limitations": [],
        })
        self.save("evidence-review.json", review)
        self.save("conditional-work-results.json", {"schema_version": 1, "results": []})
        self.assertTrue(self.accepts())

    def test_reviewed_calculation_requires_linked_source_receipt(self):
        routes = self.load("issue-route.json")
        routes["routes"][0]["requires_calculation_review"] = True
        self.save("issue-route.json", routes)
        calculation = self.load("calculation-review.json")
        calculation["calculations"][0]["status"] = "criteria_reviewed"
        calculation["calculations"][0]["criteria"] = ["Período sintético documentado."]
        self.save("calculation-review.json", calculation)
        results = self.load("conditional-work-results.json")
        results["results"].append({
            "work_id": "WRK-CLM-001-CALCULATION",
            "claim_id": "CLM-001",
            "track": "calculation_review",
            "custody_status": "linked",
            "source_ids": ["DOC-001"],
            "limitations": [],
        })
        self.save("conditional-work-results.json", results)
        self.assertTrue(self.accepts())
        results["results"][-1].update({
            "custody_status": "gap",
            "source_ids": [],
            "limitations": ["Critério sem fonte confirmada."],
        })
        self.save("conditional-work-results.json", results)
        self.assertFalse(self.accepts())

    def test_reviewed_evidence_cannot_be_backed_by_gap_receipt(self):
        review = self.load("evidence-review.json")
        review["reviews"][0]["status"] = "reviewed"
        review["reviews"][0]["assessment"] = "Registro sintético examinado."
        self.save("evidence-review.json", review)
        results = self.load("conditional-work-results.json")
        results["results"][1]["custody_status"] = "gap"
        self.save("conditional-work-results.json", results)
        self.assertFalse(self.accepts())


if __name__ == "__main__":
    unittest.main()
