#!/usr/bin/env python3
import csv
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from exchange_category_map import EXCHANGE_CATEGORY_MASKS

CATALOG_SCRIPT = ROOT / "scripts" / "build-exchange-catalog.py"
OUTPUT = ROOT / "config" / "artificial-exchange-prices.csv"

spec = importlib.util.spec_from_file_location("catalog_builder", CATALOG_SCRIPT)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)

SUBCATEGORIES = {
    key: EXCHANGE_CATEGORY_MASKS[key]
    for key in (
        "resources/raw",
        "resources/refined",
        "resources/components",
        "consumables/medical",
        "tools/mining",
        "tools/utility",
        "weapons/melee",
        "weapons/ranged",
        "armor/combat",
        "armor/stillsuit",
        "armor/social",
        "vehicles/sandbike",
        "vehicles/ornithopter",
        "vehicles/parts",
        "schematics/weapons",
        "schematics/armor",
        "schematics/vehicles",
    )
}

PRICE_HINTS = {
    "resources/raw": 25,
    "resources/refined": 150,
    "resources/components": 350,
    "consumables/medical": 100,
    "tools/mining": 450,
    "tools/utility": 450,
    "weapons/melee": 500,
    "weapons/ranged": 650,
    "armor/combat": 600,
    "armor/stillsuit": 550,
    "armor/social": 250,
    "vehicles/sandbike": 900,
    "vehicles/ornithopter": 1800,
    "vehicles/parts": 1000,
    "schematics/weapons": 2500,
    "schematics/armor": 2200,
    "schematics/vehicles": 3000,
}

SKIP_PATTERNS = [
    r"^Emote_",
    r"^Contract",
    r"SolarisCoin$",
    r"Swatch$",
    r"Dyepack",
    r"BuildingBlueprint",
    r"^t2tsp$",
    r"^ogv",
]


def should_skip(template_id):
    return any(re.search(pattern, template_id) for pattern in SKIP_PATTERNS)


def classify(template_id):
    tid = template_id
    low = tid.lower()
    if should_skip(tid):
        return None
    if "schematic" in low:
        if any(token in low for token in ("sandbike", "ornithopter", "crawler")):
            return "schematics/vehicles"
        if "combat_" in low or "stillsuit" in low or "armor" in low:
            return "schematics/armor"
        return "schematics/weapons"
    if "stillsuit" in low:
        return "armor/stillsuit"
    if "social_" in low:
        return "armor/social"
    if "combat_" in low:
        return "armor/combat"
    if "sandbike" in low:
        return "vehicles/sandbike"
    if "ornithopter" in low:
        return "vehicles/ornithopter"
    if any(token in low for token in ("vehicle", "sandcrawler")):
        return "vehicles/parts"
    if any(token in low for token in ("miningtool", "cutter", "bodyfluidextractor", "repairtool")):
        return "tools/mining"
    if any(token in low for token in ("powerpack", "binocular", "surveyprobe", "beacon", "backup", "glide", "shield")):
        return "tools/utility"
    if any(token in low for token in ("knife", "kindjal", "dirk", "sword", "rapier", "blade")):
        return "weapons/melee"
    if any(token in low for token in ("pistol", "smg", "rifle", "carbine", "scattergun", "lmg", "dart", "ammo", "ar2", "flamethrower")):
        return "weapons/ranged"
    if any(token in low for token in ("bar", "ingot", "paste", "lubricant", "filter", "fuel_cell", "fuelcanister", "silicone", "plastone")):
        return "resources/refined"
    if any(token in low for token in ("component", "part", "dust", "capacitor", "actuator", "core", "plating", "rangefinder", "welding", "powerregulator", "servok")):
        return "resources/components"
    if any(token in low for token in ("healthpack", "bloodsack", "literjon", "decajon", "detox", "spiceaddiction")):
        return "consumables/medical"
    if any(token in low for token in ("ore", "stone", "fiber", "plant", "corpse", "spice", "flour", "fuelcell")):
        return "resources/raw"
    return None


def observed_templates(limit_per_category):
    conn = catalog.connect_db()
    grouped = {}
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            select template_id, count(*) as observed_count
            from (
                select template_id from dune.items where template_id is not null
                union all
                select template_id from dune.vehicle_modules where template_id is not null
                union all
                select template_id from dune.landsraad_house_rewards where template_id is not null
                union all
                select template_id from dune.landsraad_task_rewards where template_id is not null
            ) t
            group by template_id
            order by observed_count desc, template_id
            """
        )
        for row in cur.fetchall():
            template_id = row["template_id"]
            category = classify(template_id)
            if not category:
                continue
            bucket = grouped.setdefault(category, [])
            if len(bucket) < limit_per_category:
                bucket.append((template_id, int(row["observed_count"])))
    conn.close()
    return grouped


def row_for(category, template_id, observed_count):
    mask, depth = SUBCATEGORIES[category]
    price = PRICE_HINTS[category]
    if re.search(r"_[456](?:_|$)", template_id) or re.search(r"T[456]", template_id):
        price *= 4
    elif re.search(r"_[23](?:_|$)", template_id) or re.search(r"T[23]", template_id):
        price *= 2
    return {
        "template_id": template_id,
        "display_name": template_id,
        "category": category,
        "category_mask": mask,
        "category_depth": depth,
        "sellable_status": "observed",
        "baseline_price": price,
        "max_buy_price": int(price * 0.8),
        "price_floor": price,
        "price_ceiling": price,
        "liquidity_tier": "medium",
        "enabled": "false",
        "source": "local-bootstrap",
        "confidence": "low",
        "notes": f"heuristic category and price; disabled until real price validation; observed_count={observed_count}",
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build a broad heuristic artificial Exchange catalog from local observed templates.")
    parser.add_argument("--limit-per-category", type=int, default=20)
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    parser.add_argument("--enable-heuristic-prices", action="store_true", help="write heuristic rows as enabled/validated; unsafe for live market seeding")
    args = parser.parse_args()

    grouped = observed_templates(args.limit_per_category)
    rows = []
    for category in sorted(SUBCATEGORIES):
        for template_id, observed_count in grouped.get(category, []):
            rows.append(row_for(category, template_id, observed_count))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=catalog.FIELDS)
        writer.writeheader()
        writer.writerow({
            "template_id": "PowerPack",
            "display_name": "PowerPack",
            "category": "tools/utility",
            "category_mask": SUBCATEGORIES["tools/utility"][0],
            "category_depth": SUBCATEGORIES["tools/utility"][1],
            "sellable_status": "validated" if args.enable_heuristic_prices else "observed",
            "baseline_price": 123,
            "max_buy_price": 123,
            "price_floor": 123,
            "price_ceiling": 123,
            "liquidity_tier": "high",
            "enabled": "true" if args.enable_heuristic_prices else "false",
            "source": "live-test",
            "confidence": "high" if args.enable_heuristic_prices else "low",
            "notes": "validated via order 5 live purchase and settlement; disabled by default after heuristic seed rollback",
        })
        for row in rows:
            if row["template_id"] != "PowerPack":
                if args.enable_heuristic_prices:
                    row = dict(row)
                    row["sellable_status"] = "validated"
                    row["enabled"] = "true"
                    row["confidence"] = "moderate"
                    row["notes"] = row["notes"].replace("disabled until real price validation; ", "")
                writer.writerow(row)
    print({"ok": True, "output": str(args.output), "categories": {key: len(grouped.get(key, [])) for key in sorted(SUBCATEGORIES)}, "rows": len(rows) + 1})


if __name__ == "__main__":
    main()
