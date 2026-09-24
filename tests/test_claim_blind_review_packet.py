from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfWriter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class ClaimBlindReviewPacketTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("prepare_claim_blind_review")

    def inputs(self, directory: Path):
        pdf_path = directory / "synthetic.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=72, height=72)
        writer.add_metadata({"/Title": "Synthetic case"})
        with pdf_path.open("wb") as stream:
            writer.write(stream)
        segments = {
            "schema_version": 1,
            "segmentation_method": "pje_pdf_outline",
            "source_pdf": {
                "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "page_count": 3,
            },
            "documents": [
                {
                    "document_id": "DOC-001",
                    "provider_reference": "0000001",
                    "provider_type": "Initial",
                    "filed_on": "2026-01-01",
                    "page_start": 1,
                    "page_end": 2,
                },
                {
                    "document_id": "DOC-002",
                    "provider_reference": "0000002",
                    "provider_type": "Defense",
                    "filed_on": "2026-01-02",
                    "page_start": 3,
                    "page_end": 3,
                },
            ],
        }
        return pdf_path, segments

    def test_packet_uses_only_source_custody_and_leaves_inventory_blank(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            pdf_path, segments = self.inputs(Path(directory))
            packet = api.prepare_review_packet(
                pdf_path, segments, document_id="DOC-001", case_id="PILOT-001"
            )
        self.assertIn("PILOT-001", packet)
        self.assertIn("DOC-001", packet)
        self.assertIn("páginas 1-2", packet)
        self.assertIn("sem consultar a matriz", packet)
        self.assertIn("[preencher]", packet)
        self.assertNotIn("CLM-", packet)
        self.assertNotIn("POS-", packet)
        self.assertNotIn("8 pedidos", packet)
        self.assertNotIn("16 vínculos", packet)

    def test_rejects_pdf_custody_mismatch_and_out_of_range_segment(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            pdf_path, segments = self.inputs(Path(directory))
            segments["source_pdf"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(api.BlindReviewPacketError, "custódia"):
                api.prepare_review_packet(
                    pdf_path, segments, document_id="DOC-001", case_id="PILOT-001"
                )
            segments["source_pdf"]["sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            segments["documents"][0]["page_end"] = 4
            with self.assertRaisesRegex(api.BlindReviewPacketError, "intervalo de páginas"):
                api.prepare_review_packet(
                    pdf_path, segments, document_id="DOC-001", case_id="PILOT-001"
                )

    def test_rejects_unknown_document_and_invalid_pseudonym(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            pdf_path, segments = self.inputs(Path(directory))
            with self.assertRaisesRegex(api.BlindReviewPacketError, "documento"):
                api.prepare_review_packet(
                    pdf_path, segments, document_id="DOC-999", case_id="PILOT-001"
                )
            with self.assertRaisesRegex(api.BlindReviewPacketError, "pseudônimo"):
                api.prepare_review_packet(
                    pdf_path, segments, document_id="DOC-001", case_id="0000000-00.2026.5.12.0000"
                )

    def test_protected_output_is_exclusive_and_rejects_repository_path(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = api.write_review_packet(
                "Synthetic blank form\n", output_dir=output, repository_root=ROOT
            )
            self.assertEqual(path.read_text(encoding="utf-8"), "Synthetic blank form\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(api.BlindReviewPacketError, "já existe"):
                api.write_review_packet(
                    "Synthetic blank form\n", output_dir=output, repository_root=ROOT
                )
            with self.assertRaisesRegex(api.BlindReviewPacketError, "fora do repositório"):
                api.write_review_packet(
                    "Synthetic blank form\n", output_dir=ROOT, repository_root=ROOT
                )

    def test_refuses_readable_or_linked_output_directory(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            public = parent / "public"
            public.mkdir(mode=0o755)
            os.chmod(public, 0o755)
            with self.assertRaises(api.BlindReviewPacketError):
                api.write_review_packet(
                    "Inventário protegido\n", output_dir=public, repository_root=ROOT
                )
            self.assertFalse((public / "independent-claim-review.md").exists())

            private = parent / "private"
            private.mkdir(mode=0o700)
            alias = parent / "alias"
            alias.symlink_to(private, target_is_directory=True)
            with self.assertRaises(api.BlindReviewPacketError):
                api.write_review_packet(
                    "Inventário protegido\n", output_dir=alias, repository_root=ROOT
                )
            self.assertFalse((private / "independent-claim-review.md").exists())

    def test_preserves_broken_link_at_output_name(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = output / "independent-claim-review.md"
            path.symlink_to(output / "missing-target.md")

            try:
                with self.assertRaisesRegex(api.BlindReviewPacketError, "já existe"):
                    api.write_review_packet(
                        "Inventário protegido\n", output_dir=output, repository_root=ROOT
                    )
            except OSError as error:
                self.fail(f"erro de sistema escapou da validação: {type(error).__name__}")
            self.assertTrue(path.is_symlink())
            self.assertFalse((output / "missing-target.md").exists())

    def test_cli_uses_portuguese_without_exposing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            pdf, segments = self.inputs(output)
            segments_path = output / "segments.json"
            segments_path.write_text(json.dumps(segments), encoding="utf-8")
            command = [
                sys.executable, str(SCRIPTS / "prepare_claim_blind_review.py"),
                "--input", str(pdf), "--segments", str(segments_path),
                "--document-id", "DOC-001", "--case-id", "PILOT-001",
                "--output", str(output),
            ]

            result = subprocess.run(command, capture_output=True, text=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("formulário protegido", result.stdout)
            self.assertNotIn("Synthetic case", result.stdout + result.stderr)
            self.assertTrue((output / "independent-claim-review.md").is_file())

    def test_cli_reports_invalid_pseudonym_in_portuguese(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            pdf, segments = self.inputs(output)
            segments_path = output / "segments.json"
            segments_path.write_text(json.dumps(segments), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "prepare_claim_blind_review.py"),
                 "--input", str(pdf), "--segments", str(segments_path),
                 "--document-id", "DOC-001", "--case-id", "0000000-00.2026.5.12.0000",
                 "--output", str(output)],
                capture_output=True, text=True, check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("[ERRO]", result.stderr)
            self.assertIn("pseudônimo", result.stderr)
            self.assertFalse((output / "independent-claim-review.md").exists())

    def test_cli_help_describes_source_inputs_in_portuguese(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "prepare_claim_blind_review.py"), "--help"],
            capture_output=True, text=True, check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mapa de segmentos", result.stdout.casefold())
        self.assertIn("identificador do documento", result.stdout.casefold())
