# BRT-in-Deep-Desert: Diagnostic and Fix Plan

Confidence: high for the sequencing logic, moderate for any single fix landing.
This plan supersedes the ad-hoc "stack every patch at once" posture. See
[base-reconstruction-deep-desert-ghidra.md](base-reconstruction-deep-desert-ghidra.md)
for the prior Ghidra/string evidence and
[deep-desert-research-findings.md](deep-desert-research-findings.md) /
[deep-desert-map-state.md](deep-desert-map-state.md) for map-identity facts this
plan depends on.

## Problem Statement

DD#1 currently runs four overlapping BRT levers at once (invalid-map binary
patch, action-gate binary patch, `dd-totem-groups` overlay pak, narrow
tool-state binary patch) and the Base Reconstruction Tool still reports
"not allowed in the region." With everything stacked we cannot tell which lever
fires, whether any is reached at runtime, or whether the config we keep adding
ever lands in the live process.

## Two Unknowns That Gate Everything

1. **Does the BRT RPC arrive at the server?** The first required proof is
   whether a DD1 BRT save/restore attempt reaches `ServerRequestBaseBackup`.
   If it arrives, fix the reached server-side gate. If it does not arrive, do
   not require client-side file changes; emulate the missing request server-side
   through the native DB/BRT persistence path.
2. **Do the INI keys reach the live CDO?** We keep adding
   `m_BaseBackupToolMapRestriction=(...)` but never read the running
   `UBuildingSettings` array back. UE array properties often need the
   `+m_BaseBackupToolMapRestriction=(...)` append form to override a C++
   default; a plain `=(...)` reassignment can be silently ignored.

Resolve these before treating any patch or emulator path as validated.

## Operating Rules

> **Environment constraint (2026-06-03):** the isolated lab host `kspld0` is
> unreachable. All testing runs on the **live production host `kspls0`** against
> **Deep Desert #1** (`deep-desert` service, partition 8, container
> `dune_server-deep-desert-1`). The rules below are written for that reality.

- This is a **live game server**. Trace in **keystone-only** mode (default of
  `scripts/brt-dd-trace.sh`) so gdb breakpoints fire only when someone actually
  uses the BRT, not on every player's building/totem preview. Prefer a
  low-population window.
- The runner **pauses the map watchdog** while armed and you **must** disarm with
  `scripts/brt-dd-trace.sh stop` (or `make brt-dd-trace-stop`) — that cleanly
  detaches gdb (kernel resumes the server) and resumes the watchdog. Do not leave
  a trace armed.
- The **keystone trace needs no restart**: it answers RPC-arrival against the
  current (patched) DD#1. Only restart DD#1 (`make brt-dd-live-restart`) when
  a phase explicitly needs a patches-off baseline or a config change, and do it
  in a downtime window.
- Change **one lever at a time** and record the trace outcome each time.
- All BRT patches are toggled by `DUNE_BRT_DD_*_ENABLED` env vars consumed in
  `scripts/run_server_safe.sh`; the `compose.brt-dd-invalid-map.yaml` overlay is
  auto-added by `scripts/compose-files.sh` when any are `true`. "Patches off"
  means setting all of these `false`:
  `DUNE_BRT_DD_INVALID_MAP_BINARY_PATCH_ENABLED`,
  `DUNE_BRT_DD_ACTION_GATE_BINARY_PATCH_ENABLED`,
  `DUNE_BRT_DD_BUILDABLE_MAP_REGION_PATCH_ENABLED`,
  `DUNE_BRT_DD_NARROW_TOOL_STATE_BINARY_PATCH_ENABLED`,
  `DUNE_BRT_DD_TOOL_ENABLE_BINARY_PATCH_ENABLED`.

---

## Phase 0 — Live preflight on kspls0 (no restart)

Goal: confirm the live DD#1 target without disturbing it. The keystone trace
(Phase 1) runs against the **current, patched** DD#1 — patch state does not change
whether the RPC arrives, so no restart is needed yet.

```bash
ssh kspls0
cd /home/keith/Documents/code/DuneAwakeningSelfHost
hostname                                   # must be kspls0
make brt-dd-live-preflight ENV_FILE=.env   # read-only: partition 8 / DeepDesert_1, config
docker ps --format '{{.Names}}' | grep deep-desert   # confirm dune_server-deep-desert-1
```

Record: build id, that partition 8 is `DeepDesert_1`, and which BRT patches are
currently live (from `compose.brt-dd-invalid-map.yaml`).

Optional patches-off baseline (only if a later phase needs shipped behavior):
set the five `DUNE_BRT_DD_*_ENABLED=false` and
`make brt-dd-live-restart ENV_FILE=.env CONFIRM='RESTART DEEP DESERT BRT'` in a
downtime window. Not required for the keystone.

---

## Phase 1 — KEYSTONE: RPC-arrival trace (Idea 1 + 2)

Goal: one decisive trace that says whether the DD1 BRT attempt reaches
`ServerRequestBaseBackup`, which server-side branch it hits if it does, and
whether the config landed.

Tooling built for this phase:
- `scripts/research/DumpBrtTraceAnchors.java` — Ghidra headless dumper that emits
  build-current, image-base-relative offsets for the BRT place RPC server entry
  (`ServerRequestBaseBackup_Implementation`), the `m_BaseBackupToolMapRestriction`
  read site, and the "not allowed in the region" emitter. Offsets are build
  specific and must be re-derived after any game update.
- `scripts/trace-brt-place-live.sh` — accepts `BRT_RPC_PLACE_OFFSET`,
  `BRT_RESTRICTION_GATE_OFFSET` (and `BRT_RESTRICTION_GATE_EXPR`), and
  `BRT_REGION_REJECT_OFFSET` to arm the keystone breakpoints, and
  `BRT_TRACE_KEYSTONE_ONLY=1` to **skip the dense state/preview/PerformCanBePlaced
  breakpoints** that would otherwise trap on every live player's building preview.
- `scripts/research/brt-dd-points-1988751.tsv` — current-build trace points for
  build id `6f8ca9ee5f3420c0b4c1ef7cefb412347bcba04b`. The uprobe and
  persistent trace scripts validate this build id against the running process
  before arming. Stale built-in offsets require explicit
  `DUNE_BRT_DD_TRACE_ALLOW_STALE_BUILTINS=1`.
- `scripts/brt-dd-uprobe-watch.sh arm|status|dump|stop` — tracefs uprobe runner
  for low-overhead current point canaries. It does not prove a BRT restore
  without a tester action, but it verifies current offsets can arm on the live
  process without gdb stops.
- `scripts/brt-dd-trace.sh arm|stop` (+ `make brt-dd-trace` / `brt-dd-trace-stop`)
  — live-safe runner: refuses to run off `kspls0`, resolves offsets via Ghidra,
  pauses the map watchdog while armed (keystone-only by default), and `stop`
  cleanly detaches gdb + resumes the watchdog.

2026-06-16 status: on build `1988751`, the anchor dump and static ELF xref scan
found no executable xrefs for `ServerRequestBaseBackup_Implementation`,
`ServerRequestBaseBackup`, or `m_BaseBackupToolMapRestriction`. Confidence: high
that the known BRT action/`PerformCanBePlaced` points are current.

Follow-up static pointer-table proof resolved the RPC keystone without guessing:
`ServerRequestBaseBackup` at `0x5a553f9` relocates into metadata table
`0x15214210`; the adjacent native exec thunk is `0xd1093f0`; that thunk calls
`UBuildingReplicationComponent` vtable offset `0x588`, whose relocation-applied
entry at `0x15214a18` is `0xd109ff0`. These two current-build points are now in
`scripts/research/brt-dd-points-1988751.tsv` as
`brt_rpc_exec_server_request_basebackup` and
`brt_rpc_impl_server_request_basebackup`. Confidence: high for the RPC entry
mapping, unknown for restore outcome until a tester action hits or misses those
points.

Steps (on kspls0, ideally a low-population window):

1. Arm the keystone trace against live DD#1 (resolves offsets, pauses watchdog,
   keystone-only):

   ```bash
   make brt-dd-trace ENV_FILE=.env
   # equivalently: scripts/brt-dd-trace.sh arm dune_server-deep-desert-1 \
   #   /tmp/brt-place-trace-lab.log .env
   ```

   It prints the resolved offsets and refuses if `BRT_RPC_PLACE_OFFSET` is
   unresolved (the keystone). After a game update, force a fresh resolve with
   `BRT_TRACE_RESOLVE=1`. Resolve-only inspection:

   ```bash
   scripts/research/run-ghidra-headless.sh --script DumpBrtTraceAnchors.java
   cat /tmp/ghidra-work/brt-trace-anchors.txt
   ```

2. Have a trusted tester with a Hagga-restorable backup travel to DD#1 and attempt
   a restore away from borders/POIs/cliffs, while you watch:

   ```bash
   tail -f /tmp/brt-place-trace-lab.log
   ```

3. Capture exact client error text, timestamp, location, and every breakpoint that
   fired. Then **disarm** (required — resumes the watchdog):

   ```bash
   make brt-dd-trace-stop ENV_FILE=.env
   ```

**Decision branches:**

- **No server-side hit** → the normal BRT client did not send the server RPC.
  Skip more server binary bypasses for the UI path. Go to Phase 3 only if we
  still want to prove the data/config reason, and go to Phase 6 to emulate the
  missing request server-side.
- **Hit, returns `Fail_InvalidMap`** → server-side gate confirmed. Go to Phase 2
  (find the true emitter) and Phase 4 (bounding test).
- **Server returns success but client still errors** → response/replicated-state
  mismatch. Go to Phase 3.
- **CDO array missing `DeepDesert`** → config never landed regardless of the
  above. Do Phase 3 step 1 first.

Record: the branch taken. Everything after this is conditional on it.

### Interim evidence (2026-06-03, read-only, no gdb/tester yet)

Confidence: moderate-to-high that the next proof should be RPC-arrival tracing,
not additional stacked patches.

Inspected live DD#1 on `kspls0` (build **1979201**, binary re-patched
2026-06-03). Startup log shows **every** server-side BRT gate applied cleanly,
with no signature-match failures:

- invalid-map verdict: 4× `0x88 -> 0x01` in `PerformCanBePlaced` @ 0xcfbd400
  (sites 0xcfbda3e/0xcfbdc48/0xcfbdfa6/0xcfbe092);
- action-gate: `can-use DD map-area guard 75 03 -> eb 03` (0xe043872),
  `invalid-map reason guard 0f 85.. -> 90×6` (0xe043236);
- narrow tool-state: 3 sites (0xe043765/0xe043533/0xe04336e);
- buildable-region overlay pak present + 3 jump-NOP sites
  (0xcddb77a/0xceff076/0xcefedf4).

Every known server-side decision point was forced open and BRT reportedly still
rejected in DD. That does not prove the RPC is absent; it only proves the stacked
patch state is not sufficient evidence. The keystone trace must classify the
attempt by runtime behavior.

The airtight test remains the keystone trace with a tester action on `kspls0`.
If `SERVER-RPC-ENTRY` fires, continue on the server-side gate branch. If it does
not fire, use Phase 6 to spoof the missing request server-side with no
client-side file changes. Convert the trace log into a proof artifact with:

```bash
scripts/classify-brt-dd-trace.py /tmp/brt-place-trace-lab.log --format json \
  > /tmp/brt-dd-trace-classification.json
```

Build note: live is **1979201**, not 1973075. Signature-based patch scripts and
`DumpBrtTraceAnchors.java` adapt; the trace script's hardcoded dense offsets and
the `/tmp/ghidra-work` project are stale and must be refreshed before any trace.

### Live save test (2026-06-03 ~18:36 UTC) — inconclusive by logs

Tester attempted a base-backup **save** in DD#1 (rejection is the same region
gate for save and place). Result: **the server logged nothing.** Calibration:
the Hagga (`survival`) container also has **zero** `BaseBackup` log lines ever, so
the handler simply does not log at this verbosity — log-absence cannot prove
RPC arrival either way. `dune.base_backups` has 0 rows (the rejected save
persisted nothing). Net: no new signal. Airtight proof still requires the
RPC-arrival trace.

---

## Phase 2 — Find and patch the true reject verdict emitter (Idea 4)

Run only if Phase 1 shows a server-side block. Replaces inference with an xref.

Note: the player-visible "not allowed in the region" text is almost certainly
FText localization in a **client** `.locres`, not a literal in the server binary,
so do not key the search on the English string. Work from the verdict enum
(`EBuildingBlueprintCanBePlacedType`) instead.

Tooling built for this phase:
- `scripts/research/DumpCanBePlacedVerdicts.java` — enumerates the verdict enum
  (name -> value), the functions that reference each verdict variant, and **all**
  `Fail_InvalidMap (0x88)` immediate-store sites across the binary (as
  image-base-relative offsets).

Steps:

1. Run the dumper on the host:

   ```bash
   scripts/research/run-ghidra-headless.sh --script DumpCanBePlacedVerdicts.java
   cat /tmp/ghidra-work/canbeplaced-verdicts.txt
   ```

2. Cross-check the `0x88` store sites it lists against the **four** that
   `patch-brt-dd-invalid-map-binary.py` flips inside `PerformCanBePlaced`. If the
   verdict that actually fired in the Phase-1 trace (e.g. a `Fail_Disallowed*`
   rather than `Fail_InvalidMap`) is emitted from a function the current patches
   do **not** touch, the existing patches are adjacent-but-wrong.
3. Build a narrow patch against the real emitter (a new `--sites` entry on the
   existing invalid-map patcher, or a sibling patch script), scoped to the DD
   container only.

Pass: the emitter function is identified by enum/xref evidence and confirmed by a
Phase-1 trace hit, not by string proximity.

---

## Phase 3 — Map-identity and config-replication (Idea 2 + 3)

Run if Phase 1 shows no RPC arrival, success-but-error, or a missing CDO entry.

1. **Append-form config.** Switch the DD config from
   `m_BaseBackupToolMapRestriction=(...)` to the append form and confirm the
   exact `[/Script/DuneSandbox.BuildingSettings]` section/file the property
   reads:

   ```ini
   +m_BaseBackupToolMapRestriction=(Name="DeepDesert")
   +m_BaseBackupToolMapRestriction=(Name="DeepDesert_1")
   ```

   Re-run the Phase 1 CDO dump to confirm the array now contains the DD names.
2. **Enum vs FName.** `DT_BuildableMapRegion` keys on `EDuneMapId`. Dump the
   enum and confirm whether the restriction check compares an `EDuneMapId` value
   or an FName string. If it is the enum, FName INI entries will never match and
   the fix must target the enum/data-table path, not the INI.
3. **Replication.** Confirm whether the server replicates the patched
   `UBuildingSettings` value to the client. If the UI reads only its own cooked
   pak, server config cannot make it send the RPC — escalate to Phase 6
   server-side request emulation.

Record: which identity form the gate uses; whether the CDO/replicated value now
includes DD.

---

## Phase 4 — Bounding test (Idea 5)

Cheap localizer. With no lab, run it on DD#1 in a **downtime window at low/zero
population**, and revert immediately after — this toggle disables server-side
building restriction limits globally, so it must not stay on with players present.

1. Set `m_bBuildingRestrictionLimitsEnabled=False` (or the
   `m_bEnableBuildingRestrictionLimitsCheat` flag) in the DD#1 config and restart
   DD only (`make brt-dd-live-restart`).
2. Repeat the Phase 1 attempt with a trusted tester.
3. Revert the toggle and restart DD again, regardless of result.

- **BRT now works** → the block is purely a building-restriction gate; narrow
  back down to a DD-scoped fix (Phase 2/3/5).
- **Still fails** → the block is elsewhere (RPC not sent, height/boundary,
  replication). Saves binary spelunking.

---

## Phase 5 — Data-table localization (Idea 6) and overlay-load proof (Idea 8)

Run if Phase 1/4 point at the buildable-region table.

1. **Confirm the overlay actually loads.** Verify in the server log that
   `pakchunk9999-LinuxServer.pak` mounts and that `DT_BuildableMapRegion` is
   served from it, not the base pak. Rule out wrong `--path-hash-seed` / pak load
   order (silent no-op).
2. **Wholesale-copy variant.** Add a throwaway `dd-totem-groups` variant that
   copies Hagga's buildable map-area restriction array into DD wholesale
   (accepting wrong geometry). If BRT then works, the array is the gate; build a
   DD-correct full-coverage region as the real fix.

Pass: the gate is localized to the data table, and a DD-correct region is
authored (not Hagga geometry imported into DD).

---

## Phase 6 — Server-side request emulation (Idea 7)

Run if Phase 1 proves the normal DD1 BRT UI does not send the RPC, if Phase 3
shows the UI reads only client-cooked data, or as a parallel fallback for
operator-controlled backup/restore. This path removes client-side file changes
from the requirements by issuing the equivalent server-side persistence
operations.

Do not turn a missing normal request into a client-file requirement. The required
classification is:

1. prove whether the BRT save/restore RPC reaches the server;
2. if it reaches the server, fix or bypass the reached server-side branch;
3. if it does not reach the server, spoof the missing client request from the
   server side by driving the native BRT DB path or reconstructing the equivalent
   persistence rows.

### Live API mapping (2026-06-03, read-only on kspls0)

Full `dune.base_backup_*` surface on build 1979201:

| Function | Args | Returns |
| --- | --- | --- |
| `base_backup_save` | `player_actor_id, name, building_pieces basebackupbuildingitem[], placeables bigint[], remove_totem_owner bigint[]` | `bigint` (backup id) |
| `base_backup_save_from_totem` | `player_id, totem_id` | `bigint` |
| `base_backup_save_all_totems_from_player_owner` | `player_id` | `bigint` |
| `base_backup_get_available_backups` | `player_id` | `record` |
| `base_backup_get_data` | `base_backup_id` | `getbasebackupdata` |
| `base_backup_get_actors_to_spawn` | `base_backup_id` | `actorspawninfo` |
| `base_backup_get_totem_data` / `_from_totem_id` | `base_backup_id` / `totem_id` | `basebackuptotemdata` |
| `base_backup_get_buildable_data` | `base_backup_id` | `record` |
| `base_backup_get_totem_id` | `backup_id` | `bigint` |
| `base_backup_find_totems_from_player_owner` | `player_id` | `bigint` |
| `base_backup_finish_placing` | `base_backup_id` | `void` |
| `base_backup_recycle` | `base_backup_id, target_inventory_id` | `integer` |
| `base_backup_delete` | `base_backup_id` | `void` |

Tables: `base_backups` (`id, player_id, base_backup_name` — minimal; 0 live rows),
`base_backup_linked_actors` (0 rows). Base content is the linked-actor rows plus
the `building_pieces[]`/`placeables[]` arrays passed to `base_backup_save`.

### Critical finding

There is **no mapped GM/admin command that directly places a base backup** (the
GM catalog only has `DestroyTotem`/`DestroyPlaceable`/etc.). The two viable
server-side request-emulation routes are:

1. **Native BRT DB functions where they are sufficient:** create/list/inspect
   backups with `base_backup_save_from_totem`, `base_backup_get_available_backups`,
   `base_backup_get_data`, `base_backup_get_actors_to_spawn`, and finish staged
   placement with `base_backup_finish_placing`.
2. **Direct persistence reconstruction when native placement is not exposed:**
   write the base's totem + placeables + building-piece actors as persistence
   rows keyed to the DD map/dimension (`DeepDesert_1`, partition 8, dimension by
   instance), then force a map refresh so the DD server loads them on stream-in.

`scripts/dd1-brt-emulator.py` is the operator wrapper for this branch. It defaults
to rollback-only and requires explicit live DD1 confirmations plus an RPC
classification for committed restore/finish operations. Use
`--rpc-classification normal-request-not-observed` only after the keystone trace
shows the normal BRT request did not hit `SERVER-RPC-ENTRY`/`SERVER-RPC-EXEC`.
Use `--rpc-classification operator-controlled-fallback` only for an explicitly
authorized admin fallback. Prefer `--rpc-classification-json` with the output of
`scripts/classify-brt-dd-trace.py` so the commit records the trace-derived
classification. Neither branch requires client-side file changes.

### Operator runbook

This is the current quickest path to making the BRT usable for DD1 base backup
and restore without requiring client-side file changes. Confidence: moderate for
backup/list/inspect because they use mapped native DB functions; low-to-moderate
for committed restore until a disposable-base validation survives map refresh.

All commands below must run on `kspls0` for a live mutation. Dry-run/read-only
commands can be used first to inspect the shape.

1. Confirm target host and list the player's DD1-visible totems:

   ```bash
   hostname   # must be kspls0 before any live mutation
   scripts/dd1-brt-emulator.py list-totems --player-id 17
   ```

2. Create a native BRT backup from a known totem. Default mode rolls back and is
   the first test; `--commit` persists the backup only after the operator chooses
   to create it:

   ```bash
   scripts/brt-dd-synthetic-db-backup.sh --player-id 17 --totem-id 5903

   CONFIRM='CREATE BRT DB BACKUP' \
     scripts/brt-dd-synthetic-db-backup.sh --player-id 17 --totem-id 5903 --commit

The live target audit resolves a single real available backup automatically. If
the allowlisted restore player has no backup, it reports a warning because the
restore command is correctly unavailable until `&DD1_backup` creates one. If
multiple backups exist, set `DUNE_TARGET_AUDIT_BRT_BACKUP_ID`; the audit fails
instead of guessing which restore fixture is authoritative.
   ```

3. List and inspect available backups:

   ```bash
   scripts/dd1-brt-emulator.py list-backups --player-id 17
   scripts/dd1-brt-emulator.py inspect-backup --backup-id <backup_id>
   ```

4. Simulate a restore at the target DD1 location. This creates, transforms, and
   finishes inside one transaction, then rolls back:

   ```bash
   scripts/dd1-brt-emulator.py simulate-from-totem \
     --player-id 17 \
     --totem-id 5903 \
     --map DeepDesert \
     --partition-id 8 \
     --dimension-index 0 \
     --target-x <x> \
     --target-y <y> \
     --target-z <z>
   ```

5. Commit an existing backup restore only for an explicitly authorized
   disposable-base validation:

   ```bash
   scripts/classify-brt-dd-trace.py /tmp/brt-place-trace-lab.log --format json \
     > /tmp/brt-dd-trace-classification.json

   DUNE_ALLOW_LIVE_DD1_BRT_MUTATION=1 \
   CONFIRM_DD1_BRT='I UNDERSTAND DD1 BRT MAY BREAK BASE OWNERSHIP' \
     scripts/dd1-brt-emulator.py restore-backup \
       --backup-id <backup_id> \
       --map DeepDesert \
       --partition-id 8 \
       --dimension-index 0 \
       --target-x <x> \
       --target-y <y> \
       --target-z <z> \
       --commit \
       --confirm 'RESTORE DD1 BRT BACKUP' \
       --rpc-classification-json /tmp/brt-dd-trace-classification.json
   ```

6. Validate immediately:

   ```bash
   scripts/dd1-brt-emulator.py inspect-backup --backup-id <backup_id>
   scripts/audit-dd1-base-ownership.sh --player-id 17
   ```

   Then run the approved DD1 map recovery/restart path only if a stream/load
   refresh is required. Do not use raw `docker compose restart` for live DD1.

### Steps

1. Resolve the composite types `getbasebackupdata`, `actorspawninfo`,
   `basebackuptotemdata` and the `basebackupbuildingitem` element type to learn
   the exact actor/transform/ownership payload a reconstruction must write.
2. Map the persistence tables a base occupies: `dune.totems`,
   `dune.landclaim_segments`, `dune.actors`, placeable rows — and how each is
   keyed by map/dimension (cross-ref
   [deep-desert-map-state.md](deep-desert-map-state.md): `map_areas` has no
   dimension, but `resourcefield_state`/`spicefield_types` do).
3. Prototype on a **disposable test account/base on DD#1**:
   `dd1-brt-emulator.py simulate-from-totem` first, then either finish the staged
   native backup or reconstruct its actors as DD persistence rows and
   `recover-map.sh` DD to force load.
4. Validate before exposing: `serverinfo`, nested `transform`, inventory
   ownership, spawned-actor ownership, account ownership, live map refresh, and
   rollback (timestamped backup table per `reset-deep-desert-map-areas.sh` style).

Pass: a disposable base appears in DD with correct ownership and survives a map
refresh, with no client tool or client-side file changes involved.

---

## Live Promotion

Once a phase produces a working restore on DD#1:

```bash
hostname                                   # must be kspls0
make brt-dd-live-preflight ENV_FILE=.env
make brt-dd-live-restart  ENV_FILE=.env CONFIRM='RESTART DEEP DESERT BRT'
make brt-dd-live-verify   ENV_FILE=.env
make brt-dd-live-logs     ENV_FILE=.env
```

Pass criteria (live):

- The BRT place action reaches the normal preview/confirm flow in Deep Desert.
- DD service stays ready/alive/active after restart.
- Hagga Basin BRT behavior is unchanged.

Rollback: set the relevant `DUNE_BRT_DD_*_ENABLED` flags back to `false` (and/or
restore the prior config line), then re-run `brt-dd-live-restart` +
`brt-dd-live-verify`.

## Progress Log

| Date | Phase | Branch taken / result | Next |
| --- | --- | --- | --- |
| 2026-06-03 | 1 (prep) | Built `DumpBrtTraceAnchors.java` + extended `trace-brt-place-live.sh` keystone breakpoints. | (superseded) |
| 2026-06-03 | plan | Lab host `kspld0` unreachable; retargeted all testing to live `kspls0` / DD#1. Added keystone-only mode, `scripts/brt-dd-trace.sh arm\|stop` with host guard + watchdog pause/clean-detach, `make brt-dd-trace` / `brt-dd-trace-stop`. | Run `make brt-dd-trace ENV_FILE=.env` on kspls0 in a low-pop window, attempt DD#1 restore, then `brt-dd-trace-stop` |
| 2026-06-03 | 2 (prep) | Built `scripts/research/DumpCanBePlacedVerdicts.java` (verdict enum + emitter sites + all `0x88` stores) so Phase 2 works from the verdict enum, not a guessed English string. | Run it on host if Phase 1 shows a server-side block |
| 2026-06-03 | 1 (evidence) | Read-only inspection of live DD#1 (build 1979201): stacked server-side BRT gates applied cleanly yet BRT still fails. This is not proof of no RPC; it means the next required proof is the keystone RPC-arrival trace. Build shifted from 1973075 → trace dense offsets + Ghidra project stale. | Confirm with keystone trace + tester on kspls0; if no RPC, use Phase 6 server-side request emulation |
| 2026-06-03 | 1 (save test) | Tester saved a base in DD#1; server logged nothing. Hagga also never logs BaseBackup → log test inconclusive. `base_backups`=0 rows. | Run RPC-arrival trace or use Phase 6 under explicit operator control |
| 2026-06-03 | 6 (prep) | Mapped full `base_backup_*` API live; no mapped GM placement command exists → server-side request emulation needs native DB functions where sufficient, otherwise direct persistence reconstruction + map refresh. | Resolve composite types + persistence table mapping, then disposable-base prototype |
| 2026-06-04 | 6 (tooling) | Added `scripts/dd1-brt-emulator.py` read-only `list-totems`/`list-backups`/`inspect-backup` and guarded `finish-staged-backup`. Deployed to `kspls0`; live gates remain `false/false/false`. Lukano/player `17` has totem `5903`, `622` building pieces, `117` child placeables, and zero available backups. | Use emulator for disposable-base-only validation; keep public backup/restore disabled |
| 2026-06-04 | native route | Rechecked current 1979201 binary by symbols/strings: BRT classes, `UBaseBackupSpawner`, and internal `UBuildingSubsystem` delegates exist, but no shipped admin/GM command or proven RMQ route invokes BRT placement or live actor unload. `FlushActorPersistence` is still binary-only `UDuneCheatManager::FlushActorPersistence()` and not a proven dedicated-server command. | Do not chase new command names; only resume native route after solving safe `PrintAllowedCommands`/`PrintPos` payload proof |
| _pending_ | 1 | _RPC-arrival trace result_ | branch per decision tree |
