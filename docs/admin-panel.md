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
docker compose -f compose.yaml -f compose.allmaps.yaml --env-file .env up -d --no-deps --no-recreate admin-panel
```

Open:

```text
http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}
```

The panel uses `X-Admin-Token` for protected APIs. The browser stores the token in session storage when entered in the header.

## LAN Hostname

The Compose service binds to localhost:

```text
${DUNE_ADMIN_BIND_ADDRESS:-127.0.0.1}:${DUNE_ADMIN_HOST_PORT:-18080} -> admin-panel:8080
```

If another local process already owns `18080`, set these in `.env` and recreate `admin-panel`:

```dotenv
DUNE_ADMIN_BIND_ADDRESS=127.0.0.1
DUNE_ADMIN_HOST_PORT=18081
DUNE_ADMIN_ALLOWED_HOSTS=127.0.0.1:18081,localhost:18081,admin.example.test,admin-panel:8080
```

The admin panel should connect to Postgres through Compose DNS (`postgres:5432`). Do not point `DUNE_ADMIN_DB_HOST` at the host bridge address for normal use; that path is more fragile across Docker restarts.

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

- Overview-first dashboard with player roster, realtime resource use, headline health metrics, map health, network checks, and health verdicts.
- Server/farm state view with per-map online/offline health derived from `world_partition`, `farm_state`, and `active_server_ids`.
- Realtime resource view for host load, host memory, workspace disk, and Docker container CPU/memory/network/block I/O when the Docker socket is available.
- Local/upstream health checks for Postgres reachability, the Dune account portal, and public Dune/Funcom HTTP reachability.
- Restart-announcement scheduler under Ops. It accepts a restart time, message, and repeat interval, persists state under `backups/admin-panel/announcements.json`, and invokes `DUNE_ADMIN_ANNOUNCE_COMMAND` for each delivery attempt.
- Scheduled restart planner under Ops. It targets all components, core services, the service layer, all game maps, or key individual maps. Jobs persist under `backups/admin-panel/restart-jobs.json` and invoke `DUNE_ADMIN_RESTART_COMMAND` only when execution is explicitly enabled.
- Player roster split into currently online players and offline players, plus search and detail views.
- Currency/progression table visibility.
- `.env` operations editor for install, world, network, access, secret, and admin-panel knobs. Secret fields are admin-token protected, rendered as password inputs, and returned blank unless a replacement is typed.
- Typed logout/reconnect timer editor for `config/UserGame.ini` under Settings -> Logout and Reconnect Timers.
- Typed Director character-transfer settings editor for `config/director.ini`.
- Config editor for selected local config files, including official `UserEngine.ini` and `UserGame.ini` overlays, with backups under `backups/admin-panel`.
- Director GME voice-chat credentials can be added through the `director.ini` config editor when Funcom/provider supplies real `GmeAppId` and `GmeAppKey` values. Leave them unset otherwise.
- Token-gated currency and XP mutation endpoints.
- Token-gated Postgres custom-format backup under `backups/admin-panel`.
- Redacted JSONL audit trail for rejected requests and admin writes under `backups/admin-panel/audit.jsonl`.
- Known item template, observed item template, inventory, and inventory-type references.
- Player dropdowns in Admin Actions for currency, XP, keystones, item grant targeting, and item maintenance.
- Selected players pre-populate controller/account/name fields, current currency and specialization selectors, owned inventories, and owned inventory items for stack edits or deletion.
- Exact-template item grants, dry-runs, stack edits, and item deletion behind admin gates.

## Restart Announcements

The Ops tab includes a restart-announcement scheduler with these restart-time presets:

```text
immediate, 30s, 60s, 5min, 10min, 15min, 30min, 60min, 1hr, 2hr, 3hr, 4hr, 6hr, 12hr
```

The scheduler is real and token-gated, but in-game delivery is delegated to:

```env
DUNE_ADMIN_ANNOUNCE_COMMAND=/workspace/scripts/announce.sh
```

`scripts/announce.sh` publishes a `ServiceBroadcast` command envelope to the admin RabbitMQ `rpc` exchange. The live server binary exposes `UDuneServerCommandSubsystem`, `SendDuneServerCommand`, and `ServiceBroadcast`; the repo keeps the command body configurable because Funcom can change the exact envelope between builds.

Default announcement transport settings:

```env
DUNE_ANNOUNCE_RMQ_URL=http://admin-rmq:15672
DUNE_ANNOUNCE_RMQ_USER=bgd.<world-unique-name>.duneadmin.admin
DUNE_ANNOUNCE_RMQ_PASSWORD=<local secret>
DUNE_ANNOUNCE_RMQ_EXCHANGE=rpc
DUNE_ANNOUNCE_RMQ_ROUTING_KEYS=Survival_11
DUNE_ANNOUNCE_RMQ_REPLY_TO=bgdRpc
DUNE_ANNOUNCE_RMQ_CORRELATION_ID=
DUNE_ANNOUNCE_RMQ_TYPE=json_rpc
DUNE_ANNOUNCE_RMQ_APP_ID=
DUNE_ANNOUNCE_RMQ_USER_ID=
DUNE_ANNOUNCE_COMMAND_NAME=ServiceBroadcast
DUNE_ANNOUNCE_TITLE=Maintenance
DUNE_ANNOUNCE_DURATION_SECONDS=12
DUNE_ANNOUNCE_PAYLOAD_MODE=jsonrpc-notify-array
DUNE_ANNOUNCE_PAYLOAD_TEMPLATE=
```

`DUNE_ANNOUNCE_RMQ_ROUTING_KEYS` is comma-separated. Add map RPC routing keys when you want announcements delivered through more standing maps. The live server's RPC consumer expects AMQP `type=json_rpc`, a non-empty `reply_to`, and a trusted `user_id` prefix; the default `bgd.<world-unique-name>.duneadmin.admin` identity satisfies that through the local RabbitMQ auth shim. `DUNE_ANNOUNCE_PAYLOAD_MODE` selects one of the built-in probe envelopes: `command-payload`, `server-command`, `message-type`, `flat-command`, `jsonrpc-object`, `jsonrpc-array`, `jsonrpc-notify-object`, `jsonrpc-notify-array`, `dune-server-command`, `dune-server-command-payload`, or `payload-only`. `DUNE_ANNOUNCE_PAYLOAD_TEMPLATE` can override the default JSON body without editing the hook if a newer server build requires a different `ServiceBroadcast` envelope.

After changing the announcer credentials, recreate `rmq-auth-shim` and `admin-panel`. If RabbitMQ has cached a previous denial for that user, restart only `admin-rmq` during a maintenance window; the game servers reconnect their admin queues afterward.

The admin panel passes:

- `DUNE_ANNOUNCE_MESSAGE`
- `DUNE_ANNOUNCE_RESTART_AT`
- `DUNE_ANNOUNCE_JOB_ID`

The script also receives the message as its first argument. Delivery attempts and failures are recorded in the admin audit log.

## Scheduled Restarts

The Ops tab can also schedule restart jobs for restart-safe components, the service layer, all game maps, or key individual maps such as Survival, Overmap, Arrakeen, Harko Village, and Deep Desert. It does not restart Postgres or RabbitMQ by default because replacing those services disconnects all running map servers.

Scheduled restarts default to dry-run mode. In dry-run mode, the job matures, records that it would have run, and does not touch containers.

Actual execution is delegated to:

```env
DUNE_ADMIN_RESTART_COMMAND=/workspace/scripts/restart-target.sh
```

`scripts/restart-target.sh` first uses Docker Compose when the Docker CLI is available. Inside the admin-panel container it falls back to the mounted Docker Engine socket and restarts containers by Compose labels:

```env
DUNE_RESTART_COMPOSE_PROJECT=dune_server
DUNE_RESTART_DOCKER_SOCKET=/var/run/docker.sock
```

The Docker socket is privileged host control. Keep the admin panel bound to localhost or a trusted reverse proxy, require the admin token, and do not expose the admin hostname publicly. The script receives `DUNE_RESTART_JOB_ID`, `DUNE_RESTART_TARGET`, and `DUNE_RESTART_SERVICES`, plus the target as its first argument.

The Docker-socket fallback restarts existing containers. It does not recreate containers or apply changed environment variables; use `docker compose up -d --force-recreate ...` from the host for config changes.

`scripts/restart-target.sh` refuses to restart `postgres`, `admin-rmq`, or `game-rmq` unless `DUNE_RESTART_ALLOW_STATEFUL=true` is set for a deliberate maintenance window. If Postgres must be restarted, expect all game maps to need recovery afterward.

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

## Logout Timers

Steam Deck suspend and quick logout behavior is controlled by the typed Settings -> Logout and Reconnect Timers editor. It writes this section in `config/UserGame.ini`:

```ini
[/Script/DuneSandbox.PlayerOnlineStateSettings]
m_DefaultReconnectGracePeriodSeconds=0
m_OvermapReturnGracePeriodSeconds=0
m_InstancedMapReconnectGracePeriodSeconds=0
```

The same settings are available through token-protected JSON APIs:

- `GET /api/settings/player-online-state`
- `POST /api/settings/player-online-state`

Recreate affected game-server containers after saving so `scripts/run_server_safe.sh` copies the updated `UserGame.ini` into the Unreal saved config paths.

## Security Notes

- Do not expose this service to the public internet.
- Use a long random `DUNE_ADMIN_TOKEN`.
- Keep `DUNE_ADMIN_MUTATIONS_ENABLED=false` unless actively making admin edits.
- `DUNE_ADMIN_ITEM_GRANTS_ENABLED` defaults to `true` in this repo so item tooling is visible and ready; keep general writes gated with `DUNE_ADMIN_MUTATIONS_ENABLED`.
- Director character-transfer settings write `config/director.ini`; recreate the Director container before relying on a changed transfer policy.
- Director GME voice-chat settings also live in `config/director.ini`; recreate Director after changing them.
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
