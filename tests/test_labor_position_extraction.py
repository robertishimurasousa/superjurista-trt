from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class LaborPositionExtractionTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("extract_labor_positions")
        except ModuleNotFoundError as error:
            self.fail(f"labor position extractor module is missing: {error}")

    def test_extracts_claim_sections_with_stable_ids_and_page_custody(self) -> None:
        api = self.api()
        pages = (
            (12, "D. Interval request repeated in the final request list."),
            (
                2,
                "1. DO PEDIDO DE ASSISTENCIA JUDICIARIA GRATUITA\n"
                "3. DA RESPONSABILIDADE SOLIDARIA/SUBSIDIARIA",
            ),
            (4, "4. DO CONTRATO POR PRAZO DETERMINADO E DAS VERBAS RESCISORIAS"),
            (6, "5. DO INTERVALOR INTRAJORDNADA"),
            (7, "6. DA IN DENIZACAO POR DANOS EXTRAPATRIMONIAIS"),
            (8, "7. DA MULTA DO ART. 467 DA CLT"),
            (
                9,
                "8. DA MULTA DO ART. 477, § 8 DA CLT\n"
                "9. DOS HONORARIOS ADVOCATICIOS",
            ),
        )

        result = api.extract_claim_positions(
            initial_document_id="DOC-001",
            page_texts=pages,
        )

        self.assertEqual(
            [(item.position_id, item.label) for item in result],
            [
                ("POS-001", "unmapped_legal_aid"),
                ("POS-002", "unmapped_joint_or_subsidiary_liability"),
                ("POS-003", "termination_payments"),
                ("POS-004", "meal_rest_interval"),
                ("POS-005", "moral_damages"),
                ("POS-006", "unmapped_statutory_penalty_article_467"),
                ("POS-007", "unmapped_statutory_penalty_article_477"),
                ("POS-008", "attorney_fees"),
            ],
        )
        self.assertTrue(all(item.kind == "claim" for item in result))
        self.assertEqual(
            [item.summary for item in result],
            [
                "A parte autora requer assistência judiciária gratuita.",
                "A parte autora requer responsabilidade solidária ou subsidiária.",
                "A parte autora requer verbas rescisórias.",
                "A parte autora requer pagamento pelo intervalo intrajornada alegadamente suprimido.",
                "A parte autora requer indenização por alegado dano extrapatrimonial.",
                "A parte autora requer multa do art. 467 da CLT.",
                "A parte autora requer multa do art. 477 da CLT.",
                "A parte autora requer honorários advocatícios.",
            ],
        )
        self.assertEqual(result[3].source.document_id, "DOC-001")
        self.assertEqual(result[3].source.locator, "página 6, título da seção de pedido")

    def test_uses_the_first_heading_and_does_not_duplicate_final_requests(self) -> None:
        api = self.api()

        result = api.extract_claim_positions(
            initial_document_id="DOC-007",
            page_texts=(
                (10, "DOS PEDIDOS\nD. DO INTERVALO INTRAJORNADA"),
                (3, "5. DO INTERVALO INTRAJORNADA"),
            ),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].position_id, "POS-004")
        self.assertEqual(result[0].source.locator, "página 3, título da seção de pedido")

    def test_handles_wrapped_headings_and_portuguese_ordinal_markers(self) -> None:
        api = self.api()

        result = api.extract_claim_positions(
            initial_document_id="DOC-001",
            page_texts=(
                (
                    4,
                    "4. DO CONTRATO POR PRAZO DETERMINADO E DAS VERBAS\n"
                    "RECISORIAS",
                ),
                (9, "8. DA MULTA DO ART. 477, § 8º DA CLT"),
            ),
        )

        self.assertEqual(
            [(item.position_id, item.label) for item in result],
            [
                ("POS-003", "termination_payments"),
                ("POS-007", "unmapped_statutory_penalty_article_477"),
            ],
        )

    def test_ignores_claim_phrases_in_prose_without_a_section_heading(self) -> None:
        api = self.api()

        result = api.extract_claim_positions(
            initial_document_id="DOC-001",
            page_texts=(
                (
                    2,
                    "The employment narrative mentions intervalo intrajornada and "
                    "verbas rescisorias, but it contains no claim section heading.",
                ),
            ),
        )

        self.assertEqual(result, ())

    def test_rejects_duplicate_pages_or_invalid_document_custody(self) -> None:
        api = self.api()

        invalid_inputs = (
            ("DOC-1", ((2, "5. DO INTERVALO INTRAJORNADA"),)),
            (
                "DOC-001",
                (
                    (2, "5. DO INTERVALO INTRAJORNADA"),
                    (2, "9. DOS HONORARIOS ADVOCATICIOS"),
                ),
            ),
        )
        for document_id, pages in invalid_inputs:
            with self.subTest(document_id=document_id, pages=pages):
                with self.assertRaises(api.LaborPositionExtractionError):
                    api.extract_claim_positions(
                        initial_document_id=document_id,
                        page_texts=pages,
                    )


if __name__ == "__main__":
    unittest.main()
