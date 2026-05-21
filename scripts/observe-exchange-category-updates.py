#!/usr/bin/env python3
import argparse
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "backups" / "admin-panel" / "artificial-exchange"
DEFAULT_OUTPUT = STATE_DIR / "verified-category-map.json"

import importlib.util

spec = importlib.util.spec_from_file_location("bot", ROOT / "scripts" / "artificial-exchange-bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


INSTALL_SQL = """
create table if not exists dune.dash_exchange_category_observations (
    id bigserial primary key,
    observed_at timestamptz not null default now(),
    order_id bigint not null,
    exchange_id bigint not null,
    owner_id bigint not null,
    template_id text not null,
    old_category_mask integer,
    old_category_depth smallint,
    new_category_mask integer not null,
    new_category_depth smallint not null
);

create or replace function dune.dash_record_exchange_category_update()
returns trigger
language plpgsql
as $$
begin
    if old.category_mask is distinct from new.category_mask
       or old.category_depth is distinct from new.category_depth then
        insert into dune.dash_exchange_category_observations(
            order_id, exchange_id, owner_id, template_id,
            old_category_mask, old_category_depth,
            new_category_mask, new_category_depth
        )
        values(
            new.id, new.exchange_id, new.owner_id, new.template_id,
            old.category_mask, old.category_depth,
            new.category_mask, new.category_depth
        );
    end if;
    return new;
end
$$;

drop trigger if exists dash_exchange_category_observe on dune.dune_exchange_orders;
create trigger dash_exchange_category_observe
after update of category_mask, category_depth on dune.dune_exchange_orders
for each row
execute function dune.dash_record_exchange_category_update();
"""


UNINSTALL_SQL = """
drop trigger if exists dash_exchange_category_observe on dune.dune_exchange_orders;
drop function if exists dune.dash_record_exchange_category_update();
"""


def install(conn):
    with conn.cursor() as cur:
        cur.execute(INSTALL_SQL)
    conn.commit()


def uninstall(conn):
    with conn.cursor() as cur:
        cur.execute(UNINSTALL_SQL)
    conn.commit()


def force_hash_mismatch(conn, value):
    with conn.cursor() as cur:
        cur.execute("update dune.dune_exchange_categories_hash set hash=%s", (int(value),))
    conn.commit()


def export_observations(conn, output):
    with conn.cursor() as cur:
        cur.execute(
            """
            select distinct on (template_id)
                template_id, new_category_mask as category_mask,
                new_category_depth as category_depth, observed_at,
                order_id, exchange_id, owner_id
            from dune.dash_exchange_category_observations
            order by template_id, observed_at desc, id desc
            """
        )
        rows = list(cur.fetchall())
    payload = {
        "generated_at": int(time.time()),
        "source": "dune.dash_exchange_category_observations trigger on client update_sell_orders_categories writes",
        "items": {},
    }
    for row in rows:
        payload["items"][row["template_id"]] = {
            "category_mask": int(row["category_mask"]),
            "category_depth": int(row["category_depth"]),
            "observed_at": row["observed_at"].isoformat() if row.get("observed_at") else None,
            "order_id": int(row["order_id"]),
            "exchange_id": int(row["exchange_id"]),
            "owner_id": int(row["owner_id"]),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def summary(conn):
    with conn.cursor() as cur:
        cur.execute("select to_regclass('dune.dash_exchange_category_observations') as rel")
        if not cur.fetchone()["rel"]:
            return {"installed": False, "observations": 0, "templates": 0}
        cur.execute(
            """
            select count(*) observations, count(distinct template_id) templates
            from dune.dash_exchange_category_observations
            """
        )
        row = cur.fetchone()
        return {"installed": True, "observations": int(row["observations"]), "templates": int(row["templates"])}


def main():
    parser = argparse.ArgumentParser(description="Observe and export client-verified Exchange category mask/depth updates.")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--force-hash-mismatch", type=int)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    conn = bot.connect_db()
    try:
        if args.install:
            install(conn)
        if args.force_hash_mismatch is not None:
            force_hash_mismatch(conn, args.force_hash_mismatch)
        exported = None
        if args.export:
            exported = export_observations(conn, args.output)
        if args.uninstall:
            uninstall(conn)
        result = summary(conn)
        if exported is not None:
            result["exported"] = {"path": str(args.output), "templates": len(exported["items"])}
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
