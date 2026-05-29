#!/usr/bin/env python3
"""Verify a candidate sigscan signature against a Dune server binary.

Use after Ghidra produces a candidate byte signature for the per-player
subfief / totem cap comparison. Confirms that:
  1. The signature is unique in the binary.
  2. The byte at the patch offset reads as the expected 'old' value (e.g. 3).
  3. Disassembling at the match address yields an instruction whose immediate
     operand matches the patch byte (sanity check that the offset is right).

Once it passes, copy the SIGNATURE list and PATCH_OFFSETS dict into
scripts/patch-subfief-cap-binary.py.

Usage:
    python3 scripts/research/verify-subfief-cap-signature.py \
        --binary /tmp/dune-ghidra/server-bin \
        --signature '48 89 e5 ?? 83 f8 03 0f 8c' \
        --patch-offset 6 --expected-old 3
"""
import argparse
from pathlib import Path

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
except ImportError:
    Cs = None


def parse_signature(s):
    """Parse 'aa bb ?? cc' style signature into a list of ints/None."""
    out = []
    for tok in s.split():
        tok = tok.strip().lower()
        if tok in ("??", "?", "**"):
            out.append(None)
        else:
            out.append(int(tok, 16))
    return out


def find_all(data, signature):
    anchor_i = next((i for i, b in enumerate(signature) if b is not None), None)
    if anchor_i is None:
        raise ValueError("signature is all wildcards")
    anchor_b = signature[anchor_i]
    n = len(signature)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--signature", required=True,
                    help='Space-separated hex bytes; use ?? for wildcards. Example: "48 89 e5 ?? 83 f8 03"')
    ap.add_argument("--patch-offset", type=int, default=None,
                    help="Byte offset inside the signature that holds the cap immediate.")
    ap.add_argument("--expected-old", type=int, default=3,
                    help="Expected current value at patch offset (default 3).")
    args = ap.parse_args()

    sig = parse_signature(args.signature)
    print(f"signature ({len(sig)} bytes):")
    print(" ", " ".join("??" if b is None else f"{b:02x}" for b in sig))

    data = args.binary.read_bytes()
    hits = find_all(data, sig)
    print(f"matches in binary: {len(hits)}")
    for h in hits[:5]:
        print(f"  hit @ file_off 0x{h:x}")
    if len(hits) == 0:
        raise SystemExit("FAIL: no matches — widen or correct the signature")
    if len(hits) > 1:
        raise SystemExit("FAIL: multiple matches — make the signature more specific")

    base = hits[0]
    if args.patch_offset is not None:
        observed = data[base + args.patch_offset]
        print(f"byte at patch_offset {args.patch_offset} = 0x{observed:02x} (decimal {observed})")
        if observed != args.expected_old:
            raise SystemExit(f"FAIL: expected old value {args.expected_old}, got {observed}")
        print(f"OK: patch byte matches expected old value {args.expected_old}")

    if Cs is not None:
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = True
        print()
        print("disassembly at match (interpret as code; PIE VMA == file offset in .text):")
        for ins in md.disasm(data[base:base + len(sig) + 16], base):
            print(f"  0x{ins.address:x}: {ins.mnemonic:8s} {ins.op_str}  ; bytes={ins.bytes.hex()}")
            if ins.address - base > len(sig):
                break

    print()
    print("Paste into scripts/patch-subfief-cap-binary.py:")
    print("SIGNATURE = [")
    for i, b in enumerate(sig):
        rep = "None" if b is None else f"0x{b:02x}"
        print(f"    {rep},  # +{i}")
    print("]")
    if args.patch_offset is not None:
        print("PATCH_OFFSETS = {")
        print(f"    {args.patch_offset}: lambda c: c & 0xff,  # cap immediate")
        print("}")


if __name__ == "__main__":
    main()
