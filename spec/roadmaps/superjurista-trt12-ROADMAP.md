# Roadmap: SuperJurista TRT12

**Status:** Active and approved
**Version:** 0.34.0
**Date:** 2026-09-21
**Blueprint:** [`superjurista-trt12-first-instance-BLUEPRINT.md`](../blueprints/superjurista-trt12-first-instance-BLUEPRINT.md)

---

## 1. Purpose

This roadmap measures delivered capability, not activity. A work item contributes to progress
only after its acceptance gate passes and its evidence is linked in this document.

The roadmap answers four operating questions:

1. What is the next bounded delivery target?
2. How much validated capability exists now?
3. What evidence supports the reported percentage?
4. What is blocking the next milestone?

---

## 2. Program Structure

The program has three independently measured tracks:

| Track | Outcome | Program weight | Initial state |
|---|---|---:|---:|
| A | TRT12 first-instance validated MVP | 60% | 0/100 accepted points |
| B | TRT12 second-instance validated extension | 25% | 0/100 accepted points |
| C | Multi-TRT portability proof | 15% | 0/100 accepted points |

### 2.1 Program progress formula

```text
PROGRAM_PROGRESS =
    0.60 × TRACK_A_PROGRESS
  + 0.25 × TRACK_B_PROGRESS
  + 0.15 × TRACK_C_PROGRESS
```

Each track score ranges from 0 to 100. The program reaches 60% when the TRT12 first-instance
MVP is fully accepted, even if no second-instance or multi-TRT work has started. This prevents
future scope from hiding whether the first usable target is actually ready.

### 2.2 Current baseline

```text
Track A — TRT12 first instance: 48/100 accepted points
Track B — TRT12 second instance: 0/100 accepted points
Track C — multi-TRT:            0/100 accepted points
Program progress:               28.8%
Track A candidate in review:    4/100 points
```

The blueprint and roadmap were explicitly approved by the user on 2026-09-21. `ARC-01` is
therefore accepted and earns its three points. The remaining candidate points are reported
separately and never contribute to the program progress formula before their technical gates
pass.

---

## 3. Status and Evidence Rules

### 3.1 Status values

| Status | Meaning | Earned points |
|---|---|---:|
| `PLANNED` | Defined but not started | 0 |
| `IN_PROGRESS` | Work exists but acceptance gate has not passed | 0 |
| `BLOCKED` | Cannot advance without a named dependency or decision | 0 |
| `IN_REVIEW` | Candidate evidence exists and is being evaluated | 0 |
| `ACCEPTED` | Acceptance gate passed and evidence is linked | Full item weight |
| `REOPENED` | Previously accepted evidence was invalidated | 0 until reaccepted |

Partial percentages are prohibited at work-item level. They are subjective and easy to game.
Incremental progress comes from using small independently acceptable work items.

### 3.2 Evidence requirements

Every `ACCEPTED` item must record:

- commit or pull request;
- files delivered;
- validation commands and results;
- fixture, dataset, or case sample used;
- reviewer or approval record when human judgment is required;
- known limitations that remain outside the item.

Documentation alone cannot prove runtime behavior. Synthetic tests cannot prove historical
legal adequacy. A successful historical case cannot prove adapter reproducibility.

### 3.3 Reopening rule

An accepted item returns to `REOPENED` when:

- a regression invalidates its acceptance evidence;
- a contract changes incompatibly;
- an official source or endpoint changes materially;
- a critical defect is traced to that item.

The points are removed until the item passes its gate again.

---

## 4. Track A — TRT12 First-Instance MVP

Track A contains exactly 100 points.

### 4.1 Work-package summary

| Work package | Weight | Accepted | Status |
|---|---:|---:|---|
| FND — Foundation hardening | 8 | 8 | `ACCEPTED` |
| ARC — Architecture and contracts | 12 | 12 | `ACCEPTED` |
| PJE — TRT12 PJe-JT acquisition | 18 | 0 | `IN_PROGRESS` |
| DOM — Labor domain capabilities | 20 | 0 | `IN_PROGRESS` |
| JUR — Authoritative research | 15 | 11 | `IN_PROGRESS` |
| PIP — End-to-end pipeline and gates | 15 | 15 | `ACCEPTED` |
| VAL — Historical validation | 10 | 2 | `IN_PROGRESS` |
| OPS — Controlled pilot readiness | 2 | 0 | `PLANNED` |
| **Total** | **100** | **48** |  |

### 4.2 Foundation hardening — 8 points

The first implementation package is `PKG-01 — Fork Baseline and Dual-Runtime Contract`. It
starts with `FND-04` and produces the evidence required to adapt the fork without a rewrite.

`PKG-01` delivers:

- a file-level inventory of existing commands, agents, skills, scripts, and providers;
- a Preserve/Adapt/Replace/Retire disposition for every in-scope component;
- characterization tests for reusable deterministic behavior;
- a map of Claude-specific bindings and their Codex equivalents;
- the proposed runtime-neutral pipeline manifest boundary;
- one minimal smoke path proving that Claude Code and Codex can invoke the same shared gate.

`PKG-01` is accepted when `FND-04` passes. It earns 2 Track A points. It does not claim that
the labor pipeline or either complete runtime is ready.

| ID | Deliverable | Points | Status | Acceptance gate | Evidence |
|---|---|---:|---|---|---|
| FND-01 | Cross-platform Python and dependency contract | 2 | `ACCEPTED` | Installer and documented commands run on the target macOS environment; supported Python version is consistent with code | [`runtime/python-contract.json`](../../runtime/python-contract.json), [`requirements`](../../requirements), [`scripts/check_python_contract.py`](../../scripts/check_python_contract.py), [`scripts/rehearse_target_host.py`](../../scripts/rehearse_target_host.py), `tests/test_python_contract.py`, and `tests/test_target_host_rehearsal.py`; a clean `.venv` was installed on the target macOS host with Python 3.12.14, MCP 1.30.0, the complete runtime dependency set, Tesseract 5.5.3 with Portuguese data, and Poppler 26.05. The five preserved MCP servers imported successfully and the preserved PDF converter recognized both frozen Portuguese phrases from a one-page synthetic PDF. The machine-readable rehearsal returned `ready` with evidence digest `f925340cc3be04b5ef1dffe47ac317a64e0ec452eb6688f5350dc571647f1515`; five focused tests reject missing dependencies, unsupported versions, partial OCR, incomplete MCP coverage, and unknown evidence fields |
| FND-02 | Automated quality suite and CI entry point | 2 | `ACCEPTED` | One documented command runs format/static checks/tests; CI or equivalent clean-room execution passes | [`scripts/quality_gate.py`](../../scripts/quality_gate.py), [`.github/workflows/quality.yml`](../../.github/workflows/quality.yml), `tests/test_quality_gate.py`; the shared command passes 130 tests locally, and [GitHub Actions run 35657051683](https://github.com/robertishimurasousa/superjurista-trt/actions/runs/35657051683) passed on Python 3.9 and 3.10 for commit `cf78b5c` |
| FND-03 | Credential and case-data hygiene | 2 | `ACCEPTED` | Tests prove `.env`, sessions, HARs, cookies, headers, and case data are excluded or redacted | [`runtime/data-hygiene-contract.json`](../../runtime/data-hygiene-contract.json), [`scripts/check_data_hygiene.py`](../../scripts/check_data_hygiene.py), `tests/test_data_hygiene.py`, `.gitignore`, and `scaffold/project-gitignore`; the integrated quality gate passes 130 tests and the focused 11-test hygiene review passes without reading external symlink targets or printing matched secret values |
| FND-04 | Fork inventory, characterization, and dual-runtime reuse ledger | 2 | `ACCEPTED` | Every in-scope existing command, agent, skill, script, and provider has a Preserve/Adapt/Replace/Retire disposition; reusable behavior has characterization evidence; Claude bindings have Codex mappings; both runtimes invoke one shared smoke gate | [`spec/inventory`](../inventory/README.md), [`runtime`](../../runtime/README.md), `tests/test_reuse_ledger.py`, `tests/test_runtime_contract.py`; the 130-test suite and focused reuse/runtime review pass, with 107 components and 0 unclassified |

### 4.3 Architecture and contracts — 12 points

| ID | Deliverable | Points | Status | Acceptance gate | Evidence |
|---|---|---:|---|---|---|
| ARC-01 | Blueprint and evidence-weighted roadmap | 3 | `ACCEPTED` | User explicitly approves scope, sequencing, extension boundaries, and progress model | User approval recorded on 2026-09-21; this blueprint and roadmap revision; repository commit history |
| ARC-02 | Versioned tribunal-profile schema and TRT12 profile | 2 | `ACCEPTED` | Valid profile passes; invalid branch digit, adapter, source, or signature fixtures fail closed | [`runtime/profiles`](../../runtime/profiles), [`scripts/validate_tribunal_profile.py`](../../scripts/validate_tribunal_profile.py), `tests/test_tribunal_profile.py`; the shared quality gate validates the canonical profile, and 10 focused tests cover the valid first-instance profile plus fail-closed branch, adapter, source, signature, safety-policy, and schema-drift cases |
| ARC-03 | Versioned case, document classification, labor report, claim, evidence, route, precedent, analysis, and disposition schemas | 3 | `ACCEPTED` | Positive and negative schema fixtures pass; migration/version policy documented | [`runtime/contracts`](../../runtime/contracts), [`scripts/validate_artifact_contracts.py`](../../scripts/validate_artifact_contracts.py), `tests/fixtures/contracts`, and `tests/test_artifact_contracts.py`; nine valid and twelve invalid fixtures pass the shared contract suite, including cross-field route consistency and merits-analysis completeness, direct artifact validation rejects future versions, and the versioning policy requires immutable accepted schemas plus deterministic non-destructive migrations |
| ARC-04 | PJe and research adapter interfaces | 2 | `ACCEPTED` | Contract tests execute against a fake provider without TRT12 constants in core modules | [`runtime/providers`](../../runtime/providers), [`scripts/provider_interfaces.py`](../../scripts/provider_interfaces.py), `tests/provider_fakes.py`, and `tests/test_provider_interfaces.py`; six fake-provider tests use TRT99 to cover both happy paths plus missing capability, repeated cursor, SHA-256 mismatch, and non-HTTPS official-source rejection |
| ARC-05 | Runtime-neutral execution manifest and Claude/Codex adapter contracts | 2 | `ACCEPTED` | The same fixture graph, dependencies, retry limits, artifact paths, and gates are resolved by both runtime adapters | [`runtime/pipelines/trt12-first-instance.json`](../../runtime/pipelines/trt12-first-instance.json), [`scripts/resolve_runtime_pipeline.py`](../../scripts/resolve_runtime_pipeline.py), `tests/test_pipeline_resolution.py`; both runtimes resolve the same contract digest |

### 4.4 TRT12 PJe-JT acquisition — 18 points

| ID | Deliverable | Points | Status | Acceptance gate | Evidence |
|---|---|---:|---|---|---|
| PJE-01 | Authorized, sanitized TRT12 first-instance HAR map | 3 | `IN_PROGRESS` | Endpoint, cookie/header, task, document, and failure-state map reviewed; no credential remains in the fixture | [`runtime/providers`](../../runtime/providers), [`scripts/sanitize_pje_har.py`](../../scripts/sanitize_pje_har.py), [`scripts/validate_pje_har_map.py`](../../scripts/validate_pje_har_map.py), `tests/test_pje_har_sanitizer.py`, and `tests/test_pje_har_map_review.py`; thirteen synthetic tests prove deterministic redaction, endpoint classification, failure mapping, integrity verification, review-gap reporting, target binding, and fail-closed handling. An authorized TRT12 capture and human map review remain required |
| PJE-02 | Session and authentication adapter | 4 | `IN_PROGRESS` | Detects valid, expired, MFA-required, and unauthorized states without leaking secrets | [`runtime/providers/pje-session-contract.json`](../../runtime/providers/pje-session-contract.json), [`scripts/pje_session_adapter.py`](../../scripts/pje_session_adapter.py), and `tests/test_pje_session_adapter.py`; nine synthetic TRT99 tests cover valid, expired, MFA-required, unauthorized, conflicting, and insufficient-evidence states plus capability enforcement and secret-free output. A concrete TRT12 probe and authorized real-state evidence remain required |
| PJE-03 | Task and process discovery | 3 | `IN_PROGRESS` | Reproducibly lists the authorized target queue and identifies case numbers with no silent pagination loss | [`runtime/providers/pje-task-discovery-contract.json`](../../runtime/providers/pje-task-discovery-contract.json), [`scripts/pje_task_discovery.py`](../../scripts/pje_task_discovery.py), and `tests/test_pje_task_discovery.py`; eight synthetic TRT99 tests cover complete two-level pagination, empty queues, repeated cursors, duplicate cases, CNJ region mismatch, capability enforcement, and secret-free output. A concrete TRT12 adapter and authorized queue rehearsal remain required |
| PJE-04 | Document index and download | 4 | `IN_PROGRESS` | Produces stable IDs, hashes, metadata, and explicit gaps for the rehearsal set | [`runtime/providers/document-index-contract.json`](../../runtime/providers/document-index-contract.json), [`scripts/acquire_pje_documents.py`](../../scripts/acquire_pje_documents.py), and `tests/test_pje_document_acquisition.py`; eight synthetic TRT99 tests cover deterministic two-page indexing and download, requested subsets, stable metadata, SHA-256 custody, missing requested documents, explicit provider-unavailability gaps, duplicate identifiers, repeated cursors, requested-ID validation, and schema-valid output. A concrete TRT12 adapter bound to the reviewed capture plus an authorized closed document rehearsal remain required |
| PJE-05 | Recovery and reproducibility | 4 | `IN_PROGRESS` | Repeated closed rehearsal succeeds at least 95%; retries are bounded and failures remain resumable | [`runtime/providers/pje-recovery-state.v1.schema.json`](../../runtime/providers/pje-recovery-state.v1.schema.json), [`scripts/recover_pje_acquisition.py`](../../scripts/recover_pje_acquisition.py), [`scripts/acquire_pje_documents.py`](../../scripts/acquire_pje_documents.py), and `tests/test_pje_recovery.py`; nine synthetic TRT99 tests prove atomic checkpoints, bounded immutable retry ceilings, accepted-payload reuse, explicit subsets, request binding, catalog and local-payload custody, semantic checkpoint validation, and deterministic exhaustion. Repeated authorized TRT12 closed rehearsals and the empirical 95% success result remain required |

### 4.5 Labor domain capabilities — 20 points

| ID | Deliverable | Points | Status | Acceptance gate | Evidence |
|---|---|---:|---|---|---|
| DOM-01 | Labor document classification | 3 | `IN_PROGRESS` | Approved fixture set meets the calibrated document-type target and preserves unknown type | [`runtime/domain/labor-document-classification.json`](../../runtime/domain/labor-document-classification.json), [`runtime/contracts/schemas/document-classification.v1.schema.json`](../../runtime/contracts/schemas/document-classification.v1.schema.json), [`scripts/classify_labor_documents.py`](../../scripts/classify_labor_documents.py), and `tests/test_labor_document_classifier.py`; eight synthetic tests cover core labor types, explicit unknown, specific-rule precedence, accent/case normalization, conflict handling, deterministic ordering, duplicate IDs, and source-text exclusion. Calibration against an approved authorized TRT12 fixture set remains required |
| DOM-02 | Procedural timeline and labor report | 3 | `IN_PROGRESS` | Dates, parties, procedural phase, claims, defenses, and source locators pass blind sample review | [`runtime/contracts/schemas/labor-report.v1.schema.json`](../../runtime/contracts/schemas/labor-report.v1.schema.json), [`scripts/build_labor_report.py`](../../scripts/build_labor_report.py), and `tests/test_labor_report_builder.py`; seven synthetic tests cover deterministic ordering, source custody, explicit unknown phase and missing defense, manifest boundaries, duplicate stable IDs, phase evidence, context-schema boundaries, and input immutability. Blind review against an approved authorized TRT12 fixture set remains required |
| DOM-03 | Claim and requested-remedy matrix | 4 | `IN_PROGRESS` | At least 95% recall during calibration and 100% claim coverage on the final acceptance sample | [`runtime/domain/labor-claim-taxonomy.json`](../../runtime/domain/labor-claim-taxonomy.json), [`runtime/contracts/schemas/claim-matrix.v1.schema.json`](../../runtime/contracts/schemas/claim-matrix.v1.schema.json), [`scripts/build_claim_matrix.py`](../../scripts/build_claim_matrix.py), and `tests/test_claim_matrix_builder.py`; eight synthetic tests cover deterministic assembly, multiple defenses, source custody, explicit missing or unsupported information, manifest boundaries, orphan defenses, stable-ID uniqueness, and taxonomy integrity. Recall and final claim coverage remain dependent on approved TRT12 calibration and acceptance samples |
| DOM-04 | Evidence matrix | 4 | `IN_PROGRESS` | Every material proposition links to a source locator; limitations and conflicting evidence are preserved | [`runtime/contracts/schemas/evidence-matrix.v1.schema.json`](../../runtime/contracts/schemas/evidence-matrix.v1.schema.json), [`scripts/build_evidence_matrix.py`](../../scripts/build_evidence_matrix.py), and `tests/test_evidence_matrix_builder.py`; eight synthetic tests cover deterministic assembly, claim coverage, symmetric conflicts, manifest and claim boundaries, self or missing conflict rejection, stable-ID uniqueness, and disputed-status consistency. Blind material-proposition review against an approved TRT12 fixture set remains required |
| DOM-05 | Claim-level issue routing | 3 | `IN_PROGRESS` | Every claim receives an explainable legal/evidence/calculation/procedural route or explicit abstention | [`runtime/contracts/schemas/issue-route.v1.schema.json`](../../runtime/contracts/schemas/issue-route.v1.schema.json), [`scripts/build_issue_routes.py`](../../scripts/build_issue_routes.py), and `tests/test_issue_router.py`; eight synthetic tests cover deterministic one-route-per-claim assembly, full manifest coverage, explicit abstention, route/abstention exclusivity, track-question consistency, and duplicate or unknown claim rejection. Blind routing review against an approved TRT12 fixture set remains required |
| DOM-06 | Claim analysis, judgment drafting, and disposition matrix | 3 | `IN_PROGRESS` | All accepted claims have facts, rule, reasoning, outcome, limitations, and disposition linkage | [`runtime/contracts/schemas/claim-analysis.v1.schema.json`](../../runtime/contracts/schemas/claim-analysis.v1.schema.json), [`runtime/contracts/schemas/disposition-matrix.v1.schema.json`](../../runtime/contracts/schemas/disposition-matrix.v1.schema.json), [`scripts/build_claim_decisions.py`](../../scripts/build_claim_decisions.py), and `tests/test_claim_decision_builder.py`; eight synthetic tests cover deterministic analysis, disposition, and draft assembly, exact claim coverage, evidence custody, outcome completeness, unresolved limitations, stable-ID linkage, and duplicate rejection. Blind legal and drafting review against an approved TRT12 fixture set remains required |

### 4.6 Authoritative research — 15 points

| ID | Deliverable | Points | Status | Acceptance gate | Evidence |
|---|---|---:|---|---|---|
| JUR-01 | TST official-source adapter | 4 | `ACCEPTED` | Retrieves official result, status, reference, URL, and verbatim excerpt for the test queries | [`scripts/tst_official_adapter.py`](../../scripts/tst_official_adapter.py), `tests/test_tst_official_adapter.py`, and [`runtime/providers`](../../runtime/providers); 12 synthetic tests cover normalized search, exact-CNJ filtering, pagination, schema-valid corpus generation, verbatim custody, source and origin restrictions, response limits, and publication-date variants. A bounded live query on 2026-09-21 retrieved TST document `7a2d741d22e82084a45f85ba428fa103` from the official HTTPS backend and generated one valid source while preserving status `unknown` for human review |
| JUR-02 | TRT12 jurisprudence adapter | 4 | `IN_REVIEW` | Covers the approved TRT12 source set and distinguishes PJe/current material from legacy coverage | [`scripts/trt12_official_adapter.py`](../../scripts/trt12_official_adapter.py), `tests/test_trt12_official_adapter.py`, and [`runtime/providers`](../../runtime/providers); 10 synthetic tests cover combined sentence/acórdão search, fixed TRT12 scope, zero-based pagination, collection-specific permanent URLs and detail retrieval, verbatim custody, current-PJe versus legacy coverage, schema-valid corpus generation, shared-interface conformance, session bootstrap, response limits, and fail-closed ambiguous records. The official TRT12 portal was verified to delegate current PJe research to Falcão for first- and second-instance documents from 2016 onward. Live source acceptance remains pending because Falcão activated its published network rate-limit window during the bounded integration probe |
| JUR-03 | TRT12 precedent adapter | 3 | `ACCEPTED` | Captures IRDR/IAC/regional thesis status, scope, suspension, and official source | [`scripts/trt12_precedent_adapter.py`](../../scripts/trt12_precedent_adapter.py), `tests/test_trt12_precedent_adapter.py`, and [`runtime/providers`](../../runtime/providers); 11 network-free tests cover current, cancelled, pending, and stayed IRDR states, active second-instance suspension, bounded pagination, the official Google Visualization header shape, current and cancelled IUJ theses, explicit no-thesis IAC coverage without a fabricated precedent, shared-interface conformance, exact publication URL restrictions, response limits, and schema-valid corpus generation. Bounded live checks on 2026-09-21 retrieved IRDR Theme 34 as stayed with an active second-instance suspension, confirmed the official IAC no-thesis statement, and retrieved current IUJ Thesis 3 from the official TRT12 publications |
| JUR-04 | Precedent consolidation and citation custody | 4 | `ACCEPTED` | Deduplication, hierarchy, status conflicts, and quotation custody pass deterministic fixtures | [`scripts/consolidate_precedents.py`](../../scripts/consolidate_precedents.py), `tests/test_precedent_consolidation.py`, and [`runtime/providers`](../../runtime/providers); 11 deterministic tests cover hierarchy ordering, exact duplicate removal, conflicting repeated identifiers, equivalent-source canonicalization, alias custody, explicit status conflicts, unknown-status precedence, quotation custody, deterministic sidecar serialization, invalid input contracts, and schema-valid consolidated output. Every original source retains an official URL and SHA-256 excerpt digest in the sidecar report |

### 4.7 End-to-end pipeline and gates — 15 points

| ID | Deliverable | Points | Status | Acceptance gate | Evidence |
|---|---|---:|---|---|---|
| PIP-01 | Resumable first-instance orchestrator for Claude Code and Codex | 3 | `ACCEPTED` | On both runtimes, an interrupted fixture resumes without rerunning accepted stages or trusting stale stages | [`scripts/resumable_pipeline.py`](../../scripts/resumable_pipeline.py), [`runtime/pipelines/execution-state.v1.schema.json`](../../runtime/pipelines/execution-state.v1.schema.json), `tests/test_resumable_pipeline.py`, and [`runtime`](../../runtime); 10 deterministic tests cover interrupted resume, cross-runtime checkpoint reuse with runtime-specific dispatch, output and dependency freshness, current-gate revalidation, source and contract invalidation, dependency order, bounded attempts, required outputs, atomic persistence, and schema-valid runtime-neutral state. No external action capability is present |
| PIP-02 | Conditional claim tracks | 3 | `ACCEPTED` | Research, evidence, calculation, and procedural tracks run only when routed; abstention remains valid | [`scripts/build_conditional_work_plan.py`](../../scripts/build_conditional_work_plan.py), [`runtime/pipelines/conditional-work-plan.v1.schema.json`](../../runtime/pipelines/conditional-work-plan.v1.schema.json), and `tests/test_conditional_work_plan.py`; 11 deterministic tests cover exact per-claim track dispatch, zero-dispatch abstention, mixed routed/abstained fixtures, stable ordering and identifiers, route-status consistency, question and abstention boundaries, duplicate claims, invalid input contracts, schema-valid output, and fail-closed routed claims with missing work |
| PIP-03 | Claim/reasoning/disposition congruence gates | 4 | `ACCEPTED` | Missing claims and orphan dispositions fail; acceptance fixture reaches 100% coverage | [`scripts/validate_decision_congruence.py`](../../scripts/validate_decision_congruence.py), [`runtime/pipelines/decision-congruence-report.v1.schema.json`](../../runtime/pipelines/decision-congruence-report.v1.schema.json), and `tests/test_decision_congruence.py`; 14 deterministic tests prove exact 100% analysis, disposition, and draft coverage plus fail-closed handling of missing, duplicate, unknown, mismatched, empty-reasoning, source-link, outcome, heading, identifier, and schema-drift cases |
| PIP-04 | Citation, source, calculation, and final gates | 3 | `ACCEPTED` | Unsupported quotations and inconsistent criteria fail closed; source unavailability is explicit | [`scripts/evaluate_final_gate.py`](../../scripts/evaluate_final_gate.py), [`runtime/pipelines/final-review.v1.schema.json`](../../runtime/pipelines/final-review.v1.schema.json), [`runtime/pipelines/global-gate.v1.schema.json`](../../runtime/pipelines/global-gate.v1.schema.json), and `tests/test_final_acceptance_gate.py`; 13 deterministic tests cover supported and unsupported quotations, the calibrated short-quotation boundary, missing and unavailable sources, exact calculation-criteria agreement, not-required and unavailable calculations, duplicate reviews, upstream congruence failure, schema-valid reporting, and fail-closed enforcement. Unavailability yields an explicit `blocked` report with subject and reason rather than silent acceptance |
| PIP-05 | Cross-runtime synthetic/sanitized end-to-end fixture | 2 | `ACCEPTED` | Claude Code and Codex each produce all required artifacts and a passing shared global gate from a clean workspace | [`scripts/run_synthetic_pipeline.py`](../../scripts/run_synthetic_pipeline.py), `tests/fixtures/pipeline/synthetic-first-instance.json`, and `tests/test_cross_runtime_pipeline.py`; four subprocess tests execute both runtime adapters from empty workspaces, produce all 19 manifest-required outputs, preserve runtime-specific dispatch only in the execution manifest, prove byte-identical shared artifacts and digest, reach the same passing global gate, reject non-empty workspaces, and fail closed on fixture contract tampering. The fixture contains no real process data and does not establish live PJe operation or legal adequacy |

### 4.8 Historical validation — 10 points

| ID | Deliverable | Points | Status | Acceptance gate | Evidence |
|---|---|---:|---|---|---|
| VAL-01 | Frozen historical validation protocol | 2 | `ACCEPTED` | Sampling, claim categories, reviewer form, severity scale, and analysis plan are fixed before outcomes | [`runtime/validation/historical-validation-protocol.v1.json`](../../runtime/validation/historical-validation-protocol.v1.json), [`runtime/validation/historical-validation-protocol.v1.schema.json`](../../runtime/validation/historical-validation-protocol.v1.schema.json), [`spec/validation/historical-blind-review-form.md`](../validation/historical-blind-review-form.md), [`scripts/validate_historical_protocol.py`](../../scripts/validate_historical_protocol.py), and `tests/test_historical_validation_protocol.py`; nine deterministic tests freeze a 20-case authorized sample method with 15 development and five untouched holdout cases, claim categories, blind scoring and adjudication, the complete reviewer form, zero critical/high defect budgets, 95% claim recall, 100% claim coverage, quotation support, and source-locator traceability, plus rejection of post-hoc outcomes or threshold drift |
| VAL-02 | Blind historical review | 4 | `PLANNED` | Approved sample is completed; defects are traceable by stage and severity | — |
| VAL-03 | Correction and untouched rerun | 2 | `PLANNED` | Critical/high defects are corrected and rerun on an untouched subset without regression | — |
| VAL-04 | Acceptance dossier | 2 | `PLANNED` | Results, limitations, failure modes, and go/no-go recommendation are approved | — |

### 4.9 Controlled pilot readiness — 2 points

| ID | Deliverable | Points | Status | Acceptance gate | Evidence |
|---|---|---:|---|---|---|
| OPS-01 | Installation and operator runbook | 1 | `PLANNED` | A clean operator rehearsal completes using only the runbook | — |
| OPS-02 | Pilot safety and rollback plan | 1 | `PLANNED` | Human review, incident handling, rollback, retention, and support ownership are approved | — |

---

## 5. Track A Milestones

| Milestone | Required accepted items | Outcome |
|---|---|---|
| M0 — Safe reusable foundation | FND-01 through FND-04 | Existing value is characterized and the repository can support trustworthy incremental implementation |
| M1 — Contract freeze | ARC-01 through ARC-04 | Core/profile boundary is executable and versioned |
| M2 — Authorized acquisition | PJE-01 through PJE-05 | TRT12 first-instance records can be acquired reproducibly |
| M3 — Structured case | DOM-01 through DOM-05 | Case becomes traceable claims, defenses, evidence, and routes |
| M4 — Authoritative research | JUR-01 through JUR-04 | Research corpus is official, ranked, and auditable |
| M5 — Complete draft pipeline | DOM-06 and PIP-01 through PIP-05 | End-to-end draft and all gates execute |
| M6 — Historically validated | VAL-01 through VAL-04 | Quality is measured on frozen historical evidence |
| M7 — Pilot candidate | OPS-01 and OPS-02 | Controlled human-supervised pilot may be considered |

Milestones are dependency gates, not dates. Calendar dates will be added after implementation
capacity and access to TRT12 fixtures are known.

---

## 6. Track B — TRT12 Second Instance

Track B starts only after Track A milestone M5 unless an explicit architectural dependency
must be resolved earlier.

| Work package | Weight | Acceptance outcome |
|---|---:|---|
| B-ARC — Appellate contracts and scope | 10 | Versioned appealed-chapter and appellate-disposition schemas |
| B-PJE — TRT12 second-instance acquisition | 20 | Verified second-instance PJe adapter |
| B-DOM — Appeal analysis and vote drafting | 30 | Admissibility, devolutive scope, chapter outcome, and vote artifacts |
| B-JUR — Panel and divergence research | 10 | Regional panel/divergence metadata and authority handling |
| B-PIP — Second-instance orchestrator and gates | 15 | Resumable vote pipeline with appellate congruence gates |
| B-VAL — Historical blind validation | 12 | Frozen protocol, review, correction, untouched rerun |
| B-OPS — Controlled pilot readiness | 3 | Runbook and human-supervised pilot approval |
| **Total** | **100** |  |

Track B remains 0 until its items are decomposed into evidence-bearing tasks and accepted.

---

## 7. Track C — Multi-TRT Portability

Track C begins with one intentionally selected second TRT. It does not begin by duplicating
TRT12 files.

| Work package | Weight | Acceptance outcome |
|---|---:|---|
| C-ABS — Review real variability and refine interfaces | 10 | Differences are evidenced, not guessed |
| C-PRO — Second-TRT profile | 20 | Valid court profile and local policy |
| C-PJE — Second-TRT PJe adapter/shared-adapter proof | 25 | Acquisition passes tribunal-specific rehearsals |
| C-JUR — Second-TRT research adapter | 20 | Regional precedents and jurisprudence are verified |
| C-REG — Cross-TRT regression suite | 20 | TRT12 remains green while second TRT passes |
| C-OPS — Portability runbook | 5 | A third profile can follow a documented process |
| **Total** | **100** |  |

Only after Track C reaches 100 may the project describe itself as validated for more than one
TRT.

---

## 8. Quality KPIs

Progress points answer “how much accepted capability exists?” Quality KPIs answer “is the
capability trustworthy enough to advance?”

### 8.1 Primary KPIs

| KPI | Definition | Target | Decision supported |
|---|---|---:|---|
| Accepted capability progress | Accepted Track A points divided by 100 | 100% for MVP | Delivery readiness |
| End-to-end accepted-run rate | Runs passing every required gate / eligible runs | Calibrate, then at least 95% | Operational reliability |
| Critical legal defect rate | Critical defects / blindly reviewed cases | 0 before pilot | Go/no-go |

### 8.2 Driver metrics

| Metric | Definition | Use |
|---|---|---|
| Claim extraction recall | Gold claims found / gold claims | Diagnose omitted requests |
| Congruence coverage | Claims with reasoning and disposition / mapped claims | Diagnose structural completeness |
| Citation custody rate | Verified external quotations / external quotations | Diagnose source discipline |
| Adapter explicit-failure rate | Explicit failures / all failed operations | Detect silent failure |
| Regression closure rate | Closed accepted defects / discovered accepted defects | Measure learning from failures |
| Fork disposition coverage | In-scope existing components with an evidenced disposition / in-scope existing components | Prevent accidental rewrites and invisible legacy dependencies |
| Reuse realization | Accepted Preserve or Adapt components / components initially eligible for reuse | Show how much of the fork was successfully carried into TRT12 |
| Runtime conformance rate | Shared acceptance fixtures passing on both runtimes / eligible shared fixtures | Detect runtime drift without requiring identical prose |

### 8.3 Guardrails

| Guardrail | Limit |
|---|---|
| Unsupported external quotation | Zero |
| Orphan disposition | Zero |
| Silent missing claim | Zero in acceptance sample |
| Credential or sealed-data leakage in logs/fixtures | Zero |
| External filing/signing/publication action | Zero in MVP |
| Progress item without linked evidence | Cannot be `ACCEPTED` |
| Runtime-specific legal rule or artifact schema | Zero; differences must remain in runtime adapters only |

Targets that depend on empirical distributions remain provisional until calibration. They may
be tightened after the baseline; they may not be relaxed merely to mark a milestone complete.

---

## 9. Review Cadence

Update this roadmap at each accepted pull request or equivalent delivery checkpoint.

### Weekly or milestone review

1. Recalculate accepted points.
2. Verify that every accepted item still has valid evidence.
3. List newly discovered critical/high defects.
4. Name the next highest-value unblocked item.
5. Record blockers with owner and required decision.
6. Update KPI baselines only from reproducible evidence.

### Status report template

```text
Date:
Track A progress: X/100
Program progress: Y%
Milestone reached:
Accepted this period:
Evidence:
Reopened items:
Critical/high defects:
Current blocker:
Next acceptance target:
```

---

## 10. Decision Log

| Date | Decision | Effect |
|---|---|---|
| 2026-09-20 | TRT12 first instance is the first executable target | Track A created |
| 2026-09-20 | TRT12 second instance is a separate future pipeline | Track B created |
| 2026-09-20 | Other TRTs require a portability proof | Track C created |
| 2026-09-20 | Only accepted evidence earns progress points | Binary evidence-weighted scoring adopted |
| 2026-09-20 | The fork is the implementation baseline, not a disposable prototype | Reuse-first brownfield migration and `FND-04` adopted |
| 2026-09-20 | Claude Code and Codex are first-class runtimes over one shared core | Dual-runtime contracts added to Track A |
| 2026-09-20 | Core scripts support Python 3.9+; local MCP servers require Python 3.10+ and MCP SDK 1.x | Executable and dependency contract added in `FND-01` |
| 2026-09-20 | Local development and CI share one deterministic quality command | Python 3.9/3.10 workflow and fail-closed checks added in `FND-02` |
| 2026-09-20 | Sensitive local files remain ignored while tracked and commit-ready files are scanned without echoing values | Executable hygiene contract added in `FND-03` |
| 2026-09-21 | Tribunal structure, provider registry, and TRT12 values are separate versioned contracts | `ARC-02` remains portable while TRT12 first instance is active and second instance is disabled |
| 2026-09-21 | Legal artifact schemas use a versioned catalog and explicit fail-closed migrations | `ARC-03` contracts are shared across Claude Code and Codex without tribunal constants |
| 2026-09-21 | PJe and research providers implement versioned capability contracts | `ARC-04` validates fake TRT99 providers without embedding TRT12 constants in the shared core |
| 2026-09-21 | Raw HAR and session files remain local while reviewed sanitized maps may become evidence | `PJE-01` can map endpoints without retaining credentials, query values, bodies, or dynamic identifiers |
| 2026-09-21 | Sanitized HAR maps require a separate integrity and coverage gate before human review | Missing observations remain explicit and tampered or target-mismatched maps fail closed |
| 2026-09-21 | Session classification is separate from credential acquisition | `PJE-02` can validate secret-free synthetic state observations while the real TRT12 probe remains blocked by `PJE-01` evidence |
| 2026-09-21 | Task and case discovery uses normalized bounded pages | `PJE-03` detects silent pagination loss without adopting TRF5 endpoints, task names, or payload fields as TRT12 facts |
| 2026-09-21 | Labor document triage uses versioned deterministic rules and preserves uncertainty | `DOM-01` can advance on synthetic fixtures without copying case text or claiming calibrated TRT12 accuracy |
| 2026-09-21 | Procedural reports are structured artifacts with mandatory source custody and explicit gaps | `DOM-02` can advance synthetically while real-process calibration remains a separate acceptance gate |
| 2026-09-21 | Claim matrices preserve multiple source-linked defenses and do not normalize taxonomy gaps silently | `DOM-03` can advance synthetically without claiming recall or final coverage before real-fixture review |
| 2026-09-21 | Evidence matrices preserve source custody, claim coverage, limitations, and symmetric contradictions | `DOM-04` can advance synthetically without claiming evidentiary completeness before blind review |
| 2026-09-21 | Every claim must receive one explainable route or an explicit abstention | `DOM-05` rejects silent claim loss and inconsistent downstream work requests before real-process calibration |
| 2026-09-21 | Analysis, outcome, disposition, and draft remain linked by stable decision identifiers | `DOM-06` can advance synthetically without treating an unreviewed draft as a judicial act ready for signature or publication |
| 2026-09-21 | User approved the blueprint, roadmap, target sequence, extension boundaries, traceability rule, progress model, and MVP automation boundary | `ARC-01` accepted; Track A reaches 3% and weighted program progress reaches 1.8% |
| 2026-09-21 | Remote CI and focused foundation/architecture reviews passed | `FND-02` through `FND-04` and `ARC-02` through `ARC-05` accepted; Track A reaches 18% and weighted program progress reaches 10.8% |
| 2026-09-21 | TST research uses its official public search and document endpoints with bounded HTTPS transport and verbatim custody | `JUR-01` accepted; exact CNJ queries use the structured official filter and unnormalized precedential status remains explicit |
| 2026-09-21 | TRT12 current jurisprudence uses the official Falcão sentence and acórdão collections while legacy coverage remains explicit | `JUR-02` enters review with deterministic adapter evidence; acceptance waits for one bounded live sentence/acórdão custody check after the official rate-limit window expires |
| 2026-09-21 | TRT12 regional precedents use the tribunal-linked IRDR tracker and official thesis page with fail-closed source parsing | `JUR-03` accepted; active suspension remains distinct from historical suspension, IAC absence is explicit without a fabricated precedent, and current/cancelled IUJ theses retain official custody |
| 2026-09-21 | Precedent consolidation preserves provider custody and treats explicit status disagreement as data | `JUR-04` accepted; equivalent sources use deterministic hierarchy, discarded aliases remain auditable, and `unknown` never silently overrides an explicit status |
| 2026-09-21 | Accepted stages are reusable only through a runtime-neutral checkpoint bound to current contracts, sources, dependencies, outputs, and gates | `PIP-01` accepted; Claude Code and Codex share resume evidence while retaining separate dispatch bindings, and stale stages invalidate their dependents |
| 2026-09-21 | Conditional work is derived solely from accepted claim-level route flags | `PIP-02` accepted; disabled tracks never dispatch, abstention remains explicit and valid, and routed claims cannot silently lose all work items |
| 2026-09-21 | Decision artifacts require an independent congruence gate after generation | `PIP-03` accepted; every known claim must have exactly one non-empty analysis, matching disposition, outcome, source link, and exact draft custody before the report can reach 100% |
| 2026-09-21 | Final acceptance is a machine-readable report followed by mandatory enforcement | `PIP-04` accepted; unsupported long quotations and mismatched calculations fail, source or calculation unavailability blocks with an explicit reason, and no non-passing report can continue |
| 2026-09-21 | Cross-runtime acceptance uses one sanitized fixture and one shared artifact graph | `PIP-05` accepted; Claude Code and Codex produce the same 19 pipeline outputs and final gate from clean workspaces while retaining only their declared dispatch bindings |
| 2026-09-21 | PJe document acquisition separates complete metadata indexing from requested payload download | `PJE-04` can advance on the shared provider interface; downloaded bytes must match the indexed SHA-256, skipped items remain visible, and bounded unavailability becomes an explicit gap instead of silent loss |
| 2026-09-21 | Historical acceptance thresholds and review fields are frozen before case outcomes are observed | `VAL-01` accepted; development and untouched holdout results must remain separate, unavailable evidence is never imputed as a pass, and critical/high defects have zero acceptance budget |
| 2026-09-21 | PJe acquisition recovery is bound to immutable request, catalog, payload, and retry evidence | `PJE-05` can advance synthetically without redownloading accepted payloads or treating exhausted retries as success; empirical acceptance remains tied to authorized TRT12 closed rehearsals |
| 2026-09-21 | Target-host readiness requires an executed MCP and Portuguese OCR rehearsal, not package presence alone | `FND-01` accepted after all five MCP servers imported and the preserved PDF converter completed a real Poppler-to-Tesseract run on macOS; M0 is reached |

---

## 11. Current Blockers and Inputs

| ID | Input or decision | Blocks | Status |
|---|---|---|---|
| BLK-01 | Explicit approval of blueprint and roadmap | ARC-01 | Closed on 2026-09-21 |
| BLK-02 | Authorized TRT12 first-instance HAR capture | PJE-01 onward | Open |
| BLK-03 | Data-handling decision for personal and sealed case data | Real fixtures and PJe acquisition rehearsals | Open |
| BLK-04 | Approved historical sample and reviewer availability | VAL-02 onward | Open |
| BLK-05 | Judgment house style or approved seed document | DOM-06 | Open |
| BLK-06 | Python 3.10+ interpreter on the target macOS host for real local-MCP execution | FND-01 acceptance and local MCP servers | Closed on 2026-09-21 with Python 3.12.14 and MCP 1.30.0 |
| BLK-07 | Target-host Tesseract with Portuguese data and a user-installed Poppler executable | FND-01 OCR rehearsal | Closed on 2026-09-21 with Tesseract 5.5.3, Portuguese data, Poppler 26.05, and successful OCR rehearsal |
| BLK-08 | Commit or pull request plus the first remote GitHub Actions run | FND-02 acceptance evidence | Closed by successful run 35657051683 |
| BLK-09 | Falcão network rate-limit window triggered during the bounded public integration probe | JUR-02 live acceptance evidence | Temporary; retry one bounded query after the official window expires |

Open blockers do not prevent unrelated foundation and contract work.

---

## 12. Next Acceptance Sequence

The recommended sequence after blueprint approval is:

1. Run the sanitizer against an authorized local TRT12 first-instance capture and review the map for `PJE-01`.
2. Bind the session-state classifier to one TRT12 probe from the reviewed endpoint map.
3. Bind task and case discovery to the reviewed TRT12 task and process endpoints.
4. Re-run one bounded `JUR-02` live sentence/acórdão custody check after the official Falcão rate-limit window expires.
5. Bind `PJE-04` to the reviewed TRT12 document endpoints and run an authorized closed download rehearsal.
6. Assemble the authorized 20-case sample and reviewer assignment required to start blind `VAL-02` scoring.

This sequence keeps architecture, security, and objective measurement ahead of real case
processing.
