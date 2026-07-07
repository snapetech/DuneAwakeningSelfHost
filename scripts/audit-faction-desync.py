#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import socket
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]


def read_env_file(path):
    values = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def compose_files(env_file):
    script = ROOT / "scripts" / "compose-files.sh"
    if script.exists() and os.access(script, os.X_OK):
        result = subprocess.run(
            [str(script), env_file],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[-1]
    return os.environ.get("COMPOSE_FILES", "compose.yaml:compose.allmaps.yaml")


def build_compose_cmd(env_file):
    cmd = [os.environ.get("CONTAINER_RUNTIME", "docker"), "compose"]
    for file_name in compose_files(env_file).split(":"):
        if file_name:
            cmd.extend(["-f", file_name])
    cmd.extend(["--env-file", env_file])
    return cmd


def psql(args, sql, timeout=30):
    cmd = args.compose + [
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "dune",
        "-d",
        args.database,
        "-v",
        "ON_ERROR_STOP=1",
        "-P",
        "pager=off",
        "-At",
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        input=sql,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "psql failed")
    return result.stdout


def discover_candidates(args):
    sql = f"""
with controller_reps as (
  select
    ps.id as player_state_row_id,
    ps.account_id,
    ps.character_name,
    ps.player_controller_id,
    ps.online_status::text as online_status,
    controller.map as controller_map,
    controller.partition_id as controller_partition_id,
    controller.dimension_index as controller_dimension_index,
    coalesce(dune.get_player_faction(ps.player_controller_id, {args.neutral_faction_id}::smallint), {args.neutral_faction_id})::int as current_faction_id,
    max((entry->>'ReputationAmount')::int) filter (where entry #>> '{{Faction,Name}}' = 'Atreides') as controller_atreides_rep,
    max((entry->>'ReputationAmount')::int) filter (where entry #>> '{{Faction,Name}}' = 'Harkonnen') as controller_harkonnen_rep
  from dune.player_state ps
  join dune.actors controller on controller.id = ps.player_controller_id
  left join lateral jsonb_array_elements(
    coalesce(controller.properties #> '{{FactionPlayerComponent,m_FactionDataArray}}', '[]'::jsonb)
  ) entry on true
  where ps.player_controller_id is not null
  group by ps.id, ps.account_id, ps.character_name, ps.player_controller_id, ps.online_status,
           controller.map, controller.partition_id, controller.dimension_index
),
normalized_reps as (
  select
    actor_id,
    max(reputation_amount) filter (where faction_id = 1) as normalized_atreides_rep,
    max(reputation_amount) filter (where faction_id = 2) as normalized_harkonnen_rep
  from dune.player_faction_reputation
  group by actor_id
),
inferred as (
  select
    c.*,
    n.normalized_atreides_rep,
    n.normalized_harkonnen_rep,
    case
      when coalesce(c.controller_atreides_rep, 0) > 0
       and coalesce(c.controller_atreides_rep, 0) >= {args.min_reputation}
       and coalesce(c.controller_atreides_rep, -1) > coalesce(c.controller_harkonnen_rep, -1)
        then 1
      when coalesce(c.controller_harkonnen_rep, 0) > 0
       and coalesce(c.controller_harkonnen_rep, 0) >= {args.min_reputation}
       and coalesce(c.controller_harkonnen_rep, -1) > coalesce(c.controller_atreides_rep, -1)
        then 2
      else null
    end as inferred_faction_id
  from controller_reps c
  left join normalized_reps n on n.actor_id = c.player_controller_id
),
guild_info as (
  select
    gm.player_id,
    gm.guild_id,
    gm.role_id,
    g.guild_name,
    g.guild_faction,
    dune.is_player_guild_admin(gm.player_id, gm.guild_id) as guild_admin,
    (
      select count(*)
      from dune.guild_members member
      left join dune.player_faction member_faction on member_faction.actor_id = member.player_id
      where member.guild_id = gm.guild_id
        and coalesce(member_faction.faction_id, {args.neutral_faction_id}) not in ({args.neutral_faction_id}, g.guild_faction)
    ) as incompatible_member_count
  from dune.guild_members gm
  join dune.guilds g on g.guild_id = gm.guild_id
)
select coalesce(jsonb_agg(to_jsonb(result) order by character_name), '[]'::jsonb)::text
from (
  select
    i.*,
    f.name as inferred_faction_name,
    coalesce(g.guild_id, null) as guild_id,
    g.guild_name,
    g.guild_faction,
    g.role_id as guild_role_id,
    coalesce(g.guild_admin, false) as guild_admin,
    coalesce(g.incompatible_member_count, 0) as incompatible_member_count,
    (
      g.guild_id is not null
      and g.guild_faction is not null
      and g.guild_faction <> {args.neutral_faction_id}
      and g.guild_faction <> i.inferred_faction_id
    ) as guild_faction_conflict,
    (
      i.inferred_faction_id is not null
      and i.current_faction_id <> i.inferred_faction_id
    ) as needs_faction_repair,
    (
      i.inferred_faction_id = 1
      and i.controller_atreides_rep is not null
      and coalesce(i.normalized_atreides_rep, -2147483648) <> i.controller_atreides_rep
    ) or (
      i.inferred_faction_id = 2
      and i.controller_harkonnen_rep is not null
      and coalesce(i.normalized_harkonnen_rep, -2147483648) <> i.controller_harkonnen_rep
    ) or (
      i.controller_atreides_rep is not null
      and coalesce(i.normalized_atreides_rep, -2147483648) <> i.controller_atreides_rep
    ) or (
      i.controller_harkonnen_rep is not null
      and coalesce(i.normalized_harkonnen_rep, -2147483648) <> i.controller_harkonnen_rep
    ) as needs_reputation_repair,
    not (
      g.guild_id is not null
      and g.guild_faction is not null
      and g.guild_faction <> {args.neutral_faction_id}
      and g.guild_faction <> i.inferred_faction_id
    ) as safe_to_repair,
    case
      when g.guild_id is not null
       and g.guild_faction is not null
       and g.guild_faction <> {args.neutral_faction_id}
       and g.guild_faction <> i.inferred_faction_id
        then 'guild_faction_conflict'
      else ''
    end as unsafe_reason
  from inferred i
  left join dune.factions f on f.id = i.inferred_faction_id
  left join guild_info g on g.player_id = i.player_controller_id
  where i.inferred_faction_id is not null
    and (
      i.current_faction_id <> i.inferred_faction_id
      or coalesce(i.normalized_atreides_rep, -2147483648) <> coalesce(i.controller_atreides_rep, -2147483648)
      or coalesce(i.normalized_harkonnen_rep, -2147483648) <> coalesce(i.controller_harkonnen_rep, -2147483648)
    )
) result;
"""
    text = psql(args, sql, timeout=args.timeout).strip()
    return json.loads(text.splitlines()[-1] if text else "[]")


def repair_candidate(args, candidate):
    player_id = int(candidate["player_controller_id"])
    inferred = int(candidate["inferred_faction_id"])
    before_guild_faction = candidate.get("guild_faction")
    guild_id = candidate.get("guild_id")
    guild_admin = bool(candidate.get("guild_admin"))
    incompatible_members = int(candidate.get("incompatible_member_count") or 0)
    repledge_guild = (
        guild_id is not None
        and guild_admin
        and before_guild_faction == inferred
        and incompatible_members == 0
    )
    if not candidate.get("safe_to_repair"):
        return {
            "ok": False,
            "skipped": True,
            "playerId": player_id,
            "reason": candidate.get("unsafe_reason") or "not safe to repair",
        }
    statements = [
        "BEGIN;",
        """
CREATE TABLE IF NOT EXISTS dune.faction_desync_repair_audit (
  id bigserial PRIMARY KEY,
  repaired_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  player_id bigint NOT NULL,
  account_id bigint,
  character_name text,
  action text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);
""",
        f"""
INSERT INTO dune.faction_desync_repair_audit(player_id, account_id, character_name, action, details)
VALUES (
  {player_id},
  {int(candidate["account_id"])},
  {sql_literal(candidate.get("character_name") or "")},
  'before',
  {sql_literal(json.dumps(candidate, sort_keys=True))}::jsonb
);
""",
        f"""
SELECT dune.change_player_faction(
  {player_id}::bigint,
  {inferred}::smallint,
  {args.neutral_faction_id}::smallint,
  timezone('utc', now())::timestamp
);
""",
    ]
    if candidate.get("controller_atreides_rep") is not None:
        statements.append(
            f"SELECT dune.set_player_faction_reputation({player_id}::bigint, 1::smallint, {int(candidate['controller_atreides_rep'])}::integer);"
        )
    if candidate.get("controller_harkonnen_rep") is not None:
        statements.append(
            f"SELECT dune.set_player_faction_reputation({player_id}::bigint, 2::smallint, {int(candidate['controller_harkonnen_rep'])}::integer);"
        )
    if repledge_guild:
        statements.append(
            f"""
DO $$
BEGIN
  IF (
    SELECT guild_faction
    FROM dune.guilds
    WHERE guild_id = {int(guild_id)}::bigint
  ) IS DISTINCT FROM {inferred}::smallint THEN
    PERFORM dune.pledge_guild_allegiance(
      {int(guild_id)}::bigint,
      {player_id}::bigint,
      {args.neutral_faction_id}::smallint
    );
  END IF;
END $$;
"""
        )
    statements.extend([
        f"""
INSERT INTO dune.faction_desync_repair_audit(player_id, account_id, character_name, action, details)
VALUES (
  {player_id},
  {int(candidate["account_id"])},
  {sql_literal(candidate.get("character_name") or "")},
  'after',
  jsonb_build_object(
    'repledge_guild', {str(repledge_guild).lower()},
    'faction_id', dune.get_player_faction({player_id}::bigint, {args.neutral_faction_id}::smallint),
    'reputation', to_jsonb(dune.get_player_current_faction_reputation({player_id}::bigint)),
    'guild', (
      select to_jsonb(g)
      from dune.guilds g
      where g.guild_id = {int(guild_id) if guild_id is not None else -1}
    )
  )
);
""",
        "COMMIT;",
        f"""
select jsonb_build_object(
  'playerId', {player_id},
  'factionId', dune.get_player_faction({player_id}::bigint, {args.neutral_faction_id}::smallint),
  'reputation', to_jsonb(dune.get_player_current_faction_reputation({player_id}::bigint)),
  'repledgeGuild', {str(repledge_guild).lower()}
)::text;
""",
    ])
    text = psql(args, "\n".join(statements), timeout=args.timeout).strip()
    return json.loads(text.splitlines()[-1] if text else "{}")


def main():
    parser = argparse.ArgumentParser(description="Audit and repair faction rows desynced from controller faction JSON.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--database", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--neutral-faction-id", type=int, default=3)
    parser.add_argument("--min-reputation", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--only-player-id", type=int, default=0)
    parser.add_argument("--required-host", default="")
    args = parser.parse_args()

    file_env = read_env_file(ROOT / args.env_file)
    args.database = args.database or os.environ.get("DUNE_GAME_DB_NAME") or file_env.get("DUNE_GAME_DB_NAME") or os.environ.get("DUNE_DATABASE") or file_env.get("DUNE_DATABASE") or "dune_sb_1_4_0_0"
    args.compose = build_compose_cmd(args.env_file)

    if args.execute and args.confirm != "REPAIR FACTION DESYNC":
        raise SystemExit("--execute requires --confirm 'REPAIR FACTION DESYNC'")
    if args.execute and args.required_host:
        actual_host = socket.gethostname().split(".", 1)[0]
        if actual_host != args.required_host:
            raise SystemExit(f"refusing execute on host {actual_host!r}; required {args.required_host!r}")

    candidates = discover_candidates(args)
    if args.only_player_id:
        candidates = [row for row in candidates if int(row["player_controller_id"]) == args.only_player_id]

    result = {
        "database": args.database,
        "execute": args.execute,
        "count": len(candidates),
        "candidates": candidates,
        "repairs": [],
    }
    if args.execute:
        for candidate in candidates:
            result["repairs"].append(repair_candidate(args, candidate))

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
