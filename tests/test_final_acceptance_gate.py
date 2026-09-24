from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FINAL_REVIEW_SCHEMA = ROOT / "runtime" / "pipelines" / "final-review.v1.schema.json"
GLOBAL_GATE_SCHEMA = ROOT / "runtime" / "pipelines" / "global-gate.v1.schema.json"

SUPPORTED_QUOTE = (
    "A synthetic quotation long enough for deterministic custody verification "
    "must remain exactly inside its declared source excerpt."
)


def claim_analysis(*, source_ids=("TST-001",)):
    return {
        "schema_version": 1,
        "analyses": [
            {
                "analysis_id": "ANL-001",
                "claim_id": "CLM-001",
                "facts_found": ["Synthetic fact."],
                "evidence_ids": ["EVD-001"],
                "evidence_assessment": ["Synthetic evidence assessment."],
                "applicable_rules": ["Synthetic rule."],
                "precedent_source_ids": list(source_ids),
                "reasoning": "Synthetic reasoning.",
                "proposed_outcome": "granted",
                "limitations": [],
            }
        ],
    }


def disposition_matrix(*, criteria=("Apply the synthetic indexed basis.",)):
    return {
        "schema_version": 1,
        "items": [
            {
                "disposition_id": "DSP-001",
                "claim_id": "CLM-001",
                "outcome": "granted",
                "command": "Grant the synthetic claim.",
                "period": "synthetic_period",
                "effects": ["synthetic_effect"],
                "calculation_criteria": list(criteria),
                "source_analysis_id": "ANL-001",
            }
        ],
    }


def congruence_report(*, status="passed"):
    metric = {"covered": 1, "total": 1, "percent": 100}
    return {
        "schema_version": 1,
        "status": status,
        "claim_count": 1,
        "coverage": {
            "analysis": dict(metric),
            "disposition": dict(metric),
            "draft": dict(metric),
        },
        "links": [
            {
                "claim_id": "CLM-001",
                "analysis_id": "ANL-001",
                "disposition_id": "DSP-001",
                "outcome": "granted",
            }
        ],
    }


def final_review(
    *,
    source_status="available",
    source_excerpt=SUPPORTED_QUOTE,
    source_reason="",
    calculation_status="completed",
    criteria=("Apply the synthetic indexed basis.",),
    calculation_reason="",
):
    return {
        "schema_version": 1,
        "sources": [
            {
                "source_id": "TST-001",
                "status": source_status,
                "verbatim_excerpt": source_excerpt,
                "unavailability_reason": source_reason,
            }
        ],
        "calculations": [
            {
                "claim_id": "CLM-001",
                "status": calculation_status,
                "criteria": list(criteria),
                "unavailability_reason": calculation_reason,
            }
        ],
    }


class FinalAcceptanceGateTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("evaluate_final_gate")
        except ModuleNotFoundError as error:
            self.fail(f"final acceptance gate module is missing: {error}")

    def evaluate(
        self,
        api,
        *,
        analysis=None,
        dispositions=None,
        draft=None,
        congruence=None,
        review=None,
    ):
        return api.evaluate_final_gate(
            claim_analysis() if analysis is None else analysis,
            disposition_matrix() if dispositions is None else dispositions,
            SUPPORTED_QUOTE if draft is None else draft,
            congruence_report() if congruence is None else congruence,
            final_review() if review is None else review,
            final_review_schema=FINAL_REVIEW_SCHEMA,
            global_gate_schema=GLOBAL_GATE_SCHEMA,
        )

    def test_supported_sources_quotes_and_calculations_pass_all_gates(self) -> None:
        api = self.api()

        report = self.evaluate(api, draft=f'Foundation: "{SUPPORTED_QUOTE}"')

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["issues"], [])
        self.assertEqual(
            report["checks"],
            {
                "congruence": "passed",
                "citations": "passed",
                "sources": "passed",
                "calculations": "passed",
            },
        )
        self.assertEqual(report["quotation_count"], 1)
        self.assertIsNone(api.require_final_acceptance(report))

    def test_short_quoted_expression_is_outside_verbatim_regime(self) -> None:
        api = self.api()

        report = self.evaluate(api, draft='The expression "short quotation" is used.')

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["quotation_count"], 0)

    def test_unsupported_long_quotation_fails_closed(self) -> None:
        api = self.api()
        unsupported = "X" * 80

        report = self.evaluate(api, draft=f'Foundation: "{unsupported}"')

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["checks"]["citations"], "failed")
        self.assertEqual(report["issues"][0]["code"], "unsupported_quotation")
        self.assertEqual(
            report["issues"][0]["detail"],
            "A citação não consta de nenhuma fonte literal disponível.",
        )
        with self.assertRaisesRegex(api.FinalGateRejected, "unsupported_quotation"):
            api.require_final_acceptance(report)

    def test_referenced_source_must_have_a_review_record(self) -> None:
        api = self.api()
        review = final_review()
        review["sources"] = []

        report = self.evaluate(api, review=review)

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["checks"]["sources"], "failed")
        self.assertEqual(report["issues"][0]["code"], "missing_source_review")
        self.assertEqual(
            report["issues"][0]["detail"],
            "A fonte citada não possui registro de revisão final.",
        )

    def test_source_unavailability_is_explicit_and_blocks_acceptance(self) -> None:
        api = self.api()
        review = final_review(
            source_status="unavailable",
            source_excerpt="",
            source_reason="Official provider timed out after bounded retries.",
        )

        report = self.evaluate(api, review=review, draft="No quotation required.")

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["checks"]["sources"], "blocked")
        self.assertEqual(report["issues"][0]["code"], "source_unavailable")
        self.assertEqual(report["issues"][0]["subject_id"], "TST-001")
        self.assertIn("bounded retries", report["issues"][0]["detail"])
        with self.assertRaisesRegex(api.FinalGateRejected, "source_unavailable"):
            api.require_final_acceptance(report)

    def test_unavailable_source_requires_a_reason_and_forbids_an_excerpt(self) -> None:
        api = self.api()
        cases = (
            final_review(
                source_status="unavailable",
                source_excerpt="",
                source_reason="",
            ),
            final_review(
                source_status="unavailable",
                source_excerpt=SUPPORTED_QUOTE,
                source_reason="Synthetic outage.",
            ),
        )
        for review in cases:
            with self.subTest(review=review):
                with self.assertRaisesRegex(api.FinalGateContractError, "Fonte"):
                    self.evaluate(api, review=review)

    def test_calculation_criteria_must_match_the_disposition_exactly(self) -> None:
        api = self.api()
        review = final_review(criteria=("A different synthetic criterion.",))

        report = self.evaluate(api, review=review)

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["checks"]["calculations"], "failed")
        self.assertEqual(report["issues"][0]["code"], "calculation_mismatch")
        self.assertEqual(
            report["issues"][0]["detail"],
            "Os critérios revisados divergem do dispositivo.",
        )

    def test_claim_without_calculation_criteria_must_be_not_required(self) -> None:
        api = self.api()
        review = final_review(calculation_status="not_required", criteria=())

        report = self.evaluate(
            api,
            dispositions=disposition_matrix(criteria=()),
            review=review,
        )

        self.assertEqual(report["status"], "passed")

    def test_missing_calculation_review_fails_closed(self) -> None:
        api = self.api()
        review = final_review()
        review["calculations"] = []

        report = self.evaluate(api, review=review)

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["issues"][0]["code"], "missing_calculation_review")
        self.assertEqual(
            report["issues"][0]["detail"],
            "O pedido não possui revisão final dos cálculos.",
        )

    def test_calculation_unavailability_is_explicit_and_blocks_acceptance(self) -> None:
        api = self.api()
        review = final_review(
            calculation_status="unavailable",
            criteria=(),
            calculation_reason="Calculation inputs are incomplete.",
        )

        report = self.evaluate(api, review=review)

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["checks"]["calculations"], "blocked")
        self.assertTrue(
            any(issue["code"] == "calculation_unavailable" for issue in report["issues"])
        )

    def test_failed_or_incongruent_upstream_report_fails_the_final_gate(self) -> None:
        api = self.api()
        invalid_coverage = congruence_report()
        invalid_coverage["coverage"]["draft"]["percent"] = 99
        tampered_link = congruence_report()
        tampered_link["links"][0]["analysis_id"] = "ANL-999"

        for upstream in (invalid_coverage, tampered_link):
            with self.subTest(upstream=upstream):
                report = self.evaluate(api, congruence=upstream)

                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["checks"]["congruence"], "failed")
                self.assertEqual(
                    report["issues"][0]["code"],
                    "congruence_not_passed",
                )
                self.assertIn("relatório anterior", report["issues"][0]["detail"])

    def test_duplicate_review_identifiers_are_contract_errors(self) -> None:
        api = self.api()
        cases = []
        duplicate_source = final_review()
        duplicate_source["sources"].append(copy.deepcopy(duplicate_source["sources"][0]))
        cases.append(duplicate_source)
        duplicate_claim = final_review()
        duplicate_claim["calculations"].append(
            copy.deepcopy(duplicate_claim["calculations"][0])
        )
        cases.append(duplicate_claim)

        for review in cases:
            with self.subTest(review=review):
                with self.assertRaisesRegex(api.FinalGateContractError, "duplicado"):
                    self.evaluate(api, review=review)

    def test_rejection_error_is_in_portuguese_and_preserves_codes(self) -> None:
        api = self.api()
        report = self.evaluate(api, draft=f'Fundamentação: "{"X" * 80}"')

        with self.assertRaisesRegex(
            api.FinalGateRejected,
            "Controle final reprovado: failed; códigos: unsupported_quotation",
        ):
            api.require_final_acceptance(report)

    def test_output_satisfies_the_versioned_global_gate_schema(self) -> None:
        api = self.api()
        schema_api = importlib.import_module("schema_validation")
        report = self.evaluate(api)
        schema = schema_api.load_json(GLOBAL_GATE_SCHEMA, "global gate schema")

        self.assertEqual(schema_api.validate_schema_value(report, schema), [])


if __name__ == "__main__":
    unittest.main()
