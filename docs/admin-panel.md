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

The panel uses `X-Admin-Token` for protected APIs. The browser stores the token in session storage when entered in the header.

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
- Redacted JSONL audit trail for rejected requests and admin writes under `backups/admin-panel/audit.jsonl`.
- Read-only observed item template reference for future gear grant mapping.
- Experimental exact-template item grants behind a separate opt-in flag.

## Write Safety

Mutation endpoints are disabled unless:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
```

Current mutation support is intentionally narrow:

- Currency balance add/set through `dune.player_virtual_currency_balances`.
- Specialization XP add/set through existing `dune.specialization_tracks` rows.
- Database backup through `pg_dump -Fc`.
- Experimental item grants through `dune.save_item(dune.inventoryitem)` when `DUNE_ADMIN_ITEM_GRANTS_ENABLED=true`.

Item grants require an exact server `template_id` and a target inventory ID. Public databases such as `https://dune.gaming.tools/items` expose item pages whose URL slugs look like server-style template IDs, but verify against observed local server data before bulk grants.

Recipe unlocks are not implemented yet. Those need validated unlock tables and server refresh semantics before writes are safe.

See `docs/admin-mutation-map.md` for the current DB contract map.

Back up before enabling mutations:

```bash
./scripts/backup-state.sh
```

## Security Notes

- Do not expose this service to the public internet.
- Use a long random `DUNE_ADMIN_TOKEN`.
- Keep `DUNE_ADMIN_MUTATIONS_ENABLED=false` unless actively making admin edits.
- `DUNE_ADMIN_ITEM_GRANTS_ENABLED` defaults to `true` in this repo; leave it enabled only on trusted LAN/VPN deployments and keep general mutations gated with `DUNE_ADMIN_MUTATIONS_ENABLED`.
- Keep `DUNE_ADMIN_MAX_BODY_BYTES` small unless editing unusually large config files; the default is `65536`.
- Set `DUNE_ADMIN_ALLOWED_HOSTS` to the exact hostnames used to reach the panel, for example `127.0.0.1:18080,localhost:18080,duneadmin.home`.
- Review the Security tab's recent audit events after failed login attempts, blocked host/origin requests, config edits, backups, or mutation runs.
- Restart affected game services after config changes when the target service does not hot-reload.
