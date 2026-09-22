# Legal Artifact Contracts

This directory contains the runtime-neutral JSON contracts shared by Claude Code and Codex.
The catalog maps each logical artifact name to its current immutable schema file.

The catalog currently includes case context, document classification, procedural timeline,
labor report, claim, evidence, route, precedent, analysis, and disposition artifacts. Domain
rules that produce these artifacts live outside the schemas, such as
`runtime/domain/labor-document-classification.json`.

## Validate the canonical fixture suite

```bash
python3 scripts/validate_artifact_contracts.py \
  --catalog runtime/contracts/catalog.json \
  --fixtures-root tests/fixtures/contracts
```

The suite requires one valid fixture and at least one rejected fixture for every cataloged
contract.

## Validate one generated artifact

```bash
python3 scripts/validate_artifact_contracts.py \
  --catalog runtime/contracts/catalog.json \
  --contract claim-matrix \
  --document /path/to/claim-matrix.json
```

Exit code `0` means valid, `1` means the artifact violates its selected schema, and `2` means
the catalog, schema, arguments, or input file cannot be evaluated.

See [`VERSIONING.md`](VERSIONING.md) before changing a schema or adding a migration.
