from __future__ import annotations

import importlib
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PRECEDENT_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "precedent-corpus.v1.schema.json"
)


def acordao_record(**overrides):
    record = {
        "idDocumentoAcordao": 876543,
        "tribunal": "TRT12",
        "numeroProcesso": "0000814-13.2023.5.12.0045",
        "siglaClasseProcesso": "ROT",
        "classeProcesso": "Recurso Ordinário Trabalhista",
        "relator": "Gisele Pereira Alexandrino",
        "turma": "3ª Câmara",
        "dataJuntada": "2025-03-21",
        "possuiEmenta": "S",
        "ementa": (
            "VÍNCULO DE EMPREGO. CONTRATO CIVIL. A primazia da realidade "
            "autoriza o reconhecimento do vínculo quando presentes seus requisitos."
        ),
        "textoAcordao": (
            "VÍNCULO DE EMPREGO. CONTRATO CIVIL. A primazia da realidade "
            "autoriza o reconhecimento do vínculo quando presentes seus requisitos. "
            "Recurso parcialmente provido."
        ),
    }
    record.update(overrides)
    return record


def sentenca_record(**overrides):
    record = {
        "idSentenca": 765432,
        "tribunal": "TRT12",
        "numeroProcesso": "0000915-31.2024.5.12.0036",
        "classeProcessual": "ATOrd",
        "classeProcessualPorExtenso": "Ação Trabalhista - Rito Ordinário",
        "nomeRedator": "Juíza do Trabalho Exemplo",
        "orgaoJulgador": "6ª VT de Florianópolis",
        "orgaoJulgadorPorExtenso": "6ª Vara do Trabalho de Florianópolis",
        "faseProcessual": "Conhecimento",
        "prioridades": [],
        "dataJuntada": "2025-04-02",
        "textoSentenca": (
            "HORAS EXTRAS. CONTROLES DE JORNADA. Os registros apresentados "
            "não abrangem todo o período contratual. Defere-se o pagamento das "
            "diferenças comprovadas."
        ),
    }
    record.update(overrides)
    return record


class OfficialTransport:
    def __init__(self, *, detail_override=None) -> None:
        self.prepared = []
        self.requests = []
        self.detail_override = detail_override

    def open_session(self, *, query, session_id, max_bytes):
        self.prepared.append((query, session_id, max_bytes))

    def get_json(self, url, *, max_bytes):
        self.requests.append((url, max_bytes))
        path = urlsplit(url).path
        if "/pesquisa/acordaos/TRT12/876543" in path:
            record = self.detail_override or acordao_record()
            return {"documentos": [record]}
        if "/pesquisa/sentencas/TRT12/765432" in path:
            record = self.detail_override or sentenca_record()
            return {"documentos": [record]}
        return {
            "documentos": [acordao_record(), sentenca_record()],
            "quantidadeTotal": 2,
        }


class PaginatedTransport(OfficialTransport):
    def get_json(self, url, *, max_bytes):
        response = super().get_json(url, max_bytes=max_bytes)
        if "/pesquisa?" in url:
            response["quantidadeTotal"] = 3
        return response


class FakeHTTPResponse:
    def __init__(self, *, url, body) -> None:
        self.url = url
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def geturl(self):
        return self.url

    def read(self, amount):
        return self.body[:amount]


class SequenceOpener:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.requests = []

    def open(self, request, *, timeout):
        self.requests.append((request, timeout))
        return self.responses.pop(0)


class TRT12OfficialAdapterTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("trt12_official_adapter")
        except ModuleNotFoundError as error:
            self.fail(f"TRT12 official adapter module is missing: {error}")

    def provider_api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("provider_interfaces")

    def request(self, provider, *, cursor=None, tribunal_code="TRT12"):
        return provider.ResearchQuery(
            tribunal_code=tribunal_code,
            source="trt12_jurisprudence",
            query="horas extras",
            cursor=cursor,
        )

    def test_search_normalizes_official_acordao_and_sentenca(self) -> None:
        module = self.api()
        provider = self.provider_api()
        transport = OfficialTransport()
        adapter = module.TRT12OfficialAdapter(
            transport=transport,
            page_size=5,
            session_factory=lambda: "_abc1234",
        )

        page = adapter.search(self.request(provider))

        self.assertEqual(
            page,
            provider.ResearchPage(
                items=(
                    provider.ResearchHit(
                        source_id="TRT12A-876543",
                        origin="TRT12",
                        reference=(
                            "ROT 0000814-13.2023.5.12.0045; 3ª Câmara; "
                            "acórdão juntado em 2025-03-21"
                        ),
                        status="unknown",
                        official_url=(
                            "https://jurisprudencia.jt.jus.br/"
                            "jurisprudencia-nacional/citacao/acordaos/"
                            "TRT12/876543"
                        ),
                    ),
                    provider.ResearchHit(
                        source_id="TRT12S-765432",
                        origin="TRT12",
                        reference=(
                            "ATOrd 0000915-31.2024.5.12.0036; "
                            "6ª Vara do Trabalho de Florianópolis; "
                            "sentença juntada em 2025-04-02"
                        ),
                        status="unknown",
                        official_url=(
                            "https://jurisprudencia.jt.jus.br/"
                            "jurisprudencia-nacional/citacao/sentencas/"
                            "TRT12/765432"
                        ),
                    ),
                ),
                next_cursor=None,
                complete=True,
            ),
        )
        self.assertEqual(
            transport.prepared,
            [("horas extras", "_abc1234", 8 * 1024 * 1024)],
        )
        query = parse_qs(urlsplit(transport.requests[0][0]).query)
        self.assertEqual(query["sessionId"], ["_abc1234"])
        self.assertEqual(query["tribunais"], ["TRT12"])
        self.assertEqual(query["colecao"], ["acordaos,sentencas"])
        self.assertEqual(query["texto"], ["horas%20extras"])
        self.assertEqual(query["page"], ["0"])
        self.assertEqual(query["size"], ["5"])

    def test_search_exposes_zero_based_pagination_as_an_opaque_cursor(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12OfficialAdapter(
            transport=PaginatedTransport(),
            page_size=2,
            session_factory=lambda: "_abc1234",
        )

        page = adapter.search(self.request(provider))

        self.assertFalse(page.complete)
        self.assertEqual(page.next_cursor, "1")

    def test_search_rejects_other_tribunals_and_invalid_cursors(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12OfficialAdapter(transport=OfficialTransport())

        with self.assertRaisesRegex(module.TRT12AdapterError, "only TRT12"):
            adapter.search(self.request(provider, tribunal_code="TRT2"))
        with self.assertRaisesRegex(module.TRT12AdapterError, "cursor"):
            adapter.search(self.request(provider, cursor="-1"))

    def test_search_rejects_a_legacy_or_ambiguous_record(self) -> None:
        module = self.api()
        provider = self.provider_api()

        class AmbiguousTransport(OfficialTransport):
            def get_json(self, url, *, max_bytes):
                return {
                    "documentos": [
                        {
                            **acordao_record(),
                            "idSentenca": 765432,
                            "textoSentenca": "Legacy content without a declared collection.",
                        }
                    ],
                    "quantidadeTotal": 1,
                }

        adapter = module.TRT12OfficialAdapter(transport=AmbiguousTransport())

        with self.assertRaisesRegex(module.TRT12AdapterError, "exactly one collection"):
            adapter.search(self.request(provider))

    def test_fetch_preserves_custody_and_marks_current_pje_coverage(self) -> None:
        module = self.api()
        provider = self.provider_api()
        transport = OfficialTransport()
        adapter = module.TRT12OfficialAdapter(
            transport=transport,
            clock=lambda: datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
        )
        adapter.search(self.request(provider))

        source = adapter.fetch_source(
            provider.ResearchFetchRequest(
                tribunal_code="TRT12",
                source="trt12_jurisprudence",
                source_id="TRT12S-765432",
            )
        )

        self.assertEqual(source.origin, "TRT12")
        self.assertEqual(source.binding_scope, "trt12_first_instance")
        self.assertEqual(source.retrieved_at, "2026-09-21T22:00:00Z")
        self.assertEqual(
            source.legal_question,
            "HORAS EXTRAS.",
        )
        self.assertEqual(
            source.holding,
            "Defere-se o pagamento das diferenças comprovadas.",
        )
        self.assertIn("Coverage: current_pje", source.status_notes[0])
        self.assertIn("Legacy physical and Provi", source.status_notes[1])
        self.assertEqual(
            source.official_url,
            "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional/"
            "citacao/sentencas/TRT12/765432",
        )

    def test_fetch_rejects_detail_without_verbatim_custody(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12OfficialAdapter(
            transport=OfficialTransport(
                detail_override=sentenca_record(textoSentenca="Different official text.")
            )
        )
        adapter.search(self.request(provider))

        with self.assertRaisesRegex(module.TRT12AdapterError, "verbatim custody"):
            adapter.fetch_source(
                provider.ResearchFetchRequest(
                    tribunal_code="TRT12",
                    source="trt12_jurisprudence",
                    source_id="TRT12S-765432",
                )
            )

    def test_adapter_conforms_to_the_shared_research_interface(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12OfficialAdapter(
            transport=OfficialTransport(),
            clock=lambda: datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
        )
        interfaces = provider.load_provider_interfaces(
            ROOT / "runtime" / "providers" / "interfaces.json"
        )

        result = provider.verify_research_adapter(
            interfaces["legal_research"],
            adapter,
            provider.ResearchContractScenario(
                tribunal_code="TRT12",
                source="trt12_jurisprudence",
                query="horas extras",
            ),
        )

        self.assertEqual(result["status"], "conformant")
        self.assertEqual(result["provider_id"], "trt12-falcao-official")
        self.assertEqual(result["result_count"], 2)

    def test_collection_produces_a_schema_valid_corpus(self) -> None:
        module = self.api()
        schema_api = importlib.import_module("schema_validation")
        adapter = module.TRT12OfficialAdapter(
            transport=OfficialTransport(),
            clock=lambda: datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
        )

        corpus = module.collect_precedent_corpus(
            adapter,
            tribunal_code="TRT12",
            query="horas extras",
            limit=2,
        )
        schema = schema_api.load_json(PRECEDENT_SCHEMA, "precedent corpus schema")

        self.assertEqual(schema_api.validate_schema_value(corpus, schema), [])
        self.assertEqual(
            [item["type"] for item in corpus["sources"]],
            ["persuasive_jurisprudence", "persuasive_jurisprudence"],
        )

    def test_transport_opens_the_public_session_before_search(self) -> None:
        module = self.api()
        notifications_url = (
            "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/"
            "api/no-auth/notificacoes?page=0&size=5"
        )
        autocomplete_url = (
            "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/"
            "api/no-auth/autocompletar?texto=horas%20extras"
        )
        opener = SequenceOpener(
            [
                FakeHTTPResponse(url=notifications_url, body=b'[{"id": 1}]'),
                FakeHTTPResponse(url=autocomplete_url, body=b'{"sugestoes": []}'),
            ]
        )
        transport = module.UrllibFalcaoTransport(opener=opener, timeout=7)

        transport.open_session(
            query="horas extras",
            session_id="_abc1234",
            max_bytes=1024,
        )

        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[0][0].full_url, notifications_url)
        self.assertEqual(opener.requests[1][0].full_url, autocomplete_url)
        self.assertEqual(opener.requests[0][1], 7)
        self.assertIn("SESSION_ID_COOKIE_PUJ=_abc1234", opener.requests[0][0].headers["Cookie"])
        self.assertTrue(opener.requests[0][0].headers["User-agent"].startswith("Mozilla/5.0"))
        self.assertIn("Chromium", opener.requests[0][0].headers["Sec-ch-ua"])

    def test_transport_rejects_non_official_hosts_and_oversized_responses(self) -> None:
        module = self.api()
        official_url = (
            "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/"
            "api/no-auth/pesquisa"
        )
        opener = SequenceOpener(
            [FakeHTTPResponse(url=official_url, body=b"12345")]
        )
        transport = module.UrllibFalcaoTransport(opener=opener)

        with self.assertRaisesRegex(module.TRT12AdapterError, "official Falcão host"):
            transport.get_json("https://example.test/source", max_bytes=4)
        with self.assertRaisesRegex(module.TRT12AdapterError, "size limit"):
            transport.get_json(official_url, max_bytes=4)

    def test_transport_reports_forbidden_search_without_retry(self) -> None:
        module = self.api()
        official_url = (
            "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/"
            "api/no-auth/pesquisa"
        )

        class DeniedOpener:
            def __init__(self):
                self.requests = []

            def open(self, request, *, timeout):
                self.requests.append((request, timeout))
                raise HTTPError(official_url, 403, "Forbidden", {}, None)

        opener = DeniedOpener()
        transport = module.UrllibFalcaoTransport(opener=opener)

        with self.assertRaisesRegex(
            module.TRT12AdapterError, "acesso ao Falcão negado.*403"
        ):
            transport.get_json(official_url, max_bytes=1024)

        self.assertEqual(len(opener.requests), 1)


if __name__ == "__main__":
    unittest.main()
