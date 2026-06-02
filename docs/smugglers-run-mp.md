# SmugglersRunMP

Confidence: moderate that Smugglers Run maps to
`GroundVehicleTimeTrialIsland` / `CB_Overland_S_06` / partition `26`.
Confidence: low that native multiplayer race behavior can be enabled by one
config flag.

This project is lab-first. Do not run production admin actions from `kspld0`.
Production execution must be on `kspls0` after checking `hostname`.

## Current Target

Use the existing full warm-pool map:

| Name | Value |
| --- | --- |
| User-facing target | `SmugglersRunMP` |
| Map feature | `GroundVehicleTimeTrialIsland` |
| Server map | `CB_Overland_S_06` |
| Compose service | `overland-s-06` |
| Partition | `26` |
| Game port | `7802/udp` |
| IGW port | `7913/udp` |

`config/UserGame.ini` currently marks `GroundVehicleTimeTrialIsland` as
`m_bIsInstanced=True`, while `config/director.ini` maps
`CB_Overland_S_06=SingleServer`. That combination is the baseline to test
before changing Director instancing modes.

## External Race Tool

The external/admin race layer lives in:

```bash
python3 scripts/smugglers-run-mp.py --help
```

Read-only map and vehicle snapshot:

```bash
python3 scripts/smugglers-run-mp.py --env-file .env inspect \
  --entrant RacerOne \
  --entrant RacerTwo
```

Create a local race session with a pre-start DB snapshot:

```bash
python3 scripts/smugglers-run-mp.py --env-file .env init \
  --entrant RacerOne \
  --entrant RacerTwo \
  --vehicle-mode both
```

Start external timing:

```bash
python3 scripts/smugglers-run-mp.py --env-file .env start <session-id>
```

Record checkpoints and finishes:

```bash
python3 scripts/smugglers-run-mp.py checkpoint <session-id> --entrant RacerOne --checkpoint cp1
python3 scripts/smugglers-run-mp.py finish <session-id> --entrant RacerOne
python3 scripts/smugglers-run-mp.py summary <session-id>
```

Compare a later vehicle snapshot against the pre-start snapshot:

```bash
python3 scripts/smugglers-run-mp.py --env-file .env snapshot <session-id> --label post_exit
python3 scripts/smugglers-run-mp.py compare <session-id> --after post_exit
```

Session files are written under ignored `captures/smugglers-run-mp/sessions/`.
The tool does not write the game database.

Optional chat announcements use the existing `scripts/announce.sh` path. They
are preview-only unless `--execute` is passed, and production execution refuses
to run unless `hostname` is `kspls0`.

```bash
python3 scripts/smugglers-run-mp.py start <session-id> --announce
python3 scripts/smugglers-run-mp.py start <session-id> --announce --execute --scope lab
python3 scripts/smugglers-run-mp.py start <session-id> --announce --execute --scope production
```

Preview event loaner bike spawns:

```bash
python3 scripts/smugglers-run-mp.py loaner \
  --session-id <session-id> \
  --template <SpawnVehicle-template>
```

Loaner execution is blocked unless all are true: `--execute`,
`--allow-unsafe-gm`, `DUNE_ADMIN_GM_COMMANDS_ENABLED=true`, and
`DUNE_GM_COMMAND_PAYLOAD_VERIFIED=true`. The default GM route preview is
`CB_Overland_S_0626`, matching the repo's fixed-partition route convention.
Override it with `--route` if live validation proves a different route.

## Validation Fixtures

Shared-map validation:

```bash
make fixture-runner ENV_FILE=.env \
  FIXTURE=fixtures/smugglers-run-mp-shared-map.json \
  FIXTURE_FLAGS='--phase before'
```

After two unrelated players attempt to enter the island:

```bash
make fixture-runner ENV_FILE=.env \
  FIXTURE=fixtures/smugglers-run-mp-shared-map.json \
  FIXTURE_FLAGS='--phase after'
```

Owned-bike safety validation:

```bash
make fixture-runner ENV_FILE=.env \
  FIXTURE=fixtures/smugglers-run-mp-owned-vehicle-safety.json \
  FIXTURE_FLAGS='--phase before'
```

After players bring/drop/race/exit/relog with owned bikes:

```bash
make fixture-runner ENV_FILE=.env \
  FIXTURE=fixtures/smugglers-run-mp-owned-vehicle-safety.json \
  FIXTURE_FLAGS='--phase after'
```

Pass criteria:

- Two unrelated players occupy the same `CB_Overland_S_06` partition and can
  see each other.
- Owned bike vehicle/module/inventory rows remain associated with the same
  owner after entry, drop/deploy, race, exit, and relog.
- No unexpected `backup_vehicles` or `recovered_vehicles` row appears for a
  racer after normal exit.

If owned bikes fail, use event loaner bikes only until the native ownership path
is understood.

## Native Discovery

Use Ghidra only after the baseline fixture proves where the failure is:

```bash
/opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
  -process server-bin \
  -noanalysis \
  -postScript FindSmugglersRunMp.java \
  -scriptPath scripts/research \
  -log /tmp/ghidra-work/smugglers-run-mp-ghidra.log
```

The script searches map, time-trial, race/checkpoint/leaderboard, and vehicle
ownership strings, then decompiles nearby functions into:

```text
/tmp/ghidra-work/smugglers-run-mp-findings.txt
```

Promote any native surface through the repo evidence ladder before using it:
`candidate -> loadable -> observable -> validated -> admin-safe`.

## Implementation Boundary

Do not change `m_bIsInstanced`, Director `[InstancingModes]`, or vehicle
restore functions in production until lab fixtures prove the before/after
effect and rollback path. Those settings can strand travel targets or damage
vehicle persistence if guessed.
