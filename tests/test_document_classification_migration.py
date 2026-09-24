from __future__ import annotations

import copy
import importlib
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class DocumentClassificationMigrationTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("migrate_document_classification_v1_to_v2")

    def source(self):
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
                    "document_type": "unknown",
                    "classification_status": "unknown",
                    "matched_rule_ids": [],
                    "reason_code": "no_matching_rule",
                },
            ],
        }

    def test_migration_preserves_old_findings_without_inventing_new_types(self) -> None:
        api = self.api()
        source = self.source()
        before = copy.deepcopy(source)

        target, receipt = api.migrate_classification_v1_to_v2(source)
        again, again_receipt = api.migrate_classification_v1_to_v2(source)

        self.assertEqual(source, before)
        self.assertEqual(target, again)
        self.assertEqual(receipt, again_receipt)
        self.assertEqual(target["schema_version"], 2)
        self.assertEqual(target["classifier_version"], 1)
        self.assertEqual(target["documents"], source["documents"])
        self.assertEqual(receipt["source_schema_version"], 1)
        self.assertEqual(receipt["target_schema_version"], 2)
        self.assertEqual(len(receipt["source_sha256"]), 64)
        self.assertEqual(len(receipt["target_sha256"]), 64)

    def test_migration_rejects_inconsistent_old_classification(self) -> None:
        api = self.api()
        source = self.source()
        source["documents"][1]["classification_status"] = "classified"

        with self.assertRaises(api.ClassificationMigrationError):
            api.migrate_classification_v1_to_v2(source)

    def test_migration_writes_protected_bundle_without_overwrite(self) -> None:
        api = self.api()
        target, receipt = api.migrate_classification_v1_to_v2(self.source())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "protected"
            output.mkdir(mode=0o700)
            paths = api.write_migration_bundle(
                target, receipt, output_dir=output, repository_root=ROOT
            )
            self.assertEqual(len(paths), 2)
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in paths))
            self.assertEqual(json.loads(paths[0].read_text()), target)
            with self.assertRaises(api.ClassificationMigrationError):
                api.write_migration_bundle(
                    target, receipt, output_dir=output, repository_root=ROOT
                )
            self.assertEqual(json.loads(paths[0].read_text()), target)

    def test_migration_rejects_nonprivate_destination(self) -> None:
        api = self.api()
        target, receipt = api.migrate_classification_v1_to_v2(self.source())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "unprotected"
            output.mkdir(mode=0o755)

            with self.assertRaises(api.ClassificationMigrationError):
                api.write_migration_bundle(
                    target, receipt, output_dir=output, repository_root=ROOT
                )
            self.assertEqual(list(output.iterdir()), [])

    def test_cli_migrates_once_without_echoing_private_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "document-classification.v1.json"
            source.write_text(json.dumps(self.source()), encoding="utf-8")
            source.chmod(0o600)
            output = root / "protected"
            output.mkdir(mode=0o700)
            command = [
                sys.executable,
                str(SCRIPTS / "migrate_document_classification_v1_to_v2.py"),
                "--input", str(source), "--output", str(output),
            ]

            first = subprocess.run(command, capture_output=True, text=True, check=False)
            second = subprocess.run(command, capture_output=True, text=True, check=False)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"document-classification.json", "document-classification-migration.json"},
            )
            self.assertNotIn("DOC-001", first.stdout + first.stderr)
            self.assertEqual(json.loads(source.read_text()), self.source())


if __name__ == "__main__":
    unittest.main()
