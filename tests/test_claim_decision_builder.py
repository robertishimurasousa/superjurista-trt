from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class ClaimDecisionBuilderTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("build_claim_decisions")
        except ModuleNotFoundError as error:
            self.fail(f"claim decision builder module is missing: {error}")

    def analysis(
        self,
        api,
        analysis_id="ANL-001",
        claim_id="CLM-001",
        *,
        outcome="granted",
        facts=("Synthetic fact found.",),
        evidence_ids=("EVD-001",),
        evidence_assessment=("Synthetic evidence supports the fact.",),
        rules=("RULE-001",),
        precedents=(),
        reasoning="Synthetic reasoning connects facts, evidence, and rule.",
        limitations=(),
    ):
        return api.ClaimAnalysisCandidate(
            analysis_id=analysis_id,
            claim_id=claim_id,
            facts_found=facts,
            evidence_ids=evidence_ids,
            evidence_assessment=evidence_assessment,
            applicable_rules=rules,
            precedent_source_ids=precedents,
            reasoning=reasoning,
            proposed_outcome=outcome,
            limitations=limitations,
        )

    def disposition(
        self,
        api,
        disposition_id="DSP-001",
        claim_id="CLM-001",
        *,
        source_analysis_id="ANL-001",
        command="Synthetic operative command.",
        period="synthetic_period",
        effects=("synthetic_effect",),
        calculation_criteria=("synthetic_criterion",),
    ):
        return api.DispositionCandidate(
            disposition_id=disposition_id,
            claim_id=claim_id,
            command=command,
            period=period,
            effects=effects,
            calculation_criteria=calculation_criteria,
            source_analysis_id=source_analysis_id,
        )

    def test_builds_deterministic_linked_analyses_dispositions_and_draft(self) -> None:
        api = self.api()
        analyses = (
            self.analysis(
                api,
                "ANL-002",
                "CLM-002",
                outcome="procedural_resolution",
                evidence_ids=(),
                evidence_assessment=(),
                rules=("RULE-002",),
            ),
            self.analysis(api),
        )
        dispositions = (
            self.disposition(
                api,
                "DSP-002",
                "CLM-002",
                source_analysis_id="ANL-002",
                calculation_criteria=(),
            ),
            self.disposition(api),
        )

        first_analysis = api.build_claim_analysis(
            ("CLM-002", "CLM-001"),
            ("EVD-001",),
            analyses,
        )
        first_disposition = api.build_disposition_matrix(first_analysis, dispositions)
        first_draft = api.render_judgment_draft(first_analysis, first_disposition)
        second_analysis = api.build_claim_analysis(
            ("CLM-001", "CLM-002"),
            ("EVD-001",),
            tuple(reversed(analyses)),
        )
        second_disposition = api.build_disposition_matrix(
            second_analysis,
            tuple(reversed(dispositions)),
        )
        second_draft = api.render_judgment_draft(second_analysis, second_disposition)

        self.assertEqual(first_analysis, second_analysis)
        self.assertEqual(first_disposition, second_disposition)
        self.assertEqual(first_draft, second_draft)
        self.assertEqual(
            [item["analysis_id"] for item in first_analysis["analyses"]],
            ["ANL-001", "ANL-002"],
        )
        self.assertEqual(first_disposition["items"][0]["outcome"], "granted")
        self.assertLess(first_draft.index("CLM-001"), first_draft.index("CLM-002"))
        self.assertIn("## Dispositivo", first_draft)

    def test_draft_displays_outcomes_and_non_applicable_period_in_portuguese(self) -> None:
        api = self.api()
        labels = (
            ("granted", "procedente"),
            ("denied", "improcedente"),
            ("granted_in_part", "parcialmente procedente"),
            ("dismissed_without_merits", "extinto sem resolução do mérito"),
            ("procedural_resolution", "resolução processual"),
            ("pending_human_review", "revisão humana pendente"),
            ("abstained", "abstenção"),
        )
        for code, label in labels:
            with self.subTest(code=code):
                analysis = {
                    "schema_version": 1,
                    "analyses": [{
                        "analysis_id": "ANL-001", "claim_id": "CLM-001",
                        "proposed_outcome": code, "facts_found": [],
                        "evidence_ids": [], "evidence_assessment": [],
                        "applicable_rules": [], "reasoning": "Análise sintética.",
                        "limitations": [],
                    }],
                }
                dispositions = {
                    "schema_version": 1,
                    "items": [{
                        "disposition_id": "DSP-001", "claim_id": "CLM-001",
                        "source_analysis_id": "ANL-001", "outcome": code,
                        "command": "Comando sintético.", "period": "not_applicable",
                        "effects": [], "calculation_criteria": [],
                    }],
                }

                draft = api.render_judgment_draft(analysis, dispositions)

                self.assertIn(f"Resultado proposto: {label}\n", draft)
                self.assertIn(f"Resultado: {label}\n", draft)
                self.assertIn("Período: não se aplica\n", draft)
                self.assertNotIn(f"Resultado: {code}\n", draft)

    def test_draft_rejects_unknown_disposition_outcome(self) -> None:
        api = self.api()
        analysis = {
            "schema_version": 1,
            "analyses": [{
                "analysis_id": "ANL-001", "claim_id": "CLM-001",
                "proposed_outcome": "pending_human_review", "facts_found": [],
                "evidence_ids": [], "evidence_assessment": [],
                "applicable_rules": [], "reasoning": "Revisão pendente.",
                "limitations": [],
            }],
        }
        dispositions = {
            "schema_version": 1,
            "items": [{
                "disposition_id": "DSP-001", "claim_id": "CLM-001",
                "source_analysis_id": "ANL-001", "outcome": "pending_human_review",
                "command": "Sem comando.", "period": "not_applicable",
                "effects": [], "calculation_criteria": [],
            }],
        }

        for code in ("unexpected_outcome", ["granted"]):
            with self.subTest(code=code):
                dispositions["items"][0]["outcome"] = code
                with self.assertRaisesRegex(api.ClaimDecisionContractViolation, "resultado"):
                    api.render_judgment_draft(analysis, dispositions)

    def test_analysis_must_cover_every_known_claim(self) -> None:
        api = self.api()

        with self.assertRaisesRegex(api.ClaimDecisionContractViolation, "CLM-002"):
            api.build_claim_analysis(
                ("CLM-001", "CLM-002"),
                ("EVD-001",),
                (self.analysis(api),),
            )

    def test_analysis_rejects_evidence_outside_manifest(self) -> None:
        api = self.api()

        with self.assertRaisesRegex(api.ClaimDecisionContractViolation, "EVD-999"):
            api.build_claim_analysis(
                ("CLM-001",),
                ("EVD-001",),
                (self.analysis(api, evidence_ids=("EVD-999",)),),
            )

    def test_merits_outcome_requires_facts_evidence_and_rules(self) -> None:
        api = self.api()
        cases = (
            ({"facts": ()}, "facts_found"),
            ({"evidence_ids": ()}, "evidence_ids"),
            ({"evidence_assessment": ()}, "evidence_assessment"),
            ({"rules": ()}, "applicable_rules"),
        )
        for changes, expected in cases:
            with self.subTest(expected=expected):
                candidate = self.analysis(api, **changes)
                with self.assertRaisesRegex(
                    api.ClaimDecisionContractViolation,
                    expected,
                ):
                    api.build_claim_analysis(
                        ("CLM-001",),
                        ("EVD-001",),
                        (candidate,),
                    )

    def test_unresolved_outcome_requires_an_explicit_limitation(self) -> None:
        api = self.api()
        candidate = self.analysis(
            api,
            outcome="pending_human_review",
            facts=(),
            evidence_ids=(),
            evidence_assessment=(),
            rules=(),
        )

        with self.assertRaisesRegex(api.ClaimDecisionContractViolation, "limitations"):
            api.build_claim_analysis(("CLM-001",), (), (candidate,))

    def test_disposition_must_cover_every_analysis(self) -> None:
        api = self.api()
        analyses = api.build_claim_analysis(
            ("CLM-001", "CLM-002"),
            ("EVD-001",),
            (
                self.analysis(api),
                self.analysis(
                    api,
                    "ANL-002",
                    "CLM-002",
                    outcome="pending_human_review",
                    facts=(),
                    evidence_ids=(),
                    evidence_assessment=(),
                    rules=(),
                    limitations=("Synthetic review required.",),
                ),
            ),
        )

        with self.assertRaisesRegex(api.ClaimDecisionContractViolation, "CLM-002"):
            api.build_disposition_matrix(analyses, (self.disposition(api),))

    def test_disposition_link_must_match_its_claim_analysis(self) -> None:
        api = self.api()
        analyses = api.build_claim_analysis(
            ("CLM-001", "CLM-002"),
            ("EVD-001",),
            (
                self.analysis(api),
                self.analysis(
                    api,
                    "ANL-002",
                    "CLM-002",
                    outcome="procedural_resolution",
                    evidence_ids=(),
                    evidence_assessment=(),
                ),
            ),
        )
        mismatched = self.disposition(api, source_analysis_id="ANL-002")

        with self.assertRaisesRegex(api.ClaimDecisionContractViolation, "ANL-002"):
            api.build_disposition_matrix(
                analyses,
                (
                    mismatched,
                    self.disposition(
                        api,
                        "DSP-002",
                        "CLM-002",
                        source_analysis_id="ANL-002",
                    ),
                ),
            )

    def test_duplicate_analysis_or_disposition_id_is_rejected(self) -> None:
        api = self.api()
        duplicate_analysis = self.analysis(api)
        with self.assertRaisesRegex(api.ClaimDecisionContractViolation, "analysis_id"):
            api.build_claim_analysis(
                ("CLM-001", "CLM-002"),
                ("EVD-001",),
                (
                    duplicate_analysis,
                    self.analysis(api, "ANL-001", "CLM-002"),
                ),
            )

        analyses = api.build_claim_analysis(
            ("CLM-001",),
            ("EVD-001",),
            (self.analysis(api),),
        )
        duplicate_disposition = self.disposition(api)
        with self.assertRaisesRegex(api.ClaimDecisionContractViolation, "disposition_id"):
            api.build_disposition_matrix(
                analyses,
                (duplicate_disposition, duplicate_disposition),
            )


if __name__ == "__main__":
    unittest.main()
