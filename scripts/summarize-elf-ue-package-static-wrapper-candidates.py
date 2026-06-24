#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
LINUX_XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
SCHEMA_VERSION = "dune-elf-ue-package-static-wrapper-candidates/v1"

PACKAGE_NEEDLES = (
    "StaticLoadObject",
    "StaticLoadClass",
    "LoadObject",
    "LoadPackage",
    "ResolveName",
    "UObjectGlobals",
    "AsyncPackageLoader",
    "AsyncLoading",
    "AsyncLoading2",
    "LinkerLoad",
    "CoreUObject",
)
EXCLUDE_SYMBOL_NEEDLES = (
    "vtable for ",
    "typeinfo",
    "VTT for ",
    "SDL_",
    "FAsyncPackage",
    "FLinkerLoad",
    "FBootLoad",
)


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def demangle(names):
    if not names:
        return {}
    result = {}
    chunk_size = 512
    for start in range(0, len(names), chunk_size):
        chunk = names[start : start + chunk_size]
        try:
            proc = subprocess.run(
                ["c++filt", *chunk],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.CalledProcessError):
            result.update({name: name for name in chunk})
            continue
        lines = proc.stdout.splitlines()
        for index, name in enumerate(chunk):
            result[name] = lines[index] if index < len(lines) else name
    return result


def flags_text(section):
    if not section:
        return ""
    flags = getattr(section, "flags", 0)
    if isinstance(flags, int):
        return "".join(flag for bit, flag in ((0x2, "A"), (0x1, "W"), (0x4, "X")) if flags & bit)
    return str(flags)


def section_for_addr(sections, addr):
    for section in sections:
        if section.addr <= addr < section.addr + section.size:
            return section
    return None


def printable_strings(data, min_len):
    rows = []
    current = bytearray()
    start = None
    for index, byte in enumerate(data):
        if 32 <= byte < 127:
            if start is None:
                start = index
            current.append(byte)
        else:
            if start is not None and len(current) >= min_len:
                rows.append((start, current.decode("ascii", errors="replace")))
            current.clear()
            start = None
    if start is not None and len(current) >= min_len:
        rows.append((start, current.decode("ascii", errors="replace")))
    return rows


def file_offset_to_addr(sections, file_offset):
    for section in sections:
        if section.sh_type == 8:
            continue
        if section.offset <= file_offset < section.offset + section.size:
            return section.addr + (file_offset - section.offset)
    return None


def package_string_rows(data, sections, needles, min_len):
    rows = []
    for file_offset, text in printable_strings(data, min_len):
        if not any(needle in text for needle in needles):
            continue
        addr = file_offset_to_addr(sections, file_offset)
        section = section_for_addr(sections, addr) if addr is not None else None
        rows.append(
            {
                "address": addr,
                "addressText": f"0x{addr:x}" if addr is not None else "",
                "fileOffset": f"0x{file_offset:x}",
                "section": section.name if section else "",
                "flags": flags_text(section),
                "text": text[:240],
                "needles": [needle for needle in needles if needle in text],
            }
        )
    return rows


def looks_like_itanium_typeinfo_name(text):
    return text.startswith("N") and "E" in text and any(
        token in text
        for token in (
            "TFunction_",
            "TBase",
            "TCommonDelegate",
            "FStreamable",
            "AsyncLoading",
            "Package",
        )
    )


def attach_demangled_typeinfo_rows(rows):
    by_text = {}
    for row in rows:
        text = row.get("text", "")
        if looks_like_itanium_typeinfo_name(text):
            by_text[text] = "_ZTS" + text
    demangled = demangle(sorted(by_text.values()))
    for row in rows:
        mangled = by_text.get(row.get("text", ""))
        if not mangled:
            continue
        value = demangled.get(mangled, "")
        if not value or value == mangled:
            continue
        row["demangledTypeinfo"] = value
        owner_candidates = re.findall(r"([A-Za-z_][A-Za-z0-9_:~]*::[A-Za-z_][A-Za-z0-9_~]*)\(", value)
        if owner_candidates:
            row["ownerFunctionCandidates"] = list(dict.fromkeys(owner_candidates))[:6]


def pointer_slots_for_value(ptrctx, data, sections, relocations, value):
    slots = []
    for file_offset in ptrctx.find_qword_refs(data, value):
        section = ptrctx.section_for_file_offset(sections, file_offset)
        if not section:
            continue
        addr = section.addr + (file_offset - section.offset)
        slots.append(
            {
                "address": addr,
                "addressText": f"0x{addr:x}",
                "section": section.name,
                "flags": flags_text(section),
                "source": "raw-qword",
            }
        )
    for addr, addend in relocations.items():
        if addend != value:
            continue
        section = section_for_addr(sections, addr)
        slots.append(
            {
                "address": addr,
                "addressText": f"0x{addr:x}",
                "section": section.name if section else "",
                "flags": flags_text(section),
                "source": "rela",
            }
        )
    deduped = {}
    for slot in slots:
        deduped[(slot["address"], slot["source"])] = slot
    return sorted(deduped.values(), key=lambda row: (row["address"], row["source"]))


def code_refs_to_values(xrefs, data, segments, values):
    refs = {value: [] for value in values}
    if not values:
        return refs
    value_set = set(values)
    for segment in segments:
        if not (segment.flags & xrefs.PF_X):
            continue
        code = data[segment.file_offset : segment.file_offset + segment.file_size]
        for pos in xrefs.iter_candidate_positions(code):
            for ref in xrefs.decode_rip_memory_refs(code, pos, segment.vaddr):
                target = int(ref["targetVaddr"])
                if target in value_set:
                    refs[target].append(
                        {
                            "xref": f"0x{ref['xrefVaddr']:x}",
                            "bytes": ref.get("bytes", ""),
                        }
                    )
    return refs


def classify_direct_code_refs(xrefs, data, segments, rows):
    classifications = Counter()
    for row in rows:
        for ref in row.get("directCodeRefs", []):
            ref["classification"] = "unknown-direct-ref"
            ref["promotable"] = False
            ref["reason"] = "direct source/string reference needs function review before promotion"
            try:
                vaddr = int(ref["xref"], 16)
                file_offset = xrefs.vaddr_to_file_offset(segments, vaddr)
            except (KeyError, TypeError, ValueError):
                classifications[ref["classification"]] += 1
                continue
            window = data[file_offset : file_offset + 64]
            text = row.get("text", "")
            source_path_ref = text.endswith((".cpp", ".h")) or "/Private/" in text or "\\Private\\" in text
            has_assert_log_shape = (
                b"\xbe\x01\x00\x00\x00" in window
                and b"\x41\xb8" in window
                and b"\xe8" in window
            )
            if source_path_ref and has_assert_log_shape:
                ref["classification"] = "source-diagnostic-thunk"
                ref["reason"] = "loads a source path plus line/verbosity constants for a diagnostic/assertion helper"
            elif has_assert_log_shape:
                ref["classification"] = "diagnostic-thunk"
                ref["reason"] = "loads assertion/log text plus line/verbosity constants for a diagnostic helper"
            classifications[ref["classification"]] += 1
    return dict(sorted(classifications.items()))


def attach_string_dataflow(ptrctx, xrefs, data, segments, sections, relocations, rows, context_limit):
    for row in rows:
        address = row.get("address")
        row["pointerSlots"] = pointer_slots_for_value(ptrctx, data, sections, relocations, address) if address else []
    direct_refs = code_refs_to_values(xrefs, data, segments, [row["address"] for row in rows if row.get("address")])
    slot_refs = code_refs_to_values(
        xrefs,
        data,
        segments,
        [slot["address"] for row in rows for slot in row.get("pointerSlots", [])],
    )
    for row in rows:
        direct = direct_refs.get(row.get("address"), [])
        row["directCodeRefCount"] = len(direct)
        row["directCodeRefs"] = direct[:context_limit]
        for slot in row.get("pointerSlots", []):
            refs = slot_refs.get(slot["address"], [])
            slot["codeRefCount"] = len(refs)
            slot["codeRefs"] = refs[:context_limit]
        row["pointerSlotCount"] = len(row.get("pointerSlots", []))
        row["slotCodeRefCount"] = sum(slot.get("codeRefCount", 0) for slot in row.get("pointerSlots", []))
        row["score"] = (
            row["directCodeRefCount"] * 10
            + row["slotCodeRefCount"] * 12
            + row["pointerSlotCount"] * 3
            + (8 if row.get("section") != ".dynstr" else 0)
            + len(row.get("needles", []))
        )
    rows.sort(
        key=lambda row: (
            -row.get("score", 0),
            row.get("section") == ".dynstr",
            -row.get("slotCodeRefCount", 0),
            -row.get("directCodeRefCount", 0),
            row.get("address") or 0,
        )
    )
    return classify_direct_code_refs(xrefs, data, segments, rows)


def executable_symbol_candidates(sections, symbols, needles):
    raw_names = sorted({name.split(" size=", 1)[0] for names in symbols.values() for name in names})
    demangled_by_name = demangle(raw_names)
    rows = []
    seen = set()
    for value, names in symbols.items():
        section = section_for_addr(sections, value)
        if "X" not in flags_text(section):
            continue
        for raw in names:
            name = raw.split(" size=", 1)[0]
            demangled = demangled_by_name.get(name, name)
            haystack = f"{name}\n{demangled}"
            if not any(needle in haystack for needle in needles):
                continue
            if any(needle in haystack for needle in EXCLUDE_SYMBOL_NEEDLES):
                continue
            key = (value, name)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "address": value,
                    "addressText": f"0x{value:x}",
                    "section": section.name if section else "",
                    "symbol": name,
                    "demangled": demangled,
                    "needles": [needle for needle in needles if needle in haystack],
                }
            )
    return rows


def objdump_calls(binary):
    try:
        proc = subprocess.run(
            ["objdump", "-d", str(binary)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    rows = []
    for line in proc.stdout.splitlines():
        if "\tcall" not in line:
            continue
        left, _, right = line.partition(":")
        try:
            source = int(left.strip(), 16)
        except ValueError:
            continue
        match = re.search(r"\bcall\s+([0-9a-fA-F]+)\b", right)
        if not match:
            continue
        rows.append((source, int(match.group(1), 16)))
    return rows


def build_call_counts(binary, candidate_addrs):
    counts = {addr: {"directCallCount": 0, "sampleCallsites": []} for addr in candidate_addrs}
    if not counts:
        return counts
    for source, target in objdump_calls(binary):
        if target not in counts:
            continue
        counts[target]["directCallCount"] += 1
        if len(counts[target]["sampleCallsites"]) < 8:
            counts[target]["sampleCallsites"].append(f"0x{source:x}")
    return counts


def score_symbol(row, call_info):
    score = 0
    reasons = []
    demangled = row.get("demangled", "")
    strong = ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName")
    for needle in strong:
        if needle in demangled:
            score += 10
            reasons.append(f"symbol:{needle}")
    if "UObjectGlobals" in demangled:
        score += 4
        reasons.append("symbol:UObjectGlobals")
    if call_info.get("directCallCount", 0) > 0:
        score += min(8, call_info["directCallCount"])
        reasons.append("has-direct-callers")
    row["score"] = score
    row["reasons"] = reasons
    row.update(call_info)
    return row


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_static_package_wrappers")
    xrefs = import_script(LINUX_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_static_package_wrappers")
    data, segments = xrefs.load_elf_segments(args.binary)
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)
    relocations = ptrctx.load_relocations(data, sections)
    needles = tuple(args.needle or PACKAGE_NEEDLES)
    strings = package_string_rows(data, sections, needles, args.min_string_length)
    attach_demangled_typeinfo_rows(strings)
    direct_ref_classifications = attach_string_dataflow(
        ptrctx, xrefs, data, segments, sections, relocations, strings, args.context_limit
    )
    symbols_rows = executable_symbol_candidates(sections, symbols, needles)
    call_counts = build_call_counts(args.binary, {row["address"] for row in symbols_rows})
    symbols_ranked = sorted(
        (score_symbol(dict(row), call_counts.get(row["address"], {})) for row in symbols_rows),
        key=lambda row: (-row["score"], -row.get("directCallCount", 0), row["address"]),
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "binary": str(args.binary),
        "needles": list(needles),
        "stringHitCount": len(strings),
        "nonDynstrStringHitCount": sum(1 for row in strings if row.get("section") != ".dynstr"),
        "executableSymbolCandidateCount": len(symbols_rows),
        "rankedSymbolCandidates": symbols_ranked[: args.limit],
        "stringsWithPointerSlots": sum(1 for row in strings if row.get("pointerSlotCount", 0)),
        "stringsWithCodeRefs": sum(
            1 for row in strings if row.get("directCodeRefCount", 0) or row.get("slotCodeRefCount", 0)
        ),
        "stringsWithOwnerFunctionCandidates": sum(1 for row in strings if row.get("ownerFunctionCandidates")),
        "directCodeRefClassifications": direct_ref_classifications,
        "packageStrings": strings[: args.string_limit],
        "promotionRule": (
            "Only promote a candidate after decompile/signature review proves a callable static/free-function "
            "package-loading ABI compatible with the guarded loader bridge."
        ),
    }


def markdown(summary):
    lines = ["# ELF UE Package Static Wrapper Candidates", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Needles: `{summary['needles']}`")
    lines.append(f"- Package/source string hits: `{summary['stringHitCount']}`")
    lines.append(f"- Non-dynstr package/source string hits: `{summary.get('nonDynstrStringHitCount', 0)}`")
    lines.append(f"- Strings with pointer slots: `{summary.get('stringsWithPointerSlots', 0)}`")
    lines.append(f"- Strings with code refs: `{summary.get('stringsWithCodeRefs', 0)}`")
    lines.append(f"- Strings with owner function candidates: `{summary.get('stringsWithOwnerFunctionCandidates', 0)}`")
    lines.append(f"- Direct code ref classifications: `{summary.get('directCodeRefClassifications', {})}`")
    lines.append(f"- Executable symbol candidates: `{summary['executableSymbolCandidateCount']}`")
    lines.append(f"- Promotion rule: `{summary['promotionRule']}`")
    lines.append("")
    lines.append("## Ranked Symbol Candidates")
    lines.append("")
    if not summary["rankedSymbolCandidates"]:
        lines.append("- none")
    for row in summary["rankedSymbolCandidates"]:
        lines.append(
            f"- score=`{row['score']}` addr=`{row['addressText']}` calls=`{row.get('directCallCount', 0)}` "
            f"symbol=`{row['demangled'] or row['symbol']}` reasons=`{', '.join(row['reasons']) or 'none'}`"
        )
    lines.append("")
    lines.append("## Package Strings")
    lines.append("")
    if not summary["packageStrings"]:
        lines.append("- none")
    for row in summary["packageStrings"]:
        lines.append(
            f"- addr=`{row['addressText']}` section=`{row['section']}` needles=`{', '.join(row['needles'])}` "
            f"score=`{row.get('score', 0)}` slots=`{row.get('pointerSlotCount', 0)}` "
            f"directCodeRefs=`{row.get('directCodeRefCount', 0)}` slotCodeRefs=`{row.get('slotCodeRefCount', 0)}` "
            f"text=`{row['text']}`"
        )
        if row.get("ownerFunctionCandidates"):
            lines.append(f"  - owners=`{', '.join(row['ownerFunctionCandidates'])}`")
        if row.get("demangledTypeinfo"):
            lines.append(f"  - demangled=`{row['demangledTypeinfo'][:240]}`")
        for ref in row.get("directCodeRefs", [])[:3]:
            lines.append(
                f"  - directCode=`{ref['xref']}` class=`{ref.get('classification', 'unknown-direct-ref')}` "
                f"promotable=`{str(bool(ref.get('promotable'))).lower()}` bytes=`{ref['bytes']}`"
            )
        for slot in row.get("pointerSlots", [])[:3]:
            lines.append(
                f"  - slot=`{slot['addressText']}` section=`{slot['section']}` "
                f"source=`{slot['source']}` codeRefs=`{slot.get('codeRefCount', 0)}`"
            )
            for ref in slot.get("codeRefs", [])[:3]:
                lines.append(f"    - code=`{ref['xref']}` bytes=`{ref['bytes']}`")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Rank ELF static/free-function UE package-loading wrapper candidates."
    )
    parser.add_argument("binary", type=Path)
    parser.add_argument("--needle", action="append", default=[])
    parser.add_argument("--min-string-length", type=int, default=8)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--string-limit", type=int, default=64)
    parser.add_argument("--context-limit", type=int, default=8)
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
