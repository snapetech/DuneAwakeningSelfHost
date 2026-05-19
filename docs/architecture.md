# Architecture

The official self-hosted package is Kubernetes-oriented. This repository translates the useful pieces into a Docker Compose topology for local experimentation.

## Services

- `postgres`: Funcom's Postgres image with local persistent data.
- `admin-rmq`: admin RabbitMQ queue.
- `game-rmq`: game RabbitMQ queue with local TLS.
- `rmq-auth-shim`: local HTTP auth shim for RabbitMQ service users.
- `db-init`: one-shot database setup using Funcom's bundled DB utility image.
- `director`: battlegroup director service.
- `text-router`: text/auth routing service.
- `gateway`: gateway service.
- `survival`: `Survival_1`, the Hagga Basin starting map.
- `overmap`: `Overmap`, the overland travel map.
- `arrakeen`: `SH_Arrakeen`, the Arrakeen social hub.
- `harko-village`: `SH_HarkoVillage`, the Harko Village social hub.
- `testing-hephaestus`: `CB_Story_Hephaestus`.
- `testing-carthag`: `CB_Story_Ecolab_Carthag`.
- `testing-waterfat`: `CB_Story_WaterFatManor`.
- `deep-desert`: `DeepDesert_1`.
- `proces-verbal`: `Story_ProcesVerbal`.

The game-server services use `scripts/run_server_safe.sh` instead of the image's default `/home/dune/run.sh`. The local launcher preserves command arguments containing spaces, prepares the saved/config symlink expected by Unreal, appends `-IGWBindAddress=$POD_IP`, and then starts `DuneSandboxServer.sh` as the `dune` user.

## Partition Layout

The expanded standing farm uses one partition per launched map. See `docs/full-farm.md` for the full table of service names, map names, partition ids, and ports.

## Local State

Runtime state is intentionally outside git:

- `data/postgres`
- `data/rabbitmq`
- `data/server-saved`
- `config/tls`
- `.env`

## Network

Compose uses a fixed `172.31.240.0/24` subnet so each game-server container can use a stable container IP for `POD_IP` and `-MultiHome` behavior.

Only RabbitMQ and Postgres debug/admin ports bind to `127.0.0.1`. Game UDP ports bind on the host so the router can forward them.

## Validation Boundary

- Server-side full-farm registration is proven when status reports `farm_ready_alive=9 active_servers=9 partitions=9`.
- Client login and travel between maps still need live game-client validation.
- The live token in `.env` is sensitive and should be rotated if it was exposed outside the host.
