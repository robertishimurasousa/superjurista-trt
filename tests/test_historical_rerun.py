from __future__ import annotations

import copy
import hashlib
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
SCORING_REPORT_SCHEMA = (
    ROOT / "runtime" / "validation" / "historical-review-report.v1.schema.json"
)
CORRECTION_SCHEMA = (
    ROOT / "runtime" / "validation" / "historical-correction-register.v1.schema.json"
)
RERUN_REPORT_SCHEMA = (
    ROOT / "runtime" / "validation" / "historical-rerun-report.v1.schema.json"
)


def digest(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def metric(*, count, threshold, accepted=True):
    return {
        "numerator": count,
        "eligible_count": count,
        "excluded_count": 0,
        "not_applicable_count": 0,
        "percent": 100,
        "threshold": threshold,
        "accepted": accepted if threshold is not None else None,
    }


class HistoricalRerunTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("validate_historical_rerun")
        except ModuleNotFoundError as error:
            self.fail(f"historical rerun validator is missing: {error}")

    def protocol_evidence(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        validator = importlib.import_module("validate_historical_protocol")
        return validator.validate_historical_protocol(
            PROTOCOL,
            PROTOCOL_SCHEMA,
            REVIEW_FORM,
        )

    def partition(self, *, phase, case_count, defect=None):
        defect_inventory = [] if defect is None else [defect]
        defects = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        defects_by_stage = []
        if defect is not None:
            defects[defect["severity"]] = 1
            defects_by_stage = [{"stage": defect["stage"], "count": 1}]
        accepted = defects["critical"] == 0 and defects["high"] == 0
        return {
            "name": phase,
            "case_count": case_count,
            "claim_review_count": case_count,
            "unavailable_review_count": 0,
            "metrics": {
                "claim_recall": metric(count=case_count, threshold=95),
                "claim_coverage": metric(count=case_count, threshold=100),
                "quotation_support": metric(count=case_count, threshold=100),
                "source_locator_traceability": metric(count=case_count, threshold=100),
                "outcome_congruence": metric(count=case_count, threshold=None),
                "calculation_criteria_consistency": metric(
                    count=case_count,
                    threshold=None,
                ),
            },
            "defects": defects,
            "defects_by_stage": defects_by_stage,
            "defect_inventory": defect_inventory,
            "accepted": accepted,
        }

    def reports(self, *, with_material_defect=True):
        evidence = self.protocol_evidence()
        defect = None
        if with_material_defect:
            defect = {
                "defect_id": "DEFECT-0123456789ABCDEF",
                "case_id": "CASE-001",
                "claim_id": "CLAIM-001",
                "severity": "high",
                "stage": "claim_analysis",
                "defect_code": "LEGAL-001",
            }
        development_partition = self.partition(
            phase="development",
            case_count=15,
            defect=defect,
        )
        holdout_partition = self.partition(
            phase="untouched_holdout",
            case_count=5,
        )
        development = {
            "schema_version": 1,
            "protocol_id": evidence["protocol_id"],
            "protocol_digest": evidence["protocol_digest"],
            "review_batch_digest": "b" * 64,
            "system_revision": "a" * 40,
            "phase": "development",
            "status": "failed" if with_material_defect else "passed",
            "case_count": 15,
            "claim_review_count": 15,
            "partitions": [development_partition],
        }
        holdout = {
            "schema_version": 1,
            "protocol_id": evidence["protocol_id"],
            "protocol_digest": evidence["protocol_digest"],
            "review_batch_digest": "c" * 64,
            "system_revision": "d" * 40,
            "phase": "untouched_holdout",
            "status": "passed",
            "case_count": 5,
            "claim_review_count": 5,
            "partitions": [holdout_partition],
        }
        return development, holdout

    def correction_register(self, development, *, with_material_defect=True):
        evidence = self.protocol_evidence()
        corrections = []
        if with_material_defect:
            corrections.append(
                {
                    "defect_id": "DEFECT-0123456789ABCDEF",
                    "severity": "high",
                    "stage": "claim_analysis",
                    "defect_code": "LEGAL-001",
                    "correction_commit": "e" * 40,
                    "remediation_summary": "Reject unsupported material claim outcomes.",
                    "regression_test": "tests.test_claim_decision_builder",
                    "regression_result": "passed",
                    "status": "closed",
                }
            )
        return {
            "schema_version": 1,
            "protocol_id": evidence["protocol_id"],
            "protocol_digest": evidence["protocol_digest"],
            "development_report_digest": digest(development),
            "baseline_revision": "a" * 40,
            "corrected_revision": "d" * 40,
            "corrections": corrections,
        }

    def validate(self, development, holdout, register):
        return self.api().validate_historical_rerun(
            development_report=development,
            holdout_report=holdout,
            correction_register=register,
            protocol_path=PROTOCOL,
            protocol_schema_path=PROTOCOL_SCHEMA,
            reviewer_form_path=REVIEW_FORM,
            scoring_report_schema_path=SCORING_REPORT_SCHEMA,
            correction_schema_path=CORRECTION_SCHEMA,
            rerun_report_schema_path=RERUN_REPORT_SCHEMA,
        )

    def test_closed_material_corrections_and_passing_holdout_are_accepted(self):
        development, holdout = self.reports()
        report = self.validate(
            development,
            holdout,
            self.correction_register(development),
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["required_correction_count"], 1)
        self.assertEqual(report["closed_correction_count"], 1)
        self.assertEqual(report["development_case_count"], 15)
        self.assertEqual(report["holdout_case_count"], 5)
        self.assertEqual(report["corrected_revision"], "d" * 40)

    def test_every_critical_or_high_defect_requires_one_correction(self):
        development, holdout = self.reports()
        register = self.correction_register(development)
        register["corrections"] = []

        with self.assertRaisesRegex(self.api().HistoricalRerunError, "material defect"):
            self.validate(development, holdout, register)

    def test_correction_must_match_defect_custody_and_be_closed(self):
        development, holdout = self.reports()
        register = self.correction_register(development)
        register["corrections"][0]["stage"] = "drafting"
        with self.assertRaisesRegex(self.api().HistoricalRerunError, "defect custody"):
            self.validate(development, holdout, register)

        register = self.correction_register(development)
        register["corrections"][0]["status"] = "open"
        with self.assertRaisesRegex(self.api().HistoricalRerunError, "closed"):
            self.validate(development, holdout, register)

    def test_reports_must_preserve_protocol_revision_and_phase_boundaries(self):
        development, holdout = self.reports()
        register = self.correction_register(development)

        wrong_protocol = copy.deepcopy(holdout)
        wrong_protocol["protocol_digest"] = "0" * 64
        with self.assertRaisesRegex(self.api().HistoricalRerunError, "protocol"):
            self.validate(development, wrong_protocol, register)

        wrong_phase = copy.deepcopy(holdout)
        wrong_phase["phase"] = "development"
        wrong_phase["partitions"][0]["name"] = "development"
        with self.assertRaisesRegex(self.api().HistoricalRerunError, "holdout phase"):
            self.validate(development, wrong_phase, register)

        wrong_revision = copy.deepcopy(register)
        wrong_revision["corrected_revision"] = "f" * 40
        with self.assertRaisesRegex(self.api().HistoricalRerunError, "corrected revision"):
            self.validate(development, holdout, wrong_revision)

    def test_holdout_must_pass_and_remain_distinct_from_development(self):
        development, holdout = self.reports()
        register = self.correction_register(development)

        failed = copy.deepcopy(holdout)
        failed_coverage = failed["partitions"][0]["metrics"]["claim_coverage"]
        failed_coverage["numerator"] = 0
        failed_coverage["percent"] = 0
        failed_coverage["accepted"] = False
        failed["status"] = "failed"
        failed["partitions"][0]["accepted"] = False
        with self.assertRaisesRegex(self.api().HistoricalRerunError, "holdout must pass"):
            self.validate(development, failed, register)

        reused = copy.deepcopy(holdout)
        reused["review_batch_digest"] = development["review_batch_digest"]
        with self.assertRaisesRegex(self.api().HistoricalRerunError, "distinct review batches"):
            self.validate(development, reused, register)

    def test_tampered_metric_cannot_be_promoted_by_the_accepted_flag(self):
        development, holdout = self.reports()
        register = self.correction_register(development)
        coverage = holdout["partitions"][0]["metrics"]["claim_coverage"]
        coverage["numerator"] = 0
        coverage["percent"] = 0

        with self.assertRaisesRegex(self.api().HistoricalRerunError, "metric acceptance"):
            self.validate(development, holdout, register)

    def test_no_material_development_defect_requires_no_artificial_correction(self):
        development, holdout = self.reports(with_material_defect=False)
        register = self.correction_register(development, with_material_defect=False)

        report = self.validate(development, holdout, register)

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["required_correction_count"], 0)
        self.assertEqual(report["closed_correction_count"], 0)

    def test_cli_writes_a_schema_valid_rerun_report(self):
        module = self.api()
        development, holdout = self.reports()
        register = self.correction_register(development)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "development": root / "development.json",
                "holdout": root / "holdout.json",
                "corrections": root / "corrections.json",
                "output": root / "rerun.json",
            }
            for name, value in (
                ("development", development),
                ("holdout", holdout),
                ("corrections", register),
            ):
                paths[name].write_text(json.dumps(value), encoding="utf-8")

            exit_code = module.main(
                [
                    "--development-report",
                    str(paths["development"]),
                    "--holdout-report",
                    str(paths["holdout"]),
                    "--correction-register",
                    str(paths["corrections"]),
                    "--output",
                    str(paths["output"]),
                    "--protocol",
                    str(PROTOCOL),
                    "--protocol-schema",
                    str(PROTOCOL_SCHEMA),
                    "--reviewer-form",
                    str(REVIEW_FORM),
                    "--scoring-report-schema",
                    str(SCORING_REPORT_SCHEMA),
                    "--correction-schema",
                    str(CORRECTION_SCHEMA),
                    "--rerun-report-schema",
                    str(RERUN_REPORT_SCHEMA),
                ]
            )

            self.assertEqual(exit_code, 0)
            result = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "passed")


if __name__ == "__main__":
    unittest.main()
