# Operations

This page covers state management for the Compose lab. Commands assume the default `.env` file; pass `--env-file` directly if you use a different environment.

Set `CONTAINER_RUNTIME=podman` when testing with Podman-compatible Compose commands:

```bash
CONTAINER_RUNTIME=podman ./scripts/status.sh .env
CONTAINER_RUNTIME=podman ./scripts/capture-routing.sh .env baseline-idle
CONTAINER_RUNTIME=podman ./scripts/backup-state.sh .env
CONTAINER_RUNTIME=podman ./scripts/restore-state.sh .env backups/20260519T150000Z
```

## Health Checks

Compose defines health checks for:

- `postgres`
- `admin-rmq`
- `game-rmq`

Check them with:

```bash
docker compose --env-file .env ps
```

The director, gateway, text-router, and game-server health checks are intentionally not guessed yet. Add those only after a stable local endpoint or command proves readiness accurately. A weak health check is worse than no health check because it can mark a broken routing state as healthy.

For a concise runtime verdict, use:

```bash
./scripts/status.sh .env
```

The `health verdict` section expects these signals at the same time: every partition has a ready/alive farm row, every active server id is present, and game RabbitMQ service-user connections exist.

For RabbitMQ-specific checks, use:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
```

Admin RabbitMQ can have fewer active service-user connections than farm partitions in the 30-map warm-pool layout. Treat it as unhealthy when recent auth/connectivity errors appear or when a failed client transition correlates with missing admin queue consumers.

For the expanded standing farm, the expected summary is:

```text
farm_ready_alive=9 active_servers=9 partitions=9
```

For the 30-partition warm pool, the expected summary is:

```text
farm_ready_alive=30 active_servers=30 partitions=30
```

## Survival Recovery

If Postgres or RabbitMQ restart while `survival` is running, restart the game-server process after dependencies are healthy. The observed live server build can crash fatally on a lost Postgres connection instead of reconnecting cleanly.

Use:

```bash
./scripts/recover-survival.sh .env
```

The helper starts Postgres and both RabbitMQ services, waits for their health checks, starts the service layer, force-recreates only `survival`, waits for registration, and then prints `./scripts/status.sh`.

## Expanded Farm Startup

Start the full standing farm after the core service layer is healthy:

```bash
./scripts/full-world-partitions.sh .env

docker compose --env-file .env up -d \
  survival overmap arrakeen harko-village \
  testing-hephaestus testing-carthag testing-waterfat \
  deep-desert proces-verbal

./scripts/status.sh .env
```

The full-farm partition layout is intentionally smaller than `initialize_partitions_full_battlegroup()`. Funcom's helper creates many extra `Survival_1` and other map dimensions. The Compose layout starts exactly one container for each current travel target, so the local partition script creates exactly those rows.

Capture the known-good state after all nine maps register:

```bash
./scripts/backup-state.sh .env
./scripts/capture-routing.sh .env full-farm-ready
```

For the 30-partition warm pool:

```bash
./scripts/full-world-partitions.sh .env
docker compose -f compose.yaml -f compose.allmaps.yaml --env-file .env up -d
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/status.sh .env
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
```

## Network Ports

For a single `Survival_1` layout, forward:

```text
7777/udp
```

For the expanded standing farm, forward:

```text
7777-7785/udp
```

For the 30-partition warm pool, forward:

```text
7777-7806/udp
```

The Compose files also expose `7888-7917/udp` on the host as IGW/S2S ports for debugging. Keep those closed on the router unless client testing proves the live routing path needs them. Never forward RabbitMQ (`31982/tcp`) or Postgres.

## Backup

Use the backup helper for routine snapshots:

```bash
./scripts/backup-state.sh .env
```

It writes:

- `backups/<timestamp>/postgres-dune_sb_1_4_0_0.dump`
- `backups/<timestamp>/rabbitmq-admin.tgz`
- `backups/<timestamp>/rabbitmq-game.tgz`
- `backups/<timestamp>/server-saved.tgz`
- `backups/<timestamp>/manifest.txt`

The helper intentionally writes only under `backups/`, which is ignored by git. Restore also refuses backup directories outside `backups/` so local artifacts do not drift into publishable paths.

Manual Postgres dump:

```bash
docker compose --env-file .env exec -T postgres \
  pg_dump -U dune -d dune_sb_1_4_0_0 -Fc \
  > backups/dune-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Archive RabbitMQ state from inside the running containers:

```bash
docker compose --env-file .env exec -T admin-rmq \
  tar -czf - -C /var/lib/rabbitmq . \
  > backups/rabbitmq-admin-$(date -u +%Y%m%dT%H%M%SZ).tgz

docker compose --env-file .env exec -T game-rmq \
  tar -czf - -C /var/lib/rabbitmq . \
  > backups/rabbitmq-game-$(date -u +%Y%m%dT%H%M%SZ).tgz
```

Archive server saved state:

```bash
tar -czf backups/server-saved-$(date -u +%Y%m%dT%H%M%SZ).tgz data/server-saved
```

Keep `backups/` local. Database dumps can contain player, world, and account-linked state.

## Restore

Restore is disruptive. It stops services that write state before replacing database contents, and optional RabbitMQ/server-saved restores replace local state directories. Run a dry run first and do not perform a real restore while players are online.

Stop services that write state:

```bash
docker compose --env-file .env down
```

Use the restore helper for Postgres:

```bash
./scripts/restore-state.sh --dry-run .env backups/YYYYMMDDTHHMMSSZ
./scripts/restore-state.sh .env backups/YYYYMMDDTHHMMSSZ
```

Restore RabbitMQ and saved state only when you intentionally want to replace those local directories:

```bash
./scripts/restore-state.sh --dry-run --rabbitmq --server-saved .env backups/YYYYMMDDTHHMMSSZ
./scripts/restore-state.sh --rabbitmq --server-saved .env backups/YYYYMMDDTHHMMSSZ
```

Manual restore:

```bash
docker compose --env-file .env up -d postgres
docker compose --env-file .env exec -T postgres \
  pg_restore -U dune -d dune_sb_1_4_0_0 --clean --if-exists \
  < backups/dune-YYYYMMDDTHHMMSSZ.dump
```

Then start the rest of the stack:

```bash
docker compose --env-file .env up -d admin-rmq game-rmq rmq-auth-shim text-router gateway director
```

## Upgrade Checklist

Before changing `DUNE_IMAGE_TAG`:

- Capture `docker compose --env-file .env ps`.
- Run `./scripts/status.sh .env` and save the output locally.
- Back up Postgres, RabbitMQ, and `data/server-saved`.
- Record the old `DUNE_IMAGE_TAG`.
- Load the new Funcom image tarballs with `./scripts/load-images.sh`.
- Run `docker compose --env-file .env config --quiet`.
- Start only `postgres`, `admin-rmq`, and `game-rmq`.
- Run `docker compose --env-file .env run --rm db-init`.
- Start the service layer and check `./scripts/status.sh .env`.
- Attempt Hagga Basin login before testing cross-map routing.

Rollback means restoring the old image tag and restoring state from the backups taken before the upgrade. Do not mix a downgraded image tag with post-upgrade database state unless you have verified the schema did not change.
