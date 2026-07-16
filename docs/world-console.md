# World Console

The admin panel `World` page is a token-protected, read-only browser for guild,
Landsraad, and aggregate base-storage state. Separately gated Admin actions can
write selected Landsraad reward and contribution state. It was added during the pinned
Red-Blink feature-parity audit documented in
[`red-blink-feature-parity-audit.md`](red-blink-feature-parity-audit.md).

## Routes

| Method and route | Result | Bound |
| --- | --- | --- |
| `GET /api/world/guilds?q=<text>` | Guild rows and member counts | 500 guilds; 200-character search |
| `GET /api/world/guild-members?guild_id=<id>` | Native guild detail, members, and invites | 200 invites |
| `GET /api/world/landsraad` | Current/recent terms, decrees, tasks, rewards, and contribution rows | 500 tasks/decrees; 1,000 rows per reward/contribution set |
| `GET /api/world/storage` | Known storage actors, class, map, item count, and inferred owner name | 2,000 storage actors |
| `GET /api/world/storage-items?actor_id=<id>` | Inventories and item rows for one selected storage actor; JSON response is directly exportable | 5,000 items |

All five routes use `SELECT` statements or first-party read functions. They do
not call the general SQL preview endpoint and do not expose an arbitrary query
parameter.

## Guild Reads

The guild list reads `dune.guilds` and counts matching rows in
`dune.guild_members`. Selecting a guild calls the shipped read functions:

- `dune.get_guild_data(...)`
- `dune.get_guild_members(...)`
- `dune.get_guild_invites(...)`

Guild description and role mutations remain separate, dry-run-first actions
under the mutation gates documented in [`admin-panel.md`](admin-panel.md).

## Landsraad Reads

The page reads the current term through `dune.landsraad_load_current_term()`
and then reads the matching rows from:

- `dune.landsraad_decree_term`
- `dune.landsraad_decrees`
- `dune.landsraad_tasks`
- `dune.landsraad_task_rewards`
- faction, player, and guild contribution tables

Schema-dependent subqueries fail independently. An unavailable contribution
table produces an `Unavailable schema surfaces` entry instead of making the
whole World page fail.

The World page itself cannot change term goals, rewards, contribution totals,
or reveal state. The guarded `POST /api/admin/landsraad` route supports
`change-end-time`, `force-end`, `reward-tier`, and `player-contribution` from the
Admin Actions page. Every write requires the master and Landsraad gates, an
exact confirmation, an automatic database backup, and a transaction. Reward
and contribution writes return previous values for rollback; contribution
writes recompute the affected faction and guild totals. Coriolis/Landsraad
cycle safety rules still apply.

## Aggregate Storage Reads

The storage query is limited to these observed storage placeable classes:

- `SpiceSilo_Placeable`
- `GenericContainer_Placeable`
- `StorageContainer_Placeable`
- `MediumStorageContainer_Placeable`

Holograms and rows without a nonzero owner entity are excluded. Owner names are
inferred through the placeable owner entity, permission actor rank, player
actor, and player-state joins. A blank owner name means the join did not resolve
a character; it does not prove that the container is unowned.

The World summary shows aggregate item counts; the storage-items route provides
a bounded read-only detail/export response for a selected actor. Neither route
can change container contents. Guarded base-storage item grants remain the separate,
explicit workflow in [`base-storage-item-grants.md`](base-storage-item-grants.md).

## Validation

Run:

```bash
python3 -m py_compile admin/admin_panel.py scripts/test-admin-panel-safe-surfaces.py
python3 scripts/test-admin-panel-safe-surfaces.py
```

The safe-surface tests verify that the world helpers do not call the SQL write
executor, enforce a positive guild ID, preserve query bounds, and register the
browser/API routes.

Confidence is **high** that the World browser surface is read-only and that the
write surface is independently gated. Confidence is **moderate**
for complete results across future Funcom database revisions because the
underlying optional Landsraad contribution tables can change or be absent.
