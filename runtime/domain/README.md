# Labor Domain Contracts

This directory contains runtime-neutral Labor Justice rules shared by Claude Code and Codex.
Rules in this directory are deterministic baselines, not claims of calibrated legal accuracy.

## Document classification

`labor-document-classification.json` defines the versioned document taxonomy and auditable
phrase rules used by `scripts/classify_labor_documents.py`. The classifier normalizes case,
accents, and punctuation, gives precedence to specific rules, and fails closed as `unknown`
or `conflict` when evidence is insufficient or contradictory.

The output contains stable document IDs and classification evidence only. Provider metadata,
document excerpts, party names, and case content are not copied into the result.

```bash
python3 -m unittest tests.test_labor_document_classifier -v
```

Synthetic tests establish deterministic behavior. DOM-01 remains incomplete until the
taxonomy is calibrated and reviewed against an approved, authorized TRT12 fixture set.

## Procedural timeline and labor report

`scripts/build_procedural_timeline.py` converts classified PJe PDF segments into the versioned
`procedural-timeline` artifact. It emits one dated and source-linked event for every segment,
distinguishes unknown classifications from classification conflicts, and writes protected case
artifacts only outside the repository.

`scripts/build_labor_report.py` converts already extracted, structured candidates into the
versioned `labor-report` artifact. Parties, procedural phase, timeline events, claims, and
defenses retain document IDs and source locators. Stable identifiers and manifest references
are validated, output order is deterministic, and missing information becomes an explicit
review gap rather than an inferred fact.

`scripts/extract_pje_labor_report.py` extracts case context, every party qualified in the
initial pleading, and the knowledge phase from a custodied PJe PDF. It reconciles the PJe
metadata's primary parties with the initial pleading, obtains the court unit from a classified
procedural document, consumes the complete timeline, and uses
`scripts/extract_labor_positions.py` to recognize explicit claim-section headings throughout
the classified initial pleading. Stable position IDs do not depend on page order, every match
retains its page locator, prose mentions are ignored, and unsupported categories remain
visible with `unmapped_` labels. `scripts/extract_labor_defenses.py` scans every classified
defense document under the same exact-heading rule, assigns a distinct stable ID range to each
document, and emits only the respondent positions actually found. The labor report does not
invent a response for a claimant position that has no matching defense section.

```bash
python3 -m unittest \
  tests.test_procedural_timeline_builder \
  tests.test_labor_report_builder \
  tests.test_labor_position_extraction \
  tests.test_labor_defense_extraction \
  tests.test_pje_labor_report_extraction \
  -v
```

The synthetic suite proves PDF custody, party reconciliation, timeline custody, protected
output, exact-heading claim and defense extraction, multiple-defense isolation, and
deterministic report assembly. DOM-02 still requires blind review against an approved,
authorized multi-case TRT12 fixture before acceptance. Claim-level missing-defense reporting
belongs to DOM-03 because labor-report v1 records only global position-kind gaps.

## Claim and requested-remedy taxonomy

`labor-claim-taxonomy.json` defines baseline claim labels and the requested remedies compatible
with each label. `scripts/build_claim_matrix.py` validates structured extraction candidates,
keeps claimant and respondent positions separately source-linked, supports multiple defenses,
and preserves unsupported labels or remedies as review gaps instead of remapping them silently.

`scripts/extract_pje_claim_matrix.py` connects a protected labor report and the original
PDF segment manifest to that builder. It verifies the original PDF digest, page count,
case number, and every position's document page range. A defense document must be bound
explicitly to one respondent party; an exact label match is required and ambiguous or
orphan defenses fail closed. Requested remedies, contested facts, and legal issues remain
empty until separately extracted and reviewed; the resulting gaps are explicit. The output
directory must already exist outside the repository, and the output file is created once
with mode `0600`.

```bash
python3 scripts/extract_pje_claim_matrix.py \
  --input /protected/process.pdf \
  --report /protected/report/labor-report.json \
  --segments /protected/segments/document-segments.json \
  --output /protected/matrix-v1 \
  --defense-party DOC-002=PTY-002
python3 -m unittest tests.test_claim_matrix_builder tests.test_pje_claim_matrix_extraction -v
```

DOM-03 remains incomplete until blind calibration demonstrates the roadmap recall and final
claim-coverage targets on an approved, authorized TRT12 fixture set.

## Evidence matrix assembly

`scripts/build_evidence_matrix.py` applies the source-custody rules used by the shared
`evidence-matrix` contract. Each proposition links to one or more claims and one document
locator, retains limitations, declares its relation to the claim, and records explicit
conflicts. Claims with no linked evidence are emitted under `uncovered_claim_ids`.

```bash
python3 -m unittest tests.test_evidence_matrix_builder -v
```

DOM-04 remains incomplete until every material proposition and contradiction passes blind
review against an approved, authorized TRT12 fixture set.

## Claim-level issue routing

`scripts/build_issue_routes.py` assembles one route for every known claim. Each route declares
whether legal research, evidence analysis, calculation review, or procedural review is needed
and preserves the explanation and track-specific questions. A claim with no enabled track must
record an explicit abstention reason; missing claims, duplicate routes, and contradictory route
states fail closed.

```bash
python3 -m unittest tests.test_issue_router -v
```

DOM-05 remains incomplete until route selection and abstention behavior pass blind review on an
approved, authorized TRT12 fixture set.

## Claim analysis, disposition, and draft assembly

`scripts/build_claim_decisions.py` keeps each claim as an independent decision unit. Analysis
IDs link facts, evidence IDs, rules, reasoning, outcome, and limitations to exactly one
disposition. The disposition inherits the analyzed outcome, and the deterministic renderer
keeps claim ordering and analysis links visible in the review draft.

```bash
python3 -m unittest tests.test_claim_decision_builder -v
```

DOM-06 remains incomplete until the analyses, commands, periods, effects, calculation criteria,
and rendered language pass blind legal review on an approved TRT12 fixture set.
