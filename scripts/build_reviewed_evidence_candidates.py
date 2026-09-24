#!/usr/bin/env python3
"""Converte seleção revisada em candidatos, sem promover matriz canônica."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from build_evidence_matrix import EvidenceCandidate, SourceReference, build_evidence_matrix
from prepare_source_evidence_packet import EVIDENCE_SCHEMA
from review_evidence_inventory import REVIEW_NAME, validate_evidence_inventory_review
from schema_validation import load_json, validate_schema_value


ROOT = Path(__file__).resolve().parents[1]
MATRIX_NAME = "evidence-matrix-candidates.json"
PROVENANCE_NAME = "evidence-selection-provenance.json"
PROVENANCE_SCHEMA = ROOT / "runtime/operations/evidence-selection-provenance.v1.schema.json"


class ReviewedEvidenceCandidatesError(ValueError):
    """Indica seleção incompleta, divergente ou saída preexistente."""


def _encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _read_private(workspace: Path, name: str) -> bytes:
    path = workspace / name
    if path.is_symlink() or not path.is_file():
        raise ReviewedEvidenceCandidatesError(f"insumo ausente ou vinculado: {name}")
    return path.read_bytes()


def build_reviewed_evidence_candidates(workspace: Path) -> tuple[dict, dict]:
    """Reutiliza o construtor herdado somente após revisão sem pendências."""
    try:
        review_status = validate_evidence_inventory_review(workspace)
        if review_status["status"] != "reviewed_for_selection":
            raise ReviewedEvidenceCandidatesError("revisão contém pendências")
        review_bytes = _read_private(workspace, REVIEW_NAME)
        review = json.loads(review_bytes)
        claims = load_json(workspace / "claim-matrix.json", "matriz de pedidos")
        known_documents = tuple(item["document_id"] for item in review["documents"])
        known_claims = tuple(item["claim_id"] for item in claims["claims"])
        selected = sorted(
            (item for item in review["items"] if item["decision"] == "include"),
            key=lambda item: item["item_id"],
        )
        candidates = []
        selections = []
        for number, item in enumerate(selected, start=1):
            evidence_id = f"EVD-{number:03d}"
            source_document_id = item["source_document_id"]
            pdf_page = item["pdf_page"]
            candidates.append(EvidenceCandidate(
                evidence_id=evidence_id,
                claim_ids=tuple(item["selected_claim_ids"]),
                evidence_type=item["selected_type"],
                proposition=item["proposition"],
                relation=item["relation"],
                limitations=tuple(dict.fromkeys(
                    [*item["source_limitations"], *item["limitations"]]
                )),
                analysis_status="pending",
                conflicts_with_evidence_ids=(),
                source=SourceReference(
                    document_id=source_document_id,
                    locator=f"{source_document_id}, página {pdf_page}",
                ),
            ))
            selections.append({
                "item_id": item["item_id"],
                "evidence_id": evidence_id,
                "source_document_id": source_document_id,
                "pdf_page": pdf_page,
                "excerpt": item["excerpt"],
                "review_reason": item["reason"],
            })
        matrix = build_evidence_matrix(
            known_documents, known_claims, tuple(candidates)
        )
        if validate_schema_value(
            matrix, load_json(EVIDENCE_SCHEMA, "esquema da matriz de provas")
        ):
            raise ReviewedEvidenceCandidatesError("candidatos incompatíveis com a matriz")
        provenance = {
            "schema_version": 1,
            "status": "candidate_only",
            "source_pdf_sha256": review["source_pdf_sha256"],
            "inventory_index_sha256": review["inventory_index_sha256"],
            "review_sha256": hashlib.sha256(review_bytes).hexdigest(),
            "candidate_matrix_sha256": hashlib.sha256(_encode(matrix)).hexdigest(),
            "selections": selections,
            "excluded_item_ids": sorted(
                item["item_id"] for item in review["items"]
                if item["decision"] == "exclude"
            ),
        }
        if validate_schema_value(
            provenance, load_json(PROVENANCE_SCHEMA, "esquema de proveniência")
        ):
            raise ReviewedEvidenceCandidatesError("proveniência inválida")
        return matrix, provenance
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, ReviewedEvidenceCandidatesError):
            raise
        raise ReviewedEvidenceCandidatesError("candidatos probatórios recusados") from error


def publish_reviewed_evidence_candidates(workspace: Path) -> tuple[Path, Path]:
    """Publica dois arquivos protegidos sem substituir a matriz canônica."""
    matrix, provenance = build_reviewed_evidence_candidates(workspace)
    destination = workspace.resolve()
    payloads = (
        (MATRIX_NAME, _encode(matrix)),
        (PROVENANCE_NAME, _encode(provenance)),
    )
    if any((destination / name).exists() or (destination / name).is_symlink()
           for name, _ in payloads):
        raise ReviewedEvidenceCandidatesError("saída de candidatos já existe")
    created: list[Path] = []
    try:
        for name, content in payloads:
            path = destination / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
    except OSError as error:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise ReviewedEvidenceCandidatesError("publicação de candidatos recusada") from error
    return destination / MATRIX_NAME, destination / PROVENANCE_NAME


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepara candidatos probatórios de revisão completa, sem matriz canônica."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        matrix_path, _ = publish_reviewed_evidence_candidates(args.workspace)
        matrix = load_json(matrix_path, "candidatos probatórios")
    except ReviewedEvidenceCandidatesError as error:
        print(f"[ERRO] Candidatos probatórios: {error}", file=sys.stderr)
        return 2
    print(
        f"[OK] {len(matrix['evidence_items'])} candidato(s) protegido(s); "
        "a matriz canônica não foi criada."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
