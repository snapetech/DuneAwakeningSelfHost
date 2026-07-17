# Prometheus On-Call Alert Inbox

DASH continuously imports the authoritative active-alert set from Prometheus
into a private SQLite inbox. The Operations page provides one durable queue for
current firing and pending alerts, re-fire generations, acknowledgement, and
recent transitions. The feature does not require Alertmanager and does not
modify Prometheus rules, game state, maps, players, or client files.

## What It Guarantees

- A successful `GET /api/v1/alerts` response is the only authority that may
  create, advance, or resolve source-alert state.
- A timeout, malformed response, oversized response, unsupported alert row, or
  storage failure resolves nothing. The last active set remains visible and the
  collector becomes unhealthy.
- Alert identity is a SHA-256 digest of sorted, bounded labels after
  credential-like keys are redacted. Repeated polls of the same state produce
  no new transition or delivery.
- A resolved fingerprint that fires again starts a new generation, increments
  its occurrence count, and clears the old acknowledgement.
- Acknowledgement records the authenticated operator, timestamp, and bounded
  note. It never silences Prometheus and never changes a source alert to
  resolved.
- Only `pending`, `firing`, `refiring`, `resolved`, and `acknowledged`
  transitions enter the audit ledger and outbound delivery path. Polling does
  not create notification storms.

The source contract is exposed as `dash-alert-inbox/v1` by the API.

## Configuration

The Compose defaults load the inbox and its acknowledgement surface:

```dotenv
DUNE_ALERT_INBOX_ENABLED=true
DUNE_ADMIN_ALERT_INBOX_MUTATIONS_ENABLED=true
DUNE_ALERT_INBOX_DATABASE=/workspace/backups/alert-inbox/inbox.sqlite3
DUNE_ALERT_INBOX_PROMETHEUS_URL=http://prometheus:9090
DUNE_ALERT_INBOX_POLL_SECONDS=30
DUNE_ALERT_INBOX_TIMEOUT_SECONDS=5
DUNE_ALERT_INBOX_RETENTION_DAYS=90
DUNE_ALERT_INBOX_HISTORY_LIMIT=2000
```

Bounds are enforced in code: polling is 10–3600 seconds, timeout is 1–30
seconds, retention is 1–3650 days, transition retention is 100–10,000 rows,
one response is at most 5 MiB and 5,000 alerts, and each alert has bounded label
and annotation counts and lengths.

`DUNE_ADMIN_MUTATIONS_ENABLED` remains the global admission gate for
acknowledgement. Operators need the normal `operations.write` capability.
Reading the inbox requires only authenticated `read` access.

## Operator Workflow

Open **Operations → On-Call Alert Inbox**. The collector verdict is separate
from the alert verdict:

- `clear` means the latest authoritative poll succeeded and no alert is active;
- `attention` means active alerts exist;
- `collector failed` means the displayed active set may be stale and must not be
  interpreted as resolved.

Use **Poll now** for an immediate read-only refresh. Use **Acknowledge** after
an operator has taken ownership. The optional note should contain a ticket or a
short response status, not credentials. A second acknowledgement of the same
generation is idempotent and preserves the original owner and note.

The private API equivalents are:

```bash
curl -fsS -H "X-Admin-Token: $DUNE_ADMIN_TOKEN" \
  'http://127.0.0.1:18080/api/ops/alerts?refresh=true&limit=200'

curl -fsS -X POST \
  -H "X-Admin-Token: $DUNE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"action":"acknowledge","fingerprint":"<64-hex>","note":"ticket 42","confirm":"ACKNOWLEDGE ALERT"}' \
  http://127.0.0.1:18080/api/ops/alerts
```

The POST enters the privileged-request flight recorder and the normal audit
ledger. It is an operations-state mutation only: the receipt records
`game_data_mutation_executed=false` and `map_lifecycle_invoked=false`.

## Signed Delivery

Alert transitions reuse the reviewed outbound-webhook destinations. Endpoint
filters may select all alert events or individual transitions:

```json
{
  "events": [
    "prometheus-alert-firing",
    "prometheus-alert-pending",
    "prometheus-alert-refiring",
    "prometheus-alert-resolved",
    "prometheus-alert-acknowledged"
  ]
}
```

Delivery retains the existing recursive redaction, bounded asynchronous queue,
retry limits, per-endpoint interval, redirect refusal, HTTPS policy, HMAC
signature, and secret-free delivery ledger described in
[`outbound-webhooks.md`](outbound-webhooks.md). If no destination is configured,
the local inbox remains fully functional and reports `inbox only`.

## Metrics And Meta-Alerts

The existing `/metrics/change-intelligence` scrape includes label-free:

- `dash_alert_inbox_enabled`
- `dash_alert_inbox_collector_up`
- `dash_alert_inbox_worker_running`
- `dash_alert_inbox_active`, `_firing`, and `_pending`
- `dash_alert_inbox_unacknowledged`, `_critical`, and `_warning`
- `dash_alert_inbox_consecutive_failures`
- `dash_alert_inbox_transitions_total`
- `dash_alert_inbox_last_success_timestamp_seconds`
- `dash_alert_inbox_age_seconds`

`DashAlertInboxCollectorInvalid` and `DashAlertInboxWorkerStopped` watch the
collection path. DASH deliberately does not create an alert from
`dash_alert_inbox_unacknowledged`: such a rule would ingest itself and could
self-latch after the original source alert resolved.

The feature-readiness catalog requires the worker, successful live probe,
Prometheus service, module, gates, and dependencies. The signed Operator
Briefing treats collector failure, critical active alerts, and unacknowledged
active alerts as a critical source verdict. Alert transitions invalidate the
prior briefing and wake its bounded refresh worker.

Alerts in the reserved `DashOperationsBriefing*` namespace remain fully
visible, durable, measurable, deliverable, and acknowledgeable in the inbox,
but are excluded from the alert-inbox verdict used to score the Operator
Briefing itself. This one-way boundary prevents the
`DashOperationsBriefingCriticalActions` meta-alert from feeding its own state
back into the next briefing and self-latching after the original condition
clears. The API reports the excluded active count as
`briefingSummary.feedbackExcluded`; the ordinary `summary` and all inbox
metrics continue to include those alerts.

## Backup And Recovery

`scripts/backup-state.sh` takes an online SQLite backup through SQLite's backup
API and stores it as `alert-inbox.sqlite3`. `scripts/verify-backup.sh` requires
an intact SQLite database with the `alerts`, `transitions`, and `metadata`
tables. The source database and backup artifact use mode `0600`.

If only the inbox database is lost, use the dedicated non-map restore path. It
verifies first, defaults to a dry-run plan, hostname-gates execution, stops and
recreates only `admin-panel`, preserves a private rollback copy, and
automatically restores that copy if health does not recover:

```bash
./scripts/restore-alert-inbox.sh .env backups/<verified-id>
./scripts/restore-alert-inbox.sh --execute .env backups/<verified-id>
```

The target defaults to `backups/alert-inbox/inbox.sqlite3`; override only with
the host-side `DUNE_ALERT_INBOX_HOST_DATABASE`. The first successful poll
reconciles current source state. Historical acknowledgement and transition
records newer than the backup cannot be reconstructed from Prometheus.

`restore-state.sh --alert-inbox` is reserved for a complete world recovery; it
also restores PostgreSQL and follows the full stopped-world workflow. Do not use
it for an isolated inbox repair.

If the database is corrupt and no verified copy is available, preserve it for
forensics, move it aside, and let DASH initialize a new database. Until the
first successful poll, collector readiness remains false. Never edit rows to
manufacture a resolution.

## Verification

Repository validation:

```bash
make test-alert-inbox
python3 scripts/test-admin-panel-safe-surfaces.py
make validate ENV_FILE=.env.example
```

Production verification is read-only:

1. Verify `hostname -s` is `kspls0` before deployment or any live admin write.
2. Read `/api/ops/alerts?refresh=true` and require `schemaVersion` to be
   `dash-alert-inbox/v1`, `ok=true`, no collector error, and a bounded poll age.
3. Confirm all `dash_alert_inbox_*` series are scraped.
4. Confirm both shipped meta-alert rules are loaded and healthy.
5. Confirm feature readiness reports `alert-inbox` as `ready`.
6. Confirm the next signed Operator Briefing contains 17 sources and a current
   alert-inbox verdict.

Do not create a fake production alert merely to exercise acknowledgement or
delivery. The unit suite proves state transitions against disposable SQLite;
live verification should preserve the real alert state.
