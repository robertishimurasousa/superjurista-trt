#!/usr/bin/env python3
"""Liga observações documentais à trilha probatória herdada."""

from __future__ import annotations

from pathlib import Path

from build_conditional_work_plan import ConditionalWorkPlanError, iter_dispatches
from documentary_source_custody import PACKET_MARKER
from validate_documentary_observations import (
    DocumentaryObservationsError,
    validate_documentary_observations,
)


class DocumentaryWorkRecordsError(ValueError):
    """Indica que a ponte probatória não pode ser aceita."""


def build_documentary_work_records(
    work_plan: dict, observations: dict, *, packet: str, pdf_path: Path,
    segments: dict, evidence_matrix: dict, claim_id: str,
    evidence_ids: tuple[str, ...],
) -> tuple[dict, dict]:
    """Produz apenas os registros de custódia para um pedido encaminhado."""
    try:
        dispatches = iter_dispatches(work_plan)
        dispatch = next(
            (
                item for item in dispatches
                if item.claim_id == claim_id and item.track == "evidence_analysis"
            ),
            None,
        )
        if dispatch is None:
            raise DocumentaryWorkRecordsError("pedido não encaminhado à análise probatória")
        validate_documentary_observations(
            observations, packet=packet, pdf_path=pdf_path,
            segments=segments, evidence_matrix=evidence_matrix,
            claim_id=claim_id, evidence_ids=evidence_ids,
        )
    except (ConditionalWorkPlanError, DocumentaryObservationsError) as error:
        raise DocumentaryWorkRecordsError("insumos da revisão documental inválidos") from error

    expected = {
        item["evidence_id"] for item in evidence_matrix["evidence_items"]
        if claim_id in item["claim_ids"]
    }
    if not expected or set(evidence_ids) != expected:
        raise DocumentaryWorkRecordsError("cobertura das evidências do pedido incompleta")

    ids = sorted(expected)
    status = observations["status"]
    limitations = [
        "Observações documentais automáticas; revisão jurídica e conferência visual pendentes.",
        PACKET_MARKER + observations["source_packet_sha256"],
    ]
    if status == "insufficient":
        limitations.append("Trecho literal ausente para ao menos uma evidência.")
    review = {
        "claim_id": claim_id,
        "status": status,
        "evidence_ids": ids,
        "assessment": "",
        "limitations": limitations,
    }
    receipt = {
        "work_id": dispatch.work_id,
        "claim_id": claim_id,
        "track": "evidence_analysis",
        "custody_status": "linked" if status == "pending_human_review" else "gap",
        "source_ids": ids,
        "limitations": limitations.copy(),
    }
    return review, receipt
