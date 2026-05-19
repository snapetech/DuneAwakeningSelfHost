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
```

These functions explicitly reject some operations when the player is online. The panel does not expose them yet because story node IDs and reward semantics need mapping.
