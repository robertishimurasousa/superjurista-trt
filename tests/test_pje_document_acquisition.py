from __future__ import annotations

import hashlib
import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
INTERFACES = ROOT / "runtime" / "providers" / "interfaces.json"
INDEX_SCHEMA = ROOT / "runtime" / "providers" / "document-index-contract.json"


class SyntheticDocumentAdapter:
    def __init__(
        self,
        provider,
        acquisition,
        *,
        missing_requested=False,
        unavailable_id=None,
        corrupt_id=None,
        repeat_cursor=False,
        duplicate_id=False,
    ):
        self.provider = provider
        self.acquisition = acquisition
        self.missing_requested = missing_requested
        self.unavailable_id = unavailable_id
        self.corrupt_id = corrupt_id
        self.repeat_cursor = repeat_cursor
        self.duplicate_id = duplicate_id
        self.contents = {
            "DOC-001": b"synthetic initial pleading",
            "DOC-002": b"synthetic defense",
        }
        self.fetched = []
        self.descriptor = provider.AdapterDescriptor(
            provider_id="synthetic-pje",
            interface_id="pje_case_acquisition",
            interface_version=1,
            capabilities=(
                "validate_session",
                "discover_case",
                "list_documents",
                "fetch_document",
            ),
            supported_tribunals=("TRT99",),
        )

    def validate_session(self, request):
        return self.provider.SessionResult(status="valid")

    def discover_case(self, request):
        return self.provider.CaseRecord(
            case_number=request.case_number,
            tribunal_code=request.tribunal_code,
            instance=request.instance,
            court_unit="Synthetic Labor Court",
            task_id="TASK-001",
        )

    def record(self, document_id):
        content = self.contents[document_id]
        return self.provider.DocumentRecord(
            document_id=document_id,
            filename=f"{document_id.lower()}.pdf",
            mime_type="application/pdf",
            sha256=hashlib.sha256(content).hexdigest(),
            source_locator=f"synthetic event {document_id[-1]}",
        )

    def list_documents(self, request):
        if request.cursor is None:
            return self.provider.DocumentPage(
                items=(self.record("DOC-002"),),
                next_cursor="page-2",
                complete=False,
            )
        if self.repeat_cursor:
            return self.provider.DocumentPage(
                items=(),
                next_cursor="page-2",
                complete=False,
            )
        document_id = "DOC-002" if self.duplicate_id else "DOC-001"
        return self.provider.DocumentPage(
            items=(self.record(document_id),),
            next_cursor=None,
            complete=True,
        )

    def fetch_document(self, request):
        self.fetched.append(request.document_id)
        if request.document_id == self.unavailable_id:
            raise self.acquisition.DocumentUnavailable(
                request.document_id,
                "provider_unavailable",
            )
        content = self.contents[request.document_id]
        if request.document_id == self.corrupt_id:
            content += b"corrupt"
        return self.provider.DocumentPayload(
            document_id=request.document_id,
            content=content,
        )


class PJeDocumentAcquisitionTest(unittest.TestCase):
    def apis(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            acquisition = importlib.import_module("acquire_pje_documents")
        except ModuleNotFoundError as error:
            self.fail(f"PJe document acquisition module is missing: {error}")
        provider = importlib.import_module("provider_interfaces")
        interfaces = provider.load_provider_interfaces(INTERFACES)
        return acquisition, provider, interfaces["pje_case_acquisition"]

    def scenario(self, provider):
        return provider.PJeContractScenario(
            tribunal_code="TRT99",
            instance=1,
            case_number="0000000-00.2026.5.99.0001",
            authorization_scope="synthetic-authorized-scope",
        )

    def acquire(self, *, adapter_changes=None, requested=()):
        api, provider, contract = self.apis()
        adapter = SyntheticDocumentAdapter(
            provider,
            api,
            **(adapter_changes or {}),
        )
        result = api.acquire_pje_documents(
            contract,
            adapter,
            self.scenario(provider),
            requested_document_ids=requested,
            index_schema=INDEX_SCHEMA,
        )
        return api, adapter, result

    def test_builds_deterministic_paginated_index_and_verified_payloads(self) -> None:
        _, first_adapter, first = self.acquire()
        _, second_adapter, second = self.acquire()

        self.assertEqual(first, second)
        self.assertEqual(first.index["status"], "complete")
        self.assertEqual(first.index["page_count"], 2)
        self.assertEqual(
            [item["document_id"] for item in first.index["documents"]],
            ["DOC-001", "DOC-002"],
        )
        self.assertTrue(
            all(item["download_status"] == "downloaded" for item in first.index["documents"])
        )
        self.assertEqual(set(first.payloads), {"DOC-001", "DOC-002"})
        self.assertEqual(first_adapter.fetched, ["DOC-001", "DOC-002"])
        self.assertEqual(second_adapter.fetched, ["DOC-001", "DOC-002"])

    def test_requested_subset_preserves_full_index_without_downloading_others(self) -> None:
        _, adapter, result = self.acquire(requested=("DOC-002",))

        statuses = {
            item["document_id"]: item["download_status"]
            for item in result.index["documents"]
        }
        self.assertEqual(statuses, {"DOC-001": "not_requested", "DOC-002": "downloaded"})
        self.assertEqual(adapter.fetched, ["DOC-002"])
        self.assertEqual(set(result.payloads), {"DOC-002"})
        self.assertEqual(result.index["status"], "complete")

    def test_missing_requested_document_is_an_explicit_gap(self) -> None:
        _, _, result = self.acquire(requested=("DOC-999",))

        self.assertEqual(result.index["status"], "partial")
        self.assertEqual(
            result.index["gaps"],
            [{"subject_id": "DOC-999", "reason_code": "not_listed"}],
        )

    def test_declared_provider_unavailability_is_an_explicit_gap(self) -> None:
        _, _, result = self.acquire(
            adapter_changes={"unavailable_id": "DOC-002"},
        )

        self.assertEqual(result.index["status"], "partial")
        self.assertEqual(
            result.index["gaps"],
            [{"subject_id": "DOC-002", "reason_code": "provider_unavailable"}],
        )
        item = next(
            item for item in result.index["documents"] if item["document_id"] == "DOC-002"
        )
        self.assertEqual(item["download_status"], "unavailable")
        self.assertNotIn("DOC-002", result.payloads)

    def test_hash_mismatch_fails_closed(self) -> None:
        api, provider, contract = self.apis()
        adapter = SyntheticDocumentAdapter(
            provider,
            api,
            corrupt_id="DOC-001",
        )

        with self.assertRaisesRegex(api.DocumentAcquisitionError, "SHA-256"):
            api.acquire_pje_documents(
                contract,
                adapter,
                self.scenario(provider),
                index_schema=INDEX_SCHEMA,
            )

    def test_duplicate_document_or_repeated_cursor_fails_closed(self) -> None:
        api, provider, contract = self.apis()
        cases = (
            ({"duplicate_id": True}, "duplicate"),
            ({"repeat_cursor": True}, "cursor"),
        )
        for changes, expected in cases:
            with self.subTest(changes=changes):
                adapter = SyntheticDocumentAdapter(provider, api, **changes)
                with self.assertRaisesRegex(api.DocumentAcquisitionError, expected):
                    api.acquire_pje_documents(
                        contract,
                        adapter,
                        self.scenario(provider),
                        index_schema=INDEX_SCHEMA,
                    )

    def test_requested_identifiers_must_be_stable_and_unique(self) -> None:
        api, provider, contract = self.apis()
        adapter = SyntheticDocumentAdapter(provider, api)
        for requested in (("invalid",), ("DOC-001", "DOC-001")):
            with self.subTest(requested=requested):
                with self.assertRaises(api.DocumentAcquisitionError):
                    api.acquire_pje_documents(
                        contract,
                        adapter,
                        self.scenario(provider),
                        requested_document_ids=requested,
                        index_schema=INDEX_SCHEMA,
                    )

    def test_output_satisfies_the_versioned_document_index_schema(self) -> None:
        _, _, result = self.acquire()
        schema_api = importlib.import_module("schema_validation")
        schema = schema_api.load_json(INDEX_SCHEMA, "document index schema")

        self.assertEqual(schema_api.validate_schema_value(result.index, schema), [])


if __name__ == "__main__":
    unittest.main()
