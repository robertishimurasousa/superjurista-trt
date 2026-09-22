from __future__ import annotations

import copy
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import tests.test_historical_rerun as rerun_fixtures


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
RERUN_REPORT_SCHEMA = (
    ROOT / "runtime" / "validation" / "historical-rerun-report.v1.schema.json"
)
DOSSIER_REVIEW_SCHEMA = (
    ROOT / "runtime" / "validation" / "historical-dossier-review.v1.schema.json"
)
DOSSIER_SCHEMA = (
    ROOT / "runtime" / "validation" / "historical-acceptance-dossier.v1.schema.json"
)


class HistoricalAcceptanceDossierTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("build_historical_acceptance_dossier")
        except ModuleNotFoundError as error:
            self.fail(f"historical acceptance dossier builder is missing: {error}")

    def evidence(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        fixture = rerun_fixtures.HistoricalRerunTest()
        development, holdout = fixture.reports()
        register = fixture.correction_register(development)
        validator = importlib.import_module("validate_historical_rerun")
        rerun = validator.validate_historical_rerun(
            development_report=development,
            holdout_report=holdout,
            correction_register=register,
            protocol_path=PROTOCOL,
            protocol_schema_path=PROTOCOL_SCHEMA,
            reviewer_form_path=REVIEW_FORM,
            scoring_report_schema_path=SCORING_REPORT_SCHEMA,
            correction_schema_path=(
                ROOT
                / "runtime"
                / "validation"
                / "historical-correction-register.v1.schema.json"
            ),
            rerun_report_schema_path=RERUN_REPORT_SCHEMA,
        )
        return development, holdout, rerun

    def review(self, *, approval_status="pending", recommendation="go_controlled_pilot"):
        decided = approval_status != "pending"
        return {
            "schema_version": 1,
            "reviewer_id": "REVIEWER-LEGAL-01",
            "limitations": [
                "Evidence covers the frozen historical sample, not every future labor claim."
            ],
            "failure_modes": [
                {
                    "failure_mode_id": "FM-001",
                    "stage": "claim_analysis",
                    "severity": "high",
                    "status": "controlled",
                    "description": "Unsupported material claim outcome.",
                    "mitigation": "Fail the gate and require source-linked reanalysis.",
                }
            ],
            "recommendation": recommendation,
            "recommendation_reasons": [
                "The untouched holdout passed the frozen technical gates."
            ],
            "approval": {
                "status": approval_status,
                "approver": "REPOSITORY-OWNER" if decided else "",
                "decision_date": "2026-09-21" if decided else "",
                "conditions": [
                    "One authorized non-sealed case with mandatory human legal review."
                ],
            },
        }

    def build(self, development, holdout, rerun, review):
        return self.api().build_acceptance_dossier(
            development_report=development,
            holdout_report=holdout,
            rerun_report=rerun,
            dossier_review=review,
            protocol_path=PROTOCOL,
            protocol_schema_path=PROTOCOL_SCHEMA,
            reviewer_form_path=REVIEW_FORM,
            scoring_report_schema_path=SCORING_REPORT_SCHEMA,
            rerun_report_schema_path=RERUN_REPORT_SCHEMA,
            dossier_review_schema_path=DOSSIER_REVIEW_SCHEMA,
            dossier_schema_path=DOSSIER_SCHEMA,
        )

    def test_passing_evidence_with_pending_review_builds_a_candidate(self):
        development, holdout, rerun = self.evidence()

        dossier = self.build(development, holdout, rerun, self.review())

        self.assertEqual(dossier["status"], "pending_approval")
        self.assertFalse(dossier["external_actions_allowed"])
        self.assertEqual(dossier["development_results"]["case_count"], 15)
        self.assertEqual(dossier["holdout_results"]["case_count"], 5)
        self.assertEqual(dossier["correction_results"]["required_count"], 1)

    def test_explicit_human_approval_allows_only_a_controlled_local_pilot(self):
        development, holdout, rerun = self.evidence()

        dossier = self.build(
            development,
            holdout,
            rerun,
            self.review(approval_status="approved"),
        )

        self.assertEqual(dossier["status"], "approved_for_controlled_pilot")
        self.assertEqual(dossier["scope"], "trt12_first_instance_local_human_supervised")
        self.assertFalse(dossier["external_actions_allowed"])

    def test_no_go_recommendation_or_rejection_cannot_be_promoted(self):
        development, holdout, rerun = self.evidence()

        no_go = self.build(
            development,
            holdout,
            rerun,
            self.review(recommendation="no_go"),
        )
        rejected = self.build(
            development,
            holdout,
            rerun,
            self.review(approval_status="rejected"),
        )

        self.assertEqual(no_go["status"], "no_go")
        self.assertEqual(rejected["status"], "no_go")

    def test_source_digests_and_protocol_cannot_drift(self):
        development, holdout, rerun = self.evidence()
        tampered = copy.deepcopy(holdout)
        tampered["review_batch_digest"] = "f" * 64

        with self.assertRaisesRegex(self.api().HistoricalDossierError, "holdout digest"):
            self.build(development, tampered, rerun, self.review())

        wrong_protocol = self.review()
        rerun["protocol_digest"] = "0" * 64
        with self.assertRaisesRegex(self.api().HistoricalDossierError, "protocol"):
            self.build(development, holdout, rerun, wrong_protocol)

    def test_go_recommendation_rejects_material_holdout_defects(self):
        development, holdout, rerun = self.evidence()
        holdout["partitions"][0]["defects"]["high"] = 1
        rerun["holdout_report_digest"] = rerun_fixtures.digest(holdout)

        with self.assertRaisesRegex(self.api().HistoricalDossierError, "material holdout"):
            self.build(development, holdout, rerun, self.review())

    def test_approval_identity_and_date_are_required_only_for_a_decision(self):
        development, holdout, rerun = self.evidence()
        approved = self.review(approval_status="approved")
        approved["approval"]["approver"] = ""
        with self.assertRaisesRegex(self.api().HistoricalDossierError, "approval identity"):
            self.build(development, holdout, rerun, approved)

        pending = self.review()
        pending["approval"]["decision_date"] = "2026-09-21"
        with self.assertRaisesRegex(self.api().HistoricalDossierError, "pending approval"):
            self.build(development, holdout, rerun, pending)

    def test_cli_writes_a_schema_valid_candidate_dossier(self):
        module = self.api()
        development, holdout, rerun = self.evidence()
        review = self.review()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "development": root / "development.json",
                "holdout": root / "holdout.json",
                "rerun": root / "rerun.json",
                "review": root / "review.json",
                "output": root / "dossier.json",
            }
            for name, value in (
                ("development", development),
                ("holdout", holdout),
                ("rerun", rerun),
                ("review", review),
            ):
                paths[name].write_text(json.dumps(value), encoding="utf-8")

            exit_code = module.main(
                [
                    "--development-report",
                    str(paths["development"]),
                    "--holdout-report",
                    str(paths["holdout"]),
                    "--rerun-report",
                    str(paths["rerun"]),
                    "--dossier-review",
                    str(paths["review"]),
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
                    "--rerun-report-schema",
                    str(RERUN_REPORT_SCHEMA),
                    "--dossier-review-schema",
                    str(DOSSIER_REVIEW_SCHEMA),
                    "--dossier-schema",
                    str(DOSSIER_SCHEMA),
                ]
            )

            self.assertEqual(exit_code, 0)
            dossier = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual(dossier["status"], "pending_approval")


if __name__ == "__main__":
    unittest.main()
