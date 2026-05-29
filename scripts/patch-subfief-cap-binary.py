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

# ---------------------------------------------------------------------------
# Signature: the subfief-cap validity check inside the totem placement path.
#
#   mov  rdi, [r14 + 0x70]    49 8b 7e 70
#   call <validity helper>    e8 ?? ?? ?? ??       (rel32 wildcards)
#   test al, al               84 c0
#   je   <fail block>         0f 84 ?? ?? ?? ??    ← PATCH this je to 6x NOP
#
# Patching the `je` to six NOPs (0x90) makes the cap check always succeed:
# the fail-block that writes Fail_DisallowedBuildLimit (enum value 0x6b, see
# docs/subfief-cap-enum-table.md) is never reached. Ghidra confirmed this is
# the only path that writes the enum byte at struct offset +0x18 from this
# code path. Build hash 9bf5fbdef43a6d6d… reproduces this signature uniquely.
#
# `new_cap` is accepted for API symmetry with the building-piece patcher but
# is ignored — the patch is a hard bypass, not a numeric cap raise. If
# `new_cap` equals OLD_CAP (3), this script is a no-op (rollback path uses
# the original je bytes).
# ---------------------------------------------------------------------------
SIGNATURE = [
    0xc5, 0xfc, 0x11, 0x43, 0x44,                # -10 vmovups [rbx+0x44], ymm0  (anchor)
    0xe9, None, None, None, None,                # -5  jmp <rel32>  (rel32 wildcard)
    0x49, 0x8b, 0x7e, 0x70,                      # +0  mov rdi, [r14+0x70]
    0xe8, None, None, None, None,                # +4  call <helper>  (rel32 wildcard)
    0x84, 0xc0,                                  # +9  test al, al
    0x0f, 0x84, None, None, None, None,          # +11 je <fail>  (rel32 wildcard)  ← PATCH
    0x48, 0x8b, 0x05, None, None, None, None,    # +17 mov rax, [rip+disp]
    0xc5, 0xf8, 0x28,                            # +24 vmovaps xmm0, ...
]

# Patch byte indexes inside SIGNATURE. The callback receives `new_cap` and
# returns the byte to write. We replace the 6-byte `je rel32` (0f 84 + 4-byte
# disp) with 6 NOPs. The function ignores `new_cap` other than to detect
# rollback (new_cap == OLD_CAP -> no-op, leave the bytes alone).
def _bypass_byte(new_cap):
    return 0x90  # NOP

PATCH_OFFSETS = {
    # Offsets reference SIGNATURE positions (with 10-byte pre-anchor prefix).
    # The je rel32 starts at signature index 21.
    21: _bypass_byte,  # 0x0f -> 0x90
    22: _bypass_byte,  # 0x84 -> 0x90
    23: _bypass_byte,  # rel32[0] -> 0x90
    24: _bypass_byte,  # rel32[1] -> 0x90
    25: _bypass_byte,  # rel32[2] -> 0x90
    26: _bypass_byte,  # rel32[3] -> 0x90
}


def find_all_signature(data: bytes, signature: list) -> list:
    """Return ALL match offsets (not just one). Used so the caller can apply
    a post-filter to disambiguate when multiple sites share the same outer
    pattern but differ in their downstream fail block."""
    n = len(signature)
    if n == 0:
        raise ValueError("empty signature")
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
    return hits


# Index inside SIGNATURE of the `je` instruction (the 6 bytes we NOP).
# Used to compute the je target VMA and check the fail block.
JE_OFFSET_IN_SIG = 21

# Expected enum byte written by the fail block we want to bypass.
EXPECTED_FAIL_ENUM = 0x6b  # Fail_DisallowedBuildLimit


def fail_enum_at_site(data: bytes, site_off: int) -> int | None:
    """Compute the je target from the je at site_off + JE_OFFSET_IN_SIG and
    look up the enum byte written there (mov byte [rbx+0x18], imm at +0x25)."""
    je_addr = site_off + JE_OFFSET_IN_SIG
    if je_addr + 6 > len(data):
        return None
    disp = struct.unpack_from("<i", data, je_addr + 2)[0]
    target = je_addr + 6 + disp
    # Search the fail block (200 bytes) for `c6 43 18 ??`
    fb = data[target:target + 200]
    for i in range(len(fb) - 3):
        if fb[i] == 0xc6 and fb[i + 1] == 0x43 and fb[i + 2] == 0x18:
            return fb[i + 3]
    return None


def find_signature(data: bytes, signature: list) -> int:
    """Find the unique site whose je target writes EXPECTED_FAIL_ENUM."""
    candidates = find_all_signature(data, signature)
    if not candidates:
        return -1
    filtered = [
        s for s in candidates
        if fail_enum_at_site(data, s) == EXPECTED_FAIL_ENUM
    ]
    if not filtered:
        raise SystemExit(
            f"matched {len(candidates)} candidate sites but none lead to a "
            f"0x{EXPECTED_FAIL_ENUM:02x} fail block: {[hex(s) for s in candidates]}"
        )
    if len(filtered) > 1:
        raise SystemExit(
            f"multiple sites lead to a 0x{EXPECTED_FAIL_ENUM:02x} fail block: "
            f"{[hex(s) for s in filtered]} — narrow the signature further"
        )
    return filtered[0]


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

    # The patch is a hard bypass of the cap check (changes a 6-byte `je rel32`
    # to 6 NOPs). It does not raise a numeric cap, so any new_cap > OLD_CAP
    # produces the same patch. new_cap == OLD_CAP (3) is treated as "do
    # nothing" (rollback requires restoring the original bytes from a backup).
    if args.new_cap <= OLD_CAP:
        print(f"new-cap {args.new_cap} <= OLD_CAP {OLD_CAP}; nothing to patch "
              f"(restore from backup to fully roll back the bypass)")
        return

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
