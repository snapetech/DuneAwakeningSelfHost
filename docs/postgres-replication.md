# Postgres Streaming Replica

This repo can run optional hot standby Postgres containers for near-realtime
physical streaming replication of the Dune database volume. A same-host standby
is useful for read-only dumps and primary-container failures. A remote standby is
the useful layer for host/disk failure.

This is not a replacement for point-in-time backups. A streaming replica quickly
copies good writes, bad writes, deletes, corruption, and schema migrations. Keep
`scripts/backup-state.sh` or admin-panel dumps for recoverable snapshots.

## Enable

Fresh `.env` files created by `scripts/populate-local-env.sh` already get a
random `POSTGRES_REPLICATION_PASSWORD`. If you maintain `.env` by hand, add a
strong replication password:

```sh
POSTGRES_REPLICATION_USER=dune_replicator
POSTGRES_REPLICATION_PASSWORD=<strong unique password>
POSTGRES_REPLICATION_SLOT=dune_standby
POSTGRES_REPLICA_HOST_PORT=15433
```

Initialize the primary replication role/HBA rule and start the standby:

```sh
COMPOSE_FILES=compose.yaml:compose.replica.yaml ./scripts/setup-postgres-replica.sh .env
```

The setup script:

- starts the primary `postgres` service if needed;
- creates or updates `POSTGRES_REPLICATION_USER`;
- creates the physical replication slot named by `POSTGRES_REPLICATION_SLOT`;
- appends a `pg_hba.conf` replication rule on the primary and reloads Postgres;
- starts `postgres-replica`, which runs `pg_basebackup` into `data/postgres-replica` on first boot.

## Remote Replica

For host-level redundancy, run the standby on another LAN host. The primary host
can expose a replication-only LAN forwarder without recreating the live Postgres
container:

```sh
POSTGRES_REPLICATION_BIND_ADDRESS=<primary-lan-ip>
POSTGRES_REPLICATION_ALLOWED_ADDRESS=<remote-lan-ip>
POSTGRES_REPLICATION_PRIMARY_HOST=<primary-lan-ip>
POSTGRES_REPLICATION_PUBLIC_PORT=15434
POSTGRES_REMOTE_REPLICATION_SLOT=dune_standby_remote
POSTGRES_REMOTE_REPLICA_HOST=replica.example.lan
POSTGRES_REMOTE_REPLICA_ROOT=/srv/dune-postgres-replica
```

Install the primary-side forwarder:

```sh
./scripts/install-postgres-lan-forwarder.sh .env
```

`POSTGRES_REPLICATION_ALLOWED_ADDRESS` limits the forwarder to the remote replica
host before Postgres authentication is reached. Keep this port on a private LAN
or VPN only.

Install the remote standby. This script copies the Postgres image to the remote
host if missing, creates a dedicated physical replication slot, and runs the
remote container with Docker:

```sh
./scripts/install-remote-postgres-replica.sh .env replica.example.lan /srv/dune-postgres-replica
```

The remote host needs SSH access and Docker. It does not need Docker Compose.
The standby data lives under the remote root's `data/` directory.

After the first run, include the overlay whenever managing the stack:

```sh
docker compose --env-file .env -f compose.yaml -f compose.replica.yaml ps
docker compose --env-file .env -f compose.yaml -f compose.replica.yaml up -d postgres-replica
```

If you use `COMPOSE_FILES` for the all-maps overlay, include all overlays:

```sh
COMPOSE_FILES=compose.yaml:compose.allmaps.yaml:compose.replica.yaml ./scripts/status.sh .env
```

## Check Status

One command checks the current three-layer posture:

```sh
./scripts/backup-layers-status.sh .env replica.example.lan /srv/dune-postgres-replica
```

It reports the remote replication slot, standby recovery state, latest rolling
snapshots, recent full-state backups, and the systemd timer/forwarder state.

On the primary:

```sh
docker compose --env-file .env -f compose.yaml -f compose.replica.yaml exec -T postgres \
  psql -U dune -d dune_sb_1_4_0_0 -c \
  "select application_name,state,sync_state,write_lag,flush_lag,replay_lag from pg_stat_replication;"
```

On the replica:

```sh
docker compose --env-file .env -f compose.yaml -f compose.replica.yaml exec -T postgres-replica \
  psql -U dune -d dune_sb_1_4_0_0 -c \
  "select pg_is_in_recovery(), now() - pg_last_xact_replay_timestamp() as replay_delay;"
```

## Use For Backups

Read-only logical dumps can be taken from the replica without adding dump load to
the primary:

```sh
mkdir -p backups
docker compose --env-file .env -f compose.yaml -f compose.replica.yaml exec -T postgres-replica \
  pg_dump -U dune -d dune_sb_1_4_0_0 -Fc \
  > backups/dune-replica-$(date -u +%Y%m%dT%H%M%SZ).dump
```

The existing `scripts/backup-state.sh` still dumps from the primary. Use the
manual replica dump above when you specifically want to avoid primary dump load.
RabbitMQ and `data/server-saved` archives are not covered by Postgres streaming
replication.

For remote hourly snapshots from the remote standby:

```sh
./scripts/replica-snapshot.sh .env replica.example.lan /srv/dune-postgres-replica
./scripts/install-replica-snapshot-timer.sh .env replica.example.lan /srv/dune-postgres-replica
```

The timer runs hourly and keeps `DUNE_REPLICA_SNAPSHOT_KEEP_HOURS` hours of
remote dumps. The default is 48 hours. Dumps are written on the remote host under
`/srv/dune-postgres-replica/snapshots` when using the example path.

## Restore And Failover

Routine restore still uses `scripts/restore-state.sh` and is disruptive. After
restoring the primary from a dump, rebuild the standby so it matches the new
timeline and contents:

```sh
docker compose --env-file .env -f compose.yaml -f compose.replica.yaml stop postgres-replica
rm -rf data/postgres-replica
COMPOSE_FILES=compose.yaml:compose.replica.yaml ./scripts/setup-postgres-replica.sh .env
```

Promotion is only for disaster recovery. If you promote the replica while the
original primary can still accept writes, you can split-brain the database. A
full failover runbook should stop all game/admin writers first, promote the
replica, repoint services to the promoted database, and rebuild a new standby
from the promoted primary.

## Failure Notes

- If the replica is stopped for too long, the physical replication slot can hold
  WAL on the primary. Monitor disk usage under `data/postgres/pg_wal`.
- If the replica falls unrecoverably behind, stop it, remove
  `data/postgres-replica`, then rerun `scripts/setup-postgres-replica.sh`.
- Promotion is a disaster-recovery operation. Do not promote the replica while
  the original primary can still accept writes unless you are intentionally
  failing over.
