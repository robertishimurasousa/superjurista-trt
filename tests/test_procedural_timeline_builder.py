from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCHEMA = ROOT / "runtime" / "contracts" / "schemas" / "procedural-timeline.v1.schema.json"


class ProceduralTimelineBuilderTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("build_procedural_timeline")
        except ModuleNotFoundError as error:
            self.fail(f"procedural timeline builder module is missing: {error}")

    def segments(self):
        return {
            "schema_version": 1,
            "segmentation_method": "pje_pdf_outline",
            "source_pdf": {"sha256": "a" * 64, "page_count": 5},
            "documents": [
                {
                    "document_id": "DOC-001",
                    "provider_reference": "abc1234",
                    "provider_type": "Petição Inicial",
                    "filed_on": "2026-02-01",
                    "page_start": 1,
                    "page_end": 2,
                },
                {
                    "document_id": "DOC-002",
                    "provider_reference": "def5678",
                    "provider_type": "Contestação",
                    "filed_on": "2026-02-03",
                    "page_start": 3,
                    "page_end": 4,
                },
                {
                    "document_id": "DOC-003",
                    "provider_reference": "123abcd",
                    "provider_type": "Certidão",
                    "filed_on": "2026-02-04",
                    "page_start": 5,
                    "page_end": 5,
                },
            ],
        }

    def classification(self):
        return {
            "schema_version": 1,
            "classifier_version": 1,
            "documents": [
                {
                    "document_id": "DOC-001",
                    "document_type": "initial_pleading",
                    "classification_status": "classified",
                    "matched_rule_ids": ["initial-pleading"],
                    "reason_code": "matched_rule",
                },
                {
                    "document_id": "DOC-002",
                    "document_type": "defense",
                    "classification_status": "classified",
                    "matched_rule_ids": ["defense"],
                    "reason_code": "matched_rule",
                },
                {
                    "document_id": "DOC-003",
                    "document_type": "unknown",
                    "classification_status": "unknown",
                    "matched_rule_ids": [],
                    "reason_code": "no_matching_rule",
                },
            ],
        }

    def test_builds_source_linked_event_for_every_segment(self) -> None:
        api = self.api()

        result = api.build_procedural_timeline(
            self.segments(),
            self.classification(),
            schema_path=SCHEMA,
        )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(
            result["events"],
            [
                {
                    "event_id": "EVT-001",
                    "event_date": "2026-02-01",
                    "event_type": "case_filed",
                    "summary": "Initial pleading filed.",
                    "source_document_id": "DOC-001",
                    "source_locator": "pages 1-2",
                },
                {
                    "event_id": "EVT-002",
                    "event_date": "2026-02-03",
                    "event_type": "defense_filed",
                    "summary": "Defense filed.",
                    "source_document_id": "DOC-002",
                    "source_locator": "pages 3-4",
                },
                {
                    "event_id": "EVT-003",
                    "event_date": "2026-02-04",
                    "event_type": "unclassified_document_filed",
                    "summary": "Document event requires human review.",
                    "source_document_id": "DOC-003",
                    "source_locator": "page 5",
                },
            ],
        )
        self.assertEqual(
            result["gaps"],
            [{"subject_id": "DOC-003", "reason_code": "unclassified_document"}],
        )
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("Petição Inicial", serialized)
        self.assertNotIn("abc1234", serialized)

    def test_maps_each_supported_document_type_to_labor_event_vocabulary(self) -> None:
        api = self.api()
        mappings = (
            ("initial_pleading", "case_filed"),
            ("defense", "defense_filed"),
            ("reply", "reply_filed"),
            ("hearing_record", "hearing_held"),
            ("expert_report", "expert_report_filed"),
            ("documentary_evidence", "evidence_filed"),
            ("calculations", "calculations_filed"),
            ("settlement", "settlement_filed"),
            ("procedural_order", "procedural_order_issued"),
            ("interlocutory_decision", "interlocutory_decision_issued"),
            ("judgment", "judgment_issued"),
            ("appeal", "appeal_filed"),
            ("other_petition", "petition_filed"),
        )
        segments = {
            "schema_version": 1,
            "segmentation_method": "pje_pdf_outline",
            "source_pdf": {"sha256": "b" * 64, "page_count": len(mappings)},
            "documents": [
                {
                    "document_id": f"DOC-{index:03d}",
                    "provider_reference": f"{index:07x}",
                    "provider_type": "Synthetic provider label",
                    "filed_on": f"2026-02-{index:02d}",
                    "page_start": index,
                    "page_end": index,
                }
                for index in range(1, len(mappings) + 1)
            ],
        }
        classification = {
            "schema_version": 1,
            "classifier_version": 1,
            "documents": [
                {
                    "document_id": f"DOC-{index:03d}",
                    "document_type": document_type,
                    "classification_status": "classified",
                    "matched_rule_ids": ["synthetic-rule"],
                    "reason_code": "matched_rule",
                }
                for index, (document_type, _) in enumerate(mappings, 1)
            ],
        }

        result = api.build_procedural_timeline(
            segments,
            classification,
            schema_path=SCHEMA,
        )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["gaps"], [])
        self.assertEqual(
            [event["event_type"] for event in result["events"]],
            [event_type for _, event_type in mappings],
        )

    def test_rejects_missing_extra_or_duplicate_document_custody(self) -> None:
        api = self.api()
        missing = self.classification()
        missing["documents"] = missing["documents"][:-1]
        extra = self.classification()
        extra["documents"].append(
            {
                "document_id": "DOC-999",
                "document_type": "other_petition",
                "classification_status": "classified",
                "matched_rule_ids": ["other-petition"],
                "reason_code": "matched_rule",
            }
        )
        duplicate = self.classification()
        duplicate["documents"].append(dict(duplicate["documents"][0]))

        for classification in (missing, extra, duplicate):
            with self.subTest(classification=classification):
                with self.assertRaises(api.ProceduralTimelineError):
                    api.build_procedural_timeline(
                        self.segments(),
                        classification,
                        schema_path=SCHEMA,
                    )

    def test_preserves_classification_conflict_as_a_distinct_review_gap(self) -> None:
        api = self.api()
        classification = self.classification()
        classification["documents"][2].update(
            {
                "classification_status": "conflict",
                "matched_rule_ids": ["synthetic-a", "synthetic-b"],
                "reason_code": "multiple_rules_matched",
            }
        )

        result = api.build_procedural_timeline(
            self.segments(),
            classification,
            schema_path=SCHEMA,
        )

        self.assertEqual(
            result["gaps"],
            [{"subject_id": "DOC-003", "reason_code": "classification_conflict"}],
        )

    def test_rejects_duplicate_segment_document_identifiers(self) -> None:
        api = self.api()
        segments = self.segments()
        segments["documents"].append(dict(segments["documents"][0]))

        with self.assertRaises(api.ProceduralTimelineError):
            api.build_procedural_timeline(
                segments,
                self.classification(),
                schema_path=SCHEMA,
            )

    def test_rejects_inconsistent_classification_status_and_type(self) -> None:
        api = self.api()
        scenarios = (
            ("classified", "unknown"),
            ("unknown", "defense"),
            ("conflict", "defense"),
        )
        for status, document_type in scenarios:
            with self.subTest(status=status, document_type=document_type):
                classification = self.classification()
                classification["documents"][2].update(
                    {
                        "classification_status": status,
                        "document_type": document_type,
                    }
                )
                with self.assertRaisesRegex(
                    api.ProceduralTimelineError,
                    "classification status and document type are inconsistent",
                ):
                    api.build_procedural_timeline(
                        self.segments(),
                        classification,
                        schema_path=SCHEMA,
                    )

    def test_writes_protected_timeline_only_outside_repository(self) -> None:
        api = self.api()
        timeline = api.build_procedural_timeline(
            self.segments(),
            self.classification(),
            schema_path=SCHEMA,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            protected_output = root / "protected-output"
            protected_output.mkdir()

            written = api.write_timeline_artifact(
                timeline,
                output_dir=protected_output,
                repository_root=repository,
            )

            self.assertEqual(written.name, "procedural-timeline.json")
            self.assertEqual(written.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(written.read_text()), timeline)
            with self.assertRaisesRegex(api.ProceduralTimelineError, "already exists"):
                api.write_timeline_artifact(
                    timeline,
                    output_dir=protected_output,
                    repository_root=repository,
                )

            repository_output = repository / "output"
            repository_output.mkdir()
            with self.assertRaisesRegex(api.ProceduralTimelineError, "outside repository"):
                api.write_timeline_artifact(
                    timeline,
                    output_dir=repository_output,
                    repository_root=repository,
                )

    def test_cli_writes_timeline_and_reports_only_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            output = root / "protected-output"
            output.mkdir()
            segments_path = root / "document-segments.json"
            classification_path = root / "document-classification.json"
            segments_path.write_text(json.dumps(self.segments()), encoding="utf-8")
            classification_path.write_text(
                json.dumps(self.classification()),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_procedural_timeline.py"),
                    "--segments",
                    str(segments_path),
                    "--classification",
                    str(classification_path),
                    "--output",
                    str(output),
                    "--repository-root",
                    str(repository),
                    "--schema",
                    str(SCHEMA),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                completed.stdout.strip(),
                "[OK] procedural timeline: events=3 gaps=1 status=partial",
            )
            self.assertNotIn("Petição Inicial", completed.stdout)
            self.assertTrue((output / "procedural-timeline.json").is_file())


if __name__ == "__main__":
    unittest.main()
