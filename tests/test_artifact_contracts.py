from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_artifact_contracts.py"
CATALOG = ROOT / "runtime" / "contracts" / "catalog.json"
FIXTURES = ROOT / "tests" / "fixtures" / "contracts"


class ArtifactContractsTest(unittest.TestCase):
    def run_validator(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--catalog",
                str(CATALOG),
                *arguments,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_canonical_fixture_suite_covers_all_ten_contracts(self) -> None:
        result = self.run_validator(
            "--fixtures-root",
            str(FIXTURES),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(
            report["contracts"],
            [
                "case-context",
                "claim-analysis",
                "claim-matrix",
                "disposition-matrix",
                "document-classification",
                "evidence-matrix",
                "issue-route",
                "labor-report",
                "precedent-corpus",
                "procedural-timeline",
            ],
        )
        self.assertEqual(report["valid_fixture_count"], 10)
        self.assertEqual(report["invalid_fixture_count"], 13)

    def test_each_contract_rejects_its_boundary_violation(self) -> None:
        cases = {
            "case-context": ("invalid-case-number.json", "case_number"),
            "claim-matrix": ("invalid-claim-id.json", "claims[0].claim_id"),
            "evidence-matrix": ("missing-source-locator.json", "source_locator"),
            "issue-route": ("invalid-route-flag.json", "requires_legal_research"),
            "labor-report": ("missing-source-locator.json", "source_locator"),
            "precedent-corpus": ("insecure-official-url.json", "official_url"),
            "claim-analysis": ("invalid-outcome.json", "proposed_outcome"),
            "disposition-matrix": ("missing-analysis-link.json", "source_analysis_id"),
            "document-classification": (
                "unsupported-document-type.json",
                "documents[0].document_type",
            ),
            "procedural-timeline": (
                "missing-source-locator.json",
                "events[0].source_locator",
            ),
        }
        for contract, (filename, expected_path) in cases.items():
            with self.subTest(contract=contract):
                document = FIXTURES / "invalid" / contract / filename
                result = self.run_validator(
                    "--contract",
                    contract,
                    "--document",
                    str(document),
                )

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(expected_path, result.stderr)

    def test_direct_validation_accepts_a_valid_claim_matrix(self) -> None:
        result = self.run_validator(
            "--contract",
            "claim-matrix",
            "--document",
            str(FIXTURES / "valid" / "claim-matrix.json"),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["contract"], "claim-matrix")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(len(report["contract_digest"]), 64)

    def test_unknown_future_schema_version_fails_closed(self) -> None:
        document = json.loads(
            (FIXTURES / "valid" / "claim-matrix.json").read_text(encoding="utf-8")
        )
        document["schema_version"] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future-claim-matrix.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            result = self.run_validator(
                "--contract",
                "claim-matrix",
                "--document",
                str(path),
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("schema_version", result.stderr)

    def test_procedural_timeline_rejects_inconsistent_status_and_custody(self) -> None:
        document = json.loads(
            (FIXTURES / "valid" / "procedural-timeline.json").read_text(
                encoding="utf-8"
            )
        )
        document["status"] = "complete"
        document["events"].append(
            {
                **document["events"][0],
                "event_id": "EVT-999",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-procedural-timeline.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            result = self.run_validator(
                "--contract",
                "procedural-timeline",
                "--document",
                str(path),
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("status", result.stderr)
        self.assertIn("source_document_id", result.stderr)

    def test_unknown_contract_fails_as_a_contract_configuration_error(self) -> None:
        result = self.run_validator(
            "--contract",
            "unknown-contract",
            "--document",
            str(FIXTURES / "valid" / "claim-matrix.json"),
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("unknown contract", result.stderr)


if __name__ == "__main__":
    unittest.main()
