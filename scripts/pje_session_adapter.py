#!/usr/bin/env python3
"""Provider-neutral PJe session-state assessment.

The module classifies sanitized observations produced by an adapter. It does
not acquire credentials, perform login, or know court-specific endpoints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Protocol, Tuple

from provider_interfaces import AdapterDescriptor
from schema_validation import ContractError, load_json


TRIBUNAL_PATTERN = re.compile(r"TRT[1-9][0-9]?")
TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9_-]*")
EVIDENCE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


class SessionContractViolation(ValueError):
    """Raised when a session probe violates the shared runtime contract."""


@dataclass(frozen=True)
class SessionCheck:
    tribunal_code: str
    instance: int
    authorization_scope: str


@dataclass(frozen=True)
class SessionProbeRequest:
    tribunal_code: str
    instance: int
    authorization_scope: str


@dataclass(frozen=True)
class SessionObservation:
    http_status: int
    markers: Tuple[str, ...]
    cookie_names: Tuple[str, ...]
    header_names: Tuple[str, ...]


class SessionProbe(Protocol):
    descriptor: AdapterDescriptor

    def probe_session(self, request: SessionProbeRequest) -> SessionObservation:
        ...


def _expect_exact_keys(value: dict, expected: set, label: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise ContractError(f"{label} missing field(s): {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{label} has unknown field(s): {', '.join(unknown)}")


def _expect_unique_strings(value: object, label: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "a list" if allow_empty else "a non-empty list"
        raise ContractError(f"{label} must be {qualifier}")
    if any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{label} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ContractError(f"{label} must contain unique values")


def load_session_contract(path: Path) -> Dict[str, object]:
    """Load and strictly validate the versioned PJe session contract."""
    contract = load_json(path, "PJe session contract")
    if not isinstance(contract, dict):
        raise ContractError("PJe session contract root must be an object")

    expected = {
        "schema_version",
        "interface_id",
        "interface_version",
        "required_capability",
        "allowed_states",
        "allowed_markers",
        "http_status_states",
        "marker_states",
        "valid_marker",
        "session_evidence",
    }
    _expect_exact_keys(contract, expected, "PJe session contract")
    if contract["schema_version"] != 1:
        raise ContractError("PJe session contract schema_version must be 1")
    if contract["interface_id"] != "pje_case_acquisition":
        raise ContractError("PJe session contract interface_id is unsupported")
    if contract["interface_version"] != 1:
        raise ContractError("PJe session contract interface_version must be 1")
    if contract["required_capability"] != "validate_session":
        raise ContractError("PJe session contract required_capability is unsupported")

    _expect_unique_strings(contract["allowed_states"], "allowed_states")
    _expect_unique_strings(contract["allowed_markers"], "allowed_markers")
    states = set(contract["allowed_states"])
    markers = set(contract["allowed_markers"])
    required_states = {"valid", "expired", "mfa_required", "unauthorized", "unknown"}
    if states != required_states:
        raise ContractError("allowed_states must define the complete session state set")

    status_states = contract["http_status_states"]
    if not isinstance(status_states, dict) or not status_states:
        raise ContractError("http_status_states must be a non-empty object")
    for status, state in status_states.items():
        if not isinstance(status, str) or not status.isdigit() or not 100 <= int(status) <= 599:
            raise ContractError("http_status_states contains an invalid HTTP status")
        if state not in states:
            raise ContractError("http_status_states contains an unsupported state")

    marker_states = contract["marker_states"]
    if not isinstance(marker_states, dict) or not marker_states:
        raise ContractError("marker_states must be a non-empty object")
    if any(marker not in markers for marker in marker_states):
        raise ContractError("marker_states contains an unsupported marker")
    if any(state not in states for state in marker_states.values()):
        raise ContractError("marker_states contains an unsupported state")

    valid_marker = contract["valid_marker"]
    if valid_marker not in markers or valid_marker in marker_states:
        raise ContractError("valid_marker must be a distinct allowed marker")

    evidence = contract["session_evidence"]
    if not isinstance(evidence, dict):
        raise ContractError("session_evidence must be an object")
    _expect_exact_keys(evidence, {"cookie_names_any", "header_names_any"}, "session_evidence")
    _expect_unique_strings(evidence["cookie_names_any"], "session_evidence.cookie_names_any")
    _expect_unique_strings(evidence["header_names_any"], "session_evidence.header_names_any")
    for name in evidence["cookie_names_any"] + evidence["header_names_any"]:
        if EVIDENCE_NAME_PATTERN.fullmatch(name) is None:
            raise ContractError("session_evidence contains an invalid name")
    return contract


def _validate_check(check: SessionCheck) -> None:
    if not isinstance(check, SessionCheck):
        raise SessionContractViolation("session check has an invalid type")
    if TRIBUNAL_PATTERN.fullmatch(check.tribunal_code) is None:
        raise SessionContractViolation("session check has an invalid tribunal code")
    if isinstance(check.instance, bool) or check.instance not in (1, 2):
        raise SessionContractViolation("session check instance must be 1 or 2")
    if not isinstance(check.authorization_scope, str) or not check.authorization_scope.strip():
        raise SessionContractViolation("session check requires an authorization scope")


def _validate_descriptor(contract: dict, descriptor: object, check: SessionCheck) -> None:
    if not isinstance(descriptor, AdapterDescriptor):
        raise SessionContractViolation("session probe descriptor has an invalid type")
    if TOKEN_PATTERN.fullmatch(descriptor.provider_id) is None:
        raise SessionContractViolation("session probe provider_id is invalid")
    if descriptor.interface_id != contract["interface_id"]:
        raise SessionContractViolation("session probe interface_id is incompatible")
    if descriptor.interface_version != contract["interface_version"]:
        raise SessionContractViolation("session probe interface_version is incompatible")
    required = contract["required_capability"]
    if required not in descriptor.capabilities:
        raise SessionContractViolation(f"session probe requires {required} capability")
    if check.tribunal_code not in descriptor.supported_tribunals:
        raise SessionContractViolation("session probe does not support the requested tribunal")


def _validate_observation(contract: dict, observation: object) -> SessionObservation:
    if not isinstance(observation, SessionObservation):
        raise SessionContractViolation("session probe returned an invalid observation type")
    if (
        isinstance(observation.http_status, bool)
        or not isinstance(observation.http_status, int)
        or not 100 <= observation.http_status <= 599
    ):
        raise SessionContractViolation("session observation has an invalid HTTP status")

    for values, label in (
        (observation.markers, "markers"),
        (observation.cookie_names, "cookie names"),
        (observation.header_names, "header names"),
    ):
        if not isinstance(values, tuple) or any(not isinstance(value, str) for value in values):
            raise SessionContractViolation(f"session observation {label} must be a string tuple")
        if len(values) != len(set(values)):
            raise SessionContractViolation(f"session observation {label} must be unique")

    allowed_markers = set(contract["allowed_markers"])
    if any(marker not in allowed_markers for marker in observation.markers):
        raise SessionContractViolation("session observation contains an unsupported marker")
    if any(EVIDENCE_NAME_PATTERN.fullmatch(name) is None for name in observation.cookie_names):
        raise SessionContractViolation("session observation contains an invalid cookie name")
    if any(EVIDENCE_NAME_PATTERN.fullmatch(name) is None for name in observation.header_names):
        raise SessionContractViolation("session observation contains an invalid header name")
    return observation


def _classify(contract: dict, observation: SessionObservation) -> Tuple[str, str]:
    status_state = contract["http_status_states"].get(str(observation.http_status))
    if status_state is not None:
        return status_state, f"http_{observation.http_status}"

    marker_states = contract["marker_states"]
    signals = {
        marker_states[marker]
        for marker in observation.markers
        if marker in marker_states
    }
    valid_marker = contract["valid_marker"]
    if valid_marker in observation.markers:
        signals.add("valid")
    if len(signals) > 1:
        return "unknown", "conflicting_markers"

    for marker in observation.markers:
        if marker in marker_states:
            return marker_states[marker], marker

    if valid_marker in observation.markers:
        evidence = contract["session_evidence"]
        expected_cookies = set(evidence["cookie_names_any"])
        expected_headers = {name.lower() for name in evidence["header_names_any"]}
        has_cookie = bool(expected_cookies.intersection(observation.cookie_names))
        has_header = bool(expected_headers.intersection(name.lower() for name in observation.header_names))
        if has_cookie or has_header:
            return "valid", valid_marker
        return "unknown", "missing_session_evidence"
    return "unknown", "insufficient_evidence"


def assess_pje_session(
    contract: dict,
    probe: SessionProbe,
    check: SessionCheck,
) -> dict:
    """Assess one sanitized provider observation and return JSON-safe evidence."""
    _validate_check(check)
    descriptor = getattr(probe, "descriptor", None)
    _validate_descriptor(contract, descriptor, check)
    request = SessionProbeRequest(
        tribunal_code=check.tribunal_code,
        instance=check.instance,
        authorization_scope=check.authorization_scope,
    )
    observation = _validate_observation(contract, probe.probe_session(request))
    status, reason_code = _classify(contract, observation)
    return {
        "status": status,
        "reason_code": reason_code,
        "provider_id": descriptor.provider_id,
        "tribunal_code": check.tribunal_code,
        "instance": check.instance,
        "evidence": {
            "http_status": observation.http_status,
            "markers": sorted(observation.markers),
            "cookie_names": sorted(observation.cookie_names),
            "header_names": sorted(observation.header_names),
        },
    }
