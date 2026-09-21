from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ISSUE_ROUTE_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "issue-route.v1.schema.json"
)
WORK_PLAN_SCHEMA = (
    ROOT / "runtime" / "pipelines" / "conditional-work-plan.v1.schema.json"
)


def route(
    claim_id,
    *,
    legal=False,
    evidence=False,
    calculation=False,
    procedural=False,
    status=None,
    research_questions=None,
    evidence_questions=None,
    abstention_reasons=None,
):
    flags = (legal, evidence, calculation, procedural)
    routed = any(flags)
    return {
        "claim_id": claim_id,
        "route_status": status or ("routed" if routed else "abstained"),
        "requires_legal_research": legal,
        "requires_evidence_analysis": evidence,
        "requires_calculation_review": calculation,
        "requires_procedural_review": procedural,
        "research_questions": (
            research_questions
            if research_questions is not None
            else ([f"Research question for {claim_id}."] if legal else [])
        ),
        "evidence_questions": (
            evidence_questions
            if evidence_questions is not None
            else ([f"Evidence question for {claim_id}."] if evidence else [])
        ),
        "route_reason": f"Route reason for {claim_id}.",
        "abstention_reasons": (
            abstention_reasons
            if abstention_reasons is not None
            else ([] if routed else ["insufficient_structured_information"])
        ),
    }


def issue_routes(*routes):
    return {"schema_version": 1, "routes": list(routes)}


class ConditionalWorkPlanTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("build_conditional_work_plan")
        except ModuleNotFoundError as error:
            self.fail(f"conditional work planner module is missing: {error}")

    def build(self, module, artifact):
        return module.build_conditional_work_plan(
            artifact,
            issue_route_schema=ISSUE_ROUTE_SCHEMA,
            work_plan_schema=WORK_PLAN_SCHEMA,
        )

    def test_dispatches_only_the_tracks_enabled_for_each_claim(self) -> None:
        module = self.api()
        plan = self.build(
            module,
            issue_routes(
                route("CLM-001", legal=True, evidence=True),
                route("CLM-002", calculation=True),
            ),
        )

        dispatches = module.iter_dispatches(plan)

        self.assertEqual(
            [(item.claim_id, item.track) for item in dispatches],
            [
                ("CLM-001", "legal_research"),
                ("CLM-001", "evidence_analysis"),
                ("CLM-002", "calculation_review"),
            ],
        )
        self.assertNotIn("procedural_review", [item.track for item in dispatches])

    def test_explicit_abstention_is_valid_and_never_dispatched(self) -> None:
        module = self.api()
        plan = self.build(module, issue_routes(route("CLM-001")))

        dispatches = module.iter_dispatches(plan)

        self.assertEqual(dispatches, ())
        self.assertEqual(plan["claims"][0]["route_status"], "abstained")
        self.assertEqual(plan["claims"][0]["work_items"], [])
        self.assertEqual(
            plan["claims"][0]["abstention_reasons"],
            ["insufficient_structured_information"],
        )

    def test_mixed_fixture_preserves_routed_and_abstained_claims(self) -> None:
        module = self.api()
        plan = self.build(
            module,
            issue_routes(
                route("CLM-002"),
                route("CLM-001", procedural=True),
            ),
        )

        self.assertEqual(
            [item["claim_id"] for item in plan["claims"]],
            ["CLM-001", "CLM-002"],
        )
        self.assertEqual(plan["claims"][1]["route_status"], "abstained")
        self.assertEqual(
            [(item.claim_id, item.track) for item in module.iter_dispatches(plan)],
            [("CLM-001", "procedural_review")],
        )

    def test_work_identifiers_and_output_are_input_order_independent(self) -> None:
        module = self.api()
        first = route("CLM-001", legal=True, calculation=True)
        second = route("CLM-002", evidence=True, procedural=True)

        forward = self.build(module, issue_routes(first, second))
        reverse = self.build(module, issue_routes(second, first))

        self.assertEqual(forward, reverse)
        self.assertEqual(
            [item.work_id for item in module.iter_dispatches(forward)],
            [
                "WRK-CLM-001-LEGAL",
                "WRK-CLM-001-CALCULATION",
                "WRK-CLM-002-EVIDENCE",
                "WRK-CLM-002-PROCEDURAL",
            ],
        )

    def test_route_status_must_match_track_flags(self) -> None:
        module = self.api()
        invalid = issue_routes(route("CLM-001", legal=True, status="abstained"))

        with self.assertRaisesRegex(module.ConditionalWorkPlanError, "route_status"):
            self.build(module, invalid)

    def test_abstention_requires_reasons_and_forbids_questions(self) -> None:
        module = self.api()
        cases = (
            route("CLM-001", abstention_reasons=[]),
            route("CLM-001", research_questions=["Unexpected question."]),
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    module.ConditionalWorkPlanError,
                    "abstention|questions",
                ):
                    self.build(module, issue_routes(invalid))

    def test_question_lists_must_match_legal_and_evidence_tracks(self) -> None:
        module = self.api()
        cases = (
            route("CLM-001", legal=True, research_questions=[]),
            route("CLM-001", evidence=True, evidence_questions=[]),
            route("CLM-001", research_questions=["Unexpected question."]),
            route("CLM-001", evidence_questions=["Unexpected question."]),
        )
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(module.ConditionalWorkPlanError, "questions"):
                    self.build(module, issue_routes(invalid))

    def test_duplicate_claim_route_is_rejected(self) -> None:
        module = self.api()
        repeated = route("CLM-001", legal=True)

        with self.assertRaisesRegex(module.ConditionalWorkPlanError, "duplicate claim"):
            self.build(module, issue_routes(repeated, copy.deepcopy(repeated)))

    def test_dispatch_rejects_a_routed_claim_without_work_items(self) -> None:
        module = self.api()
        plan = self.build(module, issue_routes(route("CLM-001", legal=True)))
        plan["claims"][0]["work_items"] = []

        with self.assertRaisesRegex(module.ConditionalWorkPlanError, "routed claim"):
            module.iter_dispatches(plan)

    def test_invalid_issue_route_contract_fails_before_planning(self) -> None:
        module = self.api()
        invalid = issue_routes(route("CLM-001", legal=True))
        invalid["routes"][0]["unexpected"] = True

        with self.assertRaisesRegex(module.ConditionalWorkPlanError, "issue-route contract"):
            self.build(module, invalid)

    def test_output_satisfies_the_versioned_work_plan_schema(self) -> None:
        module = self.api()
        schema_api = importlib.import_module("schema_validation")
        plan = self.build(
            module,
            issue_routes(
                route("CLM-001", legal=True, procedural=True),
                route("CLM-002"),
            ),
        )
        schema = schema_api.load_json(WORK_PLAN_SCHEMA, "conditional work plan schema")

        self.assertEqual(schema_api.validate_schema_value(plan, schema), [])


if __name__ == "__main__":
    unittest.main()
