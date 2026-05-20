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

Backups are written under:

```text
backups/<UTC timestamp>/
```

Restore with:

```bash
./scripts/restore-state.sh .env backups/<UTC timestamp>
```

Restores are disruptive. Stop game/admin writers first.

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
