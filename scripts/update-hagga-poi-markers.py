#!/usr/bin/env python3
import json
import pathlib
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


def fetch_source():
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "DASH Hagga POI importer"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    return json.loads(data["parse"]["wikitext"]["*"])


def marker_id(group_key, marker, index):
    return str(marker.get("id") or f"{group_key.lower()}-{index + 1}")


def main():
    source = fetch_source()
    source_groups = source.get("groups") or {}
    source_markers = source.get("markers") or {}
    groups = {}
    markers = []
    for group_key, rows in source_markers.items():
        group = source_groups.get(group_key) or {}
        groups[group_key] = {
            "name": group.get("name") or group_key,
            "icon": group.get("icon") or "",
            "count": len(rows or []),
        }
        for index, marker in enumerate(rows or []):
            try:
                x = float(marker["x"])
                y = float(marker["y"])
            except (KeyError, TypeError, ValueError):
                continue
            markers.append({
                "id": marker_id(group_key, marker, index),
                "group": group_key,
                "name": marker.get("name") or group.get("name") or group_key,
                "article": marker.get("article") or "",
                "x": round(x, 2),
                "y": round(y, 2),
            })
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
