from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class LaborReportBuilderTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("build_labor_report")
        except ModuleNotFoundError as error:
            self.fail(f"labor report builder module is missing: {error}")

    def source(self, api, document_id, locator):
        return api.SourceReference(document_id=document_id, locator=locator)

    def case_context(self):
        return {
            "schema_version": 1,
            "case_number": "0000000-00.2026.5.12.0000",
            "court": "TRT12",
            "instance": 1,
            "phase": "knowledge",
            "procedure": "ordinary",
            "court_unit": "Synthetic Labor Court",
            "confidentiality": "public_or_authorized",
            "source_manifest": "document-index.json",
        }

    def complete_candidates(self, api):
        parties = (
            api.PartyCandidate(
                party_id="PTY-002",
                role="respondent",
                display_name="Synthetic Respondent",
                source=self.source(api, "DOC-002", "page 1, header"),
            ),
            api.PartyCandidate(
                party_id="PTY-001",
                role="claimant",
                display_name="Synthetic Claimant",
                source=self.source(api, "DOC-001", "page 1, header"),
            ),
        )
        timeline = (
            api.TimelineEventCandidate(
                event_id="EVT-002",
                event_date="2026-02-10",
                event_type="defense_filed",
                summary="Synthetic defense was filed.",
                source=self.source(api, "DOC-002", "page 1"),
            ),
            api.TimelineEventCandidate(
                event_id="EVT-001",
                event_date="2026-01-10",
                event_type="case_filed",
                summary="Synthetic case was filed.",
                source=self.source(api, "DOC-001", "page 1"),
            ),
        )
        positions = (
            api.PositionCandidate(
                position_id="POS-002",
                kind="defense",
                label="overtime",
                summary="Synthetic denial of unpaid overtime.",
                source=self.source(api, "DOC-002", "pages 2-3"),
            ),
            api.PositionCandidate(
                position_id="POS-001",
                kind="claim",
                label="overtime",
                summary="Synthetic allegation of unpaid overtime.",
                source=self.source(api, "DOC-001", "pages 4-5"),
            ),
        )
        return parties, timeline, positions

    def test_builds_deterministic_report_with_source_locators(self) -> None:
        api = self.api()
        parties, timeline, positions = self.complete_candidates(api)
        phase = api.PhaseAssessment(
            phase="knowledge",
            status="identified",
            source=self.source(api, "DOC-001", "page 1, case metadata"),
        )

        forward = api.build_labor_report(
            self.case_context(),
            ("DOC-001", "DOC-002"),
            parties,
            phase,
            timeline,
            positions,
        )
        reverse = api.build_labor_report(
            self.case_context(),
            ("DOC-002", "DOC-001"),
            tuple(reversed(parties)),
            phase,
            tuple(reversed(timeline)),
            tuple(reversed(positions)),
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(
            [party["party_id"] for party in forward["parties"]],
            ["PTY-001", "PTY-002"],
        )
        self.assertEqual(
            [event["event_id"] for event in forward["timeline"]],
            ["EVT-001", "EVT-002"],
        )
        self.assertEqual(
            [position["position_id"] for position in forward["positions"]],
            ["POS-001", "POS-002"],
        )
        self.assertEqual(forward["review_gaps"], [])
        self.assertEqual(
            forward["positions"][0]["source_locator"],
            "pages 4-5",
        )

    def test_unknown_phase_and_missing_defense_remain_explicit(self) -> None:
        api = self.api()
        party = api.PartyCandidate(
            party_id="PTY-001",
            role="claimant",
            display_name="Synthetic Claimant",
            source=self.source(api, "DOC-001", "page 1"),
        )
        claim = api.PositionCandidate(
            position_id="POS-001",
            kind="claim",
            label="overtime",
            summary="Synthetic allegation.",
            source=self.source(api, "DOC-001", "page 4"),
        )

        result = api.build_labor_report(
            self.case_context(),
            ("DOC-001",),
            (party,),
            api.PhaseAssessment(
                phase="unknown",
                status="needs_human_review",
                source=None,
            ),
            (),
            (claim,),
        )

        self.assertEqual(
            result["procedural_phase"],
            {
                "phase": "unknown",
                "status": "needs_human_review",
                "source_document_id": None,
                "source_locator": None,
            },
        )
        self.assertEqual(
            result["review_gaps"],
            ["missing_defense_position", "unknown_phase"],
        )

    def test_rejects_reference_outside_known_document_manifest(self) -> None:
        api = self.api()
        party = api.PartyCandidate(
            party_id="PTY-001",
            role="claimant",
            display_name="Synthetic Claimant",
            source=self.source(api, "DOC-999", "page 1"),
        )

        with self.assertRaisesRegex(api.LaborReportContractViolation, "DOC-999"):
            api.build_labor_report(
                self.case_context(),
                ("DOC-001",),
                (party,),
                api.PhaseAssessment(
                    phase="unknown",
                    status="needs_human_review",
                    source=None,
                ),
                (),
                (),
            )

    def test_duplicate_stable_identifiers_are_rejected(self) -> None:
        api = self.api()
        duplicate = api.PartyCandidate(
            party_id="PTY-001",
            role="claimant",
            display_name="Synthetic Claimant",
            source=self.source(api, "DOC-001", "page 1"),
        )

        with self.assertRaisesRegex(api.LaborReportContractViolation, "party_id"):
            api.build_labor_report(
                self.case_context(),
                ("DOC-001",),
                (duplicate, duplicate),
                api.PhaseAssessment(
                    phase="unknown",
                    status="needs_human_review",
                    source=None,
                ),
                (),
                (),
            )

    def test_identified_phase_requires_a_source_reference(self) -> None:
        api = self.api()

        with self.assertRaisesRegex(api.LaborReportContractViolation, "identified phase"):
            api.build_labor_report(
                self.case_context(),
                ("DOC-001",),
                (),
                api.PhaseAssessment(
                    phase="knowledge",
                    status="identified",
                    source=None,
                ),
                (),
                (),
            )

    def test_builder_does_not_mutate_case_context(self) -> None:
        api = self.api()
        context = self.case_context()
        original = copy.deepcopy(context)

        result = api.build_labor_report(
            context,
            ("DOC-001",),
            (),
            api.PhaseAssessment(
                phase="unknown",
                status="needs_human_review",
                source=None,
            ),
            (),
            (),
        )

        self.assertEqual(context, original)
        self.assertIsNot(result["case_context"], context)

    def test_case_context_must_satisfy_existing_contract_boundaries(self) -> None:
        api = self.api()
        invalid_values = {
            "instance": True,
            "procedure": "Ordinary Procedure",
            "confidentiality": "public",
            "source_manifest": "document-index.txt",
        }

        for field, value in invalid_values.items():
            with self.subTest(field=field):
                context = self.case_context()
                context[field] = value
                with self.assertRaisesRegex(api.LaborReportContractViolation, field):
                    api.build_labor_report(
                        context,
                        ("DOC-001",),
                        (),
                        api.PhaseAssessment(
                            phase="unknown",
                            status="needs_human_review",
                            source=None,
                        ),
                        (),
                        (),
                    )


if __name__ == "__main__":
    unittest.main()
