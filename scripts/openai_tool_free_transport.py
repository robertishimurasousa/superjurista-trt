"""Envia uma requisição de texto sem ferramentas à Responses API."""

from __future__ import annotations

import http.client
import json
import re
from typing import Callable, Optional


API_HOST = "api.openai.com"
API_PATH = "/v1/responses"
MAX_PROMPT_BYTES = 2_000_000
MAX_RESPONSE_BYTES = 2_000_000
MAX_OUTPUT_TOKENS = 8192
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,79}$")


class OpenAIToolFreeTransportError(ValueError):
    """Indica que a requisição ou a resposta não passou nos limites locais."""


def _assistant_text(value: object) -> str:
    if not isinstance(value, dict) or value.get("object") != "response":
        raise OpenAIToolFreeTransportError("resposta da API inválida")
    if (
        value.get("status") != "completed"
        or value.get("error") is not None
        or value.get("incomplete_details") is not None
    ):
        raise OpenAIToolFreeTransportError("resposta da API não foi concluída")
    if (
        value.get("tools") != []
        or value.get("tool_choice") != "none"
        or value.get("store") is not False
        or value.get("conversation") is not None
        or value.get("previous_response_id") is not None
    ):
        raise OpenAIToolFreeTransportError("resposta da API diverge da política sem ferramentas")
    output = value.get("output")
    if not isinstance(output, list):
        raise OpenAIToolFreeTransportError("saída inesperada da API")
    messages = []
    for item in output:
        if not isinstance(item, dict):
            raise OpenAIToolFreeTransportError("saída inesperada da API")
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message":
            raise OpenAIToolFreeTransportError("saída inesperada da API")
        messages.append(item)
    if len(messages) != 1:
        raise OpenAIToolFreeTransportError("saída inesperada da API")
    message = messages[0]
    if message.get("role") != "assistant" or message.get("status") != "completed":
        raise OpenAIToolFreeTransportError("saída inesperada da API")
    content = message.get("content")
    if not isinstance(content, list) or not content:
        raise OpenAIToolFreeTransportError("saída inesperada da API")
    chunks = []
    for part in content:
        if (
            not isinstance(part, dict)
            or part.get("type") != "output_text"
            or not isinstance(part.get("text"), str)
        ):
            raise OpenAIToolFreeTransportError("saída inesperada da API")
        chunks.append(part["text"])
    result = "".join(chunks)
    if not result.strip():
        raise OpenAIToolFreeTransportError("a resposta da API não contém texto")
    return result


def generate_tool_free_text(
    prompt: str,
    model_id: str,
    api_key: str,
    *,
    connection_factory: Optional[Callable] = None,
) -> str:
    """Obtém texto sem anexar ferramentas, arquivos ou estado de conversa."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise OpenAIToolFreeTransportError("entrada do modelo ausente")
    if not isinstance(model_id, str) or MODEL_ID.fullmatch(model_id) is None:
        raise OpenAIToolFreeTransportError("identificador do modelo inválido")
    if not isinstance(api_key, str) or not api_key.strip() or "\n" in api_key or "\r" in api_key:
        raise OpenAIToolFreeTransportError("chave de API ausente ou inválida")
    payload = json.dumps(
        {
            "model": model_id,
            "input": prompt,
            "tools": [],
            "tool_choice": "none",
            "store": False,
            "stream": False,
            "truncation": "disabled",
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    if len(payload) > MAX_PROMPT_BYTES:
        raise OpenAIToolFreeTransportError("entrada do modelo excede o limite")

    factory = connection_factory or http.client.HTTPSConnection
    try:
        connection = factory(API_HOST, timeout=120)
        try:
            connection.request(
                "POST",
                API_PATH,
                body=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            if response.status != 200:
                raise OpenAIToolFreeTransportError(
                    f"a API recusou a requisição (HTTP {response.status})"
                )
            body = response.read(MAX_RESPONSE_BYTES + 1)
        finally:
            connection.close()
    except (OSError, http.client.HTTPException) as error:
        raise OpenAIToolFreeTransportError("falha na comunicação com a API") from error

    if len(body) > MAX_RESPONSE_BYTES:
        raise OpenAIToolFreeTransportError("a resposta da API excede o limite")
    try:
        value = json.loads(body)
    except (UnicodeError, ValueError) as error:
        raise OpenAIToolFreeTransportError("JSON da resposta da API inválido") from error
    return _assistant_text(value)
