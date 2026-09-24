#!/usr/bin/env python3
"""Migra classificações históricas sem reinterpretar os documentos-fonte."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from schema_validation import load_json, validate_schema_value


ROOT = Path(__file__).resolve().parents[1]
OLD_SCHEMA = ROOT / "runtime/contracts/schemas/document-classification.v1.schema.json"
NEW_SCHEMA = ROOT / "runtime/contracts/schemas/document-classification.v2.schema.json"
MIGRATION_VERSION = "document-classification-v1-to-v2.1"


class ClassificationMigrationError(ValueError):
    """Indica que a classificação protegida não pode ser migrada com segurança."""


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: dict) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validate_old_meaning(source: dict) -> None:
    ids = set()
    for document in source["documents"]:
        document_id = document["document_id"]
        if document_id in ids:
            raise ClassificationMigrationError("identificadores documentais repetidos")
        ids.add(document_id)
        status = document["classification_status"]
        document_type = document["document_type"]
        rules = document["matched_rule_ids"]
        reason = document["reason_code"]
        if status == "classified":
            valid = document_type != "unknown" and bool(rules) and reason == "matched_rule"
        elif status == "unknown":
            valid = document_type == "unknown" and not rules and reason == "no_matching_rule"
        else:
            valid = document_type == "unknown" and bool(rules) and reason == "conflicting_rules"
        if not valid:
            raise ClassificationMigrationError("classificação histórica semanticamente inconsistente")


def migrate_classification_v1_to_v2(source: dict) -> tuple[dict, dict]:
    """Preserva os achados v1; nenhum documento desconhecido é reclassificado."""
    issues = validate_schema_value(source, load_json(OLD_SCHEMA, "esquema v1"))
    if issues:
        raise ClassificationMigrationError("classificação v1 inválida: " + "; ".join(issues))
    _validate_old_meaning(source)
    target = copy.deepcopy(source)
    target["schema_version"] = 2
    issues = validate_schema_value(target, load_json(NEW_SCHEMA, "esquema v2"))
    if issues:
        raise ClassificationMigrationError("classificação v2 inválida: " + "; ".join(issues))
    receipt = {
        "contract_id": "document-classification",
        "source_schema_version": 1,
        "target_schema_version": 2,
        "migration_version": MIGRATION_VERSION,
        "source_sha256": _digest(source),
        "target_sha256": _digest(target),
    }
    return target, receipt


def write_migration_bundle(
    target: dict, receipt: dict, *, output_dir: Path, repository_root: Path
) -> tuple[Path, Path]:
    """Publica as duas saídas uma vez em diretório protegido existente."""
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ClassificationMigrationError("diretório protegido inválido")
    destination = output_dir.resolve()
    if stat.S_IMODE(destination.stat().st_mode) != 0o700:
        raise ClassificationMigrationError("diretório de saída deve ter permissão 0700")
    repository = repository_root.resolve()
    if destination == repository or destination.is_relative_to(repository):
        raise ClassificationMigrationError("saída da migração deve ficar fora do repositório")
    if receipt.get("target_sha256") != _digest(target):
        raise ClassificationMigrationError("resumo da classificação migrada divergente")
    outputs = (
        (destination / "document-classification.json", target),
        (destination / "document-classification-migration.json", receipt),
    )
    if any(path.exists() or path.is_symlink() for path, _ in outputs):
        raise ClassificationMigrationError("saída existente não será sobrescrita")
    created = []
    try:
        for path, value in outputs:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    except (OSError, UnicodeError):
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return tuple(path for path, _ in outputs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra classificação documental v1 para v2.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.input.is_symlink() or not args.input.is_file():
            raise ClassificationMigrationError("classificação v1 protegida ausente")
        if stat.S_IMODE(args.input.stat().st_mode) != 0o600:
            raise ClassificationMigrationError("classificação v1 deve ter permissão 0600")
        source = load_json(args.input, "classificação v1")
        target, receipt = migrate_classification_v1_to_v2(source)
        write_migration_bundle(target, receipt, output_dir=args.output, repository_root=ROOT)
    except (ClassificationMigrationError, OSError, TypeError, ValueError) as error:
        print(f"[ERRO] Migração documental: {error}", file=sys.stderr)
        return 2
    print("[OK] Classificação v1 preservada em contrato v2; tipos desconhecidos não foram inferidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
