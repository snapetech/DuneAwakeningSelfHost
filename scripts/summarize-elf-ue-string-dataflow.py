#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
LINUX_XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"

SHF_WRITE = 0x1
SHF_EXECINSTR = 0x4

UE_GROUP_HINTS = {
    "names": ("FName", "NamePool", "GName", "GNames"),
    "objects": ("UObject", "GUObject", "GObject", "ObjectArray", "FUObject"),
    "world": ("UWorld", "GWorld", "WorldContext"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByName"),
    "package": ("LoadObject", "LoadPackage", "StaticLoadObject", "StaticLoadClass", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UClass", "UFunction", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
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


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
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


def flags_text(section):
    if not section:
        return ""
    return "".join(flag for bit, flag in ((0x2, "A"), (SHF_WRITE, "W"), (SHF_EXECINSTR, "X")) if section.flags & bit)


def classify_groups(*values):
    haystack = "\n".join(value for value in values if value)
    return [group for group, needles in UE_GROUP_HINTS.items() if any(needle in haystack for needle in needles)]


def exact_anchor_hints(*values):
    haystack = "\n".join(value for value in values if value)
    return [
        anchor
        for anchor, needles in EXACT_ANCHOR_HINTS.items()
        if any(re.search(rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])", haystack) for needle in needles)
    ]


def load_targets(scan_xrefs, categories, names):
    category_filter = set(categories or [])
    name_filter = set(names or [])
    targets = []
    seen = set()
    for row in scan_xrefs.get("targets", []):
        if category_filter and row.get("category") not in category_filter:
            continue
        if name_filter and row.get("name") not in name_filter:
            continue
        value = parse_int(row.get("vaddr", "") or row.get("imageOffset", "") or row.get("fileOffset", ""))
        if value is None:
            continue
        key = (row.get("name", ""), value)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            {
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "kind": row.get("kind", ""),
                "value": value,
                "valueText": f"0x{value:x}",
                "fileOffset": row.get("fileOffset", ""),
                "imageOffset": row.get("imageOffset", ""),
                "groups": classify_groups(row.get("name", "")),
            }
        )
    return targets


def load_manual_targets(raw_targets):
    targets = []
    seen = set()
    for raw in raw_targets or []:
        if "=" in raw:
            name, value_text = raw.split("=", 1)
        else:
            name = f"manual-{raw}"
            value_text = raw
        value = parse_int(value_text)
        if value is None:
            raise ValueError(f"invalid manual target address: {raw}")
        key = (name, value)
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            {
                "name": name,
                "category": "manual",
                "kind": "manual",
                "value": value,
                "valueText": f"0x{value:x}",
                "fileOffset": f"0x{value:x}",
                "imageOffset": f"0x{value:x}",
                "groups": classify_groups(name),
            }
        )
    return targets


def pointer_slots_for_target(ptrctx, data, sections, relocations, target):
    slots = []
    for hit in ptrctx.find_qword_refs(data, target["value"]):
        section = ptrctx.section_for_file_offset(sections, hit)
        if not section:
            continue
        vaddr = section.addr + (hit - section.offset)
        slots.append(
            {
                "vaddr": vaddr,
                "vaddrText": f"0x{vaddr:x}",
                "fileOffset": f"0x{hit:x}",
                "section": section.name,
                "flags": flags_text(section),
                "source": "raw-qword",
            }
        )
    for addr, addend in relocations.items():
        if addend != target["value"]:
            continue
        section = ptrctx.section_for_addr(sections, addr)
        slots.append(
            {
                "vaddr": addr,
                "vaddrText": f"0x{addr:x}",
                "fileOffset": "rela",
                "section": section.name if section else "",
                "flags": flags_text(section),
                "source": "rela",
            }
        )
    deduped = {}
    for slot in slots:
        deduped[(slot["vaddr"], slot["source"])] = slot
    return sorted(deduped.values(), key=lambda row: (row["vaddr"], row["source"]))


def scan_code_refs_to_targets(xrefs, data, segments, target_vaddrs):
    target_set = set(target_vaddrs)
    refs = defaultdict(list)
    for segment in segments:
        if not (segment.flags & xrefs.PF_X):
            continue
        start = segment.file_offset
        code = data[start : start + segment.file_size]
        for pos in xrefs.iter_candidate_positions(code):
            for ref in xrefs.decode_rip_memory_refs(code, pos, segment.vaddr):
                target = int(ref["targetVaddr"])
                if target in target_set:
                    refs[target].append(ref)
    return refs


def value_hint(ptrctx, data, sections, symbols, value):
    section = ptrctx.section_for_addr(sections, value)
    return {
        "target": f"0x{value:x}",
        "section": section.name if section else "",
        "flags": flags_text(section),
        "symbols": symbols.get(value, [])[:4],
        "string": ptrctx.printable_hint(data, sections, value),
    }


def nearby_writable_refs(xrefs, ptrctx, data, segments, sections, symbols, xref_vaddr, window, limit):
    try:
        file_offset = xrefs.vaddr_to_file_offset(segments, xref_vaddr)
        segment = xrefs.segment_for_file_offset(segments, file_offset)
    except ValueError:
        return []
    start = max(segment.file_offset, file_offset - window)
    end = min(segment.file_offset + segment.file_size, file_offset + window)
    code = data[start:end]
    base_vaddr = segment.vaddr + (start - segment.file_offset)
    rows = []
    seen = set()
    for pos in xrefs.iter_candidate_positions(code):
        for ref in xrefs.decode_rip_memory_refs(code, pos, base_vaddr):
            target = int(ref["targetVaddr"])
            section = ptrctx.section_for_addr(sections, target)
            if not section or not (section.flags & SHF_WRITE):
                continue
            key = (ref["xrefVaddr"], target)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "xref": f"0x{ref['xrefVaddr']:x}",
                    "bytes": ref.get("bytes", ""),
                    **value_hint(ptrctx, data, sections, symbols, target),
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def attach_code_refs(xrefs, ptrctx, data, segments, sections, symbols, targets, slot_refs, context_window, context_limit):
    for target in targets:
        for slot in target["pointerSlots"]:
            refs = slot_refs.get(slot["vaddr"], [])
            slot["codeRefCount"] = len(refs)
            slot["codeRefs"] = []
            writable_targets = Counter()
            for ref in refs[:context_limit]:
                nearby = nearby_writable_refs(
                    xrefs,
                    ptrctx,
                    data,
                    segments,
                    sections,
                    symbols,
                    int(ref["xrefVaddr"]),
                    context_window,
                    context_limit,
                )
                for row in nearby:
                    writable_targets[row["target"]] += 1
                slot["codeRefs"].append(
                    {
                        "xref": f"0x{ref['xrefVaddr']:x}",
                        "bytes": ref.get("bytes", ""),
                        "nearbyWritableRefs": nearby,
                    }
                )
            slot["nearbyWritableTargetCounts"] = dict(sorted(writable_targets.items()))


def summarize_writable_targets(targets):
    rows = {}
    for target in targets:
        for slot in target.get("pointerSlots", []):
            for ref in slot.get("codeRefs", []):
                for writable in ref.get("nearbyWritableRefs", []):
                    key = writable["target"]
                    row = rows.setdefault(
                        key,
                        {
                            "target": key,
                            "section": writable.get("section", ""),
                            "flags": writable.get("flags", ""),
                            "refCount": 0,
                            "sampleXrefs": [],
                            "sourceNames": Counter(),
                            "sourceCategories": Counter(),
                            "groups": Counter(),
                            "exactAnchorHints": Counter(),
                            "context": [],
                        },
                    )
                    row["refCount"] += 1
                    source_name = target.get("name", "")
                    row["sourceNames"][source_name] += 1
                    row["sourceCategories"][target.get("category", "")] += 1
                    for group in target.get("groups", []):
                        row["groups"][group] += 1
                    exact_hints = exact_anchor_hints(source_name)
                    for anchor in exact_hints:
                        row["exactAnchorHints"][anchor] += 1
                    xref = writable.get("xref", "")
                    if xref and xref not in row["sampleXrefs"]:
                        row["sampleXrefs"].append(xref)
                    if len(row["context"]) < 12:
                        row["context"].append(
                            {
                                "xref": xref,
                                "target": target.get("valueText", ""),
                                "section": writable.get("section", ""),
                                "groups": target.get("groups", []),
                                "exactAnchorHints": exact_hints,
                                "symbols": writable.get("symbols", []),
                                "string": source_name,
                            }
                        )

    summarized = []
    for row in rows.values():
        summarized.append(
            {
                "target": row["target"],
                "section": row["section"],
                "flags": row["flags"],
                "refCount": row["refCount"],
                "xrefCount": len(row["sampleXrefs"]),
                "sourceNames": dict(row["sourceNames"].most_common(12)),
                "sourceCategories": dict(row["sourceCategories"].most_common()),
                "groups": dict(row["groups"].most_common()),
                "sampleXrefs": row["sampleXrefs"][:12],
                "exactAnchorHintCounts": dict(row["exactAnchorHints"].most_common()),
                "context": row["context"],
            }
        )
    summarized.sort(key=lambda row: (-row["refCount"], -row["xrefCount"], row["target"]))
    return summarized


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_ue_string_dataflow")
    xrefs = import_script(LINUX_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_ue_string_dataflow")
    data, segments = xrefs.load_elf_segments(args.binary)
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)
    relocations = ptrctx.load_relocations(data, sections)
    scan_xrefs = load_json(args.scan_xrefs_json)
    targets = load_targets(scan_xrefs, args.category, args.name)
    targets.extend(load_manual_targets(args.target))
    for target in targets:
        target["pointerSlots"] = pointer_slots_for_target(ptrctx, data, sections, relocations, target)
    source_target_count = len(targets)
    all_slots = [slot["vaddr"] for target in targets for slot in target["pointerSlots"]]
    slot_refs = scan_code_refs_to_targets(xrefs, data, segments, all_slots)
    attach_code_refs(xrefs, ptrctx, data, segments, sections, symbols, targets, slot_refs, args.context_window, args.context_limit)

    for target in targets:
        target["pointerSlotCount"] = len(target["pointerSlots"])
        target["codeRefCount"] = sum(slot.get("codeRefCount", 0) for slot in target["pointerSlots"])
        target["nearbyWritableTargetCount"] = len(
            {
                writable
                for slot in target["pointerSlots"]
                for writable in slot.get("nearbyWritableTargetCounts", {})
            }
        )
        target["score"] = (
            target["codeRefCount"] * 10
            + target["pointerSlotCount"] * 2
            + target["nearbyWritableTargetCount"] * 5
            + len(target.get("groups", [])) * 20
        )
    targets.sort(key=lambda row: (-row["score"], -row["codeRefCount"], row["name"], row["value"]))
    reported = [row for row in targets if row["pointerSlotCount"] or row["codeRefCount"]]
    if args.only_with_slots:
        targets = reported
    writable_targets = summarize_writable_targets(targets)
    return {
        "schemaVersion": "dune-elf-ue-string-dataflow/v1",
        "binary": str(args.binary),
        "sourceScanXrefs": str(args.scan_xrefs_json),
        "sourceTargetCount": source_target_count,
        "targetCount": len(targets),
        "reportedTargetCount": len(reported),
        "targetsWithCodeRefs": sum(1 for row in targets if row["codeRefCount"]),
        "groupCounts": dict(sorted(Counter(group for row in targets for group in row.get("groups", [])).items())),
        "writableTargetCount": len(writable_targets),
        "writableTargets": writable_targets[: args.limit],
        "targets": targets[: args.limit],
    }


def markdown(summary):
    lines = ["# ELF UE String Dataflow", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Source targets: `{summary.get('sourceTargetCount', summary['targetCount'])}`")
    lines.append(f"- Emitted targets: `{summary['targetCount']}`")
    lines.append(f"- Targets with pointer slots: `{summary['reportedTargetCount']}`")
    lines.append(f"- Targets with code refs to slots: `{summary['targetsWithCodeRefs']}`")
    lines.append(f"- Nearby writable targets: `{summary.get('writableTargetCount', 0)}`")
    lines.append(f"- Groups: `{summary['groupCounts']}`")
    lines.append("")
    if summary.get("writableTargets"):
        lines.append("## Nearby Writable Targets")
        lines.append("")
        for row in summary["writableTargets"][:20]:
            lines.append(
                f"- target=`{row['target']}` section=`{row['section']}` refs=`{row['refCount']}` "
                f"xrefs=`{row['xrefCount']}` sources=`{row['sourceNames']}`"
            )
        lines.append("")
    lines.append("## Source Targets")
    lines.append("")
    for row in summary["targets"]:
        lines.append(
            f"- `{row['name']}` value=`{row['valueText']}` groups=`{row.get('groups', [])}` "
            f"slots=`{row['pointerSlotCount']}` codeRefs=`{row['codeRefCount']}` "
            f"nearbyWritableTargets=`{row['nearbyWritableTargetCount']}` score=`{row['score']}`"
        )
        for slot in row["pointerSlots"][:6]:
            lines.append(
                f"  - slot=`{slot['vaddrText']}` source=`{slot['source']}` section=`{slot['section']}` "
                f"flags=`{slot['flags']}` codeRefs=`{slot.get('codeRefCount', 0)}` "
                f"nearbyWritable=`{slot.get('nearbyWritableTargetCounts', {})}`"
            )
            for ref in slot.get("codeRefs", [])[:3]:
                lines.append(f"    - code=`{ref['xref']}` bytes=`{ref['bytes']}`")
                for writable in ref.get("nearbyWritableRefs", [])[:4]:
                    detail = " | ".join(writable.get("symbols", [])) or writable.get("string", "")
                    suffix = f" detail=`{detail}`" if detail else ""
                    lines.append(
                        f"      - writable=`{writable['target']}` section=`{writable['section']}` "
                        f"flags=`{writable['flags']}`{suffix}"
                    )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Follow UE string hits through ELF pointer/relocation table slots and code references."
    )
    parser.add_argument("binary", type=Path)
    parser.add_argument("scan_xrefs_json", type=Path)
    parser.add_argument("--category", action="append", default=["ue"])
    parser.add_argument(
        "--all-categories",
        action="store_true",
        help="include every scan-xref category instead of the default UE anchor category",
    )
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="explicit string/data target as NAME=ADDR or ADDR; useful when loader logs did not emit the anchor",
    )
    parser.add_argument("--context-window", type=int, default=256)
    parser.add_argument("--context-limit", type=int, default=12)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--only-with-slots", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    if args.all_categories:
        args.category = []

    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
