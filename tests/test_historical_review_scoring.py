from __future__ import annotations

import copy
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PROTOCOL = ROOT / "runtime" / "validation" / "historical-validation-protocol.v1.json"
PROTOCOL_SCHEMA = (
    ROOT / "runtime" / "validation" / "historical-validation-protocol.v1.schema.json"
)
REVIEW_FORM = ROOT / "spec" / "validation" / "historical-blind-review-form.md"
BATCH_SCHEMA = ROOT / "runtime" / "validation" / "historical-review-batch.v1.schema.json"
REPORT_SCHEMA = ROOT / "runtime" / "validation" / "historical-review-report.v1.schema.json"


class HistoricalReviewScoringTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("score_historical_reviews")
        except ModuleNotFoundError as error:
            self.fail(f"historical review scorer is missing: {error}")

    def protocol_digest(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        validator = importlib.import_module("validate_historical_protocol")
        return validator.validate_historical_protocol(
            PROTOCOL,
            PROTOCOL_SCHEMA,
            REVIEW_FORM,
        )["protocol_digest"]

    def review(self, index, *, partition):
        return {
            "case_id": f"CASE-{index:03d}",
            "reviewer_id": "REVIEWER-01",
            "blind_output_id": f"OUTPUT-{index:03d}",
            "sample_partition": partition,
            "claim_id": f"CLAIM-{index:03d}",
            "claim_category": "working_time",
            "claim_present_reference": "yes",
            "claim_present_system": "yes",
            "source_locator_correct": "yes",
            "quotation_supported": "not_applicable",
            "reasoning_congruent": "yes",
            "disposition_congruent": "yes",
            "calculation_criteria_consistent": "not_applicable",
            "severity": "none",
            "defect_stage": "none",
            "defect_code": "",
            "defect_description": "",
            "reviewer_confidence": "high",
            "adjudication_required": "no",
            "unavailable_reason": "",
            "blind_scoring_completed": True,
            "output_origin_withheld": True,
        }

    def batch(self, phase="development"):
        reviews = []
        case_manifest = []
        if phase == "development":
            indexes = range(1, 16)
        else:
            indexes = range(16, 21)
        for index in indexes:
            partition = phase
            review = self.review(index, partition=partition)
            reviews.append(review)
            case_manifest.append(
                {
                    "case_id": review["case_id"],
                    "sample_partition": partition,
                    "blind_output_id": review["blind_output_id"],
                    "reviewer_id": review["reviewer_id"],
                    "expected_claim_ids": [review["claim_id"]],
                    "claim_inventory_frozen_before_scoring": True,
                }
            )
        return {
            "schema_version": 1,
            "protocol_id": "TRT12-HISTORICAL-V1",
            "protocol_digest": self.protocol_digest(),
            "system_revision": "a" * 40,
            "phase": phase,
            "case_manifest": case_manifest,
            "reviews": reviews,
        }

    def score(self, batch):
        return self.api().score_review_batch(
            batch=batch,
            protocol_path=PROTOCOL,
            protocol_schema_path=PROTOCOL_SCHEMA,
            reviewer_form_path=REVIEW_FORM,
            batch_schema_path=BATCH_SCHEMA,
            report_schema_path=REPORT_SCHEMA,
        )

    def test_complete_passing_development_sample_reports_only_its_phase(self):
        report = self.score(self.batch())

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["phase"], "development")
        self.assertEqual(report["system_revision"], "a" * 40)
        self.assertEqual(report["case_count"], 15)
        self.assertEqual(report["claim_review_count"], 15)
        self.assertEqual(
            [partition["name"] for partition in report["partitions"]],
            ["development"],
        )
        self.assertEqual(report["partitions"][0]["case_count"], 15)
        self.assertEqual(report["partitions"][0]["metrics"]["claim_recall"]["percent"], 100)
        self.assertTrue(report["partitions"][0]["accepted"])

    def test_untouched_holdout_is_scored_only_in_its_separate_phase(self):
        report = self.score(self.batch("untouched_holdout"))

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["phase"], "untouched_holdout")
        self.assertEqual(report["case_count"], 5)
        self.assertEqual(
            [partition["name"] for partition in report["partitions"]],
            ["untouched_holdout"],
        )

    def test_result_is_deterministic_when_review_order_changes(self):
        batch = self.batch()
        reversed_batch = copy.deepcopy(batch)
        reversed_batch["case_manifest"].reverse()
        reversed_batch["reviews"].reverse()

        self.assertEqual(self.score(batch), self.score(reversed_batch))

    def test_phase_must_match_its_frozen_case_count(self):
        batch = self.batch()
        batch["reviews"].pop()
        batch["case_manifest"].pop()

        with self.assertRaisesRegex(self.api().HistoricalReviewError, "phase case count"):
            self.score(batch)

    def test_one_batch_cannot_mix_development_and_holdout(self):
        batch = self.batch()
        batch["case_manifest"][0]["sample_partition"] = "untouched_holdout"
        batch["reviews"][0]["sample_partition"] = "untouched_holdout"

        with self.assertRaisesRegex(self.api().HistoricalReviewError, "single frozen phase"):
            self.score(batch)

    def test_duplicate_case_claim_review_is_rejected(self):
        batch = self.batch()
        batch["reviews"].append(copy.deepcopy(batch["reviews"][0]))

        with self.assertRaisesRegex(self.api().HistoricalReviewError, "duplicate review"):
            self.score(batch)

    def test_reviews_must_cover_the_complete_frozen_claim_inventory(self):
        batch = self.batch()
        batch["case_manifest"][0]["expected_claim_ids"].append("CLAIM-EXTRA")

        with self.assertRaisesRegex(self.api().HistoricalReviewError, "claim inventory"):
            self.score(batch)

    def test_protocol_digest_and_frozen_category_are_enforced(self):
        wrong_digest = self.batch()
        wrong_digest["protocol_digest"] = "0" * 64
        with self.assertRaisesRegex(self.api().HistoricalReviewError, "protocol digest"):
            self.score(wrong_digest)

        wrong_category = self.batch()
        wrong_category["reviews"][0]["claim_category"] = "invented_after_review"
        with self.assertRaisesRegex(self.api().HistoricalReviewError, "claim category"):
            self.score(wrong_category)

    def test_blind_attestations_are_mandatory(self):
        batch = self.batch()
        batch["reviews"][0]["output_origin_withheld"] = False

        with self.assertRaisesRegex(self.api().HistoricalReviewError, "blind review"):
            self.score(batch)

    def test_unavailable_value_requires_reason_and_is_never_imputed_as_pass(self):
        batch = self.batch()
        batch["reviews"][0]["source_locator_correct"] = "unavailable"
        with self.assertRaisesRegex(self.api().HistoricalReviewError, "unavailable reason"):
            self.score(batch)

        batch["reviews"][0]["unavailable_reason"] = "Reference page was unreadable."
        report = self.score(batch)
        metric = report["partitions"][0]["metrics"]["source_locator_traceability"]
        self.assertEqual(metric["eligible_count"], 14)
        self.assertEqual(metric["excluded_count"], 1)
        self.assertEqual(metric["percent"], 100)

    def test_critical_or_high_defect_fails_the_partition_and_batch(self):
        for severity in ("critical", "high"):
            with self.subTest(severity=severity):
                batch = self.batch()
                review = batch["reviews"][0]
                review["severity"] = severity
                review["defect_stage"] = "claim_analysis"
                review["defect_code"] = "LEGAL-001"
                review["defect_description"] = "Material claim result is unsupported."
                review["adjudication_required"] = "yes"

                report = self.score(batch)

                self.assertEqual(report["status"], "failed")
                self.assertFalse(report["partitions"][0]["accepted"])
                self.assertEqual(report["partitions"][0]["defects"][severity], 1)
                self.assertIn(
                    {"stage": "claim_analysis", "count": 1},
                    report["partitions"][0]["defects_by_stage"],
                )
                defect = report["partitions"][0]["defect_inventory"][0]
                self.assertEqual(defect["severity"], severity)
                self.assertEqual(defect["stage"], "claim_analysis")
                self.assertEqual(defect["defect_code"], "LEGAL-001")
                self.assertNotIn("defect_description", defect)

    def test_defect_fields_must_be_semantically_consistent(self):
        no_defect = self.batch()
        no_defect["reviews"][0]["defect_code"] = "STYLE-001"
        with self.assertRaisesRegex(self.api().HistoricalReviewError, "severity none"):
            self.score(no_defect)

        material_defect = self.batch()
        material_defect["reviews"][0]["severity"] = "high"
        material_defect["reviews"][0]["defect_stage"] = "claim_analysis"
        material_defect["reviews"][0]["defect_code"] = "LEGAL-001"
        material_defect["reviews"][0]["defect_description"] = "Material error."
        with self.assertRaisesRegex(self.api().HistoricalReviewError, "adjudication"):
            self.score(material_defect)

        missing_stage = self.batch()
        missing_stage["reviews"][0]["severity"] = "medium"
        missing_stage["reviews"][0]["defect_code"] = "EVIDENCE-001"
        missing_stage["reviews"][0]["defect_description"] = "Source locator is incomplete."
        with self.assertRaisesRegex(self.api().HistoricalReviewError, "defect stage"):
            self.score(missing_stage)

    def test_cli_writes_a_schema_valid_report(self):
        module = self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch_path = root / "batch.json"
            report_path = root / "report.json"
            batch_path.write_text(
                json.dumps(self.batch(), ensure_ascii=False),
                encoding="utf-8",
            )

            exit_code = module.main(
                [
                    "--batch",
                    str(batch_path),
                    "--output",
                    str(report_path),
                    "--protocol",
                    str(PROTOCOL),
                    "--protocol-schema",
                    str(PROTOCOL_SCHEMA),
                    "--reviewer-form",
                    str(REVIEW_FORM),
                    "--batch-schema",
                    str(BATCH_SCHEMA),
                    "--report-schema",
                    str(REPORT_SCHEMA),
                ]
            )

            self.assertEqual(exit_code, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")

    def test_report_schema_resolves_local_metric_references(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        schema_api = importlib.import_module("schema_validation")
        schema = json.loads(REPORT_SCHEMA.read_text(encoding="utf-8"))
        report = self.score(self.batch())
        report["partitions"][0]["metrics"]["claim_recall"]["unexpected"] = True

        issues = schema_api.validate_schema_value(report, schema)

        self.assertTrue(any("unknown field: unexpected" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
