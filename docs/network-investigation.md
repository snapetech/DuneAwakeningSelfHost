# Network Investigation

This tracks connection-level behavior that may affect latency, routing, or resource use.

## Current Signals

`scripts/watch-network.sh` on the local stack showed:

- Gateway with many Postgres `TIME_WAIT` sockets.
- TextRouter with a Postgres `CLOSE_WAIT` socket.
- Director with stable Postgres and RabbitMQ established connections.
- Survival with stable Postgres and RabbitMQ established connections plus outbound HTTPS connections to external services.
- RabbitMQ instances with internal Erlang/RabbitMQ `TIME_WAIT` sockets.

## Interpretation

Gateway Postgres `TIME_WAIT` likely means it opens short-lived DB connections. This may be acceptable at low volume but should be watched under login and transition tests. If it grows with player count or transition attempts, the next target is connection pooling or service configuration, not kernel TCP tuning.

TextRouter `CLOSE_WAIT` means the remote side closed and TextRouter has not closed its local socket yet. One stale socket can be harmless; a growing count is a leak candidate.

RabbitMQ `TIME_WAIT` on `4369` and `25672` is probably Erlang distribution/epmd self-check behavior. It is noise unless it grows rapidly or correlates with CPU spikes.

## Commands

```bash
./scripts/watch-network.sh .env
```

For profile captures:

```bash
./scripts/profile-runtime.sh .env
./scripts/summarize-runtime-profile.sh captures/YYYYMMDDTHHMMSSZ-runtime-profile
```

## Optional Postgres Connection Logging

Add a temporary local override if gateway/TextRouter DB churn needs SQL-side timestamps:

```yaml
services:
  postgres:
    command:
      - postgres
      - -c
      - log_connections=on
      - -c
      - log_disconnections=on
```

Do not leave connection logging enabled during normal play. It can produce noisy logs and may expose client addresses or operational timing.
