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

## LAN Hostname

The Compose service binds to localhost:

```text
127.0.0.1:18080 -> admin-panel:8080
```

To use a LAN hostname such as `http://admin.example.test`, point LAN DNS or `/etc/hosts` at the host running the reverse proxy:

```text
admin.example.test -> <your-server-lan-ip>
```

Keep it on trusted LAN/VPN only. The panel still runs behind the local ingress and should not be exposed directly to the internet.

Example nginx site:

```nginx
server {
    listen 80;
    server_name admin.example.test;

    location / {
        proxy_pass http://127.0.0.1:18080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Current Features

- Server/farm state view with per-map online/offline health derived from `world_partition`, `farm_state`, and `active_server_ids`.
- Local/upstream health checks for Postgres reachability, the Dune account portal, and public Dune/Funcom HTTP reachability.
- Character search and detail view.
- Currency/progression table visibility.
- `.env` operations editor for install, world, network, access, secret, and admin-panel knobs. Secret fields are admin-token protected, rendered as password inputs, and returned blank unless a replacement is typed.
- Typed Director character-transfer settings editor for `config/director.ini`.
- Config editor for selected local config files, including official `UserEngine.ini` and `UserGame.ini` overlays, with backups under `backups/admin-panel`.
- Token-gated currency and XP mutation endpoints.
- Token-gated Postgres custom-format backup under `backups/admin-panel`.
- Redacted JSONL audit trail for rejected requests and admin writes under `backups/admin-panel/audit.jsonl`.
- Known item template, observed item template, inventory, and inventory-type references.
- Character dropdowns in Admin Actions for currency, XP, keystones, item grant targeting, and item maintenance.
- Selected characters pre-populate controller/account/name fields, current currency and specialization selectors, owned inventories, and owned inventory items for stack edits or deletion.
- Exact-template item grants, dry-runs, stack edits, and item deletion behind admin gates.

## Write Safety

Mutation endpoints are disabled unless:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
```

Current mutation support is intentionally narrow:

- Currency balance add/set through `dune.player_virtual_currency_balances`.
- Specialization XP add/set through existing `dune.specialization_tracks` rows.
- Database backup through `pg_dump -Fc`.
- Item grants through `dune.save_item(dune.inventoryitem)` when `DUNE_ADMIN_ITEM_GRANTS_ENABLED=true`.
- Item grant dry-runs that resolve the target inventory and warnings without requiring `DUNE_ADMIN_MUTATIONS_ENABLED=true`.
- Item stack changes and item/count deletion through the server's existing item functions.

Item grants require an exact server `template_id`. You can enter an inventory ID directly, or let the panel resolve a player-owned inventory from account ID or character name. The mutation page now offers exact local template IDs from item, Landsraad reward, vendor, vehicle, and exchange tables. Public databases such as `https://dune.gaming.tools/items` and `https://dune.geno.gg/items/` are still useful for names and research, but dry-run and verify against local server data before bulk grants.

Recipe unlocks are not implemented yet. Those need validated unlock tables and server refresh semantics before writes are safe.

See `docs/admin-mutation-map.md` for the current DB contract map.

Back up before enabling mutations:

```bash
./scripts/backup-state.sh .env
```

## Security Notes

- Do not expose this service to the public internet.
- Use a long random `DUNE_ADMIN_TOKEN`.
- Keep `DUNE_ADMIN_MUTATIONS_ENABLED=false` unless actively making admin edits.
- `DUNE_ADMIN_ITEM_GRANTS_ENABLED` defaults to `true` in this repo so item tooling is visible and ready; keep general writes gated with `DUNE_ADMIN_MUTATIONS_ENABLED`.
- Director character-transfer settings write `config/director.ini`; recreate the Director container before relying on a changed transfer policy.
- `UserEngine.ini` and `UserGame.ini` edits are copied into game containers during game-service startup. Recreate affected game containers before relying on changed gameplay knobs.
- Keep `DUNE_ADMIN_MAX_BODY_BYTES` small unless editing unusually large config files; the default is `65536`.
- Keep `DUNE_ADMIN_AUDIT_MAX_BYTES` bounded; the default rotates the JSONL audit log at 5 MiB.
- Keep `DUNE_ADMIN_REQUEST_TIMEOUT_SECONDS` bounded; the default is `10` seconds to limit slow-body and idle connection abuse.
- Keep `DUNE_ADMIN_MAX_ITEM_STACK_SIZE` bounded; the default is `1000000` to prevent accidental enormous stack writes.
- Keep `DUNE_ADMIN_AUDIT_EVENT_LIMIT`, `DUNE_ADMIN_REFERENCE_LIMIT`, and `DUNE_ADMIN_CHARACTER_SEARCH_LIMIT` bounded so read endpoints stay predictable as local data grows.
- Set `DUNE_ADMIN_ALLOWED_HOSTS` to the exact hostnames used to reach the panel, for example `127.0.0.1:18080,localhost:18080,admin.example.test`.
- Review the Security tab's recent audit events after failed login attempts, blocked host/origin requests, config edits, backups, or mutation runs.
- Restart affected game services after config changes when the target service does not hot-reload.
- POST APIs require `application/json`; form posts, chunked bodies, duplicate `Content-Length`, and oversized requests are rejected before mutation routing.
- Destructive item/keystone actions require server-side confirmation phrases in addition to browser prompts.
- The browser UI uses a per-response CSP nonce and does not require broad `unsafe-inline` script execution.

## Container Hardening

The admin panel container runs with a read-only root filesystem, drops Linux capabilities, sets `no-new-privileges`, uses a small no-exec `/tmp`, and has process/memory guardrails. Only the explicit bind mounts for `admin/`, `config/`, `.env`, and `backups/` are writable where needed.
