# TRT12 Controlled Pilot Safety and Rollback Plan

**Status:** Approved; case execution remains `NO-GO` until the case-specific preflight passes
**Scope:** TRT12 first-instance, local and human-supervised pilot  
**External judicial actions:** Prohibited

## 1. Safety objective

The pilot may acquire authorized material, build traceable local artifacts, research official
sources, and generate an advisory draft. It may not file, sign, publish, move a PJe task, send a
message, modify a case, or make any other external judicial action.

The operator must be able to stop the run at every stage. A missing source, unavailable provider,
failed gate, stale checkpoint, integrity mismatch, or unresolved critical/high defect is a valid
terminal result and must never be converted into a pass.

## 2. Pilot eligibility

The first controlled pilot is limited to one authorized TRT12 first-instance case. Until data
handling is approved for more sensitive material, the initial case must not be sealed and must not
require exceptional access handling.

Before import, record outside Git:

- authorization scope and operator;
- case access classification;
- expected document set and local source location;
- case-specific retention deadline;
- intended outputs and review owner;
- explicit confirmation that no filing or PJe task movement is requested.

The pilot is ineligible if any of these fields is missing.

## 3. Roles and separation of duties

| Role | Responsibility | Proposed owner |
|---|---|---|
| Operator | Starts, observes, stops, and records the bounded local run | Repository owner |
| Legal reviewer | Reviews claim coverage, evidence, authorities, reasoning, calculations, and draft | Named qualified human reviewer |
| Incident owner | Coordinates containment, evidence preservation, correction, and closure | Repository owner |
| Data steward | Approves case classification, retention, and secure deletion | Repository owner |

One person may hold the operator, incident-owner, and data-steward roles for personal use. The
legal review remains a distinct human judgment step even when the repository owner is legally
qualified. No automated gate replaces that review.

## 4. Data handling and proposed retention

The following periods are conservative pilot defaults and require explicit approval before the
first real case:

| Data class | Location | Proposed retention | Disposal |
|---|---|---|---|
| Credentials, cookies, headers, MFA material | Memory or ignored local session storage only | End of authenticated session | Revoke session and securely remove local state |
| Raw authorized HAR capture | Outside repository | Delete immediately after the sanitized map is reviewed; maximum 24 hours | Secure local deletion |
| Sanitized endpoint map | Tracked only after human review | While its endpoint evidence remains current | Remove or replace when invalidated |
| Raw case documents | Ignored encrypted local storage | Case-specific deadline; proposed maximum 30 days after review closure | Secure local deletion and custody record |
| Derived case artifacts and draft | Ignored encrypted local storage | Case-specific deadline; proposed maximum 90 days after review closure | Secure local deletion and custody record |
| Secret-free rehearsal and incident summary | Protected local operations record | Proposed 180 days | Normal protected-record disposal |
| Synthetic fixtures and reports | Repository | Indefinite while contracts remain supported | Normal version-control lifecycle |

If a legal, institutional, preservation, or audit duty requires a different period, that duty wins
and must be recorded before processing. A longer period may not be selected merely for
convenience.

## 5. Mandatory preflight

The operator must complete the accepted operator runbook and record:

- exact commit on `development`;
- target-host readiness status and digest;
- passing quality gate;
- identical passing Claude Code and Codex synthetic digests;
- approved data classification and retention deadline;
- reviewed sanitized TRT12 endpoint map;
- local workspace outside tracked paths;
- named legal reviewer;
- confirmation that the global gate is enforced.

Any missing item is a no-go result.

## 6. Runtime controls

- Process one case at a time during the pilot.
- Use bounded page counts, response sizes, retries, and timeouts.
- Persist only versioned checkpoints bound to the current request, catalog, contracts, and hashes.
- Verify every downloaded payload against the indexed SHA-256 before use.
- Preserve unavailable, unknown, conflicting, and abstained states explicitly.
- Use official HTTPS legal sources and retain source locators and quotation custody.
- Never retry an expired, unauthorized, or MFA-required session as if it were valid.
- Never increase a persisted retry ceiling to force completion.
- Never continue after a non-passing global gate.
- Never place raw process text, credentials, or authenticated browser state in Git or CI.

## 7. Human review gate

The legal reviewer must check the complete artifact set before any draft is considered usable:

1. every pleaded claim and requested remedy is represented;
2. every material defense and absence of defense is explicit;
3. every material proposition has a correct source locator;
4. quotations and authorities are supported by official custody;
5. calculation criteria match the disposition;
6. analysis, outcome, disposition, and draft are congruent;
7. limitations, unavailable data, and abstentions are visible;
8. no critical or high defect remains;
9. the draft contains no instruction or mechanism for external judicial action.

Approval is case-specific. It does not certify future cases or legal adequacy in general.

## 8. Incident classification

| Severity | Examples | Immediate response |
|---|---|---|
| Critical | Credential or sealed-data exposure; unintended external action; fabricated authority; missing dispositive claim with material risk | Stop, isolate, revoke access, preserve secret-free evidence, notify incident owner and legal reviewer |
| High | Material claim, evidence, law, calculation, or disposition error likely to change the result | Stop, quarantine all outputs, invalidate downstream checkpoints, open corrective review |
| Medium | Incomplete or imprecise reasoning without independent dispositive effect | Block approval, correct, rerun affected stages and gates |
| Low | Localized style, clarity, or formatting defect | Record and correct before final review when practical |

Critical and high incidents have zero acceptance budget.

## 9. Containment and rollback

When a critical/high incident or integrity failure occurs:

1. stop the active process and do not retry external access;
2. disconnect or revoke the affected session and rotate any exposed credential through its owning
   system;
3. move the affected local workspace into a protected quarantine location without adding it to
   Git;
4. record commit, stage, checkpoint digest, provider status, affected artifact identifiers, and
   timestamps without copying sensitive content;
5. invalidate the affected stage and every dependent checkpoint;
6. restore code only from a known passing commit on `development`; never overwrite unrelated user
   changes;
7. correct the narrow owning defect and add regression evidence;
8. rerun quality, synthetic cross-runtime, and affected case gates from clean outputs;
9. require legal-review approval before release from quarantine;
10. close the incident only after containment, correction, verification, retention, and deletion
    actions are documented.

Rollback means returning to the last verified local state. It never means changing or attempting
to undo a PJe judicial action, because the pilot is not permitted to make one.

## 10. Recovery decision

Resume is allowed only when all conditions are true:

- the authorization and session are still valid;
- the request and catalog are unchanged;
- accepted payload bytes still match their stored hashes;
- the retry ceiling is not exhausted;
- the current contracts and gates accept the checkpoint;
- the incident owner has released the workspace;
- no critical/high defect remains.

Otherwise, abandon the checkpoint and begin a new authorized run from clean outputs. Preserve the
old workspace only for its approved incident-retention period.

## 11. Go/no-go and support ownership

The pilot may start only after the approval record below is complete. During personal use, support
is best-effort and owned by the repository owner; there is no production SLA. Any planned use by
another operator or court unit requires a new support, access, training, and incident-escalation
decision.

### Approval record

```text
Plan version/commit: 0.1 / approval recorded on development
Approved operator: Repository owner
Approved legal reviewer: Qualified human reviewer named for each pilot case before GO
Approved incident owner: Repository owner
Approved data steward: Repository owner
Approved raw-HAR retention: Delete after sanitized-map review; maximum 24 hours
Approved raw-document retention: Case-specific deadline; maximum 30 days after review closure
Approved derived-artifact retention: Case-specific deadline; maximum 90 days after review closure
Approved incident-summary retention: Maximum 180 days
Initial pilot case classification: Authorized, non-sealed TRT12 first-instance case
Approval date: 2026-09-21
Approver: Repository owner
Decision: NO-GO for case execution until the case-specific preflight is complete
Conditions or exceptions: No external judicial action; legal reviewer and case authorization are mandatory
```

This approval accepts the safety, ownership, retention, and rollback policy. It does not authorize
an unidentified case. Every real-case pilot remains `NO-GO` until its authorization,
classification, retention deadline, legal reviewer, and reviewed sanitized endpoint map are
recorded in the case-specific preflight.
