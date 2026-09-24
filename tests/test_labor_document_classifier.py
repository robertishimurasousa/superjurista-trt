from __future__ import annotations

import copy
import importlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = ROOT / "runtime" / "domain" / "labor-document-classification.json"


class LaborDocumentClassifierTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("classify_labor_documents")
        except ModuleNotFoundError as error:
            self.fail(f"labor document classifier module is missing: {error}")

    def candidate(
        self,
        api,
        document_id,
        *,
        provider_type="",
        title="",
        text_excerpt="",
    ):
        return api.DocumentCandidate(
            document_id=document_id,
            provider_type=provider_type,
            title=title,
            text_excerpt=text_excerpt,
        )

    def classify(self, api, *candidates, contract=None):
        active_contract = contract or api.load_classification_contract(CONTRACT)
        return api.classify_documents(active_contract, tuple(candidates))

    def test_classifies_core_labor_document_types_from_synthetic_metadata(self) -> None:
        api = self.api()

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", provider_type="Petição Inicial"),
            self.candidate(api, "DOC-002", title="CONTESTAÇÃO"),
            self.candidate(api, "DOC-003", provider_type="Ata de audiência"),
            self.candidate(api, "DOC-004", title="Laudo pericial médico"),
            self.candidate(api, "DOC-005", provider_type="Sentença"),
        )

        self.assertEqual(
            [item["document_type"] for item in result["documents"]],
            [
                "initial_pleading",
                "defense",
                "hearing_record",
                "expert_report",
                "judgment",
            ],
        )
        self.assertTrue(
            all(
                item["classification_status"] == "classified"
                and item["reason_code"] == "matched_rule"
                for item in result["documents"]
            )
        )

    def test_unknown_document_type_is_preserved_without_guessing(self) -> None:
        api = self.api()

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", provider_type="Tipo sintético não mapeado"),
        )

        self.assertEqual(
            result["documents"][0],
            {
                "document_id": "DOC-001",
                "document_type": "unknown",
                "classification_status": "unknown",
                "matched_rule_ids": [],
                "reason_code": "no_matching_rule",
            },
        )

    def test_classifies_generic_trt12_provider_labels_without_case_text(self) -> None:
        api = self.api()
        labels = (
            ("Carteira de Trabalho e Previdência Social (CTPS)", "documentary_evidence"),
            ("Termo de Rescisão de Contrato de Trabalho (TRCT)", "documentary_evidence"),
            ("Cartão de Ponto/Controle de Frequência", "documentary_evidence"),
            ("Contracheque/Recibo de Salário", "documentary_evidence"),
            ("Extrato de FGTS", "documentary_evidence"),
            ("Procuração", "documentary_evidence"),
            ("Contrato de Trabalho", "documentary_evidence"),
            ("Carta de Preposição", "documentary_evidence"),
            ("Manifestação", "other_petition"),
            ("Razões Finais", "other_petition"),
            ("Solicitação de Habilitação", "other_petition"),
            ("Impugnação à Contestação", "reply"),
        )
        candidates = tuple(
            self.candidate(api, f"DOC-{index:03d}", provider_type=provider_type)
            for index, (provider_type, _) in enumerate(labels, 1)
        )

        result = self.classify(api, *candidates)

        self.assertEqual(
            [item["document_type"] for item in result["documents"]],
            [expected for _, expected in labels],
        )

    def test_classifies_separated_contra_cheque_as_documentary_evidence(self) -> None:
        api = self.api()

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", provider_type="Documento Diverso (Contra cheque)"),
            self.candidate(api, "DOC-002", provider_type="Documento Diverso"),
        )

        self.assertEqual(result["documents"][0]["document_type"], "documentary_evidence")
        self.assertEqual(result["documents"][0]["matched_rule_ids"], ["documentary-evidence"])
        self.assertEqual(result["documents"][1]["document_type"], "unknown")

    def test_classifies_procedural_metadata_without_treating_it_as_a_decision(self) -> None:
        api = self.api()

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", provider_type="Certidão de Publicação no DJEN"),
            self.candidate(api, "DOC-002", provider_type="Intimação"),
            self.candidate(api, "DOC-003", provider_type="Notificação"),
        )

        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(
            [item["document_type"] for item in result["documents"]],
            ["procedural_certificate", "procedural_communication", "procedural_communication"],
        )

    def test_procedural_word_only_in_excerpt_does_not_classify_generic_document(self) -> None:
        api = self.api()

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", provider_type="Documento Diverso", text_excerpt="Certidão"),
        )

        self.assertEqual(result["documents"][0]["document_type"], "unknown")

    def test_certificate_of_a_decision_remains_a_certificate(self) -> None:
        api = self.api()

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", provider_type="Certidão de publicação da decisão"),
        )

        self.assertEqual(result["documents"][0]["document_type"], "procedural_certificate")

    def test_rejects_malformed_rule_field_selection_as_contract_error(self) -> None:
        api = self.api()
        contract = copy.deepcopy(api.load_classification_contract(CONTRACT))
        contract["rules"][0]["match_fields"] = [{"unsupported": "value"}]

        with self.assertRaisesRegex(api.ContractError, "match_fields"):
            self.classify(
                api,
                self.candidate(api, "DOC-001", provider_type="Petição Inicial"),
                contract=contract,
            )

    def test_specific_initial_pleading_rule_wins_over_generic_petition(self) -> None:
        api = self.api()

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", provider_type="Petição inicial"),
        )

        item = result["documents"][0]
        self.assertEqual(item["document_type"], "initial_pleading")
        self.assertEqual(item["matched_rule_ids"], ["initial-pleading"])

    def test_normalization_handles_case_accents_and_punctuation(self) -> None:
        api = self.api()

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", title="  RÉPLICA À CONTESTAÇÃO!!!  "),
        )

        self.assertEqual(result["documents"][0]["document_type"], "reply")

    def test_conflicting_top_priority_rules_fail_closed_as_unknown(self) -> None:
        api = self.api()
        contract = copy.deepcopy(api.load_classification_contract(CONTRACT))
        contract["rules"].append(
            {
                "rule_id": "synthetic-conflict",
                "document_type": "judgment",
                "priority": 90,
                "phrases": ["contestacao"],
            }
        )

        result = self.classify(
            api,
            self.candidate(api, "DOC-001", title="Contestação"),
            contract=contract,
        )

        self.assertEqual(result["documents"][0]["document_type"], "unknown")
        self.assertEqual(result["documents"][0]["classification_status"], "conflict")
        self.assertEqual(result["documents"][0]["reason_code"], "conflicting_rules")

    def test_output_is_deterministic_and_sorted_by_document_id(self) -> None:
        api = self.api()
        first = self.candidate(api, "DOC-001", title="Contestação")
        second = self.candidate(api, "DOC-002", title="Sentença")

        forward = self.classify(api, first, second)
        reverse = self.classify(api, second, first)

        self.assertEqual(forward, reverse)
        self.assertEqual(
            [item["document_id"] for item in forward["documents"]],
            ["DOC-001", "DOC-002"],
        )

    def test_duplicate_document_id_is_rejected(self) -> None:
        api = self.api()
        first = self.candidate(api, "DOC-001", title="Contestação")
        duplicate = self.candidate(api, "DOC-001", title="Sentença")

        with self.assertRaisesRegex(api.ClassificationContractViolation, "document_id"):
            self.classify(api, first, duplicate)

    def test_output_never_serializes_source_text(self) -> None:
        api = self.api()
        private_text = "private-case-content-1234567890"

        result = self.classify(
            api,
            self.candidate(
                api,
                "DOC-001",
                provider_type="Documento sem classificação",
                text_excerpt=private_text,
            ),
        )

        self.assertNotIn(private_text, json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
