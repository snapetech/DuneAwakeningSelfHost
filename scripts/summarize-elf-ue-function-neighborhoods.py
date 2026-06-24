#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
LINUX_XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"

ANCHOR_GROUPS = {
    "names": ("FNamePool", "GName", "GNames", "FName::", "FName "),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "UWorld::", "UWorld "),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
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
    "StaticLoadObject": ("StaticLoadObject", "load-object-static", "uobject-static-load-object"),
    "StaticLoadClass": ("StaticLoadClass", "load-class-static", "uobject-static-load-class"),
    "LoadAsset": ("LoadAsset", "load-asset"),
    "LoadClass": ("LoadClass",),
    "LoadObject": ("LoadObject", "uobject-load-object"),
    "LoadPackage": ("LoadPackage", "load-package", "upackage-load-package"),
    "ResolveName": ("ResolveName", "resolve-name", "uresolve-name"),
    "UObject": ("UObject",),
    "UFunction": ("UFunction",),
    "UClass": ("UClass",),
    "FProperty": ("FProperty",),
    "UStruct": ("UStruct",),
    "UEnum": ("UEnum",),
}
REQUIRED_GROUPS = ("names", "objects", "world", "dispatch")


@dataclass(frozen=True)
class FunctionSeed:
    vaddr: int
    source_name: str
    source_group: str
    source_role: str
    source_slot: str


def import_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value):
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def parse_explicit_seeds(raw_seeds):
    seeds = []
    for raw in raw_seeds or []:
        if "=" in raw:
            name, value = raw.split("=", 1)
        else:
            value = raw
            name = f"explicit-{value}"
        seeds.append(
            FunctionSeed(
                vaddr=parse_int(value),
                source_name=name,
                source_group="explicit",
                source_role="manual-seed",
                source_slot=value,
            )
        )
    return seeds


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def text_groups(*values):
    haystack = "\n".join(value for value in values if value)
    groups = []
    for group, needles in ANCHOR_GROUPS.items():
        if any(needle in haystack for needle in needles):
            groups.append(group)
    return groups


def exact_anchor_hints(*values):
    haystack = "\n".join(value for value in values if value)
    return [
        anchor
        for anchor, needles in EXACT_ANCHOR_HINTS.items()
        if any(re.search(rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])", haystack) for needle in needles)
    ]


def load_relocation_summary(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def harvest_function_seeds(summary, limit):
    seeds = {}
    for row in summary.get("rows", []):
        for context in row.get("contexts", []):
            for item in context.get("context", []):
                if item.get("section") != ".text":
                    continue
                value = parse_int(item["value"])
                seeds.setdefault(
                    value,
                    FunctionSeed(
                        vaddr=value,
                        source_name=row.get("name", ""),
                        source_group=row.get("group", ""),
                        source_role=row.get("role", ""),
                        source_slot=context.get("slot", ""),
                    ),
                )
    return list(seeds.values())[:limit]


def harvest_init_array_seeds(ptrctx, data, sections, relocations, limit):
    section = next((candidate for candidate in sections if candidate.name == ".init_array"), None)
    if section is None or section.entsize == 0 or limit <= 0:
        return []
    seeds = []
    count = section.size // section.entsize
    for index in range(count):
        slot = section.addr + index * section.entsize
        value, _source = ptrctx.qword_at_addr(data, sections, relocations, slot)
        if value is None:
            continue
        target_section = ptrctx.section_for_addr(sections, value)
        if target_section is None or target_section.name != ".text":
            continue
        seeds.append(
            FunctionSeed(
                vaddr=value,
                source_name=f".init_array[{index}]",
                source_group="init",
                source_role="constructor",
                source_slot=f"0x{slot:x}",
            )
        )
        if len(seeds) >= limit:
            break
    return seeds


def harvest_xref_summary_seeds(summary, limit, categories=None, names=None):
    category_filter = set(categories or [])
    name_filter = set(names or [])
    seeds = {}
    for target in summary.get("targets", []):
        name = target.get("name", "")
        category = target.get("category", "")
        if category_filter and category not in category_filter:
            continue
        if name_filter and name not in name_filter:
            continue
        target_vaddr = target.get("vaddr", "")
        for index, ref in enumerate(target.get("xrefs", []), 1):
            raw_vaddr = ref.get("xrefVaddr") or ref.get("xref")
            if not raw_vaddr:
                continue
            try:
                vaddr = parse_int(raw_vaddr)
            except ValueError:
                continue
            seeds.setdefault(
                vaddr,
                FunctionSeed(
                    vaddr=vaddr,
                    source_name=f"{name}@{target_vaddr}#{index}" if target_vaddr else f"{name}#{index}",
                    source_group=category,
                    source_role="xref",
                    source_slot=ref.get("kind", ""),
                ),
            )
            if len(seeds) >= limit:
                return list(seeds.values())
    return list(seeds.values())


def pattern_match_count(data, pattern):
    tokens = [None if token in ("?", "??") else int(token, 16) for token in pattern.split()]
    if not tokens:
        return 0
    count = 0
    for offset in range(0, max(0, len(data) - len(tokens) + 1)):
        for index, expected in enumerate(tokens):
            if expected is not None and data[offset + index] != expected:
                break
        else:
            count += 1
            if count > 32:
                return count
    return count


def function_signature(data, segments, xrefs, vaddr, length, count_uniqueness):
    try:
        file_offset = xrefs.vaddr_to_file_offset(segments, vaddr)
    except ValueError:
        return None
    segment = xrefs.segment_for_file_offset(segments, file_offset)
    end = min(segment.file_offset + segment.file_size, file_offset + length)
    raw = data[file_offset:end]
    pattern = " ".join(f"{byte:02x}" for byte in raw)
    signature = {
        "fileOffset": f"0x{file_offset:x}",
        "imageOffset": f"0x{file_offset:x}",
        "vaddr": f"0x{vaddr:x}",
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "pattern": pattern,
        "matchCount": None,
    }
    if count_uniqueness:
        signature["matchCount"] = pattern_match_count(data, pattern)
    return signature


def build_xref_summary(xrefs, data, segments, args):
    targets = xrefs.targets_from_log(
        args.loader_log,
        segments,
        args.exe_substring,
        args.pid,
        args.category,
        args.name,
    )
    if not targets:
        return {"targetCount": 0, "targetsWithXrefs": 0, "targets": []}
    found = xrefs.scan_xrefs(data, segments, targets)
    return xrefs.serializable(data, segments, targets, found)


def target_hint(ptrctx, data, sections, symbols, target):
    section = ptrctx.section_for_addr(sections, target)
    string = ptrctx.printable_hint(data, sections, target)
    names = symbols.get(target, [])[:4]
    groups = text_groups(string, *names)
    exact_hints = exact_anchor_hints(string, *names)
    return {
        "target": f"0x{target:x}",
        "section": section.name if section else "",
        "symbols": names,
        "string": string,
        "groups": groups,
        "exactAnchorHints": exact_hints,
    }


def summarize_writable_targets(functions):
    rows = {}
    for function in functions:
        source_groups = text_groups(function.get("sourceName", ""))
        source_exact = exact_anchor_hints(function.get("sourceName", ""))
        for ref in function.get("refs", []):
            if not ref.get("target"):
                continue
            if not ref.get("section", "").startswith((".bss", ".data")):
                continue
            key = ref["target"]
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


def analyze_function(ptrctx, xrefs, data, segments, sections, symbols, seed, prelude, window, signature_length, count_uniqueness):
    try:
        file_offset = xrefs.vaddr_to_file_offset(segments, seed.vaddr)
    except ValueError:
        return None
    segment = xrefs.segment_for_file_offset(segments, file_offset)
    start_file = max(segment.file_offset, file_offset - prelude)
    start_vaddr = segment.vaddr + (start_file - segment.file_offset)
    code = data[start_file : min(start_file + window, segment.file_offset + segment.file_size)]
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    refs = []
    calls = []
    instruction_count = 0
    for insn in md.disasm(code, start_vaddr):
        instruction_count += 1
        if instruction_count > 240:
            break
        for operand in insn.operands:
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                target = insn.address + insn.size + operand.mem.disp
                hint = target_hint(ptrctx, data, sections, symbols, target)
                if hint["section"] or hint["symbols"] or hint["string"]:
                    refs.append(
                        {
                            "instruction": f"0x{insn.address:x}",
                            "text": f"{insn.mnemonic} {insn.op_str}".strip(),
                            "kind": "rip-memory",
                            **hint,
                        }
                    )
            elif operand.type == X86_OP_IMM and insn.mnemonic.startswith(("call", "jmp")):
                target = int(operand.imm)
                hint = target_hint(ptrctx, data, sections, symbols, target)
                calls.append(
                    {
                        "instruction": f"0x{insn.address:x}",
                        "text": f"{insn.mnemonic} {insn.op_str}".strip(),
                        "kind": "rel-control",
                        **hint,
                    }
                )

    group_counts = Counter(group for ref in refs + calls for group in ref.get("groups", []))
    writable_refs = [
        ref for ref in refs
        if ptrctx.section_for_addr(sections, parse_int(ref["target"]))
        and ptrctx.section_for_addr(sections, parse_int(ref["target"])).flags & 0x1
    ]
    signature = function_signature(data, segments, xrefs, start_vaddr, signature_length, count_uniqueness)
    return {
        "function": f"0x{start_vaddr:x}",
        "fileOffset": f"0x{start_file:x}",
        "seedVaddr": f"0x{seed.vaddr:x}",
        "seedFileOffset": f"0x{file_offset:x}",
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
        "uniqueSignature": bool(signature and signature["matchCount"] == 1),
        "signature": signature,
        "refs": refs[:80],
        "calls": calls[:80],
    }


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_ue_funcs")
    xrefs = import_script(LINUX_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_ue_funcs")
    data, segments = xrefs.load_elf_segments(args.binary)
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)
    relocations = ptrctx.load_relocations(data, sections)
    seed_map = {}
    source_summaries = {}
    if args.relocation_surface:
        relocation_summary = load_relocation_summary(args.relocation_surface)
        source_summaries["relocationSurface"] = str(args.relocation_surface)
        for seed in harvest_function_seeds(relocation_summary, args.seed_limit):
            seed_map.setdefault(seed.vaddr, seed)
    if args.xref_json:
        xref_summary = load_json(args.xref_json)
        source_summaries["xrefJson"] = str(args.xref_json)
        for seed in harvest_xref_summary_seeds(xref_summary, args.seed_limit, args.category, args.name):
            seed_map.setdefault(seed.vaddr, seed)
    if args.loader_log:
        xref_summary = build_xref_summary(xrefs, data, segments, args)
        source_summaries["loaderLog"] = str(args.loader_log)
        source_summaries["loaderLogTargets"] = xref_summary.get("targetCount", 0)
        source_summaries["loaderLogTargetsWithXrefs"] = xref_summary.get("targetsWithXrefs", 0)
        for seed in harvest_xref_summary_seeds(xref_summary, args.seed_limit, args.category, args.name):
            seed_map.setdefault(seed.vaddr, seed)
    if args.seed:
        source_summaries["explicitSeedCount"] = len(args.seed)
        for seed in parse_explicit_seeds(args.seed):
            seed_map.setdefault(seed.vaddr, seed)
    for seed in harvest_init_array_seeds(ptrctx, data, sections, relocations, args.init_limit):
        seed_map.setdefault(seed.vaddr, seed)
    seeds = list(seed_map.values())
    functions = []
    for seed in seeds:
        row = analyze_function(
            ptrctx,
            xrefs,
            data,
            segments,
            sections,
            symbols,
            seed,
            args.prelude,
            args.window,
            args.signature_length,
            args.count_signature_uniqueness,
        )
        if row:
            functions.append(row)
    functions.sort(
        key=lambda row: (
            -len(row["requiredGroupCoverage"]),
            -row["writableRefCount"],
            -sum(row["groupCounts"].values()),
            row["function"],
        )
    )
    coverage = Counter(group for row in functions for group in row["requiredGroupCoverage"])
    writable_targets = summarize_writable_targets(functions)
    return {
        "schemaVersion": "dune-elf-ue-function-neighborhoods/v1",
        "binary": str(args.binary),
        **source_summaries,
        "seedCount": len(seeds),
        "relocationSeedLimit": args.seed_limit,
        "initSeedLimit": args.init_limit,
        "functionCount": len(functions),
        "functionsWithRequiredGroups": sum(1 for row in functions if row["requiredGroupCoverage"]),
        "requiredGroupCoverage": dict(sorted(coverage.items())),
        "functionsWithWritableRefs": sum(1 for row in functions if row["writableRefCount"]),
        "functionsWithUniqueSignatures": sum(1 for row in functions if row["uniqueSignature"]),
        "writableTargetCount": len(writable_targets),
        "writableTargets": writable_targets[: args.limit],
        "functions": functions,
    }


def markdown(summary, limit):
    lines = ["# ELF UE Function Neighborhoods", ""]
    if summary.get("xrefJson"):
        lines.append(f"- Xref JSON: `{summary['xrefJson']}`")
    if summary.get("loaderLog"):
        lines.append(f"- Loader log: `{summary['loaderLog']}`")
    if summary.get("relocationSurface"):
        lines.append(f"- Relocation surface: `{summary['relocationSurface']}`")
    lines.append(f"- Function seeds: `{summary['seedCount']}`")
    lines.append(f"- Relocation seed limit: `{summary['relocationSeedLimit']}`")
    lines.append(f"- Init-array seed limit: `{summary['initSeedLimit']}`")
    lines.append(f"- Functions analyzed: `{summary['functionCount']}`")
    lines.append(f"- Functions with required UE groups: `{summary['functionsWithRequiredGroups']}`")
    lines.append(f"- Required group coverage: `{summary['requiredGroupCoverage']}`")
    lines.append(f"- Functions with writable refs: `{summary['functionsWithWritableRefs']}`")
    lines.append(f"- Functions with unique prologue signatures: `{summary['functionsWithUniqueSignatures']}`")
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
    lines.append("## Functions")
    lines.append("")
    if not summary["functions"]:
        lines.append("- none")
    for row in summary["functions"][:limit]:
        lines.append(
            f"- function=`{row['function']}` file=`{row['fileOffset']}` "
            f"source=`{row['sourceName']}` role=`{row['sourceRole']}` "
            f"groups=`{row['groupCounts']}` required=`{row['requiredGroupCoverage']}` "
            f"writableRefs=`{row['writableRefCount']}` uniqueSignature=`{str(row['uniqueSignature']).lower()}`"
        )
        for ref in (row["refs"] + row["calls"])[:8]:
            symbol = " | ".join(ref["symbols"]) if ref["symbols"] else ""
            string = f" string={ref['string']!r}" if ref["string"] else ""
            groups = f" groups={','.join(ref['groups'])}" if ref["groups"] else ""
            symbol_text = f" symbol={symbol}" if symbol else ""
            lines.append(
                f"  - `{ref['instruction']}` `{ref['kind']}` target=`{ref['target']}` "
                f"section=`{ref['section'] or '-'}`{groups}{symbol_text}{string}"
            )
    if len(summary["functions"]) > limit:
        lines.append(f"- ... +{len(summary['functions']) - limit} more")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Disassemble executable functions adjacent to UE relocation metadata and classify their references."
    )
    parser.add_argument("binary", type=Path)
    parser.add_argument("--relocation-surface", type=Path)
    parser.add_argument("--xref-json", type=Path)
    parser.add_argument("--loader-log", type=Path)
    parser.add_argument("--seed", action="append", default=[], help="Explicit function seed as NAME=VADDR or VADDR")
    parser.add_argument("--exe-substring", default="DuneSandboxServer")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--seed-limit", type=int, default=512)
    parser.add_argument("--init-limit", type=int, default=0)
    parser.add_argument("--prelude", type=int, default=32)
    parser.add_argument("--window", type=int, default=1024)
    parser.add_argument("--signature-length", type=int, default=32)
    parser.add_argument("--count-signature-uniqueness", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args(argv)
    if not args.relocation_surface and not args.xref_json and not args.loader_log and not args.seed and args.init_limit <= 0:
        parser.error("provide --relocation-surface, --xref-json, --loader-log, --seed, or --init-limit")

    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
