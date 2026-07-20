# Operational SLO And Error-Budget Control Room

DASH records reliability over time instead of treating one successful health
request as proof that the server is reliable. The Infrastructure page combines
time-weighted service-level objectives, observation coverage, error-budget burn,
incident transitions, planned-maintenance exclusions, Prometheus alerts, and an
immutable incident event ledger.

The subsystem is operational metadata. It never writes the Dune database,
starts or stops a game map, changes autoscaler state, or repairs a failed
service. Existing guarded recovery paths remain separate.

## Default Objectives

The versioned policy is [`config/operational-slo.json`](../config/operational-slo.json).

| Objective | Signal | Target | Incident debounce | Maintenance excluded |
|---|---|---:|---:|---|
| Game database availability | A bounded read-only query resolves the `dune` schema. | 99.9% | 2 failures | yes |
| Control-plane availability | Postgres, Director, Gateway, both RabbitMQ brokers, and TextRouter are running. | 99.5% | 2 failures | yes |
| Required-map availability | Every currently `always-on` map has a ready, alive, active registration. With autoscaling disabled, the complete farm is required. | 99.5% | 3 failures | yes |
| Backup recovery point | The newest confined PostgreSQL dump is no older than the configured RPO. | 99.0% | 2 failures | no |
| Verified restore proof | A recent receipt has a valid hash, passed integrity and policy, met RTO, and confirms no live DB access. | 99.0% | 2 failures | no |
| Verified RabbitMQ recovery proof | A recent authenticated receipt proves both copied brokers booted networkless with inspected isolation and no live-broker access. | 99.0% | 2 failures | no |
| Host memory headroom | `MemAvailable` remains above the configured floor. | 99.0% | 5 failures | yes |
| Admin authentication | Authentication is required and a real owner/RBAC credential source exists. | 99.9% | 1 failure | no |
| Desired-state attestation | An HMAC-sealed file/container baseline exists, has no open drift, and its complete ledger verifies. | 99.9% | 2 failures | yes |
| Operational evidence integrity | The append-only Change Intelligence SQLite, triggers, and complete HMAC event chain verify. | 99.9% | 2 failures | no |

Backup, database/RabbitMQ restore-proof, and authentication objectives deliberately continue through planned
maintenance: a maintenance window is not permission to lose recovery coverage
or expose the panel. Operators can edit the committed policy, but validation
rejects duplicate/invalid identifiers, invalid targets, unknown severities,
unbounded retention, and unsafe sample intervals.

Desired-state drift collection also continues during maintenance. Its SLO time
can be excluded and its alertable metric is suppressed, but findings remain
open and visible; maintenance never acknowledges or resolves evidence. See
[`desired-state-attestation.md`](desired-state-attestation.md).

Operational evidence integrity also continues through maintenance. A planned
window cannot convert a broken or unverifiable change timeline into good time.
Every SLO incident maps to an exact deterministic response runbook embedded in
its Change Intelligence capsule; the plan does not execute recovery or affect
the objective calculation. See [`change-intelligence.md`](change-intelligence.md)
and [`incident-response.md`](incident-response.md).

## Time Weighting And Error Budgets

The worker records one snapshot every 60 seconds by default. Every objective
sample carries the elapsed interval since its prior sample, capped at five
minutes. A stopped collector therefore does not invent hours of good or bad
service. Status is calculated for:

- 1 hour;
- 6 hours;
- 24 hours;
- 7 days;
- 30 days.

For each window DASH reports good, bad, excluded, and observed seconds,
availability, observation coverage, error-budget burn rate, and remaining
budget. For target availability `T`:

```text
availability = good seconds / observed seconds
burn rate = (bad seconds / observed seconds) / (1 - T)
remaining budget = max(0, 1 - burn rate)
```

Coverage is reported separately. A 100% result from five minutes of a 30-day
window is provisional evidence, not represented as complete history.

## Incident State Machine

Failures open an incident only after the objective's consecutive-failure
threshold. A good non-excluded sample automatically resolves the open incident.
Only one incident can be open for an objective at once.

Operators can acknowledge an open incident or add a note. Acknowledgement does
not make a failing objective healthy, consume or restore budget, or resolve the
incident. Resolution is driven only by a subsequent good observation.

Incident events are append-only:

```text
opened → acknowledged / note ... → resolved
```

SQLite triggers reject event updates and deletes. Every event includes the
prior global event hash and its own canonical SHA-256. Status, backup
verification, and `slo-verify` recompute the chain. Dropping a trigger or
editing the database does not make tampering invisible: the hash verification
fails closed.

## Planned Maintenance

An infrastructure administrator can create a future/current maintenance window
lasting at most 24 hours. Windows:

- require a reason, actor, exact confirmation, and a separate mutation gate;
- may begin no more than five minutes in the past;
- cannot overlap another active window;
- exclude only objectives whose policy opts in;
- retain the underlying signal and excluded duration;
- cannot be canceled after they have completed.

Maintenance never changes containers, map modes, backups, authentication, or
game state. It changes only SLO accounting. Schedule the window before planned
work; do not create retroactive exclusions after an outage.

## Dashboard And API

Infrastructure → Reliability Control Room displays:

- overall health and the newest sample;
- current objective state, target, 30-day availability/budget/coverage, and
  1-hour burn rate;
- open critical/warning incidents;
- incident acknowledgement and notes;
- planned-maintenance creation/cancel controls;
- ledger integrity and complete bounded incident/maintenance history;
- the exact evidence context from the latest live collection.

Read status:

```text
GET /api/ops/slo
```

Mutations use `POST /api/ops/slo` and require the master gate,
`DUNE_ADMIN_OPERATIONAL_SLO_MUTATIONS_ENABLED=true`, an identity with
`infrastructure.write`, same-origin JSON, and an exact phrase.

```json
{"action":"acknowledge","incidentId":"slo-required_map_availability-...","note":"Investigating map registration","confirm":"ACKNOWLEDGE SLO INCIDENT"}
```

```json
{"action":"note","incidentId":"slo-required_map_availability-...","note":"Recovery hook restored registration","confirm":"ACKNOWLEDGE SLO INCIDENT"}
```

```json
{"action":"maintenance-create","startsAt":"2026-07-17T05:30:00-06:00","endsAt":"2026-07-17T06:30:00-06:00","reason":"Planned game update","confirm":"CHANGE SLO MAINTENANCE"}
```

```json
{"action":"maintenance-cancel","id":"maintenance-...","confirm":"CHANGE SLO MAINTENANCE"}
```

## Prometheus And Alerts

Prometheus scrapes the bounded, label-safe endpoint inside the private Compose
network:

```text
GET /metrics/slo
```

It exposes no player, database, path, token, incident note, or maintenance
reason data. Metrics include collector freshness, current good/bad state,
open-incident counts, maintenance state, availability, observation coverage,
burn rate, and remaining budget.

`config/metrics/rules/dash.yml` adds:

- stale collector after three minutes;
- any critical open incident;
- 1-hour fast burn over 14.4x after meaningful coverage;
- exhausted 30-day budget after meaningful coverage.

Validate Prometheus configuration after policy or metric changes. A missing
time series cannot satisfy these alerts; the existing Prometheus target-down
view remains the outer scrape-health signal.

## CLI

```bash
make slo-status
make slo-verify
make slo-metrics
```

Equivalent commands:

```bash
./scripts/operational-slo.py status
./scripts/operational-slo.py verify
./scripts/operational-slo.py metrics
```

For controlled fixtures or an external reviewed collector, explicit signals
can be recorded from JSON. Missing policy signals fail closed:

```bash
./scripts/operational-slo.py record --signals signals.json --context context.json
```

The admin-panel worker is the production collector; do not run a second writer
at the normal cadence.

## Storage, Retention, And Backups

The ledger defaults to:

```text
backups/operational-slo/slo.sqlite3
```

The directory is mode `0700`; the database is mode `0600` and host-operator
owned. WAL mode, full synchronous commits, foreign keys, a busy timeout, and
`BEGIN IMMEDIATE` serialize writes. Objective samples are retained for 90 days
by default. Incidents, incident events, maintenance windows, and the event hash
chain are not deleted by sample retention.

Both CLI full backups and admin maintenance backups create a transactionally
consistent `operational-slo.sqlite3` snapshot and run SQLite integrity checks.
`verify-backup.sh` additionally recomputes its incident-event hash chain.
Restore is explicit because it replaces reliability evidence:

```bash
./scripts/restore-state.sh --operational-slo .env backups/<id>
```

The restore path stops the admin writer first, removes stale WAL/SHM files, and
installs the snapshot mode `0600`.

## Configuration

| Variable | Default | Meaning |
|---|---:|---|
| `DUNE_OPERATIONAL_SLO_ENABLED` | `true` | Start collection and expose retained status/metrics. |
| `DUNE_ADMIN_OPERATIONAL_SLO_MUTATIONS_ENABLED` | `false` | Permit acknowledgement, notes, and maintenance controls. |
| `DUNE_OPERATIONAL_SLO_POLICY` | `/workspace/config/operational-slo.json` | Versioned policy. |
| `DUNE_OPERATIONAL_SLO_DATABASE` | `/workspace/backups/operational-slo/slo.sqlite3` | Private ledger. |
| `DUNE_OPERATIONAL_SLO_POLL_SECONDS` | `60` | Observation cadence, bounded to 10–3600 seconds. |
| `DUNE_OPERATIONAL_SLO_STATUS_CACHE_SECONDS` | `30` | Single-flight reuse for the 30-day aggregate plus integrity view, bounded to 1–300 seconds. Each new SLO sample and every SLO mutation invalidates it. |
| `DUNE_OPERATIONAL_SLO_BACKUP_MAX_AGE_HOURS` | `36` | Backup RPO threshold. |
| `DUNE_OPERATIONAL_SLO_RESTORE_PROOF_MAX_AGE_HOURS` | `48` | Restore-proof freshness threshold. |
| `DUNE_OPERATIONAL_SLO_RABBITMQ_RESTORE_PROOF_MAX_AGE_HOURS` | `192` | Dual-broker networkless recovery-proof freshness threshold; eight days covers the weekly timer plus bounded scheduling delay. |
| `DUNE_OPERATIONAL_SLO_MEMORY_FLOOR_GIB` | `8` | Memory-headroom threshold. |

The policy carries sample retention, maximum unobserved gap, objective targets,
severity, debounce, and maintenance-exclusion behavior.

## Failure Handling

- `no-data`: the worker has not completed its first sample. Inspect panel logs
  and policy/database permissions.
- collector stale: verify the admin panel is healthy and that the SLO worker's
  last error is empty.
- missing signal: treated as failure; collector exceptions are recorded in the
  latest context instead of converted to success.
- invalid event chain: preserve the database and its backups; do not rewrite
  hashes. Compare the last verified backup and audit access to the ledger.
- low observation coverage: wait for retained history; do not claim the target
  from a short sample.
- exhausted budget: acknowledge the incident if someone owns it, add evidence
  notes, repair through the existing guarded runbooks, and let good samples
  resolve the incident naturally.
- planned work: create a bounded maintenance window before work. Backup and
  authentication remain measured throughout.

## Validation

```bash
make test-operational-slo
make validate
```

The focused suite covers policy rejection, private ownership/modes,
time-weighted windows, budget math, debounce, open/acknowledge/note/resolve,
database immutability triggers, global hash verification, maintenance
exclusions/overlap/bounds/cancel, missing signals, retention, Prometheus output,
consistent backup, corruption detection, API gating, route capabilities, public
metric bounds, and real-surface collector behavior.
