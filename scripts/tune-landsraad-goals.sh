#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/tune-landsraad-goals.sh [ENV_FILE] [--execute]

Installs an idempotent Landsraad goal scaler and applies it to the current
term. Dry-run is the default.

Defaults:
  DUNE_LANDSRAAD_GOAL_SCALE=0.5
  DUNE_LANDSRAAD_GOAL_MIN=1
  DUNE_LANDSRAAD_GOAL_REQUIRE_HOST=kspls0
  DUNE_DATABASE=dune_sb_1_4_0_0
USAGE
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
env_file="${DUNE_ENV_FILE:-.env}"
execute=false

while (($#)); do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --execute)
      execute=true
      ;;
    *)
      env_file="$1"
      ;;
  esac
  shift
done

cd "$repo_root"

if [[ ! -f "$env_file" ]]; then
  printf 'missing env file: %s\n' "$env_file" >&2
  exit 1
fi

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

env_or_file() {
  local key="$1" default_value="${2:-}" value
  value="${!key:-}"
  if [[ -z "$value" ]]; then
    value="$(read_env "$key")"
  fi
  printf '%s' "${value:-$default_value}"
}

host_short() {
  local host_ns=""
  if command -v nsenter >/dev/null 2>&1 && [[ -e /proc/1/ns/uts ]]; then
    host_ns="$(nsenter --target 1 --uts hostname -s 2>/dev/null || true)"
  fi
  if [[ -n "$host_ns" ]]; then
    printf '%s' "$host_ns"
  else
    hostname -s 2>/dev/null || hostname
  fi
}

goal_scale="$(env_or_file DUNE_LANDSRAAD_GOAL_SCALE 0.5)"
goal_min="$(env_or_file DUNE_LANDSRAAD_GOAL_MIN 1)"
required_host="$(env_or_file DUNE_LANDSRAAD_GOAL_REQUIRE_HOST kspls0)"
db="$(env_or_file DUNE_DATABASE dune_sb_1_4_0_0)"
container_runtime="$(env_or_file CONTAINER_RUNTIME docker)"

case "$goal_min" in
  ''|*[!0-9]*) printf 'DUNE_LANDSRAAD_GOAL_MIN must be a positive integer\n' >&2; exit 64 ;;
esac

if [[ "$execute" == true && -n "$required_host" ]]; then
  current_host="$(host_short)"
  if [[ "$current_host" != "$required_host" ]]; then
    printf 'refusing Landsraad goal tuning on host %s; required host is %s\n' "$current_host" "$required_host" >&2
    exit 78
  fi
fi

compose_files="$("$script_dir/compose-files.sh" "$env_file")"
compose=("$container_runtime" compose --env-file "$env_file")
IFS=':' read -ra files <<< "$compose_files"
for file in "${files[@]}"; do
  compose+=(-f "$file")
done

psql_base=(
  "${compose[@]}" exec -T postgres
  psql -U dune -d "$db" -v ON_ERROR_STOP=1
  -v "goal_scale=$goal_scale"
  -v "goal_min=$goal_min"
)

if [[ "$execute" != true ]]; then
  "${psql_base[@]}" <<'SQL'
\pset pager off
SELECT set_config('landsraad_goal.scale', :'goal_scale', false);
SELECT set_config('landsraad_goal.min_goal', :'goal_min', false);

DO $$
DECLARE
  scale numeric := current_setting('landsraad_goal.scale')::numeric;
  min_goal integer := current_setting('landsraad_goal.min_goal')::integer;
BEGIN
  IF scale <= 0 THEN
    RAISE EXCEPTION 'DUNE_LANDSRAAD_GOAL_SCALE must be greater than zero: %', scale;
  END IF;
  IF min_goal < 1 THEN
    RAISE EXCEPTION 'DUNE_LANDSRAAD_GOAL_MIN must be at least 1: %', min_goal;
  END IF;
END $$;

\echo current_term_goal_preview
WITH current_term AS (
  SELECT term_id, start_time, end_time, winning_faction_id
    FROM dune.landsraad_decree_term
    ORDER BY term_id DESC
    LIMIT 1
),
task_goals AS (
  SELECT t.id,
         t.board_index,
         t.house_name,
         t.completed,
         t.winning_faction_id,
         t.goal_amount AS current_goal,
         COALESCE(a.original_goal_amount, t.goal_amount) AS source_goal
    FROM dune.landsraad_tasks t
    JOIN current_term ct ON ct.term_id = t.term_id
    LEFT JOIN dune.landsraad_goal_tuning_applied a ON a.task_id = t.id
)
SELECT id,
       board_index,
       house_name,
       completed,
       winning_faction_id,
       current_goal,
       GREATEST(current_setting('landsraad_goal.min_goal')::integer, CEIL(source_goal * current_setting('landsraad_goal.scale')::numeric)::integer) AS tuned_goal
  FROM task_goals
  ORDER BY board_index;
SQL
  exit 0
fi

printf 'Executing Landsraad goal tuning: scale=%s min=%s db=%s\n' "$goal_scale" "$goal_min" "$db"
"${psql_base[@]}" <<'SQL'
\pset pager off
BEGIN;
SELECT set_config('landsraad_goal.scale', :'goal_scale', true);
SELECT set_config('landsraad_goal.min_goal', :'goal_min', true);

DO $$
DECLARE
  scale numeric := current_setting('landsraad_goal.scale')::numeric;
  min_goal integer := current_setting('landsraad_goal.min_goal')::integer;
BEGIN
  IF scale <= 0 THEN
    RAISE EXCEPTION 'DUNE_LANDSRAAD_GOAL_SCALE must be greater than zero: %', scale;
  END IF;
  IF min_goal < 1 THEN
    RAISE EXCEPTION 'DUNE_LANDSRAAD_GOAL_MIN must be at least 1: %', min_goal;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS dune.landsraad_goal_tuning (
  id boolean PRIMARY KEY DEFAULT TRUE CHECK (id),
  goal_scale numeric NOT NULL CHECK (goal_scale > 0),
  min_goal integer NOT NULL DEFAULT 1 CHECK (min_goal >= 1),
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

INSERT INTO dune.landsraad_goal_tuning (id, goal_scale, min_goal, updated_at)
VALUES (TRUE, current_setting('landsraad_goal.scale')::numeric, current_setting('landsraad_goal.min_goal')::integer, now())
ON CONFLICT (id)
DO UPDATE SET goal_scale = EXCLUDED.goal_scale,
              min_goal = EXCLUDED.min_goal,
              updated_at = now();

CREATE TABLE IF NOT EXISTS dune.landsraad_goal_tuning_applied (
  task_id bigint PRIMARY KEY REFERENCES dune.landsraad_tasks(id) ON DELETE CASCADE,
  term_id bigint NOT NULL REFERENCES dune.landsraad_decree_term(term_id) ON DELETE CASCADE,
  original_goal_amount integer NOT NULL CHECK (original_goal_amount >= 1),
  applied_goal_amount integer NOT NULL CHECK (applied_goal_amount >= 1),
  goal_scale numeric NOT NULL CHECK (goal_scale > 0),
  min_goal integer NOT NULL CHECK (min_goal >= 1),
  applied_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE OR REPLACE PROCEDURE dune.landsraad_insert_tasks(
  IN in_term_id bigint,
  IN in_tasks dune.landsraadtask[],
  IN in_task_rewards dune.landsraadtaskreward[]
)
LANGUAGE plpgsql
AS $procedure$
DECLARE
  configured_scale numeric := COALESCE((SELECT goal_scale FROM dune.landsraad_goal_tuning WHERE id = TRUE), 1);
  configured_min integer := COALESCE((SELECT min_goal FROM dune.landsraad_goal_tuning WHERE id = TRUE), 1);
BEGIN
  INSERT INTO dune.landsraad_tasks (term_id, board_index, house_name, goal_amount)
    SELECT in_term_id,
           tasks.board_index,
           tasks.house_name,
           GREATEST(configured_min, CEIL(tasks.goal_amount * configured_scale)::integer)
      FROM UNNEST(in_tasks) AS tasks;

  INSERT INTO dune.landsraad_task_rewards (task_id, threshold, template_id, amount)
    SELECT tasks.id,
           task_rewards.threshold,
           task_rewards.template_id,
           task_rewards.amount
      FROM UNNEST(in_task_rewards) AS task_rewards
      LEFT JOIN dune.landsraad_tasks AS tasks ON task_rewards.house_name = tasks.house_name
     WHERE tasks.term_id = in_term_id;
END $procedure$;

\echo current_term_before
SELECT t.id, t.board_index, t.house_name, t.completed, t.winning_faction_id, t.goal_amount
  FROM dune.landsraad_tasks t
 WHERE t.term_id = (SELECT term_id FROM dune.landsraad_decree_term ORDER BY term_id DESC LIMIT 1)
 ORDER BY t.board_index;

WITH current_term AS (
  SELECT term_id
    FROM dune.landsraad_decree_term
    ORDER BY term_id DESC
    LIMIT 1
),
configured AS (
  SELECT goal_scale, min_goal
    FROM dune.landsraad_goal_tuning
   WHERE id = TRUE
),
applied AS (
  INSERT INTO dune.landsraad_goal_tuning_applied (
    task_id,
    term_id,
    original_goal_amount,
    applied_goal_amount,
    goal_scale,
    min_goal,
    applied_at
  )
  SELECT t.id,
         t.term_id,
         t.goal_amount,
         GREATEST(c.min_goal, CEIL(t.goal_amount * c.goal_scale)::integer),
         c.goal_scale,
         c.min_goal,
         now()
    FROM dune.landsraad_tasks t
    JOIN current_term ct ON ct.term_id = t.term_id
    CROSS JOIN configured c
  ON CONFLICT (task_id)
  DO UPDATE SET applied_goal_amount = GREATEST(
                  EXCLUDED.min_goal,
                  CEIL(dune.landsraad_goal_tuning_applied.original_goal_amount * EXCLUDED.goal_scale)::integer
                ),
                goal_scale = EXCLUDED.goal_scale,
                min_goal = EXCLUDED.min_goal,
                applied_at = now()
  RETURNING task_id, applied_goal_amount
),
updated AS (
  UPDATE dune.landsraad_tasks t
     SET goal_amount = a.applied_goal_amount
    FROM applied a
   WHERE t.id = a.task_id
     AND t.completed = FALSE
     AND t.goal_amount <> a.applied_goal_amount
  RETURNING t.id, t.board_index, t.house_name, t.goal_amount
)
SELECT count(*) AS tasks_updated FROM updated;

WITH eligible AS (
  SELECT t.id AS task_id,
         c.faction_id,
         c.amount,
         row_number() OVER (PARTITION BY t.id ORDER BY c.amount DESC, c.faction_id) AS winner_rank
    FROM dune.landsraad_tasks t
    JOIN dune.landsraad_task_faction_contributions c ON c.task_id = t.id
   WHERE t.term_id = (SELECT term_id FROM dune.landsraad_decree_term ORDER BY term_id DESC LIMIT 1)
     AND t.completed = FALSE
     AND c.amount >= t.goal_amount
),
newly_completed AS (
  UPDATE dune.landsraad_tasks t
     SET completed = TRUE,
         winning_faction_id = e.faction_id,
         completion_time = now()
    FROM eligible e
   WHERE t.id = e.task_id
     AND e.winner_rank = 1
  RETURNING t.id, t.board_index, t.house_name, t.winning_faction_id, t.goal_amount
)
SELECT count(*) AS newly_completed_from_existing_progress FROM newly_completed;

\echo current_term_after
SELECT t.id, t.board_index, t.house_name, t.completed, t.winning_faction_id, t.goal_amount
  FROM dune.landsraad_tasks t
 WHERE t.term_id = (SELECT term_id FROM dune.landsraad_decree_term ORDER BY term_id DESC LIMIT 1)
 ORDER BY t.board_index;

COMMIT;
SQL
