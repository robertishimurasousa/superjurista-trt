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
MATRIX = ROOT / "tests/fixtures/contracts/valid/claim-matrix.json"
REPORT = ROOT / "tests/fixtures/contracts/valid/labor-report.json"
INPUT_DIGEST = "a" * 64


class SuperjuristaTriageRoutesTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("import_superjurista_triage")

    def matrix(self):
        value = json.loads(MATRIX.read_text(encoding="utf-8"))
        second = copy.deepcopy(value["claims"][0])
        second["claim_id"] = "CLM-002"
        second["label"] = "moral_damages"
        second["claimant_position"]["summary"] = "Synthetic moral damages claim."
        second["respondent_positions"] = []
        second["requested_remedies"] = []
        second["contested_facts"] = []
        second["legal_issues"] = []
        second["status"] = "needs_human_review"
        second["review_gaps"] = ["missing_respondent_position"]
        value["claims"].append(second)
        return value

    def payload(self):
        return {
            "rota": ["pesquisa", "probatica"],
            "temas_pesquisa": ["Which rule governs the synthetic overtime claim?"],
            "fatos_probatorios": ["Which evidence addresses the synthetic harm?"],
            "justificativa_rotina": None,
            "rotas_por_pedido": [
                {
                    "claim_id": "CLM-001",
                    "requires_legal_research": True,
                    "requires_evidence_analysis": False,
                    "requires_calculation_review": False,
                    "requires_procedural_review": False,
                    "research_questions": ["Which rule governs the synthetic overtime claim?"],
                    "evidence_questions": [],
                    "route_reason": "The legal rule requires research.",
                    "abstention_reasons": [],
                },
                {
                    "claim_id": "CLM-002",
                    "requires_legal_research": False,
                    "requires_evidence_analysis": True,
                    "requires_calculation_review": False,
                    "requires_procedural_review": False,
                    "research_questions": [],
                    "evidence_questions": ["Which evidence addresses the synthetic harm?"],
                    "route_reason": "The alleged harm requires evidence review.",
                    "abstention_reasons": [],
                },
            ],
        }

    def triage(self, payload):
        return (
            "# Triagem Cognitiva do Processo\n\n"
            "**Processo**: 0000000-00.2026.5.12.0000\n"
            "**Data**: 23/09/2026\n"
            "**Insumo**: triage-input.md\n"
            f"**Insumo SHA-256**: {INPUT_DIGEST}\n\n"
            "## QUESTÕES IDENTIFICADAS\n\n"
            "Dois pedidos sintéticos são examinados separadamente, com razões e fontes "
            "registradas no relatório de entrada. Nenhuma conclusão de mérito é produzida.\n\n"
            "## EVIDÊNCIAS\n\n"
            "As fontes jurídicas externas não foram consultadas nesta triagem sintética. "
            "A pesquisa e a análise probatória são encaminhadas aos trilhos correspondentes.\n\n"
            "## ROTA\n\n"
            f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```\n\n"
            "Triagem concluída.\n"
        )

    def test_preserves_legacy_route_and_builds_one_route_per_claim(self):
        result = self.api().import_triage(
            self.triage(self.payload()), self.matrix(), {"fontes": []},
            input_digest=INPUT_DIGEST,
        )

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual([item["claim_id"] for item in result["routes"]],
                         ["CLM-001", "CLM-002"])
        self.assertTrue(result["routes"][0]["requires_legal_research"])
        self.assertFalse(result["routes"][0]["requires_evidence_analysis"])
        self.assertTrue(result["routes"][1]["requires_evidence_analysis"])
        self.assertEqual(result["routes"][1]["route_status"], "routed")

    def test_rejects_route_import_without_bound_input_digest(self):
        with self.assertRaisesRegex(self.api().TriageImportError, "resumo validado da entrada"):
            self.api().import_triage(
                self.triage(self.payload()), self.matrix(), {"fontes": []}
            )

    def test_rejects_claim_omission_and_unknown_claim(self):
        for change in ("missing", "unknown"):
            with self.subTest(change=change):
                payload = self.payload()
                if change == "missing":
                    payload["rotas_por_pedido"].pop()
                else:
                    payload["rotas_por_pedido"][1]["claim_id"] = "CLM-999"
                with self.assertRaisesRegex(self.api().TriageImportError, "rotas dos pedidos inválidas"):
                    self.api().import_triage(self.triage(payload), self.matrix(), {"fontes": []}, input_digest=INPUT_DIGEST)

    def test_rejects_disagreement_with_legacy_global_route(self):
        payload = self.payload()
        payload["rota"] = ["pesquisa"]
        with self.assertRaisesRegex(self.api().TriageImportError, "rota global diverge"):
            self.api().import_triage(self.triage(payload), self.matrix(), {"fontes": []}, input_digest=INPUT_DIGEST)

    def test_rejects_question_lost_from_the_global_legacy_route(self):
        payload = self.payload()
        payload["temas_pesquisa"] = ["An unrelated question."]
        with self.assertRaisesRegex(self.api().TriageImportError, "perguntas globais divergem"):
            self.api().import_triage(self.triage(payload), self.matrix(), {"fontes": []}, input_digest=INPUT_DIGEST)

    def test_rejects_unverified_direct_route_and_unsupported_tracks(self):
        payload = self.payload()
        payload["rota"] = []
        payload["justificativa_rotina"] = "Synthetic case seems routine."
        with self.assertRaisesRegex(self.api().TriageImportError, "rota direta exige"):
            self.api().import_triage(self.triage(payload), self.matrix(), {"fontes": []}, input_digest=INPUT_DIGEST)

        payload = self.payload()
        payload["rotas_por_pedido"][0]["requires_calculation_review"] = True
        with self.assertRaisesRegex(self.api().TriageImportError, "trilha não suportada"):
            self.api().import_triage(self.triage(payload), self.matrix(), {"fontes": []}, input_digest=INPUT_DIGEST)

    def test_reuses_legacy_format_gate_and_checks_case_number(self):
        text = self.triage(self.payload())
        with self.assertRaisesRegex(self.api().TriageImportError, "formato da triagem"):
            self.api().import_triage(text.replace("Triagem concluída.", "Incomplete."),
                                     self.matrix(), {"fontes": []}, input_digest=INPUT_DIGEST)
        with self.assertRaisesRegex(self.api().TriageImportError, "número do processo"):
            self.api().import_triage(text.replace("0000000-00.2026", "0000001-00.2026"),
                                     self.matrix(), {"fontes": []},
                                     case_number="0000000-00.2026.5.12.0000",
                                     input_digest=INPUT_DIGEST)

    def test_writes_route_outside_repository_without_overwrite(self):
        value = self.api().import_triage(
            self.triage(self.payload()), self.matrix(), {"fontes": []},
            input_digest=INPUT_DIGEST,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "issue-route.json"
            self.api().write_issue_route(value, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), value)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(self.api().TriageImportError, "arquivo de saída já existe"):
                self.api().write_issue_route(value, path)
            with self.assertRaisesRegex(self.api().TriageImportError, "fora do repositório"):
                self.api().write_issue_route(value, ROOT / "issue-route.json")

    def test_rejects_federal_research_source_in_trt12_handoff(self):
        sources = {"fontes": [{"origem_mcp": "julia-trf5"}]}
        with self.assertRaisesRegex(self.api().TriageImportError, "fontes do TRT12"):
            self.api().import_triage(
                self.triage(self.payload()), self.matrix(), sources,
                input_digest=INPUT_DIGEST,
            )

    def test_cli_accepts_only_the_exact_handoff_input(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        report["positions"][0]["summary"] = matrix["claims"][0]["claimant_position"]["summary"]
        report["positions"][1]["summary"] = matrix["claims"][0]["respondent_positions"][0]["summary"]
        payload = self.payload()
        payload["rota"] = ["pesquisa"]
        payload["fatos_probatorios"] = []
        payload["rotas_por_pedido"] = [payload["rotas_por_pedido"][0]]
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        builder = importlib.import_module("build_superjurista_triage_input")
        input_text = builder.build_triage_input(report, matrix)
        input_digest = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        triage = self.triage(payload).replace(INPUT_DIGEST, input_digest)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = {
                "report": base / "labor-report.json",
                "matrix": base / "claim-matrix.json",
                "input": base / "triage-input.md",
                "triage": base / "0000000-00.2026.5.12.0000-triagem.md",
                "sources": base / "fontes-triagem.json",
                "output": base / "issue-route.json",
            }
            paths["report"].write_text(json.dumps(report), encoding="utf-8")
            paths["matrix"].write_text(json.dumps(matrix), encoding="utf-8")
            paths["input"].write_text(input_text, encoding="utf-8")
            paths["triage"].write_text(triage, encoding="utf-8")
            paths["sources"].write_text('{"fontes": []}', encoding="utf-8")
            command = [sys.executable, str(SCRIPTS / "import_superjurista_triage.py")]
            for name, path in paths.items():
                command.extend([f"--{name}", str(path)])

            accepted = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertIn("Rotas de triagem criadas", accepted.stdout)
            self.assertTrue(paths["output"].is_file())

            paths["output"].unlink()
            paths["input"].write_text(input_text + "changed", encoding="utf-8")
            rejected = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("entrada protegida diverge", rejected.stderr)
            self.assertFalse(paths["output"].exists())

            paths["input"].write_text(input_text, encoding="utf-8")
            paths["triage"].write_text(
                triage.replace(input_digest, "b" * 64), encoding="utf-8"
            )
            rejected = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("resumo da entrada", rejected.stderr)
            self.assertFalse(paths["output"].exists())


if __name__ == "__main__":
    unittest.main()
