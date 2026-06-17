#!/usr/bin/env python3
"""Prune broken seeded Exchange listings.

Two classes of seeded NPC listing are non-functional on purchase and should be
removed until their delivery is solved:

- schematics/recipes/patents: there is no relational known-recipes table on this
  server build (recipe/pattern unlock lives in encrypted_player_state), so a
  purchased schematic item grants nothing. These are pulled until a genuine
  learnable payload is proven (see docs/artificial-exchange.md, recipe section).
- empty-stats stateful gear: armor/weapons/vehicle items seeded with an empty
  items.stats payload materialize as base/grade-0 duds. These match the
  "package that does nothing" player report.

This tool reuses the audited deletion primitive in artificial-exchange-bot.py
(delete_seeded_orders) so deletion stays scoped to exchange + populator owner +
is_npc_order=true and cascades to the backing exchange-inventory item.

Dry-run by default. Live pruning requires --apply and the confirmation phrase.
"""
import argparse
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "artificial_exchange_bot", ROOT / "scripts" / "artificial-exchange-bot.py"
)
bot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot)

CONFIRM = "PRUNE ARTIFICIAL EXCHANGE"


def is_schematic_order(row, catalog_row):
    category = str((catalog_row or {}).get("category") or "")
    if bot.is_blueprint_category(category):
        return True
    template = str(row.get("template_id") or "")
    return bool(bot.re.search(r"schematic|patent|blueprint", template, bot.re.IGNORECASE))


def classify(conn, args, catalog):
    with conn.cursor() as cur:
        cur.execute(
            """
            select o.id, o.template_id, o.category_mask, o.category_depth, o.item_price,
                   coalesce(i.stats, '{}'::jsonb) = '{}'::jsonb as empty_stats
            from dune.dune_exchange_orders o
            left join dune.items i on i.id = o.item_id
            where o.exchange_id = %s
              and o.owner_id = %s
              and o.is_npc_order = true
            order by o.id
            limit %s
            """,
            (args.exchange_id, args.populator_owner_id, args.limit),
        )
        rows = [dict(r) for r in cur.fetchall()]

    target_templates = {t.strip() for t in (args.template_ids or "").split(",") if t.strip()}
    target_masks = {int(m.strip()) for m in (args.category_masks or "").split(",") if m.strip()}
    schematic_ids, empty_gear_ids = [], []
    by_reason_category = {}
    for row in rows:
        catalog_row = catalog.get(row.get("template_id")) or {}
        category = catalog_row.get("category") or "unknown"
        reason = None
        if target_templates and row.get("template_id") in target_templates:
            schematic_ids.append(int(row["id"]))
            reason = "template-id"
        elif target_masks and int(row.get("category_mask") or -1) in target_masks:
            schematic_ids.append(int(row["id"]))
            reason = "category-mask"
        elif args.mode in ("schematics", "both") and is_schematic_order(row, catalog_row):
            schematic_ids.append(int(row["id"]))
            reason = "schematic"
        elif (
            args.mode in ("empty-stateful", "both")
            and row.get("empty_stats")
            and bot.populator_requires_stats(catalog_row)
        ):
            empty_gear_ids.append(int(row["id"]))
            reason = "empty-stateful-gear"
        if reason:
            bucket = by_reason_category.setdefault((reason, category), 0)
            by_reason_category[(reason, category)] = bucket + 1
    return rows, schematic_ids, empty_gear_ids, by_reason_category


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["schematics", "empty-stateful", "both"], default="both")
    parser.add_argument("--template-ids", default="", help="Comma-separated template_ids to prune outright (e.g. moving them to a new category bucket). Combined with --mode.")
    parser.add_argument("--category-masks", default="", help="Comma-separated category_mask ints to prune outright (e.g. re-pricing a whole commodity bucket). Combined with --mode.")
    parser.add_argument("--exchange-id", type=int, default=int(bot.env("DUNE_ARTIFICIAL_EXCHANGE_EXCHANGE_ID", "2")))
    parser.add_argument("--populator-owner-id", type=int, default=int(bot.env("DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID", "0")))
    parser.add_argument("--catalog", default=str(bot.CATALOG_PATH))
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    if args.populator_owner_id <= 0:
        raise SystemExit("--populator-owner-id (or DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID) is required")

    catalog = bot.load_catalog(pathlib.Path(args.catalog))
    conn = bot.connect_db()
    conn.autocommit = False
    try:
        rows, schematic_ids, empty_gear_ids, breakdown = classify(conn, args, catalog)
        target_ids = sorted(set(schematic_ids) | set(empty_gear_ids))
        summary = {
            "mode": args.mode,
            "exchangeId": args.exchange_id,
            "ownerId": args.populator_owner_id,
            "scannedSeededOrders": len(rows),
            "schematicOrders": len(schematic_ids),
            "emptyStatefulGearOrders": len(empty_gear_ids),
            "totalTargeted": len(target_ids),
            "breakdownByReasonCategory": {f"{r}|{c}": n for (r, c), n in sorted(breakdown.items())},
        }
        if not args.apply:
            summary["dryRun"] = True
            conn.rollback()
        else:
            if args.confirm != CONFIRM:
                raise SystemExit(f"live prune requires --confirm '{CONFIRM}'")
            with conn.cursor() as cur:
                deleted = bot.delete_seeded_orders(cur, target_ids, args.exchange_id, args.populator_owner_id)
            conn.commit()
            summary["dryRun"] = False
            summary["deletedOrders"] = len(deleted)
        print(json.dumps(summary, indent=2, default=str))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
