# Landsraad Reveal Watchdog

## 2026-06-02 Incident

Confidence: moderate.

Term 3 started at `2026-06-02 04:55:00 UTC` and had 25 Landsraad tasks, but
`dune.landsraad_task_reveal_state` had zero rows and
`last_processed_reveal_day=0`. That suspended the Landsraad board: clients saw
empty current missions while still being blocked by mission capacity.

Prior terms revealed normally around `05:00 UTC`:

- Term 2 first reveal: `2026-05-26 05:00:25 UTC`
- Term 2 final reveal rows: 50
- Term 3 first reveal before repair: none

The manual repair at `2026-06-02 18:59:09 UTC` called the first-party database
function:

```sql
select *
from dune.landsraad_perform_daily_task_reveal(
  3,
  array['Atreides','Harkonnen'],
  array[
    'DA_HouseEcaz',
    'DA_HouseNovebruns',
    'DA_HouseArgosaz',
    'DA_HouseMutelli',
    'DA_HouseKenola'
  ],
  1
);
```

That created 10 reveal rows and moved `last_processed_reveal_day` to `1`.

Docker event history did not retain enough evidence to prove why the server
runtime missed the expected reveal tick. The practical failure mode is clear:
the game runtime can miss a reveal, and before this watchdog the repo had no
self-healing check for an active term with tasks but zero reveal rows.

## Watchdog Behavior

`scripts/landsraad-reveal-watchdog.sh` is dry-run by default. With `--execute`,
it verifies the host before any production mutation and only repairs this exact
day-one suspended state:

- active Landsraad term exists
- term is at least `DUNE_LANDSRAAD_REVEAL_WATCHDOG_MIN_AGE_MINUTES` old
- task count equals `DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRED_TASK_COUNT`
- `last_processed_reveal_day=0`
- reveal row count is `0`
- boards `0..4` resolve to exactly five houses

When eligible, it calls:

```sql
dune.landsraad_perform_daily_task_reveal(
  term_id,
  array['Atreides','Harkonnen'],
  day_one_houses_ordered_by_board_index,
  1
)
```

It records every execute run in `dune.landsraad_reveal_watchdog_audit`,
including skips.

## Automation

`scripts/restart-target.sh` runs the watchdog during start/restart pre-start
hygiene. The default is enabled:

```env
DUNE_LANDSRAAD_REVEAL_WATCHDOG_ENABLED=true
DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRE_HOST=kspls0
DUNE_LANDSRAAD_REVEAL_WATCHDOG_MIN_AGE_MINUTES=5
DUNE_LANDSRAAD_REVEAL_WATCHDOG_REQUIRED_TASK_COUNT=25
```

The watchdog skips without mutating when run from any host other than the
required host.

Manual dry-run:

```bash
scripts/landsraad-reveal-watchdog.sh .env
```

Manual execute on production:

```bash
hostname
scripts/landsraad-reveal-watchdog.sh .env --execute
```

## 2026-06-02 Follow-Up: Coriolis Cycle Gate

Confidence: high.

The reveal repair above was necessary but not sufficient. After term 3 had day
one reveal rows, players still saw Landsraad suspended. The remaining cause was
the Standard PvE Coriolis config: `config/UserGame.ini` and
`config/UserGame.deep-desert-coriolis.ini` used `m_CycleDurationInDays=36524`.
The server logs then showed the Coriolis cycle parked far in the future, while
the Landsraad UI still derives its active/suspended window from that Coriolis
cycle.

The repair is to keep the weekly cycle active while disabling the destructive
parts:

```ini
m_bCoriolisAutoSpawnEnabled=False
m_bCoriolisDoesDamage=False
m_bCoriolisTriggerShiftingSands=False
m_CoriolisLightDamage=0.000000
m_CoriolisHeavyDamage=0.000000
m_CycleDurationInDays=7
m_bShouldRestartServerOnCycleEnd=False
m_bIsDbWipeEnabled=False
```

After restarting Survival and DD1 on `2026-06-02`, both maps logged:

```text
This Coriolis Cycle start date UTC: 2026.06.02-15.52.00
Next Coriolis Cycle start date UTC: 2026.06.09-15.52.00
```

Do not reintroduce the 36524-day cycle. It prevents visible Coriolis rollover
but also suspends Landsraad.
