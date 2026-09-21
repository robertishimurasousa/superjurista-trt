#!/usr/bin/env python3
"""Official TST jurisprudence adapter for the shared legal-research contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
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


SEARCH_BASE_URL = "https://jurisprudencia-backend.tst.jus.br/rest/pesquisa-textual"
DOCUMENT_BASE_URL = "https://jurisprudencia-backend.tst.jus.br/rest/documentos"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
SOURCE_NAME = "tst_precedents"
OFFICIAL_HOST = "jurisprudencia-backend.tst.jus.br"
DOCUMENT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
PUBLICATION_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
SENTENCE_PATTERN = re.compile(r"[^.!?]+[.!?]")
CNJ_NUMBER_PATTERN = re.compile(
    r"(?P<numero>[0-9]{7})-(?P<digito>[0-9]{2})\."
    r"(?P<ano>[0-9]{4})\.(?P<orgao>[0-9])\."
    r"(?P<tribunal>[0-9]{2})\.(?P<vara>[0-9]{4})"
)


class TSTAdapterError(ValueError):
    """Raised when the official response cannot be normalized safely."""


class TSTTransport(Protocol):
    def post_json(self, url: str, payload: dict, *, max_bytes: int) -> dict:
        ...

    def get_text(self, url: str, *, max_bytes: int) -> str:
        ...


class UrllibTSTTransport:
    """Bounded HTTPS transport restricted to the public TST backend."""

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout: int = 20,
    ) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            raise TSTAdapterError("timeout must be a positive integer")
        self.opener = opener
        self.timeout = timeout

    def post_json(self, url: str, payload: dict, *, max_bytes: int) -> dict:
        if not isinstance(payload, dict):
            raise TSTAdapterError("JSON request payload must be an object")
        request = Request(
            url,
            data=json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "SuperJurista-TRT/1.0 official-source-adapter",
            },
            method="POST",
        )
        body = self._read(request, max_bytes=max_bytes)
        try:
            response = json.loads(body)
        except json.JSONDecodeError as error:
            raise TSTAdapterError("official TST response is not valid JSON") from error
        if not isinstance(response, dict):
            raise TSTAdapterError("official TST JSON response must be an object")
        return response

    def get_text(self, url: str, *, max_bytes: int) -> str:
        request = Request(
            url,
            headers={
                "Accept": "text/html",
                "User-Agent": "SuperJurista-TRT/1.0 official-source-adapter",
            },
            method="GET",
        )
        return self._read(request, max_bytes=max_bytes)

    def _read(self, request: Request, *, max_bytes: int) -> str:
        _validate_official_url(request.full_url)
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise TSTAdapterError("max_bytes must be a positive integer")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                _validate_official_url(response.geturl())
                body = response.read(max_bytes + 1)
        except (HTTPError, URLError, TimeoutError) as error:
            raise TSTAdapterError("official TST source request failed") from error
        if len(body) > max_bytes:
            raise TSTAdapterError("official TST response exceeded the size limit")
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TSTAdapterError("official TST response is not valid UTF-8") from error

class TSTOfficialAdapter:
    """Normalize the public TST jurisprudence search into shared records."""

    descriptor = AdapterDescriptor(
        provider_id="tst-official",
        interface_id="legal_research",
        interface_version=1,
        capabilities=("search", "fetch_source"),
        supported_tribunals=tuple(f"TRT{number}" for number in range(1, 25)),
    )

    def __init__(
        self,
        *,
        transport: TSTTransport,
        page_size: int = 20,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            raise TSTAdapterError("page_size must be an integer")
        if page_size < 1 or page_size > 100:
            raise TSTAdapterError("page_size must be between 1 and 100")
        self.transport = transport
        self.page_size = page_size
        self.clock = clock
        self._records: dict[str, dict[str, Any]] = {}

    def search(self, request: ResearchQuery) -> ResearchPage:
        _validate_source(request.source)
        query = _require_text(request.query, "query")
        start = _parse_cursor(request.cursor)
        url = f"{SEARCH_BASE_URL}/{start}/{self.page_size}"
        response = self.transport.post_json(
            url,
            _search_payload(query),
            max_bytes=MAX_RESPONSE_BYTES,
        )
        total, records = _validate_search_response(response)
        hits = []
        for wrapper in records:
            record = _validate_record(wrapper)
            source_id = f"TST-{record['numProcDocumento']}"
            self._records[source_id] = record
            hits.append(
                ResearchHit(
                    source_id=source_id,
                    origin="TST",
                    reference=_reference(record),
                    status="unknown",
                    official_url=f"{DOCUMENT_BASE_URL}/{record['id']}",
                )
            )
        if not hits and start <= total:
            raise TSTAdapterError("official search returned an empty page before completion")
        next_start = start + len(hits)
        complete = next_start > total
        return ResearchPage(
            items=tuple(hits),
            next_cursor=None if complete else str(next_start),
            complete=complete,
        )

    def fetch_source(self, request: ResearchFetchRequest) -> ResearchSource:
        _validate_source(request.source)
        record = self._records.get(request.source_id)
        if record is None:
            raise TSTAdapterError("source_id must come from a completed adapter search")
        official_url = f"{DOCUMENT_BASE_URL}/{record['id']}"
        document = self.transport.get_text(
            official_url,
            max_bytes=MAX_RESPONSE_BYTES,
        )
        excerpt = _normalize_text(record["ementa"])
        official_text = _html_text(document)
        if excerpt not in official_text:
            raise TSTAdapterError(
                "official document does not preserve verbatim custody for the excerpt"
            )
        retrieved_at = self.clock()
        if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None:
            raise TSTAdapterError("clock must return a timezone-aware datetime")
        return ResearchSource(
            source_id=request.source_id,
            origin="TST",
            reference=_reference(record),
            status="unknown",
            status_notes=(
                "The TST search response does not expose a normalized precedential "
                "status; human verification is required.",
            ),
            binding_scope="national_labor_justice",
            legal_question=_legal_question(excerpt),
            holding=_holding(excerpt),
            verbatim_excerpt=excerpt,
            official_url=official_url,
            retrieved_at=_iso_timestamp(retrieved_at),
        )


def _search_payload(query: str) -> dict:
    case_number = CNJ_NUMBER_PATTERN.fullmatch(query)
    return {
        "ou": "",
        "e": "" if case_number is not None else query,
        "termoExato": "",
        "naoContem": "",
        "ementa": "",
        "dispositivo": "",
        "numeracaoUnica": {
            "numero": case_number.group("numero") if case_number else "",
            "ano": case_number.group("ano") if case_number else "",
            "digito": case_number.group("digito") if case_number else "",
            "orgao": case_number.group("orgao") if case_number else "5",
            "tribunal": case_number.group("tribunal") if case_number else "",
            "vara": case_number.group("vara") if case_number else "",
        },
        "orgaosJudicantes": [],
        "ministros": [],
        "convocados": [],
        "classesProcessuais": [],
        "codigosClassesPrecedentes": [],
        "indicadores": [],
        "assuntos": [],
        "tipos": ["ACORDAO"],
        "orgao": "TST",
        "publicacaoInicial": None,
        "publicacaoFinal": None,
        "julgamentoInicial": None,
        "julgamentoFinal": None,
        "ordenacao": "data",
    }


def _reference(record: dict) -> str:
    return (
        f"{record['numFormatado']}; "
        f"{record['orgaoJudicante']['descricao']}; "
        f"DEJT {record['dtaPublicacao']}"
    )


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TSTAdapterError(f"{label} must be a non-empty string")
    return value.strip()


def _validate_official_url(value: object) -> None:
    if not isinstance(value, str):
        raise TSTAdapterError("request URL must use the official TST host")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != OFFICIAL_HOST
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise TSTAdapterError("request URL must use the official TST host")


def _validate_source(source: object) -> None:
    if source != SOURCE_NAME:
        raise TSTAdapterError(f"source must be {SOURCE_NAME}")


def _parse_cursor(cursor: object) -> int:
    if cursor is None:
        return 1
    if not isinstance(cursor, str) or not cursor.isdigit() or int(cursor) < 1:
        raise TSTAdapterError("cursor must be a positive decimal offset")
    return int(cursor)


def _validate_search_response(response: object) -> tuple[int, list]:
    if not isinstance(response, dict):
        raise TSTAdapterError("official search response must be an object")
    total = response.get("totalRegistros")
    records = response.get("registros")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise TSTAdapterError("official search totalRegistros must be non-negative")
    if not isinstance(records, list):
        raise TSTAdapterError("official search registros must be an array")
    return total, records


def _validate_record(wrapper: object) -> dict:
    if not isinstance(wrapper, dict) or not isinstance(wrapper.get("registro"), dict):
        raise TSTAdapterError("official search item must contain a registro object")
    record = dict(wrapper["registro"])
    document_id = record.get("id")
    source_number = record.get("numProcDocumento")
    if not isinstance(document_id, str) or DOCUMENT_ID_PATTERN.fullmatch(document_id) is None:
        raise TSTAdapterError("official result id must be a lowercase 32-character digest")
    if (
        isinstance(source_number, bool)
        or not isinstance(source_number, int)
        or source_number < 100
    ):
        raise TSTAdapterError("official result numProcDocumento must be a stable number")
    _require_text(record.get("numFormatado"), "official result numFormatado")
    _require_text(record.get("ementa"), "official result ementa")
    origin = record.get("orgao")
    if not isinstance(origin, dict) or origin.get("sigla") != "TST":
        raise TSTAdapterError("official result origin must be TST")
    result_type = record.get("tipo")
    if (
        not isinstance(result_type, dict)
        or result_type.get("codigoTipoJurisprudencia") != "ACORDAO"
    ):
        raise TSTAdapterError("official result type must be ACORDAO")
    record["dtaPublicacao"] = _publication_date(record.get("dtaPublicacao"))
    adjudicating_body = record.get("orgaoJudicante")
    if not isinstance(adjudicating_body, dict):
        raise TSTAdapterError("official result orgaoJudicante must be an object")
    _require_text(adjudicating_body.get("descricao"), "official result adjudicating body")
    return record


def _publication_date(value: object) -> str:
    if not isinstance(value, str):
        raise TSTAdapterError("official result dtaPublicacao must be a date")
    if PUBLICATION_DATE_PATTERN.fullmatch(value) is not None:
        return value
    normalized = re.sub(r"([+-][0-9]{2})$", r"\1:00", value)
    try:
        timestamp = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise TSTAdapterError(
            "official result dtaPublicacao must be a date or zoned timestamp"
        ) from error
    if timestamp.tzinfo is None:
        raise TSTAdapterError(
            "official result dtaPublicacao timestamp must include a timezone"
        )
    return timestamp.date().isoformat()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _html_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TSTAdapterError("official document must contain HTML text")
    parser = _TextExtractor()
    parser.feed(value)
    return _normalize_text(" ".join(parser.parts))


def _sentences(value: str) -> tuple[str, ...]:
    sentences = tuple(_normalize_text(item) for item in SENTENCE_PATTERN.findall(value))
    if not sentences:
        raise TSTAdapterError("official ementa must contain at least one sentence")
    return sentences


def _legal_question(excerpt: str) -> str:
    sentences = _sentences(excerpt)
    return next((sentence for sentence in sentences if sentence.endswith("?")), sentences[0])


def _holding(excerpt: str) -> str:
    match = re.search(
        r"tese (?:vinculante|obrigat[oó]ria)[^:]*:\s*([^.!?]+[.!?])",
        excerpt,
        flags=re.IGNORECASE,
    )
    if match is not None:
        return _normalize_text(match.group(1))
    return _sentences(excerpt)[-1]


def _iso_timestamp(value: datetime) -> str:
    rendered = value.isoformat(timespec="seconds")
    return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered


def _source_type(source: ResearchSource) -> str:
    excerpt = source.verbatim_excerpt.upper()
    if "INCIDENTE DE RECURSO REPETITIVO" in excerpt:
        return "qualified_precedent"
    return "jurisprudence"


def build_precedent_corpus(sources: tuple[ResearchSource, ...]) -> dict:
    """Build a deterministic precedent-corpus artifact from fetched TST sources."""
    if not isinstance(sources, tuple):
        raise TSTAdapterError("sources must be a tuple")
    by_id = {}
    for source in sources:
        if not isinstance(source, ResearchSource):
            raise TSTAdapterError("corpus source has an invalid type")
        if source.source_id in by_id:
            raise TSTAdapterError("corpus source_id values must be unique")
        by_id[source.source_id] = {
            "source_id": source.source_id,
            "origin": source.origin,
            "type": _source_type(source),
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
    adapter: TSTOfficialAdapter,
    *,
    tribunal_code: str,
    query: str,
    limit: int,
) -> dict:
    """Collect a bounded set of official TST sources into one corpus."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise TSTAdapterError("limit must be between 1 and 100")
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
            raise TSTAdapterError("official search repeated a pagination cursor")
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    return build_precedent_corpus(tuple(sources))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a bounded precedent corpus from the official TST source.",
    )
    parser.add_argument("--query", required=True, help="Terms sent to the TST search")
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
        adapter = TSTOfficialAdapter(
            transport=UrllibTSTTransport(),
            page_size=args.page_size,
        )
        corpus = collect_precedent_corpus(
            adapter,
            tribunal_code=args.tribunal_code,
            query=args.query,
            limit=args.limit,
        )
        schema = load_json(args.schema, "precedent corpus schema")
        issues = validate_schema_value(corpus, schema)
        if issues:
            raise TSTAdapterError("generated precedent corpus violates its schema")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, TSTAdapterError) as error:
        print(f"[ERROR] TST official adapter: {error}", file=sys.stderr)
        return 2
    print(
        f"[OK] TST official adapter: {len(corpus['sources'])} source(s) written",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
