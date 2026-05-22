#!/usr/bin/env python3
import argparse
import csv
import json
import os
import pathlib
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "artificial-exchange-prices.csv"
DEFAULT_DB = "dune_sb_1_4_0_0"
CONFIRM = "GRANT ITEM"


def compose_cmd(env_file):
    return ["docker", "compose", "--env-file", env_file]


def run_psql(sql, env_file=".env", db=DEFAULT_DB, fieldsep="\t"):
    command = compose_cmd(env_file) + [
        "exec", "-T", "postgres", "psql", "-U", "dune", "-d", db,
        "-v", "ON_ERROR_STOP=1", "-At", "-F", fieldsep, "-c", sql,
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "psql failed")
    return [line.split(fieldsep) for line in result.stdout.splitlines() if line.strip()]


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def load_catalog(path=CATALOG):
    rows = []
    with pathlib.Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
    return rows


def normalize(value):
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def resolve_template(item, catalog_rows):
    needle = normalize(item)
    if not needle:
        raise ValueError("item/template is required")
    exact_template = [row for row in catalog_rows if normalize(row.get("template_id")) == needle]
    exact_name = [row for row in catalog_rows if normalize(row.get("display_name")) == needle]
    matches = exact_template or exact_name
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(f"{row.get('display_name')}={row.get('template_id')}" for row in matches[:10])
        raise ValueError(f"ambiguous item name '{item}': {names}")
    contains = [
        row for row in catalog_rows
        if needle in normalize(row.get("template_id")) or needle in normalize(row.get("display_name"))
    ]
    if len(contains) == 1:
        return contains[0]
    if contains:
        names = ", ".join(f"{row.get('display_name')}={row.get('template_id')}" for row in contains[:10])
        raise ValueError(f"ambiguous item name '{item}': {names}")
    return {"template_id": item, "display_name": item, "confidence": "unknown", "source": "manual"}


def resolve_player(args):
    clauses = []
    if args.account_id:
        clauses.append(f"ps.account_id={int(args.account_id)}")
    if args.character:
        clauses.append(f"ps.character_name ilike {sql_literal(args.character)}")
    if not clauses:
        raise ValueError("--account-id or --character is required")
    rows = run_psql(f"""
        select ps.account_id, ps.character_name, ps.online_status::text, ps.player_controller_id, ps.player_pawn_id
        from dune.player_state ps
        where {' or '.join(clauses)}
        order by ps.last_login_time desc nulls last
        limit 2;
    """, args.env_file, args.db)
    if not rows:
        raise ValueError("player not found")
    if len(rows) > 1 and args.character and not args.account_id:
        raise ValueError("character matched multiple players; use --account-id")
    row = rows[0]
    return {
        "accountId": int(row[0]),
        "characterName": row[1],
        "onlineStatus": row[2],
        "controllerId": int(row[3]),
        "pawnId": int(row[4]),
    }


def choose_inventory(args, player):
    if args.inventory_id:
        rows = run_psql(f"""
            select inv.id, inv.inventory_type, inv.max_item_count
            from dune.inventories inv
            where inv.id={int(args.inventory_id)}
            limit 1;
        """, args.env_file, args.db)
    else:
        inventory_type_clause = "" if args.inventory_type is None else f"and inv.inventory_type={int(args.inventory_type)}"
        rows = run_psql(f"""
            select inv.id, inv.inventory_type, inv.max_item_count
            from dune.inventories inv
            where inv.actor_id in ({player['pawnId']},{player['controllerId']}) {inventory_type_clause}
            order by
              case when inv.actor_id={player['pawnId']} then 0 else 1 end,
              case when inv.inventory_type=0 then 0 else 1 end,
              inv.inventory_type nulls last,
              inv.id
            limit 1;
        """, args.env_file, args.db)
    if not rows:
        raise ValueError("no target inventory found")
    row = rows[0]
    return {"inventoryId": int(row[0]), "inventoryType": row[1], "maxItemCount": None if row[2] == "" else int(row[2])}


def choose_slot(args, inventory):
    if args.position is not None:
        rows = run_psql(f"select {int(args.position)} where not exists (select 1 from dune.items where inventory_id={inventory['inventoryId']} and position_index={int(args.position)});", args.env_file, args.db)
    elif inventory["maxItemCount"] is not None and inventory["maxItemCount"] > 0:
        rows = run_psql(f"""
            select slot.position_index
            from generate_series(0, {inventory['maxItemCount']} - 1) as slot(position_index)
            where not exists (
              select 1 from dune.items i
              where i.inventory_id={inventory['inventoryId']} and i.position_index=slot.position_index
            )
            order by slot.position_index
            limit 1;
        """, args.env_file, args.db)
    else:
        rows = run_psql(f"select coalesce(max(position_index), -1) + 1 from dune.items where inventory_id={inventory['inventoryId']};", args.env_file, args.db)
    if not rows:
        raise ValueError("no free inventory slot found")
    return int(rows[0][0])


def grant(args, template_id, inventory_id, position):
    stats = sql_literal(args.stats)
    sql = f"""
    begin;
    with target as (
      select {int(inventory_id)}::bigint as inventory_id, {int(position)}::bigint as position_index
      where not exists (
        select 1 from dune.items
        where inventory_id={int(inventory_id)} and position_index={int(position)}
      )
    ),
    next_item as (
      select dune.advance_items_id_sequencer(1) as item_id from target
    ),
    saved as (
      select dune.save_item((
        next_item.item_id,
        target.inventory_id,
        {int(args.count)},
        target.position_index,
        {sql_literal(template_id)},
        true,
        {int(time.time())},
        {stats}::jsonb,
        {int(args.quality)},
        null
      )::dune.inventoryitem) as ok,
      next_item.item_id
      from next_item, target
    )
    select 'granted', i.id, i.inventory_id, i.stack_size, i.position_index, i.template_id
    from saved
    join dune.items i
      on i.id=saved.item_id
     and i.inventory_id={int(inventory_id)}
     and i.position_index={int(position)}
     and i.template_id={sql_literal(template_id)};
    commit;
    """
    rows = run_psql(sql, args.env_file, args.db)
    granted_rows = [row for row in rows if row and row[0] == "granted"]
    return granted_rows[-1][1:] if granted_rows else []


def build_parser():
    parser = argparse.ArgumentParser(description="Grant a resolved item stack to a player inventory.")
    parser.add_argument("item", help="Display name or exact template id, e.g. 'Complex Machinery' or T2MachineComponent.")
    parser.add_argument("count", type=int, help="Positive stack size to grant.")
    parser.add_argument("--character", help="Character name to target.")
    parser.add_argument("--account-id", type=int, help="Account id to target.")
    parser.add_argument("--inventory-id", type=int, help="Explicit inventory id.")
    parser.add_argument("--inventory-type", type=int, default=0, help="Inventory type to auto-resolve; default 0 carried inventory.")
    parser.add_argument("--position", type=int, help="Explicit free position index.")
    parser.add_argument("--quality", type=int, default=0)
    parser.add_argument("--stats", default="{}")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser


def main_with_argv(argv):
    args = build_parser().parse_args(argv)
    if args.count <= 0:
        raise SystemExit("count must be > 0")
    row = resolve_template(args.item, load_catalog())
    template_id = row["template_id"]
    player = resolve_player(args)
    inventory = choose_inventory(args, player)
    position = choose_slot(args, inventory)
    plan = {
        "ok": True,
        "dryRun": not args.execute,
        "player": player,
        "inventory": inventory,
        "positionIndex": position,
        "item": {
            "input": args.item,
            "templateId": template_id,
            "displayName": row.get("display_name") or template_id,
            "count": args.count,
            "confidence": row.get("confidence"),
            "source": row.get("source"),
        },
        "confirmRequired": CONFIRM,
    }
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return plan
    if args.confirm != CONFIRM:
        raise SystemExit(f"live grant requires --confirm '{CONFIRM}'")
    granted = grant(args, template_id, inventory["inventoryId"], position)
    plan["granted"] = {
        "itemId": int(granted[0]) if granted else None,
        "inventoryId": int(granted[1]) if granted else inventory["inventoryId"],
        "stackSize": int(granted[2]) if granted else args.count,
        "positionIndex": int(granted[3]) if granted else position,
        "templateId": granted[4] if granted else template_id,
    }
    print(json.dumps(plan, indent=2))
    return plan


def main():
    try:
        main_with_argv(sys.argv[1:])
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
