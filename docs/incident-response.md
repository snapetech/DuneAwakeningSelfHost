# Deterministic Incident Response Plans

DASH compiles every Change Intelligence capsule into a versioned response plan.
The plan converts retained incident evidence into an ordered operator workflow
without guessing a root cause, executing a shell, or bypassing an existing
mutation gate.

The authoritative policy is the `response` object in
[`config/change-intelligence.json`](../config/change-intelligence.json). Live
capsules, portable signed exports, the host CLI, the Infrastructure dashboard,
backup verification, and offline verification all use that same policy.

## Outcome

An incident capsule now answers four separate questions:

1. **Can this evidence be trusted?** The plan checks SQLite integrity, both
   append-only triggers, and the complete HMAC event chain.
2. **Is the incident still open?** It binds to the latest open/resolution pair
   for that incident generation.
3. **What evidence must be reviewed?** It counts and links the bounded preceding
   change candidates and follow-up evidence without calling either causation.
4. **Which existing DASH surfaces apply next?** It names exact bounded
   diagnostics, review surfaces, capabilities, feature gates, and confirmation
   phrases for the matched runbook.

The output is deterministic for one policy, incident generation, ledger head,
candidate set, and follow-up set. The plan carries SHA-256 digests for both its
policy and immutable inputs, then hashes its complete normalized output as
`planSha256`.

## Safety Contract

Response planning is read-only. A plan:

- never runs a diagnostic automatically;
- never executes a recovery action;
- never accepts command text, arguments, paths, environment overrides, stdin,
  pipes, redirects, or shell substitutions;
- never changes an incident's open/resolved state;
- never marks an operator-review step complete merely because it was displayed;
- never labels a ranked candidate as the cause;
- never weakens the capability required by the destination API;
- never substitutes for the destination feature gate or confirmation phrase;
  and
- never hides a blocked evidence-integrity step.

Diagnostic steps may reference only committed command-console IDs. The current
policy uses `stack-status`, `rmq-health`, and `storage-status`; each is an exact
native read-only handler from [`admin/command_console.py`](../admin/command_console.py).
The UI can preselect that ID in Command Console, but the operator must still
review and press **Run selected command**.

Recovery steps are navigation and contract metadata, not callable code. Each
step records:

- the existing DASH surface;
- the required RBAC capability;
- `mutation: true` and `execution: manual-gated`;
- the existing environment feature gate; and
- the existing exact confirmation phrase when that workflow has one.

The destination handler remains authoritative for hostname checks, master
mutation gates, input validation, backups, locks, confirmations, rollback,
post-start hooks, and auditing.

## Plan Structure

Every plan contains:

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Portable response-plan schema; currently `1`. |
| `runbookId` / `title` | First matching versioned policy runbook. |
| `incidentKey` | Validated `slo:`, `desired:`, or internal `event:` key. |
| `objectiveId` | Retained SLO objective ID, or `unknown` when the source event predates that field. |
| `incidentAction` | Retained incident-open action. |
| `policySha256` | SHA-256 of the normalized response policy. |
| `inputSha256` | SHA-256 of incident event IDs, candidate/follow-up IDs, ledger count, and ledger head. |
| `state` | `blocked`, `requires-operator-review`, or `verified`. |
| `summary` | Verified, pending, not-applicable, blocked, and mutation-step counts. |
| `steps` | Ordered immutable response steps and evaluated evidence. |
| `executesAutomatically` | Always `false`. |
| `causalityClaimed` | Always `false`. |
| `planSha256` | SHA-256 of every preceding normalized plan field. |

Each step includes its order, stable ID, kind, predicate, evaluated status,
title, description, evidence explanation, surface, capability, execution mode,
and optional command ID, feature gate, and confirmation.

## Step Statuses

Statuses describe machine-verifiable evidence only:

- `verified`: the predicate is proven by the same SQLite snapshot;
- `pending`: an incident remains open or an operator action/review is required;
- `not-applicable`: no candidate or follow-up event exists for that bounded
  review step; and
- `blocked`: the evidence ledger does not pass all required integrity checks.

The compiler currently supports five bounded predicates:

| Predicate | Evaluation |
| --- | --- |
| `ledger-verified` | SQLite is `ok`, both append-only triggers exist, and the HMAC chain verifies. |
| `incident-resolved` | The capsule contains a resolution after its latest open event. |
| `candidate-review` | Pending for one or more candidates; otherwise not applicable. |
| `followup-review` | Pending for one or more bounded follow-up events; otherwise not applicable. |
| `always-pending` | Requires explicit operator work and is never auto-completed. |

A displayed diagnostic result does not update the response plan. Re-export the
capsule after new retained evidence or authoritative resolution to obtain a new
input digest and plan digest.

## Runbook Coverage

Policy order is deterministic: the first matching runbook wins, and a validated
generic fallback must be last.

| Incident contract | Runbook | Reused bounded surfaces |
| --- | --- | --- |
| Database availability | `database-availability` | stack diagnosis, bounded logs, guarded stateful service control |
| Control-plane availability | `control-plane-availability` | stack and RMQ diagnosis, exact service recovery |
| Required-map availability | `required-map-availability` | map/farm readiness, logs, post-hook-aware map recovery |
| Backup RPO | `backup-rpo` | backup inventory, storage diagnosis, verified full backup |
| Restore proof | `restore-proof` | receipt review, storage diagnosis, isolated restore drill |
| Memory headroom | `memory-headroom` | stack/capacity evidence, gradual eligible recommendation apply |
| Admin authentication | `admin-authentication` | access posture, auth events, guarded settings repair |
| Desired-state attestation | `desired-state-attestation` | drift/provenance review, revert or complete-snapshot reseal |
| Change Intelligence integrity | `change-intelligence-integrity` | preserve ledger, matching-backup verification, guarded restore |
| Older/unknown SLO | `generic-slo` | stack diagnosis and objective-context review |
| Desired-state finding | `desired-state-drift` | exact finding/provenance review, revert or reviewed reseal |
| Other retained incident | `generic-incident` | evidence-contract review and bounded stack diagnosis |

Every default operational SLO has an exact runbook. Events imported from older
audit history without `objective_id` safely fall to `generic-slo` rather than
being assigned a guessed objective.

## Policy Validation

Startup refuses malformed response policy. Validation bounds:

- one schema-1 response object;
- 1–32 common steps;
- 1–64 runbooks;
- 1–32 steps per runbook;
- unique, syntax-bounded runbook and per-list step IDs;
- bounded title and description lengths;
- allowlisted kinds and predicates;
- syntax-bounded incident prefixes, objective/action glob patterns, surfaces,
  capabilities, environment gates, confirmations, and command IDs;
- command IDs only on non-mutating diagnostic steps;
- `mutation: true` only for recovery steps; and
- a final match-all fallback.

Tests additionally prove that every diagnostic command ID exists in the fixed
Command Console catalog and every default SLO objective resolves to its exact
runbook. All default recovery steps have a non-read capability and feature gate.

## Transaction And Integrity Model

Capsule selection, complete event-chain verification, ledger-head selection,
incident state, candidate ranking, follow-up selection, and response-plan
compilation occur inside one SQLite read transaction. WAL writers may continue,
but a concurrent append cannot appear in only part of the plan.

`verify_response_plan()` recomputes `planSha256`. Portable signed-capsule
verification requires both a valid plan digest and the outer capsule HMAC. A
changed step, status, gate, confirmation, input digest, policy digest, or nested
evidence value therefore fails offline verification.

The plan digest proves internal plan immutability. The outer HMAC proves the
plan was exported by the holder of the matching DASH key. The policy digest
identifies the exact normalized runbook policy; compare it with a reviewed Git
revision or the matching backup when provenance matters.

## Dashboard And API

Open **Infrastructure → Change Intelligence**, select an incident, and press
**Open evidence capsule**. DASH displays:

- runbook ID and title;
- plan state, policy-digest prefix, and plan-digest prefix;
- every ordered step, status, kind, surface, capability, gate, confirmation,
  and evaluated evidence statement;
- navigation buttons for each referenced surface; and
- the complete bounded capsule and immutable plan inputs.

A Command Console navigation stores only the fixed command ID in browser
session storage, opens Command Console, preselects the matching allowlisted
diagnostic, removes the pending selection, and asks the operator to review it.
It does not run the command.

### Response-readiness drills

Press **Run readiness drill** after reviewing the current plan and confirming
`RUN RESPONSE READINESS DRILL`. The request binds to the displayed
`planSha256`; if any incident evidence, prior drill receipt, or ledger head
changed, the server rejects the stale plan and requires a reload.

The drill refuses blocked evidence, runs each distinct fixed `commandId`
through the existing native Command Console runner, and evaluates every recovery
step against the authenticated principal's current capability, environment
feature gate, and committed confirmation contract. It executes no recovery and
no game mutation.

Diagnostic output is hashed and discarded. The retained receipt contains only
its byte count and SHA-256 plus success, return code, timeout, duration, and the
proof that shell, subprocess, and arguments were false. DASH appends that
bounded receipt as `incident-response-drill` evidence under the exact incident
key in the existing HMAC chain.

`ready=true` means every fixed diagnostic passed and every suggested recovery
contract was currently executable by that principal with its gate enabled. It
does not mean recovery ran, the incident is fixed, or a ranked candidate is a
cause. Drill events remain visible even after the normal resolved-incident
follow-up window. Their ledger IDs enter the next plan `inputSha256`, so each
rehearsal necessarily changes the plan digest and subsequent signed capsule.

Both existing capsule forms include `responsePlan`:

```text
GET /api/ops/change-intelligence/capsule?incidentKey=slo:<id>
GET /api/ops/change-intelligence/capsule?incidentKey=slo:<id>&signed=true
```

They require the normal `read` capability. Merely reading or signing a plan
does not require mutation authority because neither path executes a step.

The explicit rehearsal route is:

```text
POST /api/ops/change-intelligence/drill
{"incidentKey":"slo:<id>","planSha256":"<64 hex>","confirm":"RUN RESPONSE READINESS DRILL"}
```

It requires `operations.write`, `DUNE_RESPONSE_DRILLS_ENABLED=true`, and
`DUNE_COMMAND_CONSOLE_ENABLED=true`. It does not use the master game-mutation
gate because its only write is the private audit/HMAC evidence receipt.

### Fleet-wide readiness certification

An incident drill answers whether one selected plan is executable. **Certify
all runbooks** answers whether the complete current response policy is
executable by the authenticated operator now.

One explicit certification request:

1. binds to the displayed `response.policySha256` and rejects a stale policy;
2. deduplicates every diagnostic reference across all runbooks;
3. executes each distinct fixed native diagnostic exactly once;
4. hashes and discards diagnostic output using the same receipt contract as an
   incident drill;
5. evaluates every recovery step against the operator's current RBAC
   capability, configured feature gate, and committed confirmation phrase;
6. calculates ready/total coverage for runbooks, diagnostics, and recovery
   contracts; and
7. appends one `incident-readiness-certification` event to the existing HMAC
   ledger.

The default policy references nine diagnostic steps, but they collapse to only
`stack-status`, `rmq-health`, and `storage-status`. The certification therefore
runs three diagnostics, not nine. It evaluates all 12 runbooks and 10 recovery
contracts. Review-only runbooks with no recovery contract can be ready when
their diagnostics pass; this means the machine-executable prerequisites are
present, not that a human investigation has been completed.

The route is:

```text
POST /api/ops/change-intelligence/certify
{"policySha256":"<64 hex>","confirm":"CERTIFY INCIDENT RESPONSE READINESS"}
```

It requires `operations.write`, `DUNE_RESPONSE_DRILLS_ENABLED=true`, and
`DUNE_COMMAND_CONSOLE_ENABLED=true`. It never invokes a recovery endpoint,
executes a game mutation, starts or restarts a service, or changes a feature
gate. `recoveryExecuted` and `gameMutationExecuted` are always retained as
`false`.

The Infrastructure scorecard reports the latest policy-wide receipt, shared
diagnostics, each runbook's readiness, and exact capability/gate/confirmation
gaps. A certification is a snapshot: run it again after policy, RBAC, feature
gate, or runtime changes. Every incident capsule includes the latest global
certification, and its ledger event ID enters the next response-plan input
digest. Dashboard and metric readiness also require the receipt's retained
policy digest to match the currently loaded response policy; a previously
passing certification becomes policy-stale instead of remaining green.

## CLI

Print only the compiled plan:

```bash
./scripts/change-intelligence.py plan --incident-key 'slo:<id>'
make change-intelligence-plan INCIDENT_KEY='slo:<id>'
```

Print the complete live capsule and plan:

```bash
./scripts/change-intelligence.py capsule --incident-key 'slo:<id>'
```

Export and verify the plan inside a portable signed capsule:

```bash
./scripts/change-intelligence.py export-capsule \
  --incident-key 'slo:<id>' \
  --output backups/operator-evidence/incident.signed.json

./scripts/change-intelligence.py verify-capsule \
  --capsule-file backups/operator-evidence/incident.signed.json \
  --secret-file config/secrets/change-intelligence-hmac.secret

make change-intelligence-export-capsule \
  INCIDENT_KEY='slo:<id>' \
  CAPSULE_OUTPUT=backups/operator-evidence/incident.signed.json
make change-intelligence-verify-capsule \
  CAPSULE_FILE=backups/operator-evidence/incident.signed.json
```

The atomic export is mode `0600`. Offline verification reports
`signatureValid`, `responsePlanValid`, and `readinessReceiptsValid`. It
recomputes every nested drill and certification receipt digest rather than
trusting the verification flag embedded in the event. Verification does not
require the source SQLite database or policy file.

New plan-bearing signed capsules use outer schema 2. Authentic legacy schema-1
capsules remain valid and report `legacyWithoutResponsePlan=true` plus
`responsePlanValid=null`; schema 1 is never reinterpreted as carrying a plan.

## Backup And Recovery

Full host backups and browser/maintenance backups include up to 1,000 regular
`*.signed.json` files from `backups/operator-evidence` as
`operator-evidence.tgz`. Each source file is bounded to 10 MiB and the archive
is bounded to 100 MiB. Symlinks, nested arbitrary files, empty files, oversized
files, and non-signed suffixes are not archived.

Both backup verifiers require every archive member to be a regular confined
`operator-evidence/<safe-name>.signed.json` file. They verify every response-plan
digest, every nested readiness receipt digest, and the outer capsule HMAC
against the matching key from that backup's config archive. A structurally
valid capsule signed by the current key cannot make a backup with a different
key pass.

The evidence archive is portable, not live mutable state. Recovery is explicit:
verify the full backup, extract the archive to a private staging directory, and
retain or distribute only the required capsules. Do not overwrite the live
append-only SQLite ledger with a portable export.

Prometheus exposes latest drill readiness/time plus the latest fleet
certification readiness/time, runbook coverage, diagnostic totals, and recovery
contract totals without incident, operator, command, runbook, gate, or digest
labels. Alerts fire when the latest drill is not ready/stale, or when no current
passing policy-wide certification exists or it becomes older than seven days.

## Failure Handling

- **plan state is blocked:** preserve the ledger and use the
  `change-intelligence-integrity` runbook; do not act on ranked candidates.
- **generic runbook selected:** inspect `objectiveId`; older imported events may
  legitimately lack it. Do not rewrite history to force a match.
- **diagnostic unavailable:** use the named Command Console catalog/status to
  diagnose feature availability; never replace it with arbitrary shell input.
- **recovery gate disabled:** retain the plan and escalate to an identity with
  the required capability; enabling a gate is a separate reviewed change.
- **plan digest invalid:** reject the artifact even if its prose appears
  plausible.
- **outer HMAC invalid:** locate the matching key/backup or reject the artifact.
- **policy digest differs:** compare the exact reviewed policy revisions before
  merging or following two plans.
- **incident still open after recovery:** wait for or run the authoritative
  health observation path; never fabricate a resolution event.
- **drill not ready:** inspect diagnostic and recovery-contract booleans. Repair
  or enable a missing gate through a separate reviewed change; never bypass it.
- **certification not ready:** use the runbook scorecard to distinguish shared
  diagnostic failure from capability, gate, or confirmation gaps. A disabled
  recovery gate is reported as a gap; certification never enables it.
- **stale policy rejection:** reload Change Intelligence and review the new
  policy digest before certifying.
- **stale plan rejection:** reload the capsule. New evidence changed immutable
  plan inputs as designed.

## Validation

```bash
make test-change-intelligence
make test-command-console
make test-admin-panel-safe-surfaces
make test-operational-borrowing
make validate
```

Coverage includes every default SLO-to-runbook mapping, desired/generic
fallbacks, policy bounds, fixed diagnostic catalog membership, mutation-step
contracts, deduplicated policy-wide diagnostics, 12-runbook coverage receipts,
predicate statuses, policy/input/plan digests, nested readiness-receipt
tampering, outer HMAC tampering, concurrent append snapshot isolation, UI
navigation without execution, certification confirmation, CLI output, private
export modes, native/minimal backup verification, matching-key enforcement, and
tampered archived-capsule rejection.
