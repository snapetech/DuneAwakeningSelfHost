# Base Storage Item Grants

This runbook explains how to add an item stack directly to a base storage
container. It is written with placeholders so operators can use it in different
deployments without copying hostnames, addresses, credentials, player names, or
database identifiers from another server.

Confidence is **high** for the database ownership model and the
`dune.save_item(dune.inventoryitem)` grant path. Confidence is **moderate** for
immediate visibility while the affected game map has the container loaded in
memory; verify every live grant in the database and in game.

## Safety Boundary

- Follow the operational target-safety rules in the repository `AGENTS.md`.
- Run `hostname` immediately before any live write and confirm that it is the
  designated production admin host. Stop if it is not.
- Do discovery and selection as read-only database transactions.
- Do not copy an inventory ID from another server, environment, or container.
- Prefer a closed container and no player actively viewing it during the write.
- Always run the item-grant dry-run before execution.
- Do not repeat a grant merely because it is not immediately visible. Inspect
  the database first to avoid creating duplicate stacks.

## How Base Storage Is Represented

Base storage is not a special grant destination. A placed storage box is an
actor with a row in `dune.placeables`, and its contents live in a related row in
`dune.inventories`:

```text
dune.placeables.id
        |
        +-- dune.actors.id
        |
        +-- dune.inventories.actor_id
                    |
                    +-- dune.items.inventory_id
```

Base membership is derived from the placed actor and totem sharing the same
`placeables.owner_entity_id`. Player access is represented by
`dune.permission_actor_rank` rows on the totem. Observed base item containers
and spice silos use inventory type `4`; crafting stations and generators may
have other inventory types and should not be mistaken for storage boxes.

An exact `inventory_id` overrides player-inventory auto-resolution in
`scripts/admin-grant-item.py`. The required character argument still resolves
the operator-facing player context, while the explicit inventory ID determines
where the new item row is saved.

## Identify the Exact Box

Identical placed boxes normally have generic database names. Their actor IDs,
coordinates, current contents, and inventory IDs differ. The least ambiguous
workflow is:

1. Put a distinctive item or unusual stack count in the intended box through
   the game.
2. Close the box UI and allow the server to persist the change.
3. Run the read-only query below for a player who has permission on that base.
4. Find the row containing the marker stack and record its `inventory_id`.
5. Check `used_slots`, `max_item_count`, class, totem, and transform before
   proceeding.

Replace the uppercase placeholders before running this command:

```bash
docker compose --env-file ENVIRONMENT_FILE exec -T DATABASE_SERVICE \
  psql -U DATABASE_USER -d DATABASE_NAME -P pager=off -c "
begin transaction read only;
with target_player as (
  select player_pawn_id, player_controller_id
  from dune.player_state
  where character_name ilike 'TARGET_CHARACTER'
),
permitted_totems as (
  select distinct t.id as totem_id, tp.owner_entity_id
  from dune.totems t
  join dune.placeables tp on tp.id=t.id
  join dune.permission_actor_rank par on par.permission_actor_id=t.id
  cross join target_player p
  where par.player_id in (p.player_pawn_id,p.player_controller_id)
)
select
  inv.id as inventory_id,
  pt.totem_id,
  inv.max_item_count,
  count(i.id) as used_slots,
  case
    when inv.max_item_count is null or inv.max_item_count < 0 then null
    else greatest(inv.max_item_count-count(i.id),0)
  end as free_slots,
  a.class,
  a.transform,
  string_agg(
    i.template_id || ' x' || i.stack_size,
    ', ' order by i.position_index
  ) as contents
from permitted_totems pt
join dune.placeables box
  on box.owner_entity_id=pt.owner_entity_id
 and box.id<>pt.totem_id
join dune.actors a on a.id=box.id
join dune.inventories inv on inv.actor_id=box.id
left join dune.items i on i.inventory_id=inv.id
where inv.inventory_type=4
group by inv.id,pt.totem_id,a.id
order by pt.totem_id,inv.id;
rollback;"
```

If character names are not unique, replace the target-player predicate with an
exact account ID predicate:

```sql
where account_id = TARGET_ACCOUNT_ID
```

Do not select a box solely because it has free slots. Confirm it using the
marker contents or actor transform. A destroyed and rebuilt box receives a
different actor/inventory identity.

## Dry-Run the Grant

The command-line helper resolves reviewed display labels through the local item
catalog, validates that the inventory exists, and selects the first free slot
within `max_item_count`:

```bash
./scripts/admin-grant-item.py "ITEM_NAME_OR_TEMPLATE_ID" STACK_COUNT \
  --character "TARGET_CHARACTER" \
  --inventory-id TARGET_INVENTORY_ID \
  --env-file ENVIRONMENT_FILE \
  --db DATABASE_NAME
```

The default is a read-only dry-run. Check all of these fields in its JSON
output:

- `dryRun` is `true`.
- `player` is the intended player context.
- `inventory.inventoryId` is the marker-verified box inventory.
- `inventory.maxItemCount` has room for another row.
- `positionIndex` is an unused slot.
- `item.templateId` and `item.count` are correct.
- Item-catalog confidence and source are acceptable.

The helper checks slot count, but it does not prove that the resulting contents
fit the inventory's volume limit or the template's normal maximum stack size.
Use a stack size already observed as valid for that item type.

## Execute the Grant

Re-run the host check required by `AGENTS.md`, then append the guarded execution
arguments to the already-reviewed dry-run command:

```bash
hostname

./scripts/admin-grant-item.py "ITEM_NAME_OR_TEMPLATE_ID" STACK_COUNT \
  --character "TARGET_CHARACTER" \
  --inventory-id TARGET_INVENTORY_ID \
  --env-file ENVIRONMENT_FILE \
  --db DATABASE_NAME \
  --execute \
  --confirm "GRANT ITEM"
```

Execution performs the following database operations:

1. Rechecks that the selected `position_index` is empty.
2. Allocates an item ID with `dune.advance_items_id_sequencer(1)`.
3. Calls `dune.save_item((...)::dune.inventoryitem)`.
4. Confirms that the new row exists at the requested inventory and slot.

The operation is additive. Every successful execution creates a new item row;
it does not merge with an existing stack and does not declare the box's full
inventory state.

## Admin Panel Alternative

The Admin Actions item-grant form can use the same mechanism:

1. Open **Admin Actions** and locate **Item Grants**.
2. Enter the marker-verified box ID in **Inventory ID**. Base boxes may not
   appear in the player-owned inventory dropdown, so manual entry is expected.
3. Enter the exact template ID, stack size, quality, and any required stats.
4. Run **Dry run** and inspect the target inventory and warnings.
5. Execute only after the dry-run result is correct and the mutation gates are
   deliberately enabled.

The warning that a base inventory is not directly tied to a player
pawn/controller is expected. It is a reminder to verify the box ownership and
does not by itself invalidate the target.

## Verify the Result

Record the `itemId`, `inventoryId`, `positionIndex`, `stackSize`, and
`templateId` returned by the helper. Verify the row with a read-only query:

```sql
begin transaction read only;
select id, inventory_id, stack_size, position_index, template_id,
       quality_level, stats
from dune.items
where id = GRANTED_ITEM_ID
  and inventory_id = TARGET_INVENTORY_ID;
rollback;
```

Then reopen the box in game. If the row exists but the item is not visible:

1. Close and reopen the container.
2. Reconnect the observing player if needed.
3. Confirm that the row still exists and was not overwritten by runtime state.
4. Review the affected map logs.
5. If a map restart is required, use the repository-approved restart wrapper
   that runs post-start health and runtime-patch hooks. Do not use a raw
   Compose restart path.

Do not execute the grant a second time until the first item ID has been located
or proven absent.

## Resources Versus Equipment

Resources and other ordinary stackable materials are the safest candidates
because they commonly work with empty stats JSON and quality `0`.

Equipment grants require more care:

- Gear can require template-specific `stats` JSON.
- Durability or condition may be encoded in stats rather than inferred from the
  template ID.
- Quality is a separate `quality_level` field.
- An empty stats object can create an incomplete or unusable item even when the
  database accepts it.

For equipment, first inspect a known-valid item of the same template and copy
only the understood stats/quality shape. The CLI accepts `--stats` and
`--quality`; the admin panel exposes the same values. Confidence is **moderate**
for an equipment grant unless its exact persisted shape has already been
validated.

## Banks and Exchange Storage Are Different

Do not treat the Exchange/Solari bank as a base item container.

- Base boxes are actor-owned `dune.inventories` rows and store `dune.items`.
- Player Exchange/Solari bank value is represented by currency/balance state,
  including `dune.player_virtual_currency_balances` and
  `dune.dune_exchange_users.solari_balance`.
- The Exchange staging inventory is exchange-owned and is used for order
  mechanics. It is not a player's personal item bank.
- Item-owned sub-inventories and vehicle-module inventories also use different
  ownership columns and lookup functions.

Use the guarded Solari-bank action for bank currency. Do not point the generic
item-grant helper at an exchange-owned staging inventory. If a future game
surface labeled "bank" exposes actual item storage, prove its actor/inventory
ownership and player scoping before treating it like a base box.

## Relevant Implementation

- `scripts/admin-grant-item.py`: exact-inventory selection, slot selection,
  dry-run planning, guarded execution, and `dune.save_item` call.
- `scripts/admin-chat-commands.py`: permission-aware discovery of player and
  base-storage inventories for auction sources.
- `admin/admin_panel.py`: browser item-grant dry-run and mutation path.
- `docs/admin-mutation-map.md`: inventory and item database contracts.
- `SERVER_RUNTIME_SURFACES.md`: inventory ownership model and mapped database
  functions.
