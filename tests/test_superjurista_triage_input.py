from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REPORT = ROOT / "tests/fixtures/contracts/valid/labor-report.json"
MATRIX = ROOT / "tests/fixtures/contracts/valid/claim-matrix.json"


class SuperjuristaTriageInputTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("build_superjurista_triage_input")

    def inputs(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        report["positions"][0]["summary"] = matrix["claims"][0]["claimant_position"]["summary"]
        report["positions"][1]["summary"] = (
            matrix["claims"][0]["respondent_positions"][0]["summary"]
        )
        return report, matrix

    def test_renders_one_source_linked_question_per_claim_without_inventing_a_route(self):
        report, matrix = self.inputs()

        result = self.api().build_triage_input(report, matrix)

        self.assertIn("0000000-00.2026.5.12.0000", result)
        self.assertIn("TRT12 — 1º grau", result)
        self.assertIn("CLM-001 — overtime", result)
        self.assertIn("DOC-001, pages 4-5", result)
        self.assertIn("Overtime was worked and not fully paid.", result)
        self.assertIn("DEF-001 — Synthetic Respondent", result)
        self.assertIn("DOC-002, pages 2-3", result)
        self.assertIn("All recorded overtime was paid.", result)
        self.assertIn("overtime_payment, statutory_effects", result)
        self.assertIn("actual_working_hours", result)
        self.assertIn("reliability_of_time_records", result)
        self.assertNotIn("## ROTA", result)
        self.assertNotIn("procedente", result.lower())

    def test_preserves_unanswered_claim_and_review_gaps(self):
        report, matrix = self.inputs()
        report["positions"].append({
            **report["positions"][0],
            "position_id": "POS-003",
            "label": "unmapped_joint_liability",
            "summary": "Subsidiary liability is requested.",
            "source_locator": "page 6",
        })
        second = copy.deepcopy(matrix["claims"][0])
        second.update({
            "claim_id": "CLM-003",
            "label": "unmapped_joint_liability",
            "claimant_position": {
                "summary": "Subsidiary liability is requested.",
                "source_document_id": "DOC-001",
                "source_locator": "page 6",
            },
            "respondent_positions": [],
            "requested_remedies": [],
            "contested_facts": [],
            "legal_issues": [],
            "status": "needs_human_review",
            "review_gaps": [
                "missing_respondent_position",
                "unsupported_claim_label",
            ],
        })
        matrix["claims"].append(second)

        result = self.api().build_triage_input(report, matrix)

        self.assertIn("CLM-003 — unmapped_joint_liability", result)
        self.assertIn("Sem defesa vinculada; não presumir concordância.", result)
        self.assertIn("missing_respondent_position, unsupported_claim_label", result)
        self.assertIn("DOC-001, page 6", result)

    def test_rejects_claim_or_defense_custody_mismatch(self):
        report, matrix = self.inputs()
        for changed in ("claim", "defense"):
            with self.subTest(changed=changed):
                invalid = copy.deepcopy(matrix)
                position = (
                    invalid["claims"][0]["claimant_position"]
                    if changed == "claim"
                    else invalid["claims"][0]["respondent_positions"][0]
                )
                position["source_locator"] = "page 999"
                with self.assertRaisesRegex(self.api().TriageInputError, "fonte .* diverge"):
                    self.api().build_triage_input(report, invalid)

    def test_rejects_divergent_claim_or_defense_summary(self):
        report, matrix = self.inputs()
        for changed in ("claim", "defense"):
            with self.subTest(changed=changed):
                invalid = copy.deepcopy(matrix)
                position = (
                    invalid["claims"][0]["claimant_position"]
                    if changed == "claim"
                    else invalid["claims"][0]["respondent_positions"][0]
                )
                position["summary"] = "A contradictory summary."
                with self.assertRaisesRegex(self.api().TriageInputError, "resumo .* diverge"):
                    self.api().build_triage_input(report, invalid)

    def test_rejects_missing_or_extra_claim_in_the_report(self):
        report, matrix = self.inputs()
        report["positions"] = [report["positions"][1]]
        with self.assertRaisesRegex(self.api().TriageInputError, "cobertura dos pedidos diverge"):
            self.api().build_triage_input(report, matrix)

    def test_cli_writes_protected_once_and_refuses_repository_output(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report, matrix = self.inputs()
            report_path = base / "labor-report.json"
            matrix_path = base / "claim-matrix.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
            output = base / "triage-input.md"
            command = [
                sys.executable,
                str(SCRIPTS / "build_superjurista_triage_input.py"),
                "--report", str(report_path),
                "--matrix", str(matrix_path),
                "--output", str(output),
            ]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("Entrada de triagem criada", first.stdout)
            self.assertNotIn(str(output), first.stdout)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("Synthetic Claimant", first.stdout)
            self.assertIn(
                hashlib.sha256(output.read_bytes()).hexdigest(), first.stdout
            )

            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertIn("arquivo de saída já existe", second.stderr)

            inside = subprocess.run(
                [*command[:-1], str(ROOT / "triage-input.md")],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(inside.returncode, 2)
            self.assertIn("fora do repositório", inside.stderr)

    def test_refuses_public_destination_before_writing_case_content(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "publico"
            public.mkdir(mode=0o755)
            output = public / "triage-input.md"

            with self.assertRaisesRegex(self.api().TriageInputError, "privado"):
                self.api().write_triage_input("conteúdo processual sintético", output)

            self.assertFalse(output.exists())

    def test_refuses_linked_destination_before_writing_case_content(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "privado"
            private.mkdir(mode=0o700)
            linked = Path(directory) / "atalho"
            linked.symlink_to(private, target_is_directory=True)

            with self.assertRaisesRegex(self.api().TriageInputError, "vínculo simbólico"):
                self.api().write_triage_input("conteúdo processual sintético", linked / "triage-input.md")

            self.assertEqual(list(private.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
