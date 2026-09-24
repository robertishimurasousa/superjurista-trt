#!/usr/bin/env python3
"""Exigir fusão literal da minuta aceita no arquivo do processo."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from schema_validation import ContractError, load_json
from trt12_draft_gate import make_draft_gate


def make_merge_gate(workspace: Path) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Recusar saída renomeada, alterada ou vinculada simbolicamente."""
    if not isinstance(workspace, Path) or not workspace.is_dir():
        raise ValueError("o espaço de trabalho deve existir")
    root = workspace.resolve()
    draft_gate = make_draft_gate(root)

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        if stage.get("id") != "merge-judgment" or stage.get("gate") != "deterministic-merge":
            return False
        if not draft_gate(
            {"id": "draft-judgment", "gate": "draft-congruence"},
            (
                (root / "disposition-matrix.json").resolve(),
                (root / "judgment-draft.md").resolve(),
            ),
        ):
            return False
        try:
            context_path = root / "case-context.json"
            if context_path.is_symlink() or not context_path.is_file():
                return False
            context = load_json(context_path, "contexto do processo")
            merged = root / f"{context['case_number']}-labor-judgment.md"
            draft = root / "judgment-draft.md"
            if outputs != (merged.resolve(),):
                return False
            if merged.is_symlink() or not merged.is_file() or draft.is_symlink():
                return False
            return merged.read_bytes() == draft.read_bytes()
        except (ContractError, ValueError, OSError, UnicodeError, KeyError, TypeError):
            return False

    return validate
