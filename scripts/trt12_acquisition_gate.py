#!/usr/bin/env python3
"""Verify persisted PJe custody before accepting acquisition in the TRT12 graph."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import recover_pje_acquisition as recovery
from schema_validation import ContractError, load_json, validate_schema_value
from verify_pje_acquisition_custody import (
    AcquisitionCustodyError,
    INDEX_SCHEMA,
    verify_acquisition_custody,
)


SHA256 = re.compile(r"[0-9a-f]{64}")


def make_acquisition_gate(
    workspace: Path, authorization_scope_digest: str, payload_directory: Path
) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Require a complete recovery state bound to authorized scope and local bytes."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    if not isinstance(authorization_scope_digest, str) or not SHA256.fullmatch(
        authorization_scope_digest
    ):
        raise ValueError("o resumo do escopo autorizado deve ser SHA-256")
    root = workspace.resolve()
    if (
        not isinstance(payload_directory, Path)
        or payload_directory.is_symlink()
        or not payload_directory.is_dir()
        or not payload_directory.resolve().is_relative_to(root)
    ):
        raise ValueError("os documentos adquiridos devem ficar no espaço de trabalho")
    payload_root = payload_directory.resolve()

    def read_json(name: str, label: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("insumo ausente ou vínculo simbólico")
        return load_json(path, label)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if stage.get("id") != "acquire-case" or stage.get("gate") != "authorized-acquisition":
            return False
        if outputs != (
            (root / "document-index.json").resolve(),
            (root / "source-manifest.json").resolve(),
        ):
            return False
        try:
            if payload_root.is_symlink() or not payload_root.is_dir():
                return False
            context = read_json("case-context.json", "contexto do processo")
            index = read_json("document-index.json", "índice PJe")
            state = read_json("source-manifest.json", "estado de aquisição PJe")
            issues = validate_schema_value(index, load_json(INDEX_SCHEMA, "esquema do índice PJe"))
            if issues:
                return False
            recovery._validate_state(state, recovery.DEFAULT_RECOVERY_SCHEMA)
            if (
                state["status"] != "complete"
                or state["selection_mode"] != "all"
                or state["authorization_scope_digest"] != authorization_scope_digest
                or state["catalog_digest"] != recovery._catalog_digest(index)
                or state["case"] != {
                    field: index["case"][field]
                    for field in ("case_number", "tribunal_code", "instance")
                }
            ):
                return False
            indexed = {item["document_id"]: item for item in index["documents"]}
            if set(indexed) != {item["document_id"] for item in state["documents"]}:
                return False
            payloads = {}
            for document in state["documents"]:
                document_id = document["document_id"]
                item = indexed[document_id]
                if (
                    document["status"] != "accepted"
                    or document["sha256"] != item["sha256"]
                    or document["byte_count"] != item["byte_count"]
                    or document["relative_path"] != f"{document_id}.bin"
                ):
                    return False
                payload_path = payload_root / document["relative_path"]
                if payload_path.is_symlink() or not payload_path.is_file():
                    return False
                payloads[document_id] = payload_path.read_bytes()
            verify_acquisition_custody(index, payloads, context)
            return True
        except (AcquisitionCustodyError, ContractError, recovery.PJeRecoveryError,
                ValueError, OSError, UnicodeError, TypeError, KeyError):
            return False

    return validate
