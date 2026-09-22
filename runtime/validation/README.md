# Historical Validation Runtime

The validation runtime keeps the frozen protocol separate from reviewer results. Real case
identifiers, party names, credentials, and raw case text must never be stored in this directory
or in Git.

## Frozen inputs

- `historical-validation-protocol.v1.json` fixes the sample, partitions, categories, severity
  scale, metrics, and acceptance thresholds before results are observed.
- `historical-validation-protocol.v1.schema.json` validates the protocol structure.
- `../../spec/validation/historical-blind-review-form.md` is the human scoring form.

## Review batches

Create the real review batch outside the repository. It must satisfy
`historical-review-batch.v1.schema.json`, contain pseudonymous identifiers only, and bind to the
exact validated protocol digest. Every claim review records its owning defect stage, severity,
unavailable-data reason when applicable, and both blind-review attestations.

The batch also carries a pseudonymous case manifest whose expected claim inventory is frozen
before scoring. Each batch contains exactly one phase: first the 15 development cases, then—only
after correction—the separate five-case untouched holdout. The scorer requires exact review
coverage of every manifested claim. It rejects duplicate case/claim reviews, post-freeze
categories, inconsistent defect fields, mixed phases, reused blind output identifiers, multiple
blind outputs for one case, and missing independent reviewers.

```bash
python3 scripts/score_historical_reviews.py \
  --batch /protected/path/trt12-historical-review-batch.json \
  --output /protected/path/trt12-historical-review-report.json
```

The report is deterministic and validates against
`historical-review-report.v1.schema.json`. Development and untouched holdout metrics are emitted
by separate runs and must never be pooled. Unavailable values require a reason and are reported
as excluded rather than imputed as passes. Every report binds the evaluated Git revision and
contains a pseudonymous defect inventory by stage and severity. Any critical or high defect fails
its phase.

Run the network-free scoring tests with:

```bash
python3 -m unittest tests.test_historical_review_scoring -v
```

Passing synthetic tests prove the scoring contract only. `VAL-02` remains incomplete until the
authorized 15-case development sample is blindly reviewed by the assigned qualified human
reviewer; the remaining five cases belong exclusively to the later `VAL-03` holdout.

## Correction and untouched holdout

After the 15-case development review, record every correction outside the repository using
`historical-correction-register.v1.schema.json`. Each entry retains the pseudonymous defect ID,
stage, severity, code, correction commit, remediation summary, and passing regression evidence.
The five holdout cases must remain unscored until corrections are frozen in a new system
revision.

Validate the correction boundary and the separate passing holdout with:

```bash
python3 scripts/validate_historical_rerun.py \
  --development-report /protected/path/development-report.json \
  --correction-register /protected/path/correction-register.json \
  --holdout-report /protected/path/holdout-report.json \
  --output /protected/path/historical-rerun-report.json
```

The validator requires a correction for every development critical/high defect, preserves its
custody fields, rejects open or failing corrections, rechecks the scoring metrics against the
frozen thresholds, binds baseline and corrected revisions, and accepts only a distinct passing
five-case holdout.
