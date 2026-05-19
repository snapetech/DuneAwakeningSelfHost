# Steam Package Teardown

As of 2026-05-19, this teardown is based on the live Steam tool `Dune: Awakening Self-Hosted Server`, app ID `4754530`, not the older PTC-only package naming. Funcom's current self-hosting FAQ still links token generation through `https://account-pts.duneawakening.com/`, but the proper live token generator is in the Dune: Awakening account portal at `https://account.duneawakening.com/`.

Package path:

```text
$HOME/.local/share/Steam/steamapps/common/Dune Awakening Self-Hosted Server
```

Image tags loaded from the package:

```text
registry.funcom.com/funcom/self-hosting/seabass-server-bg-director:1963158-0-shipping
registry.funcom.com/funcom/self-hosting/seabass-server-db-utils:1963158-0-shipping
registry.funcom.com/funcom/self-hosting/seabass-server-gateway:1963158-0-shipping
registry.funcom.com/funcom/self-hosting/seabass-server-rabbitmq:1963158-0-shipping
registry.funcom.com/funcom/self-hosting/seabass-server-text-router:1963158-0-shipping
registry.funcom.com/funcom/self-hosting/seabass-server:1963158-0-shipping
registry.funcom.com/funcom/self-hosting/igw-postgres:17.4-alpine-fc-13
```

## Image Entrypoints

| Image | Entrypoint / Command | Workdir |
| --- | --- | --- |
| `seabass-server-rabbitmq` | `docker-entrypoint.sh rabbitmq-server` | `/` |
| `seabass-server-bg-director` | `./Director` | `/Tools/Battlegroups/Director/BattlegroupDirector` |
| `seabass-server-gateway` | `python -m service -c /Tools/Battlegroups/GatewayService/service/configs/service.conf` | `/Tools/Battlegroups/GatewayService/` |
| `seabass-server-text-router` | `./TextRouter` | `/Tools/Battlegroups/TextRouter/TextRouter` |
| `seabass-server-db-utils` | `python` | `/root/PSQL` |
| `seabass-server` | `/home/dune/run.sh` | `/home/dune/server/` |
| `igw-postgres` | `docker-entrypoint.sh postgres` | `/` |

## Official Default Workloads

The Funcom `world-template.yaml` enables these map server replicas by default:

- `Survival_1`: `replicas: 1`, memory limit `12Gi`
- `Overmap`: `replicas: 1`, memory limit `2Gi`

Most other maps are present but start at `replicas: 0`.

Game server base arguments:

```text
-FarmRegion={WORLD_REGION}
-ini:engine:[FuncomLiveServices]:ServiceAuthToken={FLS_SECRET}
-RMQGameTlsEnabled=true
--RMQGameHostname=<game queue>
--RMQGamePort=<game amqp port>
--RMQAdminHostname=<admin queue>
--RMQAdminPort=<admin amqp port>
```

`/home/dune/run.sh` rewrites `-MultiHome=$POD_IP`, appends `-IGWBindAddress=$POD_IP`, starts `DuneSandboxServer.sh`, then discovers the UDP game and IGW ports from `lsof`.

The Compose path uses `scripts/run_server_safe.sh` as a local replacement wrapper because list-form Compose arguments with spaces need to remain intact through the final `DuneSandboxServer.sh` exec.

## Compose Parity Notes

These are the items the k8s operators normally synthesize. The Compose topology now represents the required values explicitly in `compose.yaml`, local config files, or helper scripts:

- Postgres schema/database bootstrap using `server-db-utils` through the `db-init` service.
- RabbitMQ auth endpoint readiness through `text-router` plus the local `rmq-auth-shim`.
- TLS material for the game RabbitMQ under `config/tls/rabbitmq`.
- Database connection env/config for Director, Gateway, and TextRouter.
- Static game and IGW UDP port mapping per Compose service.

## Service-Layer Smoke Test Notes

With placeholder secrets, Postgres and both RabbitMQ instances start cleanly under Compose.

The first service-layer run showed:

- `TextRouter` requires `--RMQGameHostname` and `--RMQGamePort` launch arguments.
- `GatewayService` requires `DuneDatabaseInterfacePSQL_DatabaseHost` or equivalent config.
- `Director` defaults to `localhost:15431` unless a database config override is mounted.

Those values are now represented in `compose.yaml`.

`server-db-utils` exposes `initdb.py`, `updatedb.py`, and the SQL tree under `/root/DuneSandbox/Database`. The director is asking for database `dune_sb_1_4_0_0`, so `compose.yaml` includes a one-shot `db-init` service that runs:

```text
/root/PSQL/initdb.py --host postgres:5432 --project-database dune_sb_1_4_0_0 ...
```

After bootstrap, the branch database needs `search_path = dune, public` because the SQL setup creates functions such as `dune.update_universe_time`.

Current service-layer caveats:

- `director` reaches Postgres and RabbitMQ setup, then fails FLS initialization when `FLS_SECRET` is blank.
- The direct game-server launch path is functional for server-side registration, but client travel still needs live-client validation for each route.

The Compose path now generates equivalent local RabbitMQ TLS material under `config/tls/rabbitmq`:

- `ca.crt` -> mounted as `/etc/rabbitmq/cacert.pem`
- `server.crt` -> mounted as `/etc/rabbitmq/cert.pem`
- `server.key` -> mounted as `/etc/rabbitmq/key.pem`

This matches the paths in Funcom's `world-template.yaml`.

RabbitMQ also needs the plugins from the official `messageQueues.templates[].spec.plugins.system` list. Compose mounts `config/rabbitmq-enabled-plugins` to `/etc/rabbitmq/enabled_plugins` with:

```text
rabbitmq_management
rabbitmq_prometheus
rabbitmq_auth_backend_http
rabbitmq_auth_backend_cache
```

`server-gateway` expects `gateway_farm_api_key`. The official secret template includes an `fls-apikey` key, but using the placeholder reaches FLS and is rejected; Compose maps this to `FLS_SECRET` so the real self-host token is used once provided. The gateway also needs the operator-style `--RMQGameHostname/--RMQGamePort` launch args or it reports null RMQ addresses to FLS.

## Local RMQ Auth Shim

The official RabbitMQ HTTP auth backend points at TextRouter. In the Compose topology, Director and TextRouter service users authenticate cleanly, but game-server users shaped like:

```text
sg.<world>.<server-id>.game
sg.<world>.<server-id>.admin
```

were rejected by TextRouter with token timestamps of `01/01/0001`, while the game server still reached farm-ready. `scripts/rmq_auth_shim.py` is a local compatibility shim that forwards normal auth requests to TextRouter and explicitly allows those same-world `sg.*.game/admin` service users.

This is intentionally paired with localhost-only RabbitMQ publication. Do not expose `31982/tcp` publicly while this workaround is enabled.
