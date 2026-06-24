#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
SCHEMA_VERSION = "dune-ue4ss-package-route-vtable-targets/v1"
DEFAULT_COMPANION_SLOTS = ("0x3a0", "0x3d8")


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value):
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def parse_slot_target(raw):
    if "=" in raw:
        name, value = raw.split("=", 1)
    else:
        name = ""
        value = raw
    if "@" not in value:
        raise ValueError(f"slot target must be NAME=TARGET@SLOT_OFFSET, got {raw!r}")
    target_text, slot_text = value.rsplit("@", 1)
    target = parse_int(target_text)
    slot_offset = parse_int(slot_text)
    return {
        "name": name or f"target-0x{target:x}-slot-0x{slot_offset:x}",
        "target": target,
        "slotOffset": slot_offset,
    }


def section_name(ptrctx, sections, addr):
    section = ptrctx.section_for_addr(sections, addr)
    return section.name if section else ""


def classify(ptrctx, data, sections, symbols, value):
    row = ptrctx.classify_value(data, sections, symbols, value)
    return {
        "value": row.get("value", f"0x{value:x}"),
        "section": row.get("section", ""),
        "flags": row.get("flags", ""),
        "symbols": row.get("symbols", []),
        "string": row.get("string", ""),
    }


def qword_row(ptrctx, data, sections, symbols, relocations, addr):
    value, source = ptrctx.qword_at_addr(data, sections, relocations, addr)
    if value is None:
        return {
            "slotAddress": f"0x{addr:x}",
            "source": source,
            "value": "",
            "section": "",
            "flags": "",
            "symbols": [],
            "string": "",
        }
    return {
        "slotAddress": f"0x{addr:x}",
        "source": source,
        **classify(ptrctx, data, sections, symbols, value),
    }


def relocation_refs_to_target(relocations, target):
    return [addr for addr, addend in sorted(relocations.items()) if addend == target]


def raw_qword_refs_to_target(ptrctx, data, sections, target):
    refs = []
    for file_offset in ptrctx.find_qword_refs(data, target):
        section = ptrctx.section_for_file_offset(sections, file_offset)
        if section is None:
            continue
        refs.append(section.addr + (file_offset - section.offset))
    return refs


def summarize_slot_target(ptrctx, data, sections, symbols, relocations, spec, companion_slots, context_window):
    target = spec["target"]
    expected_slot_offset = spec["slotOffset"]
    refs = []
    for source, slot_addr in [
        *[("rela", addr) for addr in relocation_refs_to_target(relocations, target)],
        *[("raw", addr) for addr in raw_qword_refs_to_target(ptrctx, data, sections, target)],
    ]:
        vtable_base = slot_addr - expected_slot_offset
        if vtable_base < 0:
            continue
        context = []
        for delta in range(-context_window, context_window + 1):
            addr = slot_addr + delta * 8
            row = qword_row(ptrctx, data, sections, symbols, relocations, addr)
            row["relativeSlot"] = delta
            row["slotOffset"] = f"0x{addr - vtable_base:x}"
            context.append(row)
        companion_rows = []
        for slot_offset in companion_slots:
            companion_addr = vtable_base + slot_offset
            companion_rows.append(
                {
                    "slotOffset": f"0x{slot_offset:x}",
                    **qword_row(ptrctx, data, sections, symbols, relocations, companion_addr),
                }
            )
        refs.append(
            {
                "source": source,
                "slotAddress": f"0x{slot_addr:x}",
                "slotSection": section_name(ptrctx, sections, slot_addr),
                "expectedSlotOffset": f"0x{expected_slot_offset:x}",
                "inferredVtableBase": f"0x{vtable_base:x}",
                "inferredVtableSection": section_name(ptrctx, sections, vtable_base),
                "vtableSymbols": symbols.get(vtable_base, [])[:8],
                "context": context,
                "companionSlots": companion_rows,
            }
        )
    return {
        "name": spec["name"],
        "target": f"0x{target:x}",
        "expectedSlotOffset": f"0x{expected_slot_offset:x}",
        "refCount": len(refs),
        "refs": refs,
    }


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_route_vtables")
    data = args.binary.read_bytes()
    sections = ptrctx.load_sections(data)
    relocations = ptrctx.load_relocations(data, sections)
    symbols = ptrctx.load_symbols(data, sections)
    companion_slots = [parse_int(slot) for slot in (args.companion_slot or DEFAULT_COMPANION_SLOTS)]
    targets = [
        summarize_slot_target(
            ptrctx,
            data,
            sections,
            symbols,
            relocations,
            parse_slot_target(raw),
            companion_slots,
            args.context_window,
        )
        for raw in args.slot_target
    ]
    blockers = []
    if not any(target["refCount"] for target in targets):
        blockers.append("no vtable/table references found for requested target@slot specs")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "binary": str(args.binary),
        "companionSlots": [f"0x{slot:x}" for slot in companion_slots],
        "contextWindow": args.context_window,
        "targetCount": len(targets),
        "targets": targets,
        "ready": not blockers,
        "blockers": blockers,
    }


def markdown(summary):
    lines = ["# UE4SS Package Route Vtable Targets", ""]
    lines.append(f"- Ready: `{str(summary.get('ready')).lower()}`")
    lines.append(f"- Binary: `{summary.get('binary', '')}`")
    lines.append(f"- Companion slots: `{', '.join(summary.get('companionSlots', []))}`")
    for blocker in summary.get("blockers", []):
        lines.append(f"- Blocker: {blocker}")
    lines.append("")
    for target in summary.get("targets", []):
        lines.append(f"## {target['name']} `{target['target']}@{target['expectedSlotOffset']}`")
        lines.append("")
        lines.append(f"- Refs: `{target['refCount']}`")
        for ref in target.get("refs", []):
            symbol_text = " | ".join(ref.get("vtableSymbols", [])) or "-"
            lines.append(
                f"- `{ref['source']}` slot=`{ref['slotAddress']}` section=`{ref['slotSection']}` "
                f"inferredVtable=`{ref['inferredVtableBase']}` vtableSection=`{ref['inferredVtableSection']}` "
                f"symbols=`{symbol_text}`"
            )
            for companion in ref.get("companionSlots", []):
                bits = [
                    f"slot={companion['slotOffset']}",
                    f"at={companion['slotAddress']}",
                    f"value={companion.get('value', '') or '-'}",
                    f"section={companion.get('section', '') or '-'}",
                ]
                if companion.get("flags"):
                    bits.append(f"flags={companion['flags']}")
                if companion.get("symbols"):
                    bits.append("symbols=" + " | ".join(companion["symbols"]))
                if companion.get("string"):
                    bits.append(f"string={companion['string']!r}")
                lines.append("  - companion " + " ".join(bits))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Find vtable/table candidates containing package route targets at known slot offsets.")
    parser.add_argument("binary", type=Path)
    parser.add_argument(
        "--slot-target",
        action="append",
        required=True,
        help="NAME=TARGET@SLOT_OFFSET, e.g. wrapper=0x129d5880@0x3d8",
    )
    parser.add_argument("--companion-slot", action="append", help="additional slot offsets to show for each inferred table")
    parser.add_argument("--context-window", type=int, default=2)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
