# Native Player and Vehicle Actions

The Admin Actions page exposes the Red-Blink player-action outcome through
DASH's existing authenticated control plane. The native command contract is
adapted from Red-Blink commit
`12ac3b8b30a0dac3d728a37db65cad4a292750b6` under the MIT license recorded in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

## Native notification contract

`POST /api/admin/player-runtime-action` builds an inner command such as:

```json
{"ServerCommand":"UpdateAllWaterFillables","PlayerId":"<funcom-id>","WaterAmount":1000000}
```

It serializes that JSON into `MessageContent` inside this envelope:

```json
{"Version":2,"AuthToken":"<DUNE_SERVER_COMMANDS_AUTH_TOKEN>","MessageContent":"<inner-json>"}
```

The admin panel uses the mounted Docker socket to execute `rabbitmqctl eval`
inside the project `game-rmq` container and publishes to the `heartbeats`
exchange with routing key `notifications`, application id `fls_backend`, and
user id `fls`. Tokens and non-wildcard player ids are redacted from previews
and audit output. `publish=ok` proves broker acceptance; it does not prove that
the game client rendered the result.

Supported actions:

| Browser action | Native command | Constraints |
| --- | --- | --- |
| Set unspent skill points | `SkillsSetUnspentSkillPoints` | 0..100,000 |
| Set skill module level | `SkillsSetModuleLevel` | Module and max level come from the pinned catalog |
| Refill water containers | `UpdateAllWaterFillables` | Online target; 1..1,000,000,000 |
| Kick player | `KickPlayer` | Online by default; forced offline publish is API-only |
| Kick all online players | `KickPlayer`, `PlayerId="*"` | Exact `KICK ALL ONLINE PLAYERS` confirmation |
| Teleport online player | `TeleportTo` | Online target; bounded finite X/Y/Z and yaw |
| Clean inventory | `CleanPlayerInventory` | Destructive Version 2 player command |
| Reset progression | `ResetProgression` | Destructive Version 2 player command |
| Spawn vehicle | `SpawnVehicleAt` | Online target, catalog vehicle/template, finite coordinates |

The source catalogs are
[`config/admin-skill-modules.json`](../config/admin-skill-modules.json) and
[`config/admin-vehicles.json`](../config/admin-vehicles.json). Vehicle spawn
records the previous maximum vehicle id, creates a database backup, publishes
the command, polls for the matching new actor, and installs the owner rank in
`dune.permission_actor` and `dune.permission_actor_rank`.

## Gates and configuration

Execution requires:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_GM_COMMANDS_ENABLED=true
DUNE_ADMIN_PLAYER_RUNTIME_MUTATIONS_ENABLED=true
DUNE_SERVER_NOTIFICATION_SYSTEM_ENABLED=true
DUNE_SERVER_COMMANDS_AUTH_TOKEN=<private-random-token>
```

Recreate game-map containers after setting the notification/token values so
the Compose command-line settings reach every map. The admin panel must also be
recreated so it receives the same token. Use `RUN PLAYER ACTION` for individual
execution. Kick-all uses its separate phrase.

This path does not use `DUNE_GM_COMMAND_PAYLOAD_VERIFIED`. That older gate
belongs to `scripts/dune_gm_command.py` and its unsuccessful admin-RMQ RPC
envelope experiments. The player-action endpoint uses the newer Red-Blink
Version 2 game-notification contract.

## Offline vehicle maintenance

`POST /api/admin/vehicle` supports:

- `repair-decay`: repairs owned modules whose decayed maximum durability is
  below the selected 1..100 percent threshold;
- `refuel`: writes `1.0` to the selected owned vehicle actor's
  `<BPClass>.m_InitialFuel` property.

Both operations:

- require the player to be offline before planning and again under a locked
  player-state row during execution;
- require the master gate and
  `DUNE_ADMIN_VEHICLE_MUTATIONS_ENABLED=true`;
- require `REPAIR VEHICLE DECAY` or `REFUEL VEHICLE`;
- create a Postgres backup before changing data;
- commit in one transaction and report that a relog is required.

## Player recovery and gear repair

`POST /api/admin/player-maintenance` adds the remaining pinned Red player
maintenance outcomes:

- `add-intel` applies an offline-only grant capped at the observed spendable
  maximum of `2779`;
- `unlock-recipe` validates the recipe against recipes already present in the
  game database and appends the native known-recipe JSON shape;
- `unlock-research` validates the research key against game data, sets its
  native state to `Purchased`, and materializes its derived `RCP_` or `BLD_`
  crafting recipe when that recipe is known to the game database;
- `specialization-max` sets the selected track to Red's observed maximum of
  `44182` XP and level `100`, while `specialization-reset` removes that track;
- `keystones-grant-all` inserts every known specialization keystone with
  conflict-safe deduplication;
- `repair-gear` scans inventory types `0, 1, 14, 15, 27, 30`, restores current
  and decayed durability to the effective maximum in one transaction, requires
  an offline player, and creates a database backup;
- `repair-login-queue` lists queues inside the project `game-rmq`, selects only
  `<FuncomId>_queue`, and deletes that exact queue after `REPAIR LOGIN QUEUE`.
  It refuses a player whom PostgreSQL still reports Online unless the operator
  explicitly sets `force=true`.

The six progression actions require `WRITE PLAYER PROGRESSION`, an offline
target, the master and player-runtime gates, an automatic database backup, a
locked recheck, one transaction, and a relog. Their dry-run bodies accept
`amount` for Intel, `key` for recipe/research, or `track_type` for a
specialization operation. All six are available in the Admin Actions browser
panel as well as the JSON API.

The three actor-JSON actions (`add-intel`, `unlock-recipe`, and
`unlock-research`) additionally compare-and-swap the complete actor properties,
post-verify the exact affected state, and write a private self-hashed receipt.
`rollback-progression` requires `ROLL BACK PLAYER PROGRESSION`, matches the
receipt to the active database and player, requires the player to remain
Offline, and restores only when the current affected-state hash still equals
the receipt after hash. It creates both a new database backup and an inverse
receipt. Specialization and keystone actions retain their first-party
table/function mutation paths and are not claimed as receipt-reversible. See
[`player-progression-receipts.md`](player-progression-receipts.md).

## Landsraad additions

`POST /api/admin/landsraad` now includes `task-goal`, `term-task-goals`,
`reward-tier`, and `player-contribution` alongside term end-time and force-end
actions. Goal writes preserve every previous goal in a compensating rollback
list. Reward
updates identify the existing row by task and old threshold. Contribution
writes replace the selected player's value and recalculate faction totals and,
when the tables exist, guild totals in the same transaction. Every execution
requires `DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED=true`, `WRITE LANDSRAAD`, and
a pre-write database backup. Dry-run responses include the previous row and a
compensating rollback body.
