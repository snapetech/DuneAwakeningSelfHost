# Backup Strategy

Use layered backups. No single backup mechanism covers every failure mode.

## Layers

| Layer | Protects Against | Does Not Protect Against |
| --- | --- | --- |
| Local stopped-world backup | Bad config edits, failed upgrades, admin mistakes noticed quickly | Host loss, disk loss, old unnoticed corruption |
| Local Postgres streaming replica | Primary Postgres container/volume failure, read-only dump load | Deletes, bad writes, host loss when same disk/host |
| Remote Postgres replica | Host loss, primary disk loss, read-only off-host dumps | Deletes and bad writes that replicate |
| Offsite object/NAS backup | Fire/theft/site loss, rollback to older snapshots | Very recent writes unless schedule is tight |
| Manual pre-change backup | Known restore point before risky work | Problems that predate the backup |

The maintenance restart flow creates an authoritative local maintenance backup before it checks the Steam package for updated Funcom image tarballs and starts services again. That backup includes a Postgres dump, config/env archive, RabbitMQ archives, server saved data, and a manifest. See [`docs/maintenance-updates.md`](maintenance-updates.md).

## Local Backup

Run:

```bash
./scripts/backup-state.sh .env
```

Before a maintenance window, check what identity/config layers will be captured without contacting Docker:

```bash
./scripts/backup-state.sh --dry-run .env
```

Equivalent Make targets:

```bash
make backup-dry-run ENV_FILE=.env
make backup-state ENV_FILE=.env
make verify-backup BACKUP_DIR=backups/<UTC timestamp>
make restore-dry-run ENV_FILE=.env BACKUP_DIR=backups/<UTC timestamp>
make operational-report ENV_FILE=.env
make operational-bundle ENV_FILE=.env
```

Backups are written under:

```text
backups/<UTC timestamp>/
```

The local backup includes:

- Postgres custom-format dump.
- RabbitMQ state archives when brokers are running.
- Server saved-state archive when available.
- A copy of the env file used for the backup.
- `config.tgz` for committed/local config files, excluding TLS key material.
- `config-tls.tgz` for RabbitMQ TLS material under `config/tls/`.
- `manifest.txt` with `WORLD_UNIQUE_NAME`, `DUNE_FLS_ENV`, and `GAME_RMQ_PUBLIC_HOST`.

Restore with:

```bash
./scripts/restore-state.sh .env backups/<UTC timestamp>
```

Restores are disruptive. Stop game/admin writers first.
RabbitMQ, saved-state, config, and TLS replacement are opt-in:

```bash
./scripts/restore-state.sh --rabbitmq --server-saved --config --tls .env backups/<UTC timestamp>
```

Run `--dry-run` first. If the manifest `WORLD_UNIQUE_NAME` differs from the current `.env`, restore will warn because that value is the durable FLS battlegroup identity.

The equivalent Make target accepts optional restore layer flags:

```bash
make restore-dry-run ENV_FILE=.env BACKUP_DIR=backups/<UTC timestamp> RESTORE_FLAGS='--rabbitmq --server-saved --config --tls'
```

## Offsite and Onsite Sync

Use `scripts/backup-offsite.sh` to create a local backup and then sync `backups/` to another destination.

Dry local-only run:

```bash
DUNE_BACKUP_OFFSITE_MODE=none ./scripts/backup-offsite.sh .env
```

rclone example:

```bash
DUNE_BACKUP_REMOTE_ENV=examples/backup/rclone-offsite.env ./scripts/backup-offsite.sh .env
```

rsync/NAS example:

```bash
DUNE_BACKUP_REMOTE_ENV=examples/backup/rsync-nas.env ./scripts/backup-offsite.sh .env
```

restic example:

```bash
DUNE_BACKUP_REMOTE_ENV=examples/backup/restic.env ./scripts/backup-offsite.sh .env
```

Install an hourly systemd timer:

```bash
./scripts/install-backup-offsite-timer.sh .env examples/backup/rclone-offsite.env
systemctl list-timers dune-backup-offsite.timer --all --no-pager
```

The examples intentionally use placeholder destinations. Configure credentials with each tool's normal private config:

- rclone remotes in the operator user's rclone config.
- SSH keys for rsync.
- `RESTIC_PASSWORD_FILE` or a private secret manager for restic.

Do not put cloud tokens, SSH private keys, restic passwords, or provider credentials in this repo.

## Remote Postgres Replica

For a hot standby on another LAN host:

```bash
./scripts/install-postgres-lan-forwarder.sh .env
./scripts/install-remote-postgres-replica.sh .env replica.example.lan /srv/dune-postgres-replica
./scripts/install-replica-snapshot-timer.sh .env replica.example.lan /srv/dune-postgres-replica
```

The snapshot timer runs as the installing local user by default so SSH uses that
user's keys and host aliases. Set `DUNE_REPLICA_SNAPSHOT_USER` and
`DUNE_REPLICA_SNAPSHOT_GROUP` before installation only when another local
account owns the remote replica SSH credentials.

Check the layers:

```bash
./scripts/backup-layers-status.sh .env replica.example.lan /srv/dune-postgres-replica
```

See [`docs/postgres-replication.md`](docs/postgres-replication.md).

## Suggested Schedules

Small/private host:

- Local backup before upgrades and config changes.
- Daily offsite sync.
- Weekly restore test.

Public 30-map host:

- Maintenance backup before scheduled restart, followed by the Steam package image-tag check.
- Hourly offsite sync or restic backup.
- Remote Postgres replica with hourly snapshot.
- Weekly restore test to a throwaway environment.
- Alert when newest local/offsite backup is older than 24 hours.

## Restore Testing

A backup that has never been restored is only a guess. At minimum:

```bash
./scripts/verify-backup.sh backups/<id>
```

For maintenance backups:

```bash
backup=backups/admin-panel/maintenance/<id>
./scripts/verify-backup.sh "$backup"
```

For offsite backups, periodically restore to a temporary directory from the remote provider and run the same checks there.

## Retention

Reasonable starting points:

- Keep local backups for 3-7 days.
- Keep offsite daily snapshots for 14-30 days.
- Keep weekly snapshots for 2-3 months.
- Keep monthly snapshots only if storage cost is acceptable.

Tune retention to player count, upgrade frequency, storage cost, and how long it usually takes you to notice data damage.
