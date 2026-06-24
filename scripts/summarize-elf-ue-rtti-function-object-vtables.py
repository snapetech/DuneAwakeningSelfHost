#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
SCHEMA_VERSION = "dune-elf-ue-rtti-function-object-vtables/v1"


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


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def printable_strings(data, min_len=8):
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


def file_offset_to_addr(ptrctx, sections, file_offset):
    section = ptrctx.section_for_file_offset(sections, file_offset)
    if not section:
        return None
    return section.addr + (file_offset - section.offset)


def demangle_typeinfo_names(raw_names):
    if not raw_names:
        return {}
    mangled = ["_ZTS" + name for name in raw_names]
    try:
        proc = subprocess.run(
            ["c++filt", *mangled],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return dict(zip(raw_names, raw_names))
    lines = proc.stdout.splitlines()
    return {
        raw: (lines[index] if index < len(lines) else raw)
        for index, raw in enumerate(raw_names)
    }


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


def function_shape(ptrctx, data, sections, value):
    file_offset = ptrctx.addr_to_file_offset(sections, value)
    if file_offset is None:
        return {}
    raw = data[file_offset : min(len(data), file_offset + 64)]
    return {
        "startsWithFrame": raw.startswith(b"\x55\x48\x89\xe5"),
        "hasUd2": b"\x0f\x0b" in raw[:16],
        "returnsConstantZero": raw[:8] == b"\x55\x48\x89\xe5\x31\xc0\x5d\xc3",
        "writesVtableToThis": b"\x48\x89\x07" in raw[:32],
        "hasCall": b"\xe8" in raw[:64],
        "hasIndirectCall": b"\xff\x10" in raw[:64] or b"\xff\x50" in raw[:64] or b"\xff\xd0" in raw[:64],
    }


def candidate_kind(hint, shape, direct_calls=None):
    if hint.get("symbols") and any("__cxa_pure_virtual" in symbol for symbol in hint["symbols"]):
        return "pure-virtual"
    if any("_ZdlPvm" in symbol or "operator delete" in symbol for call in (direct_calls or []) for symbol in call.get("symbols", [])):
        return "deleting-destructor"
    if shape.get("hasUd2"):
        return "trap"
    if shape.get("returnsConstantZero"):
        return "trivial"
    if shape.get("writesVtableToThis"):
        return "destructor-or-header"
    if shape.get("hasIndirectCall"):
        return "function-object-dispatch"
    return "method"


def direct_control_targets(ptrctx, data, sections, symbols, value, length):
    file_offset = ptrctx.addr_to_file_offset(sections, value)
    if file_offset is None:
        return []
    raw = data[file_offset : min(len(data), file_offset + length)]
    rows = []
    for index in range(0, max(0, len(raw) - 4)):
        if raw[index] == 0xC3 or raw[index : index + 2] == b"\x0f\x0b":
            break
        opcode = raw[index]
        if opcode not in (0xE8, 0xE9):
            continue
        rel = struct.unpack_from("<i", raw, index + 1)[0]
        source = value + index
        target = source + 5 + rel
        hint = ptrctx.classify_value(data, sections, symbols, target)
        if "X" not in hint.get("flags", ""):
            continue
        rows.append(
            {
                "opcode": "call" if opcode == 0xE8 else "jmp",
                "source": f"0x{source:x}",
                "target": f"0x{target:x}",
                "section": hint.get("section", ""),
                "symbols": hint.get("symbols", []),
            }
        )
    return rows[:16]


def qword_ref_addrs(ptrctx, data, sections, relocations, target):
    addrs = set()
    for file_offset in ptrctx.find_qword_refs(data, target):
        section = ptrctx.section_for_file_offset(sections, file_offset)
        if section:
            addrs.add(section.addr + (file_offset - section.offset))
    for addr, addend in relocations.items():
        if addend == target:
            addrs.add(addr)
    return sorted(addrs)


def executable_slots_after(
    ptrctx,
    data,
    sections,
    symbols,
    relocations,
    header_addr,
    max_slots,
    signature_length,
    call_scan_length,
):
    slots = []
    for index in range(max_slots):
        slot_addr = header_addr + 8 + index * 8
        value, source = ptrctx.qword_at_addr(data, sections, relocations, slot_addr)
        if value is None:
            break
        hint = ptrctx.classify_value(data, sections, symbols, value)
        if "X" not in hint.get("flags", ""):
            if index == 0:
                return []
            break
        shape = function_shape(ptrctx, data, sections, value)
        direct_calls = direct_control_targets(ptrctx, data, sections, symbols, value, call_scan_length)
        slots.append(
            {
                "index": index,
                "slot": f"0x{slot_addr:x}",
                "source": source,
                "target": f"0x{value:x}",
                "section": hint.get("section", ""),
                "symbols": hint.get("symbols", []),
                "candidateKind": candidate_kind(hint, shape, direct_calls),
                "shape": shape,
                "directControlTargetCount": len(direct_calls),
                "directControlTargets": direct_calls,
                "signature": file_signature(ptrctx, data, sections, value, signature_length),
            }
        )
    return slots


def row_typeinfo_name_slots(row):
    slots = []
    for slot in row.get("pointerSlots", []):
        if slot.get("section") != ".data.rel.ro":
            continue
        try:
            slots.append(parse_int(slot["address"]))
        except (KeyError, ValueError):
            continue
    return sorted(set(slots))


def classify_owner_lead(owners, demangled_typeinfo):
    text = "\n".join(list(owners or []) + [demangled_typeinfo or ""])
    lead_kind = "function-object"
    reasons = []
    if any(name in text for name in ("FLinkerLoad::", "FAsyncPackage::", "FAsyncPackage2::", "FAsyncLoadingThread::", "FAsyncArchive::")):
        lead_kind = "package-loader-owner-function"
        reasons.append("package-loader-owner")
    if "RequestAsyncLoad" in text:
        lead_kind = "streamable-request"
        reasons.append("owner-request-async-load")
    if "TryLoadObjectImplementation" in text:
        lead_kind = "loadobject-owner-method"
        reasons.append("owner-try-load-object-implementation")
    if "FSoftObjectPath" in text:
        reasons.append("soft-object-path-argument")
    if "FStreamableHandle" in text:
        reasons.append("streamable-handle-callback")
    if "UPackage*" in text or "UPackage *" in text:
        lead_kind = "async-package-completion-delegate"
        reasons.append("upackage-callback")
    if "EAsyncLoadingResult" in text:
        lead_kind = "async-package-completion-delegate"
        reasons.append("async-loading-result-callback")
    if "UObject*" in text or "UObject *" in text:
        reasons.append("uobject-callback")
    if "LoadPackage" in text or "StaticLoadObject" in text or "StaticLoadClass" in text or "ResolveName" in text:
        reasons.append("core-package-name-present")
    if "LoadObject" in text or "TryLoadObjectImplementation" in text:
        reasons.append("load-object-name-present")
    if "LoadAsset" in text or "LoadAssets" in text:
        lead_kind = "loadasset-owner-surface"
        reasons.append("load-asset-name-present")
    if "BootLoadObjectData" in text or "BootLoadClassData" in text:
        lead_kind = "boot-load-data-struct"
        reasons.append("boot-load-data-struct")
    promotable = False
    blockers = [
        "function-object RTTI lead is not a stable exported/static UE package-loading ABI",
        "no target-image StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName anchor proved",
        "requires decompile review plus guarded ABI/call-frame proof before native LoadAsset promotion",
    ]
    if lead_kind == "loadobject-owner-method":
        blockers.insert(
            1,
            "owner method is gameplay/object-specific and does not prove a reusable core UE LoadObject call ABI",
        )
    if lead_kind == "loadasset-owner-surface":
        blockers.insert(
            1,
            "LoadAsset owner surface is gameplay/asset-action code and does not prove StaticLoadObject/StaticLoadClass ABI",
        )
    if lead_kind == "boot-load-data-struct":
        blockers.insert(
            1,
            "boot-load data RTTI is reflected data/struct metadata and not a callable package-loading ABI",
        )
    if lead_kind == "async-package-completion-delegate":
        blockers.insert(
            1,
            "async package completion delegate is a callback surface and does not prove a package-load entry ABI",
        )
    if lead_kind == "package-loader-owner-function":
        blockers.insert(
            1,
            "package-loader owner function-object code is lifecycle/linker plumbing until callgraph, decompile, or runtime call-frame proof identifies a stable entry ABI",
        )
    return {
        "leadKind": lead_kind,
        "leadReasons": reasons,
        "promotableAsPackageAnchor": promotable,
        "promotionBlockers": blockers,
    }


def symbol_surface_package_leads(ptrctx, data, sections, relocations, source, needles=None):
    leads = []
    needles = list(needles or [])
    for row in source.get("rows", []):
        demangled = row.get("demangled", "")
        matched_needle = any(needle in demangled for needle in needles)
        if ("package" not in row.get("groups", []) and not matched_needle) or row.get("falsePositive"):
            continue
        role = row.get("role", "")
        value = row.get("value")
        if not isinstance(value, int):
            continue
        owners = [demangled]
        if role == "rtti-vtable":
            leads.append(
                {
                    "owners": owners,
                    "demangledTypeinfo": demangled,
                    "text": demangled,
                    "addressText": f"0x{value:x}",
                    "typeinfoObject": "",
                    "typeinfoNameSlot": "",
                    "vtableRefSlots": [value + 8],
                }
            )
            continue
        typeinfo_objects = []
        if role == "rtti-typeinfo":
            typeinfo_objects = [value]
        elif role == "rtti-name":
            for name_slot in qword_ref_addrs(ptrctx, data, sections, relocations, value):
                section = ptrctx.section_for_addr(sections, name_slot)
                if section and section.name == ".data.rel.ro":
                    typeinfo_objects.append(name_slot - 8)
        for typeinfo_object in sorted(set(typeinfo_objects)):
            vtable_ref_slots = []
            for ref_addr in qword_ref_addrs(ptrctx, data, sections, relocations, typeinfo_object):
                section = ptrctx.section_for_addr(sections, ref_addr)
                if section and section.name == ".data.rel.ro":
                    vtable_ref_slots.append(ref_addr)
            if not vtable_ref_slots:
                continue
            leads.append(
                {
                    "owners": owners,
                    "demangledTypeinfo": demangled,
                    "text": demangled,
                    "addressText": f"0x{value:x}",
                    "typeinfoObject": f"0x{typeinfo_object:x}",
                    "typeinfoNameSlot": "",
                    "vtableRefSlots": sorted(set(vtable_ref_slots)),
                }
            )
    return leads


def static_wrapper_package_leads(ptrctx, data, sections, relocations, source, owners_filter):
    leads = []
    for row in source.get("packageStrings", []):
        owners = row.get("ownerFunctionCandidates") or []
        if not owners:
            continue
        if owners_filter and not any(fragment in owner for fragment in owners_filter for owner in owners):
            continue
        for name_slot in row_typeinfo_name_slots(row):
            typeinfo_object = name_slot - 8
            vtable_ref_slots = []
            for ref_addr in qword_ref_addrs(ptrctx, data, sections, relocations, typeinfo_object):
                section = ptrctx.section_for_addr(sections, ref_addr)
                if section and section.name == ".data.rel.ro":
                    vtable_ref_slots.append(ref_addr)
            if not vtable_ref_slots:
                continue
            leads.append(
                {
                    "owners": owners,
                    "demangledTypeinfo": row.get("demangledTypeinfo", ""),
                    "text": row.get("text", ""),
                    "addressText": row.get("addressText", ""),
                    "typeinfoObject": f"0x{typeinfo_object:x}",
                    "typeinfoNameSlot": f"0x{name_slot:x}",
                    "vtableRefSlots": sorted(set(vtable_ref_slots)),
                }
            )
    return leads


def raw_typeinfo_name_leads(ptrctx, data, sections, relocations, needles):
    if not needles:
        return []
    candidate_rows = []
    for file_offset, text in printable_strings(data, 8):
        if not any(needle in text for needle in needles):
            continue
        if not (text.startswith("N") or text.startswith("K") or "::" in text):
            continue
        addr = file_offset_to_addr(ptrctx, sections, file_offset)
        if addr is None:
            continue
        candidate_rows.append((addr, text))
    demangled = demangle_typeinfo_names([text for _, text in candidate_rows])
    leads = []
    for addr, text in candidate_rows:
        demangled_text = demangled.get(text, text)
        if not any(needle in text or needle in demangled_text for needle in needles):
            continue
        name_slots = []
        for name_slot in qword_ref_addrs(ptrctx, data, sections, relocations, addr):
            section = ptrctx.section_for_addr(sections, name_slot)
            if section and section.name == ".data.rel.ro":
                name_slots.append(name_slot)
        for name_slot in sorted(set(name_slots)):
            typeinfo_object = name_slot - 8
            vtable_ref_slots = []
            for ref_addr in qword_ref_addrs(ptrctx, data, sections, relocations, typeinfo_object):
                section = ptrctx.section_for_addr(sections, ref_addr)
                if section and section.name == ".data.rel.ro":
                    vtable_ref_slots.append(ref_addr)
            if not vtable_ref_slots:
                continue
            leads.append(
                {
                    "owners": [demangled_text],
                    "demangledTypeinfo": demangled_text,
                    "text": text,
                    "addressText": f"0x{addr:x}",
                    "typeinfoObject": f"0x{typeinfo_object:x}",
                    "typeinfoNameSlot": f"0x{name_slot:x}",
                    "vtableRefSlots": sorted(set(vtable_ref_slots)),
                }
            )
    return leads


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_rtti_function_objects")
    data = args.binary.read_bytes()
    sections = ptrctx.load_sections(data)
    symbols = ptrctx.load_symbols(data, sections)
    relocations = ptrctx.load_relocations(data, sections)
    leads = []
    if args.static_wrapper_json:
        leads.extend(static_wrapper_package_leads(ptrctx, data, sections, relocations, load_json(args.static_wrapper_json), args.owner))
    if args.symbol_surface_json:
        leads.extend(
            symbol_surface_package_leads(
                ptrctx,
                data,
                sections,
                relocations,
                load_json(args.symbol_surface_json),
                args.symbol_needle,
            )
        )
    leads.extend(raw_typeinfo_name_leads(ptrctx, data, sections, relocations, args.raw_typeinfo_needle))
    rows = []
    for lead in leads:
        header_refs = []
        for ref_addr in lead["vtableRefSlots"]:
            slots = executable_slots_after(
                ptrctx,
                data,
                sections,
                symbols,
                relocations,
                ref_addr,
                args.max_slots,
                args.signature_length,
                args.call_scan_length,
            )
            if not slots:
                continue
            header_refs.append(
                {
                    "typeinfoRefSlot": f"0x{ref_addr:x}",
                    "vtableAddressPoint": f"0x{ref_addr + 8:x}",
                    "executableSlotCount": len(slots),
                    "methodSlotCount": sum(1 for slot in slots if slot.get("candidateKind") == "method"),
                    "directControlTargetCount": sum(slot.get("directControlTargetCount", 0) for slot in slots),
                    "slots": slots,
                }
            )
        if not header_refs:
            continue
        classification = classify_owner_lead(lead["owners"], lead.get("demangledTypeinfo", ""))
        rows.append(
            {
                "owners": lead["owners"],
                **classification,
                "text": lead.get("text", ""),
                "addressText": lead.get("addressText", ""),
                "demangledTypeinfo": lead.get("demangledTypeinfo", ""),
                "typeinfoNameSlot": lead.get("typeinfoNameSlot", ""),
                "typeinfoObject": lead.get("typeinfoObject", ""),
                "vtableCount": len(header_refs),
                "methodSlotCount": sum(ref["methodSlotCount"] for ref in header_refs),
                "directControlTargetCount": sum(ref["directControlTargetCount"] for ref in header_refs),
                "vtables": header_refs,
            }
        )
    rows.sort(key=lambda row: (-row["methodSlotCount"], row["owners"], row["typeinfoObject"]))
    callgraph_seeds = build_callgraph_seeds(rows, args.seed_kind, args.seed_limit)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "binary": str(args.binary),
        "staticWrapperJson": str(args.static_wrapper_json) if args.static_wrapper_json else "",
        "symbolSurfaceJson": str(args.symbol_surface_json) if args.symbol_surface_json else "",
        "rawTypeinfoNeedles": list(args.raw_typeinfo_needle),
        "rowCount": len(rows),
        "vtableCount": sum(row["vtableCount"] for row in rows),
        "methodSlotCount": sum(row["methodSlotCount"] for row in rows),
        "directControlTargetCount": sum(row["directControlTargetCount"] for row in rows),
        "promotablePackageAnchorCount": sum(1 for row in rows if row.get("promotableAsPackageAnchor")),
        "leadKindCounts": {
            kind: sum(1 for row in rows if row.get("leadKind") == kind)
            for kind in sorted({row.get("leadKind", "") for row in rows})
            if kind
        },
        "callgraphSeeds": callgraph_seeds,
        "rows": rows[: args.limit],
        "promotionRule": (
            "Function-object vtables are owner-method leads only. Promote package loading only after decompile "
            "review proves a callable target-image package/load-object ABI and guarded invocation contract."
        ),
    }


def build_callgraph_seeds(rows, seed_kinds, limit):
    seed_kinds = set(seed_kinds or ("method", "function-object-dispatch"))
    seeds = []
    seen = set()
    for row_index, row in enumerate(rows):
        for vtable_index, vtable in enumerate(row.get("vtables", [])):
            for slot in vtable.get("slots", []):
                kind = slot.get("candidateKind", "")
                target = slot.get("target", "")
                if kind not in seed_kinds or not target or target in seen:
                    continue
                seen.add(target)
                label = f"rtti{row_index}_vt{vtable_index}_slot{slot.get('index', 0)}_{kind.replace('-', '_')}"
                seeds.append(
                    {
                        "label": label,
                        "target": target,
                        "candidateKind": kind,
                        "leadKind": row.get("leadKind", ""),
                        "owner": (row.get("owners") or [""])[0],
                    }
                )
                if len(seeds) >= limit:
                    return seeds
    return seeds


def markdown(summary):
    lines = ["# ELF UE RTTI Function Object VTables", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    if summary.get("staticWrapperJson"):
        lines.append(f"- Static wrapper JSON: `{summary['staticWrapperJson']}`")
    if summary.get("symbolSurfaceJson"):
        lines.append(f"- Symbol surface JSON: `{summary['symbolSurfaceJson']}`")
    if summary.get("rawTypeinfoNeedles"):
        lines.append(f"- Raw typeinfo needles: `{', '.join(summary['rawTypeinfoNeedles'])}`")
    lines.append(f"- Rows: `{summary['rowCount']}`")
    lines.append(f"- VTables: `{summary['vtableCount']}`")
    lines.append(f"- Method slots: `{summary['methodSlotCount']}`")
    lines.append(f"- Direct control targets: `{summary.get('directControlTargetCount', 0)}`")
    lines.append(f"- Lead kinds: `{summary.get('leadKindCounts', {})}`")
    lines.append(f"- Promotable package anchors: `{summary.get('promotablePackageAnchorCount', 0)}`")
    lines.append(f"- Promotion rule: `{summary['promotionRule']}`")
    if summary.get("callgraphSeeds"):
        seed_args = " ".join(f"--seed {seed['label']}={seed['target']}" for seed in summary["callgraphSeeds"][:12])
        lines.append(f"- Callgraph seed args: `{seed_args}`")
    lines.append("")
    if not summary["rows"]:
        lines.append("- none")
    for row in summary["rows"]:
        lines.append(f"## {', '.join(row['owners'])}")
        lines.append("")
        lines.append(
            f"- typeinfoObject=`{row['typeinfoObject']}` nameSlot=`{row['typeinfoNameSlot']}` "
            f"vtables=`{row['vtableCount']}` methods=`{row['methodSlotCount']}` "
            f"directControlTargets=`{row.get('directControlTargetCount', 0)}`"
        )
        lines.append(
            f"- leadKind=`{row.get('leadKind', '')}` promotableAsPackageAnchor="
            f"`{str(bool(row.get('promotableAsPackageAnchor'))).lower()}` "
            f"reasons=`{', '.join(row.get('leadReasons', [])) or 'none'}`"
        )
        for blocker in row.get("promotionBlockers", [])[:4]:
            lines.append(f"  - blocker=`{blocker}`")
        if row.get("demangledTypeinfo"):
            lines.append(f"- demangled=`{row['demangledTypeinfo'][:260]}`")
        for vtable in row["vtables"]:
            lines.append(
                f"- vtableAddressPoint=`{vtable['vtableAddressPoint']}` "
                f"typeinfoRefSlot=`{vtable['typeinfoRefSlot']}` methods=`{vtable['methodSlotCount']}` "
                f"directControlTargets=`{vtable.get('directControlTargetCount', 0)}`"
            )
            for slot in vtable["slots"][:8]:
                sig = slot.get("signature", {})
                lines.append(
                    f"  - slot=`{slot['index']}` kind=`{slot['candidateKind']}` target=`{slot['target']}` "
                    f"calls=`{slot.get('directControlTargetCount', 0)}` "
                    f"signatureFile=`{sig.get('fileOffset', '')}` sha256=`{sig.get('sha256', '')[:16]}`"
                )
                for call in slot.get("directControlTargets", [])[:4]:
                    lines.append(
                        f"    - {call['opcode']} source=`{call['source']}` target=`{call['target']}` "
                        f"section=`{call['section']}`"
                    )
        lines.append("")
    return "\n".join(lines)


def seed_args(summary):
    return " ".join(f"--seed {seed['label']}={seed['target']}" for seed in summary.get("callgraphSeeds", [])) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Summarize executable vtable slots for RTTI function-object package/streamable leads."
    )
    parser.add_argument("binary", type=Path)
    parser.add_argument("--static-wrapper-json", type=Path)
    parser.add_argument("--symbol-surface-json", type=Path)
    parser.add_argument(
        "--symbol-needle",
        action="append",
        default=[],
        help="include symbol-surface RTTI rows whose demangled name contains this text even outside the package group",
    )
    parser.add_argument(
        "--raw-typeinfo-needle",
        action="append",
        default=[],
        help="include raw Itanium typeinfo-name strings whose encoded or demangled text contains this fragment",
    )
    parser.add_argument("--owner", action="append", default=[])
    parser.add_argument("--max-slots", type=int, default=12)
    parser.add_argument("--signature-length", type=int, default=32)
    parser.add_argument("--call-scan-length", type=int, default=192)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--seed-kind", action="append", default=[])
    parser.add_argument("--seed-limit", type=int, default=32)
    parser.add_argument("--format", choices=("json", "markdown", "seeds"), default="markdown")
    args = parser.parse_args(argv)
    if not args.static_wrapper_json and not args.symbol_surface_json and not args.raw_typeinfo_needle:
        parser.error("one of --static-wrapper-json, --symbol-surface-json, or --raw-typeinfo-needle is required")
    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "seeds":
        sys.stdout.write(seed_args(summary))
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
