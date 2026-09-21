#!/usr/bin/env python3
"""Runtime-neutral provider interfaces and deterministic conformance runners."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Tuple
from urllib.parse import urlsplit

from schema_validation import ContractError, load_json


TRIBUNAL_PATTERN = re.compile(r"TRT([1-9][0-9]?)")
CASE_NUMBER_PATTERN = re.compile(
    r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.5\.([0-9]{2})\.[0-9]{4}"
)
TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9_-]*")
DOCUMENT_ID_PATTERN = re.compile(r"DOC-[0-9]{3,}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ALLOWED_RESEARCH_STATUSES = {
    "current",
    "pending",
    "stayed",
    "overruled",
    "cancelled",
    "conflicting",
    "unknown",
}


class ProviderContractViolation(ValueError):
    """Raised when an adapter or provider response violates a shared contract."""


@dataclass(frozen=True)
class AdapterDescriptor:
    provider_id: str
    interface_id: str
    interface_version: int
    capabilities: Tuple[str, ...]
    supported_tribunals: Tuple[str, ...]


@dataclass(frozen=True)
class PJeContractScenario:
    tribunal_code: str
    instance: int
    case_number: str
    authorization_scope: str


@dataclass(frozen=True)
class SessionRequest:
    tribunal_code: str
    instance: int
    authorization_scope: str


@dataclass(frozen=True)
class SessionResult:
    status: str


@dataclass(frozen=True)
class CaseRequest:
    tribunal_code: str
    instance: int
    case_number: str
    authorization_scope: str


@dataclass(frozen=True)
class CaseRecord:
    case_number: str
    tribunal_code: str
    instance: int
    court_unit: str
    task_id: str


@dataclass(frozen=True)
class DocumentListRequest:
    tribunal_code: str
    instance: int
    case_number: str
    authorization_scope: str
    cursor: Optional[str]


@dataclass(frozen=True)
class DocumentFetchRequest:
    tribunal_code: str
    instance: int
    case_number: str
    authorization_scope: str
    document_id: str


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    filename: str
    mime_type: str
    sha256: str
    source_locator: str


@dataclass(frozen=True)
class DocumentPage:
    items: Tuple[DocumentRecord, ...]
    next_cursor: Optional[str]
    complete: bool


@dataclass(frozen=True)
class DocumentPayload:
    document_id: str
    content: bytes


@dataclass(frozen=True)
class ResearchContractScenario:
    tribunal_code: str
    source: str
    query: str


@dataclass(frozen=True)
class ResearchQuery:
    tribunal_code: str
    source: str
    query: str
    cursor: Optional[str]


@dataclass(frozen=True)
class ResearchHit:
    source_id: str
    origin: str
    reference: str
    status: str
    official_url: str


@dataclass(frozen=True)
class ResearchPage:
    items: Tuple[ResearchHit, ...]
    next_cursor: Optional[str]
    complete: bool


@dataclass(frozen=True)
class ResearchFetchRequest:
    tribunal_code: str
    source: str
    source_id: str


@dataclass(frozen=True)
class ResearchSource:
    source_id: str
    origin: str
    reference: str
    status: str
    status_notes: Tuple[str, ...]
    binding_scope: str
    legal_question: str
    holding: str
    verbatim_excerpt: str
    official_url: str
    retrieved_at: str


class PJeAdapter(Protocol):
    descriptor: AdapterDescriptor

    def validate_session(self, request: SessionRequest) -> SessionResult:
        ...

    def discover_case(self, request: CaseRequest) -> CaseRecord:
        ...

    def list_documents(self, request: DocumentListRequest) -> DocumentPage:
        ...

    def fetch_document(self, request: DocumentFetchRequest) -> DocumentPayload:
        ...


class ResearchAdapter(Protocol):
    descriptor: AdapterDescriptor

    def search(self, request: ResearchQuery) -> ResearchPage:
        ...

    def fetch_source(self, request: ResearchFetchRequest) -> ResearchSource:
        ...


def _expect_exact_keys(value: dict, expected: set, label: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise ContractError(f"{label} missing field(s): {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{label} has unknown field(s): {', '.join(unknown)}")


def load_provider_interfaces(path: Path) -> Dict[str, dict]:
    """Load and validate the versioned provider-interface manifest."""
    manifest = load_json(path, "provider interface manifest")
    if not isinstance(manifest, dict):
        raise ContractError("provider interface manifest root must be an object")
    _expect_exact_keys(manifest, {"schema_version", "interfaces"}, "manifest")
    if manifest["schema_version"] != 1:
        raise ContractError("provider interface schema_version must be 1")
    interfaces = manifest["interfaces"]
    if not isinstance(interfaces, dict) or not interfaces:
        raise ContractError("provider interface manifest requires interfaces")

    expected_fields = {
        "interface_id",
        "interface_version",
        "required_capabilities",
        "max_pages",
    }
    for interface_id, contract in interfaces.items():
        label = f"interfaces.{interface_id}"
        if not isinstance(contract, dict):
            raise ContractError(f"{label} must be an object")
        _expect_exact_keys(contract, expected_fields, label)
        if contract["interface_id"] != interface_id:
            raise ContractError(f"{label}.interface_id must match its registry key")
        if not TOKEN_PATTERN.fullmatch(interface_id):
            raise ContractError(f"{label}.interface_id is invalid")
        if contract["interface_version"] != 1:
            raise ContractError(f"{label}.interface_version must be 1")
        capabilities = contract["required_capabilities"]
        if not isinstance(capabilities, list) or not capabilities:
            raise ContractError(f"{label}.required_capabilities must be a non-empty list")
        if any(
            not isinstance(capability, str)
            or not TOKEN_PATTERN.fullmatch(capability)
            for capability in capabilities
        ):
            raise ContractError(f"{label}.required_capabilities contains an invalid value")
        if len(capabilities) != len(set(capabilities)):
            raise ContractError(f"{label}.required_capabilities must be unique")
        max_pages = contract["max_pages"]
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ContractError(f"{label}.max_pages must be a positive integer")
    return interfaces


def _validate_tribunal_code(tribunal_code: str) -> re.Match:
    if not isinstance(tribunal_code, str):
        raise ProviderContractViolation("tribunal_code must be a string")
    match = TRIBUNAL_PATTERN.fullmatch(tribunal_code)
    if match is None:
        raise ProviderContractViolation("tribunal_code must identify a regional labor court")
    return match


def _validate_descriptor(contract: dict, descriptor: Any, tribunal_code: str) -> None:
    if not isinstance(descriptor, AdapterDescriptor):
        raise ProviderContractViolation("adapter descriptor is missing or invalid")
    if not TOKEN_PATTERN.fullmatch(descriptor.provider_id):
        raise ProviderContractViolation("provider_id is invalid")
    if descriptor.interface_id != contract["interface_id"]:
        raise ProviderContractViolation("adapter interface_id does not match the contract")
    if descriptor.interface_version != contract["interface_version"]:
        raise ProviderContractViolation("adapter interface_version does not match the contract")
    if len(descriptor.capabilities) != len(set(descriptor.capabilities)):
        raise ProviderContractViolation("adapter capabilities must be unique")
    missing = sorted(set(contract["required_capabilities"]) - set(descriptor.capabilities))
    if missing:
        raise ProviderContractViolation(
            f"adapter is missing required capability: {', '.join(missing)}"
        )
    if tribunal_code not in descriptor.supported_tribunals:
        raise ProviderContractViolation(
            f"adapter does not declare support for {tribunal_code}"
        )


def _require_method(adapter: Any, name: str) -> Any:
    method = getattr(adapter, name, None)
    if not callable(method):
        raise ProviderContractViolation(f"adapter capability is not callable: {name}")
    return method


def _validate_pje_scenario(scenario: PJeContractScenario) -> None:
    tribunal_match = _validate_tribunal_code(scenario.tribunal_code)
    if scenario.instance not in (1, 2):
        raise ProviderContractViolation("instance must be 1 or 2")
    case_match = CASE_NUMBER_PATTERN.fullmatch(scenario.case_number)
    if case_match is None:
        raise ProviderContractViolation("case_number must use the CNJ numbering format")
    expected_region = tribunal_match.group(1).zfill(2)
    if case_match.group(1) != expected_region:
        raise ProviderContractViolation("case_number region does not match tribunal_code")
    if not scenario.authorization_scope.strip():
        raise ProviderContractViolation("authorization_scope must not be empty")


def _validate_page_state(
    complete: bool,
    next_cursor: Optional[str],
    seen_cursors: set,
) -> Optional[str]:
    if not isinstance(complete, bool):
        raise ProviderContractViolation("page complete flag must be boolean")
    if complete:
        if next_cursor is not None:
            raise ProviderContractViolation("complete page must not expose a pagination cursor")
        return None
    if not isinstance(next_cursor, str) or not next_cursor:
        raise ProviderContractViolation("incomplete page requires a pagination cursor")
    if next_cursor in seen_cursors:
        raise ProviderContractViolation("provider repeated a pagination cursor")
    seen_cursors.add(next_cursor)
    return next_cursor


def _validate_document(record: DocumentRecord) -> None:
    if not isinstance(record, DocumentRecord):
        raise ProviderContractViolation("document page contains an invalid record")
    if DOCUMENT_ID_PATTERN.fullmatch(record.document_id) is None:
        raise ProviderContractViolation("document_id must be stable and use DOC-NNN format")
    for field, value in (
        ("filename", record.filename),
        ("mime_type", record.mime_type),
        ("source_locator", record.source_locator),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ProviderContractViolation(f"document {field} must not be empty")
    if SHA256_PATTERN.fullmatch(record.sha256) is None:
        raise ProviderContractViolation("document SHA-256 must be lowercase hexadecimal")


def verify_pje_adapter(
    contract: dict,
    adapter: PJeAdapter,
    scenario: PJeContractScenario,
) -> dict:
    """Exercise one PJe adapter without knowing any tribunal-specific constants."""
    _validate_pje_scenario(scenario)
    descriptor = getattr(adapter, "descriptor", None)
    _validate_descriptor(contract, descriptor, scenario.tribunal_code)

    session = _require_method(adapter, "validate_session")(
        SessionRequest(
            tribunal_code=scenario.tribunal_code,
            instance=scenario.instance,
            authorization_scope=scenario.authorization_scope,
        )
    )
    if not isinstance(session, SessionResult) or session.status != "valid":
        raise ProviderContractViolation("provider session must be valid for conformance")

    case = _require_method(adapter, "discover_case")(
        CaseRequest(
            tribunal_code=scenario.tribunal_code,
            instance=scenario.instance,
            case_number=scenario.case_number,
            authorization_scope=scenario.authorization_scope,
        )
    )
    if not isinstance(case, CaseRecord):
        raise ProviderContractViolation("case discovery returned an invalid record")
    if (
        case.case_number != scenario.case_number
        or case.tribunal_code != scenario.tribunal_code
        or case.instance != scenario.instance
    ):
        raise ProviderContractViolation("discovered case does not match the request")
    if not case.court_unit.strip() or not case.task_id.strip():
        raise ProviderContractViolation("discovered case metadata is incomplete")

    documents: Dict[str, DocumentRecord] = {}
    cursor: Optional[str] = None
    seen_cursors = set()
    page_count = 0
    while True:
        page_count += 1
        if page_count > contract["max_pages"]:
            raise ProviderContractViolation("document pagination exceeded max_pages")
        page = _require_method(adapter, "list_documents")(
            DocumentListRequest(
                tribunal_code=scenario.tribunal_code,
                instance=scenario.instance,
                case_number=scenario.case_number,
                authorization_scope=scenario.authorization_scope,
                cursor=cursor,
            )
        )
        if not isinstance(page, DocumentPage):
            raise ProviderContractViolation("document listing returned an invalid page")
        for record in page.items:
            _validate_document(record)
            if record.document_id in documents:
                raise ProviderContractViolation("document_id must be unique across pages")
            documents[record.document_id] = record
        cursor = _validate_page_state(page.complete, page.next_cursor, seen_cursors)
        if page.complete:
            break

    for record in documents.values():
        payload = _require_method(adapter, "fetch_document")(
            DocumentFetchRequest(
                tribunal_code=scenario.tribunal_code,
                instance=scenario.instance,
                case_number=scenario.case_number,
                authorization_scope=scenario.authorization_scope,
                document_id=record.document_id,
            )
        )
        if not isinstance(payload, DocumentPayload):
            raise ProviderContractViolation("document download returned an invalid payload")
        if payload.document_id != record.document_id:
            raise ProviderContractViolation("downloaded document_id does not match its index")
        if not isinstance(payload.content, bytes):
            raise ProviderContractViolation("document payload content must be bytes")
        if hashlib.sha256(payload.content).hexdigest() != record.sha256:
            raise ProviderContractViolation("document payload failed SHA-256 verification")

    return {
        "status": "conformant",
        "interface_id": contract["interface_id"],
        "interface_version": contract["interface_version"],
        "provider_id": descriptor.provider_id,
        "tribunal_code": scenario.tribunal_code,
        "instance": scenario.instance,
        "document_count": len(documents),
        "page_count": page_count,
    }


def _validate_https_url(value: str, field: str) -> None:
    if not isinstance(value, str):
        raise ProviderContractViolation(f"{field} must be an HTTPS URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ProviderContractViolation(f"{field} must be an HTTPS URL")


def _validate_research_hit(hit: ResearchHit) -> None:
    if not isinstance(hit, ResearchHit):
        raise ProviderContractViolation("research page contains an invalid result")
    for field, value in (
        ("source_id", hit.source_id),
        ("origin", hit.origin),
        ("reference", hit.reference),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ProviderContractViolation(f"research {field} must not be empty")
    if hit.status not in ALLOWED_RESEARCH_STATUSES:
        raise ProviderContractViolation("research status is unsupported")
    _validate_https_url(hit.official_url, "official_url")


def _validate_retrieved_at(value: str) -> None:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ProviderContractViolation("retrieved_at must be an ISO-8601 timestamp") from error
    if timestamp.tzinfo is None:
        raise ProviderContractViolation("retrieved_at must include a timezone")


def _validate_research_source(source: ResearchSource, hit: ResearchHit) -> None:
    if not isinstance(source, ResearchSource):
        raise ProviderContractViolation("research fetch returned an invalid source")
    if source.source_id != hit.source_id:
        raise ProviderContractViolation("research source_id does not match its result")
    if source.official_url != hit.official_url:
        raise ProviderContractViolation("research official_url changed between search and fetch")
    if source.status not in ALLOWED_RESEARCH_STATUSES:
        raise ProviderContractViolation("research source status is unsupported")
    _validate_https_url(source.official_url, "official_url")
    for field, value in (
        ("origin", source.origin),
        ("reference", source.reference),
        ("binding_scope", source.binding_scope),
        ("legal_question", source.legal_question),
        ("holding", source.holding),
        ("verbatim_excerpt", source.verbatim_excerpt),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ProviderContractViolation(f"research source {field} must not be empty")
    if not isinstance(source.status_notes, tuple) or any(
        not isinstance(note, str) or not note.strip() for note in source.status_notes
    ):
        raise ProviderContractViolation("research source status_notes must contain text")
    _validate_retrieved_at(source.retrieved_at)


def verify_research_adapter(
    contract: dict,
    adapter: ResearchAdapter,
    scenario: ResearchContractScenario,
) -> dict:
    """Exercise one official-source research adapter through the shared boundary."""
    _validate_tribunal_code(scenario.tribunal_code)
    if not isinstance(scenario.source, str) or not scenario.source.strip():
        raise ProviderContractViolation("research source must not be empty")
    if not isinstance(scenario.query, str) or not scenario.query.strip():
        raise ProviderContractViolation("research query must not be empty")
    descriptor = getattr(adapter, "descriptor", None)
    _validate_descriptor(contract, descriptor, scenario.tribunal_code)

    results: Dict[str, ResearchHit] = {}
    cursor: Optional[str] = None
    seen_cursors = set()
    page_count = 0
    while True:
        page_count += 1
        if page_count > contract["max_pages"]:
            raise ProviderContractViolation("research pagination exceeded max_pages")
        page = _require_method(adapter, "search")(
            ResearchQuery(
                tribunal_code=scenario.tribunal_code,
                source=scenario.source,
                query=scenario.query,
                cursor=cursor,
            )
        )
        if not isinstance(page, ResearchPage):
            raise ProviderContractViolation("research search returned an invalid page")
        for hit in page.items:
            _validate_research_hit(hit)
            if hit.source_id in results:
                raise ProviderContractViolation("research source_id must be unique across pages")
            results[hit.source_id] = hit
        cursor = _validate_page_state(page.complete, page.next_cursor, seen_cursors)
        if page.complete:
            break

    for hit in results.values():
        source = _require_method(adapter, "fetch_source")(
            ResearchFetchRequest(
                tribunal_code=scenario.tribunal_code,
                source=scenario.source,
                source_id=hit.source_id,
            )
        )
        _validate_research_source(source, hit)

    return {
        "status": "conformant",
        "interface_id": contract["interface_id"],
        "interface_version": contract["interface_version"],
        "provider_id": descriptor.provider_id,
        "tribunal_code": scenario.tribunal_code,
        "result_count": len(results),
        "page_count": page_count,
    }
