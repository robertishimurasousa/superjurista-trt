#!/usr/bin/env python3
"""Official TRT12 Falcão adapter for the shared legal-research contract."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import string
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from provider_interfaces import (
    AdapterDescriptor,
    ResearchFetchRequest,
    ResearchHit,
    ResearchPage,
    ResearchQuery,
    ResearchSource,
)
from schema_validation import load_json, validate_schema_value


API_BASE_URL = (
    "https://jurisprudencia.jt.jus.br/"
    "jurisprudencia-nacional-backend/api/no-auth"
)
PUBLIC_BASE_URL = "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional"
OFFICIAL_HOST = "jurisprudencia.jt.jus.br"
SOURCE_NAME = "trt12_jurisprudence"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
SESSION_ID_PATTERN = re.compile(r"_[a-z0-9]{7}")
CNJ_NUMBER_PATTERN = re.compile(r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.5\.12\.[0-9]{4}")
SENTENCE_PATTERN = re.compile(r"[^.!?]+[.!?]")


class TRT12AdapterError(ValueError):
    """Raised when an official Falcão response cannot be normalized safely."""


class FalcaoTransport(Protocol):
    def open_session(
        self,
        *,
        query: str,
        session_id: str,
        max_bytes: int,
    ) -> None:
        ...

    def get_json(self, url: str, *, max_bytes: int) -> dict:
        ...


class UrllibFalcaoTransport:
    """Bounded HTTPS transport restricted to the public Falcão application."""

    def __init__(
        self,
        *,
        opener: Any = urlopen,
        timeout: int = 20,
    ) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            raise TRT12AdapterError("timeout must be a positive integer")
        self.opener = opener
        self.timeout = timeout
        self.session_id: str | None = None
        self.jsession_id: str | None = None

    def open_session(
        self,
        *,
        query: str,
        session_id: str,
        max_bytes: int,
    ) -> None:
        query = _require_text(query, "query")
        _validate_session_id(session_id)
        self.session_id = session_id
        self.get_json(
            f"{API_BASE_URL}/notificacoes?page=0&size=5",
            max_bytes=max_bytes,
        )
        self.get_json(
            f"{API_BASE_URL}/autocompletar?texto={quote(query, safe='')}",
            max_bytes=max_bytes,
        )

    def get_json(self, url: str, *, max_bytes: int) -> dict:
        request = Request(
            url,
            headers=self._headers(url),
            method="GET",
        )
        body = self._read(request, max_bytes=max_bytes)
        try:
            response = json.loads(body)
        except json.JSONDecodeError as error:
            raise TRT12AdapterError("official Falcão response is not valid JSON") from error
        if not isinstance(response, dict):
            raise TRT12AdapterError("official Falcão JSON response must be an object")
        return response

    def _headers(self, url: str) -> dict[str, str]:
        referer = (
            f"{PUBLIC_BASE_URL}/pesquisa"
            if "/pesquisa" in url
            else f"{PUBLIC_BASE_URL}/home"
        )
        cookies = []
        if self.jsession_id is not None:
            cookies.append(f"JSESSIONID={self.jsession_id}")
        if self.session_id is not None:
            cookies.extend(
                (
                    f"SESSION_ID_COOKIE_PUJ={self.session_id}",
                    "SameSite=None",
                )
            )
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Referer": referer,
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Sec-CH-UA": (
                '"Chromium";v="120", "Not_A Brand";v="8", '
                '"Google Chrome";v="120"'
            ),
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Linux"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        if cookies:
            headers["Cookie"] = "; ".join(cookies)
        return headers

    def _read(self, request: Request, *, max_bytes: int) -> str:
        _validate_official_api_url(request.full_url)
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise TRT12AdapterError("max_bytes must be a positive integer")
        try:
            if hasattr(self.opener, "open"):
                response_context = self.opener.open(request, timeout=self.timeout)
            else:
                response_context = self.opener(request, timeout=self.timeout)
            with response_context as response:
                _validate_official_api_url(response.geturl())
                self._capture_session_cookie(response)
                body = response.read(max_bytes + 1)
        except (HTTPError, URLError, TimeoutError) as error:
            if isinstance(error, HTTPError) and error.code == 429:
                raise TRT12AdapterError(
                    "official Falcão rate limit is active; retry after its published window"
                ) from error
            raise TRT12AdapterError("official Falcão source request failed") from error
        if len(body) > max_bytes:
            raise TRT12AdapterError("official Falcão response exceeded the size limit")
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TRT12AdapterError(
                "official Falcão response is not valid UTF-8"
            ) from error

    def _capture_session_cookie(self, response: Any) -> None:
        headers = getattr(response, "headers", None)
        if headers is None:
            return
        values = (
            headers.get_all("Set-Cookie", [])
            if hasattr(headers, "get_all")
            else []
        )
        for value in values:
            parsed = SimpleCookie()
            parsed.load(value)
            if "JSESSIONID" in parsed:
                self.jsession_id = parsed["JSESSIONID"].value


class TRT12OfficialAdapter:
    """Normalize current TRT12 PJe judgments from the official Falcão source."""

    descriptor = AdapterDescriptor(
        provider_id="trt12-falcao-official",
        interface_id="legal_research",
        interface_version=1,
        capabilities=("search", "fetch_source"),
        supported_tribunals=("TRT12",),
    )

    def __init__(
        self,
        *,
        transport: FalcaoTransport,
        page_size: int = 20,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        session_factory: Callable[[], str] = lambda: "_" + "".join(
            secrets.choice(string.ascii_lowercase + string.digits) for _ in range(7)
        ),
    ) -> None:
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            raise TRT12AdapterError("page_size must be an integer")
        if page_size < 1 or page_size > 100:
            raise TRT12AdapterError("page_size must be between 1 and 100")
        self.transport = transport
        self.page_size = page_size
        self.clock = clock
        self.session_factory = session_factory
        self._session_id: str | None = None
        self._session_query: str | None = None
        self._records: dict[str, tuple[str, dict[str, Any]]] = {}

    def search(self, request: ResearchQuery) -> ResearchPage:
        _validate_request_scope(request.tribunal_code, request.source)
        query = _require_text(request.query, "query")
        page_number = _parse_cursor(request.cursor)
        session_id = self._ensure_session(query)
        parameters = {
            "sessionId": session_id,
            "latitude": "0",
            "longitude": "0",
            "texto": quote(query, safe=""),
            "verTodosPrecedentes": "false",
            "tribunais": "TRT12",
            "pesquisaSomenteNasEmentas": "false",
            "colecao": "acordaos,sentencas",
            "page": str(page_number),
            "size": str(self.page_size),
        }
        response = self.transport.get_json(
            f"{API_BASE_URL}/pesquisa?{urlencode(parameters)}",
            max_bytes=MAX_RESPONSE_BYTES,
        )
        total, documents = _validate_search_response(response)
        hits = []
        for raw_record in documents:
            collection, record = _validate_record(raw_record)
            source_id = _source_id(collection, record)
            if source_id in self._records:
                raise TRT12AdapterError("official search repeated a source identifier")
            self._records[source_id] = (collection, record)
            hits.append(
                ResearchHit(
                    source_id=source_id,
                    origin="TRT12",
                    reference=_reference(collection, record),
                    status="unknown",
                    official_url=_official_document_url(collection, record),
                )
            )
        consumed = page_number * self.page_size + len(hits)
        if not hits and consumed < total:
            raise TRT12AdapterError(
                "official search returned an empty page before completion"
            )
        complete = consumed >= total
        return ResearchPage(
            items=tuple(hits),
            next_cursor=None if complete else str(page_number + 1),
            complete=complete,
        )

    def fetch_source(self, request: ResearchFetchRequest) -> ResearchSource:
        _validate_request_scope(request.tribunal_code, request.source)
        cached = self._records.get(request.source_id)
        if cached is None:
            raise TRT12AdapterError("source_id must come from a completed adapter search")
        collection, search_record = cached
        document_id = _record_id(collection, search_record)
        session_id = self._session_id
        if session_id is None:
            raise TRT12AdapterError("official Falcão session is not initialized")
        parameters = urlencode(
            {
                "sessionId": session_id,
                "latitude": "0",
                "longitude": "0",
            }
        )
        response = self.transport.get_json(
            f"{API_BASE_URL}/pesquisa/{collection}/TRT12/{document_id}?{parameters}",
            max_bytes=MAX_RESPONSE_BYTES,
        )
        detail_record = _validate_detail_response(response, collection, document_id)
        excerpt = _excerpt(collection, search_record)
        full_text = _full_text(collection, detail_record)
        if excerpt not in full_text:
            raise TRT12AdapterError(
                "official detail does not preserve verbatim custody for the excerpt"
            )
        retrieved_at = self.clock()
        if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None:
            raise TRT12AdapterError("clock must return a timezone-aware datetime")
        return ResearchSource(
            source_id=request.source_id,
            origin="TRT12",
            reference=_reference(collection, search_record),
            status="unknown",
            status_notes=(
                (
                    "Coverage: current_pje. The official Falcão repository provides "
                    "TRT12 first- and second-instance PJe documents from 2016 onward."
                ),
                (
                    "Legacy physical and Provi collections are not exposed by the "
                    "current TRT12 jurisprudence page and are outside this adapter."
                ),
                (
                    "The Falcão response does not expose a normalized precedential "
                    "status; human verification is required."
                ),
            ),
            binding_scope=(
                "trt12_first_instance"
                if collection == "sentencas"
                else "trt12_second_instance"
            ),
            legal_question=_sentences(excerpt)[0],
            holding=_sentences(excerpt)[-1],
            verbatim_excerpt=excerpt,
            official_url=_official_document_url(collection, search_record),
            retrieved_at=_iso_timestamp(retrieved_at),
        )

    def _ensure_session(self, query: str) -> str:
        if self._session_id is None or self._session_query != query:
            session_id = self.session_factory()
            _validate_session_id(session_id)
            self.transport.open_session(
                query=query,
                session_id=session_id,
                max_bytes=MAX_RESPONSE_BYTES,
            )
            self._session_id = session_id
            self._session_query = query
            self._records.clear()
        return self._session_id


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TRT12AdapterError(f"{label} must be a non-empty string")
    return value.strip()


def _validate_official_api_url(value: object) -> None:
    if not isinstance(value, str):
        raise TRT12AdapterError("request URL must use the official Falcão host")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != OFFICIAL_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/jurisprudencia-nacional-backend/api/no-auth/")
    ):
        raise TRT12AdapterError("request URL must use the official Falcão host")


def _validate_session_id(value: object) -> None:
    if not isinstance(value, str) or SESSION_ID_PATTERN.fullmatch(value) is None:
        raise TRT12AdapterError("session_id must use the Falcão public-session format")


def _validate_request_scope(tribunal_code: object, source: object) -> None:
    if tribunal_code != "TRT12":
        raise TRT12AdapterError("this regional adapter supports only TRT12")
    if source != SOURCE_NAME:
        raise TRT12AdapterError(f"source must be {SOURCE_NAME}")


def _parse_cursor(cursor: object) -> int:
    if cursor is None:
        return 0
    if not isinstance(cursor, str) or not cursor.isdigit():
        raise TRT12AdapterError("cursor must be a non-negative decimal page")
    return int(cursor)


def _validate_search_response(response: object) -> tuple[int, list]:
    if not isinstance(response, dict):
        raise TRT12AdapterError("official search response must be an object")
    total = response.get("quantidadeTotal")
    documents = response.get("documentos")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise TRT12AdapterError("official quantidadeTotal must be non-negative")
    if not isinstance(documents, list):
        raise TRT12AdapterError("official documentos must be an array")
    return total, documents


def _validate_record(value: object) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise TRT12AdapterError("official search item must be an object")
    record = dict(value)
    collections = [
        collection
        for collection, field in (
            ("acordaos", "idDocumentoAcordao"),
            ("sentencas", "idSentenca"),
        )
        if field in record
    ]
    if len(collections) != 1:
        raise TRT12AdapterError(
            "official result must identify exactly one collection"
        )
    collection = collections[0]
    _record_id(collection, record)
    if record.get("tribunal") != "TRT12":
        raise TRT12AdapterError("official result tribunal must be TRT12")
    case_number = _require_text(record.get("numeroProcesso"), "official case number")
    if CNJ_NUMBER_PATTERN.fullmatch(case_number) is None:
        raise TRT12AdapterError("official case number must identify TRT12")
    _require_text(record.get("dataJuntada"), "official filing date")
    if collection == "acordaos":
        _require_text(record.get("siglaClasseProcesso"), "official case class")
        _require_text(record.get("turma"), "official adjudicating body")
    else:
        _require_text(record.get("classeProcessual"), "official case class")
        _require_text(
            record.get("orgaoJulgadorPorExtenso") or record.get("orgaoJulgador"),
            "official adjudicating body",
        )
    _excerpt(collection, record)
    return collection, record


def _record_id(collection: str, record: dict[str, Any]) -> str:
    field = "idDocumentoAcordao" if collection == "acordaos" else "idSentenca"
    value = record.get(field)
    if isinstance(value, bool):
        raise TRT12AdapterError("official document id must be numeric")
    rendered = str(value) if isinstance(value, (int, str)) else ""
    if not rendered.isdigit() or len(rendered) < 3:
        raise TRT12AdapterError("official document id must be numeric")
    return rendered


def _source_id(collection: str, record: dict[str, Any]) -> str:
    prefix = "TRT12A" if collection == "acordaos" else "TRT12S"
    return f"{prefix}-{_record_id(collection, record)}"


def _reference(collection: str, record: dict[str, Any]) -> str:
    if collection == "acordaos":
        return (
            f"{record['siglaClasseProcesso']} {record['numeroProcesso']}; "
            f"{record['turma']}; acórdão juntado em {record['dataJuntada']}"
        )
    adjudicating_body = record.get("orgaoJulgadorPorExtenso") or record["orgaoJulgador"]
    return (
        f"{record['classeProcessual']} {record['numeroProcesso']}; "
        f"{adjudicating_body}; sentença juntada em {record['dataJuntada']}"
    )


def _official_document_url(collection: str, record: dict[str, Any]) -> str:
    return (
        f"{PUBLIC_BASE_URL}/citacao/{collection}/TRT12/"
        f"{_record_id(collection, record)}"
    )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _normalize_html_text(value: object, label: str) -> str:
    text = _require_text(value, label)
    parser = _TextExtractor()
    parser.feed(text)
    normalized = " ".join(" ".join(parser.parts).split())
    if not normalized:
        raise TRT12AdapterError(f"{label} must contain text")
    return normalized


def _excerpt(collection: str, record: dict[str, Any]) -> str:
    if collection == "acordaos":
        value = record.get("ementa") or record.get("textoAcordao")
        return _normalize_html_text(value, "official acórdão excerpt")
    return _normalize_html_text(
        record.get("textoSentenca"),
        "official sentença excerpt",
    )


def _full_text(collection: str, record: dict[str, Any]) -> str:
    field = "textoAcordao" if collection == "acordaos" else "textoSentenca"
    return _normalize_html_text(record.get(field), "official full document")


def _validate_detail_response(
    response: object,
    collection: str,
    document_id: str,
) -> dict[str, Any]:
    if not isinstance(response, dict) or not isinstance(response.get("documentos"), list):
        raise TRT12AdapterError("official detail response must contain documentos")
    documents = response["documentos"]
    if len(documents) != 1:
        raise TRT12AdapterError("official detail response must contain one document")
    detail_collection, record = _validate_record(documents[0])
    if detail_collection != collection or _record_id(collection, record) != document_id:
        raise TRT12AdapterError("official detail identity does not match the search result")
    return record


def _sentences(value: str) -> tuple[str, ...]:
    sentences = tuple(" ".join(item.split()) for item in SENTENCE_PATTERN.findall(value))
    if not sentences:
        raise TRT12AdapterError("official excerpt must contain at least one sentence")
    return sentences


def _iso_timestamp(value: datetime) -> str:
    rendered = value.isoformat(timespec="seconds")
    return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered


def build_precedent_corpus(sources: tuple[ResearchSource, ...]) -> dict:
    """Build a deterministic corpus from fetched TRT12 jurisprudence sources."""
    if not isinstance(sources, tuple):
        raise TRT12AdapterError("sources must be a tuple")
    by_id = {}
    for source in sources:
        if not isinstance(source, ResearchSource):
            raise TRT12AdapterError("corpus source has an invalid type")
        if source.source_id in by_id:
            raise TRT12AdapterError("corpus source_id values must be unique")
        by_id[source.source_id] = {
            "source_id": source.source_id,
            "origin": source.origin,
            "type": "persuasive_jurisprudence",
            "reference": source.reference,
            "status": source.status,
            "status_notes": list(source.status_notes),
            "binding_scope": source.binding_scope,
            "legal_question": source.legal_question,
            "holding": source.holding,
            "verbatim_excerpt": source.verbatim_excerpt,
            "official_url": source.official_url,
            "retrieved_at": source.retrieved_at,
        }
    return {
        "schema_version": 1,
        "sources": [by_id[source_id] for source_id in sorted(by_id)],
    }


def collect_precedent_corpus(
    adapter: TRT12OfficialAdapter,
    *,
    tribunal_code: str,
    query: str,
    limit: int,
) -> dict:
    """Collect a bounded set of official TRT12 sources into one corpus."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise TRT12AdapterError("limit must be between 1 and 100")
    sources = []
    cursor = None
    seen_cursors = set()
    while len(sources) < limit:
        page = adapter.search(
            ResearchQuery(
                tribunal_code=tribunal_code,
                source=SOURCE_NAME,
                query=query,
                cursor=cursor,
            )
        )
        for hit in page.items:
            if len(sources) >= limit:
                break
            sources.append(
                adapter.fetch_source(
                    ResearchFetchRequest(
                        tribunal_code=tribunal_code,
                        source=SOURCE_NAME,
                        source_id=hit.source_id,
                    )
                )
            )
        if page.complete:
            break
        if page.next_cursor in seen_cursors:
            raise TRT12AdapterError("official search repeated a pagination cursor")
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    return build_precedent_corpus(tuple(sources))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a bounded corpus from official TRT12 PJe jurisprudence.",
    )
    parser.add_argument("--query", required=True, help="Terms sent to Falcão")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    parser.add_argument("--tribunal-code", default="TRT12")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument(
        "--schema",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "runtime"
            / "contracts"
            / "schemas"
            / "precedent-corpus.v1.schema.json"
        ),
    )
    return parser


def main(argv: list[str] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        adapter = TRT12OfficialAdapter(
            transport=UrllibFalcaoTransport(),
            page_size=args.page_size,
        )
        corpus = collect_precedent_corpus(
            adapter,
            tribunal_code=args.tribunal_code,
            query=args.query,
            limit=args.limit,
        )
        schema = load_json(args.schema, "precedent corpus schema")
        if validate_schema_value(corpus, schema):
            raise TRT12AdapterError("generated precedent corpus violates its schema")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, TRT12AdapterError) as error:
        print(f"[ERROR] TRT12 official adapter: {error}", file=sys.stderr)
        return 2
    print(f"[OK] TRT12 official adapter: {len(corpus['sources'])} source(s) written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
