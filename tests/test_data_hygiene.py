from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_data_hygiene.py"
REPOSITORY_CONTRACT = ROOT / "runtime" / "data-hygiene-contract.json"


class DataHygieneTest(unittest.TestCase):
    def initialize_repository(self, root: Path, *, required_patterns: list[str] | None = None) -> Path:
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        contract = root / "data-hygiene-contract.json"
        contract.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "required_ignore_patterns": {
                        ".gitignore": required_patterns or [],
                    },
                    "allowed_paths": [".env.example", "tests/fixtures/sanitized/**"],
                    "forbidden_paths": [
                        {"id": "environment-file", "glob": ".env*"},
                        {"id": "browser-capture", "glob": "*.har"},
                        {"id": "pje-session", "glob": "pje_session*.json"},
                        {"id": "case-data", "glob": "data/**"},
                    ],
                    "content_rules": [
                        {
                            "id": "authorization-bearer",
                            "pattern": "(?i)authorization\\s*:\\s*bearer\\s+[A-Za-z0-9._~+/=-]{16,}",
                        },
                        {
                            "id": "cookie-header",
                            "pattern": "(?i)(?:cookie|set-cookie)\\s*:\\s*[A-Za-z0-9_.-]+=[A-Za-z0-9%._~+/=-]{12,}",
                        },
                    ],
                    "scan_filenames": [".env.example"],
                    "scan_extensions": [".har", ".json", ".md", ".py", ".txt"],
                    "max_file_bytes": 1000000,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return contract

    def run_checker(self, root: Path, contract: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                "--root",
                str(root),
                "--contract",
                str(contract),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_ignored_session_and_case_data_are_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(
                root,
                required_patterns=["pje_session*.json", "data/"],
            )
            (root / ".gitignore").write_text("pje_session*.json\ndata/\n", encoding="utf-8")
            bearer = "session_" + "A" * 24
            (root / "pje_session.json").write_text(
                "Authorization: Bearer " + bearer + "\n",
                encoding="utf-8",
            )
            case_data = root / "data" / "0000001"
            case_data.mkdir(parents=True)
            (case_data / "processo.txt").write_text("confidential case data\n", encoding="utf-8")

            result = self.run_checker(root, contract)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[OK] data hygiene", result.stdout)

    def test_unignored_har_is_rejected_without_leaking_its_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root)
            secret = "private-session-" + "Z" * 24
            (root / "capture.har").write_text(secret + "\n", encoding="utf-8")

            result = self.run_checker(root, contract)

            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("capture.har", output)
            self.assertIn("browser-capture", output)
            self.assertNotIn(secret, output)

    def test_oversized_sanitized_har_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root)
            (root / ".gitignore").write_text("", encoding="utf-8")
            fixture = root / "tests" / "fixtures" / "sanitized" / "capture.har"
            fixture.parent.mkdir(parents=True)
            fixture.write_text("A" * 1000001, encoding="utf-8")

            result = self.run_checker(root, contract)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("capture.har", result.stdout)
            self.assertIn("file-too-large", result.stdout)

    def test_environment_example_is_allowed_but_still_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root)
            (root / ".gitignore").write_text("", encoding="utf-8")
            bearer = "example_" + "E" * 24
            (root / ".env.example").write_text(
                "Authorization: Bearer " + bearer + "\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, contract)

            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("authorization-bearer", output)
            self.assertNotIn(bearer, output)

    def test_symlink_target_outside_repository_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "repository"
            root.mkdir()
            contract = self.initialize_repository(root)
            (root / ".gitignore").write_text("", encoding="utf-8")
            bearer = "outside_" + "S" * 24
            external = base / "external-secret.md"
            external.write_text(
                "Authorization: Bearer " + bearer + "\n",
                encoding="utf-8",
            )
            (root / "linked.md").symlink_to(external)

            result = self.run_checker(root, contract)

            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertNotIn(bearer, output)

    def test_tracked_session_is_rejected_even_after_it_becomes_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root)
            session = root / "pje_session.json"
            session.write_text("{}\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "pje_session.json"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            (root / ".gitignore").write_text("pje_session*.json\n", encoding="utf-8")

            result = self.run_checker(root, contract)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("pje-session", result.stdout)

    def test_sensitive_headers_are_reported_without_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root)
            bearer = "bearer_" + "B" * 24
            cookie = "session=" + "C" * 24
            (root / "notes.md").write_text(
                "Authorization: Bearer " + bearer + "\nCookie: " + cookie + "\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, contract)

            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("authorization-bearer", output)
            self.assertIn("cookie-header", output)
            self.assertNotIn(bearer, output)
            self.assertNotIn(cookie, output)

    def test_repository_policy_rejects_process_pdf_filename_without_printing_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root)
            (root / ".gitignore").write_text("", encoding="utf-8")
            policy = json.loads(REPOSITORY_CONTRACT.read_text(encoding="utf-8"))
            local = json.loads(contract.read_text(encoding="utf-8"))
            local["content_rules"] = policy["content_rules"]
            contract.write_text(json.dumps(local) + "\n", encoding="utf-8")
            filename = "Processo_" + "9999999-99.2099.5.99.9999" + ".pdf"
            (root / "notes.md").write_text(filename + "\n", encoding="utf-8")

            result = self.run_checker(root, contract)

            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("process-pdf-filename", output)
            self.assertNotIn(filename, output)

    def test_repository_policy_rejects_process_pdf_basename_without_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root)
            (root / ".gitignore").write_text("", encoding="utf-8")
            policy = json.loads(REPOSITORY_CONTRACT.read_text(encoding="utf-8"))
            local = json.loads(contract.read_text(encoding="utf-8"))
            local["content_rules"] = policy["content_rules"]
            contract.write_text(json.dumps(local) + "\n", encoding="utf-8")
            basename = "Processo_" + "9999999-99.2099.5.99.9999"
            (root / "notes.py").write_text(repr(basename) + "\n", encoding="utf-8")

            result = self.run_checker(root, contract)

            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("process-pdf-filename", output)
            self.assertNotIn(basename, output)

    def test_dynamic_and_redacted_placeholders_are_not_treated_as_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root)
            (root / ".gitignore").write_text("", encoding="utf-8")
            (root / "example.py").write_text(
                'cookie_header = "generated-at-runtime"\n'
                'print(f"Cookie: {cookie_header}")\n',
                encoding="utf-8",
            )
            (root / "example.md").write_text(
                'token: "[REDACTED]"\ncookie: "[REDACTED]"\n',
                encoding="utf-8",
            )

            result = self.run_checker(root, contract)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[OK] data hygiene", result.stdout)

    def test_missing_required_ignore_pattern_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.initialize_repository(root, required_patterns=["*.har"])
            (root / ".gitignore").write_text("*.pdf\n", encoding="utf-8")

            result = self.run_checker(root, contract)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing ignore pattern", result.stdout)
            self.assertIn("*.har", result.stdout)

    def test_repository_satisfies_data_hygiene_contract(self) -> None:
        result = self.run_checker(ROOT, REPOSITORY_CONTRACT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[OK] data hygiene", result.stdout)

    def test_installed_layout_does_not_require_scaffold_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(
                ["git", "init", "--quiet"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            shutil.copy2(ROOT / "scaffold" / "project-gitignore", root / ".gitignore")

            result = self.run_checker(root, REPOSITORY_CONTRACT)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[OK] data hygiene", result.stdout)


if __name__ == "__main__":
    unittest.main()
