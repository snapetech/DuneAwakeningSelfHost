# Content Insertion Surfaces

This is the canonical catalog for DASH content/admin expansion. Confidence levels are `high`, `moderate`, `low`, or `unknown`.

Evidence rules:

- Shipped config plus live database behavior is strong evidence.
- Binary strings are leads only until the owning section, syntax, and runtime effect are proven.
- Public websites are candidate lookup sources, not authoritative local server evidence.
- New write paths must start read-only or dry-run unless an execution gate, confirmation phrase, and audit event are present.

| Surface | Capability | Evidence | Confidence | Mutation risk | Restart required | Validation command | Rollback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Config/INI knobs | Deep Desert spice field caps through `[/Script/DuneSandbox.SpiceHarvestingSystem] m_PerMapSystemSettings`. | `DEEP_DESERT_EVENT_KNOBS.md`, `SERVER_RUNTIME_SURFACES.md`, `dune.spicefield_types`, `dune.resourcefield_state`. | high | medium | yes | `select * from dune.spicefield_types order by map, field_kind_id;` | Restore backed-up `UserGame.ini` and restart `deep-desert`. |
| Config/INI knobs | Sandstorm and Coriolis safe toggles already present in config. Cycle seed, DB wipe, and cycle-end restart fields are excluded from typed writes. | `config/UserGame.ini`, `config/UserEngine.ini`, `SERVER_RUNTIME_SURFACES.md`. | high | medium | yes | `rg -n 'Sandstorm|Coriolis' config/UserGame.ini config/UserEngine.ini` | Restore backed-up config and restart affected maps. |
| Config/INI knobs | Mining/resource multipliers: `Dune.GlobalMiningOutputMultiplier`, `Dune.GlobalVehicleMiningOutputMultiplier`, `SecurityZones.PvpResourceMultiplier`. | `config/UserEngine.ini`, `docs/server-knobs-audit.md`. | high | low | yes | `rg -n 'MiningOutput|PvpResourceMultiplier' config/UserEngine.ini` | Restore backed-up `UserEngine.ini` and restart maps. |
| Config/INI knobs | PvP/security-zone toggles. | `config/UserGame.ini`, `SERVER_CONFIG_KEYS.md`. | high | medium | yes | `rg -n 'Pvp|SecurityZones' config/UserGame.ini` | Restore backed-up `UserGame.ini` and restart maps. |
| Config/INI knobs | Shelter/hydration candidates. | `HYDRATION_WATER_KNOBS.md`, shipped ShelterSettings section, local candidate overrides. | low to moderate | experimental | yes | Live in-base/outside hydration test after restart. | Restore backed-up `UserGame.ini` and restart maps. |
| Database state | Currency, XP, and item grants as a bundled transaction plan. | Existing DASH currency/XP/item grant paths and `docs/admin-mutation-map.md`. | high | medium | no | `/api/admin/bundle` with `dry_run=true`. | Manual compensating edits from audit record. |
| Database state | Faction reputation planning and gated writes through `dune.set_player_faction_reputation`. | `dune.set_player_faction_reputation`, `dune.get_player_current_faction_reputation`, `dune.player_faction_reputation`. | moderate-to-high | high | no | `/api/admin/faction-reputation` with `dry_run=true`; `select * from dune.player_faction_reputation where actor_id=<pawn_id>;` | Run the endpoint again with `mode=set` and the previous value from the audit record. |
| Database state | Offline player recovery through `dune.admin_move_offline_player_to_partition`. | Local schema function reference and player location audit work. | moderate | high | no | `select * from dune.player_state where account_id=<id>;` before and after. | Move back to the prior partition recorded in the audit result. |
| Database state | Journey story-node planning and gated reveal/complete/reset/delete calls. | `dune.admin_get_journey_details`, `dune.reveal_journey_story_nodes_for_player`, `dune.complete_journey_story_nodes_for_player`, `dune.reset_journey_story_nodes_for_player`, `dune.delete_journey_story_nodes_for_player`. | moderate | high | no | `/api/admin/journey` with `dry_run=true` and known story node ids. | Use the opposite journey action where meaningful; audit before/after details. |
| Database state | Recipe and vehicle function discovery. | `pg_proc` discovery through `/api/admin/progression/inspect`, existing DB observations. | moderate for discovery, low for writes | blocked | unknown | Map safe DB functions or live examples first. | No execution in v1. |
| RabbitMQ/admin/GM routes | Verified chat announcements. | Existing announcement scheduler and `scripts/verify-announcement.sh`. | high | low | no | `./scripts/verify-announcement.sh` | No persistent rollback; audit records delivery. |
| RabbitMQ/admin/GM routes | Candidate native GM command envelopes. | `scripts/dune_gm_command.py`, command strings, allowed command catalog. | low | blocked | no | Keep execution blocked until `DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true` is proven by live-client validation. | No execution in v1. |
| Existing content activation | Encounters, patrol ships, treasure, and resource fields. | `DEEP_DESERT_EVENT_KNOBS.md`, `RESOURCE_RESPAWN_KNOBS.md`, runtime surface notes. | moderate for shipped toggles, low for new activation weights | medium to high | yes | Compare logs and DB state before/after restart. | Restore config backups; avoid raw DB writes unless separately validated. |
| Hard limits | True new maps, cooked assets, physics, or algorithms. | Current server surface audit shows no admin-only route for new cooked content. | high | blocked | yes/build-time | Not applicable to DASH v1. | Requires cooked client/server assets or binary/plugin work. |

## DASH API Mapping

- Read-only catalog: `/api/catalog/surfaces`, `/api/catalog/evidence`, `/api/catalog/validation`.
- Typed knob inventory and dry-run: `/api/settings/typed-knobs`.
- Typed knob writes: require `DUNE_ADMIN_MUTATIONS_ENABLED=true`, `DUNE_ADMIN_TYPED_KNOBS_ENABLED=true`, and confirmation `WRITE TYPED KNOBS`.
- Economy bundle plans: `/api/admin/bundle`, default `dry_run=true`; execution also requires `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=true` and confirmation `EXECUTE BUNDLE`.
- Offline player recovery: `/api/admin/player-recovery/offline-teleport`, default `dry_run=true`; execution requires confirmation `MOVE OFFLINE PLAYER`.
- Progression inspection: `/api/admin/progression/inspect`.
- Faction reputation planning: `/api/admin/faction-reputation`, default `dry_run=true`; execution requires `DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED=true` and confirmation `WRITE REPUTATION`.
- Journey story-node planning: `/api/admin/journey`, default `dry_run=true`; execution requires `DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED=true` and confirmation `WRITE JOURNEY`.
- Spice/resource inspection: `/api/admin/spice-fields/inspect`.
- Event planner: `/api/events`, `/api/events/dry-run`, `/api/events/cancel`, `/api/events/run`; execution requires `DUNE_ADMIN_EVENT_EXECUTION_ENABLED=true`.

## Implementation Status

Implemented in `admin/admin_panel.py`:

- Catalog data model and read-only catalog endpoints.
- Catalog UI tab.
- Typed knob registry, validation, dry-run, backup-before-write, and restart metadata.
- Dry-run-first economy bundle planner.
- Offline player recovery dry-run and gated execution path using the mapped `dune.admin_move_offline_player_to_partition(...)` function.
- Progression surface inspection for faction, reputation, journey, recipe, and vehicle DB evidence.
- Dry-run-first faction reputation mutator using `dune.set_player_faction_reputation`, runtime schema checks, and a separate execution gate.
- Dry-run-first journey story-node mutator using server-provided reveal/complete/reset/delete functions and a separate execution gate.
- Read-only spice/resource field inspection.
- Event definition persistence under `backups/admin-panel/events.json`.
- Event dry-run planner and explicit execution gate.

The implementation intentionally keeps catalog reads independent from write gates. This lets an operator expose evidence and validation data without enabling mutation paths.

## Gates and Confirmation Phrases

| Gate | Default | Scope |
| --- | --- | --- |
| `DUNE_ADMIN_CATALOG_ENABLED` | `true` | Read-only catalog endpoints. |
| `DUNE_ADMIN_TYPED_KNOBS_ENABLED` | `false` | Typed config writes. Typed dry-runs remain available. |
| `DUNE_ADMIN_EVENT_EXECUTION_ENABLED` | `false` | Event run execution. Event creation and dry-runs remain available. |
| `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED` | `false` | Economy bundle execution. Bundle dry-runs remain available. |
| `DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED` | `false` | Faction reputation execution. Progression inspection and reputation dry-runs remain available. |
| `DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED` | `false` | Journey story-node execution. Journey dry-runs and progression inspection remain available. |
| `DUNE_ADMIN_MUTATIONS_ENABLED` | repo default currently `true` | Existing global mutation gate. |
| `DUNE_ADMIN_ITEM_GRANTS_ENABLED` | repo default currently `true` | Item grant and bundle item execution. |
| `DUNE_ADMIN_GM_COMMANDS_ENABLED` | `false` | Native GM command execution. Still also blocked by payload verification. |
| `DUNE_GM_COMMAND_PAYLOAD_VERIFIED` | `false` | Required for native GM command execution. |

| Confirmation | Used by |
| --- | --- |
| `WRITE TYPED KNOBS` | Typed config writes. |
| `EXECUTE BUNDLE` | Economy bundle execution. |
| `MOVE OFFLINE PLAYER` | Offline player recovery execution. |
| `WRITE REPUTATION` | Faction reputation execution. |
| `WRITE JOURNEY` | Journey story-node execution. |
| `RUN GM COMMAND` | Native GM command execution, still blocked until payload verification. |

## Typed Knob Registry

High-confidence controls:

- `spiceDeepDesertCaps`
- `sandstormEnabled`
- `coriolisAutoSpawnEnabled`
- `globalMiningMultiplier`
- `vehicleMiningMultiplier`
- `pvpResourceMultiplier`
- `forcePvpAllPartitions`
- `securityZonesEnabled`

Moderate or experimental controls:

- `sandstormTreasureEnabled`
- `buildingShelterThreshold`
- `placeableShelterThreshold`
- `shelteredProtectionThreshold`

Blocked by design:

- Coriolis cycle seed and duration controls.
- Coriolis DB wipe controls.
- Native GM command execution.
- True new maps/assets/physics/algorithms.

## Validation Checklist

Static:

```bash
python3 -m py_compile admin/admin_panel.py scripts/admin-chat-commands.py scripts/dune_gm_command.py
python3 scripts/test-admin-panel-safe-surfaces.py
make validate
```

`scripts/test-admin-panel-safe-surfaces.py` uses a temporary `ADMIN_WORKSPACE` and does not touch the live config or backup tree. It covers:

- Catalog schema and grouping.
- Typed knob validation.
- Backup-before-write behavior for typed config updates.
- Structured Deep Desert spice cap rendering.
- Event dry-run planning.
- Event persistence/cancel.
- Fail-closed event execution when `DUNE_ADMIN_EVENT_EXECUTION_ENABLED` is not set.

HTTP smoke checks:

```bash
curl -sS http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/api/catalog/surfaces | jq '.enabled, (.surfaces|length)'

curl -sS -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/api/settings/typed-knobs \
  -d '{"dry_run":true,"updates":{"globalMiningMultiplier":"2.5"}}' \
  | jq '.dryRun, .planned.globalMiningMultiplier'

curl -sS -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/api/events/dry-run \
  -d '{"name":"test","actions":[{"type":"spice-cap-proposal","caps":{"Medium":{"primed":24,"active":24}}}]}' \
  | jq '.dryRun, .event.plan[0].type'

curl -sS -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:${DUNE_ADMIN_HOST_PORT:-18080}/api/admin/bundle \
  -d '{"dry_run":true,"currency":[],"xp":[],"items":[]}' \
  | jq '.dryRun, (.plan|length)'
```

Manual Deep Desert validation:

1. Inspect current state with `POST /api/admin/spice-fields/inspect`.
2. Preview `spiceDeepDesertCaps`.
3. Enable `DUNE_ADMIN_TYPED_KNOBS_ENABLED=true` only when ready to write.
4. Write typed knob with `WRITE TYPED KNOBS`.
5. Restart `deep-desert`.
6. Query `dune.spicefield_types` and grouped `dune.resourcefield_state`.
7. Roll back from the config backup if behavior is wrong.

## Going Forward

Near-term, high-confidence work:

- Add focused tests around typed knob validation and `set_ini_section_values`.
- Add UI write controls for typed knobs only after operators have used the dry-run panel and confirmed the rendered config output.
- Add event action execution for announcements and restart scheduling by calling the already-safe scheduler functions directly.
- Add export/download of event dry-run plans and catalog entries as JSON for operator review.
- Validate faction reputation execution on disposable/offline character data and document exact table columns observed in the live schema.
- Validate journey reveal/complete/reset/delete on disposable offline character data and build a local story-node id reference from observed `admin_get_journey_details` calls.

Medium-confidence work:

- Validate `spiceDeepDesertCaps` live across a restart and record before/after DB snapshots in this file.
- Validate shelter/hydration candidates with a controlled in-base/outside test and either promote or demote those typed controls.
- Add a dedicated rollback helper that restores the exact config backup created by a typed knob write.
- Expand the typed layer to safe Director world-open/closing-soon controls after testing against live login/travel behavior.

Blocked until stronger evidence:

- Native GM command execution. Need a verified live-client payload for `UDuneServerCommandSubsystem`.
- Journey, recipe, and vehicle unlock writes. Need safe DB functions or complete table/JSON contracts.
- Ordinary resource-node respawn writes. Current evidence proves machinery exists, not a safe plain-INI respawn override.
- True new maps/assets/physics/algorithms. These require cooked assets, plugin support, binary work, or a newly discovered supported loading route.
