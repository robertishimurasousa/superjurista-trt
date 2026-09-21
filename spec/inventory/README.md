# Fork Reuse Inventory

The machine-readable reuse ledger is
[`superjurista-fork-reuse-ledger.json`](superjurista-fork-reuse-ledger.json).

It is generated from the current fork by:

```bash
python3 scripts/build_reuse_ledger.py \
  --root . \
  --output spec/inventory/superjurista-fork-reuse-ledger.json
```

## Baseline summary

| Disposition | Components |
|---|---:|
| Preserve | 1 |
| Adapt | 82 |
| Replace | 6 |
| Retire from the TRT12 executable path | 18 |
| **Total** | **107** |

Fifty components have an explicit Claude runtime dependency and 57 are currently
runtime-neutral according to the binding detector. `Retire` does not authorize deletion. A
component remains in the repository until dependency checks prove that no accepted TRT12 path
requires it.

Each ledger entry records its component kind, migration disposition, rationale, detected
runtime dependencies, and SHA-256 source fingerprint. Any new in-scope component must be
classified before the ledger can return to an accepted state.
