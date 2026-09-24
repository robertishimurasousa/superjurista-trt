from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class LaborDefenseExtractionTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("extract_labor_defenses")
        except ModuleNotFoundError as error:
            self.fail(f"labor defense extractor module is missing: {error}")

    def test_extracts_defense_sections_with_claim_labels_and_page_custody(self) -> None:
        api = self.api()
        pages = (
            (86, "9 - DOS HONORARIOS DE SUCUMBENCIA EM\nFAVOR DO PROCURADOR DA DEMANDADA"),
            (77, "3 - DAS VERBAS RESCISORIAS"),
            (78, "4 - DO INTERVALO INTRAJORNADA"),
            (79, "5 - DO DANO MORAL"),
            (82, "6 - DA MULTA DO ARTIGO 467 E 477 DA CLT"),
            (84, "7 - DA JUSTICA GRATUITA\n8 - DOS HONORARIOS DE SUCUMBENCIA EM\nFAVOR DO PROCURADOR DO DEMANDANTE"),
        )

        result = api.extract_defense_positions(
            defense_document_id="DOC-028",
            page_texts=pages,
            position_group=1,
        )

        self.assertEqual(
            [(item.position_id, item.label) for item in result],
            [
                ("POS-101", "termination_payments"),
                ("POS-102", "meal_rest_interval"),
                ("POS-103", "moral_damages"),
                ("POS-104", "unmapped_statutory_penalty_article_467"),
                ("POS-105", "unmapped_statutory_penalty_article_477"),
                ("POS-106", "unmapped_legal_aid"),
                ("POS-107", "attorney_fees"),
            ],
        )
        self.assertTrue(all(item.kind == "defense" for item in result))
        self.assertEqual(
            [item.summary for item in result],
            [
                "A parte reclamada impugna o pedido de verbas rescisórias.",
                "A parte reclamada impugna o pedido relativo ao intervalo intrajornada.",
                "A parte reclamada impugna o alegado dano extrapatrimonial e a indenização requerida.",
                "A parte reclamada impugna a multa do art. 467 da CLT.",
                "A parte reclamada impugna a multa do art. 477 da CLT.",
                "A parte reclamada impugna o pedido de assistência judiciária gratuita.",
                "A parte reclamada impugna o pedido de honorários advocatícios da parte autora.",
            ],
        )
        self.assertEqual(result[3].source.document_id, "DOC-028")
        self.assertEqual(result[3].source.locator, "página 82, título da seção de defesa")
        self.assertEqual(result[4].source.locator, "página 82, título da seção de defesa")

    def test_position_group_keeps_multiple_defense_documents_distinct(self) -> None:
        api = self.api()
        pages = ((4, "3 - DAS VERBAS RESCISORIAS"),)

        first = api.extract_defense_positions(
            defense_document_id="DOC-010",
            page_texts=pages,
            position_group=1,
        )
        second = api.extract_defense_positions(
            defense_document_id="DOC-011",
            page_texts=pages,
            position_group=2,
        )

        self.assertEqual(first[0].position_id, "POS-101")
        self.assertEqual(second[0].position_id, "POS-201")

    def test_ignores_prose_and_respondent_attorney_fee_request(self) -> None:
        api = self.api()

        result = api.extract_defense_positions(
            defense_document_id="DOC-001",
            page_texts=(
                (3, "The narrative mentions intervalo intrajornada and dano moral."),
                (
                    9,
                    "9 - DOS HONORARIOS DE SUCUMBENCIA EM\n"
                    "FAVOR DO PROCURADOR DA DEMANDADA",
                ),
            ),
            position_group=1,
        )

        self.assertEqual(result, ())

    def test_rejects_invalid_group_or_document_custody(self) -> None:
        api = self.api()

        invalid_inputs = (
            ("DOC-1", 1),
            ("DOC-001", 0),
            ("DOC-001", True),
        )
        for document_id, group in invalid_inputs:
            with self.subTest(document_id=document_id, group=group):
                with self.assertRaises(api.LaborDefenseExtractionError):
                    api.extract_defense_positions(
                        defense_document_id=document_id,
                        page_texts=((2, "3 - DAS VERBAS RESCISORIAS"),),
                        position_group=group,
                    )


if __name__ == "__main__":
    unittest.main()
