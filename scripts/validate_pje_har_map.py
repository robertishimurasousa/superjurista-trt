#!/usr/bin/env python3
"""Validate sanitized PJe HAR maps and report evidence-review gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

from sanitize_pje_har import load_sanitization_contract
from schema_validation import ContractError, load_json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SANITIZATION_CONTRACT = (
    ROOT / "runtime" / "providers" / "har-sanitization-contract.json"
)
DEFAULT_REVIEW_CONTRACT = ROOT / "runtime" / "providers" / "har-map-review-contract.json"
TRIBUNAL_PATTERN = re.compile(r"TRT[1-9][0-9]?")
CNJ_NUMBER_PATTERN = re.compile(
    r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}"
)
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
LONG_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9])[0-9]{4,}(?![A-Za-z0-9])")
OPAQUE_SEGMENT_PATTERN = re.compile(r"(?:^|/)[A-Za-z0-9_-]{24,}(?:/|$)")
MAP_FIELDS = {
    "schema_version",
    "tribunal_code",
    "instance",
    "authorization_acknowledgement",
    "capture",
    "endpoint_count",
    "endpoints",
    "coverage",
    "failure_states",
    "redaction",
    "sanitized_digest",
}
ENDPOINT_FIELDS = {
    "method",
    "origin",
    "path_template",
    "query_keys",
    "request_header_names",
    "request_cookie_names",
    "response_cookie_names",
    "response_status",
    "response_content_type",
    "classification",
    "failure_state",
}
REDACTION_FIELDS = {
    "query_values_removed",
    "request_header_values_removed",
    "request_cookie_values_removed",
    "request_bodies_removed",
    "response_header_values_removed",
    "response_cookie_values_removed",
    "response_bodies_removed",
}
CLASSIFICATIONS = {
    "authentication",
    "task_listing",
    "process_discovery",
    "document_index",
    "document_download",
    "other",
}


class MapReviewError(ValueError):
    """Raised when a sanitized map violates its structural or custody contract."""


def _require_exact_keys(value: dict, expected: set, label: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise MapReviewError(f"{label} missing field(s): {', '.join(missing)}")
    if unknown:
        raise MapReviewError(f"{label} has unknown field(s): {', '.join(unknown)}")


def _string_list(value: Any, label: str) -> List[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise MapReviewError(f"{label} must contain unique non-empty strings")
    return value


def load_review_contract(path: Path) -> dict:
    contract = load_json(path, "HAR map review contract")
    if not isinstance(contract, dict):
        raise ContractError("HAR map review contract root must be an object")
    expected = {
        "schema_version",
        "required_classifications",
        "authentication_header_names_any",
        "authentication_cookie_names_any",
        "required_failure_groups",
    }
    missing = expected - set(contract)
    unknown = set(contract) - expected
    if missing or unknown:
        detail = sorted(missing or unknown)
        raise ContractError(f"HAR map review contract fields are invalid: {', '.join(detail)}")
    if contract["schema_version"] != 1:
        raise ContractError("HAR map review contract schema_version must be 1")
    required = _string_list(contract["required_classifications"], "required_classifications")
    if not set(required).issubset(CLASSIFICATIONS - {"other"}):
        raise ContractError("HAR map review contract has unsupported classifications")
    _string_list(
        contract["authentication_header_names_any"],
        "authentication_header_names_any",
    )
    _string_list(
        contract["authentication_cookie_names_any"],
        "authentication_cookie_names_any",
    )
    groups = contract["required_failure_groups"]
    if not isinstance(groups, dict) or not groups:
        raise ContractError("required_failure_groups must be a non-empty object")
    for name, states in groups.items():
        if not isinstance(name, str) or not name:
            raise ContractError("required_failure_groups names must be non-empty strings")
        _string_list(states, f"required_failure_groups.{name}")
    return contract


def _canonical_digest(document: dict) -> str:
    unsigned = dict(document)
    unsigned.pop("sanitized_digest", None)
    payload = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_origin(value: Any, index: int) -> None:
    if not isinstance(value, str):
        raise MapReviewError(f"endpoint {index} origin must be a string")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise MapReviewError(f"endpoint {index} origin must be an HTTPS origin")


def _validate_path_template(value: Any, index: int) -> None:
    if not isinstance(value, str) or not value.startswith("/"):
        raise MapReviewError(f"endpoint {index} path_template must be an absolute path")
    if "?" in value or "#" in value:
        raise MapReviewError(f"endpoint {index} path_template must not contain URL parameters")
    if (
        CNJ_NUMBER_PATTERN.search(value)
        or UUID_PATTERN.search(value)
        or LONG_NUMBER_PATTERN.search(value)
        or OPAQUE_SEGMENT_PATTERN.search(value)
    ):
        raise MapReviewError(f"endpoint {index} path_template contains a dynamic identifier")


def _non_negative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MapReviewError(f"{label} must be a non-negative integer")
    return value


def _validate_endpoint(
    endpoint: Any,
    index: int,
    sanitization_contract: dict,
) -> dict:
    if not isinstance(endpoint, dict):
        raise MapReviewError(f"endpoint {index} must be an object")
    _require_exact_keys(endpoint, ENDPOINT_FIELDS, f"endpoint {index}")
    method = endpoint["method"]
    if method not in sanitization_contract["allowed_methods"]:
        raise MapReviewError(f"endpoint {index} method is unsupported")
    _validate_origin(endpoint["origin"], index)
    _validate_path_template(endpoint["path_template"], index)
    for field in (
        "query_keys",
        "request_header_names",
        "request_cookie_names",
        "response_cookie_names",
    ):
        _string_list(endpoint[field], f"endpoint {index} {field}")
    status = endpoint["response_status"]
    if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
        raise MapReviewError(f"endpoint {index} response_status is invalid")
    content_type = endpoint["response_content_type"]
    if content_type is not None and (
        not isinstance(content_type, str) or not content_type or ";" in content_type
    ):
        raise MapReviewError(f"endpoint {index} response_content_type is invalid")
    classification = endpoint["classification"]
    if classification not in CLASSIFICATIONS:
        raise MapReviewError(f"endpoint {index} classification is unsupported")
    expected_failure = sanitization_contract["failure_statuses"].get(str(status))
    if endpoint["failure_state"] != expected_failure:
        raise MapReviewError(f"endpoint {index} failure_state does not match its status")
    return endpoint


def validate_map(
    document: Any,
    sanitization_contract: dict,
    review_contract: dict,
    expected_tribunal: str,
    expected_instance: int,
) -> dict:
    if not isinstance(document, dict):
        raise MapReviewError("sanitized map root must be an object")
    _require_exact_keys(document, MAP_FIELDS, "sanitized map")
    digest = document["sanitized_digest"]
    if not isinstance(digest, str) or digest != _canonical_digest(document):
        raise MapReviewError("sanitized map digest does not match its content")
    if document["schema_version"] != sanitization_contract["output_schema_version"]:
        raise MapReviewError("sanitized map schema_version is unsupported")
    if TRIBUNAL_PATTERN.fullmatch(expected_tribunal) is None:
        raise MapReviewError("expected tribunal_code is invalid")
    if document["tribunal_code"] != expected_tribunal:
        raise MapReviewError("sanitized map tribunal_code does not match the review target")
    if document["instance"] != expected_instance or expected_instance not in (1, 2):
        raise MapReviewError("sanitized map instance does not match the review target")
    if document["authorization_acknowledgement"] != "operator_confirmed":
        raise MapReviewError("sanitized map lacks operator authorization acknowledgement")

    capture = document["capture"]
    if not isinstance(capture, dict):
        raise MapReviewError("sanitized map capture must be an object")
    _require_exact_keys(capture, {"format", "har_version", "entry_count"}, "capture")
    if capture["format"] != "HAR":
        raise MapReviewError("capture format must be HAR")
    if capture["har_version"] is not None and not isinstance(capture["har_version"], str):
        raise MapReviewError("capture har_version must be a string or null")
    entry_count = _non_negative_integer(capture["entry_count"], "capture entry_count")

    endpoints_value = document["endpoints"]
    if not isinstance(endpoints_value, list):
        raise MapReviewError("sanitized map endpoints must be an array")
    endpoints = [
        _validate_endpoint(endpoint, index, sanitization_contract)
        for index, endpoint in enumerate(endpoints_value)
    ]
    endpoint_count = _non_negative_integer(document["endpoint_count"], "endpoint_count")
    if endpoint_count != len(endpoints) or entry_count != len(endpoints):
        raise MapReviewError("sanitized map endpoint counts are inconsistent")

    observed_coverage = {name: 0 for name in CLASSIFICATIONS}
    observed_failures: Dict[str, int] = {}
    for endpoint in endpoints:
        observed_coverage[endpoint["classification"]] += 1
        failure_state = endpoint["failure_state"]
        if failure_state:
            observed_failures[failure_state] = observed_failures.get(failure_state, 0) + 1
    coverage = document["coverage"]
    if not isinstance(coverage, dict) or set(coverage) != CLASSIFICATIONS:
        raise MapReviewError("sanitized map coverage fields are invalid")
    for name, value in coverage.items():
        _non_negative_integer(value, f"coverage.{name}")
    if coverage != observed_coverage:
        raise MapReviewError("sanitized map coverage does not match its endpoints")
    failure_states = document["failure_states"]
    if not isinstance(failure_states, dict):
        raise MapReviewError("sanitized map failure_states must be an object")
    for name, count in failure_states.items():
        if not isinstance(name, str) or not name:
            raise MapReviewError("failure state names must be non-empty strings")
        _non_negative_integer(count, f"failure_states.{name}")
    if failure_states != dict(sorted(observed_failures.items())):
        raise MapReviewError("sanitized map failure_states do not match its endpoints")

    redaction = document["redaction"]
    if not isinstance(redaction, dict):
        raise MapReviewError("sanitized map redaction must be an object")
    _require_exact_keys(redaction, REDACTION_FIELDS, "redaction")
    for name, count in redaction.items():
        _non_negative_integer(count, f"redaction.{name}")

    gaps = review_gaps(endpoints, observed_coverage, observed_failures, review_contract)
    return {
        "status": "review_ready" if not gaps else "incomplete",
        "tribunal_code": expected_tribunal,
        "instance": expected_instance,
        "endpoint_count": endpoint_count,
        "observed_failure_states": sorted(observed_failures),
        **({"gaps": gaps} if gaps else {}),
    }


def _all_names(endpoints: Iterable[dict], fields: Iterable[str]) -> set:
    return {
        name
        for endpoint in endpoints
        for field in fields
        for name in endpoint[field]
    }


def review_gaps(
    endpoints: List[dict],
    coverage: dict,
    failure_states: dict,
    contract: dict,
) -> List[str]:
    gaps = []
    for classification in contract["required_classifications"]:
        if coverage[classification] == 0:
            gaps.append(f"classification:{classification}")
    header_names = _all_names(endpoints, ("request_header_names",))
    if not header_names.intersection(contract["authentication_header_names_any"]):
        gaps.append("authentication:header_name")
    cookie_names = _all_names(
        endpoints,
        ("request_cookie_names", "response_cookie_names"),
    )
    if not cookie_names.intersection(contract["authentication_cookie_names_any"]):
        gaps.append("authentication:cookie_name")
    observed = set(failure_states)
    for group, alternatives in contract["required_failure_groups"].items():
        if not observed.intersection(alternatives):
            gaps.append(f"failure_group:{group}")
    return sorted(gaps)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a sanitized PJe HAR evidence map.")
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--tribunal-code", required=True)
    parser.add_argument("--instance", required=True, type=int, choices=(1, 2))
    parser.add_argument("--sanitization-contract", type=Path, default=DEFAULT_SANITIZATION_CONTRACT)
    parser.add_argument("--review-contract", type=Path, default=DEFAULT_REVIEW_CONTRACT)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        document = load_json(args.map.resolve(), "sanitized HAR map")
        sanitization_contract = load_sanitization_contract(
            args.sanitization_contract.resolve()
        )
        review_contract = load_review_contract(args.review_contract.resolve())
        result = validate_map(
            document,
            sanitization_contract,
            review_contract,
            args.tribunal_code,
            args.instance,
        )
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        elif result["status"] == "review_ready":
            print(
                "[OK] sanitized HAR map is ready for human review: "
                f"endpoints={result['endpoint_count']}"
            )
        else:
            print("[INCOMPLETE] sanitized HAR map gaps: " + ", ".join(result["gaps"]))
        return 0 if result["status"] == "review_ready" else 1
    except (ContractError, MapReviewError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
