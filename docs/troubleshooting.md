# Troubleshooting

Start with:

```bash
./scripts/preflight.sh .env
./scripts/status.sh .env
```

The preflight helper catches missing tools, missing image tarballs, default credentials, empty tokens, and unsafe host bindings. The status helper prints container state, selected database rows, RabbitMQ connections, and recent high-signal logs with known token/password patterns redacted.

## Image Tarball Not Found

Symptom:

```text
missing image tar: ...
```

Check `DUNE_STEAM_SERVER_DIR` in `.env`. It must point at the official Steam tool install directory that contains `images/battlegroup` and `images/prerequisites`.

## Compose Config Fails

Run:

```bash
docker compose --env-file .env.example config --quiet
docker compose --env-file .env config
```

If `.env` is missing, run:

```bash
./scripts/populate-local-env.sh
```

## FLS Token Rejected

Symptoms often include logs mentioning invalid token, failed FLS registration, or account entitlement problems.

Check:

- `FLS_SECRET` is set in `.env`.
- The token came from the live Dune: Awakening account portal.
- The Steam account used for token generation owns the self-hosted server entitlement.
- `EXTERNAL_ADDRESS` is reachable by clients.

## RabbitMQ Auth Failures

Symptoms:

```text
ACCESS_REFUSED
PLAIN login refused
```

Check:

- `rmq-auth-shim` is running.
- `text-router` is running before game-server startup.
- `WORLD_UNIQUE_NAME` matches the expected service-user prefix.
- RabbitMQ ports are not exposed publicly.
- `COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env` has no recent auth/connectivity errors.
- `./scripts/verify-rmq-auth-path.sh` passes. This verifies `admin-rmq -> rmq-auth-shim`, `game-rmq -> rmq-auth-shim`, and `game-rmq -> text-router`.

The shim is a local compatibility workaround for internal `sg.<world>.*`, `bgd.<world>.*`, and `tr.<world>.*` service users. Keep it paired with localhost-only RabbitMQ host bindings.

RabbitMQ auth cache TTL is intentionally long in `config/rabbitmq-admin.conf` and `config/rabbitmq-game.conf` to avoid hammering the HTTP auth path during 30-map warm-pool startup. Those config files are read by RabbitMQ at container start, so changing them requires a RabbitMQ restart during a maintenance window.

## Docker Bridge Neighbor Learning Failure

Symptoms:

```text
gateway exits with psycopg2.OperationalError: connection to server at "postgres" timed out
game-rmq cannot reach rmq-auth-shim
director logs RabbitMQ BrokerUnreachableException / Host is unreachable
```

Observed on May 19, 2026: existing map containers continued to talk to Postgres, but newly recreated/control-plane containers could not reliably reach existing peers on `dune_server_default`. Packet captures showed SYN packets entering the bridge with no reply, and manually seeding neighbor entries restored connectivity immediately.

Working recovery:

```bash
docker compose -f compose.yaml -f compose.allmaps.yaml --env-file .env up -d --no-recreate \
  postgres admin-rmq game-rmq rmq-auth-shim text-router director gateway

./scripts/seed-gateway-neighbor.sh

docker exec dune_server-gateway-1 sh -lc 'nc -vz -w 2 postgres 5432'
docker exec dune_server-game-rmq-1 sh -lc 'nc -vz -w 2 rmq-auth-shim 8080; nc -vz -w 2 text-router 8080'
docker exec dune_server-director-1 sh -lc 'nc -vz -w 2 game-rmq 5672'
```

Normal startup runs `scripts/seed-gateway-neighbor.sh` from `scripts/start-full-warm-pool.sh`. If a control-plane container is force-recreated manually, run the seed script again before judging the service unhealthy.

Admin-triggered restarts run `scripts/seed-gateway-neighbor.sh` before and after recreate and then run `scripts/verify-rmq-auth-path.sh`. If the verifier fails, the restart should be treated as incomplete even when the map rows look alive.

Long-term fix: rebuild the Docker network during a maintenance window and remove the manual neighbor seeding only after new/recreated containers can ping and TCP-connect to `postgres`, `game-rmq`, `rmq-auth-shim`, and `text-router` without seeded neighbors.

## Database Already Initialized

`db-init` is idempotent for an existing schema. If you need a fresh world, stop Compose and remove local runtime data:

```bash
docker compose --env-file .env down
rm -rf data/postgres data/rabbitmq data/server-saved
```

This deletes local server state.

## Survival Server Starts But Is Not Reachable

Check:

- Router/firewall forwards `7777/udp` for the single `Survival_1` layout, or `7777-7785/udp` for the expanded standing farm.
- `EXTERNAL_ADDRESS` matches the address clients should use.
- `./scripts/status.sh` shows `farm_state.ready` and non-empty game/IGW addresses.
- `./scripts/status.sh` shows game and admin RabbitMQ `sg.<world>.<server>.game/admin` connections.
- RabbitMQ and Postgres ports remain local-only.

The game can log a warning that binding directly to the public `EXTERNAL_ADDRESS` failed. In this Compose layout that is expected when the public address belongs to the router rather than the container. The important checks are that Docker publishes the relevant game UDP port, the game reports `listening for Clients on <EXTERNAL_ADDRESS>:<port>`, and Director/Gateway declare that same address to FLS.

### Hangs at `Connecting to Sietch` from the same LAN

If the client is on the same LAN as the server and the server advertises the
public WAN address, first prove whether packets reach the host:

```bash
sudo timeout 75 tcpdump -ni enp17s0 'host <public-ip> and udp'
sudo iptables -t nat -L DOCKER -n -v | rg 'dpt:(7777|7888|7778|7889)'
```

If tcpdump captures `0` packets and Docker counters stay at `0`, the client is
not reaching the Dune host. This is a LAN hairpin/routing issue, not a password,
map readiness, or RabbitMQ issue.

Use one of the standard internal-join approaches in
`docs/lan-reflection.md`: router UDP hairpin NAT, router static route for the
public `/32` to the Dune host, or per-client `/32` route. Keep
`EXTERNAL_ADDRESS` set to the public address for a public server.

## Survival Crashes After Database Restart

Symptoms:

```text
PQconsumeInput failed: server closed the connection unexpectedly
Fatal error: ... PSqlProcessingThread.cpp
Unhandled Exception: SIGSEGV
```

The current game-server process does not reliably survive a lost Postgres connection. Avoid restarting Postgres while players are online. If it happens, recover by restarting the game server after dependencies are healthy:

```bash
./scripts/recover-survival.sh .env
```

The script does not wipe state. It restarts dependencies if needed, waits for Postgres and RabbitMQ health checks, force-recreates `survival`, and then prints status.

## Map Crashes With Local Partition Is Not Found

Symptoms:

```text
LoadPartitionDefinition: Sql::load_world_partition(<map>, <new-server-id>, 0, <partition-id>) got 0 rows, expected exactly 1.
Fatal error: ... S2sController.cpp
Local partition is not found
```

Cause: the map process started with a fresh server id while its fixed `world_partition` row was still assigned to an older server id. If the old id is still in `active_server_ids`, `load_world_partition()` will not reassign the partition, so the game server cannot find its local partition and crashes.

Recover with the fixed-partition helper. For example, partition 18 is `heighliner-dungeon`:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/recover-map.sh .env heighliner-dungeon 18
```

Avoid repeatedly force-recreating the same map while the old server id is still active. That can reproduce the same crash loop.

For unattended recovery, run the map watchdog:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/watch-maps.sh .env
```

The watchdog intentionally does not use Docker's generic restart policy. It only handles `exited` or `dead` map containers and delegates to the fixed-partition recovery helper.

A systemd unit template is available at `config/systemd/dune-map-watchdog.service`, and `scripts/install-map-watchdog-service.sh .env` renders it for the current checkout. Keep only one watchdog instance running; the script also uses a lock directory to avoid duplicate host-side instances.

Use status mode to confirm the watched services:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' \
  ./scripts/watch-maps.sh .env --status
```

## Director Repeats Unassigned Partition Warnings

Symptoms:

```text
Battlegroup, consuming 4 partitions from database.
Error:Partition's ServerId is null or empty!
```

The bundled `initialize_partitions_basic_survival_1()` function creates four `Survival_1` dimensions. A one-container Compose test world only launches dimension 0, so dimensions 1-3 remain unassigned and Director keeps trying to process them.

For a one-server test world, run:

```bash
./scripts/single-survival-partition.sh .env
```

The script backs up `world_partition` state under `backups/partition-surgery/`, deletes only unassigned `Survival_1` dimensions greater than zero, and restarts Director plus Survival. Afterward, status should show one `world_partition` row and the game log should say `Server farm is READY (1 server(s))`.

## FLS Autologin Warning

Symptoms:

```text
LogGameSession: Warning: Autologin attempt failed, unable to register server!
LogFuncomLiveServices: Error: Setting 'GgwpApiKey' was not found
```

The current server image does not ship values for several optional `FuncomLiveServices_retail` keys. Do not invent these values locally. Treat the warning as non-fatal when Director FLS calls succeed, the gateway sees the server come up, and `Battlegroups_DeclareBattlegroupUpdates` includes the public game address.

## Voice Chat Token Generation Fails

Symptoms:

```text
GmeAuthTokenHandler failed token generation for PlayerId ... with VoiceChatId ... and RoomId ...
```

This warning comes from Director's voice-auth path. The server build calls the Tencent GME token generator from `BattlegroupDirector.GmeAuthToken.GmeAuthHandler`, and it returns no token when Director has no `[ GmeSettings ]` credentials.

Check the local config without printing secrets:

```bash
./scripts/check-gme-config.sh config/director.ini
```

Fix only when Funcom or the hosting provider gives you real GME voice credentials. Add them to `config/director.ini`, then recreate Director:

```ini
[ GmeSettings ]
GmeAppId=123456789
GmeAppKey="replace-with-provider-gme-key"
```

```bash
docker compose --env-file .env up -d --force-recreate director
```

Do not invent these values. Missing GME credentials affect voice-chat auth token generation; they are separate from world login, map travel, RabbitMQ game auth, and FLS registration.

## World Region With Spaces Breaks Startup

Use the Compose list-form command and `scripts/run_server_safe.sh`. The local wrapper preserves arguments such as `-FarmRegion=North America` through the final server exec.

## Permission Denied Under `data/postgres`

Postgres files are owned by the container user. This is normal. Avoid committing or manually editing `data/`.
