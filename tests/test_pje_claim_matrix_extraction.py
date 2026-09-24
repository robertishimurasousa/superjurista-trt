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
from unittest.mock import patch

from PyPDF2 import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/contracts/valid/labor-report.json"
TAXONOMY = ROOT / "runtime/domain/labor-claim-taxonomy.json"


class PJeClaimMatrixExtractionTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("extract_pje_claim_matrix")

    def inputs(self):
        report = json.loads(FIXTURE.read_text(encoding="utf-8"))
        report["parties"].append({**report["parties"][1], "party_id": "PTY-003"})
        report["positions"] = [
            {**report["positions"][0], "source_locator": "page 4"},
            {
                **report["positions"][0],
                "position_id": "POS-002",
                "label": "unmapped_joint_liability",
                "source_locator": "page 5",
            },
            {
                **report["positions"][1],
                "position_id": "POS-101",
                "source_locator": "page 2",
            },
        ]
        segments = {
            "schema_version": 1,
            "segmentation_method": "pje_pdf_outline",
            "source_pdf": {"sha256": "0" * 64, "page_count": 6},
            "documents": [
                {
                    "document_id": f"DOC-{number:03d}",
                    "provider_reference": f"{number:07x}",
                    "provider_type": "synthetic",
                    "filed_on": "2026-01-01",
                    "page_start": start,
                    "page_end": end,
                }
                for number, start, end in ((1, 4, 5), (2, 1, 3))
            ],
        }
        return report, segments

    def build(self, report, segments, bindings):
        api = self.api()
        return api.extract_claim_matrix(report, segments, api.load_claim_taxonomy(TAXONOMY), bindings)

    def empty_remedy_evidence(self):
        return {
            "schema_version": 2, "source_pdf_sha256": "0" * 64,
            "entries": [], "unmatched_item_ids": [], "unmatched_items": [],
        }

    def test_links_only_explicitly_bound_defense_and_marks_missing_information(self):
        report, segments = self.inputs()
        result = self.build(report, segments, {"DOC-002": "PTY-002"})
        first, second = result["claims"]
        self.assertEqual((first["claim_id"], second["claim_id"]), ("CLM-001", "CLM-002"))
        self.assertEqual(first["respondent_positions"][0]["defense_id"], "DEF-101")
        self.assertEqual(first["respondent_positions"][0]["respondent_party_id"], "PTY-002")
        self.assertEqual(first["review_gaps"], ["missing_requested_remedy"])
        self.assertEqual(second["respondent_positions"], [])
        self.assertEqual(second["review_gaps"], [
            "missing_requested_remedy", "missing_respondent_position", "unsupported_claim_label"
        ])
        self.assertEqual(first["claimant_position"]["source_locator"], "page 4")

    def test_accepts_portuguese_page_locators_without_changing_source_custody(self):
        report, segments = self.inputs()
        report["positions"][0]["source_locator"] = "página 4, título da seção de pedido"
        report["positions"][2]["source_locator"] = "páginas 2-3, título da seção de defesa"

        result = self.build(report, segments, {"DOC-002": "PTY-002"})

        self.assertEqual(
            result["claims"][0]["claimant_position"]["source_locator"],
            "página 4, título da seção de pedido",
        )
        self.assertEqual(
            result["claims"][0]["respondent_positions"][0]["source_locator"],
            "páginas 2-3, título da seção de defesa",
        )

    def test_requires_binding_for_every_defense_document(self):
        report, segments = self.inputs()
        with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "vinculação"):
            self.build(report, segments, {})

    def test_keeps_distinct_defense_documents_and_parties(self):
        report, segments = self.inputs()
        report["positions"].append({
            **report["positions"][2],
            "position_id": "POS-102",
            "source_document_id": "DOC-003",
            "source_locator": "page 6",
        })
        segments["documents"].append({
            **segments["documents"][1],
            "document_id": "DOC-003",
            "provider_reference": "0000003",
            "page_start": 6,
            "page_end": 6,
        })
        result = self.build(report, segments, {"DOC-002": "PTY-002", "DOC-003": "PTY-003"})
        defenses = result["claims"][0]["respondent_positions"]
        self.assertEqual(
            [(item["defense_id"], item["respondent_party_id"]) for item in defenses],
            [("DEF-101", "PTY-002"), ("DEF-102", "PTY-003")],
        )

    def test_pdf_custody_requires_exact_digest_and_case_number(self):
        api = self.api()
        report, segments = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_metadata({"/Title": "0000000-00.2026.5.12.0000"})
            with path.open("wb") as stream:
                writer.write(stream)
            segments["source_pdf"] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "page_count": 1,
            }
            api.verify_pdf_custody(path, segments, report)
            report["case_context"]["case_number"] = "0000001-00.2026.5.12.0000"
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "processo"):
                api.verify_pdf_custody(path, segments, report)
            segments["source_pdf"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "custódia"):
                api.verify_pdf_custody(path, segments, report)

    def test_rejects_nonrespondent_and_unknown_binding(self):
        report, segments = self.inputs()
        for party_id in ("PTY-001", "PTY-999"):
            with self.subTest(party_id=party_id):
                with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "reclamada"):
                    self.build(report, segments, {"DOC-002": party_id})

    def test_rejects_ambiguous_and_orphan_defense_labels(self):
        report, segments = self.inputs()
        ambiguous = copy.deepcopy(report)
        ambiguous["positions"][1]["label"] = "overtime"
        with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "ambíguo"):
            self.build(ambiguous, segments, {"DOC-002": "PTY-002"})
        orphan = copy.deepcopy(report)
        orphan["positions"][2]["label"] = "moral_damages"
        with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "sem pedido"):
            self.build(orphan, segments, {"DOC-002": "PTY-002"})

    def test_rejects_position_outside_document_pages(self):
        report, segments = self.inputs()
        report["positions"][2]["source_locator"] = "page 6"
        with self.assertRaisesRegex(self.api().PJeClaimMatrixExtractionError, "fora"):
            self.build(report, segments, {"DOC-002": "PTY-002"})

    def test_protected_writer_is_exclusive_and_outside_repository(self):
        api = self.api()
        report, segments = self.inputs()
        matrix = self.build(report, segments, {"DOC-002": "PTY-002"})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = api.write_claim_matrix_artifact(matrix, output_dir=output, repository_root=ROOT)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), matrix)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "já existe"):
                api.write_claim_matrix_artifact(matrix, output_dir=output, repository_root=ROOT)
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "fora do repositório"):
                api.write_claim_matrix_artifact(matrix, output_dir=ROOT, repository_root=ROOT)

    def test_applies_source_backed_remedy_codes_without_suppressing_taxonomy_gaps(self):
        api = self.api()
        report, segments = self.inputs()
        remedies = {
            "CLM-001": ("overtime_payment",),
            "CLM-002": ("joint_or_subsidiary_liability",),
        }
        matrix = api.extract_claim_matrix(
            report, segments, api.load_claim_taxonomy(TAXONOMY),
            {"DOC-002": "PTY-002"}, remedies,
        )
        self.assertEqual(matrix["claims"][0]["requested_remedies"], ["overtime_payment"])
        self.assertEqual(matrix["claims"][0]["review_gaps"], [])
        self.assertEqual(matrix["claims"][1]["review_gaps"], [
            "missing_respondent_position", "unsupported_claim_label"
        ])
        with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "pedido desconhecido"):
            api.extract_claim_matrix(
                report, segments, api.load_claim_taxonomy(TAXONOMY),
                {"DOC-002": "PTY-002"}, {"CLM-999": ("compensation",)},
            )

    def test_remedy_evidence_preserves_unmatched_text_and_page_in_version_two(self):
        api = self.api()
        report, segments = self.inputs()
        report["positions"] = [report["positions"][0]]
        report["positions"][0]["label"] = "unmapped_legal_aid"
        class SyntheticPage:
            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        pages = [SyntheticPage("Fls.: 5") for _ in range(6)]
        pages[3] = SyntheticPage(
            "DOS PEDIDOS\nA. Gratuidade de justiça\n"
            "I. Seja citada a reclamada para defesa"
        )
        reader = type("Reader", (), {"pages": pages})()

        with patch.object(api, "verify_pdf_custody"), patch.object(api, "PdfReader", return_value=reader):
            evidence = api.extract_pdf_remedy_evidence(Path("synthetic.pdf"), segments, report)

        self.assertEqual(evidence["schema_version"], 2)
        self.assertEqual(evidence["unmatched_items"], [{
            "request_id": "I",
            "source_document_id": "DOC-001",
            "source_locator": "página 4, pedido I",
            "text": "Seja citada a reclamada para defesa",
        }])

    def test_remedy_evidence_writer_is_protected_and_exclusive(self):
        api = self.api()
        evidence = self.empty_remedy_evidence()
        with tempfile.TemporaryDirectory() as directory:
            path = api.write_remedy_evidence_artifact(
                evidence, output_dir=Path(directory), repository_root=ROOT
            )
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), evidence)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "já existe"):
                api.write_remedy_evidence_artifact(
                    evidence, output_dir=Path(directory), repository_root=ROOT
                )

    def test_remedy_evidence_writer_refuses_old_version_without_publication(self):
        api = self.api()
        evidence = {
            "schema_version": 1, "source_pdf_sha256": "0" * 64,
            "entries": [], "unmatched_item_ids": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "evidência"):
                api.write_remedy_evidence_artifact(
                    evidence, output_dir=output, repository_root=ROOT
                )
            self.assertEqual(list(output.iterdir()), [])

    def test_bundle_refuses_unmatched_id_divergence_before_writing_matrix(self):
        api = self.api()
        report, segments = self.inputs()
        matrix = self.build(report, segments, {"DOC-002": "PTY-002"})
        evidence = {
            "schema_version": 2, "source_pdf_sha256": "0" * 64,
            "entries": [], "unmatched_item_ids": ["I"],
            "unmatched_items": [{
                "request_id": "J", "source_document_id": "DOC-001",
                "source_locator": "página 4, pedido J", "text": "Item sintético",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "evidência"):
                api.write_claim_matrix_with_evidence(
                    matrix, evidence, output_dir=output, repository_root=ROOT
                )
            self.assertEqual(list(output.iterdir()), [])

    def test_bundle_refuses_existing_matrix_before_writing_evidence(self):
        api = self.api()
        report, segments = self.inputs()
        matrix = self.build(report, segments, {"DOC-002": "PTY-002"})
        evidence = self.empty_remedy_evidence()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            api.write_claim_matrix_artifact(matrix, output_dir=output, repository_root=ROOT)
            with self.assertRaisesRegex(api.PJeClaimMatrixExtractionError, "já existe"):
                api.write_claim_matrix_with_evidence(
                    matrix, evidence, output_dir=output, repository_root=ROOT
                )
            self.assertFalse((output / "requested-remedy-evidence.json").exists())

    def test_second_output_collision_does_not_leave_partial_bundle(self):
        api = self.api()
        report, segments = self.inputs()
        matrix = self.build(report, segments, {"DOC-002": "PTY-002"})
        evidence = self.empty_remedy_evidence()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            dangling_link = output / "claim-matrix.json"
            dangling_link.symlink_to(output / "missing-target.json")

            with self.assertRaises(FileExistsError):
                api.write_claim_matrix_with_evidence(
                    matrix, evidence, output_dir=output, repository_root=ROOT
                )

            self.assertFalse((output / "requested-remedy-evidence.json").exists())
            self.assertTrue(dangling_link.is_symlink())

    def test_second_output_serialization_error_does_not_leave_partial_bundle(self):
        api = self.api()
        evidence = self.empty_remedy_evidence()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            with self.assertRaises(TypeError):
                api.write_claim_matrix_with_evidence(
                    {"invalid": {1, 2}}, evidence, output_dir=output, repository_root=ROOT
                )

            self.assertFalse((output / "requested-remedy-evidence.json").exists())
            self.assertFalse((output / "claim-matrix.json").exists())

    def test_missing_pdf_error_is_in_portuguese_without_exposing_path(self):
        api = self.api()
        report, segments = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            missing_pdf = Path(directory) / "private-case.pdf"
            with self.assertRaises(api.PJeClaimMatrixExtractionError) as caught:
                api.verify_pdf_custody(missing_pdf, segments, report)
            self.assertIn("PDF de origem não encontrado", str(caught.exception))
            self.assertNotIn(str(missing_pdf), str(caught.exception))

    def test_cli_help_and_success_summary_are_in_portuguese(self):
        command = [sys.executable, str(SCRIPTS / "extract_pje_claim_matrix.py")]
        help_result = subprocess.run(command + ["--help"], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("matriz protegida de pedidos", help_result.stdout)

        report, segments = self.inputs()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            pdf_path = temporary / "synthetic.pdf"
            writer = PdfWriter()
            for _ in range(6):
                writer.add_blank_page(width=72, height=72)
            writer.add_metadata({"/Title": report["case_context"]["case_number"]})
            with pdf_path.open("wb") as stream:
                writer.write(stream)
            segments["source_pdf"]["sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            report_path = temporary / "labor-report.json"
            segments_path = temporary / "document-segments.json"
            output = temporary / "protected-output"
            output.mkdir()
            report_path.write_text(json.dumps(report), encoding="utf-8")
            segments_path.write_text(json.dumps(segments), encoding="utf-8")

            completed = subprocess.run(
                command + [
                    "--input", str(pdf_path),
                    "--report", str(report_path),
                    "--segments", str(segments_path),
                    "--output", str(output),
                    "--defense-party", "DOC-002=PTY-002",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                completed.stdout.strip(),
                "[OK] Matriz de pedidos do PJe: pedidos=2 defesas=1 providências=0 lacunas=4",
            )
            self.assertTrue((output / "claim-matrix.json").is_file())

    def test_cli_binding_error_is_in_portuguese(self):
        completed = subprocess.run(
            [
                sys.executable, str(SCRIPTS / "extract_pje_claim_matrix.py"),
                "--input", "unused.pdf",
                "--report", "unused-report.json",
                "--segments", "unused-segments.json",
                "--output", "unused-output",
                "--defense-party", "invalid",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn(
            "[ERRO] Matriz de pedidos do PJe: vinculação inválida ou duplicada",
            completed.stderr,
        )
