from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_pje_document_acquisition import SyntheticDocumentAdapter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
INTERFACES = ROOT / "runtime" / "providers" / "interfaces.json"
INDEX_SCHEMA = ROOT / "runtime" / "providers" / "document-index-contract.json"
RECOVERY_SCHEMA = ROOT / "runtime" / "providers" / "pje-recovery-state.v1.schema.json"


class TransientDocumentAdapter(SyntheticDocumentAdapter):
    def __init__(self, provider, acquisition, *, failures=None):
        super().__init__(provider, acquisition)
        self.failures = dict(failures or {})

    def fetch_document(self, request):
        self.fetched.append(request.document_id)
        remaining = self.failures.get(request.document_id, 0)
        if remaining:
            self.failures[request.document_id] = remaining - 1
            raise self.acquisition.DocumentUnavailable(
                request.document_id,
                "provider_unavailable",
            )
        return self.provider.DocumentPayload(
            document_id=request.document_id,
            content=self.contents[request.document_id],
        )


class PJeRecoveryTest(unittest.TestCase):
    def apis(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            recovery = importlib.import_module("recover_pje_acquisition")
        except ModuleNotFoundError as error:
            self.fail(f"PJe recovery module is missing: {error}")
        acquisition = importlib.import_module("acquire_pje_documents")
        provider = importlib.import_module("provider_interfaces")
        contract = provider.load_provider_interfaces(INTERFACES)["pje_case_acquisition"]
        return recovery, acquisition, provider, contract

    def scenario(self, provider, *, case_number="0000000-00.2026.5.99.0001"):
        return provider.PJeContractScenario(
            tribunal_code="TRT99",
            instance=1,
            case_number=case_number,
            authorization_scope="synthetic-authorized-scope",
        )

    def execute(self, api, contract, adapter, scenario, directory, **options):
        return api.run_recoverable_acquisition(
            contract,
            adapter,
            scenario,
            checkpoint_path=Path(directory) / "recovery.json",
            payload_directory=Path(directory) / "payloads",
            index_schema=INDEX_SCHEMA,
            recovery_schema=RECOVERY_SCHEMA,
            **options,
        )

    def test_transient_failure_resumes_without_redownloading_accepted_payload(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(
            provider,
            acquisition,
            failures={"DOC-002": 1},
        )
        with tempfile.TemporaryDirectory() as directory:
            first = self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=3,
            )
            second = self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=3,
            )

            self.assertEqual(first.state["status"], "in_progress")
            self.assertEqual(second.state["status"], "complete")
            self.assertEqual(adapter.fetched.count("DOC-001"), 1)
            self.assertEqual(adapter.fetched.count("DOC-002"), 2)
            attempts = {
                item["document_id"]: item["attempt_count"]
                for item in second.state["documents"]
            }
            self.assertEqual(attempts, {"DOC-001": 1, "DOC-002": 2})

    def test_checkpoint_and_payloads_are_persisted_with_schema_valid_state(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(provider, acquisition)
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=2,
            )

            checkpoint = Path(directory) / "recovery.json"
            self.assertTrue(checkpoint.is_file())
            self.assertEqual(result.state["status"], "complete")
            self.assertEqual(result.state["successful_documents"], 2)
            for document in result.state["documents"]:
                path = Path(directory) / "payloads" / document["relative_path"]
                self.assertTrue(path.is_file())
            self.assertEqual(list(Path(directory).glob(".recovery.json.*.tmp")), [])

    def test_tampered_accepted_payload_fails_closed_before_another_fetch(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(
            provider,
            acquisition,
            failures={"DOC-002": 1},
        )
        with tempfile.TemporaryDirectory() as directory:
            first = self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=3,
            )
            accepted = next(
                item for item in first.state["documents"] if item["status"] == "accepted"
            )
            path = Path(directory) / "payloads" / accepted["relative_path"]
            path.write_bytes(b"tampered")
            fetched_before = list(adapter.fetched)

            with self.assertRaisesRegex(api.PJeRecoveryError, "payload custody"):
                self.execute(
                    api,
                    contract,
                    adapter,
                    self.scenario(provider),
                    directory,
                    max_attempts=3,
                )
            self.assertEqual(adapter.fetched, fetched_before)

    def test_catalog_drift_invalidates_the_checkpoint(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(
            provider,
            acquisition,
            failures={"DOC-002": 1},
        )
        with tempfile.TemporaryDirectory() as directory:
            self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=3,
            )
            adapter.contents["DOC-001"] = b"changed synthetic pleading"

            with self.assertRaisesRegex(api.PJeRecoveryError, "catalog|SHA-256"):
                self.execute(
                    api,
                    contract,
                    adapter,
                    self.scenario(provider),
                    directory,
                    max_attempts=3,
                )

    def test_retry_ceiling_is_persisted_and_cannot_be_exceeded(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(
            provider,
            acquisition,
            failures={"DOC-002": 10},
        )
        with tempfile.TemporaryDirectory() as directory:
            first = self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=2,
            )
            second = self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=2,
            )
            fetched_before = list(adapter.fetched)
            third = self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=2,
            )

            self.assertEqual(first.state["status"], "in_progress")
            self.assertEqual(second.state["status"], "exhausted")
            self.assertEqual(third.state, second.state)
            self.assertEqual(adapter.fetched, fetched_before)
            failed = next(
                item for item in third.state["documents"] if item["document_id"] == "DOC-002"
            )
            self.assertEqual(failed["attempt_count"], 2)
            self.assertEqual(failed["status"], "exhausted")

    def test_checkpoint_is_bound_to_scenario_and_retry_policy(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(provider, acquisition)
        with tempfile.TemporaryDirectory() as directory:
            self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=2,
            )
            cases = (
                (self.scenario(provider, case_number="0000000-00.2026.5.99.0002"), 2),
                (self.scenario(provider), 3),
            )
            for scenario, max_attempts in cases:
                with self.subTest(case_number=scenario.case_number, max_attempts=max_attempts):
                    with self.assertRaisesRegex(api.PJeRecoveryError, "checkpoint"):
                        self.execute(
                            api,
                            contract,
                            adapter,
                            scenario,
                            directory,
                            max_attempts=max_attempts,
                        )

    def test_semantically_inconsistent_checkpoint_fails_closed(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(provider, acquisition)
        with tempfile.TemporaryDirectory() as directory:
            self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=2,
            )
            checkpoint = Path(directory) / "recovery.json"
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
            state["documents"][0]["status"] = "pending"
            state["documents"][0]["relative_path"] = None
            state["documents"][0]["byte_count"] = 0
            state["documents"][0]["last_error"] = "provider_unavailable"
            state["successful_documents"] = 1
            checkpoint.write_text(json.dumps(state), encoding="utf-8")
            fetched_before = list(adapter.fetched)

            with self.assertRaisesRegex(api.PJeRecoveryError, "status|pending"):
                self.execute(
                    api,
                    contract,
                    adapter,
                    self.scenario(provider),
                    directory,
                    max_attempts=2,
                )
            self.assertEqual(adapter.fetched, fetched_before)

    def test_explicit_subset_never_fetches_unrequested_documents(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(provider, acquisition)
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(
                api,
                contract,
                adapter,
                self.scenario(provider),
                directory,
                max_attempts=2,
                requested_document_ids=("DOC-002",),
            )

            self.assertEqual(result.state["status"], "complete")
            self.assertEqual(adapter.fetched, ["DOC-002"])
            self.assertEqual(
                [item["document_id"] for item in result.state["documents"]],
                ["DOC-002"],
            )

    def test_invalid_retry_configuration_fails_before_provider_access(self) -> None:
        api, acquisition, provider, contract = self.apis()
        adapter = TransientDocumentAdapter(provider, acquisition)
        with tempfile.TemporaryDirectory() as directory:
            for value in (0, True, 6):
                with self.subTest(max_attempts=value):
                    with self.assertRaisesRegex(api.PJeRecoveryError, "max_attempts"):
                        self.execute(
                            api,
                            contract,
                            adapter,
                            self.scenario(provider),
                            directory,
                            max_attempts=value,
                        )
            self.assertEqual(adapter.fetched, [])


if __name__ == "__main__":
    unittest.main()
