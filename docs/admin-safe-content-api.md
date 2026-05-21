# Admin Safe Content API

This document is the endpoint contract for the DASH safe content expansion. The evidence catalog is [`../CONTENT_INSERTION_SURFACES.md`](../CONTENT_INSERTION_SURFACES.md); operator workflow details are in [`admin-panel.md`](admin-panel.md).

All endpoints are served by `admin/admin_panel.py`. When token auth is enabled, send:

```http
X-Admin-Token: <token>
```

All `POST` requests must use:

```http
Content-Type: application/json
```

## Gates

| Env var | Default | Effect |
| --- | --- | --- |
| `DUNE_ADMIN_CATALOG_ENABLED` | `true` | Enables read-only catalog endpoints. |
| `DUNE_ADMIN_TYPED_KNOBS_ENABLED` | `false` | Enables typed config writes. Does not block dry-runs. |
| `DUNE_ADMIN_EVENT_EXECUTION_ENABLED` | `false` | Enables event execution. Does not block event creation or dry-runs. |
| `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED` | `false` | Enables bundle execution. Does not block bundle dry-runs. |
| `DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED` | `false` | Enables faction reputation writes through `dune.set_player_faction_reputation`. Does not block inspection or dry-runs. |
| `DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED` | `false` | Enables journey reveal/complete/reset/delete server-function calls. Does not block inspection or dry-runs. |
| `DUNE_ADMIN_FACTION_MUTATIONS_ENABLED` | `false` | Enables player faction change through `dune.change_player_faction`. Does not block inspection or dry-runs. |
| `DUNE_ADMIN_MUTATIONS_ENABLED` | repo default currently `true` | Existing global mutation gate. |
| `DUNE_ADMIN_ITEM_GRANTS_ENABLED` | repo default currently `true` | Existing item mutation gate. |

## Read-Only Catalog

### `GET /api/catalog/surfaces`

Returns grouped insertion surfaces and the flat surface list.

Optional query:

```text
?group=Deep%20Desert
```

Response shape:

```json
{
  "enabled": true,
  "groups": {
    "Deep Desert": []
  },
  "surfaces": [
    {
      "id": "deep-desert-spice-caps",
      "group": "Deep Desert",
      "surface": "Config/INI knobs",
      "capability": "Raise or lower Deep Desert spice field active/primed caps.",
      "evidence": ["DEEP_DESERT_EVENT_KNOBS.md"],
      "confidence": "high",
      "mutationRisk": "medium",
      "restartRequired": true,
      "validationCommand": "select * from dune.spicefield_types order by map, field_kind_id;",
      "rollback": "Restore backed-up UserGame.ini and restart deep-desert."
    }
  ]
}
```

### `GET /api/catalog/evidence`

Returns the catalog schema, evidence rules, and entries.

### `GET /api/catalog/validation`

Returns validation commands for static checks, announcements, and Deep Desert DB state.

## Typed Knobs

### `GET /api/settings/typed-knobs`

Returns the typed knob registry and current values.

Response fields:

- `enabled`: whether typed writes are enabled.
- `values`: object keyed by typed knob id.
- `confirmPhrase`: currently `WRITE TYPED KNOBS`.

### `POST /api/settings/typed-knobs`

Dry-run:

```json
{
  "dry_run": true,
  "updates": {
    "globalMiningMultiplier": "2.5"
  }
}
```

Dry-run response:

```json
{
  "ok": true,
  "dryRun": true,
  "planned": {
    "globalMiningMultiplier": "2.5"
  },
  "restartRequired": true
}
```

Write:

```json
{
  "confirm": "WRITE TYPED KNOBS",
  "updates": {
    "globalMiningMultiplier": "2.5"
  }
}
```

Write requirements:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_TYPED_KNOBS_ENABLED=true`
- confirmation phrase

Write behavior:

- Validates all supplied knob values.
- Creates a backup of each affected config file under `backups/admin-panel`.
- Updates only the known section/key pairs.
- Returns current typed knob values and restart metadata.

### Typed Knob IDs

| ID | Value type |
| --- | --- |
| `spiceDeepDesertCaps` | Raw INI string or structured object. |
| `sandstormEnabled` | `0/1` or `true/false`. |
| `sandstormTreasureEnabled` | `0/1` or `true/false`. |
| `coriolisAutoSpawnEnabled` | `true/false`. |
| `globalMiningMultiplier` | float, `0..100`. |
| `vehicleMiningMultiplier` | float, `0..100`. |
| `pvpResourceMultiplier` | float, `0..100`. |
| `forcePvpAllPartitions` | `true/false`. |
| `securityZonesEnabled` | `true/false`. |
| `buildingShelterThreshold` | float, `0..1`. |
| `placeableShelterThreshold` | float, `0..1`. |
| `shelteredProtectionThreshold` | float, `0..1`. |

Structured spice cap example:

```json
{
  "dry_run": true,
  "updates": {
    "spiceDeepDesertCaps": {
      "Small": {"primed": 60, "active": 60},
      "Medium": {"primed": 24, "active": 24},
      "Large": {"primed": 3, "active": 3}
    }
  }
}
```

## Economy Bundle

### `POST /api/admin/bundle`

Default mode is dry-run.

```json
{
  "dry_run": true,
  "currency": [
    {"player_controller_id": 123, "currency_id": 1, "amount": 1000, "mode": "add"}
  ],
  "xp": [
    {"player_id": 123, "track_type": "Combat", "amount": 1000, "mode": "add", "level": 0}
  ],
  "items": [
    {"account_id": 456, "template_id": "SolarisCoin", "stack_size": 1, "stats": {}}
  ]
}
```

Dry-run behavior:

- Currency and XP rows are returned as planned statements.
- Item rows call the existing item dry-run resolver so inventory, capacity, slot, and template warnings are visible.
- No DB writes occur.

Execution request:

```json
{
  "dry_run": false,
  "confirm": "EXECUTE BUNDLE",
  "currency": [],
  "xp": [],
  "items": []
}
```

Execution requirements:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_ITEM_GRANTS_ENABLED=true` for item rows
- confirmation phrase

Risk note: execution is a sequence of helper calls, not a single database transaction spanning all helper calls. Keep broad bundles dry-run until every target row is verified.

## Offline Player Recovery

### `POST /api/admin/player-recovery/offline-teleport`

Dry-run request:

```json
{
  "dry_run": true,
  "account_id": 456,
  "partition_id": 12,
  "location": {"x": 0, "y": 0, "z": 0}
}
```

Behavior:

- Resolves `account_id` to `dune.accounts.user` or `funcom_id`.
- Refuses players whose `online_status` is `Online`.
- Plans or executes `dune.admin_move_offline_player_to_partition(fls_id, partition_id, location)`.

Execution request:

```json
{
  "dry_run": false,
  "confirm": "MOVE OFFLINE PLAYER",
  "account_id": 456,
  "partition_id": 12,
  "location": {"x": 0, "y": 0, "z": 0}
}
```

Execution requirements:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- confirmation phrase

Rollback: use the previous partition/server context in the response/audit record and perform another offline move.

## Progression Inspect

### `POST /api/admin/progression/inspect`

Read-only. Discovers currently mapped player progression rows and relevant DB function/table signatures.

```json
{
  "account_id": 456
}
```

Returns:

- `player`: selected player account/controller/pawn context.
- `faction`: rows from `dune.player_faction`.
- `reputation`: rows from `dune.player_faction_reputation`.
- `functions`: `dune` functions whose names match journey, recipe, vehicle, faction, or reputation.
- `tables`: relevant `information_schema.columns` rows.
- `mutators`: current mutator status and gates.
- `errors`: per-query failures.

This endpoint is the safe evidence collector for future journey, recipe, vehicle, and faction work. It does not execute discovered functions.

## Journey Mutations

### `POST /api/admin/journey`

Default mode is dry-run. Supported actions are:

- `reveal`
- `complete`
- `reset`
- `delete`

Dry-run request:

```json
{
  "dry_run": true,
  "account_id": 456,
  "action": "reveal",
  "story_node_ids": ["ExampleStoryNode"]
}
```

`story_node_ids` can also be a comma-separated string from the Catalog UI.

Dry-run behavior:

- Resolves `account_id` to the account FLS/user id.
- Verifies the corresponding `dune.<action>_journey_story_nodes_for_player` function exists.
- Reads up to the first 20 requested nodes through `dune.admin_get_journey_details(fls_id, story_node_id)`.
- Reports whether execution would be blocked because the player is online.

Execution request:

```json
{
  "dry_run": false,
  "confirm": "WRITE JOURNEY",
  "account_id": 456,
  "action": "complete",
  "story_node_ids": ["ExampleStoryNode"]
}
```

Execution requirements:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED=true`
- confirmation phrase
- target player must be offline

Function mapping:

| Action | Function |
| --- | --- |
| `reveal` | `dune.reveal_journey_story_nodes_for_player(in_player_id text, in_story_node_ids text[])` |
| `complete` | `dune.complete_journey_story_nodes_for_player(in_player_id text, in_story_node_ids text[])` |
| `reset` | `dune.reset_journey_story_nodes_for_player(in_player_id text, in_story_node_ids text[])` |
| `delete` | `dune.delete_journey_story_nodes_for_player(in_player_id text, in_story_node_ids text[])` |

Risk: these are server-provided functions, but story-node ids and reward semantics are not cataloged yet. Use dry-run detail output first and validate on disposable offline data.

## Player Faction Change

### `POST /api/admin/faction`

Default mode is dry-run.

```json
{
  "dry_run": true,
  "account_id": 456,
  "faction_id": 1,
  "neutral_faction_id": 3
}
```

Dry-run behavior:

- Resolves `account_id` to `player_pawn_id`.
- Validates `faction_id` and `neutral_faction_id` against `dune.factions`.
- Reads current `dune.player_faction` rows.
- Reads the effective current faction through `dune.get_player_faction(actor_id, neutral_faction_id)`.
- Verifies `dune.change_player_faction(...)` exists.
- Reports whether execution would be blocked because the player is online.

Execution request:

```json
{
  "dry_run": false,
  "confirm": "CHANGE FACTION",
  "account_id": 456,
  "faction_id": 1,
  "neutral_faction_id": 3
}
```

Execution requirements:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_FACTION_MUTATIONS_ENABLED=true`
- confirmation phrase
- target player must be offline

Function call:

```sql
dune.change_player_faction(
  in_player_id := player_pawn_id,
  in_faction_id := faction_id,
  neutral_faction_id := neutral_faction_id,
  in_utc_time_faction_change := now_utc
)
```

Risk: the function is first-party, but guild side effects and live-client refresh behavior need disposable-character validation.

## Faction Reputation

### `POST /api/admin/faction-reputation`

Default mode is dry-run.

```json
{
  "dry_run": true,
  "account_id": 456,
  "faction_id": 1,
  "amount": 100,
  "mode": "add"
}
```

Dry-run behavior:

- Resolves `account_id` to `player_pawn_id`.
- Checks `information_schema.columns` for `dune.player_faction_reputation`.
- Accepts the reputation value column only if it is one of:
  - `reputation`
  - `reputation_amount`
  - `amount`
  - `value`
- Reads current rows for `(actor_id, faction_id)`.
- Discovers `dune.set_player_faction_reputation` and `dune.get_player_current_faction_reputation`.
- Returns the planned new value and rollback value.

Execution request:

```json
{
  "dry_run": false,
  "confirm": "WRITE REPUTATION",
  "account_id": 456,
  "faction_id": 1,
  "amount": 100,
  "mode": "add"
}
```

Execution requirements:

- `DUNE_ADMIN_MUTATIONS_ENABLED=true`
- `DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED=true`
- confirmation phrase

Execution behavior:

- Calls `dune.set_player_faction_reputation(actor_id, faction_id, new_value)`.
- Records before/after rows and a rollback set value in the response/audit context.

Risk: this is a high-impact player progression mutation, but it uses a server-provided function rather than raw table writes. Confidence is moderate-to-high for the write path when the function is present; still validate on disposable/offline character data before routine operator use.

## Spice and Resource Inspect

### `POST /api/admin/spice-fields/inspect`

Read-only. Body can be `{}`.

Returns:

- `caps`: rows from `dune.spicefield_types`.
- `availability`: rows from `dune.spicefield_server_availability`.
- `resourceFields`: grouped `dune.resourcefield_state`.
- `typedKnob`: current `spiceDeepDesertCaps` registry/value.
- `errors`: per-query failures if the DB schema is unavailable.

Use this before and after typed Deep Desert cap writes.

## Events

### `GET /api/events`

Returns:

- `events`: persisted event definitions.
- `lastRun`: most recent run summary.
- `executionEnabled`: gate state.

Events persist under:

```text
backups/admin-panel/events.json
```

### `POST /api/events/dry-run`

Builds an event plan without persisting it.

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

### `POST /api/events`

Persists a scheduled event. Same body as dry-run.

### `POST /api/events/cancel`

```json
{"id": "<event-id>"}
```

Sets a scheduled event to `cancelled`.

### `POST /api/events/run`

```json
{"id": "<event-id>"}
```

Requires:

```env
DUNE_ADMIN_EVENT_EXECUTION_ENABLED=true
```

Current v1 behavior is intentionally conservative: dry-run-only event actions record planned work and do not perform underlying config or DB writes. Use the dedicated typed-knob, bundle, announcement, or restart endpoint for actual writes until event execution is expanded and tested.

Supported action types:

| Type | Payload fields | Current behavior |
| --- | --- | --- |
| `announcement` | `message`, `delay`, `repeat_seconds` | Plans `/api/ops/announcement`. |
| `restart` | `target`, `action`, `delay` | Plans `/api/ops/restart` with `execute=false`. |
| `typed-knob-plan` | `updates` | Plan-only typed knob update. |
| `economy-bundle` | `payload` | Plan-only bundle with `dry_run=true`. |
| `spice-cap-proposal` | `caps` | Plan-only `spiceDeepDesertCaps` update. |

## Failure Modes

Expected fail-closed responses:

- Catalog endpoints return `401` if `DUNE_ADMIN_CATALOG_ENABLED=false`.
- Typed writes return `401` if `DUNE_ADMIN_TYPED_KNOBS_ENABLED=false`.
- Bundle execution returns `401` if `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=false`.
- Event execution returns `401` if `DUNE_ADMIN_EVENT_EXECUTION_ENABLED=false`.
- Offline recovery returns `400` for online players or missing target locations.
- Native GM execution remains blocked unless both GM gates and payload verification are true.

Confidence: high for dry-run and gate behavior; moderate for live DB execution paths until tested against disposable local data.
