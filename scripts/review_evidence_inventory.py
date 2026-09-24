#!/usr/bin/env python3
"""Prepara e confere decisões humanas sobre o inventário, sem criar provas."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from prepare_evidence_inventory_packets import INDEX_NAME, SEGMENTS_NAME
from schema_validation import load_json, validate_schema_value
from validate_evidence_inventory_batch import validate_evidence_inventory_batch


ROOT = Path(__file__).resolve().parents[1]
REVIEW_NAME = "evidence-inventory-review.json"
REVIEW_SCHEMA = ROOT / "runtime/operations/evidence-inventory-review.v1.schema.json"
SOURCE_FIELDS = (
    "source_document_id", "pdf_page", "excerpt", "source_type", "description",
    "source_limitations", "proposed_claim_ids",
)
DOCUMENT_SOURCE_FIELDS = (
    "page_start", "page_end", "inventory_status", "coverage_status",
    "inventory_limitations",
)


class EvidenceInventoryReviewError(ValueError):
    """Indica revisão incompleta ou alterada em relação às fontes."""


def _read_json(workspace: Path, name: str) -> dict:
    path = workspace / name
    if path.is_symlink() or not path.is_file():
        raise EvidenceInventoryReviewError(f"insumo ausente ou vinculado: {name}")
    return load_json(path, name)


def _source_template(workspace: Path) -> tuple[dict, dict]:
    coverage = validate_evidence_inventory_batch(workspace)
    index = _read_json(workspace, INDEX_NAME)
    segments = _read_json(workspace, SEGMENTS_NAME)
    by_document = {
        item["document_id"]: item for item in segments["documents"]
    }
    documents = []
    items = []
    for document_id in sorted(by_document):
        document = by_document[document_id]
        observation = _read_json(
            workspace, f"{document_id}-inventory-observations.json"
        )
        documents.append({
            "document_id": document_id,
            "page_start": document["page_start"],
            "page_end": document["page_end"],
            "inventory_status": observation["status"],
            "coverage_status": observation["coverage_status"],
            "inventory_limitations": observation["limitations"],
            "all_pages_reviewed": False,
            "missing_item_note": "",
            "notes": "",
        })
        for item in observation["items"]:
            items.append({
                "item_id": item["item_id"],
                "source_document_id": document_id,
                "pdf_page": item["excerpt"]["pdf_page"],
                "excerpt": item["excerpt"]["text"],
                "source_type": item["type"],
                "description": item["description"],
                "source_limitations": item["limitations"],
                "proposed_claim_ids": item["claim_ids"],
                "decision": "pending",
                "selected_type": "",
                "selected_claim_ids": [],
                "relation": "",
                "proposition": "",
                "reason": "",
                "limitations": [],
            })
    template = {
        "schema_version": 1,
        "source_pdf_sha256": index["source_pdf_sha256"],
        "inventory_index_sha256": hashlib.sha256(
            (workspace / INDEX_NAME).read_bytes()
        ).hexdigest(),
        "reviewer_name": "",
        "reviewed_at": "",
        "documents": documents,
        "items": items,
    }
    return template, coverage


def prepare_evidence_inventory_review(workspace: Path) -> Path:
    """Cria registro pendente e privado a partir de fontes conferidas."""
    try:
        template, _ = _source_template(workspace)
        if validate_schema_value(template, load_json(REVIEW_SCHEMA, "esquema de revisão")):
            raise EvidenceInventoryReviewError("modelo de revisão inválido")
        path = workspace.resolve() / REVIEW_NAME
        if path.exists() or path.is_symlink():
            raise EvidenceInventoryReviewError("revisão já existe; arquivo preservado")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(template, output, ensure_ascii=False, indent=2)
            output.write("\n")
        return path
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, EvidenceInventoryReviewError):
            raise
        raise EvidenceInventoryReviewError("preparo da revisão recusado") from error


def _indexed(values: list[dict], key: str, label: str) -> dict[str, dict]:
    indexed = {item[key]: item for item in values}
    if len(indexed) != len(values):
        raise EvidenceInventoryReviewError(f"{label} duplicado na revisão")
    return indexed


def validate_evidence_inventory_review(workspace: Path) -> dict[str, int | str]:
    """Confere cobertura e escolhas declaradas, sem autenticar o revisor."""
    try:
        expected, coverage = _source_template(workspace)
        review = _read_json(workspace, REVIEW_NAME)
        if validate_schema_value(review, load_json(REVIEW_SCHEMA, "esquema de revisão")):
            raise EvidenceInventoryReviewError("contrato de revisão inválido")
        if (
            review["source_pdf_sha256"] != expected["source_pdf_sha256"]
            or review["inventory_index_sha256"] != expected["inventory_index_sha256"]
            or not review["reviewer_name"].strip()
            or not review["reviewed_at"]
        ):
            raise EvidenceInventoryReviewError("fonte ou declaração do revisor ausente")
        reviewed_documents = _indexed(review["documents"], "document_id", "documento")
        expected_documents = _indexed(expected["documents"], "document_id", "documento")
        if set(reviewed_documents) != set(expected_documents):
            raise EvidenceInventoryReviewError("cobertura documental da revisão diverge")
        missing_notes = 0
        for document_id, item in reviewed_documents.items():
            source = expected_documents[document_id]
            if any(item[field] != source[field] for field in DOCUMENT_SOURCE_FIELDS):
                raise EvidenceInventoryReviewError("fonte documental da revisão alterada")
            if not item["all_pages_reviewed"]:
                raise EvidenceInventoryReviewError("há documento sem conferência de páginas")
            missing_notes += bool(item["missing_item_note"].strip())
        reviewed_items = _indexed(review["items"], "item_id", "item")
        expected_items = _indexed(expected["items"], "item_id", "item")
        if set(reviewed_items) != set(expected_items):
            raise EvidenceInventoryReviewError("cobertura dos itens da revisão diverge")
        known_claims = {
            item["claim_id"] for item in _read_json(workspace, "claim-matrix.json")["claims"]
        }
        counts = {"include": 0, "exclude": 0, "defer": 0}
        for item_id, item in reviewed_items.items():
            source = expected_items[item_id]
            if any(item[field] != source[field] for field in SOURCE_FIELDS):
                raise EvidenceInventoryReviewError("item da revisão diverge da observação")
            decision = item["decision"]
            if decision == "pending" or not item["reason"].strip():
                raise EvidenceInventoryReviewError("decisão ou justificativa pendente")
            if decision == "include":
                if (
                    not item["selected_claim_ids"]
                    or not set(item["selected_claim_ids"]) <= known_claims
                    or not item["selected_type"]
                    or not item["relation"]
                    or not item["proposition"].strip()
                ):
                    raise EvidenceInventoryReviewError("seleção sem pedido, relação ou proposição")
            elif (
                item["selected_type"] or item["selected_claim_ids"] or item["relation"]
                or item["proposition"].strip()
            ):
                raise EvidenceInventoryReviewError("item não selecionado contém avaliação")
            counts[decision] += 1
        return {
            "document_count": coverage["document_count"],
            "item_count": coverage["item_count"],
            "included_count": counts["include"],
            "excluded_count": counts["exclude"],
            "deferred_count": counts["defer"],
            "missing_item_note_count": missing_notes,
            "status": (
                "requires_followup"
                if counts["defer"] or missing_notes or coverage["insufficient_count"]
                else "reviewed_for_selection"
            ),
        }
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, EvidenceInventoryReviewError):
            raise
        raise EvidenceInventoryReviewError("revisão do inventário recusada") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepara ou confere revisão humana do inventário sem criar matriz de provas."
    )
    parser.add_argument("action", choices=("prepare", "validate"))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            path = prepare_evidence_inventory_review(args.workspace)
            review = _read_json(path.parent, REVIEW_NAME)
            print(
                f"[OK] Revisão pendente preparada para {len(review['documents'])} "
                f"documento(s) e {len(review['items'])} item(ns); nenhuma prova aceita."
            )
        else:
            result = validate_evidence_inventory_review(args.workspace)
            print(
                f"[OK] Revisão declarada: {result['included_count']} selecionado(s), "
                f"{result['excluded_count']} excluído(s), "
                f"{result['deferred_count']} pendente(s) de apuração; "
                f"estado {result['status']}. Nenhuma matriz criada."
            )
    except EvidenceInventoryReviewError as error:
        print(f"[ERRO] Revisão do inventário: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
