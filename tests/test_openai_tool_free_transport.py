from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class FakeResponse:
    def __init__(self, body: dict | bytes, status: int = 200) -> None:
        self.status = status
        self.body = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class FakeConnection:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.request_details = None
        self.closed = False

    def request(self, method: str, path: str, body: bytes, headers: dict) -> None:
        self.request_details = (method, path, body, headers)

    def getresponse(self) -> FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


class OpenAIToolFreeTransportTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        if importlib.util.find_spec("openai_tool_free_transport") is None:
            self.fail("o transporte sem ferramentas não existe")
        return importlib.import_module("openai_tool_free_transport")

    def response(self, text: str = "RELATÓRIO sintético") -> dict:
        return {
            "object": "response",
            "status": "completed",
            "error": None,
            "incomplete_details": None,
            "tools": [],
            "tool_choice": "none",
            "store": False,
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}],
                },
            ],
        }

    def test_request_disables_tools_and_storage_and_reads_only_assistant_text(self) -> None:
        api = self.api()
        connection = FakeConnection(FakeResponse(self.response()))
        hosts = []

        def factory(host: str, timeout: int):
            hosts.append((host, timeout))
            return connection

        result = api.generate_tool_free_text(
            "Insumo sintético", "modelo-exemplo", "chave-de-teste", connection_factory=factory
        )

        self.assertEqual(result, "RELATÓRIO sintético")
        self.assertEqual(hosts, [("api.openai.com", 120)])
        method, path, body, headers = connection.request_details
        self.assertEqual((method, path), ("POST", "/v1/responses"))
        self.assertEqual(
            json.loads(body),
            {
                "model": "modelo-exemplo", "input": "Insumo sintético",
                "tools": [], "tool_choice": "none", "store": False,
                "stream": False, "truncation": "disabled", "max_output_tokens": 8192,
            },
        )
        self.assertEqual(headers["Authorization"], "Bearer chave-de-teste")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertTrue(connection.closed)

    def test_missing_credentials_fail_before_network_access(self) -> None:
        api = self.api()

        def forbidden_factory(host: str, timeout: int):
            self.fail("a rede não deve ser acessada sem chave")

        with self.assertRaisesRegex(api.OpenAIToolFreeTransportError, "chave de API"):
            api.generate_tool_free_text(
                "Insumo sintético", "modelo-exemplo", "", connection_factory=forbidden_factory
            )

    def test_tool_call_or_extra_message_is_rejected(self) -> None:
        api = self.api()
        for extra in (
            {"type": "function_call", "name": "unsafe"},
            {"type": "mcp_list_tools", "server_label": "internal"},
            self.response()["output"][1],
        ):
            with self.subTest(extra=extra["type"]):
                response = self.response()
                response["output"].append(extra)
                connection = FakeConnection(FakeResponse(response))
                with self.assertRaisesRegex(api.OpenAIToolFreeTransportError, "saída inesperada"):
                    api.generate_tool_free_text(
                        "Insumo sintético", "modelo-exemplo", "chave-de-teste",
                        connection_factory=lambda host, timeout: connection,
                    )
                self.assertTrue(connection.closed)

    def test_incomplete_or_refused_response_is_rejected(self) -> None:
        api = self.api()
        incomplete = self.response()
        incomplete["status"] = "incomplete"
        refused = self.response()
        refused["output"][1]["content"] = [{"type": "refusal", "refusal": "recusado"}]
        for response in (incomplete, refused):
            connection = FakeConnection(FakeResponse(response))
            with self.assertRaises(api.OpenAIToolFreeTransportError):
                api.generate_tool_free_text(
                    "Insumo sintético", "modelo-exemplo", "chave-de-teste",
                    connection_factory=lambda host, timeout: connection,
                )

    def test_http_error_never_exposes_key_prompt_or_response_body(self) -> None:
        api = self.api()
        connection = FakeConnection(FakeResponse(b"segredo remoto", status=429))
        with self.assertRaises(api.OpenAIToolFreeTransportError) as caught:
            api.generate_tool_free_text(
                "processo privado", "modelo-exemplo", "chave-secreta",
                connection_factory=lambda host, timeout: connection,
            )
        message = str(caught.exception)
        self.assertNotIn("processo privado", message)
        self.assertNotIn("chave-secreta", message)
        self.assertNotIn("segredo remoto", message)
        self.assertTrue(connection.closed)

    def test_response_without_confirmed_tool_and_storage_policy_is_rejected(self) -> None:
        api = self.api()
        for key, value in (
            ("tools", [{"type": "web_search"}]),
            ("tool_choice", "auto"),
            ("store", True),
            ("conversation", {"id": "conversa-inesperada"}),
            ("previous_response_id", "resposta-anterior"),
        ):
            with self.subTest(key=key):
                response = self.response()
                response[key] = value
                connection = FakeConnection(FakeResponse(response))
                with self.assertRaisesRegex(
                    api.OpenAIToolFreeTransportError, "política"
                ):
                    api.generate_tool_free_text(
                        "Insumo sintético", "modelo-exemplo", "chave-de-teste",
                        connection_factory=lambda host, timeout: connection,
                    )
        response = self.response()
        del response["store"]
        with self.assertRaisesRegex(api.OpenAIToolFreeTransportError, "política"):
            api.generate_tool_free_text(
                "Insumo sintético", "modelo-exemplo", "chave-de-teste",
                connection_factory=lambda host, timeout: FakeConnection(FakeResponse(response)),
            )


if __name__ == "__main__":
    unittest.main()
