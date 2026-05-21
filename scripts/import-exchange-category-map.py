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


def has_tag(tags, prefix):
    return any(tag == prefix or tag.startswith(f"{prefix}.") for tag in tags)


def vehicle_category_from_tags(tags):
    if any("VehicleBase.Sandbike" in tag or "VehicleExtra.Sandbike" in tag or "VehicleBase.Treadwheel" in tag or "VehicleExtra.Treadwheel" in tag for tag in tags):
        return "vehicles/sandbike"
    if any("VehicleBase.Buggy" in tag or "VehicleExtra.Buggy" in tag for tag in tags):
        return "vehicles/buggy"
    if any("LightOrni" in tag for tag in tags):
        return "vehicles/light_ornithopter"
    if any("MediumOrni" in tag for tag in tags):
        return "vehicles/medium_ornithopter"
    if any("TransportOrni" in tag for tag in tags):
        return "vehicles/transport_ornithopter"
    if any("Sandcrawler" in tag for tag in tags):
        return "vehicles/sandcrawler"
    return None


def armor_category_from_tags(tags):
    if has_tag(tags, "Items.Clothes.Stillsuit"):
        return "armor/stillsuit"
    if has_tag(tags, "Items.Clothes.Social"):
        return "armor/social"
    if has_tag(tags, "Items.Clothes.HeavyArmor"):
        return "armor/heavy"
    if has_tag(tags, "Items.Clothes.ScoutArmor") or has_tag(tags, "Items.Clothes.LightArmor") or has_tag(tags, "Items.Clothes.AssaultArmor"):
        return "armor/light"
    if has_tag(tags, "Items.Clothes"):
        return "armor/combat"
    return None


def schematic_category_from_identity(item, tags):
    item_id = str(item.get("item_id") or "").lower()
    name = str(item.get("name") or "").lower()
    text = f"{item_id} {name}"

    if "socialclothing" in text or "social clothing" in text:
        return "schematics/armor/social"
    if "consumables_spice" in text or "spiced food" in text or "spiced drink" in text:
        return "schematics/utility"
    if any(token in text for token in ("respawnbeacon", "respawn beacon", "stilltent", "still tent")):
        return "schematics/utility/deployables"
    if any(token in text for token in ("dewreaper", "dew reaper", "bloodsack", "bloodbag", "bodyfluidextractor", "exsanguination")):
        return "schematics/utility/hydration"
    if any(token in text for token in ("miningtool", "cutteray", "cutter ray", "cutterray", "cutter ")):
        return "schematics/utility/gathering"
    if any(token in text for token in ("scanner", "surveyprobe", "survey probe", "seismicprobe", "sesmicprobe", "seismic probe", "hand scanner")):
        return "schematics/utility/cartography"
    return None


def schematic_category_from_tags(item, tags):
    identity_category = schematic_category_from_identity(item, tags)
    if identity_category:
        return identity_category
    if has_tag(tags, "Items.Schematics.Augments"):
        return "schematics/augments"
    if has_tag(tags, "Items.Schematics.Clothes.Stillsuit"):
        return "schematics/armor/stillsuit"
    if has_tag(tags, "Items.Schematics.Clothes.Social"):
        return "schematics/armor/social"
    if has_tag(tags, "Items.Schematics.Clothes.HeavyArmor"):
        return "schematics/armor/heavy"
    if has_tag(tags, "Items.Schematics.Clothes.ScoutArmor") or has_tag(tags, "Items.Schematics.Clothes.LightArmor") or has_tag(tags, "Items.Schematics.Clothes.AssaultArmor"):
        return "schematics/armor/light"
    if has_tag(tags, "Items.Schematics.Clothes"):
        return "schematics/armor"
    if has_tag(tags, "Items.Schematics.MeleeWeapons"):
        return "schematics/weapons/melee"
    if has_tag(tags, "Items.Schematics.RangedWeapons"):
        return "schematics/weapons/ranged"
    if has_tag(tags, "Items.Schematics.UtilityTools.HydrationTools") or has_tag(tags, "Items.Schematics.HydrationTools"):
        return "schematics/utility/hydration"
    if has_tag(tags, "Items.Schematics.UtilityTools.GatheringTools") or has_tag(tags, "Items.Schematics.GatheringTools"):
        return "schematics/utility/gathering"
    if has_tag(tags, "Items.Schematics.UtilityTools.CartographyTools") or has_tag(tags, "Items.Schematics.CartographyTools"):
        return "schematics/utility/cartography"
    if has_tag(tags, "Items.Schematics.Deployables") or any(".Deployables." in tag for tag in tags):
        vehicle_category = vehicle_category_from_tags(tags)
        if vehicle_category:
            return "schematics/" + vehicle_category
        return "schematics/utility/deployables"
    if has_tag(tags, "Items.Schematics.UtilityTools"):
        return "schematics/utility"
    return None


def category_from_identity(item):
    item_id = str(item.get("item_id") or "").lower()
    name = str(item.get("name") or "").lower()
    text = f"{item_id} {name}"

    if any(token in text for token in ("dewreaper", "dew reaper", "bodyfluidextractor", "bloodsack", "bloodbag")):
        return "tools/hydration", "item_id/name hydration tool"
    if any(token in text for token in ("miningtool", "cutteray", "cutter ray", "cutterray")):
        return "tools/gathering", "item_id/name gathering tool"
    if any(token in text for token in ("scanner", "surveyprobe", "survey probe", "seismicprobe", "sesmicprobe", "seismic probe", "hand scanner")):
        return "tools/cartography", "item_id/name cartography tool"
    if any(token in text for token in ("respawnbeacon", "respawn beacon", "stilltent", "still tent")):
        return "tools/deployables", "item_id/name deployable"
    return None, None


def category_from_tags(item):
    tags = tags_for(item)
    if any(tag == "Items.ExcludeFromExchange" for tag in tags):
        return None, "excluded-from-exchange"
    for tag in tags:
        if tag.startswith("Items.Schematics."):
            category = schematic_category_from_tags(item, tags)
            if category:
                return category, tag
            return None, f"unmapped-schematic-tag:{tag}"
    identity_category, identity_source = category_from_identity(item)
    if identity_category:
        return identity_category, identity_source
    for tag in tags:
        vehicle_category = vehicle_category_from_tags(tags)
        if vehicle_category:
            return vehicle_category, tag
        armor_category = armor_category_from_tags(tags)
        if armor_category:
            return armor_category, tag
        if tag.startswith("Items.Augment.Armor"):
            return "augments/armor", tag
        if tag.startswith("Items.Augment.Melee"):
            return "augments/melee", tag
        if tag.startswith("Items.Augment.Ranged"):
            return "augments/ranged", tag
        if tag.startswith("Items.Augment"):
            return "augments/misc", tag
        if tag.startswith("Items.Holsters.Deployables") or any(t.startswith("Items.Holsters.Deployables") for t in tags):
            return "tools/deployables", tag
        if tag.startswith("Items.Ammo."):
            if tag.startswith("Items.Ammo.Repair"):
                return "vehicles/ammunition", tag
            return "weapons/ammunition", tag
        if tag.startswith("Items.Holsters.RangedWeapons."):
            return "weapons/ranged", tag
        if tag.startswith("Items.Holsters.MeleeWeapons."):
            return "weapons/melee", tag
        if tag.startswith("Items.RawResources.Fuel") or tag.startswith("Items.RawResources.SolidFuel") or tag.startswith("Items.RefinedResources.Fuel"):
            return "resources/fuel", tag
        if tag.startswith("Items.RefinedResources."):
            return "resources/refined", tag
        if tag.startswith("Items.RawResources."):
            return "resources/raw", tag
        if tag.startswith("Items.CraftedResources.") or tag == "Loot.Component":
            return "resources/components", tag
        if tag.startswith("Items.Consumables.Spice"):
            return "consumables/spice", tag
        if tag.startswith("Items.Consumables.Health") or tag.startswith("Items.Consumables.Spice") or tag == "Items.Consumables":
            return "consumables/medical", tag
        if tag.startswith("Items.Holsters.HydrationTools") or tag.startswith("Items.UtilityTools.HydrationTools"):
            return "tools/hydration", tag
        if tag.startswith("Items.Holsters.GatheringTools") or tag.startswith("Items.UtilityTools.GatheringTools"):
            return "tools/gathering", tag
        if tag.startswith("Items.Holsters.CartographyTools") or tag.startswith("Items.UtilityTools.CartographyTools") or tag.startswith("Items.Maps"):
            return "tools/cartography", tag
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
