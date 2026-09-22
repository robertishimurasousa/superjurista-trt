#!/usr/bin/env python3
"""Build a deterministic PJe document index with verified local payloads."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import provider_interfaces as provider
from schema_validation import ContractError, load_json, validate_schema_value


DEFAULT_INDEX_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "providers"
    / "document-index-contract.json"
)


class DocumentAcquisitionError(ValueError):
    """Raised when document listing or download cannot be trusted."""


class DocumentUnavailable(RuntimeError):
    """Adapter-declared bounded failure for one known document."""

    def __init__(self, document_id: str, reason_code: str) -> None:
        super().__init__(reason_code)
        self.document_id = document_id
        self.reason_code = reason_code


@dataclass(frozen=True)
class AcquisitionResult:
    index: dict
    payloads: dict[str, bytes]


def acquire_pje_documents(
    contract: dict,
    adapter: provider.PJeAdapter,
    scenario: provider.PJeContractScenario,
    *,
    requested_document_ids: tuple[str, ...] = (),
    verified_payloads: dict[str, bytes] | None = None,
    index_schema: Path = DEFAULT_INDEX_SCHEMA,
) -> AcquisitionResult:
    """List all metadata and download the requested set with SHA-256 custody."""
    requested = _requested_ids(requested_document_ids)
    recovered = _verified_payload_map(verified_payloads)
    try:
        provider._validate_pje_scenario(scenario)
        descriptor = getattr(adapter, "descriptor", None)
        provider._validate_descriptor(contract, descriptor, scenario.tribunal_code)
        session = provider._require_method(adapter, "validate_session")(
            provider.SessionRequest(
                tribunal_code=scenario.tribunal_code,
                instance=scenario.instance,
                authorization_scope=scenario.authorization_scope,
            )
        )
        if not isinstance(session, provider.SessionResult) or session.status != "valid":
            raise DocumentAcquisitionError("provider session is not valid")
        case = provider._require_method(adapter, "discover_case")(
            provider.CaseRequest(
                tribunal_code=scenario.tribunal_code,
                instance=scenario.instance,
                case_number=scenario.case_number,
                authorization_scope=scenario.authorization_scope,
            )
        )
        _validate_case(case, scenario)
        documents, page_count = _list_documents(contract, adapter, scenario)
    except provider.ProviderContractViolation as error:
        raise DocumentAcquisitionError(str(error)) from error

    target_ids = requested or set(documents)
    unknown_recovered = set(recovered) - target_ids
    if unknown_recovered:
        raise DocumentAcquisitionError(
            "verified payload is outside the requested set: "
            + sorted(unknown_recovered)[0]
        )
    gaps = [
        {"subject_id": document_id, "reason_code": "not_listed"}
        for document_id in sorted(target_ids - set(documents))
    ]
    if not documents:
        gaps.append(
            {"subject_id": scenario.case_number, "reason_code": "no_documents"}
        )
    payloads = {}
    indexed = []
    for document_id in sorted(documents):
        record = documents[document_id]
        status = "not_requested"
        byte_count = 0
        if document_id in target_ids:
            if document_id in recovered:
                content = _verified_payload(
                    provider.DocumentPayload(
                        document_id=document_id,
                        content=recovered[document_id],
                    ),
                    record,
                )
                payloads[document_id] = content
                status = "downloaded"
                byte_count = len(content)
            else:
                try:
                    payload = provider._require_method(adapter, "fetch_document")(
                        provider.DocumentFetchRequest(
                            tribunal_code=scenario.tribunal_code,
                            instance=scenario.instance,
                            case_number=scenario.case_number,
                            authorization_scope=scenario.authorization_scope,
                            document_id=document_id,
                        )
                    )
                except DocumentUnavailable as error:
                    _validate_unavailability(error, document_id)
                    status = "unavailable"
                    gaps.append(
                        {
                            "subject_id": document_id,
                            "reason_code": error.reason_code,
                        }
                    )
                else:
                    content = _verified_payload(payload, record)
                    payloads[document_id] = content
                    status = "downloaded"
                    byte_count = len(content)
        indexed.append(
            {
                "document_id": record.document_id,
                "filename": record.filename,
                "mime_type": record.mime_type,
                "sha256": record.sha256,
                "source_locator": record.source_locator,
                "download_status": status,
                "byte_count": byte_count,
            }
        )
    index = {
        "schema_version": 1,
        "case": {
            "case_number": case.case_number,
            "tribunal_code": case.tribunal_code,
            "instance": case.instance,
            "court_unit": case.court_unit,
            "task_id": case.task_id,
        },
        "status": "partial" if gaps else "complete",
        "page_count": page_count,
        "documents": indexed,
        "gaps": sorted(gaps, key=lambda item: (item["subject_id"], item["reason_code"])),
    }
    _validate_index(index, index_schema)
    return AcquisitionResult(index=index, payloads=payloads)


def _requested_ids(values: object) -> set[str]:
    if not isinstance(values, tuple):
        raise DocumentAcquisitionError("requested_document_ids must be a tuple")
    requested = set()
    for value in values:
        if not isinstance(value, str) or provider.DOCUMENT_ID_PATTERN.fullmatch(value) is None:
            raise DocumentAcquisitionError("requested document identifier is invalid")
        if value in requested:
            raise DocumentAcquisitionError(f"duplicate requested document: {value}")
        requested.add(value)
    return requested


def _verified_payload_map(values: object) -> dict[str, bytes]:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise DocumentAcquisitionError("verified_payloads must be a dictionary")
    recovered = {}
    for document_id, content in values.items():
        if (
            not isinstance(document_id, str)
            or provider.DOCUMENT_ID_PATTERN.fullmatch(document_id) is None
        ):
            raise DocumentAcquisitionError("verified payload identifier is invalid")
        if not isinstance(content, bytes):
            raise DocumentAcquisitionError("verified payload content must be bytes")
        recovered[document_id] = content
    return recovered


def _validate_case(case: object, scenario: provider.PJeContractScenario) -> None:
    if not isinstance(case, provider.CaseRecord):
        raise DocumentAcquisitionError("case discovery returned an invalid record")
    if (
        case.case_number != scenario.case_number
        or case.tribunal_code != scenario.tribunal_code
        or case.instance != scenario.instance
    ):
        raise DocumentAcquisitionError("discovered case does not match the request")
    if not case.court_unit.strip() or not case.task_id.strip():
        raise DocumentAcquisitionError("discovered case metadata is incomplete")


def _list_documents(contract: dict, adapter: object, scenario: object) -> tuple[dict, int]:
    documents = {}
    cursor = None
    seen_cursors = set()
    page_count = 0
    while True:
        page_count += 1
        if page_count > contract["max_pages"]:
            raise DocumentAcquisitionError("document pagination exceeded max_pages")
        page = provider._require_method(adapter, "list_documents")(
            provider.DocumentListRequest(
                tribunal_code=scenario.tribunal_code,
                instance=scenario.instance,
                case_number=scenario.case_number,
                authorization_scope=scenario.authorization_scope,
                cursor=cursor,
            )
        )
        if not isinstance(page, provider.DocumentPage):
            raise DocumentAcquisitionError("document listing returned an invalid page")
        for record in page.items:
            try:
                provider._validate_document(record)
            except provider.ProviderContractViolation as error:
                raise DocumentAcquisitionError(str(error)) from error
            if record.document_id in documents:
                raise DocumentAcquisitionError(
                    f"duplicate document identifier: {record.document_id}"
                )
            documents[record.document_id] = record
        try:
            cursor = provider._validate_page_state(
                page.complete,
                page.next_cursor,
                seen_cursors,
            )
        except provider.ProviderContractViolation as error:
            raise DocumentAcquisitionError(str(error)) from error
        if page.complete:
            return documents, page_count


def _validate_unavailability(error: DocumentUnavailable, expected_id: str) -> None:
    if error.document_id != expected_id:
        raise DocumentAcquisitionError(
            "unavailable document identifier does not match its request"
        )
    if (
        not isinstance(error.reason_code, str)
        or provider.TOKEN_PATTERN.fullmatch(error.reason_code) is None
    ):
        raise DocumentAcquisitionError("document unavailability reason code is invalid")


def _verified_payload(payload: object, record: provider.DocumentRecord) -> bytes:
    if not isinstance(payload, provider.DocumentPayload):
        raise DocumentAcquisitionError("document download returned an invalid payload")
    if payload.document_id != record.document_id:
        raise DocumentAcquisitionError(
            "downloaded document identifier does not match its index"
        )
    if not isinstance(payload.content, bytes):
        raise DocumentAcquisitionError("document payload content must be bytes")
    actual = hashlib.sha256(payload.content).hexdigest()
    if actual != record.sha256:
        raise DocumentAcquisitionError(
            f"document {record.document_id} failed SHA-256 verification"
        )
    return payload.content


def _validate_index(index: dict, schema_path: Path) -> None:
    try:
        schema = load_json(schema_path, "document index schema")
    except ContractError as error:
        raise DocumentAcquisitionError(str(error)) from error
    issues = validate_schema_value(index, schema)
    if issues:
        raise DocumentAcquisitionError(
            "document index contract failed: " + "; ".join(issues)
        )
