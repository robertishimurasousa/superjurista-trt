#!/usr/bin/env python3
"""Validate a runtime-neutral tribunal profile and its provider bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from schema_validation import ContractError, load_json, validate_schema_value


def validate_registry(registry: Any) -> dict:
    if not isinstance(registry, dict):
        raise ContractError("registry root must be an object")
    if registry.get("schema_version") != 1:
        raise ContractError("registry schema_version must be 1")
    for field in ("cnj_branch_digits", "case_system_adapters", "research_adapters"):
        if not isinstance(registry.get(field), dict):
            raise ContractError(f"registry field must be an object: {field}")
    return registry


def validate_profile_bindings(profile: dict, registry: dict) -> list[str]:
    issues: list[str] = []
    tribunal = profile["tribunal"]
    segment = tribunal["segment"]
    tribunal_code = tribunal["code"]
    expected_digit = registry["cnj_branch_digits"].get(segment)
    if expected_digit is None or tribunal["cnj_branch_digit"] != expected_digit:
        issues.append(
            "tribunal.cnj_branch_digit: unknown digit for tribunal segment "
            f"{segment!r}"
        )
    if tribunal_code != f"TRT{tribunal['region']}":
        issues.append("tribunal.code: must correspond to tribunal.region")

    case_system = profile["providers"]["case_system"]
    registered_case_adapters = registry["case_system_adapters"]
    for instance in ("first", "second"):
        adapter_field = f"{instance}_instance_adapter"
        adapter_id = case_system[adapter_field]
        if profile["instances"][instance]["enabled"] and not adapter_id:
            issues.append(
                f"providers.case_system.{adapter_field}: enabled instance requires an adapter"
            )
            continue
        if adapter_id is None:
            continue
        adapter = registered_case_adapters.get(adapter_id)
        if not isinstance(adapter, dict):
            issues.append(
                f"providers.case_system.{adapter_field}: unregistered case-system adapter "
                f"{adapter_id!r}"
            )
            continue
        if adapter.get("system") != case_system["type"]:
            issues.append(
                f"providers.case_system.{adapter_field}: adapter does not support system "
                f"{case_system['type']!r}"
            )
        if tribunal_code not in adapter.get("tribunals", []):
            issues.append(
                f"providers.case_system.{adapter_field}: adapter does not support "
                f"{tribunal_code}"
            )
        if instance not in adapter.get("instances", []):
            issues.append(
                f"providers.case_system.{adapter_field}: adapter does not support "
                f"{instance} instance"
            )

    registered_research = registry["research_adapters"]
    for index, binding in enumerate(profile["providers"]["research"]):
        base = f"providers.research[{index}]"
        adapter = registered_research.get(binding["adapter"])
        if not isinstance(adapter, dict):
            issues.append(
                f"{base}.adapter: unregistered research adapter {binding['adapter']!r}"
            )
            continue
        if binding["source"] not in adapter.get("sources", []):
            issues.append(
                f"{base}.source: unregistered research source {binding['source']!r} "
                f"for adapter {binding['adapter']!r}"
            )
        if binding["scope"] not in adapter.get("scopes", []):
            issues.append(
                f"{base}.scope: adapter does not support scope {binding['scope']!r}"
            )
        tribunals = adapter.get("tribunals")
        if tribunals is not None and tribunal_code not in tribunals:
            issues.append(f"{base}.adapter: adapter does not support {tribunal_code}")

    policy = profile["policy"]
    for field in (
        "allow_external_filing",
        "allow_external_signing",
        "allow_external_publication",
    ):
        if policy[field]:
            issues.append(f"policy.{field}: must remain false in the MVP")
    if not policy["require_human_review"]:
        issues.append("policy.require_human_review: must remain true")
    if not policy["require_verbatim_custody"]:
        issues.append("policy.require_verbatim_custody: must remain true")

    return issues


def contract_digest(schema: dict, registry: dict, profile: dict) -> str:
    payload = json.dumps(
        {"schema": schema, "registry": registry, "profile": profile},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validation_report(schema: dict, registry: dict, profile: dict) -> dict:
    active = [
        name for name in ("first", "second") if profile["instances"][name]["enabled"]
    ]
    inactive = [
        name for name in ("first", "second") if not profile["instances"][name]["enabled"]
    ]
    return {
        "status": "valid",
        "schema_version": profile["schema_version"],
        "profile_id": profile["profile_id"],
        "tribunal_code": profile["tribunal"]["code"],
        "active_instances": active,
        "inactive_instances": inactive,
        "contract_digest": contract_digest(schema, registry, profile),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a SuperJurista tribunal profile.")
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        schema = load_json(args.schema, "profile schema")
        registry = validate_registry(load_json(args.registry, "profile registry"))
        profile = load_json(args.profile, "tribunal profile")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ContractError("profile schema root must describe an object")
        if not isinstance(profile, dict):
            issues = ["$: expected object"]
        else:
            issues = validate_schema_value(profile, schema)
            if not issues:
                issues.extend(validate_profile_bindings(profile, registry))
        if issues:
            for issue in issues:
                print(f"[ERROR] {issue}", file=sys.stderr)
            return 1
        report = validation_report(schema, registry, profile)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(
                "[OK] tribunal profile "
                f"{report['profile_id']}: active={','.join(report['active_instances'])}; "
                f"inactive={','.join(report['inactive_instances'])}; "
                f"digest={report['contract_digest']}"
            )
        return 0
    except (ContractError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
