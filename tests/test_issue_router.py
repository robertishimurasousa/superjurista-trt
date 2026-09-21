from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class IssueRouterTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("build_issue_routes")
        except ModuleNotFoundError as error:
            self.fail(f"issue router module is missing: {error}")

    def route(
        self,
        api,
        claim_id="CLM-001",
        *,
        legal=True,
        evidence=True,
        calculation=False,
        procedural=False,
        research_questions=("Which legal rule governs the synthetic issue?",),
        evidence_questions=("Which synthetic evidence resolves the disputed fact?",),
        reason="The claim presents legal and evidentiary issues.",
        abstention_reasons=(),
    ):
        return api.IssueRouteCandidate(
            claim_id=claim_id,
            requires_legal_research=legal,
            requires_evidence_analysis=evidence,
            requires_calculation_review=calculation,
            requires_procedural_review=procedural,
            research_questions=research_questions,
            evidence_questions=evidence_questions,
            route_reason=reason,
            abstention_reasons=abstention_reasons,
        )

    def build(self, api, routes, known_claims=("CLM-001",)):
        return api.build_issue_routes(known_claims, tuple(routes))

    def test_builds_one_deterministic_explainable_route_per_claim(self) -> None:
        api = self.api()
        first = self.route(
            api,
            "CLM-002",
            legal=False,
            evidence=False,
            calculation=True,
            procedural=True,
            research_questions=(),
            evidence_questions=(),
            reason="Calculation and procedural review are required.",
        )
        second = self.route(api, "CLM-001")

        forward = self.build(api, (first, second), ("CLM-002", "CLM-001"))
        reverse = self.build(api, (second, first), ("CLM-001", "CLM-002"))

        self.assertEqual(forward, reverse)
        self.assertEqual(forward["schema_version"], 1)
        self.assertEqual(
            [route["claim_id"] for route in forward["routes"]],
            ["CLM-001", "CLM-002"],
        )
        self.assertEqual(forward["routes"][0]["route_status"], "routed")
        self.assertEqual(forward["routes"][0]["abstention_reasons"], [])

    def test_no_track_route_is_preserved_as_explicit_abstention(self) -> None:
        api = self.api()
        candidate = self.route(
            api,
            legal=False,
            evidence=False,
            research_questions=(),
            evidence_questions=(),
            reason="The available structured inputs do not support a route.",
            abstention_reasons=("insufficient_structured_information",),
        )

        result = self.build(api, (candidate,))

        route = result["routes"][0]
        self.assertEqual(route["route_status"], "abstained")
        self.assertEqual(
            route["abstention_reasons"],
            ["insufficient_structured_information"],
        )

    def test_no_track_route_without_abstention_is_rejected(self) -> None:
        api = self.api()
        candidate = self.route(
            api,
            legal=False,
            evidence=False,
            research_questions=(),
            evidence_questions=(),
        )

        with self.assertRaisesRegex(api.IssueRouteContractViolation, "abstention"):
            self.build(api, (candidate,))

    def test_routed_claim_cannot_carry_abstention_reasons(self) -> None:
        api = self.api()
        candidate = self.route(
            api,
            abstention_reasons=("insufficient_structured_information",),
        )

        with self.assertRaisesRegex(api.IssueRouteContractViolation, "abstention"):
            self.build(api, (candidate,))

    def test_legal_questions_must_match_legal_research_route(self) -> None:
        api = self.api()
        cases = (
            (True, (), "requires at least one research question"),
            (False, ("Unexpected question.",), "must be empty"),
        )
        for required, questions, expected in cases:
            with self.subTest(required=required):
                candidate = self.route(
                    api,
                    legal=required,
                    evidence=True,
                    research_questions=questions,
                )
                with self.assertRaisesRegex(api.IssueRouteContractViolation, expected):
                    self.build(api, (candidate,))

    def test_evidence_questions_must_match_evidence_analysis_route(self) -> None:
        api = self.api()
        cases = (
            (True, (), "requires at least one evidence question"),
            (False, ("Unexpected question.",), "must be empty"),
        )
        for required, questions, expected in cases:
            with self.subTest(required=required):
                candidate = self.route(
                    api,
                    legal=True,
                    evidence=required,
                    evidence_questions=questions,
                )
                with self.assertRaisesRegex(api.IssueRouteContractViolation, expected):
                    self.build(api, (candidate,))

    def test_routes_must_cover_exactly_the_known_claim_manifest(self) -> None:
        api = self.api()
        cases = (
            ((self.route(api, "CLM-001"),), ("CLM-001", "CLM-002"), "CLM-002"),
            ((self.route(api, "CLM-999"),), ("CLM-001",), "CLM-999"),
        )
        for routes, known_claims, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(api.IssueRouteContractViolation, expected):
                    self.build(api, routes, known_claims)

    def test_duplicate_claim_route_is_rejected(self) -> None:
        api = self.api()
        duplicate = self.route(api)

        with self.assertRaisesRegex(api.IssueRouteContractViolation, "claim_id"):
            self.build(api, (duplicate, duplicate))


if __name__ == "__main__":
    unittest.main()
