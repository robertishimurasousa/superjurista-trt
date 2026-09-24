#!/usr/bin/env python3
"""Confere autorização distinta da API sem despachar nem ler os autos."""

from __future__ import annotations

import argparse
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from schema_validation import ContractError, load_json, validate_schema_value


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_SCHEMA = ROOT / "runtime/operations/openai-api-authorization.v1.schema.json"
PREFLIGHT_SCHEMA = ROOT / "runtime/operations/pilot-preflight.v4.schema.json"


class OpenAIAPIAuthorizationError(ValueError):
    """Indica autorização ausente, divergente ou vencida para a API."""


def _timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise OpenAIAPIAuthorizationError("data da autorização inválida") from error
    if result.tzinfo is None:
        raise OpenAIAPIAuthorizationError("data da autorização sem fuso horário")
    return result


def validate_openai_api_authorization(
    authorization: dict, preflight: dict, *, now: Optional[datetime] = None
) -> dict:
    """Vincula o registro à verificação prévia; não concede GO ao piloto."""
    try:
        if validate_schema_value(preflight, load_json(PREFLIGHT_SCHEMA, "piloto")):
            raise OpenAIAPIAuthorizationError("verificação prévia inválida")
        if validate_schema_value(
            authorization, load_json(AUTHORIZATION_SCHEMA, "autorização da API")
        ):
            raise OpenAIAPIAuthorizationError("contrato da autorização da API inválido")
    except ContractError as error:
        raise OpenAIAPIAuthorizationError("esquema da autorização indisponível") from error

    case = preflight["case"]
    if (
        authorization["pilot_id"] != preflight["pilot_id"]
        or authorization["case_reference_digest"] != case["reference_digest"]
        or authorization["authorization_scope_digest"] != case["authorization_scope_digest"]
        or authorization["access_classification"] != case["access_classification"]
    ):
        raise OpenAIAPIAuthorizationError("autorização da API diverge do processo")
    steward = preflight["roles"]["data_steward_id"]
    if (
        authorization["authorized_by"] != steward
        or authorization["provider_terms_reviewed_by"] != steward
    ):
        raise OpenAIAPIAuthorizationError("responsável pela autorização da API diverge")
    if "analyze" not in preflight["controls"]["requested_operations"]:
        raise OpenAIAPIAuthorizationError("análise do processo não foi autorizada")

    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise OpenAIAPIAuthorizationError("a hora atual precisa de fuso horário")
    preflight_created = _timestamp(preflight["created_at"])
    preflight_until = _timestamp(preflight["valid_until"])
    approved_at = _timestamp(authorization["approved_at"])
    authorized_until = _timestamp(authorization["valid_until"])
    if not (
        preflight_created <= approved_at <= checked_at < authorized_until <= preflight_until
    ):
        raise OpenAIAPIAuthorizationError("autorização da API fora da validade do piloto")
    return {
        "status": "authorization_linked_not_pilot_go",
        "provider": "openai_api",
        "surface": "responses",
        "pilot_id": preflight["pilot_id"],
        "case_reference_digest": case["reference_digest"],
        "model_id": authorization["model_id"],
    }


def _protected_record(path: Path) -> dict:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.resolve().is_relative_to(ROOT.resolve())
        or stat.S_IMODE(path.stat().st_mode) & 0o077
    ):
        raise OpenAIAPIAuthorizationError("registro protegido inválido")
    try:
        return load_json(path, "registro protegido")
    except ContractError as error:
        raise OpenAIAPIAuthorizationError("registro protegido inválido") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confere vínculo da autorização da API; não autoriza despacho de autos."
    )
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--authorization", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = validate_openai_api_authorization(
            _protected_record(args.authorization), _protected_record(args.preflight)
        )
    except (OpenAIAPIAuthorizationError, OSError, TypeError, ValueError) as error:
        if isinstance(error, OpenAIAPIAuthorizationError):
            message = str(error)
        else:
            message = "não foi possível conferir os registros protegidos"
        print(f"[NO-GO] Autorização da API: {message}", file=sys.stderr)
        return 2
    print(f"[OK] Registro vinculado ao piloto {result['pilot_id']}; despacho não autorizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
