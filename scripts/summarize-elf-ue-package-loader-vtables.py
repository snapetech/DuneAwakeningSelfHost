#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
SCHEMA_VERSION = "dune-elf-ue-package-loader-vtables/v1"
DEFAULT_CLASS_FILTERS = (
    "FLinkerLoad",
    "FAsyncPackage",
    "FAsyncPackage2",
    "FBootLoadObjectData",
    "FBootLoadClassData",
)


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def strip_symbol_suffix(name):
    return name.split(" size=", 1)[0]


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
        result.update({name: lines[index] if index < len(lines) else name for index, name in enumerate(chunk)})
    return result


def file_signature(ptrctx, data, sections, value, length):
    file_offset = ptrctx.addr_to_file_offset(sections, value)
    if file_offset is None:
        return {}
    raw = data[file_offset : min(len(data), file_offset + length)]
    return {
        "fileOffset": f"0x{file_offset:x}",
        "imageOffset": f"0x{file_offset:x}",
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "pattern": " ".join(f"{byte:02x}" for byte in raw),
    }


def function_shape(data, sections, value):
    file_offset = ptrctx_addr_to_file_offset(data, sections, value)
    if file_offset is None:
        return {}
    raw = data[file_offset : min(len(data), file_offset + 64)]
    call_count = raw.count(b"\xe8")
    jump_count = raw.count(b"\xe9") + raw.count(b"\xeb")
    return {
        "startsWithFrame": raw.startswith(b"\x55\x48\x89\xe5"),
        "hasUd2": b"\x0f\x0b" in raw[:16],
        "returnsConstantZero": raw[:8] in (b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3",),
        "callOpcodeCount": call_count,
        "jumpOpcodeCount": jump_count,
        "hasCall": call_count > 0,
        "hasJump": jump_count > 0,
        "hasControlTransfer": call_count > 0 or jump_count > 0,
        "callsDelete": call_count > 0,
        "writesVtableToThis": b"\x48\x89\x07" in raw[:32],
    }


def ptrctx_addr_to_file_offset(data, sections, value):
    del data
    for section in sections:
        if section.addr <= value < section.addr + section.size:
            if section.sh_type == 8:
                return None
            return section.offset + (value - section.addr)
    return None


def source_file_hint(value_hint):
    text = value_hint.get("string", "")
    if not text:
        return ""
    if ".cpp" in text or ".h" in text or "Runtime/" in text or "\\Runtime\\" in text:
        return text
    return ""


def summarize_vtable(ptrctx, data, sections, symbols, relocations, addr, demangled, max_slots, signature_length):
    slots = []
    executable_slots = []
    source_hints = []
    for index in range(max_slots):
        slot_addr = addr + index * 8
        value, source = ptrctx.qword_at_addr(data, sections, relocations, slot_addr)
        if value is None:
            continue
        hint = ptrctx.classify_value(data, sections, symbols, value)
        row = {
            "index": index,
            "slot": f"0x{slot_addr:x}",
            "source": source,
            "value": f"0x{value:x}",
            "section": hint.get("section", ""),
            "flags": hint.get("flags", ""),
            "symbols": hint.get("symbols", []),
            "string": hint.get("string", ""),
        }
        if "X" in row["flags"]:
            row["signature"] = file_signature(ptrctx, data, sections, value, signature_length)
            row["shape"] = function_shape(data, sections, value)
            if row["symbols"] and any("__cxa_pure_virtual" in symbol for symbol in row["symbols"]):
                row["candidateKind"] = "pure-virtual"
            elif row["shape"].get("hasUd2"):
                row["candidateKind"] = "trap"
            elif index in (2, 3) or row["shape"].get("writesVtableToThis"):
                row["candidateKind"] = "destructor-or-header"
            elif row["shape"].get("returnsConstantZero"):
                row["candidateKind"] = "trivial"
            else:
                row["candidateKind"] = "method"
            executable_slots.append(row)
        hint_text = source_file_hint(hint)
        if hint_text and hint_text not in source_hints:
            source_hints.append(hint_text)
        slots.append(row)
    return {
        "vtable": f"0x{addr:x}",
        "demangled": demangled,
        "executableSlotCount": len(executable_slots),
        "sourceHints": source_hints[:12],
        "executableSlots": executable_slots,
        "slots": slots,
    }


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_package_vtables")
    data = args.binary.read_bytes()
    sections = ptrctx.load_sections(data)
    relocations = ptrctx.load_relocations(data, sections)
    symbols = ptrctx.load_symbols(data, sections)

    raw_names = sorted({strip_symbol_suffix(name) for names in symbols.values() for name in names})
    demangled_by_name = demangle(raw_names)
    filters = tuple(args.class_filter or (() if args.no_default_class_filters else DEFAULT_CLASS_FILTERS))
    rows = []
    for raw in args.address or []:
        if "=" in raw:
            label, value = raw.split("=", 1)
        else:
            value = raw
            label = f"reviewed-table-{value}"
        rows.append(
            summarize_vtable(
                ptrctx,
                data,
                sections,
                symbols,
                relocations,
                int(value, 0),
                label,
                args.max_slots,
                args.signature_length,
            )
        )
    for value, names in sorted(symbols.items()):
        for raw in names:
            name = strip_symbol_suffix(raw)
            demangled = demangled_by_name.get(name, name)
            if not demangled.startswith("vtable for "):
                continue
            if not any(fragment in demangled for fragment in filters):
                continue
            rows.append(
                summarize_vtable(
                    ptrctx,
                    data,
                    sections,
                    symbols,
                    relocations,
                    value,
                    demangled,
                    args.max_slots,
                    args.signature_length,
                )
            )
            break

    rows.sort(key=lambda row: (-row["executableSlotCount"], row["demangled"], row["vtable"]))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "binary": str(args.binary),
        "classFilters": list(filters),
        "explicitAddresses": list(args.address or []),
        "vtableCount": len(rows),
        "executableSlotCount": sum(row["executableSlotCount"] for row in rows),
        "rows": rows[: args.limit],
    }


def markdown(summary):
    lines = ["# ELF UE Package Loader VTables", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- VTables: `{summary['vtableCount']}`")
    lines.append(f"- Executable slots: `{summary['executableSlotCount']}`")
    lines.append(f"- Class filters: `{summary['classFilters']}`")
    if summary.get("explicitAddresses"):
        lines.append(f"- Explicit addresses: `{summary['explicitAddresses']}`")
    lines.append("")
    for row in summary["rows"]:
        lines.append(f"## {row['demangled']}")
        lines.append("")
        lines.append(
            f"- vtable=`{row['vtable']}` executableSlots=`{row['executableSlotCount']}` "
            f"sourceHints=`{row['sourceHints']}`"
        )
        for slot in row["executableSlots"][:24]:
            sig = slot.get("signature", {})
            lines.append(
                f"- slot=`{slot['index']}` kind=`{slot.get('candidateKind', '')}` "
                f"target=`{slot['value']}` section=`{slot['section']}` "
                f"signatureFile=`{sig.get('fileOffset', '')}` sha256=`{sig.get('sha256', '')[:16]}`"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Summarize target-image UE package-loader vtable method candidates from a stripped ELF."
    )
    parser.add_argument("binary", type=Path)
    parser.add_argument("--address", action="append", default=[], help="Explicit table as LABEL=0xADDR or 0xADDR")
    parser.add_argument("--class-filter", action="append", default=[])
    parser.add_argument("--no-default-class-filters", action="store_true")
    parser.add_argument("--max-slots", type=int, default=96)
    parser.add_argument("--signature-length", type=int, default=32)
    parser.add_argument("--limit", type=int, default=32)
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
