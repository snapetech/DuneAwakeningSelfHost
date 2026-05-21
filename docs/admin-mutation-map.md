# Admin Mutation Map

This document records the database contracts currently used or deliberately avoided by the admin panel.

## Item Template IDs

Public item databases are useful for finding item names and likely template IDs. For example, gaming.tools item URLs use slugs such as:

```text
https://dune.gaming.tools/items/smg_unique_largemag_06
```

The slug style matches server `template_id` values seen in `dune.items`, but public data should be treated as a candidate source. Verify template IDs against local observed rows when possible.

Local reference query:

```sql
select template_id, count(*)
from dune.items
where template_id is not null
group by template_id
order by count desc, template_id;
```

The admin panel also builds a known-template catalog from local server tables that expose exact `template_id` values:

```sql
dune.items
dune.landsraad_task_rewards
dune.landsraad_house_rewards
dune.vendor_stock_state
dune.vehicle_modules
dune.dune_exchange_orders
```

On the current clean local database, `dune.landsraad_task_rewards` is the useful populated source. It exposes schematics, swatches, resources, and currency-like rewards such as `SolarisCoin`. Gear grants are handled by the same item grant path when an exact gear `template_id` is known.

## Inventory Ownership

The mapped read function is:

```sql
dune.admin_get_inventory_details(in_account_id bigint)
```

It joins `dune.items`, `dune.inventories`, and `dune.player_state` through `player_state.player_pawn_id`, so player inventory grants should target an inventory owned by the player pawn.

The panel shows recent inventory IDs from `dune.inventories` joined to `dune.player_state`, and character detail includes `dune.admin_get_inventory_details(account_id)`. Grants can target an explicit `inventory_id` or resolve the first owned inventory for an `account_id` / character name, optionally filtered by `inventory_type`. Template inputs use an HTML datalist populated from known local template sources.

## Item Grants

The panel uses the server DB function:

```sql
dune.save_item(in_item dune.inventoryitem)
```

It allocates a new ID with:

```sql
dune.advance_items_id_sequencer(1)
```

Required opt-ins:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
```

The grant creates a row shaped as `dune.inventoryitem`:

```text
item_id, inventory_id, stack_size, position_index, template_id,
is_new, acquisition_time, stats, quality_level, volume_override
```

The panel dry-run path resolves inventory, position, capacity, and local-template warnings without writing. Actual writes check that the target slot is empty and that the chosen position is inside `max_item_count` when the inventory has a capacity.

Remaining risk: server-side refresh behavior is not fully proven. Prefer granting while the player is offline, then restart or reload affected game services if the item does not appear.

## Item Maintenance

Implemented item maintenance endpoints:

```sql
dune.load_item(item_id)
dune.save_item(in_item dune.inventoryitem)
dune.delete_item(item_id)
dune.delete_inventory_item(item_id, count)
```

The panel exposes stack-size replacement and full/partial deletion. These are mutation-gated and require explicit confirmation phrases.

## Currency

The panel writes:

```sql
dune.player_virtual_currency_balances
```

It supports add/set by `(player_controller_id, currency_id)`.

## Economy Bundle Plans

The panel exposes:

```text
POST /api/admin/bundle
```

This endpoint is a planning wrapper around the existing currency, XP, and item grant paths. It defaults to `dry_run=true` and returns a combined plan without writing.

Dry-run request shape:

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

Execution requires:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED=true
```

Item rows also require:

```env
DUNE_ADMIN_ITEM_GRANTS_ENABLED=true
```

The execution confirmation phrase is:

```text
EXECUTE BUNDLE
```

Rollback is compensating mutation from the audit record. There is no database transaction spanning the helper calls yet, so broad bundles should stay dry-run until the target rows are confirmed.

## Specialization XP

The panel uses:

```sql
dune.set_specialization_xp_and_level(
  in_player_id bigint,
  in_track_type dune.specializationtracktype,
  in_xp_amount integer,
  in_level real
)
```

This is safer than raw writes because the DB function upserts `dune.specialization_tracks`.

## Specialization Keystones

Known keystones live in:

```sql
dune.specialization_keystones_map
```

The panel uses:

```sql
dune.purchase_specialization_keystone(in_player_id bigint, in_keystone text)
dune.reset_specialization_keystones(in_player_id bigint)
```

The map currently contains keystone names such as:

```text
Combat_CombatKeystone_SkillPoint1
Crafting_CraftingKeystone_CraftingSpeedIncrease18
Exploration_ExplorationKeystone_PlayerInventorySlots50
```

## Recipe Unlocks

Recipe grants are not implemented.

Mapped evidence:

- `dune.remove_items_and_recipes(...)` can remove recipes.
- Actor JSON includes `CraftingRecipesLibraryActorComponent.m_KnownItemRecipes`.
- No safe grant/upsert function for recipes has been mapped yet.

Until a supported function or fully understood JSON contract is found, the panel will not write recipe unlocks.

## Journey and Skill-Like Unlocks

The DB has journey admin functions, including:

```sql
dune.complete_journey_story_nodes_for_player(...)
dune.reveal_journey_story_nodes_for_player(...)
dune.reset_journey_story_nodes_for_player(...)
dune.delete_journey_story_nodes_for_player(...)
```

These functions explicitly reject some operations when the player is online. The panel exposes them only as a dry-run-first mutator, requires offline targets for execution, and keeps story-node ID discovery separate because reward semantics still need mapping.

## Offline Player Teleport / Recovery

The mapped safe movement functions are:

```sql
dune.admin_move_offline_player(in_fls_id text, in_target_partition_name text, in_target_location dune.vector)
dune.admin_move_offline_player_to_partition(in_fls_id text, in_target_partition_id bigint, in_target_location dune.vector)
```

Both functions require `dune.is_player_offline(in_fls_id)` to be true. They are the right primitive for a DASH teleport command that moves an offline player to an admin's current location.

The first chat-command implementation deliberately does not write live online actor state. Online players are owned by the running map server, so a raw actor transform update can be overwritten or desynced. For now, `&teleport <playername>` resolves the admin and target, rejects online targets, and calls `admin_move_offline_player_to_partition` only when execution is explicitly enabled.

The movement write performed by the server function is effectively:

```sql
update dune.actors
set
  transform = (in_target_location, (transform).rotation),
  map = dune.upgrade_map_name(target_partition.map),
  dimension_index = target_partition.dimension_index,
  partition_id = target_partition.partition_id
where id = player_pawn_id;
```

The command uses `dune.accounts.user` as the FLS/user id and `dune.player_state.character_name` for human-facing names.

The admin panel endpoint is:

```text
POST /api/admin/player-recovery/offline-teleport
```

Dry-run request shape:

```json
{
  "dry_run": true,
  "account_id": 456,
  "partition_id": 12,
  "location": {"x": 0, "y": 0, "z": 0}
}
```

Execution requires:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
```

and confirmation:

```text
MOVE OFFLINE PLAYER
```

The panel resolves `account_id` to `dune.accounts.user` and refuses players whose `online_status` is `Online`. Confidence is moderate: the DB function is mapped, but recovery should be validated on a disposable/offline character before use on valuable characters.

## Spice and Resource Field Inspection

The read-only endpoint is:

```text
POST /api/admin/spice-fields/inspect
```

It reads:

```sql
dune.spicefield_types
dune.spicefield_server_availability
dune.resourcefield_state
```

The endpoint is intended to validate typed Deep Desert cap changes before and after restart. It does not write DB resource-field rows.

## Faction and Journey Mutators

Progression evidence collector:

```text
POST /api/admin/progression/inspect
```

This endpoint reads current player faction/reputation rows and discovers relevant `dune` functions/tables through `pg_proc` and `information_schema`. It is read-only.

Function-backed mutators added after live schema validation:

```text
POST /api/admin/faction-reputation
POST /api/admin/faction
POST /api/admin/journey
POST /api/admin/landsraad
POST /api/admin/respawn-location
```

Mapped first-party functions:

```sql
dune.set_player_faction_reputation(in_actor_id bigint, in_faction_id smallint, in_reputation_amount integer)
dune.get_player_current_faction_reputation(in_actor_id bigint)
dune.change_player_faction(in_player_id bigint, in_faction_id smallint, neutral_faction_id smallint, in_utc_time_faction_change timestamp)
dune.get_player_faction(in_player_id bigint, in_neutral_faction_id smallint)
dune.admin_get_journey_details(in_player_id text, in_story_node_id text)
dune.reveal_journey_story_nodes_for_player(in_player_id text, in_story_node_ids text[])
dune.complete_journey_story_nodes_for_player(in_player_id text, in_story_node_ids text[])
dune.reset_journey_story_nodes_for_player(in_player_id text, in_story_node_ids text[])
dune.delete_journey_story_nodes_for_player(in_player_id text, in_story_node_ids text[])
dune.landsraad_load_current_term()
dune.landsraad_change_term_end_time(end_term_id bigint, new_end_time timestamp without time zone, in_test_term boolean)
dune.landsraad_force_end_term(end_term_id bigint)
dune.get_respawn_locations(in_account_id bigint)
dune.update_respawn_locations(player_id bigint, respawn_locations respawnlocation[])
```

Separate gates:

```env
DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED=false
DUNE_ADMIN_FACTION_MUTATIONS_ENABLED=false
DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED=false
DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED=false
DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED=false
```

Confirmation phrases:

```text
WRITE REPUTATION
CHANGE FACTION
WRITE JOURNEY
WRITE LANDSRAAD
DELETE RESPAWN
```

Current confidence:

- Reputation: moderate-to-high mechanically because a first-party setter exists.
- Faction: moderate; guild side effects need disposable-character validation.
- Journey: moderate; functions exist, but story-node IDs and reward semantics need cataloging.
- Landsraad term end-time: moderate mechanically because first-party functions exist; high operational risk because it changes shared world/economy state. `force-end` is not safely reversible.
- Respawn-location delete: moderate mechanically because first-party array read/write functions exist; high rollback risk because restoring requires preserving and reconstructing the removed `respawnlocation` composite.

## Landsraad Term Administration

The panel endpoint is:

```text
POST /api/admin/landsraad
```

Supported actions:

```text
change-end-time
force-end
```

Dry-run reads the current term through `dune.landsraad_load_current_term()`, reads recent `dune.landsraad_decree_term` rows, and verifies the mapped functions exist. Execution is blocked unless the global mutation gate and `DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE LANDSRAAD"`.

Rollback posture:

- `change-end-time`: dry-run records the prior `end_time`, so a compensating change can restore it.
- `force-end`: no safe rollback is mapped.

## Respawn Location Delete

The panel endpoint is:

```text
POST /api/admin/respawn-location
```

Supported action:

```text
delete
```

Dry-run verifies that the requested UUID exists in `dune.player_respawn_locations` for the account and plans a call equivalent to:

```sql
select dune.update_respawn_locations(
  account_id,
  array(
    select current_location.loc
    from unnest(dune.get_respawn_locations(account_id)) as current_location(loc)
    where (current_location.loc).id <> target_uuid
  )
);
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED=true` are both set, the request includes `confirm: "DELETE RESPAWN"`, and the target player is offline.

Creation and arbitrary editing of respawn locations remain blocked. Confidence is moderate for deletion mechanics and low for safe creation because `spawnlocatordescriptor`, nested `transform`, map/dimension, and actor binding semantics are not fully proven.
