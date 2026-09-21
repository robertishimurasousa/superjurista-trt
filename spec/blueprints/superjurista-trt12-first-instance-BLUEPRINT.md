# Blueprint: SuperJurista TRT12 — First Instance

**Status:** Draft for architectural approval
**Version:** 0.16.0
**Date:** 2026-09-21
**Primary target:** TRT12 first-instance labor judgments
**Future targets:** TRT12 second instance, then additional Regional Labor Courts
**Progress system:** [`superjurista-trt12-ROADMAP.md`](../roadmaps/superjurista-trt12-ROADMAP.md)

---

## 1. Executive Decision

The project will preserve the deterministic SuperJurista execution kernel and replace the
Federal Justice-specific domain layer with a Labor Justice domain layer.

Claude Code and Codex are both supported execution runtimes. They must consume one shared
legal domain, artifact contract, tribunal profile, deterministic script set, and acceptance
suite. Runtime-specific files may orchestrate work, but may not define divergent legal rules.

The first production-shaped target is **TRT12 first instance**. Second instance and other
TRTs are extension targets, not claims of current compatibility. The architecture must expose
the required extension points now, while implementation and validation remain sequential:

1. TRT12 first instance;
2. TRT12 second instance;
3. one additional TRT as the portability proof;
4. broader multi-TRT support only after the portability proof passes.

This avoids two failure modes:

- hard-coding TRT12 into reusable legal capabilities;
- prematurely generalizing behavior that has not been observed in a second tribunal.

---

## 2. Objective

Build an auditable, resumable, human-supervised system that receives an authorized TRT12
first-instance PJe-JT case, extracts and structures the record, maps every claim and defense,
routes legal and evidentiary issues, researches authoritative precedents, drafts a proposed
labor judgment, and validates the result through deterministic gates on both Claude Code and
Codex.

The final product is a **draft for judicial review**, never an autonomous judicial decision.

### 2.1 Primary input

- an authorized PJe-JT case workspace; or
- a previously downloaded and sanitized case workspace containing the document index and
  source documents.

### 2.2 Primary output

```text
data/judgment/<CNJ_NUMBER>/<CNJ_NUMBER>-labor-judgment.md
```

The workspace also retains the intermediate artifacts, evidence provenance, precedent
provenance, gate results, and execution manifest.

### 2.3 Success definition

The first-instance MVP is successful only when it can reproducibly process the approved
historical validation set while satisfying all critical gates:

- every pleaded claim is represented in the claim matrix;
- every contested claim has an evidence and/or legal-issue route;
- every final disposition maps to a pleaded claim or an explicitly identified matter the
  court may address;
- every external verbatim quotation is traceable to an authorized source;
- no critical legal or factual defect remains in blind review;
- the pipeline resumes without silently skipping invalid or stale artifacts.

---

## 3. Scope

### 3.1 In scope for TRT12 first-instance MVP

- TRT12 first-instance tribunal profile;
- PJe-JT session, task listing, process discovery, document index, and document download;
- labor document classification;
- procedural timeline and labor report;
- claim, defense, evidence, and requested-remedy matrices;
- claim-level routing between legal research, evidentiary analysis, calculation review, and
  procedural review;
- TST, STF/BNP, TRT12 precedent, and TRT12 jurisprudence research;
- claim-level legal analysis;
- labor judgment drafting and deterministic merge;
- congruence, quotation, source, calculation-criteria, and final-integrity gates;
- historical blind validation and a controlled pilot-readiness dossier.

### 3.2 Explicitly out of scope for the first MVP

- autonomous filing, signing, publication, or movement of a case in PJe-JT;
- replacing judicial review;
- TRT12 second-instance votes or judgments;
- declaring compatibility with another TRT without tribunal-specific validation;
- automated monetary liquidation that claims parity with PJe-Calc;
- model training or fine-tuning;
- processing sealed cases without an approved data-handling protocol.

### 3.3 Future scope

- TRT12 second-instance appeal analysis and vote drafting;
- PJe-Calc import/export or independently verified calculation interoperability;
- additional TRT profiles;
- reusable adapters where two or more TRTs demonstrate the same technical contract.

---

## 4. Governing Principles

1. **One validated target at a time.** TRT12 first instance is the only executable target in
   the first delivery wave.
2. **Core versus profile separation.** Reusable agents cannot contain TRT12 URLs, court-unit
   names, local chamber names, or authentication constants.
3. **Claim-level reasoning.** A labor case is not one indivisible question. Each claim is a
   traceable decision unit.
4. **The file is the state.** Agents write artifacts to disk and return one status line.
5. **Gates, not confidence prose.** Completion is determined by scripts and review evidence.
6. **Fail closed.** Missing, unreadable, stale, or inconsistent evidence blocks advancement.
7. **No citation without custody.** Verbatim quotations require an authorized corpus entry.
8. **No silent legal substitution.** Persuasive decisions cannot be labeled binding.
9. **Human adjudication remains mandatory.** The system proposes; the judge decides.
10. **Expansion is proven, not asserted.** Multi-TRT readiness requires a second-TRT
    implementation and regression evidence.
11. **Runtime neutrality.** Claude Code and Codex may have different orchestration syntax,
    but they must produce the same versioned artifacts and pass the same gates.

### 4.1 Reuse-first migration policy

This is a brownfield migration of the existing fork, not a greenfield rewrite. The current
repository is the implementation baseline. Existing components must be inventoried,
characterized, and assigned one of four explicit dispositions before implementation work may
replace them:

| Disposition | Meaning | Required evidence |
|---|---|---|
| Preserve | Behavior is court-agnostic and remains materially unchanged | Existing behavior passes characterization and regression tests |
| Adapt | The component has a reusable core but contains Federal Justice assumptions | Tests protect the reusable behavior and TRT12 fixtures prove the adaptation |
| Replace | The contract or legal behavior is incompatible with Labor Justice | Replacement passes equivalent or stronger gates before the old path is retired |
| Retire | The capability is outside the TRT12 first-instance scope | Dependency scan proves no accepted TRT12 path still requires it |

No component may be rewritten merely to make the architecture look cleaner. Replacement is
justified only by an incompatible legal rule, provider contract, data contract, security
requirement, or a demonstrated maintenance defect. The old implementation remains available
until the adapted or replacement path passes its acceptance gate.

### 4.2 Initial fork disposition map

The following map is the planning hypothesis. Roadmap item `FND-04` must confirm it against
the code and record the final file-level disposition.

| Existing fork capability | Initial disposition | TRT12 treatment |
|---|---|---|
| Blind orchestrator, file-as-state, one-line agent status, retry ceiling | Preserve | Keep the execution model and add regression coverage |
| Resumability and deterministic gate pattern | Preserve and harden | Reuse the pattern in `verificar_sentenca.py` and related gates; version artifact dependencies |
| Deterministic source and judgment merge | Preserve and adapt | Keep non-LLM merge and custody behavior; change labor artifact contracts |
| Citation custody and verbatim verification | Preserve and adapt | Keep the fail-closed mechanism; register TST and TRT12 source types |
| PDF conversion and OCR | Preserve and harden | Characterize digital and scanned fixtures; fix runtime/dependency portability where required |
| Procedural timeline | Adapt | Preserve chronological extraction; add Labor Justice events and terminology |
| Case reporter | Adapt | Preserve source-locator discipline; replace federal claim vocabulary with labor claim coverage |
| Documentary, testimonial, expert, digital, confession, and recognition analysis | Adapt after audit | Retain generic evidentiary reasoning only where fixtures prove no Federal Justice assumptions |
| Research consolidation and source review | Adapt | Preserve ranking/custody structure; implement Labor Justice authority hierarchy |
| Current PJe download workflow | Adapt behind an interface | Reuse session/download mechanics only after an authorized TRT12 HAR proves compatible behavior |
| Federal research agents and providers such as CJF, TNU, JULIA/TRF5, and Federal Justice-specific STJ routing | Retire from the TRT12 executable path | Keep outside the accepted labor pipeline; replace with TST/TRT12 adapters and applicable STF/BNP routes |
| TRF judgment-list agents and federal-only review rules | Retire from the TRT12 first-instance path | Do not delete until dependency scans confirm they are unreachable from the TRT12 profile |
| Federal merits analysis, calculation, remessa, fees, and drafting assumptions | Replace or deeply adapt | Implement labor claim analysis, labor calculation criteria, congruence, and judgment drafting |
| Tribunal profiles, labor claim matrix, issue router, TST/TRT12 research, and labor disposition matrix | Create | These are missing contracts required by the TRT12 target |

### 4.3 Migration sequence

1. Freeze a representative set of current fork fixtures and outputs.
2. Add characterization tests for the capabilities marked Preserve or Adapt.
3. Introduce stable core and provider interfaces around existing behavior.
4. Adapt one vertical slice for TRT12: acquire, convert, classify, report, analyze, draft, and gate.
5. Compare old and new outputs where their responsibilities overlap.
6. Retire an old path only after the TRT12 path is accepted and dependency checks pass.

This sequence avoids a big-bang rewrite and makes reuse measurable rather than aspirational.

---

## 5. Target Architecture

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                          RUNTIME ADAPTERS                                    │
│                  Claude Code                 Codex                           │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ shared execution manifest
┌──────────────────────────────────────────────────────────────────────────────┐
│                         DETERMINISTIC CORE                                   │
│ orchestration · resume · manifests · gates · merge · audit · redaction      │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ stable contracts
┌───────────────────────────────▼──────────────────────────────────────────────┐
│                        LABOR JUSTICE DOMAIN                                  │
│ claim matrix · evidence matrix · issue routing · labor reasoning · drafting │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ provider interfaces
             ┌──────────────────┼──────────────────┐
             │                  │                  │
┌────────────▼───────────┐ ┌────▼────────────┐ ┌──▼───────────────────────────┐
│ PJe-JT adapter         │ │ Research       │ │ Calculation/review adapters │
│ auth/index/download    │ │ TST/TRT12/BNP  │ │ PJe-Calc-aware criteria     │
└────────────┬───────────┘ └────┬────────────┘ └──┬───────────────────────────┘
             │                  │                  │
┌────────────▼──────────────────▼──────────────────▼───────────────────────────┐
│                           TRT PROFILE                                       │
│ TRT12 · first instance · URLs · source policy · signature · local rules     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Extension rule

An extension may supply configuration and adapter implementations, but it may not fork or
copy the core claim/evidence contracts. If a new TRT requires a new contract, the contract
must be generalized in the core and regression-tested against TRT12.

### 5.2 Dual-runtime contract

The canonical capability definition is runtime-neutral. Claude Code and Codex adapters may
translate tool names, task dispatch, progress reporting, and skill discovery, but they must
not duplicate or alter the legal prompt, artifact schema, tribunal profile, or gate logic.

| Concern | Shared contract | Claude Code adapter | Codex adapter |
|---|---|---|---|
| Project instructions | Legal and engineering policies | `CLAUDE.md` projection | `AGENTS.md` projection |
| Skills | Canonical skill instructions and resources | Claude-compatible skill location | `.agents/skills` projection |
| Orchestration | Versioned pipeline manifest and stage dependencies | Claude command/task dispatch | Codex task/tool dispatch |
| Progress | Artifact manifest and gate status | Runtime-facing progress view | Runtime-facing progress view |
| Tools | Capability names and input/output schemas | Claude tool bindings | Codex/MCP or local tool bindings |
| Validation | Shared scripts, fixtures, and acceptance gates | Runs the shared suite | Runs the shared suite |

The system does not require byte-identical prose from both models. Runtime conformance means
that both produce schema-valid artifacts, preserve the same source custody, respect the same
fail-closed conditions, and pass the same deterministic and human-review gates.

### 5.3 Provider interface contract

PJe acquisition and legal research use versioned, capability-based interfaces under
`runtime/providers/`. The shared core owns immutable requests, responses, pagination safety,
content-integrity checks, and official-source custody. Concrete adapters own endpoints,
authentication, provider payload translation, and tribunal-specific behavior.

Conformance is exercised against fake providers using a non-target tribunal code. This guards
the core/profile boundary, but it does not certify real PJe-JT or research-source access.

### 5.4 Authorized capture boundary

Raw HAR captures and extracted sessions are local operational inputs and may not become
repository artifacts. The evidence path produces a deterministic sanitized endpoint map that
retains methods, endpoint templates, header and cookie names, response status, content type,
capability classification, and failure states. It removes all header, cookie, and query values,
all request and response bodies, and recognized dynamic path identifiers.

Operator acknowledgement is mandatory before processing a capture, but it is not independent
proof of authorization. `PJE-01` still requires an authorized TRT12 capture and human review of
the resulting map.

The map-review gate verifies the sanitized digest, target tribunal and instance, endpoint and
coverage counts, failure-state consistency, redacted path templates, authentication artifacts,
and the minimum capability/failure coverage. Missing evidence is reported as incomplete;
structural or custody violations fail closed.

### 5.5 Session-state boundary

Credential acquisition and session-state classification are separate responsibilities. A
tribunal adapter may probe an already authorized session, but the shared classifier receives
only a sanitized HTTP status, recognized semantic markers, and cookie or header names. It
never receives or emits credential values, MFA material, request bodies, or response bodies.

The versioned contract recognizes `valid`, `expired`, `mfa_required`, `unauthorized`, and
`unknown`. HTTP denial has precedence over optimistic markers. Contradictory markers or an
authenticated marker without recognized session evidence fail closed as `unknown`. Synthetic
TRT99 tests prove this shared behavior; they do not prove real TRT12 authentication. A concrete
TRT12 probe remains dependent on the authorized and reviewed `PJE-01` map.

### 5.6 Task and case discovery boundary

The shared discovery runner requests only normalized, authorized task and case pages from a
concrete adapter. It owns bounded pagination, repeated-cursor detection, task and per-task case
deduplication, CNJ tribunal-region validation, deterministic ordering, and secret-free output.
An empty authorized queue is complete, not an error.

Task IDs, task names, endpoints, provider fields, and cursor encodings remain adapter-owned.
The original TRF5 listing scripts are reuse evidence, not TRT12 truth. Synthetic TRT99 tests
prove the portable contract while a concrete TRT12 adapter remains dependent on the reviewed
`PJE-01` map.

---

## 6. Tribunal Profile Contract

Canonical paths:

```text
runtime/profiles/
├── schema.json
├── registry.json
└── trt12.json
```

The schema is a standard, runtime-neutral JSON Schema. The registry maps judicial segments,
case-system adapter contracts, research sources, and official references without embedding
TRT12 values in the core schema. The profile carries the tribunal-specific values:

- Labor Justice segment, TRT12, region 12, Santa Catarina, and CNJ branch digit 5;
- first instance enabled with `labor_judgment` as its final artifact;
- second instance described for forward compatibility but explicitly disabled;
- PJe-JT as the case system, with only the first-instance adapter declared;
- TST, BNP, STF, and TRT12 official research sources;
- mandatory human review and verbatim custody; and
- external filing, signing, and publication disabled.

Registry entries with `contract_status: declared` define the adapter boundary expected by
later work packages. They do not assert that an adapter is implemented, authenticated, or
operationally verified.

Profile validation must reject:

- unknown CNJ branch digits;
- enabled instances without an adapter;
- empty signature sets;
- research sources without a registered adapter;
- any policy that permits filing, signing, or publication in the MVP.

---

## 7. Stable Data Contracts

The contracts below are implemented as versioned JSON Schema files under
`runtime/contracts/schemas/`. `runtime/contracts/catalog.json` selects the current version,
and `runtime/contracts/VERSIONING.md` defines the fail-closed migration policy. Agents may
consume only artifacts that pass the shared validator and the current contract version.

### 7.0 `document-classification.json`

Each downloaded document receives a stable labor-domain type or an explicit unknown/conflict
state. The deterministic baseline records only the rule evidence and never copies source text
into the classification artifact.

```json
{
  "schema_version": 1,
  "classifier_version": 1,
  "documents": [
    {
      "document_id": "DOC-001",
      "document_type": "initial_pleading",
      "classification_status": "classified",
      "matched_rule_ids": ["initial-pleading"],
      "reason_code": "matched_rule"
    }
  ]
}
```

The original fork's relevance classifier is reuse evidence for deterministic normalization and
explicit unknown handling. Its Federal Justice labels and priority assumptions are not carried
into the labor taxonomy without calibration evidence.

### 7.1 `labor-report.json`

The procedural report is a structured source-of-truth artifact. Narrative views may be
rendered from it, but may not replace its source links or review gaps.

```json
{
  "schema_version": 1,
  "case_context": {"case_number": "0000000-00.2026.5.12.0000"},
  "parties": [
    {
      "party_id": "PTY-001",
      "role": "claimant",
      "display_name": "...",
      "source_document_id": "DOC-001",
      "source_locator": "page 1"
    }
  ],
  "procedural_phase": {
    "phase": "knowledge",
    "status": "identified",
    "source_document_id": "DOC-001",
    "source_locator": "page 1"
  },
  "timeline": [],
  "positions": [],
  "review_gaps": []
}
```

Deterministic assembly rejects references outside the document manifest, preserves unknown
phase and missing positions as review gaps, and orders stable identifiers independently of
runtime or input order.

### 7.2 `case-context.json`

```json
{
  "schema_version": 1,
  "case_number": "0000000-00.2026.5.12.0000",
  "court": "TRT12",
  "instance": 1,
  "phase": "knowledge",
  "procedure": "ordinary",
  "court_unit": "Labor Court",
  "confidentiality": "public_or_authorized",
  "source_manifest": "document-index.json"
}
```

### 7.3 `claim-matrix.json`

Each pleaded claim receives a stable identifier.

```json
{
  "schema_version": 1,
  "taxonomy_version": 1,
  "claims": [
    {
      "claim_id": "CLM-001",
      "label": "overtime",
      "claimant_position": {
        "summary": "...",
        "source_document_id": "DOC-001",
        "source_locator": "pages 4-5"
      },
      "respondent_positions": [
        {
          "defense_id": "DEF-001",
          "respondent_party_id": "PTY-002",
          "summary": "...",
          "source_document_id": "DOC-002",
          "source_locator": "pages 2-3"
        }
      ],
      "requested_remedies": ["overtime_payment"],
      "contested_facts": [],
      "legal_issues": [],
      "status": "mapped",
      "review_gaps": []
    }
  ]
}
```

Claim and defense positions retain independent locators so multiple respondents are not
collapsed. Taxonomy mismatches and missing requested remedies or defenses require review and
may not be silently normalized.

### 7.4 `evidence-matrix.json`

```json
{
  "schema_version": 1,
  "evidence_items": [
    {
      "evidence_id": "EVD-001",
      "claim_ids": ["CLM-001"],
      "type": "time_record",
      "source_document_id": "DOC-014",
      "source_locator": "page_or_event_reference",
      "proposition": "...",
      "relation": "supports_claim",
      "limitations": [],
      "analysis_status": "pending",
      "conflicts_with_evidence_ids": []
    }
  ],
  "uncovered_claim_ids": []
}
```

Contradiction links are symmetric, self-links and missing targets fail closed, and any claim
without linked evidence remains explicit in `uncovered_claim_ids`.

### 7.5 `issue-route.json`

```json
{
  "schema_version": 1,
  "routes": [
    {
      "claim_id": "CLM-001",
      "route_status": "routed",
      "requires_legal_research": true,
      "requires_evidence_analysis": true,
      "requires_calculation_review": true,
      "requires_procedural_review": false,
      "research_questions": [],
      "evidence_questions": [],
      "route_reason": "...",
      "abstention_reasons": []
    }
  ]
}
```

Every known claim has exactly one route. A route with no enabled track is valid only as an
explicit `abstained` result with one or more reasons; routed claims may not carry abstention
reasons. Legal and evidentiary tracks require concrete questions for their downstream work.

### 7.6 `precedent-corpus.json`

```json
{
  "schema_version": 1,
  "sources": [
    {
      "source_id": "TST-001",
      "origin": "TST",
      "type": "qualified_precedent",
      "reference": "...",
      "status": "current",
      "binding_scope": "national_labor_justice",
      "legal_question": "...",
      "holding": "...",
      "verbatim_excerpt": "...",
      "official_url": "...",
      "retrieved_at": "ISO-8601"
    }
  ]
}
```

### 7.7 `claim-analysis.json`

```json
{
  "schema_version": 1,
  "analyses": [
    {
      "analysis_id": "ANL-001",
      "claim_id": "CLM-001",
      "facts_found": [],
      "evidence_ids": [],
      "evidence_assessment": [],
      "applicable_rules": [],
      "precedent_source_ids": [],
      "reasoning": "...",
      "proposed_outcome": "pending_human_review",
      "limitations": []
    }
  ]
}
```

### 7.8 `disposition-matrix.json`

```json
{
  "schema_version": 1,
  "items": [
    {
      "disposition_id": "DSP-001",
      "claim_id": "CLM-001",
      "outcome": "granted_in_part",
      "command": "...",
      "period": "...",
      "effects": [],
      "calculation_criteria": [],
      "source_analysis_id": "ANL-001"
    }
  ]
}
```

Every known claim has exactly one analysis and one disposition. Merits outcomes require facts,
evidence, evidence assessment, applicable rules, and reasoning. Procedural outcomes require
facts and rules, while unresolved outcomes require explicit limitations. The disposition
inherits the analyzed outcome and links through a stable `ANL-*` identifier.

---

## 8. First-Instance Pipeline

```text
0. Prepare and validate profile
   └─ case-context.json + workspace manifest

1. Acquire case
   ├─ session validation
   ├─ task/process discovery
   ├─ document index
   └─ authorized document download

2. Extract procedural record
   ├─ document classification
   ├─ procedural timeline
   └─ labor report

3. Build decision units
   ├─ claim matrix
   ├─ defense mapping
   ├─ requested-remedy mapping
   └─ evidence matrix

4. Route each claim
   ├─ legal research
   ├─ evidence analysis
   ├─ calculation review
   └─ procedural review

5. Execute conditional tracks
   ├─ TST/STF/BNP research
   ├─ TRT12 precedent and jurisprudence research
   ├─ specialized evidence review
   └─ calculation-criteria review

6. Analyze each claim
   └─ claim-analysis.json

7. Draft the judgment
   ├─ reasoning by claim
   ├─ disposition matrix
   └─ draft components

8. Merge deterministically
   └─ <CNJ_NUMBER>-labor-judgment.md

9. Review and gate
   ├─ claim coverage
   ├─ reasoning/disposition congruence
   ├─ quotation custody
   ├─ precedent status and hierarchy
   ├─ calculation-criteria consistency
   └─ final global gate
```

Every step must be resumable. Re-running a workspace may reuse only artifacts that pass the
current schema version, content gate, dependency freshness check, and source fingerprint.

---

## 9. Agent Plan

| Agent | Atomic capability | Source strategy | MVP action |
|---|---|---|---|
| `labor-document-classifier` | Classify one indexed document | New | Create |
| `labor-procedural-timeline` | Extract procedural events | Adapt existing timeline agent | Absorb |
| `labor-case-reporter` | Report claims, defenses, events, and pending issues | Adapt existing reporter | Absorb |
| `labor-claim-mapper` | Enumerate claims and requested remedies | New | Create |
| `labor-evidence-mapper` | Link evidence to contested propositions and claims | New | Create |
| `labor-issue-router` | Route each claim to required tracks | New | Create |
| `tst-precedent-researcher` | Research authoritative TST material | New | Create |
| `trt12-precedent-researcher` | Research TRT12 precedents and jurisprudence | New | Create |
| `labor-precedent-consolidator` | Rank and reconcile authorities | Adapt research consolidator | Absorb |
| `labor-claim-analyzer` | Analyze one claim from evidence and authorities | New | Create |
| `labor-judgment-drafter` | Draft reasoning and disposition from approved analyses | New | Create |
| `labor-congruence-reviewer` | Verify claim/reasoning/disposition coverage | New | Create |
| `labor-source-reviewer` | Verify status, hierarchy, wording, and relevance | Adapt source reviewer | Absorb |
| `labor-calculation-reviewer` | Review criteria, periods, and effects | Replace Federal calculation reviewer | Create |

Existing generic documentary, testimonial, expert, digital, confession, and recognition
analysis capabilities may be reused only after their examples and contracts are shown not to
inject Federal Justice assumptions.

---

## 10. Skill and Adapter Plan

| Component | Responsibility | Scope |
|---|---|---|
| `tribunal-profile` | Load and validate court profiles | Core |
| `pje-jt` | PJe-JT workflow and adapter contract | Labor Justice |
| `pje-jt-trt12-first-instance` | TRT12 observed endpoints and session behavior | TRT12 profile |
| `labor-claim-taxonomy` | Claim and remedy vocabulary | Labor Justice |
| `labor-precedent-hierarchy` | Binding scope, status, distinction, and overruling rules | Labor Justice |
| `labor-evidence-review` | Labor-specific evidence guidance | Labor Justice |
| `labor-calculation-criteria` | Criteria review without claiming independent liquidation | Labor Justice |
| `tst-jurisprudence` | TST official-source research adapter | National |
| `trt12-jurisprudence` | TRT12 official-source research adapter | TRT12 profile |

No adapter may log session cookies, MFA material, authorization headers, complete case text,
or unredacted personal identifiers in diagnostic output.

---

## 11. Research Authority Policy

The consolidator must preserve this hierarchy and explicitly record exceptions:

1. STF binding authority applicable to the issue;
2. TST qualified precedents and other nationally binding labor authority;
3. current TST summaries, orientations, and normative precedents according to their legal
   weight;
4. TRT12 IRDR, IAC, regional theses, and other binding regional authority;
5. TRT12 jurisprudence, with chamber or panel identified;
6. other TRT decisions, labeled persuasive only;
7. doctrine, if human-authorized for a specific workflow, never silently introduced into the
   automated judgment draft.

Research output must record:

- source and official URL;
- current status when the source exposes it;
- binding scope;
- legal question and holding;
- verbatim excerpt;
- retrieval timestamp;
- any suspension, overruling, cancellation, or unresolved conflict found.

---

## 12. Deterministic Gates

| Gate | Blocking conditions | Exit evidence |
|---|---|---|
| Profile | Invalid or incomplete tribunal configuration | Profile validation report |
| Input | Invalid TRT12 CNJ number, missing authorization, unreadable source | Input report |
| Document index | Missing IDs, duplicate identifiers, unexplained download gaps | Index report |
| Claim coverage | Pleaded claim absent from matrix | Claim reconciliation report |
| Defense coverage | Contested claim lacks defense mapping or explicit no-defense status | Defense reconciliation report |
| Evidence custody | Evidence proposition lacks source locator | Evidence report |
| Route | Claim lacks a valid route and rationale | Route report |
| Research | Cited authority absent from authorized corpus or status unresolved | Research report |
| Analysis | Claim lacks facts, rule, reasoning, outcome, or limitation field | Analysis report |
| Disposition congruence | Missing claim disposition or orphan disposition | Congruence report |
| Quotation | External quotation does not match authorized corpus | Citation report |
| Calculation criteria | Period/effect/criterion is inconsistent or unsupported | Calculation report |
| Final | Any blocking gate fails or an artifact is stale | Global report |

Critical gates do not degrade to warnings. A claim may end in an explicit abstention or request
for human resolution, but it may not silently disappear.

---

## 13. Security and Privacy

Before real case ingestion, the project must implement and verify:

- `.env`, session, HAR, cookie, authorization, and case-data ignore rules;
- sanitized HAR fixtures for tests;
- log redaction with tests for all credential fields;
- least-privilege tool access for every agent;
- no external write or filing tools in the MVP pipeline;
- a sealed-case policy approved by the responsible human;
- retention and deletion rules for local case workspaces;
- explicit confirmation that selected model and infrastructure use comply with the court's
  data-handling requirements.

---

## 14. Validation Strategy

### 14.1 Test layers

1. **Schema tests:** valid and invalid examples for every stable contract.
2. **Unit tests:** gates, normalization, merge, fingerprints, and redaction.
3. **Adapter contract tests:** recorded and sanitized PJe/research responses.
4. **Integration tests:** complete pipeline over synthetic and sanitized fixtures.
5. **Historical blind review:** completed TRT12 first-instance cases whose outcomes are hidden
   during generation and inspected only in evaluation.
6. **Regression suite:** all accepted defects become permanent fixtures.

### 14.2 Provisional acceptance targets

Targets are provisional until the first calibration sample establishes a baseline.

| Metric | MVP target | Guardrail |
|---|---:|---|
| Claim extraction recall | at least 95% | 100% for claims in the acceptance sample before pilot |
| Claim/disposition coverage | 100% | Any omission is critical |
| Verbatim quotation custody | 100% | Any unsupported quotation is critical |
| Orphan disposition rate | 0% | Any orphan is critical |
| Silent adapter failure rate | 0% | Explicit unavailability is acceptable |
| Authorized PJe rehearsal success | at least 95% | No credential leakage |
| Critical defects in final blind review | 0 | Blocks pilot readiness |

The historical sample protocol must define case selection, claim categories, procedures,
reviewer instructions, and defect severity before results are observed.

---

## 15. Target Repository Layout

```text
.
├── runtime/
│   ├── contracts/
│   │   ├── catalog.json
│   │   ├── VERSIONING.md
│   │   └── schemas/
│   │       └── *.v1.schema.json
│   ├── domain/
│   │   ├── labor-document-classification.json
│   │   └── README.md
│   ├── profiles/
│   │   ├── schema.json
│   │   ├── registry.json
│   │   └── trt12.json
│   └── providers/
│       ├── har-sanitization-contract.json
│       ├── har-map-review-contract.json
│       ├── interfaces.json
│       ├── pje-session-contract.json
│       ├── pje-task-discovery-contract.json
│       └── README.md
├── scaffold/
│   ├── commands/
│   │   ├── pipeline-labor-judgment.md
│   │   └── pipeline-labor-vote.md          # future, disabled
│   ├── agents/
│   │   ├── labor/
│   │   ├── research/
│   │   ├── drafting/
│   │   └── review/
│   ├── skills/
│   │   ├── tribunal-profile/
│   │   ├── pje-jt/
│   │   ├── labor-claim-taxonomy/
│   │   ├── labor-precedent-hierarchy/
│   │   └── labor-calculation-criteria/
│   └── adapters/
│       ├── pje-jt/
│       │   └── trt12-first-instance/
│       └── research/
│           ├── tst/
│           └── trt12/
├── scripts/
│   ├── validate_tribunal_profile.py
│   ├── build_claim_matrix.py
│   ├── build_claim_decisions.py
│   ├── build_evidence_matrix.py
│   ├── build_issue_routes.py
│   ├── build_labor_report.py
│   ├── classify_labor_documents.py
│   ├── provider_interfaces.py
│   ├── pje_session_adapter.py
│   ├── pje_task_discovery.py
│   ├── sanitize_pje_har.py
│   ├── validate_pje_har_map.py
│   ├── validate_claims.py
│   ├── validate_congruence.py
│   └── verify_labor_judgment.py
└── tests/
    ├── contracts/
    ├── gates/
    ├── adapters/
    ├── integration/
    └── fixtures/
        ├── synthetic/
        └── sanitized/
```

The exact physical layout may be adapted to existing project conventions during
implementation. The logical separation between core, labor domain, and court profile is
mandatory.

---

## 16. Second-Instance Extension Contract

The first-instance implementation must not implement second-instance behavior, but it must
avoid blocking it. The future second-instance pipeline will add:

- appeal admissibility;
- appealed-chapter matrix;
- scope of appellate review;
- reasons and counterarguments;
- maintain/reverse/annul disposition per chapter;
- regional panel and divergence metadata;
- prequestioning review where applicable;
- vote and judgment output contracts.

The second-instance pipeline will reuse case acquisition, document classification, evidence
custody, precedent custody, source review, and core execution mechanics.

---

## 17. Multi-TRT Extension Contract

A second TRT is considered supported only when it has:

- an approved profile;
- a verified first-instance PJe adapter or a proven shared adapter;
- a verified regional research adapter;
- a local precedent policy;
- sanitized fixtures;
- end-to-end regression results;
- an approved historical validation dossier.

The first additional TRT is the portability test. Until it passes, the project is
**TRT12-extensible**, not **multi-TRT compatible**.

---

## 18. Architectural Decisions

| ID | Decision | Rationale |
|---|---|---|
| ADR-001 | TRT12 first instance is the first executable target | Keeps validation bounded |
| ADR-002 | First and second instance use separate orchestrators | Their legal workflows differ materially |
| ADR-003 | Claim is the primary decision unit | Prevents omitted or conflated requests |
| ADR-004 | Court differences live in profiles and adapters | Preserves reusable domain agents |
| ADR-005 | PJe-Calc awareness does not equal independent liquidation | Avoids overstating calculation correctness |
| ADR-006 | Progress is earned only by accepted evidence | Prevents false completion metrics |
| ADR-007 | A second TRT is required to prove portability | Avoids speculative abstraction |
| ADR-008 | Provider contracts are capability-based and tribunal-neutral | Keeps endpoints and court-specific behavior outside the shared core |
| ADR-009 | Raw HAR and session files remain local; only reviewed sanitized maps are evidence candidates | Prevents credentials and case content from entering version control |
| ADR-010 | Session classification is separate from credential acquisition and fails closed on ambiguity | Keeps the shared core secret-free and prevents optimistic authentication decisions |
| ADR-011 | Task and case discovery uses normalized bounded pages and treats an empty queue as complete | Prevents silent pagination loss without embedding provider payloads or task names in the core |
| ADR-012 | Labor document classification is versioned, deterministic, and preserves unknown/conflict states | Makes triage auditable without presenting an uncalibrated guess as a fact |
| ADR-013 | The procedural labor report is structured, source-linked, and preserves review gaps | Prevents narrative summaries from becoming an untraceable source of truth |
| ADR-014 | Claim and defense positions remain independently source-linked and taxonomy mismatches stay explicit | Prevents multi-respondent defenses or novel claims from being silently collapsed |
| ADR-015 | Evidence is claim-linked, source-located, limitation-preserving, and contradiction-aware | Prevents unsupported propositions and conflicting evidence from disappearing in narrative synthesis |
| ADR-016 | Every claim receives one explainable work route or an explicit abstention | Prevents claims from disappearing between structured extraction and downstream legal analysis |
| ADR-017 | Claim analyses and dispositions form a one-to-one, stable-ID-linked decision chain | Prevents outcome drift between reasoning, operative language, and deterministic draft assembly |

---

## 19. Open Decisions Before Implementation

These do not block blueprint approval, but they block the indicated work packages:

1. authorized TRT12 PJe-JT access context and a sanitized HAR capture;
2. exact first-instance task names and document types used by the target unit;
3. approved handling policy for personal data and sealed cases;
4. minimum historical case sample and reviewer availability;
5. whether PJe-Calc interoperability is file-based, manual comparison, or deferred;
6. preferred judgment house style and whether an approved seed document exists.

---

## 20. Blueprint Acceptance Gate

This blueprint is accepted when the user confirms all of the following:

- TRT12 first instance is the first executable target;
- second instance remains a separate future pipeline;
- other TRTs are supported through profiles and adapters after portability proof;
- claim-level traceability is mandatory;
- progress is measured by the evidence-weighted roadmap;
- no filing, signing, or publication automation is included in the MVP.

On acceptance, roadmap item `ARC-01` earns its allocated points and the project moves to the
foundation and contract implementation work packages.

---

## 21. Official Domain References

- CNJ unique case numbering and Labor Justice branch digit:
  <https://www.cnj.jus.br/programas-e-acoes/numeracao-unica/perguntas-frequentes/>
- CNJ Banco Nacional de Precedentes:
  <https://www.cnj.jus.br/tecnologia-da-informacao-e-comunicacao/justica-4-0/banco-nacional-de-precedentes-bnp/>
- TRT12 service charter, including distinct first- and second-instance PJe access and
  jurisprudence coverage:
  <https://portal.trt12.jus.br/sites/default/files/2025-08/Carta%20de%20Servi%C3%A7os%20TRT12%20%281%29.pdf>
- TRT12 jurisprudence search:
  <https://portal.trt12.jus.br/consulta-jurisprudencia>
- TRT12 precedent and jurisprudence uniformization:
  <https://portal.trt12.jus.br/uniformizacao-jurisprudencia>
- TRT12 precedent information:
  <https://portal.trt12.jus.br/informativo-de-precedentes-2024>
- TST jurisprudence:
  <https://www.tst.jus.br/jurisprudencia>
- TST qualified precedent index:
  <https://www.tst.jus.br/indice-tematico-precedentes-qualificados-tst>
- STF jurisprudence:
  <https://portal.stf.jus.br/jurisprudencia/>
