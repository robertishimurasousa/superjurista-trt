from __future__ import annotations

import importlib
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PRECEDENT_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "precedent-corpus.v1.schema.json"
)


class SearchTransport:
    def post_json(self, url, payload, *, max_bytes):
        self.request = (url, payload, max_bytes)
        return {
            "totalRegistros": 1,
            "registros": [
                {
                    "registro": {
                        "id": "7a2d741d22e82084a45f85ba428fa103",
                        "numProcDocumento": 93805024,
                        "numFormatado": "RR - 0021532-54.2015.5.04.0006",
                        "tipo": {
                            "codigoTipoJurisprudencia": "ACORDAO",
                            "nome": "Acordão",
                        },
                        "orgao": {
                            "numero": 0,
                            "nome": "Tribunal Superior do Trabalho",
                            "sigla": "TST",
                        },
                        "orgaoJudicante": {
                            "codigo": 23,
                            "descricao": "Tribunal Pleno",
                        },
                        "nomRelator": "aloysio silva correa da veiga",
                        "dtaJulgamento": "2025-06-30",
                        "dtaPublicacao": "2025-07-01",
                        "ementa": (
                            "INCIDENTE DE RECURSO REPETITIVO. HORAS EXTRAS. "
                            "São devidas as parcelas vincendas."
                        ),
                        "dispositivo": "Recurso conhecido e provido.",
                    }
                }
            ],
        }

    def get_text(self, url, *, max_bytes):
        raise AssertionError("search must not fetch the full source")


class SourceTransport(SearchTransport):
    def __init__(self, *, document_text=None) -> None:
        self.document_text = document_text or (
            "<html><body><p>INCIDENTE DE RECURSO REPETITIVO. HORAS EXTRAS. "
            "São devidas as parcelas vincendas.</p></body></html>"
        )

    def get_text(self, url, *, max_bytes):
        self.document_request = (url, max_bytes)
        return self.document_text


class PaginatedTransport(SearchTransport):
    def post_json(self, url, payload, *, max_bytes):
        response = super().post_json(url, payload, max_bytes=max_bytes)
        response["totalRegistros"] = 3
        return response


class TimestampTransport(SearchTransport):
    def post_json(self, url, payload, *, max_bytes):
        response = super().post_json(url, payload, max_bytes=max_bytes)
        response["registros"][0]["registro"]["dtaPublicacao"] = (
            "2026-09-11T07:00:00-03"
        )
        return response


class UnexpectedOriginTransport(SearchTransport):
    def post_json(self, url, payload, *, max_bytes):
        response = super().post_json(url, payload, max_bytes=max_bytes)
        response["registros"][0]["registro"]["orgao"]["sigla"] = "CSJT"
        return response


class HTTPResponse:
    def __init__(self, *, url, body, content_type) -> None:
        self.url = url
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def geturl(self):
        return self.url

    def read(self, amount):
        return self.body[:amount]


class OfficialOpener:
    def __init__(self, response) -> None:
        self.response = response

    def __call__(self, request, *, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


class TSTOfficialAdapterTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("tst_official_adapter")
        except ModuleNotFoundError as error:
            self.fail(f"TST official adapter module is missing: {error}")

    def provider_api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("provider_interfaces")

    def test_search_normalizes_one_official_tst_result(self) -> None:
        module = self.api()
        provider = self.provider_api()
        transport = SearchTransport()
        adapter = module.TSTOfficialAdapter(transport=transport, page_size=2)

        page = adapter.search(
            provider.ResearchQuery(
                tribunal_code="TRT12",
                source="tst_precedents",
                query="horas extras parcelas vincendas",
                cursor=None,
            )
        )

        self.assertEqual(
            page,
            provider.ResearchPage(
                items=(
                    provider.ResearchHit(
                        source_id="TST-93805024",
                        origin="TST",
                        reference=(
                            "RR - 0021532-54.2015.5.04.0006; "
                            "Tribunal Pleno; DEJT 2025-07-01"
                        ),
                        status="unknown",
                        official_url=(
                            "https://jurisprudencia-backend.tst.jus.br/rest/"
                            "documentos/7a2d741d22e82084a45f85ba428fa103"
                        ),
                    ),
                ),
                next_cursor=None,
                complete=True,
            ),
        )
        url, payload, max_bytes = transport.request
        self.assertEqual(
            url,
            "https://jurisprudencia-backend.tst.jus.br/rest/pesquisa-textual/1/2",
        )
        self.assertEqual(payload["e"], "horas extras parcelas vincendas")
        self.assertEqual(payload["tipos"], ["ACORDAO"])
        self.assertEqual(payload["orgao"], "TST")
        self.assertEqual(max_bytes, 8 * 1024 * 1024)

    def test_search_exposes_a_bounded_next_cursor(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TSTOfficialAdapter(
            transport=PaginatedTransport(),
            page_size=2,
        )

        page = adapter.search(
            provider.ResearchQuery(
                tribunal_code="TRT12",
                source="tst_precedents",
                query="horas extras parcelas vincendas",
                cursor=None,
            )
        )

        self.assertFalse(page.complete)
        self.assertEqual(page.next_cursor, "2")

    def test_search_normalizes_timestamp_publication_date(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TSTOfficialAdapter(transport=TimestampTransport())

        page = adapter.search(
            provider.ResearchQuery(
                tribunal_code="TRT12",
                source="tst_precedents",
                query="horas extras",
                cursor=None,
            )
        )

        self.assertEqual(
            page.items[0].reference,
            "RR - 0021532-54.2015.5.04.0006; Tribunal Pleno; DEJT 2026-09-11",
        )

    def test_search_uses_structured_filter_for_an_exact_cnj_number(self) -> None:
        module = self.api()
        provider = self.provider_api()
        transport = SearchTransport()
        adapter = module.TSTOfficialAdapter(transport=transport)

        adapter.search(
            provider.ResearchQuery(
                tribunal_code="TRT12",
                source="tst_precedents",
                query="0021532-54.2015.5.04.0006",
                cursor=None,
            )
        )

        payload = transport.request[1]
        self.assertEqual(payload["e"], "")
        self.assertEqual(
            payload["numeracaoUnica"],
            {
                "numero": "0021532",
                "digito": "54",
                "ano": "2015",
                "orgao": "5",
                "tribunal": "04",
                "vara": "0006",
            },
        )

    def test_search_rejects_a_result_not_identified_as_tst(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TSTOfficialAdapter(transport=UnexpectedOriginTransport())

        with self.assertRaisesRegex(module.TSTAdapterError, "origin must be TST"):
            adapter.search(
                provider.ResearchQuery(
                    tribunal_code="TRT12",
                    source="tst_precedents",
                    query="horas extras",
                    cursor=None,
                )
            )

    def test_fetch_preserves_verbatim_custody_and_builds_precedent_corpus(self) -> None:
        module = self.api()
        provider = self.provider_api()
        transport = SourceTransport()
        adapter = module.TSTOfficialAdapter(
            transport=transport,
            page_size=2,
            clock=lambda: datetime(2026, 9, 21, 21, 0, tzinfo=timezone.utc),
        )
        adapter.search(
            provider.ResearchQuery(
                tribunal_code="TRT12",
                source="tst_precedents",
                query="horas extras parcelas vincendas",
                cursor=None,
            )
        )

        source = adapter.fetch_source(
            provider.ResearchFetchRequest(
                tribunal_code="TRT12",
                source="tst_precedents",
                source_id="TST-93805024",
            )
        )
        corpus = module.build_precedent_corpus((source,))

        self.assertEqual(
            source,
            provider.ResearchSource(
                source_id="TST-93805024",
                origin="TST",
                reference=(
                    "RR - 0021532-54.2015.5.04.0006; "
                    "Tribunal Pleno; DEJT 2025-07-01"
                ),
                status="unknown",
                status_notes=(
                    "The TST search response does not expose a normalized "
                    "precedential status; human verification is required.",
                ),
                binding_scope="national_labor_justice",
                legal_question="INCIDENTE DE RECURSO REPETITIVO.",
                holding="São devidas as parcelas vincendas.",
                verbatim_excerpt=(
                    "INCIDENTE DE RECURSO REPETITIVO. HORAS EXTRAS. "
                    "São devidas as parcelas vincendas."
                ),
                official_url=(
                    "https://jurisprudencia-backend.tst.jus.br/rest/"
                    "documentos/7a2d741d22e82084a45f85ba428fa103"
                ),
                retrieved_at="2026-09-21T21:00:00Z",
            ),
        )
        self.assertEqual(
            corpus,
            {
                "schema_version": 1,
                "sources": [
                    {
                        "source_id": "TST-93805024",
                        "origin": "TST",
                        "type": "qualified_precedent",
                        "reference": (
                            "RR - 0021532-54.2015.5.04.0006; "
                            "Tribunal Pleno; DEJT 2025-07-01"
                        ),
                        "status": "unknown",
                        "status_notes": [
                            "The TST search response does not expose a normalized "
                            "precedential status; human verification is required."
                        ],
                        "binding_scope": "national_labor_justice",
                        "legal_question": "INCIDENTE DE RECURSO REPETITIVO.",
                        "holding": "São devidas as parcelas vincendas.",
                        "verbatim_excerpt": (
                            "INCIDENTE DE RECURSO REPETITIVO. HORAS EXTRAS. "
                            "São devidas as parcelas vincendas."
                        ),
                        "official_url": (
                            "https://jurisprudencia-backend.tst.jus.br/rest/"
                            "documentos/7a2d741d22e82084a45f85ba428fa103"
                        ),
                        "retrieved_at": "2026-09-21T21:00:00Z",
                    }
                ],
            },
        )
        self.assertEqual(
            transport.document_request,
            (
                "https://jurisprudencia-backend.tst.jus.br/rest/"
                "documentos/7a2d741d22e82084a45f85ba428fa103",
                8 * 1024 * 1024,
            ),
        )

    def test_fetch_rejects_excerpt_not_present_in_official_document(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TSTOfficialAdapter(
            transport=SourceTransport(document_text="<html><body>different</body></html>"),
        )
        adapter.search(
            provider.ResearchQuery(
                tribunal_code="TRT12",
                source="tst_precedents",
                query="horas extras parcelas vincendas",
                cursor=None,
            )
        )

        with self.assertRaisesRegex(module.TSTAdapterError, "verbatim custody"):
            adapter.fetch_source(
                provider.ResearchFetchRequest(
                    tribunal_code="TRT12",
                    source="tst_precedents",
                    source_id="TST-93805024",
                )
            )

    def test_adapter_rejects_an_unconfigured_source(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TSTOfficialAdapter(transport=SearchTransport())

        with self.assertRaisesRegex(module.TSTAdapterError, "tst_precedents"):
            adapter.search(
                provider.ResearchQuery(
                    tribunal_code="TRT12",
                    source="regional_jurisprudence",
                    query="horas extras",
                    cursor=None,
                )
            )

    def test_https_transport_posts_json_only_to_the_official_tst_host(self) -> None:
        module = self.api()
        response = HTTPResponse(
            url=(
                "https://jurisprudencia-backend.tst.jus.br/rest/"
                "pesquisa-textual/1/2"
            ),
            body=b'{"totalRegistros": 0, "registros": []}',
            content_type="application/json;charset=UTF-8",
        )
        opener = OfficialOpener(response)
        transport = module.UrllibTSTTransport(opener=opener, timeout=7)

        result = transport.post_json(
            response.url,
            {"e": "horas extras"},
            max_bytes=1024,
        )

        self.assertEqual(result, {"totalRegistros": 0, "registros": []})
        self.assertEqual(opener.timeout, 7)
        self.assertEqual(json.loads(opener.request.data), {"e": "horas extras"})
        self.assertEqual(opener.request.method, "POST")
        self.assertEqual(
            opener.request.headers["Content-type"],
            "application/json; charset=utf-8",
        )

    def test_https_transport_rejects_non_official_hosts_before_opening(self) -> None:
        module = self.api()
        opener = OfficialOpener(
            HTTPResponse(
                url="https://example.test/source",
                body=b"untrusted",
                content_type="text/plain",
            )
        )
        transport = module.UrllibTSTTransport(opener=opener)

        with self.assertRaisesRegex(module.TSTAdapterError, "official TST host"):
            transport.get_text("https://example.test/source", max_bytes=1024)

        self.assertFalse(hasattr(opener, "request"))

    def test_https_transport_rejects_oversized_responses(self) -> None:
        module = self.api()
        url = (
            "https://jurisprudencia-backend.tst.jus.br/rest/"
            "documentos/7a2d741d22e82084a45f85ba428fa103"
        )
        opener = OfficialOpener(
            HTTPResponse(
                url=url,
                body=b"12345",
                content_type="text/html;charset=UTF-8",
            )
        )
        transport = module.UrllibTSTTransport(opener=opener)

        with self.assertRaisesRegex(module.TSTAdapterError, "size limit"):
            transport.get_text(url, max_bytes=4)

    def test_collection_produces_a_schema_valid_corpus(self) -> None:
        module = self.api()
        schema_api = importlib.import_module("schema_validation")
        adapter = module.TSTOfficialAdapter(
            transport=SourceTransport(),
            clock=lambda: datetime(2026, 9, 21, 21, 0, tzinfo=timezone.utc),
        )

        corpus = module.collect_precedent_corpus(
            adapter,
            tribunal_code="TRT12",
            query="horas extras parcelas vincendas",
            limit=1,
        )
        schema = schema_api.load_json(PRECEDENT_SCHEMA, "precedent corpus schema")

        self.assertEqual(schema_api.validate_schema_value(corpus, schema), [])
        self.assertEqual(len(corpus["sources"]), 1)


if __name__ == "__main__":
    unittest.main()
