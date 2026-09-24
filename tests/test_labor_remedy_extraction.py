from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class LaborRemedyExtractionTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("extract_labor_remedies")

    def pages(self):
        return (
            (11, """11. DOS PEDIDOS
Diante do exposto, requer-se:
A. A concessão da gratuidade de justiça;
B. A declaração da responsabilidade solidária e/ou subsidiária;
C. O reconhecimento judicial do contrato por prazo indeterminado e dispensa sem justa causa,
com as verbas abaixo:
1) Saldo de salário: R$ 10,00;
2) Aviso prévio indenizado: R$ 20,00;
3) Descanso semanal remunerado: R$ 30,00;
4) 13º salário proporcional: R$ 40,00;
5) Férias proporcionais + 1/3: R$ 50,00;
6) FGTS e multa de 40%: R$ 60,00;
Documento assinado eletronicamente por Synthetic User
Fls.: 11"""),
            (12, """Av. Synthetic Address
7) Entrega das guias para levantamento do FGTS e encaminhamento do seguro desemprego;
8) Liberação das guias para seguro-desemprego ou, subsidiariamente,
indenização substitutiva;
D. Pagamento do intervalo intrajornada não concedido e seus reflexos;
E. Pagamento de indenização por danos morais;
F. Pagamento de parcelas incontroversas na audiência acrescidas de 50%;
G. Pagamento da multa prevista no artigo 477, § 8º;
H. Pagamento de honorários advocatícios;
I. Seja citada a reclamada para defesa;
Fls.: 12"""),
        )

    def claims(self):
        return {
            "unmapped_legal_aid": "CLM-001",
            "unmapped_joint_or_subsidiary_liability": "CLM-002",
            "termination_payments": "CLM-003",
            "meal_rest_interval": "CLM-004",
            "moral_damages": "CLM-005",
            "unmapped_statutory_penalty_article_467": "CLM-006",
            "unmapped_statutory_penalty_article_477": "CLM-007",
            "attorney_fees": "CLM-008",
        }

    def test_extracts_source_linked_prayer_items_and_cross_page_subitems(self):
        result = self.api().extract_requested_remedies(
            self.pages(), "DOC-001", self.claims()
        )
        self.assertEqual(len(result["entries"]), 16)
        self.assertEqual(result["unmatched_item_ids"], ["I"])
        by_id = {item["request_id"]: item for item in result["entries"]}
        self.assertEqual(by_id["A"]["remedy_codes"], ["legal_aid"])
        self.assertEqual(by_id["B"]["claim_id"], "CLM-002")
        self.assertEqual(by_id["C"]["remedy_codes"], [
            "recognition_of_indefinite_term", "recognition_of_dismissal_without_cause"
        ])
        self.assertEqual(by_id["C.6"]["remedy_codes"], ["fgts_deposit", "fgts_40_percent_penalty"])
        self.assertEqual(by_id["C.7"]["source_locator"], "página 12, pedido C.7")
        self.assertEqual(by_id["C.8"]["review_gaps"], ["conditional_alternative"])
        self.assertEqual(by_id["D"]["remedy_codes"], ["interval_payment", "statutory_effects"])
        self.assertEqual(by_id["E"]["remedy_codes"], ["compensation"])
        self.assertEqual(by_id["F"]["remedy_codes"], ["article_467_penalty"])
        self.assertEqual(by_id["G"]["remedy_codes"], ["article_477_penalty"])
        self.assertEqual(by_id["H"]["remedy_codes"], ["attorney_fee_award"])
        self.assertEqual(by_id["C.8"]["source_document_id"], "DOC-001")
        self.assertNotIn("Synthetic Address", by_id["C.7"]["text"])

    def test_rejects_missing_prayer_heading_and_duplicate_request_ids(self):
        api = self.api()
        with self.assertRaisesRegex(api.LaborRemedyExtractionError, "prayer heading"):
            api.extract_requested_remedies(((11, "A. Gratuidade de justiça"),), "DOC-001", self.claims())
        pages = ((11, "DOS PEDIDOS\nA. Gratuidade de justiça\nA. Gratuidade de justiça"),)
        with self.assertRaisesRegex(api.LaborRemedyExtractionError, "duplicate"):
            api.extract_requested_remedies(pages, "DOC-001", self.claims())

    def test_fails_closed_on_unrecognized_subitem_in_known_claim(self):
        api = self.api()
        pages = ((11, "DOS PEDIDOS\nC. Reconhecimento do contrato por prazo indeterminado e dispensa sem justa causa\n1) Pagamento de verba não conhecida"),)
        with self.assertRaisesRegex(api.LaborRemedyExtractionError, "unrecognized"):
            api.extract_requested_remedies(pages, "DOC-001", self.claims())

    def test_recognizes_attorney_fees_with_de_advocaticios_wording(self):
        pages = ((12, "DOS PEDIDOS\nH. A condenação ao pagamento dos honorários de advocatícios previstos no artigo 791-A."),)
        result = self.api().extract_requested_remedies(pages, "DOC-001", self.claims())
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["entries"][0]["claim_id"], "CLM-008")
        self.assertEqual(result["entries"][0]["remedy_codes"], ["attorney_fee_award"])

    def test_rejects_a_numbered_subitem_with_multiple_unhandled_remedies(self):
        pages = ((11, "DOS PEDIDOS\nC. Reconhecimento do contrato por prazo indeterminado e dispensa sem justa causa\n1) Saldo de salário e aviso prévio"),)
        with self.assertRaisesRegex(self.api().LaborRemedyExtractionError, "ambiguous"):
            self.api().extract_requested_remedies(pages, "DOC-001", self.claims())
