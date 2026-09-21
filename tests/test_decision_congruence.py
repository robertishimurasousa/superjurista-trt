from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REPORT_SCHEMA = (
    ROOT / "runtime" / "pipelines" / "decision-congruence-report.v1.schema.json"
)


def claim_analysis():
    return {
        "schema_version": 1,
        "analyses": [
            {
                "analysis_id": "ANL-002",
                "claim_id": "CLM-002",
                "reasoning": "Synthetic reasoning for the second claim.",
                "proposed_outcome": "denied",
            },
            {
                "analysis_id": "ANL-001",
                "claim_id": "CLM-001",
                "reasoning": "Synthetic reasoning for the first claim.",
                "proposed_outcome": "granted",
            },
        ],
    }


def disposition_matrix():
    return {
        "schema_version": 1,
        "items": [
            {
                "disposition_id": "DSP-002",
                "claim_id": "CLM-002",
                "outcome": "denied",
                "source_analysis_id": "ANL-002",
            },
            {
                "disposition_id": "DSP-001",
                "claim_id": "CLM-001",
                "outcome": "granted",
                "source_analysis_id": "ANL-001",
            },
        ],
    }


def judgment_draft():
    return """# Synthetic judgment draft

## Fundamentação

### CLM-002

Análise: ANL-002

### CLM-001

Análise: ANL-001

## Dispositivo

### DSP-002 — CLM-002

Análise de origem: ANL-002

### DSP-001 — CLM-001

Análise de origem: ANL-001
"""


class DecisionCongruenceTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("validate_decision_congruence")
        except ModuleNotFoundError as error:
            self.fail(f"decision congruence module is missing: {error}")

    def validate(
        self,
        api,
        *,
        claims=("CLM-002", "CLM-001"),
        analyses=None,
        dispositions=None,
        draft=None,
    ):
        return api.validate_decision_congruence(
            claims,
            claim_analysis() if analyses is None else analyses,
            disposition_matrix() if dispositions is None else dispositions,
            judgment_draft() if draft is None else draft,
            report_schema=REPORT_SCHEMA,
        )

    def test_acceptance_fixture_reaches_exact_and_deterministic_coverage(self) -> None:
        api = self.api()

        first = self.validate(api)
        reversed_analyses = claim_analysis()
        reversed_analyses["analyses"].reverse()
        reversed_dispositions = disposition_matrix()
        reversed_dispositions["items"].reverse()
        second = self.validate(
            api,
            claims=("CLM-001", "CLM-002"),
            analyses=reversed_analyses,
            dispositions=reversed_dispositions,
        )

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "passed")
        self.assertEqual(first["claim_count"], 2)
        for metric in first["coverage"].values():
            self.assertEqual(metric, {"covered": 2, "total": 2, "percent": 100})
        self.assertEqual(
            [link["claim_id"] for link in first["links"]],
            ["CLM-001", "CLM-002"],
        )

    def test_missing_claim_analysis_is_rejected(self) -> None:
        api = self.api()
        analyses = claim_analysis()
        analyses["analyses"].pop()

        with self.assertRaisesRegex(api.DecisionCongruenceError, "missing analysis.*CLM-001"):
            self.validate(api, analyses=analyses)

    def test_analysis_for_unknown_claim_is_rejected(self) -> None:
        api = self.api()
        analyses = claim_analysis()
        analyses["analyses"][0]["claim_id"] = "CLM-999"

        with self.assertRaisesRegex(api.DecisionCongruenceError, "unknown claim.*CLM-999"):
            self.validate(api, analyses=analyses)

    def test_duplicate_claim_or_analysis_identifier_is_rejected(self) -> None:
        api = self.api()
        cases = []
        repeated_claim = claim_analysis()
        repeated_claim["analyses"][1]["claim_id"] = "CLM-002"
        cases.append(repeated_claim)
        repeated_id = claim_analysis()
        repeated_id["analyses"][1]["analysis_id"] = "ANL-002"
        cases.append(repeated_id)

        for analyses in cases:
            with self.subTest(analyses=analyses):
                with self.assertRaisesRegex(api.DecisionCongruenceError, "duplicate"):
                    self.validate(api, analyses=analyses)

    def test_empty_reasoning_is_rejected(self) -> None:
        api = self.api()
        analyses = claim_analysis()
        analyses["analyses"][0]["reasoning"] = "  "

        with self.assertRaisesRegex(api.DecisionCongruenceError, "reasoning"):
            self.validate(api, analyses=analyses)

    def test_missing_claim_disposition_is_rejected(self) -> None:
        api = self.api()
        dispositions = disposition_matrix()
        dispositions["items"].pop()

        with self.assertRaisesRegex(
            api.DecisionCongruenceError,
            "missing disposition.*CLM-001",
        ):
            self.validate(api, dispositions=dispositions)

    def test_disposition_for_unknown_claim_is_rejected(self) -> None:
        api = self.api()
        dispositions = disposition_matrix()
        dispositions["items"][0]["claim_id"] = "CLM-999"

        with self.assertRaisesRegex(api.DecisionCongruenceError, "unknown claim.*CLM-999"):
            self.validate(api, dispositions=dispositions)

    def test_disposition_source_must_match_the_claim_analysis(self) -> None:
        api = self.api()
        dispositions = disposition_matrix()
        dispositions["items"][0]["source_analysis_id"] = "ANL-001"

        with self.assertRaisesRegex(api.DecisionCongruenceError, "source analysis"):
            self.validate(api, dispositions=dispositions)

    def test_disposition_outcome_must_match_the_analysis(self) -> None:
        api = self.api()
        dispositions = disposition_matrix()
        dispositions["items"][0]["outcome"] = "granted"

        with self.assertRaisesRegex(api.DecisionCongruenceError, "outcome"):
            self.validate(api, dispositions=dispositions)

    def test_draft_must_contain_each_exact_foundation_heading_once(self) -> None:
        api = self.api()
        draft = judgment_draft().replace("### CLM-001\n", "")

        with self.assertRaisesRegex(api.DecisionCongruenceError, "foundation.*CLM-001"):
            self.validate(api, draft=draft)

    def test_draft_must_contain_each_exact_disposition_heading_once(self) -> None:
        api = self.api()
        draft = judgment_draft().replace("### DSP-001 — CLM-001\n", "")

        with self.assertRaisesRegex(api.DecisionCongruenceError, "disposition.*DSP-001"):
            self.validate(api, draft=draft)

    def test_draft_rejects_unknown_structured_identifiers(self) -> None:
        api = self.api()
        cases = ("CLM-999", "ANL-999", "DSP-999")
        for identifier in cases:
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(
                    api.DecisionCongruenceError,
                    f"unknown.*{identifier}",
                ):
                    self.validate(api, draft=judgment_draft() + identifier)

    def test_input_schema_or_identifier_drift_fails_closed(self) -> None:
        api = self.api()
        cases = []
        invalid_version = claim_analysis()
        invalid_version["schema_version"] = 2
        cases.append({"analyses": invalid_version})
        invalid_claims = ("CLM-001", "bad-id")
        cases.append({"claims": invalid_claims})
        invalid_dispositions = disposition_matrix()
        invalid_dispositions["items"].append(copy.deepcopy(invalid_dispositions["items"][0]))
        cases.append({"dispositions": invalid_dispositions})

        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(api.DecisionCongruenceError):
                    self.validate(api, **changes)

    def test_output_satisfies_the_versioned_report_schema(self) -> None:
        api = self.api()
        schema_api = importlib.import_module("schema_validation")
        report = self.validate(api)
        schema = schema_api.load_json(REPORT_SCHEMA, "decision congruence schema")

        self.assertEqual(schema_api.validate_schema_value(report, schema), [])


if __name__ == "__main__":
    unittest.main()
