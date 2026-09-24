#!/usr/bin/env python3
"""Validate SuperJurista legal artifacts and their canonical fixture suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from schema_validation import ContractError, load_json, validate_schema_value


def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_catalog(path: Path) -> tuple[dict, dict[str, tuple[dict, Path]]]:
    catalog = load_json(path, "artifact contract catalog")
    if not isinstance(catalog, dict) or set(catalog) != {"schema_version", "contracts"}:
        raise ContractError("catalog must contain only schema_version and contracts")
    if catalog["schema_version"] != 1:
        raise ContractError("catalog schema_version must be 1")
    contracts = catalog["contracts"]
    if not isinstance(contracts, dict) or not contracts:
        raise ContractError("catalog contracts must be a non-empty object")

    catalog_root = path.resolve().parent
    loaded: dict[str, tuple[dict, Path]] = {}
    for contract_id, entry in contracts.items():
        if not isinstance(contract_id, str) or not contract_id:
            raise ContractError("contract ids must be non-empty strings")
        if not isinstance(entry, dict) or set(entry) != {"current_version", "schema"}:
            raise ContractError(
                f"catalog contract {contract_id} must contain current_version and schema"
            )
        if not isinstance(entry["current_version"], int) or entry["current_version"] < 1:
            raise ContractError(f"contract {contract_id} current_version must be positive")
        if not isinstance(entry["schema"], str) or not entry["schema"]:
            raise ContractError(f"contract {contract_id} schema must be a path")
        schema_path = (catalog_root / entry["schema"]).resolve()
        try:
            schema_path.relative_to(catalog_root)
        except ValueError as error:
            raise ContractError(f"contract {contract_id} schema escapes catalog root") from error
        schema = load_json(schema_path, f"schema for {contract_id}")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ContractError(f"schema for {contract_id} must describe an object")
        version_schema = schema.get("properties", {}).get("schema_version", {})
        if version_schema.get("const") != entry["current_version"]:
            raise ContractError(
                f"contract {contract_id} version does not match its schema_version const"
            )
        loaded[contract_id] = (schema, schema_path)
    return catalog, loaded


def validate_document(document: object, schema: dict) -> list[str]:
    if not isinstance(document, dict):
        return ["$: expected object"]
    issues = validate_schema_value(document, schema)
    if issues:
        return issues
    if schema.get("$id", "").endswith("/issue-route.v1.schema.json"):
        issues.extend(validate_issue_route_semantics(document))
    if schema.get("$id", "").endswith("/claim-analysis.v1.schema.json"):
        issues.extend(validate_claim_analysis_semantics(document))
    if schema.get("$id", "").endswith("/procedural-timeline.v1.schema.json"):
        issues.extend(validate_procedural_timeline_semantics(document))
    if schema.get("$id", "").endswith("/document-classification.v2.schema.json"):
        issues.extend(validate_document_classification_semantics(document))
    if schema.get("$id", "").endswith("/requested-remedy-evidence.v2.schema.json"):
        issues.extend(validate_requested_remedy_evidence_semantics(document))
    return issues


def validate_requested_remedy_evidence_semantics(document: dict) -> list[str]:
    """Exige cobertura e localizadores coerentes para itens sem associação."""
    unmatched_ids = document["unmatched_item_ids"]
    unmatched = document["unmatched_items"]
    issues = []
    if unmatched_ids != [item["request_id"] for item in unmatched]:
        issues.append("unmatched_item_ids: deve corresponder aos itens sem associação")
    entry_ids = [item["request_id"] for item in document["entries"]]
    if len(entry_ids) != len(set(entry_ids)) or set(entry_ids) & set(unmatched_ids):
        issues.append("entries: identificadores de pedidos devem ser únicos")
    for index, item in enumerate(unmatched):
        if not item["source_locator"].endswith(f"pedido {item['request_id']}"):
            issues.append(f"unmatched_items[{index}].source_locator: pedido divergente")
    return issues


def validate_document_classification_semantics(document: dict) -> list[str]:
    """Recusa tipos inventados e evidência de classificação incoerente."""
    issues: list[str] = []
    seen_ids = set()
    new_types = {"procedural_certificate", "procedural_communication"}
    for index, item in enumerate(document["documents"]):
        path = f"documents[{index}]"
        document_id = item["document_id"]
        if document_id in seen_ids:
            issues.append(f"{path}.document_id: identificador deve ser único")
        seen_ids.add(document_id)
        document_type = item["document_type"]
        status = item["classification_status"]
        reason = item["reason_code"]
        rules = item["matched_rule_ids"]
        if document["classifier_version"] == 1 and document_type in new_types:
            issues.append(f"{path}.document_type: classificador v1 não pode atribuir tipo v2")
        if status == "classified":
            consistent = document_type != "unknown" and bool(rules) and reason == "matched_rule"
        elif status == "unknown":
            consistent = document_type == "unknown" and not rules and reason == "no_matching_rule"
        else:
            consistent = document_type == "unknown" and bool(rules) and reason == "conflicting_rules"
        if not consistent:
            issues.append(f"{path}.classification_status: evidência de classificação incoerente")
    return issues


def validate_procedural_timeline_semantics(document: dict) -> list[str]:
    """Reject inconsistent completeness and repeated or orphan source custody."""
    issues: list[str] = []
    gaps = document["gaps"]
    expected_status = "partial" if gaps else "complete"
    if document["status"] != expected_status:
        issues.append(
            f"status: must be {expected_status!r} when gaps are "
            f"{'present' if gaps else 'empty'}"
        )

    seen_event_ids = set()
    seen_source_ids = set()
    unclassified_source_ids = set()
    for index, event in enumerate(document["events"]):
        path = f"events[{index}]"
        if event["event_id"] in seen_event_ids:
            issues.append(f"{path}.event_id: value must be unique")
        if event["source_document_id"] in seen_source_ids:
            issues.append(
                f"{path}.source_document_id: timeline must contain one event per document"
            )
        seen_event_ids.add(event["event_id"])
        seen_source_ids.add(event["source_document_id"])
        if event["event_type"] == "unclassified_document_filed":
            unclassified_source_ids.add(event["source_document_id"])

    seen_gap_ids = set()
    gap_source_ids = set()
    for index, gap in enumerate(gaps):
        path = f"gaps[{index}]"
        subject_id = gap["subject_id"]
        if subject_id in seen_gap_ids:
            issues.append(f"{path}.subject_id: value must be unique")
        if subject_id not in seen_source_ids:
            issues.append(f"{path}.subject_id: source document is not present in events")
        seen_gap_ids.add(subject_id)
        gap_source_ids.add(subject_id)

    for subject_id in sorted(unclassified_source_ids - gap_source_ids):
        issues.append(f"gaps: missing review gap for {subject_id}")
    for subject_id in sorted(gap_source_ids - unclassified_source_ids):
        issues.append(f"gaps: {subject_id} does not identify an unclassified event")
    return issues


def validate_claim_analysis_semantics(document: dict) -> list[str]:
    """Reject incomplete outcomes and duplicate analysis coverage."""
    issues: list[str] = []
    merits = {"granted", "denied", "granted_in_part"}
    procedural = {"dismissed_without_merits", "procedural_resolution"}
    unresolved = {"pending_human_review", "abstained"}
    seen_analysis_ids = set()
    seen_claim_ids = set()
    for index, analysis in enumerate(document["analyses"]):
        path = f"analyses[{index}]"
        if analysis["analysis_id"] in seen_analysis_ids:
            issues.append(f"{path}.analysis_id: value must be unique")
        if analysis["claim_id"] in seen_claim_ids:
            issues.append(f"{path}.claim_id: analysis must be unique per claim")
        seen_analysis_ids.add(analysis["analysis_id"])
        seen_claim_ids.add(analysis["claim_id"])
        outcome = analysis["proposed_outcome"]
        if outcome in merits:
            required = (
                "facts_found",
                "evidence_ids",
                "evidence_assessment",
                "applicable_rules",
            )
        elif outcome in procedural:
            required = ("facts_found", "applicable_rules")
        else:
            required = ()
        for field in required:
            if not analysis[field]:
                issues.append(f"{path}.{field}: {outcome} requires supporting content")
        if outcome in unresolved and not analysis["limitations"]:
            issues.append(
                f"{path}.limitations: {outcome} requires an explicit limitation"
            )
    return issues


def validate_issue_route_semantics(document: dict) -> list[str]:
    """Validate cross-field rules outside the supported JSON Schema subset."""
    issues: list[str] = []
    seen_claim_ids = set()
    for index, route in enumerate(document["routes"]):
        path = f"routes[{index}]"
        claim_id = route["claim_id"]
        if claim_id in seen_claim_ids:
            issues.append(f"{path}.claim_id: route must be unique per claim")
        seen_claim_ids.add(claim_id)
        enabled = any(
            route[field]
            for field in (
                "requires_legal_research",
                "requires_evidence_analysis",
                "requires_calculation_review",
                "requires_procedural_review",
            )
        )
        if route["route_status"] == "routed":
            if not enabled:
                issues.append(f"{path}.route_status: routed claim requires a track")
            if route["abstention_reasons"]:
                issues.append(
                    f"{path}.abstention_reasons: routed claim must not abstain"
                )
        else:
            if enabled:
                issues.append(
                    f"{path}.route_status: abstained claim cannot enable a track"
                )
            if not route["abstention_reasons"]:
                issues.append(
                    f"{path}.abstention_reasons: abstained claim requires a reason"
                )
        question_rules = (
            (
                "requires_legal_research",
                "research_questions",
                "legal research",
            ),
            (
                "requires_evidence_analysis",
                "evidence_questions",
                "evidence analysis",
            ),
        )
        for flag, questions, label in question_rules:
            if route[flag] and not route[questions]:
                issues.append(f"{path}.{questions}: {label} requires a question")
            if not route[flag] and route[questions]:
                issues.append(f"{path}.{questions}: disabled track must be empty")
    return issues


def run_fixture_suite(
    contracts: dict[str, tuple[dict, Path]],
    fixtures_root: Path,
) -> tuple[dict, list[str]]:
    issues: list[str] = []
    valid_count = 0
    invalid_count = 0
    for contract_id, (schema, _) in sorted(contracts.items()):
        valid_path = fixtures_root / "valid" / f"{contract_id}.json"
        valid_document = load_json(valid_path, f"valid fixture for {contract_id}")
        valid_issues = validate_document(valid_document, schema)
        if valid_issues:
            issues.extend(f"{valid_path}: {issue}" for issue in valid_issues)
        valid_count += 1

        invalid_root = fixtures_root / "invalid" / contract_id
        invalid_paths = sorted(invalid_root.glob("*.json"))
        if not invalid_paths:
            raise ContractError(f"invalid fixture is required for contract {contract_id}")
        for invalid_path in invalid_paths:
            invalid_document = load_json(invalid_path, f"invalid fixture for {contract_id}")
            if not validate_document(invalid_document, schema):
                issues.append(f"{invalid_path}: invalid fixture unexpectedly passed")
            invalid_count += 1

    report = {
        "status": "valid" if not issues else "invalid",
        "contracts": sorted(contracts),
        "valid_fixture_count": valid_count,
        "invalid_fixture_count": invalid_count,
    }
    return report, issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate legal artifact contracts.")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--fixtures-root", type=Path)
    parser.add_argument("--contract")
    parser.add_argument("--document", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        catalog, contracts = load_catalog(args.catalog.resolve())
        fixture_mode = args.fixtures_root is not None
        document_mode = args.contract is not None or args.document is not None
        if fixture_mode == document_mode:
            raise ContractError(
                "choose either --fixtures-root or both --contract and --document"
            )

        if fixture_mode:
            report, issues = run_fixture_suite(contracts, args.fixtures_root.resolve())
        else:
            if args.contract is None or args.document is None:
                raise ContractError("--contract and --document must be provided together")
            if args.contract not in contracts:
                raise ContractError(f"unknown contract: {args.contract}")
            schema, _ = contracts[args.contract]
            document = load_json(args.document.resolve(), "artifact document")
            issues = validate_document(document, schema)
            report = {
                "status": "valid" if not issues else "invalid",
                "contract": args.contract,
                "schema_version": document.get("schema_version")
                if isinstance(document, dict)
                else None,
                "contract_digest": canonical_digest(
                    {"catalog_version": catalog["schema_version"], "schema": schema}
                ),
            }

        if issues:
            for issue in issues:
                print(f"[ERROR] {issue}", file=sys.stderr)
            return 1
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        elif fixture_mode:
            print(
                "[OK] artifact contracts: "
                f"{report['valid_fixture_count']} valid and "
                f"{report['invalid_fixture_count']} invalid fixtures checked"
            )
        else:
            print(
                f"[OK] artifact contract {report['contract']} "
                f"v{report['schema_version']}: digest={report['contract_digest']}"
            )
        return 0
    except (ContractError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
