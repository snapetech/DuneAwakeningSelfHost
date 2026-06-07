#!/usr/bin/env python3
import argparse
import importlib.util
import json
import pathlib
import socket
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
ADMIN_CHAT_PATH = ROOT / "scripts" / "admin-chat-commands.py"
SPEC = importlib.util.spec_from_file_location("admin_chat_commands", ADMIN_CHAT_PATH)
admin_chat_commands = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(admin_chat_commands)


def print_json(value):
    print(json.dumps(value, default=str, separators=(",", ":")))


def fetch_one(cur):
    row = cur.fetchone()
    return dict(row) if row else None


def restore_totem_permission(cur, totem_id, player_id, actor_name="##Totem_Placeable", owner_rank=1):
    cur.execute(
        """
        insert into dune.permission_actor(actor_id, actor_name, actor_type, access_level, is_child)
        values (%s, %s, 3, 3, false)
        on conflict (actor_id) do update set
          actor_name=excluded.actor_name,
          actor_type=excluded.actor_type,
          access_level=excluded.access_level,
          is_child=excluded.is_child
        """,
        (totem_id, actor_name),
    )
    permission_actor_rows = cur.rowcount
    cur.execute(
        """
        insert into dune.permission_actor_rank(permission_actor_id, player_id, rank)
        values (%s, %s, %s)
        on conflict (permission_actor_id, player_id) do update set rank=excluded.rank
        """,
        (totem_id, player_id, owner_rank),
    )
    permission_rank_rows = cur.rowcount
    return {
        "permissionActorRows": permission_actor_rows,
        "permissionRankRows": permission_rank_rows,
    }


def staged_backup_health(cur, backup_id, totem_id=None):
    cur.execute(
        """
        with linked as (
          select actor_id
          from dune.base_backup_linked_actors
          where id=%s
        )
        select
          (select count(*) from linked)::integer as linked_actor_count,
          (select count(*) from linked l join dune.actors a on a.id=l.actor_id)::integer as linked_actors_present,
          (select count(*) from linked l join dune.actor_state ast on ast.actor_id=l.actor_id)::integer as linked_actor_state_rows,
          (select count(*) from linked l join dune.building_instances bi on bi.building_id=l.actor_id)::integer as linked_building_instance_rows,
          (select count(*) from dune.permission_actor where actor_id=%s)::integer as totem_permission_actor_rows,
          (select count(*) from dune.permission_actor_rank where permission_actor_id=%s)::integer as totem_permission_rank_rows,
          (select count(*) from dune.base_backups where id=%s)::integer as base_backup_rows
        """,
        (backup_id, totem_id, totem_id, backup_id),
    )
    return fetch_one(cur)


def backup_summary(cur, backup_id):
    cur.execute(
        """
        with d as (
          select * from dune.base_backup_get_data(%s)
        ),
        points as (
          select
            ((s.transform).location).x::float8 as x,
            ((s.transform).location).y::float8 as y,
            ((s.transform).location).z::float8 as z
          from dune.base_backup_get_actors_to_spawn(%s) s
          union all
          select
            bp.transform[array_lower(bp.transform, 1)]::float8 as x,
            bp.transform[array_lower(bp.transform, 1) + 1]::float8 as y,
            bp.transform[array_lower(bp.transform, 1) + 2]::float8 as z
          from d, unnest(d.building_pieces) bp
        )
        select
          bb.id as backup_id,
          bb.player_id,
          (d.totem).totem_actor_id as totem_id,
          (d.totem).totem_building_type as totem_building_type,
          (d.totem).totem_map as source_map,
          (d.totem).landclaim_original_global_location as source_landclaim_location,
          coalesce(array_length((d.totem).landclaim_grid, 1), 0)::integer as landclaim_segment_count,
          coalesce(array_length(d.building_pieces, 1), 0)::integer as building_piece_count,
          coalesce(array_length(d.placeables, 1), 0)::integer as placeable_count,
          (select count(*) from dune.base_backup_get_actors_to_spawn(%s))::integer as actor_spawn_count,
          (select count(*) from dune.base_backup_linked_actors where id=%s)::integer as linked_actor_count,
          ((a.transform).location).x::float8 as source_anchor_x,
          ((a.transform).location).y::float8 as source_anchor_y,
          ((a.transform).location).z::float8 as source_anchor_z,
          min(points.x) as min_x,
          max(points.x) as max_x,
          min(points.y) as min_y,
          max(points.y) as max_y,
          min(points.z) as min_z,
          max(points.z) as max_z
        from d
        join dune.base_backups bb on bb.id=%s
        join dune.actors a on a.id=(d.totem).totem_actor_id
        cross join points
        group by bb.id, bb.player_id, d.totem, d.building_pieces, d.placeables, a.transform
        """,
        (backup_id, backup_id, backup_id, backup_id, backup_id),
    )
    row = fetch_one(cur)
    if not row:
        raise ValueError(f"backup {backup_id} not found")
    return row


def player_location(cur, player_id):
    cur.execute(
        """
        select
          a.id,
          a.map,
          a.partition_id,
          a.dimension_index,
          ((a.transform).location).x::float8 as x,
          ((a.transform).location).y::float8 as y,
          ((a.transform).location).z::float8 as z
        from dune.actors a
        where a.id=%s
        """,
        (player_id,),
    )
    row = fetch_one(cur)
    if not row:
        raise ValueError(f"player/controller actor {player_id} not found")
    return row


def apply_restore_transform(cur, backup_id, target, actor_name="##Totem_Placeable", owner_rank=1):
    summary = backup_summary(cur, backup_id)
    target_x = float(target["x"])
    target_y = float(target["y"])
    target_z = float(target["z"])
    dx = target_x - float(summary["source_anchor_x"])
    dy = target_y - float(summary["source_anchor_y"])
    dz = target_z - float(summary["source_anchor_z"])
    partition_id = int(target["partition_id"])
    dimension_index = int(target["dimension_index"])
    target_map = target["map"]
    player_id = int(summary["player_id"])
    totem_id = int(summary["totem_id"])

    cur.execute(
        """
        update dune.actors a
        set
          map=%s,
          partition_id=%s,
          dimension_index=%s,
          transform=row(
            row(
              ((a.transform).location).x + %s::float8,
              ((a.transform).location).y + %s::float8,
              ((a.transform).location).z + %s::float8
            )::dune.vector,
            (a.transform).rotation
          )::dune.transform
        where a.id in (
          select actor_id from dune.base_backup_linked_actors where id=%s
        )
        """,
        (target_map, partition_id, dimension_index, dx, dy, dz, backup_id),
    )
    actor_rows = cur.rowcount

    cur.execute(
        """
        update dune.building_instances bi
        set
          transform[array_lower(bi.transform, 1)] = bi.transform[array_lower(bi.transform, 1)] + %s::real,
          transform[array_lower(bi.transform, 1) + 1] = bi.transform[array_lower(bi.transform, 1) + 1] + %s::real,
          transform[array_lower(bi.transform, 1) + 2] = bi.transform[array_lower(bi.transform, 1) + 2] + %s::real
        where bi.building_id in (
          select actor_id from dune.base_backup_linked_actors where id=%s
        )
        """,
        (dx, dy, dz, backup_id),
    )
    building_instance_rows = cur.rowcount

    cur.execute(
        """
        update dune.totems t
        set
          landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1)] =
            t.landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1)] + %s::real,
          landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1) + 1] =
            t.landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1) + 1] + %s::real,
          landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1) + 2] =
            t.landclaim_original_global_location[array_lower(t.landclaim_original_global_location, 1) + 2] + %s::real
        where t.id=%s
        """,
        (dx, dy, dz, totem_id),
    )
    totem_rows = cur.rowcount

    cur.execute("select dune.base_backup_finish_placing(%s)", (backup_id,))
    permission_counts = restore_totem_permission(cur, totem_id, player_id, actor_name=actor_name, owner_rank=owner_rank)

    return {
        "backupId": backup_id,
        "playerId": player_id,
        "totemId": totem_id,
        "delta": {"x": dx, "y": dy, "z": dz},
        "target": target,
        "source": {
            "x": summary["source_anchor_x"],
            "y": summary["source_anchor_y"],
            "z": summary["source_anchor_z"],
            "map": summary["source_map"],
        },
        "counts": {
            "actorsUpdated": actor_rows,
            "buildingInstancesUpdated": building_instance_rows,
            "totemsUpdated": totem_rows,
            "buildingPieces": int(summary["building_piece_count"] or 0),
            "placeables": int(summary["placeable_count"] or 0),
            "linkedActors": int(summary["linked_actor_count"] or 0),
            "actorSpawns": int(summary["actor_spawn_count"] or 0),
            "landclaimSegments": int(summary["landclaim_segment_count"] or 0),
            **permission_counts,
        },
    }


def run_list_totems(args):
    conn = admin_chat_commands.connect_db()
    try:
        rows = admin_chat_commands.dd1_totems_for_player(conn, args.player_id)
        if args.totem_id is not None:
            rows = [row for row in rows if int(row["totem_id"]) == int(args.totem_id)]
        print_json({
            "ok": True,
            "mode": "list-totems",
            "playerId": args.player_id,
            "totems": [dict(row) for row in rows],
        })
    finally:
        conn.close()


def run_list_backups(args):
    conn = admin_chat_commands.connect_db()
    try:
        with conn.cursor(cursor_factory=admin_chat_commands.psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                select *
                from dune.base_backup_get_available_backups(%s)
                order by id desc
                """,
                (args.player_id,),
            )
            backups = [dict(row) for row in cur.fetchall()]
        print_json({
            "ok": True,
            "mode": "list-backups",
            "playerId": args.player_id,
            "backups": backups,
        })
    finally:
        conn.close()


def run_inspect_backup(args):
    conn = admin_chat_commands.connect_db()
    try:
        with conn.cursor(cursor_factory=admin_chat_commands.psycopg2.extras.RealDictCursor) as cur:
            summary = backup_summary(cur, args.backup_id)
            health = staged_backup_health(cur, args.backup_id, int(summary["totem_id"]))
        print_json({
            "ok": True,
            "mode": "inspect-backup",
            "summary": summary,
            "health": health,
        })
    finally:
        conn.close()


def run_finish_staged_backup(args):
    if args.commit:
        if socket.gethostname() != "kspls0":
            raise SystemExit("commit refused: host is not kspls0")
        if args.confirm != "FINISH DD1 BRT BACKUP":
            raise SystemExit("commit refused: pass --confirm 'FINISH DD1 BRT BACKUP'")
    conn = admin_chat_commands.connect_db()
    try:
        with conn.cursor(cursor_factory=admin_chat_commands.psycopg2.extras.RealDictCursor) as cur:
            cur.execute("begin")
            summary = backup_summary(cur, args.backup_id)
            totem_id = int(summary["totem_id"])
            player_id = int(args.player_id if args.player_id is not None else summary["player_id"])
            before = staged_backup_health(cur, args.backup_id, totem_id)
            cur.execute("select dune.base_backup_finish_placing(%s)", (args.backup_id,))
            permission_counts = restore_totem_permission(
                cur,
                totem_id,
                player_id,
                actor_name=args.actor_name,
                owner_rank=args.owner_rank,
            )
            after = staged_backup_health(cur, args.backup_id, totem_id)
            if args.commit:
                cur.execute("commit")
                committed = True
                rolled_back = False
            else:
                cur.execute("rollback")
                committed = False
                rolled_back = True
            print_json({
                "ok": True,
                "mode": "finish-staged-backup",
                "backupId": args.backup_id,
                "playerId": player_id,
                "totemId": totem_id,
                "summary": summary,
                "before": before,
                "after": after,
                "counts": permission_counts,
                "committed": committed,
                "rolledBack": rolled_back,
            })
    finally:
        conn.close()


def run_simulate_from_totem(args):
    conn = admin_chat_commands.connect_db()
    try:
        with conn.cursor(cursor_factory=admin_chat_commands.psycopg2.extras.RealDictCursor) as cur:
            cur.execute("begin")
            cur.execute(
                "select dune.base_backup_save_from_totem(%s, %s) as backup_id",
                (args.player_id, args.totem_id),
            )
            backup_id = int(cur.fetchone()["backup_id"])
            player = player_location(cur, args.player_id)
            target = {
                "map": args.map or player["map"],
                "partition_id": args.partition_id if args.partition_id is not None else int(player["partition_id"]),
                "dimension_index": args.dimension_index if args.dimension_index is not None else int(player["dimension_index"]),
                "x": float(args.target_x) if args.target_x is not None else float(player["x"]) + float(args.offset_x),
                "y": float(args.target_y) if args.target_y is not None else float(player["y"]) + float(args.offset_y),
                "z": float(args.target_z) if args.target_z is not None else float(player["z"]) + float(args.offset_z),
            }
            result = apply_restore_transform(cur, backup_id, target)
            cur.execute("rollback")
            result["ok"] = True
            result["rolledBack"] = True
            result["mode"] = "simulate-from-totem"
            print_json(result)
    finally:
        conn.close()


def run_restore_backup(args):
    if args.commit:
        if socket.gethostname() != "kspls0":
            raise SystemExit("commit refused: host is not kspls0")
        if args.confirm != "RESTORE DD1 BRT BACKUP":
            raise SystemExit("commit refused: pass --confirm 'RESTORE DD1 BRT BACKUP'")
    conn = admin_chat_commands.connect_db()
    try:
        with conn.cursor(cursor_factory=admin_chat_commands.psycopg2.extras.RealDictCursor) as cur:
            cur.execute("begin")
            player = player_location(cur, args.player_id) if args.player_id else None
            target = {
                "map": args.map or (player or {}).get("map") or "DeepDesert",
                "partition_id": args.partition_id if args.partition_id is not None else int((player or {}).get("partition_id") or 8),
                "dimension_index": args.dimension_index if args.dimension_index is not None else int((player or {}).get("dimension_index") or 0),
                "x": float(args.target_x),
                "y": float(args.target_y),
                "z": float(args.target_z),
            }
            result = apply_restore_transform(cur, args.backup_id, target)
            if args.commit:
                cur.execute("commit")
                result["committed"] = True
                result["rolledBack"] = False
            else:
                cur.execute("rollback")
                result["committed"] = False
                result["rolledBack"] = True
            result["ok"] = True
            result["mode"] = "restore-backup"
            print_json(result)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="DD1 BRT DB-emulation experiments. Defaults are rollback-only.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_totems = sub.add_parser("list-totems", help="List owned DD1 totems that the DB BRT path can see.")
    list_totems.add_argument("--player-id", type=int, required=True)
    list_totems.add_argument("--totem-id", type=int)
    list_totems.set_defaults(func=run_list_totems)

    list_backups = sub.add_parser("list-backups", help="List BRT backups available to a player.")
    list_backups.add_argument("--player-id", type=int, required=True)
    list_backups.set_defaults(func=run_list_backups)

    inspect = sub.add_parser("inspect-backup", help="Inspect a staged BRT backup without mutating it.")
    inspect.add_argument("--backup-id", type=int, required=True)
    inspect.set_defaults(func=run_inspect_backup)

    sim = sub.add_parser("simulate-from-totem", help="Create a backup, transform/finish it, and rollback the whole transaction.")
    sim.add_argument("--player-id", type=int, required=True)
    sim.add_argument("--totem-id", type=int, required=True)
    sim.add_argument("--target-x", type=float)
    sim.add_argument("--target-y", type=float)
    sim.add_argument("--target-z", type=float)
    sim.add_argument("--offset-x", type=float, default=1000)
    sim.add_argument("--offset-y", type=float, default=0)
    sim.add_argument("--offset-z", type=float, default=0)
    sim.add_argument("--map", default="")
    sim.add_argument("--partition-id", type=int)
    sim.add_argument("--dimension-index", type=int)
    sim.set_defaults(func=run_simulate_from_totem)

    restore = sub.add_parser("restore-backup", help="Transform and finish an existing backup. Rollback unless --commit is passed.")
    restore.add_argument("--backup-id", type=int, required=True)
    restore.add_argument("--player-id", type=int, help="Optional target player/controller for default map/partition/dimension.")
    restore.add_argument("--target-x", type=float, required=True)
    restore.add_argument("--target-y", type=float, required=True)
    restore.add_argument("--target-z", type=float, required=True)
    restore.add_argument("--map", default="")
    restore.add_argument("--partition-id", type=int)
    restore.add_argument("--dimension-index", type=int)
    restore.add_argument("--commit", action="store_true")
    restore.add_argument("--confirm", default="")
    restore.set_defaults(func=run_restore_backup)

    finish = sub.add_parser(
        "finish-staged-backup",
        help="Finish/delete a staged backup in its current position and restore totem permission. Rollback unless --commit is passed.",
    )
    finish.add_argument("--backup-id", type=int, required=True)
    finish.add_argument("--player-id", type=int, help="Override owner player/controller id for restored totem permission.")
    finish.add_argument("--actor-name", default="##Totem_Placeable")
    finish.add_argument("--owner-rank", type=int, default=1)
    finish.add_argument("--commit", action="store_true")
    finish.add_argument("--confirm", default="")
    finish.set_defaults(func=run_finish_staged_backup)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
