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

## Solari Grants

The panel exposes two explicit Solari grant helpers:

```text
POST /api/admin/solari/inventory
POST /api/admin/solari/bank
```

Inventory Solari grants create fresh carried `SolarisCoin` item stacks in free slots with `dune.save_item(dune.inventoryitem)`. Exchange/bank Solari grants update the visible Solaris row in `dune.player_virtual_currency_balances`, ensure the Exchange user row with `dune.dune_exchange_get_user_id`, and mirror the value to `dune.dune_exchange_users.solari_balance`. Do not use `dune.dune_exchange_modify_user_solari_balance` as a grant primitive; it transfers existing wallet Solaris into the Exchange balance and subtracts the same amount from `player_virtual_currency_balances`. Execution requires the global mutation gate and the relevant confirmation phrase.

Bank Solari grants call the existing Exchange balance mutator path with `mode=add`. Execution requires the global mutation gate, `DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED=true`, and `confirm: "WRITE EXCHANGE"`.

Both endpoints default to dry-run and return before/after balance plans plus rollback data.

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

Both functions require `dune.is_player_offline(in_fls_id)` to be true. Live testing on 2026-05-21 showed `admin_move_offline_player_to_partition` is the right primitive when the player is actually treated as offline: it updates only the pawn actor row, and the client/server rejoin path can consume that pawn transform. Confidence: high for the tested same-partition Survival case, moderate for broader map/partition reuse.

The chat-command implementation deliberately does not write live online actor state. Online players are owned by the running map server, so a raw actor transform update can be overwritten or desynced. A same-partition live test moved the test player's controller, player-state, and pawn actor rows together by `+750` X and incremented their serial; the live Survival server then wrote the old in-memory position back on the next save cycle. For now, `&teleport <playername>` resolves the admin and target, rejects online targets, and calls `dune.admin_move_offline_player_to_partition(...)` only when execution is explicitly enabled.

The verified network-disconnect teleport path is documented in [soft-disconnect-teleport.md](soft-disconnect-teleport.md). DB-only presence flips were a false positive: they can trigger bot automation but do not release the live pawn. The working path forces a real `UNetConnection` timeout, waits for Survival to mark the player `Offline`, calls `dune.admin_move_offline_player_to_partition(...)`, then lets reconnect load the moved pawn.

Verified online-control boundary: game RabbitMQ JSON-RPC to the Director works when AMQP properties match the shipped `SimpleShaTokens.Rpc` contract (`type=json_rpc`, service `user_id`, `reply_to` bound on exchange `rpc`). The active Survival server queue consumes messages, but guessed server command methods for `PrintPos` did not produce a response or log hit. Confidence is high that online teleport needs the server-side RPC/command method contract, not another raw database actor update.

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
POST /api/admin/guild
POST /api/admin/marker
POST /api/admin/landclaim
POST /api/admin/exchange
POST /api/admin/player-tags
POST /api/admin/access-code
POST /api/admin/communinet
POST /api/admin/tutorial
POST /api/admin/permission
POST /api/admin/vendor
GET /api/admin/character-slots?account_id=<id>
POST /api/admin/character-slots/plan
POST /api/admin/character-slots/execute
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
dune.get_guild_data(in_guild_id bigint)
dune.get_guild_members(in_guild_id bigint)
dune.edit_guild_description(in_guild_id bigint, in_guild_desc text)
dune.promote_guild_member(in_guild_id bigint, in_player_id bigint, in_new_role smallint)
dune.demote_guild_member(in_guild_id bigint, in_player_id bigint, in_new_role smallint)
dune.delete_markers_by_id(in_marker_ids integer[])
dune.delete_static_location_markers(p_location_keys text[])
dune.delete_markers_return_actor_ids(in_dimension_index integer, in_map_name text, in_marker_ids integer[])
dune.get_landclaim_segments(in_totem_id bigint)
dune.add_landclaim_segment(in_totem_id bigint, in_grid_location_x bigint, in_grid_location_y bigint)
dune.dune_exchange_retrieve_solari_balance(in_owner_id bigint)
dune.dune_exchange_modify_user_solari_balance(in_controller_id bigint, in_solari_delta bigint)
dune.admin_read_player_tags(in_account_id bigint)
dune.update_player_tags(in_account_id bigint, tags_to_add text[], tags_to_remove text[])
dune.get_player_access_codes(in_account_id bigint)
dune.create_server_player_access_codes(in_account_id bigint, in_access_code integer, in_access_code_type integer, in_is_resettable boolean)
dune.delete_server_player_access_codes(in_account_id bigint, in_access_code integer, in_access_code_type integer)
dune.reset_server_all_player_access_codes(in_account_id bigint)
dune.load_communinet_player_data(in_account_id bigint)
dune.update_communinet_player_data(in_account_id bigint, in_is_active boolean, in_selected_channel_name text)
dune.update_communinet_player_channel(in_account_id bigint, in_channel_name text, in_is_tuned boolean)
dune.remove_communinet_player_channel(in_account_id bigint, in_channel_name text)
dune.get_all_tutorial_entries(in_player_id bigint)
dune.create_or_update_tutorial_entry(in_player_id bigint, in_tutorial_id smallint, in_tutorial_state smallint)
dune.permission_set_name(in_actor_id bigint, in_name text)
dune.permission_set_access_level(in_actor_id bigint, in_access_level smallint)
dune.permission_set_player_rank(in_actor_id bigint, in_player_id bigint, in_rank smallint, in_map_id text)
dune.permission_remove_player_rank(in_actor_id bigint, in_player_id bigint)
dune.update_vendor_timestamp_for_player(in_vendor_id text, in_player_id bigint, in_timestamp bigint)
dune.interact_get_vendor_items_bought_from_player(in_vendor_id text, in_player_id bigint, in_current_cycle_start_timestamp bigint)
```

Separate gates:

```env
DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED=false
DUNE_ADMIN_FACTION_MUTATIONS_ENABLED=false
DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED=false
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

Confirmation phrases:

```text
WRITE REPUTATION
CHANGE FACTION
WRITE JOURNEY
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
SWAP CHARACTER
```

Current confidence:

- Reputation: moderate-to-high mechanically because a first-party setter exists.
- Faction: moderate; guild side effects need disposable-character validation.
- Journey: moderate; functions exist, but story-node IDs and reward semantics need cataloging.
- Landsraad term end-time: moderate mechanically because first-party functions exist; high operational risk because it changes shared world/economy state. `force-end` is not safely reversible.
- Respawn-location delete: moderate mechanically because first-party array read/write functions exist; high rollback risk because restoring requires preserving and reconstructing the removed `respawnlocation` composite.
- Guild description and role changes: moderate mechanically because first-party functions exist; high social-state risk. Destructive guild operations remain blocked.
- Marker deletion: moderate mechanically because first-party delete functions exist; high rollback risk because marker save/recreation semantics are not mapped.
- Landclaim segment addition: low-to-moderate because add/get functions exist, but the current local table has no rows and no delete-segment rollback function is mapped.
- Dune Exchange Solari balance: moderate mechanically because first-party retrieve/modify functions exist; high economy risk. Order lifecycle functions remain blocked.
- Player tags: moderate mechanically because first-party read/update functions exist; medium operational risk.
- Access codes: moderate mechanically because first-party create/delete/reset functions exist; high operational risk because reset rollback is manual.
- Communinet: moderate mechanically because first-party read/update/remove functions exist; medium social/channel-state risk.
- Tutorial entry: moderate mechanically because first-party get/update functions exist; medium progression risk.
- Permission actor name/access/rank: moderate mechanically because first-party functions exist; high base access risk.
- Vendor stock-cycle timestamp: moderate mechanically because a first-party setter exists; medium economy/vendor-limit risk.
- Character slots: moderate for inspection and switch/restore execution because it reads `player_state`, `accounts`, `pg_proc`, and `information_schema`, then uses only the validated native `dune.takeover_account(in_user_to_takeover text, in_current_user text)` path when the plan is executable. `new-character` execution remains blocked because the mapped native blank-character path is destructive `delete_account`. No synthetic blank character rows or raw `player_state` surgery are allowed.

## Character Slot Hibernation And Switch

The panel endpoints are:

```text
GET /api/admin/character-slots?account_id=<id>
POST /api/admin/character-slots/plan
POST /api/admin/character-slots/execute
```

The read path inspects the active account row, candidate same-owner character rows, known identity columns, and native lifecycle function signatures. The inspected function set includes:

```text
login_account
delete_account
takeover_account
save_player
save_player_pawn
export_character
import_character
transfer_character
```

Those functions are evidence, not authorization. `takeover_account(in_user_to_takeover text, in_current_user text)` is the only mapped native switch/restore path. It swaps FLS user identity between two same-owner existing character accounts and is used only after the dry-run plan is executable.

Safe dry-run payloads:

```json
{"dry_run": true, "account_id": 456, "action": "new-character"}
```

```json
{"dry_run": true, "account_id": 456, "action": "switch-character", "target_account_id": 789}
```

Executable switch/restore plans include `plan.transactionSafety` so the API/UI
response shows the backup, advisory-lock, underlying account/player-state row
lock, offline-recheck, and post-swap verification requirements before the
operator executes the mutation.

Fail-closed rules:

- `switch-character` and `restore-character` require `target_account_id`.
- The target must be in the same-owner candidate set.
- Online active or target characters make the plan non-executable.
- Missing native contract returns `executable: false`.
- `new-character` returns `executable: false`; DASH does not call destructive `delete_account` to create a blank slot.
- Switch/restore execution creates a backup first, opens one DB transaction, takes account-id advisory locks, locks both underlying `encrypted_player_state` and `encrypted_accounts` rows, rechecks offline state, audits before/after rows, calls `dune.takeover_account(target_fls_id, active_fls_id)`, verifies the FLS identity swap, and returns an inverse restore payload.
- Non-dry-run execution requires `DUNE_ADMIN_MUTATIONS_ENABLED=true`, `DUNE_ADMIN_CHARACTER_SWAP_ENABLED=true`, and `confirm: "SWAP CHARACTER"`.
- Even with gates enabled, execution stops before backup/write when the plan is not executable.

Safe tests currently cover direct planner behavior plus handler-route behavior for GET, plan POST, dry-run execute POST, and rejected live execute POST. They intentionally do not fake `safeNativeSwapPath=true`, because that would normalize an execution path that has not been proven against native Dune lifecycle semantics.

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

## World State Inspect

The read-only endpoint is:

```text
POST /api/admin/world-state/inspect
```

It accepts optional `account_id`, `player_id`, and `guild_id`, then returns local evidence for:

```sql
dune.get_guild_for_player(...)
dune.get_guild_data(...)
dune.get_guild_members(...)
dune.get_guild_invites(...)
dune.get_player_owned_vehicles_data(...)
dune.player_respawn_locations
```

It also lists matching `pg_proc` signatures and `information_schema` table columns for guild, vehicle, marker, landclaim, recipe, and respawn surfaces. It deliberately does not call vehicle restore, marker save/delete, landclaim add, guild invite/remove/disband, or recipe removal functions.

## Guild Administration

The panel endpoint is:

```text
POST /api/admin/guild
```

Supported actions:

```text
edit-description
promote-member
demote-member
```

Mapped functions:

```sql
dune.edit_guild_description(in_guild_id bigint, in_guild_desc text)
dune.promote_guild_member(in_guild_id bigint, in_player_id bigint, in_new_role smallint)
dune.demote_guild_member(in_guild_id bigint, in_player_id bigint, in_new_role smallint)
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_GUILD_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE GUILD"`.

Rollback posture:

- Description edit: dry-run records the previous `guild_description`.
- Role change: dry-run records the previous `role_id` from `dune.guild_members`.

Blocked guild functions for now:

```sql
dune.create_guild(...)
dune.disband_guild(...)
dune.remove_guild_members(...)
dune.add_guild_invite(...)
dune.accept_guild_invite(...)
dune.reject_guild_invite(...)
dune.pledge_guild_allegiance(...)
dune.break_guild_allegiance(...)
```

Confidence is moderate for the narrow promoted functions and low for the blocked destructive/social-flow functions until role IDs, faction side effects, invite lifecycle, and rollback are validated on disposable guild data.

## Marker Deletion

The panel endpoint is:

```text
POST /api/admin/marker
```

Supported actions:

```text
delete-by-id
delete-static-location
```

Mapped functions:

```sql
dune.delete_markers_by_id(in_marker_ids integer[])
dune.delete_static_location_markers(p_location_keys text[])
dune.delete_markers_return_actor_ids(in_dimension_index integer, in_map_name text, in_marker_ids integer[])
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_MARKER_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "DELETE MARKERS"`.

Rollback posture is weak. The dry-run records matching marker rows when deleting by id, but marker recreation through `save_markers` is not mapped. Use only with disposable/static marker data until marker payloads, player-marker rows, and ID update semantics are fully documented.

## Landclaim Segment Addition

The panel endpoint is:

```text
POST /api/admin/landclaim
```

Supported action:

```text
add-segment
```

Mapped functions:

```sql
dune.get_landclaim_segments(in_totem_id bigint)
dune.add_landclaim_segment(in_totem_id bigint, in_grid_location_x bigint, in_grid_location_y bigint)
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE LANDCLAIM"`.

Rollback posture is weak. No delete-segment function is mapped. The current local database has an empty `dune.landclaim_segments` table, so live semantics need disposable base/totem validation before this is used on real claims.

## Economy And Exchange Inspection

The read-only endpoint is:

```text
POST /api/admin/economy/inspect
```

It accepts optional `account_id`, `player_id`, `controller_id`, and `exchange_id`, then returns local evidence for:

```sql
dune.dune_exchange_retrieve_solari_balance(...)
dune.dune_exchange_orders
dune.dune_exchange_users
dune.load_recovered_vehicles(...)
dune.load_backup_vehicle(...)
dune.base_backup_get_available_backups(...)
```

It also lists matching `pg_proc` signatures and `information_schema` table columns for exchange, vehicle, backup, and contract surfaces.

Current local evidence:

```text
vehicles: 3
vehicle_modules: 26
recovered_vehicles: 0
backup_vehicles: 1
dune_exchange_orders: 0
```

## Dune Exchange Solari Balance

The panel endpoint is:

```text
POST /api/admin/exchange
```

Supported modes:

```text
add
set
```

Mapped functions:

```sql
dune.dune_exchange_retrieve_solari_balance(in_owner_id bigint)
dune.dune_exchange_modify_user_solari_balance(in_controller_id bigint, in_solari_delta bigint)
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE EXCHANGE"`.

Rollback posture:

- Dry-run records the prior Exchange Solari balance.
- A compensating `mode=set` request can restore the prior balance.

Blocked Exchange functions for now:

```sql
dune.dune_exchange_add_sell_order(...)
dune.dune_exchange_fulfill_sell_order(...)
dune.dune_exchange_cancel_order(...)
dune.dune_exchange_relist_order(...)
dune.dune_exchange_retrieve_storage_item(...)
dune.dune_exchange_retrieve_solaris_from_item(...)
dune.dune_exchange_expire_orders(...)
dune.dune_exchange_purge_completed_orders(...)
```

Confidence is moderate for balance mechanics and low for order lifecycle operations until inventory IDs, order revisions, completion types, purge timing, and item transfer rollback are documented.

## Player Lifecycle Inspection

The read-only endpoint is:

```text
POST /api/admin/player-lifecycle/inspect
```

It accepts optional `account_id` and `player_id`, then returns local evidence for:

```sql
dune.admin_read_player_tags(...)
dune.get_player_access_codes(...)
dune.load_communinet_player_data(...)
dune.get_all_party_invites(...)
dune.party_members
dune.accounts
dune.player_state
```

It also lists matching `pg_proc` signatures and `information_schema` columns for party, account, player, Communinet, access-code, tag, dungeon, and tutorial surfaces.

Current local evidence:

```text
accounts: 16
player_state: 16
parties: 0
party_members: 0
```

## Player Tags

The panel endpoint is:

```text
POST /api/admin/player-tags
```

Mapped functions:

```sql
dune.admin_read_player_tags(in_account_id bigint)
dune.update_player_tags(in_account_id bigint, tags_to_add text[], tags_to_remove text[])
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE PLAYER TAGS"`.

Rollback is the inverse add/remove operation from the audit record. Confidence is moderate.

## Access Codes

The panel endpoint is:

```text
POST /api/admin/access-code
```

Supported actions:

```text
create
delete
reset
```

Mapped functions:

```sql
dune.get_player_access_codes(in_account_id bigint)
dune.create_server_player_access_codes(in_account_id bigint, in_access_code integer, in_access_code_type integer, in_is_resettable boolean)
dune.delete_server_player_access_codes(in_account_id bigint, in_access_code integer, in_access_code_type integer)
dune.reset_server_all_player_access_codes(in_account_id bigint)
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE ACCESS CODES"`.

Create/delete have compensating rollback. Reset is higher risk because rollback requires recreating prior access codes from the dry-run/audit record.

## Communinet

The panel endpoint is:

```text
POST /api/admin/communinet
```

Supported actions:

```text
update-data
update-channel
remove-channel
```

Mapped functions:

```sql
dune.load_communinet_player_data(in_account_id bigint)
dune.update_communinet_player_data(in_account_id bigint, in_is_active boolean, in_selected_channel_name text)
dune.update_communinet_player_channel(in_account_id bigint, in_channel_name text, in_is_tuned boolean)
dune.remove_communinet_player_channel(in_account_id bigint, in_channel_name text)
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE COMMUNINET"`.

Rollback is a compensating data/channel update from prior rows recorded in the dry-run/audit record. Current local evidence shows 16 `communinet_player` rows and 112 `communinet_player_channels` rows.

## Blocked Vendor, Tutorial, Lore, Dungeon, Overmap, And Coriolis Routes

The following functions are cataloged but blocked:

```sql
dune.player_purchased_item_from_vendor(...)
dune.update_vendor_timestamp_for_player(...)
dune.clean_stock_for_player(...)
dune.create_or_update_tutorial_entry(...)
dune.delete_all_tutorial_entries(...)
dune.register_lore_pickup(...)
dune.register_per_player_lore_pickup(...)
dune.update_consumed_per_player_lore(...)
dune.record_dungeon_completion(...)
dune.delete_all_dungeon_completions_by_player(...)
dune.overmap_save_player_survival_data(...)
dune.overmap_delete_player_survival_data(...)
dune.update_coriolis_for_player(...)
dune.coriolis_update_seed(...)
```

Local evidence found:

```text
communinet_player: 16
communinet_player_channels: 112
tutorial_per_player: 223
overmap_players: 1
dungeon_completion_players: 0
```

Confidence is moderate for function existence and low for safe admin mutation semantics. These routes affect client progression, vendor limits, survival/overmap state, dungeon records, and map/server lifecycle behavior.

## Tutorial Entry

The panel endpoint is:

```text
POST /api/admin/tutorial
```

Mapped functions:

```sql
dune.get_all_tutorial_entries(in_player_id bigint)
dune.create_or_update_tutorial_entry(in_player_id bigint, in_tutorial_id smallint, in_tutorial_state smallint)
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE TUTORIAL"`.

Rollback is a compensating state update when a previous row existed. If the dry-run shows no previous row, deletion rollback is not exposed because no narrow single-entry delete function is mapped.

## Permission Actor

The panel endpoint is:

```text
POST /api/admin/permission
```

Supported actions:

```text
set-name
set-access-level
set-player-rank
remove-player-rank
```

Mapped functions:

```sql
dune.permission_set_name(in_actor_id bigint, in_name text)
dune.permission_set_access_level(in_actor_id bigint, in_access_level smallint)
dune.permission_set_player_rank(in_actor_id bigint, in_player_id bigint, in_rank smallint, in_map_id text)
dune.permission_remove_player_rank(in_actor_id bigint, in_player_id bigint)
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE PERMISSION"`.

Dry-run reads `dune.permission_actor` and `dune.permission_actor_rank` for rollback context. Confidence is moderate mechanically and high risk operationally.

Blocked permission functions:

```sql
dune.permission_actor_register(...)
dune.permission_actor_takeover(...)
dune.permission_actor_destroy(...)
dune.permission_actor_create_or_update_base_marker(...)
dune.permission_actor_update_marker_location(...)
```

Local evidence found:

```text
permission_actor: 72
permission_actor_rank: 19
```

## Vendor Cycle Timestamp

The panel endpoint is:

```text
POST /api/admin/vendor
```

Supported action:

```text
set-cycle-timestamp
```

Mapped functions:

```sql
dune.update_vendor_timestamp_for_player(in_vendor_id text, in_player_id bigint, in_timestamp bigint)
dune.interact_get_vendor_items_bought_from_player(in_vendor_id text, in_player_id bigint, in_current_cycle_start_timestamp bigint)
```

Execution is blocked unless the global mutation gate and `DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED=true` are both set, and the request includes `confirm: "WRITE VENDOR"`.

Dry-run reads the prior `dune.vendor_stock_cycle` row and item-bought view for the proposed timestamp.

Local evidence found:

```text
vendor_stock_cycle: 6
vendor_stock_state: 0
```

## Blocked Taxation, Landsraad Task, Vendor Stock, Lore, And Dungeon Routes

The following functions are cataloged but blocked:

```sql
dune.taxation_pay_invoice(...)
dune.taxation_remove_invoices(...)
dune.taxation_update_invoice_status(...)
dune.landsraad_insert_task_progress(...)
dune.landsraad_update_task_faction_reveal_state(...)
dune.landsraad_perform_daily_task_reveal(...)
dune.player_purchased_item_from_vendor(...)
dune.clean_stock_for_vendors(...)
dune.register_lore_pickup(...)
dune.register_per_player_lore_pickup(...)
dune.update_consumed_per_player_lore(...)
dune.record_dungeon_completion(...)
dune.delete_all_dungeon_completions_by_player(...)
```

Local evidence found:

```text
tutorials: 103
tutorial_per_player: 223
vendor_stock_state: 0
vendor_stock_cycle: 6
landsraad_task_progress_player: 0
landsraad_task_player_contributions: 0
```

Confidence is moderate for existence and low for safe mutation semantics. These routes affect base permissions, taxes, competitive Landsraad progression, and vendor limits.

## Blocked Player Lifecycle Routes

The following functions are cataloged but blocked:

```sql
dune.delete_account(...)
dune.set_account_as_takeoverable(...)
dune.takeover_account(...)
dune.login_account(...)
dune.save_player(...)
dune.save_player_pawn(...)
dune.accept_party_invite(...)
dune.add_party_invite(...)
dune.remove_party_member(...)
dune.disband_party(...)
dune.update_communinet_player_data(...)
dune.update_communinet_player_channel(...)
dune.delete_all_dungeon_completions_by_player(...)
dune.overmap_save_player_survival_data(...)
```

Confidence is low for safe admin mutation semantics until lifecycle side effects, online/offline constraints, account ownership, party session state, and rollback/recovery are validated.

## Vehicle And Base Backup Limits

Vehicle and base backup functions are cataloged but blocked for execution:

```sql
dune.restore_recovered_vehicle(...)
dune.restore_backup_vehicle(...)
dune.store_recovered_vehicle(...)
dune.save_vehicle_modules(...)
dune.base_backup_save(...)
dune.base_backup_save_from_totem(...)
dune.base_backup_recycle(...)
dune.base_backup_delete(...)
```

Confidence is moderate for read functions and low for write functions. Restore/spawn paths require `serverinfo`, nested `transform`, inventory ownership, spawned actor ownership, and live map-server refresh semantics to be validated before any safe admin mutator is exposed.
