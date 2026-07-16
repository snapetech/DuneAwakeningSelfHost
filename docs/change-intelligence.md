# Operational Change Intelligence

DASH retains one private, HMAC-authenticated operational timeline and uses it
to answer a practical incident question: **what changed shortly before this
signal failed?** It correlates SLO incidents and desired-state drift with
preceding deployments, settings writes, service actions, restarts, restores,
and capacity decisions.

Correlation is not causation. DASH ranks investigation candidates from time,
declared impact, and shared scope. The dashboard and API explicitly preserve
that distinction and never label a candidate as a root cause.

The versioned policy is
[`config/change-intelligence.json`](../config/change-intelligence.json). The
Infrastructure page, authenticated API, CLI, Prometheus endpoint, backup
verifier, and restore preflight use the same private ledger.

## Why This Exists

Peers provide health, logs, action history, and alerts as separate surfaces.
DASH already had stronger individual evidence—time-weighted SLOs, signed
desired state, restore proof, capacity receipts, and a redacted admin audit
log—but an operator still had to align timestamps manually. Change
Intelligence connects those surfaces without inventing certainty.

For each incident capsule it preserves:

- the signed incident-open event and current open/resolved state;
- preceding change candidates inside the bounded policy window;
- candidate age, declared impact, shared scope, score, and human-readable
  ranking reasons;
- bounded follow-up evidence after the incident; and
- the explicit statement that no causal conclusion was generated.

Reopened desired-state findings begin a fresh capsule window. Prior resolved
history remains in the append-only event chain.

## Event Sources

Every new admin audit event is recorded directly after it is written to the
private JSONL audit log. This includes system-generated events and authenticated
operator actions such as:

- SLO incident open/resolution;
- desired-state drift open/resolution, seal, and acknowledgement;
- capacity recommendation application;
- service lifecycle actions and scheduled restart execution;
- settings, database, player, economy, world, and other guarded writes;
- update and runtime-repair workflows;
- backup/restore and isolated restore-drill events; and
- security denials and other retained audit events.

On activation and every later start, DASH scans at most the newest
`historyImportLimit` events from rotated and current admin audit JSONL files.
It bulk-checks keyed source fingerprints and inserts only missing rows, so the
normal catch-up is idempotent and cheap—including an event that may race first
startup. An audit event whose direct SQLite insertion failed transiently is
recovered on restart instead of being abandoned. The catch-up time is marked in
private SQLite metadata. Future events carry a random `audit-...` ID before
being written to both stores.

The original JSONL audit remains the webhook/digest compatibility surface.
Change Intelligence is the durable authenticated correlation surface.

## Classification And Ranking

Policy rules use bounded shell-style action patterns. The first matching rule
sets:

- `kind`: `change`, `incident-open`, `incident-resolved`, `evidence`, or
  `observation`;
- `category`: a bounded operator domain such as configuration, lifecycle,
  deployment, recovery, capacity, or reliability; and
- `impact`: `info`, `low`, `medium`, `high`, or `critical`.

An unknown authenticated `POST`, `PUT`, `PATCH`, or `DELETE` fails toward a
generic medium-impact administration change instead of disappearing. Unknown
read events become observations.

For each incident, candidates are restricted to `correlationWindowBeforeSeconds`
before its open time. The score combines:

1. declared impact weight;
2. linear recency within the window; and
3. bounded overlap between normalized scope values.

The score orders review; it has no probability interpretation. A highly ranked
change can be unrelated, and a true external cause can have no corresponding
change event. Operators must verify with the linked SLO, desired-state, logs,
backup, deployment, and runtime evidence.

Follow-up evidence ends at the incident resolution or
`correlationWindowAfterSeconds`, whichever occurs first. It is context for
response/recovery, not a success claim.

## Privacy And Bounds

The change ledger does not copy arbitrary audit payloads verbatim.

- keys containing password, secret, token, cookie, authorization, private-key,
  or credential markers become `<redacted>`;
- player, character, account, FLS, peer/client, target, and subject identifiers
  become keyed HMAC pseudonyms;
- absolute host/filesystem paths become keyed path HMACs, while API/metric/
  health routes remain readable;
- URL user/password components and bearer values in free text are removed;
- depth, dictionary keys, list entries, text length, serialized payload bytes,
  action/source syntax, incident-key syntax, query results, and UI rows are
  bounded; and
- Prometheus metrics contain no action, identity, path, scope, candidate,
  incident, note, or digest labels.

Named admin actors remain readable because accountability is an operator
requirement; local RBAC already constrains their syntax. Game/player identities
do not.

## Integrity Model

Each event contains a random ledger ID, source fingerprint, occurred/ingested
times, action, kind/category/impact, outcome, actor, source, incident key,
change flag, normalized scope/payload, and the prior signature. HMAC-SHA256
covers that complete document. Each signature becomes the next event's chain
link.

SQLite triggers reject every event update and deletion. Verification checks:

- SQLite `integrity_check`;
- both append-only triggers;
- every event HMAC; and
- every previous-signature link from genesis through the newest event.

The HMAC key must contain at least 64 encoded characters and must be mode
`0600` or stricter. `scripts/enable-feature-parity.sh` creates a random 32-byte
key as 64 hex characters when absent:

```text
config/secrets/change-intelligence-hmac.secret
```

The boundary detects database-only tampering, corruption, and mismatched
policy/key/ledger recovery. An actor able to read the key and replace both code
and database can forge evidence; retain off-host backups and signed release/Git
history as independent controls.

The ledger is intentionally append-only. `maxEvents` is a large hard bound,
not silent retention. On reaching it, ingestion fails visibly and requires a
reviewed archive/rotation design; DASH does not delete evidence behind the
operator's back.

## Dashboard And API

Open **Infrastructure → Change Intelligence**. The panel shows ledger
verification, retained event count, open incident count, incidents with
candidate changes, import errors, incident/candidate summaries, and recent
changes. Select an incident to load its complete bounded evidence capsule.

Authenticated read routes:

```text
GET /api/ops/change-intelligence
GET /api/ops/change-intelligence/capsule?incidentKey=slo:<id>
GET /api/ops/change-intelligence/capsule?incidentKey=desired:<id>
```

They require only normal authenticated `read` capability. There is no browser
write route: evidence is produced by existing guarded workflows and system
transitions, not manually fabricated through the UI.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DUNE_CHANGE_INTELLIGENCE_ENABLED` | `true` | Enables history import and direct future ingestion. |
| `DUNE_CHANGE_INTELLIGENCE_POLICY` | `/workspace/config/change-intelligence.json` | Classification, impact, correlation, and bounds. |
| `DUNE_CHANGE_INTELLIGENCE_DATABASE` | `/workspace/backups/change-intelligence/change-intelligence.sqlite3` | Private append-only ledger. |
| `DUNE_CHANGE_INTELLIGENCE_HMAC_SECRET_FILE` | `/workspace/config/secrets/change-intelligence-hmac.secret` | Private authentication key. |

Host CLI overrides are `DUNE_CHANGE_INTELLIGENCE_HOST_DATABASE`,
`DUNE_CHANGE_INTELLIGENCE_HOST_POLICY`, and
`DUNE_CHANGE_INTELLIGENCE_HOST_HMAC_SECRET_FILE`.

Policy bounds:

| Key | Default | Valid range |
| --- | ---: | ---: |
| `maxEvents` | 1,000,000 | 1,000–10,000,000 |
| `maxPayloadBytes` | 32,768 | 1,024–1,048,576 |
| `correlationWindowBeforeSeconds` | 3,600 | 60–86,400 |
| `correlationWindowAfterSeconds` | 1,800 | 60–86,400 |
| `statusEventLimit` | 200 | 10–1,000 |
| `candidateLimit` | 20 | 1–100 |
| `capsuleEvidenceLimit` | 200 | 10–1,000 |
| `historyImportLimit` | 10,000 | 0–100,000 |

## CLI, Metrics, And Alerts

```bash
make change-intelligence-status
make change-intelligence-verify
make change-intelligence-metrics

./scripts/change-intelligence.py capsule --incident-key 'slo:<id>'
```

The label-free private endpoint is:

```text
GET /metrics/change-intelligence
```

It exposes ledger verification, total events, open incidents, open incidents
with at least one candidate change, and last-event time. Prometheus alerts when
the target is unreachable, integrity verification fails, or an open incident
has preceding changes requiring review. The latter is an investigation alert,
not a root-cause verdict.

Ledger verification is also the ninth default operational SLO and is not
maintenance-excludable. Planned work cannot hide lost operational evidence.

## Backup And Recovery

Every full backup includes an online SQLite snapshot as
`change-intelligence.sqlite3` when the ledger exists. The matching `config.tgz`
contains the policy and HMAC key. Both the host shell verifier and the minimal
admin-image verifier extract those exact matching files into a private
temporary directory and recompute the entire event chain.

Restore preflight refuses a structurally valid database with the wrong key:

```bash
./scripts/restore-state.sh --dry-run --config --change-intelligence \
  .env backups/<UTC timestamp>

./scripts/restore-state.sh --config --change-intelligence \
  .env backups/<UTC timestamp>
```

Without `--config`, the backup must verify with the current policy/key before
only the ledger is restored. Executed restore removes stale WAL/SHM files and
writes mode `0600`. Stop the admin writer through the normal restore workflow.

Loss of the key cannot be repaired by generating a new one. Restore the policy,
key, and database from one verified backup set.

## Failure Handling

- **collector down:** check admin health, feature flag, policy path, database
  permissions, and key presence/mode.
- **import errors:** inspect `runtime.importErrors`; malformed legacy JSONL is
  skipped and counted, never converted into valid evidence.
- **integrity invalid:** preserve the current database, stop relying on its
  correlations, and compare with the newest matching verified backup.
- **no candidates:** investigate external/runtime causes and logs. The absence
  of a recorded change is not evidence that nothing changed outside DASH.
- **too many candidates:** narrow the policy window only after reviewing normal
  change frequency; do not tune scores to force a preferred explanation.
- **max events reached:** preserve and archive the complete ledger. Do not
  delete rows or remove append-only triggers.
- **wrong incident selected:** incident keys are bounded to `slo:`, `desired:`,
  or internal `event:` forms and SQL remains parameterized.

## Validation

```bash
make test-change-intelligence
make test-admin-panel-safe-surfaces
make test-operational-borrowing
make validate
```

Tests cover policy/key/file modes, credential/identity/path redaction, payload
bounds, classification fallbacks, temporal ranking, non-causal language,
resolution/reopen handling, idempotent history import, append-only enforcement,
HMAC tamper detection, metrics privacy, native/minimal backup verification,
restore preflight, API authentication, and dashboard wiring.
