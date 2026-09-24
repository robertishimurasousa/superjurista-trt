#!/usr/bin/env python3
"""Compose the implemented TRT12 stage gates for checkpoint validation."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from trt12_acquisition_gate import make_acquisition_gate
from trt12_claim_analysis_gate import make_claim_analysis_gate
from trt12_conditional_tracks_gate import make_conditional_tracks_gate
from trt12_decision_units_gate import make_decision_units_gate
from trt12_draft_gate import make_draft_gate
from trt12_extraction_gate import make_extraction_gate
from trt12_final_gate import make_final_gate
from trt12_handoff_gate import make_handoff_gate
from trt12_initial_gate import make_initial_gate
from trt12_merge_gate import make_merge_gate


def make_trt12_gate_validator(
    workspace: Path,
    plan: dict,
    authorization_scope_digest: str,
    payload_dir: Path,
) -> Callable[[dict, tuple[Path, ...]], bool]:
    """Validate only implemented stages; never infer approval for later stages."""
    initial = make_initial_gate(workspace, plan)
    acquisition = make_acquisition_gate(
        workspace, authorization_scope_digest, payload_dir
    )
    extraction = make_extraction_gate(workspace)
    decisions = make_decision_units_gate(workspace)
    handoff = make_handoff_gate(workspace)
    conditional_tracks = make_conditional_tracks_gate(workspace)
    claim_analysis = make_claim_analysis_gate(workspace)
    draft = make_draft_gate(workspace)
    merged = make_merge_gate(workspace)
    final = make_final_gate(workspace)
    validators = {
        "prepare-profile": initial,
        "acquire-case": acquisition,
        "extract-record": extraction,
        "build-decision-units": decisions,
        "prepare-triage-input": handoff,
        "narrate-record": handoff,
        "route-claims": handoff,
        "execute-conditional-tracks": conditional_tracks,
        "analyze-claims": claim_analysis,
        "draft-judgment": draft,
        "merge-judgment": merged,
        "review-and-gate": final,
    }

    def validate(stage: dict, outputs: tuple[Path, ...]) -> bool:
        validator = validators.get(stage.get("id"))
        return validator(stage, outputs) if validator is not None else False

    return validate
