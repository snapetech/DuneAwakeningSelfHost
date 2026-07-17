# Infrastructure Console

The DASH Admin `Infrastructure` page provides service/log control, full backup
lifecycle operations, and database inspection/query/row/password workflows.
Read operations are always available; each mutation family is separately
gated, confirmed, backed up where state changes, audited, and verified.

## Access

Start the existing admin panel and open `Infrastructure`:

```bash
docker compose --env-file .env up -d admin-panel
```

```text
http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/infrastructure
```

The page uses the same host allowlist, optional `X-Admin-Token`, same-origin
checks, request-size limit, CSP, and audit behavior as the rest of DASH Admin.

## Feature Readiness

`GET /api/ops/feature-readiness` is the page's activation/runtime control
center. It evaluates every parity-activator gate with credential presence,
confined artifacts, current service state, dependencies, explicit runtime
probes, external blockers, and honest live-canary state. `?refresh=1` bypasses
the bounded cache. It is read-only and never returns credential values. See
[`feature-readiness.md`](feature-readiness.md) for the catalog, state machine,
tamper-evident deployment-correlated transition history, backup verification,
metrics, alerts, recovery workflow, and validation contract. The bounded
history feed is available at
`GET /api/ops/feature-readiness/history?limit=100`.

## Service Inventory

`GET /api/ops/services` reads the Docker Engine Unix socket and returns only
containers with this Compose project label:

```text
com.docker.compose.project=${DUNE_RESTART_COMPOSE_PROJECT:-dune_server}
```

Returned fields are service, container name/id, image, state, Docker status,
and published ports. `POST /api/ops/services/control` starts, stops, or restarts
one exact project service when `DUNE_ADMIN_SERVICE_CONTROL_ENABLED=true`.
Execution uses `scripts/restart-target.sh`, not a raw container call, so game
starts/restarts run the normal bridge, health, Coriolis, Landsraad, and runtime
post-start hooks. The admin panel cannot stop itself. Postgres and RabbitMQ
also require `DUNE_ADMIN_STATEFUL_SERVICE_CONTROL_ENABLED=true`. Every request
requires `CONTROL SERVICE` and the master mutation gate.

## Scoped Logs

`GET /api/ops/logs?service=director&tail=200` returns recent stdout/stderr for
one exact Compose service from the same project-label allowlist.

Safety and resource limits:

- service names must match `[A-Za-z0-9_.-]` and an observed project service;
- `tail` is clamped to `1..1000` lines;
- the Docker response is capped at 2 MiB;
- returned text is capped at 512 KiB;
- Docker multiplexed stdout/stderr frames and plain TTY streams are supported;
- no user-provided container id, Docker path, or label filter is accepted.

## Adaptive Map Pool

The Infrastructure autoscaler card supports minimum-footprint, balanced,
adaptive, full-warm, and custom profiles. It displays current map mode/state, players,
retention, warm deadline, last activity, demand count, and eviction reason.
Balanced mode caps empty optional-warm maps by least-recent activity and can
evict them when host `MemAvailable` falls below its configured floor. It never
selects always-on maps, maps with players, or maps with an active demand lease.
See [`autoscaling-memory.md`](autoscaling-memory.md) for the complete state and
configuration contract.

## Capacity Intelligence

`GET /api/ops/capacity` reports retained 1-day, 7-day, and 30-day map
efficiency. The card shows map-hours saved against a continuously running farm,
idle warm cost, productive-running ratio, observation coverage, warm/cold
revisits, revisit-gap quantiles, request-to-ready cold-start p50/p95, and the
next-visit forecast for each dynamic map.

`POST /api/ops/capacity` applies only evidence-qualified retention
recommendations. It requires `infrastructure.write`, the master mutation gate,
the autoscaler mutation gate, and `APPLY CAPACITY RECOMMENDATIONS`. Application
preserves map modes and LRU/memory-pressure budgets, moves each value by at most
the committed fractional bound, and writes a tamper-evident receipt. See
[`capacity-intelligence.md`](capacity-intelligence.md).

## Backup Lifecycle

`GET /api/ops/backups` inventories backup sets beneath `backups/` to a maximum
depth of four. It reports relative paths, timestamps, file counts, detected
manifests, and recent standalone admin backup artifacts. It does not return
backup contents.

`POST /api/ops/backups/verify` accepts:

```json
{"path":"20260715T120000Z"}
```

The path must resolve to a directory beneath `backups/`. Absolute paths and
path traversal are rejected. Verification invokes the existing read-only
`scripts/verify-backup.sh` helper, returns its exit code and bounded output,
and records a redacted audit event.

The same page exposes:

- `POST /api/ops/backups/create`: creates a full maintenance backup and refuses
  success unless `verify-backup.sh` passes;
- `GET /api/ops/backups/download`: creates a temporary `.tar.gz` with a
  content-disposition download and removes the temporary file after transfer;
- `POST /api/ops/backups/import`: accepts a SHA-256-checked base64 `.tar.gz` or
  `.tgz`, rejects traversal/links/devices, caps members and expanded bytes,
  stages extraction, requires a Postgres dump, and verifies before promotion;
- `POST /api/ops/backups/delete`: removes a set from the active inventory by
  moving it to `backups/admin-panel/deleted-backups/` for recovery;
- `POST /api/ops/backups/restore`: verifies first and supports dry-run plus
  independently selected Postgres/RabbitMQ/server-saved/config/TLS layers in
  both current and legacy backup layouts;
- `POST /api/ops/backups/schedule`: enables/disables verified automatic full
  backups with a local first-run time, 1..744 hour interval, and optional
  retention in days.

Schedule state lives at `backups/admin-panel/backup-schedule.json`. The worker
checks every 30 seconds and advances `nextRun` before work begins to prevent
duplicates. Retention `0` keeps all runs. Positive retention deletes only
paths recorded as scheduled runs and only beneath
`backups/admin-panel/maintenance/`; manual and imported sets are outside that
selection. Changes require the master gate,
`DUNE_ADMIN_BACKUP_MUTATIONS_ENABLED=true`, and `CHANGE BACKUP SCHEDULE`.

Create/import/delete require `DUNE_ADMIN_BACKUP_MUTATIONS_ENABLED=true`.
Restore execution additionally requires the master mutation gate,
`DUNE_ADMIN_BACKUP_RESTORE_ENABLED=true`, `RESTORE BACKUP`, and zero online
players. It stops running Compose writers, creates a verified full pre-restore
backup from the quiet state, restores Postgres directly with `pg_restore`,
replaces selected file layers, restarts the prior writer set, and invokes the
normal `scripts/restart-target.sh` post-start health/runtime-patch path. Failure
restarts writers and reports the recovery backup path.

The base admin container keeps `data/` read-only. Database-only restore and dry
runs work with the base file. For RabbitMQ or server-saved restore, recreate the
panel for the reviewed maintenance window with:

```bash
docker compose --env-file .env \
  -f compose.yaml -f compose.admin-restore.yaml \
  up -d --force-recreate admin-panel
```

Remove the overlay and recreate `admin-panel` afterward. The overlay changes
only `/workspace/data` to read-write. Config restore preserves the current
Postgres password because role passwords are not part of a database dump.

## Recovery Proof

The Recovery Proof card is stronger than `verify-backup.sh`. It reports whether
the newest PostgreSQL dump has actually restored inside a disposable,
no-network container and whether the measured backup age and `pg_restore`
duration meet policy.

`GET /api/ops/restore-drill` returns the latest private receipt, recent history,
hash-verification result, runtime state, RPO/RTO targets, resource bounds, and
the enforced isolation contract. It is read-only.

`POST /api/ops/restore-drill` queues a background run and immediately returns
`202 Accepted`. It requires the `infrastructure.write` capability, master
mutation gate, `DUNE_ADMIN_RESTORE_DRILL_EXECUTION_ENABLED=true`, and exact
`RUN ISOLATED RESTORE DRILL` confirmation. CLI, timer, and browser runs share a
nonblocking filesystem lock, so only one can exist at a time.

The source must be a regular `.dump` beneath `backups/`; traversal and symlinks
fail closed. Docker applies `network=none`, read-only root, UID/GID 70, all
capabilities dropped, `no-new-privileges`, no published ports, fixed
CPU/memory/PID bounds, and ephemeral tmpfs PGDATA. DASH copies the selected dump
to a temporary mode-`0400` file owned by the configured non-root container
identity, verifies its SHA-256, mounts only that copy read-only, verifies it
again inside the container, and deletes it during cleanup. Minimal private
passwd/group files name that numeric identity for PostgreSQL client tools and
are also read-only and ephemeral. The original dump's permissions never change.
DASH inspects the container settings and always removes the labeled container.

The receipt proves source archive listing, an error-stopping full restore,
required Dune tables and native base-backup function, valid indexes and
constraints, exact reads from core tables, analyze, and a second nonempty
custom-format dump that `pg_restore` can list. The live database is never
contacted. Complete configuration, receipt schema, systemd scheduling, and
failure recovery are in [`restore-drills.md`](restore-drills.md).

## RabbitMQ Recovery Proof

`GET /api/ops/rabbitmq-restore-drill` returns configuration readiness, bounded
runtime state, latest and recent private receipts, HMAC-anchored history
integrity, name-free topology counts, and the inspected no-network isolation
contract for copied admin/game broker state.

`POST /api/ops/rabbitmq-restore-drill` queues the two sequential disposable
broker boots and returns `202 Accepted`. It requires `infrastructure.write`, the
master mutation gate, `DUNE_ADMIN_RABBITMQ_RESTORE_DRILL_EXECUTION_ENABLED=true`,
and exact `RUN NETWORKLESS RABBITMQ RESTORE DRILL` confirmation. The Admin UI
does not mount or connect to either live broker; it supplies only the full
backup path and private staging paths to no-network containers.

The Infrastructure card shows per-broker readiness time, inspected isolation,
and counts of vhosts, users, queues, exchanges, bindings, and messages. It never
returns their names. Complete extraction bounds, isolation details, receipt
integrity, timer installation, configuration, and recovery are documented in
[`rabbitmq-restore-drills.md`](rabbitmq-restore-drills.md).

## Reliability Control Room

`GET /api/ops/slo` reports retained, time-weighted reliability rather than only
the current health response. Ten default objectives cover the Dune database,
control plane, currently required maps, backup RPO, verified PostgreSQL and
RabbitMQ recovery proofs, memory headroom, admin authentication, desired-state attestation, and operational
evidence integrity. Every objective includes 1h, 6h,
24h, 7d, and 30d availability, coverage, burn rate, and remaining budget.

The background worker records every 60 seconds by default. Gaps are capped so
a stopped collector cannot invent unlimited good or bad time. Missing signals
fail closed. Consecutive failures open one incident per objective; a good
sample resolves it. Acknowledgements and notes establish operator ownership but
cannot make a signal healthy.

`POST /api/ops/slo` supports `acknowledge`, `note`, `maintenance-create`, and
`maintenance-cancel`. It requires `infrastructure.write`, the master mutation
gate, `DUNE_ADMIN_OPERATIONAL_SLO_MUTATIONS_ENABLED=true`, and one of the exact
phrases `ACKNOWLEDGE SLO INCIDENT` or `CHANGE SLO MAINTENANCE`.

Planned maintenance lasts at most 24 hours, cannot overlap, cannot be created
retroactively after an incident, and excludes only opted-in objectives. Backup
RPO, both recovery proofs, and admin authentication continue measuring during
maintenance.

Incident events are protected from update/delete by SQLite triggers and linked
through a global SHA-256 chain. The dashboard, CLI, and backup verifier
recompute it. Prometheus scrapes `/metrics/slo` inside the private Compose
network and alerts on collector staleness, critical incidents, fast burn, and
exhausted 30-day budget. The endpoint contains no identities, notes, paths,
tokens, or player data. See [`operational-slo.md`](operational-slo.md).

## Desired-State Attestation

`GET /api/ops/desired-state` reports whether the approved repository/config
and Compose-container snapshot is still current. The Infrastructure page shows
the active baseline, last observation, critical/open/acknowledged drift,
integrity proof, policy, superseded baselines, resolved findings, and signed
events. File contents, environment values, and host mount sources are not
returned.

`POST /api/ops/desired-state` supports `seal` and `acknowledge`. Both require
`infrastructure.write`, the master mutation gate, and
`DUNE_ADMIN_DESIRED_STATE_MUTATIONS_ENABLED=true`. Sealing also requires a
reason and exact `SEAL DESIRED STATE`; acknowledgement requires exact
`ACKNOWLEDGE CONFIGURATION DRIFT`. Acknowledgement records ownership but cannot
resolve or suppress the finding. See
[`desired-state-attestation.md`](desired-state-attestation.md).

## Change Intelligence

`GET /api/ops/change-intelligence` returns the privacy-bounded append-only
operational timeline and incident summaries. The Infrastructure page aligns SLO
and desired-state incident onset with preceding classified changes. Candidate
ranking uses bounded recency, declared impact, and shared scope; it is displayed
as investigation evidence and never as a causal conclusion.

`GET /api/ops/change-intelligence/capsule?incidentKey=...` returns the incident
open/resolution events, ranked preceding candidates, and bounded follow-up
evidence. Both routes are authenticated reads. There is deliberately no manual
browser insertion route. See [`change-intelligence.md`](change-intelligence.md).
Add `&signed=true` to freeze the bounded capsule with the verified ledger count
and head signature under an outer HMAC. The Infrastructure panel can download
that portable artifact, and the host CLI verifies it offline without the source
database or policy. Exporting remains a read-only operation; no incident or
ledger row is created or changed.

Every capsule includes a deterministic response plan. The panel renders its
verified/pending/not-applicable/blocked steps and the exact existing diagnostic,
review, or guarded recovery surface. Navigation can preselect a fixed Command
Console diagnostic but never runs it; recovery suggestions retain their normal
capability, feature gate, and confirmation. See
[`incident-response.md`](incident-response.md).

The same panel can run an explicit fleet-wide readiness certification bound to
the displayed policy digest. DASH executes each distinct fixed read-only
diagnostic once, evaluates every runbook's current capability/gate/confirmation
contracts, and displays exact gaps. The certification writes only a bounded
HMAC evidence receipt; it executes no recovery or game mutation.

## Public-IP Repair Proof

The Infrastructure page includes an authenticated proof card for the complete
advertised-address repair lifecycle. It distinguishes monitor enablement,
dry-run/armed state, and cryptographically current lifecycle proof. Running the
proof requires `infrastructure.write`, the global mutation gate, and exact
confirmation, but writes only a private signed receipt: all environment, TLS,
restart, retry, and timer behavior executes against disposable state with fake
service control. See
[`public-ip-repair-canary.md`](public-ip-repair-canary.md).

## Assured Change Windows

`GET /api/ops/deployment-assurance` returns bounded open-window and signed
receipt summaries. The Infrastructure dashboard shows exact-commit promotion
outcomes plus source, protected-map continuity, desired-state, readiness,
SLO/Prometheus, and backup proof. It does not expose the HMAC key, full Docker
IDs, or a browser source-upload/deploy button.

The two-phase POST route requires `infrastructure.write` and exact start,
finish, or cancel confirmation. Source manifests and snapshots are not trusted
from the browser: the production host stages exact Git blobs, while the server
derives Docker/health results and verifies backup/source artifacts itself. See
[`deployment-assurance.md`](deployment-assurance.md).

## Database Browser and Query Console

`GET /api/ops/database` lists tables and views in the `dune` and `public`
schemas.

`GET /api/ops/database/table?schema=dune&table=world_partition&limit=50`
returns a bounded preview and column metadata.

The table preview:

- allows only the `dune` and `public` schemas;
- validates table identifiers and verifies the object through
  `information_schema.tables` before constructing a `SELECT`;
- executes only `SELECT * ... LIMIT %s` with a maximum of 200 rows;
- redacts non-empty password, token, secret, credential, service-auth, and
  private-key-like columns;
- performs no write by itself.

`GET /api/ops/database/search` searches schema/table/column metadata. The query
console uses `POST /api/ops/database/query`, permits exactly one statement,
applies 10-second statement and 2-second lock timeouts, caps results at 1000
rows, and redacts the same credential-like fields. PostgreSQL `SET TRANSACTION
READ ONLY` enforces read-only requests. Enable it with
`DUNE_ADMIN_DATABASE_QUERY_ENABLED=true`.

Write SQL additionally requires the master mutation gate,
`DUNE_ADMIN_DATABASE_WRITE_ENABLED=true`, `EXECUTE DATABASE WRITE`, and an
automatic DB backup. Audit records store only the SQL SHA-256, mode, and row
counts—not statement text.

The primary-key row editor uses `POST /api/ops/database/row`. It verifies the
exact primary-key shape and columns through the catalog, locks the current row,
captures before/after, verifies `RETURNING`, and rolls back on failure. It
requires `DUNE_ADMIN_DATABASE_ROW_MUTATIONS_ENABLED=true`, the master gate,
`UPDATE DATABASE ROW`, and a pre-write backup.

Password rotation requires a 16-character mixed-class password, zero online
players, `DUNE_ADMIN_DATABASE_PASSWORD_MUTATIONS_ENABLED=true`, the master
gate, and `ROTATE DATABASE PASSWORD`. It backs up first, changes the `dune`
role and `POSTGRES_DUNE_PASSWORD` together, verifies a fresh login, and restores
both old values through the still-authenticated recovery connection on any
failure. Recreate all database clients after success.

This is an administrative data view. Keep DASH Admin on a trusted LAN/VPN.

## Updates and Runtime Repair

`GET /api/ops/updates` reports the local Steam package/image-tag comparison,
current Git branch/commit/upstream/behind count, worktree cleanliness, and the
hotfix auto-update timer state. It also embeds the candidate-bound Update
Readiness evaluation and latest signed receipt. Read checks do not require the
mutation gate.

`GET /api/ops/update-readiness` exposes the same complete evaluation.
`POST /api/ops/update-readiness` recollects all server-side inputs and requires
`CERTIFY GAME UPDATE READINESS`. It writes a private HMAC receipt but executes
no update, restart, or game mutation. See [`update-readiness.md`](update-readiness.md).
The evaluation and dashboard show total evidence-collection and package-scan
latency. Prometheus warns above the documented 15-second/five-second budgets.

Steam package inspection is native Python over a read-only mount; it does not
depend on Bash, jq, Docker CLI, or a host-only path inside the minimal Admin
container. Explicit stage/apply actions use a bounded short-lived Docker CLI
helper after verifying Docker `/info` matches
`DUNE_UPDATE_READINESS_REQUIRED_HOST`.

`POST /api/ops/updates` supports:

- `game-check`: rerun `check-steam-update.sh`;
- `game-stage`: acquire/settle the local Steam candidate without loading
  images, writing the active tag, or touching containers/game state;
- `game-apply`: execute the existing full-farm stop, backup, staged-package
  validation, image ingest/tag update, start, readiness, and post-hook workflow.
  With the default policy, this first requires a current candidate-bound signed
  update readiness receipt and disables further Steam acquisition during apply;
- `stack-check`: fetch and fast-forward-check the configured Git upstream;
- `stack-apply`: require a clean tree, fetch, reject non-fast-forwards, write a
  pre-update Git bundle, validate the candidate in a temporary worktree, and
  only then fast-forward the active tree;
- `runtime-repair`: run `restart-post-start-health.sh` to restore bridge/RMQ,
  logoff timer, Coriolis, and other process-local post-start state;
- `auto-update-install`: install/enable the existing hotfix update timer.

Mutating actions require `DUNE_ADMIN_UPDATE_MUTATIONS_ENABLED=true`, the master
mutation gate, and `STAGE GAME UPDATE`, `APPLY GAME UPDATE`, `APPLY STACK UPDATE`, or
`REPAIR RUNTIME` as appropriate. `scripts/admin-stack-update.sh` never merges
or rebases divergent history and never applies an unvalidated candidate.

The base Compose file mounts admin code read-only. To authorize stack apply,
include the explicit overlay so the panel can see `.git` and fast-forward the
workspace:

```bash
docker compose --env-file .env -f compose.yaml -f compose.admin-stack-update.yaml up -d admin-panel
```

Keep this overlay limited to a private admin host. Game state under `data/`
remains read-only in the updater container.

## Docker Storage Cleanup

Inspect Docker use and safe candidates:

```bash
make storage-status ENV_FILE=.env
make storage-cleanup-dry-run ENV_FILE=.env
```

Equivalent direct command:

```bash
./scripts/storage-cleanup.sh --env-file .env cleanup --dry-run
```

Execution requires both an explicit mode and exact confirmation:

```bash
./scripts/storage-cleanup.sh --env-file .env cleanup \
  --execute --confirm 'REMOVE OBSOLETE DUNE IMAGES'
```

The script considers only known Funcom Dune self-host repositories. It
protects every image referenced by a running or stopped container, the current
`DUNE_IMAGE_TAG`, and the pinned Funcom Postgres image. It never removes
containers, volumes, databases, game files, configs, or backups.

Shared Docker build cache is untouched unless `--include-build-cache` is
added to an executing command. That optional flag runs:

```text
docker builder prune --force --filter until=168h
```

## Validation

```bash
python3 -m py_compile admin/admin_panel.py
python3 scripts/test-admin-panel-safe-surfaces.py
./scripts/test-storage-cleanup.sh
bash -n scripts/admin-stack-update.sh
docker compose --env-file .env.example config --quiet
```

The admin tests cover log-frame decoding, service allowlisting/control gates,
backup path containment/import traversal/verification, SQL classification and
write backup ordering, database schema/table allowlisting, row caps,
credential redaction, and UI/route registration. The storage test uses a fake
Docker command and proves that current, in-use, and unrelated images are not
removal candidates.
