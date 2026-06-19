#!/usr/bin/env python3
"""Summarize pointer-table context for ELF virtual-address targets.

This is a static reverse-engineering helper for stripped PIE binaries. Direct
RIP-relative string xrefs miss UE/reflection metadata because many names are
reached through pointer tables. This tool follows raw qword references to a
target address and prints the neighboring qwords with section, symbol, and
string hints so candidate function pointers can be reviewed without guessing.
"""

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_RELA = 4
SHT_DYNSYM = 11
SHF_EXECINSTR = 0x4
SHF_ALLOC = 0x2
SHF_WRITE = 0x1


@dataclass(frozen=True)
class Section:
    name: str
    sh_type: int
    flags: int
    addr: int
    offset: int
    size: int
    link: int
    entsize: int

    def contains_addr(self, addr: int) -> bool:
        return self.addr <= addr < self.addr + self.size

    def contains_file_offset(self, offset: int) -> bool:
        return self.offset <= offset < self.offset + self.size


def read_c_string(data: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\x00", offset)
    if end < 0:
        end = min(len(data), offset + 256)
    raw = data[offset:end]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def load_sections(data: bytes) -> list[Section]:
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise ValueError("expected a 64-bit little-endian ELF")

    e_shoff = struct.unpack_from("<Q", data, 40)[0]
    e_shentsize = struct.unpack_from("<H", data, 58)[0]
    e_shnum = struct.unpack_from("<H", data, 60)[0]
    e_shstrndx = struct.unpack_from("<H", data, 62)[0]
    if e_shoff == 0 or e_shnum == 0:
        return []

    raw_sections = []
    for index in range(e_shnum):
        off = e_shoff + index * e_shentsize
        if off + 64 > len(data):
            break
        sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, _info, _align, sh_entsize = struct.unpack_from(
            "<IIQQQQIIQQ", data, off
        )
        raw_sections.append((sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_entsize))

    shstr = raw_sections[e_shstrndx] if e_shstrndx < len(raw_sections) else None
    shstr_data = b""
    if shstr is not None:
        shstr_data = data[shstr[4] : shstr[4] + shstr[5]]

    sections = []
    for raw in raw_sections:
        sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_entsize = raw
        name = read_c_string(shstr_data, sh_name) if shstr_data else ""
        sections.append(Section(name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_entsize))
    return sections


def section_for_addr(sections: list[Section], addr: int) -> Section | None:
    return next((section for section in sections if section.contains_addr(addr)), None)


def section_for_file_offset(sections: list[Section], offset: int) -> Section | None:
    return next((section for section in sections if section.contains_file_offset(offset)), None)


def addr_to_file_offset(sections: list[Section], addr: int) -> int | None:
    section = section_for_addr(sections, addr)
    if section is None or section.sh_type == 8:
        return None
    return section.offset + (addr - section.addr)


def load_symbols(data: bytes, sections: list[Section]) -> dict[int, list[str]]:
    symbols: dict[int, list[str]] = {}
    for section in sections:
        if section.sh_type not in (SHT_SYMTAB, SHT_DYNSYM) or section.entsize == 0:
            continue
        if section.link >= len(sections):
            continue
        strings = sections[section.link]
        strings_data = data[strings.offset : strings.offset + strings.size]
        count = section.size // section.entsize
        for index in range(count):
            off = section.offset + index * section.entsize
            if off + 24 > len(data):
                continue
            st_name, _info, _other, _shndx, st_value, st_size = struct.unpack_from("<IBBHQQ", data, off)
            if st_value == 0 or st_name == 0:
                continue
            name = read_c_string(strings_data, st_name)
            if not name:
                continue
            suffix = f" size=0x{st_size:x}" if st_size else ""
            symbols.setdefault(st_value, []).append(name + suffix)
    return symbols


def load_relocations(data: bytes, sections: list[Section]) -> dict[int, int]:
    relocations: dict[int, int] = {}
    for section in sections:
        if section.sh_type != SHT_RELA or section.entsize == 0:
            continue
        count = section.size // section.entsize
        for index in range(count):
            off = section.offset + index * section.entsize
            if off + 24 > len(data):
                continue
            r_offset, r_info, r_addend = struct.unpack_from("<QQq", data, off)
            r_type = r_info & 0xFFFFFFFF
            # R_X86_64_RELATIVE. These reconstruct almost all stripped PIE
            # pointer tables in .data.rel.ro for this server binary.
            if r_type == 8:
                relocations[r_offset] = r_addend
    return relocations


def parse_int(value: str) -> int:
    return int(value, 16 if value.lower().startswith("0x") else 10)


def parse_targets(raw_targets: list[str]) -> list[tuple[str, int]]:
    targets = []
    for raw in raw_targets:
        if "=" not in raw:
            raise ValueError(f"--target must be NAME=OFFSET, got {raw!r}")
        name, value = raw.split("=", 1)
        targets.append((name, parse_int(value)))
    return targets


def printable_hint(data: bytes, sections: list[Section], addr: int) -> str:
    file_off = addr_to_file_offset(sections, addr)
    if file_off is None:
        return ""
    raw = data[file_off : min(len(data), file_off + 160)]
    if not raw:
        return ""
    nul = raw.find(b"\x00")
    if nul >= 0:
        raw = raw[:nul]
    if len(raw) < 4:
        return ""
    if any((byte < 0x20 or byte > 0x7e) for byte in raw):
        return ""
    return raw.decode("ascii", errors="replace")


def classify_value(data: bytes, sections: list[Section], symbols: dict[int, list[str]], value: int) -> dict:
    section = section_for_addr(sections, value)
    section_name = section.name if section else ""
    flags = ""
    if section:
        flags = "".join(
            flag
            for bit, flag in ((SHF_ALLOC, "A"), (SHF_WRITE, "W"), (SHF_EXECINSTR, "X"))
            if section.flags & bit
        )
    result = {
        "value": f"0x{value:x}",
        "section": section_name,
        "flags": flags,
        "symbols": symbols.get(value, [])[:4],
        "string": printable_hint(data, sections, value),
    }
    return result


def qword_at_addr(data: bytes, sections: list[Section], relocations: dict[int, int], addr: int) -> tuple[int | None, str]:
    if addr in relocations:
        return relocations[addr], "rela"
    file_off = addr_to_file_offset(sections, addr)
    if file_off is None or file_off + 8 > len(data):
        return None, ""
    return struct.unpack_from("<Q", data, file_off)[0], "file"


def find_qword_refs(data: bytes, target: int) -> list[int]:
    pattern = struct.pack("<Q", target)
    hits = []
    pos = 0
    while True:
        hit = data.find(pattern, pos)
        if hit < 0:
            break
        hits.append(hit)
        pos = hit + 1
    return hits


def pointer_context_at_addr(
    data: bytes,
    sections: list[Section],
    symbols: dict[int, list[str]],
    relocations: dict[int, int],
    center_addr: int,
    window: int,
) -> list[dict]:
    rows = []
    for slot in range(-window, window + 1):
        addr = center_addr + slot * 8
        value, source = qword_at_addr(data, sections, relocations, addr)
        if value is None:
            continue
        section = section_for_addr(sections, addr)
        rows.append(
            {
                "slot": slot,
                "vaddr": f"0x{addr:x}",
                "source": source,
                **classify_value(data, sections, symbols, value),
            }
        )
    return rows


def summarize_target(
    data: bytes,
    sections: list[Section],
    symbols: dict[int, list[str]],
    relocations: dict[int, int],
    name: str,
    target: int,
    window: int,
) -> dict:
    refs = []
    for hit in find_qword_refs(data, target):
        hit_section = section_for_file_offset(sections, hit)
        hit_addr = None
        if hit_section:
            hit_addr = hit_section.addr + (hit - hit_section.offset)
        aligned_start = hit - (hit % 8)
        rows = []
        for slot in range(-window, window + 1):
            off = aligned_start + slot * 8
            if off < 0 or off + 8 > len(data):
                continue
            value = struct.unpack_from("<Q", data, off)[0]
            row_section = section_for_file_offset(sections, off)
            row_addr = row_section.addr + (off - row_section.offset) if row_section else None
            rows.append(
                {
                    "slot": slot,
                    "fileOffset": f"0x{off:x}",
                    "vaddr": f"0x{row_addr:x}" if row_addr is not None else "",
                    "source": "file",
                    **classify_value(data, sections, symbols, value),
                }
            )
        refs.append(
            {
                "fileOffset": f"0x{hit:x}",
                "vaddr": f"0x{hit_addr:x}" if hit_addr is not None else "",
                "section": hit_section.name if hit_section else "",
                "context": rows,
            }
        )
    rela_refs = []
    for addr, addend in sorted(relocations.items()):
        if addend != target:
            continue
        section = section_for_addr(sections, addr)
        rela_refs.append(
            {
                "vaddr": f"0x{addr:x}",
                "section": section.name if section else "",
                "context": pointer_context_at_addr(data, sections, symbols, relocations, addr, window),
            }
        )
    return {
        "name": name,
        "target": f"0x{target:x}",
        "rawRefCount": len(refs),
        "refs": refs,
        "relaRefCount": len(rela_refs),
        "relaRefs": rela_refs,
    }


def markdown(summary: dict) -> str:
    lines = ["# ELF Pointer Context", ""]
    for context in summary.get("contexts", []):
        lines.append(f"## Context {context['name']} `{context['center']}`")
        lines.append("")
        for row in context["context"]:
            pieces = [
                f"slot={row['slot']:+d}",
                f"at={row['vaddr']}",
                f"source={row['source']}",
                f"value={row['value']}",
                f"section={row['section'] or '-'}",
            ]
            if row["flags"]:
                pieces.append(f"flags={row['flags']}")
            if row["symbols"]:
                pieces.append("symbol=" + " | ".join(row["symbols"]))
            if row["string"]:
                pieces.append(f"string={row['string']!r}")
            lines.append("- " + " ".join(pieces))
        lines.append("")
    for target in summary["targets"]:
        lines.append(f"## {target['name']} `{target['target']}`")
        lines.append("")
        lines.append(f"- relocation-applied refs: `{target['relaRefCount']}`")
        for ref in target["relaRefs"]:
            lines.append(f"- relocated slot {ref['vaddr']} section=`{ref['section']}`")
            for row in ref["context"]:
                pieces = [
                    f"slot={row['slot']:+d}",
                    f"at={row['vaddr']}",
                    f"source={row['source']}",
                    f"value={row['value']}",
                    f"section={row['section'] or '-'}",
                ]
                if row["flags"]:
                    pieces.append(f"flags={row['flags']}")
                if row["symbols"]:
                    pieces.append("symbol=" + " | ".join(row["symbols"]))
                if row["string"]:
                    pieces.append(f"string={row['string']!r}")
                lines.append("  - " + " ".join(pieces))
        lines.append(f"- raw qword refs: `{target['rawRefCount']}`")
        for ref in target["refs"]:
            lines.append(f"- ref {ref['vaddr'] or ref['fileOffset']} section=`{ref['section']}`")
            for row in ref["context"]:
                pieces = [
                    f"slot={row['slot']:+d}",
                    f"at={row['vaddr'] or row['fileOffset']}",
                    f"source={row['source']}",
                    f"value={row['value']}",
                    f"section={row['section'] or '-'}",
                ]
                if row["flags"]:
                    pieces.append(f"flags={row['flags']}")
                if row["symbols"]:
                    pieces.append("symbol=" + " | ".join(row["symbols"]))
                if row["string"]:
                    pieces.append(f"string={row['string']!r}")
                lines.append("  - " + " ".join(pieces))
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--target", action="append", default=[], help="NAME=VADDR/OFFSET target")
    parser.add_argument("--context", action="append", default=[], help="NAME=VADDR table context to dump")
    parser.add_argument("--window", type=int, default=4, help="qwords before/after each hit")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    if not args.target and not args.context:
        parser.error("at least one --target or --context is required")

    data = args.binary.read_bytes()
    sections = load_sections(data)
    symbols = load_symbols(data, sections)
    relocations = load_relocations(data, sections)
    targets = [
        summarize_target(data, sections, symbols, relocations, name, target, args.window)
        for name, target in parse_targets(args.target)
    ]
    contexts = [
        {
            "name": name,
            "center": f"0x{addr:x}",
            "context": pointer_context_at_addr(data, sections, symbols, relocations, addr, args.window),
        }
        for name, addr in parse_targets(args.context)
    ]
    summary = {"binary": str(args.binary), "contexts": contexts, "targets": targets}
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
