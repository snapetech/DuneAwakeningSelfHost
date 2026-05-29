#!/usr/bin/env python3
"""Probe the server binary to narrow down the byte location of the per-player
subfief/totem placement cap.

Background
----------
The placement cap (default 3) is *not* exposed via:
  - any INI key (no entries in `[/Script/DuneSandbox.DunePlayerCharacter]`,
    `[/Script/DuneSandbox.DuneCharacter]`, or `[/Script/DuneSandbox.BuildingSettings]`
    that govern per-player landclaim/totem count),
  - any `EServerGameplaySettingType` enum entry,
  - any GameplayEffect or DataTable in pakchunk0..240 (no asset references the
    `DunePlayerCharacterAttributeSet.SubfiefLimitBonus` attribute as a modifier
    target — verified by scanning all paks for the AttributeSet string).

Empirical evidence (kspls0 production DB):
  - SubfiefLimitBonus.BaseValue=6 + CurrentValue=6 persisted on Lukano's pawn
    (`dune.actors.gas_attributes`) survives relog, but in-game cap stays at 3/3.
  - Conclusion: the placement validator does not read SubfiefLimitBonus for the
    cap calculation. The cap is enforced by code in the C++ server binary.

`BP_SetMaxClaimCapacity`/`BP_ClearMaxClaimCapacity` are red herrings: they
belong to `UClaimSubsystem` (FLS reward-pack queue), not landclaims.

Approach
--------
This script narrows the search space inside
`DuneSandboxServer-Linux-Shipping` to the function(s) most likely containing
the cap-vs-count comparison.

It does NOT yet patch. The byte location is unconfirmed; that requires either
Ghidra-driven RE or live gdb attach in the handoff lab.

Heuristics
----------
1. Find each `DuneSandbox/.../Foo.cpp` source-file string in `.rodata`.
2. Count RIP-relative `lea r, [rip+disp]` xrefs to each from `.text`. The count
   = number of `__FILE__` macro expansions inside that source file's functions
   (asserts, log sites, check() failures, etc.).
3. Report the most plausible files (Totem / Subfief / BuildingSystem placement).
4. For each xref, disassemble the surrounding function (between adjacent int3
   padding blocks) and surface:
     - small integer cmp imm (1..20) → candidate for `cmp r32, 3`
     - SSE rip-relative loads of float constants 1.0..10.0 → candidate for
       `ucomiss xmm, [rip+disp]` against 3.0f
     - calls to the same callee repeated 3+ times → candidate GAS attribute
       getter (`GetSubfiefLimitBonusAttribute().GetCurrentValue()` etc.)

Run on the server host (kspls0) with binary staged to /tmp:
    docker cp dune_server-deep-desert-1:/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping \
        /tmp/subfief-research/server-bin
    python3 probe-subfief-cap-binary.py /tmp/subfief-research/server-bin

Requires `pip install --user --break-system-packages capstone` on the host.
"""
import argparse
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
except ImportError:
    sys.exit("Install capstone: pip install --user --break-system-packages capstone")


CANDIDATE_SOURCE_FILES = [
    b"DuneTotemCanBePlaced.cpp",
    b"DunePlaceableTotem.cpp",
    b"BuildingSystemActionPlaceBuildable.cpp",
    b"BuildingSystemActionSpawnBuildable.cpp",
    b"TotemPersistenceComponent.cpp",
    b"TotemUtils.cpp",
    b"BuildingSystemPlacementUtils.cpp",
    b"InsideLandclaimCanBePlaced.cpp",
]


def parse_sections(data):
    """Find .text and .rodata file offsets/sizes by scanning section header table."""
    # Read ELF header
    e_shoff = struct.unpack_from("<Q", data, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", data, 0x3a)[0]
    e_shnum = struct.unpack_from("<H", data, 0x3c)[0]
    e_shstrndx = struct.unpack_from("<H", data, 0x3e)[0]
    shstrtab_off = struct.unpack_from("<Q", data, e_shoff + e_shstrndx * e_shentsize + 0x18)[0]
    sections = {}
    for i in range(e_shnum):
        sh = e_shoff + i * e_shentsize
        sh_name = struct.unpack_from("<I", data, sh)[0]
        sh_addr = struct.unpack_from("<Q", data, sh + 0x10)[0]
        sh_off = struct.unpack_from("<Q", data, sh + 0x18)[0]
        sh_size = struct.unpack_from("<Q", data, sh + 0x20)[0]
        end = data.index(b"\0", shstrtab_off + sh_name)
        name = data[shstrtab_off + sh_name:end].decode()
        sections[name] = {"addr": sh_addr, "offset": sh_off, "size": sh_size}
    return sections


def find_string_start(data, needle_pos):
    pos = needle_pos
    while pos > 0 and data[pos - 1] != 0:
        pos -= 1
    return pos


def find_func_start(data, off, text_start):
    pos = off - 1
    floor = max(text_start, off - 0x4000)
    while pos > floor:
        if data[pos] == 0xCC and data[pos - 1] == 0xCC:
            return pos + 1
        pos -= 1
    return off - 0x800


def find_func_end(data, off, text_end):
    pos = off
    while pos + 3 < text_end:
        if data[pos] == 0xCC and data[pos + 1] == 0xCC and data[pos + 2] == 0xCC:
            return pos
        pos += 1
    return min(off + 0x4000, text_end)


def rodata_floats(data, rod_off, rod_size, values):
    out = {}
    end = rod_off + rod_size
    for v in values:
        fb = struct.pack("<f", v)
        pos = rod_off
        while True:
            p = data.find(fb, pos, end)
            if p < 0:
                break
            if (p & 3) == 0:
                out.setdefault(p, v)
            pos = p + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("binary", type=Path)
    ap.add_argument("--xref-budget", type=int, default=12,
                    help="max xrefs per source file to disassemble")
    args = ap.parse_args()

    data = args.binary.read_bytes()
    sections = parse_sections(data)
    text = sections[".text"]
    rod = sections[".rodata"]
    text_start = text["addr"]
    text_size = text["size"]
    text_end = text_start + text_size

    # In LOAD1 of this PIE binary, VMA == file offset for .text and .rodata
    # so we can address the same byte by either.
    floats = rodata_floats(data, rod["offset"], rod["size"],
                           [0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    # Locate each candidate source file string and count xrefs
    cpp_strings = []
    for name in CANDIDATE_SOURCE_FILES:
        m = re.search(re.escape(name), data)
        if not m:
            continue
        start = find_string_start(data, m.start())
        cpp_strings.append((start, name.decode()))

    print("Counting RIP-relative xrefs from .text to candidate source-file strings...")
    targets = {start: name for start, name in cpp_strings}
    hits_per_target = defaultdict(list)
    i = text["offset"]
    end = text["offset"] + text_size
    while i < end - 4:
        disp = struct.unpack_from("<i", data, i)[0]
        t = i + 4 + disp
        if t in targets:
            hits_per_target[t].append(i)
        i += 1

    ranking = sorted(hits_per_target.items(), key=lambda kv: len(kv[1]))
    for target_off, hits in ranking:
        print(f"  {targets[target_off]:50s}  xrefs={len(hits):4d}  string @0x{target_off:x}")

    print("\nDisassembling around top xrefs (lowest count first — narrower candidates)...")
    for target_off, hits in ranking:
        if len(hits) > 30:
            continue  # Skip noisy utility files
        # Disassemble the function containing each xref
        seen_funcs = {}
        for xoff in hits[: args.xref_budget]:
            lea_start = xoff - 3  # 48 8d 35 <disp32>
            fs = find_func_start(data, lea_start, text["offset"])
            if fs in seen_funcs:
                continue
            seen_funcs[fs] = True
            fe = find_func_end(data, fs, end)
            chunk = data[fs:fe]
            cmps = []
            flts = []
            calls = []
            for ins in md.disasm(chunk, fs):
                if ins.mnemonic == "cmp" and len(ins.operands) == 2:
                    o0, o1 = ins.operands
                    if o1.type == X86_OP_IMM and o0.type != X86_OP_IMM:
                        if 1 <= o1.imm < 20:
                            cmps.append((ins.address, ins.op_str, ins.bytes.hex(), o1.imm))
                for op in ins.operands:
                    if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                        tgt = ins.address + ins.size + op.mem.disp
                        if tgt in floats and floats[tgt] in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0):
                            flts.append((ins.address, ins.mnemonic, ins.op_str, ins.bytes.hex(), floats[tgt]))
                if ins.mnemonic == "call":
                    calls.append(ins.op_str)
            print(f"\n  -- {targets[target_off]}: func 0x{fs:x}..0x{fe:x} ({fe-fs} bytes)")
            if cmps:
                print(f"     cmp_imm: {[(hex(c[0]), c[3]) for c in cmps[:6]]}")
            if flts:
                print(f"     float:   {[(hex(f[0]), f[1], f[4]) for f in flts[:6]]}")
            # Most-repeated callee count
            from collections import Counter
            top_calls = Counter(calls).most_common(3)
            if top_calls and top_calls[0][1] >= 3:
                print(f"     hot calls: {top_calls}")


if __name__ == "__main__":
    main()
