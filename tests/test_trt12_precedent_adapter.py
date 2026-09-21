from __future__ import annotations

import csv
import importlib
import io
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PRECEDENT_SCHEMA = (
    ROOT / "runtime" / "contracts" / "schemas" / "precedent-corpus.v1.schema.json"
)

TRACKER_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1ViUtXjLrsOypfuG8UBTPx80n2OGUQpTRdtmz4zBv4bk/gviz/tq?tqx=out:csv"
)
THESES_URL = "https://portal.trt12.jus.br/teses-juridicas"

TRACKER_HEADER = [
    "Tema (TRT12)",
    "Número do IRDR",
    "Número do processo paradigma",
    "Classe processual do processo paradigma",
    "Número do Tema (Pje)",
    "Questão submetida  a julgamento",
    "Assunto",
    "Data da autuação",
    "Data da admissão (Sessão de julgamento)",
    "Situação do tema",
    "Tese firmada",
    "Referência legislativa",
    "Relator",
    "Órgão Julgador",
    "Data da publicação do acórdão de (in)admissibilidade",
    "Data do julgamento do mérito do tema",
    "Data da publicação do acórdão  relativo ao mérito do tema",
    "Data do trânsito em julgado do acórdão relativo ao mérito do tema",
]


def tracker_csv() -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["", "INCIDENTES DE RESOLUÇÃO DE DEMANDAS REPETITIVAS"] + [""] * 16)
    writer.writerow(TRACKER_HEADER)
    writer.writerow(
        [
            "21",
            "0002206-60.2022.5.12.0000",
            "0001000-00.2022.5.12.0001",
            "Recurso Ordinário",
            "21",
            "É válido o regime de trabalho 12x36 instituído por decreto municipal?",
            "Jornada de trabalho",
            "01/01/2022",
            "01/02/2022",
            "Transitado em julgado. Mérito julgado.",
            (
                "TESE JURÍDICA N.º 16: É inválido o regime de trabalho 12 x 36 "
                "instituído por decreto municipal."
            ),
            "Art. 7º da Constituição",
            "Relator",
            "Tribunal Pleno",
            "01/03/2022",
            "01/04/2022",
            "01/05/2022",
            "01/06/2022",
        ]
    )
    writer.writerow(
        [
            "23\n* Observar cancelamento da tese",
            "0000118-78.2024.5.12.0000",
            "0000021-22.2023.5.12.0030",
            "Recurso Ordinário",
            "23",
            "O transporte de valores configura dano moral?",
            "Dano moral",
            "01/01/2024",
            "01/02/2024",
            "Transitado em julgado.",
            (
                "RESOLUÇÃO Nº 3/2025 CANCELA A TESE JURÍDICA Nº 19: "
                "O transporte de valores, por si só, não configura dano moral."
            ),
            "Código Civil",
            "Relator",
            "Tribunal Pleno",
            "01/03/2024",
            "01/04/2024",
            "01/05/2024",
            "01/06/2024",
        ]
    )
    writer.writerow(
        [
            "33",
            "0000839-91.2026.5.12.0054",
            "0000839-91.2026.5.12.0054",
            "IRDR",
            "33",
            "O Tema 555 do STF é aplicável na Justiça do Trabalho?",
            "Adicional de insalubridade",
            "01/08/2026",
            "31/08/2026",
            "Admitido na sessão de 31/08/2026.",
            "",
            "",
            "Relator",
            "Tribunal Pleno",
            "15/09/2026",
            "",
            "",
            "",
        ]
    )
    writer.writerow(
        [
            "34",
            "0000884-46.2025.5.12.0017",
            "0000884-46.2025.5.12.0017",
            "IRDR",
            "34",
            "Qual é o termo inicial para pagamento das verbas rescisórias?",
            "Verbas rescisórias",
            "01/08/2026",
            "31/08/2026",
            (
                "Admitido na sessão de 31/08/2026. Com determinação de SUSPENSÃO "
                "dos processos em tramitação na SEGUNDA INSTÂNCIA."
            ),
            "",
            "",
            "Relator",
            "Tribunal Pleno",
            "14/09/2026",
            "",
            "",
            "",
        ]
    )
    return output.getvalue()


def gviz_tracker_csv() -> str:
    rows = list(csv.reader(io.StringIO(tracker_csv())))
    merged_header = list(rows[1])
    merged_header[0] = f"ão {merged_header[0]}"
    merged_header[1] = f"INCIDENTES DE RESOLUÇÃO DE DEMANDAS REPETITIVAS {merged_header[1]}"
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(merged_header)
    writer.writerows(rows[2:])
    return output.getvalue()


THESES_HTML = """
<html><body>
  <table>
    <caption>TESES JURÍDICAS EM INCIDENTES DE ASSUNÇÃO DE COMPETÊNCIA (IAC's)</caption>
    <tbody><tr><td><strong>Ainda não há tese jurídica firmada em IAC.</strong></td></tr></tbody>
  </table>
  <table>
    <caption>TESES JURÍDICAS EM INCIDENTES DE UNIFORMIZAÇÃO DE JURISPRUDÊNCIA (IUJ's)</caption>
    <tbody>
      <tr><td><strong>TESE JURÍDICA N.º 2 EM IUJ - CANCELADA</strong></td></tr>
      <tr><td><p><strong>EXECUÇÃO DE CRÉDITOS TRABALHISTAS.</strong> A competência limita-se
      à apuração dos créditos. (Resolução)</p><p>OBS.: Cancelada pela Resolução n. 4/2022.</p></td></tr>
      <tr><td><strong>TESE JURÍDICA N.º 3 EM IUJ</strong></td></tr>
      <tr><td><p><strong>VIGIA. ATIVIDADE DE SEGURANÇA PATRIMONIAL.</strong> É devido o
      adicional de periculosidade ao trabalhador vigia. (Resolução)</p><p>Ver: Edital.</p></td></tr>
    </tbody>
  </table>
</body></html>
"""


class OfficialTransport:
    def __init__(self, *, tracker=None, theses=None) -> None:
        self.tracker = tracker if tracker is not None else tracker_csv()
        self.theses = theses if theses is not None else THESES_HTML
        self.requests = []

    def get_text(self, url, *, max_bytes):
        self.requests.append((url, max_bytes))
        if url == TRACKER_URL:
            return self.tracker
        if url == THESES_URL:
            return self.theses
        raise AssertionError(f"unexpected URL: {url}")


class HTTPResponse:
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


class OfficialOpener:
    def __init__(self, response) -> None:
        self.response = response

    def __call__(self, request, *, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


class TRT12PrecedentAdapterTest(unittest.TestCase):
    def api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        try:
            return importlib.import_module("trt12_precedent_adapter")
        except ModuleNotFoundError as error:
            self.fail(f"TRT12 precedent adapter module is missing: {error}")

    def provider_api(self):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        return importlib.import_module("provider_interfaces")

    def request(self, provider, query, cursor=None):
        return provider.ResearchQuery(
            tribunal_code="TRT12",
            source="trt12_precedents",
            query=query,
            cursor=cursor,
        )

    def test_search_normalizes_current_and_cancelled_irdr_theses(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12PrecedentAdapter(transport=OfficialTransport())

        current = adapter.search(self.request(provider, "regime de trabalho 12x36"))
        cancelled = adapter.search(self.request(provider, "transporte de valores"))

        self.assertEqual(current.items[0].source_id, "TRT12IRDR-021")
        self.assertEqual(current.items[0].status, "current")
        self.assertEqual(current.items[0].origin, "TRT12")
        self.assertEqual(current.items[0].official_url, TRACKER_URL)
        self.assertEqual(cancelled.items[0].source_id, "TRT12IRDR-023")
        self.assertEqual(cancelled.items[0].status, "cancelled")

    def test_search_accepts_the_gviz_merged_title_and_header_row(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12PrecedentAdapter(
            transport=OfficialTransport(tracker=gviz_tracker_csv())
        )

        page = adapter.search(self.request(provider, "regime de trabalho 12x36"))

        self.assertEqual(page.items[0].source_id, "TRT12IRDR-021")

    def test_search_distinguishes_pending_and_active_second_instance_stay(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12PrecedentAdapter(transport=OfficialTransport())

        pending = adapter.search(self.request(provider, "Tema 555"))
        stayed = adapter.search(self.request(provider, "verbas rescisórias"))

        self.assertEqual(pending.items[0].status, "pending")
        self.assertEqual(stayed.items[0].status, "stayed")
        source = adapter.fetch_source(
            provider.ResearchFetchRequest(
                tribunal_code="TRT12",
                source="trt12_precedents",
                source_id="TRT12IRDR-034",
            )
        )
        self.assertIn(
            "Suspension: active; scope: trt12_second_instance.",
            source.status_notes,
        )
        self.assertEqual(source.binding_scope, "trt12_regional_jurisdiction")

    def test_iac_absence_is_explicit_coverage_and_not_a_fake_precedent(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12PrecedentAdapter(transport=OfficialTransport())

        page = adapter.search(self.request(provider, "IAC"))
        coverage = adapter.coverage()

        self.assertEqual(page.items, ())
        self.assertEqual(coverage.iac_status, "none_published")
        self.assertEqual(
            coverage.iac_statement,
            "Ainda não há tese jurídica firmada em IAC.",
        )
        self.assertEqual(coverage.official_url, THESES_URL)

    def test_search_includes_current_and_cancelled_iuj_regional_theses(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12PrecedentAdapter(transport=OfficialTransport())

        current = adapter.search(self.request(provider, "atividade de segurança"))
        cancelled = adapter.search(self.request(provider, "apuração dos créditos"))

        self.assertEqual(current.items[0].source_id, "TRT12IUJ-003")
        self.assertEqual(current.items[0].status, "current")
        self.assertEqual(cancelled.items[0].source_id, "TRT12IUJ-002")
        self.assertEqual(cancelled.items[0].status, "cancelled")

    def test_search_uses_bounded_offset_pagination(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12PrecedentAdapter(
            transport=OfficialTransport(),
            page_size=2,
        )

        first = adapter.search(self.request(provider, "TRT12"))
        second = adapter.search(self.request(provider, "TRT12", first.next_cursor))

        self.assertFalse(first.complete)
        self.assertEqual(first.next_cursor, "2")
        self.assertEqual(len(first.items), 2)
        self.assertNotEqual(first.items[0].source_id, second.items[0].source_id)

    def test_fetch_preserves_custody_and_builds_schema_valid_corpus(self) -> None:
        module = self.api()
        provider = self.provider_api()
        schema_api = importlib.import_module("schema_validation")
        adapter = module.TRT12PrecedentAdapter(
            transport=OfficialTransport(),
            clock=lambda: datetime(2026, 9, 21, 23, 0, tzinfo=timezone.utc),
        )
        adapter.search(self.request(provider, "regime de trabalho 12x36"))

        source = adapter.fetch_source(
            provider.ResearchFetchRequest(
                tribunal_code="TRT12",
                source="trt12_precedents",
                source_id="TRT12IRDR-021",
            )
        )
        corpus = module.build_precedent_corpus((source,))
        schema = schema_api.load_json(PRECEDENT_SCHEMA, "precedent corpus schema")

        self.assertEqual(source.status, "current")
        self.assertEqual(source.retrieved_at, "2026-09-21T23:00:00Z")
        self.assertIn("É inválido o regime de trabalho", source.verbatim_excerpt)
        self.assertEqual(corpus["sources"][0]["type"], "binding_precedent")
        self.assertEqual(schema_api.validate_schema_value(corpus, schema), [])

    def test_adapter_conforms_to_shared_research_interface(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12PrecedentAdapter(
            transport=OfficialTransport(),
            clock=lambda: datetime(2026, 9, 21, 23, 0, tzinfo=timezone.utc),
        )
        interfaces = provider.load_provider_interfaces(
            ROOT / "runtime" / "providers" / "interfaces.json"
        )

        report = provider.verify_research_adapter(
            interfaces["legal_research"],
            adapter,
            provider.ResearchContractScenario(
                tribunal_code="TRT12",
                source="trt12_precedents",
                query="regime de trabalho 12x36",
            ),
        )

        self.assertEqual(report["status"], "conformant")
        self.assertEqual(report["provider_id"], "trt12-precedents-official")
        self.assertEqual(report["result_count"], 1)

    def test_adapter_rejects_wrong_tribunal_and_source(self) -> None:
        module = self.api()
        provider = self.provider_api()
        adapter = module.TRT12PrecedentAdapter(transport=OfficialTransport())

        with self.assertRaisesRegex(module.TRT12PrecedentError, "TRT12"):
            adapter.search(
                provider.ResearchQuery(
                    tribunal_code="TRT2",
                    source="trt12_precedents",
                    query="jornada",
                    cursor=None,
                )
            )
        with self.assertRaisesRegex(module.TRT12PrecedentError, "trt12_precedents"):
            adapter.search(
                provider.ResearchQuery(
                    tribunal_code="TRT12",
                    source="tst_precedents",
                    query="jornada",
                    cursor=None,
                )
            )

    def test_https_transport_restricts_exact_official_publication_urls(self) -> None:
        module = self.api()
        opener = OfficialOpener(
            HTTPResponse(url=THESES_URL, body=THESES_HTML.encode("utf-8"))
        )
        transport = module.UrllibTRT12PrecedentTransport(opener=opener, timeout=7)

        text = transport.get_text(THESES_URL, max_bytes=1024 * 1024)

        self.assertIn("Ainda não há tese", text)
        self.assertEqual(opener.timeout, 7)
        with self.assertRaisesRegex(module.TRT12PrecedentError, "approved official"):
            transport.get_text(
                "https://portal.trt12.jus.br/not-an-approved-page",
                max_bytes=1024,
            )

    def test_https_transport_rejects_oversized_response(self) -> None:
        module = self.api()
        transport = module.UrllibTRT12PrecedentTransport(
            opener=OfficialOpener(HTTPResponse(url=THESES_URL, body=b"12345"))
        )

        with self.assertRaisesRegex(module.TRT12PrecedentError, "size limit"):
            transport.get_text(THESES_URL, max_bytes=4)


if __name__ == "__main__":
    unittest.main()
