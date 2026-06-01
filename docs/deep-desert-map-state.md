# Deep Desert Map State Runbook

Confidence: high for the current live schema observed on 2026-05-28.

## Why Casual and Hardcore Scans Overlap

Both Deep Desert instances use the same map identity for scan/probe area state:

| Instance | Partition | Dimension | World map | Area map name |
| --- | ---: | ---: | --- | --- |
| `01 Recommended PVE Casual` | `8` | `0` | `DeepDesert_1` | `DeepDesert` |
| `02 PVE Hardcore` | `31` | `1` | `DeepDesert_1` | `DeepDesert` |

`dune.map_areas` stores survey/probe area progress with primary key
`(account_id, area_id, map_name)`. It has no `dimension_index`. Any player scan
or probe recorded for `map_name='DeepDesert'` is therefore shared between Casual
DD and Hardcore DD.

This is separate from resource/spice state. `dune.resourcefield_state` and
`dune.spicefield_types` are dimension-aware, so those can be inspected or reset
per DD dimension. Map scan/probe area state cannot be split per DD dimension
without a deeper game/schema change.

## Reset Everyone's Deep Desert Scan/Probe State

Use this when players have stale or mismatched scanned/probed Deep Desert areas
after moving between Casual and Hardcore DD. This clears area discovery/survey
state only. It does not reset bases, actors, totems, resources, spice fields,
POI marker rows, or world partitions.

Run on the production host only:

```bash
ssh kspls0
cd /home/keith/Documents/code/DuneAwakeningSelfHost
./scripts/reset-deep-desert-map-areas.sh .env
./scripts/reset-deep-desert-map-areas.sh .env --execute
```

The script is dry-run by default. On `--execute`, it refuses to run unless
`hostname -s` matches `DUNE_DD_MAP_AREAS_REQUIRE_HOST`, which defaults to
`kspls0`.

Each execution creates a timestamped backup table before deleting rows:

```text
dune.operator_map_areas_deepdesert_backup_<UTC timestamp>
```

The manual SQL equivalent is:

```sql
BEGIN;

CREATE TABLE dune.operator_map_areas_deepdesert_backup_YYYYMMDD AS
SELECT now() AS backed_up_at, m.*
FROM dune.map_areas m
WHERE m.map_name = 'DeepDesert';

DELETE FROM dune.map_areas
WHERE map_name = 'DeepDesert';

COMMIT;
```

## Validate

```bash
docker compose --env-file .env exec -T postgres \
  psql -U dune -d dune_sb_1_4_0_0 -P pager=off -c \
  "select count(*) from dune.map_areas where map_name = 'DeepDesert';"
```

Expected result after a full reset:

```text
 count
-------
     0
```

## Restore From A Backup

Restore only if the reset was a mistake. Replace the backup table name with the
one printed by the script.

```sql
INSERT INTO dune.map_areas (
  account_id,
  area_id,
  time_discovered,
  time_first_entered,
  survey_point_marker_id,
  map_name,
  items_surveyed_target,
  items_surveyed_progress
)
SELECT
  account_id,
  area_id,
  time_discovered,
  time_first_entered,
  survey_point_marker_id,
  map_name,
  items_surveyed_target,
  items_surveyed_progress
FROM dune.operator_map_areas_deepdesert_backup_YYYYMMDD
ON CONFLICT (account_id, area_id, map_name) DO UPDATE SET
  time_discovered = excluded.time_discovered,
  time_first_entered = excluded.time_first_entered,
  survey_point_marker_id = excluded.survey_point_marker_id,
  items_surveyed_target = excluded.items_surveyed_target,
  items_surveyed_progress = excluded.items_surveyed_progress;
```

## Current Live Incident

On 2026-05-28, all `DeepDesert` rows in `dune.map_areas` were backed up to:

```text
dune.operator_map_areas_deepdesert_backup_20260528
```

Then `126` rows were deleted from `dune.map_areas` for `map_name='DeepDesert'`.
The post-delete count was `0`. Confidence: high.
