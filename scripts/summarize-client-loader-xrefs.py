#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import re
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


IMAGE_SCN_MEM_EXECUTE = 0x20000000
RM5_MODRM_BYTES = (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D)
ONE_BYTE_MODRM_OPCODES = (
    0x03,
    0x0B,
    0x13,
    0x1B,
    0x23,
    0x2B,
    0x33,
    0x3A,
    0x3B,
    0x38,
    0x39,
    0x80,
    0x81,
    0x83,
    0x85,
    0x88,
    0x89,
    0x8A,
    0x8B,
    0x8D,
    0xC6,
    0xC7,
    0xF6,
    0xF7,
)
TWO_BYTE_MODRM_OPCODES = (
    0x10,
    0x11,
    0x28,
    0x29,
    0x2E,
    0x2F,
    0x40,
    0x41,
    0x42,
    0x43,
    0x44,
    0x45,
    0x46,
    0x47,
    0x48,
    0x49,
    0x4A,
    0x4B,
    0x4C,
    0x4D,
    0x4E,
    0x4F,
    0x90,
    0x91,
    0x92,
    0x93,
    0x94,
    0x95,
    0x96,
    0x97,
    0x98,
    0x99,
    0x9A,
    0x9B,
    0x9C,
    0x9D,
    0x9E,
    0x9F,
    0xAF,
    0xB6,
    0xB7,
    0xBA,
    0xBE,
    0xBF,
)


def byte_class(values):
    return b"[" + re.escape(bytes(values)) + b"]"


RIP_MODRM_PATTERN = re.compile(byte_class(ONE_BYTE_MODRM_OPCODES) + byte_class(RM5_MODRM_BYTES), re.DOTALL)
RIP_MODRM_0F_PATTERN = re.compile(b"\x0f" + byte_class(TWO_BYTE_MODRM_OPCODES) + byte_class(RM5_MODRM_BYTES), re.DOTALL)
REL_CALL_JUMP_PATTERN = re.compile(byte_class((0xE8, 0xE9)) + b".{4}", re.DOTALL)
REL_JCC_PATTERN = re.compile(b"\x0f" + byte_class(range(0x80, 0x90)) + b".{4}", re.DOTALL)


@dataclass(frozen=True)
class Section:
    name: str
    virtual_address: int
    virtual_size: int
    raw_size: int
    raw_pointer: int
    characteristics: int

    @property
    def mapped_size(self):
        return max(self.virtual_size, self.raw_size)

    @property
    def is_executable(self):
        return bool(self.characteristics & IMAGE_SCN_MEM_EXECUTE)

    def contains_rva(self, rva):
        return self.virtual_address <= rva < self.virtual_address + self.mapped_size

    def contains_file_offset(self, file_offset):
        return self.raw_pointer <= file_offset < self.raw_pointer + self.raw_size


@dataclass(frozen=True)
class PEImage:
    path: Path
    data: bytes
    image_base: int
    machine: int
    sections: tuple


@dataclass(frozen=True)
class Target:
    name: str
    category: str
    kind: str
    rva: int
    file_offset: Optional[int]
    string_start_rva: Optional[int]
    string_start_file_offset: Optional[int]
    source: str


def parse_int(value):
    if isinstance(value, int):
        return value
    return int(value, 16 if value.lower().startswith("0x") else 10)


def format_hex(value):
    if value is None:
        return ""
    return f"0x{value:x}"


def read_c_string(raw):
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace")


def load_pe_image(binary):
    data = binary.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError(f"{binary} is not a PE file")

    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 24 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise ValueError(f"{binary} has an invalid PE header")

    file_header = e_lfanew + 4
    machine, section_count, _timestamp, _sym_ptr, _sym_count, optional_size, _characteristics = struct.unpack_from(
        "<HHIIIHH", data, file_header
    )
    optional_header = file_header + 20
    if optional_header + optional_size > len(data):
        raise ValueError(f"{binary} has a truncated optional header")
    magic = struct.unpack_from("<H", data, optional_header)[0]
    if magic == 0x20B:
        image_base = struct.unpack_from("<Q", data, optional_header + 24)[0]
    elif magic == 0x10B:
        image_base = struct.unpack_from("<I", data, optional_header + 28)[0]
    else:
        raise ValueError(f"{binary} has unsupported PE optional header magic 0x{magic:x}")

    section_table = optional_header + optional_size
    sections = []
    for index in range(section_count):
        offset = section_table + index * 40
        if offset + 40 > len(data):
            raise ValueError(f"{binary} has a truncated section table")
        raw_name = data[offset : offset + 8]
        name = read_c_string(raw_name) or f"section{index}"
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, offset + 8)
        characteristics = struct.unpack_from("<I", data, offset + 36)[0]
        sections.append(
            Section(
                name=name,
                virtual_address=virtual_address,
                virtual_size=virtual_size,
                raw_size=raw_size,
                raw_pointer=raw_pointer,
                characteristics=characteristics,
            )
        )

    return PEImage(path=binary, data=data, image_base=image_base, machine=machine, sections=tuple(sections))


def section_for_rva(pe, rva):
    for section in pe.sections:
        if section.contains_rva(rva):
            return section
    raise ValueError(f"RVA 0x{rva:x} is not inside a PE section")


def section_for_file_offset(pe, file_offset):
    for section in pe.sections:
        if section.contains_file_offset(file_offset):
            return section
    raise ValueError(f"file offset 0x{file_offset:x} is not inside a PE section")


def rva_to_file_offset(pe, rva):
    section = section_for_rva(pe, rva)
    offset_in_section = rva - section.virtual_address
    if offset_in_section >= section.raw_size:
        raise ValueError(f"RVA 0x{rva:x} maps past section raw data")
    return section.raw_pointer + offset_in_section


def file_offset_to_rva(pe, file_offset):
    section = section_for_file_offset(pe, file_offset)
    return section.virtual_address + (file_offset - section.raw_pointer)


def import_scan_summary():
    script = Path(__file__).resolve().parent / "summarize-client-loader-scan.py"
    spec = importlib.util.spec_from_file_location("summarize_client_loader_scan", script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def is_ascii_string_byte(value):
    return value in (0x09, 0x20) or 0x21 <= value <= 0x7E


def containing_ascii_string(pe, file_offset):
    data = pe.data
    if file_offset < 0 or file_offset >= len(data) or not is_ascii_string_byte(data[file_offset]):
        return None
    start = file_offset
    while start > 0 and is_ascii_string_byte(data[start - 1]):
        start -= 1
    end = file_offset
    while end < len(data) and is_ascii_string_byte(data[end]):
        end += 1
    if end - start < 4:
        return None
    try:
        return {
            "fileOffset": start,
            "rva": file_offset_to_rva(pe, start),
            "text": data[start:end].decode("ascii", errors="replace"),
        }
    except ValueError:
        return None


def make_target(pe, name, category, kind, rva, source=""):
    try:
        file_offset = rva_to_file_offset(pe, rva)
    except ValueError:
        file_offset = None

    string_start_rva = None
    string_start_file_offset = None
    if file_offset is not None and kind in ("string", "manual"):
        string_info = containing_ascii_string(pe, file_offset)
        if string_info:
            string_start_rva = string_info["rva"]
            string_start_file_offset = string_info["fileOffset"]

    return Target(
        name=name,
        category=category,
        kind=kind,
        rva=rva,
        file_offset=file_offset,
        string_start_rva=string_start_rva,
        string_start_file_offset=string_start_file_offset,
        source=source,
    )


def targets_from_log(pe, log_path, loader, pid, exe_substrings, categories, names):
    scan_summary = import_scan_summary()
    summary = scan_summary.summarize(
        scan_summary.load_records(log_path),
        loader_filter=loader,
        pid_filter=pid,
        exe_substrings=exe_substrings,
    )
    category_filter = set(categories or [])
    name_filter = set(names or [])
    targets = []
    seen = set()
    for name, data in summary["hitsByName"].items():
        category = data["category"]
        if category_filter and category not in category_filter:
            continue
        if name_filter and name not in name_filter:
            continue
        for offset_record in data["offsets"]:
            raw_rva = offset_record.get("rva") or offset_record.get("imageOffset") or offset_record.get("offset")
            if not raw_rva:
                continue
            rva = parse_int(raw_rva)
            kind = offset_record.get("kind", "")
            source = offset_record.get("source", "")
            key = (name, rva, kind, source)
            if key in seen:
                continue
            seen.add(key)
            targets.append(make_target(pe, name, category, kind, rva, source=source))
    return targets


def targets_from_args(pe, raw_targets, raw_rvas, raw_file_targets, raw_file_offsets):
    targets = []
    for raw in raw_targets or []:
        if "=" not in raw:
            raise ValueError(f"--target must be NAME=RVA, got {raw!r}")
        name, raw_rva = raw.split("=", 1)
        targets.append(make_target(pe, name, "manual", "manual", parse_int(raw_rva)))
    for raw in raw_rvas or []:
        rva = parse_int(raw)
        targets.append(make_target(pe, f"0x{rva:x}", "manual", "manual", rva))
    for raw in raw_file_targets or []:
        if "=" not in raw:
            raise ValueError(f"--file-target must be NAME=FILE_OFFSET, got {raw!r}")
        name, raw_file_offset = raw.split("=", 1)
        rva = file_offset_to_rva(pe, parse_int(raw_file_offset))
        targets.append(make_target(pe, name, "manual", "manual", rva))
    for raw in raw_file_offsets or []:
        file_offset = parse_int(raw)
        rva = file_offset_to_rva(pe, file_offset)
        targets.append(make_target(pe, f"0x{file_offset:x}", "manual", "manual", rva))
    return targets


def signed32(data, offset):
    return struct.unpack_from("<i", data, offset)[0]


def hex_bytes(data, start, length):
    return data[start : start + length].hex(" ")


def is_prefix_byte(value):
    return value in (
        0x26,
        0x2E,
        0x36,
        0x3E,
        0x64,
        0x65,
        0x66,
        0x67,
        0xF0,
        0xF2,
        0xF3,
    ) or 0x40 <= value <= 0x4F


def instruction_start_for_opcode(data, opcode_pos):
    start = opcode_pos
    while start > 0 and opcode_pos - start < 8 and is_prefix_byte(data[start - 1]):
        start -= 1
    return start


def iter_candidate_positions(data):
    seen = set()
    for pattern in (RIP_MODRM_PATTERN, RIP_MODRM_0F_PATTERN):
        for match in pattern.finditer(data):
            start = instruction_start_for_opcode(data, match.start())
            if start not in seen:
                seen.add(start)
                yield start
    for pattern in (REL_CALL_JUMP_PATTERN, REL_JCC_PATTERN):
        for match in pattern.finditer(data):
            start = match.start()
            if start not in seen:
                seen.add(start)
                yield start


def immediate_lengths(opcode, modrm):
    del modrm
    if not opcode:
        return (0,)
    if len(opcode) == 1:
        op = opcode[0]
        if op in (0x80, 0x82, 0x83, 0xC0, 0xC1, 0xC6):
            return (1,)
        if op in (0x81, 0xC7):
            return (4,)
        if op == 0xF6:
            return (0, 1)
        if op == 0xF7:
            return (0, 4)
    if len(opcode) == 2 and opcode == (0x0F, 0xBA):
        return (1,)
    return (0,)


def decode_rip_memory_refs(data, pos, base_rva):
    cursor = pos
    while cursor < len(data) and data[cursor] in (
        0x26,
        0x2E,
        0x36,
        0x3E,
        0x64,
        0x65,
        0x66,
        0x67,
        0xF0,
        0xF2,
        0xF3,
    ):
        cursor += 1
    while cursor < len(data) and 0x40 <= data[cursor] <= 0x4F:
        cursor += 1
    if cursor >= len(data):
        return []

    opcode_start = cursor
    if data[cursor] == 0x0F:
        cursor += 1
        if cursor >= len(data):
            return []
        if data[cursor] in (0x38, 0x3A):
            cursor += 1
            if cursor >= len(data):
                return []
        cursor += 1
    else:
        cursor += 1

    if cursor + 5 > len(data):
        return []
    opcode = tuple(data[opcode_start:cursor])
    modrm = data[cursor]
    if (modrm & 0xC7) != 0x05:
        return []

    disp_offset = cursor + 1
    disp = signed32(data, disp_offset)
    refs = []
    for imm_len in immediate_lengths(opcode, modrm):
        end = disp_offset + 4 + imm_len
        if end > len(data):
            continue
        refs.append(
            {
                "kind": "rip-memory",
                "xrefRva": base_rva + pos,
                "length": end - pos,
                "dispOffset": disp_offset - pos,
                "targetRva": base_rva + end + disp,
                "bytes": hex_bytes(data, pos, min(end - pos, 16)),
            }
        )
    return refs


def decode_rel_refs(data, pos, base_rva):
    op = data[pos]
    refs = []
    if op in (0xE8, 0xE9) and pos + 5 <= len(data):
        disp = signed32(data, pos + 1)
        refs.append(
            {
                "kind": "rel-call-jump",
                "xrefRva": base_rva + pos,
                "length": 5,
                "dispOffset": 1,
                "targetRva": base_rva + pos + 5 + disp,
                "bytes": hex_bytes(data, pos, 5),
            }
        )
    elif op == 0x0F and pos + 6 <= len(data) and 0x80 <= data[pos + 1] <= 0x8F:
        disp = signed32(data, pos + 2)
        refs.append(
            {
                "kind": "rel-jcc",
                "xrefRva": base_rva + pos,
                "length": 6,
                "dispOffset": 2,
                "targetRva": base_rva + pos + 6 + disp,
                "bytes": hex_bytes(data, pos, 6),
            }
        )
    return refs


def target_match_rvas(target):
    values = {target.rva}
    if target.string_start_rva is not None:
        values.add(target.string_start_rva)
    return values


def scan_xrefs(pe, targets):
    by_rva = defaultdict(list)
    for target in targets:
        for rva in target_match_rvas(target):
            by_rva[rva].append(target)

    found = defaultdict(list)
    seen = set()
    for section in pe.sections:
        if not section.is_executable or not section.raw_size:
            continue
        start = section.raw_pointer
        end = min(len(pe.data), start + section.raw_size)
        code = pe.data[start:end]
        for pos in iter_candidate_positions(code):
            for ref in decode_rel_refs(code, pos, section.virtual_address):
                for target in by_rva.get(ref["targetRva"], []):
                    key = (target.name, target.rva, ref["xrefRva"], ref["kind"])
                    if key not in seen:
                        seen.add(key)
                        found[target].append(ref)
            for ref in decode_rip_memory_refs(code, pos, section.virtual_address):
                for target in by_rva.get(ref["targetRva"], []):
                    key = (target.name, target.rva, ref["xrefRva"], ref["kind"])
                    if key not in seen:
                        seen.add(key)
                        found[target].append(ref)
    return found


def extract_ascii_strings(pe, start_file, end_file, min_len=4):
    strings = []
    cursor = start_file
    data = pe.data
    end_file = min(end_file, len(data))
    while cursor < end_file:
        if not is_ascii_string_byte(data[cursor]):
            cursor += 1
            continue
        start = cursor
        while cursor < end_file and is_ascii_string_byte(data[cursor]):
            cursor += 1
        if cursor - start >= min_len:
            try:
                strings.append(
                    {
                        "fileOffset": start,
                        "rva": file_offset_to_rva(pe, start),
                        "text": data[start:cursor].decode("ascii", errors="replace"),
                    }
                )
            except ValueError:
                pass
    return strings


def nearby_strings(pe, target, radius):
    if target.file_offset is None:
        return []
    try:
        section = section_for_file_offset(pe, target.file_offset)
    except ValueError:
        return []
    start = max(section.raw_pointer, target.file_offset - radius)
    end = min(section.raw_pointer + section.raw_size, target.file_offset + radius)
    return extract_ascii_strings(pe, start, end)


def signature_seed(pe, ref, prefix, suffix):
    xref_file = rva_to_file_offset(pe, ref["xrefRva"])
    section = section_for_file_offset(pe, xref_file)
    seed_start = max(section.raw_pointer, xref_file - prefix)
    seed_end = min(section.raw_pointer + section.raw_size, xref_file + ref["length"] + suffix)
    raw = pe.data[seed_start:seed_end]
    wildcard_start = xref_file + ref.get("dispOffset", 0)
    wildcard_end = wildcard_start + 4
    parts = []
    for index, value in enumerate(raw):
        file_offset = seed_start + index
        if wildcard_start <= file_offset < wildcard_end:
            parts.append("??")
        else:
            parts.append(f"{value:02x}")
    return {
        "fileOffset": format_hex(seed_start),
        "rva": format_hex(file_offset_to_rva(pe, seed_start)),
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "pattern": " ".join(parts),
    }


def serializable(pe, targets, xrefs, context_radius, signature_prefix=8, signature_suffix=16):
    rows = []
    for target in targets:
        refs = xrefs.get(target, [])
        rows.append(
            {
                "name": target.name,
                "category": target.category,
                "kind": target.kind,
                "rva": format_hex(target.rva),
                "fileOffset": format_hex(target.file_offset),
                "stringStartRva": format_hex(target.string_start_rva),
                "stringStartFileOffset": format_hex(target.string_start_file_offset),
                "source": target.source,
                "xrefCount": len(refs),
                "xrefs": [
                    {
                        "kind": ref["kind"],
                        "xrefRva": format_hex(ref["xrefRva"]),
                        "xrefFileOffset": format_hex(rva_to_file_offset(pe, ref["xrefRva"])),
                        "targetRva": format_hex(ref["targetRva"]),
                        "targetFileOffset": format_hex(rva_to_file_offset(pe, ref["targetRva"])),
                        "length": ref["length"],
                        "dispOffset": ref["dispOffset"],
                        "bytes": ref["bytes"],
                        "signatureSeed": signature_seed(pe, ref, signature_prefix, signature_suffix),
                    }
                    for ref in refs
                ],
                "nearbyStrings": [
                    {
                        "rva": format_hex(item["rva"]),
                        "fileOffset": format_hex(item["fileOffset"]),
                        "text": item["text"],
                    }
                    for item in nearby_strings(pe, target, context_radius)
                ],
            }
        )
    return {
        "format": "pe64" if pe.machine == 0x8664 else "pe",
        "imageBase": format_hex(pe.image_base),
        "sectionCount": len(pe.sections),
        "targetCount": len(targets),
        "targetsWithXrefs": sum(1 for target in targets if xrefs.get(target)),
        "xrefCount": sum(len(refs) for refs in xrefs.values()),
        "targets": rows,
    }


def markdown(summary, limit, max_targets, show_context, show_seeds):
    lines = []
    lines.append("# Windows Client Loader Xref Summary")
    lines.append("")
    lines.append(f"- Format: `{summary['format']}`")
    lines.append(f"- Image base: `{summary['imageBase']}`")
    lines.append(f"- Sections: `{summary['sectionCount']}`")
    lines.append(f"- Targets: `{summary['targetCount']}`")
    lines.append(f"- Targets with xrefs: `{summary['targetsWithXrefs']}`")
    lines.append(f"- Xrefs: `{summary['xrefCount']}`")
    lines.append("")

    rows = sorted(
        summary["targets"],
        key=lambda item: (item["category"], item["name"], -item["xrefCount"], item["rva"]),
    )
    if max_targets > 0:
        visible_rows = rows[:max_targets]
    else:
        visible_rows = rows

    current_category = None
    for row in visible_rows:
        if row["category"] != current_category:
            current_category = row["category"]
            lines.append(f"## {current_category}")
            lines.append("")
        anchor_suffix = ""
        if row["stringStartRva"] and row["stringStartRva"] != row["rva"]:
            anchor_suffix = f" stringStart=`{row['stringStartRva']}`"
        lines.append(
            f"- `{row['name']}` rva=`{row['rva']}` file=`{row['fileOffset']}` "
            f"xrefs=`{row['xrefCount']}`{anchor_suffix}"
        )
        for ref in row["xrefs"][:limit]:
            lines.append(
                f"  - xref=`{ref['xrefRva']}` file=`{ref['xrefFileOffset']}` "
                f"`{ref['kind']}` bytes=`{ref['bytes']}`"
            )
            if show_seeds:
                lines.append(
                    f"    seed=`{ref['signatureSeed']['pattern']}` "
                    f"seedFile=`{ref['signatureSeed']['fileOffset']}`"
                )
        if len(row["xrefs"]) > limit:
            lines.append(f"  - ... +{len(row['xrefs']) - limit} more")
        if show_context:
            for item in row["nearbyStrings"][:limit]:
                text = item["text"]
                if len(text) > 120:
                    text = text[:117] + "..."
                lines.append(f"  - string `{item['rva']}` `{text}`")
            if len(row["nearbyStrings"]) > limit:
                lines.append(f"  - ... +{len(row['nearbyStrings']) - limit} more strings")
    if len(rows) > len(visible_rows):
        lines.append("")
        lines.append(f"... +{len(rows) - len(visible_rows)} more targets. Use `--max-targets 0` for all rows.")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find simple x86-64 references to Windows client loader scan anchors.")
    parser.add_argument("binary", type=Path, help="DuneSandbox-Win64-Shipping.exe or another PE image")
    parser.add_argument("--loader-log", type=Path, help="client probe loader log to source targets from")
    parser.add_argument("--loader", action="append", default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--target", action="append", default=[], help="manual target as NAME=RVA")
    parser.add_argument("--rva", action="append", default=[], help="manual unnamed target RVA")
    parser.add_argument("--file-target", action="append", default=[], help="manual target as NAME=FILE_OFFSET")
    parser.add_argument("--file-offset", action="append", default=[], help="manual unnamed target file offset")
    parser.add_argument("--context-radius", type=int, default=96)
    parser.add_argument("--signature-prefix", type=int, default=8)
    parser.add_argument("--signature-suffix", type=int, default=16)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=6, help="xref/context rows per target in markdown")
    parser.add_argument("--max-targets", type=int, default=120, help="maximum target rows in markdown, or 0 for all")
    parser.add_argument("--show-context", action="store_true", help="show nearby ASCII strings in markdown")
    parser.add_argument("--show-seeds", action="store_true", help="show wildcarded signature seed windows in markdown")
    args = parser.parse_args(argv)

    pe = load_pe_image(args.binary)
    targets = []
    if args.loader_log:
        loader_filter = args.loader or ["win-client"]
        exe_filter = args.exe_substring or ["DuneSandbox-Win64-Shipping"]
        targets.extend(
            targets_from_log(pe, args.loader_log, loader_filter, args.pid, exe_filter, args.category, args.name)
        )
    targets.extend(targets_from_args(pe, args.target, args.rva, args.file_target, args.file_offset))
    if not targets:
        parser.error("provide --loader-log, --target, --rva, --file-target, or --file-offset")

    xrefs = scan_xrefs(pe, targets)
    summary = serializable(pe, targets, xrefs, args.context_radius, args.signature_prefix, args.signature_suffix)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit, args.max_targets, args.show_context, args.show_seeds))


if __name__ == "__main__":
    main()
