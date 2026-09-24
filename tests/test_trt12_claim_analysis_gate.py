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


class TRT12ClaimAnalysisGateTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        for name in (
            "case-context.json", "claim-matrix.json", "evidence-matrix.json",
            "issue-route.json", "precedent-corpus.json", "evidence-review.json",
            "calculation-review.json", "conditional-work-results.json", "claim-analysis.json",
            "disposition-matrix.json", "review-report.json",
        ):
            self.save(name, artifacts[name])
        self.save("global-gate.json", {
            "schema_version": 1,
            "status": "passed",
            "checks": {
                "congruence": "passed", "citations": "passed",
                "sources": "passed", "calculations": "passed",
            },
            "quotation_count": 0,
            "issues": [],
        })
        (self.workspace / "judgment-draft.md").write_text(
            artifacts["judgment-draft.md"], encoding="utf-8"
        )
        self.merged_name = (
            f"{artifacts['case-context.json']['case_number']}-labor-judgment.md"
        )
        (self.workspace / self.merged_name).write_text(
            artifacts["judgment-draft.md"], encoding="utf-8"
        )
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
            "status": "complete", "page_count": 1,
            "documents": documents, "gaps": [],
        })
        self.stage = {"id": "analyze-claims", "gate": "claim-analysis-coverage"}
        self.outputs = ((self.workspace / "claim-analysis.json").resolve(),)

    def save(self, name, value):
        (self.workspace / name).write_text(json.dumps(value), encoding="utf-8")

    def load(self, name):
        return json.loads((self.workspace / name).read_text(encoding="utf-8"))

    def accepts(self):
        if importlib.util.find_spec("trt12_claim_analysis_gate") is None:
            self.fail("o controle de análise dos pedidos TRT12 não existe")
        gate = importlib.import_module("trt12_claim_analysis_gate")
        return gate.make_claim_analysis_gate(self.workspace)(self.stage, self.outputs)

    def accepts_draft(self):
        if importlib.util.find_spec("trt12_draft_gate") is None:
            self.fail("o controle da minuta TRT12 não existe")
        gate = importlib.import_module("trt12_draft_gate")
        stage = {"id": "draft-judgment", "gate": "draft-congruence"}
        outputs = (
            (self.workspace / "disposition-matrix.json").resolve(),
            (self.workspace / "judgment-draft.md").resolve(),
        )
        return gate.make_draft_gate(self.workspace)(stage, outputs)

    def accepts_merge(self):
        if importlib.util.find_spec("trt12_merge_gate") is None:
            self.fail("o controle de fusão da minuta TRT12 não existe")
        gate = importlib.import_module("trt12_merge_gate")
        return gate.make_merge_gate(self.workspace)(
            {"id": "merge-judgment", "gate": "deterministic-merge"},
            ((self.workspace / self.merged_name).resolve(),),
        )

    def accepts_final(self):
        if importlib.util.find_spec("trt12_final_gate") is None:
            self.fail("o controle final TRT12 não existe")
        gate = importlib.import_module("trt12_final_gate")
        return gate.make_final_gate(self.workspace)(
            {"id": "review-and-gate", "gate": "global-acceptance"},
            (
                (self.workspace / "review-report.json").resolve(),
                (self.workspace / "global-gate.json").resolve(),
            ),
        )

    def set_abstained_analysis(self):
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0]["proposed_outcome"] = "abstained"
        self.save("claim-analysis.json", analysis)
        dispositions = self.load("disposition-matrix.json")
        dispositions["items"][0].update({
            "outcome": "abstained",
            "command": "Nenhum comando dispositivo foi produzido devido à abstenção.",
        })
        self.save("disposition-matrix.json", dispositions)
        draft = (self.workspace / "judgment-draft.md").read_text(encoding="utf-8")
        draft = draft.replace("revisão humana pendente", "abstenção")
        draft = draft.replace(
            "Nenhum comando dispositivo pode ser emitido antes da revisão humana.",
            "Nenhum comando dispositivo foi produzido devido à abstenção.",
        )
        (self.workspace / "judgment-draft.md").write_text(draft, encoding="utf-8")
        (self.workspace / self.merged_name).write_text(draft, encoding="utf-8")

    def test_final_gate_accepts_explicit_abstention_as_a_technical_exit(self):
        self.set_abstained_analysis()
        self.assertTrue(self.accepts_final())

    def test_final_gate_holds_pending_human_review_despite_passed_technical_checks(self):
        self.assertFalse(self.accepts_final())

    def test_final_gate_rejects_report_that_disagrees_with_recalculation(self):
        self.set_abstained_analysis()
        report = self.load("global-gate.json")
        report["quotation_count"] = 1
        self.save("global-gate.json", report)
        self.assertFalse(self.accepts_final())

    def test_final_gate_rejects_source_review_divergent_from_corpus(self):
        self.set_abstained_analysis()
        review = self.load("review-report.json")
        review["sources"][0]["verbatim_excerpt"] = "Excerto inventado para o teste."
        self.save("review-report.json", review)
        self.assertFalse(self.accepts_final())

    def test_full_pipeline_dispatches_final_gate_for_abstention(self):
        self.set_abstained_analysis()
        gates = importlib.import_module("trt12_pipeline_gates")
        runner = importlib.import_module("run_synthetic_pipeline")
        payload_dir = self.workspace / "pje-payloads"
        payload_dir.mkdir()
        validator = gates.make_trt12_gate_validator(
            self.workspace, runner._resolve_plan("codex"), "a" * 64, payload_dir
        )
        self.assertTrue(validator(
            {"id": "review-and-gate", "gate": "global-acceptance"},
            (
                (self.workspace / "review-report.json").resolve(),
                (self.workspace / "global-gate.json").resolve(),
            ),
        ))

    def test_accepts_exact_merged_copy_of_approved_draft(self):
        self.assertTrue(self.accepts_merge())

    def test_rejects_extra_text_in_merged_judgment(self):
        merged = self.workspace / self.merged_name
        merged.write_text(
            merged.read_text(encoding="utf-8") + "\nJulgo procedente o pedido.\n",
            encoding="utf-8",
        )
        self.assertFalse(self.accepts_merge())

    def test_rejects_symlinked_merged_judgment(self):
        merged = self.workspace / self.merged_name
        copy = self.workspace / "copied-judgment.md"
        copy.write_bytes(merged.read_bytes())
        merged.unlink()
        merged.symlink_to(copy)
        self.assertFalse(self.accepts_merge())

    def test_full_pipeline_dispatches_merge_gate(self):
        gates = importlib.import_module("trt12_pipeline_gates")
        runner = importlib.import_module("run_synthetic_pipeline")
        payload_dir = self.workspace / "pje-payloads"
        payload_dir.mkdir()
        validator = gates.make_trt12_gate_validator(
            self.workspace, runner._resolve_plan("codex"), "a" * 64, payload_dir
        )
        self.assertTrue(validator(
            {"id": "merge-judgment", "gate": "deterministic-merge"},
            ((self.workspace / self.merged_name).resolve(),),
        ))

    def test_accepts_draft_that_preserves_pending_review(self):
        self.assertTrue(self.accepts_draft())

    def test_rejects_draft_with_added_merits_conclusion(self):
        draft = (self.workspace / "judgment-draft.md").read_text(encoding="utf-8")
        (self.workspace / "judgment-draft.md").write_text(
            draft + "\nResultado do pedido: procedente.\n", encoding="utf-8"
        )
        self.assertFalse(self.accepts_draft())

    def test_rejects_operative_command_while_review_is_pending(self):
        dispositions = self.load("disposition-matrix.json")
        dispositions["items"][0]["command"] = "Condeno a reclamada ao pagamento."
        self.save("disposition-matrix.json", dispositions)
        self.assertFalse(self.accepts_draft())

    def test_rejects_effects_while_review_is_pending(self):
        dispositions = self.load("disposition-matrix.json")
        dispositions["items"][0]["effects"] = ["Reflexos nas férias."]
        self.save("disposition-matrix.json", dispositions)
        self.assertFalse(self.accepts_draft())

    def test_rejects_draft_output_symlink(self):
        draft = self.workspace / "judgment-draft.md"
        copied = self.workspace / "copied-draft.md"
        copied.write_bytes(draft.read_bytes())
        draft.unlink()
        draft.symlink_to(copied)
        self.assertFalse(self.accepts_draft())

    def test_full_pipeline_dispatches_draft_gate(self):
        gates = importlib.import_module("trt12_pipeline_gates")
        runner = importlib.import_module("run_synthetic_pipeline")
        payload_dir = self.workspace / "pje-payloads"
        payload_dir.mkdir()
        validator = gates.make_trt12_gate_validator(
            self.workspace, runner._resolve_plan("codex"), "a" * 64, payload_dir
        )
        self.assertTrue(validator(
            {"id": "draft-judgment", "gate": "draft-congruence"},
            (
                (self.workspace / "disposition-matrix.json").resolve(),
                (self.workspace / "judgment-draft.md").resolve(),
            ),
        ))

    def test_accepts_unresolved_analysis_without_established_facts(self):
        self.assertTrue(self.accepts())

    def test_rejects_fact_found_while_evidence_review_is_pending(self):
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0]["facts_found"] = ["A jornada foi comprovada."]
        self.save("claim-analysis.json", analysis)
        self.assertFalse(self.accepts())

    def test_rejects_merits_outcome_while_evidence_review_is_pending(self):
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0].update({
            "facts_found": ["A jornada foi comprovada."],
            "proposed_outcome": "granted",
        })
        self.save("claim-analysis.json", analysis)
        self.assertFalse(self.accepts())

    def test_accepts_merits_only_after_linked_evidence_is_reviewed(self):
        review = self.load("evidence-review.json")
        review["reviews"][0].update({
            "status": "reviewed", "assessment": "Registro sintético conferido.",
            "limitations": [],
        })
        self.save("evidence-review.json", review)
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0].update({
            "facts_found": ["Fato sintético estabelecido para teste."],
            "proposed_outcome": "granted",
        })
        self.save("claim-analysis.json", analysis)
        self.assertTrue(self.accepts())

    def test_rejects_merits_when_legal_research_has_only_a_gap(self):
        review = self.load("evidence-review.json")
        review["reviews"][0].update({
            "status": "reviewed", "assessment": "Registro sintético conferido.",
            "limitations": [],
        })
        self.save("evidence-review.json", review)
        receipts = self.load("conditional-work-results.json")
        receipts["results"][0].update({
            "custody_status": "gap", "source_ids": [],
            "limitations": ["Pesquisa ainda não disponível."],
        })
        self.save("conditional-work-results.json", receipts)
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0].update({
            "facts_found": ["Fato sintético estabelecido para teste."],
            "proposed_outcome": "granted", "precedent_source_ids": [],
        })
        self.save("claim-analysis.json", analysis)
        self.assertFalse(self.accepts())

    def test_rejects_evidence_from_another_claim(self):
        evidence = self.load("evidence-matrix.json")
        evidence["evidence_items"][0]["claim_ids"] = ["CLM-999"]
        self.save("evidence-matrix.json", evidence)
        self.assertFalse(self.accepts())

    def test_rejects_unknown_precedent(self):
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0]["precedent_source_ids"] = ["TST-999"]
        self.save("claim-analysis.json", analysis)
        self.assertFalse(self.accepts())

    def test_rejects_missing_claim_analysis(self):
        analysis = self.load("claim-analysis.json")
        analysis["analyses"] = []
        self.save("claim-analysis.json", analysis)
        self.assertFalse(self.accepts())

    def test_rejects_merits_for_claim_with_review_gaps(self):
        claim_matrix = self.load("claim-matrix.json")
        claim_matrix["claims"][0].update({
            "status": "needs_human_review", "review_gaps": ["Pedido não mapeado."],
        })
        self.save("claim-matrix.json", claim_matrix)
        review = self.load("evidence-review.json")
        review["reviews"][0].update({
            "status": "reviewed", "assessment": "Registro sintético conferido.",
            "limitations": [],
        })
        self.save("evidence-review.json", review)
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0].update({
            "facts_found": ["Fato sintético estabelecido para teste."],
            "proposed_outcome": "granted",
        })
        self.save("claim-analysis.json", analysis)
        self.assertFalse(self.accepts())

    def test_full_pipeline_dispatches_claim_analysis_gate(self):
        gates = importlib.import_module("trt12_pipeline_gates")
        runner = importlib.import_module("run_synthetic_pipeline")
        payload_dir = self.workspace / "pje-payloads"
        payload_dir.mkdir()
        validator = gates.make_trt12_gate_validator(
            self.workspace, runner._resolve_plan("codex"), "a" * 64, payload_dir
        )
        self.assertTrue(validator(self.stage, self.outputs))

    def test_rejects_merits_for_abstained_route(self):
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
        route["abstention_reasons"] = ["Não há fontes suficientes."]
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
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0].update({
            "facts_found": ["A jornada foi comprovada."],
            "evidence_ids": ["EVD-001"],
            "proposed_outcome": "granted",
            "precedent_source_ids": [],
        })
        self.save("claim-analysis.json", analysis)
        self.assertFalse(self.accepts())

    def test_abstained_route_requires_explicit_abstained_analysis(self):
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
        route["abstention_reasons"] = ["Fontes insuficientes para encaminhamento."]
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
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0].update({
            "evidence_ids": [], "evidence_assessment": [], "precedent_source_ids": [],
        })
        self.save("claim-analysis.json", analysis)
        self.assertFalse(self.accepts())
        analysis["analyses"][0]["proposed_outcome"] = "abstained"
        self.save("claim-analysis.json", analysis)
        self.assertTrue(self.accepts())


if __name__ == "__main__":
    unittest.main()
