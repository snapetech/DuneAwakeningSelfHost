#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import shlex
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = "dune_sb_1_4_0_0"

TRIAL_PREFIXES = {
    "1": ("First Trial", "DA_MQ_FindTheFremen.FirstTest"),
    "2": ("Second Trial", "DA_MQ_FindTheFremen.SecondTest"),
    "3": ("Third Trial", "DA_MQ_FindTheFremen.ThirdTest"),
    "4": ("Fourth Trial", "DA_MQ_FindTheFremen.FourthTest"),
    "5": ("Fifth Trial", "DA_MQ_FindTheFremen.FifthTest"),
    "6": ("Sixth Trial", "DA_MQ_FindTheFremen.SixthTest"),
    "7": ("Seventh Trial", "DA_MQ_FindTheFremen.SeventhTest"),
    "8": ("The Sietch", "DA_MQ_FindTheFremen.TheSietch"),
}


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def sql_array(values):
    return "array[" + ",".join(sql_literal(value) for value in values) + "]"


def compose_base(env_file, compose_cmd):
    cmd = shlex.split(compose_cmd)
    if env_file:
        cmd.extend(["--env-file", str(env_file)])
    return cmd


def psql(sql, *, env_file, compose_cmd, database, tuples_only=False):
    cmd = compose_base(env_file, compose_cmd)
    cmd.extend(
        [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "dune",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-P",
            "pager=off",
        ]
    )
    if tuples_only:
        cmd.extend(["-At"])
    proc = subprocess.run(
        cmd,
        input=sql,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "psql failed:\n"
            + proc.stderr.strip()
            + ("\n" + proc.stdout.strip() if proc.stdout.strip() else "")
        )
    return proc.stdout


def parse_json_scalar(output, default):
    text = output.strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"could not parse psql JSON output: {text}") from exc


def resolve_player(args):
    if args.fls_id:
        query = f"""
select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb)
from (
  select player_id, character_name, fls_id
  from dune.get_player_infos_for_fls_ids({sql_array([args.fls_id])})
) t;
"""
    else:
        query = f"""
select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb)
from (
  select player_id, character_name, fls_id
  from dune.get_player_infos_for_character_names({sql_array([args.character])})
) t;
"""
    rows = parse_json_scalar(
        psql(
            query,
            env_file=args.env_file,
            compose_cmd=args.compose,
            database=args.database,
            tuples_only=True,
        ),
        [],
    )
    if not rows:
        target = args.fls_id if args.fls_id else args.character
        raise SystemExit(f"no player found for {target!r}")
    if len(rows) > 1:
        raise SystemExit(f"ambiguous player lookup returned {len(rows)} rows: {rows}")
    row = rows[0]
    if not row.get("fls_id"):
        raise SystemExit(f"player lookup did not return an FLS id: {row}")
    return row


def selected_trials(value):
    if value == "all":
        return list(TRIAL_PREFIXES)
    trials = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if part not in TRIAL_PREFIXES:
            raise SystemExit(f"unknown trial {part!r}; use 1-8 or all")
        trials.append(part)
    if not trials:
        raise SystemExit("--trial must select at least one trial")
    return trials


def discover_nodes(args, trials):
    values = ", ".join(
        f"({trial}, {sql_literal(TRIAL_PREFIXES[trial][1])})" for trial in trials
    )
    query = f"""
with prefixes(trial, prefix) as (values {values})
select coalesce(jsonb_agg(to_jsonb(t) order by trial, story_node_id), '[]'::jsonb)
from (
  select p.trial, j.story_node_id
  from prefixes p
  join dune.journey_story_node j
    on j.story_node_id = p.prefix
    or j.story_node_id like p.prefix || '.%'
  group by p.trial, j.story_node_id
) t;
"""
    rows = parse_json_scalar(
        psql(
            query,
            env_file=args.env_file,
            compose_cmd=args.compose,
            database=args.database,
            tuples_only=True,
        ),
        [],
    )
    found_trials = {str(row["trial"]) for row in rows}
    missing = [trial for trial in trials if trial not in found_trials]
    if missing:
        names = ", ".join(f"{trial}:{TRIAL_PREFIXES[trial][1]}" for trial in missing)
        raise SystemExit(f"no journey rows found for selected trial(s): {names}")
    return rows


def player_status(args, fls_id):
    query = f"""
select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb)
from (
  select character_name, online_status, reconnect_grace_period_end,
         logoff_persistence_end_time, dune.is_player_offline({sql_literal(fls_id)}) as offline
  from dune.player_state
  where player_controller_id = (
    select player_id
    from dune.get_player_infos_for_fls_ids({sql_array([fls_id])})
    limit 1
  )
) t;
"""
    rows = parse_json_scalar(
        psql(
            query,
            env_file=args.env_file,
            compose_cmd=args.compose,
            database=args.database,
            tuples_only=True,
        ),
        [],
    )
    return rows[0] if rows else {"offline": None}


def completion_summary(args, fls_id, node_ids):
    query = f"""
with target as (
  select id as account_id
  from dune.accounts
  where "user" = {sql_literal(fls_id)}
), selected(story_node_id) as (
  select unnest({sql_array(node_ids)}::text[])
)
select coalesce(jsonb_agg(to_jsonb(t) order by story_node_id), '[]'::jsonb)
from (
  select s.story_node_id,
         coalesce(j.complete_condition_state, 'null'::jsonb) as complete_condition_state,
         coalesce(j.reveal_condition_state, 'null'::jsonb) as reveal_condition_state
  from selected s
  cross join target
  left join dune.journey_story_node j
    on j.account_id = target.account_id
   and j.story_node_id = s.story_node_id
) t;
"""
    return parse_json_scalar(
        psql(
            query,
            env_file=args.env_file,
            compose_cmd=args.compose,
            database=args.database,
            tuples_only=True,
        ),
        [],
    )


def count_completed(rows):
    return sum(1 for row in rows if row.get("complete_condition_state") is True)


def print_plan(player, trials, nodes, status, before):
    print(f"player: {player['character_name']} ({player['fls_id']})")
    print(
        "status: "
        + str(status.get("online_status", "unknown"))
        + f" offline={status.get('offline')}"
    )
    print("trials:")
    for trial in trials:
        name, prefix = TRIAL_PREFIXES[trial]
        count = sum(1 for row in nodes if str(row["trial"]) == trial)
        print(f"  {trial}: {name} ({count} nodes) {prefix}")
    print(f"selected nodes: {len(nodes)}")
    print(f"currently complete in selection: {count_completed(before)}/{len(before)}")


def complete_nodes(args, fls_id, node_ids):
    query = f"""
select dune.complete_journey_story_nodes_for_player(
  {sql_literal(fls_id)},
  {sql_array(node_ids)}::text[]
);
"""
    psql(
        query,
        env_file=args.env_file,
        compose_cmd=args.compose,
        database=args.database,
        tuples_only=False,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Grant Find the Fremen / Trials of Aql journey completion nodes for an offline player."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--fls-id", help="Player FLS id, for example 6FF6498F4074E3DE.")
    target.add_argument("--character", help="Exact character name to look up.")
    parser.add_argument("--trial", default="all", help="Trial number 1-8, comma list like 1,2,8, or all. Default: all.")
    parser.add_argument("--env-file", type=pathlib.Path, default=ROOT / ".env")
    parser.add_argument("--compose", default=os.environ.get("COMPOSE", "docker compose"))
    parser.add_argument("--database", default=os.environ.get("DUNE_DATABASE", DEFAULT_DATABASE))
    parser.add_argument("--execute", action="store_true", help="Apply the completion. Without this, only prints a dry-run plan.")
    parser.add_argument("--list", action="store_true", help="Print the selected node ids.")
    args = parser.parse_args(argv)

    trials = selected_trials(args.trial)
    player = resolve_player(args)
    nodes = discover_nodes(args, trials)
    node_ids = [row["story_node_id"] for row in nodes]
    status = player_status(args, player["fls_id"])
    before = completion_summary(args, player["fls_id"], node_ids)

    print_plan(player, trials, nodes, status, before)
    if args.list:
        for row in nodes:
            trial = str(row["trial"])
            print(f"{trial}\t{row['story_node_id']}")

    if not args.execute:
        print("dry-run only; rerun with --execute to apply.")
        return 0

    if status.get("offline") is not True:
        raise SystemExit("refusing to execute: player is not offline")

    complete_nodes(args, player["fls_id"], node_ids)
    after = completion_summary(args, player["fls_id"], node_ids)
    print(f"after complete in selection: {count_completed(after)}/{len(after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
