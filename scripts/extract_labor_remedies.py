#!/usr/bin/env python3
"""Extract source-linked requested remedies from a pleading's final prayer."""

from __future__ import annotations

import re
import unicodedata

from extract_labor_positions import validated_pages


DOCUMENT_ID = re.compile(r"DOC-[0-9]{3,}")
LETTER_ITEM = re.compile(r"^([A-Z])\.\s+(.+)$")
NUMBERED_ITEM = re.compile(r"^([0-9]+)\)\s+(.+)$")
BOILERPLATE = (
    "DOCUMENTO ASSINADO ELETRONICAMENTE",
    "FLS ",
    "AV ",
    "TELEFONE ",
)


class LaborRemedyExtractionError(ValueError):
    """Raised when the prayer cannot be mapped without unsupported assumptions."""


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", unaccented.upper()).split())


def _prayer_items(page_texts: tuple[tuple[int, str], ...]) -> list[dict]:
    items: list[dict] = []
    heading_found = False
    current: dict | None = None
    subitem: dict | None = None
    parent_appended = False
    seen = set()

    def finish_subitem() -> None:
        nonlocal subitem
        if subitem is not None:
            items.append(subitem)
            subitem = None

    def finish_item() -> None:
        nonlocal current, parent_appended
        finish_subitem()
        if current is not None and not parent_appended:
            items.append(current)
        current = None
        parent_appended = False

    for page_number, page_text in validated_pages(page_texts):
        for raw_line in page_text.splitlines():
            line = " ".join(raw_line.split())
            if not line or line.startswith("_"):
                continue
            normalized = _normalize(line)
            if any(normalized.startswith(prefix) for prefix in BOILERPLATE):
                continue
            if not heading_found:
                if re.fullmatch(r"(?:[0-9]+ )?DOS PEDIDOS", normalized):
                    heading_found = True
                continue
            letter_match = LETTER_ITEM.fullmatch(line)
            if letter_match:
                finish_item()
                request_id = letter_match.group(1)
                if request_id in seen:
                    raise LaborRemedyExtractionError("duplicate prayer request identifier")
                seen.add(request_id)
                current = {
                    "request_id": request_id,
                    "page": page_number,
                    "lines": [letter_match.group(2)],
                }
                continue
            number_match = NUMBERED_ITEM.fullmatch(line)
            if number_match and current is not None:
                if not parent_appended:
                    items.append(current)
                    parent_appended = True
                finish_subitem()
                request_id = f"{current['request_id']}.{number_match.group(1)}"
                if request_id in seen:
                    raise LaborRemedyExtractionError("duplicate prayer request identifier")
                seen.add(request_id)
                subitem = {
                    "request_id": request_id,
                    "page": page_number,
                    "lines": [number_match.group(2)],
                }
                continue
            if subitem is not None:
                subitem["lines"].append(line)
            elif current is not None:
                current["lines"].append(line)
    finish_item()
    if not heading_found:
        raise LaborRemedyExtractionError("final prayer heading is missing")
    if not items:
        raise LaborRemedyExtractionError("final prayer has no lettered requests")
    return items


def _claim_label(text: str) -> str | None:
    checks = (
        ("unmapped_legal_aid", "GRATUIDADE DE JUSTICA" in text),
        ("unmapped_joint_or_subsidiary_liability", "RESPONSABILIDADE SOLIDARIA" in text),
        (
            "termination_payments",
            "CONTRATO" in text
            and "PRAZO INDETERMINADO" in text
            and "DISPENSA SEM JUSTA CAUSA" in text,
        ),
        ("meal_rest_interval", "INTERVALO INTRAJORNADA" in text),
        ("moral_damages", "DANOS MORAIS" in text),
        ("unmapped_statutory_penalty_article_467", "PARCELAS INCONTROVERSAS" in text),
        ("unmapped_statutory_penalty_article_477", "ARTIGO 477" in text),
        (
            "attorney_fees",
            re.search(r"HONORARIOS (?:DE )?ADVOCATICIOS", text) is not None
            and (
                re.search(r"PAGAMENTO (?:DE|DOS) HONORARIOS", text) is not None
                or "ARTIGO 791" in text
            ),
        ),
    )
    matches = [label for label, matched in checks if matched]
    if len(matches) > 1:
        raise LaborRemedyExtractionError("prayer item matches multiple claim labels")
    return matches[0] if matches else None


def _remedies_for_item(label: str, text: str) -> tuple[list[str], list[str]]:
    if label == "unmapped_legal_aid":
        return ["legal_aid"], []
    if label == "unmapped_joint_or_subsidiary_liability":
        return ["joint_or_subsidiary_liability"], ["conditional_alternative"]
    if label == "termination_payments":
        return ["recognition_of_indefinite_term", "recognition_of_dismissal_without_cause"], []
    if label == "meal_rest_interval":
        remedies = ["interval_payment"]
        if "REFLEXOS" in text:
            remedies.append("statutory_effects")
        return remedies, []
    if label == "moral_damages":
        return ["compensation"], []
    if label == "unmapped_statutory_penalty_article_467":
        return ["article_467_penalty"], []
    if label == "unmapped_statutory_penalty_article_477":
        return ["article_477_penalty"], []
    if label == "attorney_fees":
        return ["attorney_fee_award"], []
    raise LaborRemedyExtractionError("unsupported claim label in prayer")


def _termination_subitem(text: str) -> tuple[list[str], list[str]]:
    rules = (
        (
            "INDENIZACAO SUBSTITUTIVA" in text and "SEGURO DESEMPREGO" in text,
            ["unemployment_insurance_documents", "substitute_unemployment_insurance_compensation"],
            ["conditional_alternative"],
        ),
        (
            "GUIAS" in text and "FGTS" in text and "SEGURO DESEMPREGO" in text,
            ["fgts_withdrawal_documents", "unemployment_insurance_documents"],
            [],
        ),
        ("SALDO DE SALARIO" in text, ["accrued_salary"], []),
        ("AVISO PREVIO" in text, ["notice_pay"], []),
        ("DESCANSO SEMANAL REMUNERADO" in text, ["weekly_paid_rest"], []),
        (re.search(r"\b13O? SALARIO\b", text) is not None, ["thirteenth_salary"], []),
        ("FERIAS PROPORCIONAIS" in text, ["proportional_vacation"], []),
        (
            "FGTS" in text and "MULTA DE 40" in text,
            ["fgts_deposit", "fgts_40_percent_penalty"],
            [],
        ),
    )
    matches = [(codes, gaps) for matched, codes, gaps in rules if matched]
    if not matches:
        raise LaborRemedyExtractionError("unrecognized termination-payment subitem")
    if len(matches) > 1:
        raise LaborRemedyExtractionError("ambiguous termination-payment subitem")
    return matches[0]


def extract_requested_remedies(
    page_texts: tuple[tuple[int, str], ...],
    document_id: str,
    claim_ids_by_label: dict[str, str],
) -> dict:
    """Keep exact prayer excerpts and page locators; never guess an unknown subitem."""
    if not isinstance(document_id, str) or DOCUMENT_ID.fullmatch(document_id) is None:
        raise LaborRemedyExtractionError("initial document identifier is invalid")
    if not isinstance(claim_ids_by_label, dict):
        raise LaborRemedyExtractionError("claim label map is invalid")
    entries = []
    unmatched = []
    parent_label = None
    for item in _prayer_items(page_texts):
        request_id = item["request_id"]
        text = " ".join(item["lines"])
        normalized = _normalize(text)
        if "." in request_id:
            if parent_label != "termination_payments":
                raise LaborRemedyExtractionError("unrecognized numbered prayer subitem")
            label = parent_label
            remedies, gaps = _termination_subitem(normalized)
        else:
            label = _claim_label(normalized)
            parent_label = label
            if label is None:
                unmatched.append(request_id)
                continue
            remedies, gaps = _remedies_for_item(label, normalized)
        claim_id = claim_ids_by_label.get(label)
        if claim_id is None:
            raise LaborRemedyExtractionError("prayer claim label is absent from labor report")
        entries.append(
            {
                "request_id": request_id,
                "claim_id": claim_id,
                "remedy_codes": remedies,
                "source_document_id": document_id,
                "source_locator": f"page {item['page']}, request {request_id}",
                "text": text,
                "review_gaps": gaps,
            }
        )
    return {"entries": entries, "unmatched_item_ids": unmatched}
