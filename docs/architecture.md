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
- `survival`: experimental direct launch of the game server image.

## Local State

Runtime state is intentionally outside git:

- `data/postgres`
- `data/rabbitmq`
- `data/server-saved`
- `config/tls`
- `.env`

## Network

Compose uses a fixed `172.31.240.0/24` subnet so the experimental game server can use a stable container IP for `POD_IP` and `-MultiHome` behavior.

## Current Blockers

- Full service registration depends on a valid `FLS_SECRET`.
- Direct game-server launch still needs parity with the operator-generated map arguments.
- Public UDP port behavior needs verification once the service layer registers cleanly.
