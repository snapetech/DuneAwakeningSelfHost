# Player-Impact-Aware Maintenance

## Outcome

DASH no longer has to assume that one fixed clock time is the least disruptive
maintenance window. The Operations page learns a zero-inclusive aggregate
population history, ranks bounded future windows, compares the best window with
the configured `06:00` baseline, and loads an exact timestamp into the existing
restart planner.

This is recommendation and scheduling intelligence, not an autonomous restart
authority. Choosing a recommendation only fills the planner. The existing
execution selector, backup policy, update-readiness receipt, soft disconnect,
announcements, change contract, optional dual control, post-start hooks, and
maintenance-outcome receipt still govern the actual job.

## Evidence Model

The moderation worker already performs the authoritative online-player query.
When `DUNE_MAINTENANCE_PLANNER_ENABLED=true`, each poll also records an
aggregate observation in the isolated moderation SQLite database:

- five-minute UTC bucket;
- sample count;
- sum and maximum online-player count;
- aggregate count of maps containing an online player; and
- last observation time.

No account, character, Funcom, platform, network, map-position, or coordinate
identity is written to the planner table. Recording empty polls is deliberate:
it distinguishes a measured zero-player window from an absence of telemetry.
Multiple polls in one bucket are aggregated, so the retained row count is
bounded. Old buckets are pruned by the policy retention period.

The table is stored inside `backups/moderation/moderation.sqlite3`. Existing
transactionally consistent full backups, integrity verification, restore, and
retention therefore preserve it without adding a second state database.

## Ranking

The default policy is [`config/maintenance-planner.json`](../config/maintenance-planner.json).
For every slot in the next seven days between `02:00` and `09:00`
`America/Regina`, the planner evaluates a 30-minute window from the previous 28
days. A historical day is admitted only when at least 80 percent of its
expected five-minute buckets exist.

When at least two matching weekdays exist, the estimate uses matching weekdays.
Until then it uses all complete historical days for the same local time. Each
candidate exposes:

- mean expected concurrent players;
- expected player-minutes affected;
- p95 peak players;
- probability that at least one player is online;
- evidence days and mean coverage;
- weekday/all-days evidence scope; and
- a deterministic risk score.

The lowest-risk candidates are ordered by score and then time. Until enough
complete historical days exist, DASH explicitly returns
`policy-fallback-learning` and the next configured `06:00` slot. It does not
mislabel sparse positive-only history as proof that an unobserved window is
empty. Once evidence qualifies, the source becomes `measured-presence` and the
dashboard reports expected player-minutes saved and percentage impact reduction
against the default-time baseline.

## Exact-Time Scheduling

The maintenance job planner accepts an optional ISO-backed exact local date and
time. A selected recommendation fills this field. The server converts it to UTC
and requires it to be at least 30 seconds in the future and no more than 30 days
away. If the field is empty, the original bounded relative-delay choices remain
available.

For an exact-time job, in-game warnings do not begin immediately days in
advance. The default first warning is 30 minutes before execution, every five
minutes until five minutes remain, then every minute. The final existing
"starting now" message and restart execution remain tied to the exact job time.

The API remains the existing governed endpoint:

```http
POST /api/ops/restart
Content-Type: application/json

{
  "target": "all",
  "action": "restart",
  "runAt": "2026-07-18T12:00:00Z",
  "execute": false,
  "backup": true,
  "announce": true,
  "updatePolicy": "certified",
  "message": "Server maintenance soon. Please get to a safe place."
}
```

`execute:false` creates a dry-run schedule. Enabling execution still requires
the normal mutation, capability, change-contract, optional approval, update
readiness, backup, and recovery contracts.

## Read API

Authenticated operators can inspect the current calculation at:

```http
GET /api/ops/maintenance-planner
```

The response includes `source`, `confidence`, `evidence`, `recommendation`,
`recommendations`, `baseline`, `comparison`, `policy`, and runtime collector
state. The Operations page renders the same evidence and never hides fallback
mode.

## Metrics And Alerting

The existing `dash-change-intelligence` scrape includes label-free metrics:

```text
dash_maintenance_planner_enabled
dash_maintenance_planner_collector_up
dash_maintenance_planner_measured
dash_maintenance_planner_observation_buckets
dash_maintenance_planner_recommended_expected_players
dash_maintenance_planner_baseline_expected_players
dash_maintenance_planner_expected_player_minutes_saved
```

`DashMaintenancePlannerCollectorDown` fires after ten minutes when the feature
is enabled but policy/database evaluation is unavailable. Learning mode is not
an alert: it is an expected, visible evidence state after first activation.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `DUNE_MAINTENANCE_PLANNER_ENABLED` | `true` | Enables aggregate observation and recommendations. |
| `DUNE_MAINTENANCE_PLANNER_POLICY` | `/workspace/config/maintenance-planner.json` | Container policy path. |
| `timezone` | `America/Regina` | Local candidate and weekday boundary. |
| `lookbackDays` | `28` | Population evidence horizon. |
| `retentionDays` | `90` | Aggregate bucket retention. |
| `horizonDays` | `7` | Future search horizon. |
| `bucketSeconds` | `300` | Zero-inclusive aggregation bucket. |
| `slotMinutes` | `30` | Candidate spacing. |
| `durationMinutes` | `30` | Modeled maintenance duration. |
| `eligibleLocalStart` / `eligibleLocalEnd` | `02:00` / `09:00` | Allowed local search window. |
| `defaultLocalTime` | `06:00` | Honest fallback and comparison baseline. |
| `minimumNoticeMinutes` | `30` | Earliest future candidate. |
| `minimumWindowCoverage` | `0.8` | Required bucket coverage per historical sample day. |
| `minimumSampleDays` | `2` | Complete days required before measured ranking. |
| `weekdayWeightingMinimumDays` | `2` | Matching weekdays required before weekday-only estimates. |
| `recommendationCount` | `8` | Maximum ranked choices returned. |

Policy validation rejects unknown keys, bad timezones, cross-midnight eligible
windows, incompatible bucket/duration boundaries, and out-of-range evidence or
horizon settings.

## Verification

Run:

```bash
make test-maintenance-planner
python3 scripts/test-admin-panel-safe-surfaces.py
```

The focused tests prove zero-inclusive bucket aggregation without identity,
fallback honesty, low-impact ranking against a populated default window,
policy failure boundaries, exact-time scheduling, delayed warning start, API,
dashboard, and metrics exposure.
