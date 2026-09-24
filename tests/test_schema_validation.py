"""Confere diagnósticos dos contratos sem alterar suas regras de validação."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_validation import ContractError, load_json, validate_schema_value


class SchemaValidationTest(unittest.TestCase):
    def test_issues_preserve_field_paths_and_explain_errors_in_portuguese(self) -> None:
        cases = (
            ({"type": "object"}, [], "$: esperado objeto, recebido lista"),
            ({"type": "object", "required": ["claim_id"]}, {}, "claim_id: campo obrigatório ausente"),
            ({"type": "object", "additionalProperties": False}, {"extra": 1}, "campo desconhecido: extra"),
            ({"type": "string", "enum": ["ready"]}, "other", "$: valor não permitido 'other'"),
            ({"type": "array", "uniqueItems": True}, [1, 1], "$: os itens devem ser únicos"),
            ({"type": "integer", "minimum": 2}, 1, "$: deve ser no mínimo 2"),
        )
        for schema, value, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, validate_schema_value(value, schema))

    def test_missing_json_reports_portuguese_error_without_losing_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "ausente.json"
            with self.assertRaisesRegex(ContractError, "contrato de teste não encontrado"):
                load_json(missing, "contrato de teste")


if __name__ == "__main__":
    unittest.main()
