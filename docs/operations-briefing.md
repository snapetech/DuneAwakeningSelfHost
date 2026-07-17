# Signed Operator Briefing

The Operator Briefing turns DASH's existing operational evidence into one
prioritized answer to three questions:

- What is healthy now?
- What changed since the preceding briefing?
- What requires operator attention next, and where is its authoritative
  control surface?

The briefing is a synthesis layer. It does not replace the underlying evidence
stores, and its recommendations never execute automatically.

## What it reads

The worker collects categorical verdicts from 14 existing DASH authorities:

| Source | Severity when unhealthy | Authority |
| --- | --- | --- |
| Internal feature readiness | Critical | Gate, artifact, service, dependency, probe, and canary matrix |
| Optional external integrations | Informational | External-credential readiness state |
| Privileged mutation governance | Critical | Audit ledger and open-request reconciliation |
| Reliability objectives | Critical | SLO state, incidents, and evidence integrity |
| Desired-state attestation | Critical | Baseline state, open findings, and HMAC integrity |
| Change and incident intelligence | Critical | Incident ledger and response-readiness certification |
| Assured deployments | Warning | Latest promotion receipt and open/overdue windows |
| Latest assured recovery backup | Critical | Backup verdict inside the latest passing deployment receipt |
| PostgreSQL recovery | Warning | Latest disposable no-network restore receipt |
| RabbitMQ recovery | Warning | Latest dual-broker networkless recovery receipt |
| Capacity and scaling | Warning | Capacity ledger integrity and worker health |
| Credential lifecycle | Warning | Secret-safe contract and observation-ledger posture |
| Isolated proof freshness | Warning | Canary Autopilot target freshness and retry state |
| Game update readiness | Warning | Candidate evaluation and current certification receipt |

The collector catches each source independently. One broken subsystem becomes
one explicit `collector-error` action instead of suppressing the other 13
verdicts. Detail is whitespace-normalized, bounded to 500 characters, and does
not include credential values.

## Receipt and priority model

Every source has an ID, title, categorical state, healthy verdict, severity,
bounded detail, and linked Admin surface. The source fingerprint includes only
ID, state, verdict, and severity. Volatile timestamps, paths, counters in prose,
and receipt IDs therefore do not create meaningless churn.

The score is deterministic:

```text
score = max(0, 100 - 20 × critical - 7 × warning)
```

Informational provider follow-ups remain visible but do not reduce the local
server-health score. State is `critical` when any critical source is unhealthy,
`attention` when only warning sources are unhealthy, and `ready` otherwise.
Actions are sorted critical, warning, informational, then by stable source ID.

The next receipt compares source state, verdict, and severity with the previous
valid receipt. Deltas are classified as `regression`, `improvement`, or
`changed`, and the receipt stores the preceding receipt ID and SHA-256. Retained
history verification walks each adjacent link and independently re-derives its
delta list. The receipt includes a SHA-256 digest over all semantic fields and
is wrapped in HMAC-SHA256 using the existing Change Intelligence key.
Verification recomputes the source fingerprint, score, state, summary,
action/source mapping, receipt digest, signature, signing-key fingerprint,
timestamp, age, current source fingerprint, retained link, and delta semantics.

Receipt files are private (`0700` directory, `0600` files), written through an
fsynced atomic replacement, reject symlink evidence roots, and are retained in:

```text
backups/operator-evidence/operations-briefing-*.signed.json
```

## Freshness and worker behavior

The Admin Panel starts one daemon worker. It checks sources every five minutes
by default and generates a new receipt only when:

- no receipt exists;
- the categorical source fingerprint changed; or
- an unchanged receipt reached its scheduled 24-hour refresh.

A five-minute minimum interval suppresses repeated receipts during rapid source
flapping. A changed source makes the current receipt non-current immediately;
the API and metric expose that distinction while the bounded cooldown applies.
The maximum accepted receipt age defaults to 36 hours.

The Feature Readiness probe treats the worker's first collection as a bounded
`collector-starting` state. After the first receipt, readiness requires a
running worker, valid evidence, a current source fingerprint, acceptable age,
and no retained worker error.

## Dashboard and API

The Overview page places the briefing above the player map. It shows state,
score, source counts, critical/warning/informational totals, receipt age,
prioritized actions, changes, retained evidence metadata, and buttons to the
named Admin surfaces.

Authenticated API:

```http
GET /api/ops/operations-briefing?limit=20
```

This endpoint refreshes the in-memory source fingerprint and returns verified
receipts. There is deliberately no browser action that executes or automatically
chains a recommendation into a recovery mutation.

## Configuration

```env
DUNE_OPERATIONS_BRIEFING_ENABLED=true
DUNE_OPERATIONS_BRIEFING_POLL_SECONDS=300
DUNE_OPERATIONS_BRIEFING_REFRESH_HOURS=24
DUNE_OPERATIONS_BRIEFING_MAX_AGE_HOURS=36
DUNE_OPERATIONS_BRIEFING_MIN_INTERVAL_SECONDS=300
DUNE_OPERATIONS_BRIEFING_RETENTION=100
```

`scripts/enable-feature-parity.sh .env --execute` enables the feature and writes
the bounded defaults. The existing
`DUNE_CHANGE_INTELLIGENCE_HMAC_SECRET_FILE` signs receipts; no additional
credential is introduced.

## Metrics and alerts

The Change Intelligence metrics endpoint exports label-free gauges:

```text
dash_operations_briefing_enabled
dash_operations_briefing_collector_up
dash_operations_briefing_worker_running
dash_operations_briefing_current
dash_operations_briefing_score
dash_operations_briefing_critical
dash_operations_briefing_attention
dash_operations_briefing_actions
dash_operations_briefing_last_generation_timestamp_seconds
dash_operations_briefing_age_seconds
dash_operations_briefing_retained
```

Alert rules cover invalid evidence/source collection, a stopped worker, a
briefing that remains non-current for 30 minutes, and retained critical actions.
Source IDs, details, operators, paths, receipt IDs, and credential names remain
in the authenticated API rather than Prometheus labels.

## Backup, deployment, and recovery

Full backups already archive the mixed `operator-evidence.tgz` collection with
the matching Change Intelligence key in the config archive. Both the Admin
backup verifier and `scripts/verify-backup.sh` dispatch the briefing schema and
recompute its HMAC and semantic contract. Assured deployment manifests and the
control-plane push helper include `admin/operations_briefing.py` whenever the
Admin entrypoint is promoted.

If verification fails:

1. Do not edit or resign the failed receipt.
2. Preserve the receipt and matching Change Intelligence key for diagnosis.
3. Repair the named source subsystem if source collection failed.
4. Restore the newest backup whose mixed evidence archive verifies if the
   receipt itself was corrupted.
5. Let the worker observe the repaired categorical state and issue the next
   signed receipt.

Rotating the Change Intelligence key invalidates all evidence that uses it.
Rotate and archive the key and dependent evidence as one coordinated recovery
operation.

## Non-execution contract

Collection and receipt generation do not:

- invoke map lifecycle;
- write game or player data;
- execute a recovery recommendation;
- call an external provider;
- touch a client machine or local Steam directory.

The API returns these assertions as `executionContract`. The audit event emitted
for a new receipt records the same false mutation/lifecycle/provider/client
flags.

## Validation

```bash
make test-operations-briefing
make test-feature-readiness
make test-deployment-assurance
make validate
```

The focused suite covers deterministic scoring/priority, strict source
normalization, private atomic persistence, current-input detection, retained
deltas, signature/semantic tamper rejection, expiry, label-free metrics, API/UI,
readiness, Compose/env activation, alerts, backup dispatch, and assured
deployment support.
