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
Technical readiness is not legal or operational acceptance.
