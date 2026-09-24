#!/usr/bin/env python3
"""Promove candidatos revisados com aprovação declarada, sem inferir mérito."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from datetime import datetime
from pathlib import Path

from build_reviewed_evidence_candidates import MATRIX_NAME, PROVENANCE_NAME, _encode
from review_evidence_inventory import REVIEW_NAME
from schema_validation import load_json, validate_schema_value
from verify_reviewed_evidence_candidates import verify_reviewed_evidence_candidates


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_NAME = "evidence-matrix-approval.json"
CANONICAL_NAME = "evidence-matrix.json"
PROMOTION_NAME = "evidence-matrix-promotion.json"
APPROVAL_SCHEMA = ROOT / "runtime/operations/evidence-matrix-approval.v1.schema.json"
PROMOTION_SCHEMA = ROOT / "runtime/operations/evidence-matrix-promotion.v1.schema.json"


class EvidenceMatrixPromotionError(ValueError):
    """Indica que a promoção ou sua conferência deve ser recusada."""


def _private_workspace(workspace: Path) -> Path:
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise EvidenceMatrixPromotionError("espaço de trabalho inválido")
    resolved = workspace.resolve()
    if resolved == ROOT or resolved.is_relative_to(ROOT):
        raise EvidenceMatrixPromotionError("o processo não pode estar no repositório")
    if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise EvidenceMatrixPromotionError("espaço de trabalho deve ser privado")
    return resolved


def _read_private(workspace: Path, name: str) -> bytes:
    path = workspace / name
    if path.is_symlink() or not path.is_file():
        raise EvidenceMatrixPromotionError(f"insumo ausente ou vinculado: {name}")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise EvidenceMatrixPromotionError(f"insumo não privado: {name}")
    return path.read_bytes()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validated_payloads(workspace: Path) -> tuple[bytes, bytes, dict]:
    verify_reviewed_evidence_candidates(workspace)
    matrix_bytes = _read_private(workspace, MATRIX_NAME)
    provenance_bytes = _read_private(workspace, PROVENANCE_NAME)
    approval_bytes = _read_private(workspace, APPROVAL_NAME)
    review_bytes = _read_private(workspace, REVIEW_NAME)
    matrix = json.loads(matrix_bytes)
    provenance = json.loads(provenance_bytes)
    approval = json.loads(approval_bytes)
    review = json.loads(review_bytes)
    if validate_schema_value(
        approval, load_json(APPROVAL_SCHEMA, "esquema de aprovação probatória")
    ):
        raise EvidenceMatrixPromotionError("registro de aprovação inválido")
    if not approval["reviewer_name"].strip() or not approval["reviewer_role"].strip():
        raise EvidenceMatrixPromotionError("identificação ou função do revisor ausente")
    approved_at = datetime.fromisoformat(approval["approved_at"].replace("Z", "+00:00"))
    reviewed_at = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    if approved_at <= reviewed_at:
        raise EvidenceMatrixPromotionError("aprovação não sucede a revisão do inventário")
    if (
        approval["candidate_matrix_sha256"] != _sha256(matrix_bytes)
        or approval["provenance_sha256"] != _sha256(provenance_bytes)
        or approval["source_pdf_sha256"] != provenance["source_pdf_sha256"]
        or approval["review_sha256"] != _sha256(review_bytes)
        or approval["acknowledged_uncovered_claim_ids"] != matrix["uncovered_claim_ids"]
    ):
        raise EvidenceMatrixPromotionError("aprovação diverge das fontes ou lacunas")
    receipt = {
        "schema_version": 1,
        "status": "declared_approval",
        "candidate_matrix_sha256": _sha256(matrix_bytes),
        "provenance_sha256": _sha256(provenance_bytes),
        "approval_sha256": _sha256(approval_bytes),
        "review_sha256": _sha256(review_bytes),
        "source_pdf_sha256": provenance["source_pdf_sha256"],
        "evidence_count": len(matrix["evidence_items"]),
        "uncovered_claim_count": len(matrix["uncovered_claim_ids"]),
    }
    if validate_schema_value(
        receipt, load_json(PROMOTION_SCHEMA, "esquema de promoção probatória")
    ):
        raise EvidenceMatrixPromotionError("recibo de promoção inválido")
    return matrix_bytes, _encode(receipt), receipt


def verify_promoted_evidence_matrix(workspace: Path) -> dict[str, int]:
    """Confere matriz canônica e recibo contra aprovação e fontes atuais."""
    try:
        target = _private_workspace(workspace)
        matrix_bytes, receipt_bytes, receipt = _validated_payloads(target)
        if (
            _read_private(target, CANONICAL_NAME) != matrix_bytes
            or _read_private(target, PROMOTION_NAME) != receipt_bytes
        ):
            raise EvidenceMatrixPromotionError("matriz canônica ou recibo divergente")
        return {
            "evidence_count": receipt["evidence_count"],
            "uncovered_claim_count": receipt["uncovered_claim_count"],
        }
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, EvidenceMatrixPromotionError):
            raise
        raise EvidenceMatrixPromotionError("conferência da matriz promovida recusada") from error


def promote_reviewed_evidence_matrix(workspace: Path) -> tuple[Path, Path]:
    """Publica matriz canônica e recibo somente após aprovação vinculada."""
    try:
        target = _private_workspace(workspace)
        matrix_bytes, receipt_bytes, _ = _validated_payloads(target)
        payloads = (
            (target / CANONICAL_NAME, matrix_bytes),
            (target / PROMOTION_NAME, receipt_bytes),
        )
        if any(path.exists() or path.is_symlink() for path, _ in payloads):
            raise EvidenceMatrixPromotionError("matriz canônica ou recibo já existe")
        created: list[Path] = []
        try:
            for path, content in payloads:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                created.append(path)
                with os.fdopen(descriptor, "wb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
            verify_promoted_evidence_matrix(target)
        except Exception:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            raise
        return payloads[0][0], payloads[1][0]
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, EvidenceMatrixPromotionError):
            raise
        raise EvidenceMatrixPromotionError("promoção da matriz probatória recusada") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promove ou confere matriz probatória após aprovação declarada."
    )
    parser.add_argument("action", choices=("promote", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == "promote":
            promote_reviewed_evidence_matrix(args.workspace)
        result = verify_promoted_evidence_matrix(args.workspace)
    except EvidenceMatrixPromotionError as error:
        print(f"[ERRO] Matriz probatória: {error}", file=sys.stderr)
        return 2
    print(
        f"[OK] {result['evidence_count']} prova(s) na matriz; "
        f"{result['uncovered_claim_count']} pedido(s) sem prova selecionada. "
        "A qualificação do revisor não foi autenticada pelo sistema."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
