#!/usr/bin/env python3
"""Segment one PJe consolidated PDF through its native outline destinations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from PyPDF2 import PdfReader

from classify_labor_documents import (
    DocumentCandidate,
    classify_documents,
    load_classification_contract,
)
from schema_validation import load_json, validate_schema_value


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSIFICATION_CONTRACT = (
    ROOT / "runtime" / "domain" / "labor-document-classification.json"
)
DEFAULT_SEGMENT_SCHEMA = ROOT / "runtime" / "providers" / "pje-pdf-segments.v1.schema.json"
DEFAULT_CLASSIFICATION_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "document-classification.v2.schema.json"
)


OUTLINE_TITLE = re.compile(
    r"^\s*(?P<sequence>[0-9]+)\.\s+"
    r"(?P<filed_on>[0-9]{2}/[0-9]{2}/[0-9]{4})\s+-\s+"
    r"(?P<provider_type>.+)\s+-\s+"
    r"(?P<provider_reference>[0-9a-fA-F]{7})\s*$"
)


class PJePdfSegmentationError(ValueError):
    """Raised when the PDF cannot produce a complete deterministic document map."""


@dataclass(frozen=True)
class PJePdfClassificationResult:
    segments: dict
    classification: dict


def _outline_destinations(items: list) -> Iterator[object]:
    for item in items:
        if isinstance(item, list):
            yield from _outline_destinations(item)
        else:
            yield item


def _parse_outline_title(title: object) -> dict:
    if not isinstance(title, str):
        raise PJePdfSegmentationError("o título do marcador do sumário deve ser texto")
    match = OUTLINE_TITLE.fullmatch(title)
    if match is None:
        raise PJePdfSegmentationError("o título do marcador do sumário é inválido")
    try:
        filed_on = datetime.strptime(match.group("filed_on"), "%d/%m/%Y").date()
    except ValueError as error:
        raise PJePdfSegmentationError("a data do marcador do sumário é inválida") from error
    return {
        "sequence": int(match.group("sequence")),
        "provider_reference": match.group("provider_reference").lower(),
        "provider_type": match.group("provider_type").strip(),
        "filed_on": filed_on.isoformat(),
    }


def segment_pje_pdf(pdf_path: Path) -> dict:
    """Return stable document page ranges without extracting source text."""
    source = pdf_path.resolve()
    if not source.is_file():
        raise PJePdfSegmentationError("PDF do PJe não encontrado")

    reader = PdfReader(str(source))
    page_count = len(reader.pages)
    if page_count < 1:
        raise PJePdfSegmentationError("o PDF do PJe não contém páginas")

    destinations = list(_outline_destinations(reader.outline))
    if not destinations:
        raise PJePdfSegmentationError("o sumário de marcadores do PDF do PJe está ausente")
    parsed = []
    for destination in destinations:
        item = _parse_outline_title(getattr(destination, "title", None))
        item["page_start"] = reader.get_destination_page_number(destination) + 1
        parsed.append(item)

    starts = [item["page_start"] for item in parsed]
    expected_sequences = list(range(1, len(parsed) + 1))
    if [item["sequence"] for item in parsed] != expected_sequences:
        raise PJePdfSegmentationError("a sequência do sumário de marcadores não é contínua")
    if starts[0] != 1 or any(left >= right for left, right in zip(starts, starts[1:])):
        raise PJePdfSegmentationError("as páginas do sumário se sobrepõem ou estão incompletas")
    references = [item["provider_reference"] for item in parsed]
    if len(references) != len(set(references)):
        raise PJePdfSegmentationError("as referências do sumário devem ser únicas")

    documents = []
    for index, item in enumerate(parsed):
        page_end = starts[index + 1] - 1 if index + 1 < len(starts) else page_count
        documents.append(
            {
                "document_id": f"DOC-{item['sequence']:03d}",
                "provider_reference": item["provider_reference"],
                "provider_type": item["provider_type"],
                "filed_on": item["filed_on"],
                "page_start": item["page_start"],
                "page_end": page_end,
            }
        )

    return {
        "schema_version": 1,
        "segmentation_method": "pje_pdf_outline",
        "source_pdf": {
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "page_count": page_count,
        },
        "documents": documents,
    }


def _validate_artifact(value: dict, schema_path: Path, label: str) -> None:
    schema = load_json(schema_path, f"esquema de {label}")
    issues = validate_schema_value(value, schema)
    if issues:
        raise PJePdfSegmentationError(f"contrato inválido de {label}: {'; '.join(issues)}")


def classify_pje_pdf(
    pdf_path: Path,
    *,
    classification_contract_path: Path,
    segment_schema_path: Path,
    classification_schema_path: Path,
) -> PJePdfClassificationResult:
    """Segment and classify a PJe PDF without copying source metadata into classification."""
    segments = segment_pje_pdf(pdf_path)
    _validate_artifact(segments, segment_schema_path, "segmentos do PDF do PJe")
    contract = load_classification_contract(classification_contract_path)
    candidates = tuple(
        DocumentCandidate(
            document_id=item["document_id"],
            provider_type=item["provider_type"],
            title="",
            text_excerpt="",
        )
        for item in segments["documents"]
    )
    classification = classify_documents(contract, candidates)
    _validate_artifact(
        classification,
        classification_schema_path,
        "classificação documental",
    )
    return PJePdfClassificationResult(
        segments=segments,
        classification=classification,
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def write_classification_artifacts(
    result: PJePdfClassificationResult,
    *,
    output_dir: Path,
    repository_root: Path,
) -> tuple[Path, Path]:
    """Write protected local artifacts without allowing repository-local case data."""
    destination = output_dir.resolve()
    repository = repository_root.resolve()
    if destination == repository or _is_within(destination, repository):
        raise PJePdfSegmentationError("a saída da classificação deve ficar fora do repositório")
    if not destination.is_dir():
        raise PJePdfSegmentationError("o diretório de saída da classificação deve existir")

    artifacts = (
        (destination / "document-segments.json", result.segments),
        (destination / "document-classification.json", result.classification),
    )
    if any(path.exists() for path, _ in artifacts):
        raise PJePdfSegmentationError("a saída da classificação já existe")

    written = []
    try:
        for path, value in artifacts:
            payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            written.append(path)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
    except (OSError, UnicodeError, TypeError, ValueError):
        for path in reversed(written):
            path.unlink(missing_ok=True)
        raise
    return tuple(written)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Segmenta e classifica um PDF consolidado do PJe autorizado.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument(
        "--classification-contract",
        type=Path,
        default=DEFAULT_CLASSIFICATION_CONTRACT,
    )
    parser.add_argument("--segment-schema", type=Path, default=DEFAULT_SEGMENT_SCHEMA)
    parser.add_argument(
        "--classification-schema",
        type=Path,
        default=DEFAULT_CLASSIFICATION_SCHEMA,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = classify_pje_pdf(
            args.input,
            classification_contract_path=args.classification_contract,
            segment_schema_path=args.segment_schema,
            classification_schema_path=args.classification_schema,
        )
        write_classification_artifacts(
            result,
            output_dir=args.output,
            repository_root=args.repository_root,
        )
    except (OSError, PJePdfSegmentationError, ValueError) as error:
        print(f"[ERRO] Classificação do PDF do PJe: {error}", file=sys.stderr)
        return 1

    statuses = [
        item["classification_status"]
        for item in result.classification["documents"]
    ]
    print(
        "[OK] Classificação do PDF do PJe: "
        f"documentos={len(statuses)} "
        f"classificados={statuses.count('classified')} "
        f"desconhecidos={statuses.count('unknown')} "
        f"conflitos={statuses.count('conflict')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
