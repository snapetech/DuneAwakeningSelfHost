# Steam Package Teardown

As of 2026-05-19, this teardown is based on the live Steam tool `Dune: Awakening Self-Hosted Server`, app ID `4754530`, not the older PTC-only package naming. Funcom's current self-hosting FAQ still links token generation through `https://account-pts.duneawakening.com/`, so `account-pts` remains part of the live token flow for now.

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

## Known Missing Pieces

These are the items the k8s operators normally synthesize and still need to be reproduced:

- Postgres schema/database bootstrap using `server-db-utils`.
- RabbitMQ auth endpoint readiness through `text-router`.
- TLS material for the game RabbitMQ if strict TLS is required outside k8s.
- Exact database connection env/config expected by director, gateway, and text-router.
- Public port mapping after the game process dynamically chooses its UDP game and IGW ports.

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

Current service-layer blockers:

- `director` reaches Postgres and RabbitMQ setup, then fails FLS initialization when `FLS_SECRET` is blank.
- exact game-server map launch arguments still need to be reproduced from the server operator before starting `seabass-server` directly.

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
