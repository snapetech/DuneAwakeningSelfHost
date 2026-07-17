# Isolated Proof Autopilot

## Outcome

Canary Autopilot keeps DASH's existing signed, disposable lifecycle proofs
current without waiting for an operator to notice that a receipt expired or a
bound input changed. It manages three targets:

| Target | Authority | Refresh trigger |
| --- | --- | --- |
| Community Rewards | Policy-bound signed receipt from `admin/community_canary.py` | Missing/failed receipt, active-policy drift, expiry, or refresh lead reached |
| Creator/Modding | Input-manifest-bound signed receipt from `admin/creator_canary.py` | Missing/failed receipt, module/catalog/config drift, expiry, or refresh lead reached |
| Public-IP repair | Input-manifest-bound signed receipt from `admin/public_ip_canary.py` | Missing/failed receipt, repair-script/unit drift, expiry, or refresh lead reached |

The scheduler does not create a second definition of readiness. Each target's
signed receipt and strict verifier remain authoritative. Scheduler state holds
only attempt counts, retry deadlines, errors, and bounded history.

## Isolation Boundary

Automatic and manual runs use the exact existing canary implementations. They
do not:

- open or write the game database;
- read or mutate player data;
- invoke game-map lifecycle;
- call Discord, payment, vote, Tencent, or another external provider;
- edit the live public-IP environment, RabbitMQ TLS, or systemd units;
- touch a Steam/Dune client or desktop.

The public-IP proof retains its additional networkless, read-only,
capability-dropped helper-container confinement. The Community and
Creator/Modding proofs use private temporary state and remove it before signing
their verdicts.

## Scheduling Policy

The worker polls every five minutes by default. Polling is cheap: it verifies
the newest retained receipt and compares its policy/input digest and age. It
does not execute a canary every five minutes.

A target becomes due when its feature is enabled and the newest receipt is:

- absent;
- cryptographically or semantically invalid;
- a valid failed run;
- bound to an older policy or input manifest;
- expired; or
- within the configured refresh lead of expiry.

Only one batch can run at a time. A failed target retries after 15 minutes by
default; each consecutive failure doubles that delay up to 24 hours. A
successful run resets its failure streak. Other targets remain independently
schedulable. The manual force-all action bypasses a retry deadline for the
current request but does not disable future backoff.

Default configuration:

```env
DUNE_CANARY_AUTOPILOT_ENABLED=true
DUNE_CANARY_AUTOPILOT_POLL_SECONDS=300
DUNE_CANARY_AUTOPILOT_REFRESH_BEFORE_HOURS=24
DUNE_CANARY_AUTOPILOT_FAILURE_BACKOFF_SECONDS=900
DUNE_CANARY_AUTOPILOT_MAX_BACKOFF_SECONDS=86400
DUNE_CANARY_AUTOPILOT_RETENTION=200
DUNE_CANARY_AUTOPILOT_STATE_FILE=/workspace/backups/admin-panel/canary-autopilot.json
```

The default target receipts are valid for 168 hours, so a 24-hour lead normally
refreshes them after six days. If a target has a shorter maximum age, the
planner clamps the lead to that target's actual lifetime.

## Dashboard And API

Open **Infrastructure → Isolated Proof Autopilot**. The card shows:

- worker and collector health;
- current, due, runnable, and backoff counts;
- each proof's age, remaining lifetime, reason, retry time, counters, receipt,
  and last error;
- the newest 50 retained attempts; and
- the explicit no-live-state isolation contract.

Authenticated endpoints:

```text
GET  /api/ops/canary-autopilot
POST /api/ops/canary-autopilot
```

The POST requires `infrastructure.write`, the global mutation admission gate,
and this exact body confirmation:

```json
{"confirm":"RUN ALL ISOLATED CANARIES"}
```

The force-all action runs every enabled target even when its current receipt is
fresh. Each target attempt and the aggregate request enter the admin audit
ledger with explicit `game_data_mutation_executed=false`,
`map_lifecycle_invoked=false`, `external_provider_called=false`, and
`client_machine_touched=false` evidence.

## Readiness, Metrics, And Alerts

Feature Readiness contains the `canary-autopilot` row. It is ready only when
the gate is enabled, the worker is started, the scheduler/evidence collectors
are valid, at least one proof target is enabled, and no enabled target remains
due.

The private `/metrics/change-intelligence` scrape exports label-free metrics:

```text
dash_canary_autopilot_enabled
dash_canary_autopilot_collector_up
dash_canary_autopilot_worker_running
dash_canary_autopilot_targets
dash_canary_autopilot_current
dash_canary_autopilot_due
dash_canary_autopilot_backoff
dash_canary_autopilot_attempts_total
dash_canary_autopilot_failures_total
dash_canary_autopilot_last_attempt_timestamp_seconds
dash_canary_autopilot_last_success_timestamp_seconds
```

Prometheus alerts report invalid scheduler/target evidence after two minutes,
an enabled worker that did not start after five minutes, and any proof that
remains due for 30 minutes. Target names and failure text stay in the
authenticated API instead of becoming metric labels.

## Durability And Recovery

The scheduler state is atomically replaced, mode `0600`, inside a mode `0700`
directory. Symlink, non-regular, oversized, malformed, unknown-field, invalid
timestamp, invalid-counter, and malformed-history state fails closed. It is
included as `canary-autopilot.json` in a full backup and revalidated by
`scripts/verify-backup.sh`.

Signed proof receipts live separately in `operator-evidence.tgz` and remain the
recovery/readiness authority. Losing scheduler state therefore loses retry and
attempt history, not proof evidence. On a clean replacement, stop the Admin
Panel, preserve the invalid file for diagnosis, remove it, and start the panel;
the store creates a private fresh state and immediately derives due work from
the signed receipts.

Do not edit retry timestamps or mark a target current by hand. Fix the named
canary failure and use the automatic retry or the force-all action.

## Validation

```bash
make test-canary-autopilot
make test-community-rewards
make test-creator-canary
make test-public-ip-canary
make validate
```

The focused suite covers strict state validation, private atomic persistence,
symlink refusal, every scheduling reason, exponential backoff/reset, bounded
history, label-free metrics, API/RBAC, Compose, alert, readiness, and assured
deployment integration.
