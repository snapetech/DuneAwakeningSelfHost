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

The admin panel Overview and Ops tabs expose the same high-level readiness from a browser. The map table is derived from `world_partition`, `farm_state`, and `active_server_ids`; the network table probes local Postgres plus upstream HTTP reachability for the Dune account portal and public Dune/Funcom sites. Treat those probes as operator signals, not proof that FLS registration or client travel is healthy.

The Ops tab also has a restart-announcement scheduler. It stores scheduled jobs in `backups/admin-panel/announcements.json` and invokes `DUNE_ADMIN_ANNOUNCE_COMMAND` at the chosen repeat interval until the scheduled restart time. The default hook, `scripts/announce.sh`, publishes a configurable `ServiceBroadcast` envelope to the admin RabbitMQ `rpc` exchange. `DUNE_ANNOUNCE_PAYLOAD_MODE` can switch among built-in probe envelopes while validating the live server's expected wrapper. Keep `DUNE_ANNOUNCE_RMQ_PASSWORD` secret and scope that RabbitMQ user to management plus write access on the `rpc` exchange.

The same Ops area has a scheduled restart planner. Restart jobs store in `backups/admin-panel/restart-jobs.json`. They default to dry-run mode and only invoke `DUNE_ADMIN_RESTART_COMMAND` when execution is explicitly enabled. The default hook, `scripts/restart-target.sh`, uses Docker Compose on the host or the mounted Docker Engine socket in the admin-panel container. Treat that socket as privileged host control: keep the panel local/private, require the admin token, and do not publish it to the internet. The socket fallback restarts existing containers only; it does not recreate containers with changed environment.

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

## Fixed-Partition Map Recovery

If a specific map process crashes with `Local partition is not found`, recover it with the fixed-partition helper instead of immediately force-recreating the container. The failure means the process started with a new server id while its `world_partition` row was still assigned to an old server id that had not aged out of `active_server_ids`.

For example, partition 18 is `heighliner-dungeon`:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/recover-map.sh .env heighliner-dungeon 18
```

The helper marks the old partition owner dead, stops the map service, waits until the old id is no longer active, starts the service, and waits for the partition to become ready/alive/active again.

## Map Watchdog

Compose does not currently restart map containers automatically, and a generic `restart: always` policy is not safe for fixed-partition maps because a fast blind restart can reproduce the stale server-id crash loop.

Run the watchdog from an operator shell or a host-level service manager if you want automatic recovery:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/watch-maps.sh .env
```

The watchdog only recovers services that already have containers and are `exited` or `dead`; it does not start maps that were intentionally never launched. Recovery delegates to `scripts/recover-map.sh`, so the old partition owner is marked dead and aged out before the service starts again.

Check what it is monitoring without changing state:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/watch-maps.sh .env --status
```

Validate watchdog status and dry-run behavior without Docker:

```bash
make test-watch-maps
```

To run it under systemd on this host, install a rendered unit for the current checkout:

```bash
./scripts/install-map-watchdog-service.sh .env
sudo systemctl enable --now dune-map-watchdog.service
systemctl status dune-map-watchdog.service
```

The installer updates `WorkingDirectory` and `ExecStart` for the current repo path before copying the unit to `/etc/systemd/system/`.

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

The Compose files also expose `7888-7917/udp` on the host as IGW/S2S ports for debugging. Keep those closed on the router unless client testing proves the live routing path needs them.

Live-client login also asks FLS for a game RabbitMQ address before it starts the gameplay UDP leg. `GAME_RMQ_PUBLIC_HOST` and `GAME_RMQ_PUBLIC_PORT` control the address Gateway reports to FLS. For a publicly reachable live self-hosted server, forward `GAME_RMQ_PUBLIC_PORT` TCP, default `31982/tcp`, to the host. Do not forward Postgres, RabbitMQ management, or admin panel ports.

### Internal Clients and LAN Reflection

For a public server, keep `EXTERNAL_ADDRESS` set to the public WAN address even
for internal players. Internal players joining through the server listing will
still be handed that public address by the Dune/FLS path.

Do not make changing `EXTERNAL_ADDRESS` part of normal operations. Instead,
choose one LAN reflection mode and document it for the site:

- router UDP hairpin/NAT reflection;
- router static route for the public `/32` to the Dune host;
- per-client route for the public `/32` to the Dune host.

See `docs/lan-reflection.md` for the standard setup and validation commands.

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
