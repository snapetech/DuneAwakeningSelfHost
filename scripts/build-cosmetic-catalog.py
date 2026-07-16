#!/usr/bin/env python3
"""Build a reviewable cosmetic catalog from observed IDs or an operator-owned pak.

The generated file is data, not authority: DASH still requires exact catalog
membership, an offline player, a backup, and confirmation before a write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re


TOKEN = re.compile(rb"[A-Za-z][A-Za-z0-9_ ]{3,191}")
PREFIXES = ("DyePack_", "MaterialVariant_", "VehicleVariant_", "MTX_", "Beta_", "WaterS_")
CONTAINS = ("DyePack", "Dyepack", "MeshVariant")
NOISE = re.compile(r"(?i)(?:_DESC|_NAME|_Data|_Icon|_Texture|Blueprint|Widget|Preview|Placeholder|Debug|Patent)$")


def category(cosmetic_id):
    low = cosmetic_id.lower()
    if "dyepack" in low or low.endswith("global"):
        return "Dye Packs"
    if cosmetic_id.startswith("VehicleVariant_"):
        return "Vehicle Variants"
    if cosmetic_id.startswith("MaterialVariant_"):
        if any(word in low for word in ("buggy", "sandbike", "orni", "vehicle", "sandcrawler")):
            return "Vehicle Paints"
        if any(word in low for word in ("rifle", "smg", "knife", "sword", "pistol", "shotgun")):
            return "Weapon Paints"
        return "Armor Paints"
    if any(word in low for word in ("buggy", "sandbike", "orni", "vehicle", "sandcrawler")):
        return "Vehicle Skins"
    if any(word in low for word in ("rifle", "smg", "knife", "sword", "pistol", "shotgun", "rapier")):
        return "Weapon Skins"
    return "Armor Skins"


def label(cosmetic_id):
    value = cosmetic_id
    for prefix in ("DyePack_", "MaterialVariant_", "VehicleVariant_", "MTX_"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    suffix = ""
    group = category(cosmetic_id)
    if group == "Dye Packs" and "dye pack" not in value.lower():
        suffix = " Dye Pack"
    elif group.endswith("Skins") and "skin" not in value.lower():
        suffix = " Skin"
    return (value + suffix).strip() or cosmetic_id


def load_ids(path):
    value = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("ids", value.get("cosmetics"))
    if not isinstance(value, list):
        raise ValueError("observed JSON must be an array or an object containing an ids array")
    return {str(item) for item in value if isinstance(item, str) and item}


def scan_pak(path):
    data = pathlib.Path(path).read_bytes()
    ids = set()
    for match in TOKEN.finditer(data):
        value = match.group().decode("ascii", "ignore").strip()
        if len(value) > 192 or NOISE.search(value):
            continue
        if value.startswith(PREFIXES) or any(token in value for token in CONTAINS):
            ids.add(value)
    return ids


def build(ids, source, confidence):
    rows = [{
        "id": cosmetic_id,
        "name": label(cosmetic_id),
        "category": category(cosmetic_id),
        "unlockMode": "customization",
        "enabled": True,
        "source": source,
        "confidence": confidence,
    } for cosmetic_id in sorted(ids)]
    return {
        "version": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": source,
        "reviewRequired": True,
        "notes": "Generated identifiers require operator review; inventory Swatch_* tokens are deliberately excluded from customization-library writes.",
        "items": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-json", action="append", default=[])
    parser.add_argument("--pak", action="append", default=[])
    parser.add_argument("--output", default="config/cosmetic-catalog.json")
    parser.add_argument("--source", default="operator-generated")
    parser.add_argument("--confidence", choices=("high", "moderate", "low", "unknown"), default="moderate")
    args = parser.parse_args()
    if not args.observed_json and not args.pak:
        parser.error("at least one --observed-json or --pak input is required")
    ids = set()
    for path in args.observed_json:
        ids.update(load_ids(path))
    for path in args.pak:
        ids.update(scan_pak(path))
    ids = {value for value in ids if not value.startswith("Swatch_")}
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build(ids, args.source, args.confidence), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "items": len(ids), "source": args.source}, sort_keys=True))


if __name__ == "__main__":
    main()
