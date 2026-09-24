#!/usr/bin/env python3
"""Limita despachos diretos do Codex à amostra sintética versionada."""

from __future__ import annotations

from pathlib import Path

from schema_validation import load_json


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/pipeline/synthetic-first-instance.json"


class SyntheticRehearsalError(ValueError):
    """Indica que um insumo não pertence ao ensaio sintético aprovado."""


def require_synthetic_rehearsal(report: dict, matrix: dict) -> None:
    """Recusa dados arbitrários antes de despachar qualquer conteúdo ao modelo."""
    fixture = load_json(FIXTURE, "amostra sintética do TRT12")
    artifacts = fixture.get("artifacts", {})
    if (
        report != artifacts.get("labor-report.json")
        or matrix != artifacts.get("claim-matrix.json")
    ):
        raise SyntheticRehearsalError(
            "a entrada não corresponde à amostra sintética versionada"
        )
