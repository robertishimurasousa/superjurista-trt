from __future__ import annotations

import importlib
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfWriter
from PyPDF2._page import PageObject
from PyPDF2.generic import DecodedStreamObject, DictionaryObject, NameObject


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LABOR_REPORT_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "labor-report.v1.schema.json"
)
SEGMENT_SCHEMA = ROOT / "runtime" / "providers" / "pje-pdf-segments.v1.schema.json"
CLASSIFICATION_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "document-classification.v1.schema.json"
)
TIMELINE_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "procedural-timeline.v1.schema.json"
)


class PJeLaborReportExtractionTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("extract_pje_labor_report")
        except ModuleNotFoundError as error:
            self.fail(f"PJe labor report extractor module is missing: {error}")

    def context_arguments(self):
        return {
            "title": (
                "PROCESSO: 0000001-23.2026.5.99.0042 - "
                "AÇÃO TRABALHISTA - RITO SUMARÍSSIMO"
            ),
            "subject": "RECLAMANTE: ANA EXEMPLO; RECLAMADO: EMPRESA ALFA LTDA - EPP",
            "initial_page_text": (
                "AO JUÍZO DA VARA DO TRABALHO DE CIDADE/XX\n"
                "ANA EXEMPLO, brasileira, vem propor RECLAMAÇÃO TRABALHISTA. "
                "Pelo rito sumaríssimo, em face de EMPRESA ALFA LTDA, "
                "Pessoa Jurídica de Direito Privado, e EMPRESA BETA LTDA, "
                "Pessoa Jurídica de Direito Privado, pelas razões a seguir."
            ),
            "court_page_text": "AO JUÍZO DA 3ª VARA DO TRABALHO DE CIDADE-XX.",
            "initial_document_id": "DOC-001",
            "initial_page": 1,
            "phase_document_id": "DOC-003",
            "phase_page": 20,
            "tribunal": "TRT99",
            "instance": 1,
            "confidentiality": "public_or_authorized",
            "source_manifest": "document-segments.json",
        }

    def timeline(self):
        return {
            "schema_version": 1,
            "status": "complete",
            "events": [
                {
                    "event_id": "EVT-002",
                    "event_date": "2026-02-03",
                    "event_type": "defense_filed",
                    "summary": "Defense filed.",
                    "source_document_id": "DOC-002",
                    "source_locator": "pages 3-4",
                },
                {
                    "event_id": "EVT-001",
                    "event_date": "2026-02-01",
                    "event_type": "case_filed",
                    "summary": "Initial pleading filed.",
                    "source_document_id": "DOC-001",
                    "source_locator": "pages 1-2",
                },
            ],
            "gaps": [],
        }

    def segments(self):
        return {
            "schema_version": 1,
            "segmentation_method": "pje_pdf_outline",
            "source_pdf": {"sha256": "a" * 64, "page_count": 30},
            "documents": [
                {
                    "document_id": "DOC-001",
                    "provider_reference": "abc1234",
                    "provider_type": "Initial",
                    "filed_on": "2026-02-01",
                    "page_start": 1,
                    "page_end": 10,
                },
                {
                    "document_id": "DOC-002",
                    "provider_reference": "def5678",
                    "provider_type": "Hearing",
                    "filed_on": "2026-02-02",
                    "page_start": 11,
                    "page_end": 12,
                },
                {
                    "document_id": "DOC-003",
                    "provider_reference": "123abcd",
                    "provider_type": "Defense",
                    "filed_on": "2026-02-03",
                    "page_start": 13,
                    "page_end": 30,
                },
            ],
        }

    def classification(self):
        return {
            "schema_version": 1,
            "classifier_version": 1,
            "documents": [
                {
                    "document_id": "DOC-003",
                    "document_type": "defense",
                    "classification_status": "classified",
                    "matched_rule_ids": ["defense"],
                    "reason_code": "matched_rule",
                },
                {
                    "document_id": "DOC-001",
                    "document_type": "initial_pleading",
                    "classification_status": "classified",
                    "matched_rule_ids": ["initial"],
                    "reason_code": "matched_rule",
                },
                {
                    "document_id": "DOC-002",
                    "document_type": "hearing_record",
                    "classification_status": "classified",
                    "matched_rule_ids": ["hearing"],
                    "reason_code": "matched_rule",
                },
            ],
        }

    def synthetic_pdf(
        self,
        destination: Path,
        claim_heading=None,
        defense_heading=None,
    ) -> None:
        writer = PdfWriter()
        texts = (
            "ANA EXEMPLO vem propor reclamacao em face de EMPRESA ALFA LTDA, "
            "Pessoa Juridica de Direito Privado, e EMPRESA BETA LTDA, "
            "Pessoa Juridica de Direito Privado.",
            "ATA DE AUDIENCIA referente a acao trabalhista.",
            "AO JUIZO DA VARA DO TRABALHO DE CIDADE-XX.",
        )
        for index, text in enumerate(texts):
            page = PageObject.create_blank_page(width=612, height=792)
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                    NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): font}
                    )
                }
            )
            stream = DecodedStreamObject()
            commands = [f"BT\n/F1 10 Tf\n30 720 Td\n({text}) Tj"]
            if index == 0 and claim_heading is not None:
                commands.append(f"0 -20 Td\n({claim_heading}) Tj")
            if index == 2 and defense_heading is not None:
                commands.append(f"0 -20 Td\n({defense_heading}) Tj")
            commands.append("ET\n")
            stream.set_data("\n".join(commands).encode("ascii"))
            page[NameObject("/Contents")] = stream
            writer.add_page(page)
        writer.add_metadata(
            {
                "/Title": (
                    "PROCESSO: 0000001-23.2026.5.99.0042 - "
                    "ACAO TRABALHISTA - RITO SUMARISSIMO"
                ),
                "/Subject": (
                    "RECLAMANTE: ANA EXEMPLO; "
                    "RECLAMADO: EMPRESA ALFA LTDA - EPP"
                ),
            }
        )
        with destination.open("wb") as stream:
            writer.write(stream)

    def test_extracts_portable_context_parties_and_phase_with_source_custody(self) -> None:
        api = self.api()

        result = api.extract_context_candidates(**self.context_arguments())

        self.assertEqual(
            result.case_context,
            {
                "schema_version": 1,
                "case_number": "0000001-23.2026.5.99.0042",
                "court": "TRT99",
                "instance": 1,
                "phase": "knowledge",
                "procedure": "summary",
                "court_unit": "3ª VARA DO TRABALHO DE CIDADE-XX",
                "confidentiality": "public_or_authorized",
                "source_manifest": "document-segments.json",
            },
        )
        self.assertEqual(
            [(party.party_id, party.role, party.display_name) for party in result.parties],
            [
                ("PTY-001", "claimant", "ANA EXEMPLO"),
                ("PTY-002", "respondent", "EMPRESA ALFA LTDA"),
                ("PTY-003", "respondent", "EMPRESA BETA LTDA"),
            ],
        )
        self.assertTrue(
            all(party.source.document_id == "DOC-001" for party in result.parties)
        )
        self.assertTrue(
            all(
                party.source.locator == "page 1, party qualification"
                for party in result.parties
            )
        )
        self.assertEqual(result.phase.phase, "knowledge")
        self.assertEqual(result.phase.status, "identified")
        self.assertEqual(result.phase.source.document_id, "DOC-003")
        self.assertEqual(result.phase.source.locator, "page 20, procedural document")

    def test_rejects_tribunal_mismatch_or_missing_primary_respondent(self) -> None:
        api = self.api()
        arguments = {
            "title": (
                "PROCESSO: 0000001-23.2026.5.99.0042 - "
                "AÇÃO TRABALHISTA - RITO SUMARÍSSIMO"
            ),
            "subject": "RECLAMANTE: ANA EXEMPLO; RECLAMADO: EMPRESA ALFA LTDA",
            "initial_page_text": (
                "ANA EXEMPLO propõe reclamação em face de EMPRESA BETA LTDA, "
                "Pessoa Jurídica de Direito Privado."
            ),
            "court_page_text": "AO JUÍZO DA 3ª VARA DO TRABALHO DE CIDADE-XX.",
            "initial_document_id": "DOC-001",
            "initial_page": 1,
            "phase_document_id": "DOC-003",
            "phase_page": 20,
            "tribunal": "TRT99",
            "instance": 1,
            "confidentiality": "public_or_authorized",
            "source_manifest": "document-segments.json",
        }

        with self.assertRaisesRegex(api.PJeLaborReportExtractionError, "primary respondent"):
            api.extract_context_candidates(**arguments)

        arguments["initial_page_text"] = (
            "ANA EXEMPLO propõe reclamação em face de EMPRESA ALFA LTDA, "
            "Pessoa Jurídica de Direito Privado."
        )
        arguments["tribunal"] = "TRT12"
        with self.assertRaisesRegex(api.PJeLaborReportExtractionError, "tribunal"):
            api.extract_context_candidates(**arguments)

    def test_converts_every_procedural_event_into_report_candidates(self) -> None:
        api = self.api()
        result = api.timeline_candidates(self.timeline())

        self.assertEqual([item.event_id for item in result], ["EVT-001", "EVT-002"])
        self.assertEqual(result[1].source.document_id, "DOC-002")
        self.assertEqual(result[1].source.locator, "pages 3-4")

    def test_builds_partial_report_with_only_position_gaps(self) -> None:
        api = self.api()
        context = api.extract_context_candidates(**self.context_arguments())

        result = api.build_partial_labor_report(
            context,
            known_document_ids=("DOC-001", "DOC-002", "DOC-003"),
            timeline=self.timeline(),
            schema_path=LABOR_REPORT_SCHEMA,
        )

        self.assertEqual(len(result["parties"]), 3)
        self.assertEqual(len(result["timeline"]), 2)
        self.assertEqual(result["positions"], [])
        self.assertEqual(
            result["review_gaps"],
            ["missing_claim_position", "missing_defense_position"],
        )

    def test_writes_protected_report_only_outside_repository(self) -> None:
        api = self.api()
        context = api.extract_context_candidates(**self.context_arguments())
        report = api.build_partial_labor_report(
            context,
            known_document_ids=("DOC-001", "DOC-002", "DOC-003"),
            timeline=self.timeline(),
            schema_path=LABOR_REPORT_SCHEMA,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            output = root / "protected-output"
            output.mkdir()

            written = api.write_labor_report_artifact(
                report,
                output_dir=output,
                repository_root=repository,
            )

            self.assertEqual(written.name, "labor-report.json")
            self.assertEqual(written.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(written.read_text()), report)
            with self.assertRaisesRegex(api.PJeLaborReportExtractionError, "already exists"):
                api.write_labor_report_artifact(
                    report,
                    output_dir=output,
                    repository_root=repository,
                )

            repository_output = repository / "output"
            repository_output.mkdir()
            with self.assertRaisesRegex(
                api.PJeLaborReportExtractionError,
                "outside repository",
            ):
                api.write_labor_report_artifact(
                    report,
                    output_dir=repository_output,
                    repository_root=repository,
                )

    def test_selects_initial_defense_and_hearing_sources_by_document_type(self) -> None:
        api = self.api()

        result = api.select_source_documents(self.segments(), self.classification())

        self.assertEqual(result.initial["document_id"], "DOC-001")
        self.assertEqual(result.court["document_id"], "DOC-003")
        self.assertEqual(result.phase["document_id"], "DOC-002")
        self.assertEqual(
            [
                document["document_id"]
                for document in getattr(result, "defenses", ())
            ],
            ["DOC-003"],
        )

    def test_selects_every_defense_document_in_stable_order(self) -> None:
        api = self.api()
        segments = self.segments()
        segments["documents"].append(
            {
                "document_id": "DOC-004",
                "provider_reference": "456def0",
                "provider_type": "Defense",
                "filed_on": "2026-02-04",
                "page_start": 31,
                "page_end": 32,
            }
        )
        classification = self.classification()
        classification["documents"].append(
            {
                "document_id": "DOC-004",
                "document_type": "defense",
                "classification_status": "classified",
                "matched_rule_ids": ["defense"],
                "reason_code": "matched_rule",
            }
        )

        result = api.select_source_documents(segments, classification)

        self.assertEqual(
            [
                document["document_id"]
                for document in getattr(result, "defenses", ())
            ],
            ["DOC-003", "DOC-004"],
        )

    def test_source_selection_rejects_duplicate_or_mismatched_document_custody(self) -> None:
        api = self.api()
        duplicate = self.classification()
        duplicate["documents"].append(dict(duplicate["documents"][1]))
        missing = self.classification()
        missing["documents"] = missing["documents"][:-1]

        for classification in (duplicate, missing):
            with self.subTest(classification=classification):
                with self.assertRaises(api.PJeLaborReportExtractionError):
                    api.select_source_documents(self.segments(), classification)

    def test_extracts_schema_valid_partial_report_from_a_custodied_pdf(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "synthetic-process.pdf"
            self.synthetic_pdf(pdf_path)
            segments = self.segments()
            segments["source_pdf"] = {
                "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "page_count": 3,
            }
            for index, document in enumerate(segments["documents"], 1):
                document["page_start"] = index
                document["page_end"] = index
            timeline = self.timeline()
            timeline["status"] = "complete"
            timeline["gaps"] = []

            result = api.extract_pdf_labor_report(
                pdf_path,
                segments,
                self.classification(),
                timeline,
                tribunal="TRT99",
                instance=1,
                confidentiality="public_or_authorized",
                source_manifest="document-segments.json",
                segment_schema_path=SEGMENT_SCHEMA,
                classification_schema_path=CLASSIFICATION_SCHEMA,
                timeline_schema_path=TIMELINE_SCHEMA,
                labor_report_schema_path=LABOR_REPORT_SCHEMA,
            )

        self.assertEqual(len(result["parties"]), 3)
        self.assertEqual(result["case_context"]["court"], "TRT99")
        self.assertEqual(result["case_context"]["instance"], 1)
        self.assertEqual(result["procedural_phase"]["source_document_id"], "DOC-002")
        self.assertEqual(
            result["review_gaps"],
            ["missing_claim_position", "missing_defense_position"],
        )

    def test_extracts_claim_positions_from_the_complete_initial_document(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "synthetic-process.pdf"
            self.synthetic_pdf(
                pdf_path,
                claim_heading="5. DO INTERVALO INTRAJORNADA",
            )
            segments = self.segments()
            segments["source_pdf"] = {
                "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "page_count": 3,
            }
            for index, document in enumerate(segments["documents"], 1):
                document["page_start"] = index
                document["page_end"] = index
            timeline = self.timeline()
            timeline["status"] = "complete"
            timeline["gaps"] = []

            result = api.extract_pdf_labor_report(
                pdf_path,
                segments,
                self.classification(),
                timeline,
                tribunal="TRT99",
                instance=1,
                confidentiality="public_or_authorized",
                source_manifest="document-segments.json",
                segment_schema_path=SEGMENT_SCHEMA,
                classification_schema_path=CLASSIFICATION_SCHEMA,
                timeline_schema_path=TIMELINE_SCHEMA,
                labor_report_schema_path=LABOR_REPORT_SCHEMA,
            )

        self.assertEqual(
            result["positions"],
            [
                {
                    "position_id": "POS-004",
                    "kind": "claim",
                    "label": "meal_rest_interval",
                    "summary": (
                        "Claimant requests payment for an allegedly suppressed meal interval."
                    ),
                    "source_document_id": "DOC-001",
                    "source_locator": "page 1, claim section heading",
                }
            ],
        )
        self.assertEqual(result["review_gaps"], ["missing_defense_position"])

    def test_combines_claim_and_defense_positions_from_classified_documents(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "synthetic-process.pdf"
            self.synthetic_pdf(
                pdf_path,
                claim_heading="5. DO INTERVALO INTRAJORNADA",
                defense_heading="3 - DAS VERBAS RESCISORIAS",
            )
            segments = self.segments()
            segments["source_pdf"] = {
                "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "page_count": 3,
            }
            for index, document in enumerate(segments["documents"], 1):
                document["page_start"] = index
                document["page_end"] = index
            timeline = self.timeline()
            timeline["status"] = "complete"
            timeline["gaps"] = []

            result = api.extract_pdf_labor_report(
                pdf_path,
                segments,
                self.classification(),
                timeline,
                tribunal="TRT99",
                instance=1,
                confidentiality="public_or_authorized",
                source_manifest="document-segments.json",
                segment_schema_path=SEGMENT_SCHEMA,
                classification_schema_path=CLASSIFICATION_SCHEMA,
                timeline_schema_path=TIMELINE_SCHEMA,
                labor_report_schema_path=LABOR_REPORT_SCHEMA,
            )

        self.assertEqual(
            [(item["position_id"], item["kind"]) for item in result["positions"]],
            [("POS-004", "claim"), ("POS-101", "defense")],
        )
        self.assertEqual(result["review_gaps"], [])

    def test_rejects_pdf_that_does_not_match_segment_custody(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "synthetic-process.pdf"
            self.synthetic_pdf(pdf_path)
            timeline = self.timeline()
            timeline["status"] = "complete"
            timeline["gaps"] = []

            with self.assertRaisesRegex(
                api.PJeLaborReportExtractionError,
                "PDF custody",
            ):
                api.extract_pdf_labor_report(
                    pdf_path,
                    self.segments(),
                    self.classification(),
                    timeline,
                    tribunal="TRT99",
                    instance=1,
                    confidentiality="public_or_authorized",
                    source_manifest="document-segments.json",
                    segment_schema_path=SEGMENT_SCHEMA,
                    classification_schema_path=CLASSIFICATION_SCHEMA,
                    timeline_schema_path=TIMELINE_SCHEMA,
                    labor_report_schema_path=LABOR_REPORT_SCHEMA,
                )

    def test_cli_writes_protected_partial_report_and_reports_only_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            output = root / "protected-output"
            output.mkdir()
            pdf_path = root / "synthetic-process.pdf"
            self.synthetic_pdf(pdf_path)
            segments = self.segments()
            segments["source_pdf"] = {
                "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "page_count": 3,
            }
            for index, document in enumerate(segments["documents"], 1):
                document["page_start"] = index
                document["page_end"] = index
            timeline = self.timeline()
            timeline["status"] = "complete"
            timeline["gaps"] = []
            segments_path = root / "document-segments.json"
            classification_path = root / "document-classification.json"
            timeline_path = root / "procedural-timeline.json"
            segments_path.write_text(json.dumps(segments), encoding="utf-8")
            classification_path.write_text(
                json.dumps(self.classification()),
                encoding="utf-8",
            )
            timeline_path.write_text(json.dumps(timeline), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "extract_pje_labor_report.py"),
                    "--input",
                    str(pdf_path),
                    "--segments",
                    str(segments_path),
                    "--classification",
                    str(classification_path),
                    "--timeline",
                    str(timeline_path),
                    "--output",
                    str(output),
                    "--repository-root",
                    str(repository),
                    "--tribunal",
                    "TRT99",
                    "--instance",
                    "1",
                    "--confidentiality",
                    "public_or_authorized",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                completed.stdout.strip(),
                "[OK] PJe labor report: parties=3 events=2 positions=0 gaps=2",
            )
            self.assertNotIn("ANA EXEMPLO", completed.stdout)
            self.assertTrue((output / "labor-report.json").is_file())


if __name__ == "__main__":
    unittest.main()
