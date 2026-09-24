#!/usr/bin/env python3
"""Verify a PJe acquisition index against its in-memory document payloads."""

from __future__ import annotations

import hashlib
from pathlib import Path

from schema_validation import load_json, validate_schema_value


INDEX_SCHEMA = (
    Path(__file__).resolve().parents[1]
    / "runtime/providers/document-index-contract.json"
)


class AcquisitionCustodyError(ValueError):
    """Raised when index metadata cannot be trusted as payload custody."""


def verify_acquisition_custody(
    index: dict, payloads: dict[str, bytes], context: dict
) -> None:
    """Require the acquired bytes to match their indexed identity and digest."""
    issues = validate_schema_value(index, load_json(INDEX_SCHEMA, "esquema do índice PJe"))
    if issues:
        raise AcquisitionCustodyError(f"índice PJe inválido: {issues[0]}")
    case = index["case"]
    if not isinstance(context, dict) or any(
        case[index_field] != context.get(context_field)
        for index_field, context_field in (
            ("case_number", "case_number"),
            ("tribunal_code", "court"),
            ("instance", "instance"),
            ("court_unit", "court_unit"),
        )
    ):
        raise AcquisitionCustodyError("o índice PJe não corresponde ao contexto do processo")
    if index["status"] != "complete" or index["gaps"] or not index["documents"]:
        raise AcquisitionCustodyError("a aquisição PJe não está completa")
    indexed = index["documents"]
    if any(item["download_status"] != "downloaded" for item in indexed):
        raise AcquisitionCustodyError("há documento listado sem cópia verificada")
    if any(
        item["filename"] in {".", ".."}
        or "/" in item["filename"]
        or "\\" in item["filename"]
        for item in indexed
    ):
        raise AcquisitionCustodyError("o índice contém nome de arquivo inseguro")
    ids = {item["document_id"] for item in indexed}
    if len(ids) != len(indexed):
        raise AcquisitionCustodyError("o índice repete um documento")
    if not isinstance(payloads, dict) or set(payloads) != ids:
        raise AcquisitionCustodyError("os documentos recebidos divergem do índice")
    for item in indexed:
        payload = payloads[item["document_id"]]
        if not isinstance(payload, bytes) or (
            len(payload) != item["byte_count"]
            or hashlib.sha256(payload).hexdigest() != item["sha256"]
        ):
            raise AcquisitionCustodyError("o conteúdo do documento diverge do índice")
