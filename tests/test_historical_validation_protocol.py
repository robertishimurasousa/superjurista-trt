from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PROTOCOL = ROOT / "runtime" / "validation" / "historical-validation-protocol.v1.json"
SCHEMA = ROOT / "runtime" / "validation" / "historical-validation-protocol.v1.schema.json"
REVIEW_FORM = ROOT / "spec" / "validation" / "historical-blind-review-form.md"


class HistoricalValidationProtocolTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("validate_historical_protocol")
        except ModuleNotFoundError as error:
            self.fail(f"historical protocol validator is missing: {error}")

    def protocol(self):
        return json.loads(PROTOCOL.read_text(encoding="utf-8"))

    def validate(self, api, protocol=None, form=REVIEW_FORM):
        if protocol is None:
            return api.validate_historical_protocol(PROTOCOL, SCHEMA, form)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.json"
            path.write_text(json.dumps(protocol), encoding="utf-8")
            return api.validate_historical_protocol(path, SCHEMA, form)

    def test_frozen_protocol_is_valid_and_has_a_deterministic_digest(self) -> None:
        api = self.api()

        first = self.validate(api)
        second = self.validate(api)

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "valid")
        self.assertEqual(first["protocol_id"], "TRT12-HISTORICAL-V1")
        self.assertRegex(first["protocol_digest"], r"^[0-9a-f]{64}$")

    def test_sample_partition_must_equal_the_frozen_total(self) -> None:
        api = self.api()
        protocol = self.protocol()
        protocol["sampling"]["untouched_holdout_cases"] = 4

        with self.assertRaisesRegex(api.HistoricalProtocolError, "partition"):
            self.validate(api, protocol)

    def test_holdout_must_be_at_least_one_quarter_of_the_sample(self) -> None:
        api = self.api()
        protocol = self.protocol()
        protocol["sampling"].update(
            {"total_cases": 20, "development_cases": 16, "untouched_holdout_cases": 4}
        )

        with self.assertRaisesRegex(api.HistoricalProtocolError, "holdout"):
            self.validate(api, protocol)

    def test_claim_categories_and_case_identifiers_must_not_be_posthoc(self) -> None:
        api = self.api()
        duplicate = self.protocol()
        duplicate["sampling"]["claim_categories"].append(
            duplicate["sampling"]["claim_categories"][0]
        )
        leaked = self.protocol()
        leaked["sampling"]["selected_case_numbers"] = [
            "0000000-00.2026.5.12.0000"
        ]

        with self.assertRaises(api.HistoricalProtocolError):
            self.validate(api, duplicate)
        with self.assertRaises(api.HistoricalProtocolError):
            self.validate(api, leaked)

    def test_acceptance_thresholds_preserve_coverage_and_source_custody(self) -> None:
        api = self.api()
        cases = (
            ("claim_recall", 0.94),
            ("claim_coverage", 0.99),
            ("quotation_support", 0.99),
            ("source_locator_traceability", 0.99),
        )
        for metric, threshold in cases:
            with self.subTest(metric=metric):
                protocol = self.protocol()
                protocol["analysis_plan"]["acceptance_thresholds"][metric] = threshold
                with self.assertRaisesRegex(api.HistoricalProtocolError, metric):
                    self.validate(api, protocol)

    def test_critical_and_high_defects_have_zero_acceptance_budget(self) -> None:
        api = self.api()
        for severity in ("critical", "high"):
            protocol = self.protocol()
            protocol["analysis_plan"]["maximum_defects"][severity] = 1
            with self.subTest(severity=severity):
                with self.assertRaisesRegex(api.HistoricalProtocolError, severity):
                    self.validate(api, protocol)

    def test_blinding_and_disagreement_adjudication_are_mandatory(self) -> None:
        api = self.api()
        cases = []
        not_blind = self.protocol()
        not_blind["review_design"]["reviewer_blinded_to_system_output_origin"] = False
        cases.append(not_blind)
        no_adjudicator = self.protocol()
        no_adjudicator["review_design"]["disagreement_resolution"] = ""
        cases.append(no_adjudicator)

        for protocol in cases:
            with self.subTest(protocol=protocol):
                with self.assertRaises(api.HistoricalProtocolError):
                    self.validate(api, protocol)

    def test_reviewer_form_contains_every_frozen_scoring_field(self) -> None:
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            incomplete = Path(directory) / "review.md"
            incomplete.write_text("# Review\n\ncase_id:\n", encoding="utf-8")

            with self.assertRaisesRegex(api.HistoricalProtocolError, "review form"):
                self.validate(api, self.protocol(), incomplete)

    def test_schema_rejects_outcome_results_inside_the_frozen_protocol(self) -> None:
        api = self.api()
        protocol = self.protocol()
        protocol["outcome_results"] = {"claim_recall": 1.0}

        with self.assertRaisesRegex(api.HistoricalProtocolError, "campo desconhecido"):
            self.validate(api, protocol)


if __name__ == "__main__":
    unittest.main()
