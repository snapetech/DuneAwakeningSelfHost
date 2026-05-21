# Operational Identity Handoff

Confidence: high.

This runbook covers the DASH-native operational work borrowed from AMP research: FLS environment handling, durable world identity, RabbitMQ TLS identity, backup identity layers, and redacted handoff artifacts.

## Durable Identity

`WORLD_UNIQUE_NAME` is the durable FLS battlegroup identity. After first successful registration, do not rotate it for the same world. Back up `.env` with database, RabbitMQ, saved-state, config, and TLS material.

Use `DUNE_FLS_ENV=retail` for normal live servers. Non-retail values such as `beta`, `test`, `ptc`, or `staging` should only be used with a matching server build and token authorization.

## Read-Only Checks

Run these before startup, migration, or handoff:

```bash
./scripts/bootstrap-checklist.sh .env
make operational-identity-check ENV_FILE=.env
./scripts/preflight.sh .env
```

`operational-identity-check` does not require running services. It checks:

- `WORLD_UNIQUE_NAME` is not an example placeholder.
- `DUNE_FLS_ENV` is known or intentionally non-retail.
- Rendered Compose passes the FLS environment to the game-server command and service layer.
- RabbitMQ certificate SANs cover expected names.
- Backup identity dry-run succeeds.

## RabbitMQ TLS

Inspect the client-facing game RabbitMQ certificate:

```bash
make rabbitmq-cert-check ENV_FILE=.env
```

Generate TLS only for first setup or planned maintenance:

```bash
make rabbitmq-cert-generate ENV_FILE=.env
```

The generator refuses to overwrite existing TLS files unless called directly with `--force`:

```bash
cp -a config/tls/rabbitmq "config/tls/rabbitmq.backup.$(date -u +%Y%m%dT%H%M%SZ)"
./scripts/generate-rabbitmq-cert.sh .env --force
./scripts/check-rabbitmq-cert-sans.sh .env
```

Recreate `game-rmq`, `gateway`, `director`, `text-router`, and game-server containers after deliberate certificate replacement.

## Backup And Restore Identity Layers

Plan the local backup without touching Docker:

```bash
make backup-dry-run ENV_FILE=.env
```

Create and verify the backup:

```bash
make backup-state ENV_FILE=.env
make verify-backup BACKUP_DIR=backups/<backup-id>
```

Backups include:

- Postgres dump.
- RabbitMQ archives when brokers are running.
- Saved-state archive when available.
- Env file copy.
- `config.tgz`.
- `config-tls.tgz`.
- Manifest fields for `WORLD_UNIQUE_NAME`, `DUNE_FLS_ENV`, and `GAME_RMQ_PUBLIC_HOST`.

Plan restore before replacing state:

```bash
make restore-dry-run ENV_FILE=.env BACKUP_DIR=backups/<backup-id>
make restore-dry-run ENV_FILE=.env BACKUP_DIR=backups/<backup-id> RESTORE_FLAGS='--rabbitmq --server-saved --config --tls'
```

If backup and current `WORLD_UNIQUE_NAME` differ, restore dry-run warns because the value controls the FLS battlegroup identity.

## Redacted Handoff Artifacts

Create a redacted report:

```bash
make operational-report ENV_FILE=.env
```

Create and verify a portable bundle:

```bash
make operational-bundle ENV_FILE=.env
make verify-operational-bundle BUNDLE_FILE=backups/<operational-bundle>.tgz
```

The bundle contains:

- `operational-report.txt`
- `operational-identity-check.txt`
- `backup-dry-run.txt`
- `compose-summary.txt`
- `manifest.txt`

It does not contain `.env`, TLS keys, database dumps, RabbitMQ state, or raw Compose output. The verifier checks expected files, forbidden file types, obvious secret patterns, and manifest exclusion markers.

## AMP Boundary

AMP was used as a reference source only. DASH reimplements useful operational lessons in Compose, scripts, tests, and docs. AMP public templates do not verify GM, teleport, item grant, or kick payload execution; that research remains separate in `docs/admin-gm-console.md`.
