#!/usr/bin/env python3
import json
import pathlib
import re
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_PATHS = [
    ROOT / "public-site" / "static" / "hagga-pois.json",
    ROOT / "admin" / "static" / "hagga-pois.json",
]
SOURCE_PAGE = "Map:Hagga Basin"
SOURCE_URL = "https://awakening.wiki/api.php?" + urllib.parse.urlencode({
    "action": "parse",
    "page": SOURCE_PAGE,
    "prop": "wikitext",
    "format": "json",
})
MAX_GROUPS = 64
MAX_MARKERS = 5000
MAX_TEXT_LENGTH = 120
SAFE_GROUP_RE = re.compile(r"^[A-Za-z0-9 _:'()./-]{1,80}$")


def clean_text(value, fallback=""):
    text = str(value or fallback).strip()
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_TEXT_LENGTH]


def clean_group_key(value):
    key = clean_text(value)
    if not SAFE_GROUP_RE.match(key):
        key = re.sub(r"[^A-Za-z0-9 _:'()./-]+", "", key)[:80].strip()
    return key


def clean_url(value):
    text = clean_text(value, "")
    if not text:
        return ""
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return ""
    return text


def fetch_source():
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "DASH Hagga POI importer"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    return json.loads(data["parse"]["wikitext"]["*"])


def marker_id(group_key, marker, index):
    return clean_text(marker.get("id") or f"{group_key.lower()}-{index + 1}", f"{group_key.lower()}-{index + 1}")


def main():
    source = fetch_source()
    source_groups = source.get("groups") or {}
    source_markers = source.get("markers") or {}
    groups = {}
    markers = []
    for group_key, rows in list(source_markers.items())[:MAX_GROUPS]:
        safe_group_key = clean_group_key(group_key)
        if not safe_group_key:
            continue
        group = source_groups.get(group_key) or {}
        groups[safe_group_key] = {
            "name": clean_text(group.get("name"), safe_group_key),
            "icon": clean_url(group.get("icon")),
            "count": len(rows or []),
        }
        for index, marker in enumerate(rows or []):
            if len(markers) >= MAX_MARKERS:
                break
            try:
                x = float(marker["x"])
                y = float(marker["y"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (0 <= x <= 100000 and 0 <= y <= 100000):
                continue
            markers.append({
                "id": marker_id(safe_group_key, marker, index),
                "group": safe_group_key,
                "name": clean_text(marker.get("name"), group.get("name") or safe_group_key),
                "article": clean_text(marker.get("article"), ""),
                "x": round(x, 2),
                "y": round(y, 2),
            })
        groups[safe_group_key]["count"] = sum(1 for marker in markers if marker["group"] == safe_group_key)
    payload = {
        "source": {
            "name": "Dune: Awakening Community Wiki Map:Hagga Basin",
            "url": "https://awakening.wiki/Map:Hagga_Basin",
            "license": "CC BY-NC-SA 4.0 unless otherwise noted",
            "api": SOURCE_URL,
        },
        "crs": source.get("crs") or {"topLeft": [0, 0], "bottomRight": [100000, 100000], "order": "xy"},
        "groups": groups,
        "markers": markers,
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    for path in OUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path} with {len(markers)} markers in {len(groups)} groups")


if __name__ == "__main__":
    main()
