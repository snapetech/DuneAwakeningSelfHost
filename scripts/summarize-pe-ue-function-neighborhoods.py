#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


ROOT = Path(__file__).resolve().parents[1]
CLIENT_XREF_SCRIPT = ROOT / "scripts" / "summarize-client-loader-xrefs.py"
IMAGE_SCN_MEM_EXECUTE = 0x20000000
IMAGE_SCN_MEM_READ = 0x40000000
IMAGE_SCN_MEM_WRITE = 0x80000000
ANCHOR_GROUPS = {
    "names": ("FNamePool", "GName", "GNames", "FName::", "FName "),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "UWorld::", "UWorld "),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject::", "UFunction::", "UClass::", "FProperty::", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct::", "UEnum::"),
}
EXACT_ANCHOR_HINTS = {
    "FNamePool": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "NamePoolData": ("NamePoolData",),
    "GName": ("GName",),
    "GNames": ("GNames",),
    "GUObjectArray": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "GObjectArray": ("GObjectArray",),
    "GObjects": ("GObjects",),
    "FUObjectArray": ("FUObjectArray",),
    "GWorld": ("GWorld",),
    "GEngine": ("GEngine",),
    "ProcessEvent": ("ProcessEvent",),
    "StaticFindObject": ("StaticFindObject",),
    "CallFunctionByNameWithArguments": ("CallFunctionByNameWithArguments",),
    "CallFunctionByName": ("CallFunctionByName",),
    "StaticLoadObject": ("StaticLoadObject",),
    "LoadAsset": ("LoadAsset",),
    "LoadClass": ("LoadClass",),
    "LoadObject": ("LoadObject",),
    "LoadPackage": ("LoadPackage",),
    "ResolveName": ("ResolveName",),
    "UObject": ("UObject",),
    "UFunction": ("UFunction",),
    "UClass": ("UClass",),
    "FProperty": ("FProperty",),
    "UStruct": ("UStruct",),
    "UEnum": ("UEnum",),
}
REQUIRED_GROUPS = ("names", "objects", "world", "dispatch")


@dataclass(frozen=True)
class Seed:
    rva: int
    file_offset: int
    source_name: str
    source_group: str
    source_role: str
    source_slot: str


def import_script(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value, default=None):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def section_flags(section):
    if not section:
        return ""
    return "".join(
        flag
        for bit, flag in (
            (IMAGE_SCN_MEM_READ, "R"),
            (IMAGE_SCN_MEM_WRITE, "W"),
            (IMAGE_SCN_MEM_EXECUTE, "X"),
        )
        if section.characteristics & bit
    )


def text_groups(*values):
    haystack = "\n".join(value for value in values if value)
    return [group for group, needles in ANCHOR_GROUPS.items() if any(needle in haystack for needle in needles)]


def exact_anchor_hints(*values):
    haystack = "\n".join(value for value in values if value)
    return [
        anchor
        for anchor, needles in EXACT_ANCHOR_HINTS.items()
        if any(re.search(rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])", haystack) for needle in needles)
    ]


def section_for_rva(pe, rva):
    for section in pe.sections:
        if section.contains_rva(rva):
            return section
    return None


def rva_to_file_offset(pe, rva):
    section = section_for_rva(pe, rva)
    if not section:
        return None
    offset = rva - section.virtual_address
    if offset >= section.raw_size:
        return None
    return section.raw_pointer + offset


def value_to_rva(pe, value):
    return value - pe.image_base if value >= pe.image_base else value


def printable_hint(pe, rva):
    file_offset = rva_to_file_offset(pe, rva)
    if file_offset is None:
        return ""
    raw = pe.data[file_offset : min(len(pe.data), file_offset + 96)]
    chars = []
    for byte in raw:
        if byte == 0:
            break
        if byte in (0x09, 0x20) or 0x21 <= byte <= 0x7E:
            chars.append(byte)
        else:
            break
    return bytes(chars).decode("ascii", errors="replace") if len(chars) >= 4 else ""


def target_hint(pe, value):
    rva = value_to_rva(pe, value)
    section = section_for_rva(pe, rva)
    string = printable_hint(pe, rva) if section else ""
    return {
        "target": f"0x{rva:x}",
        "section": section.name if section else "",
        "flags": section_flags(section),
        "symbols": [],
        "string": string,
        "groups": text_groups(string),
        "exactAnchorHints": exact_anchor_hints(string),
    }


def signature(pe, seed, length, count_uniqueness):
    section = section_for_rva(pe, seed.rva)
    if not section:
        return None
    end = min(section.raw_pointer + section.raw_size, seed.file_offset + length)
    raw = pe.data[seed.file_offset:end]
    pattern = " ".join(f"{byte:02x}" for byte in raw)
    return {
        "fileOffset": f"0x{seed.file_offset:x}",
        "imageOffset": f"0x{seed.rva:x}",
        "vaddr": f"0x{pe.image_base + seed.rva:x}",
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "pattern": pattern,
        "matchCount": pattern_match_count(pe.data, raw) if count_uniqueness else None,
    }


def pattern_match_count(data, raw):
    if not raw:
        return 0
    count = 0
    cursor = 0
    while True:
        found = data.find(raw, cursor)
        if found < 0:
            return count
        count += 1
        if count > 32:
            return count
        cursor = found + 1


def harvest_xref_summary_seeds(summary, limit):
    seeds = {}
    for target in summary.get("targets", []):
        name = target.get("name", "")
        category = target.get("category", "")
        target_rva = target.get("rva", "")
        for index, ref in enumerate(target.get("xrefs", []), 1):
            rva = parse_int(ref.get("xrefRva", ""))
            file_offset = parse_int(ref.get("xrefFileOffset", ""))
            if rva is None or file_offset is None:
                continue
            seeds.setdefault(
                rva,
                Seed(
                    rva=rva,
                    file_offset=file_offset,
                    source_name=f"{name}@{target_rva}#{index}" if target_rva else f"{name}#{index}",
                    source_group=category,
                    source_role="xref",
                    source_slot=ref.get("kind", ""),
                ),
            )
            if len(seeds) >= limit:
                return list(seeds.values())
    return list(seeds.values())


def build_xref_summary(xrefs, args):
    pe = xrefs.load_pe_image(args.binary)
    loader_filter = args.loader or ["win-client"]
    exe_filter = args.exe_substring or ["DuneSandbox-Win64-Shipping"]
    targets = xrefs.targets_from_log(pe, args.loader_log, loader_filter, args.pid, exe_filter, args.category, args.name)
    found = xrefs.scan_xrefs(pe, targets)
    return xrefs.serializable(pe, targets, found, args.context_radius), pe


def analyze_seed(pe, seed, prelude, window, signature_length, count_uniqueness):
    section = section_for_rva(pe, seed.rva)
    if not section:
        return None
    start_file = max(section.raw_pointer, seed.file_offset - prelude)
    start_rva = section.virtual_address + (start_file - section.raw_pointer)
    code = pe.data[start_file : min(section.raw_pointer + section.raw_size, start_file + window)]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    refs = []
    calls = []
    instruction_count = 0
    base = pe.image_base + start_rva
    for insn in md.disasm(code, base):
        instruction_count += 1
        if instruction_count > 240:
            break
        text = f"{insn.mnemonic} {insn.op_str}".strip()
        for operand in insn.operands:
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                refs.append(
                    {
                        "instruction": f"0x{insn.address:x}",
                        "text": text,
                        "kind": "rip-memory",
                        **target_hint(pe, insn.address + insn.size + operand.mem.disp),
                    }
                )
            elif operand.type == X86_OP_IMM and insn.mnemonic.startswith(("call", "jmp")):
                calls.append(
                    {
                        "instruction": f"0x{insn.address:x}",
                        "text": text,
                        "kind": "rel-control",
                        **target_hint(pe, int(operand.imm)),
                    }
                )
    group_counts = Counter(group for ref in refs + calls for group in ref.get("groups", []))
    writable_refs = [ref for ref in refs if "W" in section_flags(section_for_rva(pe, parse_int(ref.get("target", ""))))]
    sig_seed = Seed(start_rva, start_file, seed.source_name, seed.source_group, seed.source_role, seed.source_slot)
    sig = signature(pe, sig_seed, signature_length, count_uniqueness)
    return {
        "function": f"0x{start_rva:x}",
        "fileOffset": f"0x{start_file:x}",
        "sourceName": seed.source_name,
        "sourceGroup": seed.source_group,
        "sourceRole": seed.source_role,
        "sourceSlot": seed.source_slot,
        "instructionCount": instruction_count,
        "refCount": len(refs),
        "callCount": len(calls),
        "groupCounts": dict(sorted(group_counts.items())),
        "requiredGroupCoverage": [group for group in REQUIRED_GROUPS if group_counts.get(group)],
        "writableRefCount": len(writable_refs),
        "uniqueSignature": bool(sig and sig.get("matchCount") == 1),
        "signature": sig,
        "refs": refs[:80],
        "calls": calls[:80],
    }


def summarize_writable_targets(functions):
    rows = {}
    for function in functions:
        source_groups = text_groups(function.get("sourceName", ""))
        source_exact = exact_anchor_hints(function.get("sourceName", ""))
        for ref in function.get("refs", []):
            if "W" not in ref.get("flags", ""):
                continue
            key = ref.get("target", "")
            if not key:
                continue
            row = rows.setdefault(
                key,
                {
                    "target": key,
                    "section": ref.get("section", ""),
                    "refCount": 0,
                    "functionCount": Counter(),
                    "sourceNames": Counter(),
                    "groups": Counter(),
                    "exactAnchorHints": Counter(),
                    "context": [],
                },
            )
            row["refCount"] += 1
            row["functionCount"][function.get("function", "")] += 1
            row["sourceNames"][function.get("sourceName", "")] += 1
            groups = list(dict.fromkeys((ref.get("groups", []) or []) + source_groups))
            exact = list(dict.fromkeys((ref.get("exactAnchorHints", []) or []) + source_exact))
            for group in groups:
                row["groups"][group] += 1
            for anchor in exact:
                row["exactAnchorHints"][anchor] += 1
            if len(row["context"]) < 12:
                row["context"].append(
                    {
                        "xref": ref.get("instruction", ""),
                        "target": ref.get("target", ""),
                        "section": ref.get("section", ""),
                        "flags": ref.get("flags", ""),
                        "groups": groups,
                        "exactAnchorHints": exact,
                        "symbols": ref.get("symbols", []) or [],
                        "string": ref.get("string", "") or function.get("sourceName", ""),
                    }
                )
    summarized = []
    for row in rows.values():
        summarized.append(
            {
                "target": row["target"],
                "section": row["section"],
                "refCount": row["refCount"],
                "functionCount": len(row["functionCount"]),
                "sourceNames": dict(row["sourceNames"].most_common(12)),
                "groups": dict(row["groups"].most_common()),
                "exactAnchorHintCounts": dict(row["exactAnchorHints"].most_common()),
                "context": row["context"],
            }
        )
    summarized.sort(
        key=lambda row: (
            -sum(row["exactAnchorHintCounts"].values()),
            -sum(row["groups"].values()),
            -row["refCount"],
            row["target"],
        )
    )
    return summarized


def summarize(args):
    xrefs = import_script(CLIENT_XREF_SCRIPT, "summarize_client_loader_xrefs_for_pe_neighborhoods")
    if args.xref_json:
        summary = load_json(args.xref_json)
        pe = xrefs.load_pe_image(args.binary)
    else:
        summary, pe = build_xref_summary(xrefs, args)
    seeds = harvest_xref_summary_seeds(summary, args.seed_limit)
    functions = []
    for seed in seeds:
        row = analyze_seed(pe, seed, args.prelude, args.window, args.signature_length, args.count_uniqueness)
        if row:
            functions.append(row)
    writable_targets = summarize_writable_targets(functions)
    limit = getattr(args, "limit", 40)
    return {
        "schemaVersion": "dune-pe-ue-function-neighborhoods/v1",
        "binary": str(args.binary),
        "imageBase": f"0x{pe.image_base:x}",
        "seedCount": len(seeds),
        "functionCount": len(functions),
        "writableTargetCount": len(writable_targets),
        "writableTargets": writable_targets[:limit],
        "functions": functions,
    }


def markdown(summary, limit):
    lines = ["# PE UE Function Neighborhoods", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Image base: `{summary['imageBase']}`")
    lines.append(f"- Seeds: `{summary['seedCount']}`")
    lines.append(f"- Functions: `{summary['functionCount']}`")
    lines.append(f"- Writable targets: `{summary.get('writableTargetCount', 0)}`")
    lines.append("")
    if summary.get("writableTargets"):
        lines.append("## Writable Targets")
        lines.append("")
        for row in summary["writableTargets"][:20]:
            lines.append(
                f"- target=`{row['target']}` section=`{row['section']}` refs=`{row['refCount']}` "
                f"functions=`{row['functionCount']}` exact=`{row['exactAnchorHintCounts']}` "
                f"groups=`{row['groups']}` sources=`{row['sourceNames']}`"
            )
        lines.append("")
    for row in summary["functions"][:limit]:
        lines.append(
            f"- function=`{row['function']}` file=`{row['fileOffset']}` source=`{row['sourceName']}` "
            f"refs=`{row['refCount']}` writableRefs=`{row['writableRefCount']}` calls=`{row['callCount']}` "
            f"groups=`{row['groupCounts']}`"
        )
        for ref in row["refs"][:6]:
            detail = ref.get("string", "")
            suffix = f" detail=`{detail}`" if detail else ""
            lines.append(
                f"  - `{ref['instruction']}` `{ref['text']}` -> `{ref['target']}` "
                f"section=`{ref['section']}`{suffix}"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize PE UE function neighborhoods from Windows client xrefs.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("--xref-json", type=Path)
    parser.add_argument("--loader-log", type=Path)
    parser.add_argument("--loader", action="append", default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--context-radius", type=int, default=96)
    parser.add_argument("--seed-limit", type=int, default=512)
    parser.add_argument("--prelude", type=int, default=32)
    parser.add_argument("--window", type=int, default=384)
    parser.add_argument("--signature-length", type=int, default=32)
    parser.add_argument("--count-uniqueness", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)
    if not args.xref_json and not args.loader_log:
        parser.error("provide --xref-json or --loader-log")

    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
