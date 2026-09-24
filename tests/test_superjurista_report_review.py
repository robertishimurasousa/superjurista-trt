from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "tests/fixtures/contracts/valid/labor-report.json"
MATRIX = ROOT / "tests/fixtures/contracts/valid/claim-matrix.json"
SCRIPT = ROOT / "scripts/validate_superjurista_report.py"
sys.path.insert(0, str(ROOT / "scripts"))
from build_superjurista_triage_input import build_triage_input  # noqa: E402


class SuperjuristaReportReviewTest(unittest.TestCase):
    def material(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        report["positions"][0]["summary"] = matrix["claims"][0]["claimant_position"]["summary"]
        report["positions"][1]["summary"] = matrix["claims"][0]["respondent_positions"][0]["summary"]
        input_text = build_triage_input(report, matrix)
        digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        coverage = {
            "events": [{
                "event_id": "EVT-001",
                "source_document_id": "DOC-001",
                "source_locator": "page 1",
            }],
            "claims": [{
                "claim_id": "CLM-001",
                "source_document_id": "DOC-001",
                "source_locator": "pages 4-5",
            }],
            "defenses": [{
                "defense_id": "DEF-001",
                "claim_id": "CLM-001",
                "respondent_party_id": "PTY-002",
                "source_document_id": "DOC-002",
                "source_locator": "pages 2-3",
            }],
            "unanswered_claim_ids": [],
        }
        return report, matrix, input_text, digest, coverage

    def narrative(self, digest, coverage):
        paragraph = (
            "A parte autora alegou a prestação de horas extras, e a parte reclamada "
            "contestou o pagamento insuficiente. Esta narrativa sintética conserva "
            "a divergência e não decide o mérito do pedido. "
        )
        return (
            "RELATÓRIO\n\n"
            "Processo: 0000000-00.2026.5.12.0000\n"
            f"Insumo SHA-256: {digest}\n\n"
            + paragraph * 4
            + "\n\nREFERÊNCIAS DE COBERTURA\n\n"
            + "```json\n"
            + json.dumps(coverage, ensure_ascii=False, indent=2)
            + "\n```\n\nÉ o que havia de relevante a relatar.\n"
        )

    def run_validator(self, report, matrix, input_text, narrative):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = {
                "report": base / "labor-report.json",
                "matrix": base / "claim-matrix.json",
                "input": base / "triage-input.md",
                "narrative": base / "relatorio-trabalhista.md",
            }
            paths["report"].write_text(json.dumps(report), encoding="utf-8")
            paths["matrix"].write_text(json.dumps(matrix), encoding="utf-8")
            paths["input"].write_text(input_text, encoding="utf-8")
            paths["narrative"].write_text(narrative, encoding="utf-8")
            command = [sys.executable, str(SCRIPT)]
            for name, path in paths.items():
                command.extend([f"--{name}", str(path)])
            return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)

    def test_accepts_complete_source_linked_narrative_without_echoing_case_text(self):
        report, matrix, input_text, digest, coverage = self.material()

        result = self.run_validator(report, matrix, input_text, self.narrative(digest, coverage))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Relatório narrativo validado", result.stdout)
        self.assertNotIn("A parte autora alegou", result.stdout)

    def test_rejects_stale_protected_input(self):
        report, matrix, input_text, digest, coverage = self.material()

        result = self.run_validator(
            report, matrix, input_text + "alterado", self.narrative(digest, coverage)
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("entrada protegida diverge", result.stderr)

    def test_rejects_narrative_with_wrong_input_digest(self):
        report, matrix, input_text, digest, coverage = self.material()
        narrative = self.narrative(digest, coverage).replace(digest, "b" * 64)

        result = self.run_validator(report, matrix, input_text, narrative)

        self.assertEqual(result.returncode, 2)
        self.assertIn("resumo da entrada", result.stderr)

    def test_rejects_narrative_for_another_case(self):
        report, matrix, input_text, digest, coverage = self.material()
        narrative = self.narrative(digest, coverage).replace(
            "Processo: 0000000-00.2026.5.12.0000",
            "Processo: 0000001-00.2026.5.12.0000",
        )

        result = self.run_validator(report, matrix, input_text, narrative)

        self.assertEqual(result.returncode, 2)
        self.assertIn("número do processo", result.stderr)

    def test_reuses_inherited_report_format_gate(self):
        report, matrix, input_text, digest, coverage = self.material()
        narrative = self.narrative(digest, coverage).replace(
            "É o que havia de relevante a relatar.", "Fim do relatório."
        )

        result = self.run_validator(report, matrix, input_text, narrative)

        self.assertEqual(result.returncode, 2)
        self.assertIn("formato herdado", result.stderr)

    def test_requires_coverage_heading_before_json(self):
        report, matrix, input_text, digest, coverage = self.material()
        narrative = self.narrative(digest, coverage).replace(
            "REFERÊNCIAS DE COBERTURA", "BLOCO DE DADOS"
        )

        result = self.run_validator(report, matrix, input_text, narrative)

        self.assertEqual(result.returncode, 2)
        self.assertIn("referências de cobertura", result.stderr)

    def test_requires_exact_opening_and_closing_markers(self):
        report, matrix, input_text, digest, coverage = self.material()
        narrative = self.narrative(digest, coverage)

        for modified in ("Aviso prévio\n" + narrative, narrative + "Nota posterior\n"):
            with self.subTest(modified=modified.startswith("Aviso")):
                result = self.run_validator(report, matrix, input_text, modified)
                self.assertEqual(result.returncode, 2)
                self.assertIn("marcadores exatos", result.stderr)

    def test_rejects_missing_claim_in_coverage_block(self):
        report, matrix, input_text, digest, coverage = self.material()
        coverage["claims"] = []

        result = self.run_validator(report, matrix, input_text, self.narrative(digest, coverage))

        self.assertEqual(result.returncode, 2)
        self.assertIn("cobertura dos pedidos", result.stderr)

    def test_rejects_wrong_defense_source_in_coverage_block(self):
        report, matrix, input_text, digest, coverage = self.material()
        coverage["defenses"][0]["source_locator"] = "page 999"

        result = self.run_validator(report, matrix, input_text, self.narrative(digest, coverage))

        self.assertEqual(result.returncode, 2)
        self.assertIn("cobertura das defesas", result.stderr)

    def test_rejects_omitted_timeline_event_in_coverage_block(self):
        report, matrix, _, _, coverage = self.material()
        report["timeline"].append({
            "event_id": "EVT-002",
            "event_date": "2026-01-20",
            "event_type": "defense_filed",
            "summary": "Contestação sintética apresentada.",
            "source_document_id": "DOC-002",
            "source_locator": "page 1",
        })
        input_text = build_triage_input(report, matrix)
        digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()

        result = self.run_validator(report, matrix, input_text, self.narrative(digest, coverage))

        self.assertEqual(result.returncode, 2)
        self.assertIn("cobertura dos eventos", result.stderr)

    def test_requires_explicit_marking_of_unanswered_claim(self):
        report, matrix, _, _, coverage = self.material()
        position = copy.deepcopy(report["positions"][0])
        position.update({
            "position_id": "POS-003",
            "label": "unmapped_joint_liability",
            "summary": "Pedido sintético de responsabilidade subsidiária.",
            "source_locator": "page 6",
        })
        report["positions"].append(position)
        claim = copy.deepcopy(matrix["claims"][0])
        claim.update({
            "claim_id": "CLM-003",
            "label": position["label"],
            "claimant_position": {
                "summary": position["summary"],
                "source_document_id": position["source_document_id"],
                "source_locator": position["source_locator"],
            },
            "respondent_positions": [],
            "requested_remedies": [],
            "contested_facts": [],
            "legal_issues": [],
            "status": "needs_human_review",
            "review_gaps": ["missing_respondent_position"],
        })
        matrix["claims"].append(claim)
        input_text = build_triage_input(report, matrix)
        digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        coverage["claims"].append({
            "claim_id": "CLM-003",
            "source_document_id": "DOC-001",
            "source_locator": "page 6",
        })

        result = self.run_validator(report, matrix, input_text, self.narrative(digest, coverage))

        self.assertEqual(result.returncode, 2)
        self.assertIn("pedidos sem defesa", result.stderr)


if __name__ == "__main__":
    unittest.main()
