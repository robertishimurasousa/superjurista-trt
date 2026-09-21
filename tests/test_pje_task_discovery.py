from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACT = ROOT / "runtime" / "providers" / "pje-task-discovery-contract.json"


class FakeTaskDiscoveryProbe:
    def __init__(
        self,
        api,
        task_pages,
        case_pages,
        *,
        capabilities=("list_tasks", "list_task_cases"),
        secret="private-probe-secret-that-must-not-leak",
    ) -> None:
        self.task_pages = task_pages
        self.case_pages = case_pages
        self.secret = secret
        self.descriptor = api.AdapterDescriptor(
            provider_id="fake-task-discovery",
            interface_id="pje_case_acquisition",
            interface_version=1,
            capabilities=capabilities,
            supported_tribunals=("TRT99",),
        )

    def list_tasks(self, request):
        return self.task_pages[request.cursor]

    def list_task_cases(self, request):
        return self.case_pages[(request.task_id, request.cursor)]


class PJeTaskDiscoveryTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("pje_task_discovery")
        except ModuleNotFoundError as error:
            self.fail(f"PJe task discovery module is missing: {error}")

    def check(self, api, *, authorization_scope="authorized_synthetic_fixture"):
        return api.TaskDiscoveryCheck(
            tribunal_code="TRT99",
            instance=1,
            authorization_scope=authorization_scope,
        )

    def complete_probe(self, api):
        task_one = api.TaskRecord(task_id="TASK-001", task_name="Synthetic judgments")
        task_two = api.TaskRecord(task_id="TASK-002", task_name="Synthetic decisions")
        case_one = api.QueueCaseRecord(
            case_number="0000001-00.2026.5.99.0001",
            task_id="TASK-001",
            court_unit="Synthetic Labor Court 1",
        )
        case_two = api.QueueCaseRecord(
            case_number="0000002-00.2026.5.99.0002",
            task_id="TASK-001",
            court_unit="Synthetic Labor Court 2",
        )
        task_pages = {
            None: api.TaskPage(items=(task_one,), next_cursor="task-page-2", complete=False),
            "task-page-2": api.TaskPage(items=(task_two,), next_cursor=None, complete=True),
        }
        case_pages = {
            ("TASK-001", None): api.CasePage(
                items=(case_one,), next_cursor="case-page-2", complete=False
            ),
            ("TASK-001", "case-page-2"): api.CasePage(
                items=(case_two,), next_cursor=None, complete=True
            ),
            ("TASK-002", None): api.CasePage(items=(), next_cursor=None, complete=True),
        }
        return FakeTaskDiscoveryProbe(api, task_pages, case_pages)

    def discover(self, api, probe, *, authorization_scope="authorized_synthetic_fixture"):
        contract = api.load_task_discovery_contract(CONTRACT)
        return api.discover_authorized_queue(
            contract,
            probe,
            self.check(api, authorization_scope=authorization_scope),
        )

    def test_discovers_every_task_and_case_across_pages(self) -> None:
        api = self.api()

        result = self.discover(api, self.complete_probe(api))

        self.assertEqual(
            result,
            {
                "status": "complete",
                "provider_id": "fake-task-discovery",
                "tribunal_code": "TRT99",
                "instance": 1,
                "task_count": 2,
                "case_count": 2,
                "task_page_count": 2,
                "case_page_count": 3,
                "tasks": [
                    {
                        "task_id": "TASK-001",
                        "task_name": "Synthetic judgments",
                        "cases": [
                            {
                                "case_number": "0000001-00.2026.5.99.0001",
                                "court_unit": "Synthetic Labor Court 1",
                            },
                            {
                                "case_number": "0000002-00.2026.5.99.0002",
                                "court_unit": "Synthetic Labor Court 2",
                            },
                        ],
                    },
                    {
                        "task_id": "TASK-002",
                        "task_name": "Synthetic decisions",
                        "cases": [],
                    },
                ],
            },
        )

    def test_empty_authorized_queue_is_a_complete_result(self) -> None:
        api = self.api()
        probe = FakeTaskDiscoveryProbe(
            api,
            {None: api.TaskPage(items=(), next_cursor=None, complete=True)},
            {},
        )

        result = self.discover(api, probe)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["task_count"], 0)
        self.assertEqual(result["case_count"], 0)
        self.assertEqual(result["tasks"], [])

    def test_repeated_task_cursor_fails_closed(self) -> None:
        api = self.api()
        task = api.TaskRecord(task_id="TASK-001", task_name="Synthetic judgments")
        probe = FakeTaskDiscoveryProbe(
            api,
            {
                None: api.TaskPage(items=(task,), next_cursor="repeat", complete=False),
                "repeat": api.TaskPage(items=(), next_cursor="repeat", complete=False),
            },
            {},
        )

        with self.assertRaisesRegex(api.TaskDiscoveryContractViolation, "pagination cursor"):
            self.discover(api, probe)

    def test_repeated_case_cursor_fails_closed(self) -> None:
        api = self.api()
        task = api.TaskRecord(task_id="TASK-001", task_name="Synthetic judgments")
        probe = FakeTaskDiscoveryProbe(
            api,
            {None: api.TaskPage(items=(task,), next_cursor=None, complete=True)},
            {
                ("TASK-001", None): api.CasePage(
                    items=(), next_cursor="repeat", complete=False
                ),
                ("TASK-001", "repeat"): api.CasePage(
                    items=(), next_cursor="repeat", complete=False
                ),
            },
        )

        with self.assertRaisesRegex(api.TaskDiscoveryContractViolation, "pagination cursor"):
            self.discover(api, probe)

    def test_duplicate_case_within_task_fails_closed(self) -> None:
        api = self.api()
        task = api.TaskRecord(task_id="TASK-001", task_name="Synthetic judgments")
        case = api.QueueCaseRecord(
            case_number="0000001-00.2026.5.99.0001",
            task_id="TASK-001",
            court_unit="Synthetic Labor Court 1",
        )
        probe = FakeTaskDiscoveryProbe(
            api,
            {None: api.TaskPage(items=(task,), next_cursor=None, complete=True)},
            {
                ("TASK-001", None): api.CasePage(
                    items=(case,), next_cursor="next", complete=False
                ),
                ("TASK-001", "next"): api.CasePage(
                    items=(case,), next_cursor=None, complete=True
                ),
            },
        )

        with self.assertRaisesRegex(api.TaskDiscoveryContractViolation, "case_number"):
            self.discover(api, probe)

    def test_case_region_must_match_requested_tribunal(self) -> None:
        api = self.api()
        task = api.TaskRecord(task_id="TASK-001", task_name="Synthetic judgments")
        wrong_region = api.QueueCaseRecord(
            case_number="0000001-00.2026.5.12.0001",
            task_id="TASK-001",
            court_unit="Synthetic Labor Court 1",
        )
        probe = FakeTaskDiscoveryProbe(
            api,
            {None: api.TaskPage(items=(task,), next_cursor=None, complete=True)},
            {
                ("TASK-001", None): api.CasePage(
                    items=(wrong_region,), next_cursor=None, complete=True
                )
            },
        )

        with self.assertRaisesRegex(api.TaskDiscoveryContractViolation, "region"):
            self.discover(api, probe)

    def test_missing_task_case_capability_is_rejected(self) -> None:
        api = self.api()
        probe = FakeTaskDiscoveryProbe(
            api,
            {None: api.TaskPage(items=(), next_cursor=None, complete=True)},
            {},
            capabilities=("list_tasks",),
        )

        with self.assertRaisesRegex(api.TaskDiscoveryContractViolation, "list_task_cases"):
            self.discover(api, probe)

    def test_result_never_serializes_authorization_scope_or_probe_secret(self) -> None:
        api = self.api()
        authorization_scope = "private-authorization-scope-1234567890"
        probe = self.complete_probe(api)

        result = self.discover(api, probe, authorization_scope=authorization_scope)
        serialized = json.dumps(result, sort_keys=True)

        self.assertNotIn(authorization_scope, serialized)
        self.assertNotIn(probe.secret, serialized)


if __name__ == "__main__":
    unittest.main()
