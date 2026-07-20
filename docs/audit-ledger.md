# Mutation Flight Recorder

DASH independently seals the admin audit stream and refuses privileged HTTP
mutations when their intent cannot be durably recorded first. This closes the
gap between a rotated JSONL activity log and evidence that can detect payload
editing, row deletion, chain splicing, or tail truncation.

Confidence: **high** for repository behavior and tamper detection covered by
the unit/integration suite. Live operator events begin at the first Admin Panel
start with this feature loaded; older JSONL records remain legacy evidence and
are not retroactively claimed as authenticated.

## Defaults

```env
DUNE_ADMIN_AUDIT_LEDGER_ENABLED=true
DUNE_ADMIN_AUDIT_LEDGER_REQUIRED_FOR_MUTATIONS=true
```

The first setting dual-writes sanitized audit events to the existing
`backups/admin-panel/audit.jsonl` stream and to the private ledger. The second
requires a complete ledger verification and a sealed admission receipt before
an authenticated non-read POST can dispatch.

Turning the second setting off leaves event sealing enabled but changes
privileged-request admission to best effort. That mode is intended only for
recovery. The Security page reports it.

## Evidence model

The private store creates three artifacts under `backups/admin-panel/`:

| Artifact | Purpose | Mode |
| --- | --- | --- |
| `audit-ledger.sqlite3` | Ordered event payloads, indexed metadata, payload SHA-256, previous HMAC, and event HMAC | `0600` |
| `audit-ledger.hmac.key` | Random 256-bit HMAC key | `0600` |
| `audit-ledger.anchor.json` | Separately authenticated sequence and current chain head | `0600` |

The parent directory is forced to `0700`. `DUNE_HOST_UID` and
`DUNE_HOST_GID`, when set, are applied to all three artifacts.

Each ledger event binds:

- schema version and monotonic sequence;
- canonical event JSON SHA-256;
- the previous event HMAC;
- event identity, timestamp, action, outcome, and optional request identity.

SQLite `BEFORE UPDATE` and `BEFORE DELETE` triggers reject ordinary changes to
event rows. Verification also requires those triggers, so dropping them is an
integrity failure even before a payload changes.

The authenticated anchor binds the current sequence, chain-head HMAC, and
anchor update time. Verifying only a hash chain cannot detect deletion of its
last rows; comparing it with a separately authenticated head does. DASH checks
the complete chain before every fail-closed privileged admission and exposes
continuous verification through the dashboard and metrics.

An attacker who can roll back the database, key, and anchor to one internally
consistent historical snapshot can evade purely local detection. Preserve
successive full backups or external metric history when rollback detection
across whole-host compromise matters.

## Privileged request lifecycle

For every authenticated POST whose RBAC requirement is not `read`, DASH:

1. validates JSON framing and the route-specific body bound;
2. authenticates and authorizes the caller;
3. canonicalizes the parsed request and computes SHA-256 without storing the
   executable plaintext body in the flight-recorder fields;
4. verifies the complete HMAC chain and authenticated head;
5. appends `privileged-request-admitted` with a random request ID, principal,
   path, capability, body digest, and optional approval ID;
6. dispatches the existing route, feature gate, confirmation, backup, and
   transaction logic unchanged;
7. appends `privileged-request-completed` when the JSON response or error is
   constructed.

The response includes `X-DASH-Request-ID`. Admission and completion share that
identifier. An old admission without completion means the execution outcome is
unknown: the process may have stopped, the connection may have failed before
response construction, or evidence append may have failed. It does not prove
that the game/database mutation ran or did not run.

After investigating authoritative domain evidence, an infrastructure
administrator can close that ambiguity without editing history. The governed
reconciliation route appends `privileged-request-reconciled` against the
original request ID with one of `succeeded`, `failed`, `cancelled`, or
`no-effect`, a required reason, and optional bounded evidence. It rejects an
unknown or already terminal request. The reconciliation POST receives its own
normal admission/completion pair, so resolving one gap cannot create an
unrecorded governance mutation.

Community reward webhooks and the Discord service adapter keep their separate
signature/service-token boundaries and domain ledgers. Four-eyes approvals
remain cumulative: approval consumption does not replace flight-recorder
admission, and flight-recorder admission does not replace approval, feature,
confirmation, offline-player, backup, or transaction gates.

## Dashboard and API

Open **Security > Mutation Flight Recorder**. It shows:

- full-chain validity;
- sealed event count and current sequence/head;
- authenticated-anchor update time;
- admitted, completed, and open privileged-request counts;
- age of the oldest incomplete request;
- recent sealed events with ledger sequence/HMAC metadata;
- the current raw JSONL stream for migration/troubleshooting context.

The authenticated endpoint is:

```bash
curl -H "X-Admin-Token: $TOKEN" \
  -H 'Host: admin-panel:8080' \
  http://127.0.0.1:18080/api/ops/audit
```

The response contains `ledger`, `sealedEvents`, and legacy/current `events`.
Neither status nor metrics exports request bodies.

Open requests are returned as bounded metadata under
`ledger.requests.openRequests`. Reconcile only after checking the referenced
route's authoritative receipt, transaction, window, or domain state:

```bash
curl -H "X-Admin-Token: $TOKEN" -H 'Content-Type: application/json' \
  --data '{"requestId":"request-...","outcome":"cancelled","reason":"Investigated authoritative change-window state.","evidence":"deployment-window-... cancelled","confirm":"RECONCILE PRIVILEGED REQUEST"}' \
  http://127.0.0.1:18080/api/ops/audit/reconcile
```

This route requires `infrastructure.write` and is classified as a high-risk
governed change for change-contract and optional two-person approval policy.

## Metrics and alerts

`/metrics/change-intelligence` also exports label-free series:

```text
dash_admin_audit_ledger_enabled
dash_admin_audit_ledger_valid
dash_admin_audit_ledger_events
dash_admin_audit_ledger_head_sequence
dash_admin_audit_ledger_append_failures_total
dash_admin_audit_privileged_requests_admitted_total
dash_admin_audit_privileged_requests_completed_total
dash_admin_audit_privileged_requests_reconciled_total
dash_admin_audit_privileged_requests_open
dash_admin_audit_privileged_request_oldest_open_age_seconds
```

No series labels principals, paths, capabilities, request IDs, approval IDs,
body digests, event HMACs, or event values.

Prometheus rules include:

- `DashAdminAuditLedgerInvalid` after two minutes of failed ledger/head
  verification;
- `DashPrivilegedRequestOutcomeUnknown` when the oldest unmatched admission is
  older than five minutes for two minutes.

## Failure and recovery

When required mode is active, a chain, key, database, anchor, permission, or
append failure refuses the privileged request before route dispatch. Read-only
status remains available so an operator can diagnose the condition.

Full backups retry until all three artifacts form one verified chain/head set.
Recover them from the same verified backup; do not pair a database from one
backup with a key or anchor from another. During a full disaster restore,
include `--audit-ledger` in the existing `restore-state.sh` command. That script
always restores PostgreSQL; do not use it as a ledger-only shortcut:

```bash
./scripts/verify-backup.sh backups/<id>
./scripts/restore-state.sh --dry-run --audit-ledger <other-required-layer-flags> .env backups/<id>
```

After restore, recreate only the Admin Panel and confirm:

```bash
curl -fsS -H "X-Admin-Token: $TOKEN" \
  -H 'Host: admin-panel:8080' \
  http://127.0.0.1:18080/api/ops/audit | jq '.ledger'
```

If no matching evidence set exists, preserve the failed artifacts for
forensics, move all three aside together, and restart the Admin Panel to begin
a new chain. Record that evidence discontinuity externally. Never delete only
the database, key, or anchor to make a check green.

Repeated invalid-token polling is bounded before it reaches the ledger. DASH
still rejects every request and maintains the in-memory failure window, but it
emits at most one `auth-failed` and one `auth-throttled` event per peer per
minute. Successful authentication clears that peer's aggregation state. This
prevents a stale dashboard refresh loop from causing unbounded signed-ledger
growth.

## Validation

```bash
make test-audit-ledger
make test-admin-panel-safe-surfaces
docker compose --env-file .env.example config --quiet
make validate
```

The tests cover private permissions, canonical append/list/verification,
idempotency and collision refusal, concurrent serialization, enforced
append-only triggers, payload/HMAC/anchor modification, tail deletion,
missing-anchor refusal, consistent three-artifact snapshots, request
correlation, fail-closed admission ordering, response completion, UI/metrics/
alert contracts, and label-free exposition.
