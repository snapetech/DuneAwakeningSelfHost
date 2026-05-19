# Dune Awakening Linux Host

Work-in-progress Linux/Compose harness for the Steam-installed Dune: Awakening self-hosted server package.

The goal is a reproducible Linux host layout that starts from Funcom's current container images but avoids the Hyper-V/k3s/operator wrapper where possible. This repository does not contain, mirror, or license any Funcom server binaries, container images, Steam package files, game assets, or secrets.

As of 2026-05-19, Steam exposes `Dune: Awakening Self-Hosted Server` as a released live tool, not only a PTC-only server package. Funcom's current live self-hosting FAQ still points token generation at `https://account-pts.duneawakening.com/`, but the proper live token generator is in the Dune: Awakening account portal at `https://account.duneawakening.com/`.

## Current State

- Steam package found at `$HOME/.local/share/Steam/steamapps/common/Dune Awakening Self-Hosted Server`
- Battlegroup image version: `1963158-0-shipping`
- Operator version in the package: `v1.5.0`
- Host has AVX2 and enough CPU for the server image
- Docker is installed and the Funcom images have been loaded locally
- Postgres, both RabbitMQ instances, gateway, and text-router start under Compose; FLS registration still needs a valid self-host token
- `Survival_1` reaches farm-ready with public address advertisement when `FLS_SECRET` and `EXTERNAL_ADDRESS` are set
- `rmq-auth-shim` is a local compatibility workaround for game-server S2S RabbitMQ users; keep RabbitMQ ports internal only

Adjust the path and image tag in `.env` for your install. The values above document the package version used during this teardown.

## Runtime Shape

The official package creates a Kubernetes `BattleGroup` custom resource. The useful workload pieces are:

- `igw-postgres`
- `server-rabbitmq` twice: admin queue and game queue
- `server-bg-director`
- `server-gateway`
- `server-text-router`
- `server` game map instances, with `Survival_1` and `Overmap` enabled by default
- `server-db-utils` for dump/import/DB operations

The first target here is Docker Compose parity for those pieces. After that, systemd units can wrap either Docker/Podman containers or native extracted binaries if that proves viable.

## Files

- `compose.yaml`: first-pass container topology.
- `.env.example`: required world/token/password settings.
- `docs/teardown.md`: notes extracted from the Steam install and image metadata.
- `docs/publication.md`: what is safe to publish and what must stay local.
- `docs/setup.md`: step-by-step local startup flow.
- `docs/architecture.md`: Compose service map and runtime state notes.
- `scripts/load-images.sh`: loads the Steam image tarballs into Docker.
- `scripts/inspect-images.sh`: prints entrypoints, env, ports, and volumes from the loaded images.
- `scripts/bootstrap_db.py`: one-shot Compose DB bootstrap using Funcom's bundled SQL setup API.
- `scripts/populate-local-env.sh`: generates local passwords/RabbitMQ secret and RabbitMQ TLS files.
- `scripts/rmq_auth_shim.py`: local RabbitMQ HTTP auth compatibility shim.
- `scripts/status.sh`: redacted status/log inspection helper.

## Requirements

- Linux host with Docker Compose.
- Official Dune: Awakening Self-Hosted Server Steam tool installed locally.
- A valid self-hosting/FLS token from Funcom's account flow.
- `openssl`, `jq`, and `rg` for the helper scripts.

## Quick Start

Generate local secrets, fill in the self-hosting token in `.env`, load the official images, then bootstrap the DB:

```bash
./scripts/populate-local-env.sh
./scripts/load-images.sh
docker compose --env-file .env up -d postgres admin-rmq game-rmq
docker compose --env-file .env run --rm db-init
```

Then bring up the service layer:

```bash
docker compose --env-file .env up -d rmq-auth-shim text-router gateway director
./scripts/status.sh
```

The `survival` service is present as an experimental direct game-server launch target:

```bash
docker compose --env-file .env up -d survival
```

Do not expect full gameplay until `FLS_SECRET` is set. The gateway/director/text-router path depends on that token for FLS registration; if the account page redirects to `/buy`, Funcom's entitlement service is not seeing the Steam ownership for the logged-in account.

Only forward the gameplay UDP ports from the router:

- `7777/udp`
- `7888/udp`

Do not forward RabbitMQ (`31982/tcp`) or the local debug/admin ports. Compose binds RabbitMQ and database debug ports to `127.0.0.1` where host publication is needed.

## Repository Boundaries

This repo is intended to contain only original orchestration, documentation, and local helper scripts. Keep these local and uncommitted:

- `.env`
- `data/`
- `config/tls/`
- Steam package contents
- Funcom container image tarballs
- logs, dumps, and generated runtime state

See `docs/publication.md` for the public-release checklist.

## Validation

Run the local validation target before pushing:

```bash
make validate
```

This checks the Compose config against `.env.example` and scans publishable files for obvious secret patterns.
