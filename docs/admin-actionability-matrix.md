# Admin Actionability Matrix

This document answers which cataloged evidence is actionable now. Confidence levels are `high`, `moderate`, `low`, or `unknown`.

Default posture: every listed execution path still requires `DUNE_ADMIN_MUTATIONS_ENABLED=true`, its specific feature gate, its exact confirmation phrase, and an audit record. Dry-runs and inspectors are the default operating mode.

## Actionable Now

These surfaces have implemented endpoints and can be previewed immediately with `dry_run=true`. Execution is possible only after enabling the listed gate.

| Surface | Endpoint | Gate | Confirmation | Confidence | Notes |
| --- | --- | --- | --- | --- | --- |
| Typed config knobs | `POST /api/settings/typed-knobs` | `DUNE_ADMIN_TYPED_KNOBS_ENABLED` | `WRITE TYPED KNOBS` | high for promoted knobs | Writes config with backup; restart required for most effects. |
| Economy bundle | `POST /api/admin/bundle` | `DUNE_ADMIN_BUNDLE_MUTATIONS_ENABLED` | `EXECUTE BUNDLE` | high for plan, moderate for broad execution | Currency, XP, and item grants share one audited plan. |
| Offline player recovery | `POST /api/admin/player-recovery/offline-teleport` | global mutation gate | `MOVE OFFLINE PLAYER` | moderate | Refuses online target players. |
| Faction reputation | `POST /api/admin/faction-reputation` | `DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED` | `WRITE REPUTATION` | moderate-to-high | Uses first-party setter/getter. |
| Player faction | `POST /api/admin/faction` | `DUNE_ADMIN_FACTION_MUTATIONS_ENABLED` | `CHANGE FACTION` | moderate | Offline-only; guild side effects still need disposable validation. |
| Journey story nodes | `POST /api/admin/journey` | `DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED` | `WRITE JOURNEY` | moderate | Reveal, complete, reset, delete known story-node ids. |
| Landsraad term | `POST /api/admin/landsraad` | `DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED` | `WRITE LANDSRAAD` | moderate mechanics, very high risk | End-time change has rollback; force-end is not safely reversible. |
| Respawn location delete | `POST /api/admin/respawn-location` | `DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED` | `DELETE RESPAWN` | moderate | Delete only; creation/editing blocked. |
| Guild description/roles | `POST /api/admin/guild` | `DUNE_ADMIN_GUILD_MUTATIONS_ENABLED` | `WRITE GUILD` | moderate | Description, promote, demote only. |
| Marker deletion | `POST /api/admin/marker` | `DUNE_ADMIN_MARKER_MUTATIONS_ENABLED` | `DELETE MARKERS` | moderate mechanics, high rollback risk | Delete by id or static-location key; creation/editing blocked. |
| Landclaim segment add | `POST /api/admin/landclaim` | `DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED` | `WRITE LANDCLAIM` | low-to-moderate | No mapped delete-segment rollback. |
| Dune Exchange Solari | `POST /api/admin/exchange` | `DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED` | `WRITE EXCHANGE` | moderate | Balance add/set only; order lifecycle blocked. |
| Player tags | `POST /api/admin/player-tags` | `DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED` | `WRITE PLAYER TAGS` | moderate | Add/remove with inverse rollback. |
| Access codes | `POST /api/admin/access-code` | `DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED` | `WRITE ACCESS CODES` | moderate | Create/delete/reset; reset rollback is manual from audit. |
| Communinet | `POST /api/admin/communinet` | `DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED` | `WRITE COMMUNINET` | moderate | Player active/selected channel and per-channel tuned/remove. |
| Tutorial entry | `POST /api/admin/tutorial` | `DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED` | `WRITE TUTORIAL` | moderate | Create/update one tutorial row; delete not exposed. |
| Permission actor | `POST /api/admin/permission` | `DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED` | `WRITE PERMISSION` | moderate mechanics, high risk | Name/access/rank only; register/takeover/destroy blocked. |
| Vendor cycle timestamp | `POST /api/admin/vendor` | `DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED` | `WRITE VENDOR` | moderate | Timestamp only; purchase counts and stock cleanup blocked. |

## Read-Only But Useful

These endpoints turn evidence into operator decisions without writing state.

| Surface | Endpoint | Confidence | Use |
| --- | --- | --- | --- |
| Catalog | `GET /api/catalog/surfaces`, `/api/catalog/evidence`, `/api/catalog/validation` | high for schema delivery | See all known surfaces, confidence, risk, validation, rollback. |
| Spice/resource fields | `POST /api/admin/spice-fields/inspect` | high for local DB reads | Validate Deep Desert cap changes before/after restart. |
| Progression | `POST /api/admin/progression/inspect` | moderate | Discover player faction, reputation, journey, recipe, vehicle functions. |
| World state | `POST /api/admin/world-state/inspect` | moderate | Discover guild, vehicle, marker, landclaim, permission, respawn state. |
| Economy | `POST /api/admin/economy/inspect` | moderate | Discover exchange, vehicle backup/recovery, base backup state. |
| Player lifecycle | `POST /api/admin/player-lifecycle/inspect` | moderate | Discover account/player, tags, access codes, Communinet, party, tutorial, vendor state. |
| Events | `POST /api/events/dry-run` | high for fail-closed planning | Compose announcements, restart plans, config proposals, and dry-run-only actions. |

## Evidence Only

These have local evidence but are not safe admin writes yet.

| Surface | Confidence | Why blocked |
| --- | --- | --- |
| Recipe grants/unlocks | low for mutation semantics | No safe grant/upsert function mapped. |
| Vehicle restore/spawn/module writes | low for mutation semantics | Needs `serverinfo`, `transform`, inventory ownership, actor ownership, and live map refresh validation. |
| Base backup save/recycle/delete | low for mutation semantics | Spawned actor ownership and rollback are not mapped. |
| Exchange order add/fulfill/cancel/relist/retrieve/purge | low for safe admin semantics | Requires inventory locking, order revisions, completion types, purge timing, and item transfer rollback. |
| Guild create/disband/remove/invite/allegiance | low-to-moderate | Social/faction side effects and rollback are not mapped. |
| Permission actor register/takeover/destroy/marker-location | low-to-moderate | Base ownership side effects are high risk. |
| Marker creation/editing | low | `save_markers`, marker payloads, player-marker rows, and id updates are not mapped safely. |
| Respawn creation/editing | low | `spawnlocatordescriptor` and restoration semantics are not mapped. |
| Taxation invoice pay/remove/status | low | Tax lifecycle and rollback are not validated. |
| Landsraad task progress/reveal | low-to-moderate | Competitive world state; task lifecycle side effects are not validated. |
| Vendor purchase counts/stock cleanup | low-to-moderate | Stock cycle and player purchase semantics need live validation. |
| Lore registration/consumption | low | Bit-array mapping and client refresh semantics are not mapped. |
| Dungeon completion record/delete | low | Completion records are empty locally and rollback is unclear. |
| Overmap survival save/delete | low | Vehicle/location state and client refresh semantics are not mapped. |
| Coriolis DB/player/map writes | low | Map/server lifecycle and wipe/seed effects are high risk. |
| Native GM command execution | low | Requires verified live RabbitMQ payload and `DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true`. |
| True new maps/assets/physics/algorithms | high blocked | Requires cooked assets, plugin/binary support, or a newly discovered supported loading route. |

## Practical Answer

Yes, the evidence has already become actionable. The actionable subset is not “new content” in the asset-pipeline sense; it is safe admin control over shipped systems and live database state:

- Economy/admin: bundles, reputation, faction, Exchange balance, tags, access codes.
- Player recovery/progression: offline teleport, journey nodes, tutorial rows, respawn deletion.
- World/social state: guild roles/descriptions, permission actor access/ranks, marker deletion, landclaim segment add.
- World rules/config: typed spice, weather, mining, PvP/security, shelter candidates.
- Operations/events: dry-run event plans, announcements, restart plans, typed config proposals.

The next useful work is not to blindly add more mutators. It is to validate the moderate-risk promoted mutators on disposable data, then raise confidence or demote them based on observed client/server behavior.

## Test Coverage

Automated coverage currently verifies:

- Catalog entries include required evidence, confidence, risk, validation, and rollback fields.
- Catalog evidence/validation payloads expose the operator commands and evidence rules used by the UI.
- Catalog access fails closed when `DUNE_ADMIN_CATALOG_ENABLED` is disabled.
- Read-only inspectors expose actionable mutator metadata and blocked/inspect-only areas without executing writes.
- Typed knob validation, rendering, and backup-before-write behavior.
- Event dry-run planning, persistence, cancellation, and fail-closed execution.
- Character-slot discovery, dry-run shape, online-player refusal, and missing native contract blockers.
- Restart recovery edge cases for SIGPIPE-like start exits and incomplete farm readiness.
- Dry-run planning and fail-closed gates for representative promoted mutators:
  - faction reputation
  - player faction
  - journey story nodes
  - respawn location deletion
  - Landsraad term end-time
  - guild description
  - marker deletion
  - landclaim segment add
  - Dune Exchange Solari
  - player tags
  - access codes
  - Communinet
  - tutorial entries
  - vendor cycle timestamp
  - permission actors

Automated tests deliberately mock database reads/writes for mutator unit tests. Confidence is high that these paths are dry-run-first and gate-protected. Confidence in live gameplay effects remains moderate until disposable-data validation is performed on a running server.

Run:

```bash
python3 scripts/test-admin-panel-safe-surfaces.py
make validate
```

## Disposable Live Validation Queue

Validate in this order, because rollback quality is stronger at the top:

1. Player tags: add/remove a harmless tag, verify `dune.player_tags`, roll back by inverse update.
2. Tutorial entry: update one known tutorial row on a disposable character, verify client state and DB row, roll back to prior state.
3. Communinet: tune/untune one channel, verify `load_communinet_player_data`, roll back.
4. Vendor timestamp: adjust one disposable vendor/player cycle timestamp, verify bought-item view, restore prior timestamp.
5. Exchange Solari: set a disposable balance, verify Exchange UI/DB, restore prior balance.
6. Guild description/role: use a disposable guild, verify side effects, restore prior description/role.
7. Permission actor rank/access/name: use disposable base/actor data only, verify access behavior, restore prior rows.
8. Journey/faction/reputation: use disposable offline character data, verify game-client behavior and rollback paths.
9. Marker deletion, landclaim add, respawn delete, Landsraad term changes: validate only after taking a DB backup because rollback is weaker or world-impacting.
