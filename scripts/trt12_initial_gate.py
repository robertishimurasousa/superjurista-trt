#!/usr/bin/env python3
"""Validate the TRT12 profile checkpoint against the current pipeline plan."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from schema_validation import ContractError, load_json
from validate_artifact_contracts import validate_document


ROOT = Path(__file__).resolve().parents[1]
CASE_SCHEMA = ROOT / "runtime/contracts/schemas/case-context.v1.schema.json"
TRT12_NUMBER = re.compile(r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.5\.12\.[0-9]{4}")


def make_initial_gate(workspace: Path, plan: dict) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Return a fail-closed gate for the initial profile stage only."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()

    def read_json(name: str, label: str) -> dict:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("insumo ausente ou vínculo simbólico")
        return load_json(path, label)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if stage.get("id") != "prepare-profile" or stage.get("gate") != "profile-context":
            return False
        expected = (
            (root / "case-context.json").resolve(),
            (root / "execution-manifest.json").resolve(),
        )
        if outputs != expected:
            return False
        try:
            context = read_json("case-context.json", "contexto do processo")
            manifest = read_json("execution-manifest.json", "manifesto de execução")
            schema = load_json(CASE_SCHEMA, "esquema do contexto")
            if validate_document(context, schema):
                return False
            source_manifest = Path(context["source_manifest"])
            return (
                manifest == plan
                and plan["contract"]["profile"] == "trt12"
                and context["court"] == "TRT12"
                and context["instance"] == 1
                and TRT12_NUMBER.fullmatch(context["case_number"]) is not None
                and not source_manifest.is_absolute()
                and ".." not in source_manifest.parts
                and context["confidentiality"] != "sealed_authorized"
            )
        except (ContractError, ValueError, OSError, UnicodeError, KeyError, TypeError):
            return False

    return validate
