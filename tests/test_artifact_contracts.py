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

    def test_canonical_fixture_suite_covers_all_eleven_contracts(self) -> None:
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
                "requested-remedy-evidence",
            ],
        )
        self.assertEqual(report["valid_fixture_count"], 11)
        self.assertEqual(report["invalid_fixture_count"], 15)

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
            "requested-remedy-evidence": (
                "missing-unmatched-locator.json",
                "unmatched_items[0].source_locator",
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

    def test_unmatched_remedy_ids_must_match_source_linked_items(self) -> None:
        result = self.run_validator(
            "--contract", "requested-remedy-evidence",
            "--document",
            str(FIXTURES / "invalid" / "requested-remedy-evidence" / "mismatched-unmatched-id.json"),
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unmatched_item_ids", result.stderr)

    def test_historical_remedy_evidence_v1_remains_valid_for_custody(self) -> None:
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        from schema_validation import load_json
        from validate_artifact_contracts import validate_document

        schema = load_json(
            ROOT / "runtime/contracts/schemas/requested-remedy-evidence.v1.schema.json",
            "contrato histórico",
        )
        historical = {
            "schema_version": 1, "source_pdf_sha256": "0" * 64,
            "entries": [], "unmatched_item_ids": ["I"],
        }

        self.assertEqual(validate_document(historical, schema), [])
        self.assertTrue(validate_document(historical, load_json(
            ROOT / "runtime/contracts/schemas/requested-remedy-evidence.v2.schema.json",
            "contrato vigente",
        )))

    def test_current_classification_contract_accepts_procedural_types(self) -> None:
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        from validate_artifact_contracts import load_catalog, validate_document

        _, contracts = load_catalog(CATALOG)
        schema, _ = contracts["document-classification"]
        document = {
            "schema_version": 2,
            "classifier_version": 2,
            "documents": [{
                "document_id": "DOC-001",
                "document_type": "procedural_certificate",
                "classification_status": "classified",
                "matched_rule_ids": ["procedural-certificate"],
                "reason_code": "matched_rule",
            }],
        }

        self.assertEqual(validate_document(document, schema), [])
        document["schema_version"] = 1
        self.assertTrue(validate_document(document, schema))

    def test_historical_classification_schema_remains_available(self) -> None:
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        from schema_validation import load_json
        from validate_artifact_contracts import validate_document

        historical = load_json(
            ROOT / "runtime/contracts/schemas/document-classification.v1.schema.json",
            "historical classification schema",
        )
        artifact = {
            "schema_version": 1,
            "classifier_version": 1,
            "documents": [{
                "document_id": "DOC-001",
                "document_type": "initial_pleading",
                "classification_status": "classified",
                "matched_rule_ids": ["initial-pleading"],
                "reason_code": "matched_rule",
            }],
        }
        self.assertEqual(validate_document(artifact, historical), [])
        artifact["documents"][0]["document_type"] = "procedural_certificate"
        self.assertTrue(validate_document(artifact, historical))

    def test_v2_rejects_new_type_claimed_by_old_classifier(self) -> None:
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        from validate_artifact_contracts import load_catalog, validate_document

        _, contracts = load_catalog(CATALOG)
        schema, _ = contracts["document-classification"]
        artifact = json.loads(
            (FIXTURES / "valid/document-classification.json").read_text(encoding="utf-8")
        )
        artifact["classifier_version"] = 1

        self.assertTrue(validate_document(artifact, schema))

    def test_v2_explains_old_classifier_mismatch_in_portuguese(self) -> None:
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        from validate_artifact_contracts import load_catalog, validate_document

        _, contracts = load_catalog(CATALOG)
        schema, _ = contracts["document-classification"]
        artifact = json.loads(
            (FIXTURES / "valid/document-classification.json").read_text(encoding="utf-8")
        )
        artifact["classifier_version"] = 1

        self.assertIn(
            "classificador v1 não pode atribuir tipo v2",
            "; ".join(validate_document(artifact, schema)),
        )

    def test_v2_rejects_classification_status_inconsistent_with_type(self) -> None:
        if str(ROOT / "scripts") not in sys.path:
            sys.path.insert(0, str(ROOT / "scripts"))
        from validate_artifact_contracts import load_catalog, validate_document

        _, contracts = load_catalog(CATALOG)
        schema, _ = contracts["document-classification"]
        artifact = json.loads(
            (FIXTURES / "valid/document-classification.json").read_text(encoding="utf-8")
        )
        artifact["documents"][0]["classification_status"] = "unknown"

        self.assertTrue(validate_document(artifact, schema))

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
