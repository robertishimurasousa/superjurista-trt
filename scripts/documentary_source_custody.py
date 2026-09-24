#!/usr/bin/env python3
"""Vincula revisões documentais automáticas ao PDF original verificável."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from prepare_source_evidence_packet import build_source_evidence_packet
from schema_validation import load_json, validate_schema_value
from validate_documentary_observations import validate_documentary_observations


ROOT = Path(__file__).resolve().parents[1]
REGISTER_NAME = "documentary-source-register.json"
REGISTER_SCHEMA = ROOT / "runtime/pipelines/documentary-source-register.v1.schema.json"
PACKET_MARKER = "Pacote de fontes SHA-256: "
OBSERVATIONS_MARKER = "Observações documentais SHA-256: "


class DocumentarySourceCustodyError(ValueError):
    """Indica que a fonte documental não confirma a revisão publicada."""


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def observations_digest(value: dict) -> str:
    """Resume as observações de modo independente da formatação do arquivo."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_source_record(workspace: Path, claim_id: str, bundle: dict) -> dict:
    """Prepara registro limitado a PDF direto do espaço privado do caso."""
    pdf_path = bundle["pdf_path"]
    if (
        not isinstance(pdf_path, Path)
        or pdf_path.is_symlink()
        or not pdf_path.is_file()
        or pdf_path.resolve().parent != workspace
    ):
        raise DocumentarySourceCustodyError("PDF documental fora do espaço do caso")
    return {
        "claim_id": claim_id,
        "source_pdf_name": pdf_path.name,
        "source_pdf_sha256": _file_digest(pdf_path),
        "source_packet_sha256": hashlib.sha256(bundle["packet"].encode("utf-8")).hexdigest(),
        "observations_sha256": observations_digest(bundle["observations"]),
        "evidence_ids": sorted(bundle["evidence_ids"]),
        "segments": bundle["segments"],
        "observations": bundle["observations"],
    }


def _marker(review: dict, prefix: str) -> str | None:
    matches = [item.removeprefix(prefix) for item in review["limitations"] if item.startswith(prefix)]
    if len(matches) > 1:
        raise DocumentarySourceCustodyError("marcador documental duplicado")
    return matches[0] if matches else None


def validate_source_register(workspace: Path, evidence: dict, reviews: dict) -> None:
    """Reconfere PDF, pacote e observações quando a revisão cita um pacote automático."""
    path = workspace / REGISTER_NAME
    automated = {}
    for item in reviews["reviews"]:
        packet_marker = _marker(item, PACKET_MARKER)
        observations_marker = _marker(item, OBSERVATIONS_MARKER)
        if (packet_marker is None) != (observations_marker is None):
            raise DocumentarySourceCustodyError("marcadores documentais incompletos")
        if packet_marker is not None:
            automated[item["claim_id"]] = item
    if not automated and not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_file():
        raise DocumentarySourceCustodyError("registro de fontes ausente ou vinculado")
    register = load_json(path, "registro de custódia documental")
    if validate_schema_value(register, load_json(REGISTER_SCHEMA, "esquema de custódia documental")):
        raise DocumentarySourceCustodyError("registro de fontes inválido")
    records = {item["claim_id"]: item for item in register["records"]}
    if len(records) != len(register["records"]) or set(records) != set(automated):
        raise DocumentarySourceCustodyError("cobertura do registro documental diverge")
    for claim_id, review in automated.items():
        record = records[claim_id]
        packet_digest = _marker(review, PACKET_MARKER)
        observation_digest = _marker(review, OBSERVATIONS_MARKER)
        if (
            packet_digest != record["source_packet_sha256"]
            or observation_digest != record["observations_sha256"]
            or sorted(review["evidence_ids"]) != record["evidence_ids"]
            or observations_digest(record["observations"]) != record["observations_sha256"]
        ):
            raise DocumentarySourceCustodyError("revisão e registro documental divergem")
        name = record["source_pdf_name"]
        if Path(name).name != name or name in {".", ".."}:
            raise DocumentarySourceCustodyError("nome do PDF documental inválido")
        pdf_path = workspace / name
        if pdf_path.is_symlink() or not pdf_path.is_file() or (
            _file_digest(pdf_path) != record["source_pdf_sha256"]
        ):
            raise DocumentarySourceCustodyError("PDF documental alterado ou ausente")
        evidence_ids = tuple(record["evidence_ids"])
        packet = build_source_evidence_packet(
            pdf_path, record["segments"], evidence,
            claim_id=claim_id, evidence_ids=evidence_ids,
        )
        if hashlib.sha256(packet.encode("utf-8")).hexdigest() != packet_digest:
            raise DocumentarySourceCustodyError("pacote documental diverge do PDF")
        validate_documentary_observations(
            record["observations"], packet=packet, pdf_path=pdf_path,
            segments=record["segments"], evidence_matrix=evidence,
            claim_id=claim_id, evidence_ids=evidence_ids,
        )
        if review["status"] != "reviewed" and review["status"] != record["observations"]["status"]:
            raise DocumentarySourceCustodyError("estado da revisão documental diverge")
