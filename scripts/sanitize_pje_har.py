#!/usr/bin/env python3
"""Build a deterministic, secret-free endpoint map from an authorized PJe HAR."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

from schema_validation import ContractError, load_json


DEFAULT_CONTRACT = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "providers"
    / "har-sanitization-contract.json"
)
TRIBUNAL_PATTERN = re.compile(r"TRT[1-9][0-9]?")
CNJ_NUMBER_PATTERN = re.compile(
    r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}"
)
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
OPAQUE_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9_-]{24,}")
SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-pje-cookies",
}
CLASSIFICATION_KEYS = (
    "authentication",
    "task_listing",
    "process_discovery",
    "document_index",
    "document_download",
    "other",
)


class SanitizationError(ValueError):
    """Raised when an input cannot be transformed without weakening the contract."""


def _require_exact_keys(value: dict, expected: set, label: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise ContractError(f"{label} missing field(s): {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{label} has unknown field(s): {', '.join(unknown)}")


def load_sanitization_contract(path: Path) -> dict:
    contract = load_json(path, "HAR sanitization contract")
    if not isinstance(contract, dict):
        raise ContractError("HAR sanitization contract root must be an object")
    expected = {
        "schema_version",
        "output_schema_version",
        "max_entries",
        "allowed_methods",
        "classification_markers",
        "failure_statuses",
    }
    _require_exact_keys(contract, expected, "HAR sanitization contract")
    if contract["schema_version"] != 1 or contract["output_schema_version"] != 1:
        raise ContractError("HAR sanitization contract versions must be 1")
    max_entries = contract["max_entries"]
    if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
        raise ContractError("HAR sanitization max_entries must be a positive integer")
    methods = contract["allowed_methods"]
    if (
        not isinstance(methods, list)
        or not methods
        or any(not isinstance(method, str) or not method for method in methods)
        or len(methods) != len(set(methods))
    ):
        raise ContractError("HAR sanitization allowed_methods must be unique strings")
    markers = contract["classification_markers"]
    required_markers = set(CLASSIFICATION_KEYS) - {"other"}
    if not isinstance(markers, dict) or set(markers) != required_markers:
        raise ContractError("HAR sanitization classification_markers are incomplete")
    for classification, values in markers.items():
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value for value in values)
        ):
            raise ContractError(
                f"classification markers must be non-empty strings: {classification}"
            )
    failures = contract["failure_statuses"]
    if not isinstance(failures, dict):
        raise ContractError("HAR sanitization failure_statuses must be an object")
    for status, state in failures.items():
        if not status.isdigit() or not isinstance(state, str) or not state:
            raise ContractError("HAR sanitization failure_statuses are invalid")
    return contract


def load_har(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SanitizationError("HAR input file was not found") from error
    except UnicodeDecodeError as error:
        raise SanitizationError("HAR input must be UTF-8 JSON") from error
    except json.JSONDecodeError as error:
        raise SanitizationError("HAR input is not valid JSON") from error
    if not isinstance(document, dict):
        raise SanitizationError("HAR root must be an object")
    log = document.get("log")
    if not isinstance(log, dict):
        raise SanitizationError("HAR log must be an object")
    entries = log.get("entries")
    if not isinstance(entries, list):
        raise SanitizationError("HAR entries must be an array")
    return document


def _list_of_objects(value: Any, label: str, entry_index: int) -> List[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise SanitizationError(f"entry {entry_index} {label} must be an array of objects")
    return value


def _names(items: Iterable[dict], label: str, entry_index: int, *, lower: bool) -> List[str]:
    names = []
    for item in items:
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SanitizationError(f"entry {entry_index} {label} contains an invalid name")
        normalized = name.strip().lower() if lower else name.strip()
        names.append(normalized)
    return sorted(set(names))


def _sensitive_values(
    request_headers: Iterable[dict],
    response_headers: Iterable[dict],
    request_cookies: Iterable[dict],
    response_cookies: Iterable[dict],
    query: Iterable[dict],
) -> List[str]:
    values = []
    for header in (*request_headers, *response_headers):
        name = header.get("name")
        value = header.get("value")
        if (
            isinstance(name, str)
            and isinstance(value, str)
            and value
            and (
                name.lower() in SENSITIVE_HEADER_NAMES
                or name.lower().startswith("x-pje-")
            )
        ):
            values.append(value)
    for item in (*request_cookies, *response_cookies, *query):
        value = item.get("value")
        if isinstance(value, str) and value:
            values.append(value)
    return values


def _removed_value_count(items: Iterable[dict]) -> int:
    return sum(1 for item in items if item.get("value") not in (None, ""))


def _path_template(path: str) -> str:
    decoded = unquote(path or "/")
    segments = []
    for segment in decoded.split("/"):
        if not segment:
            continue
        if CNJ_NUMBER_PATTERN.fullmatch(segment):
            segments.append("{cnj_number}")
        elif UUID_PATTERN.fullmatch(segment):
            segments.append("{uuid}")
        elif segment.isdigit() and len(segment) >= 4:
            segments.append("{numeric_id}")
        elif OPAQUE_SEGMENT_PATTERN.fullmatch(segment):
            segments.append("{opaque_id}")
        else:
            redacted = CNJ_NUMBER_PATTERN.sub("{cnj_number}", segment)
            segments.append(redacted)
    return "/" + "/".join(segments)


def _safe_endpoint(url: str, entry_index: int) -> Tuple[str, str]:
    if not isinstance(url, str):
        raise SanitizationError(f"entry {entry_index} request URL must be a string")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise SanitizationError(f"entry {entry_index} request URL is invalid") from error
    if parsed.scheme != "https" or not parsed.hostname:
        raise SanitizationError(f"entry {entry_index} request URL must use HTTPS")
    if parsed.username or parsed.password:
        raise SanitizationError(f"entry {entry_index} request URL must not contain credentials")
    origin = f"https://{parsed.hostname.lower()}"
    if port not in (None, 443):
        origin += f":{port}"
    return origin, _path_template(parsed.path)


def _classification(path_template: str, contract: dict) -> str:
    tokens = {token for token in path_template.lower().split("/") if token}
    markers = contract["classification_markers"]
    document = bool(tokens.intersection(markers["document_index"]))
    download = bool(tokens.intersection(markers["document_download"]))
    if document and download:
        return "document_download"
    if tokens.intersection(markers["authentication"]):
        return "authentication"
    if tokens.intersection(markers["task_listing"]):
        return "task_listing"
    if tokens.intersection(markers["process_discovery"]):
        return "process_discovery"
    if document:
        return "document_index"
    return "other"


def _content_type(response: dict, entry_index: int) -> Optional[str]:
    content = response.get("content")
    if content is None:
        return None
    if not isinstance(content, dict):
        raise SanitizationError(f"entry {entry_index} response content must be an object")
    mime_type = content.get("mimeType")
    if mime_type in (None, ""):
        return None
    if not isinstance(mime_type, str):
        raise SanitizationError(f"entry {entry_index} response mimeType must be a string")
    return mime_type.split(";", 1)[0].strip().lower() or None


def _has_body(container: dict, field: str) -> bool:
    value = container.get(field)
    if not isinstance(value, dict):
        return value is not None
    return any(item not in (None, "", [], {}) for item in value.values())


def _sanitize_entry(entry: Any, index: int, contract: dict) -> Tuple[dict, List[str], dict]:
    if not isinstance(entry, dict):
        raise SanitizationError(f"entry {index} must be an object")
    request = entry.get("request")
    response = entry.get("response")
    if not isinstance(request, dict) or not isinstance(response, dict):
        raise SanitizationError(f"entry {index} requires request and response objects")
    method = request.get("method")
    if not isinstance(method, str) or method.upper() not in contract["allowed_methods"]:
        raise SanitizationError(f"entry {index} request method is unsupported")
    method = method.upper()
    origin, path_template = _safe_endpoint(request.get("url"), index)

    request_headers = _list_of_objects(request.get("headers"), "request headers", index)
    response_headers = _list_of_objects(response.get("headers"), "response headers", index)
    request_cookies = _list_of_objects(request.get("cookies"), "request cookies", index)
    response_cookies = _list_of_objects(response.get("cookies"), "response cookies", index)
    query = _list_of_objects(request.get("queryString"), "query string", index)
    secret_values = _sensitive_values(
        request_headers,
        response_headers,
        request_cookies,
        response_cookies,
        query,
    )

    status = response.get("status")
    if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
        raise SanitizationError(f"entry {index} response status is invalid")
    classification = _classification(path_template, contract)
    failure_state = contract["failure_statuses"].get(str(status))
    redaction = {
        "query_values_removed": _removed_value_count(query),
        "request_header_values_removed": _removed_value_count(request_headers),
        "request_cookie_values_removed": _removed_value_count(request_cookies),
        "request_bodies_removed": int(_has_body(request, "postData")),
        "response_header_values_removed": _removed_value_count(response_headers),
        "response_cookie_values_removed": _removed_value_count(response_cookies),
        "response_bodies_removed": int(_has_body(response, "content")),
    }
    sanitized = {
        "method": method,
        "origin": origin,
        "path_template": path_template,
        "query_keys": _names(query, "query string", index, lower=False),
        "request_header_names": _names(
            request_headers,
            "request headers",
            index,
            lower=True,
        ),
        "request_cookie_names": _names(
            request_cookies,
            "request cookies",
            index,
            lower=False,
        ),
        "response_cookie_names": _names(
            response_cookies,
            "response cookies",
            index,
            lower=False,
        ),
        "response_status": status,
        "response_content_type": _content_type(response, index),
        "classification": classification,
        "failure_state": failure_state,
    }
    return sanitized, secret_values, redaction


def sanitize_har(document: dict, contract: dict, tribunal_code: str, instance: int) -> dict:
    if TRIBUNAL_PATTERN.fullmatch(tribunal_code) is None:
        raise SanitizationError("tribunal_code must identify a regional labor court")
    if instance not in (1, 2):
        raise SanitizationError("instance must be 1 or 2")
    log = document["log"]
    entries = log["entries"]
    if not entries:
        raise SanitizationError("HAR entries must not be empty")
    if len(entries) > contract["max_entries"]:
        raise SanitizationError("HAR entry count exceeds the sanitization contract")

    sanitized_entries = []
    secret_values: List[str] = []
    coverage = {key: 0 for key in CLASSIFICATION_KEYS}
    failure_states: Dict[str, int] = {}
    redaction = {
        "query_values_removed": 0,
        "request_header_values_removed": 0,
        "request_cookie_values_removed": 0,
        "request_bodies_removed": 0,
        "response_header_values_removed": 0,
        "response_cookie_values_removed": 0,
        "response_bodies_removed": 0,
    }

    for index, entry in enumerate(entries):
        sanitized, entry_secrets, entry_redaction = _sanitize_entry(entry, index, contract)
        secret_values.extend(entry_secrets)
        classification = sanitized["classification"]
        failure_state = sanitized["failure_state"]
        coverage[classification] += 1
        if failure_state:
            failure_states[failure_state] = failure_states.get(failure_state, 0) + 1
        for field, count in entry_redaction.items():
            redaction[field] += count
        sanitized_entries.append(sanitized)

    report = {
        "schema_version": contract["output_schema_version"],
        "tribunal_code": tribunal_code,
        "instance": instance,
        "authorization_acknowledgement": "operator_confirmed",
        "capture": {
            "format": "HAR",
            "har_version": log.get("version") if isinstance(log.get("version"), str) else None,
            "entry_count": len(entries),
        },
        "endpoint_count": len(sanitized_entries),
        "endpoints": sanitized_entries,
        "coverage": coverage,
        "failure_states": dict(sorted(failure_states.items())),
        "redaction": redaction,
    }
    canonical = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    report["sanitized_digest"] = hashlib.sha256(canonical).hexdigest()
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    for value in secret_values:
        if len(value) >= 4 and value in serialized:
            raise SanitizationError("sanitized output retained a sensitive input value")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a deterministic, secret-free endpoint map from a PJe HAR."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tribunal-code", required=True)
    parser.add_argument("--instance", required=True, type=int, choices=(1, 2))
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument(
        "--authorized-capture",
        required=True,
        action="store_true",
        help="Acknowledge that the operator is authorized to process this capture.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        input_path = args.input.resolve()
        output_path = args.output.resolve()
        if input_path == output_path:
            raise SanitizationError("input and output paths must differ")
        contract = load_sanitization_contract(args.contract.resolve())
        report = sanitize_har(
            load_har(input_path),
            contract,
            args.tribunal_code,
            args.instance,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            "[OK] sanitized HAR map: "
            f"endpoints={report['endpoint_count']}; "
            f"digest={report['sanitized_digest']}"
        )
        return 0
    except (ContractError, SanitizationError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
