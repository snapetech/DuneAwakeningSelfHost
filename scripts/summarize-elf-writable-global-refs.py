#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
LINUX_XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"

SHF_WRITE = 0x1
SHF_EXECINSTR = 0x4
SHF_ALLOC = 0x2

UE_HINTS = {
    "names": ("FName", "NamePool", "GName", "GNames"),
    "objects": ("UObject", "GUObject", "GObject", "ObjectArray", "FUObject"),
    "world": ("UWorld", "GWorld", "WorldContext"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByName"),
    "package": ("LoadObject", "LoadPackage", "StaticLoadObject", "ResolveName", "LoadAsset", "LoadClass"),
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
    "CallFunctionByNameWithArguments": ("CallFunctionByNameWithArguments", "CallFunctionByName"),
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


def import_script(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value):
    if isinstance(value, int):
        return value
    return int(str(value), 16 if str(value).lower().startswith("0x") else 10)


def flags_text(section):
    if not section:
        return ""
    return "".join(
        flag
        for bit, flag in ((SHF_ALLOC, "A"), (SHF_WRITE, "W"), (SHF_EXECINSTR, "X"))
        if section.flags & bit
    )


def classify_text(*values):
    haystack = "\n".join(value for value in values if value)
    groups = []
    for group, needles in UE_HINTS.items():
        if any(needle in haystack for needle in needles):
            groups.append(group)
    return groups


def exact_anchor_hints(*values):
    haystack = "\n".join(value for value in values if value)
    hints = []
    for anchor, needles in EXACT_ANCHOR_HINTS.items():
        if any(re.search(rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])", haystack) for needle in needles):
            hints.append(anchor)
    return hints


def context_quality_score(row):
    exact_count = len(row.get("exactAnchorHints", []) or [])
    group_count = len(row.get("groups", []) or [])
    symbol_count = len(row.get("symbols", []) or [])
    has_string = 1 if row.get("string") else 0
    return exact_count * 1000 + group_count * 100 + symbol_count * 10 + has_string


def rank_context_rows(rows):
    return sorted(
        rows,
        key=lambda row: (
            -context_quality_score(row),
            row.get("xref", ""),
            row.get("target", ""),
        ),
    )


def scan_writable_refs(xrefs, ptrctx, data, segments, sections):
    refs_by_target = defaultdict(list)
    for segment in segments:
        if not (segment.flags & xrefs.PF_X):
            continue
        start = segment.file_offset
        end = start + segment.file_size
        code = data[start:end]
        for pos in xrefs.iter_candidate_positions(code):
            for ref in xrefs.decode_rip_memory_refs(code, pos, segment.vaddr):
                target = int(ref["targetVaddr"])
                section = ptrctx.section_for_addr(sections, target)
                if not section or not (section.flags & SHF_WRITE):
                    continue
                refs_by_target[target].append(ref)
    return refs_by_target


def scan_nearby_context(xrefs, ptrctx, data, segments, sections, symbols, xref_vaddr, window, limit, scan_limit):
    try:
        file_offset = xrefs.vaddr_to_file_offset(segments, xref_vaddr)
    except ValueError:
        return []
    segment = xrefs.segment_for_file_offset(segments, file_offset)
    start = max(segment.file_offset, file_offset - window)
    end = min(segment.file_offset + segment.file_size, file_offset + window)
    code = data[start:end]
    base_vaddr = segment.vaddr + (start - segment.file_offset)
    rows = []
    seen = set()
    effective_scan_limit = max(limit, scan_limit)
    for pos in xrefs.iter_candidate_positions(code):
        for ref in xrefs.decode_rip_memory_refs(code, pos, base_vaddr):
            target = int(ref["targetVaddr"])
            section = ptrctx.section_for_addr(sections, target)
            if not section:
                continue
            text = ptrctx.printable_hint(data, sections, target)
            names = symbols.get(target, [])[:4]
            groups = classify_text(text, *names)
            exact_hints = exact_anchor_hints(text, *names)
            if not text and not names and not groups and not exact_hints:
                continue
            key = (target, ref["xrefVaddr"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "xref": f"0x{ref['xrefVaddr']:x}",
                    "target": f"0x{target:x}",
                    "section": section.name,
                    "groups": groups,
                    "exactAnchorHints": exact_hints,
                    "symbols": names,
                    "string": text,
                }
            )
            if len(rows) >= effective_scan_limit:
                return rank_context_rows(rows)[:limit]
    return rank_context_rows(rows)[:limit]


def summarize_target(
    xrefs,
    ptrctx,
    data,
    segments,
    sections,
    symbols,
    target,
    refs,
    context_window,
    context_limit,
    context_scan_limit,
):
    section = ptrctx.section_for_addr(sections, target)
    ref_functions = Counter()
    samples = []
    context = []
    for ref in refs:
        xref_vaddr = int(ref["xrefVaddr"])
        function_bucket = xref_vaddr & ~0xFF
        ref_functions[function_bucket] += 1
        if len(samples) < 8:
            samples.append(
                {
                    "xref": f"0x{xref_vaddr:x}",
                    "bytes": ref["bytes"],
                    "length": ref["length"],
                }
            )
        if len(context) < context_limit:
            for row in scan_nearby_context(
                xrefs,
                ptrctx,
                data,
                segments,
                sections,
                symbols,
                xref_vaddr,
                context_window,
                context_limit - len(context),
                context_scan_limit,
            ):
                context.append(row)
                if len(context) >= context_limit:
                    break
    group_counts = Counter(group for row in context for group in row["groups"])
    exact_anchor_counts = Counter(anchor for row in context for anchor in row["exactAnchorHints"])
    return {
        "target": f"0x{target:x}",
        "fileOffset": "unbacked" if ptrctx.addr_to_file_offset(sections, target) is None else f"0x{ptrctx.addr_to_file_offset(sections, target):x}",
        "section": section.name if section else "",
        "flags": flags_text(section),
        "refCount": len(refs),
        "functionBucketCount": len(ref_functions),
        "groupCounts": dict(sorted(group_counts.items())),
        "exactAnchorHintCounts": dict(sorted(exact_anchor_counts.items())),
        "score": len(refs) + len(ref_functions) * 4 + sum(group_counts.values()) * 20 + sum(exact_anchor_counts.values()) * 200,
        "samples": samples,
        "context": context,
    }


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_writable_refs")
    xrefs = import_script(LINUX_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_writable_refs")
    data, segments = xrefs.load_elf_segments(args.binary)
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)
    refs_by_target = scan_writable_refs(xrefs, ptrctx, data, segments, sections)
    rows = [
        summarize_target(
            xrefs,
            ptrctx,
            data,
            segments,
            sections,
            symbols,
            target,
            refs,
            args.context_window,
            args.context_limit,
            args.context_scan_limit,
        )
        for target, refs in refs_by_target.items()
        if len(refs) >= args.min_refs
    ]
    rows.sort(key=lambda row: (-row["score"], -row["refCount"], row["target"]))
    section_counts = Counter(row["section"] for row in rows)
    group_counts = Counter(group for row in rows for group in row["groupCounts"])
    exact_anchor_counts = Counter(anchor for row in rows for anchor in row["exactAnchorHintCounts"])
    return {
        "schemaVersion": "dune-elf-writable-global-refs/v1",
        "binary": str(args.binary),
        "targetCount": len(refs_by_target),
        "reportedTargetCount": len(rows),
        "minRefs": args.min_refs,
        "sectionCounts": dict(sorted(section_counts.items())),
        "groupCounts": dict(sorted(group_counts.items())),
        "exactAnchorHintCounts": dict(sorted(exact_anchor_counts.items())),
        "top": rows[: args.limit],
    }


def markdown(summary):
    lines = ["# ELF Writable Global References", ""]
    lines.append(f"- Writable targets with refs: `{summary['targetCount']}`")
    lines.append(f"- Reported targets: `{summary['reportedTargetCount']}`")
    lines.append(f"- Min refs: `{summary['minRefs']}`")
    lines.append(f"- Sections: `{summary['sectionCounts']}`")
    lines.append(f"- UE hint groups in context: `{summary['groupCounts']}`")
    lines.append(f"- Exact anchor hints in context: `{summary['exactAnchorHintCounts']}`")
    lines.append("")
    lines.append("## Top Targets")
    lines.append("")
    if not summary["top"]:
        lines.append("- none")
    for row in summary["top"]:
        lines.append(
            f"- target=`{row['target']}` file=`{row['fileOffset']}` section=`{row['section']}` "
            f"refs=`{row['refCount']}` functionBuckets=`{row['functionBucketCount']}` "
            f"groups=`{row['groupCounts']}` exactAnchors=`{row['exactAnchorHintCounts']}` score=`{row['score']}`"
        )
        for context in row["context"][:8]:
            symbol = " | ".join(context["symbols"]) if context["symbols"] else ""
            groups = f" groups={','.join(context['groups'])}" if context["groups"] else ""
            exact = f" exact={','.join(context['exactAnchorHints'])}" if context["exactAnchorHints"] else ""
            symbol_text = f" symbol={symbol}" if symbol else ""
            string = f" string={context['string']!r}" if context["string"] else ""
            lines.append(
                f"  - ctx xref=`{context['xref']}` target=`{context['target']}` "
                f"section=`{context['section']}`{groups}{exact}{symbol_text}{string}"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cluster anonymous writable ELF globals referenced by executable RIP-relative memory operands."
    )
    parser.add_argument("binary", type=Path)
    parser.add_argument("--min-refs", type=int, default=8)
    parser.add_argument("--context-window", type=int, default=192)
    parser.add_argument("--context-limit", type=int, default=12)
    parser.add_argument(
        "--context-scan-limit",
        type=int,
        default=96,
        help="nearby context rows to scan before returning the highest-quality context rows",
    )
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
