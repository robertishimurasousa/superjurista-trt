from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_tribunal_profile.py"
SCHEMA = ROOT / "runtime" / "profiles" / "schema.json"
REGISTRY = ROOT / "runtime" / "profiles" / "registry.json"
TRT12_PROFILE = ROOT / "runtime" / "profiles" / "trt12.json"


class TribunalProfileTest(unittest.TestCase):
    def run_validator(
        self,
        profile: Path = TRT12_PROFILE,
        *,
        output_format: str = "text",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--schema",
                str(SCHEMA),
                "--registry",
                str(REGISTRY),
                "--profile",
                str(profile),
                "--format",
                output_format,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def invalid_profile(self, mutate) -> subprocess.CompletedProcess[str]:
        profile = json.loads(TRT12_PROFILE.read_text(encoding="utf-8"))
        mutate(profile)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            return self.run_validator(path)

    def test_trt12_first_instance_profile_is_valid_and_machine_readable(self) -> None:
        result = self.run_validator(output_format="json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["profile_id"], "trt12")
        self.assertEqual(report["tribunal_code"], "TRT12")
        self.assertEqual(report["active_instances"], ["first"])
        self.assertEqual(report["inactive_instances"], ["second"])
        self.assertEqual(len(report["contract_digest"]), 64)

    def test_schema_is_runtime_neutral_and_profile_carries_trt12_values(self) -> None:
        schema_text = SCHEMA.read_text(encoding="utf-8")
        profile = json.loads(TRT12_PROFILE.read_text(encoding="utf-8"))

        self.assertNotIn("TRT12", schema_text)
        self.assertNotIn("trt12", schema_text.lower())
        self.assertEqual(profile["tribunal"]["code"], "TRT12")
        self.assertEqual(profile["tribunal"]["region"], 12)
        self.assertEqual(profile["tribunal"]["state"], "SC")
        self.assertTrue(profile["instances"]["first"]["enabled"])
        self.assertFalse(profile["instances"]["second"]["enabled"])

    def test_unknown_cnj_branch_digit_fails_closed(self) -> None:
        result = self.invalid_profile(
            lambda profile: profile["tribunal"].update(cnj_branch_digit=4)
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("tribunal.cnj_branch_digit", result.stderr)

    def test_enabled_instance_without_registered_adapter_fails_closed(self) -> None:
        def mutate(profile: dict) -> None:
            profile["instances"]["second"]["enabled"] = True
            profile["providers"]["case_system"]["second_instance_adapter"] = None

        result = self.invalid_profile(mutate)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("providers.case_system.second_instance_adapter", result.stderr)

    def test_unknown_case_system_adapter_fails_closed(self) -> None:
        result = self.invalid_profile(
            lambda profile: profile["providers"]["case_system"].update(
                first_instance_adapter="unregistered_adapter"
            )
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unregistered case-system adapter", result.stderr)

    def test_empty_signature_set_fails_closed(self) -> None:
        result = self.invalid_profile(
            lambda profile: profile["instances"]["first"].update(signatures=[])
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("instances.first.signatures", result.stderr)

    def test_unknown_research_source_fails_closed(self) -> None:
        def mutate(profile: dict) -> None:
            profile["providers"]["research"][0]["source"] = "unregistered_source"

        result = self.invalid_profile(mutate)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unregistered research source", result.stderr)

    def test_research_source_without_registered_adapter_fails_closed(self) -> None:
        def mutate(profile: dict) -> None:
            profile["providers"]["research"][0]["adapter"] = "unregistered_adapter"

        result = self.invalid_profile(mutate)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unregistered research adapter", result.stderr)

    def test_policy_cannot_enable_external_actions(self) -> None:
        for field in (
            "allow_external_signing",
            "allow_external_filing",
            "allow_external_publication",
        ):
            with self.subTest(field=field):
                result = self.invalid_profile(
                    lambda profile, field=field: profile["policy"].update({field: True})
                )

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(f"policy.{field}", result.stderr)

    def test_profile_schema_rejects_unknown_fields(self) -> None:
        result = self.invalid_profile(lambda profile: profile.update(typo=True))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unknown field: typo", result.stderr)


if __name__ == "__main__":
    unittest.main()
