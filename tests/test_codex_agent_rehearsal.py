from __future__ import annotations

import hashlib
import importlib
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class CodexAgentRehearsalTest(unittest.TestCase):
    def setUp(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        self.preparer = importlib.import_module("prepare_codex_agent_rehearsal")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)

    def test_prepares_only_protected_synthetic_inputs(self):
        paths = self.preparer.prepare_codex_agent_rehearsal(self.workspace)
        expected_names = {"labor-report.json", "claim-matrix.json", "triage-input.md"}
        self.assertEqual({path.name for path in paths}, expected_names)
        self.assertEqual({path.name for path in self.workspace.iterdir()}, expected_names)
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["artifacts"]
        for name in ("labor-report.json", "claim-matrix.json"):
            self.assertEqual(
                json.loads((self.workspace / name).read_text(encoding="utf-8")),
                fixture[name],
            )
        self.assertEqual(
            hashlib.sha256((self.workspace / "triage-input.md").read_bytes()).hexdigest(),
            "ea2c24c3b59d9c390c0b0709ae1fa0478be8abfa0bac4a9b331f202b32670748",
        )
        for path in paths:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_nonempty_workspace_is_refused_without_changing_existing_file(self):
        existing = self.workspace / "preservar.txt"
        existing.write_text("manter", encoding="utf-8")
        with self.assertRaisesRegex(self.preparer.CodexRehearsalError, "vazio"):
            self.preparer.prepare_codex_agent_rehearsal(self.workspace)
        self.assertEqual(existing.read_text(encoding="utf-8"), "manter")
        self.assertEqual([path.name for path in self.workspace.iterdir()], ["preservar.txt"])

    def test_repository_and_symlinked_workspace_are_refused(self):
        with self.assertRaises(self.preparer.CodexRehearsalError):
            self.preparer.prepare_codex_agent_rehearsal(ROOT)
        linked = self.workspace.parent / f"{self.workspace.name}-link"
        linked.symlink_to(self.workspace)
        self.addCleanup(linked.unlink)
        with self.assertRaises(self.preparer.CodexRehearsalError):
            self.preparer.prepare_codex_agent_rehearsal(linked)


if __name__ == "__main__":
    unittest.main()
