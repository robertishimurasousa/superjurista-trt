from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

from tests.provider_fakes import FakePJeAdapter, FakeResearchAdapter


ROOT = Path(__file__).resolve().parents[1]
INTERFACES = ROOT / "runtime" / "providers" / "interfaces.json"
SCRIPTS = ROOT / "scripts"


class ProviderInterfacesTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("provider_interfaces")
        except ModuleNotFoundError as error:
            self.fail(f"provider interface module is missing: {error}")

    def pje_scenario(self, api):
        return api.PJeContractScenario(
            tribunal_code="TRT99",
            instance=1,
            case_number="0000000-00.2026.5.99.0001",
            authorization_scope="authorized_synthetic_fixture",
        )

    def research_scenario(self, api):
        return api.ResearchContractScenario(
            tribunal_code="TRT99",
            source="regional_jurisprudence",
            query="synthetic overtime question",
        )

    def test_pje_fake_executes_complete_contract_for_non_trt12(self) -> None:
        api = self.api()
        contracts = api.load_provider_interfaces(INTERFACES)
        adapter = FakePJeAdapter(api)

        report = api.verify_pje_adapter(
            contracts["pje_case_acquisition"],
            adapter,
            self.pje_scenario(api),
        )

        self.assertEqual(
            report,
            {
                "status": "conformant",
                "interface_id": "pje_case_acquisition",
                "interface_version": 1,
                "provider_id": "fake-pje",
                "tribunal_code": "TRT99",
                "instance": 1,
                "document_count": 1,
                "page_count": 2,
            },
        )

    def test_research_fake_executes_official_source_contract_for_non_trt12(self) -> None:
        api = self.api()
        contracts = api.load_provider_interfaces(INTERFACES)
        adapter = FakeResearchAdapter(api)

        report = api.verify_research_adapter(
            contracts["legal_research"],
            adapter,
            self.research_scenario(api),
        )

        self.assertEqual(
            report,
            {
                "status": "conformant",
                "interface_id": "legal_research",
                "interface_version": 1,
                "provider_id": "fake-research",
                "tribunal_code": "TRT99",
                "result_count": 1,
                "page_count": 1,
            },
        )

    def test_pje_contract_rejects_missing_required_capability(self) -> None:
        api = self.api()
        contracts = api.load_provider_interfaces(INTERFACES)
        adapter = FakePJeAdapter(
            api,
            capabilities=("validate_session", "discover_case", "list_documents"),
        )

        with self.assertRaisesRegex(api.ProviderContractViolation, "fetch_document"):
            api.verify_pje_adapter(
                contracts["pje_case_acquisition"],
                adapter,
                self.pje_scenario(api),
            )

    def test_pje_contract_rejects_download_hash_mismatch(self) -> None:
        api = self.api()
        contracts = api.load_provider_interfaces(INTERFACES)
        adapter = FakePJeAdapter(api, corrupt_payload=True)

        with self.assertRaisesRegex(api.ProviderContractViolation, "SHA-256"):
            api.verify_pje_adapter(
                contracts["pje_case_acquisition"],
                adapter,
                self.pje_scenario(api),
            )

    def test_pje_contract_rejects_repeated_pagination_cursor(self) -> None:
        api = self.api()
        contracts = api.load_provider_interfaces(INTERFACES)
        adapter = FakePJeAdapter(api, repeat_cursor=True)

        with self.assertRaisesRegex(api.ProviderContractViolation, "pagination cursor"):
            api.verify_pje_adapter(
                contracts["pje_case_acquisition"],
                adapter,
                self.pje_scenario(api),
            )

    def test_research_contract_rejects_non_https_official_source(self) -> None:
        api = self.api()
        contracts = api.load_provider_interfaces(INTERFACES)
        adapter = FakeResearchAdapter(api, official_url="http://example.test/source")

        with self.assertRaisesRegex(api.ProviderContractViolation, "official_url"):
            api.verify_research_adapter(
                contracts["legal_research"],
                adapter,
                self.research_scenario(api),
            )


if __name__ == "__main__":
    unittest.main()
