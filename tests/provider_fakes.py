from __future__ import annotations

import hashlib
from typing import Optional, Tuple


class FakePJeAdapter:
    def __init__(
        self,
        api,
        *,
        capabilities: Optional[Tuple[str, ...]] = None,
        corrupt_payload: bool = False,
        repeat_cursor: bool = False,
    ) -> None:
        self.api = api
        self.corrupt_payload = corrupt_payload
        self.repeat_cursor = repeat_cursor
        self.content = b"synthetic PDF fixture"
        self.descriptor = api.AdapterDescriptor(
            provider_id="fake-pje",
            interface_id="pje_case_acquisition",
            interface_version=1,
            capabilities=capabilities
            or (
                "validate_session",
                "discover_case",
                "list_documents",
                "fetch_document",
            ),
            supported_tribunals=("TRT99",),
        )

    def validate_session(self, request):
        return self.api.SessionResult(status="valid")

    def discover_case(self, request):
        return self.api.CaseRecord(
            case_number=request.case_number,
            tribunal_code=request.tribunal_code,
            instance=request.instance,
            court_unit="Synthetic Labor Court",
            task_id="TASK-001",
        )

    def list_documents(self, request):
        digest = hashlib.sha256(self.content).hexdigest()
        if request.cursor is None:
            return self.api.DocumentPage(
                items=(
                    self.api.DocumentRecord(
                        document_id="DOC-001",
                        filename="synthetic.pdf",
                        mime_type="application/pdf",
                        sha256=digest,
                        source_locator="event 1",
                    ),
                ),
                next_cursor="page-2",
                complete=False,
            )
        return self.api.DocumentPage(
            items=(),
            next_cursor="page-2" if self.repeat_cursor else None,
            complete=not self.repeat_cursor,
        )

    def fetch_document(self, request):
        content = self.content + b"corrupt" if self.corrupt_payload else self.content
        return self.api.DocumentPayload(document_id=request.document_id, content=content)


class FakeResearchAdapter:
    def __init__(
        self,
        api,
        *,
        official_url: str = "https://example.test/official-source",
    ) -> None:
        self.api = api
        self.official_url = official_url
        self.descriptor = api.AdapterDescriptor(
            provider_id="fake-research",
            interface_id="legal_research",
            interface_version=1,
            capabilities=("search", "fetch_source"),
            supported_tribunals=("TRT99",),
        )

    def search(self, request):
        return self.api.ResearchPage(
            items=(
                self.api.ResearchHit(
                    source_id="SRC-001",
                    origin="TRT99",
                    reference="Synthetic result",
                    status="current",
                    official_url=self.official_url,
                ),
            ),
            next_cursor=None,
            complete=True,
        )

    def fetch_source(self, request):
        return self.api.ResearchSource(
            source_id=request.source_id,
            origin="TRT99",
            reference="Synthetic result",
            status="current",
            status_notes=(),
            binding_scope="regional_labor_justice",
            legal_question="Synthetic question.",
            holding="Synthetic holding.",
            verbatim_excerpt="Synthetic excerpt; not a real judicial quotation.",
            official_url=self.official_url,
            retrieved_at="2026-09-21T12:00:00-03:00",
        )
