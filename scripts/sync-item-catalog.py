#!/usr/bin/env python3
"""Build DASH's compact visual item catalog from the Community Wiki API."""
import argparse
import csv
import json
import pathlib
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
ITEM_API = "https://api.awakening.wiki/items"
WIKI_API = "https://awakening.wiki/api.php"
OUTPUT = ROOT / "config" / "item-catalog.json"


def get_json(url, params):
    request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "DASH item catalog/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def prices():
    path = ROOT / "config" / "artificial-exchange-prices.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return {row["template_id"]: row for row in csv.DictReader(fh)}


def tags(raw):
    try:
        return json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []


def positive_int(value, default=1):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def resolve_images(names):
    resolved = {}
    names = sorted(set(filter(None, names)))
    for start in range(0, len(names), 50):
        batch = names[start:start + 50]
        payload = get_json(WIKI_API, {"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url", "titles": "|".join(f"File:{name}" for name in batch)})
        for page in (payload.get("query", {}).get("pages", {}) or {}).values():
            info = page.get("imageinfo") or []
            if info:
                url = info[0].get("url", "")
                resolved[urllib.parse.unquote(pathlib.PurePosixPath(urllib.parse.urlparse(url).path).name)] = url
    return resolved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    rows, offset = [], 0
    fields = "item_id,name,image,max_stack,short_description,long_description,item_tags,weapon_type,utility_type,vehicle_module_type"
    while True:
        payload = get_json(ITEM_API, {"limit": args.limit, "offset": offset, "sort": "item_id", "fields": fields})
        page = payload.get("list") or []
        if not page:
            break
        rows.extend(page)
        if (payload.get("pageInfo") or {}).get("isLastPage"):
            break
        offset += len(page)
    image_urls = resolve_images(row.get("image") for row in rows)
    price_rows = prices()
    items = []
    for row in rows:
        template = str(row.get("item_id") or "").strip()
        if not template:
            continue
        price = price_rows.get(template, {})
        item_tags = tags(row.get("item_tags"))
        tier = next((tag.split(".", 1)[1] for tag in item_tags if str(tag).startswith("LootTier.")), "")
        items.append({
            "templateId": template,
            "name": str(row.get("name") or template),
            "imageUrl": image_urls.get(row.get("image"), ""),
            "category": price.get("category", "unknown"),
            "tier": tier,
            "maxStack": positive_int(row.get("max_stack")),
            "description": row.get("short_description") or row.get("long_description") or "",
            "kind": row.get("weapon_type") or row.get("utility_type") or row.get("vehicle_module_type") or "",
        })
    items.sort(key=lambda item: (item["category"], item["name"].lower(), item["templateId"]))
    output = {"schemaVersion": 1, "generatedAt": int(time.time()), "source": {"label": "Dune: Awakening Community Wiki", "url": "https://awakening.wiki/"}, "items": items}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output), "items": len(items), "images": sum(bool(item["imageUrl"]) for item in items)}, indent=2))


if __name__ == "__main__":
    main()
