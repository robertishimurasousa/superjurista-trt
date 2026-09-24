from __future__ import annotations

import copy
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
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class DocumentaryConditionalStageTest(unittest.TestCase):
    def setUp(self) -> None:
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        self.subject = importlib.import_module("compose_documentary_conditional_stage")
        rehearsal = importlib.import_module("run_codex_documentary_rehearsal")
        segmenter = importlib.import_module("segment_pje_pdf")
        packet_builder = importlib.import_module("prepare_source_evidence_packet")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        os.chmod(self.workspace, 0o700)
        artifacts = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        for name in (
            "case-context.json", "claim-matrix.json", "issue-route.json",
            "precedent-corpus.json", "calculation-review.json",
        ):
            self.save(name, artifacts[name])
        self.evidence = rehearsal._synthetic_evidence()
        self.save("evidence-matrix.json", self.evidence)
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
            "page_count": 2,
            "documents": documents,
            "gaps": [],
        })
        self.pdf = self.workspace / "fonte-sintetica.pdf"
        self.pdf.write_bytes(rehearsal._synthetic_pdf())
        segments = segmenter.segment_pje_pdf(self.pdf)
        packet = packet_builder.build_source_evidence_packet(
            self.pdf, segments, self.evidence,
            claim_id="CLM-001", evidence_ids=("EVD-001",),
        )
        observations = {
            "schema_version": 1,
            "claim_id": "CLM-001",
            "source_packet_sha256": hashlib.sha256(packet.encode("utf-8")).hexdigest(),
            "status": "pending_human_review",
            "observations": [{
                "evidence_id": "EVD-001",
                "source_document_id": "DOC-002",
                "excerpts": [{"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"}],
                "observation": "A página contém o título citado.",
                "limitations": ["O conteúdo integral não foi examinado."],
            }],
        }
        self.bundles = {"CLM-001": {
            "observations": observations, "packet": packet,
            "pdf_path": self.pdf, "segments": segments,
            "evidence_ids": ("EVD-001",),
        }}
        self.other_results = {
            "schema_version": 1,
            "results": [artifacts["conditional-work-results.json"]["results"][0]],
        }

    def save(self, name: str, value: dict) -> None:
        (self.workspace / name).write_text(json.dumps(value), encoding="utf-8")

    def load(self, name: str) -> dict:
        return json.loads((self.workspace / name).read_text(encoding="utf-8"))

    def compose(self):
        return self.subject.publish_documentary_conditional_stage(
            self.workspace, self.bundles, other_results=self.other_results,
        )

    def assert_no_outputs(self) -> None:
        for name in (
            "evidence-review.json", "conditional-work-results.json",
            "documentary-source-register.json",
        ):
            self.assertFalse((self.workspace / name).exists())

    def test_publishes_complete_stage_and_existing_gate_accepts_it(self) -> None:
        published = self.compose()
        self.assertEqual(published, (
            (self.workspace / "evidence-review.json").resolve(),
            (self.workspace / "conditional-work-results.json").resolve(),
            (self.workspace / "documentary-source-register.json").resolve(),
        ))
        review = self.load("evidence-review.json")["reviews"][0]
        self.assertEqual(review["status"], "pending_human_review")
        self.assertEqual(review["assessment"], "")
        results = self.load("conditional-work-results.json")["results"]
        self.assertEqual({item["track"] for item in results}, {
            "legal_research", "evidence_analysis",
        })
        for path in published:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        gate = importlib.import_module("trt12_conditional_tracks_gate")
        outputs = tuple((self.workspace / name).resolve() for name in gate.OUTPUTS)
        self.assertTrue(gate.make_conditional_tracks_gate(self.workspace)(
            {"id": "execute-conditional-tracks", "gate": "conditional-track-custody"},
            outputs,
        ))

    def test_changed_source_pdf_revokes_documentary_gate(self) -> None:
        self.compose()
        self.pdf.write_bytes(self.pdf.read_bytes() + b"\n")
        gate = importlib.import_module("trt12_conditional_tracks_gate")
        outputs = tuple((self.workspace / name).resolve() for name in gate.OUTPUTS)

        self.assertFalse(gate.make_conditional_tracks_gate(self.workspace)(
            {"id": "execute-conditional-tracks", "gate": "conditional-track-custody"},
            outputs,
        ))

    def test_missing_source_register_revokes_documentary_gate(self) -> None:
        self.compose()
        (self.workspace / "documentary-source-register.json").unlink()
        gate = importlib.import_module("trt12_conditional_tracks_gate")
        outputs = tuple((self.workspace / name).resolve() for name in gate.OUTPUTS)

        self.assertFalse(gate.make_conditional_tracks_gate(self.workspace)(
            {"id": "execute-conditional-tracks", "gate": "conditional-track-custody"},
            outputs,
        ))

    def test_missing_bundle_fails_without_publication(self) -> None:
        self.bundles = {}
        with self.assertRaises(self.subject.DocumentaryConditionalStageError):
            self.compose()
        self.assert_no_outputs()

    def test_abstained_claim_needs_no_documentary_bundle(self) -> None:
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
        self.bundles = {}
        self.other_results = {"schema_version": 1, "results": []}

        self.compose()

        review = self.load("evidence-review.json")["reviews"][0]
        self.assertEqual(review["status"], "not_required")
        self.assertEqual(self.load("conditional-work-results.json")["results"], [])

    def test_false_excerpt_fails_without_publication(self) -> None:
        self.bundles["CLM-001"]["observations"]["observations"][0]["excerpts"][0]["text"] = "NÃO EXISTE"
        with self.assertRaises(self.subject.DocumentaryConditionalStageError):
            self.compose()
        self.assert_no_outputs()

    def test_existing_stage_rejection_rolls_back_new_outputs(self) -> None:
        calculation = self.load("calculation-review.json")
        calculation["calculations"][0]["status"] = "criteria_reviewed"
        calculation["calculations"][0]["criteria"] = ["Critério não encaminhado."]
        self.save("calculation-review.json", calculation)
        with self.assertRaises(self.subject.DocumentaryConditionalStageError):
            self.compose()
        self.assert_no_outputs()
        self.assertTrue((self.workspace / "precedent-corpus.json").exists())

    def test_existing_review_is_preserved(self) -> None:
        old = b'{"nao":"substituir"}'
        (self.workspace / "evidence-review.json").write_bytes(old)
        with self.assertRaises(self.subject.DocumentaryConditionalStageError):
            self.compose()
        self.assertEqual((self.workspace / "evidence-review.json").read_bytes(), old)
        self.assertFalse((self.workspace / "conditional-work-results.json").exists())

    def test_rejects_external_evidence_receipt(self) -> None:
        extra = copy.deepcopy(self.other_results["results"][0])
        extra["track"] = "evidence_analysis"
        self.other_results["results"].append(extra)
        with self.assertRaises(self.subject.DocumentaryConditionalStageError):
            self.compose()
        self.assert_no_outputs()

    def _second_evidence_claim(self) -> None:
        routes = self.load("issue-route.json")
        second = copy.deepcopy(routes["routes"][0])
        second["claim_id"] = "CLM-002"
        second["requires_legal_research"] = False
        second["research_questions"] = []
        second["evidence_questions"] = ["Qual trecho sustenta o segundo pedido sintético?"]
        routes["routes"].append(second)
        self.save("issue-route.json", routes)
        item = copy.deepcopy(self.evidence["evidence_items"][0])
        item["evidence_id"] = "EVD-002"
        item["claim_ids"] = ["CLM-002"]
        item["proposition"] = "Registro relacionado ao segundo pedido sintético."
        self.evidence["evidence_items"].append(item)
        self.save("evidence-matrix.json", self.evidence)

    def test_prepares_separate_protected_packets_for_every_evidence_claim(self) -> None:
        self._second_evidence_claim()
        self.assertIsNotNone(importlib.util.find_spec("prepare_documentary_claim_packets"))
        batch = importlib.import_module("prepare_documentary_claim_packets")

        index = batch.prepare_documentary_claim_packets(self.workspace, self.pdf)

        self.assertEqual([record["claim_id"] for record in index["records"]], [
            "CLM-001", "CLM-002",
        ])
        self.assertEqual([record["evidence_ids"] for record in index["records"]], [
            ["EVD-001"], ["EVD-002"],
        ])
        self.assertEqual(index["source_pdf_sha256"], hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        self.assertEqual(self.load("documentary-packet-index.json"), index)
        for claim_id, own_id, other_id in (
            ("CLM-001", "EVD-001", "EVD-002"),
            ("CLM-002", "EVD-002", "EVD-001"),
        ):
            path = self.workspace / f"{claim_id}-source-evidence-packet.md"
            packet = path.read_text(encoding="utf-8")
            self.assertIn(own_id, packet)
            self.assertNotIn(other_id, packet)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.workspace / "documentary-packet-index.json").stat().st_mode), 0o600)

    def test_bad_second_claim_does_not_publish_any_batch_output(self) -> None:
        self._second_evidence_claim()
        self.evidence["evidence_items"][1]["source_document_id"] = "DOC-999"
        self.save("evidence-matrix.json", self.evidence)
        self.assertIsNotNone(importlib.util.find_spec("prepare_documentary_claim_packets"))
        batch = importlib.import_module("prepare_documentary_claim_packets")

        with self.assertRaises(batch.DocumentaryClaimPacketsError):
            batch.prepare_documentary_claim_packets(self.workspace, self.pdf)

        for name in (
            "documentary-packet-index.json",
            "documentary-pje-pdf-segments.json",
            "CLM-001-source-evidence-packet.md",
            "CLM-002-source-evidence-packet.md",
        ):
            self.assertFalse((self.workspace / name).exists())

    def test_packet_batch_cli_keeps_source_text_out_of_terminal(self) -> None:
        self._second_evidence_claim()
        result = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "prepare_documentary_claim_packets.py"),
                "--workspace", str(self.workspace), "--pdf", str(self.pdf),
            ],
            text=True, capture_output=True, check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.workspace / "documentary-packet-index.json").is_file())
        self.assertEqual(len(self.load("documentary-packet-index.json")["records"]), 2)
        self.assertNotIn("REGISTRO DE JORNADA SINTÉTICO", result.stdout + result.stderr)

    def test_prepared_packets_feed_complete_two_claim_conditional_stage(self) -> None:
        self._second_evidence_claim()
        batch = importlib.import_module("prepare_documentary_claim_packets")
        index = batch.prepare_documentary_claim_packets(self.workspace, self.pdf)
        claims = self.load("claim-matrix.json")
        second_claim = copy.deepcopy(claims["claims"][0])
        second_claim["claim_id"] = "CLM-002"
        claims["claims"].append(second_claim)
        self.save("claim-matrix.json", claims)
        calculations = self.load("calculation-review.json")
        calculations["calculations"].append({
            "claim_id": "CLM-002", "status": "not_required",
            "criteria": [], "unavailability_reason": "",
        })
        self.save("calculation-review.json", calculations)
        for record in index["records"]:
            claim_id = record["claim_id"]
            evidence_id = record["evidence_ids"][0]
            self.save(
                f"{claim_id}-documentary-observations.json",
                {
                    "schema_version": 1,
                    "claim_id": claim_id,
                    "source_packet_sha256": record["source_packet_sha256"],
                    "status": "pending_human_review",
                    "observations": [{
                        "evidence_id": evidence_id,
                        "source_document_id": "DOC-002",
                        "excerpts": [{"pdf_page": 2, "text": "REGISTRO DE JORNADA SINTÉTICO"}],
                        "observation": "A página contém o título citado.",
                        "limitations": ["O conteúdo integral não foi examinado."],
                    }],
                },
            )
        self.assertIsNotNone(importlib.util.find_spec("load_documentary_claim_bundles"))
        loader = importlib.import_module("load_documentary_claim_bundles")
        self.bundles = loader.load_documentary_claim_bundles(self.workspace)

        self.compose()

        self.assertEqual(
            {item["claim_id"] for item in self.load("evidence-review.json")["reviews"]},
            {"CLM-001", "CLM-002"},
        )
        self.assertEqual(
            {item["claim_id"] for item in self.load("documentary-source-register.json")["records"]},
            {"CLM-001", "CLM-002"},
        )

    def test_missing_observation_refuses_entire_prepared_batch(self) -> None:
        self._second_evidence_claim()
        batch = importlib.import_module("prepare_documentary_claim_packets")
        index = batch.prepare_documentary_claim_packets(self.workspace, self.pdf)
        record = index["records"][0]
        self.save("CLM-001-documentary-observations.json", {
            "schema_version": 1,
            "claim_id": "CLM-001",
            "source_packet_sha256": record["source_packet_sha256"],
            "status": "insufficient",
            "observations": [{
                "evidence_id": "EVD-001", "source_document_id": "DOC-002",
                "excerpts": [], "observation": "Trecho não disponível.",
                "limitations": ["Leitura pendente."],
            }],
        })
        self.assertIsNotNone(importlib.util.find_spec("load_documentary_claim_bundles"))
        loader = importlib.import_module("load_documentary_claim_bundles")

        with self.assertRaises(loader.DocumentaryClaimBundlesError):
            loader.load_documentary_claim_bundles(self.workspace)

        self.assert_no_outputs()

    def test_changed_packet_index_refuses_prepared_batch(self) -> None:
        batch = importlib.import_module("prepare_documentary_claim_packets")
        index = batch.prepare_documentary_claim_packets(self.workspace, self.pdf)
        index["records"][0]["packet_name"] = "../pacote-fora-do-caso.md"
        self.save("documentary-packet-index.json", index)
        self.assertIsNotNone(importlib.util.find_spec("load_documentary_claim_bundles"))
        loader = importlib.import_module("load_documentary_claim_bundles")

        with self.assertRaises(loader.DocumentaryClaimBundlesError):
            loader.load_documentary_claim_bundles(self.workspace)

        self.assert_no_outputs()


if __name__ == "__main__":
    unittest.main()
