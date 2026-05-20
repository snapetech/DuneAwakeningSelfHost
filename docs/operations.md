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

The `health verdict` section expects these signals at the same time: every current partition has an alive farm row joined through `world_partition`, every active server id is present, and game RabbitMQ service-user connections exist. A separate `current_ready_alive` line is still useful, but some live builds can leave `farm_state.ready=false` for a current map after the game log has already reported `Server farm is READY`.

For RabbitMQ-specific checks, use:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
```

Admin RabbitMQ can have fewer active service-user connections than farm partitions in the 30-map warm-pool layout. Treat it as unhealthy when recent auth/connectivity errors appear or when a failed client transition correlates with missing admin queue consumers.

Fast auth-path check:

```bash
./scripts/seed-gateway-neighbor.sh
./scripts/verify-rmq-auth-path.sh
```

That verifier covers the restart failure mode where maps are alive in the database but dynamic RabbitMQ auth times out because `admin-rmq` cannot reach the local auth shim.

The admin panel Overview and Ops tabs expose the same high-level readiness from a browser. The map table is derived from `world_partition`, `farm_state`, and `active_server_ids`; the network table probes local Postgres plus upstream HTTP reachability for the Dune account portal and public Dune/Funcom sites. Treat those probes as operator signals, not proof that FLS registration or client travel is healthy.

The Ops tab also has a restart-announcement scheduler. It stores scheduled jobs in `backups/admin-panel/announcements.json` and invokes `DUNE_ADMIN_ANNOUNCE_COMMAND` at the chosen repeat interval until the scheduled restart time. The default hook, `scripts/announce.sh`, publishes directly to game RabbitMQ `chat.map` as the Paul announcer account using bundled `pika`. It reads `/workspace/.env` at delivery time, binds currently connected player queues to the configured chat routes when `DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES=true`, and then sends the message. Dashboard-origin announcements are wrapped as `!!! message !!!`. Verify with `./scripts/verify-announcement.sh 'DASH ANNOUNCEMENT VERIFY'`. Keep the announcer password and RabbitMQ credentials private.

The same Ops area has a scheduled restart planner. Restart jobs store in `backups/admin-panel/restart-jobs.json`. They default to dry-run mode and only invoke `DUNE_ADMIN_RESTART_COMMAND` when execution is explicitly enabled. Executed restart jobs stop the selected services, create a maintenance backup under `backups/admin-panel/maintenance/`, then start/recreate the selected services and wait for all current world partitions to become alive and active again. Executed shutdown jobs stop the selected services, create the same maintenance backup, and leave them offline. Maintenance backups include the authoritative local stopped-world Postgres dump plus `postgres-layers.json`, which records streaming-replication slot/sender status and optionally triggers a remote replica snapshot when `POSTGRES_REMOTE_REPLICA_HOST` is configured. Replica/snapshot failures are recorded as warnings because they are additional layers, not replacements for the stopped-world dump. The default hook, `scripts/restart-target.sh`, uses Docker Compose on the host or the mounted Docker Engine socket in the admin-panel container. Treat that socket as privileged host control: keep the panel local/private, require the admin token, and do not publish it to the internet. The socket fallback now uses a short-lived privileged Docker CLI helper for start/recreate phases, so scheduled daily restarts apply changed `.env` values and bind-mounted config, then run `scripts/seed-gateway-neighbor.sh` before and after the recreate. Recreate is run with `--no-deps` so excluded stateful services are not pulled into the restart as Compose dependencies. After seeding, the hook runs `scripts/verify-rmq-auth-path.sh`; the restart is failed if `admin-rmq` cannot reach `rmq-auth-shim`, or if `game-rmq` cannot reach `rmq-auth-shim` and `text-router`.

For the expanded standing farm, the expected summary is:

```text
current_alive_active=9 active_servers=9 partitions=9
```

For the 30-partition warm pool, the expected summary is:

```text
current_alive_active=30 active_servers=30 partitions=30
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

The watchdog only recovers services that already have containers; it does not start maps that were intentionally never launched. It recovers containers that are `exited` or `dead`, and it also checks running maps against Postgres for partition registration. A running map is recovered when its partition is not alive or is missing from `active_server_ids`. Recovery delegates to `scripts/recover-map.sh`, so the old partition owner is marked dead and aged out before the service starts again.

By default the watchdog does not recover solely on `farm_state.ready=false`, because some live builds can report `ready=false` after the map log has reached `Server farm is READY`. To make readiness strict, set:

```bash
DUNE_WATCH_REQUIRE_READY=true
```

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
./scripts/start-full-warm-pool.sh .env
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
```

The helper starts Postgres and both RabbitMQ services first, waits for their
health checks, writes the 30-partition layout, starts the service layer, then
starts maps in batches: `survival`/`overmap`, partitions 3-9, then partitions
10-30. It uses `--no-recreate` for normal startup so a routine online operation
does not replace Postgres under running game servers.

The helper also seeds required Docker bridge neighbor entries before and after
the control-plane services start. This is a site-specific guard for the current
`dune_server_default` bridge, where recreated containers have sometimes failed
to learn existing peers or kept stale permanent neighbor entries. The gateway
keeps `172.31.240.40` and MAC `02:42:ac:1f:f0:28`; `admin-chat-commands` is
pinned to `172.31.240.41` so it cannot take the gateway address during a
recreate. The seeder derives Postgres and live container MACs with
`docker inspect`, pre-seeds Postgres with the gateway's static MAC before
gateway starts, then refreshes both directions while gateway is still in its
startup sleep. Run the same step manually after force-recreating `gateway`,
`director`, `game-rmq`, `rmq-auth-shim`, or `text-router`:

```bash
./scripts/seed-gateway-neighbor.sh
```

Known working baseline as of May 19, 2026:

```text
gateway declares Snapetech PVE Friendly Server (www.snape.tech) to FLS
gateway reaches postgres:5432
game-rmq reaches rmq-auth-shim:8080 and text-router:8080
director reaches game-rmq:5672, admin-rmq:5672, and postgres:5432
director heartbeat to FLS succeeds
current_alive_active=30 active_servers=30 partitions=30
```

Known brittle area: Docker bridge peer discovery on this host. Do not remove
the neighbor-seeding step until a maintenance-window network rebuild proves
that newly recreated control-plane containers can connect without it.

For unattended operation, run the map watchdog as a host service after startup:

```bash
./scripts/install-map-watchdog-service.sh .env
sudo systemctl enable --now dune-map-watchdog.service
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

If the optional streaming replica is enabled, prefer taking routine logical dumps from the read-only standby:

```bash
mkdir -p backups
docker compose --env-file .env -f compose.yaml -f compose.replica.yaml exec -T postgres-replica \
  pg_dump -U dune -d dune_sb_1_4_0_0 -Fc \
  > backups/dune-replica-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Check replica health before relying on it:

```bash
docker compose --env-file .env -f compose.yaml -f compose.replica.yaml exec -T postgres \
  psql -U dune -d dune_sb_1_4_0_0 -c \
  "select application_name,state,sync_state,write_lag,flush_lag,replay_lag from pg_stat_replication;"
```

See `docs/postgres-replication.md` for setup, lag checks, and failure handling. Streaming replication is not point-in-time recovery; bad writes and deletes replicate immediately.

For the remote standby layout, use the snapshot helper instead of pulling dumps back to the primary host:

```bash
./scripts/replica-snapshot.sh .env replica.example.lan /srv/dune-postgres-replica
./scripts/install-replica-snapshot-timer.sh .env replica.example.lan /srv/dune-postgres-replica
```

This keeps rolling dumps on the remote replica host. Use it alongside daily offline full-state backups.

Check all backup layers:

```bash
./scripts/backup-layers-status.sh .env replica.example.lan /srv/dune-postgres-replica
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
