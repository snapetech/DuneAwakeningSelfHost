# Admin Panel

The admin helper panel is a LAN-only web UI for local server operators. It is not exposed publicly by default.

## Start

Set a strong token in `.env`:

```env
DUNE_ADMIN_TOKEN=replace-with-a-long-random-token
DUNE_ADMIN_MUTATIONS_ENABLED=false
```

Start the service:

```bash
docker compose --env-file .env up -d admin-panel
```

Open:

```text
http://127.0.0.1:18080
```

The panel uses `X-Admin-Token` for write operations. The browser stores the token in local storage when entered in the header.

## `duneadmin.home`

The Compose service binds to localhost:

```text
127.0.0.1:18080 -> admin-panel:8080
```

To use `http://duneadmin.home`, point local DNS or `/etc/hosts` at the host running a reverse proxy. Keep it on trusted LAN/VPN only.

Example nginx site:

```nginx
server {
    listen 80;
    server_name duneadmin.home;

    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Current Features

- Server/farm state view.
- Character search and detail view.
- Currency/progression table visibility.
- Safe `.env` key editor for non-secret world settings.
- Config editor for selected local config files, with backups under `backups/admin-panel`.
- Token-gated currency and XP mutation endpoints.
- Token-gated Postgres custom-format backup under `backups/admin-panel`.
- Read-only observed item template reference for future gear grant mapping.

## Write Safety

Mutation endpoints are disabled unless:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
```

Current mutation support is intentionally narrow:

- Currency balance add/set through `dune.player_virtual_currency_balances`.
- Specialization XP add/set through existing `dune.specialization_tracks` rows.
- Database backup through `pg_dump -Fc`.

Gear grants, skill unlocks, recipes, and item insertion are not implemented yet. Those need validated template IDs, inventory ownership rules, uniqueness behavior, and server refresh semantics before writes are safe.

Back up before enabling mutations:

```bash
./scripts/backup-state.sh
```

## Security Notes

- Do not expose this service to the public internet.
- Use a long random `DUNE_ADMIN_TOKEN`.
- Keep `DUNE_ADMIN_MUTATIONS_ENABLED=false` unless actively making admin edits.
- Restart affected game services after config changes when the target service does not hot-reload.
