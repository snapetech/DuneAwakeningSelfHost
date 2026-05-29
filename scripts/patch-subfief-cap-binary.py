#!/usr/bin/env python3
"""Patch the per-player subfief / totem placement cap in the Dune server binary.

This is the binary-patching counterpart to scripts/patch-building-piece-limit-pak.py
(which patches a cooked data table in a pak). Here the cap is enforced by a
C++ comparison inside DuneSandboxServer-Linux-Shipping, so we patch the
binary directly using a byte-pattern signature (so the patch survives
Funcom binary updates as long as the surrounding codegen is stable).

The actual signature and patch offset MUST be filled in once the byte is
identified (via Ghidra; see docs/subfief-cap-research.md and
scripts/research/ghidra-find-subfief-cap.py). Until then, this script
errors out cleanly.

Usage on the server host:
    python3 scripts/patch-subfief-cap-binary.py \
        --binary /home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping \
        --new-cap 6

Pattern (when filled in below):
    SIGNATURE is a list of ints (0..255) or None (wildcard). The script finds
    exactly ONE byte range in the binary matching the signature, then patches
    `PATCH_OFFSETS` bytes inside that range with new values derived from --new-cap.

The script is idempotent: it detects an already-patched signature and exits 0.
Rollback: re-run with --new-cap equal to OLD_CAP (default 3).
"""
import argparse
import hashlib
import shutil
import struct
import sys
from pathlib import Path

DEFAULT_BINARY = Path("/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping")
OLD_CAP = 3

# Sigscan signature. Populate after Ghidra identifies the patch byte.
#   Each entry is an int (exact match) or None (wildcard).
#   Length should be 16-32 bytes to be uniquely findable across the binary.
SIGNATURE = None  # e.g. [0x83, 0xf8, None, 0x0f, 0x8c, None, None, None, None, ...]

# Bytes inside the signature to overwrite. Keys are byte indexes within
# SIGNATURE; values are functions(new_cap) -> int returning the replacement byte.
PATCH_OFFSETS = {}  # e.g. {2: lambda c: c & 0xff}


def find_signature(data: bytes, signature: list) -> int:
    n = len(signature)
    if n == 0:
        raise ValueError("empty signature")
    # First fixed-byte index to anchor the search
    anchor_i = next((i for i, b in enumerate(signature) if b is not None), None)
    if anchor_i is None:
        raise ValueError("signature is all wildcards")
    anchor_b = signature[anchor_i]
    hits = []
    pos = 0
    while True:
        p = data.find(bytes([anchor_b]), pos)
        if p < 0 or p - anchor_i < 0 or p - anchor_i + n > len(data):
            break
        ok = True
        for i, b in enumerate(signature):
            if b is None:
                continue
            if data[p - anchor_i + i] != b:
                ok = False
                break
        if ok:
            hits.append(p - anchor_i)
        pos = p + 1
        if len(hits) > 1:
            break  # early-out: more than one hit is fatal
    if not hits:
        return -1
    if len(hits) > 1:
        raise SystemExit(
            f"signature is ambiguous (>=2 matches at {hex(hits[0])}, {hex(hits[1])}); "
            f"widen it before patching"
        )
    return hits[0]


def matches_target(data: bytes, base: int, signature: list, target_values: dict) -> bool:
    """Return True if the bytes at PATCH_OFFSETS already match target_values."""
    for off, target in target_values.items():
        if data[base + off] != target:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--new-cap", type=int, required=True,
                        help="Desired per-player subfief cap (e.g. 6). Use OLD_CAP to roll back.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Find the site and report what would change without writing.")
    parser.add_argument("--backup", type=Path, default=None,
                        help="Optional path for a one-time backup before first patch.")
    args = parser.parse_args()

    if SIGNATURE is None or not PATCH_OFFSETS:
        sys.exit(
            "ERROR: SIGNATURE / PATCH_OFFSETS are not populated yet.\n"
            "Identify the patch byte via Ghidra first (see docs/subfief-cap-research.md),\n"
            "then fill in SIGNATURE and PATCH_OFFSETS at the top of this script."
        )

    if not (1 <= args.new_cap <= 200):
        sys.exit(f"new-cap out of range: {args.new_cap}")

    data = args.binary.read_bytes()
    base = find_signature(data, SIGNATURE)
    if base < 0:
        sys.exit(f"signature not found in {args.binary} — Funcom may have changed the codegen")

    target_values = {off: fn(args.new_cap) for off, fn in PATCH_OFFSETS.items()}
    if matches_target(data, base, SIGNATURE, target_values):
        print(f"already patched at 0x{base:x} (new_cap={args.new_cap}); nothing to do")
        return

    # Pre-patch backup
    if args.backup and not args.backup.exists():
        shutil.copy2(args.binary, args.backup)
        print(f"backup written: {args.backup}")

    sha_before = hashlib.sha256(data).hexdigest()
    patched = bytearray(data)
    for off, value in target_values.items():
        old_byte = patched[base + off]
        patched[base + off] = value
        print(f"  patch @ 0x{base+off:x}: 0x{old_byte:02x} -> 0x{value:02x}")
    sha_after = hashlib.sha256(bytes(patched)).hexdigest()

    if args.dry_run:
        print(f"DRY RUN: would change bytes at 0x{base:x}.")
        print(f"  sha256 before: {sha_before}")
        print(f"  sha256 after:  {sha_after}")
        return

    args.binary.write_bytes(bytes(patched))
    print(f"patched OK: {args.binary}")
    print(f"  sha256 before: {sha_before}")
    print(f"  sha256 after:  {sha_after}")


if __name__ == "__main__":
    main()
