# Admin Panel

The admin helper panel is a LAN-only web UI for local server operators. It is not exposed publicly by default.

## Start

Set a strong token in `.env`:

```env
DUNE_ADMIN_TOKEN=replace-with-a-long-random-token
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
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

`scripts/announce.sh` publishes directly to the game RabbitMQ `chat.map` exchange as the local DASH announcer account. This is the only path currently verified in-game. The old `ServiceBroadcast`/JSON-RPC route, RabbitMQ management `publish`, and hand-written AMQP publisher can report success while the client renders nothing.

The stable transport is:

1. The hook binds currently online player queues to the configured `chat.map` routing keys.
2. The hook publishes a `TextChat` payload with bundled `pika`, matching the AMQP property encoding used by real player chat.
3. Dashboard-origin messages are wrapped as `!!! message !!!` before delivery. Direct/manual hook invocations with `DUNE_ANNOUNCE_JOB_ID=manual` are not wrapped.

Default announcement transport settings:

```env
DUNE_ANNOUNCE_GAME_RMQ_MANAGEMENT_URL=http://game-rmq:15672
DUNE_ANNOUNCE_GAME_RMQ_AMQP_HOST=172.31.240.1
DUNE_ANNOUNCE_GAME_RMQ_AMQP_PORT=31982
DUNE_ANNOUNCE_HOST_AMQP_HOST=172.31.240.1
DUNE_ANNOUNCE_HOST_AMQP_PORT=31982
DUNE_ANNOUNCE_HOST_WORKSPACE=/home/keith/Documents/code/DuneAwakeningSelfHost
DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS=true
DUNE_ANNOUNCE_HTTP_TIMEOUT_SECONDS=0.5
DUNE_ANNOUNCE_ALLOW_MANAGEMENT_PUBLISH=false
DUNE_ANNOUNCE_CHAT_USER=A000000000000001
DUNE_ANNOUNCE_CHAT_PASSWORD=<local announcer password>
DUNE_ANNOUNCE_CHAT_FUNCOM_ID=ADMIN#00001
DUNE_ANNOUNCE_CHAT_SPOOF_NAME=DASH Admin
DUNE_ANNOUNCE_CHAT_EXCHANGE=chat.map
DUNE_ANNOUNCE_CHAT_ROUTING_KEYS=HaggaBasin.0,Survival_1.dim_0,<empty>
DUNE_ANNOUNCE_CHAT_CHANNEL=Map
DUNE_ANNOUNCE_CHAT_USE_SPOOF_NAME=false
DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES=true
DUNE_ANNOUNCE_CHAT_ENSURE_ACCOUNT=false
DUNE_ANNOUNCE_CHAT_PLATFORM_ID=DASH-ADMIN
DUNE_ANNOUNCE_CHAT_PLATFORM_NAME=DASH
```

`DUNE_ANNOUNCE_CHAT_ROUTING_KEYS` is comma-separated. Use `<empty>` for the blank RabbitMQ routing key. Keep the three default routes unless a new build changes chat routing; those are the routes verified with the live client. When `DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES=true`, the hook first lists connected player queues on game RabbitMQ and idempotently binds them to the configured chat routes, then publishes the restart message. The hook reads `/workspace/.env` at delivery time, so route and sender changes are picked up without recreating the admin-panel container.

Do not replace the `pika` publisher with RabbitMQ HTTP publish unless you validate the client visually. The management API can accept messages and return `routed=true` while the Dune client ignores them. The bundled dependency lives under `scripts/vendor/pika` so the admin panel does not need internet access.

Verification command:

```bash
./scripts/verify-announcement.sh 'DASH ANNOUNCEMENT VERIFY'
```

For a dashboard-origin test, use Ops -> Restart Announcement or POST `/api/ops/announcement`; the visible message should be wrapped, for example `!!! ADMIN Alert f00 !!!`.

Known formatting limits: normal chat does not parse Unreal/HTML-style rich text tags. Tested color syntaxes such as `<#ff4444>`, `<RichColor ...>`, `<Red>`, `<b>`, `^1`, and `&c` render literally or blank the message. Keep automated restart announcements plain ASCII.

The default sender account is created with the game database login function so the client treats it as a real player-shaped identity:

```sql
select *
from dune.login_account('A000000000000001','ADMIN#00001','DASH-ADMIN','DASH',0,'DASH Admin',0,0)
limit 1;
```

The admin panel passes:

- `DUNE_ANNOUNCE_MESSAGE`
- `DUNE_ANNOUNCE_RESTART_AT`
- `DUNE_ANNOUNCE_JOB_ID`

The script also receives the message as its first argument. Delivery attempts and failures are recorded in the admin audit log.

## Chat Commands

`scripts/admin-chat-commands.py` is the first DASH chat-command bridge. It listens for game chat messages that start with `DUNE_CHAT_COMMAND_PREFIX`, resolves the sending account through `dune.accounts.user`, and only accepts commands from configured admins.

Default command settings:

```env
DUNE_CHAT_COMMAND_PREFIX=&
DUNE_CHAT_COMMAND_ADMINS=Lukano
DUNE_CHAT_COMMAND_ADMIN_FLS_IDS=6FF6498F4074E3DE
DUNE_CHAT_COMMAND_DRY_RUN=true
DUNE_CHAT_COMMAND_EXECUTE_TELEPORT=false
DUNE_CHAT_COMMAND_EXCHANGE=chat.intercept
DUNE_CHAT_COMMAND_QUEUE=dash_admin_chat_commands
DUNE_CHAT_COMMAND_ROUTING_KEY=#
DUNE_CHAT_COMMAND_AMQP_HOST=172.31.240.1
DUNE_CHAT_COMMAND_AMQP_PORT=31982
DUNE_CHAT_COMMAND_AMQP_TLS=true
DUNE_CHAT_COMMAND_AMQP_USER=A000000000000001
DUNE_CHAT_COMMAND_AMQP_PASSWORD=<local announcer password>
DUNE_CHAT_COMMAND_REPLY_COMMAND=/workspace/scripts/announce.sh
```

Implemented commands:

```text
&test
&where <playername>
&teleport <playername>
&goto <playername>
```

`&test` replies with `f00` through the configured announcement/reply path. Use it as the first live smoke test for chat-command ingestion and reply delivery.

`&where` reports the resolved player's current online/offline state and last known location. `&teleport` moves an offline target to the admin's current partition and location, using the server's own `dune.admin_move_offline_player_to_partition(...)` function. It rejects online targets because live actor transforms are owned by the running map server and can be overwritten.

`&goto` resolves the target's location and reports the native command candidates for moving the admin to that target. It does not execute yet. Online admin movement needs the native live GM route (`TeleportToPlayer`, `TeleportToExact`, or `TravelTo`) to be verified first.

Teleport starts in dry-run mode. To apply the movement write, set:

```env
DUNE_CHAT_COMMAND_DRY_RUN=false
DUNE_CHAT_COMMAND_EXECUTE_TELEPORT=true
```

Dry-run verification from the live admin container:

```bash
docker compose exec -T admin-panel /workspace/scripts/admin-chat-commands.py \
  --dry-run-command '&teleport Cletus' \
  --sender-name Lukano \
  --sender-fls-id 6FF6498F4074E3DE
```

The listener has been validated to bind `chat.intercept` from the admin container path. If that regresses, first check that `/workspace/.env` contains the current `DUNE_ANNOUNCE_*` and `DUNE_CHAT_COMMAND_*` credentials; stale container environment was the original blocker.

Persistent listener service:

```bash
docker compose up -d --no-deps admin-chat-commands
docker compose logs -f admin-chat-commands
```

The listener service is separate from the web panel so a command-loop failure does not take down `duneadmin.home`. It uses `restart: unless-stopped` and reads `/workspace/.env` at runtime for chat-command and announcement credentials, matching the announcement hook behavior.

## Scheduled Restarts And Shutdowns

The Ops tab can also schedule restart or shutdown jobs for restart-safe components, the service layer, all game maps, or key individual maps such as Survival, Overmap, Arrakeen, Harko Village, and Deep Desert. It does not stop or restart Postgres or RabbitMQ by default because replacing those services disconnects all running map servers.

Scheduled maintenance defaults to dry-run mode. In dry-run mode, the job matures, records that it would have run, and does not touch containers. Executed restart jobs now use a stop-backup-start sequence: stop the selected game services, take the maintenance backup while they are down, then start/recreate the selected services. Executed shutdown jobs stop the selected services, take the maintenance backup, and leave them stopped. If the stop step fails, no backup or start is attempted. If the backup step fails during a restart, the selected services are left stopped so the failed backup can be investigated before the world is brought back online.

Maintenance backups are written under `backups/admin-panel/maintenance/<utc-stamp>-<job-id>/`. Each backup includes a unique Postgres custom-format dump, config/env archive, and mounted `data/server-saved` / `data/rabbitmq` archives when those paths are available to the admin container.

Actual execution is delegated to:

```env
DUNE_ADMIN_RESTART_COMMAND=/workspace/scripts/restart-target.sh
```

`scripts/restart-target.sh` first uses Docker Compose when the Docker CLI is available. Inside the admin-panel container it falls back to the mounted Docker Engine socket and operates on containers by Compose labels:

```env
DUNE_RESTART_COMPOSE_PROJECT=dune_server
DUNE_RESTART_DOCKER_SOCKET=/var/run/docker.sock
```

The Docker socket is privileged host control. Keep the admin panel bound to localhost or a trusted reverse proxy, require the admin token, and do not expose the admin hostname publicly. The script receives `DUNE_RESTART_JOB_ID`, `DUNE_RESTART_TARGET`, `DUNE_RESTART_SERVICES`, and `DUNE_RESTART_ACTION`, plus the target as its first argument.

For admin-triggered restart jobs, the stop phase uses Docker stop, and the start phase uses Compose `up -d --force-recreate` when the Docker CLI is available. The Docker-socket fallback can stop, start, or restart existing containers, but it cannot recreate containers or apply changed environment variables; use the host Compose path for config-change maintenance.

`scripts/restart-target.sh` refuses to stop or restart `postgres`, `admin-rmq`, or `game-rmq` unless `DUNE_RESTART_ALLOW_STATEFUL=true` is set for a deliberate maintenance window. If Postgres must be restarted, expect all game maps to need recovery afterward.

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
- `DUNE_ADMIN_MUTATIONS_ENABLED=true` is the repo default so the character-admin workflows can apply currency, XP, item stack, and item grant changes without a separate redeploy.
- `DUNE_ADMIN_ITEM_GRANTS_ENABLED` defaults to `true` in this repo so item tooling is visible and ready.
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
