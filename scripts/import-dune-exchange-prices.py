#!/usr/bin/env python3
import argparse
import csv
import json
import pathlib
import re
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "config" / "artificial-exchange-prices.csv"
API = "https://auctionscannerapi.azurewebsites.net/api/auction-history"


def norm(value):
    text = (value or "").lower()
    text = text.replace("mk ", "mk")
    text = text.replace("choam", "choam")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def parse_int(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def fetch_market(hours, server=""):
    url = f"{API}?hours={int(hours)}"
    if server:
        from urllib.parse import quote
        url += f"&server={quote(server)}"
    request = urllib.request.Request(url, headers={"User-Agent": "DASH dune.exchange price importer"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_market_rows(rows):
    latest = {}
    for row in rows:
        name = row.get("itemName")
        if not name:
            continue
        current = latest.get(name)
        if current is None or str(row.get("timestamp") or "") > str(current.get("timestamp") or ""):
            latest[name] = row
    return latest


def market_index(rows):
    index = {}
    for row in latest_market_rows(rows).values():
        names = {row.get("itemName") or "", row.get("baseName") or ""}
        item_name = row.get("itemName") or ""
        if item_name.endswith(" (Schematic)"):
            names.add(item_name.replace(" (Schematic)", " Schematic"))
        for name in names:
            key = norm(name)
            if key:
                index[key] = row
    return index


def choose_ceiling(row, market_row, price_field):
    value = market_row.get(price_field)
    if value in (None, ""):
        value = market_row.get("averagePrice")
    if value in (None, ""):
        value = market_row.get("lowestPrice")
    ceiling = parse_int(value)
    game_price = parse_int(row.get("price_floor") or row.get("baseline_price"), 1)
    return max(game_price, ceiling)


def midpoint_floor(game_price, market_price):
    game_price = max(1, int(game_price))
    market_price = max(game_price, int(market_price))
    return game_price + int(round((market_price - game_price) * 0.50))


def strip_price_notes(notes):
    prefixes = (
        "game_file_price=",
        "price_floor=",
        "price_ceiling=",
        "market_item=",
        "market_avg=",
        "market_low=",
        "market_high=",
        "market_listings=",
        "market_timestamp=",
    )
    kept = []
    for part in str(notes or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if any(part.startswith(prefix) for prefix in prefixes):
            continue
        kept.append(part)
    return "; ".join(kept)


def original_game_price(row):
    notes = str(row.get("notes") or "")
    match = re.search(r"(?:^|; )game_file_price=(\d+)(?:;|$)", notes)
    if match:
        return parse_int(match.group(1), 1)
    return parse_int(row.get("price_floor") or row.get("baseline_price"), 1)


def update_catalog(catalog_path, market_rows, price_field):
    with catalog_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    for field in ("price_floor", "price_ceiling"):
        if field not in fieldnames:
            anchor = "price_floor" if field == "price_ceiling" and "price_floor" in fieldnames else "max_buy_price"
            insert_at = fieldnames.index(anchor) + 1 if anchor in fieldnames else len(fieldnames)
            fieldnames.insert(insert_at, field)
    index = market_index(market_rows)
    matched = []
    for row in rows:
        game_price = original_game_price(row)
        key = norm(row.get("display_name") or row.get("template_id"))
        market = index.get(key)
        if not market and row.get("template_id", "").endswith("_Schematic"):
            market = index.get(norm((row.get("display_name") or "") + " Schematic"))
        if not market:
            floor = midpoint_floor(game_price, parse_int(row.get("price_ceiling") or game_price, game_price))
            row["price_floor"] = str(floor)
            row["price_ceiling"] = row.get("price_ceiling") or str(max(floor, game_price))
            continue
        ceiling = choose_ceiling(row, market, price_field)
        floor = midpoint_floor(game_price, ceiling)
        row["price_floor"] = str(floor)
        row["price_ceiling"] = str(ceiling)
        row["baseline_price"] = str(floor)
        row["max_buy_price"] = str(ceiling)
        row["source"] = "dune.exchange+midpoint-floor"
        row["confidence"] = "moderate"
        base_notes = strip_price_notes(row.get("notes", ""))
        row["notes"] = (
            f"{base_notes}; " if base_notes else ""
        ) + (
            f"game_file_price={game_price}; "
            "price_floor=50pct_between_game_file_and_dune_exchange; "
            f"price_ceiling=dune.exchange {price_field}; "
            f"market_item={market.get('itemName')}; "
            f"market_avg={market.get('averagePrice')}; "
            f"market_low={market.get('lowestPrice')}; "
            f"market_high={market.get('highestPrice')}; "
            f"market_listings={market.get('listingCount')}; "
            f"market_timestamp={market.get('timestamp')}"
        )
        matched.append({
            "template_id": row["template_id"],
            "display_name": row["display_name"],
            "floor": floor,
            "ceiling": ceiling,
            "game_price": game_price,
            "market_item": market.get("itemName"),
        })
    with catalog_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return matched, len(rows)


def main():
    parser = argparse.ArgumentParser(description="Import public dune.exchange auction-history prices into the artificial Exchange catalog.")
    parser.add_argument("--catalog", type=pathlib.Path, default=DEFAULT_CATALOG)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--server", default="")
    parser.add_argument("--price-field", choices=["averagePrice", "lowestPrice", "highestPrice"], default="averagePrice")
    parser.add_argument("--cache", type=pathlib.Path)
    args = parser.parse_args()

    if args.cache and args.cache.exists():
        market_rows = json.loads(args.cache.read_text(encoding="utf-8"))
    else:
        market_rows = fetch_market(args.hours, args.server)
        if args.cache:
            args.cache.parent.mkdir(parents=True, exist_ok=True)
            args.cache.write_text(json.dumps(market_rows, indent=2, sort_keys=True), encoding="utf-8")
    matched, total = update_catalog(args.catalog, market_rows, args.price_field)
    print(json.dumps({
        "ok": True,
        "catalog": str(args.catalog),
        "totalRows": total,
        "marketRows": len(market_rows),
        "matchedRows": len(matched),
        "priceField": args.price_field,
        "hours": args.hours,
        "server": args.server,
        "updatedAt": int(time.time()),
        "examples": matched[:20],
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
