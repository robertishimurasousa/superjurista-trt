#!/usr/bin/env python3
"""Extract source-linked respondent positions from labor defense headings."""

from __future__ import annotations

from dataclasses import dataclass

from build_labor_report import PositionCandidate, SourceReference
from extract_labor_positions import (
    DOCUMENT_ID_PATTERN,
    heading_candidates_by_page,
)


class LaborDefenseExtractionError(ValueError):
    """Raised when defense pages cannot satisfy source-custody boundaries."""


@dataclass(frozen=True)
class DefenseSectionRule:
    slot: int
    label: str
    summary: str
    headings: tuple[str, ...]


DEFENSE_SECTION_RULES = (
    DefenseSectionRule(
        slot=1,
        label="termination_payments",
        summary="Respondent contests the requested termination-related payments.",
        headings=("DAS VERBAS RESCISORIAS",),
    ),
    DefenseSectionRule(
        slot=2,
        label="meal_rest_interval",
        summary="Respondent contests the requested meal-interval payment.",
        headings=("DO INTERVALO INTRAJORNADA",),
    ),
    DefenseSectionRule(
        slot=3,
        label="moral_damages",
        summary="Respondent contests the alleged non-pecuniary harm and compensation.",
        headings=("DO DANO MORAL",),
    ),
    DefenseSectionRule(
        slot=4,
        label="unmapped_statutory_penalty_article_467",
        summary="Respondent contests the statutory penalty under CLT article 467.",
        headings=("DA MULTA DO ARTIGO 467 E 477 DA CLT",),
    ),
    DefenseSectionRule(
        slot=5,
        label="unmapped_statutory_penalty_article_477",
        summary="Respondent contests the statutory penalty under CLT article 477.",
        headings=("DA MULTA DO ARTIGO 467 E 477 DA CLT",),
    ),
    DefenseSectionRule(
        slot=6,
        label="unmapped_legal_aid",
        summary="Respondent contests eligibility for legal-aid relief.",
        headings=("DA JUSTICA GRATUITA",),
    ),
    DefenseSectionRule(
        slot=7,
        label="attorney_fees",
        summary="Respondent contests the claimant's requested attorney-fee award.",
        headings=(
            "DOS HONORARIOS DE SUCUMBENCIA EM FAVOR DO PROCURADOR DO DEMANDANTE",
        ),
    ),
)


def extract_defense_positions(
    *,
    defense_document_id: str,
    page_texts: tuple[tuple[int, str], ...],
    position_group: int,
) -> tuple[PositionCandidate, ...]:
    """Extract explicit defense headings without inferring an absent answer."""
    if (
        not isinstance(defense_document_id, str)
        or DOCUMENT_ID_PATTERN.fullmatch(defense_document_id) is None
    ):
        raise LaborDefenseExtractionError("defense_document_id is invalid")
    if (
        isinstance(position_group, bool)
        or not isinstance(position_group, int)
        or position_group < 1
    ):
        raise LaborDefenseExtractionError("position_group is invalid")
    try:
        headings_by_page = heading_candidates_by_page(page_texts)
    except ValueError as error:
        raise LaborDefenseExtractionError(str(error)) from error

    positions = []
    for rule in DEFENSE_SECTION_RULES:
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
                position_id=f"POS-{position_group * 100 + rule.slot:03d}",
                kind="defense",
                label=rule.label,
                summary=rule.summary,
                source=SourceReference(
                    document_id=defense_document_id,
                    locator=f"page {source_page}, defense section heading",
                ),
            )
        )
    return tuple(positions)
