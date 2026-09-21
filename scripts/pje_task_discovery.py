#!/usr/bin/env python3
"""Provider-neutral discovery of authorized PJe tasks and case queues.

Concrete adapters translate provider payloads into the immutable records below. The shared
runner owns validation, pagination safety, deterministic output, and secret-free reporting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Protocol, Tuple

from provider_interfaces import AdapterDescriptor
from schema_validation import ContractError, load_json


TRIBUNAL_PATTERN = re.compile(r"TRT([1-9][0-9]?)")
CASE_NUMBER_PATTERN = re.compile(
    r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.5\.([0-9]{2})\.[0-9]{4}"
)
TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9_-]*")
TASK_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


class TaskDiscoveryContractViolation(ValueError):
    """Raised when a task-discovery provider violates the shared contract."""


@dataclass(frozen=True)
class TaskDiscoveryCheck:
    tribunal_code: str
    instance: int
    authorization_scope: str


@dataclass(frozen=True)
class TaskListRequest:
    tribunal_code: str
    instance: int
    authorization_scope: str
    cursor: Optional[str]


@dataclass(frozen=True)
class TaskQueueRequest:
    tribunal_code: str
    instance: int
    authorization_scope: str
    task_id: str
    cursor: Optional[str]


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    task_name: str


@dataclass(frozen=True)
class QueueCaseRecord:
    case_number: str
    task_id: str
    court_unit: str


@dataclass(frozen=True)
class TaskPage:
    items: Tuple[TaskRecord, ...]
    next_cursor: Optional[str]
    complete: bool


@dataclass(frozen=True)
class CasePage:
    items: Tuple[QueueCaseRecord, ...]
    next_cursor: Optional[str]
    complete: bool


class TaskDiscoveryProbe(Protocol):
    descriptor: AdapterDescriptor

    def list_tasks(self, request: TaskListRequest) -> TaskPage:
        ...

    def list_task_cases(self, request: TaskQueueRequest) -> CasePage:
        ...


def _expect_exact_keys(value: dict, expected: set, label: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise ContractError(f"{label} missing field(s): {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{label} has unknown field(s): {', '.join(unknown)}")


def load_task_discovery_contract(path: Path) -> Dict[str, object]:
    """Load and strictly validate the PJe task-discovery contract."""
    contract = load_json(path, "PJe task discovery contract")
    if not isinstance(contract, dict):
        raise ContractError("PJe task discovery contract root must be an object")
    expected = {
        "schema_version",
        "interface_id",
        "interface_version",
        "required_capabilities",
        "max_task_pages",
        "max_case_pages_per_task",
    }
    _expect_exact_keys(contract, expected, "PJe task discovery contract")
    if contract["schema_version"] != 1:
        raise ContractError("PJe task discovery schema_version must be 1")
    if contract["interface_id"] != "pje_case_acquisition":
        raise ContractError("PJe task discovery interface_id is unsupported")
    if contract["interface_version"] != 1:
        raise ContractError("PJe task discovery interface_version must be 1")

    capabilities = contract["required_capabilities"]
    if capabilities != ["list_tasks", "list_task_cases"]:
        raise ContractError("PJe task discovery capabilities are unsupported")
    for field in ("max_task_pages", "max_case_pages_per_task"):
        value = contract[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ContractError(f"{field} must be a positive integer")
    return contract


def _validate_check(check: TaskDiscoveryCheck) -> re.Match:
    if not isinstance(check, TaskDiscoveryCheck):
        raise TaskDiscoveryContractViolation("task discovery check has an invalid type")
    if not isinstance(check.tribunal_code, str):
        raise TaskDiscoveryContractViolation("tribunal_code must be a string")
    tribunal_match = TRIBUNAL_PATTERN.fullmatch(check.tribunal_code)
    if tribunal_match is None:
        raise TaskDiscoveryContractViolation("tribunal_code must identify a labor court")
    if isinstance(check.instance, bool) or check.instance not in (1, 2):
        raise TaskDiscoveryContractViolation("instance must be 1 or 2")
    if not isinstance(check.authorization_scope, str) or not check.authorization_scope.strip():
        raise TaskDiscoveryContractViolation("authorization_scope must not be empty")
    return tribunal_match


def _validate_descriptor(contract: dict, descriptor: object, tribunal_code: str) -> None:
    if not isinstance(descriptor, AdapterDescriptor):
        raise TaskDiscoveryContractViolation("task discovery descriptor is missing or invalid")
    if TOKEN_PATTERN.fullmatch(descriptor.provider_id) is None:
        raise TaskDiscoveryContractViolation("task discovery provider_id is invalid")
    if descriptor.interface_id != contract["interface_id"]:
        raise TaskDiscoveryContractViolation("task discovery interface_id is incompatible")
    if descriptor.interface_version != contract["interface_version"]:
        raise TaskDiscoveryContractViolation("task discovery interface_version is incompatible")
    if not isinstance(descriptor.capabilities, tuple):
        raise TaskDiscoveryContractViolation("task discovery capabilities must be a tuple")
    if len(descriptor.capabilities) != len(set(descriptor.capabilities)):
        raise TaskDiscoveryContractViolation("task discovery capabilities must be unique")
    missing = sorted(set(contract["required_capabilities"]) - set(descriptor.capabilities))
    if missing:
        raise TaskDiscoveryContractViolation(
            f"task discovery probe requires capability: {', '.join(missing)}"
        )
    if tribunal_code not in descriptor.supported_tribunals:
        raise TaskDiscoveryContractViolation("task discovery probe does not support the tribunal")


def _require_method(probe: object, name: str):
    method = getattr(probe, name, None)
    if not callable(method):
        raise TaskDiscoveryContractViolation(f"task discovery capability is not callable: {name}")
    return method


def _validate_page_state(
    complete: bool,
    next_cursor: Optional[str],
    seen_cursors: set,
) -> Optional[str]:
    if not isinstance(complete, bool):
        raise TaskDiscoveryContractViolation("page complete flag must be boolean")
    if complete:
        if next_cursor is not None:
            raise TaskDiscoveryContractViolation("complete page must not expose a pagination cursor")
        return None
    if not isinstance(next_cursor, str) or not next_cursor:
        raise TaskDiscoveryContractViolation("incomplete page requires a pagination cursor")
    if next_cursor in seen_cursors:
        raise TaskDiscoveryContractViolation("provider repeated a pagination cursor")
    seen_cursors.add(next_cursor)
    return next_cursor


def _validate_task(task: object) -> TaskRecord:
    if not isinstance(task, TaskRecord):
        raise TaskDiscoveryContractViolation("task page contains an invalid record")
    if TASK_ID_PATTERN.fullmatch(task.task_id) is None:
        raise TaskDiscoveryContractViolation("task_id is invalid")
    if not isinstance(task.task_name, str) or not task.task_name.strip():
        raise TaskDiscoveryContractViolation("task_name must not be empty")
    return task


def _validate_case(
    record: object,
    task_id: str,
    expected_region: str,
) -> QueueCaseRecord:
    if not isinstance(record, QueueCaseRecord):
        raise TaskDiscoveryContractViolation("case page contains an invalid record")
    case_match = CASE_NUMBER_PATTERN.fullmatch(record.case_number)
    if case_match is None:
        raise TaskDiscoveryContractViolation("case_number must use the CNJ numbering format")
    if case_match.group(1) != expected_region:
        raise TaskDiscoveryContractViolation("case_number region does not match tribunal_code")
    if record.task_id != task_id:
        raise TaskDiscoveryContractViolation("case record does not match the requested task")
    if not isinstance(record.court_unit, str) or not record.court_unit.strip():
        raise TaskDiscoveryContractViolation("case court_unit must not be empty")
    return record


def _list_all_tasks(contract: dict, probe: TaskDiscoveryProbe, check: TaskDiscoveryCheck):
    tasks: Dict[str, TaskRecord] = {}
    cursor: Optional[str] = None
    seen_cursors = set()
    page_count = 0
    while True:
        page_count += 1
        if page_count > contract["max_task_pages"]:
            raise TaskDiscoveryContractViolation("task pagination exceeded max_task_pages")
        page = _require_method(probe, "list_tasks")(
            TaskListRequest(
                tribunal_code=check.tribunal_code,
                instance=check.instance,
                authorization_scope=check.authorization_scope,
                cursor=cursor,
            )
        )
        if not isinstance(page, TaskPage) or not isinstance(page.items, tuple):
            raise TaskDiscoveryContractViolation("task listing returned an invalid page")
        for item in page.items:
            task = _validate_task(item)
            if task.task_id in tasks:
                raise TaskDiscoveryContractViolation("task_id must be unique across pages")
            tasks[task.task_id] = task
        cursor = _validate_page_state(page.complete, page.next_cursor, seen_cursors)
        if page.complete:
            return tasks, page_count


def _list_all_cases(
    contract: dict,
    probe: TaskDiscoveryProbe,
    check: TaskDiscoveryCheck,
    task: TaskRecord,
    expected_region: str,
):
    cases: Dict[str, QueueCaseRecord] = {}
    cursor: Optional[str] = None
    seen_cursors = set()
    page_count = 0
    while True:
        page_count += 1
        if page_count > contract["max_case_pages_per_task"]:
            raise TaskDiscoveryContractViolation(
                "case pagination exceeded max_case_pages_per_task"
            )
        page = _require_method(probe, "list_task_cases")(
            TaskQueueRequest(
                tribunal_code=check.tribunal_code,
                instance=check.instance,
                authorization_scope=check.authorization_scope,
                task_id=task.task_id,
                cursor=cursor,
            )
        )
        if not isinstance(page, CasePage) or not isinstance(page.items, tuple):
            raise TaskDiscoveryContractViolation("case listing returned an invalid page")
        for item in page.items:
            record = _validate_case(item, task.task_id, expected_region)
            if record.case_number in cases:
                raise TaskDiscoveryContractViolation(
                    "case_number must be unique within a task across pages"
                )
            cases[record.case_number] = record
        cursor = _validate_page_state(page.complete, page.next_cursor, seen_cursors)
        if page.complete:
            return cases, page_count


def discover_authorized_queue(
    contract: dict,
    probe: TaskDiscoveryProbe,
    check: TaskDiscoveryCheck,
) -> dict:
    """Discover every normalized task and case visible to an authorized probe."""
    tribunal_match = _validate_check(check)
    descriptor = getattr(probe, "descriptor", None)
    _validate_descriptor(contract, descriptor, check.tribunal_code)
    tasks, task_page_count = _list_all_tasks(contract, probe, check)

    task_results = []
    case_count = 0
    case_page_count = 0
    expected_region = tribunal_match.group(1).zfill(2)
    for task_id in sorted(tasks):
        task = tasks[task_id]
        cases, pages = _list_all_cases(contract, probe, check, task, expected_region)
        case_page_count += pages
        case_count += len(cases)
        task_results.append(
            {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "cases": [
                    {
                        "case_number": record.case_number,
                        "court_unit": record.court_unit,
                    }
                    for record in (cases[number] for number in sorted(cases))
                ],
            }
        )

    return {
        "status": "complete",
        "provider_id": descriptor.provider_id,
        "tribunal_code": check.tribunal_code,
        "instance": check.instance,
        "task_count": len(tasks),
        "case_count": case_count,
        "task_page_count": task_page_count,
        "case_page_count": case_page_count,
        "tasks": task_results,
    }
