#!/usr/bin/env python3
"""Reconstrói e confere candidatos probatórios publicados, sem escrever arquivos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from build_reviewed_evidence_candidates import (
    MATRIX_NAME,
    PROVENANCE_NAME,
    _encode,
    _read_private,
    build_reviewed_evidence_candidates,
)


class ReviewedEvidenceVerificationError(ValueError):
    """Indica que candidatos ou proveniência divergiram da revisão atual."""


def verify_reviewed_evidence_candidates(workspace: Path) -> dict[str, int]:
    """Compara os arquivos publicados à reconstrução de todas as fontes."""
    try:
        matrix, provenance = build_reviewed_evidence_candidates(workspace)
        if (
            _read_private(workspace, MATRIX_NAME) != _encode(matrix)
            or _read_private(workspace, PROVENANCE_NAME) != _encode(provenance)
        ):
            raise ReviewedEvidenceVerificationError(
                "candidatos ou proveniência divergem da revisão"
            )
        return {
            "candidate_count": len(matrix["evidence_items"]),
            "uncovered_claim_count": len(matrix["uncovered_claim_ids"]),
            "excluded_count": len(provenance["excluded_item_ids"]),
        }
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, ReviewedEvidenceVerificationError):
            raise
        raise ReviewedEvidenceVerificationError("verificação dos candidatos recusada") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confere candidatos e proveniência contra o inventário e revisão atuais."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify_reviewed_evidence_candidates(args.workspace)
    except ReviewedEvidenceVerificationError as error:
        print(f"[ERRO] Candidatos probatórios: {error}", file=sys.stderr)
        return 2
    print(
        f"[OK] {result['candidate_count']} candidato(s), "
        f"{result['uncovered_claim_count']} pedido(s) sem candidato e "
        f"{result['excluded_count']} item(ns) excluído(s); fontes e hashes conferidos."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
