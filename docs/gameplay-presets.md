# Gameplay Presets

The Gameplay Presets page provides a validated, backup-first workflow for
applying curated gameplay settings to one exact `UserGame` target. Preview is
read-only. Apply and rollback never restart a game map automatically.

## Included profiles

The committed catalog is [`../config/gameplay-presets.json`](../config/gameplay-presets.json).
It currently contains:

| Profile | Category | Outcome |
| --- | --- | --- |
| `calm-worms` | sandworm | Sparse, slower-to-provoke worms and a high giant-worm threshold. |
| `standard-worms` | sandworm | Restore the shipped worm/threat values represented by the peer preset. |
| `wormageddon` | sandworm | Dense, hair-trigger worms and a one-harvester giant-worm threshold. |
| `cosmetic-storms` | storm | Automatic visible storms without Coriolis or building damage. |
| `harsh-storms` | storm | Automatic damaging storms using the reviewed reference values. |
| `abundant-arrakis` | harvest | More spice, all flour-sand fields active, and cheaper repair. |
| `long-days` | world | A 90-minute day/night cycle. |
| `no-hydration` | world | Disable global dehydration. |
| `standard-world-survival` | world | Restore the reviewed standard day, hydration, PvP-drop, flour-sand, and repair values. |

The calm, standard, and WORMAGEDDON values are adapted from
`SetsuaD/DuneAwakening-Wormageddon` at pinned revision
`62ef3890886b8c7ddb5b764f36e5f83189ca7515`. That source is MIT licensed; the
full attribution and license are in [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).
DASH's additional operational profiles and validation workflow are local work.

## Targets and safety contract

Only these committed filenames can be selected:

- `config/UserGame.ini`
- `config/UserGame.deep-desert-coriolis.ini`
- `config/UserGame.deep-desert-pvp.ini`

The implementation in [`../admin/gameplay_presets.py`](../admin/gameplay_presets.py)
uses a fixed section/key/type/range allowlist. It preserves comments, unrelated
sections, unrelated keys, and existing line order where possible. It does not
accept arbitrary paths or arbitrary CVar names.

Every preview, apply, and rollback checks that both `UserGame.ini` and
`UserGame.deep-desert-coriolis.ini` contain
`m_CycleDurationInDays=7` in the Coriolis subsystem. Cycle start, duration,
seed, database wipe, shifting-sands, and restart settings are not in the preset
allowlist. A failed invariant stops the operation before a write.

Apply creates a timestamped private backup under:

```text
backups/admin-panel/gameplay-presets/<UTC timestamp>/<target filename>
```

The replacement is atomic. Rollback only accepts a regular file beneath that
backup root with one of the three exact target names. It first preserves the
current target beside it as a `before-rollback` recovery copy and then checks
the seven-day invariant again.

## Configuration and access

```dotenv
DUNE_GAMEPLAY_PRESETS_ENABLED=true
DUNE_GAMEPLAY_PRESET_MUTATIONS_ENABLED=false
```

The first setting loads the catalog and permits previews. Applying or rolling
back additionally requires all of the following:

- a valid authenticated admin identity;
- the `configuration.write` capability;
- `DUNE_ADMIN_MUTATIONS_ENABLED=true`;
- `DUNE_GAMEPLAY_PRESET_MUTATIONS_ENABLED=true`;
- the exact confirmation phrase `APPLY GAMEPLAY PRESET` or
  `ROLL BACK GAMEPLAY PRESET`.

`scripts/enable-feature-parity.sh .env --execute` enables the catalog and its
second mutation gate, but it does not select or apply a preset.

## Dashboard and API

Open **Gameplay Presets** in the admin panel. Select a profile and exact target,
then use **Preview exact diff**. The result lists every allowed setting with its
before value, after value, and whether it changes. Applying writes the selected
file only after its backup. The page lists available rollback backups and links
to the separate guarded restart planner.

The authenticated endpoint is `GET /api/presets/gameplay` and
`POST /api/presets/gameplay`.

Preview request:

```json
{"action":"preview","presetId":"long-days","target":"UserGame.ini"}
```

Apply request:

```json
{"action":"apply","presetId":"long-days","target":"UserGame.ini","confirm":"APPLY GAMEPLAY PRESET"}
```

Rollback request:

```json
{"action":"rollback","backup":"/workspace/backups/admin-panel/gameplay-presets/<timestamp>/UserGame.ini","confirm":"ROLL BACK GAMEPLAY PRESET"}
```

Responses identify whether content changed, the exact setting diff, backup
location, affected service class, Landsraad validation, and the required manual
restart. Audit events record the action, preset, target, backup, and restart
requirement without copying config contents.

## Activation and rollback procedure

Preview first. Before and after a production map restart involving Coriolis
configuration, run:

```bash
scripts/validate-landsraad-coriolis-cycle.sh .env
```

An apply or rollback changes only a file on disk; already-running maps keep
their current process-local configuration. Use the Operations restart planner
or the guarded target scripts such as `scripts/restart-target.sh`. Do not use
raw `docker compose restart`, because the guarded paths restore required
post-start runtime hooks.

To undo a write before restart, select its backup on the Gameplay Presets page
and roll it back. To undo it after restart, roll back and then perform another
guarded restart of the affected target.

## Validation

Run the focused tests and repository checks:

```bash
make test-gameplay-presets
python3 scripts/test-admin-panel-safe-surfaces.py
docker compose --env-file .env config >/dev/null
scripts/validate-landsraad-coriolis-cycle.sh .env
```

The focused suite covers every committed catalog profile, type/range
validation, comment-preserving merge behavior, read-only preview, invariant
refusal, backup-first apply, idempotence, rollback, and rollback path
confinement.

The signed Creator/Modding canary additionally copies all three active targets,
selects an effective catalog preset, applies and rolls it back through these
same functions, verifies exact final bytes, and proves the seven-day Landsraad
cycle remained intact. It never changes the live files; see
[`creator-modding-canary.md`](creator-modding-canary.md).
