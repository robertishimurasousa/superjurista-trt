#!/usr/bin/env python3
"""Extract source-linked claimant positions from labor pleading headings."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from build_labor_report import PositionCandidate, SourceReference


DOCUMENT_ID_PATTERN = re.compile(r"DOC-[0-9]{3,}")


class LaborPositionExtractionError(ValueError):
    """Raised when pleading pages cannot satisfy source-custody boundaries."""


@dataclass(frozen=True)
class ClaimSectionRule:
    position_id: str
    label: str
    summary: str
    headings: tuple[str, ...]


CLAIM_SECTION_RULES = (
    ClaimSectionRule(
        position_id="POS-001",
        label="unmapped_legal_aid",
        summary="Claimant requests legal-aid relief.",
        headings=("DO PEDIDO DE ASSISTENCIA JUDICIARIA GRATUITA",),
    ),
    ClaimSectionRule(
        position_id="POS-002",
        label="unmapped_joint_or_subsidiary_liability",
        summary="Claimant requests joint or subsidiary liability.",
        headings=("DA RESPONSABILIDADE SOLIDARIA SUBSIDIARIA",),
    ),
    ClaimSectionRule(
        position_id="POS-003",
        label="termination_payments",
        summary="Claimant requests termination-related payments.",
        headings=(
            "DO CONTRATO POR PRAZO DETERMINADO E DAS VERBAS RESCISORIAS",
            "DO CONTRATO POR PRAZO DETERMINADO E DAS VERBAS RECISORIAS",
            "DAS VERBAS RESCISORIAS",
        ),
    ),
    ClaimSectionRule(
        position_id="POS-004",
        label="meal_rest_interval",
        summary="Claimant requests payment for an allegedly suppressed meal interval.",
        headings=(
            "DO INTERVALO INTRAJORNADA",
            "DO INTERVALOR INTRAJORDNADA",
        ),
    ),
    ClaimSectionRule(
        position_id="POS-005",
        label="moral_damages",
        summary="Claimant requests compensation for alleged non-pecuniary harm.",
        headings=(
            "DA INDENIZACAO POR DANOS EXTRAPATRIMONIAIS",
            "DA IN DENIZACAO POR DANOS EXTRAPATRIMONIAIS",
            "DA INDENIZACAO POR DANOS MORAIS",
        ),
    ),
    ClaimSectionRule(
        position_id="POS-006",
        label="unmapped_statutory_penalty_article_467",
        summary="Claimant requests the statutory penalty under CLT article 467.",
        headings=("DA MULTA DO ART 467 DA CLT",),
    ),
    ClaimSectionRule(
        position_id="POS-007",
        label="unmapped_statutory_penalty_article_477",
        summary="Claimant requests the statutory penalty under CLT article 477.",
        headings=(
            "DA MULTA DO ART 477 8 DA CLT",
            "DA MULTA DO ART 477 PARAGRAFO 8 DA CLT",
        ),
    ),
    ClaimSectionRule(
        position_id="POS-008",
        label="attorney_fees",
        summary="Claimant requests an attorney-fee award.",
        headings=("DOS HONORARIOS ADVOCATICIOS",),
    ),
)


def normalize_heading(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.replace("º", "").replace("ª", ""))
    unaccented = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    normalized = " ".join(re.sub(r"[^A-Za-z0-9]+", " ", unaccented).upper().split())
    return re.sub(r"^[0-9]+\s+", "", normalized)


def validated_pages(page_texts: object) -> tuple[tuple[int, str], ...]:
    if not isinstance(page_texts, tuple):
        raise LaborPositionExtractionError("page_texts must be a tuple")
    pages = {}
    for value in page_texts:
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or isinstance(value[0], bool)
            or not isinstance(value[0], int)
            or value[0] < 1
            or not isinstance(value[1], str)
            or not value[1].strip()
        ):
            raise LaborPositionExtractionError("page_texts contains an invalid page")
        page_number, text = value
        if page_number in pages:
            raise LaborPositionExtractionError("page_texts contains a duplicate page")
        pages[page_number] = text
    return tuple(sorted(pages.items()))


def heading_candidates_by_page(page_texts: object) -> dict[int, set[str]]:
    """Return exact one- and two-line heading candidates for each source page."""
    headings_by_page = {}
    for page_number, text in validated_pages(page_texts):
        lines = tuple(line for line in text.splitlines() if line.strip())
        headings = {normalize_heading(line) for line in lines}
        headings.update(
            normalize_heading(f"{first} {second}")
            for first, second in zip(lines, lines[1:])
        )
        headings_by_page[page_number] = headings
    return headings_by_page


def extract_claim_positions(
    *,
    initial_document_id: str,
    page_texts: tuple[tuple[int, str], ...],
) -> tuple[PositionCandidate, ...]:
    """Extract only explicit claim section headings and keep unsupported labels visible."""
    if (
        not isinstance(initial_document_id, str)
        or DOCUMENT_ID_PATTERN.fullmatch(initial_document_id) is None
    ):
        raise LaborPositionExtractionError("initial_document_id is invalid")
    headings_by_page = heading_candidates_by_page(page_texts)
    positions = []
    for rule in CLAIM_SECTION_RULES:
        source_page = next(
            (
                page_number
                for page_number, headings in headings_by_page.items()
                if any(heading in headings for heading in rule.headings)
            ),
            None,
        )
        if source_page is None:
            continue
        positions.append(
            PositionCandidate(
                position_id=rule.position_id,
                kind="claim",
                label=rule.label,
                summary=rule.summary,
                source=SourceReference(
                    document_id=initial_document_id,
                    locator=f"page {source_page}, claim section heading",
                ),
            )
        )
    return tuple(positions)
