from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class EvidenceMatrixBuilderTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("build_evidence_matrix")
        except ModuleNotFoundError as error:
            self.fail(f"evidence matrix builder module is missing: {error}")

    def source(self, api, document_id="DOC-010", locator="pages 3-8"):
        return api.SourceReference(document_id=document_id, locator=locator)

    def evidence(
        self,
        api,
        evidence_id="EVD-001",
        *,
        claim_ids=("CLM-001",),
        evidence_type="time_record",
        relation="supports_claim",
        analysis_status="pending",
        conflicts_with=(),
        document_id="DOC-010",
    ):
        return api.EvidenceCandidate(
            evidence_id=evidence_id,
            claim_ids=claim_ids,
            evidence_type=evidence_type,
            proposition="Synthetic evidentiary proposition.",
            relation=relation,
            limitations=("Synthetic fixture only.",),
            analysis_status=analysis_status,
            conflicts_with_evidence_ids=conflicts_with,
            source=self.source(api, document_id),
        )

    def build(
        self,
        api,
        candidates,
        *,
        known_documents=("DOC-010", "DOC-011"),
        known_claims=("CLM-001", "CLM-002"),
    ):
        return api.build_evidence_matrix(
            known_documents,
            known_claims,
            tuple(candidates),
        )

    def test_builds_deterministic_source_linked_evidence_with_claim_coverage(self) -> None:
        api = self.api()
        candidates = (
            self.evidence(
                api,
                "EVD-002",
                claim_ids=("CLM-002",),
                evidence_type="expert_report",
                relation="neutral_context",
                document_id="DOC-011",
            ),
            self.evidence(api, "EVD-001"),
        )

        forward = self.build(api, candidates)
        reverse = self.build(
            api,
            tuple(reversed(candidates)),
            known_documents=("DOC-011", "DOC-010"),
            known_claims=("CLM-002", "CLM-001"),
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(
            [item["evidence_id"] for item in forward["evidence_items"]],
            ["EVD-001", "EVD-002"],
        )
        self.assertEqual(forward["uncovered_claim_ids"], [])
        self.assertEqual(
            forward["evidence_items"][0]["source_locator"],
            "pages 3-8",
        )

    def test_claim_without_evidence_is_reported_as_uncovered(self) -> None:
        api = self.api()

        result = self.build(api, (self.evidence(api),))

        self.assertEqual(result["uncovered_claim_ids"], ["CLM-002"])

    def test_conflicting_evidence_is_linked_symmetrically(self) -> None:
        api = self.api()
        first = self.evidence(
            api,
            "EVD-001",
            analysis_status="disputed",
            conflicts_with=("EVD-002",),
        )
        second = self.evidence(
            api,
            "EVD-002",
            relation="opposes_claim",
            analysis_status="disputed",
            document_id="DOC-011",
        )

        result = self.build(api, (first, second))

        items = {item["evidence_id"]: item for item in result["evidence_items"]}
        self.assertEqual(items["EVD-001"]["conflicts_with_evidence_ids"], ["EVD-002"])
        self.assertEqual(items["EVD-002"]["conflicts_with_evidence_ids"], ["EVD-001"])

    def test_reference_to_unknown_claim_is_rejected(self) -> None:
        api = self.api()

        with self.assertRaisesRegex(api.EvidenceMatrixContractViolation, "CLM-999"):
            self.build(api, (self.evidence(api, claim_ids=("CLM-999",)),))

    def test_source_outside_document_manifest_is_rejected(self) -> None:
        api = self.api()

        with self.assertRaisesRegex(api.EvidenceMatrixContractViolation, "DOC-999"):
            self.build(api, (self.evidence(api, document_id="DOC-999"),))

    def test_unknown_or_self_conflict_is_rejected(self) -> None:
        api = self.api()
        cases = (
            ("EVD-999", "unknown"),
            ("EVD-001", "itself"),
        )
        for conflict_id, expected in cases:
            with self.subTest(conflict_id=conflict_id):
                candidate = self.evidence(
                    api,
                    conflicts_with=(conflict_id,),
                    analysis_status="disputed",
                )
                with self.assertRaisesRegex(api.EvidenceMatrixContractViolation, expected):
                    self.build(api, (candidate,))

    def test_duplicate_evidence_identifier_is_rejected(self) -> None:
        api = self.api()
        duplicate = self.evidence(api)

        with self.assertRaisesRegex(api.EvidenceMatrixContractViolation, "evidence_id"):
            self.build(api, (duplicate, duplicate))

    def test_conflict_requires_disputed_analysis_status(self) -> None:
        api = self.api()
        first = self.evidence(api, conflicts_with=("EVD-002",))
        second = self.evidence(api, "EVD-002", document_id="DOC-011")

        with self.assertRaisesRegex(api.EvidenceMatrixContractViolation, "disputed"):
            self.build(api, (first, second))


if __name__ == "__main__":
    unittest.main()
