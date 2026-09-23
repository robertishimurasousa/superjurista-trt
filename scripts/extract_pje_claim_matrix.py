#!/usr/bin/env python3
"""Build a protected, partial claim matrix from a source-linked labor report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from PyPDF2 import PdfReader

from build_claim_matrix import (
    ClaimCandidate,
    DefenseCandidate,
    SourceReference,
    build_claim_matrix,
    load_claim_taxonomy,
)
from schema_validation import load_json
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = ROOT / "runtime/contracts/schemas/labor-report.v1.schema.json"
SEGMENT_SCHEMA = ROOT / "runtime/providers/pje-pdf-segments.v1.schema.json"
MATRIX_SCHEMA = ROOT / "runtime/contracts/schemas/claim-matrix.v1.schema.json"
TAXONOMY = ROOT / "runtime/domain/labor-claim-taxonomy.json"
PAGE_LOCATOR = re.compile(r"^pages? ([0-9]+)(?:-([0-9]+))?(?:,.*)?$")
CASE_NUMBER = re.compile(r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}")


class PJeClaimMatrixExtractionError(ValueError):
    """Raised when a report cannot safely support claim-to-defense linkage."""


def _validate(value: dict, schema_path: Path, name: str) -> None:
    issues = validate_document(value, load_json(schema_path, f"{name} schema"))
    if issues:
        raise PJeClaimMatrixExtractionError(f"invalid {name}: {issues[0]}")


def _position_source(position: dict, documents: dict) -> SourceReference:
    document_id = position["source_document_id"]
    document = documents.get(document_id)
    if document is None:
        raise PJeClaimMatrixExtractionError(f"position references unknown document {document_id}")
    locator = position["source_locator"]
    match = PAGE_LOCATOR.fullmatch(locator)
    if match is None:
        raise PJeClaimMatrixExtractionError(
            f"position {position['position_id']} has unsupported page locator"
        )
    first = int(match.group(1))
    last = int(match.group(2) or match.group(1))
    if first > last or first < document["page_start"] or last > document["page_end"]:
        raise PJeClaimMatrixExtractionError(
            f"position {position['position_id']} page locator is outside source document"
        )
    return SourceReference(document_id=document_id, locator=locator)


def extract_claim_matrix(
    report: dict,
    segments: dict,
    taxonomy: dict,
    respondent_by_document: dict[str, str],
) -> dict:
    """Link exact labels only; do not infer parties, remedies, facts, or legal issues."""
    _validate(report, REPORT_SCHEMA, "labor report")
    _validate(segments, SEGMENT_SCHEMA, "PDF segments")
    documents = {item["document_id"]: item for item in segments["documents"]}
    if len(documents) != len(segments["documents"]):
        raise PJeClaimMatrixExtractionError("segment document identifiers must be unique")
    party_roles = {item["party_id"]: item["role"] for item in report["parties"]}
    if len(party_roles) != len(report["parties"]):
        raise PJeClaimMatrixExtractionError("report party identifiers must be unique")
    positions = report["positions"]
    if len({item["position_id"] for item in positions}) != len(positions):
        raise PJeClaimMatrixExtractionError("report position identifiers must be unique")
    claim_positions = [item for item in positions if item["kind"] == "claim"]
    defense_positions = [item for item in positions if item["kind"] == "defense"]
    if not claim_positions:
        raise PJeClaimMatrixExtractionError("report has no claim positions")
    defense_documents = {item["source_document_id"] for item in defense_positions}
    if set(respondent_by_document) != defense_documents:
        raise PJeClaimMatrixExtractionError(
            "defense-party binding must cover exactly the defense source documents"
        )
    for document_id, party_id in respondent_by_document.items():
        if party_roles.get(party_id) != "respondent":
            raise PJeClaimMatrixExtractionError(
                f"defense-party binding for {document_id} must identify a respondent"
            )

    claims = []
    claims_by_label: dict[str, list[str]] = {}
    for position in claim_positions:
        claim_id = position["position_id"].replace("POS-", "CLM-", 1)
        source = _position_source(position, documents)
        claims.append(
            ClaimCandidate(
                claim_id=claim_id,
                label=position["label"],
                claimant_position=position["summary"],
                requested_remedies=(),
                contested_facts=(),
                legal_issues=(),
                source=source,
            )
        )
        claims_by_label.setdefault(position["label"], []).append(claim_id)

    defenses = []
    for position in defense_positions:
        matches = claims_by_label.get(position["label"], [])
        if not matches:
            raise PJeClaimMatrixExtractionError(
                f"defense {position['position_id']} has no claim with the same label"
            )
        if len(matches) != 1:
            raise PJeClaimMatrixExtractionError(
                f"defense {position['position_id']} has ambiguous claim label"
            )
        defenses.append(
            DefenseCandidate(
                defense_id=position["position_id"].replace("POS-", "DEF-", 1),
                claim_id=matches[0],
                respondent_party_id=respondent_by_document[position["source_document_id"]],
                respondent_position=position["summary"],
                source=_position_source(position, documents),
            )
        )
    matrix = build_claim_matrix(
        taxonomy,
        tuple(sorted(documents)),
        tuple(claims),
        tuple(defenses),
    )
    _validate(matrix, MATRIX_SCHEMA, "claim matrix")
    return matrix


def verify_pdf_custody(pdf_path: Path, segments: dict, report: dict) -> None:
    """Ensure the supplied report/segments relate to the exact source PDF."""
    source = pdf_path.resolve()
    if not source.is_file():
        raise PJeClaimMatrixExtractionError("source PDF does not exist")
    reader = PdfReader(str(source))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    source_pdf = segments["source_pdf"]
    if digest != source_pdf["sha256"] or len(reader.pages) != source_pdf["page_count"]:
        raise PJeClaimMatrixExtractionError("PDF custody does not match segments")
    title = (reader.metadata or {}).get("/Title")
    case_match = CASE_NUMBER.search(title) if isinstance(title, str) else None
    if case_match is None or case_match.group(0) != report["case_context"]["case_number"]:
        raise PJeClaimMatrixExtractionError("report case does not match PDF metadata")


def write_claim_matrix_artifact(matrix: dict, *, output_dir: Path, repository_root: Path) -> Path:
    """Write once with restrictive permissions, never into the repository."""
    destination = output_dir.resolve()
    repository = repository_root.resolve()
    if destination == repository or repository in destination.parents:
        raise PJeClaimMatrixExtractionError("claim matrix output must stay outside repository")
    if not destination.is_dir():
        raise PJeClaimMatrixExtractionError("claim matrix output directory must already exist")
    path = destination / "claim-matrix.json"
    if path.exists():
        raise PJeClaimMatrixExtractionError("claim matrix output already exists")
    payload = (json.dumps(matrix, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a protected partial PJe claim matrix.")
    parser.add_argument("--input", required=True, type=Path, help="Original PJe PDF")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Existing directory outside repository")
    parser.add_argument("--defense-party", action="append", default=[], metavar="DOC-ID=PTY-ID")
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        bindings = {}
        for item in args.defense_party:
            document_id, separator, party_id = item.partition("=")
            if not separator or not document_id or not party_id or document_id in bindings:
                raise PJeClaimMatrixExtractionError("invalid or duplicate defense-party binding")
            bindings[document_id] = party_id
        report = load_json(args.report, "labor report")
        segments = load_json(args.segments, "PDF segments")
        _validate(report, REPORT_SCHEMA, "labor report")
        _validate(segments, SEGMENT_SCHEMA, "PDF segments")
        verify_pdf_custody(args.input, segments, report)
        matrix = extract_claim_matrix(report, segments, load_claim_taxonomy(args.taxonomy), bindings)
        write_claim_matrix_artifact(matrix, output_dir=args.output, repository_root=ROOT)
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"[ERROR] PJe claim matrix: {error}", file=sys.stderr)
        return 1
    print(
        "[OK] PJe claim matrix: "
        f"claims={len(matrix['claims'])} "
        f"defenses={sum(len(item['respondent_positions']) for item in matrix['claims'])} "
        f"review_gaps={sum(len(item['review_gaps']) for item in matrix['claims'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
