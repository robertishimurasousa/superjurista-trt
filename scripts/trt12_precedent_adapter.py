#!/usr/bin/env python3
"""Official TRT12 regional-precedent adapter for the shared research contract."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
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


SOURCE_NAME = "trt12_precedents"
TRACKER_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1ViUtXjLrsOypfuG8UBTPx80n2OGUQpTRdtmz4zBv4bk/gviz/tq?tqx=out:csv"
)
THESES_URL = "https://portal.trt12.jus.br/teses-juridicas"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
IAC_EMPTY_STATEMENT = "Ainda não há tese jurídica firmada em IAC."
IRDR_NUMBER_PATTERN = re.compile(r"[0-9]{6,7}-[0-9]{2}\.[0-9]{4}\.5\.12\.[0-9]{4}")
IUJ_HEADER_PATTERN = re.compile(
    r"TESE JUR[IÍ]DICA\s+N[.º°\s]*\s*(?P<number>[0-9]+)\s+EM\s+IUJ",
    flags=re.IGNORECASE,
)


class TRT12PrecedentError(ValueError):
    """Raised when an official TRT12 precedent source cannot be normalized safely."""


class TRT12PrecedentTransport(Protocol):
    def get_text(self, url: str, *, max_bytes: int) -> str:
        ...


class UrllibTRT12PrecedentTransport:
    """Bounded HTTPS transport restricted to the two TRT12-published sources."""

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout: int = 20,
    ) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            raise TRT12PrecedentError("timeout must be a positive integer")
        self.opener = opener
        self.timeout = timeout

    def get_text(self, url: str, *, max_bytes: int) -> str:
        _validate_publication_url(url)
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise TRT12PrecedentError("max_bytes must be a positive integer")
        request = Request(
            url,
            headers={
                "Accept": "text/csv,text/html;q=0.9",
                "User-Agent": "SuperJurista-TRT/1.0 official-source-adapter",
            },
            method="GET",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                _validate_publication_url(response.geturl())
                body = response.read(max_bytes + 1)
        except (HTTPError, URLError, TimeoutError) as error:
            raise TRT12PrecedentError(
                "official TRT12 precedent source request failed"
            ) from error
        if len(body) > max_bytes:
            raise TRT12PrecedentError(
                "official TRT12 precedent response exceeded the size limit"
            )
        try:
            return body.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise TRT12PrecedentError(
                "official TRT12 precedent response is not valid UTF-8"
            ) from error


@dataclass(frozen=True)
class TRT12PrecedentCoverage:
    iac_status: str
    iac_statement: str
    official_url: str


@dataclass(frozen=True)
class _CatalogRecord:
    source_id: str
    incident_type: str
    reference: str
    status: str
    status_notes: tuple[str, ...]
    binding_scope: str
    legal_question: str
    holding: str
    verbatim_excerpt: str
    official_url: str


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[tuple[str, tuple[tuple[str, ...], ...]]] = []
        self._in_table = False
        self._in_caption = False
        self._in_row = False
        self._in_cell = False
        self._caption_parts: list[str] = []
        self._cell_parts: list[str] = []
        self._row: list[str] = []
        self._rows: list[tuple[str, ...]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self._in_table:
                raise TRT12PrecedentError("official thesis page contains nested tables")
            self._in_table = True
            self._caption_parts = []
            self._rows = []
        elif self._in_table and tag == "caption":
            self._in_caption = True
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._row = []
        elif self._in_row and tag in {"td", "th"}:
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_cell and tag in {"td", "th"}:
            self._row.append(_normalize_text(" ".join(self._cell_parts)))
            self._in_cell = False
            self._cell_parts = []
        elif self._in_row and tag == "tr":
            if any(self._row):
                self._rows.append(tuple(self._row))
            self._in_row = False
            self._row = []
        elif self._in_caption and tag == "caption":
            self._in_caption = False
        elif self._in_table and tag == "table":
            caption = _normalize_text(" ".join(self._caption_parts))
            self.tables.append((caption, tuple(self._rows)))
            self._in_table = False
            self._caption_parts = []
            self._rows = []

    def handle_data(self, data: str) -> None:
        if self._in_caption:
            self._caption_parts.append(data)
        if self._in_cell:
            self._cell_parts.append(data)


class TRT12PrecedentAdapter:
    """Normalize TRT12 IRDR, IAC coverage, and regional legal theses."""

    descriptor = AdapterDescriptor(
        provider_id="trt12-precedents-official",
        interface_id="legal_research",
        interface_version=1,
        capabilities=("search", "fetch_source"),
        supported_tribunals=("TRT12",),
    )

    def __init__(
        self,
        *,
        transport: TRT12PrecedentTransport,
        page_size: int = 20,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            raise TRT12PrecedentError("page_size must be an integer")
        if not 1 <= page_size <= 100:
            raise TRT12PrecedentError("page_size must be between 1 and 100")
        self.transport = transport
        self.page_size = page_size
        self.clock = clock
        self._catalog: dict[str, _CatalogRecord] | None = None
        self._coverage: TRT12PrecedentCoverage | None = None

    def search(self, request: ResearchQuery) -> ResearchPage:
        _validate_request_scope(request.tribunal_code, request.source)
        query = _require_text(request.query, "query")
        offset = _parse_cursor(request.cursor)
        catalog = self._load_catalog()
        query_key = _search_key(query)
        matching = sorted(
            (
                record
                for record in catalog.values()
                if query_key in _searchable_text(record)
            ),
            key=lambda record: record.source_id,
        )
        page_records = matching[offset : offset + self.page_size]
        next_offset = offset + len(page_records)
        complete = next_offset >= len(matching)
        return ResearchPage(
            items=tuple(_hit(record) for record in page_records),
            next_cursor=None if complete else str(next_offset),
            complete=complete,
        )

    def fetch_source(self, request: ResearchFetchRequest) -> ResearchSource:
        _validate_request_scope(request.tribunal_code, request.source)
        previous = self._load_catalog().get(request.source_id)
        if previous is None:
            raise TRT12PrecedentError(
                "source_id must come from a completed adapter search"
            )
        record = self._load_catalog(refresh=True).get(request.source_id)
        if record is None:
            raise TRT12PrecedentError(
                "official source no longer contains the selected precedent"
            )
        if record.official_url != previous.official_url:
            raise TRT12PrecedentError("official source URL changed during retrieval")
        retrieved_at = self.clock()
        if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None:
            raise TRT12PrecedentError("clock must return a timezone-aware datetime")
        return ResearchSource(
            source_id=record.source_id,
            origin="TRT12",
            reference=record.reference,
            status=record.status,
            status_notes=record.status_notes,
            binding_scope=record.binding_scope,
            legal_question=record.legal_question,
            holding=record.holding,
            verbatim_excerpt=record.verbatim_excerpt,
            official_url=record.official_url,
            retrieved_at=_iso_timestamp(retrieved_at),
        )

    def coverage(self) -> TRT12PrecedentCoverage:
        """Return explicit IAC publication coverage without fabricating a precedent."""
        self._load_catalog()
        if self._coverage is None:
            raise TRT12PrecedentError("TRT12 precedent coverage was not initialized")
        return self._coverage

    def _load_catalog(self, *, refresh: bool = False) -> dict[str, _CatalogRecord]:
        if self._catalog is not None and not refresh:
            return self._catalog
        tracker = self.transport.get_text(
            TRACKER_URL,
            max_bytes=MAX_RESPONSE_BYTES,
        )
        thesis_page = self.transport.get_text(
            THESES_URL,
            max_bytes=MAX_RESPONSE_BYTES,
        )
        records = _parse_irdr_tracker(tracker)
        iuj_records, coverage = _parse_thesis_page(thesis_page)
        for record in iuj_records:
            if record.source_id in records:
                raise TRT12PrecedentError("official sources repeated a source identifier")
            records[record.source_id] = record
        self._catalog = records
        self._coverage = coverage
        return records


def _validate_publication_url(value: object) -> None:
    if not isinstance(value, str):
        raise TRT12PrecedentError("request URL must use an approved official publication")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise TRT12PrecedentError("request URL must use an approved official publication")
    if (
        parsed.hostname == "portal.trt12.jus.br"
        and parsed.path == "/teses-juridicas"
        and not parsed.query
    ):
        return
    tracker_path = (
        "/spreadsheets/d/1ViUtXjLrsOypfuG8UBTPx80n2OGUQpTRdtmz4zBv4bk/gviz/tq"
    )
    if (
        parsed.hostname == "docs.google.com"
        and parsed.path == tracker_path
        and parse_qs(parsed.query, keep_blank_values=True) == {"tqx": ["out:csv"]}
    ):
        return
    raise TRT12PrecedentError("request URL must use an approved official publication")


def _validate_request_scope(tribunal_code: object, source: object) -> None:
    if tribunal_code != "TRT12":
        raise TRT12PrecedentError("TRT12 precedent adapter requires tribunal_code TRT12")
    if source != SOURCE_NAME:
        raise TRT12PrecedentError(f"source must be {SOURCE_NAME}")


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TRT12PrecedentError(f"{label} must be a non-empty string")
    return value.strip()


def _parse_cursor(value: object) -> int:
    if value is None:
        return 0
    if not isinstance(value, str) or not value.isdigit():
        raise TRT12PrecedentError("cursor must be a non-negative integer string")
    return int(value)


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        raise TRT12PrecedentError("official precedent field must be text")
    return " ".join(value.replace("\xa0", " ").split())


def _search_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", _normalize_text(value))
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).casefold()


def _parse_irdr_tracker(value: str) -> dict[str, _CatalogRecord]:
    try:
        rows = list(csv.reader(io.StringIO(value)))
    except csv.Error as error:
        raise TRT12PrecedentError("official IRDR tracker is not valid CSV") from error
    required = (
        "Tema (TRT12)",
        "Número do IRDR",
        "Questão submetida  a julgamento",
        "Situação do tema",
        "Tese firmada",
    )
    header_match = next(
        (
            (index, row, _tracker_header_positions(row, required))
            for index, row in enumerate(rows)
            if _tracker_header_positions(row, required) is not None
        ),
        None,
    )
    if header_match is None:
        raise TRT12PrecedentError("official IRDR tracker header is missing")
    header_index, header, positions = header_match
    records: dict[str, _CatalogRecord] = {}
    for row in rows[header_index + 1 :]:
        if len(row) != len(header):
            raise TRT12PrecedentError("official IRDR tracker row width changed")
        theme_match = re.match(r"\s*([0-9]+)", row[positions["Tema (TRT12)"]])
        if theme_match is None:
            continue
        theme = int(theme_match.group(1))
        source_id = f"TRT12IRDR-{theme:03d}"
        if source_id in records:
            raise TRT12PrecedentError("official IRDR tracker repeated a theme")
        records[source_id] = _irdr_record(
            theme=theme,
            theme_cell=row[positions["Tema (TRT12)"]],
            incident_number=row[positions["Número do IRDR"]],
            question=row[positions["Questão submetida  a julgamento"]],
            tracker_status=row[positions["Situação do tema"]],
            thesis=row[positions["Tese firmada"]],
        )
    if not records:
        raise TRT12PrecedentError("official IRDR tracker contains no incidents")
    return records


def _tracker_header_positions(
    row: list[str],
    required: tuple[str, ...],
) -> dict[str, int] | None:
    positions = {}
    for name in required:
        normalized_name = _normalize_text(name)
        matches = [
            index
            for index, cell in enumerate(row)
            if _normalize_text(cell) == normalized_name
            or _normalize_text(cell).endswith(f" {normalized_name}")
        ]
        if len(matches) != 1:
            return None
        positions[name] = matches[0]
    return positions


def _irdr_record(
    *,
    theme: int,
    theme_cell: str,
    incident_number: str,
    question: str,
    tracker_status: str,
    thesis: str,
) -> _CatalogRecord:
    number_match = IRDR_NUMBER_PATTERN.search(_normalize_text(incident_number))
    if number_match is None:
        raise TRT12PrecedentError("official IRDR tracker has an invalid incident number")
    normalized_question = _require_text(_normalize_text(question), "IRDR legal question")
    normalized_status = _require_text(
        _normalize_text(tracker_status),
        "IRDR tracker status",
    )
    normalized_thesis = _normalize_text(thesis)
    if _search_key(normalized_thesis) in {"", "xxxxx"}:
        normalized_thesis = ""
    classification_text = _search_key(f"{theme_cell} {normalized_thesis}")
    status_key = _search_key(normalized_status)
    cancelled = "cancel" in classification_text
    suspension_scope = _suspension_scope(status_key)
    suspension_active = bool(
        not normalized_thesis
        and suspension_scope not in {"none", "not_reported"}
    )
    if cancelled:
        status = "cancelled"
    elif normalized_thesis:
        status = "current"
    elif suspension_active:
        status = "stayed"
    elif "admitido" in status_key:
        status = "pending"
    else:
        status = "unknown"
    if suspension_scope == "none":
        suspension_note = "Suspension: none, as explicitly reported by the tracker."
    elif suspension_scope == "not_reported":
        suspension_note = "Suspension: not reported by the tracker."
    else:
        state = "active" if suspension_active else "historical"
        suspension_note = f"Suspension: {state}; scope: {suspension_scope}."
    holding = normalized_thesis or (
        "No legal thesis is published for this incident in the official tracker."
    )
    excerpt_parts = [normalized_question, normalized_status]
    if normalized_thesis:
        excerpt_parts.append(normalized_thesis)
    return _CatalogRecord(
        source_id=f"TRT12IRDR-{theme:03d}",
        incident_type="IRDR",
        reference=f"TRT12 IRDR theme {theme}; {number_match.group(0)}",
        status=status,
        status_notes=(
            "Incident type: IRDR.",
            f"Official tracker status: {normalized_status}",
            suspension_note,
        ),
        binding_scope="trt12_regional_jurisdiction",
        legal_question=normalized_question,
        holding=holding,
        verbatim_excerpt=" ".join(excerpt_parts),
        official_url=TRACKER_URL,
    )


def _suspension_scope(status_key: str) -> str:
    if "nao determinada suspensao" in status_key:
        return "none"
    if "suspensao" not in status_key:
        return "not_reported"
    has_first = "primeira instancia" in status_key
    has_second = "segunda instancia" in status_key
    if has_first and has_second:
        return "trt12_first_and_second_instances"
    if has_second:
        return "trt12_second_instance"
    if has_first:
        return "trt12_first_instance"
    return "trt12_regional_scope_unspecified"


def _parse_thesis_page(
    value: str,
) -> tuple[tuple[_CatalogRecord, ...], TRT12PrecedentCoverage]:
    parser = _TableParser()
    try:
        parser.feed(value)
        parser.close()
    except (TRT12PrecedentError, ValueError) as error:
        if isinstance(error, TRT12PrecedentError):
            raise
        raise TRT12PrecedentError("official TRT12 thesis page is invalid HTML") from error
    iac_rows = _find_table(parser.tables, "ASSUNÇÃO DE COMPETÊNCIA")
    iac_text = _normalize_text(" ".join(cell for row in iac_rows for cell in row))
    if IAC_EMPTY_STATEMENT not in iac_text:
        raise TRT12PrecedentError(
            "official TRT12 thesis page no longer confirms IAC coverage"
        )
    iuj_rows = _find_table(parser.tables, "UNIFORMIZAÇÃO DE JURISPRUDÊNCIA")
    records = []
    index = 0
    while index < len(iuj_rows):
        header = _normalize_text(" ".join(iuj_rows[index]))
        match = IUJ_HEADER_PATTERN.search(header)
        if match is None:
            index += 1
            continue
        if index + 1 >= len(iuj_rows):
            raise TRT12PrecedentError("official IUJ thesis body is missing")
        body = _normalize_text(" ".join(iuj_rows[index + 1]))
        records.append(_iuj_record(int(match.group("number")), header, body))
        index += 2
    if not records:
        raise TRT12PrecedentError("official TRT12 thesis page contains no IUJ theses")
    return (
        tuple(records),
        TRT12PrecedentCoverage(
            iac_status="none_published",
            iac_statement=IAC_EMPTY_STATEMENT,
            official_url=THESES_URL,
        ),
    )


def _find_table(
    tables: list[tuple[str, tuple[tuple[str, ...], ...]]],
    caption_fragment: str,
) -> tuple[tuple[str, ...], ...]:
    fragment_key = _search_key(caption_fragment)
    matches = [rows for caption, rows in tables if fragment_key in _search_key(caption)]
    if len(matches) != 1:
        raise TRT12PrecedentError(
            "official TRT12 thesis page has ambiguous precedent tables"
        )
    return matches[0]


def _iuj_record(number: int, header: str, body: str) -> _CatalogRecord:
    if not body:
        raise TRT12PrecedentError("official IUJ thesis text is empty")
    holding = re.split(
        r"\s+\(?Resolu[cç][aã]o\)?|\s+Ver:\s*|\s+OBS\.:\s*",
        body,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    if not holding:
        raise TRT12PrecedentError("official IUJ holding is empty")
    first_sentence = re.match(r".+?[.!?](?:\s|$)", holding)
    legal_question = (
        first_sentence.group(0).strip() if first_sentence is not None else holding
    )
    cancelled = "cancel" in _search_key(f"{header} {body}")
    status = "cancelled" if cancelled else "current"
    return _CatalogRecord(
        source_id=f"TRT12IUJ-{number:03d}",
        incident_type="IUJ",
        reference=f"TRT12 legal thesis {number} in IUJ",
        status=status,
        status_notes=(
            "Incident type: IUJ.",
            (
                "The official TRT12 thesis page marks this thesis as cancelled."
                if cancelled
                else "The official TRT12 thesis page publishes this thesis without a cancellation marker."
            ),
            "Suspension: not applicable to the published IUJ thesis record.",
        ),
        binding_scope="trt12_regional_jurisdiction",
        legal_question=legal_question,
        holding=holding,
        verbatim_excerpt=holding,
        official_url=THESES_URL,
    )


def _searchable_text(record: _CatalogRecord) -> str:
    return _search_key(
        " ".join(
            (
                "TRT12",
                record.incident_type,
                record.reference,
                record.legal_question,
                record.holding,
                record.verbatim_excerpt,
            )
        )
    )


def _hit(record: _CatalogRecord) -> ResearchHit:
    return ResearchHit(
        source_id=record.source_id,
        origin="TRT12",
        reference=record.reference,
        status=record.status,
        official_url=record.official_url,
    )


def _iso_timestamp(value: datetime) -> str:
    rendered = value.isoformat(timespec="seconds")
    return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered


def build_precedent_corpus(sources: tuple[ResearchSource, ...]) -> dict:
    """Build a deterministic precedent corpus from official TRT12 records."""
    if not isinstance(sources, tuple):
        raise TRT12PrecedentError("sources must be a tuple")
    by_id = {}
    for source in sources:
        if not isinstance(source, ResearchSource):
            raise TRT12PrecedentError("corpus source has an invalid type")
        if source.source_id in by_id:
            raise TRT12PrecedentError("corpus source_id values must be unique")
        source_type = (
            "binding_precedent"
            if source.source_id.startswith("TRT12IRDR-")
            else "orientation"
        )
        by_id[source.source_id] = {
            "source_id": source.source_id,
            "origin": source.origin,
            "type": source_type,
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
    adapter: TRT12PrecedentAdapter,
    *,
    tribunal_code: str,
    query: str,
    limit: int,
) -> dict:
    """Collect a bounded set of official TRT12 precedents."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise TRT12PrecedentError("limit must be between 1 and 100")
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
            raise TRT12PrecedentError("official search repeated a pagination cursor")
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    return build_precedent_corpus(tuple(sources))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a bounded corpus from official TRT12 precedent sources.",
    )
    parser.add_argument("--query", required=True)
    parser.add_argument("--output", required=True, type=Path)
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
        adapter = TRT12PrecedentAdapter(
            transport=UrllibTRT12PrecedentTransport(),
            page_size=args.page_size,
        )
        corpus = collect_precedent_corpus(
            adapter,
            tribunal_code=args.tribunal_code,
            query=args.query,
            limit=args.limit,
        )
        schema = load_json(args.schema, "precedent corpus schema")
        errors = validate_schema_value(corpus, schema)
        if errors:
            raise TRT12PrecedentError("; ".join(errors))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, TRT12PrecedentError) as error:
        print(f"TRT12 precedent adapter failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Wrote {len(corpus['sources'])} official TRT12 precedent source(s) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
