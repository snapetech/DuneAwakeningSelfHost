#!/usr/bin/env python3
import argparse
import importlib.util
import json
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER_CONTEXT_SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"
SCHEMA_VERSION = "dune-elf-ue-package-wrapper-candidates/v1"
DEFAULT_NEAR_BYTES = 96


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
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text, 0)


def executable_sections(sections):
    executable = []
    for section in sections:
        flags = getattr(section, "flags", "")
        if isinstance(flags, int):
            if flags & 0x4:
                executable.append(section)
        elif "X" in str(flags):
            executable.append(section)
    return executable


def section_bytes(data, section):
    if getattr(section, "sh_type", None) == 8:
        return b""
    start = section.offset
    end = min(len(data), section.offset + section.size)
    return data[start:end]


def call_targets_in_section(section, raw):
    for index in range(0, max(0, len(raw) - 4)):
        opcode = raw[index]
        if opcode not in (0xE8, 0xE9):
            continue
        rel = struct.unpack_from("<i", raw, index + 1)[0]
        source = section.addr + index
        yield opcode, source, source + 5 + rel


def objdump_direct_calls(binary, targets):
    if not targets:
        return []
    target_hex = {}
    for target in targets:
        target_hex[f"{target:x}"] = target
        target_hex[f"0{target:x}"] = target
    try:
        proc = subprocess.run(
            ["objdump", "-d", str(binary)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    rows = []
    for line in proc.stdout.splitlines():
        if "\tcall" not in line and "\tjmp" not in line:
            continue
        left, _, right = line.partition(":")
        try:
            source = int(left.strip(), 16)
        except ValueError:
            continue
        stripped = right.strip()
        for text, target in target_hex.items():
            if f" {text} " in stripped or stripped.startswith(f"call   {text}") or stripped.startswith(f"jmp    {text}"):
                opcode = "call" if "\tcall" in line else "jmp"
                rows.append((opcode, source, target))
                break
    return rows


def slot_allowed(slot_value, slot_filters):
    if not slot_filters:
        return True
    text = str(slot_value)
    try:
        numeric = int(text, 0)
    except (TypeError, ValueError):
        numeric = None
    for item in slot_filters:
        if text == item:
            return True
        if numeric is not None:
            try:
                if numeric == int(item, 0):
                    return True
            except ValueError:
                pass
    return False


def collect_package_method_targets(package_vtables, limit_per_vtable, vtable_filters=None, slot_filters=None):
    targets = []
    seen = set()
    if not isinstance(package_vtables, dict):
        return targets
    vtable_filters = tuple(vtable_filters or [])
    slot_filters = tuple(slot_filters or [])
    for row in package_vtables.get("rows", []) + package_vtables.get("vtables", []):
        vtable = row.get("demangled") or row.get("name") or ""
        if vtable_filters and not any(fragment in vtable for fragment in vtable_filters):
            continue
        slots = row.get("executableSlots") or row.get("slots") or []
        count = 0
        for slot in slots:
            if slot.get("candidateKind") != "method":
                continue
            slot_value = slot.get("index") if slot.get("index") is not None else slot.get("slot")
            if not slot_allowed(slot_value, slot_filters):
                continue
            target = parse_int(slot.get("value") or slot.get("target") or slot.get("imageOffset"))
            if target is None:
                continue
            key = (vtable, target, slot_value)
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                {
                    "vtable": vtable,
                    "slot": slot_value,
                    "target": target,
                    "candidateKind": slot.get("candidateKind"),
                }
            )
            count += 1
            if limit_per_vtable and count >= limit_per_vtable:
                break
    return targets


def nearby_ascii(raw, offset, near_bytes):
    start = max(0, offset - near_bytes)
    end = min(len(raw), offset + near_bytes)
    window = raw[start:end]
    strings = []
    current = bytearray()
    for byte in window:
        if 32 <= byte < 127:
            current.append(byte)
        else:
            if len(current) >= 4:
                strings.append(current.decode("ascii", errors="replace"))
            current.clear()
    if len(current) >= 4:
        strings.append(current.decode("ascii", errors="replace"))
    return strings[:12]


def rank_callsite(row):
    score = 0
    reasons = []
    strings = " ".join(row.get("nearbyStrings", []))
    needles = (
        ("LoadPackage", 6),
        ("LoadObject", 5),
        ("StaticLoadObject", 7),
        ("StaticLoadClass", 7),
        ("AsyncPackage", 4),
        ("FLinkerLoad", 4),
        ("Package", 2),
        ("CoreUObject", 3),
    )
    for needle, points in needles:
        if needle in strings:
            score += points
            reasons.append(f"near-string:{needle}")
    if row.get("opcode") == "call":
        score += 2
        reasons.append("direct-call")
    else:
        reasons.append("direct-jump")
    row["score"] = score
    row["reasons"] = reasons
    return row


def summarize(args):
    ptrctx = import_script(POINTER_CONTEXT_SCRIPT, "summarize_elf_pointer_context_for_package_wrappers")
    data = args.binary.read_bytes()
    sections = ptrctx.load_sections(data)
    package_vtables = json.loads(args.package_loader_vtables_json.read_text(encoding="utf-8"))
    method_targets = collect_package_method_targets(
        package_vtables,
        args.limit_per_vtable,
        args.vtable_filter,
        args.slot,
    )
    target_values = {row["target"] for row in method_targets}
    target_by_value = {}
    for row in method_targets:
        target_by_value.setdefault(row["target"], []).append(row)

    executable = executable_sections(sections)
    callsites = []
    confirmed_calls = None if args.raw_scan else objdump_direct_calls(args.binary, target_values)
    if confirmed_calls:
        for opcode, source, target in confirmed_calls:
            section = next((item for item in executable if item.addr <= source < item.addr + item.size), None)
            raw = section_bytes(data, section) if section else b""
            offset = source - section.addr if section else 0
            for method in target_by_value[target]:
                callsites.append(
                    rank_callsite(
                        {
                            "source": f"0x{source:x}",
                            "target": f"0x{target:x}",
                            "opcode": opcode,
                            "section": section.name if section else "",
                            "vtable": method.get("vtable", ""),
                            "slot": method.get("slot"),
                            "nearbyStrings": nearby_ascii(raw, offset, args.near_bytes) if raw else [],
                            "confirmedBy": "objdump",
                        }
                    )
                )
    elif confirmed_calls is None:
        for section in executable:
            raw = section_bytes(data, section)
            for opcode, source, target in call_targets_in_section(section, raw):
                if target not in target_values:
                    continue
                offset = source - section.addr
                for method in target_by_value[target]:
                    callsites.append(
                        rank_callsite(
                            {
                                "source": f"0x{source:x}",
                                "target": f"0x{target:x}",
                                "opcode": "call" if opcode == 0xE8 else "jmp",
                                "section": section.name,
                                "vtable": method.get("vtable", ""),
                                "slot": method.get("slot"),
                                "nearbyStrings": nearby_ascii(raw, offset, args.near_bytes),
                                "confirmedBy": "raw-rel32",
                            }
                        )
                    )
    callsites.sort(key=lambda row: (-row["score"], row["source"], row["target"]))
    targets_with_calls = sorted({row["target"] for row in callsites})
    calls_by_target = {}
    for row in callsites:
        target = row["target"]
        entry = calls_by_target.setdefault(
            target,
            {
                "target": target,
                "directCallsiteCount": 0,
                "bestScore": row["score"],
                "bestSource": row["source"],
                "vtable": row.get("vtable", ""),
                "slot": row.get("slot"),
            },
        )
        entry["directCallsiteCount"] += 1
        if row["score"] > entry["bestScore"]:
            entry["bestScore"] = row["score"]
            entry["bestSource"] = row["source"]
    target_ranked = sorted(
        calls_by_target.values(),
        key=lambda row: (-row["bestScore"], -row["directCallsiteCount"], row["target"]),
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "binary": str(args.binary),
        "packageLoaderVTables": str(args.package_loader_vtables_json),
        "vtableFilters": args.vtable_filter,
        "slotFilters": args.slot,
        "methodTargetCount": len(method_targets),
        "targetsWithDirectCalls": len(targets_with_calls),
        "directCallsiteCount": len(callsites),
        "callsiteConfirmation": "raw-rel32" if confirmed_calls is None else "objdump",
        "targetRanked": target_ranked[: args.limit],
        "callsiteRanked": callsites[: args.limit],
        "nonPromotableWithoutWrapperReason": (
            "vtable method targets require a receiver/context; promote only a proven wrapper/static package-loading ABI"
        ),
    }


def markdown(summary):
    lines = ["# ELF UE Package Wrapper Candidates", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Package-loader vtables: `{summary['packageLoaderVTables']}`")
    lines.append(f"- Method targets scanned: `{summary['methodTargetCount']}`")
    if summary.get("vtableFilters"):
        lines.append(f"- VTable filters: `{summary['vtableFilters']}`")
    if summary.get("slotFilters"):
        lines.append(f"- Slot filters: `{summary['slotFilters']}`")
    lines.append(f"- Targets with direct calls: `{summary['targetsWithDirectCalls']}`")
    lines.append(f"- Direct callsites: `{summary['directCallsiteCount']}`")
    lines.append(f"- Callsite confirmation: `{summary.get('callsiteConfirmation', 'unknown')}`")
    lines.append(f"- Non-promotable reason: `{summary['nonPromotableWithoutWrapperReason']}`")
    lines.append("")
    lines.append("## Ranked Targets")
    lines.append("")
    if not summary.get("targetRanked"):
        lines.append("- none")
    for row in summary.get("targetRanked", []):
        lines.append(
            f"- target=`{row['target']}` calls=`{row['directCallsiteCount']}` "
            f"bestScore=`{row['bestScore']}` bestSource=`{row['bestSource']}` "
            f"slot=`{row['slot']}` vtable=`{row['vtable']}`"
        )
    lines.append("")
    lines.append("## Ranked Callsites")
    lines.append("")
    if not summary["callsiteRanked"]:
        lines.append("- none")
    for row in summary["callsiteRanked"]:
        lines.append(
            f"- score=`{row['score']}` source=`{row['source']}` target=`{row['target']}` "
            f"opcode=`{row['opcode']}` slot=`{row['slot']}` vtable=`{row['vtable']}` "
            f"confirmedBy=`{row.get('confirmedBy', 'unknown')}` reasons=`{', '.join(row['reasons']) or 'none'}`"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find direct caller/wrapper candidates around UE package-loader vtable methods."
    )
    parser.add_argument("binary", type=Path)
    parser.add_argument("--package-loader-vtables-json", type=Path, required=True)
    parser.add_argument("--vtable-filter", action="append", default=[])
    parser.add_argument("--slot", action="append", default=[])
    parser.add_argument("--limit-per-vtable", type=int, default=48)
    parser.add_argument("--near-bytes", type=int, default=DEFAULT_NEAR_BYTES)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument(
        "--raw-scan",
        action="store_true",
        help="use raw rel32 byte scanning instead of objdump-confirmed instruction decoding",
    )
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
