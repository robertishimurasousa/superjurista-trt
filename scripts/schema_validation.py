"""Validação sem dependências do subconjunto JSON Schema dos contratos."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional


class ContractError(ValueError):
    """Indica que um contrato de esquema não pôde ser avaliado."""


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ContractError(f"{label} não encontrado: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(
            f"JSON inválido em {label}: linha {error.lineno}, coluna {error.colno}"
        ) from error


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def display_path(path: str) -> str:
    return path or "$"


def _type_label(type_name: str) -> str:
    return {
        "null": "nulo",
        "boolean": "booleano",
        "integer": "inteiro",
        "string": "texto",
        "array": "lista",
        "object": "objeto",
    }.get(type_name, type_name)


def validate_schema_value(
    value: Any,
    schema: dict,
    path: str = "",
    _root_schema: Optional[dict] = None,
    _ref_stack: tuple[str, ...] = (),
) -> list[str]:
    """Valida um valor conforme o subconjunto de esquemas do projeto."""
    root_schema = schema if _root_schema is None else _root_schema
    reference = schema.get("$ref")
    if isinstance(reference, str):
        if reference in _ref_stack:
            return [f"{display_path(path)}: referência cíclica no esquema {reference}"]
        resolved = _resolve_local_reference(root_schema, reference)
        if resolved is None:
            return [f"{display_path(path)}: referência não suportada no esquema {reference}"]
        return validate_schema_value(
            value,
            resolved,
            path,
            root_schema,
            _ref_stack + (reference,),
        )

    issues: list[str] = []
    expected = schema.get("type")
    allowed_types = [expected] if isinstance(expected, str) else expected
    if allowed_types and value_type(value) not in allowed_types:
        return [
            f"{display_path(path)}: esperado {' ou '.join(_type_label(kind) for kind in allowed_types)}, "
            f"recebido {_type_label(value_type(value))}"
        ]

    if "const" in schema and value != schema["const"]:
        issues.append(f"{display_path(path)}: deve ser igual a {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        issues.append(f"{display_path(path)}: valor não permitido {value!r}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for field in schema.get("required", []):
            if field not in value:
                child = f"{path}.{field}" if path else field
                issues.append(f"{child}: campo obrigatório ausente")
        if schema.get("additionalProperties") is False:
            for field in value:
                if field not in properties:
                    prefix = f"{path}: " if path else ""
                    issues.append(f"{prefix}campo desconhecido: {field}")
        for field, child_value in value.items():
            child_schema = properties.get(field)
            if child_schema is not None:
                child = f"{path}.{field}" if path else field
                issues.extend(
                    validate_schema_value(
                        child_value,
                        child_schema,
                        child,
                        root_schema,
                        _ref_stack,
                    )
                )

    if isinstance(value, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(value) < minimum:
            issues.append(f"{display_path(path)}: requer pelo menos {minimum} item(ns)")
        if schema.get("uniqueItems"):
            normalized = [json.dumps(item, sort_keys=True) for item in value]
            if len(normalized) != len(set(normalized)):
                issues.append(f"{display_path(path)}: os itens devem ser únicos")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                issues.extend(
                    validate_schema_value(
                        item,
                        item_schema,
                        f"{path}[{index}]",
                        root_schema,
                        _ref_stack,
                    )
                )

    if isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            issues.append(f"{display_path(path)}: texto muito curto")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            issues.append(f"{display_path(path)}: valor não corresponde ao padrão {pattern}")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int) and value < minimum:
            issues.append(f"{display_path(path)}: deve ser no mínimo {minimum}")
        if isinstance(maximum, int) and value > maximum:
            issues.append(f"{display_path(path)}: deve ser no máximo {maximum}")

    return issues


def _resolve_local_reference(root_schema: dict, reference: str) -> Any:
    if not reference.startswith("#/"):
        return None
    current: Any = root_schema
    for encoded_part in reference[2:].split("/"):
        part = encoded_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, dict) else None
