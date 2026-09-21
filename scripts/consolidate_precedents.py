#!/usr/bin/env python3
"""Deterministically consolidate official precedent corpora with citation custody."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schema_validation import ContractError, load_json, validate_schema_value


TYPE_RANK = {
    "binding_precedent": 700,
    "qualified_precedent": 600,
    "normative_precedent": 500,
    "summary": 400,
    "orientation": 300,
    "jurisprudence": 200,
    "persuasive_jurisprudence": 100,
}
DEFAULT_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "contracts"
    / "schemas"
    / "precedent-corpus.v1.schema.json"
)


class PrecedentConsolidationError(ValueError):
    """Raised when precedent inputs cannot be consolidated without losing custody."""


@dataclass(frozen=True)
class CitationCustody:
    source_id: str
    official_url: str
    verbatim_sha256: str


@dataclass(frozen=True)
class DuplicateAlias:
    canonical_source_id: str
    duplicate_source_id: str


@dataclass(frozen=True)
class StatusConflict:
    canonical_source_id: str
    source_statuses: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ConsolidationResult:
    corpus: dict
    citation_custody: tuple[CitationCustody, ...]
    duplicate_aliases: tuple[DuplicateAlias, ...]
    status_conflicts: tuple[StatusConflict, ...]


def consolidate_precedent_corpora(
    corpora: tuple[dict, ...],
    *,
    schema_path: Path = DEFAULT_SCHEMA,
) -> ConsolidationResult:
    """Merge schema-valid corpora without hiding duplicates or status conflicts."""
    if not isinstance(corpora, tuple) or not corpora:
        raise PrecedentConsolidationError("corpora must be a non-empty tuple")
    schema = load_json(schema_path, "precedent corpus schema")
    unique_by_id: dict[str, dict[str, Any]] = {}
    custody_by_id: dict[str, CitationCustody] = {}
    for index, corpus in enumerate(corpora):
        errors = validate_schema_value(corpus, schema)
        if errors:
            raise PrecedentConsolidationError(
                f"input corpus {index} violates the precedent contract: {'; '.join(errors)}"
            )
        for raw_source in corpus["sources"]:
            source = copy.deepcopy(raw_source)
            _validate_quote_custody(source)
            source_id = source["source_id"]
            existing = unique_by_id.get(source_id)
            if existing is not None:
                if existing != source:
                    raise PrecedentConsolidationError(
                        f"source_id {source_id} identifies different source records"
                    )
                continue
            unique_by_id[source_id] = source
            custody_by_id[source_id] = CitationCustody(
                source_id=source_id,
                official_url=source["official_url"],
                verbatim_sha256=hashlib.sha256(
                    source["verbatim_excerpt"].encode("utf-8")
                ).hexdigest(),
            )

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for source in unique_by_id.values():
        groups.setdefault(_logical_key(source), []).append(source)

    consolidated = []
    aliases = []
    conflicts = []
    for key in sorted(groups):
        group = sorted(
            groups[key],
            key=lambda item: (-TYPE_RANK[item["type"]], item["source_id"]),
        )
        canonical = copy.deepcopy(group[0])
        group_aliases = [
            DuplicateAlias(
                canonical_source_id=canonical["source_id"],
                duplicate_source_id=item["source_id"],
            )
            for item in group[1:]
        ]
        aliases.extend(group_aliases)
        if group_aliases:
            _append_status_note(
                canonical,
                "Deduplicated equivalent source IDs: "
                + ", ".join(alias.duplicate_source_id for alias in group_aliases)
                + ".",
            )
        source_statuses = tuple(
            sorted((item["source_id"], item["status"]) for item in group)
        )
        explicit_statuses = sorted(
            {status for _, status in source_statuses if status != "unknown"}
        )
        if len(explicit_statuses) > 1:
            canonical["status"] = "conflicting"
            _append_status_note(
                canonical,
                "Consolidation conflict: explicit statuses "
                + ", ".join(explicit_statuses)
                + ".",
            )
            conflicts.append(
                StatusConflict(
                    canonical_source_id=canonical["source_id"],
                    source_statuses=source_statuses,
                )
            )
        elif explicit_statuses:
            canonical["status"] = explicit_statuses[0]
        else:
            canonical["status"] = "unknown"
        consolidated.append(canonical)

    consolidated.sort(
        key=lambda item: (-TYPE_RANK[item["type"]], item["source_id"])
    )
    output = {"schema_version": 1, "sources": consolidated}
    output_errors = validate_schema_value(output, schema)
    if output_errors:
        raise PrecedentConsolidationError(
            "consolidated precedent contract failed: " + "; ".join(output_errors)
        )
    return ConsolidationResult(
        corpus=output,
        citation_custody=tuple(
            custody_by_id[source_id] for source_id in sorted(custody_by_id)
        ),
        duplicate_aliases=tuple(
            sorted(
                aliases,
                key=lambda item: (
                    item.canonical_source_id,
                    item.duplicate_source_id,
                ),
            )
        ),
        status_conflicts=tuple(
            sorted(conflicts, key=lambda item: item.canonical_source_id)
        ),
    )


def _validate_quote_custody(source: dict[str, Any]) -> None:
    excerpt = _normalize_text(source["verbatim_excerpt"])
    for field in ("legal_question", "holding"):
        value = _normalize_text(source[field])
        if value not in excerpt:
            raise PrecedentConsolidationError(
                f"citation custody failed for {source['source_id']}: "
                f"{field} is not preserved in verbatim_excerpt"
            )


def _logical_key(source: dict[str, Any]) -> tuple[str, str, str]:
    return (
        source["origin"],
        _comparison_key(source["reference"]),
        _comparison_key(source["holding"]),
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _comparison_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", _normalize_text(value))
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).casefold()


def _append_status_note(source: dict[str, Any], note: str) -> None:
    if note not in source["status_notes"]:
        source["status_notes"].append(note)


def build_consolidation_report(result: ConsolidationResult) -> dict:
    """Build a deterministic sidecar report for custody and merge decisions."""
    if not isinstance(result, ConsolidationResult):
        raise PrecedentConsolidationError("result has an invalid type")
    return {
        "schema_version": 1,
        "citation_custody": [
            {
                "source_id": item.source_id,
                "official_url": item.official_url,
                "verbatim_sha256": item.verbatim_sha256,
            }
            for item in result.citation_custody
        ],
        "duplicate_aliases": [
            {
                "canonical_source_id": item.canonical_source_id,
                "duplicate_source_id": item.duplicate_source_id,
            }
            for item in result.duplicate_aliases
        ],
        "status_conflicts": [
            {
                "canonical_source_id": item.canonical_source_id,
                "source_statuses": [
                    {"source_id": source_id, "status": status}
                    for source_id, status in item.source_statuses
                ],
            }
            for item in result.status_conflicts
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consolidate official precedent corpora with citation custody.",
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        type=Path,
        help="Precedent corpus input; repeat for multiple providers",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report-output", required=True, type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser


def main(argv: list[str] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        corpora = tuple(
            load_json(path, f"precedent corpus {path}") for path in args.input
        )
        result = consolidate_precedent_corpora(
            corpora,
            schema_path=args.schema,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.corpus, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        args.report_output.write_text(
            json.dumps(
                build_consolidation_report(result),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except (ContractError, OSError, PrecedentConsolidationError) as error:
        print(f"Precedent consolidation failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Wrote {len(result.corpus['sources'])} consolidated source(s) "
        f"with {len(result.citation_custody)} custody record(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
