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


PT_LOAD = 1
PF_X = 1
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
class Segment:
    file_offset: int
    file_size: int
    vaddr: int
    mem_size: int
    flags: int

    def contains_file_offset(self, offset):
        return self.file_offset <= offset < self.file_offset + self.file_size


@dataclass(frozen=True)
class Target:
    name: str
    category: str
    kind: str
    file_offset: int
    image_offset: int
    vaddr: int


def parse_int(value):
    if isinstance(value, int):
        return value
    return int(value, 16 if value.lower().startswith("0x") else 10)


def load_elf_segments(binary):
    data = binary.read_bytes()
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise ValueError(f"{binary} is not an ELF file")
    if data[4] != 2 or data[5] != 1:
        raise ValueError(f"{binary} is not a 64-bit little-endian ELF")

    e_phoff = struct.unpack_from("<Q", data, 32)[0]
    e_phentsize = struct.unpack_from("<H", data, 54)[0]
    e_phnum = struct.unpack_from("<H", data, 56)[0]
    segments = []
    for index in range(e_phnum):
        offset = e_phoff + index * e_phentsize
        if offset + 56 > len(data):
            break
        p_type, p_flags, p_offset, p_vaddr, _p_paddr, p_filesz, p_memsz, _p_align = struct.unpack_from(
            "<IIQQQQQQ", data, offset
        )
        if p_type == PT_LOAD and p_filesz:
            segments.append(Segment(p_offset, p_filesz, p_vaddr, p_memsz, p_flags))
    return data, segments


def file_offset_to_vaddr(segments, file_offset):
    for segment in segments:
        if segment.contains_file_offset(file_offset):
            return segment.vaddr + (file_offset - segment.file_offset)
    raise ValueError(f"file offset 0x{file_offset:x} is not inside a LOAD segment")


def segment_for_file_offset(segments, file_offset):
    for segment in segments:
        if segment.contains_file_offset(file_offset):
            return segment
    raise ValueError(f"file offset 0x{file_offset:x} is not inside a LOAD segment")


def vaddr_to_file_offset(segments, vaddr):
    for segment in segments:
        if segment.vaddr <= vaddr < segment.vaddr + segment.file_size:
            return segment.file_offset + (vaddr - segment.vaddr)
    raise ValueError(f"vaddr 0x{vaddr:x} is not inside a file-backed LOAD segment")


def import_scan_summary():
    script = Path(__file__).resolve().parent / "summarize-linux-loader-scan.py"
    spec = importlib.util.spec_from_file_location("summarize_linux_loader_scan", script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def targets_from_log(log_path, segments, exe_substring, pid, categories, names):
    scan_summary = import_scan_summary()
    summary = scan_summary.summarize(scan_summary.load_records(log_path), exe_substring, pid)
    targets = []
    category_filter = set(categories or [])
    name_filter = set(names or [])
    seen = set()
    for name, data in summary["hitsByName"].items():
        category = data["category"]
        if category_filter and category not in category_filter:
            continue
        if name_filter and name not in name_filter:
            continue
        for offset_record in data["offsets"]:
            raw_file = offset_record.get("fileOffset") or offset_record.get("imageOffset")
            raw_image = offset_record.get("imageOffset") or raw_file
            if not raw_file:
                continue
            file_offset = parse_int(raw_file)
            image_offset = parse_int(raw_image)
            key = (name, file_offset, offset_record.get("kind", ""))
            if key in seen:
                continue
            seen.add(key)
            try:
                vaddr = file_offset_to_vaddr(segments, file_offset)
            except ValueError:
                continue
            targets.append(
                Target(
                    name=name,
                    category=category,
                    kind=offset_record.get("kind", ""),
                    file_offset=file_offset,
                    image_offset=image_offset,
                    vaddr=vaddr,
                )
            )
    return targets


def targets_from_args(raw_targets, raw_offsets, segments):
    targets = []
    for raw in raw_targets or []:
        if "=" not in raw:
            raise ValueError(f"--target must be NAME=OFFSET, got {raw!r}")
        name, raw_offset = raw.split("=", 1)
        file_offset = parse_int(raw_offset)
        targets.append(
            Target(
                name=name,
                category="manual",
                kind="manual",
                file_offset=file_offset,
                image_offset=file_offset,
                vaddr=file_offset_to_vaddr(segments, file_offset),
            )
        )
    for raw in raw_offsets or []:
        file_offset = parse_int(raw)
        targets.append(
            Target(
                name=f"0x{file_offset:x}",
                category="manual",
                kind="manual",
                file_offset=file_offset,
                image_offset=file_offset,
                vaddr=file_offset_to_vaddr(segments, file_offset),
            )
        )
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


def decode_rip_memory_refs(data, pos, base_vaddr):
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
        target_vaddr = base_vaddr + end + disp
        refs.append(
            {
                "kind": "rip-memory",
                "xrefVaddr": base_vaddr + pos,
                "length": end - pos,
                "dispOffset": disp_offset - pos,
                "targetVaddr": target_vaddr,
                "bytes": hex_bytes(data, pos, min(end - pos, 16)),
            }
        )
    return refs


def decode_rel_refs(data, pos, base_vaddr):
    op = data[pos]
    refs = []
    if op in (0xE8, 0xE9) and pos + 5 <= len(data):
        disp = signed32(data, pos + 1)
        refs.append(
            {
                "kind": "rel-call-jump",
                "xrefVaddr": base_vaddr + pos,
                "length": 5,
                "dispOffset": 1,
                "targetVaddr": base_vaddr + pos + 5 + disp,
                "bytes": hex_bytes(data, pos, 5),
            }
        )
    elif op == 0x0F and pos + 6 <= len(data) and 0x80 <= data[pos + 1] <= 0x8F:
        disp = signed32(data, pos + 2)
        refs.append(
            {
                "kind": "rel-jcc",
                "xrefVaddr": base_vaddr + pos,
                "length": 6,
                "dispOffset": 2,
                "targetVaddr": base_vaddr + pos + 6 + disp,
                "bytes": hex_bytes(data, pos, 6),
            }
        )
    return refs


def scan_xrefs(binary_data, segments, targets):
    by_vaddr = defaultdict(list)
    for target in targets:
        by_vaddr[target.vaddr].append(target)

    found = defaultdict(list)
    seen = set()
    for segment in segments:
        if not (segment.flags & PF_X):
            continue
        start = segment.file_offset
        end = start + segment.file_size
        code = binary_data[start:end]
        for pos in iter_candidate_positions(code):
            for ref in decode_rel_refs(code, pos, segment.vaddr):
                for target in by_vaddr.get(ref["targetVaddr"], []):
                    key = (target.name, target.file_offset, ref["xrefVaddr"], ref["kind"])
                    if key not in seen:
                        seen.add(key)
                        found[target].append(ref)
            for ref in decode_rip_memory_refs(code, pos, segment.vaddr):
                for target in by_vaddr.get(ref["targetVaddr"], []):
                    key = (target.name, target.file_offset, ref["xrefVaddr"], ref["kind"])
                    if key not in seen:
                        seen.add(key)
                        found[target].append(ref)
    return found


def signature_seed(binary_data, segments, ref, prefix, suffix):
    xref_file = vaddr_to_file_offset(segments, ref["xrefVaddr"])
    segment = segment_for_file_offset(segments, xref_file)
    seed_start = max(segment.file_offset, xref_file - prefix)
    seed_end = min(segment.file_offset + segment.file_size, xref_file + ref["length"] + suffix)
    raw = binary_data[seed_start:seed_end]
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
        "fileOffset": f"0x{seed_start:x}",
        "imageOffset": f"0x{seed_start:x}",
        "vaddr": f"0x{file_offset_to_vaddr(segments, seed_start):x}",
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "pattern": " ".join(parts),
    }


def serializable(binary_data, segments, targets, xrefs, signature_prefix=8, signature_suffix=16):
    rows = []
    for target in targets:
        refs = xrefs.get(target, [])
        rows.append(
            {
                "name": target.name,
                "category": target.category,
                "kind": target.kind,
                "fileOffset": f"0x{target.file_offset:x}",
                "imageOffset": f"0x{target.image_offset:x}",
                "vaddr": f"0x{target.vaddr:x}",
                "xrefCount": len(refs),
                "xrefs": [
                    {
                        "kind": ref["kind"],
                        "xrefVaddr": f"0x{ref['xrefVaddr']:x}",
                        "targetVaddr": f"0x{ref['targetVaddr']:x}",
                        "bytes": ref["bytes"],
                        "signatureSeed": signature_seed(binary_data, segments, ref, signature_prefix, signature_suffix),
                    }
                    for ref in refs
                ],
            }
        )
    return {
        "targetCount": len(targets),
        "targetsWithXrefs": sum(1 for target in targets if xrefs.get(target)),
        "targets": rows,
    }


def markdown(summary, limit):
    lines = []
    lines.append("# Linux Loader Xref Summary")
    lines.append("")
    lines.append(f"- Targets: `{summary['targetCount']}`")
    lines.append(f"- Targets with xrefs: `{summary['targetsWithXrefs']}`")
    lines.append("")
    current_category = None
    for row in sorted(summary["targets"], key=lambda item: (item["category"], item["name"], item["fileOffset"])):
        if row["category"] != current_category:
            current_category = row["category"]
            lines.append(f"## {current_category}")
            lines.append("")
        lines.append(
            f"- `{row['name']}` file=`{row['fileOffset']}` image=`{row['imageOffset']}` "
            f"xrefs=`{row['xrefCount']}`"
        )
        for ref in row["xrefs"][:limit]:
            seed = ref.get("signatureSeed", {})
            seed_text = f" seed=`{seed.get('pattern', '')}` seedFile=`{seed.get('fileOffset', '')}`" if seed else ""
            lines.append(f"  - `{ref['xrefVaddr']}` `{ref['kind']}` bytes=`{ref['bytes']}`{seed_text}")
        if len(row["xrefs"]) > limit:
            lines.append(f"  - ... +{len(row['xrefs']) - limit} more")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find simple x86-64 references to Linux loader scan anchors.")
    parser.add_argument("binary", type=Path, help="DuneSandboxServer-Linux-Shipping binary")
    parser.add_argument("--loader-log", type=Path, help="probe loader log to source targets from")
    parser.add_argument("--exe-substring", default="DuneSandboxServer")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--target", action="append", default=[], help="manual target as NAME=FILE_OFFSET")
    parser.add_argument("--offset", action="append", default=[], help="manual target file offset")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=8, help="xref rows per target in markdown")
    parser.add_argument("--signature-prefix", type=int, default=8)
    parser.add_argument("--signature-suffix", type=int, default=16)
    args = parser.parse_args(argv)

    binary_data, segments = load_elf_segments(args.binary)
    targets = []
    if args.loader_log:
        targets.extend(
            targets_from_log(args.loader_log, segments, args.exe_substring, args.pid, args.category, args.name)
        )
    targets.extend(targets_from_args(args.target, args.offset, segments))
    if not targets:
        parser.error("provide --loader-log, --target, or --offset")

    xrefs = scan_xrefs(binary_data, segments, targets)
    summary = serializable(binary_data, segments, targets, xrefs, args.signature_prefix, args.signature_suffix)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit))


if __name__ == "__main__":
    main()
