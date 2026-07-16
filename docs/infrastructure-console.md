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
full-warm, and custom profiles. It displays current map mode/state, players,
retention, warm deadline, last activity, demand count, and eviction reason.
Balanced mode caps empty optional-warm maps by least-recent activity and can
evict them when host `MemAvailable` falls below its configured floor. It never
selects always-on maps, maps with players, or maps with an active demand lease.
See [`autoscaling-memory.md`](autoscaling-memory.md) for the complete state and
configuration contract.

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
hotfix auto-update timer state. Read checks do not require the mutation gate.

`POST /api/ops/updates` supports:

- `game-check`: rerun `check-steam-update.sh`;
- `game-apply`: execute the existing full-farm stop, backup, Steam refresh,
  image ingest/tag update, start, readiness, and post-hook workflow;
- `stack-check`: fetch and fast-forward-check the configured Git upstream;
- `stack-apply`: require a clean tree, fetch, reject non-fast-forwards, write a
  pre-update Git bundle, validate the candidate in a temporary worktree, and
  only then fast-forward the active tree;
- `runtime-repair`: run `restart-post-start-health.sh` to restore bridge/RMQ,
  logoff timer, Coriolis, and other process-local post-start state;
- `auto-update-install`: install/enable the existing hotfix update timer.

Mutating actions require `DUNE_ADMIN_UPDATE_MUTATIONS_ENABLED=true`, the master
mutation gate, and `APPLY GAME UPDATE`, `APPLY STACK UPDATE`, or
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
