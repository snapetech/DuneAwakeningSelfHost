#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
LOADER_XREF_SCRIPT = ROOT / "scripts" / "summarize-linux-loader-xrefs.py"
SYMBOL_SURFACE_SCRIPT = ROOT / "scripts" / "summarize-elf-ue-symbol-surface.py"


@dataclass(frozen=True)
class RelocationTarget:
    name: str
    source: str
    group: str
    role: str
    value: int


def import_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_int(value):
    if isinstance(value, int):
        return value
    return int(str(value), 16 if str(value).lower().startswith("0x") else 10)


def normalize_groups(groups):
    if isinstance(groups, str):
        return [groups]
    return list(groups or [])


def load_live_targets(loader_log, binary, exe_substring, categories, names, limit):
    if loader_log is None:
        return []
    xrefs = import_script(LOADER_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_rela")
    _data, segments = xrefs.load_elf_segments(binary)
    targets = xrefs.targets_from_log(loader_log, segments, exe_substring, None, categories, names)
    rows = []
    seen = set()
    for target in targets:
        key = (target.name, target.file_offset)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            RelocationTarget(
                name=target.name,
                source="live-log",
                group=target.category,
                role=target.kind or "scan-hit",
                value=target.vaddr,
            )
        )
    return rows[:limit]


def load_symbol_targets(symbol_surface, limit):
    if symbol_surface is None:
        return []
    summary = load_json(symbol_surface)
    rows = []
    for row in summary.get("rows", []):
        if row.get("falsePositive"):
            continue
        value = int(row.get("value") or 0)
        if value <= 0:
            continue
        groups = normalize_groups(row.get("groups"))
        group = ",".join(groups) if groups else "unknown"
        rows.append(
            RelocationTarget(
                name=row.get("demangled") or row.get("name") or f"0x{value:x}",
                source="symbol-surface",
                group=group,
                role=row.get("role") or "symbol",
                value=value,
            )
        )
    rows.sort(key=lambda item: (runtime_priority(item.role), item.group, item.value, item.name))
    return rows[:limit]


def runtime_priority(role):
    order = {
        "process-event": 0,
        "dispatch-function": 1,
        "package-function": 2,
        "global-symbol": 3,
        "rtti-vtable": 4,
        "rtti-typeinfo": 5,
        "rtti-name": 6,
    }
    return order.get(role, 20)


def relocation_index(relocations):
    by_addend = defaultdict(list)
    for slot, addend in relocations.items():
        by_addend[addend].append(slot)
    return by_addend


def section_name(ptrctx, sections, addr):
    section = ptrctx.section_for_addr(sections, addr)
    return section.name if section else ""


def first_contexts(ptrctx, data, sections, symbols, relocations, slots, window, limit):
    rows = []
    for slot in slots[:limit]:
        rows.append(
            {
                "slot": f"0x{slot:x}",
                "section": section_name(ptrctx, sections, slot),
                "context": ptrctx.pointer_context_at_addr(data, sections, symbols, relocations, slot, window),
            }
        )
    return rows


def load_init_array(ptrctx, data, sections, relocations, symbols, limit):
    section = next((candidate for candidate in sections if candidate.name == ".init_array"), None)
    if section is None or section.entsize == 0:
        return {"entryCount": 0, "entries": []}
    entries = []
    count = section.size // section.entsize
    for index in range(count):
        slot = section.addr + index * section.entsize
        value, source = ptrctx.qword_at_addr(data, sections, relocations, slot)
        if value is None:
            continue
        names = symbols.get(value, [])[:4]
        entries.append(
            {
                "index": index,
                "slot": f"0x{slot:x}",
                "value": f"0x{value:x}",
                "source": source,
                "symbols": names,
            }
        )
    named = [entry for entry in entries if entry["symbols"]]
    ue_named = [
        entry
        for entry in named
        if any(
            needle in " ".join(entry["symbols"])
            for needle in ("UObject", "UClass", "UFunction", "FProperty", "FName", "ProcessEvent", "LoadObject")
        )
    ]
    return {
        "entryCount": count,
        "namedEntryCount": len(named),
        "ueNamedEntryCount": len(ue_named),
        "entries": (ue_named or named)[:limit],
    }


def xrefs_to_slots(binary, slots, limit):
    if not slots:
        return {"slotCount": 0, "slotsWithXrefs": 0, "xrefs": []}
    xrefs = import_script(LOADER_XREF_SCRIPT, "summarize_linux_loader_xrefs_for_rela_slots")
    binary_data, segments = xrefs.load_elf_segments(binary)
    targets = []
    for slot in sorted(slots)[:limit]:
        try:
            file_offset = xrefs.vaddr_to_file_offset(segments, slot)
        except ValueError:
            continue
        targets.append(
            xrefs.Target(
                name=f"rela_slot_0x{slot:x}",
                category="relocation-slot",
                kind="rela-slot",
                file_offset=file_offset,
                image_offset=file_offset,
                vaddr=slot,
            )
        )
    found = xrefs.scan_xrefs(binary_data, segments, targets)
    rows = []
    for target in targets:
        refs = found.get(target, [])
        if not refs:
            continue
        rows.append(
            {
                "slot": f"0x{target.vaddr:x}",
                "fileOffset": f"0x{target.file_offset:x}",
                "xrefCount": len(refs),
                "xrefs": [
                    {
                        "kind": ref["kind"],
                        "xrefVaddr": f"0x{ref['xrefVaddr']:x}",
                        "targetVaddr": f"0x{ref['targetVaddr']:x}",
                        "bytes": ref["bytes"],
                    }
                    for ref in refs[:8]
                ],
            }
        )
    return {"slotCount": len(targets), "slotsWithXrefs": len(rows), "xrefs": rows}


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_ue_rela")
    data = args.binary.read_bytes()
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)
    relocations = ptrctx.load_relocations(data, sections)
    by_addend = relocation_index(relocations)

    targets = []
    targets.extend(
        load_live_targets(
            args.loader_log,
            args.binary,
            args.exe_substring,
            args.category,
            args.name,
            args.live_limit,
        )
    )
    targets.extend(load_symbol_targets(args.symbol_surface, args.symbol_limit))

    rows = []
    all_slots = set()
    for target in targets:
        slots = sorted(by_addend.get(target.value, []))
        all_slots.update(slots)
        rows.append(
            {
                "name": target.name,
                "source": target.source,
                "group": target.group,
                "role": target.role,
                "value": f"0x{target.value:x}",
                "valueSection": section_name(ptrctx, sections, target.value),
                "relocationRefCount": len(slots),
                "relocationSections": dict(Counter(section_name(ptrctx, sections, slot) for slot in slots)),
                "contexts": first_contexts(
                    ptrctx,
                    data,
                    sections,
                    symbols,
                    relocations,
                    slots,
                    args.window,
                    args.context_limit,
                ),
            }
        )

    rows_with_refs = [row for row in rows if row["relocationRefCount"]]
    return {
        "schemaVersion": "dune-elf-ue-relocation-surface/v1",
        "binary": str(args.binary),
        "loaderLog": str(args.loader_log) if args.loader_log else None,
        "symbolSurface": str(args.symbol_surface) if args.symbol_surface else None,
        "targetCount": len(rows),
        "targetsWithRelocationRefs": len(rows_with_refs),
        "relocationRefTotal": sum(row["relocationRefCount"] for row in rows),
        "relocationCount": len(relocations),
        "relocationSlotXrefs": xrefs_to_slots(args.binary, all_slots, args.slot_xref_limit),
        "initArray": load_init_array(ptrctx, data, sections, relocations, symbols, args.init_limit),
        "rows": rows,
    }


def markdown(summary, limit):
    lines = ["# ELF UE Relocation Surface", ""]
    lines.append(f"- Targets checked: `{summary['targetCount']}`")
    lines.append(f"- Targets with relocation refs: `{summary['targetsWithRelocationRefs']}`")
    lines.append(f"- Relocation refs total: `{summary['relocationRefTotal']}`")
    lines.append(f"- ELF relative relocations: `{summary['relocationCount']}`")
    slot_xrefs = summary["relocationSlotXrefs"]
    lines.append(
        f"- Relocation slots scanned for code xrefs: `{slot_xrefs['slotCount']}`; "
        f"slots with code xrefs: `{slot_xrefs['slotsWithXrefs']}`"
    )
    init = summary["initArray"]
    lines.append(
        f"- Init array entries: `{init['entryCount']}`; named: `{init['namedEntryCount']}`; "
        f"UE-named: `{init['ueNamedEntryCount']}`"
    )
    lines.append("")

    if slot_xrefs["xrefs"]:
        lines.append("## Relocation Slot Code Xrefs")
        lines.append("")
        for row in slot_xrefs["xrefs"][:limit]:
            lines.append(f"- slot `{row['slot']}` code xrefs=`{row['xrefCount']}`")
            for ref in row["xrefs"]:
                lines.append(f"  - `{ref['xrefVaddr']}` `{ref['kind']}` bytes=`{ref['bytes']}`")
        lines.append("")

    if init["entries"]:
        lines.append("## Init Array Samples")
        lines.append("")
        for entry in init["entries"][:limit]:
            symbols = " | ".join(entry["symbols"]) if entry["symbols"] else "-"
            lines.append(
                f"- index=`{entry['index']}` slot=`{entry['slot']}` value=`{entry['value']}` "
                f"source=`{entry['source']}` symbols=`{symbols}`"
            )
        lines.append("")

    lines.append("## Targets")
    lines.append("")
    for row in sorted(
        summary["rows"],
        key=lambda item: (-item["relocationRefCount"], item["source"], item["group"], item["name"]),
    )[:limit]:
        lines.append(
            f"- `{row['name']}` source=`{row['source']}` group=`{row['group']}` role=`{row['role']}` "
            f"value=`{row['value']}` section=`{row['valueSection'] or '-'}` "
            f"relocs=`{row['relocationRefCount']}`"
        )
        for context in row["contexts"]:
            lines.append(f"  - slot `{context['slot']}` section=`{context['section']}`")
            for item in context["context"][:5]:
                symbol = " | ".join(item["symbols"]) if item["symbols"] else ""
                string = f" string={item['string']!r}" if item["string"] else ""
                symbol_text = f" symbol={symbol}" if symbol else ""
                lines.append(
                    f"    - slot={item['slot']:+d} at={item['vaddr']} source={item['source']} "
                    f"value={item['value']} section={item['section'] or '-'}{symbol_text}{string}"
                )
    if len(summary["rows"]) > limit:
        lines.append(f"- ... +{len(summary['rows']) - limit} more targets")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Summarize relocation/init-array evidence for UE-like anchors in a Linux ELF target image."
    )
    parser.add_argument("binary", type=Path)
    parser.add_argument("--loader-log", type=Path)
    parser.add_argument("--symbol-surface", type=Path)
    parser.add_argument("--exe-substring", default="DuneSandboxServer")
    parser.add_argument("--category", action="append", default=["ue", "package"])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--live-limit", type=int, default=120)
    parser.add_argument("--symbol-limit", type=int, default=160)
    parser.add_argument("--context-limit", type=int, default=2)
    parser.add_argument("--slot-xref-limit", type=int, default=512)
    parser.add_argument("--init-limit", type=int, default=24)
    parser.add_argument("--window", type=int, default=4)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args(argv)

    if args.loader_log is None and args.symbol_surface is None:
        parser.error("provide --loader-log, --symbol-surface, or both")

    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
