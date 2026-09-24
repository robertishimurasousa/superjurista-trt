from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"
SOURCE_FINGERPRINT = "a" * 64
SCOPE_DIGEST = hashlib.sha256(b"escopo sintetico autorizado").hexdigest()


class TRT12ExtractionGateTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("trt12_extraction_gate") is None:
            self.fail("o controle de extração TRT12 não existe")
        self.gate = importlib.import_module("trt12_extraction_gate")
        runner = importlib.import_module("run_synthetic_pipeline")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        runner.run_synthetic_pipeline("codex", FIXTURE, self.workspace)
        self.plan = runner._resolve_plan("codex")
        self.stage = self.plan["contract"]["stages"][2]
        self.outputs = tuple(
            (self.workspace / name).resolve()
            for name in (
                "document-classification.json",
                "procedural-timeline.json",
                "labor-report.json",
            )
        )
        self.make_complete_index_and_timeline()

    def save(self, name, value):
        (self.workspace / name).write_text(json.dumps(value), encoding="utf-8")

    def load(self, name):
        return json.loads((self.workspace / name).read_text(encoding="utf-8"))

    def make_complete_index_and_timeline(self):
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
        timeline = self.load("procedural-timeline.json")
        timeline["events"].append({
            "event_id": "EVT-002",
            "event_date": "2026-01-20",
            "event_type": "defense_filed",
            "summary": "Defesa sintética apresentada.",
            "source_document_id": "DOC-002",
            "source_locator": "página 1",
        })
        self.save("procedural-timeline.json", timeline)
        report = self.load("labor-report.json")
        report["timeline"] = timeline["events"]
        self.save("labor-report.json", report)

    def test_complete_record_matches_all_acquired_documents(self):
        self.assertTrue(self.gate.make_extraction_gate(self.workspace)(self.stage, self.outputs))

    def test_partial_acquisition_cannot_appear_as_complete_extraction(self):
        index = self.load("document-index.json")
        index["status"] = "partial"
        index["gaps"] = [{"subject_id": "DOC-003", "reason_code": "not_listed"}]
        self.save("document-index.json", index)
        self.assertFalse(self.gate.make_extraction_gate(self.workspace)(self.stage, self.outputs))

    def test_missing_classification_for_acquired_document_is_rejected(self):
        classification = self.load("document-classification.json")
        classification["documents"].pop()
        self.save("document-classification.json", classification)
        self.assertFalse(self.gate.make_extraction_gate(self.workspace)(self.stage, self.outputs))

    def test_report_with_stale_timeline_is_rejected(self):
        report = self.load("labor-report.json")
        report["timeline"].pop()
        self.save("labor-report.json", report)
        self.assertFalse(self.gate.make_extraction_gate(self.workspace)(self.stage, self.outputs))

    def test_conflicting_classification_reason_is_rejected(self):
        classification = self.load("document-classification.json")
        classification["documents"][0]["reason_code"] = "no_matching_rule"
        self.save("document-classification.json", classification)
        self.assertFalse(self.gate.make_extraction_gate(self.workspace)(self.stage, self.outputs))

    def test_unknown_document_remains_explicit_review_gap(self):
        classification = self.load("document-classification.json")
        classification["documents"][1].update({
            "document_type": "unknown",
            "classification_status": "unknown",
            "matched_rule_ids": [],
            "reason_code": "no_matching_rule",
        })
        self.save("document-classification.json", classification)
        timeline = self.load("procedural-timeline.json")
        timeline["events"][1]["event_type"] = "unclassified_document_filed"
        timeline["status"] = "partial"
        timeline["gaps"] = [{
            "subject_id": "DOC-002",
            "reason_code": "unclassified_document",
        }]
        self.save("procedural-timeline.json", timeline)
        report = self.load("labor-report.json")
        report["timeline"] = timeline["events"]
        self.save("labor-report.json", report)
        self.assertTrue(self.gate.make_extraction_gate(self.workspace)(self.stage, self.outputs))

    def make_verified_acquisition(self):
        recovery = importlib.import_module("recover_pje_acquisition")
        index = self.load("document-index.json")
        payload_dir = self.workspace / "pje-payloads"
        payload_dir.mkdir()
        recovered_documents = []
        for document in index["documents"]:
            document_id = document["document_id"]
            content = f"conteudo sintetico {document_id}".encode()
            (payload_dir / f"{document_id}.bin").write_bytes(content)
            recovered_documents.append({
                "document_id": document_id,
                "sha256": document["sha256"],
                "attempt_count": 1,
                "status": "accepted",
                "relative_path": f"{document_id}.bin",
                "byte_count": len(content),
                "last_error": None,
            })
        self.save("source-manifest.json", {
            "schema_version": 1,
            "case": {
                "case_number": index["case"]["case_number"],
                "tribunal_code": "TRT12",
                "instance": 1,
            },
            "authorization_scope_digest": SCOPE_DIGEST,
            "selection_mode": "all",
            "requested_document_ids": [],
            "max_attempts": 2,
            "catalog_digest": recovery._catalog_digest(index),
            "status": "complete",
            "acquisition_cycles": 1,
            "successful_documents": len(recovered_documents),
            "documents": recovered_documents,
        })
        return index, payload_dir

    def prepare_documentary_checkpoint(self, evidence_override=None):
        """Prepara somente fontes e checkpoints fictícios anteriores à etapa documental."""
        if evidence_override is not None:
            self.save("evidence-matrix.json", evidence_override)
        gates = importlib.import_module("trt12_pipeline_gates")
        resume = importlib.import_module("resumable_pipeline")
        triage_input = importlib.import_module("build_superjurista_triage_input")
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        segmenter = importlib.import_module("segment_pje_pdf")
        packet_builder = importlib.import_module("prepare_source_evidence_packet")
        index, payload_dir = self.make_verified_acquisition()
        validator = gates.make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        old_input = (self.workspace / "triage-input.md").read_text(encoding="utf-8")
        old_digest = hashlib.sha256(old_input.encode()).hexdigest()
        new_input = triage_input.build_triage_input(
            self.load("labor-report.json"), self.load("claim-matrix.json")
        )
        new_digest = hashlib.sha256(new_input.encode()).hexdigest()
        (self.workspace / "triage-input.md").unlink()
        triage_input.write_triage_input(new_input, self.workspace / "triage-input.md")
        narrative_path = self.workspace / "report-narrative.md"
        narrative = narrative_path.read_text(encoding="utf-8").replace(old_digest, new_digest)
        narrative = narrative.replace(
            "A linha do tempo registra o ajuizamento em 10 de janeiro de 2026 "
            "(DOC-001, página 1).",
            "A linha do tempo registra o ajuizamento em 10 de janeiro de 2026 "
            "(DOC-001, página 1) e a defesa apresentada em 20 de janeiro de 2026 "
            "(DOC-002, página 1).",
        )
        prefix, rest = narrative.split("```json\n", 1)
        _, suffix = rest.split("\n```", 1)
        coverage = {
            "events": [
                {"event_id": "EVT-001", "source_document_id": "DOC-001", "source_locator": "página 1"},
                {"event_id": "EVT-002", "source_document_id": "DOC-002", "source_locator": "página 1"},
            ],
            "claims": [{"claim_id": "CLM-001", "source_document_id": "DOC-001", "source_locator": "páginas 4-5"}],
            "defenses": [{
                "defense_id": "DEF-001", "claim_id": "CLM-001", "respondent_party_id": "PTY-002",
                "source_document_id": "DOC-002", "source_locator": "páginas 2-3",
            }],
            "unanswered_claim_ids": [],
        }
        narrative_path.write_text(
            prefix + "```json\n" + json.dumps(coverage, ensure_ascii=False)
            + "\n```" + suffix,
            encoding="utf-8",
        )
        case_number = index["case"]["case_number"]
        triage_path = self.workspace / f"{case_number}-triagem.md"
        triage_path.write_text(
            triage_path.read_text(encoding="utf-8").replace(old_digest, new_digest),
            encoding="utf-8",
        )
        context = {"case_number": case_number}
        state = resume.new_execution_state(self.plan, SOURCE_FINGERPRINT)
        for stage_id in (
            "prepare-profile", "acquire-case", "extract-record", "build-decision-units",
            "prepare-triage-input", "narrate-record", "route-claims",
        ):
            state = resume.record_stage_acceptance(
                self.plan, workspace=self.workspace, state=state, stage_id=stage_id,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                gate_validator=validator, attempt=1,
            )
        self.assertEqual(resume.plan_resume(
            self.plan, workspace=self.workspace, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "execute-conditional-tracks")

        pdf = self.workspace / "fonte-sintetica.pdf"
        pdf.write_bytes(rehearsal._synthetic_pdf())
        segments = segmenter.segment_pje_pdf(pdf)
        evidence = self.load("evidence-matrix.json")
        packet = packet_builder.build_source_evidence_packet(
            pdf, segments, evidence, claim_id="CLM-001", evidence_ids=("EVD-001",),
        )
        observations = {
            "schema_version": 1, "claim_id": "CLM-001",
            "source_packet_sha256": hashlib.sha256(packet.encode("utf-8")).hexdigest(),
            "status": "pending_human_review",
            "observations": [{
                "evidence_id": "EVD-001", "source_document_id": "DOC-002",
                "excerpts": [{"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"}],
                "observation": "A página contém o título citado.",
                "limitations": ["O conteúdo integral não foi examinado."],
            }],
        }
        other_results = self.load("conditional-work-results.json")
        other_results["results"] = [
            item for item in other_results["results"]
            if item["track"] != "evidence_analysis"
        ]
        (self.workspace / "evidence-review.json").unlink()
        (self.workspace / "conditional-work-results.json").unlink()
        return state, context, payload_dir, {
            "CLM-001": {
                "observations": observations, "packet": packet, "pdf_path": pdf,
                "segments": segments, "evidence_ids": ("EVD-001",),
            }
        }, other_results

    def test_documentary_stage_records_shared_checkpoint_and_advances_resume(self):
        stage_runner = importlib.import_module("run_documentary_conditional_stage")
        resume = importlib.import_module("resumable_pipeline")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()

        updated = stage_runner.accept_documentary_conditional_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            documentary_bundles=bundles, other_results=other_results, attempt=1,
        )

        self.assertEqual(updated["stages"][-1]["id"], "execute-conditional-tracks")
        self.assertEqual(self.load("evidence-review.json")["reviews"][0]["assessment"], "")
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(resume.plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "analyze-claims")

    def test_claim_analysis_stage_publishes_and_records_shared_checkpoint(self):
        documentary = importlib.import_module("run_documentary_conditional_stage")
        resume = importlib.import_module("resumable_pipeline")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        state = documentary.accept_documentary_conditional_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            documentary_bundles=bundles, other_results=other_results, attempt=1,
        )
        (self.workspace / "claim-analysis.json").unlink()
        analysis = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]["claim-analysis.json"]
        self.assertIsNotNone(importlib.util.find_spec("run_claim_analysis_stage"))
        stage_runner = importlib.import_module("run_claim_analysis_stage")
        state_path = self.workspace / "state-after-analysis.json"

        updated = stage_runner.accept_claim_analysis_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            analysis=analysis, attempt=1, state_output=state_path,
        )

        self.assertEqual(updated["stages"][-1]["id"], "analyze-claims")
        self.assertEqual(stat.S_IMODE((self.workspace / "claim-analysis.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), updated)
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(resume.plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "draft-judgment")

    def test_claim_analysis_stage_rolls_back_a_merits_conclusion_without_review(self):
        documentary = importlib.import_module("run_documentary_conditional_stage")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        state = documentary.accept_documentary_conditional_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            documentary_bundles=bundles, other_results=other_results, attempt=1,
        )
        (self.workspace / "claim-analysis.json").unlink()
        analysis = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]["claim-analysis.json"]
        analysis["analyses"][0]["proposed_outcome"] = "granted"
        self.assertIsNotNone(importlib.util.find_spec("run_claim_analysis_stage"))
        stage_runner = importlib.import_module("run_claim_analysis_stage")

        with self.assertRaises(stage_runner.ClaimAnalysisStageError):
            stage_runner.accept_claim_analysis_stage(
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                analysis=analysis, attempt=1,
            )
        self.assertFalse((self.workspace / "claim-analysis.json").exists())

    def prepare_draft_checkpoint(self):
        documentary = importlib.import_module("run_documentary_conditional_stage")
        claim_stage = importlib.import_module("run_claim_analysis_stage")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        state = documentary.accept_documentary_conditional_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            documentary_bundles=bundles, other_results=other_results, attempt=1,
        )
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        (self.workspace / "claim-analysis.json").unlink()
        state = claim_stage.accept_claim_analysis_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            analysis=artifacts["claim-analysis.json"], attempt=1,
        )
        (self.workspace / "disposition-matrix.json").unlink()
        (self.workspace / "judgment-draft.md").unlink()
        return state, context, payload_dir, artifacts["disposition-matrix.json"]

    def test_draft_stage_renders_and_records_pending_review_without_command(self):
        state, context, payload_dir, dispositions = self.prepare_draft_checkpoint()
        self.assertIsNotNone(importlib.util.find_spec("run_draft_judgment_stage"))
        stage_runner = importlib.import_module("run_draft_judgment_stage")
        resume = importlib.import_module("resumable_pipeline")
        state_path = self.workspace / "state-after-draft.json"

        updated = stage_runner.accept_draft_judgment_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            dispositions=dispositions, attempt=1, state_output=state_path,
        )

        self.assertEqual(updated["stages"][-1]["id"], "draft-judgment")
        self.assertEqual(stat.S_IMODE((self.workspace / "disposition-matrix.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.workspace / "judgment-draft.md").stat().st_mode), 0o600)
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), updated)
        self.assertIn("Nenhum comando dispositivo", (self.workspace / "judgment-draft.md").read_text())
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(resume.plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "merge-judgment")

    def test_draft_stage_rejects_decision_command_and_rolls_back_both_outputs(self):
        state, context, payload_dir, dispositions = self.prepare_draft_checkpoint()
        self.assertIsNotNone(importlib.util.find_spec("run_draft_judgment_stage"))
        stage_runner = importlib.import_module("run_draft_judgment_stage")
        dispositions["items"][0]["command"] = "Condeno a reclamada ao pagamento."

        with self.assertRaises(stage_runner.DraftJudgmentStageError):
            stage_runner.accept_draft_judgment_stage(
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                dispositions=dispositions, attempt=1,
            )
        self.assertFalse((self.workspace / "disposition-matrix.json").exists())
        self.assertFalse((self.workspace / "judgment-draft.md").exists())

    def test_draft_stage_removes_partial_file_if_second_write_fails(self):
        state, context, payload_dir, dispositions = self.prepare_draft_checkpoint()
        stage_runner = importlib.import_module("run_draft_judgment_stage")
        real_fsync = stage_runner.os.fsync
        calls = 0

        def fail_second_sync(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("falha de sincronização simulada")
            return real_fsync(descriptor)

        with patch.object(stage_runner.os, "fsync", side_effect=fail_second_sync):
            with self.assertRaises(stage_runner.DraftJudgmentStageError):
                stage_runner.accept_draft_judgment_stage(
                    workspace=self.workspace, plan=self.plan, state=state,
                    source_fingerprint=SOURCE_FINGERPRINT, context=context,
                    authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                    dispositions=dispositions, attempt=1,
                )
        self.assertEqual(calls, 2)
        self.assertFalse((self.workspace / "disposition-matrix.json").exists())
        self.assertFalse((self.workspace / "judgment-draft.md").exists())

    def prepare_merge_checkpoint(self):
        state, context, payload_dir, dispositions = self.prepare_draft_checkpoint()
        draft_stage = importlib.import_module("run_draft_judgment_stage")
        state = draft_stage.accept_draft_judgment_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            dispositions=dispositions, attempt=1,
        )
        merged = self.workspace / f"{context['case_number']}-labor-judgment.md"
        merged.unlink()
        return state, context, payload_dir, merged

    def test_merge_stage_copies_accepted_draft_and_advances_checkpoint(self):
        state, context, payload_dir, merged = self.prepare_merge_checkpoint()
        self.assertIsNotNone(importlib.util.find_spec("run_merge_judgment_stage"))
        stage_runner = importlib.import_module("run_merge_judgment_stage")
        state_path = self.workspace / "state-after-merge.json"

        updated = stage_runner.accept_merge_judgment_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            attempt=1, state_output=state_path,
        )

        self.assertEqual(updated["stages"][-1]["id"], "merge-judgment")
        self.assertEqual(merged.read_bytes(), (self.workspace / "judgment-draft.md").read_bytes())
        self.assertEqual(stat.S_IMODE(merged.stat().st_mode), 0o600)
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), updated)
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(importlib.import_module("resumable_pipeline").plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "review-and-gate")
        with self.assertRaisesRegex(
            importlib.import_module("resumable_pipeline").ResumeContractError,
            "content gate failed",
        ):
            importlib.import_module("resumable_pipeline").record_stage_acceptance(
                self.plan, workspace=self.workspace, state=updated,
                stage_id="review-and-gate", source_fingerprint=SOURCE_FINGERPRINT,
                context=context, gate_validator=validator, attempt=1,
            )

    def test_merge_stage_refuses_stale_draft_without_creating_judgment(self):
        state, context, payload_dir, merged = self.prepare_merge_checkpoint()
        self.assertIsNotNone(importlib.util.find_spec("run_merge_judgment_stage"))
        stage_runner = importlib.import_module("run_merge_judgment_stage")
        draft = self.workspace / "judgment-draft.md"
        draft.write_bytes(draft.read_bytes() + b"\nComando indevido.\n")

        with self.assertRaises(stage_runner.MergeJudgmentStageError):
            stage_runner.accept_merge_judgment_stage(
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                attempt=1,
            )
        self.assertFalse(merged.exists())

    def prepare_fixture_claim_analysis_checkpoint(self, *, extra_limitation=None):
        state, context, payload_dir, _, _ = self.prepare_documentary_checkpoint()
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        review = artifacts["evidence-review.json"]
        if extra_limitation is not None:
            review["reviews"][0]["limitations"].append(extra_limitation)
        self.save("evidence-review.json", review)
        self.save("conditional-work-results.json", artifacts["conditional-work-results.json"])
        resume = importlib.import_module("resumable_pipeline")
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        state = resume.record_stage_acceptance(
            self.plan, workspace=self.workspace, state=state,
            stage_id="execute-conditional-tracks",
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator, attempt=1,
        )
        self.assertEqual(resume.plan_resume(
            self.plan, workspace=self.workspace, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "analyze-claims")
        (self.workspace / "claim-analysis.json").unlink()
        return state, context, payload_dir

    def make_claim_analysis_rehearsal(self, rehearsal_workspace):
        rehearsal = importlib.import_module("run_codex_claim_analysis_rehearsal")
        analysis = {
            "schema_version": 1,
            "analyses": [{
                "analysis_id": "ANL-001", "claim_id": "CLM-001",
                "facts_found": [], "evidence_ids": ["EVD-001"],
                "evidence_assessment": ["EVD-001 ainda depende de revisão humana."],
                "applicable_rules": [], "precedent_source_ids": [],
                "reasoning": "As versões sobre jornada e pagamento permanecem controvertidas.",
                "proposed_outcome": "pending_human_review",
                "limitations": ["Prova e regra jurídica ainda não foram conferidas."],
            }],
        }
        rehearsal.run_codex_claim_analysis_rehearsal(
            rehearsal_workspace, synthetic_rehearsal=True,
            text_generator=lambda _: json.dumps(analysis, ensure_ascii=False),
            model_id="modelo-teste",
        )

    def test_imported_codex_analysis_reaches_shared_checkpoint(self):
        state, context, payload_dir = self.prepare_fixture_claim_analysis_checkpoint()
        self.assertIsNotNone(importlib.util.find_spec("import_codex_claim_analysis_rehearsal"))
        importer = importlib.import_module("import_codex_claim_analysis_rehearsal")
        with tempfile.TemporaryDirectory() as directory:
            rehearsal_workspace = Path(directory)
            self.make_claim_analysis_rehearsal(rehearsal_workspace)
            updated = importer.import_codex_claim_analysis_rehearsal(
                rehearsal_workspace=rehearsal_workspace, workspace=self.workspace,
                plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, authorization_scope_digest=SCOPE_DIGEST,
                payload_dir=payload_dir, expected_model_id="modelo-teste",
                expected_execution_mode="simulated", attempt=1,
            )

        self.assertEqual(updated["stages"][-1]["id"], "analyze-claims")
        self.assertEqual(self.load("claim-analysis.json")["analyses"][0]["proposed_outcome"],
                         "pending_human_review")
        self.assertEqual(stat.S_IMODE((self.workspace / "claim-analysis.json").stat().st_mode),
                         0o600)

    def test_imported_codex_disposition_reaches_shared_draft_checkpoint(self):
        state, context, payload_dir = self.prepare_fixture_claim_analysis_checkpoint()
        claim_importer = importlib.import_module("import_codex_claim_analysis_rehearsal")
        draft_runner = importlib.import_module("run_codex_draft_rehearsal")
        self.assertIsNotNone(importlib.util.find_spec("import_codex_draft_rehearsal"))
        draft_importer = importlib.import_module("import_codex_draft_rehearsal")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "analise"
            draft_source = Path(directory) / "minuta"
            for path in (source, draft_source):
                path.mkdir(mode=0o700)
            self.make_claim_analysis_rehearsal(source)
            state = claim_importer.import_codex_claim_analysis_rehearsal(
                rehearsal_workspace=source, workspace=self.workspace,
                plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, authorization_scope_digest=SCOPE_DIGEST,
                payload_dir=payload_dir, expected_model_id="modelo-teste",
                expected_execution_mode="simulated", attempt=1,
            )
            draft_runner.run_codex_draft_rehearsal(
                draft_source, analysis_workspace=source,
                synthetic_rehearsal=True, model_id="modelo-minuta-teste",
                expected_analysis_model_id="modelo-teste",
                expected_analysis_mode="simulated",
                text_generator=lambda _: json.dumps({
                    "schema_version": 1,
                    "items": [{
                        "disposition_id": "DSP-001", "claim_id": "CLM-001",
                        "outcome": "pending_human_review",
                        "command": "Nenhum comando dispositivo pode ser emitido antes da revisão humana.",
                        "period": "not_applicable", "effects": [],
                        "calculation_criteria": [], "source_analysis_id": "ANL-001",
                    }],
                }, ensure_ascii=False),
            )
            (self.workspace / "disposition-matrix.json").unlink()
            (self.workspace / "judgment-draft.md").unlink()
            updated = draft_importer.import_codex_draft_rehearsal(
                rehearsal_workspace=draft_source, analysis_workspace=source,
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                expected_model_id="modelo-minuta-teste",
                expected_analysis_model_id="modelo-teste",
                expected_execution_mode="simulated",
                expected_analysis_mode="simulated", attempt=1,
            )

        self.assertEqual(updated["stages"][-1]["id"], "draft-judgment")
        self.assertIn("Nenhum comando dispositivo", (self.workspace / "judgment-draft.md").read_text())
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(importlib.import_module("resumable_pipeline").plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "merge-judgment")

    def test_import_rejects_changed_model_output_before_checkpoint(self):
        state, context, payload_dir = self.prepare_fixture_claim_analysis_checkpoint()
        self.assertIsNotNone(importlib.util.find_spec("import_codex_claim_analysis_rehearsal"))
        importer = importlib.import_module("import_codex_claim_analysis_rehearsal")
        with tempfile.TemporaryDirectory() as directory:
            rehearsal_workspace = Path(directory)
            self.make_claim_analysis_rehearsal(rehearsal_workspace)
            output = rehearsal_workspace / "claim-analysis.json"
            output.write_bytes(output.read_bytes() + b" ")
            with self.assertRaises(importer.CodexClaimAnalysisImportError):
                importer.import_codex_claim_analysis_rehearsal(
                    rehearsal_workspace=rehearsal_workspace, workspace=self.workspace,
                    plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                    context=context, authorization_scope_digest=SCOPE_DIGEST,
                    payload_dir=payload_dir, expected_model_id="modelo-teste",
                    expected_execution_mode="simulated", attempt=1,
                )
        self.assertFalse((self.workspace / "claim-analysis.json").exists())

    def test_import_rejects_current_inputs_that_differ_from_model_inputs(self):
        state, context, payload_dir = self.prepare_fixture_claim_analysis_checkpoint(
            extra_limitation="Limitação adicionada após a amostra enviada ao modelo."
        )
        self.assertIsNotNone(importlib.util.find_spec("import_codex_claim_analysis_rehearsal"))
        importer = importlib.import_module("import_codex_claim_analysis_rehearsal")
        with tempfile.TemporaryDirectory() as directory:
            rehearsal_workspace = Path(directory)
            self.make_claim_analysis_rehearsal(rehearsal_workspace)
            with self.assertRaises(importer.CodexClaimAnalysisImportError):
                importer.import_codex_claim_analysis_rehearsal(
                    rehearsal_workspace=rehearsal_workspace, workspace=self.workspace,
                    plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                    context=context, authorization_scope_digest=SCOPE_DIGEST,
                    payload_dir=payload_dir, expected_model_id="modelo-teste",
                    expected_execution_mode="simulated", attempt=1,
                )
        self.assertFalse((self.workspace / "claim-analysis.json").exists())

    def test_codex_import_rejects_a_claude_runtime_plan(self):
        _, context, payload_dir = self.prepare_fixture_claim_analysis_checkpoint()
        importer = importlib.import_module("import_codex_claim_analysis_rehearsal")
        claude_plan = importlib.import_module("run_synthetic_pipeline")._resolve_plan("claude")
        self.save("execution-manifest.json", claude_plan)
        resume = importlib.import_module("resumable_pipeline")
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, claude_plan, SCOPE_DIGEST, payload_dir
        )
        state = resume.new_execution_state(claude_plan, SOURCE_FINGERPRINT)
        for stage_id in (
            "prepare-profile", "acquire-case", "extract-record", "build-decision-units",
            "prepare-triage-input", "narrate-record", "route-claims",
            "execute-conditional-tracks",
        ):
            state = resume.record_stage_acceptance(
                claude_plan, workspace=self.workspace, state=state,
                stage_id=stage_id, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, gate_validator=validator, attempt=1,
            )
        with tempfile.TemporaryDirectory() as directory:
            rehearsal_workspace = Path(directory)
            self.make_claim_analysis_rehearsal(rehearsal_workspace)
            with self.assertRaises(importer.CodexClaimAnalysisImportError):
                importer.import_codex_claim_analysis_rehearsal(
                    rehearsal_workspace=rehearsal_workspace, workspace=self.workspace,
                    plan=claude_plan, state=state,
                    source_fingerprint=SOURCE_FINGERPRINT, context=context,
                    authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                    expected_model_id="modelo-teste",
                    expected_execution_mode="simulated", attempt=1,
                )
        self.assertFalse((self.workspace / "claim-analysis.json").exists())

    def test_documentary_files_record_shared_checkpoint_without_manual_bundles(self):
        stage_runner = importlib.import_module("run_documentary_conditional_stage")
        batch = importlib.import_module("prepare_documentary_claim_packets")
        resume = importlib.import_module("resumable_pipeline")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        index = batch.prepare_documentary_claim_packets(
            self.workspace, bundles["CLM-001"]["pdf_path"]
        )
        self.save(
            "CLM-001-documentary-observations.json",
            bundles["CLM-001"]["observations"],
        )
        self.assertEqual(len(index["records"]), 1)
        self.assertTrue(hasattr(stage_runner, "accept_documentary_conditional_stage_from_files"))

        updated = stage_runner.accept_documentary_conditional_stage_from_files(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            other_results=other_results, attempt=1,
        )

        self.assertEqual(updated["stages"][-1]["id"], "execute-conditional-tracks")
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(resume.plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "analyze-claims")

    def test_documentary_files_missing_observation_never_publish_checkpoint(self):
        stage_runner = importlib.import_module("run_documentary_conditional_stage")
        batch = importlib.import_module("prepare_documentary_claim_packets")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        batch.prepare_documentary_claim_packets(self.workspace, bundles["CLM-001"]["pdf_path"])
        self.assertTrue(hasattr(stage_runner, "accept_documentary_conditional_stage_from_files"))

        with self.assertRaises(stage_runner.DocumentaryStageRunnerError):
            stage_runner.accept_documentary_conditional_stage_from_files(
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                other_results=other_results, attempt=1,
            )

        self.assertFalse((self.workspace / "evidence-review.json").exists())
        self.assertFalse((self.workspace / "conditional-work-results.json").exists())
        self.assertFalse((self.workspace / "documentary-source-register.json").exists())

    def test_documentary_stage_rejects_missing_route_checkpoint_without_outputs(self):
        stage_runner = importlib.import_module("run_documentary_conditional_stage")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        state["stages"].pop()

        with self.assertRaises(stage_runner.DocumentaryStageRunnerError):
            stage_runner.accept_documentary_conditional_stage(
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                documentary_bundles=bundles, other_results=other_results, attempt=1,
            )

        self.assertFalse((self.workspace / "evidence-review.json").exists())
        self.assertFalse((self.workspace / "conditional-work-results.json").exists())

    def test_documentary_stage_persists_private_state_for_resume(self):
        stage_runner = importlib.import_module("run_documentary_conditional_stage")
        resume = importlib.import_module("resumable_pipeline")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        state_output = self.workspace / "execution-state-conditional.json"

        updated = stage_runner.accept_documentary_conditional_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            documentary_bundles=bundles, other_results=other_results, attempt=1,
            state_output=state_output,
        )

        self.assertEqual(self.load("execution-state-conditional.json"), updated)
        self.assertEqual(stat.S_IMODE(state_output.stat().st_mode), 0o600)
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(resume.plan_resume(
            self.plan, workspace=self.workspace,
            state=self.load("execution-state-conditional.json"),
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "analyze-claims")

    def test_documentary_source_change_invalidates_saved_checkpoint(self):
        stage_runner = importlib.import_module("run_documentary_conditional_stage")
        resume = importlib.import_module("resumable_pipeline")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        state_output = self.workspace / "execution-state-conditional.json"
        stage_runner.accept_documentary_conditional_stage(
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            documentary_bundles=bundles, other_results=other_results, attempt=1,
            state_output=state_output,
        )
        source_pdf = bundles["CLM-001"]["pdf_path"]
        source_pdf.write_bytes(source_pdf.read_bytes() + b"\n")
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )

        resumed = resume.plan_resume(
            self.plan, workspace=self.workspace,
            state=self.load("execution-state-conditional.json"),
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )

        self.assertEqual(resumed["next_stage"], "execute-conditional-tracks")
        self.assertIn(
            "current content gate failed",
            resumed["stale_reasons"]["execute-conditional-tracks"],
        )

    def synthetic_documentary_response(self, prompt):
        digest_line = next(
            line for line in prompt.splitlines()
            if line.startswith("SHA-256 UTF-8 do pacote informado pelo orquestrador: ")
        )
        return json.dumps({
            "schema_version": 1, "claim_id": "CLM-001",
            "source_packet_sha256": digest_line.rsplit(": ", 1)[1],
            "status": "pending_human_review",
            "observations": [{
                "evidence_id": "EVD-001", "source_document_id": "DOC-002",
                "excerpts": [{"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"}],
                "observation": "A página contém o registro citado.",
                "limitations": ["Autenticidade não conferida."],
            }],
        }, ensure_ascii=False)

    def make_documentary_rehearsal_output(self):
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        source_workspace = Path(temporary.name)

        rehearsal.run_codex_documentary_rehearsal(
            source_workspace, synthetic_rehearsal=True,
            text_generator=self.synthetic_documentary_response, model_id="modelo-teste",
        )
        return source_workspace, rehearsal._synthetic_evidence()

    def test_protected_codex_rehearsal_reaches_shared_checkpoint(self):
        importer = importlib.import_module("import_codex_documentary_rehearsal")
        resume = importlib.import_module("resumable_pipeline")
        source_workspace, evidence = self.make_documentary_rehearsal_output()
        state, context, payload_dir, _, other_results = self.prepare_documentary_checkpoint(
            evidence_override=evidence
        )
        (self.workspace / "fonte-sintetica.pdf").unlink()
        state_output = self.workspace / "execution-state-conditional.json"

        updated = importer.import_codex_documentary_rehearsal(
            rehearsal_workspace=source_workspace, workspace=self.workspace,
            plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
            context=context, authorization_scope_digest=SCOPE_DIGEST,
            payload_dir=payload_dir, other_results=other_results,
            expected_model_id="modelo-teste", attempt=1, state_output=state_output,
        )

        self.assertEqual(updated["stages"][-1]["id"], "execute-conditional-tracks")
        self.assertEqual(self.load("execution-state-conditional.json"), updated)
        imported_pdf = self.workspace / "synthetic-source.pdf"
        self.assertEqual(
            imported_pdf.read_bytes(), (source_workspace / "synthetic-source.pdf").read_bytes()
        )
        self.assertEqual(stat.S_IMODE(imported_pdf.stat().st_mode), 0o600)
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(resume.plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "analyze-claims")

    def test_changed_rehearsal_summary_is_refused_before_copy(self):
        importer = importlib.import_module("import_codex_documentary_rehearsal")
        source_workspace, evidence = self.make_documentary_rehearsal_output()
        state, context, payload_dir, _, other_results = self.prepare_documentary_checkpoint(
            evidence_override=evidence
        )
        (self.workspace / "fonte-sintetica.pdf").unlink()
        summary_path = source_workspace / "documentary-rehearsal-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["observations_sha256"] = "a" * 64
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

        with self.assertRaises(importer.DocumentaryRehearsalImportError):
            importer.import_codex_documentary_rehearsal(
                rehearsal_workspace=source_workspace, workspace=self.workspace,
                plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, authorization_scope_digest=SCOPE_DIGEST,
                payload_dir=payload_dir, other_results=other_results,
                expected_model_id="modelo-teste", attempt=1,
            )

        self.assertFalse((self.workspace / "synthetic-source.pdf").exists())
        self.assertFalse((self.workspace / "evidence-review.json").exists())

    def test_codex_documentary_stage_dispatches_after_shared_preflight(self):
        dispatcher = importlib.import_module("run_codex_documentary_stage")
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        state, context, payload_dir, _, other_results = self.prepare_documentary_checkpoint(
            evidence_override=rehearsal._synthetic_evidence()
        )
        (self.workspace / "fonte-sintetica.pdf").unlink()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        rehearsal_workspace = Path(temporary.name)
        prompts = []

        def generator(prompt):
            prompts.append(prompt)
            return self.synthetic_documentary_response(prompt)

        updated = dispatcher.run_codex_documentary_stage(
            rehearsal_workspace=rehearsal_workspace, workspace=self.workspace,
            plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
            context=context, authorization_scope_digest=SCOPE_DIGEST,
            payload_dir=payload_dir, other_results=other_results,
            model_id="modelo-teste", synthetic_rehearsal=True,
            text_generator=generator, attempt=1,
            state_output=self.workspace / "execution-state-conditional.json",
        )

        self.assertEqual(len(prompts), 1)
        self.assertIn("REGISTRO DE JORNADA SINTÉTICO", prompts[0])
        self.assertEqual(updated["stages"][-1]["id"], "execute-conditional-tracks")
        self.assertTrue((self.workspace / "documentary-source-register.json").is_file())

    def prepare_codex_documentary_analysis_checkpoint(self):
        documentary = importlib.import_module("run_codex_documentary_stage")
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        state, context, payload_dir, _, other_results = self.prepare_documentary_checkpoint(
            evidence_override=rehearsal._synthetic_evidence()
        )
        (self.workspace / "fonte-sintetica.pdf").unlink()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = documentary.run_codex_documentary_stage(
            rehearsal_workspace=Path(temporary.name), workspace=self.workspace,
            plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
            context=context, authorization_scope_digest=SCOPE_DIGEST,
            payload_dir=payload_dir, other_results=other_results,
            model_id="modelo-documental-teste", synthetic_rehearsal=True,
            text_generator=self.synthetic_documentary_response, attempt=1,
        )
        (self.workspace / "claim-analysis.json").unlink()
        return state, context, payload_dir

    def test_codex_analysis_stage_dispatches_current_documentary_inputs(self):
        state, context, payload_dir = self.prepare_codex_documentary_analysis_checkpoint()
        self.assertIsNotNone(importlib.util.find_spec("run_codex_claim_analysis_stage"))
        dispatcher = importlib.import_module("run_codex_claim_analysis_stage")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        receipt_workspace = Path(temporary.name)
        prompts = []

        def response(prompt):
            prompts.append(prompt)
            return json.dumps({
                "schema_version": 1,
                "analyses": [{
                    "analysis_id": "ANL-001", "claim_id": "CLM-001",
                    "facts_found": [], "evidence_ids": ["EVD-001"],
                    "evidence_assessment": ["O documento fictício depende de revisão humana."],
                    "applicable_rules": [], "precedent_source_ids": [],
                    "reasoning": "As alegações são conflitantes; não há prova nem regra revisada.",
                    "proposed_outcome": "pending_human_review",
                    "limitations": ["Revisão jurídica e probatória pendente."],
                }],
            }, ensure_ascii=False)

        updated = dispatcher.run_codex_claim_analysis_stage(
            receipt_workspace=receipt_workspace, workspace=self.workspace,
            plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
            context=context, authorization_scope_digest=SCOPE_DIGEST,
            payload_dir=payload_dir, model_id="modelo-analise-teste",
            synthetic_rehearsal=True, text_generator=response, attempt=1,
        )

        self.assertEqual(updated["stages"][-1]["id"], "analyze-claims")
        self.assertEqual(len(prompts), 1)
        current_review = self.load("evidence-review.json")
        self.assertIn(current_review["reviews"][0]["limitations"][-1], prompts[0])
        self.assertIn("<conditional-work-results.json>", prompts[0])
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", prompts[0])
        self.assertEqual(self.load("claim-analysis.json")["analyses"][0]["proposed_outcome"],
                         "pending_human_review")
        self.assertEqual(stat.S_IMODE((self.workspace / "claim-analysis.json").stat().st_mode),
                         0o600)
        receipt = json.loads(
            (receipt_workspace / "claim-analysis-stage-receipt.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["execution_mode"], "simulated")
        self.assertEqual(receipt["analysis_sha256"], hashlib.sha256(
            (self.workspace / "claim-analysis.json").read_bytes()
        ).hexdigest())
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(importlib.import_module("resumable_pipeline").plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "draft-judgment")

    def test_codex_analysis_stage_rejects_occupied_state_before_dispatch(self):
        state, context, payload_dir = self.prepare_codex_documentary_analysis_checkpoint()
        dispatcher = importlib.import_module("run_codex_claim_analysis_stage")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        receipt_workspace = Path(temporary.name)
        state_output = self.workspace / "state-after-analysis.json"
        state_output.write_text("preservar", encoding="utf-8")

        def forbidden(_prompt):
            self.fail("o agente não deveria receber insumos com saída ocupada")

        with self.assertRaises(dispatcher.CodexClaimAnalysisStageError):
            dispatcher.run_codex_claim_analysis_stage(
                receipt_workspace=receipt_workspace, workspace=self.workspace,
                plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, authorization_scope_digest=SCOPE_DIGEST,
                payload_dir=payload_dir, model_id="modelo-analise-teste",
                synthetic_rehearsal=True, text_generator=forbidden, attempt=1,
                state_output=state_output,
            )
        self.assertEqual(state_output.read_text(encoding="utf-8"), "preservar")
        self.assertFalse((self.workspace / "claim-analysis.json").exists())
        self.assertFalse(any(receipt_workspace.iterdir()))

    def test_codex_analysis_stage_rejects_invalid_attempt_before_dispatch(self):
        state, context, payload_dir = self.prepare_codex_documentary_analysis_checkpoint()
        dispatcher = importlib.import_module("run_codex_claim_analysis_stage")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        receipt_workspace = Path(temporary.name)

        def forbidden(_prompt):
            self.fail("o agente não deveria ser chamado com tentativa inválida")

        with self.assertRaises(dispatcher.CodexClaimAnalysisStageError):
            dispatcher.run_codex_claim_analysis_stage(
                receipt_workspace=receipt_workspace, workspace=self.workspace,
                plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, authorization_scope_digest=SCOPE_DIGEST,
                payload_dir=payload_dir, model_id="modelo-analise-teste",
                synthetic_rehearsal=True, text_generator=forbidden, attempt=0,
            )
        self.assertFalse((self.workspace / "claim-analysis.json").exists())
        self.assertFalse(any(receipt_workspace.iterdir()))

    def test_codex_analysis_stage_rejects_unlinked_review_text_before_dispatch(self):
        state, context, payload_dir = self.prepare_codex_documentary_analysis_checkpoint()
        dispatcher = importlib.import_module("run_codex_claim_analysis_stage")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        receipt_workspace = Path(temporary.name)
        review = self.load("evidence-review.json")
        review["reviews"][0]["assessment"] = "Conteúdo não derivado do PDF fictício."
        self.save("evidence-review.json", review)

        def forbidden(_prompt):
            self.fail("texto não vinculado à fonte não deve ser enviado ao modelo")

        with self.assertRaises(dispatcher.CodexClaimAnalysisStageError):
            dispatcher.run_codex_claim_analysis_stage(
                receipt_workspace=receipt_workspace, workspace=self.workspace,
                plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, authorization_scope_digest=SCOPE_DIGEST,
                payload_dir=payload_dir, model_id="modelo-analise-teste",
                synthetic_rehearsal=True, text_generator=forbidden, attempt=1,
            )
        self.assertFalse((self.workspace / "claim-analysis.json").exists())
        self.assertFalse(any(receipt_workspace.iterdir()))

    def prepare_codex_current_draft_checkpoint(self):
        state, context, payload_dir = self.prepare_codex_documentary_analysis_checkpoint()
        analyzer = importlib.import_module("run_codex_claim_analysis_stage")
        receipt_parent = tempfile.TemporaryDirectory()
        self.addCleanup(receipt_parent.cleanup)
        analysis_receipt = Path(receipt_parent.name) / "analise"
        draft_receipt = Path(receipt_parent.name) / "minuta"
        for directory in (analysis_receipt, draft_receipt):
            directory.mkdir(mode=0o700)
        state = analyzer.run_codex_claim_analysis_stage(
            receipt_workspace=analysis_receipt, workspace=self.workspace,
            plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
            context=context, authorization_scope_digest=SCOPE_DIGEST,
            payload_dir=payload_dir, model_id="modelo-analise-teste",
            synthetic_rehearsal=True, attempt=1,
            text_generator=lambda _: json.dumps({
                "schema_version": 1,
                "analyses": [{
                    "analysis_id": "ANL-001", "claim_id": "CLM-001",
                    "facts_found": [], "evidence_ids": ["EVD-001"],
                    "evidence_assessment": ["A observação documental exige revisão humana."],
                    "applicable_rules": [], "precedent_source_ids": [],
                    "reasoning": "A análise documental atual não resolve o pedido.",
                    "proposed_outcome": "pending_human_review",
                    "limitations": ["Revisão jurídica pendente."],
                }],
            }, ensure_ascii=False),
        )
        (self.workspace / "disposition-matrix.json").unlink()
        (self.workspace / "judgment-draft.md").unlink()
        return state, context, payload_dir, analysis_receipt, draft_receipt

    def test_codex_draft_stage_uses_current_documentary_analysis(self):
        state, context, payload_dir, analysis_receipt, draft_receipt = (
            self.prepare_codex_current_draft_checkpoint()
        )
        self.assertIsNotNone(importlib.util.find_spec("run_codex_draft_stage"))
        drafter = importlib.import_module("run_codex_draft_stage")
        prompts = []

        def pending_response(prompt):
            prompts.append(prompt)
            return json.dumps({
                "schema_version": 1,
                "items": [{
                    "disposition_id": "DSP-001", "claim_id": "CLM-001",
                    "outcome": "pending_human_review",
                    "command": "Nenhum comando dispositivo pode ser emitido antes da revisão humana.",
                    "period": "not_applicable", "effects": [],
                    "calculation_criteria": [], "source_analysis_id": "ANL-001",
                }],
            }, ensure_ascii=False)

        updated = drafter.run_codex_draft_stage(
            receipt_workspace=draft_receipt, analysis_receipt_workspace=analysis_receipt,
            workspace=self.workspace, plan=self.plan, state=state,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
            model_id="modelo-minuta-teste", expected_analysis_model_id="modelo-analise-teste",
            expected_analysis_mode="simulated", synthetic_rehearsal=True,
            text_generator=pending_response, attempt=1,
        )

        self.assertEqual(updated["stages"][-1]["id"], "draft-judgment")
        self.assertEqual(len(prompts), 1)
        self.assertIn("A análise documental atual não resolve o pedido.", prompts[0])
        self.assertIn("<evidence-review.json>", prompts[0])
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", prompts[0])
        self.assertIn("Nenhum comando dispositivo", self.load("disposition-matrix.json")["items"][0]["command"])
        self.assertEqual(stat.S_IMODE((self.workspace / "judgment-draft.md").stat().st_mode), 0o600)
        receipt = json.loads((draft_receipt / "draft-stage-receipt.json").read_text())
        self.assertEqual(receipt["analysis_sha256"], hashlib.sha256(
            (self.workspace / "claim-analysis.json").read_bytes()
        ).hexdigest())
        self.assertEqual(receipt["execution_mode"], "simulated")
        validator = importlib.import_module("trt12_pipeline_gates").make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        self.assertEqual(importlib.import_module("resumable_pipeline").plan_resume(
            self.plan, workspace=self.workspace, state=updated,
            source_fingerprint=SOURCE_FINGERPRINT, context=context,
            gate_validator=validator,
        )["next_stage"], "merge-judgment")

    def test_codex_draft_stage_rejects_state_output_collision_before_dispatch(self):
        state, context, payload_dir, analysis_receipt, draft_receipt = (
            self.prepare_codex_current_draft_checkpoint()
        )
        drafter = importlib.import_module("run_codex_draft_stage")

        def forbidden(_prompt):
            self.fail("o fundamentador não deve receber insumos com destino conflitante")

        with self.assertRaises(drafter.CodexDraftStageError):
            drafter.run_codex_draft_stage(
                receipt_workspace=draft_receipt,
                analysis_receipt_workspace=analysis_receipt,
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                model_id="modelo-minuta-teste",
                expected_analysis_model_id="modelo-analise-teste",
                expected_analysis_mode="simulated", synthetic_rehearsal=True,
                text_generator=forbidden, attempt=1,
                state_output=self.workspace / "disposition-matrix.json",
            )
        self.assertFalse((self.workspace / "disposition-matrix.json").exists())
        self.assertFalse((self.workspace / "judgment-draft.md").exists())
        self.assertFalse(any(draft_receipt.iterdir()))

    def test_codex_draft_stage_rejects_changed_analysis_prompt_receipt(self):
        state, context, payload_dir, analysis_receipt, draft_receipt = (
            self.prepare_codex_current_draft_checkpoint()
        )
        receipt_path = analysis_receipt / "claim-analysis-stage-receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["prompt_sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
        drafter = importlib.import_module("run_codex_draft_stage")

        def forbidden(_prompt):
            self.fail("o fundamentador não deve receber análise com recibo adulterado")

        with self.assertRaises(drafter.CodexDraftStageError):
            drafter.run_codex_draft_stage(
                receipt_workspace=draft_receipt,
                analysis_receipt_workspace=analysis_receipt,
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                model_id="modelo-minuta-teste",
                expected_analysis_model_id="modelo-analise-teste",
                expected_analysis_mode="simulated", synthetic_rehearsal=True,
                text_generator=forbidden, attempt=1,
            )
        self.assertFalse((self.workspace / "disposition-matrix.json").exists())
        self.assertFalse(any(draft_receipt.iterdir()))

    def test_codex_documentary_stage_never_dispatches_before_route_checkpoint(self):
        dispatcher = importlib.import_module("run_codex_documentary_stage")
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        state, context, payload_dir, _, other_results = self.prepare_documentary_checkpoint(
            evidence_override=rehearsal._synthetic_evidence()
        )
        state["stages"].pop()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        rehearsal_workspace = Path(temporary.name)

        def forbidden(_prompt):
            self.fail("o agente não deveria ter sido chamado")

        with self.assertRaises(dispatcher.CodexDocumentaryStageError):
            dispatcher.run_codex_documentary_stage(
                rehearsal_workspace=rehearsal_workspace, workspace=self.workspace,
                plan=self.plan, state=state, source_fingerprint=SOURCE_FINGERPRINT,
                context=context, authorization_scope_digest=SCOPE_DIGEST,
                payload_dir=payload_dir, other_results=other_results,
                model_id="modelo-teste", synthetic_rehearsal=True,
                text_generator=forbidden, attempt=1,
            )

        self.assertFalse(any(rehearsal_workspace.iterdir()))
        self.assertFalse((self.workspace / "documentary-source-register.json").exists())

    def test_documentary_stage_preserves_existing_state_without_publishing_outputs(self):
        stage_runner = importlib.import_module("run_documentary_conditional_stage")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        state_output = self.workspace / "execution-state-conditional.json"
        existing = b'{"nao":"substituir"}'
        state_output.write_bytes(existing)

        with self.assertRaises(stage_runner.DocumentaryStageRunnerError):
            stage_runner.accept_documentary_conditional_stage(
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                documentary_bundles=bundles, other_results=other_results, attempt=1,
                state_output=state_output,
            )

        self.assertEqual(state_output.read_bytes(), existing)
        self.assertFalse((self.workspace / "evidence-review.json").exists())
        self.assertFalse((self.workspace / "conditional-work-results.json").exists())

    def test_documentary_stage_invalid_attempt_leaves_no_state_or_stage_outputs(self):
        stage_runner = importlib.import_module("run_documentary_conditional_stage")
        state, context, payload_dir, bundles, other_results = self.prepare_documentary_checkpoint()
        state_output = self.workspace / "execution-state-conditional.json"

        with self.assertRaises(stage_runner.DocumentaryStageRunnerError):
            stage_runner.accept_documentary_conditional_stage(
                workspace=self.workspace, plan=self.plan, state=state,
                source_fingerprint=SOURCE_FINGERPRINT, context=context,
                authorization_scope_digest=SCOPE_DIGEST, payload_dir=payload_dir,
                documentary_bundles=bundles, other_results=other_results, attempt=3,
                state_output=state_output,
            )

        self.assertFalse(state_output.exists())
        self.assertFalse((self.workspace / "evidence-review.json").exists())
        self.assertFalse((self.workspace / "conditional-work-results.json").exists())

    def test_complete_record_records_third_global_checkpoint(self):
        initial = importlib.import_module("trt12_initial_gate")
        acquisition = importlib.import_module("trt12_acquisition_gate")
        resume = importlib.import_module("resumable_pipeline")
        index, payload_dir = self.make_verified_acquisition()
        validators = (
            initial.make_initial_gate(self.workspace, self.plan),
            acquisition.make_acquisition_gate(self.workspace, SCOPE_DIGEST, payload_dir),
            self.gate.make_extraction_gate(self.workspace),
        )

        def validate(stage, outputs):
            return any(validator(stage, outputs) for validator in validators)

        context = {"case_number": index["case"]["case_number"]}
        state = resume.new_execution_state(self.plan, SOURCE_FINGERPRINT)
        for stage_id in ("prepare-profile", "acquire-case", "extract-record"):
            state = resume.record_stage_acceptance(
                self.plan,
                workspace=self.workspace,
                state=state,
                stage_id=stage_id,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=context,
                gate_validator=validate,
                attempt=1,
            )
        resumed = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validate,
        )
        self.assertEqual(resumed["reused_stages"], [
            "prepare-profile", "acquire-case", "extract-record",
        ])
        self.assertEqual(resumed["next_stage"], "build-decision-units")

    def test_matrices_and_triage_input_record_checkpoints_in_full_pipeline(self):
        if importlib.util.find_spec("trt12_pipeline_gates") is None:
            self.fail("o conjunto de controles do pipeline TRT12 não existe")
        gates = importlib.import_module("trt12_pipeline_gates")
        resume = importlib.import_module("resumable_pipeline")
        index, payload_dir = self.make_verified_acquisition()
        validator = gates.make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        triage_input = importlib.import_module("build_superjurista_triage_input")
        (self.workspace / "triage-input.md").unlink()
        triage_input.write_triage_input(
            triage_input.build_triage_input(
                self.load("labor-report.json"), self.load("claim-matrix.json")
            ),
            self.workspace / "triage-input.md",
        )
        context = {"case_number": index["case"]["case_number"]}
        state = resume.new_execution_state(self.plan, SOURCE_FINGERPRINT)
        for stage_id in (
            "prepare-profile", "acquire-case", "extract-record", "build-decision-units",
            "prepare-triage-input",
        ):
            state = resume.record_stage_acceptance(
                self.plan,
                workspace=self.workspace,
                state=state,
                stage_id=stage_id,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=context,
                gate_validator=validator,
                attempt=1,
            )
        resumed = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(resumed["reused_stages"], [
            "prepare-profile", "acquire-case", "extract-record", "build-decision-units",
            "prepare-triage-input",
        ])
        self.assertEqual(resumed["next_stage"], "narrate-record")

    def test_full_pipeline_checkpoints_hold_pending_review_and_accept_abstention(self):
        gates = importlib.import_module("trt12_pipeline_gates")
        resume = importlib.import_module("resumable_pipeline")
        triage_input = importlib.import_module("build_superjurista_triage_input")
        index, payload_dir = self.make_verified_acquisition()
        validator = gates.make_trt12_gate_validator(
            self.workspace, self.plan, SCOPE_DIGEST, payload_dir
        )
        old_input = (self.workspace / "triage-input.md").read_text(encoding="utf-8")
        old_digest = hashlib.sha256(old_input.encode()).hexdigest()
        new_input = triage_input.build_triage_input(
            self.load("labor-report.json"), self.load("claim-matrix.json")
        )
        new_digest = hashlib.sha256(new_input.encode()).hexdigest()
        (self.workspace / "triage-input.md").unlink()
        triage_input.write_triage_input(new_input, self.workspace / "triage-input.md")
        narrative_path = self.workspace / "report-narrative.md"
        narrative = narrative_path.read_text(encoding="utf-8").replace(
            old_digest, new_digest
        )
        narrative = narrative.replace(
            "A linha do tempo registra o ajuizamento em 10 de janeiro de 2026 "
            "(DOC-001, página 1).",
            "A linha do tempo registra o ajuizamento em 10 de janeiro de 2026 "
            "(DOC-001, página 1) e a defesa apresentada em 20 de janeiro de 2026 "
            "(DOC-002, página 1).",
        )
        prefix, rest = narrative.split("```json\n", 1)
        _, suffix = rest.split("\n```", 1)
        coverage = {
            "events": [
                {"event_id": "EVT-001", "source_document_id": "DOC-001", "source_locator": "página 1"},
                {"event_id": "EVT-002", "source_document_id": "DOC-002", "source_locator": "página 1"},
            ],
            "claims": [{"claim_id": "CLM-001", "source_document_id": "DOC-001", "source_locator": "páginas 4-5"}],
            "defenses": [{
                "defense_id": "DEF-001", "claim_id": "CLM-001", "respondent_party_id": "PTY-002",
                "source_document_id": "DOC-002", "source_locator": "páginas 2-3",
            }],
            "unanswered_claim_ids": [],
        }
        narrative_path.write_text(
            prefix + "```json\n" + json.dumps(coverage, ensure_ascii=False)
            + "\n```" + suffix,
            encoding="utf-8",
        )
        case_number = index["case"]["case_number"]
        triage_path = self.workspace / f"{case_number}-triagem.md"
        triage_path.write_text(
            triage_path.read_text(encoding="utf-8").replace(old_digest, new_digest),
            encoding="utf-8",
        )
        context = {"case_number": case_number}
        state = resume.new_execution_state(self.plan, SOURCE_FINGERPRINT)
        accepted = (
            "prepare-profile", "acquire-case", "extract-record", "build-decision-units",
            "prepare-triage-input", "narrate-record", "route-claims", "execute-conditional-tracks",
        )
        for stage_id in accepted:
            state = resume.record_stage_acceptance(
                self.plan,
                workspace=self.workspace,
                state=state,
                stage_id=stage_id,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=context,
                gate_validator=validator,
                attempt=1,
            )
        resumed = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(resumed["reused_stages"], list(accepted))
        self.assertEqual(resumed["next_stage"], "analyze-claims")
        ninth_state = resume.record_stage_acceptance(
            self.plan,
            workspace=self.workspace,
            state=state,
            stage_id="analyze-claims",
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
            attempt=1,
        )
        ninth_resumed = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=ninth_state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(ninth_resumed["reused_stages"], [*accepted, "analyze-claims"])
        self.assertEqual(ninth_resumed["next_stage"], "draft-judgment")
        tenth_state = resume.record_stage_acceptance(
            self.plan,
            workspace=self.workspace,
            state=ninth_state,
            stage_id="draft-judgment",
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
            attempt=1,
        )
        tenth_resumed = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=tenth_state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(
            tenth_resumed["reused_stages"], [*accepted, "analyze-claims", "draft-judgment"]
        )
        self.assertEqual(tenth_resumed["next_stage"], "merge-judgment")
        eleventh_state = resume.record_stage_acceptance(
            self.plan,
            workspace=self.workspace,
            state=tenth_state,
            stage_id="merge-judgment",
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
            attempt=1,
        )
        eleventh_resumed = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=eleventh_state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(
            eleventh_resumed["reused_stages"],
            [*accepted, "analyze-claims", "draft-judgment", "merge-judgment"],
        )
        self.assertEqual(eleventh_resumed["next_stage"], "review-and-gate")
        with self.assertRaisesRegex(resume.ResumeContractError, "content gate failed"):
            resume.record_stage_acceptance(
                self.plan,
                workspace=self.workspace,
                state=eleventh_state,
                stage_id="review-and-gate",
                source_fingerprint=SOURCE_FINGERPRINT,
                context=context,
                gate_validator=validator,
                attempt=1,
            )
        merged_path = self.workspace / f"{case_number}-labor-judgment.md"
        accepted_merged = merged_path.read_text(encoding="utf-8")
        merged_path.write_text(accepted_merged + "\nTexto acrescentado.\n", encoding="utf-8")
        invalid_merge = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=eleventh_state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(
            invalid_merge["reused_stages"], [*accepted, "analyze-claims", "draft-judgment"]
        )
        self.assertEqual(invalid_merge["next_stage"], "merge-judgment")
        merged_path.write_text(accepted_merged, encoding="utf-8")
        draft_path = self.workspace / "judgment-draft.md"
        accepted_draft = draft_path.read_text(encoding="utf-8")
        draft_path.write_text(accepted_draft + "\nJulgo procedente o pedido.\n", encoding="utf-8")
        invalid_draft = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=tenth_state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(invalid_draft["reused_stages"], [*accepted, "analyze-claims"])
        self.assertEqual(invalid_draft["next_stage"], "draft-judgment")
        draft_path.write_text(accepted_draft, encoding="utf-8")
        analysis = self.load("claim-analysis.json")
        analysis["analyses"][0]["facts_found"] = ["Conclusão sem revisão da prova."]
        self.save("claim-analysis.json", analysis)
        invalid_analysis = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=ninth_state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(invalid_analysis["reused_stages"], list(accepted))
        self.assertEqual(invalid_analysis["next_stage"], "analyze-claims")
        receipt_path = self.workspace / "conditional-work-results.json"
        accepted_receipt_bytes = receipt_path.read_bytes()
        receipts = self.load("conditional-work-results.json")
        receipts["results"][0]["limitations"].append("Revisão posterior necessária.")
        self.save("conditional-work-results.json", receipts)
        invalidated = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=state,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(invalidated["reused_stages"], list(accepted[:-1]))
        self.assertEqual(invalidated["next_stage"], "execute-conditional-tracks")

        receipt_path.write_bytes(accepted_receipt_bytes)
        analysis["analyses"][0]["facts_found"] = []
        analysis["analyses"][0]["proposed_outcome"] = "abstained"
        self.save("claim-analysis.json", analysis)
        dispositions = self.load("disposition-matrix.json")
        dispositions["items"][0].update({
            "outcome": "abstained",
            "command": "Nenhum comando dispositivo foi produzido devido à abstenção.",
        })
        self.save("disposition-matrix.json", dispositions)
        abstained_draft = accepted_draft.replace("revisão humana pendente", "abstenção")
        abstained_draft = abstained_draft.replace(
            "Nenhum comando dispositivo pode ser emitido antes da revisão humana.",
            "Nenhum comando dispositivo foi produzido devido à abstenção.",
        )
        draft_path.write_text(abstained_draft, encoding="utf-8")
        merged_path.write_text(abstained_draft, encoding="utf-8")
        completed = state
        for stage_id in (
            "analyze-claims", "draft-judgment", "merge-judgment", "review-and-gate"
        ):
            completed = resume.record_stage_acceptance(
                self.plan,
                workspace=self.workspace,
                state=completed,
                stage_id=stage_id,
                source_fingerprint=SOURCE_FINGERPRINT,
                context=context,
                gate_validator=validator,
                attempt=1,
            )
        complete_resume = resume.plan_resume(
            self.plan,
            workspace=self.workspace,
            state=completed,
            source_fingerprint=SOURCE_FINGERPRINT,
            context=context,
            gate_validator=validator,
        )
        self.assertEqual(len(complete_resume["reused_stages"]), 12)
        self.assertIsNone(complete_resume["next_stage"])


if __name__ == "__main__":
    unittest.main()
