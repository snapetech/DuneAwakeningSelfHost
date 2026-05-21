# Operator Handoff

Use this when moving DASH to another operator, another host, or a published setup guide. It is intentionally practical: what the next operator needs, what must stay private, and what to verify before calling the server ready.

## Handoff Package

Share:

- Repository URL and target branch/tag.
- Release notes based on [`docs/release-template.md`](docs/release-template.md).
- Official Steam tool install instructions.
- Required public ports for the selected layout.
- Private `.env` values through a secret channel, not git.
- Backup/restore location and retention policy.
- Admin panel LAN/VPN URL.
- Expected health target, for example `current_alive_active=30 active_servers=30 partitions=30`.

Do not share:

- Funcom image tarballs or Steam package files.
- `.env` in chat, tickets, screenshots, or git.
- `data/`, `backups/`, `config/tls/`, runtime logs, dumps, or player data.
- Cloud backup credentials, SSH private keys, restic passwords, or rclone configs.

Generate a publishable-file manifest for review:

```bash
./scripts/package-manifest.sh /tmp/dash-package-manifest.md
```

## New Host Checklist

1. Install Docker Engine and Compose plugin.
2. Install helper tools:

```bash
jq --version
rg --version
openssl version
```

3. Clone the repo:

```bash
git clone <repo-url> DuneAwakeningSelfHost
cd DuneAwakeningSelfHost
```

4. Generate local env and TLS:

```bash
./scripts/populate-local-env.sh
```

5. Copy relevant example values into `.env`:

```text
examples/env/home-lab-single-map.env
examples/env/full-warm-pool.env
examples/env/lan-vpn-admin.env
```

6. Fill the real private values in `.env`:

```text
DUNE_STEAM_SERVER_DIR
DUNE_IMAGE_TAG
WORLD_NAME
WORLD_UNIQUE_NAME
FLS_SECRET
EXTERNAL_ADDRESS
GAME_RMQ_PUBLIC_HOST
DUNE_ADMIN_TOKEN
```

Treat `WORLD_UNIQUE_NAME` as the durable FLS battlegroup identity. It must move with the database/RabbitMQ state during host migration unless the operator deliberately wants a different world registration.

7. Run preflight:

```bash
./scripts/bootstrap-checklist.sh .env
make operational-identity-check ENV_FILE=.env
make operational-report ENV_FILE=.env
make operational-bundle ENV_FILE=.env
make verify-operational-bundle BUNDLE_FILE=backups/<operational-bundle>.tgz
./scripts/preflight.sh
```

The operational report is written under `backups/` by default and redacts token values while preserving identity, FLS environment, RabbitMQ TLS, backup dry-run, and Compose-render status.
The operational bundle packages that report with identity-check output, backup dry-run output, a redacted Compose service summary, and a manifest. It does not include `.env`, TLS keys, Postgres dumps, RabbitMQ data, or raw Compose output.

8. Load official images from the Steam package:

```bash
./scripts/load-images.sh .env
```

9. Bootstrap and start according to [`docs/setup.md`](docs/setup.md).

## Backup Handoff

Pick one primary backup path before going live:

| Target | Example Config | Use When |
| --- | --- | --- |
| Local only | inline `DUNE_BACKUP_OFFSITE_MODE=none` | Lab or first boot only. |
| NAS/SSH | `examples/backup/rsync-nas.env` | Onsite backup host exists. |
| Cloud/object store | `examples/backup/rclone-offsite.env` | rclone remote is already configured. |
| Encrypted repository | `examples/backup/restic.env` | You want encrypted snapshots and retention. |

Manual smoke test:

```bash
DUNE_BACKUP_OFFSITE_MODE=none ./scripts/backup-offsite.sh .env
./scripts/verify-backup.sh backups/<new-backup-id>
```

Confirm the backup contains the env/config identity layers before going live:

```bash
tar -tzf backups/<new-backup-id>/config.tgz >/dev/null
tar -tzf backups/<new-backup-id>/config-tls.tgz >/dev/null
rg '^world_unique_name=' backups/<new-backup-id>/manifest.txt
```

Install timer after the chosen remote mode works manually:

```bash
./scripts/install-backup-offsite-timer.sh .env examples/backup/rclone-offsite.env
```

Install the daily 06:00 restart/backup/update maintenance timer after the admin panel restart path works manually:

```bash
./scripts/install-daily-maintenance-timer.sh .env
```

## Readiness Criteria

Before announcing the server as ready:

```bash
./scripts/status.sh .env
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
./scripts/verify-rmq-auth-path.sh
```

For the 30-map warm pool, expect:

```text
current_alive_active=30 active_servers=30 partitions=30
```

Also verify:

- Admin panel opens only from the intended LAN/VPN path.
- Public UDP game ports are forwarded for the selected layout.
- `GAME_RMQ_PUBLIC_PORT` TCP is reachable from a player machine.
- LAN clients can join through public listing, or LAN reflection is configured.
- A local backup exists and passes `scripts/verify-backup.sh`.
- Offsite/onsite sync has a recent successful log under `backups/offsite-logs`.

## Incident Notes

If the next operator reports that maps are online in the database but client joins fail, check in this order:

1. Public address and router/NAT.
2. `GAME_RMQ_PUBLIC_HOST` and `GAME_RMQ_PUBLIC_PORT`.
3. Game RabbitMQ auth path:

```bash
./scripts/verify-rmq-auth-path.sh
```

4. Docker bridge neighbor refresh:

```bash
./scripts/seed-gateway-neighbor.sh
```

5. Current world partition health:

```bash
./scripts/status.sh .env
```
