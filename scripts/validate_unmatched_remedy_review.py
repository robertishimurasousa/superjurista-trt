#!/usr/bin/env python3
"""Confere decisões humanas sobre itens sem associação, sem alterar a matriz."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from prepare_unmatched_remedy_review import (
    RECORD_NAME,
    REVIEW_SCHEMA,
    UnmatchedRemedyReviewError,
    _private_file,
    current_review_sources,
)
from schema_validation import ContractError, load_json, validate_schema_value


def validate_unmatched_remedy_review(workspace: Path, pdf_path: Path) -> str:
    """Valida completude e custódia; retorna estado de comparação, não aprovação."""
    _, expected = current_review_sources(workspace, pdf_path)
    record_path = workspace.resolve() / RECORD_NAME
    _private_file(record_path, "registro da revisão")
    actual = load_json(record_path, "registro da revisão")
    if validate_schema_value(actual, load_json(REVIEW_SCHEMA, "esquema da revisão")):
        raise UnmatchedRemedyReviewError("registro da revisão inválido")

    fixed_fields = (
        "schema_version", "source_pdf_sha256", "evidence_sha256",
        "blind_inventory_sha256", "authorizes_external_action",
    )
    if any(actual[field] != expected[field] for field in fixed_fields):
        raise UnmatchedRemedyReviewError("registro diverge das fontes originais")
    expected_items = {item["request_id"]: item for item in expected["items"]}
    actual_items = actual["items"]
    if len(actual_items) != len(expected_items) or {
        item["request_id"] for item in actual_items
    } != set(expected_items):
        raise UnmatchedRemedyReviewError("itens revisados não cobrem exatamente a evidência")
    for item in actual_items:
        original = expected_items[item["request_id"]]
        if any(item[field] != original[field] for field in (
            "request_id", "source_document_id", "source_locator", "text_sha256"
        )):
            raise UnmatchedRemedyReviewError("identidade ou fonte do item foi alterada")

    if not actual["reviewer_name"].strip() or not actual["reviewed_at"]:
        raise UnmatchedRemedyReviewError("identificação e data da revisão obrigatórias")
    try:
        datetime.strptime(actual["reviewed_at"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise UnmatchedRemedyReviewError("data da revisão inválida") from error
    if not actual["blind_inventory_frozen"] or not actual["original_pdf_checked"]:
        raise UnmatchedRemedyReviewError("conferência do inventário e do PDF incompleta")
    if any(item["decision"] == "pending" or not item["reason"].strip()
           for item in actual_items):
        raise UnmatchedRemedyReviewError("há decisão pendente ou sem justificativa")
    if any(item["decision"] != "non_material" for item in actual_items):
        return "requires_followup"
    return "reviewed_for_comparison"


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida conferência humana sem aprovar a matriz.")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    args = parser.parse_args()
    try:
        status = validate_unmatched_remedy_review(args.workspace, args.pdf)
    except (UnmatchedRemedyReviewError, ContractError, OSError, ValueError,
            TypeError, UnicodeError, KeyError) as error:
        detail = str(error) if isinstance(error, UnmatchedRemedyReviewError) else "fontes ou registro inválidos"
        print(f"[ERRO] Conferência dos itens sem associação: {detail}", file=sys.stderr)
        return 2
    print(f"[OK] Conferência validada: {status}; nenhuma ação externa autorizada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
