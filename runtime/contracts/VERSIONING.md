# Artifact Contract Versioning and Migration Policy

## Version identity

- Every artifact carries an integer `schema_version`.
- Every catalog entry declares exactly one `current_version` and points to a versioned,
  immutable schema filename such as `claim-matrix.v1.schema.json`.
- Readers validate the artifact against the explicitly selected logical contract. They reject
  unknown contracts, unknown future versions, and versions that do not match the selected
  schema.
- The pipeline may reuse an artifact only when its version is current and its deterministic
  content and freshness gates also pass.

## Change policy

While a work item is `IN_REVIEW`, a contract may be corrected if its digest and acceptance
evidence are regenerated. After acceptance, an existing versioned schema is immutable.

Any accepted-schema change that alters required fields, allowed values, meaning, identifier
rules, or validation behavior requires all of the following:

1. add a new `vN` schema file instead of editing the accepted file;
2. add independent valid and invalid fixtures for the new version;
3. add a deterministic migration when an older artifact can be upgraded safely;
4. update the catalog only after the new schema and migration tests pass; and
5. document compatibility and custody implications in the roadmap evidence.

## Migration rules

- Migrations are explicit, one-version steps named `vN_to_vNplus1`; no implicit or multi-hop
  rewrite is allowed.
- A migration must be deterministic, offline, and free of provider or model calls.
- It writes a new artifact and never overwrites the source artifact.
- Stable claim, evidence, source, analysis, and disposition identifiers must be preserved.
- Source locators, verbatim excerpts, retrieval timestamps, and limitation records must not be
  discarded or weakened.
- The migration output records the logical contract, source and target versions, source digest,
  output digest, and migration implementation version.
- If safe conversion is impossible, the migration fails closed and requires regeneration from
  authorized source material plus human review.

## Required evidence

A migration is eligible for acceptance only when tests prove:

- valid old-version input produces valid new-version output;
- malformed or semantically unsupported input is rejected;
- repeated execution produces byte-equivalent canonical output;
- the source artifact remains unchanged; and
- custody-critical fields and stable identifiers are preserved.
