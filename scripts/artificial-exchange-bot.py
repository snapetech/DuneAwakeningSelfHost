#!/usr/bin/env python3
import argparse
import copy
import json
import os
import pathlib
import random
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "backups" / "admin-panel" / "artificial-exchange"
CATALOG_PATH = STATE_DIR / "catalog.json"
AUDIT_PATH = STATE_DIR / "bot-audit.jsonl"
STATE_PATH = STATE_DIR / "bot-state.json"
CONFIRM = "RUN ARTIFICIAL EXCHANGE"
CLAIM_CONFIRM = "CLAIM ARTIFICIAL EXCHANGE"
FUND_CONFIRM = "FUND ARTIFICIAL EXCHANGE"
POPULATE_CONFIRM = "POPULATE ARTIFICIAL EXCHANGE"


def read_env_file(path):
    values = {}
    try:
        for raw in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


FILE_ENV = {}
for env_path in ("/workspace/.env", ROOT / ".env"):
    FILE_ENV.update(read_env_file(env_path))


def env(name, default=""):
    value = os.environ.get(name)
    if value not in (None, ""):
        return value
    return FILE_ENV.get(name, default)


def env_bool(name, default=False):
    return env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def db_default_host():
    return "postgres" if pathlib.Path("/workspace/.env").exists() else "127.0.0.1"


def db_default_port():
    return "5432" if pathlib.Path("/workspace/.env").exists() else "15431"


def connect_db():
    import psycopg2
    import psycopg2.extras

    host = env("DUNE_ADMIN_DB_HOST", db_default_host())
    port = env("DUNE_ADMIN_DB_PORT", db_default_port())
    dbname = env("DUNE_ADMIN_DB_NAME", env("DUNE_DATABASE", "dune_sb_1_4_0_0"))
    log_event("db-connect-attempt", host=host, port=port, dbname=dbname)
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=env("DUNE_ADMIN_DB_USER", "dune"),
        password=env("DUNE_ADMIN_DB_PASSWORD", env("POSTGRES_DUNE_PASSWORD", "")),
        dbname=dbname,
        connect_timeout=5,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    log_event("db-connect-ok", host=host, port=port, dbname=dbname)
    return conn


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def audit(event):
    event = dict(event)
    event["ts"] = int(time.time())
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def log_event(event, **fields):
    print(json.dumps({"event": event, "ts": int(time.time()), **fields}, sort_keys=True, default=str), flush=True)


def log_failure(event, exc, **fields):
    payload = {
        "event": event,
        "ok": False,
        "error": str(exc),
        "exceptionType": type(exc).__name__,
        "traceback": traceback.format_exc(),
        **fields,
    }
    log_event(event, **{key: value for key, value in payload.items() if key != "event"})
    audit(payload)


def today_key():
    return time.strftime("%Y-%m-%d", time.localtime())


def load_catalog(path):
    payload = load_json(path, {"items": []})
    items = {}
    for row in payload.get("items", []):
        if row.get("template_id"):
            items[row["template_id"]] = row
    log_event("catalog-loaded", path=str(path), items=len(items), enabledItems=sum(1 for row in items.values() if row.get("enabled")))
    return items


def load_state():
    state = load_json(STATE_PATH, {})
    today = today_key()
    if state.get("day") != today:
        state = {"day": today, "spent_global": 0, "spent_by_seller": {}, "spent_by_template": {}, "seen_completed": [], "claimed_settlements": []}
    state.setdefault("claimed_settlements", [])
    return state


def spend_available(state, order, catalog_row):
    price = int(order["item_price"])
    global_cap = int(env("DUNE_ARTIFICIAL_EXCHANGE_DAILY_SOLARI_CAP", "50000"))
    seller_cap = int(env("DUNE_ARTIFICIAL_EXCHANGE_DAILY_SELLER_CAP", "10000"))
    template_cap = int(env("DUNE_ARTIFICIAL_EXCHANGE_DAILY_TEMPLATE_CAP", "15000"))
    seller = str(order["owner_id"])
    template = order["template_id"]
    if state.get("spent_global", 0) + price > global_cap:
        return False, "global daily cap"
    if state["spent_by_seller"].get(seller, 0) + price > seller_cap:
        return False, "seller daily cap"
    if state["spent_by_template"].get(template, 0) + price > template_cap:
        return False, "template daily cap"
    if price > int(catalog_row["max_buy_price"]):
        return False, "above max_buy_price"
    return True, ""


def record_spend(state, order):
    price = int(order["item_price"])
    seller = str(order["owner_id"])
    template = order["template_id"]
    state["spent_global"] = state.get("spent_global", 0) + price
    state["spent_by_seller"][seller] = state["spent_by_seller"].get(seller, 0) + price
    state["spent_by_template"][template] = state["spent_by_template"].get(template, 0) + price


def buy_probability(tier):
    defaults = {"low": "0.08", "medium": "0.18", "high": "0.35"}
    return float(env(f"DUNE_ARTIFICIAL_EXCHANGE_{tier.upper()}_BUY_PROBABILITY", defaults.get(tier, "0.05")))


def blocked_sellers():
    return {item.strip() for item in env("DUNE_ARTIFICIAL_EXCHANGE_BLOCKED_SELLERS", "").split(",") if item.strip()}


def populator_owner_ids():
    ids = {item.strip() for item in env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_IDS", "").split(",") if item.strip()}
    owner_id = env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID", "").strip()
    if owner_id:
        ids.add(owner_id)
    return ids


def buyer_skip_reason(order, args):
    if order.get("is_npc_order") and not args.include_npc_test_orders:
        return "npc order skipped"
    if str(order.get("owner_id")) in populator_owner_ids() and not args.include_npc_test_orders:
        return "populator owner skipped"
    return ""


def populator_catalog_rows(catalog):
    rows = []
    for row in catalog.values():
        if not row.get("enabled"):
            continue
        if row.get("baseline_price") in (None, "", 0):
            continue
        if env_bool("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_REQUIRE_VALIDATED", True) and row.get("sellable_status") != "validated":
            continue
        rows.append(row)
    return rows


def jitter_price(baseline_price, jitter_pct):
    baseline = int(baseline_price)
    pct = max(0, int(jitter_pct))
    low = max(1, int(round(baseline * (100 - pct) / 100)))
    high = max(low, int(round(baseline * (100 + pct) / 100)))
    return random.randint(low, high)


def jitter_price_bounds(baseline_price, jitter_pct):
    baseline = int(baseline_price)
    pct = max(0, int(jitter_pct))
    low = max(1, int(round(baseline * (100 - pct) / 100)))
    high = max(low, int(round(baseline * (100 + pct) / 100)))
    return low, high


def planned_unique_price(row, jitter_pct, used_prices):
    low, high = jitter_price_bounds(row["baseline_price"], jitter_pct)
    template_id = row["template_id"]
    used = used_prices.setdefault(template_id, set())
    available = [price for price in range(low, high + 1) if price not in used]
    if not available:
        raise RuntimeError(f"not enough unique prices for {template_id} in jitter range {low}-{high}")
    price = random.choice(available)
    used.add(price)
    return price


def jitter_expiration(now, min_seconds, max_seconds):
    min_seconds = int(min_seconds)
    max_seconds = max(min_seconds, int(max_seconds))
    return int(now) + random.randint(min_seconds, max_seconds)


def desired_seed_count(active_count, target_min, target_max):
    forced_count = env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_FORCE_COUNT", "").strip()
    if forced_count:
        return max(0, int(forced_count))
    target_min = int(target_min)
    target_max = max(target_min, int(target_max))
    if active_count >= target_min:
        return 0
    return random.randint(target_min - active_count, target_max - active_count)


def expire_probability_selected(order_ids, probability):
    probability = max(0.0, min(1.0, float(probability)))
    return [order_id for order_id in order_ids if random.random() < probability]


def cleanup_candidate_ids(active_orders, target_max_orders, expire_probability):
    target_max_orders = max(0, int(target_max_orders))
    over_cap = max(0, len(active_orders) - target_max_orders)
    over_cap_ids = [row["id"] for row in active_orders[:over_cap]]
    random_ids = expire_probability_selected([row["id"] for row in active_orders[over_cap:]], expire_probability)
    return sorted(set(over_cap_ids + random_ids))


def free_position_candidates(occupied_positions, needed_count, start=0, max_position=100000):
    occupied = {int(pos) for pos in occupied_positions if pos is not None}
    positions = []
    position = int(start)
    while len(positions) < int(needed_count) and position <= int(max_position):
        if position not in occupied:
            positions.append(position)
        position += 1
    if len(positions) < int(needed_count):
        raise RuntimeError(f"not enough free staging inventory positions: needed {needed_count}, found {len(positions)}")
    return positions


def populator_quality_level(row):
    configured = int(row.get("quality_level") or env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_QUALITY_LEVEL", "1"))
    minimum = int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MIN_QUALITY_LEVEL", "1"))
    if configured < minimum:
        raise RuntimeError(f"populator quality_level {configured} is below minimum {minimum}")
    return configured


def populator_category_mask(row):
    return int(row.get("category_mask") if row.get("category_mask") is not None else env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_CATEGORY_MASK", "0"))


def populator_category_depth(row):
    return int(row.get("category_depth") if row.get("category_depth") is not None else env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_CATEGORY_DEPTH", "0"))


def fetch_orders(conn, exchange_id, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            select
                o.id, o.exchange_id, o.access_point_id, o.owner_id, o.item_id,
                o.template_id, o.item_price, o.quality_level, o.expiration_time,
                o.durability_cur, o.durability_max, s.initial_stack_size,
                s.wear_normalized_price, i.stack_size,
                o.revision,
                o.is_npc_order
            from dune.dune_exchange_orders o
            join dune.dune_exchange_sell_orders s on s.order_id = o.id
            left join dune.items i on i.id = o.item_id
            where o.exchange_id = %s
              and o.template_id is not null
              and o.item_price is not null
            order by o.id
            limit %s
            """,
            (exchange_id, limit),
        )
        return list(cur.fetchall())


def fetch_completed(conn, limit):
    with conn.cursor() as cur:
        cur.execute("select to_regclass('dune.dune_exchange_fulfilled_orders') as rel")
        if not cur.fetchone()["rel"]:
            return []
        cur.execute("select * from dune.dune_exchange_fulfilled_orders order by 1 desc limit %s", (limit,))
        return list(cur.fetchall())


def fetch_seeded_orders(conn, exchange_id, owner_id, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            select
                o.id, o.exchange_id, o.access_point_id, o.owner_id, o.item_id,
                o.template_id, o.item_price, o.expiration_time, o.quality_level,
                i.stack_size
            from dune.dune_exchange_orders o
            left join dune.items i on i.id=o.item_id
            where o.exchange_id=%s
              and o.owner_id=%s
              and o.is_npc_order=true
            order by o.expiration_time, o.id
            limit %s
            """,
            (exchange_id, owner_id, limit),
        )
        return list(cur.fetchall())


def seeded_order_ids(rows):
    return {int(row["id"]) for row in rows}


def fetch_free_inventory_positions(conn, inventory_id, needed_count):
    if needed_count <= 0:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            select position_index
            from dune.items
            where inventory_id=%s
            """,
            (inventory_id,),
        )
        occupied = [row["position_index"] for row in cur.fetchall()]
    return free_position_candidates(
        occupied,
        needed_count,
        start=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_POSITION_START", "0")),
        max_position=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_POSITION_MAX", "100000")),
    )


def execute_native_expiry(cur, exchange_id, now):
    cur.execute(
        """
        select to_regprocedure('dune.dune_exchange_expire_orders(bigint,bigint,bigint,bigint)') as rel
        """
    )
    if not cur.fetchone()["rel"]:
        return {"called": False, "reason": "function missing"}
    purge_time = int(now) + int(env("DUNE_ARTIFICIAL_EXCHANGE_PURGE_SECONDS", "2419200"))
    expired_completion_type = int(env("DUNE_ARTIFICIAL_EXCHANGE_EXPIRED_COMPLETION_TYPE", "2"))
    cur.execute(
        """
        select dune.dune_exchange_expire_orders(%s, %s, %s, %s) as result
        """,
        (exchange_id, int(now), purge_time, expired_completion_type),
    )
    row = cur.fetchone()
    return {"called": True, "result": row["result"] if row else None}


def delete_seeded_orders(cur, order_ids, exchange_id, owner_id):
    if not order_ids:
        return []
    cur.execute(
        """
        select id, item_id, template_id, item_price
        from dune.dune_exchange_orders
        where id = any(%s)
          and exchange_id=%s
          and owner_id=%s
          and is_npc_order=true
        for update
        """,
        (order_ids, exchange_id, owner_id),
    )
    rows = [dict(row) for row in cur.fetchall()]
    item_ids = [row["item_id"] for row in rows if row.get("item_id") not in (None, 0, "")]
    if item_ids:
        cur.execute(
            """
            update dune.dune_exchange_orders
            set item_id = null
            where id = any(%s)
              and exchange_id=%s
              and owner_id=%s
              and is_npc_order=true
            """,
            (order_ids, exchange_id, owner_id),
        )
        cur.execute(
            """
            delete from dune.items
            where id = any(%s)
              and inventory_id = dune.get_exchange_inventory_id(%s)
            returning id
            """,
            (item_ids, exchange_id),
        )
        deleted_items = [row["id"] for row in cur.fetchall()]
    else:
        deleted_items = []
    cur.execute(
        """
        delete from dune.dune_exchange_orders
        where id = any(%s)
          and exchange_id=%s
          and owner_id=%s
          and is_npc_order=true
        returning id, item_id, template_id, item_price
        """,
        (order_ids, exchange_id, owner_id),
    )
    deleted_orders = [dict(row) for row in cur.fetchall()]
    for row in deleted_orders:
        row["deletedItemIds"] = deleted_items
    return deleted_orders


def create_staging_item(cur, row, source_inventory_id, position_index):
    item_id = None
    cur.execute("select dune.advance_items_id_sequencer(1) as item_id")
    item_id = int(cur.fetchone()["item_id"])
    quality_level = populator_quality_level(row)
    cur.execute(
        """
        select dune.save_item((
            %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s
        )::dune.inventoryitem)
        """,
        (
            item_id,
            source_inventory_id,
            int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_STACK_SIZE", "1")),
            position_index,
            row["template_id"],
            True,
            int(time.time() * 1000),
            "{}",
            quality_level,
            None,
        ),
    )
    return item_id, quality_level


def execute_seed_listing(cur, row, args, price, expiration_time, position_index):
    item_id, quality_level = create_staging_item(cur, row, args.populator_source_inventory_id, position_index)
    cur.execute(
        """
        select dune.dune_exchange_update_recurring_sell_order(
            %s::bigint, %s::bigint, %s::bigint, %s::bigint, %s::bigint,
            %s::bigint, %s::bigint, %s::integer, %s::smallint, %s::real,
            %s::real, %s::bigint, %s::bigint, %s::bigint
        ) as increment_added
        """,
        (
            args.exchange_id,
            expiration_time,
            args.populator_access_point_id,
            args.populator_owner_id,
            item_id,
            int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_STACK_SIZE", "1")),
            int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_MAX_STACK_SIZE", "1")),
            populator_category_mask(row),
            populator_category_depth(row),
            float(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DURABILITY_CUR", "1")),
            float(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DURABILITY_MAX", "1")),
            price,
            price,
            quality_level,
        ),
    )
    result = cur.fetchone()
    increment_added = result["increment_added"] if result else None
    if int(increment_added or 0) <= 0:
        raise RuntimeError(f"seed listing did not add inventory for {row['template_id']} at price {price}")
    return {"itemId": item_id, "incrementAdded": increment_added}


def expire_seeded_once(args):
    if not env_bool("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED", False):
        raise RuntimeError("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED is false")
    if args.populator_owner_id <= 0:
        raise RuntimeError("--populator-owner-id is required")
    now = int(time.time())
    conn = connect_db()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            native = execute_native_expiry(cur, args.exchange_id, now)
            active = fetch_seeded_orders(conn, args.exchange_id, args.populator_owner_id, args.limit)
            candidates = cleanup_candidate_ids(active, args.populator_target_max_orders, args.populator_expire_probability)
            if args.dry_run:
                conn.rollback()
                deleted = []
            else:
                if args.confirm != POPULATE_CONFIRM:
                    raise RuntimeError(f"confirmation phrase required: {POPULATE_CONFIRM}")
                deleted = delete_seeded_orders(cur, candidates, args.exchange_id, args.populator_owner_id)
                conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return {"ok": True, "dryRun": args.dry_run, "nativeExpiry": native, "cleanupCandidates": candidates, "deleted": deleted}


def populate_once(args):
    started = time.time()
    log_event(
        "populate-start",
        dryRun=args.dry_run,
        exchangeId=args.exchange_id,
        ownerId=args.populator_owner_id,
        sourceInventoryId=args.populator_source_inventory_id,
    )
    if not env_bool("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED", False):
        raise RuntimeError("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED is false")
    if args.populator_owner_id <= 0:
        raise RuntimeError("--populator-owner-id is required")
    if args.populator_source_inventory_id <= 0:
        raise RuntimeError("--populator-source-inventory-id is required")
    catalog = load_catalog(args.catalog)
    eligible = populator_catalog_rows(catalog)
    if not eligible:
        return {"ok": True, "dryRun": args.dry_run, "planned": [], "reason": "no eligible catalog rows"}
    conn = connect_db()
    conn.autocommit = False
    planned = []
    cleanup = None
    now = int(time.time())
    try:
        active = fetch_seeded_orders(conn, args.exchange_id, args.populator_owner_id, args.limit)
        count = args.populator_force_count if args.populator_force_count is not None else desired_seed_count(len(active), args.populator_target_min_orders, args.populator_target_max_orders)
        positions = fetch_free_inventory_positions(conn, args.populator_source_inventory_id, count)
        used_prices = {}
        for order in active:
            used_prices.setdefault(order["template_id"], set()).add(int(order["item_price"]))
        for index in range(count):
            row = random.choice(eligible)
            price = args.populator_force_price + index if args.populator_force_price is not None else planned_unique_price(row, args.populator_price_jitter_pct, used_prices)
            expiration_time = jitter_expiration(now, args.populator_expiry_min_seconds, args.populator_expiry_max_seconds)
            position_index = positions[index]
            event = {
                "templateId": row["template_id"],
                "baselinePrice": row["baseline_price"],
                "price": price,
                "qualityLevel": populator_quality_level(row),
                "categoryMask": populator_category_mask(row),
                "categoryDepth": populator_category_depth(row),
                "expirationTime": expiration_time,
                "ownerId": args.populator_owner_id,
                "exchangeId": args.exchange_id,
                "accessPointId": args.populator_access_point_id,
                "sourceInventoryId": args.populator_source_inventory_id,
                "sourcePositionIndex": position_index,
                "plannedItemCreation": True,
                "dryRun": args.dry_run,
            }
            if not args.dry_run:
                if args.confirm != POPULATE_CONFIRM:
                    raise RuntimeError(f"confirmation phrase required: {POPULATE_CONFIRM}")
                with conn.cursor() as cur:
                    event.update(execute_seed_listing(cur, row, args, price, expiration_time, position_index))
            planned.append(event)
            audit({"event": "populator-seed-planned", **event})
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    if args.expire_seeded:
        cleanup = expire_seeded_once(args)
    result = {"ok": True, "dryRun": args.dry_run, "activeSeededOrders": len(active), "eligibleCatalogRows": len(eligible), "planned": planned, "cleanup": cleanup}
    log_event(
        "populate-complete",
        dryRun=args.dry_run,
        activeSeededOrders=len(active),
        eligibleCatalogRows=len(eligible),
        planned=len(planned),
        durationMs=int((time.time() - started) * 1000),
    )
    return result


def validate_populator_once(args):
    if not env_bool("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_LIVE_VALIDATION_ENABLED", False):
        raise RuntimeError("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_LIVE_VALIDATION_ENABLED is false")
    if args.dry_run:
        validation_args = copy.copy(args)
        validation_args.populator_force_count = 1
        validation_args.expire_seeded = False
        planned = populate_once(validation_args)
        return {"ok": True, "dryRun": True, "planned": planned, "applied": False}
    if args.confirm != POPULATE_CONFIRM:
        raise RuntimeError(f"confirmation phrase required: {POPULATE_CONFIRM}")

    conn = connect_db()
    try:
        before = fetch_seeded_orders(conn, args.exchange_id, args.populator_owner_id, args.limit)
    finally:
        conn.close()

    validation_args = copy.copy(args)
    validation_args.populator_force_count = 1
    validation_args.populator_force_price = int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_VALIDATION_PRICE", str(900000000 + int(time.time()) % 100000000)))
    validation_args.expire_seeded = False
    populate_result = populate_once(validation_args)

    conn = connect_db()
    cleanup = []
    try:
        after = fetch_seeded_orders(conn, args.exchange_id, args.populator_owner_id, args.limit)
        new_ids = sorted(seeded_order_ids(after) - seeded_order_ids(before))
        new_orders = [dict(row) for row in after if int(row["id"]) in new_ids]
        skip_args = copy.copy(args)
        skip_args.dry_run = True
        skip_args.ignore_enabled_gate = True
        skip_args.include_npc_test_orders = False
        skip_args.limit = max(args.limit, 10000)
        skip_args.report_skips = max(args.report_skips, 10000)
        buyer_result = scan_once(skip_args)
        skipped_new = [
            row for row in buyer_result.get("skipped", [])
            if int(row.get("orderId", 0)) in new_ids and row.get("reason") in ("npc order skipped", "populator owner skipped")
        ]
        with conn.cursor() as cur:
            cleanup = delete_seeded_orders(cur, new_ids, args.exchange_id, args.populator_owner_id)
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    ok = bool(new_orders) and len(skipped_new) == len(new_orders) and len(cleanup) == len(new_orders)
    return {
        "ok": ok,
        "dryRun": False,
        "populate": populate_result,
        "newOrders": new_orders,
        "buyerSkippedNewOrders": skipped_new,
        "cleanup": cleanup,
    }


def settlement_status(row):
    completion_type = int(row.get("completion_type") if row.get("completion_type") is not None else -1)
    sold_completion_type = int(env("DUNE_ARTIFICIAL_EXCHANGE_SOLD_COMPLETION_TYPE", "1"))
    purchased_completion_type = int(env("DUNE_ARTIFICIAL_EXCHANGE_PURCHASED_COMPLETION_TYPE", "0"))
    if completion_type == purchased_completion_type:
        return "purchased_item_storage"
    if completion_type != sold_completion_type:
        return "unknown_completion_type"
    if row.get("item_id") not in (None, 0, ""):
        return "seller_claim_has_item_id"
    if row.get("currency_balance") is None:
        return "unsafe_missing_base_solaris_balance"
    return "seller_solari_claim_ready"


def settlement_claim_safe(row):
    return settlement_status(row) == "seller_solari_claim_ready"


def settlement_report(conn, limit):
    with conn.cursor() as cur:
        cur.execute("select to_regclass('dune.dune_exchange_fulfilled_orders') as rel")
        if not cur.fetchone()["rel"]:
            return []
        cur.execute(
            """
            select
                o.id as order_id,
                o.owner_id,
                ps.character_name as owner_character_name,
                o.item_id,
                o.template_id,
                o.item_price,
                f.completion_type,
                f.stack_size,
                f.source_order_id,
                f.original_order_id,
                b.balance as currency_balance,
                (o.item_price * f.stack_size) as expected_solari
            from dune.dune_exchange_fulfilled_orders f
            join dune.dune_exchange_orders o on o.id = f.order_id
            left join dune.player_state ps on ps.player_controller_id = o.owner_id
            left join dune.player_virtual_currency_balances b
              on b.player_controller_id = o.owner_id
             and b.currency_id = dune.get_solaris_id()
            order by o.id desc
            limit %s
            """,
            (limit,),
        )
        rows = []
        for raw in cur.fetchall():
            row = dict(raw)
            row["status"] = settlement_status(row)
            row["claimSafe"] = settlement_claim_safe(row)
            rows.append(row)
        return rows


def settlement_row(conn, order_id):
    rows = settlement_report(conn, 1000)
    for row in rows:
        if int(row["order_id"]) == int(order_id):
            return row
    return None


def settlement_claim_key(row):
    return ":".join(str(row.get(key) or "") for key in ("order_id", "source_order_id", "original_order_id", "completion_type"))


def read_exchange_balance(conn, owner_id):
    with conn.cursor() as cur:
        cur.execute("select dune.dune_exchange_retrieve_solari_balance(%s) as balance", (owner_id,))
        row = cur.fetchone()
    return int(row["balance"]) if row and row.get("balance") is not None else 0


def ensure_solaris_balance_row(cur, controller_id):
    cur.execute(
        """
        insert into dune.player_virtual_currency_balances(player_controller_id, currency_id, balance)
        values(%s, dune.get_solaris_id(), 0)
        on conflict do nothing
        """,
        (controller_id,),
    )


def read_solaris_balance(cur, controller_id):
    cur.execute(
        """
        select balance
        from dune.player_virtual_currency_balances
        where player_controller_id=%s and currency_id=dune.get_solaris_id()
        for update
        """,
        (controller_id,),
    )
    row = cur.fetchone()
    return int(row["balance"]) if row and row.get("balance") is not None else None


def revision_matches(conn, order):
    with conn.cursor() as cur:
        cur.execute(
            "select revision, item_price from dune.dune_exchange_orders where id=%s for share",
            (order["id"],),
        )
        row = cur.fetchone()
    return bool(row and int(row["revision"]) == int(order["revision"]) and int(row["item_price"]) == int(order["item_price"]))


def fulfill_signature(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            select pg_get_function_identity_arguments(p.oid) as args
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname='dune' and p.proname='dune_exchange_fulfill_sell_order'
            order by p.pronargs
            """
        )
        return [row["args"] for row in cur.fetchall()]


def execute_purchase(conn, order, buyer_controller_id):
    log_event(
        "purchase-attempt",
        orderId=order["id"],
        templateId=order["template_id"],
        sellerId=order["owner_id"],
        price=order["item_price"],
        buyerControllerId=buyer_controller_id,
        revision=order["revision"],
    )
    signatures = fulfill_signature(conn)
    supported = [args for args in signatures if "in_order_id bigint" in args and "in_order_revision bigint" in args]
    if not supported:
        raise RuntimeError(f"unsupported fulfill function signature(s): {signatures}")
    purge_time = int(time.time()) + int(env("DUNE_ARTIFICIAL_EXCHANGE_PURGE_SECONDS", "2419200"))
    with conn.cursor() as cur:
        cur.execute(
            """
            select (dune.dune_exchange_fulfill_sell_order(
                in_exchange_id => %s,
                in_max_orders_per_player => %s,
                in_purchased_completion_type => %s,
                in_sold_completion_type => %s,
                in_instigator_id => %s,
                in_order_id => %s,
                in_order_revision => %s,
                in_dst_inventory_id => null,
                in_dst_index => 0,
                in_count => 1,
                in_solaris_fee => 0,
                in_purge_time => %s
            )).*
            """,
            (
                order["exchange_id"],
                int(env("DUNE_ARTIFICIAL_EXCHANGE_MAX_ORDERS_PER_PLAYER", "50")),
                int(env("DUNE_ARTIFICIAL_EXCHANGE_PURCHASED_COMPLETION_TYPE", "0")),
                int(env("DUNE_ARTIFICIAL_EXCHANGE_SOLD_COMPLETION_TYPE", "1")),
                buyer_controller_id,
                order["id"],
                order["revision"],
                purge_time,
            ),
        )
        result = cur.fetchone()
    log_event("purchase-result", orderId=order["id"], result=dict(result) if result else None)
    return result


def inspect_settlement(conn, limit):
    rows = settlement_report(conn, limit)
    for row in rows:
        audit({"event": "completed-order-observed", "row": row})
    return rows


def print_settlement_report(args):
    conn = connect_db()
    with conn:
        rows = settlement_report(conn, args.settlement_limit)
    conn.close()
    unsafe = [row for row in rows if not row["claimSafe"] and row["status"].startswith("unsafe")]
    return {
        "ok": True,
        "dryRun": True,
        "autoClaimEnabled": env_bool("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED", False),
        "claimable": sum(1 for row in rows if row["claimSafe"]),
        "unsafe": len(unsafe),
        "rows": rows,
    }


def execute_direct_seller_claim(cur, row):
    expected = int(row["expected_solari"])
    ensure_solaris_balance_row(cur, row["owner_id"])
    before_balance = read_solaris_balance(cur, row["owner_id"])
    cur.execute(
        """
        select
            o.id as order_id,
            o.owner_id,
            o.item_id,
            o.item_price,
            f.completion_type,
            f.stack_size,
            f.original_order_id
        from dune.dune_exchange_orders o
        join dune.dune_exchange_fulfilled_orders f on f.order_id=o.id
        where o.id=%s
        for update
        """,
        (row["order_id"],),
    )
    locked = cur.fetchone()
    if not locked:
        raise RuntimeError(f"settlement order {row['order_id']} vanished before claim")
    if int(locked["owner_id"]) != int(row["owner_id"]):
        raise RuntimeError("settlement owner changed before claim")
    if locked["item_id"] not in (None, 0, ""):
        raise RuntimeError("settlement order has item_id; refusing Solari claim")
    if int(locked["completion_type"]) != int(env("DUNE_ARTIFICIAL_EXCHANGE_SOLD_COMPLETION_TYPE", "1")):
        raise RuntimeError("settlement completion type is not a seller Solari claim")
    actual_value = int(locked["item_price"]) * int(locked["stack_size"])
    if actual_value != expected:
        raise RuntimeError(f"settlement value changed before claim: expected {expected}, got {actual_value}")
    cur.execute(
        """
        update dune.player_virtual_currency_balances
        set balance = balance + %s
        where player_controller_id=%s and currency_id=dune.get_solaris_id()
        returning balance
        """,
        (expected, row["owner_id"]),
    )
    after_balance = int(cur.fetchone()["balance"])
    cur.execute("delete from dune.dune_exchange_orders where id=%s", (row["order_id"],))
    cur.execute(
        """
        select exists(
            select 1
            from dune.dune_exchange_orders o
            left join dune.dune_exchange_fulfilled_orders f on f.order_id=o.id
            where o.id=%s or f.order_id=%s
        ) as still_exists
        """,
        (row["order_id"], row["order_id"]),
    )
    still_exists = bool(cur.fetchone()["still_exists"])
    return {
        "total_item_value": expected,
        "original_order_id": locked["original_order_id"],
        "before_balance": before_balance,
        "after_balance": after_balance,
        "credited": after_balance - before_balance,
        "still_exists": still_exists,
        "method": "direct_validated_sql",
    }


def readiness_check(args):
    checks = []
    catalog = load_catalog(args.catalog)
    checks.append({
        "name": "catalog",
        "ok": bool(catalog),
        "items": len(catalog),
        "enabledItems": sum(1 for row in catalog.values() if row.get("enabled")),
        "path": str(args.catalog),
    })
    checks.append({
        "name": "buyerGate",
        "ok": env_bool("DUNE_ARTIFICIAL_EXCHANGE_ENABLED", True),
        "enabled": env_bool("DUNE_ARTIFICIAL_EXCHANGE_ENABLED", True),
        "dryRun": env_bool("DUNE_ARTIFICIAL_EXCHANGE_DRY_RUN", True),
        "purchasesEnabled": env_bool("DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED", False),
    })
    checks.append({
        "name": "settlementGate",
        "ok": True,
        "autoClaimEnabled": env_bool("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED", False),
        "autoClaimAfterScan": env_bool("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_AFTER_SCAN", False),
    })
    checks.append({
        "name": "populatorGate",
        "ok": True,
        "enabled": env_bool("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED", False),
        "dryRun": env_bool("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN", True),
        "ownerId": int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID", "0") or "0"),
        "sourceInventoryId": int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_INVENTORY_ID", "0") or "0"),
    })
    try:
        conn = connect_db()
        with conn:
            orders = fetch_orders(conn, args.exchange_id, min(args.limit, 20))
            settlements = settlement_report(conn, args.settlement_limit)
            buyer_balance = read_exchange_balance(conn, args.buyer_controller_id) if args.buyer_controller_id > 0 else None
        conn.close()
        checks.append({"name": "database", "ok": True, "exchangeId": args.exchange_id, "ordersSeen": len(orders), "settlementsSeen": len(settlements)})
        checks.append({"name": "settlementState", "ok": True, "claimable": sum(1 for row in settlements if row["claimSafe"]), "unsafe": sum(1 for row in settlements if row["status"].startswith("unsafe"))})
        purchase_enabled = env_bool("DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED", False) and not env_bool("DUNE_ARTIFICIAL_EXCHANGE_DRY_RUN", True)
        checks.append({
            "name": "buyerFunding",
            "ok": (not purchase_enabled) or (args.buyer_controller_id > 0 and buyer_balance is not None and buyer_balance > 0),
            "buyerControllerId": args.buyer_controller_id,
            "exchangeBalance": buyer_balance,
            "requiredForApply": purchase_enabled,
        })
    except Exception as exc:
        checks.append({"name": "database", "ok": False, "error": str(exc)})
    ok = all(check["ok"] for check in checks if check["name"] not in ("buyerGate",))
    return {"ok": ok, "checks": checks}


def claim_settlement_once(args):
    log_event("settlement-claim-start", orderId=args.claim_settlement)
    if not env_bool("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED", False):
        raise RuntimeError("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED is false")
    if args.confirm != CLAIM_CONFIRM:
        raise RuntimeError(f"confirmation phrase required: {CLAIM_CONFIRM}")
    state = load_state()
    conn = connect_db()
    conn.autocommit = False
    try:
        row = settlement_row(conn, args.claim_settlement)
        if not row:
            raise RuntimeError(f"settlement order {args.claim_settlement} was not found")
        key = settlement_claim_key(row)
        if key in state["claimed_settlements"]:
            conn.rollback()
            return {"ok": True, "dryRun": True, "alreadyClaimed": True, "row": row}
        if not settlement_claim_safe(row):
            audit({"event": "settlement-claim-preflight-repair", "key": key, "row": row})
        with conn.cursor() as cur:
            result = execute_direct_seller_claim(cur, row)
            before_balance = result["before_balance"]
            after_balance = result["after_balance"]
            still_exists = result["still_exists"]
        expected = int(row["expected_solari"])
        credited = after_balance - before_balance if after_balance is not None and before_balance is not None else None
        valid = (
            result.get("total_item_value") is not None
            and int(result["total_item_value"]) == expected
            and int(result.get("original_order_id") or 0) == int(row["original_order_id"] or 0)
            and credited == expected
            and not still_exists
        )
        if not valid:
            conn.rollback()
            audit({
                "event": "settlement-claim-rolled-back",
                "key": key,
                "row": row,
                "result": result,
                "beforeBalance": before_balance,
                "afterBalance": after_balance,
                "credited": credited,
                "expected": expected,
                "stillExists": still_exists,
            })
            return {
                "ok": False,
                "dryRun": False,
                "rolledBack": True,
                "reason": "native claim failed validation",
                "row": row,
                "result": result,
                "beforeBalance": before_balance,
                "afterBalance": after_balance,
                "credited": credited,
                "expected": expected,
                "stillExists": still_exists,
            }
        conn.commit()
        state["claimed_settlements"].append(key)
        audit({"event": "settlement-claimed", "key": key, "row": row, "result": result, "beforeBalance": before_balance, "afterBalance": after_balance})
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    save_json(STATE_PATH, state)
    response = {"ok": True, "dryRun": False, "claimed": key, "row": row, "result": result, "beforeBalance": before_balance, "afterBalance": after_balance}
    log_event("settlement-claim-complete", orderId=args.claim_settlement, credited=result.get("credited"), beforeBalance=before_balance, afterBalance=after_balance)
    return response


def claim_all_settlements(args, *, require_confirm=True):
    log_event("settlement-auto-claim-start", settlementLimit=args.settlement_limit, requireConfirm=require_confirm)
    if not env_bool("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED", False):
        raise RuntimeError("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED is false")
    if require_confirm and args.confirm != CLAIM_CONFIRM:
        raise RuntimeError(f"confirmation phrase required: {CLAIM_CONFIRM}")
    state = load_state()
    conn = connect_db()
    claimed = []
    skipped = []
    sold_completion_type = int(env("DUNE_ARTIFICIAL_EXCHANGE_SOLD_COMPLETION_TYPE", "1"))
    try:
        rows = settlement_report(conn, args.settlement_limit)
        for row in rows:
            key = settlement_claim_key(row)
            if key in state["claimed_settlements"]:
                skipped.append({"orderId": row["order_id"], "reason": "already claimed"})
                continue
            if int(row.get("completion_type") or -1) != sold_completion_type or row.get("item_id") not in (None, 0, ""):
                skipped.append({"orderId": row["order_id"], "reason": row["status"]})
                continue
            with conn.cursor() as cur:
                result = execute_direct_seller_claim(cur, row)
            expected = int(row["expected_solari"])
            valid = (
                int(result["total_item_value"]) == expected
                and int(result.get("original_order_id") or 0) == int(row["original_order_id"] or 0)
                and result["credited"] == expected
                and not result["still_exists"]
            )
            if not valid:
                conn.rollback()
                audit({"event": "settlement-auto-claim-rolled-back", "key": key, "row": row, "result": result})
                skipped.append({"orderId": row["order_id"], "reason": "claim failed validation", "result": result})
                continue
            conn.commit()
            state["claimed_settlements"].append(key)
            event = {"orderId": row["order_id"], "key": key, "row": row, "result": result}
            claimed.append(event)
            audit({"event": "settlement-auto-claimed", **event})
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    save_json(STATE_PATH, state)
    result = {"ok": True, "dryRun": False, "claimed": claimed, "skipped": skipped}
    log_event("settlement-auto-claim-complete", claimed=len(claimed), skipped=len(skipped))
    return result


def fund_buyer(args):
    if not env_bool("DUNE_ARTIFICIAL_EXCHANGE_FUNDING_ENABLED", False):
        raise RuntimeError("DUNE_ARTIFICIAL_EXCHANGE_FUNDING_ENABLED is false")
    if args.confirm != FUND_CONFIRM:
        raise RuntimeError(f"confirmation phrase required: {FUND_CONFIRM}")
    if args.buyer_controller_id <= 0:
        raise RuntimeError("--buyer-controller-id is required")
    if args.fund_buyer <= 0:
        raise RuntimeError("--fund-buyer amount must be positive")
    conn = connect_db()
    with conn:
        before = read_exchange_balance(conn, args.buyer_controller_id)
        with conn.cursor() as cur:
            cur.execute(
                "select dune.dune_exchange_modify_user_solari_balance(%s,%s)",
                (args.buyer_controller_id, args.fund_buyer),
            )
        after = read_exchange_balance(conn, args.buyer_controller_id)
    conn.close()
    result = {
        "ok": True,
        "buyerControllerId": args.buyer_controller_id,
        "delta": args.fund_buyer,
        "beforeBalance": before,
        "afterBalance": after,
    }
    audit({"event": "buyer-funded", **result})
    return result


def scan_once(args):
    started = time.time()
    log_event(
        "scan-start",
        dryRun=args.dry_run,
        exchangeId=args.exchange_id,
        limit=args.limit,
        autoClaimAfterScan=args.auto_claim_after_scan,
    )
    if not env_bool("DUNE_ARTIFICIAL_EXCHANGE_ENABLED", True) and not args.ignore_enabled_gate:
        raise RuntimeError("DUNE_ARTIFICIAL_EXCHANGE_ENABLED is false")
    catalog = load_catalog(args.catalog)
    state = load_state()
    conn = connect_db()
    selected = []
    skipped = []
    auto_claim = None
    with conn:
        completed = inspect_settlement(conn, args.settlement_limit)
        if args.auto_claim_after_scan and env_bool("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_ENABLED", False):
            auto_claim = claim_all_settlements(args, require_confirm=False)
            state["claimed_settlements"] = load_state().get("claimed_settlements", [])
        orders = fetch_orders(conn, args.exchange_id, args.limit)
        for order in orders:
            skip_reason = buyer_skip_reason(order, args)
            if skip_reason:
                skipped.append({"orderId": order["id"], "templateId": order["template_id"], "reason": skip_reason})
                continue
            row = catalog.get(order["template_id"])
            if not row:
                skipped.append({"orderId": order["id"], "reason": "template not in catalog"})
                continue
            if not row.get("enabled"):
                skipped.append({"orderId": order["id"], "templateId": order["template_id"], "reason": "template disabled"})
                continue
            if str(order["owner_id"]) in blocked_sellers():
                skipped.append({"orderId": order["id"], "reason": "seller blocked"})
                continue
            ok, reason = spend_available(state, order, row)
            if not ok:
                skipped.append({"orderId": order["id"], "templateId": order["template_id"], "reason": reason})
                continue
            probability = buy_probability(str(row.get("liquidity_tier", "low")))
            if random.random() > probability:
                skipped.append({"orderId": order["id"], "templateId": order["template_id"], "reason": "probability skip", "probability": probability})
                continue
            if not revision_matches(conn, order):
                skipped.append({"orderId": order["id"], "templateId": order["template_id"], "reason": "stale revision"})
                continue
            decision = {"orderId": order["id"], "templateId": order["template_id"], "sellerId": order["owner_id"], "price": order["item_price"]}
            if args.dry_run:
                decision["dryRun"] = True
            else:
                if not env_bool("DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED", False):
                    raise RuntimeError("DUNE_ARTIFICIAL_EXCHANGE_PURCHASES_ENABLED is false")
                if args.confirm != CONFIRM:
                    raise RuntimeError(f"confirmation phrase required: {CONFIRM}")
                result = execute_purchase(conn, order, args.buyer_controller_id)
                decision["dryRun"] = False
                decision["result"] = dict(result) if result else None
                record_spend(state, order)
            selected.append(decision)
            audit({"event": "purchase-selected", **decision})
    conn.close()
    save_json(STATE_PATH, state)
    result = {"ok": True, "dryRun": args.dry_run, "selected": selected, "skipped": skipped[: args.report_skips], "completedObserved": len(completed), "autoClaim": auto_claim}
    log_event(
        "scan-complete",
        dryRun=args.dry_run,
        selected=len(selected),
        skipped=len(skipped),
        completedObserved=len(completed),
        autoClaimed=len((auto_claim or {}).get("claimed", [])) if isinstance(auto_claim, dict) else 0,
        durationMs=int((time.time() - started) * 1000),
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="Conservative artificial buyer for player Exchange sell orders.")
    parser.add_argument("--catalog", type=pathlib.Path, default=CATALOG_PATH)
    parser.add_argument("--exchange-id", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_ID", "2")))
    parser.add_argument("--buyer-controller-id", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_BUYER_CONTROLLER_ID", "0")))
    parser.add_argument("--limit", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_SCAN_LIMIT", "200")))
    parser.add_argument("--settlement-limit", type=int, default=50)
    parser.add_argument("--report-skips", type=int, default=50)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--populate-once", action="store_true")
    parser.add_argument("--populate-loop", action="store_true")
    parser.add_argument("--expire-seeded", action="store_true")
    parser.add_argument("--validate-populator-once", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--ignore-enabled-gate", action="store_true")
    parser.add_argument("--include-npc-test-orders", action="store_true")
    parser.add_argument("--settlement-report", action="store_true")
    parser.add_argument("--check-ready", action="store_true")
    parser.add_argument("--claim-settlement", type=int)
    parser.add_argument("--claim-all-settlements", action="store_true")
    parser.add_argument("--fund-buyer", type=int, default=0)
    parser.add_argument("--auto-claim-after-scan", action="store_true", default=env_bool("DUNE_ARTIFICIAL_EXCHANGE_AUTO_CLAIM_AFTER_SCAN", False))
    parser.add_argument("--populator-owner-id", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID", "0") or "0"))
    parser.add_argument("--populator-source-inventory-id", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_INVENTORY_ID", "0") or "0"))
    parser.add_argument("--populator-access-point-id", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_ACCESS_POINT_ID", "1")))
    parser.add_argument("--populator-target-min-orders", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_TARGET_MIN_ORDERS", "20")))
    parser.add_argument("--populator-target-max-orders", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_TARGET_MAX_ORDERS", "80")))
    parser.add_argument("--populator-price-jitter-pct", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_PRICE_JITTER_PCT", "20")))
    parser.add_argument("--populator-expiry-min-seconds", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRY_MIN_SECONDS", "3600")))
    parser.add_argument("--populator-expiry-max-seconds", type=int, default=int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRY_MAX_SECONDS", "86400")))
    parser.add_argument("--populator-expire-probability", type=float, default=float(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_EXPIRE_PROBABILITY", "0.10")))
    parser.add_argument("--populator-force-count", type=int)
    parser.add_argument("--populator-force-price", type=int)
    parser.add_argument("--dry-run", action="store_true", default=env_bool("DUNE_ARTIFICIAL_EXCHANGE_DRY_RUN", env_bool("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_DRY_RUN", True)))
    parser.add_argument("--apply", dest="dry_run", action="store_false")
    args = parser.parse_args()
    log_event(
        "bot-start",
        argv=sys.argv[1:],
        dryRun=args.dry_run,
        loop=args.loop,
        populateLoop=args.populate_loop,
        exchangeId=args.exchange_id,
    )
    if args.settlement_report:
        print(json.dumps(print_settlement_report(args), indent=2, default=str))
        return
    if args.check_ready:
        print(json.dumps(readiness_check(args), indent=2, default=str))
        return
    if args.claim_settlement is not None:
        print(json.dumps(claim_settlement_once(args), indent=2, default=str))
        return
    if args.claim_all_settlements:
        print(json.dumps(claim_all_settlements(args), indent=2, default=str))
        return
    if args.validate_populator_once:
        print(json.dumps(validate_populator_once(args), indent=2, default=str))
        return
    if args.expire_seeded and not (args.populate_once or args.populate_loop):
        print(json.dumps(expire_seeded_once(args), indent=2, default=str))
        return
    if args.loop and not args.dry_run and args.buyer_controller_id <= 0:
        raise RuntimeError("--buyer-controller-id is required for buyer apply mode")
    if args.populate_loop and args.loop:
        iteration = 0
        while True:
            iteration += 1
            try:
                log_event("loop-iteration-start", mode="combined", iteration=iteration)
                result = {"populate": populate_once(args), "buyer": scan_once(args)}
                print(json.dumps({"event": "loop-result", "mode": "combined", "iteration": iteration, "result": result}, sort_keys=True, default=str), flush=True)
            except Exception as exc:
                log_failure("loop-iteration-failed", exc, mode="combined", iteration=iteration)
                raise
            sleep_min = int(env("DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MIN_SECONDS", "180"))
            sleep_max = int(env("DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MAX_SECONDS", "420"))
            sleep_seconds = random.randint(sleep_min, max(sleep_min, sleep_max))
            log_event("loop-sleep", mode="combined", iteration=iteration, seconds=sleep_seconds)
            time.sleep(sleep_seconds)
        return
    if args.populate_once or args.populate_loop:
        iteration = 0
        while True:
            iteration += 1
            try:
                log_event("loop-iteration-start", mode="populator", iteration=iteration)
                result = populate_once(args)
                print(json.dumps({"event": "loop-result", "mode": "populator", "iteration": iteration, "result": result}, sort_keys=True, default=str), flush=True)
            except Exception as exc:
                log_failure("loop-iteration-failed", exc, mode="populator", iteration=iteration)
                raise
            if not args.populate_loop:
                break
            sleep_min = int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_INTERVAL_MIN_SECONDS", env("DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MIN_SECONDS", "180")))
            sleep_max = int(env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_INTERVAL_MAX_SECONDS", env("DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MAX_SECONDS", "420")))
            sleep_seconds = random.randint(sleep_min, max(sleep_min, sleep_max))
            log_event("loop-sleep", mode="populator", iteration=iteration, seconds=sleep_seconds)
            time.sleep(sleep_seconds)
        return
    if args.fund_buyer:
        print(json.dumps(fund_buyer(args), indent=2, default=str))
        return
    if not args.dry_run and args.buyer_controller_id <= 0:
        raise RuntimeError("--buyer-controller-id is required for apply mode")
    iteration = 0
    while True:
        iteration += 1
        try:
            log_event("loop-iteration-start", mode="buyer", iteration=iteration)
            result = scan_once(args)
            print(json.dumps({"event": "loop-result", "mode": "buyer", "iteration": iteration, "result": result}, sort_keys=True, default=str), flush=True)
        except Exception as exc:
            log_failure("loop-iteration-failed", exc, mode="buyer", iteration=iteration)
            raise
        if not args.loop:
            break
        sleep_min = int(env("DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MIN_SECONDS", "180"))
        sleep_max = int(env("DUNE_ARTIFICIAL_EXCHANGE_SCAN_INTERVAL_MAX_SECONDS", "420"))
        sleep_seconds = random.randint(sleep_min, max(sleep_min, sleep_max))
        log_event("loop-sleep", mode="buyer", iteration=iteration, seconds=sleep_seconds)
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_failure("bot-fatal", exc)
        print(f"error: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
