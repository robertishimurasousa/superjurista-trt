# TRT12 First-Instance Operator Runbook

## Purpose and safety boundary

This runbook prepares and verifies the local SuperJurista TRT12 environment. It supports local
acquisition, analysis, and draft generation only. It does not file, sign, publish, move a PJe task,
or perform any other external judicial action.

Use only records that the operator is authorized to access. Raw HAR captures, session material,
cookies, headers, process files, generated workspaces, and sealed or personal case data must remain
outside Git and in the ignored local paths documented below.

Stop immediately if any command exposes a credential, writes case data into a tracked path, reports
an integrity mismatch, or produces a non-passing gate.

## 1. Start from a clean checkout

Use the approved `development` branch and confirm that no local change is present:

```bash
git switch development
git pull --ff-only origin development
git status --short --branch
```

Expected result: `development` is aligned with `origin/development`, with no modified or untracked
files.

## 2. Install host prerequisites on macOS

The shared environment requires Python 3.10 or newer. The core alone supports Python 3.9, but that
version cannot run the local MCP servers.

Install the external OCR tools once:

```bash
brew install tesseract tesseract-lang poppler
tesseract --version
tesseract --list-langs
pdftoppm -v
```

Expected result: Tesseract and Poppler report versions, and `tesseract --list-langs` contains `por`.

## 3. Create the isolated Python environment

Replace `/path/to/python3.12` with an installed Python 3.10+ executable. Do not use the macOS system
Python 3.9 for the combined runtime.

```bash
/path/to/python3.12 -m venv .venv
source .venv/bin/activate
python3 --version
python3 -m pip install -r requirements/runtime.txt
for requirements_file in scaffold/mcp-servers/*/requirements.txt; do
  python3 -m pip install -r "$requirements_file"
done
```

Expected result: the active interpreter is Python 3.10 or newer and every installation command
finishes successfully. `.venv/` is ignored by Git.

## 4. Prove target-host readiness

Run the version contracts followed by the executed MCP/OCR rehearsal:

```bash
python3 scripts/check_python_contract.py --root . \
  --contract runtime/python-contract.json --mode core
python3 scripts/check_python_contract.py --root . \
  --contract runtime/python-contract.json --mode mcp
python3 scripts/rehearse_target_host.py --root .
```

The final command must report `"status": "ready"`, five MCP servers, one OCR page, and an evidence
digest. Package presence alone is insufficient: the rehearsal imports all five servers and runs
the preserved PDF converter through Poppler and Portuguese Tesseract OCR.

## 5. Run repository quality and both synthetic runtimes

```bash
python3 scripts/quality_gate.py --root .
python3 -m unittest tests.test_cross_runtime_pipeline -v
```

Create two new empty workspaces and execute the same sanitized fixture:

```bash
CLAUDE_REHEARSAL=$(mktemp -d /tmp/superjurista-claude.XXXXXX)
CODEX_REHEARSAL=$(mktemp -d /tmp/superjurista-codex.XXXXXX)
python3 scripts/run_synthetic_pipeline.py \
  --runtime claude \
  --fixture tests/fixtures/pipeline/synthetic-first-instance.json \
  --workspace "$CLAUDE_REHEARSAL"
python3 scripts/run_synthetic_pipeline.py \
  --runtime codex \
  --fixture tests/fixtures/pipeline/synthetic-first-instance.json \
  --workspace "$CODEX_REHEARSAL"
```

Both summaries must report:

- `artifact_count` equal to 19;
- `global_gate_status` equal to `passed`;
- the same `contract_digest`;
- the same `shared_artifact_digest`.

The workspaces contain synthetic data only. A passing rehearsal proves runtime and contract
execution, not legal adequacy or live PJe access.

## 6. Prepare an authorized TRT12 capture

Do not place a raw HAR in the repository. Save it in an operator-controlled location outside the
checkout, then generate only the sanitized map:

```bash
python3 scripts/sanitize_pje_har.py \
  --input /path/outside-the-repository/authorized-capture.har \
  --output tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1 \
  --authorized-capture
python3 scripts/validate_pje_har_map.py \
  --map tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --tribunal-code TRT12 \
  --instance 1
```

Before committing a sanitized map, review every retained endpoint and marker. Exit code `0` means
the map has the required technical coverage; it does not prove authorization. Exit code `1` means
coverage remains incomplete. Exit code `2` means the map is invalid or inconsistent and must not
be used.

## 7. Handle real process material

Store authorized process material only under an ignored local path such as `processos/`, `cases/`,
`data/`, or `workspace/`. Never copy raw documents or authenticated browser state into `tests/`,
`runtime/`, or `spec/`.

Before the first real rehearsal, record:

- operator and authorization scope;
- whether the case is public, restricted, or sealed;
- retention and deletion requirements;
- the local input path and an output path outside Git;
- the process number only in the protected local record, never in a tracked fixture;
- the intended bounded operation and explicit stop condition.

The real PJe sequence remains disabled until the sanitized endpoint map has been reviewed. When it
is enabled, any expired session, MFA requirement, unauthorized response, repeated pagination
cursor, catalog drift, hash mismatch, or exhausted retry must stop the run without a filing or task
movement.

## 8. Validate the case-specific preflight

Create the protected preflight JSON outside the repository using
`runtime/operations/pilot-preflight.v1.schema.json`. Use digests instead of a process number or
authorization text. The contract records the named roles, exact `development` commit, host and
quality evidence, identical Claude/Codex rehearsal summaries, reviewed endpoint-map digest,
case classification, retention deadlines, allowed local operations, and permanent prohibition on
external judicial actions. Raw-HAR retention is measured from its capture timestamp, not from the
later preflight timestamp.

Create separate existing directories outside the checkout for authorized source material and new
outputs. The output directory must be empty. Then run:

```bash
python3 scripts/validate_pilot_preflight.py \
  --preflight /protected/path/pilot-preflight.json \
  --endpoint-map tests/fixtures/sanitized/trt12-first-instance-har-map.json \
  --workspace /protected/path/authorized-case-workspace \
  --output /protected/path/new-pilot-output \
  --summary /protected/path/pilot-preflight-summary.json
```

`[GO]` authorizes only the listed local, read-only controlled-pilot operations. The validator
returns `NO-GO` for a sealed or exceptional-access case, repository-local workspace, stale commit,
dirty working tree, non-passing host or quality evidence, divergent runtime summaries, incomplete or changed endpoint
map, excessive retention, non-empty output directory, or any contract drift. The secret-free
summary contains no process number, authorization scope, local path, credential, or case text.

## 9. Record the rehearsal

For each controlled run, retain a secret-free local record containing:

```text
Commit:
Operator:
Started at:
Completed at:
Host readiness digest:
Quality gate result:
Claude synthetic digest:
Codex synthetic digest:
Authorized capture review result:
Real-process scope, if applicable:
Final gate status:
Observed gaps or incidents:
```

Do not record cookies, tokens, header values, raw case text, party names, or protected document
content in this summary.

## 10. Stop and recovery rules

- Do not bypass a failed or blocked global gate.
- Do not increase a persisted retry ceiling to force success.
- Resume only from a checkpoint whose request, catalog, and accepted payload hashes still match.
- Keep a failed workspace intact until its secret-free diagnostics are recorded.
- A draft remains advisory and requires human legal review; it is never an instruction to sign or
  publish.
- If the official source rate-limits a request, wait for the published window instead of retrying
  repeatedly.
