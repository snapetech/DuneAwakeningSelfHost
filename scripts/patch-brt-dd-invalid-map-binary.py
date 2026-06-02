#!/usr/bin/env python3
"""Bypass the Deep Desert invalid-map verdict in the BRT placement path.

Ghidra shows BaseBackupActionPlace calling BuildingBlueprintBrush::PerformCanBePlaced,
which returns EBuildingBlueprintCanBePlacedType::Fail_InvalidMap (0x88) for the
Deep Desert BRT rejection path. This patch changes only the four Fail_InvalidMap
result writes inside that function to Success (0x01).

Usage:
    python3 scripts/patch-brt-dd-invalid-map-binary.py \
        --binary /home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping \
        --dry-run

The script is idempotent. Rollback requires restoring the original binary from
the container image or a pre-patch backup.
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

DEFAULT_BINARY = Path("/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping")
FAIL_INVALID_MAP = 0x88
SUCCESS = 0x01


class PatchPattern(NamedTuple):
    name: str
    prefix: bytes
    expected_count: int


# Function-start signature for BuildingBlueprintBrush::PerformCanBePlaced in
# build 1973075-0-shipping. Relative branch/call displacements are wildcards.
FUNCTION_SIGNATURE = [
    0x55, 0x48, 0x89, 0xe5, 0x41, 0x57, 0x41, 0x56,
    0x41, 0x55, 0x41, 0x54, 0x53, 0x48, 0x81, 0xec,
    0xc8, 0x02, 0x00, 0x00,
    0x48, 0x89, 0x95, 0x38, 0xff, 0xff, 0xff,
    0x49, 0x89, 0xf4,
    0x49, 0x89, 0xfd,
    0x48, 0x8d, 0x86, 0x60, 0x03, 0x00, 0x00,
    0x48, 0x89, 0x85, 0x30, 0xff, 0xff, 0xff,
    0x80, 0xbe, 0x60, 0x03, 0x00, 0x00, 0x01,
    0x0f, 0x85, None, None, None, None,
    0x48, 0x8d, 0x05, None, None, None, None,
    0x80, 0x38, 0x00,
    0x0f, 0x84, None, None, None, None,
    0x41, 0x80, 0xbc, 0x24, 0x40, 0x05, 0x00, 0x00, 0x01,
    0x0f, 0x85, None, None, None, None,
]

FUNCTION_SCAN_WINDOW = 0x1200
PATTERNS = [
    PatchPattern("invalid-map result A", bytes.fromhex("c6 85 88 fd ff ff"), 1),
    PatchPattern("invalid-map result B/D", bytes.fromhex("c6 85 68 ff ff ff"), 2),
    PatchPattern("invalid-map result C", bytes.fromhex("c6 85 f8 fd ff ff"), 1),
]


def find_all_signature(data: bytes, signature: list[int | None]) -> list[int]:
    if not signature:
        raise ValueError("empty signature")
    anchor_i = next((i for i, b in enumerate(signature) if b is not None), None)
    if anchor_i is None:
        raise ValueError("signature is all wildcards")
    anchor_b = signature[anchor_i]
    hits = []
    pos = 0
    while True:
        p = data.find(bytes([anchor_b]), pos)
        if p < 0:
            break
        start = p - anchor_i
        if start >= 0 and start + len(signature) <= len(data):
            ok = True
            for i, b in enumerate(signature):
                if b is not None and data[start + i] != b:
                    ok = False
                    break
            if ok:
                hits.append(start)
        pos = p + 1
    return hits


def find_function(data: bytes) -> int:
    hits = find_all_signature(data, FUNCTION_SIGNATURE)
    if len(hits) != 1:
        raise SystemExit(
            "BRT invalid-map patch: expected one PerformCanBePlaced function "
            f"signature, found {len(hits)}: {[hex(h) for h in hits]}"
        )
    return hits[0]


def find_patch_offsets(data: bytes, func_start: int) -> tuple[list[int], list[int]]:
    window = data[func_start:func_start + FUNCTION_SCAN_WINDOW]
    patch_offsets = []
    already_patched = []
    for pattern in PATTERNS:
        hits = []
        pos = 0
        while True:
            p = window.find(pattern.prefix, pos)
            if p < 0:
                break
            value_off = func_start + p + len(pattern.prefix)
            if value_off >= len(data):
                raise SystemExit(f"{pattern.name}: patch offset outside binary")
            if data[value_off] in (FAIL_INVALID_MAP, SUCCESS):
                hits.append(value_off)
            pos = p + 1
        if len(hits) != pattern.expected_count:
            raise SystemExit(
                f"{pattern.name}: expected {pattern.expected_count} patchable "
                f"site(s), found {len(hits)}: {[hex(h) for h in hits]}"
            )
        for off in hits:
            if data[off] == FAIL_INVALID_MAP:
                patch_offsets.append(off)
            else:
                already_patched.append(off)
    return sorted(patch_offsets), sorted(already_patched)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup", type=Path, default=None)
    args = parser.parse_args()

    data = args.binary.read_bytes()
    func_start = find_function(data)
    patch_offsets, already_patched = find_patch_offsets(data, func_start)

    for off in already_patched:
        print(f"already patched @ 0x{off:x}: 0x01")
    if not patch_offsets:
        print("BRT invalid-map bypass already patched; nothing to do")
        return

    sha_before = hashlib.sha256(data).hexdigest()
    patched = bytearray(data)
    print(f"PerformCanBePlaced function @ 0x{func_start:x}")
    for off in patch_offsets:
        patched[off] = SUCCESS
        print(f"patch @ 0x{off:x}: 0x88 -> 0x01")
    sha_after = hashlib.sha256(bytes(patched)).hexdigest()

    if args.dry_run:
        print(f"DRY RUN: would patch {len(patch_offsets)} site(s).")
        print(f"  sha256 before: {sha_before}")
        print(f"  sha256 after:  {sha_after}")
        return

    if args.backup and not args.backup.exists():
        shutil.copy2(args.binary, args.backup)
        print(f"backup written: {args.backup}")
    args.binary.write_bytes(bytes(patched))
    print(f"patched OK: {args.binary}")
    print(f"  sha256 before: {sha_before}")
    print(f"  sha256 after:  {sha_after}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        sys.exit(str(exc))
