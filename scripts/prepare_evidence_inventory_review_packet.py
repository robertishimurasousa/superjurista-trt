#!/usr/bin/env python3
"""Prepara roteiro privado de conferência sem decidir itens probatórios."""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from pathlib import Path

from prepare_evidence_inventory_packets import INDEX_NAME
from review_evidence_inventory import REVIEW_NAME, ROOT, _read_json, _source_template


PACKET_NAME = "evidence-inventory-review-packet.md"


class EvidenceInventoryReviewPacketError(ValueError):
    """Indica fonte divergente ou impossibilidade de publicar o roteiro."""


def _fenced(text: str) -> list[str]:
    """Isola texto de origem sem interpretá-lo como instrução Markdown."""
    longest = max((len(match.group()) for match in re.finditer(r"~+", text)), default=0)
    fence = "~" * max(3, longest + 1)
    return [f"{fence}text", text, fence]


def _packet(review: dict, claims: dict, source_pdf_name: str) -> str:
    lines = [
        "# Roteiro protegido de revisão do inventário probatório",
        "",
        "Este roteiro orienta a conferência e não substitui a leitura do PDF original.",
        "As observações são sugestões do inventariador, não fatos ou provas aceitos.",
        "Preencha as decisões somente em `evidence-inventory-review.json`; este roteiro",
        "não é formulário de aprovação nem autentica a identidade do revisor.",
        "",
        "Arquivo PDF do caso:",
        *_fenced(source_pdf_name),
        f"SHA-256 do PDF original: `{review['source_pdf_sha256']}`",
        "",
        "## Pedidos para consulta",
        "",
    ]
    for claim in claims["claims"]:
        lines.extend((
            f"### {claim['claim_id']}",
            "",
            "Rótulo e alegação estruturada; confira as fontes antes de usar:",
            *_fenced(f"{claim['label']} — {claim['claimant_position']['summary']}"),
            "",
        ))
    lines.extend(("## Conferência por documento", ""))
    items_by_document: dict[str, list[dict]] = {}
    for item in review["items"]:
        items_by_document.setdefault(item["source_document_id"], []).append(item)
    for document in review["documents"]:
        document_id = document["document_id"]
        lines.extend((
            f"### {document_id} — páginas {document['page_start']}–{document['page_end']}",
            "",
            "- [ ] Conferi todas as páginas no PDF original, inclusive elementos visuais.",
            "- [ ] Registrei omissões em `missing_item_note` e ressalvas em `notes`.",
            f"Estado do inventário: `{document['inventory_status']}`; "
            f"cobertura: `{document['coverage_status']}`.",
            "",
        ))
        for limitation in document["inventory_limitations"]:
            lines.extend(("Limitação informada pelo inventariador:", *_fenced(limitation), ""))
        document_items = items_by_document.get(document_id, [])
        if not document_items:
            lines.extend((
                "Nenhum item foi identificado automaticamente neste documento.",
                "Confirme no PDF; não marque a página como lida sem essa conferência.",
                "",
            ))
        for item in document_items:
            proposed_claims = ", ".join(item["proposed_claim_ids"]) or "nenhum"
            lines.extend((
                f"#### {item['item_id']} — página {item['pdf_page']}",
                "",
                f"Tipo sugerido: `{item['source_type']}`. Pedidos sugeridos: {proposed_claims}.",
                "- [ ] Comparei o trecho com a página e seu contexto visual.",
                "- [ ] Decidi `include`, `exclude` ou `defer` no registro JSON, com justificativa.",
                "- [ ] Selecionei tipo, pedidos, relação e proposição apenas se `include`.",
                "Trecho extraído para localização; o PDF prevalece:",
                *_fenced(item["excerpt"]),
                "",
                "Descrição sugerida pelo inventariador:",
                *_fenced(item["description"]),
                "",
            ))
            for limitation in item["source_limitations"]:
                lines.extend(("Limitação informada pelo inventariador:", *_fenced(limitation), ""))
    lines.extend((
        "## Encerramento da revisão",
        "",
        "- [ ] Identificação e data foram declaradas no JSON por revisor qualificado.",
        "- [ ] Todos os documentos foram conferidos e todos os itens receberam decisão.",
        "- [ ] Executei `review_evidence_inventory.py validate` e tratei toda pendência.",
        "",
    ))
    return "\n".join(lines)


def prepare_evidence_inventory_review_packet(workspace: Path) -> Path:
    """Publica roteiro somente para a revisão inicial ainda sem alterações."""
    try:
        if not isinstance(workspace, Path) or workspace.is_symlink() or not workspace.is_dir():
            raise EvidenceInventoryReviewPacketError("espaço de trabalho inválido")
        workspace = workspace.resolve()
        if workspace == ROOT or workspace.is_relative_to(ROOT):
            raise EvidenceInventoryReviewPacketError("o roteiro não pode entrar no repositório")
        if stat.S_IMODE(workspace.stat().st_mode) & 0o077:
            raise EvidenceInventoryReviewPacketError("espaço de trabalho deve ser privado")
        expected, _ = _source_template(workspace)
        review = _read_json(workspace, REVIEW_NAME)
        if review != expected:
            raise EvidenceInventoryReviewPacketError(
                "o registro já foi alterado ou diverge das fontes"
            )
        claims = _read_json(workspace, "claim-matrix.json")
        index = _read_json(workspace, INDEX_NAME)
        content = _packet(review, claims, index["source_pdf_name"]).encode("utf-8")
        path = workspace / PACKET_NAME
        if path.exists() or path.is_symlink():
            raise EvidenceInventoryReviewPacketError("roteiro já existe; arquivo preservado")
        created = False
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
        except OSError:
            if created:
                path.unlink(missing_ok=True)
            raise
        return path
    except (OSError, TypeError, ValueError, KeyError, UnicodeError, IndexError) as error:
        if isinstance(error, EvidenceInventoryReviewPacketError):
            raise
        raise EvidenceInventoryReviewPacketError("preparo do roteiro recusado") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepara roteiro privado de revisão sem selecionar provas."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    try:
        path = prepare_evidence_inventory_review_packet(args.workspace)
        review = _read_json(path.parent, REVIEW_NAME)
    except EvidenceInventoryReviewPacketError as error:
        print(f"[ERRO] Roteiro de revisão: {error}", file=sys.stderr)
        return 2
    print(
        f"[OK] Roteiro privado para {len(review['documents'])} documento(s) e "
        f"{len(review['items'])} item(ns); nenhuma decisão jurídica registrada."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
