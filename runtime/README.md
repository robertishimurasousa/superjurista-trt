# SuperJurista Runtime Contract

This directory contains the runtime-neutral execution boundary used by Claude Code and Codex.
Runtime adapters may translate instruction discovery, skill paths, task dispatch, progress
reporting, and tool names. They may not override legal rules, tribunal profiles, artifact
schemas, or deterministic gates.

## Layout

```text
runtime/
├── data-hygiene-contract.json
├── python-contract.json
├── adapters/
│   ├── claude.json
│   └── codex.json
├── contracts/
│   ├── catalog.json
│   ├── README.md
│   ├── VERSIONING.md
│   └── schemas/
│       └── *.v1.schema.json
├── domain/
│   ├── labor-claim-taxonomy.json
│   ├── labor-document-classification.json
│   └── README.md
├── operations/
│   └── pilot-preflight.v1.schema.json
├── profiles/
│   ├── schema.json
│   ├── registry.json
│   └── trt12.json
├── providers/
│   ├── har-map-review-contract.json
│   ├── har-sanitization-contract.json
│   ├── interfaces.json
│   ├── pje-session-contract.json
│   ├── pje-task-discovery-contract.json
│   └── README.md
└── pipelines/
    ├── conditional-work-plan.v1.schema.json
    ├── execution-state.v1.schema.json
    ├── smoke.json
    └── trt12-first-instance.json
```

The smoke manifest describes one shared artifact and one shared gate. The adapter identifies
the runtime-facing bindings. `scripts/verify_runtime_contract.py` validates both contracts and
delegates artifact validation to the existing deterministic gate engine.

## Validate adapter contracts

```bash
python3 scripts/verify_runtime_contract.py \
  --runtime claude \
  --manifest runtime/pipelines/smoke.json \
  --validate-only

python3 scripts/verify_runtime_contract.py \
  --runtime codex \
  --manifest runtime/pipelines/smoke.json \
  --validate-only
```

## Run the shared smoke gate

The workspace name or `--id` must provide an artifact identifier. The expected artifact is
`<ID>-runtime-smoke.md`.

```bash
python3 scripts/verify_runtime_contract.py \
  --runtime claude \
  --manifest runtime/pipelines/smoke.json \
  --workspace /path/to/workspace

python3 scripts/verify_runtime_contract.py \
  --runtime codex \
  --manifest runtime/pipelines/smoke.json \
  --workspace /path/to/workspace
```

Both commands must return the same gate result for the same artifact. The conformance target
is contract equivalence, not byte-identical model prose.

## Resolve the TRT12 first-instance pipeline

The first-instance manifest is the shared source of truth for the stage graph, dependencies,
retry ceiling, artifact paths, conditions, and gates. Runtime adapters add only instruction,
skill, dispatch, progress, and tool bindings.

```bash
python3 scripts/resolve_runtime_pipeline.py \
  --runtime claude \
  --manifest runtime/pipelines/trt12-first-instance.json

python3 scripts/resolve_runtime_pipeline.py \
  --runtime codex \
  --manifest runtime/pipelines/trt12-first-instance.json
```

Each command prints a resolved execution plan containing:

- the runtime adapter bindings;
- the normalized shared contract;
- a SHA-256 digest of that contract.

The digest and shared contract must be identical for Claude Code and Codex. The resolver fails
closed on unknown dependencies, dependency cycles, duplicate artifacts, unknown gates,
unsupported conditions, invalid retry policies, or runtime-specific fields inside the shared
manifest.

## Resume an interrupted pipeline safely

`scripts/resumable_pipeline.py` implements the runtime-neutral checkpoint used by the resolved
Claude Code and Codex plans. `new_execution_state()` creates the versioned state,
`record_stage_acceptance()` records a stage only after its dependencies, declared outputs, retry
ceiling, and current deterministic gate pass, and `plan_resume()` identifies the next stage.

A checkpoint is reusable only when all of these still match:

- pipeline contract digest;
- authorized-source fingerprint;
- dependency aggregate fingerprints;
- every declared output SHA-256 digest;
- the stage's current content gate.

Changing any item makes the stage pending and prevents reuse of every dependent stage. The state
is saved atomically under `execution-state.v1.schema.json` and deliberately omits runtime dispatch
details, so the same accepted checkpoint can resume through Claude Code or Codex while each keeps
its own adapter binding.

```bash
python3 -m unittest tests.test_resumable_pipeline -v
```

The module plans and checkpoints execution; it does not perform external actions, PJe writes,
filing, signing, or publication.

## Dispatch only routed claim tracks

`scripts/build_conditional_work_plan.py` converts the accepted `issue-route` artifact into a
versioned `conditional-work-plan`. Each enabled legal research, evidence analysis, calculation
review, or procedural review flag becomes one stable claim-scoped work item. Disabled tracks do
not appear in the dispatch sequence.

An explicitly abstained claim remains in the plan with its reasons and produces no dispatch. A
routed claim without work, a repeated track, mismatched questions, or a work identifier attached
to another claim fails closed.

```bash
python3 -m unittest tests.test_conditional_work_plan -v
```

This layer controls which work may run. It does not decide a real claim's route and does not
replace the human review and calibration required for `DOM-05`.

## Validate the TRT12 tribunal profile

The profile schema is runtime-neutral. Court values live in `trt12.json`, while provider and
official-source bindings live in the versioned registry. A declared binding records the
contract expected by later adapters; it does not claim that the adapter is implemented or
operationally verified.

```bash
python3 scripts/validate_tribunal_profile.py \
  --schema runtime/profiles/schema.json \
  --registry runtime/profiles/registry.json \
  --profile runtime/profiles/trt12.json
```

The command fails closed on structural drift, an unknown CNJ branch digit, an enabled instance
without a compatible case-system adapter, an unregistered research source or adapter, an empty
signature set, or an MVP policy that permits external filing or signing. First instance is the
only active TRT12 target; publication is also forbidden, and the second-instance contract is
present but disabled.

## Validate legal artifact contracts

The artifact catalog currently covers case context, document classification, procedural
timeline, labor report, claim matrix, evidence matrix, issue routes, precedent corpus, claim
analysis, and disposition matrix. Each schema has independent positive and negative fixtures.

```bash
python3 scripts/validate_artifact_contracts.py \
  --catalog runtime/contracts/catalog.json \
  --fixtures-root tests/fixtures/contracts
```

Use `--contract <id> --document <path>` instead of `--fixtures-root` to validate one generated
artifact. Unknown versions and unknown contracts fail closed. Migration rules are documented
in `runtime/contracts/VERSIONING.md`.

## Classify labor documents with the synthetic baseline

The deterministic classifier consumes normalized provider labels, titles, or local text
excerpts and emits only stable document IDs, taxonomy values, rule IDs, and status. It does not
copy source text into its artifact and preserves `unknown` or `conflict` rather than guessing.

```bash
python3 -m unittest tests.test_labor_document_classifier -v
```

This proves the versioned baseline and output contract, not calibrated accuracy on TRT12 case
files. Calibration requires an approved authorized fixture set.

## Build a source-linked procedural timeline and labor report

`scripts/build_procedural_timeline.py` converts classified PJe PDF segments into one dated,
source-linked event per document. Unknown and conflicting classifications remain explicit gaps.
The CLI refuses repository-local output and existing output files, and writes the protected
artifact with owner-only permissions.

```bash
python3 scripts/build_procedural_timeline.py \
  --segments /protected/input/document-segments.json \
  --classification /protected/input/document-classification.json \
  --output /protected/output
```

The report builder consumes structured candidates after document classification and emits a
deterministic JSON artifact for parties, procedural phase, timeline events, claims, defenses,
and review gaps. Every asserted item retains its source document and locator; unknown or
missing information is never silently completed.

`scripts/extract_pje_labor_report.py` connects the protected PJe PDF, segment map,
classification, and procedural timeline to that builder. Tribunal, instance, and
confidentiality are explicit inputs so the extraction core remains portable. The extractor
checks the PDF digest and page count, requires matching document custody, retains every source
locator, and scans the complete classified initial pleading with
`scripts/extract_labor_positions.py`. Only explicit claim-section headings become positions;
text mentions are ignored, wrapped headings are reconstructed, supported labels keep their
taxonomy names, and unsupported categories retain an `unmapped_` label for later human review.
`scripts/extract_labor_defenses.py` applies the same exact-heading boundary to every classified
defense document. Defense position groups retain document-level custody and distinct stable
identifiers, while an absent answer is never inferred. The labor-report v1 gap is global by
position kind; claim-level defense coverage remains the responsibility of the claim matrix.

```bash
python3 scripts/extract_pje_labor_report.py \
  --input /protected/process.pdf \
  --segments /protected/input/document-segments.json \
  --classification /protected/input/document-classification.json \
  --timeline /protected/input/procedural-timeline.json \
  --output /protected/output \
  --tribunal TRT12 \
  --instance 1 \
  --confidentiality public_or_authorized
```

```bash
python3 -m unittest \
  tests.test_procedural_timeline_builder \
  tests.test_labor_report_builder \
  tests.test_labor_position_extraction \
  tests.test_labor_defense_extraction \
  tests.test_pje_labor_report_extraction \
  -v
```

This establishes the deterministic DOM-02 timeline, context, party, and report assembly
boundary. Claim-level respondent linkage, multi-case calibration, and blind review against
approved TRT12 fixtures remain separate acceptance evidence.

## Build a claim and requested-remedy matrix

`runtime/domain/labor-claim-taxonomy.json` defines the versioned baseline labels and compatible
requested remedies. `scripts/build_claim_matrix.py` consumes structured claim and defense
candidates, preserves multiple respondent positions, and emits source-linked entries under the
shared `claim-matrix` contract. Unsupported labels or remedies remain visible review gaps.

```bash
python3 -m unittest tests.test_claim_matrix_builder -v
```

The taxonomy is a synthetic engineering baseline. Its recall and category coverage are not
accepted until calibrated against an approved TRT12 sample.

## Build a claim-linked evidence matrix

`scripts/build_evidence_matrix.py` assembles evidence candidates against known claim and
document manifests. It retains source locators and limitations, records whether an item
supports, opposes, or contextualizes a claim, normalizes contradiction links symmetrically,
and reports every claim without evidence coverage.

```bash
python3 -m unittest tests.test_evidence_matrix_builder -v
```

This synthetic boundary does not assess evidentiary weight or prove completeness on real TRT12
cases. Those conclusions remain subject to authorized calibration and human review.

## Build claim-level issue routes

`scripts/build_issue_routes.py` requires exactly one route candidate for every known claim.
Enabled legal and evidentiary tracks must carry concrete questions, while calculation and
procedural tracks remain explicit booleans with an overall explanation. If no track can be
selected, the result is an explicit `abstained` route with one or more reasons; silent omission
is rejected.

```bash
python3 -m unittest tests.test_issue_router -v
```

The builder validates coverage and internal consistency. It does not decide which legal route
is correct for a real TRT12 claim without approved source material and human review.

## Build claim decisions and a review draft

`scripts/build_claim_decisions.py` assembles exactly one analysis and one linked disposition
for every known claim, then renders a deterministic Markdown draft. Merits outcomes require
facts, evidence identifiers, an evidence assessment, applicable rules, and reasoning.
Procedural outcomes require facts and rules. Pending or abstained analyses must retain an
explicit limitation.

```bash
python3 -m unittest tests.test_claim_decision_builder -v
```

The draft is a structured review artifact, not a judicial act ready for signature or
publication. Real TRT12 correctness, house style, calculation criteria, and disposition
language remain subject to authorized fixtures and human review.

## Verify provider interface conformance

The provider manifest defines capabilities for PJe case acquisition and official-source legal
research. Concrete implementations must satisfy the typed requests and responses plus the
deterministic runners in `scripts/provider_interfaces.py`.

```bash
python3 -m unittest tests.test_provider_interfaces -v
```

The synthetic suite uses a non-target tribunal code and covers complete fake-provider flows,
missing capabilities, repeated pagination cursors, download hash mismatches, and non-HTTPS
official sources. Passing it proves interface conformance only; it does not prove real PJe or
research-provider access.

The session classifier is a separate provider-neutral layer. It consumes only sanitized
status, marker, cookie-name, and header-name evidence and fails closed on contradictions or
missing evidence:

```bash
python3 -m unittest tests.test_pje_session_adapter -v
```

This test does not perform authentication. Binding the classifier to TRT12 remains dependent
on an authorized and reviewed endpoint map.

Task and case discovery uses the same boundary: adapters normalize provider responses while
the shared runner verifies complete pagination, stable identifiers, CNJ region consistency,
and secret-free deterministic output:

```bash
python3 -m unittest tests.test_pje_task_discovery -v
```

The synthetic probe does not establish any TRT12 endpoint or task name.

Authorized PJe HAR captures can be reduced to a deterministic, secret-free endpoint map with
`scripts/sanitize_pje_har.py`. The raw HAR must remain outside the repository. See
`runtime/providers/README.md` for the sanitization command and the separate map-review gate.

## Validate the Python contract

The core scripts support Python 3.9+. Local MCP servers use the MCP SDK 1.x contract and
require Python 3.10+.

```bash
python3 scripts/check_python_contract.py \
  --root . \
  --contract runtime/python-contract.json \
  --mode core

python3 scripts/check_python_contract.py \
  --root . \
  --contract runtime/python-contract.json \
  --mode mcp
```

The validator also rejects ambiguous `python` and direct `pip` command references in
executable documentation and scaffold source files.

## Validate data hygiene

The data-hygiene contract defines required ignore rules, forbidden sensitive paths,
sanitized-fixture exceptions, content detectors, and the maximum scannable fixture size.

```bash
python3 scripts/check_data_hygiene.py \
  --root . \
  --contract runtime/data-hygiene-contract.json
```

The checker reads only Git-tracked and non-ignored commit candidates. It never prints a
matched credential value.
