from __future__ import annotations

import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_synthetic_pipeline.py"
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class SyntheticPipelinePrivacyTest(unittest.TestCase):
    def run_fixture(self, workspace: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), "--runtime", "codex", "--fixture", str(FIXTURE),
             "--workspace", str(workspace)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )

    def test_synthetic_outputs_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            result = self.run_fixture(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                {stat.S_IMODE(path.stat().st_mode) for path in workspace.iterdir()},
                {0o600},
            )

    def test_refuses_public_workspace_before_materializing_case_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "publico"
            workspace.mkdir(mode=0o755)
            workspace.chmod(0o755)

            result = self.run_fixture(workspace)

            self.assertEqual(result.returncode, 2)
            self.assertIn("privado", result.stderr)
            self.assertEqual(list(workspace.iterdir()), [])

    def test_refuses_linked_workspace_before_materializing_case_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            private = base / "privado"
            private.mkdir(mode=0o700)
            linked = base / "atalho"
            linked.symlink_to(private, target_is_directory=True)

            result = self.run_fixture(linked)

            self.assertEqual(result.returncode, 2)
            self.assertIn("vínculo simbólico", result.stderr)
            self.assertEqual(list(private.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
