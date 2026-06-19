#!/usr/bin/env bash
set -euo pipefail

pak="${1:-${DUNE_BRT_DD_OVERLAY_PAK:-backups/operations/brt-dd-overlay/pakchunk9999-LinuxServer.pak}}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
repak="${DUNE_REPAK_BIN:-/tmp/repak/target/debug/repak}"

cd "$repo_root"

[[ -f "$pak" ]] || { echo "ERROR: overlay pak not found: $pak" >&2; exit 1; }
[[ -x "$repak" ]] || { echo "ERROR: repak not executable: $repak" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

"$repak" unpack "$pak" --output "$tmp" >/dev/null

python3 - "$tmp" <<'PY'
from pathlib import Path
import importlib.util
import struct
import sys

root = Path(sys.argv[1]) / "DuneSandbox/Content/Dune/Systems/Building/Data"
uasset_path = root / "DT_BuildableMapRegion.uasset"
uexp_path = root / "DT_BuildableMapRegion.uexp"
if not uasset_path.exists() or not uexp_path.exists():
    raise SystemExit("ERROR: overlay does not contain DT_BuildableMapRegion.uasset/.uexp")

spec = importlib.util.spec_from_file_location(
    "brt_patch", "scripts/patch-brt-dd-buildable-map-region-pak.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

uasset = uasset_path.read_bytes()
uexp = uexp_path.read_bytes()
names = mod.parse_uasset_names(uasset)
rows = mod.parse_rows(uexp, names)
map_offsets = mod.find_map_value_offsets(uexp, names)

summary = {}
for row, off in zip(rows, map_offsets):
    name_idx, num = struct.unpack_from("<ii", uexp, off)
    map_name = names[name_idx]
    props = row["props"]
    summary[map_name] = {
        "num": num,
        "default": props["m_DefaultRegionData"]["size"],
        "pvp": props["m_PvpRegionData"]["size"],
        "override": props["m_bOverridePvpRegionData"].get("bool_value"),
    }

if "HaggaBasin" not in summary or "DeepDesert" not in summary:
    raise SystemExit(f"ERROR: expected HaggaBasin and DeepDesert rows, found {sorted(summary)}")

hagga = summary["HaggaBasin"]
deep = summary["DeepDesert"]
mod.validate_dd_full_region_patch(uexp, names, hagga["default"], hagga["pvp"])

print(f"rows={len(rows)}")
for name in ("HaggaBasin", "DeepDesert"):
    info = summary[name]
    print(
        f"row={name}:{info['num']} "
        f"default={info['default']} pvp={info['pvp']} override={info['override']}"
    )
print(f"dd_default_matches_hagga={deep['default'] == hagga['default']}")
print(f"dd_pvp_matches_hagga={deep['pvp'] == hagga['pvp']}")
print(f"dd_override_matches_hagga={deep['override'] == hagga['override']}")
print("validator=dd-full-region-ok")
PY

sha256sum "$pak"
