#!/usr/bin/env bash
set -euo pipefail

action="${1:-status}"
env_file="${2:-.env}"
required_host="${DUNE_BRT_DD_DB_SHIM_HOST:-kspls0}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
backup_root="${DUNE_BRT_DD_DB_SHIM_BACKUP_DIR:-$repo_root/backups/operations/brt-dd-db-metadata-map-shim}"
sample_player_id="${DUNE_BRT_DD_DB_SHIM_SAMPLE_PLAYER_ID:-17}"
shimmed_functions=(
  base_backup_get_available_backups
  base_backup_get_actors_to_spawn
  base_backup_get_data
  base_backup_get_buildable_data
  base_backup_finish_placing
  base_backup_get_totem_data
  base_backup_get_totem_data_from_totem_id
  brt_dd_shift_backup_transform
  brt_dd_shift_actor_transform
  brt_dd_try_auto_backup
  brt_dd_log_event
)

short_host="$(hostname -s 2>/dev/null || hostname 2>/dev/null || true)"
if [[ "$short_host" != "$required_host" && "${DUNE_BRT_DD_DB_SHIM_ALLOW_ANY_HOST:-0}" != "1" ]]; then
  echo "ERROR: refusing to run on host '$short_host'; required '$required_host'." >&2
  exit 1
fi

cd "$repo_root"

db_name="$(
  awk -F= '
    /^DUNE_GAME_DB_NAME=/ {
      sub(/^[^=]*=/, "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$env_file"
)"
db_name="${db_name:-dune_sb_1_4_5_0}"

compose_cmd() {
  local files file
  IFS=: read -ra files <<<"$(./scripts/compose-files.sh "$env_file")"
  printf 'docker compose'
  for file in "${files[@]}"; do
    printf ' -f %q' "$file"
  done
  printf ' --env-file %q' "$env_file"
}

psql() {
  local compose
  compose="$(compose_cmd)"
  eval "$compose exec -T postgres psql -U dune -d \"\$db_name\" -v ON_ERROR_STOP=1 -P pager=off" "$@"
}

backup_functions() {
  local stamp dir
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dir="$backup_root/$stamp"
  mkdir -p "$dir"
  psql -qAt >"$dir/original-functions.sql" <<'SQL'
select pg_get_functiondef(p.oid) || E';\n'
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'dune'
  and p.proname in (
    'base_backup_get_available_backups',
    'base_backup_get_actors_to_spawn',
    'base_backup_get_data',
    'base_backup_get_buildable_data',
    'base_backup_finish_placing',
    'base_backup_get_totem_data',
    'base_backup_get_totem_data_from_totem_id',
    'brt_dd_shift_backup_transform',
    'brt_dd_shift_actor_transform',
    'brt_dd_try_auto_backup',
    'brt_dd_log_event'
  )
order by p.proname;
SQL
  ln -sfn "$dir" "$backup_root/latest"
  echo "backup=$dir/original-functions.sql"
}

apply_shim() {
  backup_functions
psql <<'SQL'
BEGIN;

CREATE TABLE IF NOT EXISTS dune.brt_dd_shim_events (
    id bigserial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    event text NOT NULL,
    backup_id bigint,
    player_id bigint,
    totem_id bigint,
    player_map text,
    player_partition bigint,
    player_dimension integer,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS dune.brt_dd_shim_settings (
    key text PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO dune.brt_dd_shim_settings (key, value)
VALUES ('z_mode', 'anchor')
ON CONFLICT (key) DO NOTHING;

INSERT INTO dune.brt_dd_shim_settings (key, value)
VALUES ('preview_shift_mode', 'full')
ON CONFLICT (key) DO NOTHING;

INSERT INTO dune.brt_dd_shim_settings (key, value)
VALUES
    ('auto_backup_on_brt_call', 'false'),
    ('auto_backup_cooldown_seconds', '300'),
    ('auto_backup_radius', '20000'),
    ('auto_backup_source_events', 'get_data'),
    ('auto_backup_player_allowlist', ''),
    ('auto_backup_one_shot', 'false'),
    ('available_backups_mode', 'normal'),
    ('available_backups_player_allowlist', ''),
    ('hidden_backup_data_mode', 'serve')
ON CONFLICT (key) DO NOTHING;

CREATE OR REPLACE FUNCTION dune.brt_dd_log_event(
    in_event text,
    in_backup_id bigint,
    in_player_id bigint,
    in_totem_id bigint,
    in_player_map text,
    in_player_partition bigint,
    in_player_dimension integer,
    in_details jsonb
)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF current_setting('dune.brt_dd_suppress_log', true) = '1' THEN
        RETURN;
    END IF;

    INSERT INTO brt_dd_shim_events (
        event,
        backup_id,
        player_id,
        totem_id,
        player_map,
        player_partition,
        player_dimension,
        details
    )
    VALUES (
        in_event,
        in_backup_id,
        in_player_id,
        in_totem_id,
        in_player_map,
        in_player_partition,
        in_player_dimension,
        coalesce(in_details, '{}'::jsonb)
    );
EXCEPTION WHEN OTHERS THEN
    NULL;
END
$function$;

CREATE OR REPLACE FUNCTION dune.brt_dd_shift_backup_transform(in_transform real[], dx real, dy real, dz real)
 RETURNS real[]
 LANGUAGE plpgsql
AS $function$
DECLARE
    result real[] := in_transform;
    lower_idx integer;
BEGIN
    IF result IS NULL THEN
        RETURN result;
    END IF;

    lower_idx := array_lower(result, 1);
    IF lower_idx IS NULL OR array_upper(result, 1) < lower_idx + 2 THEN
        RETURN result;
    END IF;

    result[lower_idx] := result[lower_idx] + dx;
    result[lower_idx + 1] := result[lower_idx + 1] + dy;
    result[lower_idx + 2] := result[lower_idx + 2] + dz;
    RETURN result;
END
$function$;

CREATE OR REPLACE FUNCTION dune.brt_dd_shift_actor_transform(in_transform transform, dx real, dy real, dz real)
 RETURNS transform
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF in_transform IS NULL THEN
        RETURN in_transform;
    END IF;

    RETURN ROW(
        ROW(
            ((in_transform).location).x + dx,
            ((in_transform).location).y + dy,
            ((in_transform).location).z + dz
        )::vector,
        (in_transform).rotation
    )::transform;
END
$function$;

CREATE OR REPLACE FUNCTION dune.brt_dd_try_auto_backup(in_player_id bigint, in_source_event text, in_backup_id bigint DEFAULT NULL)
 RETURNS bigint
 LANGUAGE plpgsql
AS $function$
DECLARE
    enabled TEXT := 'false';
    source_events TEXT := 'get_data';
    player_allowlist TEXT := '';
    one_shot TEXT := 'false';
    cooldown_seconds INTEGER := 300;
    radius REAL := 20000;
    player_map TEXT;
    player_partition BIGINT;
    player_dimension INTEGER;
    player_location REAL[];
    selected_totem_id BIGINT;
    selected_totem_entity_id BIGINT;
    selected_distance REAL;
    stale_actor_state_deleted INTEGER := 0;
    recent_count INTEGER := 0;
    created_backup_id BIGINT;
BEGIN
    IF current_setting('dune.brt_dd_suppress_log', true) = '1' THEN
        RETURN NULL;
    END IF;

    SELECT value INTO enabled
      FROM brt_dd_shim_settings
      WHERE key = 'auto_backup_on_brt_call';
    enabled := coalesce(enabled, 'false');
    IF lower(enabled) NOT IN ('1', 'true', 'yes', 'on') THEN
        RETURN NULL;
    END IF;

    SELECT coalesce(nullif(value, ''), 'get_data')
      INTO source_events
      FROM brt_dd_shim_settings
      WHERE key = 'auto_backup_source_events';
    source_events := coalesce(source_events, 'get_data');
    IF NOT EXISTS (
        SELECT 1
        FROM regexp_split_to_table(source_events, '\s*,\s*') AS allowed(value)
        WHERE allowed.value IN ('*', in_source_event)
    ) THEN
        RETURN NULL;
    END IF;

    SELECT coalesce(nullif(value, ''), '')
      INTO player_allowlist
      FROM brt_dd_shim_settings
      WHERE key = 'auto_backup_player_allowlist';
    player_allowlist := coalesce(player_allowlist, '');
    IF player_allowlist <> ''
        AND NOT EXISTS (
            SELECT 1
            FROM regexp_split_to_table(player_allowlist, '\s*,\s*') AS allowed(value)
            WHERE allowed.value ~ '^[0-9]+$'
              AND allowed.value::bigint = in_player_id
        ) THEN
        RETURN NULL;
    END IF;

    SELECT coalesce(nullif(value, ''), 'false')
      INTO one_shot
      FROM brt_dd_shim_settings
      WHERE key = 'auto_backup_one_shot';
    one_shot := coalesce(one_shot, 'false');

    SELECT coalesce(nullif(value, '')::integer, 300)
      INTO cooldown_seconds
      FROM brt_dd_shim_settings
      WHERE key = 'auto_backup_cooldown_seconds';
    cooldown_seconds := greatest(coalesce(cooldown_seconds, 300), 1);

    SELECT coalesce(nullif(value, '')::real, 20000)
      INTO radius
      FROM brt_dd_shim_settings
      WHERE key = 'auto_backup_radius';
    radius := greatest(coalesce(radius, 20000), 1);

    SELECT a.map,
           a.partition_id,
           a.dimension_index,
           ARRAY[
               ((a.transform).location).x::real,
               ((a.transform).location).y::real,
               ((a.transform).location).z::real
           ]
      INTO player_map, player_partition, player_dimension, player_location
      FROM actors a
      WHERE a.id = in_player_id;

    IF player_map NOT IN ('DeepDesert', 'DeepDesert_1') OR player_location IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT candidate.totem_id,
           sqrt(
               power(((ta.transform).location).x::real - player_location[array_lower(player_location, 1)], 2) +
               power(((ta.transform).location).y::real - player_location[array_lower(player_location, 1) + 1], 2)
           )::real AS distance_xy
      INTO selected_totem_id, selected_distance
      FROM (
          SELECT f.totem_id, 0 AS priority
          FROM base_backup_find_totems_from_player_owner(in_player_id) f

          UNION

          SELECT bbla.actor_id AS totem_id, 1 AS priority
          FROM base_backups bb
          JOIN base_backup_linked_actors bbla ON bbla.id = bb.id
          JOIN totems t ON t.id = bbla.actor_id
          WHERE bb.player_id = in_player_id
      ) candidate
      JOIN actors ta ON ta.id = candidate.totem_id
      WHERE ta.map IN ('DeepDesert', 'DeepDesert_1')
        AND ta.partition_id = player_partition
        AND ta.dimension_index = player_dimension
      ORDER BY candidate.priority, distance_xy
      LIMIT 1;

    IF selected_totem_id IS NULL OR selected_distance > radius THEN
        PERFORM brt_dd_log_event(
            'auto_backup_skipped',
            in_backup_id,
            in_player_id,
            selected_totem_id,
            player_map,
            player_partition,
            player_dimension,
            jsonb_build_object(
                'source_event', in_source_event,
                'reason', CASE WHEN selected_totem_id IS NULL THEN 'no_owned_dd_totem' ELSE 'outside_radius' END,
                'distance_xy', selected_distance,
                'radius', radius
            )
        );
        RETURN NULL;
    END IF;

    SELECT count(*)::integer
      INTO recent_count
      FROM brt_dd_shim_events e
      WHERE e.event = 'auto_backup_created'
        AND e.player_id = in_player_id
        AND e.totem_id = selected_totem_id
        AND e.created_at > clock_timestamp() - make_interval(secs => cooldown_seconds);

    IF recent_count > 0 THEN
        PERFORM brt_dd_log_event(
            'auto_backup_skipped',
            in_backup_id,
            in_player_id,
            selected_totem_id,
            player_map,
            player_partition,
            player_dimension,
            jsonb_build_object(
                'source_event', in_source_event,
                'reason', 'cooldown',
                'cooldown_seconds', cooldown_seconds,
                'distance_xy', selected_distance
            )
        );
        RETURN NULL;
    END IF;

    SELECT afe.entity_id
      INTO selected_totem_entity_id
      FROM actor_fgl_entities afe
      LEFT JOIN placeables p ON p.id = afe.actor_id
      WHERE afe.actor_id = selected_totem_id
      ORDER BY CASE WHEN afe.entity_id = p.owner_entity_id THEN 0 ELSE 1 END, afe.entity_id
      LIMIT 1;

    BEGIN
        WITH candidate_placeables AS (
            SELECT p.id
            FROM placeables p
            WHERE p.id = selected_totem_id
               OR (
                   selected_totem_entity_id IS NOT NULL
                   AND p.owner_entity_id = selected_totem_entity_id
                   AND p.has_buildable_support = TRUE
               )
        ),
        deleted AS (
            DELETE FROM actor_state s
            USING candidate_placeables cp
            WHERE s.actor_id = cp.id
              AND s.state = 'BaseBackup'::ActorState
            RETURNING s.actor_id
        )
        SELECT count(*)::integer
          INTO stale_actor_state_deleted
          FROM deleted;

        created_backup_id := base_backup_save_from_totem(in_player_id, selected_totem_id);

        UPDATE base_backups
        SET base_backup_name = 'Deep Desert BRT Backup #' || created_backup_id::text
        WHERE id = created_backup_id
          AND coalesce(nullif(base_backup_name, ''), '') = '';
    EXCEPTION WHEN OTHERS THEN
        PERFORM brt_dd_log_event(
            'auto_backup_error',
            in_backup_id,
            in_player_id,
            selected_totem_id,
            player_map,
            player_partition,
            player_dimension,
            jsonb_build_object(
                'source_event', in_source_event,
                'sqlstate', SQLSTATE,
                'message', SQLERRM,
                'stale_actor_state_deleted', stale_actor_state_deleted,
                'totem_entity_id', selected_totem_entity_id
            )
        );
        RETURN NULL;
    END;

    PERFORM brt_dd_log_event(
        'auto_backup_created',
        created_backup_id,
        in_player_id,
        selected_totem_id,
        player_map,
        player_partition,
        player_dimension,
        jsonb_build_object(
            'source_event', in_source_event,
            'trigger_backup_id', in_backup_id,
            'distance_xy', selected_distance,
            'radius', radius,
            'cooldown_seconds', cooldown_seconds,
            'source_events', source_events,
            'player_allowlist', player_allowlist,
            'stale_actor_state_deleted', stale_actor_state_deleted,
            'totem_entity_id', selected_totem_entity_id
        )
    );

    IF lower(one_shot) IN ('1', 'true', 'yes', 'on') THEN
        UPDATE brt_dd_shim_settings
        SET value = 'false',
            updated_at = clock_timestamp()
        WHERE key = 'auto_backup_on_brt_call';

        PERFORM brt_dd_log_event(
            'auto_backup_one_shot_disabled',
            created_backup_id,
            in_player_id,
            selected_totem_id,
            player_map,
            player_partition,
            player_dimension,
            jsonb_build_object(
                'source_event', in_source_event,
                'trigger_backup_id', in_backup_id
            )
        );
    END IF;

    RETURN created_backup_id;
EXCEPTION WHEN OTHERS THEN
    PERFORM brt_dd_log_event(
        'auto_backup_error',
        in_backup_id,
        in_player_id,
        selected_totem_id,
        player_map,
        player_partition,
        player_dimension,
        jsonb_build_object(
            'source_event', in_source_event,
            'sqlstate', SQLSTATE,
            'message', SQLERRM
        )
    );
    RETURN NULL;
END
$function$;

CREATE OR REPLACE FUNCTION dune.base_backup_get_available_backups(in_player_id bigint)
 RETURNS TABLE(id bigint, base_backup_name text, totem_id bigint, totem_buildable_type text, landclaim_original_global_location real[], base_backup_map text)
 LANGUAGE plpgsql
AS $function$
DECLARE
    current_player_map TEXT;
    current_player_location REAL[];
    current_player_partition BIGINT;
    current_player_dimension INTEGER;
    available_count INTEGER := 0;
    available_mode TEXT := 'normal';
    available_player_allowlist TEXT := '';
    hide_existing_backups BOOLEAN := false;
BEGIN
    SELECT a.map, ARRAY[
               ((a.transform).location).x::real,
               ((a.transform).location).y::real,
               ((a.transform).location).z::real
           ],
           a.partition_id,
           a.dimension_index
      INTO current_player_map, current_player_location, current_player_partition, current_player_dimension
      FROM actors a
      WHERE a.id = in_player_id;

    SELECT count(*)::integer
      INTO available_count
      FROM base_backups bb
        JOIN base_backup_linked_actors bbla ON bbla.id = bb.id
        JOIN totems t ON bbla.actor_id = t.id
        JOIN actors a ON a.id = t.id
        JOIN placeables p ON p.id = a.id
      WHERE bb.player_id = in_player_id;

    PERFORM brt_dd_log_event(
        'get_available_backups',
        NULL,
        in_player_id,
        NULL,
        current_player_map,
        current_player_partition,
        current_player_dimension,
        jsonb_build_object(
            'available_count', available_count,
            'player_location', current_player_location
        )
    );

    SELECT coalesce(nullif(value, ''), 'normal')
      INTO available_mode
      FROM brt_dd_shim_settings
      WHERE key = 'available_backups_mode';
    available_mode := coalesce(available_mode, 'normal');

    SELECT coalesce(nullif(value, ''), '')
      INTO available_player_allowlist
      FROM brt_dd_shim_settings
      WHERE key = 'available_backups_player_allowlist';
    available_player_allowlist := coalesce(available_player_allowlist, '');

    hide_existing_backups :=
        current_player_map IN ('DeepDesert', 'DeepDesert_1')
        AND available_mode = 'backup-only-empty'
        AND (
            available_player_allowlist = ''
            OR EXISTS (
                SELECT 1
                FROM regexp_split_to_table(available_player_allowlist, '\s*,\s*') AS allowed(value)
                WHERE allowed.value ~ '^[0-9]+$'
                  AND allowed.value::bigint = in_player_id
            )
        );

    IF hide_existing_backups THEN
        PERFORM brt_dd_try_auto_backup(in_player_id, 'get_available_backups_hidden', NULL);

        PERFORM brt_dd_log_event(
            'get_available_backups_hidden_for_backup_only',
            NULL,
            in_player_id,
            NULL,
            current_player_map,
            current_player_partition,
            current_player_dimension,
            jsonb_build_object(
                'available_count', available_count,
                'available_backups_mode', available_mode,
                'available_backups_player_allowlist', available_player_allowlist
            )
        );
        RETURN;
    END IF;

    PERFORM brt_dd_try_auto_backup(in_player_id, 'get_available_backups', NULL);

    RETURN QUERY
    SELECT
        bb.id,
        bb.base_backup_name,
        t.id AS totem_id,
        p.building_type,
        CASE
            WHEN current_player_map IS NOT NULL THEN current_player_location
            ELSE t.landclaim_original_global_location
        END AS landclaim_original_global_location,
        CASE
            WHEN current_player_map IS NOT NULL THEN current_player_map
            ELSE a.map
        END AS base_backup_map
    FROM base_backups bb
        JOIN base_backup_linked_actors bbla ON bbla.id = bb.id
        JOIN totems t ON bbla.actor_id = t.id
        JOIN actors a ON a.id = t.id
        JOIN placeables p ON p.id = a.id
    WHERE bb.player_id = in_player_id
    ORDER BY bb.id DESC;
END
$function$;

CREATE OR REPLACE FUNCTION dune.base_backup_get_totem_data(in_base_backup_id bigint)
 RETURNS basebackuptotemdata
 LANGUAGE plpgsql
AS $function$
DECLARE
    totem_id BIGINT;
    backup_player_id BIGINT;
    result BaseBackupTotemData;
    current_player_map TEXT;
    current_player_partition BIGINT;
    current_player_dimension INTEGER;
BEGIN
    SELECT t.id, bb.player_id, player_actor.map, player_actor.partition_id, player_actor.dimension_index
        INTO totem_id, backup_player_id, current_player_map, current_player_partition, current_player_dimension
        FROM base_backups bb
        JOIN base_backup_linked_actors bbla ON bbla.id = bb.id
        JOIN totems t ON t.id = bbla.actor_id
        LEFT JOIN actors player_actor ON player_actor.id = bb.player_id
        WHERE bb.id = in_base_backup_id
        LIMIT 1;

    IF totem_id IS NULL THEN
        RAISE EXCEPTION 'No totem found for base_backup id %', in_base_backup_id;
    END IF;

    result := base_backup_get_totem_data_from_totem_id(totem_id);

    IF current_player_map IS NOT NULL THEN
        result := ROW(
            result.totem_actor_id,
            result.totem_building_type,
            result.landclaim_original_global_location,
            result.landclaim_original_global_yaw_rotation,
            result.landclaim_vertical_level,
            result.landclaim_grid,
            current_player_map
        )::BaseBackupTotemData;
    END IF;

    PERFORM brt_dd_log_event(
        'get_totem_data',
        in_base_backup_id,
        backup_player_id,
        totem_id,
        current_player_map,
        current_player_partition,
        current_player_dimension,
        jsonb_build_object(
            'returned_map', result.totem_map,
            'returned_anchor', result.landclaim_original_global_location
        )
    );

    RETURN result;
END;
$function$;

CREATE OR REPLACE FUNCTION dune.base_backup_get_totem_data_from_totem_id(in_totem_id bigint)
 RETURNS basebackuptotemdata
 LANGUAGE plpgsql
AS $function$
DECLARE
    result BaseBackupTotemData;
    current_player_map TEXT;
    current_player_location REAL[];
    owner_player_id BIGINT;
    owner_partition BIGINT;
    owner_dimension INTEGER;
BEGIN
    SELECT
        t.id,
        p.building_type,
        bb.player_id,
        CASE
            WHEN player_actor.map IS NOT NULL THEN player_actor.map
            ELSE a.map
        END AS totem_map,
        player_actor.partition_id,
        player_actor.dimension_index,
        t.landclaim_original_global_location,
        t.landclaim_original_global_yaw_rotation,
        t.landclaim_vertical_level,
        CASE
            WHEN player_actor.id IS NOT NULL THEN ARRAY[
                ((player_actor.transform).location).x::real,
                ((player_actor.transform).location).y::real,
                ((player_actor.transform).location).z::real
            ]
            ELSE NULL
        END
    INTO
        result.totem_actor_id,
        result.totem_building_type,
        owner_player_id,
        result.totem_map,
        owner_partition,
        owner_dimension,
        result.landclaim_original_global_location,
        result.landclaim_original_global_yaw_rotation,
        result.landclaim_vertical_level,
        current_player_location
    FROM totems t
        JOIN placeables p ON p.id = t.id
        JOIN actors a ON a.id = t.id
        LEFT JOIN base_backup_linked_actors bbla ON bbla.actor_id = t.id
        LEFT JOIN base_backups bb ON bb.id = bbla.id
        LEFT JOIN actors player_actor ON player_actor.id = bb.player_id
    WHERE t.id = in_totem_id
    ORDER BY CASE WHEN player_actor.map IN ('DeepDesert', 'DeepDesert_1') THEN 0 ELSE 1 END
    LIMIT 1;

    IF result.totem_actor_id IS NULL THEN
        RAISE EXCEPTION 'No totem found for totem_id %', in_totem_id;
    END IF;

    IF current_player_location IS NOT NULL THEN
        result := ROW(
            result.totem_actor_id,
            result.totem_building_type,
            current_player_location,
            result.landclaim_original_global_yaw_rotation,
            result.landclaim_vertical_level,
            result.landclaim_grid,
            result.totem_map
        )::BaseBackupTotemData;
    END IF;

    SELECT array_agg(ROW(grid_location_x, grid_location_y)::SMALLINTPOINT)
        INTO result.landclaim_grid
        FROM landclaim_segments s
        WHERE s.totem_id = result.totem_actor_id;

    PERFORM brt_dd_log_event(
        'get_totem_data_from_totem_id',
        NULL,
        owner_player_id,
        in_totem_id,
        result.totem_map,
        owner_partition,
        owner_dimension,
        jsonb_build_object(
            'returned_anchor', result.landclaim_original_global_location,
            'grid_segments', coalesce(array_length(result.landclaim_grid, 1), 0)
        )
    );

    RETURN result;
END;
$function$;

CREATE OR REPLACE FUNCTION dune.base_backup_get_data(in_base_backup_id bigint)
 RETURNS getbasebackupdata
 LANGUAGE plpgsql
AS $function$
DECLARE
    base_backup_name TEXT;
    totem_data BaseBackupTotemData;
    buildings_array BaseBackupBuildingItem[];
    placeables_array BaseBackupPlaceableItem[];
    result GetBaseBackupData;
    source_anchor REAL[];
    target_anchor REAL[];
    shift_backup BOOLEAN := false;
    dx REAL := 0;
    dy REAL := 0;
    dz REAL := 0;
    backup_player_id BIGINT;
    target_map TEXT;
    target_partition BIGINT;
    target_dimension INTEGER;
    building_count INTEGER := 0;
    placeable_count INTEGER := 0;
    z_mode TEXT := 'anchor';
    preview_shift_mode TEXT := 'full';
    preview_shift_buildings BOOLEAN := true;
    preview_shift_placeables BOOLEAN := true;
    source_actor_floor REAL;
    source_building_floor REAL;
    available_mode TEXT := 'normal';
    available_player_allowlist TEXT := '';
    hidden_data_mode TEXT := 'serve';
    deny_cached_backup_data BOOLEAN := false;
BEGIN
    SELECT bb.base_backup_name, t.landclaim_original_global_location
        INTO base_backup_name, source_anchor
        FROM base_backups bb
        JOIN base_backup_linked_actors bbla ON bbla.id = bb.id
        JOIN totems t ON t.id = bbla.actor_id
        WHERE bb.id = in_base_backup_id
        LIMIT 1;

    SELECT ARRAY[
               ((a.transform).location).x::real,
               ((a.transform).location).y::real,
               ((a.transform).location).z::real
           ],
           bb.player_id,
           a.map,
           a.partition_id,
           a.dimension_index
        INTO target_anchor, backup_player_id, target_map, target_partition, target_dimension
        FROM base_backups bb
        JOIN actors a ON a.id = bb.player_id
        WHERE bb.id = in_base_backup_id
        LIMIT 1;

    SELECT coalesce(nullif(value, ''), 'normal')
      INTO available_mode
      FROM brt_dd_shim_settings
      WHERE key = 'available_backups_mode';
    available_mode := coalesce(available_mode, 'normal');

    SELECT coalesce(nullif(value, ''), '')
      INTO available_player_allowlist
      FROM brt_dd_shim_settings
      WHERE key = 'available_backups_player_allowlist';
    available_player_allowlist := coalesce(available_player_allowlist, '');

    SELECT coalesce(nullif(value, ''), 'serve')
      INTO hidden_data_mode
      FROM brt_dd_shim_settings
      WHERE key = 'hidden_backup_data_mode';
    hidden_data_mode := coalesce(hidden_data_mode, 'serve');

    deny_cached_backup_data :=
        target_map IN ('DeepDesert', 'DeepDesert_1')
        AND available_mode = 'backup-only-empty'
        AND hidden_data_mode = 'return-null'
        AND (
            available_player_allowlist = ''
            OR EXISTS (
                SELECT 1
                FROM regexp_split_to_table(available_player_allowlist, '\s*,\s*') AS allowed(value)
                WHERE allowed.value ~ '^[0-9]+$'
                  AND allowed.value::bigint = backup_player_id
            )
        );

    IF deny_cached_backup_data THEN
        PERFORM brt_dd_try_auto_backup(backup_player_id, 'get_data', in_base_backup_id);

        PERFORM brt_dd_log_event(
            'get_data_hidden_for_backup_only',
            in_base_backup_id,
            backup_player_id,
            NULL,
            target_map,
            target_partition,
            target_dimension,
            jsonb_build_object(
                'available_backups_mode', available_mode,
                'available_backups_player_allowlist', available_player_allowlist,
                'hidden_backup_data_mode', hidden_data_mode
            )
        );
        RETURN NULL::GetBaseBackupData;
    END IF;

    IF source_anchor IS NOT NULL
        AND target_anchor IS NOT NULL
        AND array_length(source_anchor, 1) >= 3
        AND array_length(target_anchor, 1) >= 3 THEN
        shift_backup := true;
        dx := target_anchor[array_lower(target_anchor, 1)] - source_anchor[array_lower(source_anchor, 1)];
        dy := target_anchor[array_lower(target_anchor, 1) + 1] - source_anchor[array_lower(source_anchor, 1) + 1];
        dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_anchor[array_lower(source_anchor, 1) + 2];

        SELECT value INTO z_mode
          FROM brt_dd_shim_settings
          WHERE key = 'z_mode';
        z_mode := coalesce(z_mode, 'anchor');

        IF z_mode = 'actor-floor' THEN
            SELECT min(((a.transform).location).z)::real
              INTO source_actor_floor
              FROM actors a
              JOIN base_backup_linked_actors bbla ON bbla.actor_id = a.id
              WHERE bbla.id = in_base_backup_id;
            IF source_actor_floor IS NOT NULL THEN
                dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_actor_floor;
            END IF;
        ELSIF z_mode = 'building-floor' THEN
            SELECT min(bi.transform[array_lower(bi.transform, 1) + 2])::real
              INTO source_building_floor
              FROM building_instances bi
              JOIN base_backup_linked_actors bbla ON bbla.actor_id = bi.building_id
              WHERE bbla.id = in_base_backup_id;
            IF source_building_floor IS NOT NULL THEN
                dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_building_floor;
            END IF;
        ELSIF z_mode = 'xy-only' THEN
            dz := 0;
        END IF;

        SELECT value INTO preview_shift_mode
          FROM brt_dd_shim_settings
          WHERE key = 'preview_shift_mode';
        preview_shift_mode := coalesce(preview_shift_mode, 'full');

        IF preview_shift_mode = 'metadata-only' THEN
            preview_shift_buildings := false;
            preview_shift_placeables := false;
        ELSIF preview_shift_mode = 'buildings-only' THEN
            preview_shift_buildings := true;
            preview_shift_placeables := false;
        ELSIF preview_shift_mode = 'placeables-only' THEN
            preview_shift_buildings := false;
            preview_shift_placeables := true;
        ELSE
            preview_shift_mode := 'full';
            preview_shift_buildings := true;
            preview_shift_placeables := true;
        END IF;
    END IF;

    PERFORM brt_dd_try_auto_backup(backup_player_id, 'get_data', in_base_backup_id);

    totem_data := base_backup_get_totem_data(in_base_backup_id);

    SELECT array_agg((
            bi.building_id,
            bi.instance_id,
            bi.building_type,
            CASE
                WHEN shift_backup AND preview_shift_buildings THEN brt_dd_shift_backup_transform(bi.transform, dx, dy, dz)
                ELSE bi.transform
            END,
            bi.building_flags
        )::BaseBackupBuildingItem)
        INTO buildings_array
        FROM
            building_instances bi
            JOIN base_backup_linked_actors bbla ON bi.building_id = bbla.actor_id
        WHERE bbla.id = in_base_backup_id;

    building_count := coalesce(array_length(buildings_array, 1), 0);

    SELECT array_agg((
            p.building_type,
            CASE
                WHEN shift_backup AND preview_shift_placeables THEN brt_dd_shift_actor_transform(a.transform, dx, dy, dz)
                ELSE a.transform
            END
        )::BaseBackupPlaceableItem)
        INTO placeables_array
        FROM
            placeables p
            JOIN actors a ON p.id = a.id
            JOIN base_backup_linked_actors bbla ON a.id = bbla.actor_id
        WHERE
            bbla.id = in_base_backup_id;

    placeable_count := coalesce(array_length(placeables_array, 1), 0);

    result := ROW(base_backup_name, totem_data, buildings_array, placeables_array)::GetBaseBackupData;
    PERFORM brt_dd_log_event(
        'get_data',
        in_base_backup_id,
        backup_player_id,
        totem_data.totem_actor_id,
        target_map,
        target_partition,
        target_dimension,
        jsonb_build_object(
            'shift_backup', shift_backup,
            'source_anchor', source_anchor,
            'target_anchor', target_anchor,
            'dx', dx,
            'dy', dy,
            'dz', dz,
            'z_mode', z_mode,
            'preview_shift_mode', preview_shift_mode,
            'preview_shift_buildings', preview_shift_buildings,
            'preview_shift_placeables', preview_shift_placeables,
            'source_actor_floor', source_actor_floor,
            'source_building_floor', source_building_floor,
            'building_count', building_count,
            'placeable_count', placeable_count,
            'returned_map', totem_data.totem_map
        )
    );
    RETURN result;
END
$function$;

CREATE OR REPLACE FUNCTION dune.base_backup_get_actors_to_spawn(in_base_backup_id bigint)
 RETURNS SETOF actorspawninfo
 LANGUAGE plpgsql
AS $function$
DECLARE
    source_anchor REAL[];
    target_anchor REAL[];
    target_partition BIGINT;
    target_dimension INTEGER;
    backup_player_id BIGINT;
    target_map TEXT;
    shift_backup BOOLEAN := false;
    dx REAL := 0;
    dy REAL := 0;
    dz REAL := 0;
    spawn_count INTEGER := 0;
    z_mode TEXT := 'anchor';
    source_actor_floor REAL;
    source_building_floor REAL;
BEGIN
    SELECT t.landclaim_original_global_location
        INTO source_anchor
        FROM base_backups bb
        JOIN base_backup_linked_actors bbla ON bbla.id = bb.id
        JOIN totems t ON t.id = bbla.actor_id
        WHERE bb.id = in_base_backup_id
        LIMIT 1;

    SELECT ARRAY[
               ((a.transform).location).x::real,
               ((a.transform).location).y::real,
               ((a.transform).location).z::real
           ],
           bb.player_id,
           a.map,
           a.partition_id,
           a.dimension_index
        INTO target_anchor, backup_player_id, target_map, target_partition, target_dimension
        FROM base_backups bb
        JOIN actors a ON a.id = bb.player_id
        WHERE bb.id = in_base_backup_id
        LIMIT 1;

    IF source_anchor IS NOT NULL
        AND target_anchor IS NOT NULL
        AND array_length(source_anchor, 1) >= 3
        AND array_length(target_anchor, 1) >= 3 THEN
        shift_backup := true;
        dx := target_anchor[array_lower(target_anchor, 1)] - source_anchor[array_lower(source_anchor, 1)];
        dy := target_anchor[array_lower(target_anchor, 1) + 1] - source_anchor[array_lower(source_anchor, 1) + 1];
        dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_anchor[array_lower(source_anchor, 1) + 2];

        SELECT value INTO z_mode
          FROM brt_dd_shim_settings
          WHERE key = 'z_mode';
        z_mode := coalesce(z_mode, 'anchor');

        IF z_mode = 'actor-floor' THEN
            SELECT min(((a.transform).location).z)::real
              INTO source_actor_floor
              FROM actors a
              JOIN base_backup_linked_actors bbla ON bbla.actor_id = a.id
              WHERE bbla.id = in_base_backup_id;
            IF source_actor_floor IS NOT NULL THEN
                dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_actor_floor;
            END IF;
        ELSIF z_mode = 'building-floor' THEN
            SELECT min(bi.transform[array_lower(bi.transform, 1) + 2])::real
              INTO source_building_floor
              FROM building_instances bi
              JOIN base_backup_linked_actors bbla ON bbla.actor_id = bi.building_id
              WHERE bbla.id = in_base_backup_id;
            IF source_building_floor IS NOT NULL THEN
                dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_building_floor;
            END IF;
        ELSIF z_mode = 'xy-only' THEN
            dz := 0;
        END IF;
    END IF;

    SELECT count(*)::integer
      INTO spawn_count
      FROM actors as a
      WHERE a.id IN (
          SELECT actor_id FROM base_backup_linked_actors as bbla WHERE bbla.id = in_base_backup_id
      );

    PERFORM brt_dd_log_event(
        'get_actors_to_spawn',
        in_base_backup_id,
        backup_player_id,
        NULL,
        target_map,
        target_partition,
        target_dimension,
        jsonb_build_object(
            'shift_backup', shift_backup,
            'source_anchor', source_anchor,
            'target_anchor', target_anchor,
            'dx', dx,
            'dy', dy,
            'dz', dz,
            'z_mode', z_mode,
            'source_actor_floor', source_actor_floor,
            'source_building_floor', source_building_floor,
            'spawn_count', spawn_count
        )
    );

    RETURN QUERY
        SELECT
            a.id,
            a.class as class_name,
            CASE
                WHEN shift_backup THEN brt_dd_shift_actor_transform(a.transform, dx, dy, dz)
                ELSE a.transform
            END AS transform,
            CASE
                WHEN shift_backup THEN target_partition
                ELSE a.partition_id
            END AS partition_id,
            CASE
                WHEN shift_backup THEN target_dimension
                ELSE a.dimension_index
            END AS dimension_index
        FROM actors as a
        WHERE a.id IN (
            SELECT actor_id FROM base_backup_linked_actors as bbla WHERE bbla.id = in_base_backup_id
        );
END
$function$;

CREATE OR REPLACE FUNCTION dune.base_backup_get_buildable_data(in_base_backup_id bigint)
 RETURNS TABLE(buildable_type text, total_count integer)
 LANGUAGE plpgsql
AS $function$
DECLARE
    backup_player_id BIGINT;
    target_map TEXT;
    target_partition BIGINT;
    target_dimension INTEGER;
    row_count INTEGER := 0;
BEGIN
    SELECT bb.player_id, a.map, a.partition_id, a.dimension_index
      INTO backup_player_id, target_map, target_partition, target_dimension
      FROM base_backups bb
      LEFT JOIN actors a ON a.id = bb.player_id
      WHERE bb.id = in_base_backup_id
      LIMIT 1;

    SELECT count(*)::integer
      INTO row_count
      FROM (
        SELECT bi.building_type AS buildable_type
        FROM base_backup_linked_actors bla
        JOIN building_instances bi ON bla.actor_id = bi.building_id
        WHERE
            bla.id = in_base_backup_id AND
            (bi.building_flags IS NULL OR (bi.building_flags & (1 << 2) = 0 AND bi.building_flags & (1 << 7) = 0))
        GROUP BY bi.building_type

        UNION ALL

        SELECT p.building_type AS buildable_type
        FROM base_backup_linked_actors bla
        JOIN placeables p ON bla.actor_id = p.id
        WHERE bla.id = in_base_backup_id AND p.is_hologram = FALSE
        GROUP BY p.building_type
      ) t;

    PERFORM brt_dd_log_event(
        'get_buildable_data',
        in_base_backup_id,
        backup_player_id,
        NULL,
        target_map,
        target_partition,
        target_dimension,
        jsonb_build_object('row_count', row_count)
    );

    RETURN QUERY
    SELECT t.buildable_type, SUM(t.cnt)::INT AS total_count
    FROM (
        SELECT bi.building_type AS buildable_type, COUNT(*) AS cnt
        FROM base_backup_linked_actors bla
        JOIN building_instances bi ON bla.actor_id = bi.building_id
        WHERE
            bla.id = in_base_backup_id AND
            (bi.building_flags IS NULL OR (bi.building_flags & (1 << 2) = 0 AND bi.building_flags & (1 << 7) = 0))
        GROUP BY bi.building_type

        UNION ALL

        SELECT p.building_type AS buildable_type, COUNT(*) AS cnt
        FROM base_backup_linked_actors bla
        JOIN placeables p ON bla.actor_id = p.id
        WHERE bla.id = in_base_backup_id AND p.is_hologram = FALSE
        GROUP BY p.building_type
    ) t
    GROUP BY t.buildable_type;
END
$function$;

CREATE OR REPLACE FUNCTION dune.base_backup_finish_placing(in_base_backup_id bigint)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
    source_anchor REAL[];
    target_anchor REAL[];
    shift_backup BOOLEAN := false;
    dx REAL := 0;
    dy REAL := 0;
    dz REAL := 0;
    linked_actor_count INTEGER := 0;
    linked_actors_near_target INTEGER := 0;
    backup_player_id BIGINT;
    target_map TEXT;
    target_partition BIGINT;
    target_dimension INTEGER;
    z_mode TEXT := 'anchor';
    source_actor_floor REAL;
    source_building_floor REAL;
BEGIN
    SELECT t.landclaim_original_global_location
        INTO source_anchor
        FROM base_backups bb
        JOIN base_backup_linked_actors bbla ON bbla.id = bb.id
        JOIN totems t ON t.id = bbla.actor_id
        WHERE bb.id = in_base_backup_id
        LIMIT 1;

    SELECT ARRAY[
               ((a.transform).location).x::real,
               ((a.transform).location).y::real,
               ((a.transform).location).z::real
           ],
           bb.player_id,
           a.map,
           a.partition_id,
           a.dimension_index
        INTO target_anchor, backup_player_id, target_map, target_partition, target_dimension
        FROM base_backups bb
        JOIN actors a ON a.id = bb.player_id
        WHERE bb.id = in_base_backup_id
        LIMIT 1;

    IF source_anchor IS NOT NULL
        AND target_anchor IS NOT NULL
        AND array_length(source_anchor, 1) >= 3
        AND array_length(target_anchor, 1) >= 3 THEN
        shift_backup := true;
        dx := target_anchor[array_lower(target_anchor, 1)] - source_anchor[array_lower(source_anchor, 1)];
        dy := target_anchor[array_lower(target_anchor, 1) + 1] - source_anchor[array_lower(source_anchor, 1) + 1];
        dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_anchor[array_lower(source_anchor, 1) + 2];

        SELECT value INTO z_mode
          FROM brt_dd_shim_settings
          WHERE key = 'z_mode';
        z_mode := coalesce(z_mode, 'anchor');

        IF z_mode = 'actor-floor' THEN
            SELECT min(((a.transform).location).z)::real
              INTO source_actor_floor
              FROM actors a
              JOIN base_backup_linked_actors bbla ON bbla.actor_id = a.id
              WHERE bbla.id = in_base_backup_id;
            IF source_actor_floor IS NOT NULL THEN
                dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_actor_floor;
            END IF;
        ELSIF z_mode = 'building-floor' THEN
            SELECT min(bi.transform[array_lower(bi.transform, 1) + 2])::real
              INTO source_building_floor
              FROM building_instances bi
              JOIN base_backup_linked_actors bbla ON bbla.actor_id = bi.building_id
              WHERE bbla.id = in_base_backup_id;
            IF source_building_floor IS NOT NULL THEN
                dz := target_anchor[array_lower(target_anchor, 1) + 2] - source_building_floor;
            END IF;
        ELSIF z_mode = 'xy-only' THEN
            dz := 0;
        END IF;
    END IF;

    IF shift_backup THEN
        SELECT
            count(*)::integer,
            count(*) FILTER (
                WHERE abs(((a.transform).location).x - target_anchor[array_lower(target_anchor, 1)]) < 20000
                  AND abs(((a.transform).location).y - target_anchor[array_lower(target_anchor, 1) + 1]) < 20000
            )::integer
        INTO linked_actor_count, linked_actors_near_target
        FROM actors a
        JOIN base_backup_linked_actors bbl ON bbl.actor_id = a.id
        WHERE bbl.id = in_base_backup_id;

        IF linked_actor_count > 0 AND linked_actors_near_target * 2 >= linked_actor_count THEN
            shift_backup := false;
        END IF;
    END IF;

    PERFORM brt_dd_log_event(
        'finish_placing_begin',
        in_base_backup_id,
        backup_player_id,
        NULL,
        target_map,
        target_partition,
        target_dimension,
        jsonb_build_object(
            'shift_backup', shift_backup,
            'source_anchor', source_anchor,
            'target_anchor', target_anchor,
            'dx', dx,
            'dy', dy,
            'dz', dz,
            'z_mode', z_mode,
            'source_actor_floor', source_actor_floor,
            'source_building_floor', source_building_floor,
            'linked_actor_count', linked_actor_count,
            'linked_actors_near_target', linked_actors_near_target
        )
    );

    IF shift_backup THEN
        UPDATE building_instances bi
        SET transform = brt_dd_shift_backup_transform(bi.transform, dx, dy, dz)
        FROM base_backup_linked_actors bbl
        WHERE bbl.id = in_base_backup_id
          AND bi.building_id = bbl.actor_id;
    END IF;

    WITH base_info AS (
        SELECT
            bb.id AS base_backup_id,
            a.partition_id,
            a.dimension_index,
            a.map
        FROM
            base_backups bb
            JOIN actors a on bb.player_id = a.id
        WHERE
            bb.id = in_base_backup_id
    )
    UPDATE actors
    SET
        partition_id = base_info.partition_id,
        dimension_index = base_info.dimension_index,
        map = base_info.map,
        transform = CASE
            WHEN shift_backup THEN brt_dd_shift_actor_transform(actors.transform, dx, dy, dz)
            ELSE actors.transform
        END
    FROM
        base_backup_linked_actors bbl
        JOIN base_info ON bbl.id = base_info.base_backup_id
    WHERE
        actors.id = bbl.actor_id;

    DELETE FROM actor_state a
        WHERE actor_id = ANY(
            SELECT actor_id
            FROM base_backup_linked_actors bbla
            WHERE bbla.id = in_base_backup_id
        );

    DELETE FROM base_backups
        WHERE id = in_base_backup_id;

    PERFORM brt_dd_log_event(
        'finish_placing_end',
        in_base_backup_id,
        backup_player_id,
        NULL,
        target_map,
        target_partition,
        target_dimension,
        jsonb_build_object('deleted_backup', true)
    );
END
$function$;

COMMENT ON FUNCTION dune.base_backup_get_available_backups(bigint)
  IS 'DD BRT metadata shim: when the owner is currently in Deep Desert, report the current map to the client instead of the backup source map.';
COMMENT ON FUNCTION dune.base_backup_get_actors_to_spawn(bigint)
  IS 'DD BRT metadata shim: when the owner is currently in Deep Desert, shift returned spawn transforms and partition to the owner current location.';
COMMENT ON FUNCTION dune.base_backup_get_data(bigint)
  IS 'DD BRT metadata shim: when the owner is currently in Deep Desert, report the current map and optionally shift returned preview transforms around the owner current location.';
COMMENT ON FUNCTION dune.base_backup_get_buildable_data(bigint)
  IS 'DD BRT metadata shim: preserve buildable count behavior while logging live BRT canary calls.';
COMMENT ON FUNCTION dune.base_backup_finish_placing(bigint)
  IS 'DD BRT metadata shim: when the owner is currently in Deep Desert, commit linked backup actor and building transforms at the owner current location unless linked actors are already shifted near that target.';
COMMENT ON FUNCTION dune.base_backup_get_totem_data(bigint)
  IS 'DD BRT metadata shim: when the backup owner is currently in Deep Desert, report the current map in returned totem metadata.';
COMMENT ON FUNCTION dune.base_backup_get_totem_data_from_totem_id(bigint)
  IS 'DD BRT metadata shim: when the totem belongs to a backup whose owner is currently in Deep Desert, report the owner current map and location in returned totem metadata.';
COMMENT ON FUNCTION dune.brt_dd_shift_backup_transform(real[], real, real, real)
  IS 'DD BRT metadata shim helper: offset the x/y/z entries in a saved base backup building transform array.';
COMMENT ON FUNCTION dune.brt_dd_shift_actor_transform(transform, real, real, real)
  IS 'DD BRT metadata shim helper: offset the x/y/z entries in an actor transform composite.';
COMMENT ON FUNCTION dune.brt_dd_try_auto_backup(bigint, text, bigint)
  IS 'DD BRT metadata shim helper: optionally create a guarded DD backup from a real BRT server metadata call when the client does not send the native backup action.';
COMMENT ON FUNCTION dune.brt_dd_log_event(text, bigint, bigint, bigint, text, bigint, integer, jsonb)
  IS 'DD BRT metadata shim helper: best-effort event logging for live BRT canaries.';

COMMIT;
SQL
}

rollback_shim() {
  local backup="${3:-$backup_root/latest/original-functions.sql}"
  [[ -f "$backup" ]] || { echo "ERROR: rollback backup not found: $backup" >&2; exit 1; }
  psql -f "$backup"
  echo "rolled_back_from=$backup"
}

rollback_pristine() {
  local oldest four_function_backup placement_function_backup candidate
  resolve_pristine_rollback_backups
  [[ -n "$oldest" && -f "$oldest" ]] || { echo "ERROR: no rollback backups found under $backup_root" >&2; exit 1; }

  if [[ -n "$placement_function_backup" && "$placement_function_backup" != "$oldest" ]]; then
    psql -f "$placement_function_backup"
    echo "rolled_back_placement_function_backup=$placement_function_backup"
  fi
  if [[ -n "$four_function_backup" && "$four_function_backup" != "$oldest" ]]; then
    psql -f "$four_function_backup"
    echo "rolled_back_four_function_backup=$four_function_backup"
  fi
  psql -f "$oldest"
  psql -c 'DROP FUNCTION IF EXISTS dune.brt_dd_shift_backup_transform(real[], real, real, real);'
  psql -c 'DROP FUNCTION IF EXISTS dune.brt_dd_shift_actor_transform(transform, real, real, real);'
  psql -c 'DROP FUNCTION IF EXISTS dune.brt_dd_try_auto_backup(bigint, text, bigint);'
  psql -c 'DROP FUNCTION IF EXISTS dune.brt_dd_log_event(text, bigint, bigint, bigint, text, bigint, integer, jsonb);'
  echo "rolled_back_oldest=$oldest"
}

resolve_pristine_rollback_backups() {
  oldest="$(find "$backup_root" -mindepth 2 -maxdepth 2 -type f -name original-functions.sql | sort | head -1 || true)"
  placement_function_backup=""
  four_function_backup=""

  while IFS= read -r candidate; do
    if rg -q 'FUNCTION dune\.base_backup_get_actors_to_spawn\(' "$candidate" \
      && rg -q 'FUNCTION dune\.base_backup_finish_placing\(' "$candidate"; then
      placement_function_backup="$candidate"
      break
    fi
  done < <(find "$backup_root" -mindepth 2 -maxdepth 2 -type f -name original-functions.sql | sort)

  while IFS= read -r candidate; do
    if rg -q 'FUNCTION dune\.base_backup_get_totem_data\(' "$candidate" \
      && rg -q 'FUNCTION dune\.base_backup_get_totem_data_from_totem_id\(' "$candidate"; then
      four_function_backup="$candidate"
      break
    fi
  done < <(find "$backup_root" -mindepth 2 -maxdepth 2 -type f -name original-functions.sql | sort)
}

rollback_plan() {
  local oldest four_function_backup placement_function_backup candidate
  resolve_pristine_rollback_backups
  [[ -n "$oldest" && -f "$oldest" ]] || { echo "ERROR: no rollback backups found under $backup_root" >&2; exit 1; }
  echo "placement_function_backup=${placement_function_backup:-none}"
  echo "four_function_backup=${four_function_backup:-none}"
  echo "oldest_metadata_backup=$oldest"
  echo "drops=dune.brt_dd_shift_backup_transform(real[], real, real, real),dune.brt_dd_shift_actor_transform(transform, real, real, real),dune.brt_dd_try_auto_backup(bigint, text, bigint),dune.brt_dd_log_event(text, bigint, bigint, bigint, text, bigint, integer, jsonb)"
}

status() {
  psql -v sample_player_id="$sample_player_id" -qAt <<'SQL'
set dune.brt_dd_suppress_log = '1';
select 'shim_setting=' || key || '=' || value
from dune.brt_dd_shim_settings
order by key;
select p.proname || ':' || coalesce(obj_description(p.oid, 'pg_proc'), 'no_comment')
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'dune'
  and p.proname in (
    'base_backup_get_available_backups',
    'base_backup_get_actors_to_spawn',
    'base_backup_get_data',
    'base_backup_finish_placing',
    'base_backup_get_totem_data',
    'base_backup_get_totem_data_from_totem_id',
    'brt_dd_shift_backup_transform',
    'brt_dd_shift_actor_transform',
    'brt_dd_try_auto_backup'
  )
order by p.proname;
select 'sample_player=' || :'sample_player_id';
select 'sample_player_actor=' || coalesce(a.id::text || ':' || a.map || ':' || a.partition_id::text || ':' || a.dimension_index::text, 'missing')
from (select :'sample_player_id'::bigint id) p
left join dune.actors a on a.id = p.id;
select 'sample_available=' || coalesce(string_agg(id::text || ':' || base_backup_map, ',' order by id), 'none')
from dune.base_backup_get_available_backups(:'sample_player_id');
select 'sample_available_anchor=' || coalesce(string_agg(id::text || ':' || landclaim_original_global_location::text, ',' order by id), 'none')
from dune.base_backup_get_available_backups(:'sample_player_id');
select 'sample_get_data=' || coalesce(
    b.id::text || ':' ||
    (d.totem).totem_map || ':' ||
    (d.totem).landclaim_original_global_location::text || ':' ||
    array_length(d.building_pieces, 1)::text || ':' ||
    array_length(d.placeables, 1)::text,
    'none'
)
from (
  select id
  from dune.base_backups
  where player_id = :'sample_player_id'
  order by id desc
  limit 1
) b
cross join lateral dune.base_backup_get_data(b.id) d;
select 'sample_get_data_first_building=' || coalesce(
    b.id::text || ':' ||
    ((d.building_pieces[1]).transform[array_lower((d.building_pieces[1]).transform, 1)])::text || ',' ||
    ((d.building_pieces[1]).transform[array_lower((d.building_pieces[1]).transform, 1) + 1])::text || ',' ||
    ((d.building_pieces[1]).transform[array_lower((d.building_pieces[1]).transform, 1) + 2])::text,
    'none'
)
from (
  select id
  from dune.base_backups
  where player_id = :'sample_player_id'
  order by id desc
  limit 1
) b
cross join lateral dune.base_backup_get_data(b.id) d
where array_length(d.building_pieces, 1) > 0;
select 'sample_get_data_first_placeable=' || coalesce(
    b.id::text || ':' ||
    (((d.placeables[1]).transform).location).x::text || ',' ||
    (((d.placeables[1]).transform).location).y::text || ',' ||
    (((d.placeables[1]).transform).location).z::text,
    'none'
)
from (
  select id
  from dune.base_backups
  where player_id = :'sample_player_id'
  order by id desc
  limit 1
) b
cross join lateral dune.base_backup_get_data(b.id) d
where array_length(d.placeables, 1) > 0;
select 'sample_actors_to_spawn_first=' || coalesce(
    b.id::text || ':' ||
    s.id::text || ':' ||
    s.partition_id::text || ':' ||
    s.dimension_index::text || ':' ||
    ((s.transform).location).x::text || ',' ||
    ((s.transform).location).y::text || ',' ||
    ((s.transform).location).z::text,
    'none'
)
from (
  select id
  from dune.base_backups
  where player_id = :'sample_player_id'
  order by id desc
  limit 1
) b
cross join lateral dune.base_backup_get_actors_to_spawn(b.id) s
limit 1;
select 'sample_get_totem_data=' || coalesce(b.id::text || ':' || (d).totem_map || ':' || (d).landclaim_original_global_location::text, 'none')
from (
  select id
  from dune.base_backups
  where player_id = :'sample_player_id'
  order by id desc
  limit 1
) b
cross join lateral dune.base_backup_get_totem_data(b.id) d;
select 'sample_get_totem_data_from_totem=' || coalesce(t.totem_id::text || ':' || (d).totem_map || ':' || (d).landclaim_original_global_location::text, 'none')
from (
  select available.totem_id
  from dune.base_backup_get_available_backups(:'sample_player_id') available
  order by available.id desc
  limit 1
) t
cross join lateral dune.base_backup_get_totem_data_from_totem_id(t.totem_id) d;
SQL
}

set_z_mode() {
  local mode="${3:-}"
  case "$mode" in
    anchor|actor-floor|building-floor|xy-only) ;;
    *)
      echo "usage: $0 set-z-mode [env_file] anchor|actor-floor|building-floor|xy-only" >&2
      exit 2
      ;;
  esac
  psql -v mode="$mode" <<'SQL'
INSERT INTO dune.brt_dd_shim_settings (key, value)
VALUES ('z_mode', :'mode')
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = clock_timestamp();
SQL
  echo "z_mode=$mode"
}

set_preview_shift_mode() {
  local mode="${3:-}"
  case "$mode" in
    full|metadata-only|buildings-only|placeables-only) ;;
    *)
      echo "usage: $0 set-preview-shift-mode [env_file] full|metadata-only|buildings-only|placeables-only" >&2
      exit 2
      ;;
  esac
  psql -v mode="$mode" <<'SQL'
INSERT INTO dune.brt_dd_shim_settings (key, value)
VALUES ('preview_shift_mode', :'mode')
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = clock_timestamp();
SQL
  echo "preview_shift_mode=$mode"
}

set_auto_backup_mode() {
  local mode="${3:-}"
  case "$mode" in
    on|true|1|enable|enabled) mode="true" ;;
    off|false|0|disable|disabled) mode="false" ;;
    *)
      echo "usage: $0 set-auto-backup-mode [env_file] on|off" >&2
      exit 2
      ;;
  esac
  psql -v mode="$mode" <<'SQL'
INSERT INTO dune.brt_dd_shim_settings (key, value)
VALUES ('auto_backup_on_brt_call', :'mode')
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = clock_timestamp();
SQL
  echo "auto_backup_on_brt_call=$mode"
}

set_auto_backup_canary() {
  local player_id="${3:-}"
  local mode="${4:-on}"
  case "$player_id" in
    ''|*[!0-9]*)
      echo "usage: $0 set-auto-backup-canary [env_file] player_id on|off" >&2
      exit 2
      ;;
  esac
  case "$mode" in
    on|true|1|enable|enabled) mode="true" ;;
    off|false|0|disable|disabled) mode="false" ;;
    *)
      echo "usage: $0 set-auto-backup-canary [env_file] player_id on|off" >&2
      exit 2
      ;;
  esac

  psql -v mode="$mode" -v player_id="$player_id" <<'SQL'
INSERT INTO dune.brt_dd_shim_settings (key, value)
VALUES
    ('auto_backup_on_brt_call', :'mode'),
    ('auto_backup_source_events', 'get_data,get_available_backups_hidden'),
    ('auto_backup_player_allowlist', :'player_id'),
    ('auto_backup_one_shot', 'true'),
    ('auto_backup_cooldown_seconds', '15'),
    ('auto_backup_radius', '50000')
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = clock_timestamp();
SQL
  echo "auto_backup_on_brt_call=$mode"
  echo "auto_backup_source_events=get_data,get_available_backups_hidden"
  echo "auto_backup_player_allowlist=$player_id"
  echo "auto_backup_one_shot=true"
  echo "auto_backup_cooldown_seconds=15"
  echo "auto_backup_radius=50000"
}

set_available_backups_mode() {
  local mode="${3:-}"
  local player_id="${4:-}"
  local hidden_data_mode="${5:-serve}"
  case "$mode" in
    normal)
      player_id=""
      hidden_data_mode="serve"
      ;;
    backup-only-empty)
      case "$player_id" in
        ''|*[!0-9]*)
          echo "usage: $0 set-available-backups-mode [env_file] normal|backup-only-empty [player_id]" >&2
          exit 2
          ;;
      esac
      case "$hidden_data_mode" in
        serve|return-null) ;;
        *)
          echo "usage: $0 set-available-backups-mode [env_file] normal|backup-only-empty [player_id] [serve|return-null]" >&2
          exit 2
          ;;
      esac
      ;;
    *)
      echo "usage: $0 set-available-backups-mode [env_file] normal|backup-only-empty [player_id] [serve|return-null]" >&2
      exit 2
      ;;
  esac

  psql -v mode="$mode" -v player_id="$player_id" -v hidden_data_mode="$hidden_data_mode" <<'SQL'
INSERT INTO dune.brt_dd_shim_settings (key, value)
VALUES
    ('available_backups_mode', :'mode'),
    ('available_backups_player_allowlist', :'player_id'),
    ('hidden_backup_data_mode', :'hidden_data_mode')
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = clock_timestamp();
SQL
  echo "available_backups_mode=$mode"
  echo "available_backups_player_allowlist=$player_id"
  echo "hidden_backup_data_mode=$hidden_data_mode"
}

self_test() {
  local test_player_id="${DUNE_BRT_DD_DB_SHIM_TEST_PLAYER_ID:-$sample_player_id}"
  local test_backup_id="${DUNE_BRT_DD_DB_SHIM_TEST_BACKUP_ID:-}"
  local test_totem_id="${DUNE_BRT_DD_DB_SHIM_TEST_TOTEM_ID:-}"
  psql -v test_player_id="$test_player_id" -v test_backup_id="$test_backup_id" -v test_totem_id="$test_totem_id" <<'SQL'
\pset tuples_only on
BEGIN;
select coalesce(nullif(:'test_backup_id', '')::bigint, (
  select id
  from dune.base_backups
  where player_id = :'test_player_id'::bigint
  order by id desc
  limit 1
)) as selected_backup_id \gset
select 'self_test_backup=' || :'selected_backup_id';
create temporary table normal_before_actor on commit drop as
select a.id, a.transform
from dune.actors a
join dune.base_backup_linked_actors l on l.actor_id = a.id
where l.id = :'selected_backup_id'::bigint;
create temporary table normal_player_anchor on commit drop as
select p.id, p.transform
from dune.base_backups bb
join dune.actors p on p.id = bb.player_id
where bb.id = :'selected_backup_id'::bigint;
create temporary table normal_before_building on commit drop as
select bi.building_id, bi.instance_id, bi.transform
from dune.building_instances bi
join dune.base_backup_linked_actors l on l.actor_id = bi.building_id
where l.id = :'selected_backup_id'::bigint;
select dune.base_backup_finish_placing(:'selected_backup_id'::bigint);
select 'normal_actor_changed=' || count(*)
from dune.actors a
join normal_before_actor b on b.id = a.id
where a.transform is distinct from b.transform;
select 'normal_building_changed=' || count(*)
from dune.building_instances bi
join normal_before_building b on b.building_id = bi.building_id and b.instance_id = bi.instance_id
where bi.transform is distinct from b.transform;
select 'normal_actor_near_player=' || count(*)
from dune.actors a
join normal_before_actor b on b.id = a.id
cross join normal_player_anchor p
where abs(((a.transform).location).x - ((p.transform).location).x) < 20000
  and abs(((a.transform).location).y - ((p.transform).location).y) < 20000;
ROLLBACK;

BEGIN;
select :'selected_backup_id'::bigint as selected_backup_id \gset
create temporary table preshift_before_actor on commit drop as
select a.id, a.transform
from dune.actors a
join dune.base_backup_linked_actors l on l.actor_id = a.id
where l.id = :'selected_backup_id'::bigint;
create temporary table preshift_player_anchor on commit drop as
select p.id, p.transform
from dune.base_backups bb
join dune.actors p on p.id = bb.player_id
where bb.id = :'selected_backup_id'::bigint;
create temporary table preshift_before_building on commit drop as
select bi.building_id, bi.instance_id, bi.transform
from dune.building_instances bi
join dune.base_backup_linked_actors l on l.actor_id = bi.building_id
where l.id = :'selected_backup_id'::bigint;
create temporary table shift_delta on commit drop as
select
  (((p.transform).location).x::real - t.landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1)])::real as dx,
  (((p.transform).location).y::real - t.landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1) + 1])::real as dy,
  (((p.transform).location).z::real - t.landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1) + 2])::real as dz
from dune.base_backups bb
join dune.actors p on p.id = bb.player_id
join dune.base_backup_linked_actors l on l.id = bb.id
join dune.totems t on t.id = l.actor_id
where bb.id = :'selected_backup_id'::bigint
limit 1;
update dune.actors a
set transform = dune.brt_dd_shift_actor_transform(a.transform, d.dx, d.dy, d.dz)
from dune.base_backup_linked_actors l, shift_delta d
where l.id = :'selected_backup_id'::bigint and l.actor_id = a.id;
update dune.building_instances bi
set transform = dune.brt_dd_shift_backup_transform(bi.transform, d.dx, d.dy, d.dz)
from dune.base_backup_linked_actors l, shift_delta d
where l.id = :'selected_backup_id'::bigint and l.actor_id = bi.building_id;
create temporary table preshift_after_manual_actor on commit drop as
select a.id, a.transform
from dune.actors a
join dune.base_backup_linked_actors l on l.actor_id = a.id
where l.id = :'selected_backup_id'::bigint;
create temporary table preshift_after_manual_building on commit drop as
select bi.building_id, bi.instance_id, bi.transform
from dune.building_instances bi
join dune.base_backup_linked_actors l on l.actor_id = bi.building_id
where l.id = :'selected_backup_id'::bigint;
select 'manual_actor_changed=' || count(*)
from preshift_after_manual_actor a
join preshift_before_actor b on b.id = a.id
where a.transform is distinct from b.transform;
select 'manual_building_changed=' || count(*)
from preshift_after_manual_building a
join preshift_before_building b on b.building_id = a.building_id and b.instance_id = a.instance_id
where a.transform is distinct from b.transform;
select dune.base_backup_finish_placing(:'selected_backup_id'::bigint);
select 'preshift_actor_changed_by_finish=' || count(*)
from dune.actors a
join preshift_after_manual_actor b on b.id = a.id
where a.transform is distinct from b.transform;
select 'preshift_building_changed_by_finish=' || count(*)
from dune.building_instances bi
join preshift_after_manual_building b on b.building_id = bi.building_id and b.instance_id = bi.instance_id
where bi.transform is distinct from b.transform;
select 'preshift_actor_near_player=' || count(*)
from dune.actors a
join preshift_after_manual_actor b on b.id = a.id
cross join preshift_player_anchor p
where abs(((a.transform).location).x - ((p.transform).location).x) < 20000
  and abs(((a.transform).location).y - ((p.transform).location).y) < 20000;
ROLLBACK;
select 'post_rollback_backup_exists=' || count(*) from dune.base_backups where id = :'selected_backup_id'::bigint;

BEGIN;
select coalesce(nullif(:'test_totem_id', '')::bigint, (
  select t.id
  from dune.base_backup_find_totems_from_player_owner(:'test_player_id'::bigint) f
  join dune.totems t on t.id = f.totem_id
  join dune.actors a on a.id = t.id
  where a.map in ('DeepDesert', 'DeepDesert_1')
  order by t.id desc
  limit 1
)) as selected_totem_id \gset
select 'self_test_totem=' || :'selected_totem_id';
select count(*) as base_backups_before_save from dune.base_backups \gset
select count(*) as linked_actors_before_save from dune.base_backup_linked_actors \gset
select dune.base_backup_save_from_totem(:'test_player_id'::bigint, :'selected_totem_id'::bigint) as created_backup_id \gset
select 'save_created_backup=' || :'created_backup_id';
select 'save_base_backups_delta=' || (count(*) - :'base_backups_before_save'::bigint)
from dune.base_backups;
select 'save_linked_actors_delta=' || (count(*) - :'linked_actors_before_save'::bigint)
from dune.base_backup_linked_actors;
select 'save_created_linked_actors=' || count(*)
from dune.base_backup_linked_actors
where id = :'created_backup_id'::bigint;
select 'save_available=' || coalesce(string_agg(id::text || ':' || base_backup_map || ':' || totem_id::text, ',' order by id), 'none')
from dune.base_backup_get_available_backups(:'test_player_id'::bigint)
where id = :'created_backup_id'::bigint;
select 'save_get_data=' || coalesce(
  :'created_backup_id' || ':' ||
  (d.totem).totem_map || ':' ||
  array_length(d.building_pieces, 1)::text || ':' ||
  array_length(d.placeables, 1)::text,
  'none'
)
from dune.base_backup_get_data(:'created_backup_id'::bigint) d;
ROLLBACK;
select 'post_rollback_created_backup_exists=' || count(*) from dune.base_backups where id = :'created_backup_id'::bigint;
SQL
}

case "$action" in
  apply) apply_shim ;;
  rollback) rollback_shim "$@" ;;
  rollback-plan) rollback_plan ;;
  rollback-pristine) rollback_pristine ;;
  self-test) self_test ;;
  set-z-mode) set_z_mode "$@" ;;
  set-preview-shift-mode) set_preview_shift_mode "$@" ;;
  set-auto-backup-mode) set_auto_backup_mode "$@" ;;
  set-auto-backup-canary) set_auto_backup_canary "$@" ;;
  set-available-backups-mode) set_available_backups_mode "$@" ;;
  status) status ;;
  *)
    echo "usage: $0 apply|rollback|rollback-plan|rollback-pristine|self-test|set-z-mode|set-preview-shift-mode|set-auto-backup-mode|set-auto-backup-canary|set-available-backups-mode|status [env_file] [rollback_sql|mode]" >&2
    exit 2
    ;;
esac
