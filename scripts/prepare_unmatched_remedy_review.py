#!/usr/bin/env python3
"""Prepara conferência protegida dos itens finais sem associação."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from PyPDF2 import PdfReader

from schema_validation import ContractError, load_json, validate_schema_value
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
PACKET_NAME = "unmatched-remedy-review.md"
RECORD_NAME = "unmatched-remedy-review.json"
EVIDENCE_SCHEMA = ROOT / "runtime/contracts/schemas/requested-remedy-evidence.v2.schema.json"
REVIEW_SCHEMA = ROOT / "runtime/operations/unmatched-remedy-review.v1.schema.json"
PAGE_LOCATOR = re.compile(r"página ([0-9]+), pedido [A-Z]")


class UnmatchedRemedyReviewError(ValueError):
    """Indica que o roteiro não pode ser publicado."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise UnmatchedRemedyReviewError(f"{label} ausente ou vínculo simbólico")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise UnmatchedRemedyReviewError(f"{label} deve ser privado")


def _fenced(text: str) -> list[str]:
    longest = max((len(match.group()) for match in re.finditer(r"~+", text)), default=0)
    fence = "~" * max(3, longest + 1)
    return [f"{fence}text", text, fence]


def current_review_sources(workspace: Path, pdf_path: Path) -> tuple[dict, dict]:
    """Confere fontes privadas e monta o registro esperado, sem publicá-lo."""
    if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
        raise UnmatchedRemedyReviewError("espaço de revisão inválido")
    workspace = workspace.resolve()
    if workspace == ROOT or workspace.is_relative_to(ROOT):
        raise UnmatchedRemedyReviewError("a revisão não pode entrar no repositório")
    if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
        raise UnmatchedRemedyReviewError("espaço de revisão deve ser privado")
    evidence_path = workspace / "requested-remedy-evidence.json"
    blind_path = workspace / "independent-claim-review.md"
    _private_file(evidence_path, "evidência das providências")
    _private_file(blind_path, "inventário cego")
    if not isinstance(pdf_path, Path) or pdf_path.is_symlink() or not pdf_path.is_file():
        raise UnmatchedRemedyReviewError("PDF original ausente ou vínculo simbólico")
    evidence = load_json(evidence_path, "evidência das providências")
    if validate_document(evidence, load_json(EVIDENCE_SCHEMA, "esquema das providências")):
        raise UnmatchedRemedyReviewError("evidência das providências inválida")
    if not evidence["unmatched_items"]:
        raise UnmatchedRemedyReviewError("evidência não contém itens sem associação")
    pdf_digest = _digest(pdf_path)
    if pdf_digest != evidence["source_pdf_sha256"]:
        raise UnmatchedRemedyReviewError("PDF original diverge da evidência")
    blind = blind_path.read_text(encoding="utf-8")
    if (
        "# Inventário independente de pedidos" not in blind
        or f"- SHA-256 do PDF: {pdf_digest}" not in blind
        or "Inventário congelado em:" not in blind
        or "[preencher]" in blind
        or "- [ ]" in blind
        or blind.count("- [x]") < 3
    ):
        raise UnmatchedRemedyReviewError("inventário cego não está preenchido e congelado")
    page_count = len(PdfReader(str(pdf_path.resolve())).pages)
    for item in evidence["unmatched_items"]:
        match = PAGE_LOCATOR.fullmatch(item["source_locator"])
        if match is None or not 1 <= int(match.group(1)) <= page_count:
            raise UnmatchedRemedyReviewError("página do item fora do PDF original")
    review = {
        "schema_version": 1,
        "source_pdf_sha256": pdf_digest,
        "evidence_sha256": _digest(evidence_path),
        "blind_inventory_sha256": _digest(blind_path),
        "reviewer_name": "",
        "reviewed_at": "",
        "blind_inventory_frozen": False,
        "original_pdf_checked": False,
        "authorizes_external_action": False,
        "items": [
            {
                "request_id": item["request_id"],
                "source_document_id": item["source_document_id"],
                "source_locator": item["source_locator"],
                "text_sha256": hashlib.sha256(item["text"].encode("utf-8")).hexdigest(),
                "decision": "pending",
                "reason": "",
            }
            for item in evidence["unmatched_items"]
        ],
    }
    if validate_schema_value(review, load_json(REVIEW_SCHEMA, "esquema da revisão")):
        raise UnmatchedRemedyReviewError("registro pendente da revisão inválido")
    return evidence, review


def prepare_unmatched_remedy_review(workspace: Path, pdf_path: Path) -> tuple[Path, Path]:
    """Publica roteiro e decisões pendentes sem associar itens a pedidos."""
    evidence, review = current_review_sources(workspace, pdf_path)
    workspace = workspace.resolve()
    lines = [
        "# Conferência dos itens sem associação",
        "",
        "Este roteiro não constitui aprovação jurídica nem autoriza ato externo.",
        "Compare cada trecho com o PDF original e com o inventário cego congelado.",
        f"SHA-256 do PDF original: `{review['source_pdf_sha256']}`",
        "",
    ]
    for item in evidence["unmatched_items"]:
        lines.extend((
            f"## Item {item['request_id']}",
            f"Fonte: {item['source_document_id']}, {item['source_locator']}",
            "Trecho extraído para localização; o PDF original prevalece:",
            *_fenced(item["text"]),
            "",
            "Decisão e justificativa: preencher no registro JSON, sem inferência automática.",
            "",
        ))
    packet = workspace / PACKET_NAME
    record = workspace / RECORD_NAME
    if any(path.exists() or path.is_symlink() for path in (packet, record)):
        raise UnmatchedRemedyReviewError("roteiro ou registro já existe; arquivos preservados")
    outputs = (
        (packet, "\n".join(lines).encode("utf-8")),
        (record, (json.dumps(review, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
    )
    written = []
    try:
        for path, content in outputs:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            written.append(path)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
    except OSError as error:
        for path in written:
            path.unlink(missing_ok=True)
        raise UnmatchedRemedyReviewError("publicação protegida da revisão recusada") from error
    return packet, record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepara conferência protegida dos itens da petição sem associação."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    args = parser.parse_args()
    try:
        _, record = prepare_unmatched_remedy_review(args.workspace, args.pdf)
        review = load_json(record, "registro da revisão")
    except (UnmatchedRemedyReviewError, ContractError, OSError, ValueError,
            TypeError, UnicodeError, KeyError) as error:
        detail = (
            str(error) if isinstance(error, UnmatchedRemedyReviewError)
            else "não foi possível preparar o roteiro protegido"
        )
        print(f"[ERRO] Conferência dos itens sem associação: {detail}", file=sys.stderr)
        return 2
    print(
        f"[OK] Roteiro protegido para {len(review['items'])} item(ns) criado; "
        "todas as decisões continuam pendentes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
