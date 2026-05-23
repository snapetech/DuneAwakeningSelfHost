# Admin Panel

The admin helper panel is a LAN-only web UI for local server operators. It is not exposed publicly by default.

## Start

For the current local trusted deployment, the panel runs unlocked by default:

```env
DUNE_ADMIN_REQUIRE_TOKEN=false
DUNE_ADMIN_MUTATIONS_ENABLED=false
DUNE_ADMIN_ITEM_GRANTS_ENABLED=false
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

## Optional GitLab Deployment

GitLab deployment is optional. The default admin-panel install and maintenance path is still direct Compose/systemd operation from the DASH host. Use the `.gitlab-ci.yml` jobs only when you deliberately want a protected `gitlab.home` shell runner to validate and manually deploy the panel.

The optional jobs are:

- `validate:admin-panel` compiles admin-related Python and runs safe-surface/chat tests.
- `deploy:admin-panel` is manual on the default branch and recreates only the `admin-panel` Compose service.
- `observe:admin-panel` is read-only and runs `scripts/check-admin-ingress.sh`.

The deploy path is:

```bash
scripts/deploy-admin-panel.sh .env
```

That script validates the Python entry points, runs `scripts/test-admin-panel-safe-surfaces.py`, recreates `admin-panel` with `docker compose up -d --no-deps --force-recreate admin-panel`, then checks direct and LAN ingress. It does not restart Postgres, RabbitMQ, game maps, Director, Gateway, or admin-panel-ingress.

Keep scheduled GitLab jobs read-only. Admin-panel deploys should stay manual because the panel is a live control surface for mutations, restarts, backups, config writes, and player operations. Do not give a public/shared runner Docker access to the Dune host.

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
- Hagga Basin coordinate grid that projects persisted database pawn coordinates onto a clean `survival_1` tile composite at `admin/static/hagga-basin.webp` through `DUNE_HAGGA_MAP_*` calibration. The default grid follows the public map tile bounds, `X -457200..355600`, `Y -457200..355600`, with world X mapped horizontally and world Y mapped downward so the observed test persistence coordinates render south-central instead of north-central. The panel intentionally does not overlay DB POIs/waypoints/landmarks.
- Location source diagnostics are shown under the map and returned by `/api/players/hagga-basin`. Current findings are documented in [`../PLAYER_LOCATION_SOURCE_AUDIT.md`](../PLAYER_LOCATION_SOURCE_AUDIT.md): actor transforms, `load_travel_to_player_info`, return info, respawn locations, actor state, overmap rows, game events, and normal server logs do not currently provide a proven live in-game arrow position.
- Server/farm state view with per-map online/offline health derived from `world_partition`, `farm_state`, and `active_server_ids`.
- Realtime resource view for host load, host memory, workspace disk, and Docker container CPU/memory/network/block I/O when the Docker socket is available.
- Local/upstream health checks for Postgres reachability, the Dune account portal, and public Dune/Funcom HTTP reachability.
- Restart-announcement scheduler under Ops. It accepts a restart time, message, and repeat interval, persists state under `backups/admin-panel/announcements.json`, and invokes `DUNE_ADMIN_ANNOUNCE_COMMAND` for each delivery attempt.
- Scheduled restart planner under Ops. It targets all components, core services, the service layer, all game maps, or key individual maps. Jobs persist under `backups/admin-panel/restart-jobs.json` and invoke `DUNE_ADMIN_RESTART_COMMAND` only when execution is explicitly enabled.
- Player roster split into currently online players and offline players, plus search and detail views.
- Currency/progression table visibility.
- `.env` operations editor for install, world, network, access, secret, and admin-panel knobs. Secret fields are admin-token protected, rendered as password inputs, and returned blank unless a replacement is typed.
- Artificial Exchange controls under Settings. Operators can manage the first-class Exchange economy workflow: rebuild the reviewed catalog, check buyer/seller readiness, run buyer dry-runs, inspect and claim seller settlement candidates through the gated bot, validate the seeded-listing populator, manage buyer/populator/watchdog systemd units, and edit all `DUNE_ARTIFICIAL_EXCHANGE_*` gates and tuning knobs through the safe `.env` editor.
- Typed logout/reconnect timer editor for `config/UserGame.ini` under Settings -> Logout and Reconnect Timers.
- Typed Director character-transfer settings editor for `config/director.ini`.
- Catalog tab for content-insertion surfaces, evidence levels, validation commands, typed knob dry-runs, spice/resource inspection, event dry-runs, and economy bundle dry-runs.
- Read-only content catalog APIs:
  - `GET /api/catalog/surfaces`
  - `GET /api/catalog/evidence`
  - `GET /api/catalog/validation`
- Artificial Exchange operator API:
  - `GET /api/admin/artificial-exchange`
  - `POST /api/admin/artificial-exchange`
  Supported actions are `build-catalog`, `check-ready`, `buyer-dry-run`, `settlement-report`, `validate-populator`, `install-buyer-service`, `install-populator-service`, `install-watchdog-timer`, `watchdog-once`, and `start|stop|restart|status:buyer|populator|watchdog`.
- Typed gameplay knob API at `GET/POST /api/settings/typed-knobs`. Dry-runs are available without the typed-write gate; writes require backups, the global mutation gate, `DUNE_ADMIN_TYPED_KNOBS_ENABLED=true`, and the confirmation phrase `WRITE TYPED KNOBS`.
- Config editor for selected local config files, including official `UserEngine.ini` and `UserGame.ini` overlays, with backups under `backups/admin-panel`.
- Director GME voice-chat credentials can be added through the `director.ini` config editor when Funcom/provider supplies real `GmeAppId` and `GmeAppKey` values. Leave them unset otherwise.
- Currency and XP mutation endpoints gated by `DUNE_ADMIN_MUTATIONS_ENABLED`.
- Economy bundle planning through `POST /api/admin/bundle`. It plans currency, XP, and item grants in one response and defaults to `dry_run=true`. Execution additionally requires `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=true` and confirmation `EXECUTE BUNDLE`.
- Targeted Solari grants through `POST /api/admin/solari/inventory` for carried `SolarisCoin` stacks and `POST /api/admin/solari/bank` for Exchange/bank balance.
- Offline player recovery preview through `POST /api/admin/player-recovery/offline-teleport`. Execution refuses online players, requires `MOVE OFFLINE PLAYER`, and calls the shipped `dune.admin_move_offline_player_to_partition(...)` pawn move helper.
- Spice/resource field inspection through `POST /api/admin/spice-fields/inspect`.
- Progression surface inspection through `POST /api/admin/progression/inspect`; this discovers faction, reputation, journey, recipe, vehicle, and related DB function/table evidence without executing discovered functions.
- Faction reputation planning through `POST /api/admin/faction-reputation`, default `dry_run=true`. Execution requires `DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED=true` and confirmation `WRITE REPUTATION`.
- Player faction-change planning through `POST /api/admin/faction`, default `dry_run=true`. Execution requires `DUNE_ADMIN_FACTION_MUTATIONS_ENABLED=true`, confirmation `CHANGE FACTION`, and an offline target player.
- Journey story-node planning through `POST /api/admin/journey`, default `dry_run=true`. Execution requires `DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED=true`, confirmation `WRITE JOURNEY`, and an offline target player.
- Landsraad term planning through `POST /api/admin/landsraad`, default `dry_run=true`. Execution requires `DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED=true` and confirmation `WRITE LANDSRAAD`.
- Respawn-location delete planning through `POST /api/admin/respawn-location`, default `dry_run=true`. Execution requires `DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED=true`, confirmation `DELETE RESPAWN`, and an offline target player.
- World-state inspection through `POST /api/admin/world-state/inspect` for guild, vehicle, marker, landclaim, recipe, and respawn evidence.
- Guild description and role planning through `POST /api/admin/guild`, default `dry_run=true`. Execution requires `DUNE_ADMIN_GUILD_MUTATIONS_ENABLED=true` and confirmation `WRITE GUILD`.
- Marker deletion planning through `POST /api/admin/marker`, default `dry_run=true`. Execution requires `DUNE_ADMIN_MARKER_MUTATIONS_ENABLED=true` and confirmation `DELETE MARKERS`.
- Landclaim segment planning through `POST /api/admin/landclaim`, default `dry_run=true`. Execution requires `DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED=true` and confirmation `WRITE LANDCLAIM`.
- Economy inspection through `POST /api/admin/economy/inspect` for Dune Exchange, vehicle, recovered/backup vehicle, and base-backup evidence.
- Dune Exchange Solari planning through `POST /api/admin/exchange`, default `dry_run=true`. Execution requires `DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED=true` and confirmation `WRITE EXCHANGE`.
- Player lifecycle inspection through `POST /api/admin/player-lifecycle/inspect` for account/player, party, tags, access codes, Communinet, dungeon, tutorial, and lifecycle evidence.
- Player tag planning through `POST /api/admin/player-tags`, default `dry_run=true`. Execution requires `DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED=true` and confirmation `WRITE PLAYER TAGS`.
- Access-code planning through `POST /api/admin/access-code`, default `dry_run=true`. Execution requires `DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED=true` and confirmation `WRITE ACCESS CODES`.
- Character slot inspection and planning through `GET /api/admin/character-slots?account_id=...`, `POST /api/admin/character-slots/plan`, and `POST /api/admin/character-slots/execute`, default `dry_run=true`. Execution requires `DUNE_ADMIN_CHARACTER_SWAP_ENABLED=true`, confirmation `SWAP CHARACTER`, offline targets, a DB backup, and a proven native lifecycle contract; current builds are inspect/plan-only when that contract is absent.
- Communinet planning through `POST /api/admin/communinet`, default `dry_run=true`. Execution requires `DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED=true` and confirmation `WRITE COMMUNINET`.
- Tutorial entry planning through `POST /api/admin/tutorial`, default `dry_run=true`. Execution requires `DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED=true` and confirmation `WRITE TUTORIAL`.
- Permission actor planning through `POST /api/admin/permission`, default `dry_run=true`. Execution requires `DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED=true` and confirmation `WRITE PERMISSION`.
- Vendor stock-cycle timestamp planning through `POST /api/admin/vendor`, default `dry_run=true`. Execution requires `DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED=true` and confirmation `WRITE VENDOR`.
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
- Player dropdowns in Admin Actions for currency, carried/bank Solari, XP, keystones, item grant targeting, and item maintenance.
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

For the current actionability split, read [`admin-actionability-matrix.md`](admin-actionability-matrix.md). Confidence is high that every write-capable endpoint listed there is dry-run-first and gate-protected; confidence varies by game-system side effect.

The safe-surface test suite now includes mocked dry-run and fail-closed checks for the promoted mutator families. These tests prove the admin code plans writes and refuses execution when gates are disabled; they do not prove live client-visible game behavior. Use the disposable validation queue in [`admin-actionability-matrix.md`](admin-actionability-matrix.md) before routine use on real player/world state.

```env
DUNE_ADMIN_CATALOG_ENABLED=true
DUNE_ADMIN_TYPED_KNOBS_ENABLED=false
DUNE_ADMIN_EVENT_EXECUTION_ENABLED=false
DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=false
DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED=false
DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED=false
DUNE_ADMIN_FACTION_MUTATIONS_ENABLED=false
DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED=false
DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED=false
DUNE_ADMIN_GUILD_MUTATIONS_ENABLED=false
DUNE_ADMIN_MARKER_MUTATIONS_ENABLED=false
DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED=false
DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED=false
DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED=false
DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED=false
DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED=false
DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED=false
DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED=false
DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED=false
DUNE_ADMIN_CHARACTER_SWAP_ENABLED=false
```

Gate behavior:

- `DUNE_ADMIN_CATALOG_ENABLED`: controls read-only catalog endpoints.
- `DUNE_ADMIN_TYPED_KNOBS_ENABLED`: controls typed config writes only. Typed dry-runs still work.
- `DUNE_ADMIN_EVENT_EXECUTION_ENABLED`: controls event execution. Event creation and dry-run planning still work.
- `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED`: controls economy bundle execution. Bundle dry-runs still work.
- `DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED`: controls faction reputation writes through `dune.set_player_faction_reputation`. Progression inspection and reputation dry-runs still work.
- `DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED`: controls journey server-function calls. Journey dry-runs still work.
- `DUNE_ADMIN_FACTION_MUTATIONS_ENABLED`: controls player faction-change server-function calls. Faction dry-runs still work.
- `DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED`: controls Landsraad term server-function calls. Landsraad dry-runs still work.
- `DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED`: controls respawn-location deletion through `dune.update_respawn_locations`. Respawn dry-runs still work.
- `DUNE_ADMIN_GUILD_MUTATIONS_ENABLED`: controls guild description and role server-function calls. Guild dry-runs still work.
- `DUNE_ADMIN_MARKER_MUTATIONS_ENABLED`: controls marker deletion server-function calls. Marker dry-runs still work.
- `DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED`: controls landclaim segment server-function calls. Landclaim dry-runs still work.
- `DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED`: controls Dune Exchange Solari balance server-function calls. Economy dry-runs still work.
- `DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED`: controls player tag server-function calls. Lifecycle dry-runs still work.
- `DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED`: controls server player access-code server-function calls. Lifecycle dry-runs still work.
- `DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED`: controls Communinet player/channel server-function calls. Lifecycle dry-runs still work.
- `DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED`: controls tutorial entry server-function calls. Lifecycle dry-runs still work.
- `DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED`: controls permission actor name/access/rank server-function calls. World-state dry-runs still work.
- `DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED`: controls vendor stock-cycle timestamp server-function calls. Lifecycle dry-runs still work.
- `DUNE_ADMIN_CHARACTER_SWAP_ENABLED`: controls character slot hibernation/switch execution. Slot inspection and planning still work; execution remains blocked unless the plan returns `executable: true`.
- `DUNE_ADMIN_GRANT_PRIVATE_MESSAGE_ENABLED`: controls best-effort private relog reminders after successful admin item and inventory-Solari grants.
- `DUNE_ADMIN_GRANT_PRIVATE_MESSAGE_TEMPLATE`: private relog reminder template. Supports `{item}`, `{amount}`, and `{template_id}`.

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
WRITE REPUTATION
WRITE JOURNEY
CHANGE FACTION
WRITE LANDSRAAD
DELETE RESPAWN
WRITE GUILD
DELETE MARKERS
WRITE LANDCLAIM
WRITE EXCHANGE
WRITE PLAYER TAGS
WRITE ACCESS CODES
WRITE COMMUNINET
WRITE TUTORIAL
WRITE PERMISSION
WRITE VENDOR
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
| `characterRecustomizationCost` | `UserGame.ini` | `[/Script/DuneSandbox.CharacterRecustomizerSubsystem] m_CostAmount` | high | low |
| `buildingShelterThreshold` | `UserGame.ini` | `[/Script/DuneSandbox.ShelterSettings] m_BuildingShelterThreshold` | moderate | experimental |
| `placeableShelterThreshold` | `UserGame.ini` | `[/Script/DuneSandbox.ShelterSettings] m_PlaceableShelterThreshold` | moderate | experimental |
| `shelteredProtectionThreshold` | `UserGame.ini` | `[/Script/DuneSandbox.HydrationSubsystem] ShelteredProtectionThreshold` | low | experimental |

Typed writes create a backup under `backups/admin-panel` before writing the config file. Most of these values require restarting the affected map containers.

Character recustomization is currently overridden to `0` in `config/UserGame.ini`, making it free instead of the shipped/default `5000` Solaris. Use the `characterRecustomizationCost` typed knob to restore or tune the cost.

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

`POST /api/admin/player-recovery/offline-teleport` previews or executes a strict-offline pawn move. It backs the Admin Actions Offline Teleport panel, which lets an operator pick a player, choose a partition, enter exact coordinates, or click the Hagga Basin map to fill rough X/Y coordinates.

The endpoint calls the shipped database helper below. This is the verified primitive for the network-disconnect teleport path once Survival has marked the player `Offline`, because it updates the pawn actor row consumed by reconnect:

```sql
dune.admin_move_offline_player_to_partition(
  in_fls_id text,
  in_target_partition_id bigint,
  in_target_location dune.vector
)
```

The endpoint does not force a disconnect and does not hide the timeout-based online-adjacent workflow. Operators must make the target truly `Offline` first, either by waiting for a normal logout or by using the documented network-timeout runbook. That workflow remains separate in [soft-disconnect-teleport.md](soft-disconnect-teleport.md).

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

## Progression Inspection and Reputation

`POST /api/admin/progression/inspect` is the read-only evidence collector for player progression work. With an `account_id`, it returns current player faction/reputation rows. It also introspects `pg_proc` and `information_schema.columns` for journey, recipe, vehicle, faction, and reputation surfaces.

`POST /api/admin/faction-reputation` plans a faction reputation mutation through `dune.set_player_faction_reputation`. Default dry-run body:

```json
{
  "dry_run": true,
  "account_id": 456,
  "faction_id": 1,
  "amount": 100,
  "mode": "add"
}
```

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED=true`
- `confirm: "WRITE REPUTATION"`

The endpoint checks the live table shape and confirms the server-provided setter before planning or writing. It only recognizes `actor_id`, `faction_id`, and one of `reputation`, `reputation_amount`, `amount`, or `value` as the reputation value column. Confidence is moderate-to-high when `dune.set_player_faction_reputation` is present; still validate execution on disposable/offline character data before routine use.

`POST /api/admin/faction` plans or executes first-party faction changes through `dune.change_player_faction`.

Dry-run body:

```json
{
  "dry_run": true,
  "account_id": 456,
  "faction_id": 1,
  "neutral_faction_id": 3
}
```

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_FACTION_MUTATIONS_ENABLED=true`
- `confirm: "CHANGE FACTION"`
- target player must be offline

The live schema currently has `dune.factions` rows for `1=Atreides`, `2=Harkonnen`, `3=None`, and `4=Smuggler`. Confidence is moderate because the faction-change function is first-party; guild side effects and client refresh behavior still need disposable-character validation.

`POST /api/admin/landsraad` plans or executes Landsraad term administration. Supported actions are `change-end-time` and `force-end`.

Dry-run body:

```json
{
  "dry_run": true,
  "action": "change-end-time",
  "term_id": 1,
  "new_end_time": "2026-05-26 04:55:00",
  "test_term": false
}
```

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED=true`
- `confirm: "WRITE LANDSRAAD"`

The endpoint reads `dune.landsraad_load_current_term()` and recent `dune.landsraad_decree_term` rows before planning. End-time changes are reversible by writing the previous `end_time`; `force-end` is not safely reversible. Confidence is moderate for function mechanics and high that the action is world-impacting.

`POST /api/admin/respawn-location` plans or executes deletion of one known respawn location by UUID.

Dry-run body:

```json
{
  "dry_run": true,
  "action": "delete",
  "account_id": 456,
  "respawn_id": "0a0556f6-a387-41f2-b613-deacee4e2bd0"
}
```

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED=true`
- `confirm: "DELETE RESPAWN"`
- target player must be offline

The endpoint verifies the UUID against `dune.player_respawn_locations` and then re-saves `dune.get_respawn_locations(account_id)` without that entry through `dune.update_respawn_locations`. Confidence is moderate for deletion mechanics and low for creation/editing, so creation and arbitrary edits remain blocked.

`POST /api/admin/world-state/inspect` reads guild, vehicle, marker, landclaim, recipe, and respawn evidence without writing. It accepts optional `account_id`, `player_id`, and `guild_id`, resolves missing player/guild IDs when possible, and returns matching `pg_proc` functions plus table/column metadata.

`POST /api/admin/guild` plans or executes narrow guild administration. Supported actions are `edit-description`, `promote-member`, and `demote-member`.

Dry-run body:

```json
{
  "dry_run": true,
  "action": "edit-description",
  "guild_id": 789,
  "description": "Updated guild note"
}
```

Role-change dry-run body:

```json
{
  "dry_run": true,
  "action": "promote-member",
  "guild_id": 789,
  "player_id": 123,
  "new_role": 1
}
```

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_GUILD_MUTATIONS_ENABLED=true`
- `confirm: "WRITE GUILD"`

The endpoint uses `dune.edit_guild_description`, `dune.promote_guild_member`, and `dune.demote_guild_member`. Confidence is moderate because the functions are first-party and rollback is a compensating call from the dry-run/audit record. Disband, invite, remove-member, create-guild, and allegiance operations remain blocked.

`POST /api/admin/marker` plans or executes marker deletion. Supported actions are `delete-by-id` and `delete-static-location`.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_MARKER_MUTATIONS_ENABLED=true`
- `confirm: "DELETE MARKERS"`

The endpoint uses `dune.delete_markers_by_id` and `dune.delete_static_location_markers`. Confidence is moderate for deletion mechanics and low for rollback because marker recreation/payload semantics are not fully mapped.

`POST /api/admin/landclaim` plans or executes adding one landclaim segment to a known totem id.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED=true`
- `confirm: "WRITE LANDCLAIM"`

The endpoint uses `dune.get_landclaim_segments` for preflight and `dune.add_landclaim_segment` for execution. Confidence is low-to-moderate because the local table is empty and no delete-segment rollback function is mapped.

`POST /api/admin/economy/inspect` reads Dune Exchange, vehicle, recovered/backup vehicle, and base-backup evidence without writing. It accepts optional `account_id`, `player_id`, `controller_id`, and `exchange_id`, and returns matching `pg_proc` functions plus table/column metadata.

`POST /api/admin/exchange` plans or executes Dune Exchange Solari balance changes. Supported modes are `add` and `set`.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED=true`
- `confirm: "WRITE EXCHANGE"`

The endpoint uses `dune.dune_exchange_retrieve_solari_balance` for preflight and `dune.dune_exchange_modify_user_solari_balance` for execution. Confidence is moderate for the balance mechanics and low for order operations, so add/fulfill/cancel/relist/retrieve/purge order functions remain blocked.

`POST /api/admin/solari/inventory` grants Solari to a player's carried inventory as a fresh `SolarisCoin` item stack in a free slot. It accepts `inventory_id` directly, or resolves a player inventory from `account_id` / `character_name`.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `confirm: "GRANT SOLARI"`

`POST /api/admin/solari/bank` grants Solari to the player's Exchange/bank balance. It accepts `owner_id` and `controller_id` directly, or resolves them from `account_id` / `character_name`. The write delegates to `dune.dune_exchange_modify_user_solari_balance`.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED=true`
- `confirm: "WRITE EXCHANGE"`

### Reproducible Item Grants

Use `scripts/admin-grant-item.py` when an operator needs a repeatable backend item grant outside the browser. It resolves reviewed display names through `config/artificial-exchange-prices.csv`, prints a dry-run plan by default, and only writes when `--execute --confirm "GRANT ITEM"` are both present.

Examples:

```bash
./scripts/admin-grant-item.py "Complex Machinery" 2 --character Lukano
./scripts/admin-grant-item.py "Complex Machinery" 2 --character Lukano --execute --confirm "GRANT ITEM"
```

Known machinery labels:

| Display label | Server template ID | Confidence |
| --- | --- | --- |
| Complex Machinery | `T2MachineComponent` | high |
| Advanced Machinery | `T6Machinery` | high |

The script targets carried inventory type `0` by default, chooses a free slot, and calls `dune.save_item(dune.inventoryitem)`. Use `--inventory-id` for an exact container, `--inventory-type` for a different resolved inventory type, or `--position` for an exact free slot. Live grants are additive: each execution creates a new stack and does not declare the player's full inventory state.

`POST /api/admin/player-lifecycle/inspect` reads account/player, party, tag, access-code, Communinet, dungeon, tutorial, and lifecycle evidence without writing.

`POST /api/admin/player-tags` plans or executes player tag add/remove calls through `dune.update_player_tags`.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED=true`
- `confirm: "WRITE PLAYER TAGS"`

Confidence is moderate. Rollback is the inverse add/remove set from the dry-run/audit record.

`POST /api/admin/access-code` plans or executes server player access-code create/delete/reset calls.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED=true`
- `confirm: "WRITE ACCESS CODES"`

The endpoint uses `dune.get_player_access_codes`, `dune.create_server_player_access_codes`, `dune.delete_server_player_access_codes`, and `dune.reset_server_all_player_access_codes`. Confidence is moderate for function mechanics and high for operational risk because reset needs manual recreation from audit data.

## Character Slots

Character slot tooling is admin-only and inspect/plan-first. It is built for three operator intents:

- `new-character`: hibernate the current active character and let the game run its native character creator on next login.
- `switch-character`: make a previously hibernated, same-owner character active again.
- `restore-character`: same safety model as switch, used when returning to a prior hibernated character.

Endpoints:

```text
GET /api/admin/character-slots?account_id=456
POST /api/admin/character-slots/plan
POST /api/admin/character-slots/execute
```

`GET /api/admin/character-slots` returns:

- `activeCharacter`: the current `dune.player_state` row joined to account identity fields.
- `offline`: whether the active character is offline.
- `candidates`: same-owner native candidate characters matched through account user/Funcom/platform identity.
- `contract`: discovered lifecycle functions and identity table metadata.
- `executionGate`: `DUNE_ADMIN_CHARACTER_SWAP_ENABLED`.
- `confirm`: `SWAP CHARACTER`.

Executable switch/restore plans include `plan.transactionSafety`, which records
that execution creates a backup before the transaction, takes account-id
advisory locks, locks both underlying `encrypted_player_state` and
`encrypted_accounts` rows, rechecks offline state inside the transaction, and
requires post-swap identity verification before commit.

Safe preview examples:

```json
{
  "dry_run": true,
  "account_id": 456,
  "action": "new-character"
}
```

```json
{
  "dry_run": true,
  "account_id": 456,
  "action": "switch-character",
  "target_account_id": 789
}
```

Safe HTTP smoke checks:

```bash
curl -sS "http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/api/admin/character-slots?account_id=456" \
  | jq '.accountId, .offline, .candidates, .contract.safeNativeSwapPath'

curl -sS -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/api/admin/character-slots/plan \
  -d '{"dry_run":true,"account_id":456,"action":"new-character"}' \
  | jq '.dryRun, .executable, .plan.blockers'
```

CLI workflow:

Find accounts that actually have same-owner slot candidates:

```bash
python3 scripts/character-slot-tool.py \
  --action scan \
  --summary \
  --pretty
```

```bash
python3 scripts/character-slot-tool.py \
  --account-id 456 \
  --action inspect \
  --summary \
  --pretty
```

```bash
python3 scripts/character-slot-tool.py \
  --account-id 456 \
  --action switch-character \
  --target-account-id 789 \
  --summary \
  --pretty
```

```bash
python3 scripts/character-slot-tool.py \
  --account-id 456 \
  --action switch-character \
  --target-account-id 789 \
  --execute \
  --confirm "SWAP CHARACTER" \
  --pretty
```

The CLI reads `DUNE_ADMIN_HOST_PORT` and `DUNE_ADMIN_TOKEN` from `.env` by
default. Use `--base-url` or `--token` to override them.

Execution remains blocked unless the plan reports `executable: true`. Current contract discovery treats `dune.takeover_account(in_user_to_takeover text, in_current_user text)` as the only executable native switch/restore path. It swaps the active login identity onto the selected same-owner hibernated character and moves that target identity onto the current character account. Confidence: moderate.

`new-character` execution remains blocked. The mapped native blank-character path is `delete_account(in_user_id, in_reason)`, and that function deletes the current account/actors instead of hibernating them. DASH does not use it for character-slot creation. Confidence: high.

Non-dry-run execution requires all of:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_CHARACTER_SWAP_ENABLED=true`
- `confirm: "SWAP CHARACTER"`
- the active account and selected target are offline
- the action is `switch-character` or `restore-character`
- the plan returns `executable: true`
- a DB backup can be created before any native lifecycle call

Execution behavior:

- creates a Postgres backup first
- opens one DB transaction, takes account-id advisory locks, locks both underlying `encrypted_player_state` and `encrypted_accounts` rows, and aborts before mutation if either came online
- audits before/after rows for the active and target account ids
- calls only `select dune.takeover_account(target_fls_id, active_fls_id)`
- verifies that the active and target FLS identities swapped as expected
- returns an inverse restore payload and backup path

Blocked behavior is intentional. The panel does not create synthetic starter rows, does not overwrite raw `player_state`, and does not execute account deletion or save-player functions as a guessed swap mechanism.

Test coverage includes direct planner tests and handler-route tests for `GET /api/admin/character-slots`, `POST /api/admin/character-slots/plan`, and dry-run/blocked `POST /api/admin/character-slots/execute`. The tests verify that blocked execution does not call SQL write helpers or create a backup.

`POST /api/admin/communinet` plans or executes Communinet active/selected-channel and per-channel tuned state.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED=true`
- `confirm: "WRITE COMMUNINET"`

The endpoint uses `dune.load_communinet_player_data`, `dune.update_communinet_player_data`, `dune.update_communinet_player_channel`, and `dune.remove_communinet_player_channel`. Confidence is moderate. Vendor stock, tutorial, lore, dungeon, overmap, and Coriolis writes remain blocked.

`POST /api/admin/tutorial` plans or executes one tutorial state update for a player through `dune.create_or_update_tutorial_entry`.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED=true`
- `confirm: "WRITE TUTORIAL"`

Confidence is moderate. Bulk tutorial deletion and tutorial registration remain blocked.

`POST /api/admin/permission` plans or executes permission actor name/access/rank changes.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED=true`
- `confirm: "WRITE PERMISSION"`

The endpoint uses `dune.permission_set_name`, `dune.permission_set_access_level`, `dune.permission_set_player_rank`, and `dune.permission_remove_player_rank`. Confidence is moderate mechanically and high risk operationally because these calls affect base/actor access.

`POST /api/admin/vendor` plans or executes one vendor/player stock-cycle timestamp update.

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED=true`
- `confirm: "WRITE VENDOR"`

The endpoint uses `dune.update_vendor_timestamp_for_player` and reads `dune.interact_get_vendor_items_bought_from_player` for dry-run context. Confidence is moderate for timestamp mechanics. Purchase-count and stock-cleanup writes remain blocked.

`POST /api/admin/journey` plans or executes journey story-node server functions. Supported actions are `reveal`, `complete`, `reset`, and `delete`.

Dry-run body:

```json
{
  "dry_run": true,
  "account_id": 456,
  "action": "reveal",
  "story_node_ids": ["ExampleStoryNode"]
}
```

Execution requires:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED=true`
- `confirm: "WRITE JOURNEY"`
- target player must be offline

The endpoint uses `dune.admin_get_journey_details` for preflight details and then calls the matching server function: `reveal_journey_story_nodes_for_player`, `complete_journey_story_nodes_for_player`, `reset_journey_story_nodes_for_player`, or `delete_journey_story_nodes_for_player`. Confidence is moderate because the functions are first-party DB functions; story-node IDs and reward semantics still need a local reference catalog.

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

Admin chat and private player-message routing have a separate focused target:

```bash
make test-admin-chat
```

That target runs the chat-command parser/reply tests plus the player-presence private whisper routing test.

Current coverage:

- Catalog schema and groups.
- Catalog evidence and validation payloads.
- Catalog disabled-gate refusal.
- Read-only inspector mutator metadata for progression, world state, economy, player lifecycle, and spice fields.
- Typed knob value validation.
- Typed config writes with backups in a temporary workspace.
- Deep Desert spice cap rendering from structured JSON.
- Event dry-run planning.
- Event persistence and cancellation.
- Event execution blocked by default.
- Character-slot discovery, dry-run behavior, online-player refusal, and missing native-contract blockers.
- Dry-run planning and fail-closed gates for promoted mutator families.

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

`scripts/admin-chat-commands.py` is the DASH chat-command bridge. It listens only for private whispers/PMs sent to Paul that start with `DUNE_CHAT_COMMAND_PREFIX`, resolves the sending account through `dune.accounts.user`, and only accepts commands from configured admins. Map, proximity, party, and guild chat are not command input channels.

Default command settings:

```env
DUNE_CHAT_COMMAND_PREFIX=&
DUNE_CHAT_COMMAND_ADMINS=AdminUser
DUNE_CHAT_COMMAND_ADMIN_FLS_IDS=TEST_FLS_ID
DUNE_CHAT_COMMAND_DRY_RUN=true
DUNE_CHAT_COMMAND_EXECUTE_TELEPORT=false
DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=false
DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT=false
DUNE_CHAT_COMMAND_AUCTION_ENABLED=false
DUNE_CHAT_COMMAND_AUCTION_BASE_STORAGE_ENABLED=false
DUNE_CHAT_COMMAND_AUCTION_EXCHANGE_ID=2
DUNE_CHAT_COMMAND_AUCTION_ACCESS_POINT_ID=1
DUNE_CHAT_COMMAND_AUCTION_MAX_ORDERS_PER_PLAYER=50
DUNE_CHAT_COMMAND_AUCTION_LISTING_FEE=0
DUNE_CHAT_COMMAND_AUCTION_DURATION_SECONDS=2419200
DUNE_CHAT_COMMAND_AUCTION_CATEGORY_MASK=0
DUNE_CHAT_COMMAND_AUCTION_CATEGORY_DEPTH=0
DUNE_CHAT_COMMAND_AUCTION_CONFIRM_SECONDS=120
DUNE_CHAT_COMMAND_AUCTION_SUGGESTION_MIN_SCORE=0.55
DUNE_CHAT_COMMAND_EXCHANGE_CASHOUT_ENABLED=false
DUNE_CHAT_COMMAND_EXCHANGE_CASHOUT_LIMIT=50
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
DUNE_CHAT_COMMAND_EXCHANGE=chat.whispers
DUNE_CHAT_COMMAND_EXCHANGES=chat.whispers
DUNE_CHAT_COMMAND_QUEUE=dash_admin_chat_commands
DUNE_CHAT_COMMAND_ROUTING_KEY=ADMIN#00001
DUNE_CHAT_COMMAND_BIND_ROUTING_KEYS=ADMIN#00001
DUNE_CHAT_COMMAND_AMQP_HOST=game-rmq
DUNE_CHAT_COMMAND_AMQP_PORT=5672
DUNE_CHAT_COMMAND_AMQP_TLS=true
DUNE_CHAT_COMMAND_AMQP_RETRY_SECONDS=5
DUNE_CHAT_COMMAND_AMQP_CONNECT_ATTEMPTS=0
DUNE_CHAT_COMMAND_AMQP_USER=guest
DUNE_CHAT_COMMAND_AMQP_PASSWORD=guest
DUNE_CHAT_COMMAND_REPLY_COMMAND=/workspace/scripts/announce.sh
DUNE_CHAT_COMMAND_PRIVATE_REPLIES_ENABLED=true
DUNE_CHAT_COMMAND_PRIVATE_REPLY_EXCHANGE=chat.whispers
DUNE_CHAT_COMMAND_PRIVATE_REPLY_CHANNEL=Whispers
DUNE_CHAT_COMMAND_PRIVATE_REPLY_ROUTING_KEY=
DUNE_CHAT_COMMAND_TARGET_REPLY_MODE=whisper
DUNE_CHAT_COMMAND_TARGET_REPLY_EXCHANGE=chat.proximity
DUNE_CHAT_COMMAND_TARGET_REPLY_CHANNEL=Proximity
DUNE_CHAT_COMMAND_TARGET_REPLY_ROUTING_KEY=
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
&list
&inv_list
&where <playername>
&disconnect <playername>
&kick <playername>
&auction [--base|--inventory <inventory_id>] [--item-id <item_id>|"<item name or template>"] <count> <price>
&exchange_list [limit]
&exchange_cashout
&teleport <playername>
&teleport list|locations
&teleport set <slot> [name]
&teleport replace <slot> [name]
&teleport delete|rm <slot>
&teleport <playername> <slot>
&teleport <slot>
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

`&list` replies to the sender with all currently online players formatted as `Player (Map)`. It also accepts `&players` and `&online`.

`&inv_list` replies to the sender with their personal inventory stacks, including `code=<template_id>` and `item-id=<item_id>` for auction listing. Players can use `&auction --item-id <item-id> <count> <price>` for an exact stack, or `&auction "<item code/template>" <count> <price>` for template matching. Bare `&auction` replies with the syntax and the same inventory list.

`&exchange_list [limit]` replies to the sender with their own active player exchange sales without requiring travel to Arrakeen. It filters orders to the sender's player controller, excludes NPC orders, and excludes fulfilled orders when the fulfilled-order table is present.

`&exchange_cashout` claims the sender's completed seller Solari settlements through the same validated settlement path used by `scripts/artificial-exchange-bot.py`: it locks each completed seller-claim row, credits the sender's Solaris balance by `item_price * stack_size`, deletes the completed claim order, and validates that the order is gone and the credited amount matches. It previews by default; set `DUNE_CHAT_COMMAND_EXCHANGE_CASHOUT_ENABLED=true` to execute from chat. The batch size defaults to `DUNE_CHAT_COMMAND_EXCHANGE_CASHOUT_LIMIT=50`.

`&where` reports the resolved player's current online/offline state and last known location. `&teleport <playername>` moves an offline target to the admin's current partition and location. Live actor transforms are owned by the running map server and can be overwritten, so raw online actor updates are not a teleport path.

Shared numbered teleport slots live in `backups/admin-panel/teleport-slots.json`. `&teleport set <slot> [name]` saves the issuing admin's current location only when the slot is empty; if occupied, it reports the current slot and next free number. Use `&teleport replace <slot> [name]` to overwrite, `&teleport list` to show slots in numeric order, and `&teleport delete <slot>` to remove a slot. `&teleport <playername> <slot>` moves a strict-offline target to the saved slot through `dune.admin_move_offline_player_to_partition(...)`; `&teleport <slot>` prepares or sends a gated native `TeleportToExact` for the issuing admin.

Recommended city slots are operator-created, not seeded: stand in Arrakeen and run `&teleport set 0 arrakeen`; stand in Harko Village and run `&teleport set 1 harko`.

The verified online-adjacent fallback is network-disconnect teleport: force a real connection timeout, wait until Survival marks the player `Offline`, call `dune.admin_move_offline_player_to_partition(...)`, then let the client reconnect and load the moved pawn. DB-only presence flips are not sufficient. The full contract is in [soft-disconnect-teleport.md](soft-disconnect-teleport.md).

`&auction "<item name or template>" <count> <price>` is a player-facing exchange listing command. It does not require admin allow-list membership, but only operates for the sender's own resolved character. Use `--item-id <item_id>` when the operator already knows the exact item row and wants to bypass fuzzy name/template matching. By default the command previews the listing and does not mutate the database. Set `DUNE_CHAT_COMMAND_AUCTION_ENABLED=true` to execute. The command uses `dune.dune_exchange_add_sell_order(...)`, so the order is owned by the sender's player controller and should use the normal exchange seller settlement path. Confidence: moderate until a live purchase settlement has been validated.

Auction item matching searches the sender's pawn/controller inventories by normalized template/name text and requires a single stack with at least `<count>` items. Use `--base` to search permitted shared base storage, or `--inventory <inventory_id>` to target a specific personal/permitted base inventory. Base and explicit-storage sources require `DUNE_CHAT_COMMAND_AUCTION_BASE_STORAGE_ENABLED=true`; otherwise they are rejected. Split-across-stacks listings are not supported.

If no exact/contains match is found, the command scores allowed inventory items and replies with `did you mean <template>? reply &auction yes or &auction no` when the best score is at least `DUNE_CHAT_COMMAND_AUCTION_SUGGESTION_MIN_SCORE`. The pending suggestion expires after `DUNE_CHAT_COMMAND_AUCTION_CONFIRM_SECONDS`. Confirmation state is held in the running chat listener process, so it works in service mode but not across separate one-shot `--dry-run-command` invocations.

Private command replies are supported through the direct player-queue path documented in [private-chat-replies.md](private-chat-replies.md). The working client-visible form is `m_ChannelType=Whispers` plus the exact `m_TimeStamp` field name. Confidence: high.

Private-chat investigation found a real `chat.whispers` direct exchange and a required TextRouter redirect header, `redirect_exchange`, whose AMQP value must be bytes, for example `b"chat.whispers"`. The TextRouter binary also confirms private player queue names are `{FLS_ID}_queue` and private RPC queue names are `{FLS_ID}_rpcQueue`.

Current confidence: high for exchange/header/queue naming and client-visible private rendering through a direct player-queue publish. Direct `chat.whispers` and direct queue publishes can be delivered to RabbitMQ. The client-visible private form uses `m_ChannelType=Whispers` and the exact `m_TimeStamp` field name; the earlier `m_Timestamp` payload was consumed but silently ignored by the client. Operator confirmation showed `fieldfix 204311 timeS-whispers` rendered in the private/whisper color. Intercepted synthetic whispers with no AMQP `user_id` reach TextRouter but fail `DemoPlayersFilter` with `ArgumentNullException`; intercepted synthetic whispers with `user_id` pass redirect permission checks but TextRouter republishes with the original `user_id` while authenticated as its router account, causing RabbitMQ `PRECONDITION_FAILED`.

Online research on 2026-05-20 did not find a public self-host recipe for injecting client-visible private whispers. GitHub code search found no Dune-specific use of `chat.whispers`, `redirect_exchange`, `send-whisper-probe.py`, or this repo's private-reply toggles. General web/Steam/community-wiki searches found private-chat references but no RabbitMQ/TextRouter implementation details. The useful external signal is official/community patch-note evidence for update `1.3.20.0` on 2026-04-28: one fix says muted players receive a whisper notification, and another says private chat messages could fail to show after opening chat directly into the private tab. That confirms the client has a real private-message display path, and also that display behavior has been buggy. Confidence: high that private chat exists in the product; low that anyone has publicly documented a working self-host injection path.

Deeper local decompilation found a TextRouter launch knob: `--RMQCredentials <username>:<password>`. In normal mode TextRouter authenticates to RabbitMQ as a generated `tr.<battlegroup>.<correlation>` user. Intercepted messages keep the original AMQP `user_id` when TextRouter republishes them, so RabbitMQ rejects the publish when `user_id` differs from the authenticated router user. In fixed-credential mode, TextRouter also enables battlegroup-prefixed exchange names such as `<world>_chat.intercept` and `<world>_chat.whispers`.

Experimental result on 2026-05-20: TextRouter was temporarily restarted with fixed `guest` credentials, a synthetic message was published to the battlegroup-prefixed intercept exchange with AMQP `user_id=guest`, and TextRouter successfully redirected four variants to `chat.whispers` without `PRECONDITION_FAILED`: `prefixed-fixed-tr 203132 Map`, `prefixed-fixed-tr 203132 Whisper`, `prefixed-fixed-tr 203132 Private`, and `prefixed-fixed-tr 203132 Whispers`. Temporary target-queue bindings were removed afterward and TextRouter was restored to its normal compose command. These did not render for the operator, so fixed TextRouter credentials are not required for the working direct-queue path.

Use `scripts/send-whisper-probe.py` for repeatable tests. The probe uses the working `m_TimeStamp` spelling:

```bash
scripts/send-whisper-probe.py --target-name SamplePlayer --target-fls-id TEST_FLS_ID --bind-target-queue --send-intercept --message-prefix "probe $(date +%H%M%S)"
```

Capture a real client whisper with:

```bash
scripts/capture-chat-routing.py --seconds 120 \
  --routing-key '#' \
  --routing-key TEST_FLS_ID \
  --routing-key SamplePlayer \
  --routing-key 36A0226630A5875 \
  --routing-key Talon \
  --routing-key EC8C54C4BB4463D9 \
  --routing-key Xale \
  --routing-key HaggaBasin.0 \
  --routing-key Survival_1.dim_0
```

Then compare the real payload's exchange, routing key, AMQP properties, `redirect_exchange` header, outer `Type`, and inner `m_ChannelType`/`m_UserNameTo` against probe output.

The working private reply path is also documented as a standalone runbook in [private-chat-replies.md](private-chat-replies.md). Keep that file updated when changing `scripts/announce.sh`, `scripts/send-whisper-probe.py`, or chat-command reply routing.

Additional channel probes are available through `scripts/send-chat-channel-probe.py`. This sends labeled `Proximity`, `Guild`, `Faction`, and optional `Party` messages as both direct exchange publishes and TextRouter intercept redirects:

```bash
scripts/send-chat-channel-probe.py --target-name SamplePlayer --target-fls-id TEST_FLS_ID --guild-id 1 --faction-id 3 --message-prefix "chan-native $(date +%H%M%S)"
scripts/send-chat-channel-probe.py --target-name SamplePlayer --target-fls-id TEST_FLS_ID --guild-id 1 --faction-id 3 --bind-target-queue --message-prefix "chan-bound $(date +%H%M%S)"
```

Live findings: the test player's player controller `17` is in guild `1`; no active party row was present during testing. Direct `chat.proximity`, `chat.guild.1`, and `chat.faction.3` publishes with temporary target-queue bindings reached RabbitMQ and were delivered to the player queue, then the bindings were removed. Operator confirmation reported proximity and guild messages rendered in the client. TextRouter intercept redirects without `user_id` fail permission checks; redirects with `user_id` pass permission for `chat.proximity` but hit the same RabbitMQ `PRECONDITION_FAILED` republish issue seen with whispers.

For command replies, set `DUNE_CHAT_COMMAND_TARGET_REPLY_MODE=whisper` and `DUNE_CHAT_COMMAND_PRIVATE_REPLY_CHANNEL=Whispers` to reply through `chat.whispers`. The route is deterministic: `scripts/dune_whisper_route.py` derives routing key `<FLS_ID>` and queue `<FLS_ID>_queue`, so no player-created whisper is required after reboot. Command responses generated inside `handle_command()` infer the issuing player as the target when the sender FLS id is known, so admin command results and errors stay private by default. Returned command JSON includes `reply.stdout` from `scripts/announce.sh`; private replies should show `transport=chat.whispers` and `exchange=chat.whispers`. Set `DUNE_CHAT_COMMAND_TARGET_REPLY_MODE=proximity` to use `chat.proximity`, or set `DUNE_CHAT_COMMAND_TARGET_REPLY_MODE=guild` and `DUNE_CHAT_COMMAND_TARGET_REPLY_EXCHANGE=chat.guild.<id>` to use a confirmed guild exchange. The command listener sets `DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS=true` for these targeted replies so the temporary binding is removed after publish. Spam-protection action announcements are intentionally outside command context and remain global when `DUNE_CHAT_SPAM_ANNOUNCE_ACTION=true`.

The complete private/global split, command smoke tests, expected `reply.stdout` shape, and stale-binding checks live in [private-chat-replies.md](private-chat-replies.md). Run `make test-admin-chat` after changing command reply routing, `scripts/announce.sh`, or player-presence private messaging.

`&disconnect` and its `&kick` alias resolve a target player, route the request to the player's current map, and default to `RemoveSessionMember <playername>`. That is the softest known native session-removal candidate. `KickLobbyMember` can be selected with `DUNE_PLAYER_DISCONNECT_COMMAND=KickLobbyMember` if session removal does not work. `BattlEyeMegaKick` is intentionally excluded unless `DUNE_PLAYER_DISCONNECT_ALLOW_BATTLEYE=true` and `DUNE_PLAYER_DISCONNECT_COMMAND=BattlEyeMegaKick` are set, because it is the most likely option to behave like a punitive kick or retry cooldown.

Targeted disconnect execution has its own gate. It requires all three of `DUNE_ADMIN_GM_COMMANDS_ENABLED=true`, `DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true`, and `DUNE_CHAT_COMMAND_EXECUTE_PLAYER_DISCONNECT=true`. Until those are true, the command returns the exact native payload preview instead of publishing it. The repo also sets the server reconnect grace periods to `0` in `config/UserGame.ini`, so normal disconnects should not leave a long persisted reconnect window.

DB-only soft-disconnect is not a verified game-session disconnect. The verified fallback is network-disconnect teleport: force a real timeout, wait for `Offline`, run the offline move helper, then let reconnect load the moved pawn. Keep it behind its own mutation gate and audit trail; do not mix it with unverified native kick gates.

`&goto` and `&bring` are wired through the native GM command adapter for online movement, but execution remains gated until the command payload is proven. `&goto <playername>` prepares `TeleportToPlayer <playername>` targeted at the admin; `&bring <playername>` prepares `TeleportToExact <admin-x> <admin-y> <admin-z>` targeted at the online player. The three required gates are `DUNE_ADMIN_GM_COMMANDS_ENABLED=true`, `DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true`, and `DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT=true`. Until then, the commands return the exact payload preview instead of publishing a live teleport.

Online movement has additional live-test guards. `DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_REQUIRE_SAME_ROUTE=true` by default, so the admin and target must both be online and resolve to the same GM route before a publish is attempted. `DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_REQUIRE_ARM=true` by default, so live movement also requires a short-lived, one-use arm command:

```text
&armgoto <playername>
&goto <playername>

&armbring <playername>
&bring <playername>
```

The arm expires after `DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_ARM_SECONDS`, default `60`. This keeps first live tests limited to same-map/same-partition movement and prevents an old preview or repeated chat command from publishing unexpectedly.

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
  --sender-name SamplePlayer \
  --sender-fls-id TEST_FLS_ID
```

The listener has been validated to bind `chat.intercept` from the admin container path. If that regresses, first check that `/workspace/.env` contains the current `DUNE_ANNOUNCE_*` and `DUNE_CHAT_COMMAND_*` credentials; stale container environment was the original blocker.

Persistent listener service:

```bash
docker compose up -d --no-deps admin-chat-commands
docker compose logs -f admin-chat-commands
docker compose ps admin-chat-commands
docker compose exec -T admin-chat-commands /workspace/scripts/admin-chat-commands.py --healthcheck
```

The listener service is separate from the web panel so a command-loop failure does not take down the admin panel hostname. It uses `restart: unless-stopped`, has a Docker healthcheck for the command queue consumer, and reads `/workspace/.env` at runtime for chat-command and announcement credentials, matching the announcement hook behavior. The service runs on host networking and uses the host-published Postgres/RabbitMQ ports for command ingestion and replies, so Paul can recover even when the compose bridge path is degraded.

## Scheduled Restarts And Shutdowns

The Ops tab can also schedule restart or shutdown jobs for restart-safe components, the service layer, all game maps, or key individual maps such as Survival, Overmap, Arrakeen, Harko Village, and Deep Desert. It does not stop or restart Postgres or RabbitMQ by default because replacing those services disconnects all running map servers. It also does not include `admin-panel` in the admin-triggered `all` target, because stopping the container running the scheduler would interrupt the stop-backup-update-start workflow.

Scheduled maintenance defaults to dry-run mode. In dry-run mode, the job matures, records that it would have run, and does not touch containers. Executed restart jobs now use a stop-backup-update-start sequence: stop the selected game services, take the maintenance backup while they are down, check the local Steam package for a newer Funcom image tag, then start/recreate the selected services. Executed shutdown jobs stop the selected services, take the maintenance backup, run the same Steam-package update check, and leave them stopped. If the stop step fails, no backup, update check, or start is attempted. If the backup step fails during a restart, the failure is recorded as a warning and the selected services are still started so a backup issue does not strand the farm offline.

Maintenance announcements automatically append the live time remaining, or fill `{remaining}` / `{time_remaining}` if either token appears in the configured message. At the zero mark, the announcement worker sends a final "starting now" notice before execution begins. Announcement jobs also support an optional cadence list, using `remaining_seconds` and `interval_seconds` entries, so unattended maintenance can announce every 5 minutes during the 30-minute warning window and every 1 minute during the final 5 minutes.

Before an executed restart or shutdown stops containers, the admin panel resolves the online players affected by the target, publishes the configured soft-disconnect command to each player's current map route, waits `DUNE_ADMIN_RESTART_DISCONNECT_WAIT_SECONDS` seconds after all publishes complete, and only then starts the stop phase. If online players are present and the targeted-disconnect gates are not enabled, the restart/shutdown fails closed and does not stop services.

Maintenance backups are written under `backups/admin-panel/maintenance/<utc-stamp>-<job-id>/`. Each backup includes a unique Postgres custom-format dump, config/env archive, and mounted `data/server-saved` / `data/rabbitmq` archives when those paths are available to the admin container. Each backup also writes `postgres-layers.json`, which records primary streaming-replication slots and active senders at the stopped-world backup point. If `POSTGRES_REMOTE_REPLICA_HOST` is configured and `DUNE_ADMIN_MAINTENANCE_REPLICA_SNAPSHOT_ENABLED=true` (default), the backup attempts `scripts/replica-snapshot.sh` so the remote standby also gets a rolling logical snapshot. Replica status and remote snapshot failures are recorded as warnings in `manifest.json`; they do not replace or block the authoritative local stopped-world dump.

After a restart start hook returns, the admin panel waits for farm DB readiness before marking the job successful. The gate requires every current `world_partition` row to have an alive farm row and an `active_server_ids` entry; it also records the stricter ready/alive count as `readyOnline` in the execution details. If readiness is incomplete, the panel runs one guarded recovery pass through `DUNE_ADMIN_RESTART_RECOVERY_COMMAND` before waiting again. The default recovery command is `scripts/watch-maps.sh .env --once` with startup grace disabled, so a map that is running but not alive/active in the DB is recovered instead of leaving the farm half-warm. A start hook return code of `141` is treated as recoverable only if the farm subsequently reports fully online, because that code commonly means a broken output pipe rather than a confirmed container startup failure.

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
DUNE_RESTART_COMPOSE_IMAGE=docker:27.5.1-cli
DUNE_RESTART_USE_HOST_COMPOSE=true
DUNE_RESTART_COMPOSE_TIMEOUT_SECONDS=1800
DUNE_RESTART_DOCKER_STOP_TIMEOUT_SECONDS=120
DUNE_RESTART_DOCKER_API_TIMEOUT_SECONDS=30
DUNE_ADMIN_RESTART_RECOVERY_ENABLED=true
DUNE_ADMIN_RESTART_RECOVERY_COMMAND=/workspace/scripts/watch-maps.sh
DUNE_ADMIN_RESTART_RECOVERY_TIMEOUT_SECONDS=900
```

The Docker socket is privileged host control. Keep the admin panel bound to localhost or a trusted reverse proxy, and do not expose the admin hostname publicly. If the panel is reachable beyond a trusted local admin surface, enable `DUNE_ADMIN_REQUIRE_TOKEN=true`. The script receives `DUNE_RESTART_JOB_ID`, `DUNE_RESTART_TARGET`, `DUNE_RESTART_SERVICES`, and `DUNE_RESTART_ACTION`, plus the target as its first argument.

For admin-triggered restart jobs, the stop phase uses Docker stop, and the start phase uses Compose `up -d --force-recreate --no-deps`. When the admin image has no Docker CLI, the socket fallback starts a short-lived privileged `docker:27.5.1-cli` helper container with the repo and Docker socket mounted, then runs host-side Compose from that helper. It also runs `scripts/seed-gateway-neighbor.sh` before and after recreate so gateway's static `172.31.240.40`/`02:42:ac:1f:f0:28` identity is refreshed in Postgres, gateway, RabbitMQ, service-layer, and host bridge neighbor tables. After recreate and seeding, `scripts/restart-post-start-health.sh` waits for Postgres connectivity, re-seeds bridge neighbors, recreates `text-router` if it exited during early startup, and retries `scripts/verify-rmq-auth-path.sh` until the auth and text-router paths are reachable or the timeout expires. This catches the broken state where `admin-rmq` cannot reach `rmq-auth-shim`, `game-rmq` cannot reach `text-router`, or `text-router` exits because it raced Postgres during startup. This means the daily restart schedule applies changed `.env` values and bind-mounted config files during the recreate phase without pulling in excluded dependencies such as Postgres or RabbitMQ. Keep `DUNE_RESTART_COMPOSE_IMAGE` available locally on the Docker host; if it is missing, pull it before relying on unattended maintenance. The socket fallback gives stop/restart calls a longer timeout than Docker's graceful stop window so a normal slow shutdown is not misreported as a failed maintenance job.

The host-side daily scheduler uses `scripts/schedule-daily-maintenance.sh`. Run it from cron or systemd before the desired maintenance time; the deployed schedule should call it at 05:30 and create an executed, backed-up, announced `all` restart for 06:00, after Funcom's nightly maintenance window. Install the provided timer with `./scripts/install-daily-maintenance-timer.sh .env`. See [`docs/maintenance-updates.md`](maintenance-updates.md) for the timeline, cadence, and Steam-package update logic.

`scripts/restart-target.sh` refuses to stop or restart `postgres`, `admin-rmq`, or `game-rmq` unless `DUNE_RESTART_ALLOW_STATEFUL=true` is set for a deliberate maintenance window. If Postgres must be restarted, expect all game maps to need recovery afterward.

## Write Safety

Mutation endpoints are disabled unless:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
```

Current mutation support is intentionally narrow:

- Currency balance add/set through `dune.player_virtual_currency_balances`.
- Inventory Solari grants through `dune.save_item(dune.inventoryitem)` against `SolarisCoin` item stacks.
- Exchange/bank Solari grants through `dune.dune_exchange_modify_user_solari_balance`.
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
- `DUNE_ADMIN_MUTATIONS_ENABLED=false` is the example default. Enable it only after backup/restore validation and operator access controls are in place.
- `DUNE_ADMIN_ITEM_GRANTS_ENABLED=false` is the example default. Enable it only for item grant, stack edit, and deletion workflows that have been validated on the current build.
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
