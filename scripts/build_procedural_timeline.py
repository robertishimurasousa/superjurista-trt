#!/usr/bin/env python3
"""Build a source-linked procedural timeline from segmented PJe documents."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from schema_validation import load_json, validate_schema_value


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "procedural-timeline.v1.schema.json"
)


EVENT_PRESENTATION = {
    "initial_pleading": ("case_filed", "Initial pleading filed."),
    "defense": ("defense_filed", "Defense filed."),
    "reply": ("reply_filed", "Reply filed."),
    "hearing_record": ("hearing_held", "Hearing recorded."),
    "expert_report": ("expert_report_filed", "Expert report filed."),
    "documentary_evidence": ("evidence_filed", "Documentary evidence filed."),
    "calculations": ("calculations_filed", "Calculations filed."),
    "settlement": ("settlement_filed", "Settlement document filed."),
    "procedural_order": ("procedural_order_issued", "Procedural order issued."),
    "interlocutory_decision": (
        "interlocutory_decision_issued",
        "Interlocutory decision issued.",
    ),
    "judgment": ("judgment_issued", "Judgment issued."),
    "appeal": ("appeal_filed", "Appeal filed."),
    "other_petition": ("petition_filed", "Petition filed."),
}
UNCLASSIFIED_EVENT = (
    "unclassified_document_filed",
    "Document event requires human review.",
)


class ProceduralTimelineError(ValueError):
    """Raised when segment and classification custody cannot build a timeline."""


def _source_locator(document: dict) -> str:
    start = document["page_start"]
    end = document["page_end"]
    return f"page {start}" if start == end else f"pages {start}-{end}"


def build_procedural_timeline(
    segments: dict,
    classification: dict,
    *,
    schema_path: Path,
) -> dict:
    """Create one deterministic event for every segmented source document."""
    segment_ids = [item["document_id"] for item in segments["documents"]]
    classification_ids = [
        item["document_id"] for item in classification["documents"]
    ]
    if len(segment_ids) != len(set(segment_ids)):
        raise ProceduralTimelineError("segment document identifiers must be unique")
    if len(classification_ids) != len(set(classification_ids)):
        raise ProceduralTimelineError("classification document identifiers must be unique")
    if set(segment_ids) != set(classification_ids):
        raise ProceduralTimelineError(
            "segment and classification document sets must match exactly"
        )
    classified_by_id = {
        item["document_id"]: item for item in classification["documents"]
    }
    events = []
    gaps = []
    for document in segments["documents"]:
        document_id = document["document_id"]
        classified = classified_by_id[document_id]
        classification_status = classified["classification_status"]
        document_type = classified["document_type"]
        if classification_status not in {"classified", "conflict", "unknown"}:
            raise ProceduralTimelineError("classification status is unsupported")
        if document_type not in {*EVENT_PRESENTATION, "unknown"}:
            raise ProceduralTimelineError("classified document type is unsupported")
        if (classification_status == "classified") != (document_type != "unknown"):
            raise ProceduralTimelineError(
                "classification status and document type are inconsistent"
            )
        presentation = EVENT_PRESENTATION.get(
            document_type,
            UNCLASSIFIED_EVENT,
        )
        if classification_status != "classified":
            reason_code = (
                "classification_conflict"
                if classification_status == "conflict"
                else "unclassified_document"
            )
            gaps.append(
                {
                    "subject_id": document_id,
                    "reason_code": reason_code,
                }
            )
        events.append(
            {
                "event_id": f"EVT-{document_id.removeprefix('DOC-')}",
                "event_date": document["filed_on"],
                "event_type": presentation[0],
                "summary": presentation[1],
                "source_document_id": document_id,
                "source_locator": _source_locator(document),
            }
        )

    result = {
        "schema_version": 1,
        "status": "partial" if gaps else "complete",
        "events": sorted(
            events,
            key=lambda item: (item["event_date"], item["event_id"]),
        ),
        "gaps": sorted(gaps, key=lambda item: item["subject_id"]),
    }
    schema = load_json(schema_path, "procedural timeline schema")
    issues = validate_schema_value(result, schema)
    if issues:
        raise ProceduralTimelineError(
            "procedural timeline contract failed: " + "; ".join(issues)
        )
    return result


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def write_timeline_artifact(
    timeline: dict,
    *,
    output_dir: Path,
    repository_root: Path,
) -> Path:
    """Write one protected timeline without allowing repository-local case data."""
    destination = output_dir.resolve()
    repository = repository_root.resolve()
    if destination == repository or _is_within(destination, repository):
        raise ProceduralTimelineError("timeline output must stay outside repository")
    if not destination.is_dir():
        raise ProceduralTimelineError("timeline output directory must already exist")

    path = destination / "procedural-timeline.json"
    if path.exists():
        raise ProceduralTimelineError("timeline output already exists")
    payload = (json.dumps(timeline, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a protected procedural timeline from classified PJe segments.",
    )
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--classification", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        segments = load_json(args.segments, "PJe PDF segments")
        classification = load_json(
            args.classification,
            "document classification",
        )
        timeline = build_procedural_timeline(
            segments,
            classification,
            schema_path=args.schema,
        )
        write_timeline_artifact(
            timeline,
            output_dir=args.output,
            repository_root=args.repository_root,
        )
    except (KeyError, OSError, ProceduralTimelineError, TypeError, ValueError) as error:
        print(f"[ERROR] procedural timeline: {error}", file=sys.stderr)
        return 1

    print(
        "[OK] procedural timeline: "
        f"events={len(timeline['events'])} "
        f"gaps={len(timeline['gaps'])} "
        f"status={timeline['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
