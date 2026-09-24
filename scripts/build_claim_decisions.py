#!/usr/bin/env python3
"""Build linked claim analyses, dispositions, and a deterministic draft."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple


CLAIM_ID_PATTERN = re.compile(r"CLM-[0-9]{3,}")
ANALYSIS_ID_PATTERN = re.compile(r"ANL-[0-9]{3,}")
EVIDENCE_ID_PATTERN = re.compile(r"EVD-[0-9]{3,}")
DISPOSITION_ID_PATTERN = re.compile(r"DSP-[0-9]{3,}")
SOURCE_ID_PATTERN = re.compile(r"[A-Z0-9]+-[0-9]{3,}")
OUTCOME_LABELS = {
    "granted": "procedente",
    "denied": "improcedente",
    "granted_in_part": "parcialmente procedente",
    "dismissed_without_merits": "extinto sem resolução do mérito",
    "procedural_resolution": "resolução processual",
    "pending_human_review": "revisão humana pendente",
    "abstained": "abstenção",
}
OUTCOMES = set(OUTCOME_LABELS)
MERITS_OUTCOMES = {"granted", "denied", "granted_in_part"}
PROCEDURAL_OUTCOMES = {"dismissed_without_merits", "procedural_resolution"}
UNRESOLVED_OUTCOMES = {"pending_human_review", "abstained"}


class ClaimDecisionContractViolation(ValueError):
    """Raised when analysis or disposition coverage and linkage are invalid."""


@dataclass(frozen=True)
class ClaimAnalysisCandidate:
    analysis_id: str
    claim_id: str
    facts_found: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    evidence_assessment: Tuple[str, ...]
    applicable_rules: Tuple[str, ...]
    precedent_source_ids: Tuple[str, ...]
    reasoning: str
    proposed_outcome: str
    limitations: Tuple[str, ...]


@dataclass(frozen=True)
class DispositionCandidate:
    disposition_id: str
    claim_id: str
    command: str
    period: str
    effects: Tuple[str, ...]
    calculation_criteria: Tuple[str, ...]
    source_analysis_id: str


def _require_identifier(value: object, pattern: re.Pattern, label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ClaimDecisionContractViolation(f"{label} is invalid")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClaimDecisionContractViolation(f"{label} must be a non-empty string")
    return value


def _require_tuple(
    value: object,
    label: str,
    *,
    pattern: re.Pattern = None,
) -> Tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ClaimDecisionContractViolation(f"{label} must be a tuple")
    for item in value:
        if pattern is None:
            _require_text(item, label)
        else:
            _require_identifier(item, pattern, label)
    if len(value) != len(set(value)):
        raise ClaimDecisionContractViolation(f"{label} values must be unique")
    return value


def _known_ids(value: object, pattern: re.Pattern, label: str, *, empty: bool) -> set:
    if not isinstance(value, tuple) or (not empty and not value):
        suffix = "a tuple" if empty else "a non-empty tuple"
        raise ClaimDecisionContractViolation(f"{label} must be {suffix}")
    for identifier in value:
        _require_identifier(identifier, pattern, label)
    if len(value) != len(set(value)):
        raise ClaimDecisionContractViolation(f"{label} values must be unique")
    return set(value)


def _require_analysis_content(candidate: ClaimAnalysisCandidate, fields: dict) -> None:
    outcome = candidate.proposed_outcome
    if outcome in MERITS_OUTCOMES:
        for field in (
            "facts_found",
            "evidence_ids",
            "evidence_assessment",
            "applicable_rules",
        ):
            if not fields[field]:
                raise ClaimDecisionContractViolation(
                    f"{outcome} outcome requires non-empty {field}"
                )
    if outcome in PROCEDURAL_OUTCOMES:
        for field in ("facts_found", "applicable_rules"):
            if not fields[field]:
                raise ClaimDecisionContractViolation(
                    f"{outcome} outcome requires non-empty {field}"
                )
    if outcome in UNRESOLVED_OUTCOMES and not fields["limitations"]:
        raise ClaimDecisionContractViolation(
            f"{outcome} outcome requires non-empty limitations"
        )


def build_claim_analysis(
    known_claim_ids: Tuple[str, ...],
    known_evidence_ids: Tuple[str, ...],
    candidates: Tuple[ClaimAnalysisCandidate, ...],
) -> dict:
    """Build exactly one evidence-aware analysis for every known claim."""
    known_claims = _known_ids(
        known_claim_ids,
        CLAIM_ID_PATTERN,
        "known_claim_ids",
        empty=False,
    )
    known_evidence = _known_ids(
        known_evidence_ids,
        EVIDENCE_ID_PATTERN,
        "known_evidence_ids",
        empty=True,
    )
    if not isinstance(candidates, tuple):
        raise ClaimDecisionContractViolation("analysis candidates must be a tuple")
    analyses = {}
    analysis_ids = set()
    for candidate in candidates:
        if not isinstance(candidate, ClaimAnalysisCandidate):
            raise ClaimDecisionContractViolation("analysis candidate has an invalid type")
        analysis_id = _require_identifier(
            candidate.analysis_id,
            ANALYSIS_ID_PATTERN,
            "analysis_id",
        )
        if analysis_id in analysis_ids:
            raise ClaimDecisionContractViolation("analysis_id values must be unique")
        analysis_ids.add(analysis_id)
        claim_id = _require_identifier(candidate.claim_id, CLAIM_ID_PATTERN, "claim_id")
        if claim_id not in known_claims:
            raise ClaimDecisionContractViolation(
                f"analysis references unknown claim {claim_id}"
            )
        if claim_id in analyses:
            raise ClaimDecisionContractViolation("claim_id analysis values must be unique")
        fields = {
            "facts_found": _require_tuple(candidate.facts_found, "facts_found"),
            "evidence_ids": _require_tuple(
                candidate.evidence_ids,
                "evidence_ids",
                pattern=EVIDENCE_ID_PATTERN,
            ),
            "evidence_assessment": _require_tuple(
                candidate.evidence_assessment,
                "evidence_assessment",
            ),
            "applicable_rules": _require_tuple(
                candidate.applicable_rules,
                "applicable_rules",
            ),
            "precedent_source_ids": _require_tuple(
                candidate.precedent_source_ids,
                "precedent_source_ids",
                pattern=SOURCE_ID_PATTERN,
            ),
            "limitations": _require_tuple(candidate.limitations, "limitations"),
        }
        unknown_evidence = sorted(set(fields["evidence_ids"]) - known_evidence)
        if unknown_evidence:
            raise ClaimDecisionContractViolation(
                f"analysis references unknown evidence {unknown_evidence[0]}"
            )
        if candidate.proposed_outcome not in OUTCOMES:
            raise ClaimDecisionContractViolation("proposed_outcome is unsupported")
        _require_analysis_content(candidate, fields)
        analyses[claim_id] = {
            "analysis_id": analysis_id,
            "claim_id": claim_id,
            "facts_found": sorted(fields["facts_found"]),
            "evidence_ids": sorted(fields["evidence_ids"]),
            "evidence_assessment": sorted(fields["evidence_assessment"]),
            "applicable_rules": sorted(fields["applicable_rules"]),
            "precedent_source_ids": sorted(fields["precedent_source_ids"]),
            "reasoning": _require_text(candidate.reasoning, "reasoning"),
            "proposed_outcome": candidate.proposed_outcome,
            "limitations": sorted(fields["limitations"]),
        }
    missing_claims = sorted(known_claims - set(analyses))
    if missing_claims:
        raise ClaimDecisionContractViolation(
            f"analysis is missing known claim {missing_claims[0]}"
        )
    return {
        "schema_version": 1,
        "analyses": [analyses[claim_id] for claim_id in sorted(analyses)],
    }


def _analysis_index(claim_analysis: object) -> dict:
    if not isinstance(claim_analysis, dict):
        raise ClaimDecisionContractViolation("claim analysis artifact must be an object")
    if claim_analysis.get("schema_version") != 1:
        raise ClaimDecisionContractViolation("claim analysis schema_version must be 1")
    items = claim_analysis.get("analyses")
    if not isinstance(items, list) or not items:
        raise ClaimDecisionContractViolation("claim analysis must contain analyses")
    by_claim = {}
    by_analysis = {}
    for item in items:
        if not isinstance(item, dict):
            raise ClaimDecisionContractViolation("claim analysis item must be an object")
        claim_id = _require_identifier(item.get("claim_id"), CLAIM_ID_PATTERN, "claim_id")
        analysis_id = _require_identifier(
            item.get("analysis_id"),
            ANALYSIS_ID_PATTERN,
            "analysis_id",
        )
        if claim_id in by_claim or analysis_id in by_analysis:
            raise ClaimDecisionContractViolation("claim analysis identifiers must be unique")
        if item.get("proposed_outcome") not in OUTCOMES:
            raise ClaimDecisionContractViolation("claim analysis outcome is unsupported")
        by_claim[claim_id] = item
        by_analysis[analysis_id] = item
    return {"by_claim": by_claim, "by_analysis": by_analysis}


def build_disposition_matrix(
    claim_analysis: dict,
    candidates: Tuple[DispositionCandidate, ...],
) -> dict:
    """Build one disposition linked to each claim analysis."""
    analyses = _analysis_index(claim_analysis)
    if not isinstance(candidates, tuple):
        raise ClaimDecisionContractViolation("disposition candidates must be a tuple")
    dispositions = {}
    disposition_ids = set()
    for candidate in candidates:
        if not isinstance(candidate, DispositionCandidate):
            raise ClaimDecisionContractViolation("disposition candidate has an invalid type")
        disposition_id = _require_identifier(
            candidate.disposition_id,
            DISPOSITION_ID_PATTERN,
            "disposition_id",
        )
        if disposition_id in disposition_ids:
            raise ClaimDecisionContractViolation("disposition_id values must be unique")
        disposition_ids.add(disposition_id)
        claim_id = _require_identifier(candidate.claim_id, CLAIM_ID_PATTERN, "claim_id")
        if claim_id not in analyses["by_claim"]:
            raise ClaimDecisionContractViolation(
                f"disposition references unknown claim {claim_id}"
            )
        if claim_id in dispositions:
            raise ClaimDecisionContractViolation("claim_id disposition values must be unique")
        source_analysis_id = _require_identifier(
            candidate.source_analysis_id,
            ANALYSIS_ID_PATTERN,
            "source_analysis_id",
        )
        source = analyses["by_analysis"].get(source_analysis_id)
        if source is None or source["claim_id"] != claim_id:
            raise ClaimDecisionContractViolation(
                f"source analysis {source_analysis_id} does not match claim {claim_id}"
            )
        effects = _require_tuple(candidate.effects, "effects")
        criteria = _require_tuple(
            candidate.calculation_criteria,
            "calculation_criteria",
        )
        dispositions[claim_id] = {
            "disposition_id": disposition_id,
            "claim_id": claim_id,
            "outcome": source["proposed_outcome"],
            "command": _require_text(candidate.command, "command"),
            "period": _require_text(candidate.period, "period"),
            "effects": sorted(effects),
            "calculation_criteria": sorted(criteria),
            "source_analysis_id": source_analysis_id,
        }
    missing_claims = sorted(set(analyses["by_claim"]) - set(dispositions))
    if missing_claims:
        raise ClaimDecisionContractViolation(
            f"disposition is missing analyzed claim {missing_claims[0]}"
        )
    return {
        "schema_version": 1,
        "items": [dispositions[claim_id] for claim_id in sorted(dispositions)],
    }


def _markdown_list(values: list) -> list:
    if not values:
        return ["- Nenhum item registrado."]
    return [f"- {value}" for value in values]


def _outcome_label(code: object) -> str:
    if not isinstance(code, str) or code not in OUTCOME_LABELS:
        raise ClaimDecisionContractViolation("resultado não reconhecido na minuta")
    return OUTCOME_LABELS[code]


def render_judgment_draft(claim_analysis: dict, disposition_matrix: dict) -> str:
    """Render a deterministic review draft from linked structured artifacts."""
    analyses = _analysis_index(claim_analysis)["by_claim"]
    if not isinstance(disposition_matrix, dict):
        raise ClaimDecisionContractViolation("disposition matrix must be an object")
    if disposition_matrix.get("schema_version") != 1:
        raise ClaimDecisionContractViolation("disposition schema_version must be 1")
    items = disposition_matrix.get("items")
    if not isinstance(items, list) or not items:
        raise ClaimDecisionContractViolation("disposition matrix must contain items")
    dispositions = {item["claim_id"]: item for item in items}
    if set(dispositions) != set(analyses):
        raise ClaimDecisionContractViolation("draft claim coverage is inconsistent")
    lines = ["# Minuta de sentença trabalhista", "", "## Fundamentação", ""]
    for claim_id in sorted(analyses):
        item = analyses[claim_id]
        lines.extend(
            [
                f"### {claim_id}",
                "",
                f"Análise: {item['analysis_id']}",
                "",
                "Fatos reconhecidos:",
                *_markdown_list(item["facts_found"]),
                "",
                "Provas consideradas:",
                *_markdown_list(item["evidence_ids"]),
                "",
                "Avaliação probatória:",
                *_markdown_list(item["evidence_assessment"]),
                "",
                "Regras aplicáveis:",
                *_markdown_list(item["applicable_rules"]),
                "",
                f"Fundamentação: {item['reasoning']}",
                "",
                f"Resultado proposto: {_outcome_label(item['proposed_outcome'])}",
                "",
                "Limitações:",
                *_markdown_list(item["limitations"]),
                "",
            ]
        )
    lines.extend(["## Dispositivo", ""])
    for claim_id in sorted(dispositions):
        item = dispositions[claim_id]
        lines.extend(
            [
                f"### {item['disposition_id']} — {claim_id}",
                "",
                f"Resultado: {_outcome_label(item['outcome'])}",
                f"Comando: {item['command']}",
                f"Período: {'não se aplica' if item['period'] == 'not_applicable' else item['period']}",
                "Efeitos:",
                *_markdown_list(item["effects"]),
                "",
                "Critérios de cálculo:",
                *_markdown_list(item["calculation_criteria"]),
                "",
                f"Análise de origem: {item['source_analysis_id']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
