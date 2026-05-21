#!/usr/bin/env python3
import argparse
import json
import pathlib
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from exchange_category_map import EXCHANGE_CATEGORY_MASKS

DEFAULT_OUTPUT = ROOT / "backups" / "admin-panel" / "artificial-exchange" / "source-category-map.json"
API = "https://api.awakening.wiki/items"
CATEGORY_MASKS = EXCHANGE_CATEGORY_MASKS


def api_get(offset, limit):
    query = urllib.parse.urlencode({
        "limit": limit,
        "offset": offset,
        "sort": "item_id",
        "fields": "item_id,name,item_tags,unique_schematic,weapon_type,utility_type",
    })
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": "DASH exchange category mapper"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def tags_for(item):
    try:
        return [str(tag) for tag in json.loads(item.get("item_tags") or "[]")]
    except json.JSONDecodeError:
        return []


def category_from_tags(item):
    tags = tags_for(item)
    if any(tag == "Items.ExcludeFromExchange" for tag in tags):
        return None, "excluded-from-exchange"
    for tag in tags:
        if tag.startswith("Items.Schematics."):
            if ".Deployables." in tag:
                return "schematics/vehicles", tag
            if ".Clothes." in tag:
                return "schematics/armor", tag
            if ".RangedWeapons." in tag or ".MeleeWeapons." in tag or ".UtilityTools." in tag:
                return "schematics/weapons", tag
            return None, f"unmapped-schematic-tag:{tag}"
    for tag in tags:
        if tag.startswith("Items.Holsters.Deployables.VehicleBase.Sandbike") or tag.startswith("Items.Holsters.Deployables.VehicleExtra.Sandbike"):
            return "vehicles/sandbike", tag
        if "LightOrni" in tag or "MediumOrni" in tag or "Ornithopter" in tag:
            return "vehicles/ornithopter", tag
        if tag.startswith("Items.Holsters.Deployables."):
            return "vehicles/parts", tag
        if tag.startswith("Items.Holsters.RangedWeapons.") or tag.startswith("Items.Ammo."):
            return "weapons/ranged", tag
        if tag.startswith("Items.Holsters.MeleeWeapons."):
            return "weapons/melee", tag
        if tag.startswith("Items.Clothes.Stillsuit"):
            return "armor/stillsuit", tag
        if tag.startswith("Items.Clothes.Social"):
            return "armor/social", tag
        if tag.startswith("Items.Clothes."):
            return "armor/combat", tag
        if tag.startswith("Items.RefinedResources."):
            return "resources/refined", tag
        if tag.startswith("Items.RawResources."):
            return "resources/raw", tag
        if tag.startswith("Items.CraftedResources.") or tag == "Loot.Component":
            return "resources/components", tag
        if tag.startswith("Items.Consumables.Health") or tag.startswith("Items.Consumables.Spice") or tag == "Items.Consumables":
            return "consumables/medical", tag
        if tag.startswith("Items.UtilityTools.Mining") or tag.startswith("Items.Holsters.MiningTools"):
            return "tools/mining", tag
        if tag.startswith("Items.UtilityTools.") or tag.startswith("Items.Holsters.UtilityTools") or tag.startswith("Items.Holsters.BuildingTools"):
            return "tools/utility", tag
        if tag.startswith("Items.Contract"):
            return "contracts", tag
        if tag.startswith("Items.Customization"):
            return "customization", tag
        if tag == "Items.Consumables.BuildableSets":
            return "building/patents", tag
    item_id = str(item.get("item_id") or "")
    if item_id.endswith("_Patent") or "Patent" in str(item.get("name") or ""):
        return "building/patents", "item_id/name patent"
    return None, "unmapped-tags"


def fetch_items(limit):
    offset = 0
    while True:
        payload = api_get(offset, limit)
        rows = payload.get("list") or []
        if not rows:
            break
        yield from rows
        page = payload.get("pageInfo") or payload.get("PageInfo") or {}
        if page.get("isLastPage"):
            break
        offset += len(rows)


def main():
    parser = argparse.ArgumentParser(description="Build a source-backed item category map from awakening.wiki game-file tags.")
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    items = {}
    skipped = {}
    for item in fetch_items(args.limit):
        template_id = str(item.get("item_id") or "").strip()
        if not template_id:
            continue
        category, source = category_from_tags(item)
        if not category:
            skipped[source] = skipped.get(source, 0) + 1
            continue
        mask, depth = CATEGORY_MASKS[category]
        items[template_id] = {
            "template_id": template_id,
            "display_name": str(item.get("name") or template_id).strip(),
            "category": category,
            "category_mask": mask,
            "category_depth": depth,
            "source": "awakening.wiki:item_tags",
            "source_detail": source,
            "item_tags": tags_for(item),
        }

    payload = {
        "generatedAt": int(time.time()),
        "source": API,
        "sourceMode": "awakening.wiki item_tags",
        "items": items,
        "skipped": skipped,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output), "items": len(items), "skipped": skipped}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
