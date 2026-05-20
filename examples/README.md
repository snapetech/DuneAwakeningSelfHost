# Examples

These files are starting points for other operators. They are not complete private configurations.

## Env Overlays

- `env/home-lab-single-map.env`: conservative single-map defaults.
- `env/full-warm-pool.env`: 30-partition warm-pool defaults.
- `env/lan-vpn-admin.env`: private admin panel hostname and port pattern.

Copy values from these into `.env`. Do not replace `.env.example` with one of these partial files.

## Backups

- `backup/rclone-offsite.env`: cloud/object sync through rclone.
- `backup/rsync-nas.env`: onsite NAS or backup host over SSH.
- `backup/restic.env`: encrypted restic repository.

Test manually before installing a timer:

```bash
DUNE_BACKUP_REMOTE_ENV=examples/backup/rclone-offsite.env ./scripts/backup-offsite.sh .env
```

## Ingress

- `ingress/caddy-admin.example`
- `ingress/nginx-admin.example`

Keep the admin panel on trusted LAN/VPN only. Do not publish it to the internet.

## Firewall

- `firewall/ufw-single-map.sh`
- `firewall/ufw-full-warm-pool.sh`
- `firewall/firewalld-full-warm-pool.sh`

Review before running. These examples expose game traffic only, not the admin panel or database services.
