# Troubleshooting

Start with:

```bash
./scripts/preflight.sh
./scripts/status.sh
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

The shim is a local compatibility workaround for internal `sg.<world>.*`, `bgd.<world>.*`, and `tr.<world>.*` service users. Keep it paired with localhost-only RabbitMQ host bindings.

RabbitMQ auth cache TTL is intentionally long in `config/rabbitmq-admin.conf` and `config/rabbitmq-game.conf` to avoid hammering the HTTP auth path during 30-map warm-pool startup. Those config files are read by RabbitMQ at container start, so changing them requires a RabbitMQ restart during a maintenance window.

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

## Director Repeats Unassigned Partition Warnings

Symptoms:

```text
Battlegroup, consuming 4 partitions from database.
Error:Partition's ServerId is null or empty!
```

The bundled `initialize_partitions_basic_survival_1()` function creates four `Survival_1` dimensions. A one-container Compose test world only launches dimension 0, so dimensions 1-3 remain unassigned and Director keeps trying to process them.

For a one-server test world, run:

```bash
./scripts/single-survival-partition.sh
```

The script backs up `world_partition` state under `backups/partition-surgery/`, deletes only unassigned `Survival_1` dimensions greater than zero, and restarts Director plus Survival. Afterward, status should show one `world_partition` row and the game log should say `Server farm is READY (1 server(s))`.

## FLS Autologin Warning

Symptoms:

```text
LogGameSession: Warning: Autologin attempt failed, unable to register server!
LogFuncomLiveServices: Error: Setting 'GgwpApiKey' was not found
```

The current server image does not ship values for several optional `FuncomLiveServices_retail` keys. Do not invent these values locally. Treat the warning as non-fatal when Director FLS calls succeed, the gateway sees the server come up, and `Battlegroups_DeclareBattlegroupUpdates` includes the public game address.

## World Region With Spaces Breaks Startup

Use the Compose list-form command and `scripts/run_server_safe.sh`. The local wrapper preserves arguments such as `-FarmRegion=North America` through the final server exec.

## Permission Denied Under `data/postgres`

Postgres files are owned by the container user. This is normal. Avoid committing or manually editing `data/`.
