#!/usr/bin/env python3
"""Confere a revisão declarada da minuta sem autenticar nem aprovar atos."""

from __future__ import annotations

import argparse
import stat
import sys
from datetime import datetime
from pathlib import Path

from prepare_final_human_review import (
    REVIEW_NAME, REVIEW_SCHEMA, FinalHumanReviewPacketError,
    current_review_sources, review_template,
)
from schema_validation import load_json, validate_schema_value


class FinalHumanReviewError(ValueError):
    """Indica revisão pendente ou incompatível com os arquivos examinados."""


def validate_final_human_review(workspace: Path) -> dict[str, int | str | bool]:
    """Confere cobertura e custódia das declarações, nunca a qualidade jurídica."""
    try:
        target, hashes, claims, analysis, dispositions = current_review_sources(workspace)
        path = target / REVIEW_NAME
        if path.is_symlink() or not path.is_file():
            raise FinalHumanReviewError("registro de revisão ausente ou vinculado")
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise FinalHumanReviewError("registro de revisão deve ser privado")
        review = load_json(path, "registro de revisão final")
        schema = load_json(REVIEW_SCHEMA, "esquema de revisão final")
        if validate_schema_value(review, schema):
            raise FinalHumanReviewError("contrato do registro de revisão inválido")
        expected = review_template(hashes, claims, analysis, dispositions)
        if review["source_hashes"] != expected["source_hashes"]:
            raise FinalHumanReviewError("fontes divergem da revisão registrada")
        reviewed = review["claims"]
        original = expected["claims"]
        by_claim = {item["claim_id"]: item for item in reviewed}
        expected_by_claim = {item["claim_id"]: item for item in original}
        if len(by_claim) != len(reviewed) or set(by_claim) != set(expected_by_claim):
            raise FinalHumanReviewError("cobertura dos pedidos da revisão diverge")
        fixed_fields = ("analysis_id", "disposition_id", "proposed_outcome")
        for claim_id, item in by_claim.items():
            if any(item[field] != expected_by_claim[claim_id][field] for field in fixed_fields):
                raise FinalHumanReviewError("origem da análise ou do dispositivo alterada")
        if (
            not review["reviewer_name"].strip()
            or not review["reviewed_at"]
            or not review["blind_inventory_frozen"]
            or not review["original_pdf_checked"]
        ):
            raise FinalHumanReviewError("revisão humana ainda pendente")
        datetime.strptime(review["reviewed_at"], "%Y-%m-%dT%H:%M:%SZ")
        for item in reviewed:
            if (
                not item["source_checked"]
                or not item["law_checked"]
                or not item["draft_checked"]
                or item["decision"] == "pending"
                or not item["reason"].strip()
            ):
                raise FinalHumanReviewError("revisão de pedido ainda pendente")
        status = (
            "reviewed_for_consideration"
            if all(item["decision"] == "agree" for item in reviewed)
            else "requires_followup"
        )
        return {
            "status": status,
            "claim_count": len(reviewed),
            "authorizes_external_action": False,
        }
    except (
        FinalHumanReviewPacketError, OSError, ValueError, TypeError,
        KeyError, UnicodeError,
    ) as error:
        if isinstance(error, FinalHumanReviewError):
            raise
        raise FinalHumanReviewError("conferência da revisão final recusada") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confere registro declarado de revisão final sem aprovar atos."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = validate_final_human_review(args.workspace)
    except FinalHumanReviewError as error:
        print(f"[ERRO] Revisão final: {error}", file=sys.stderr)
        return 2
    print(
        f"[OK] {result['claim_count']} pedido(s) revisado(s); estado "
        f"{result['status']}; nenhum ato externo autorizado."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
