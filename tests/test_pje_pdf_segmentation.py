from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLASSIFICATION_CONTRACT = ROOT / "runtime" / "domain" / "labor-document-classification.json"
SEGMENT_SCHEMA = ROOT / "runtime" / "providers" / "pje-pdf-segments.v1.schema.json"
CLASSIFICATION_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "document-classification.v1.schema.json"
)


class PJePdfSegmentationTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("segment_pje_pdf")
        except ModuleNotFoundError as error:
            self.fail(f"PJe PDF segmentation module is missing: {error}")

    def synthetic_pdf(
        self,
        destination: Path,
        outlines: tuple[tuple[str, int], ...] | None = None,
    ) -> None:
        writer = PdfWriter()
        for _ in range(5):
            writer.add_blank_page(width=595, height=842)
        active_outlines = outlines
        if active_outlines is None:
            active_outlines = (
                ("1. 01/02/2026 - Petição Inicial - abc1234", 0),
                ("2. 03/02/2026 - Contestação - def5678", 2),
                ("3. 04/02/2026 - Ata da Audiência - 123abcd", 4),
            )
        for title, page in active_outlines:
            writer.add_outline_item(title, page)
        with destination.open("wb") as stream:
            writer.write(stream)

    def test_segments_pje_outline_into_stable_document_page_ranges(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "synthetic-process.pdf"
            self.synthetic_pdf(pdf_path)
            expected_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

            result = api.segment_pje_pdf(pdf_path)

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["segmentation_method"], "pje_pdf_outline")
        self.assertEqual(result["source_pdf"]["page_count"], 5)
        self.assertEqual(
            result["source_pdf"]["sha256"],
            expected_sha256,
        )
        self.assertEqual(
            result["documents"],
            [
                {
                    "document_id": "DOC-001",
                    "provider_reference": "abc1234",
                    "provider_type": "Petição Inicial",
                    "filed_on": "2026-02-01",
                    "page_start": 1,
                    "page_end": 2,
                },
                {
                    "document_id": "DOC-002",
                    "provider_reference": "def5678",
                    "provider_type": "Contestação",
                    "filed_on": "2026-02-03",
                    "page_start": 3,
                    "page_end": 4,
                },
                {
                    "document_id": "DOC-003",
                    "provider_reference": "123abcd",
                    "provider_type": "Ata da Audiência",
                    "filed_on": "2026-02-04",
                    "page_start": 5,
                    "page_end": 5,
                },
            ],
        )

    def test_rejects_pdf_without_pje_outline(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "missing-outline.pdf"
            self.synthetic_pdf(pdf_path, outlines=())

            with self.assertRaisesRegex(api.PJePdfSegmentationError, "outline"):
                api.segment_pje_pdf(pdf_path)

    def test_rejects_malformed_or_noncontiguous_pje_outline(self) -> None:
        api = self.api()
        scenarios = (
            (("invalid title", 0),),
            (
                ("1. 01/02/2026 - Petição Inicial - abc1234", 0),
                ("3. 03/02/2026 - Contestação - def5678", 2),
            ),
        )
        for outlines in scenarios:
            with self.subTest(outlines=outlines):
                with tempfile.TemporaryDirectory() as temporary:
                    pdf_path = Path(temporary) / "invalid-outline.pdf"
                    self.synthetic_pdf(pdf_path, outlines=outlines)

                    with self.assertRaises(api.PJePdfSegmentationError):
                        api.segment_pje_pdf(pdf_path)

    def test_rejects_incomplete_overlapping_or_duplicate_outline_custody(self) -> None:
        api = self.api()
        scenarios = (
            (
                ("1. 01/02/2026 - Petição Inicial - abc1234", 1),
                ("2. 03/02/2026 - Contestação - def5678", 3),
            ),
            (
                ("1. 01/02/2026 - Petição Inicial - abc1234", 0),
                ("2. 03/02/2026 - Contestação - def5678", 0),
            ),
            (
                ("1. 01/02/2026 - Petição Inicial - abc1234", 0),
                ("2. 03/02/2026 - Contestação - abc1234", 2),
            ),
        )
        for outlines in scenarios:
            with self.subTest(outlines=outlines):
                with tempfile.TemporaryDirectory() as temporary:
                    pdf_path = Path(temporary) / "invalid-custody.pdf"
                    self.synthetic_pdf(pdf_path, outlines=outlines)

                    with self.assertRaises(api.PJePdfSegmentationError):
                        api.segment_pje_pdf(pdf_path)

    def test_classifies_segments_without_copying_provider_metadata(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            pdf_path = Path(temporary) / "synthetic-process.pdf"
            self.synthetic_pdf(pdf_path)

            result = api.classify_pje_pdf(
                pdf_path,
                classification_contract_path=CLASSIFICATION_CONTRACT,
                segment_schema_path=SEGMENT_SCHEMA,
                classification_schema_path=CLASSIFICATION_SCHEMA,
            )

        self.assertEqual(
            [item["document_type"] for item in result.classification["documents"]],
            ["initial_pleading", "defense", "hearing_record"],
        )
        serialized_classification = json.dumps(
            result.classification,
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertNotIn("Petição Inicial", serialized_classification)
        self.assertNotIn("abc1234", serialized_classification)

    def test_writes_protected_artifacts_only_outside_repository(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            pdf_path = root / "synthetic-process.pdf"
            self.synthetic_pdf(pdf_path)
            result = api.classify_pje_pdf(
                pdf_path,
                classification_contract_path=CLASSIFICATION_CONTRACT,
                segment_schema_path=SEGMENT_SCHEMA,
                classification_schema_path=CLASSIFICATION_SCHEMA,
            )

            protected_output = root / "protected-output"
            protected_output.mkdir()
            written = api.write_classification_artifacts(
                result,
                output_dir=protected_output,
                repository_root=repository,
            )

            self.assertEqual(
                {path.name for path in written},
                {"document-segments.json", "document-classification.json"},
            )
            self.assertTrue(all((path.stat().st_mode & 0o777) == 0o600 for path in written))
            self.assertEqual(
                json.loads((protected_output / "document-classification.json").read_text()),
                result.classification,
            )

            repository_output = repository / "output"
            repository_output.mkdir()
            with self.assertRaisesRegex(api.PJePdfSegmentationError, "outside repository"):
                api.write_classification_artifacts(
                    result,
                    output_dir=repository_output,
                    repository_root=repository,
                )

    def test_cli_writes_bounded_artifacts_and_reports_only_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            output = root / "protected-output"
            output.mkdir()
            pdf_path = root / "synthetic-process.pdf"
            self.synthetic_pdf(pdf_path)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "segment_pje_pdf.py"),
                    "--input",
                    str(pdf_path),
                    "--output",
                    str(output),
                    "--repository-root",
                    str(repository),
                    "--classification-contract",
                    str(CLASSIFICATION_CONTRACT),
                    "--segment-schema",
                    str(SEGMENT_SCHEMA),
                    "--classification-schema",
                    str(CLASSIFICATION_SCHEMA),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                completed.stdout.strip(),
                "[OK] PJe PDF classification: documents=3 classified=3 unknown=0 conflict=0",
            )
            self.assertNotIn("Petição Inicial", completed.stdout)
            self.assertTrue((output / "document-segments.json").is_file())
            self.assertTrue((output / "document-classification.json").is_file())


if __name__ == "__main__":
    unittest.main()
