#!/usr/bin/env python3
import argparse
import csv
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "exchange-price-snapshots" / "awakening-wiki-items.csv"
API = "https://api.awakening.wiki/items"

FIELDS = [
    "template_id",
    "display_name",
    "category",
    "category_mask",
    "category_depth",
    "sellable_status",
    "baseline_price",
    "max_buy_price",
    "liquidity_tier",
    "enabled",
    "source",
    "confidence",
    "notes",
]

SUBCATEGORIES = {
    "resources/raw": (0x01010000, 2),
    "resources/refined": (0x01020000, 2),
    "resources/components": (0x01030000, 2),
    "consumables/medical": (0x02010000, 2),
    "tools/mining": (0x03010000, 2),
    "tools/utility": (0x03020000, 2),
    "weapons/melee": (0x04010000, 2),
    "weapons/ranged": (0x04020000, 2),
    "armor/combat": (0x05010000, 2),
    "armor/stillsuit": (0x05020000, 2),
    "armor/social": (0x05030000, 2),
    "vehicles/sandbike": (0x06010000, 2),
    "vehicles/ornithopter": (0x06020000, 2),
    "vehicles/parts": (0x06030000, 2),
    "schematics/weapons": (0x07010000, 2),
    "schematics/armor": (0x07020000, 2),
    "schematics/vehicles": (0x07030000, 2),
    "building/placeables": (0x08010000, 2),
    "building/patents": (0x08020000, 2),
    "contracts": (0x09010000, 2),
    "customization": (0x0A010000, 2),
    "unknown": (0, 0),
}


def api_get(params):
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "DASH exchange catalog importer"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_number(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return max(1, int(round(number)))


def tags_for(item):
    raw = item.get("item_tags")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(tag) for tag in parsed]


def category_for(item):
    item_id = str(item.get("item_id") or "")
    low_id = item_id.lower()
    tags = tags_for(item)
    low_tags = " ".join(tags).lower()
    name = str(item.get("name") or "").lower()
    haystack = f"{low_id} {low_tags} {name}"

    if "patent" in haystack:
        return "building/patents"
    if "schematic" in low_id or "items.schematics" in low_tags:
        if any(token in haystack for token in ("vehicle", "sandbike", "ornithopter", "crawler")):
            return "schematics/vehicles"
        if any(token in haystack for token in ("garment", "armor", "stillsuit", "combat_", "social_")):
            return "schematics/armor"
        return "schematics/weapons"
    if "building" in low_tags or "placeable" in low_tags:
        return "building/placeables"
    if "contract" in low_tags or "contract" in low_id:
        return "contracts"
    if "customization" in low_tags or "swatch" in low_id or "dye" in low_id:
        return "customization"
    if any(token in low_id for token in ("d_utility_", "utility_")) and any(token in name for token in ("boots", "pants", "gloves", "helmet", "jacket", "robe", "mask", "shoes", "hood", "apron")):
        return "armor/combat"
    if "stillsuit" in haystack:
        return "armor/stillsuit"
    if "social_" in low_id or "clothing.social" in low_tags:
        return "armor/social"
    if "garment" in low_tags or "armor" in low_tags or "combat_" in low_id:
        return "armor/combat"
    if "sandbike" in haystack:
        return "vehicles/sandbike"
    if "ornithopter" in haystack:
        return "vehicles/ornithopter"
    if "vehicle" in low_tags or any(token in haystack for token in ("sandcrawler", "buggy", "tank")):
        return "vehicles/parts"
    if item.get("weapon_type") == "melee" or any(token in haystack for token in ("kindjal", "dirk", "sword", "rapier", "knife", "blade")):
        return "weapons/melee"
    if item.get("weapon_type") == "ranged" or any(token in haystack for token in ("pistol", "smg", "rifle", "carbine", "scattergun", "lmg", "dart", "ammo", "disruptor", "lasgun")):
        return "weapons/ranged"
    if item.get("utility_type") or any(token in haystack for token in ("powerpack", "binocular", "survey", "shield", "suspensor", "beacon")):
        return "tools/utility"
    if any(token in haystack for token in ("miningtool", "cutter", "compactor", "bodyfluidextractor", "repairtool", "dewreaper")):
        return "tools/mining"
    if any(token in haystack for token in ("healthpack", "bloodsack", "literjon", "decajon", "detox", "consumable")):
        return "consumables/medical"
    if any(token in haystack for token in ("bar", "ingot", "paste", "lubricant", "filter", "fuelcanister", "silicone", "plastone", "flour")):
        return "resources/refined"
    if any(token in haystack for token in ("component", "part", "dust", "capacitor", "actuator", "core", "plating", "rangefinder", "welding", "servok")):
        return "resources/components"
    if any(token in haystack for token in ("ore", "stone", "fiber", "plant", "corpse", "spice", "seed", "flour", "raw")):
        return "resources/raw"
    return "unknown"


def tier_for(item):
    tags = tags_for(item)
    for tag in tags:
        match = re.fullmatch(r"LootTier\.(\d+)", tag)
        if match:
            return match.group(1)
    return ""


def row_for(item, args):
    template_id = str(item.get("item_id") or "").strip()
    category = category_for(item)
    mask, depth = SUBCATEGORIES[category]
    market_price = parse_number(item.get("market_price"))
    vendor_price = parse_number(item.get("base_vendor_price"))
    price = market_price or vendor_price
    if price is None:
        price = 1
    price_source = "market_price" if market_price else "base_vendor_price" if vendor_price else "missing_price_default"
    tier = tier_for(item)
    notes = [
        "imported from awakening.wiki API game-file data",
        f"price_source={price_source}",
    ]
    if tier:
        notes.append(f"tier={tier}")
    if item.get("unique_schematic"):
        notes.append("unique_schematic=yes")
    return {
        "template_id": template_id,
        "display_name": str(item.get("name") or template_id).strip(),
        "category": category,
        "category_mask": mask,
        "category_depth": depth,
        "sellable_status": args.sellable_status,
        "baseline_price": price,
        "max_buy_price": max(1, int(price * 0.8)),
        "liquidity_tier": "low",
        "enabled": "true" if args.enabled else "false",
        "source": args.source,
        "confidence": args.confidence or ("moderate" if market_price or vendor_price else "low"),
        "notes": "; ".join(notes),
    }


def fetch_items(limit):
    offset = 0
    while True:
        payload = api_get({
            "limit": limit,
            "offset": offset,
            "sort": "item_id",
            "fields": "item_id,name,item_tags,market_price,base_vendor_price,unique_schematic,weapon_type,utility_type",
        })
        rows = payload.get("list") or []
        if not rows:
            break
        yield from rows
        page = payload.get("pageInfo") or payload.get("PageInfo") or {}
        if page.get("isLastPage"):
            break
        offset += len(rows)


def main():
    parser = argparse.ArgumentParser(description="Import Dune: Awakening item prices from the Community Wiki API.")
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--enabled", action="store_true", help="write imported rows as enabled for population/buying")
    parser.add_argument("--sellable-status", default="known", choices=["known", "observed", "validated"])
    parser.add_argument("--source", default="awakening-wiki-game-files")
    parser.add_argument("--confidence", choices=["low", "moderate", "high"])
    args = parser.parse_args()

    seen = set()
    rows = []
    for item in fetch_items(args.limit):
        template_id = str(item.get("item_id") or "").strip()
        if not template_id or template_id in seen:
            continue
        seen.add(template_id)
        rows.append(row_for(item, args))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({
        "ok": True,
        "output": str(args.output),
        "items": len(rows),
        "enabled": sum(1 for row in rows if row["enabled"] == "true"),
        "source": API,
        "generatedAt": int(time.time()),
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
