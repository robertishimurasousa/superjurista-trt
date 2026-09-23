#!/usr/bin/env python3
"""Prepare a protected, source-only claim inventory form for independent review."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

from PyPDF2 import PdfReader

from schema_validation import load_json
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
SEGMENT_SCHEMA = ROOT / "runtime/providers/pje-pdf-segments.v1.schema.json"
CASE_ID = re.compile(r"[A-Z][A-Z0-9_-]{2,63}")
DOCUMENT_ID = re.compile(r"DOC-[0-9]{3,}")


class BlindReviewPacketError(ValueError):
    """Raised when the source or protected output cannot satisfy review boundaries."""


def prepare_review_packet(
    pdf_path: Path, segments: dict, *, document_id: str, case_id: str
) -> str:
    """Build a review packet without consulting system claim predictions."""
    if not isinstance(case_id, str) or CASE_ID.fullmatch(case_id) is None:
        raise BlindReviewPacketError("case ID must be pseudonymous")
    if not isinstance(document_id, str) or DOCUMENT_ID.fullmatch(document_id) is None:
        raise BlindReviewPacketError("source document identifier is invalid")
    issues = validate_document(segments, load_json(SEGMENT_SCHEMA, "PDF segment schema"))
    if issues:
        raise BlindReviewPacketError(f"PDF segment contract failed: {issues[0]}")
    documents = {item["document_id"]: item for item in segments["documents"]}
    if len(documents) != len(segments["documents"]):
        raise BlindReviewPacketError("source document identifiers must be unique")
    document = documents.get(document_id)
    if document is None:
        raise BlindReviewPacketError("source document is absent from segment map")

    source = pdf_path.resolve()
    if not source.is_file():
        raise BlindReviewPacketError("source PDF does not exist")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    reader = PdfReader(str(source))
    page_count = len(reader.pages)
    pdf_custody = segments["source_pdf"]
    if digest != pdf_custody["sha256"] or page_count != pdf_custody["page_count"]:
        raise BlindReviewPacketError("PDF custody does not match segment map")
    start, end = document["page_start"], document["page_end"]
    if start > end or end > page_count:
        raise BlindReviewPacketError("source document page range is invalid")

    return f"""# Inventário independente de pedidos - {case_id}

Este formulário é para leitura humana do PDF original. Preencha-o **sem consultar a matriz,
o relatório de posições ou as evidências geradas pelo sistema**. Ele não contém uma lista
prévia de pedidos nem sugere categorias ou resultados.

## Identificação e custódia

- Caso pseudônimo: {case_id}
- Documento-fonte: {document_id}, páginas {start}-{end} do PDF consolidado
- SHA-256 do PDF: {digest}
- Revisor(a): [preencher]
- Data da revisão: [preencher]

## Instruções

1. Leia todas as páginas indicadas no PDF original, inclusive a lista final de pedidos.
2. Registre cada pedido material e cada subitem que contenha providência ou parcela distinta.
3. Anote alternativas, condições, pedidos acessórios e pedidos sem valor definido.
4. Use palavras próprias; não copie nomes, contatos, credenciais ou dados pessoais para este formulário.
5. Se não puder decidir se um item é pedido material, registre a dúvida, sem omiti-lo.
6. Congele e date este inventário antes de abrir qualquer saída do sistema.
7. Se já viu a matriz, seus rótulos ou suas contagens, não declare esta revisão cega;
   encaminhe o PDF e este formulário a outro revisor ainda não exposto.

## Inventário de pedidos materiais

Copie a linha abaixo quantas vezes forem necessárias. Não há quantidade predefinida.

| ID do revisor | Pedido/questão | Providência ou parcela requerida | Página | Marcador na petição | Alternativa/condição | Dúvida |
|---|---|---|---|---|---|---|
| [preencher] | [preencher] | [preencher] | [preencher] | [preencher] | [preencher] | [preencher] |

## Pedidos acessórios ou procedimentais

| ID do revisor | Descrição | Página | Marcador na petição | Dúvida |
|---|---|---|---|---|
| [preencher] | [preencher] | [preencher] | [preencher] | [preencher] |

## Verificação antes da comparação

- [ ] Examinei todas as páginas {start}-{end} e registrei também as dúvidas e alternativas.
- [ ] Não consultei a matriz ou os rótulos extraídos pelo sistema antes de concluir esta leitura.
- [ ] Inventário congelado em: [preencher data/hora]
- [ ] Identificação do revisor: [preencher]

Depois de congelar o inventário, salve uma cópia preenchida em local protegido.
Somente então compare-a com a matriz do sistema; este formulário em branco não é aprovação jurídica.
"""


def write_review_packet(
    packet: str, *, output_dir: Path, repository_root: Path
) -> Path:
    """Write the protected form without overwriting existing work."""
    destination = output_dir.resolve()
    repository = repository_root.resolve()
    if destination == repository or repository in destination.parents:
        raise BlindReviewPacketError("review output must stay outside repository")
    if not destination.is_dir():
        raise BlindReviewPacketError("review output directory must already exist")
    path = destination / "independent-claim-review.md"
    if path.exists():
        raise BlindReviewPacketError("review output already exists")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(packet)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a protected, source-only independent claim review form."
    )
    parser.add_argument("--input", required=True, type=Path, help="Original consolidated PDF")
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--case-id", required=True, help="Pseudonym, never the CNJ case number")
    parser.add_argument("--output", required=True, type=Path, help="Existing protected directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        segments = load_json(args.segments, "PDF segments")
        packet = prepare_review_packet(
            args.input, segments, document_id=args.document_id, case_id=args.case_id
        )
        write_review_packet(packet, output_dir=args.output, repository_root=ROOT)
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"[ERROR] independent claim review: {error}", file=sys.stderr)
        return 1
    print("[OK] independent claim review: blank protected form created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
