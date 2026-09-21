from __future__ import annotations

import copy
import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TAXONOMY = ROOT / "runtime" / "domain" / "labor-claim-taxonomy.json"


class ClaimMatrixBuilderTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("build_claim_matrix")
        except ModuleNotFoundError as error:
            self.fail(f"claim matrix builder module is missing: {error}")

    def source(self, api, document_id, locator):
        return api.SourceReference(document_id=document_id, locator=locator)

    def claim(
        self,
        api,
        claim_id="CLM-001",
        *,
        label="overtime",
        remedies=("overtime_payment", "statutory_effects"),
        document_id="DOC-001",
    ):
        return api.ClaimCandidate(
            claim_id=claim_id,
            label=label,
            claimant_position="Synthetic claimant position.",
            requested_remedies=remedies,
            contested_facts=("actual_working_hours",),
            legal_issues=("reliability_of_time_records",),
            source=self.source(api, document_id, "pages 4-5"),
        )

    def defense(
        self,
        api,
        defense_id="DEF-001",
        *,
        claim_id="CLM-001",
        party_id="PTY-002",
        document_id="DOC-002",
    ):
        return api.DefenseCandidate(
            defense_id=defense_id,
            claim_id=claim_id,
            respondent_party_id=party_id,
            respondent_position="Synthetic respondent position.",
            source=self.source(api, document_id, "pages 2-3"),
        )

    def build(self, api, claims, defenses, known_documents=("DOC-001", "DOC-002")):
        taxonomy = api.load_claim_taxonomy(TAXONOMY)
        return api.build_claim_matrix(
            taxonomy,
            known_documents,
            tuple(claims),
            tuple(defenses),
        )

    def test_builds_deterministic_source_linked_claims_and_multiple_defenses(self) -> None:
        api = self.api()
        claims = (
            self.claim(
                api,
                "CLM-002",
                label="moral_damages",
                remedies=("compensation",),
                document_id="DOC-003",
            ),
            self.claim(api, "CLM-001"),
        )
        defenses = (
            self.defense(
                api,
                "DEF-002",
                party_id="PTY-003",
                document_id="DOC-003",
            ),
            self.defense(api, "DEF-001"),
            self.defense(
                api,
                "DEF-003",
                claim_id="CLM-002",
                party_id="PTY-002",
                document_id="DOC-002",
            ),
        )
        known = ("DOC-003", "DOC-002", "DOC-001")

        forward = self.build(api, claims, defenses, known)
        reverse = self.build(
            api,
            tuple(reversed(claims)),
            tuple(reversed(defenses)),
            tuple(reversed(known)),
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(forward["taxonomy_version"], 1)
        self.assertEqual(
            [claim["claim_id"] for claim in forward["claims"]],
            ["CLM-001", "CLM-002"],
        )
        overtime = forward["claims"][0]
        self.assertEqual(
            [item["defense_id"] for item in overtime["respondent_positions"]],
            ["DEF-001", "DEF-002"],
        )
        self.assertEqual(overtime["claimant_position"]["source_locator"], "pages 4-5")
        self.assertEqual(overtime["status"], "mapped")
        self.assertEqual(overtime["review_gaps"], [])

    def test_missing_remedy_and_defense_are_explicit_review_gaps(self) -> None:
        api = self.api()

        result = self.build(
            api,
            (self.claim(api, remedies=()),),
            (),
            ("DOC-001",),
        )

        claim = result["claims"][0]
        self.assertEqual(claim["respondent_positions"], [])
        self.assertEqual(claim["requested_remedies"], [])
        self.assertEqual(
            claim["review_gaps"],
            ["missing_requested_remedy", "missing_respondent_position"],
        )
        self.assertEqual(claim["status"], "needs_human_review")

    def test_unsupported_claim_label_is_preserved_without_guessing(self) -> None:
        api = self.api()

        result = self.build(
            api,
            (
                self.claim(
                    api,
                    label="synthetic_unmapped_claim",
                    remedies=("synthetic_remedy",),
                ),
            ),
            (self.defense(api),),
        )

        claim = result["claims"][0]
        self.assertEqual(claim["label"], "synthetic_unmapped_claim")
        self.assertEqual(claim["requested_remedies"], ["synthetic_remedy"])
        self.assertEqual(claim["review_gaps"], ["unsupported_claim_label"])
        self.assertEqual(claim["status"], "needs_human_review")

    def test_unsupported_remedy_for_known_claim_requires_review(self) -> None:
        api = self.api()

        result = self.build(
            api,
            (self.claim(api, remedies=("synthetic_remedy",)),),
            (self.defense(api),),
        )

        claim = result["claims"][0]
        self.assertEqual(claim["requested_remedies"], ["synthetic_remedy"])
        self.assertEqual(claim["review_gaps"], ["unsupported_requested_remedy"])
        self.assertEqual(claim["status"], "needs_human_review")

    def test_source_reference_outside_manifest_is_rejected(self) -> None:
        api = self.api()

        with self.assertRaisesRegex(api.ClaimMatrixContractViolation, "DOC-999"):
            self.build(
                api,
                (self.claim(api, document_id="DOC-999"),),
                (),
                ("DOC-001",),
            )

    def test_defense_for_unknown_claim_is_rejected(self) -> None:
        api = self.api()

        with self.assertRaisesRegex(api.ClaimMatrixContractViolation, "CLM-999"):
            self.build(
                api,
                (self.claim(api),),
                (self.defense(api, claim_id="CLM-999"),),
            )

    def test_duplicate_stable_identifiers_are_rejected(self) -> None:
        api = self.api()
        duplicate = self.claim(api)

        with self.assertRaisesRegex(api.ClaimMatrixContractViolation, "claim_id"):
            self.build(api, (duplicate, duplicate), ())

    def test_taxonomy_rejects_duplicate_claim_labels(self) -> None:
        api = self.api()
        taxonomy = copy.deepcopy(api.load_claim_taxonomy(TAXONOMY))
        taxonomy["claim_types"].append(copy.deepcopy(taxonomy["claim_types"][0]))

        with self.assertRaisesRegex(api.ClaimMatrixContractViolation, "label"):
            api.build_claim_matrix(
                taxonomy,
                ("DOC-001",),
                (self.claim(api),),
                (),
            )


if __name__ == "__main__":
    unittest.main()
