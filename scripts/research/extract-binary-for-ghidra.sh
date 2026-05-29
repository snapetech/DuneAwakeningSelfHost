#!/usr/bin/env bash
# Package the live Dune server binary + research notes into a tarball ready
# for transfer to a Ghidra-equipped workstation.
#
# Usage:
#   scripts/research/extract-binary-for-ghidra.sh [--host kspls0] [--out /tmp/dune-ghidra]
#
# Produces:
#   <out>/server-bin                 — the stripped ELF binary
#   <out>/server-bin.sha256          — checksum for tamper detection
#   <out>/build-id                   — ELF NT_GNU_BUILD_ID for traceability
#   <out>/candidates.md              — pre-marked function VMAs from the probe
#   <out>/probe-output.txt           — full probe-subfief-cap-binary.py output
#   <out>/ghidra-find-subfief-cap.py — Ghidra script to drop into ~/ghidra_scripts/
#   <out>/README.md                  — workflow overview for a fresh Ghidra session
#
# Then `tar -czf dune-ghidra.tgz <out>` and copy to the workstation.

set -euo pipefail

HOST="${1:-kspls0}"
OUT="${2:-/tmp/dune-ghidra}"
CONTAINER="${DUNE_CONTAINER:-dune_server-deep-desert-1}"
BIN_IN_CONTAINER="/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping"

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"

mkdir -p "$OUT"

echo "==> Copying binary from $HOST:$CONTAINER"
ssh "$HOST" "docker cp $CONTAINER:$BIN_IN_CONTAINER /tmp/server-bin-staged"
scp "$HOST:/tmp/server-bin-staged" "$OUT/server-bin"
ssh "$HOST" "rm /tmp/server-bin-staged"

sha256sum "$OUT/server-bin" > "$OUT/server-bin.sha256"
echo "==> Recording GNU build-id"
readelf -n "$OUT/server-bin" | awk '/Build ID/{print $3}' > "$OUT/build-id" || true

echo "==> Copying probe script + research note"
cp "$repo_root/scripts/research/probe-subfief-cap-binary.py" "$OUT/"
cp "$repo_root/scripts/research/ghidra-find-subfief-cap.py" "$OUT/"
cp "$repo_root/docs/subfief-cap-research.md" "$OUT/"

echo "==> Installing capstone (if missing) and running probe"
python3 -c "import capstone" 2>/dev/null || pip install --user --break-system-packages capstone >/dev/null
python3 "$OUT/probe-subfief-cap-binary.py" "$OUT/server-bin" > "$OUT/probe-output.txt"

cat > "$OUT/candidates.md" <<EOF
# Pre-marked candidate function VMAs

These are the most likely places for the per-player subfief/totem cap check,
ranked by xref count (fewer = narrower).

## Top candidates

| Function VMA | Source file (xrefs) | Size | Why |
|---|---|---:|---|
| 0xcf70210 | BuildingSystemActionPlaceBuildable.cpp (3) | 4860 b | Strong: likely OnInstigatorServerBeforeValidation_Internal |
| 0xcf7ac80 | BuildingSystemActionSpawnBuildable.cpp (5) | 2487 b | Strong: actual totem spawn action |
| 0xcedcb40 | DuneTotemCanBePlaced.cpp (7)              | 4706 b | Plausible: cap may be checked alongside collision/terrain |
| 0xd04d020 | InsideLandclaimCanBePlaced.cpp (3)         | 1676 b | Less likely: about placing INSIDE landclaim, not cap |

## Indirection to resolve

The hot callee at **0xf7d8600** (92 bytes) is a singleton dispatcher:
- checks rdi != null
- lazy-inits singleton at [rip + 0x6e0f7e2]
- virtual-dispatches via vtable+0x48 method

The cap check is INSIDE that virtual method. In Ghidra:
1. Navigate to 0xf7d8600, follow the singleton's class via the cached pointer's xrefs.
2. Identify the class via RTTI/vtable cross-reference.
3. Inspect the vtable's 9th entry (offset 0x48 / 8 bytes per ptr).
4. That function contains the actual cap-vs-count comparison.

## Ghidra session checklist

1. Import server-bin (Linux ELF 64-bit, x86_64).
2. Run auto-analysis with all default analyzers (1-2h on 374MB stripped binary).
3. Drop ghidra-find-subfief-cap.py into ~/ghidra_scripts/ or add this folder via
   Script Manager > Manage Script Directories.
4. Open Symbol Tree > Filter "EBuildingSystemActionResult" — Ghidra often
   reconstructs the enum from RTTI; if so, navigate to Fail_DisallowedBuildLimit.
5. Otherwise run "ghidra-find-subfief-cap.py" from Script Manager.

EOF

cat > "$OUT/README.md" <<'EOF'
# Dune subfief cap — Ghidra investigation package

Background: docs/subfief-cap-research.md (or copy in this directory).

Quick start on the workstation:
1. Extract: `tar -xzf dune-ghidra.tgz`
2. Verify: `sha256sum -c server-bin.sha256`
3. Open Ghidra, create project, import `server-bin`.
4. Run analysis (allow several hours).
5. Drop `ghidra-find-subfief-cap.py` into `~/ghidra_scripts/`.
6. Run via Script Manager.

If the script's auto-finder fails, fall back to manual:
1. Search > For Strings > "Fail_DisallowedBuildLimit"
2. Follow xrefs.
3. Decompile each referencing function.
4. Look for `result = X;` where X equals the enum value, and walk back to find
   the comparison that gates entry.
5. Record a 16-32 byte signature around the patch byte (the immediate 3).
6. Encode signature in scripts/patch-subfief-cap-binary.py (template TBD).

Once the patch byte signature is known, wire it through
`scripts/run_server_safe.sh` like the existing
`install_building_piece_limit_patch` block (around line 203).
EOF

echo
echo "==> Package ready in $OUT"
echo "    Size:"
du -sh "$OUT"
echo
echo "    To ship to workstation:"
echo "      tar -czf dune-ghidra.tgz -C $(dirname "$OUT") $(basename "$OUT")"
echo "      scp dune-ghidra.tgz <workstation>:"
