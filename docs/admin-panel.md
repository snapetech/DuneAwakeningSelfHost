# Admin Panel

The admin helper panel is a LAN-only web UI for local server operators. It is not exposed publicly by default.

## Start

For the current local trusted deployment, the panel runs unlocked by default:

```env
DUNE_ADMIN_REQUIRE_TOKEN=false
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
```

To require a browser token, set:

```env
DUNE_ADMIN_REQUIRE_TOKEN=true
DUNE_ADMIN_TOKEN=replace-with-a-long-random-token
```

Start the service:

```bash
docker compose -f compose.yaml -f compose.allmaps.yaml --env-file .env up -d --no-deps --no-recreate admin-panel
```

Open:

```text
http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}
```

When token auth is enabled, protected APIs use `X-Admin-Token`. The browser stores the token in local/session storage when entered in the header. When token auth is disabled, the token header is hidden and the Security page reports `local unlocked`.

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

If you put a separate LAN reverse proxy in front of the local admin-panel port, make sure the hostname has an explicit route. A missing route can look like the panel is offline even when `127.0.0.1:${DUNE_ADMIN_HOST_PORT}` is healthy. The reverse proxy should forward the original `Host` header and target the local published port:

```caddyfile
@admin_panel {
    host admin.example.test
}
reverse_proxy @admin_panel 127.0.0.1:18081 {
    header_up Host {host}
    header_up X-Forwarded-Host {host}
    header_up X-Forwarded-Proto http
}
```

For Caddy or any other LAN ingress, also keep the admin hostname in a private/LAN allow rule. Do not add it to a public catch-all route.

If the local published port accepts TCP but returns no HTTP bytes, check for stale permanent neighbor entries on the Docker bridge after admin container recreation:

```bash
ip neigh show dev br-<dune-bridge-id> | grep '172.31.240.8\|172.31.240.9'
./scripts/seed-gateway-neighbor.sh
curl -H 'Host: admin-panel:8080' http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18081}/api/status
```

`scripts/seed-gateway-neighbor.sh` refreshes the host bridge entries for the admin ingress and panel containers. This avoids the failure mode where Docker's localhost proxy connects but sends traffic to an old container MAC after a recreate.

Optional hardening probe:

```dotenv
DUNE_ADMIN_LAN_URL=http://admin.example.test/api/status
```

```bash
./scripts/check-admin-ingress.sh .env
```

That script checks both the direct local panel endpoint and the optional LAN hostname. It catches the common failure where the container is healthy but the external reverse proxy returns `502` because no hostname route points at the panel.

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
- Hagga Basin coordinate grid that projects persisted database pawn coordinates onto a clean `survival_1` tile composite at `admin/static/hagga-basin.webp` through `DUNE_HAGGA_MAP_*` calibration. The default grid follows the public map tile bounds, `X -457200..355600`, `Y -457200..355600`, with world X mapped horizontally and world Y mapped downward so the currently observed Lukano persistence coordinates render south-central instead of north-central. The panel intentionally does not overlay DB POIs/waypoints/landmarks.
- Location source diagnostics are shown under the map and returned by `/api/players/hagga-basin`. Current findings are documented in [`../PLAYER_LOCATION_SOURCE_AUDIT.md`](../PLAYER_LOCATION_SOURCE_AUDIT.md): actor transforms, `load_travel_to_player_info`, return info, respawn locations, actor state, overmap rows, game events, and normal server logs do not currently provide a proven live in-game arrow position.
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
- Catalog tab for content-insertion surfaces, evidence levels, validation commands, typed knob dry-runs, spice/resource inspection, event dry-runs, and economy bundle dry-runs.
- Read-only content catalog APIs:
  - `GET /api/catalog/surfaces`
  - `GET /api/catalog/evidence`
  - `GET /api/catalog/validation`
- Typed gameplay knob API at `GET/POST /api/settings/typed-knobs`. Dry-runs are available without the typed-write gate; writes require backups, the global mutation gate, `DUNE_ADMIN_TYPED_KNOBS_ENABLED=true`, and the confirmation phrase `WRITE TYPED KNOBS`.
- Config editor for selected local config files, including official `UserEngine.ini` and `UserGame.ini` overlays, with backups under `backups/admin-panel`.
- Director GME voice-chat credentials can be added through the `director.ini` config editor when Funcom/provider supplies real `GmeAppId` and `GmeAppKey` values. Leave them unset otherwise.
- Currency and XP mutation endpoints gated by `DUNE_ADMIN_MUTATIONS_ENABLED`.
- Economy bundle planning through `POST /api/admin/bundle`. It plans currency, XP, and item grants in one response and defaults to `dry_run=true`. Execution additionally requires `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=true` and confirmation `EXECUTE BUNDLE`.
- Offline player recovery preview through `POST /api/admin/player-recovery/offline-teleport`. Execution refuses online players and requires `MOVE OFFLINE PLAYER`.
- Spice/resource field inspection through `POST /api/admin/spice-fields/inspect`.
- Event planner APIs:
  - `GET /api/events`
  - `POST /api/events/dry-run`
  - `POST /api/events`
  - `POST /api/events/cancel`
  - `POST /api/events/run`
  Event execution is blocked unless `DUNE_ADMIN_EVENT_EXECUTION_ENABLED=true`.
- Postgres custom-format backup under `backups/admin-panel`.
- Redacted JSONL audit trail for rejected requests and admin writes under `backups/admin-panel/audit.jsonl`.
- Known item template, observed item template, inventory, and inventory-type references.
- Player dropdowns in Admin Actions for currency, XP, keystones, item grant targeting, and item maintenance.
- Selected players pre-populate controller/account/name fields, current currency and specialization selectors, owned inventories, and owned inventory items for stack edits or deletion.
- Exact-template item grants, dry-runs, stack edits, and item deletion behind admin gates.

## Content Catalog and Safe Expansion

The source-of-truth evidence catalog is [`../CONTENT_INSERTION_SURFACES.md`](../CONTENT_INSERTION_SURFACES.md). The Catalog tab renders the same model through read-only APIs and groups surfaces as:

- Deep Desert
- Economy/Admin
- World Rules
- GM/RabbitMQ
- Limits

Each catalog entry uses this schema:

```text
surface, capability, evidence, confidence, mutationRisk,
restartRequired, validationCommand, rollback
```

Evidence handling is deliberately strict:

- Shipped config plus live database behavior is strong evidence.
- Binary strings are leads until section, syntax, and runtime effect are proven.
- Public websites are candidate lookup sources only.
- Native GM command routes remain previews until `DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true` is proven by live-client validation.

The Catalog tab includes safe forms for:

- Typed knob dry-runs.
- Spice/resource state inspection.
- Event dry-run planning.
- Economy bundle dry-run planning.

These forms are intentionally preview-first. They make the plan visible before any write gate can matter.

## New Admin Gates

The content expansion adds separate gates so operators can expose discovery without enabling writes:

```env
DUNE_ADMIN_CATALOG_ENABLED=true
DUNE_ADMIN_TYPED_KNOBS_ENABLED=false
DUNE_ADMIN_EVENT_EXECUTION_ENABLED=false
DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=false
```

Gate behavior:

- `DUNE_ADMIN_CATALOG_ENABLED`: controls read-only catalog endpoints.
- `DUNE_ADMIN_TYPED_KNOBS_ENABLED`: controls typed config writes only. Typed dry-runs still work.
- `DUNE_ADMIN_EVENT_EXECUTION_ENABLED`: controls event execution. Event creation and dry-run planning still work.
- `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED`: controls economy bundle execution. Bundle dry-runs still work.

Existing gates still apply:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
DUNE_ADMIN_GM_COMMANDS_ENABLED=false
DUNE_GM_COMMAND_PAYLOAD_VERIFIED=false
```

Write confirmation phrases:

```text
WRITE TYPED KNOBS
EXECUTE BUNDLE
MOVE OFFLINE PLAYER
RUN GM COMMAND
```

## Typed Gameplay Knobs

`GET /api/settings/typed-knobs` returns the typed knob registry and current values. `POST /api/settings/typed-knobs` accepts:

```json
{
  "dry_run": true,
  "updates": {
    "globalMiningMultiplier": "2.5"
  }
}
```

For Deep Desert spice caps, the dry-run body can use structured caps:

```json
{
  "dry_run": true,
  "updates": {
    "spiceDeepDesertCaps": {
      "Medium": {"primed": 24, "active": 24},
      "Large": {"primed": 3, "active": 3}
    }
  }
}
```

Current typed knobs:

| ID | File | Section/key | Confidence | Risk |
| --- | --- | --- | --- | --- |
| `spiceDeepDesertCaps` | `UserGame.ini` | `[/Script/DuneSandbox.SpiceHarvestingSystem] m_PerMapSystemSettings` | high | medium |
| `sandstormEnabled` | `UserEngine.ini` | `[ConsoleVariables] Sandstorm.Enabled` | high | low |
| `sandstormTreasureEnabled` | `UserEngine.ini` | `[ConsoleVariables] Sandstorm.Treasure.Enabled` | moderate | medium |
| `coriolisAutoSpawnEnabled` | `UserGame.ini` | `[/Script/DuneSandbox.SandStormConfig] m_bCoriolisAutoSpawnEnabled` | high | medium |
| `globalMiningMultiplier` | `UserEngine.ini` | `[ConsoleVariables] Dune.GlobalMiningOutputMultiplier` | high | low |
| `vehicleMiningMultiplier` | `UserEngine.ini` | `[ConsoleVariables] Dune.GlobalVehicleMiningOutputMultiplier` | high | low |
| `pvpResourceMultiplier` | `UserEngine.ini` | `[ConsoleVariables] SecurityZones.PvpResourceMultiplier` | high | low |
| `forcePvpAllPartitions` | `UserGame.ini` | `[/Script/DuneSandbox.PvpPveSettings] m_bShouldForceEnablePvpOnAllPartitions` | high | medium |
| `securityZonesEnabled` | `UserGame.ini` | `[/Script/DuneSandbox.SecurityZonesSubsystem] m_bAreSecurityZonesEnabled` | high | medium |
| `buildingShelterThreshold` | `UserGame.ini` | `[/Script/DuneSandbox.ShelterSettings] m_BuildingShelterThreshold` | moderate | experimental |
| `placeableShelterThreshold` | `UserGame.ini` | `[/Script/DuneSandbox.ShelterSettings] m_PlaceableShelterThreshold` | moderate | experimental |
| `shelteredProtectionThreshold` | `UserGame.ini` | `[/Script/DuneSandbox.HydrationSubsystem] ShelteredProtectionThreshold` | low | experimental |

Typed writes create a backup under `backups/admin-panel` before writing the config file. Most of these values require restarting the affected map containers.

The typed layer deliberately does not expose Coriolis cycle seed, DB wipe, or cycle-end restart fields.

## Economy Bundle Plans

`POST /api/admin/bundle` produces a single audited plan for currency, XP, and item grants. Default behavior is dry-run:

```json
{
  "dry_run": true,
  "currency": [
    {"player_controller_id": 123, "currency_id": 1, "amount": 1000, "mode": "add"}
  ],
  "xp": [
    {"player_id": 123, "track_type": "Combat", "amount": 1000, "mode": "add"}
  ],
  "items": [
    {"account_id": 456, "template_id": "SolarisCoin", "stack_size": 1}
  ]
}
```

Execution requires all of:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_ITEM_GRANTS_ENABLED=true` for item rows
- `confirm: "EXECUTE BUNDLE"`

Rollback is compensating work from the audit record: set currency back, set XP back through the specialization function, and delete or adjust granted item rows.

## Offline Player Recovery

`POST /api/admin/player-recovery/offline-teleport` previews or executes the mapped database function:

```sql
dune.admin_move_offline_player_to_partition(
  in_fls_id text,
  in_target_partition_id bigint,
  in_target_location dune.vector
)
```

Dry-run body:

```json
{
  "dry_run": true,
  "account_id": 456,
  "partition_id": 12,
  "location": {"x": 0, "y": 0, "z": 0}
}
```

The endpoint refuses online players. Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `confirm: "MOVE OFFLINE PLAYER"`

Rollback is another offline move using the previous partition/location recorded in the audit context. Confidence is moderate because the function contract is mapped, but live recovery should still be validated on a non-critical character first.

## Spice and Resource Inspection

`POST /api/admin/spice-fields/inspect` is read-only. It queries:

- `dune.spicefield_types`
- `dune.spicefield_server_availability`
- grouped `dune.resourcefield_state`
- the current `spiceDeepDesertCaps` typed knob value

Use it before and after Deep Desert cap changes, then validate with:

```sql
select * from dune.spicefield_types order by map, field_kind_id;

select map,dimension_index,field_kind_id,count(*),sum(value_remaining)
from dune.resourcefield_state
group by 1,2,3
order by 1,2,3;
```

## Event Orchestrator

Events are persisted in:

```text
backups/admin-panel/events.json
```

Supported action types:

| Type | Behavior |
| --- | --- |
| `announcement` | Plans a call to `/api/ops/announcement`. |
| `restart` | Plans a restart schedule with execution disabled in the action payload. |
| `typed-knob-plan` | Plans typed knob updates only. |
| `economy-bundle` | Plans an economy bundle with `dry_run=true`. |
| `spice-cap-proposal` | Plans Deep Desert spice cap typed knob changes. |

Dry-run example:

```json
{
  "name": "Deep Desert spice proposal",
  "actions": [
    {
      "type": "spice-cap-proposal",
      "caps": {
        "Medium": {"primed": 24, "active": 24},
        "Large": {"primed": 3, "active": 3}
      }
    }
  ]
}
```

`POST /api/events/run` remains blocked unless `DUNE_ADMIN_EVENT_EXECUTION_ENABLED=true`. In the current v1 implementation, dry-run-only actions still do not perform underlying writes during event execution; they record the planned action and tell the operator which dedicated endpoint to use. Confidence: high that this is fail-closed, moderate that it is sufficient for real event automation without a later worker loop.

## Blocked in v1

The admin expansion does not implement:

- Native GM command execution.
- True new maps, cooked assets, physics, or algorithms.
- Raw recipe/journey/vehicle DB grants.
- Coriolis wipe/cycle mutation controls.
- Ordinary resource-node respawn mutation beyond documented config candidates.

Those areas need stronger evidence, safe DB functions, or cooked asset/plugin/binary work before they should move out of the catalog.

## Regression Tests

The safe-surface expansion has a focused test target:

```bash
python3 scripts/test-admin-panel-safe-surfaces.py
```

It runs under a temporary `ADMIN_WORKSPACE`, so it does not edit the live `.env`, `config/`, or `backups/` paths. `make validate` runs this test after the existing map-watch tests.

Current coverage:

- Catalog schema and groups.
- Typed knob value validation.
- Typed config writes with backups in a temporary workspace.
- Deep Desert spice cap rendering from structured JSON.
- Event dry-run planning.
- Event persistence and cancellation.
- Event execution blocked by default.

## Restart Announcements

The Ops tab includes a restart-announcement scheduler with these restart-time presets:

```text
immediate, 30s, 60s, 5min, 10min, 15min, 30min, 60min, 1hr, 2hr, 3hr, 4hr, 6hr, 12hr
```

The scheduler is real, and in-game delivery is delegated to:

```env
DUNE_ADMIN_ANNOUNCE_COMMAND=/workspace/scripts/announce.sh
```

`scripts/announce.sh` publishes directly to the game RabbitMQ `chat.map` exchange as the local Paul announcer account. This is the only path currently verified in-game. The old `ServiceBroadcast`/JSON-RPC route, RabbitMQ management `publish`, and hand-written AMQP publisher can report success while the client renders nothing.

The stable transport is:

1. The hook binds currently online player queues to the configured `chat.map` routing keys.
2. The hook publishes a `TextChat` payload with bundled `pika`, matching the AMQP property encoding used by real player chat.
3. Paul-origin messages are wrapped as `!!! message !!!` before delivery. Direct/manual hook invocations with `DUNE_ANNOUNCE_JOB_ID=manual` are not wrapped.

Default announcement transport settings:

```env
DUNE_ANNOUNCE_GAME_RMQ_MANAGEMENT_URL=http://game-rmq:15672
DUNE_ANNOUNCE_GAME_RMQ_AMQP_HOST=172.31.240.1
DUNE_ANNOUNCE_GAME_RMQ_AMQP_PORT=31982
DUNE_ANNOUNCE_HOST_AMQP_HOST=172.31.240.1
DUNE_ANNOUNCE_HOST_AMQP_PORT=31982
DUNE_ANNOUNCE_HOST_WORKSPACE=/path/to/DuneAwakeningSelfHost
DUNE_ANNOUNCE_GAME_RMQ_AMQP_TLS=true
DUNE_ANNOUNCE_HTTP_TIMEOUT_SECONDS=0.5
DUNE_ANNOUNCE_ALLOW_MANAGEMENT_PUBLISH=false
DUNE_ANNOUNCE_CHAT_USER=A000000000000001
DUNE_ANNOUNCE_CHAT_PASSWORD=<local announcer password>
DUNE_ANNOUNCE_CHAT_FUNCOM_ID=ADMIN#00001
DUNE_ANNOUNCE_CHAT_SPOOF_NAME=Paul
DUNE_ANNOUNCE_CHAT_EXCHANGE=chat.map
DUNE_ANNOUNCE_CHAT_ROUTING_KEYS=HaggaBasin.0,Survival_1.dim_0,<empty>
DUNE_ANNOUNCE_CHAT_CHANNEL=Map
DUNE_ANNOUNCE_CHAT_USE_SPOOF_NAME=true
DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES=true
DUNE_ANNOUNCE_CHAT_ENSURE_ACCOUNT=false
DUNE_ANNOUNCE_CHAT_PLATFORM_ID=PAUL
DUNE_ANNOUNCE_CHAT_PLATFORM_NAME=Paul
```

`DUNE_ANNOUNCE_CHAT_ROUTING_KEYS` is comma-separated. Use `<empty>` for the blank RabbitMQ routing key. Keep the three default routes unless a new build changes chat routing; those are the routes verified with the live client. When `DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES=true`, the hook first lists connected player queues on game RabbitMQ and idempotently binds them to the configured chat routes, then publishes the restart message. The hook reads `/workspace/.env` at delivery time, so route and sender changes are picked up without recreating the admin-panel container.

Do not replace the `pika` publisher with RabbitMQ HTTP publish unless you validate the client visually. The management API can accept messages and return `routed=true` while the Dune client ignores them. The bundled dependency lives under `scripts/vendor/pika` so the admin panel does not need internet access.

Verification command:

```bash
./scripts/verify-announcement.sh 'PAUL ANNOUNCEMENT VERIFY'
```

For a dashboard-origin test, use Ops -> Restart Announcement or POST `/api/ops/announcement`; the visible message should be wrapped, for example `!!! ADMIN Alert f00 !!!`.

Known formatting limits: normal chat does not parse Unreal/HTML-style rich text tags. Tested color syntaxes such as `<#ff4444>`, `<RichColor ...>`, `<Red>`, `<b>`, `^1`, and `&c` render literally or blank the message. Keep automated restart announcements plain ASCII.

The default sender account is created with the game database login function so the client treats it as a real player-shaped identity:

```sql
select *
from dune.login_account('A000000000000001','ADMIN#00001','PAUL','Paul',0,'Paul',0,0)
limit 1;
```

If in-game chat shows an older sender name, the client is resolving the persisted announcer account instead of honoring only `DUNE_ANNOUNCE_CHAT_SPOOF_NAME`. Repair only the synthetic announcer account:

```sql
update dune.encrypted_player_state
set encrypted_character_name = dune.encrypt_user_data('Paul')
where account_id = (select id from dune.encrypted_accounts where "user" = 'A000000000000001');

update dune.encrypted_accounts
set platform_id = 'PAUL', platform_name = 'Paul'
where "user" = 'A000000000000001';
```

The admin panel passes:

- `DUNE_ANNOUNCE_MESSAGE`
- `DUNE_ANNOUNCE_RESTART_AT`
- `DUNE_ANNOUNCE_JOB_ID`

The script also receives the message as its first argument. Delivery attempts and failures are recorded in the admin audit log.

## Chat Commands

`scripts/admin-chat-commands.py` is the DASH chat-command bridge. It listens for game chat messages that start with `DUNE_CHAT_COMMAND_PREFIX`, resolves the sending account through `dune.accounts.user`, and only accepts commands from configured admins.

Default command settings:

```env
DUNE_CHAT_COMMAND_PREFIX=&
DUNE_CHAT_COMMAND_ADMINS=Lukano
DUNE_CHAT_COMMAND_ADMIN_FLS_IDS=6FF6498F4074E3DE
DUNE_CHAT_COMMAND_DRY_RUN=true
DUNE_CHAT_COMMAND_EXECUTE_TELEPORT=false
DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=false
DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT=false
DUNE_PLAYER_DISCONNECT_COMMAND=RemoveSessionMember
DUNE_PLAYER_DISCONNECT_ALLOW_BATTLEYE=false
DUNE_ADMIN_RESTART_DISCONNECT_WAIT_SECONDS=5
DUNE_GM_COMMAND_PAYLOAD_VERIFIED=false
DUNE_GM_COMMAND_ENVELOPE_MODE=service-message
DUNE_GM_COMMAND_TRANSPORT=amqp
DUNE_GM_COMMAND_EXCHANGE=rpc
DUNE_GM_COMMAND_REPLY_TO=bgdRpc
DUNE_GM_COMMAND_AMQP_HOST=admin-rmq
DUNE_GM_COMMAND_AMQP_PORT=5672
DUNE_GM_COMMAND_AMQP_USER=<admin-rmq command user>
DUNE_GM_COMMAND_AMQP_PASSWORD=<admin-rmq command password>
DUNE_GM_COMMAND_RMQ_URL=http://admin-rmq:15672
DUNE_GM_COMMAND_RMQ_USER=<admin-rmq command user>
DUNE_GM_COMMAND_RMQ_PASSWORD=<admin-rmq command password>
DUNE_CHAT_COMMAND_EXCHANGE=chat.intercept
DUNE_CHAT_COMMAND_QUEUE=dash_admin_chat_commands
DUNE_CHAT_COMMAND_ROUTING_KEY=#
DUNE_CHAT_COMMAND_AMQP_HOST=game-rmq
DUNE_CHAT_COMMAND_AMQP_PORT=5672
DUNE_CHAT_COMMAND_AMQP_TLS=true
DUNE_CHAT_COMMAND_AMQP_USER=guest
DUNE_CHAT_COMMAND_AMQP_PASSWORD=guest
DUNE_CHAT_COMMAND_REPLY_COMMAND=/workspace/scripts/announce.sh
DUNE_CHAT_SPAM_PROTECT_ENABLED=true
DUNE_CHAT_SPAM_SAME_CONSECUTIVE_LIMIT=3
DUNE_CHAT_SPAM_SAME_WINDOW_LIMIT=5
DUNE_CHAT_SPAM_SAME_WINDOW_SECONDS=30
DUNE_CHAT_SPAM_KICK_COMMAND=/workspace/scripts/spam-kick-player.sh --player {character_name} --fls-id {fls_id} --reason {reason} --message {message}
DUNE_SPAM_KICK_BACKEND=blocked
```

Implemented commands:

```text
&test
&where <playername>
&disconnect <playername>
&kick <playername>
&teleport <playername>
&goto <playername>
&bring <playername>
&gm help
&gm routes
&gm mark|marks|unmark|recall
&gm pos|dry
&gm where|goto|bring|unstuck
&gm item|kit|xp
&gm tp|map|travel|dimension|patrol|sandworm|marker|vehicle
&gm fly|ghost|walk
```

`&test` replies with `f00` through the configured announcement/reply path. Use it as the first live smoke test for chat-command ingestion and reply delivery.

`&where` reports the resolved player's current online/offline state and last known location. `&teleport` moves an offline target to the admin's current partition and location, using the server's own `dune.admin_move_offline_player_to_partition(...)` function. It rejects online targets because live actor transforms are owned by the running map server and can be overwritten.

`&disconnect` and its `&kick` alias resolve a target player, route the request to the player's current map, and default to `RemoveSessionMember <playername>`. That is the softest known native session-removal candidate. `KickLobbyMember` can be selected with `DUNE_PLAYER_DISCONNECT_COMMAND=KickLobbyMember` if session removal does not work. `BattlEyeMegaKick` is intentionally excluded unless `DUNE_PLAYER_DISCONNECT_ALLOW_BATTLEYE=true` and `DUNE_PLAYER_DISCONNECT_COMMAND=BattlEyeMegaKick` are set, because it is the most likely option to behave like a punitive kick or retry cooldown.

Targeted disconnect execution has its own gate. It requires all three of `DUNE_ADMIN_GM_COMMANDS_ENABLED=true`, `DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true`, and `DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT=true`. Until those are true, the command returns the exact native payload preview instead of publishing it. The repo also sets the server reconnect grace periods to `0` in `config/UserGame.ini`, so normal disconnects should not leave a long persisted reconnect window.

`&goto` and `&bring` are wired through the native GM command adapter for online movement, but execution remains gated until the command payload is proven. `&goto <playername>` prepares `TeleportToPlayer <playername>` targeted at the admin; `&bring <playername>` prepares `TeleportToExact <admin-x> <admin-y> <admin-z>` targeted at the online player. The three required gates are `DUNE_ADMIN_GM_COMMANDS_ENABLED=true`, `DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true`, and `DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=true`. Until then, the commands return the exact payload preview instead of publishing a live teleport.

`&gm` is the richer native-command namespace. It supports safe probes, saved admin marks, movement/travel previews, player help, item/kit previews, XP mutation request previews, and movement-mode previews. All native publishes remain gated by the same three GM flags; dangerous building/placeable destroy commands are intentionally not wired as chat shortcuts.

### Chat Spam Auto-Protection

The chat-command listener also watches all intercepted chat messages for repeated-message spam. It is enabled by default with these rules:

- More than `3` identical messages in a row from the same player triggers enforcement.
- `5` identical messages within `30` seconds from the same player triggers enforcement.
- Admins are exempt by default through `DUNE_CHAT_SPAM_PROTECT_EXEMPT_ADMINS=true`.
- A cooldown prevents repeated enforcement on the same player for `300` seconds.

The detector normalizes whitespace and case before comparing messages. On violation it runs `DUNE_CHAT_SPAM_KICK_COMMAND` and announces the result. The default hook is `scripts/spam-kick-player.sh`, which fails closed with `DUNE_SPAM_KICK_BACKEND=blocked` until a real kick backend is configured. Because targeted disconnect depends on the native GM command route being verified for the current server build, violations are logged and announced as blocked by default instead of silently doing unsafe state writes.

Useful knobs:

```env
DUNE_CHAT_SPAM_PROTECT_ENABLED=true
DUNE_CHAT_SPAM_PROTECT_EXEMPT_ADMINS=true
DUNE_CHAT_SPAM_SAME_CONSECUTIVE_LIMIT=3
DUNE_CHAT_SPAM_SAME_WINDOW_LIMIT=5
DUNE_CHAT_SPAM_SAME_WINDOW_SECONDS=30
DUNE_CHAT_SPAM_KICK_COOLDOWN_SECONDS=300
DUNE_CHAT_SPAM_KICK_COMMAND=/workspace/scripts/spam-kick-player.sh --player {character_name} --fls-id {fls_id} --reason {reason} --message {message}
DUNE_SPAM_KICK_BACKEND=blocked
DUNE_SPAM_KICK_BACKEND_COMMAND=
DUNE_CHAT_SPAM_EXEMPT_NAMES=
DUNE_CHAT_SPAM_EXEMPT_FLS_IDS=
```

`DUNE_CHAT_SPAM_KICK_COMMAND` is parsed with shell-style quoting and supports these placeholders: `{character_name}`, `{player}`, `{fls_id}`, `{reason}`, and `{message}`.

`scripts/spam-kick-player.sh` supports `DUNE_SPAM_KICK_BACKEND=blocked` and `DUNE_SPAM_KICK_BACKEND=command`. The `command` backend delegates to `DUNE_SPAM_KICK_BACKEND_COMMAND` with `--player`, `--fls-id`, `--reason`, and `--message`; use it only after a targeted disconnect primitive is proven.

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

The listener service is separate from the web panel so a command-loop failure does not take down the admin panel hostname. It uses `restart: unless-stopped` and reads `/workspace/.env` at runtime for chat-command and announcement credentials, matching the announcement hook behavior.

## Scheduled Restarts And Shutdowns

The Ops tab can also schedule restart or shutdown jobs for restart-safe components, the service layer, all game maps, or key individual maps such as Survival, Overmap, Arrakeen, Harko Village, and Deep Desert. It does not stop or restart Postgres or RabbitMQ by default because replacing those services disconnects all running map servers. It also does not include `admin-panel` in the admin-triggered `all` target, because stopping the container running the scheduler would interrupt the stop-backup-update-start workflow.

Scheduled maintenance defaults to dry-run mode. In dry-run mode, the job matures, records that it would have run, and does not touch containers. Executed restart jobs now use a stop-backup-update-start sequence: stop the selected game services, take the maintenance backup while they are down, check the local Steam package for a newer Funcom image tag, then start/recreate the selected services. Executed shutdown jobs stop the selected services, take the maintenance backup, run the same Steam-package update check, and leave them stopped. If the stop step fails, no backup, update check, or start is attempted. If the backup step fails during a restart, the selected services are left stopped so the failed backup can be investigated before the world is brought back online.

Maintenance announcements automatically append the live time remaining, or fill `{remaining}` / `{time_remaining}` if either token appears in the configured message. At the zero mark, the announcement worker sends a final "starting now" notice before execution begins. Announcement jobs also support an optional cadence list, using `remaining_seconds` and `interval_seconds` entries, so unattended maintenance can announce every 5 minutes during the 30-minute warning window and every 1 minute during the final 5 minutes.

Before an executed restart or shutdown stops containers, the admin panel resolves the online players affected by the target, publishes the configured soft-disconnect command to each player's current map route, waits `DUNE_ADMIN_RESTART_DISCONNECT_WAIT_SECONDS` seconds after all publishes complete, and only then starts the stop phase. If online players are present and the targeted-disconnect gates are not enabled, the restart/shutdown fails closed and does not stop services.

Maintenance backups are written under `backups/admin-panel/maintenance/<utc-stamp>-<job-id>/`. Each backup includes a unique Postgres custom-format dump, config/env archive, and mounted `data/server-saved` / `data/rabbitmq` archives when those paths are available to the admin container. Each backup also writes `postgres-layers.json`, which records primary streaming-replication slots and active senders at the stopped-world backup point. If `POSTGRES_REMOTE_REPLICA_HOST` is configured and `DUNE_ADMIN_MAINTENANCE_REPLICA_SNAPSHOT_ENABLED=true` (default), the backup attempts `scripts/replica-snapshot.sh` so the remote standby also gets a rolling logical snapshot. Replica status and remote snapshot failures are recorded as warnings in `manifest.json`; they do not replace or block the authoritative local stopped-world dump.

After a restart start hook returns successfully, the admin panel waits for farm DB readiness before marking the job successful. The gate requires every current `world_partition` row to have an alive farm row and an `active_server_ids` entry; it also records the stricter ready/alive count as `readyOnline` in the execution details.

When the restart form's announcement checkbox is enabled, the admin panel schedules the first warning immediately and repeats it until the maintenance run time. The standalone announcement card is separate: it only schedules chat notices and does not stop, start, or back up services.

Actual execution is delegated to:

```env
DUNE_ADMIN_RESTART_COMMAND=/workspace/scripts/restart-target.sh
```

`scripts/restart-target.sh` first uses Docker Compose when the Docker CLI is available. Inside the admin-panel container it falls back to the mounted Docker Engine socket and operates on containers by Compose labels:

```env
DUNE_RESTART_COMPOSE_PROJECT=dune_server
DUNE_RESTART_DOCKER_SOCKET=/var/run/docker.sock
DUNE_RESTART_HOST_WORKSPACE=/path/to/DuneAwakeningSelfHost
DUNE_RESTART_COMPOSE_IMAGE=docker:27-cli
DUNE_RESTART_USE_HOST_COMPOSE=true
DUNE_RESTART_COMPOSE_TIMEOUT_SECONDS=1800
DUNE_RESTART_DOCKER_STOP_TIMEOUT_SECONDS=120
DUNE_RESTART_DOCKER_API_TIMEOUT_SECONDS=30
```

The Docker socket is privileged host control. Keep the admin panel bound to localhost or a trusted reverse proxy, and do not expose the admin hostname publicly. If the panel is reachable beyond a trusted local admin surface, enable `DUNE_ADMIN_REQUIRE_TOKEN=true`. The script receives `DUNE_RESTART_JOB_ID`, `DUNE_RESTART_TARGET`, `DUNE_RESTART_SERVICES`, and `DUNE_RESTART_ACTION`, plus the target as its first argument.

For admin-triggered restart jobs, the stop phase uses Docker stop, and the start phase uses Compose `up -d --force-recreate --no-deps`. When the admin image has no Docker CLI, the socket fallback starts a short-lived privileged `docker:27-cli` helper container with the repo and Docker socket mounted, then runs host-side Compose from that helper. It also runs `scripts/seed-gateway-neighbor.sh` before and after recreate so gateway's static `172.31.240.40`/`02:42:ac:1f:f0:28` identity is refreshed in Postgres, gateway, RabbitMQ, service-layer, and host bridge neighbor tables. After recreate and seeding, `scripts/restart-post-start-health.sh` waits for Postgres connectivity, re-seeds bridge neighbors, recreates `text-router` if it exited during early startup, and retries `scripts/verify-rmq-auth-path.sh` until the auth and text-router paths are reachable or the timeout expires. This catches the broken state where `admin-rmq` cannot reach `rmq-auth-shim`, `game-rmq` cannot reach `text-router`, or `text-router` exits because it raced Postgres during startup. This means the daily restart schedule applies changed `.env` values and bind-mounted config files during the recreate phase without pulling in excluded dependencies such as Postgres or RabbitMQ. Keep `DUNE_RESTART_COMPOSE_IMAGE` available locally on the Docker host; if it is missing, pull it before relying on unattended maintenance. The socket fallback gives stop/restart calls a longer timeout than Docker's graceful stop window so a normal slow shutdown is not misreported as a failed maintenance job.

The host-side daily scheduler uses `scripts/schedule-daily-maintenance.sh`. Run it from cron or systemd before the desired maintenance time; the deployed schedule should call it at 05:30 and create an executed, backed-up, announced `all` restart for 06:00, after Funcom's nightly maintenance window. Install the provided timer with `./scripts/install-daily-maintenance-timer.sh .env`. See [`docs/maintenance-updates.md`](maintenance-updates.md) for the timeline, cadence, and Steam-package update logic.

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
- Use a long random `DUNE_ADMIN_TOKEN` whenever `DUNE_ADMIN_REQUIRE_TOKEN=true`.
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
- Steam account ids in `dune.accounts.platform_id` are SteamID64 values. The roster resolves them to public Steam persona names and profile links, cached in `backups/admin-panel/steam-profiles.json`; tune the cache age with `DUNE_ADMIN_STEAM_PROFILE_CACHE_TTL_SECONDS`, or disable outbound lookups with `DUNE_ADMIN_STEAM_PROFILE_LOOKUP_ENABLED=false`. Steam private login names are not exposed.
- Set `DUNE_ADMIN_ALLOWED_HOSTS` to the exact hostnames used to reach the panel, for example `127.0.0.1:18080,localhost:18080,admin.example.test`.
- Review the Security tab's recent audit events after failed login attempts, blocked host/origin requests, config edits, backups, or mutation runs.
- Restart affected game services after config changes when the target service does not hot-reload.
- POST APIs require `application/json`; form posts, chunked bodies, duplicate `Content-Length`, and oversized requests are rejected before mutation routing.
- Destructive item/keystone actions require server-side confirmation phrases in addition to browser prompts.
- The browser UI uses a per-response CSP nonce and does not require broad `unsafe-inline` script execution.

## Container Hardening

The admin panel container runs with a read-only root filesystem, drops Linux capabilities, sets `no-new-privileges`, uses a small no-exec `/tmp`, and has process/memory guardrails. Only the explicit bind mounts for `admin/`, `config/`, `.env`, and `backups/` are writable where needed.
