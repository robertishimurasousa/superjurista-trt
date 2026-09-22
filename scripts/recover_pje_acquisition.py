#!/usr/bin/env python3
"""Persist bounded, content-verified recovery for PJe document acquisition."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import acquire_pje_documents as acquisition
import provider_interfaces as provider
from schema_validation import ContractError, load_json, validate_schema_value


DEFAULT_RECOVERY_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "providers"
    / "pje-recovery-state.v1.schema.json"
)


class PJeRecoveryError(ValueError):
    """Raised when a PJe acquisition checkpoint cannot be safely resumed."""


@dataclass(frozen=True)
class RecoveryResult:
    state: dict
    index: dict | None


def run_recoverable_acquisition(
    contract: dict,
    adapter: provider.PJeAdapter,
    scenario: provider.PJeContractScenario,
    *,
    checkpoint_path: Path,
    payload_directory: Path,
    max_attempts: int,
    requested_document_ids: tuple[str, ...] = (),
    index_schema: Path = acquisition.DEFAULT_INDEX_SCHEMA,
    recovery_schema: Path = DEFAULT_RECOVERY_SCHEMA,
) -> RecoveryResult:
    """Run one bounded acquisition cycle and atomically persist resumable evidence."""
    _validate_paths(checkpoint_path, payload_directory)
    _validate_max_attempts(max_attempts)
    try:
        requested = acquisition._requested_ids(requested_document_ids)
        provider._validate_pje_scenario(scenario)
    except (acquisition.DocumentAcquisitionError, provider.ProviderContractViolation) as error:
        raise PJeRecoveryError(str(error)) from error

    state = None
    recovered = {}
    if checkpoint_path.exists():
        state = _load_state(checkpoint_path, recovery_schema)
        _validate_binding(state, scenario, requested, max_attempts)
        recovered = _load_accepted_payloads(state, payload_directory)
        if state["status"] in {"complete", "exhausted"}:
            return RecoveryResult(state=state, index=None)

    target_ids = tuple(sorted(requested)) if requested else ()
    if state is not None:
        target_ids = tuple(item["document_id"] for item in state["documents"])
    try:
        result = acquisition.acquire_pje_documents(
            contract,
            adapter,
            scenario,
            requested_document_ids=target_ids,
            verified_payloads=recovered,
            index_schema=index_schema,
        )
    except acquisition.DocumentAcquisitionError as error:
        raise PJeRecoveryError(str(error)) from error

    catalog_digest = _catalog_digest(result.index)
    if state is None:
        state = _new_state(
            scenario,
            result.index,
            requested,
            max_attempts,
            catalog_digest,
        )
    elif state["catalog_digest"] != catalog_digest:
        raise PJeRecoveryError("document catalog changed after checkpoint creation")

    updated = _apply_cycle(
        state,
        result,
        payload_directory,
        max_attempts,
    )
    _validate_state(updated, recovery_schema)
    _save_json_atomic(checkpoint_path, updated)
    return RecoveryResult(state=updated, index=result.index)


def _validate_paths(checkpoint_path: object, payload_directory: object) -> None:
    if not isinstance(checkpoint_path, Path) or not isinstance(payload_directory, Path):
        raise PJeRecoveryError("checkpoint and payload locations must be Path values")
    if checkpoint_path == payload_directory:
        raise PJeRecoveryError("checkpoint and payload locations must be distinct")


def _validate_max_attempts(max_attempts: object) -> None:
    if (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or not 1 <= max_attempts <= 5
    ):
        raise PJeRecoveryError("max_attempts must be an integer between 1 and 5")


def _new_state(
    scenario: provider.PJeContractScenario,
    index: dict,
    requested: set[str],
    max_attempts: int,
    catalog_digest: str,
) -> dict:
    available = {item["document_id"]: item for item in index["documents"]}
    targets = requested or set(available)
    if not targets:
        raise PJeRecoveryError("document catalog has no recoverable documents")
    missing = targets - set(available)
    if missing:
        raise PJeRecoveryError(
            "requested document is absent from the catalog: " + sorted(missing)[0]
        )
    return {
        "schema_version": 1,
        "case": {
            "case_number": scenario.case_number,
            "tribunal_code": scenario.tribunal_code,
            "instance": scenario.instance,
        },
        "authorization_scope_digest": _sha256_text(scenario.authorization_scope),
        "selection_mode": "explicit" if requested else "all",
        "requested_document_ids": sorted(requested),
        "max_attempts": max_attempts,
        "catalog_digest": catalog_digest,
        "status": "in_progress",
        "acquisition_cycles": 0,
        "successful_documents": 0,
        "documents": [
            {
                "document_id": document_id,
                "sha256": available[document_id]["sha256"],
                "attempt_count": 0,
                "status": "pending",
                "relative_path": None,
                "byte_count": 0,
                "last_error": None,
            }
            for document_id in sorted(targets)
        ],
    }


def _apply_cycle(
    state: dict,
    result: acquisition.AcquisitionResult,
    payload_directory: Path,
    max_attempts: int,
) -> dict:
    updated = json.loads(json.dumps(state))
    indexed = {item["document_id"]: item for item in result.index["documents"]}
    gap_reasons = {
        item["subject_id"]: item["reason_code"] for item in result.index["gaps"]
    }
    for document in updated["documents"]:
        if document["status"] == "accepted":
            continue
        document_id = document["document_id"]
        document["attempt_count"] += 1
        item = indexed[document_id]
        if item["download_status"] == "downloaded":
            content = result.payloads[document_id]
            relative_path = f"{document_id}.bin"
            _save_bytes_atomic(payload_directory / relative_path, content)
            document.update(
                {
                    "status": "accepted",
                    "relative_path": relative_path,
                    "byte_count": len(content),
                    "last_error": None,
                }
            )
        else:
            exhausted = document["attempt_count"] >= max_attempts
            document.update(
                {
                    "status": "exhausted" if exhausted else "pending",
                    "relative_path": None,
                    "byte_count": 0,
                    "last_error": gap_reasons.get(
                        document_id,
                        "document_not_downloaded",
                    ),
                }
            )
    updated["acquisition_cycles"] += 1
    updated["successful_documents"] = sum(
        item["status"] == "accepted" for item in updated["documents"]
    )
    statuses = {item["status"] for item in updated["documents"]}
    if statuses == {"accepted"}:
        updated["status"] = "complete"
    elif "pending" in statuses:
        updated["status"] = "in_progress"
    else:
        updated["status"] = "exhausted"
    return updated


def _load_accepted_payloads(state: dict, payload_directory: Path) -> dict[str, bytes]:
    recovered = {}
    for document in state["documents"]:
        if document["status"] != "accepted":
            continue
        relative_path = document["relative_path"]
        if relative_path != f"{document['document_id']}.bin":
            raise PJeRecoveryError("accepted payload path is not canonical")
        path = payload_directory / relative_path
        try:
            content = path.read_bytes()
        except FileNotFoundError as error:
            raise PJeRecoveryError("accepted payload custody file is missing") from error
        if (
            hashlib.sha256(content).hexdigest() != document["sha256"]
            or len(content) != document["byte_count"]
        ):
            raise PJeRecoveryError("accepted payload custody verification failed")
        recovered[document["document_id"]] = content
    return recovered


def _validate_binding(
    state: dict,
    scenario: provider.PJeContractScenario,
    requested: set[str],
    max_attempts: int,
) -> None:
    expected_case = {
        "case_number": scenario.case_number,
        "tribunal_code": scenario.tribunal_code,
        "instance": scenario.instance,
    }
    expected_mode = "explicit" if requested else "all"
    if (
        state["case"] != expected_case
        or state["authorization_scope_digest"]
        != _sha256_text(scenario.authorization_scope)
        or state["selection_mode"] != expected_mode
        or state["requested_document_ids"] != sorted(requested)
        or state["max_attempts"] != max_attempts
    ):
        raise PJeRecoveryError("checkpoint does not match the acquisition request")


def _catalog_digest(index: dict) -> str:
    catalog = {
        "case": index["case"],
        "page_count": index["page_count"],
        "documents": [
            {
                field: item[field]
                for field in (
                    "document_id",
                    "filename",
                    "mime_type",
                    "sha256",
                    "source_locator",
                )
            }
            for item in index["documents"]
        ],
    }
    return _sha256_text(
        json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _load_state(path: Path, schema_path: Path) -> dict:
    try:
        state = load_json(path, "PJe recovery checkpoint")
    except ContractError as error:
        raise PJeRecoveryError(str(error)) from error
    _validate_state(state, schema_path)
    return state


def _validate_state(state: dict, schema_path: Path) -> None:
    try:
        schema = load_json(schema_path, "PJe recovery schema")
    except ContractError as error:
        raise PJeRecoveryError(str(error)) from error
    issues = validate_schema_value(state, schema)
    if issues:
        raise PJeRecoveryError("recovery checkpoint contract failed: " + "; ".join(issues))
    ids = [item["document_id"] for item in state["documents"]]
    if len(ids) != len(set(ids)) or ids != sorted(ids):
        raise PJeRecoveryError("recovery checkpoint documents must be unique and sorted")
    accepted = sum(item["status"] == "accepted" for item in state["documents"])
    if accepted != state["successful_documents"]:
        raise PJeRecoveryError("recovery checkpoint success count is inconsistent")
    if state["selection_mode"] == "all" and state["requested_document_ids"]:
        raise PJeRecoveryError("all-document checkpoint cannot contain requested identifiers")
    if state["selection_mode"] == "explicit":
        if state["requested_document_ids"] != ids:
            raise PJeRecoveryError("explicit checkpoint identifiers are inconsistent")
    statuses = {item["status"] for item in state["documents"]}
    expected_status = (
        "complete"
        if statuses == {"accepted"}
        else "in_progress"
        if "pending" in statuses
        else "exhausted"
    )
    if state["status"] != expected_status:
        raise PJeRecoveryError("recovery checkpoint status is inconsistent")
    for item in state["documents"]:
        if item["attempt_count"] > state["max_attempts"]:
            raise PJeRecoveryError("document attempt exceeds checkpoint retry ceiling")
        if item["status"] == "accepted":
            if item["relative_path"] is None or item["last_error"] is not None:
                raise PJeRecoveryError("accepted document checkpoint is inconsistent")
        elif item["relative_path"] is not None or item["byte_count"] != 0:
            raise PJeRecoveryError("non-accepted document retains a payload path")
        elif not item["last_error"]:
            raise PJeRecoveryError("non-accepted document must retain its failure reason")
        if item["status"] == "pending" and item["attempt_count"] >= state["max_attempts"]:
            raise PJeRecoveryError("pending document reached the retry ceiling")
        if item["status"] == "exhausted" and item["attempt_count"] != state["max_attempts"]:
            raise PJeRecoveryError("exhausted document has an invalid attempt count")


def _save_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def _save_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
