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
from extract_labor_remedies import extract_requested_remedies
from schema_validation import load_json
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = ROOT / "runtime/contracts/schemas/labor-report.v1.schema.json"
SEGMENT_SCHEMA = ROOT / "runtime/providers/pje-pdf-segments.v1.schema.json"
MATRIX_SCHEMA = ROOT / "runtime/contracts/schemas/claim-matrix.v1.schema.json"
REMEDY_EVIDENCE_SCHEMA = ROOT / "runtime/contracts/schemas/requested-remedy-evidence.v2.schema.json"
TAXONOMY = ROOT / "runtime/domain/labor-claim-taxonomy.json"
PAGE_LOCATOR = re.compile(r"^(?:pages?|páginas?) ([0-9]+)(?:-([0-9]+))?(?:,.*)?$")
CASE_NUMBER = re.compile(r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}")


class PJeClaimMatrixExtractionError(ValueError):
    """Raised when a report cannot safely support claim-to-defense linkage."""


def _validate(value: dict, schema_path: Path, name: str) -> None:
    issues = validate_document(value, load_json(schema_path, f"esquema de {name}"))
    if issues:
        raise PJeClaimMatrixExtractionError(f"{name} inválido: {issues[0]}")


def _position_source(position: dict, documents: dict) -> SourceReference:
    document_id = position["source_document_id"]
    document = documents.get(document_id)
    if document is None:
        raise PJeClaimMatrixExtractionError(f"posição referencia documento desconhecido {document_id}")
    locator = position["source_locator"]
    match = PAGE_LOCATOR.fullmatch(locator)
    if match is None:
        raise PJeClaimMatrixExtractionError(
            f"posição {position['position_id']} tem localizador de página não suportado"
        )
    first = int(match.group(1))
    last = int(match.group(2) or match.group(1))
    if first > last or first < document["page_start"] or last > document["page_end"]:
        raise PJeClaimMatrixExtractionError(
            f"localizador da posição {position['position_id']} está fora do documento de origem"
        )
    return SourceReference(document_id=document_id, locator=locator)


def extract_claim_matrix(
    report: dict,
    segments: dict,
    taxonomy: dict,
    respondent_by_document: dict[str, str],
    requested_remedies_by_claim: dict[str, tuple[str, ...]] | None = None,
) -> dict:
    """Link exact labels only; do not infer parties, remedies, facts, or legal issues."""
    _validate(report, REPORT_SCHEMA, "relatório trabalhista")
    _validate(segments, SEGMENT_SCHEMA, "segmentos do PDF")
    documents = {item["document_id"]: item for item in segments["documents"]}
    if len(documents) != len(segments["documents"]):
        raise PJeClaimMatrixExtractionError("identificadores dos documentos segmentados devem ser únicos")
    party_roles = {item["party_id"]: item["role"] for item in report["parties"]}
    if len(party_roles) != len(report["parties"]):
        raise PJeClaimMatrixExtractionError("identificadores das partes do relatório devem ser únicos")
    positions = report["positions"]
    if len({item["position_id"] for item in positions}) != len(positions):
        raise PJeClaimMatrixExtractionError("identificadores das posições do relatório devem ser únicos")
    claim_positions = [item for item in positions if item["kind"] == "claim"]
    defense_positions = [item for item in positions if item["kind"] == "defense"]
    if not claim_positions:
        raise PJeClaimMatrixExtractionError("relatório não contém posições dos pedidos")
    remedies_by_claim = requested_remedies_by_claim or {}
    claim_ids = {item["position_id"].replace("POS-", "CLM-", 1) for item in claim_positions}
    if set(remedies_by_claim) - claim_ids:
        raise PJeClaimMatrixExtractionError("providências solicitadas referenciam pedido desconhecido")
    defense_documents = {item["source_document_id"] for item in defense_positions}
    if set(respondent_by_document) != defense_documents:
        raise PJeClaimMatrixExtractionError(
            "vinculação entre defesa e parte deve cobrir exatamente os documentos de defesa"
        )
    for document_id, party_id in respondent_by_document.items():
        if party_roles.get(party_id) != "respondent":
            raise PJeClaimMatrixExtractionError(
                f"vinculação da defesa {document_id} deve identificar uma reclamada"
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
                requested_remedies=remedies_by_claim.get(claim_id, ()),
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
                f"defesa {position['position_id']} está sem pedido de mesmo rótulo"
            )
        if len(matches) != 1:
            raise PJeClaimMatrixExtractionError(
                f"defesa {position['position_id']} tem rótulo de pedido ambíguo"
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
    _validate(matrix, MATRIX_SCHEMA, "matriz de pedidos")
    return matrix


def verify_pdf_custody(pdf_path: Path, segments: dict, report: dict) -> None:
    """Ensure the supplied report/segments relate to the exact source PDF."""
    source = pdf_path.resolve()
    if not source.is_file():
        raise PJeClaimMatrixExtractionError("PDF de origem não encontrado")
    reader = PdfReader(str(source))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    source_pdf = segments["source_pdf"]
    if digest != source_pdf["sha256"] or len(reader.pages) != source_pdf["page_count"]:
        raise PJeClaimMatrixExtractionError("custódia do PDF não corresponde aos segmentos")
    title = (reader.metadata or {}).get("/Title")
    case_match = CASE_NUMBER.search(title) if isinstance(title, str) else None
    if case_match is None or case_match.group(0) != report["case_context"]["case_number"]:
        raise PJeClaimMatrixExtractionError("processo do relatório não corresponde aos metadados do PDF")


def _write_protected_artifact(
    value: dict, *, filename: str, output_dir: Path, repository_root: Path
) -> Path:
    return _write_protected_artifacts(
        ((filename, value),), output_dir=output_dir, repository_root=repository_root
    )[0]


def _write_protected_artifacts(
    artifacts: tuple[tuple[str, dict], ...], *, output_dir: Path, repository_root: Path
) -> tuple[Path, ...]:
    destination = output_dir.resolve()
    repository = repository_root.resolve()
    if destination == repository or repository in destination.parents:
        raise PJeClaimMatrixExtractionError("saída da matriz de pedidos deve ficar fora do repositório")
    if not destination.is_dir():
        raise PJeClaimMatrixExtractionError("diretório de saída da matriz de pedidos deve existir previamente")
    paths = tuple(destination / filename for filename, _ in artifacts)
    if any(path.exists() for path in paths):
        raise PJeClaimMatrixExtractionError("saída da matriz de pedidos já existe")
    payloads = tuple(
        (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        for _, value in artifacts
    )
    written = []
    try:
        for path, payload in zip(paths, payloads):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            written.append(path)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
    except OSError:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        raise
    return paths


def write_claim_matrix_artifact(matrix: dict, *, output_dir: Path, repository_root: Path) -> Path:
    """Write one versioned claim matrix without overwriting prior case data."""
    return _write_protected_artifact(
        matrix, filename="claim-matrix.json", output_dir=output_dir,
        repository_root=repository_root,
    )


def write_remedy_evidence_artifact(
    evidence: dict, *, output_dir: Path, repository_root: Path
) -> Path:
    """Keep prayer excerpts and page locators in the same protected output directory."""
    _validate(evidence, REMEDY_EVIDENCE_SCHEMA, "evidência das providências")
    return _write_protected_artifact(
        evidence, filename="requested-remedy-evidence.json", output_dir=output_dir,
        repository_root=repository_root,
    )


def write_claim_matrix_with_evidence(
    matrix: dict, evidence: dict, *, output_dir: Path, repository_root: Path
) -> None:
    """Refuse a mixed-version output before writing either artifact."""
    _validate(evidence, REMEDY_EVIDENCE_SCHEMA, "evidência das providências")
    _write_protected_artifacts(
        (
            ("requested-remedy-evidence.json", evidence),
            ("claim-matrix.json", matrix),
        ),
        output_dir=output_dir,
        repository_root=repository_root,
    )


def extract_pdf_remedy_evidence(pdf_path: Path, segments: dict, report: dict) -> dict:
    """Extract final-prayer evidence only from the single claim source document."""
    verify_pdf_custody(pdf_path, segments, report)
    claim_positions = [item for item in report["positions"] if item["kind"] == "claim"]
    source_ids = {item["source_document_id"] for item in claim_positions}
    if len(source_ids) != 1:
        raise PJeClaimMatrixExtractionError("posições dos pedidos exigem uma petição inicial")
    document_id = source_ids.pop()
    documents = {item["document_id"]: item for item in segments["documents"]}
    document = documents.get(document_id)
    if document is None:
        raise PJeClaimMatrixExtractionError("petição inicial ausente dos segmentos do PDF")
    labels = [item["label"] for item in claim_positions]
    if len(labels) != len(set(labels)):
        raise PJeClaimMatrixExtractionError("rótulos dos pedidos são ambíguos para vincular providências")
    claim_ids_by_label = {
        item["label"]: item["position_id"].replace("POS-", "CLM-", 1)
        for item in claim_positions
    }
    reader = PdfReader(str(pdf_path.resolve()))
    page_texts = tuple(
        (number, reader.pages[number - 1].extract_text() or "")
        for number in range(document["page_start"], document["page_end"] + 1)
    )
    evidence = extract_requested_remedies(page_texts, document_id, claim_ids_by_label)
    result = {
        "schema_version": 2,
        "source_pdf_sha256": segments["source_pdf"]["sha256"],
        **evidence,
    }
    _validate(result, REMEDY_EVIDENCE_SCHEMA, "evidência das providências")
    return result


def remedy_codes_by_claim(evidence: dict) -> dict[str, tuple[str, ...]]:
    """Deduplicate codes while retaining each occurrence in source evidence."""
    grouped: dict[str, set[str]] = {}
    for entry in evidence["entries"]:
        grouped.setdefault(entry["claim_id"], set()).update(entry["remedy_codes"])
    return {claim_id: tuple(sorted(codes)) for claim_id, codes in grouped.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera uma matriz protegida de pedidos do PJe.")
    parser.add_argument("--input", required=True, type=Path, help="PDF original do PJe")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Diretório existente fora do repositório")
    parser.add_argument("--defense-party", action="append", default=[], metavar="DOC-ID=PTY-ID")
    parser.add_argument("--extract-remedies", action="store_true")
    parser.add_argument("--taxonomy", type=Path, default=TAXONOMY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        bindings = {}
        for item in args.defense_party:
            document_id, separator, party_id = item.partition("=")
            if not separator or not document_id or not party_id or document_id in bindings:
                raise PJeClaimMatrixExtractionError("vinculação inválida ou duplicada entre defesa e parte")
            bindings[document_id] = party_id
        report = load_json(args.report, "relatório trabalhista")
        segments = load_json(args.segments, "segmentos do PDF")
        _validate(report, REPORT_SCHEMA, "relatório trabalhista")
        _validate(segments, SEGMENT_SCHEMA, "segmentos do PDF")
        verify_pdf_custody(args.input, segments, report)
        evidence = (
            extract_pdf_remedy_evidence(args.input, segments, report)
            if args.extract_remedies else None
        )
        matrix = extract_claim_matrix(
            report, segments, load_claim_taxonomy(args.taxonomy), bindings,
            remedy_codes_by_claim(evidence) if evidence is not None else None,
        )
        if evidence is not None:
            write_claim_matrix_with_evidence(
                matrix, evidence, output_dir=args.output, repository_root=ROOT
            )
        else:
            write_claim_matrix_artifact(matrix, output_dir=args.output, repository_root=ROOT)
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"[ERRO] Matriz de pedidos do PJe: {error}", file=sys.stderr)
        return 1
    print(
        "[OK] Matriz de pedidos do PJe: "
        f"pedidos={len(matrix['claims'])} "
        f"defesas={sum(len(item['respondent_positions']) for item in matrix['claims'])} "
        f"providências={len(evidence['entries']) if evidence else 0} "
        f"lacunas={sum(len(item['review_gaps']) for item in matrix['claims'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
