# Operations

This page covers state management for the Compose lab. Commands assume the default `.env` file; pass `--env-file` directly if you use a different environment.

Set `CONTAINER_RUNTIME=podman` when testing with Podman-compatible Compose commands:

```bash
CONTAINER_RUNTIME=podman ./scripts/status.sh .env
CONTAINER_RUNTIME=podman ./scripts/capture-routing.sh .env baseline-idle
CONTAINER_RUNTIME=podman ./scripts/backup-state.sh .env
CONTAINER_RUNTIME=podman ./scripts/restore-state.sh .env backups/20260519T150000Z
```

For platform-specific notes, including Windows/macOS operator workstations,
Podman caveats, VM layout, and NAS storage guidance, see `docs/platforms.md`.

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

Normal production scripts derive Docker Compose overlays with
`scripts/compose-files.sh .env`. Do not pin `COMPOSE_FILES` in persistent
service units or `.env` for host role selection; `POSTGRES_REMOTE_REPLICA_HOST`
is the active Postgres owner and causes `compose.failover-standby.yaml` to be
included on the promoted host.

The `health verdict` section expects these signals at the same time: every current partition has an alive farm row joined through `world_partition`, every active server id is present, and game RabbitMQ service-user connections exist. A separate `current_ready_alive` line is still useful, but some live builds can leave `farm_state.ready=false` for a current map after the game log has already reported `Server farm is READY`.

For RabbitMQ-specific checks, use:

```bash
./scripts/rmq-health.sh .env
```

For the client-facing game RabbitMQ TLS certificate identity, use:

```bash
./scripts/check-rabbitmq-cert-sans.sh .env
```

The check is read-only. It reports the certificate SANs and warns when the cert does not cover `GAME_RMQ_PUBLIC_HOST`, `game-rmq`, `localhost`, or `127.0.0.1`.

Certificate generation is explicit and guarded:

```bash
./scripts/generate-rabbitmq-cert.sh .env
```

The generator refuses to overwrite existing TLS files unless `--force` is passed. Use `--force` only during planned maintenance after backing up `config/tls/rabbitmq`.

Admin RabbitMQ can have fewer active service-user connections than farm partitions in the 30-map warm-pool layout. Treat it as unhealthy when recent auth/connectivity errors appear or when a failed client transition correlates with missing admin queue consumers.

Fast auth-path check:

```bash
./scripts/seed-gateway-neighbor.sh
./scripts/verify-rmq-auth-path.sh
```

That verifier covers the restart failure mode where maps are alive in the database but dynamic RabbitMQ auth times out because `admin-rmq` cannot reach the local auth shim.

The admin panel Overview and Ops tabs expose the same high-level readiness from a browser. The map table is derived from `world_partition`, `farm_state`, and `active_server_ids`; the network table probes local Postgres plus upstream HTTP reachability for the Dune account portal and public Dune/Funcom sites. Treat those probes as operator signals, not proof that FLS registration or client travel is healthy.

The Ops tab also has restart-announcement and scheduled restart planners. The daily maintenance target is 06:00 local host time, with the host timer firing at 05:30 to create a 30-minute warning window. Executed maintenance uses a stopped-world backup, then checks the current Steam package for updated Funcom image tarballs before recreating services. See [`docs/maintenance-updates.md`](maintenance-updates.md) for the full timeline, update logic, and timer install path.

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

## Control-Plane Nudges

Use a nudge when the maps are already running and registered locally, but the
browser/FLS view is stale. This is different from map recovery: do not restart
map containers just because the server browser is missing maps.

Good nudge candidates:

- The server parent row appears in the browser, but the nested map list is empty
  or stale.
- `world_partition` has the expected assigned rows and `blocked=false`.
- Director logs show `[ServerState] Received server state` for the expected
  partitions.
- Director, gateway, or RabbitMQ had a temporary connectivity failure and then
  recovered.

First confirm the local state:

```bash
docker compose --env-file .env exec -T postgres psql -U dune -d dune_sb_1_4_0_0 \
  -c "select count(*) filter (where server_id is not null) assigned, count(*) filter (where blocked) blocked, count(*) total from dune.world_partition;"

docker logs --since 5m dune_server-director-1 2>&1 \
  | grep '\[ServerState\] Received server state' \
  | sed -E 's/.*"partitionId":([0-9]+).*/\1/' \
  | sort -n | uniq -c
```

If maps are locally present but FLS declarations are stale, restart only
Director. This causes Director to rebuild RabbitMQ subscriptions and re-declare
the battlegroup/map state to FLS without replacing running map containers:

```bash
docker compose --env-file .env \
  -f compose.yaml -f compose.allmaps.yaml \
  restart director
```

On standby/failover hosts, include the same override files the stack is
currently using. For example:

```bash
docker compose --env-file .env \
  -f compose.yaml -f compose.failover-standby.yaml \
  -f compose.allmaps.yaml -f compose.64g-limits.yaml \
  restart director
```

Verify the nudge by watching for successful FLS calls:

```bash
docker logs --since 90s dune_server-director-1 2>&1 \
  | grep -E 'Director_InitializeDirector|Battlegroups_DeclareBattlegroupUpdates|Battlegroups_SendBattlegroupHeartbeat|RMQ unreachable|No database connection'
```

`./scripts/status.sh` also runs `scripts/fls-publication-health.py`. Treat a
degraded FLS publication result as a server-browser outage even when all map
rows are locally green. The check looks for recent successful Director
initialization, heartbeat, population/capacity declarations, Gateway farm
status declaration, and no later FLS errors such as `INVALID_DATA` or
`does not exist or is inactive`.

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml:compose.gateway-hostnet.yaml' \
  ./scripts/fls-publication-health.py .env \
  --compose-files 'compose.yaml:compose.allmaps.yaml:compose.gateway-hostnet.yaml'
```

Admin alerts can include the same signal when
`DUNE_PLAYER_PRESENCE_INFRA_ADMIN_ALERTS_ENABLED=true`; the FLS publication
subcheck is controlled by `DUNE_PLAYER_PRESENCE_FLS_PUBLICATION_HEALTH_ENABLED`.

### HP3 on map travel from FLS DNS failure

On 2026-05-28, live players hit HP3 disconnects while entering or leaving
Overmap and Deep Desert. The destination map logs showed
`Auth_VerifyFlsServerToken` failing with `Couldn't resolve host name` for
`sb-retail.fls.funcom.com`, followed by `VerifyIdentity Failed` and the HP3
`NMT_Failure` rejection. This was not a bad player token; a retry with the same
identity could succeed after DNS recovered.

The persistent fix is `compose.fls-ipv4-hosts.yaml`. Keep
`DUNE_FLS_IPV4_HOSTS_ENABLED=true` for live stacks and include the compose files
from `scripts/compose-files.sh .env`. The overlay pins
`sb-retail.fls.funcom.com` for Director, Gateway, TextRouter, Survival, and all
map containers because map containers perform `Auth_VerifyFlsServerToken`
during travel/login:

```bash
IFS=: read -r -a compose_files <<< "$(./scripts/compose-files.sh .env)"
compose_args=()
for file in "${compose_files[@]}"; do
  compose_args+=("-f" "$file")
done
docker compose --env-file .env "${compose_args[@]}" config \
  | awk '/^  overmap:/{flag=1} flag && /^  [[:alnum:]_-]+:/{if ($1 != "overmap:") exit} flag{print}' \
  | grep -E 'extra_hosts|sb-retail'
```

For an immediate no-restart live mitigation, add the same host pin to every
running Dune service container after verifying the host is `kspls0`:

```bash
hostname
for c in $(docker ps --format '{{.Names}}' | grep '^dune_server-' | grep -Ev 'postgres|rmq|admin-panel|ingress'); do
  docker exec "$c" sh -lc "grep -q 'sb-retail.fls.funcom.com' /etc/hosts || printf '13.107.253.70 sb-retail.fls.funcom.com\n13.107.226.70 sb-retail.fls.funcom.com\n' >> /etc/hosts"
done
```

Verify the runtime resolver path from a representative map:

```bash
docker exec dune_server-overmap-1 sh -lc 'python3 - <<PY
import socket
for row in socket.getaddrinfo("sb-retail.fls.funcom.com", 443, 0, socket.SOCK_STREAM):
    print(row[-1][0])
PY'
```

Then check recent travel destinations for recurrence:

```bash
docker logs --since 15m dune_server-overmap-1 dune_server-deep-desert-1 dune_server-arrakeen-1 2>&1 \
  | grep -Ei 'HP3|Couldn.t resolve host|Auth_VerifyFlsServerToken|VerifyIdentity Failed' || true
```

If the parent server row itself is missing from the browser, nudge `gateway`
instead of Director. This is also the recovery for accidental FLS identity
stealing: if another host starts with the same `.env`/`WORLD_UNIQUE_NAME` and
then stops, it can publish the same battlegroup as inactive. Restarting
`gateway` on the intended live host re-declares the farm as active without
restarting Survival or the map containers:

```bash
docker compose --env-file .env \
  -f compose.yaml -f compose.allmaps.yaml \
  restart gateway
```

Then verify that Gateway declared the farm and observed the maps:

```bash
docker compose --env-file .env \
  -f compose.yaml -f compose.allmaps.yaml \
  logs --since 3m gateway \
  | grep -E 'GatewayDeclareFarmStatus|Server .* came up|HTTP Request Error|failed|inactive'
```

On hosts affected by Docker bridge neighbor-learning issues, reseed the
gateway/Postgres neighbors after the restart:

```bash
./scripts/seed-gateway-neighbor.sh
```

If `scripts/fls-publication-health.py` still reports Director population
errors such as `INVALID_DATA` or `does not exist or is inactive` immediately
after the gateway restart, check the live browser before escalating. Gateway
farm declaration is the authoritative fix for the missing parent row; Director
population may lag or continue reporting stale FLS-side state for a short
interval.

If Director cannot reach RabbitMQ, nudge the stuck broker path first, then
Director:

```bash
docker exec dune_server-director-1 sh -lc 'nc -vz -w2 game-rmq 5672; nc -vz -w2 admin-rmq 5672; nc -vz -w2 postgres 5432'
docker compose --env-file .env restart admin-rmq director
```

If a specific map container is exited, dead, missing from `active_server_ids`,
or crashing with `Local partition is not found`, use the fixed-partition map
recovery helper instead of a nudge.

## Map Watchdog

Compose does not currently restart map containers automatically, and a generic `restart: always` policy is not safe for fixed-partition maps because a fast blind restart can reproduce the stale server-id crash loop.

Run the watchdog from an operator shell or a host-level service manager if you want automatic recovery:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/watch-maps.sh .env
```

The watchdog only recovers services that already have containers; it does not start maps that were intentionally never launched. It recovers containers that are `exited` or `dead`, and it also checks running maps against Postgres for partition registration. A running map is recovered when its partition is not alive or is missing from `active_server_ids`. Recovery delegates to `scripts/recover-map.sh`, so the old partition owner is marked dead and aged out before the service starts again. After the recovered partition is ready/alive/active, `recover-map.sh` runs `scripts/restart-post-start-health.sh`; that reapplies process-local runtime patches such as the instant-logoff timer patch. Do not replace this with a raw `docker compose up -d <map>` on live maps.

If a raw Compose map start or recreate is unavoidable during live repair, finish
with:

```bash
./scripts/restart-post-start-health.sh
./scripts/patch-logoff-timers-runtime.sh --local --dry-run
```

The dry run must show the target containers' logoff timer arrays as `0 0 0 0`.
On 2026-06-02, DD1 lost instant logout because it was manually recreated without
that post-start step; the process came back with `30`/`300` second runtime
timers despite correct INI values.

For intentional manual starts, use the wrapper instead of raw Compose:

```bash
./scripts/start-map-with-post-hooks.sh .env deep-desert
```

Use `scripts/recover-map.sh` instead when the map has stale partition
registration or `Local partition is not found`; the wrapper does not mark old
partition owners dead.

## Landsraad Coriolis Guard

Confidence: high.

Standard PvE DD must keep a weekly Coriolis cycle even when Coriolis damage,
shifting sands, cycle-end restart, and DB wipe are disabled. Landsraad derives
its active/suspended window from the Coriolis cycle. Setting
`m_CycleDurationInDays=36524` prevented visible Coriolis rollover, but also
globally suspended Landsraad while the database term still looked active.

Required live values in `config/UserGame.ini` and
`config/UserGame.deep-desert-coriolis.ini`:

```ini
m_bCoriolisAutoSpawnEnabled=False
m_bCoriolisDoesDamage=False
m_bCoriolisTriggerShiftingSands=False
m_CycleDurationInDays=7
m_bShouldRestartServerOnCycleEnd=False
m_bIsDbWipeEnabled=False
```

Run the guard before and after any Coriolis or DD1 map restart work:

```bash
./scripts/validate-landsraad-coriolis-cycle.sh .env
```

`scripts/restart-target.sh`, `scripts/start-map-with-post-hooks.sh`, and
`scripts/restart-post-start-health.sh` run this guard by default. Leave
`DUNE_LANDSRAAD_CORIOLIS_GUARD_ENABLED=true` unless intentionally testing in a
non-production lab.

On hosts affected by the Docker bridge neighbor-learning failure, run the host
systemd watchdog with `DUNE_WATCH_SEED_NEIGHBORS=true`. That makes the watchdog
run `scripts/seed-gateway-neighbor.sh` periodically after recovery scans,
keeping the known control-plane and map-to-RabbitMQ/Postgres neighbor entries
warm without putting seeding ahead of map crash detection. Neighbor seeding is
best-effort, runs no more often than `DUNE_WATCH_SEED_INTERVAL`, default `300`
seconds, and is bounded by `DUNE_WATCH_SEED_TIMEOUT`, default `90` seconds, so
a slow Docker inspection or namespace command cannot stall map recovery
indefinitely.

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
current_alive_active=31 active_servers=31 partitions=31
```

Server-browser naming is split across the control plane based on the observed
in-game browser. `config/gateway.ini` `[gateway].display_name` is the
parent/top row and must stay the branded server title. `WORLD_NAME` and
`DUNE_SERVER_DISPLAY_NAME` are the nested/details row and must stay the
feature-list description. To refresh the server-browser rows without
disconnecting existing map sessions, recreate only `gateway`, then reseed the
gateway/Postgres bridge neighbor entries:

```bash
docker compose --env-file .env up -d --force-recreate --no-deps gateway
./scripts/seed-gateway-neighbor.sh
```

Known brittle area: Docker bridge peer discovery on this host. Do not remove
the neighbor-seeding step until a maintenance-window network rebuild proves
that newly recreated control-plane containers can connect without it.

For unattended operation, run the map watchdog as a host service after startup:

```bash
./scripts/install-map-watchdog-service.sh .env
sudo systemctl enable --now dune-map-watchdog.service
```

For unattended backup sync, configure one of the examples under
`examples/backup/`, test `scripts/backup-offsite.sh` manually, then install:

```bash
./scripts/install-backup-offsite-timer.sh .env examples/backup/rclone-offsite.env
```

Verify backup readability after changing the backup path:

```bash
./scripts/verify-backup.sh backups/<backup-id>
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
7888-7917/udp
```

`7888-7918/udp` are the IGW ports paired with the 31 warm-pool game ports. If your deployment relies on them for live-client routing or server-browser checks, forward them to the Dune host. Do not remove IGW forwards from a working deployment without packet-capture evidence and a router backup.

Live-client login also asks FLS for a game RabbitMQ address before it starts the gameplay UDP leg. `GAME_RMQ_PUBLIC_HOST` and `GAME_RMQ_PUBLIC_PORT` control the AMQP address Gateway reports to FLS. `GAME_RMQ_PUBLIC_HTTP_PORT`, default `15673/tcp`, controls the HTTP address Gateway reports to FLS, while `GAME_RMQ_HTTP_BIND_ADDRESS` controls the host bind for RabbitMQ management and defaults to `127.0.0.1`. For a publicly reachable live self-hosted server, forward `GAME_RMQ_PUBLIC_PORT` TCP, default `31982/tcp`, to the host. Do not forward Postgres, RabbitMQ management, or admin panel ports unless a targeted browser-ping experiment explicitly requires it.

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

## Artificial Exchange Buyer

Use `scripts/build-exchange-catalog.py` to build the reviewed local catalog and
`scripts/artificial-exchange-bot.py` for dry-run scans. Real purchases require
the explicit artificial Exchange gates and confirmation phrase. Settlement
auto-claim remains disabled; use the bot's `--settlement-report` mode to inspect
completed orders. See `docs/artificial-exchange.md`.

Install the long-running service with:

```bash
python3 scripts/artificial-exchange-bot.py --check-ready
make install-artificial-exchange-buyer-service ENV_FILE=.env
```

The Exchange populator is separate from the buyer. Leave
`dune-artificial-exchange-populator.service` stopped unless you are deliberately
seeding operator-owned NPC listings. Current populator policy requires
dune.exchange price evidence and tier 2+ rows; see `docs/artificial-exchange.md`
before starting it.

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

This keeps rolling dumps on the remote replica host. The installed timer runs as
the installing local user by default so SSH uses that user's keys and host
aliases. Use `DUNE_REPLICA_SNAPSHOT_USER` and
`DUNE_REPLICA_SNAPSHOT_GROUP` only for a dedicated service account with working
remote SSH credentials. Use it alongside daily offline full-state backups.

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
- Run `./scripts/check-steam-update.sh .env` to compare `.env` with the current Steam package.
- Load the new Funcom image tarballs with `./scripts/load-images.sh .env`.
- Update the env pin with `./scripts/check-steam-update.sh .env --write-env`, or edit `DUNE_IMAGE_TAG` manually if multiple tags are reported.
- Run `docker compose --env-file .env config --quiet`.
- Start only `postgres`, `admin-rmq`, and `game-rmq`.
- Run `docker compose --env-file .env run --rm db-init`.
- Start the service layer and check `./scripts/status.sh .env`.
- Attempt Hagga Basin login before testing cross-map routing.

Rollback means restoring the old image tag and restoring state from the backups taken before the upgrade. Do not mix a downgraded image tag with post-upgrade database state unless you have verified the schema did not change.
