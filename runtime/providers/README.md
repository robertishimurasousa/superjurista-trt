# Provider Interface Contracts

`interfaces.json` defines the runtime-neutral boundary for case acquisition and authoritative
legal research. Concrete providers implement the Python protocols and immutable request and
response records in `scripts/provider_interfaces.py`.

The shared core knows only capabilities and validated data. Tribunal URLs, authentication
mechanics, cookies, headers, task names, and source-specific request formats belong in concrete
adapters and tribunal profiles.

## Interfaces

- `pje_case_acquisition`: session validation, case discovery, paginated document indexing,
  document download, and SHA-256 verification;
- `legal_research`: paginated search, source retrieval, official HTTPS location, status, and
  verbatim-custody metadata.

## Conformance boundary

The fake-provider suite exercises both interfaces with a synthetic tribunal code that is not
the initial implementation target. This proves that the shared runner does not require a
specific regional court constant. It does not prove that any real provider is authenticated,
reachable, authorized, or operationally compatible.

```bash
python3 -m unittest tests.test_provider_interfaces -v
```

Real PJe-JT and research adapters remain separate work packages and require authorized,
sanitized evidence before implementation or acceptance.

## Segment and classify an authorized consolidated PJe PDF

`scripts/segment_pje_pdf.py` uses the native outline destinations embedded by PJe when a
consolidated process PDF is exported. It derives stable `DOC-NNN` identifiers, filing dates,
provider references, and inclusive page ranges without reading case text. The resulting segments
feed the shared labor-document classifier, whose output intentionally excludes provider titles,
references, and source content.

Both output artifacts contain case-specific metadata and must stay in a protected directory
outside the repository. The command refuses repository-local output and refuses to overwrite an
existing artifact:

```bash
mkdir -p /protected/case/classification
chmod 700 /protected/case/classification
python3 scripts/segment_pje_pdf.py \
  --input /protected/case/process.pdf \
  --output /protected/case/classification
```

The command writes `document-segments.json` and `document-classification.json` with mode `0600`.
PDFs without a complete, ordered PJe outline fail closed; they are not heuristically split from
OCR text. Generic certificates, notices, and ambiguous document labels remain explicitly
`unknown` until the taxonomy has a semantically correct type and approved review evidence.

Run the synthetic segmentation and classification suite with:

```bash
python3 -m unittest tests.test_pje_pdf_segmentation -v
```

## Query the official TST jurisprudence source

`scripts/tst_official_adapter.py` implements the shared `legal_research` interface against the
public TST jurisprudence application. It targets the backend published by the official portal
configuration, restricts every request and redirect to `jurisprudencia-backend.tst.jus.br`,
bounds response sizes, and emits a schema-valid `precedent-corpus` artifact.

An exact CNJ case number uses the TST structured `numeracaoUnica` filter. Other input is sent as
a textual query. The adapter verifies that the normalized excerpt is present in the official
full-document HTML before accepting the source. It does not infer whether a decision remains a
current binding precedent because the search response has no normalized validity field; such
results retain status `unknown` and require human review.

Generate a bounded corpus outside the repository:

```bash
python3 scripts/tst_official_adapter.py \
  --query '0021532-54.2015.5.04.0006' \
  --output /tmp/tst-precedent-corpus.json \
  --tribunal-code TRT12 \
  --limit 1 \
  --page-size 1
```

The generated artifact may contain public judicial text. Review it under the project data policy
before moving it into a tracked fixture. Unit tests use synthetic records and never call the
network:

```bash
python3 -m unittest tests.test_tst_official_adapter -v
```

## Query official TRT12 PJe jurisprudence

`scripts/trt12_official_adapter.py` implements `legal_research` for the TRT12 source selected
by the tribunal profile. The current TRT12 portal delegates first- and second-instance research
to the official Falcão repository. The adapter therefore fixes the tribunal filter to `TRT12`,
queries the `sentencas` and `acordaos` collections together, follows bounded zero-based pages,
and retrieves the selected document again from the collection-specific detail endpoint before
accepting its verbatim custody.

Coverage is deliberately explicit. Falcão is the current PJe-backed source and the TRT12 portal
states that it exposes documents from 2016 onward. Older physical and Provi collections described
by historical service material are not exposed by the current portal, so this adapter records
`current_pje` coverage and a legacy-coverage gap on every normalized source. Sentences receive the
`trt12_first_instance` scope and acórdãos receive `trt12_second_instance`; neither is assigned a
binding or current precedential status that the official response does not provide.

The public application establishes a short-lived session and enforces a network rate limit. A
rate-limit response fails closed and must be retried only after the official window expires. Its
session bootstrap currently returns an array from the notifications endpoint and an object from
autocomplete; the transport validates those endpoint-specific shapes before it searches.

Generate a bounded public corpus outside the repository:

```bash
python3 scripts/trt12_official_adapter.py \
  --query 'horas extras' \
  --output /tmp/trt12-jurisprudence-corpus.json \
  --tribunal-code TRT12 \
  --limit 2 \
  --page-size 5
```

Run the network-free contract and normalization suite:

```bash
python3 -m unittest tests.test_trt12_official_adapter -v
```

## Query official TRT12 regional precedents

`scripts/trt12_precedent_adapter.py` implements `legal_research` for the TRT12 regional
precedent source. It combines the IRDR tracker linked by the TRT12 uniformization portal with
the tribunal's legal-thesis page. The adapter uses exact bounded HTTPS locations, rejects
unexpected redirects or page shapes, and re-reads the official publication when fetching a
selected source.

IRDR records preserve the submitted legal question, published thesis, tracker status, and
suspension scope. A published thesis is `current` unless the official material expressly marks
it as cancelled. An admitted incident without a thesis is `pending`, or `stayed` when the
tracker expressly reports an active suspension. Historical suspension text remains a status
note after a thesis is published and is not treated as an active stay.

The official thesis page currently states that no legal thesis has been established in IAC.
The adapter exposes that fact through `coverage()` and intentionally returns no fabricated IAC
precedent. Published IUJ theses are normalized as regional orientations, including explicit
cancellation markers.

Generate a bounded corpus outside the repository:

```bash
python3 scripts/trt12_precedent_adapter.py \
  --query 'horas extras' \
  --output /tmp/trt12-precedent-corpus.json \
  --tribunal-code TRT12 \
  --limit 5
```

The generated artifact contains public legal text and must be reviewed under the project data
policy before it is moved into a tracked fixture. Run the network-free contract, source-shape,
status, suspension, IAC-coverage, and corpus suite with:

```bash
python3 -m unittest tests.test_trt12_precedent_adapter -v
```

## Consolidate official precedent corpora

`scripts/consolidate_precedents.py` merges one or more schema-valid `precedent-corpus`
artifacts without discarding provenance. Sources are ordered deterministically by legal-source
type: binding, qualified, normative, summary, orientation, jurisprudence, and persuasive
jurisprudence.

Equivalent sources share the same origin, normalized reference, and holding. The highest-ranked
record becomes canonical, while the sidecar report retains each duplicate source identifier,
official URL, and SHA-256 digest of its exact verbatim excerpt. Repeated identifiers with changed
content fail closed. An `unknown` status never overrides explicit evidence; two different explicit
statuses produce `conflicting` plus a structured conflict entry for later human resolution.

Both the legal question and holding must remain present in the verbatim excerpt. This custody gate
prevents a normalized conclusion from surviving after its supporting quotation is lost.

```bash
python3 scripts/consolidate_precedents.py \
  --input /tmp/tst-precedent-corpus.json \
  --input /tmp/trt12-precedent-corpus.json \
  --output /tmp/consolidated-precedent-corpus.json \
  --report-output /tmp/consolidated-precedent-custody.json
```

Run the deterministic consolidation suite with:

```bash
python3 -m unittest tests.test_precedent_consolidation -v
```

## Assess a sanitized session observation

`pje-session-contract.json` defines provider-neutral states for session probes. A concrete
adapter may report only an HTTP status, recognized semantic markers, and cookie or header
names. It must not return credential values. `scripts/pje_session_adapter.py` validates the
adapter capability and target tribunal, then classifies the observation as `valid`, `expired`,
`mfa_required`, `unauthorized`, or `unknown`.

Conflicting markers and authenticated responses without recognized session evidence resolve
to `unknown`. HTTP 401 and 403 resolve to `unauthorized` even if an authenticated marker is
present. The classifier does not log in, generate MFA material, or know any tribunal endpoint.

```bash
python3 -m unittest tests.test_pje_session_adapter -v
```

The synthetic TRT99 probe proves the state contract and secret-free result shape. A real
TRT12 probe remains dependent on the authorized, reviewed PJE-01 endpoint map.

## Discover authorized tasks and case queues

`pje-task-discovery-contract.json` defines a second provider-neutral boundary for paginated
task and case discovery. Concrete adapters normalize provider payloads into stable task IDs,
task names, CNJ case numbers, and court units. `scripts/pje_task_discovery.py` owns cursor
safety, per-task deduplication, tribunal-region validation, deterministic ordering, and a
secret-free result.

```bash
python3 -m unittest tests.test_pje_task_discovery -v
```

An empty authorized queue is a valid complete result. Repeated cursors, incomplete pages
without a cursor, duplicate task or case records, and mismatched CNJ regions fail closed. The
TRT99 fake proves shared behavior only; real TRT12 task names, endpoints, payloads, and cursor
semantics still require the reviewed PJE-01 map.

## Acquire and resume verified documents

`scripts/acquire_pje_documents.py` builds the complete normalized document index before it
downloads either every document or an explicit subset. Each accepted payload must match the
SHA-256 published in that index. Missing requested identifiers and bounded provider
unavailability remain visible as structured gaps.

`scripts/recover_pje_acquisition.py` adds a versioned, atomic checkpoint around that contract.
It persists only normalized case identity, the digest of the authorization scope, catalog and
payload hashes, bounded attempt counts, and canonical local payload paths. A resumed run verifies
every accepted payload before provider access, never downloads an accepted payload again, and
fails closed if the catalog, request, retry ceiling, or local bytes changed. The retry ceiling is
one to five attempts and cannot be raised by resuming with different parameters.

Run the network-free acquisition and recovery suites with:

```bash
python3 -m unittest \
  tests.test_pje_document_acquisition \
  tests.test_pje_recovery \
  -v
```

These fixtures use TRT99 and prove shared recovery behavior only. `PJE-05` acceptance still
requires repeated authorized TRT12 closed rehearsals with at least 95% success; no synthetic run
contributes to that empirical rate.

## Build a sanitized HAR map

Raw HAR files and extracted sessions remain local and ignored. For an authorized capture,
create a deterministic map that retains endpoint structure but removes header values, cookie
values, query values, request bodies, response bodies, and dynamic path identifiers:

```bash
python3 scripts/sanitize_pje_har.py \
  --input /path/outside-the-repository/authorized-capture.har \
  --output tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1 \
  --authorized-capture
```

The acknowledgement flag records an operator assertion; it does not independently prove
authorization. Review the generated map before making it a commit candidate. Never copy the
raw HAR or a generated session file into the repository.

Validate structural integrity and evidence coverage before human review:

```bash
python3 scripts/validate_pje_har_map.py \
  --map tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1
```

Exit code `0` means the map has the required technical coverage and is ready for human review;
`1` reports explicit coverage gaps; `2` rejects an invalid, inconsistent, or tampered map.
Technical readiness is not legal or operational acceptance. Do not intentionally induce an
authentication failure, timeout, or provider error merely to enrich a capture. Missing functional
endpoint or authentication-artifact coverage blocks readiness; failure groups not naturally
observed are returned as `observed_failure_gaps` and remain explicit limitations for the later
session and recovery rehearsals.
