#!/usr/bin/env python3
"""Validate extracted TRT12 record coverage against acquired PJe documents."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from build_procedural_timeline import EVENT_PRESENTATION, UNCLASSIFIED_EVENT
from schema_validation import ContractError, load_json, validate_schema_value
from validate_artifact_contracts import load_catalog, validate_document
from verify_pje_acquisition_custody import INDEX_SCHEMA


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "runtime/contracts/catalog.json"
CONTRACTS = {
    "document-classification.json": "document-classification",
    "procedural-timeline.json": "procedural-timeline",
    "labor-report.json": "labor-report",
}


def make_extraction_gate(workspace: Path) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Return a fail-closed gate for the extracted record stage only."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()

    def read_json(name: str, label: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("insumo ausente ou vínculo simbólico")
        return load_json(path, label)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if stage.get("id") != "extract-record" or stage.get("gate") != "record-completeness":
            return False
        if outputs != tuple((root / name).resolve() for name in CONTRACTS):
            return False
        try:
            context = read_json("case-context.json", "contexto do processo")
            index = read_json("document-index.json", "índice PJe")
            if validate_schema_value(index, load_json(INDEX_SCHEMA, "esquema do índice PJe")):
                return False
            if index["status"] != "complete" or index["gaps"]:
                return False
            if index["case"] != {
                "case_number": context["case_number"],
                "tribunal_code": context["court"],
                "instance": context["instance"],
                "court_unit": context["court_unit"],
                "task_id": index["case"]["task_id"],
            }:
                return False
            _, contracts = load_catalog(CATALOG)
            artifacts = {}
            for name, contract_id in CONTRACTS.items():
                value = read_json(name, contract_id)
                if validate_document(value, contracts[contract_id][0]):
                    return False
                artifacts[name] = value
            classification = artifacts["document-classification.json"]
            timeline = artifacts["procedural-timeline.json"]
            report = artifacts["labor-report.json"]
            indexed_ids = [item["document_id"] for item in index["documents"]]
            indexed_id_set = set(indexed_ids)
            classified = classification["documents"]
            classified_ids = [item["document_id"] for item in classified]
            events = timeline["events"]
            event_ids = [event["source_document_id"] for event in events]
            if (
                not indexed_ids
                or len(indexed_ids) != len(indexed_id_set)
                or len(classified_ids) != len(set(classified_ids))
                or set(classified_ids) != indexed_id_set
                or set(event_ids) != indexed_id_set
                or report["case_context"] != context
                or report["timeline"] != events
            ):
                return False
            classified_by_id = {item["document_id"]: item for item in classified}
            expected_gaps = {}
            for event in events:
                document_id = event["source_document_id"]
                item = classified_by_id[document_id]
                classification_status = item["classification_status"]
                expected_reason = {
                    "classified": "matched_rule",
                    "unknown": "no_matching_rule",
                    "conflict": "conflicting_rules",
                }[classification_status]
                if item["reason_code"] != expected_reason or (
                    bool(item["matched_rule_ids"]) != (classification_status != "unknown")
                ):
                    return False
                if classification_status == "classified":
                    if (
                        item["document_type"] not in EVENT_PRESENTATION
                        or event["event_type"] != EVENT_PRESENTATION[item["document_type"]][0]
                    ):
                        return False
                else:
                    if item["document_type"] != "unknown" or event["event_type"] != UNCLASSIFIED_EVENT[0]:
                        return False
                    expected_gaps[document_id] = (
                        "classification_conflict"
                        if classification_status == "conflict"
                        else "unclassified_document"
                    )
            if {gap["subject_id"]: gap["reason_code"] for gap in timeline["gaps"]} != expected_gaps:
                return False
            references = [*report["parties"], *report["positions"]]
            references.append(report["procedural_phase"])
            for reference in references:
                source_id = reference["source_document_id"]
                if source_id is not None and source_id not in indexed_id_set:
                    return False
            return True
        except (ContractError, ValueError, OSError, UnicodeError, KeyError, TypeError):
            return False

    return validate
