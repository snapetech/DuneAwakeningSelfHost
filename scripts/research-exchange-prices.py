#!/usr/bin/env python3
import argparse
import csv
import hashlib
import importlib.util
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_SCRIPT = ROOT / "scripts" / "build-exchange-catalog.py"
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "build-exchange-bootstrap-catalog.py"
DEFAULT_OUTPUT = ROOT / "data" / "exchange-price-snapshots" / "wiki-base-vendor-prices.csv"
DEFAULT_CACHE = ROOT / "backups" / "admin-panel" / "artificial-exchange" / "wiki-cache"
API_URL = "https://awakening.wiki/api.php"

spec = importlib.util.spec_from_file_location("catalog_builder", CATALOG_SCRIPT)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)

bootstrap_spec = importlib.util.spec_from_file_location("exchange_bootstrap", BOOTSTRAP_SCRIPT)
bootstrap = importlib.util.module_from_spec(bootstrap_spec)
bootstrap_spec.loader.exec_module(bootstrap)


def humanize_template_id(template_id):
    text = re.sub(r"[_-]+", " ", template_id)
    text = re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    text = re.sub(r"\bMk\s+([0-9]+)\b", r"Mk\1", text)
    return " ".join(text.split())


def extract_item_data(wikitext, title=""):
    item_match = re.search(r"\|ITEMID\|([^|]+)\|ITEMID\|", wikitext)
    price_match = re.search(r"\|\s*Base Vendor Price\s*\|\|\s*([0-9][0-9,]*)", wikitext)
    name_match = re.search(r"\|\s*Name\s*\|\|\s*([^\n|<]+)", wikitext)
    categories = sorted(set(re.findall(r"\[\[Category:([^\]|]+)", wikitext)))
    return {
        "template_id": item_match.group(1).strip() if item_match else "",
        "display_name": name_match.group(1).strip() if name_match else title,
        "base_vendor_price": int(price_match.group(1).replace(",", "")) if price_match else None,
        "categories": categories,
    }


def cache_key(params):
    encoded = urllib.parse.urlencode(sorted(params.items()), doseq=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest() + ".json"


def api_get(params, cache_dir, sleep_seconds):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / cache_key(params)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    query = dict(params)
    query.setdefault("format", "json")
    query.setdefault("formatversion", "2")
    url = API_URL + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": "DuneAwakeningSelfHost exchange price research"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    return data


def search_titles(query, cache_dir, sleep_seconds, limit):
    data = api_get(
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": str(limit),
        },
        cache_dir,
        sleep_seconds,
    )
    return [row["title"] for row in data.get("query", {}).get("search", [])]


def parse_page(title, cache_dir, sleep_seconds):
    data = api_get(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
        },
        cache_dir,
        sleep_seconds,
    )
    if "error" in data:
        return None
    return data.get("parse", {}).get("wikitext", "")


def page_wikitext_batch(titles, cache_dir, sleep_seconds):
    if not titles:
        return {}
    data = api_get(
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "titles": "|".join(titles),
        },
        cache_dir,
        sleep_seconds,
    )
    pages = data.get("query", {}).get("pages", [])
    result = {}
    if isinstance(pages, dict):
        pages = pages.values()
    for page in pages:
        title = page.get("title", "")
        revisions = page.get("revisions") or []
        if not title or not revisions:
            continue
        rev = revisions[0]
        result[title] = rev.get("content") or rev.get("*") or rev.get("slots", {}).get("main", {}).get("content", "")
    return result


def all_page_titles(cache_dir, sleep_seconds, max_pages=0):
    titles = []
    params = {
        "action": "query",
        "list": "allpages",
        "apnamespace": "0",
        "aplimit": "500",
    }
    while True:
        data = api_get(params, cache_dir, sleep_seconds)
        titles.extend(row["title"] for row in data.get("query", {}).get("allpages", []))
        if max_pages > 0 and len(titles) >= max_pages:
            return titles[:max_pages]
        cont = data.get("continue", {}).get("apcontinue")
        if not cont:
            return titles
        params["apcontinue"] = cont


def local_templates(limit_per_category):
    grouped = bootstrap.observed_templates(limit_per_category)
    rows = []
    for category in sorted(grouped):
        for template_id, observed_count in grouped[category]:
            row = bootstrap.row_for(category, template_id, observed_count)
            rows.append(row)
    return rows


def candidate_queries(template_id):
    human = humanize_template_id(template_id)
    queries = [f'"{template_id}"', template_id, human]
    if template_id.startswith("PowerPack"):
        queries.append("Power Pack")
    if template_id.endswith("_Schematic"):
        queries.append(human.replace(" Schematic", ""))
    return list(dict.fromkeys(query for query in queries if query))


def find_price_for_template(row, cache_dir, sleep_seconds, search_limit):
    template_id = row["template_id"]
    checked_titles = []
    for query in candidate_queries(template_id):
        for title in search_titles(query, cache_dir, sleep_seconds, search_limit):
            if title in checked_titles:
                continue
            checked_titles.append(title)
            wikitext = parse_page(title, cache_dir, sleep_seconds)
            if not wikitext:
                continue
            data = extract_item_data(wikitext, title)
            if data["template_id"] == template_id and data["base_vendor_price"] is not None:
                return data, title, "exact-item-id", checked_titles
            if not data["template_id"] and data["base_vendor_price"] is not None and title.lower() == humanize_template_id(template_id).lower():
                return data, title, "title-match", checked_titles
    return None, "", "not-found", checked_titles


def crawl_wiki_prices(cache_dir, sleep_seconds, max_pages):
    found = {}
    titles = all_page_titles(cache_dir, sleep_seconds, max_pages)
    for index in range(0, len(titles), 50):
        batch = page_wikitext_batch(titles[index:index + 50], cache_dir, sleep_seconds)
        for title, wikitext in batch.items():
            if not wikitext:
                continue
            data = extract_item_data(wikitext, title)
            if data["template_id"] and data["base_vendor_price"] is not None:
                found[data["template_id"]] = (data, title)
    return found


def price_row(template_row, wiki_data, title, match_type):
    baseline = wiki_data["base_vendor_price"]
    category = template_row.get("category") or "unknown"
    mask = template_row.get("category_mask") or 0
    depth = template_row.get("category_depth") or 0
    return {
        "template_id": template_row["template_id"],
        "display_name": wiki_data["display_name"] or template_row["display_name"],
        "category": category,
        "category_mask": mask,
        "category_depth": depth,
        "sellable_status": "validated",
        "baseline_price": baseline,
        "max_buy_price": int(baseline * 0.8),
        "liquidity_tier": "medium",
        "enabled": "false",
        "source": "awakening-wiki",
        "confidence": "high" if match_type == "exact-item-id" else "moderate",
        "notes": f"Base Vendor Price from https://awakening.wiki/{urllib.parse.quote(title.replace(' ', '_'))}; match={match_type}; wiki_categories={';'.join(wiki_data['categories'])}",
    }


def write_rows(rows, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=catalog.FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Research real artificial Exchange baseline prices from Awakening Wiki Base Vendor Price fields.")
    parser.add_argument("--limit-per-category", type=int, default=20)
    parser.add_argument("--max-templates", type=int, default=0)
    parser.add_argument("--search-limit", type=int, default=5)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=pathlib.Path, default=DEFAULT_CACHE)
    parser.add_argument("--crawl-allpages", action="store_true", help="crawl wiki mainspace pages and extract exact item IDs with Base Vendor Price")
    parser.add_argument("--max-pages", type=int, default=0, help="maximum wiki pages to crawl with --crawl-allpages; 0 means all pages")
    parser.add_argument("--no-search-fallback", action="store_true", help="after crawling, do not run slower per-template search misses")
    args = parser.parse_args()

    template_rows = local_templates(args.limit_per_category)
    if args.max_templates > 0:
        template_rows = template_rows[:args.max_templates]

    found = []
    misses = []
    crawled = crawl_wiki_prices(args.cache_dir, args.sleep_seconds, args.max_pages) if args.crawl_allpages else {}
    for row in template_rows:
        if row["template_id"] in crawled:
            data, title = crawled[row["template_id"]]
            found.append(price_row(row, data, title, "exact-item-id"))
            continue
        if args.no_search_fallback:
            misses.append({"template_id": row["template_id"], "checked_titles": []})
            continue
        data, title, match_type, checked = find_price_for_template(row, args.cache_dir, args.sleep_seconds, args.search_limit)
        if data:
            found.append(price_row(row, data, title, match_type))
        else:
            misses.append({"template_id": row["template_id"], "checked_titles": checked})

    write_rows(found, args.output)
    miss_path = args.output.with_suffix(".misses.json")
    miss_path.write_text(json.dumps(misses, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output), "priced": len(found), "misses": len(misses), "crawledPrices": len(crawled), "missesOutput": str(miss_path)}, indent=2))


if __name__ == "__main__":
    main()
