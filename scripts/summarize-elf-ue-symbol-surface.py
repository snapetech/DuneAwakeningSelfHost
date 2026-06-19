#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from elftools.elf.elffile import ELFFile


ANCHOR_GROUPS = {
    "names": ("FNamePool", "GName", "GNames", "FName::", "FName "),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "UWorld::", "UWorld "),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject::", "UFunction::", "UClass::", "FProperty::", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct::", "UEnum::"),
}
FALSE_POSITIVE_PREFIXES = (
    "icu_",
    "icu::",
    "icu_64::",
    "SDL_",
)
FALSE_POSITIVE_CONTAINS = (
    "GNameSearchHandler",
    "icu_64::UObject",
    "SDL_LoadObject",
)


def demangle(names):
    if not names:
        return {}
    try:
        proc = subprocess.run(
            ["c++filt"],
            input="\n".join(names) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {name: name for name in names}
    lines = proc.stdout.splitlines()
    return {name: lines[index] if index < len(lines) else name for index, name in enumerate(names)}


def iter_symbols(binary):
    with binary.open("rb") as handle:
        elf = ELFFile(handle)
        for section_name in (".dynsym", ".symtab"):
            section = elf.get_section_by_name(section_name)
            if section is None:
                continue
            for symbol in section.iter_symbols():
                name = symbol.name
                if not name:
                    continue
                entry = symbol.entry
                yield {
                    "section": section_name,
                    "name": name,
                    "value": int(entry["st_value"]),
                    "size": int(entry["st_size"]),
                    "bind": entry["st_info"]["bind"],
                    "type": entry["st_info"]["type"],
                    "visibility": entry["st_other"]["visibility"],
                    "shndx": str(entry["st_shndx"]),
                }


def symbol_groups(raw_name, demangled):
    haystacks = (raw_name, demangled)
    groups = []
    for group, needles in ANCHOR_GROUPS.items():
        if any(needle in haystack for haystack in haystacks for needle in needles):
            groups.append(group)
    return groups


def is_false_positive(raw_name, demangled):
    for value in (raw_name, demangled):
        if value.startswith(FALSE_POSITIVE_PREFIXES):
            return True
        if any(part in value for part in FALSE_POSITIVE_CONTAINS):
            return True
    return False


def classify_role(row):
    demangled = row["demangled"]
    raw = row["name"]
    symbol_type = row["type"]
    if raw.startswith("_ZTI") or demangled.startswith("typeinfo for "):
        return "rtti-typeinfo"
    if raw.startswith("_ZTV") or demangled.startswith("vtable for "):
        return "rtti-vtable"
    if raw.startswith("_ZTS") or demangled.startswith("typeinfo name for "):
        return "rtti-name"
    if symbol_type == "STT_FUNC" and "ProcessEvent" in demangled:
        return "process-event"
    if symbol_type == "STT_FUNC" and any(name in demangled for name in ("StaticFindObject", "CallFunctionByNameWithArguments")):
        return "dispatch-function"
    if symbol_type == "STT_FUNC" and any(name in demangled for name in ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName")):
        return "package-function"
    if any(name in demangled for name in ("GUObjectArray", "GObjectArray", "GWorld", "FNamePool", "GNames")):
        return "global-symbol"
    if symbol_type == "STT_FUNC":
        return "function"
    if symbol_type == "STT_OBJECT":
        return "object"
    return "other"


def summarize(binary):
    symbols = list(iter_symbols(binary))
    demangled = demangle([row["name"] for row in symbols])
    rows = []
    for row in symbols:
        row = dict(row)
        row["demangled"] = demangled.get(row["name"], row["name"])
        row["groups"] = symbol_groups(row["name"], row["demangled"])
        if not row["groups"]:
            continue
        row["falsePositive"] = is_false_positive(row["name"], row["demangled"])
        row["role"] = classify_role(row)
        rows.append(row)

    group_counts = Counter()
    role_counts = Counter()
    non_false_group_counts = Counter()
    exact_runtime_roles = defaultdict(list)
    for row in rows:
        role_counts[row["role"]] += 1
        for group in row["groups"]:
            group_counts[group] += 1
            if not row["falsePositive"]:
                non_false_group_counts[group] += 1
        if not row["falsePositive"] and row["role"] in (
            "process-event",
            "dispatch-function",
            "package-function",
            "global-symbol",
        ):
            exact_runtime_roles[row["role"]].append(row)

    return {
        "schemaVersion": "dune-elf-ue-symbol-surface/v1",
        "binary": str(binary),
        "symbolCount": len(symbols),
        "matchedCount": len(rows),
        "nonFalsePositiveMatchedCount": sum(1 for row in rows if not row["falsePositive"]),
        "groupCounts": dict(sorted(group_counts.items())),
        "nonFalsePositiveGroupCounts": dict(sorted(non_false_group_counts.items())),
        "roleCounts": dict(sorted(role_counts.items())),
        "exactRuntimeRoleCounts": {key: len(value) for key, value in sorted(exact_runtime_roles.items())},
        "hasProcessEventExport": bool(exact_runtime_roles.get("process-event")),
        "hasCoreGlobalExport": bool(exact_runtime_roles.get("global-symbol")),
        "hasPackageFunctionExport": bool(exact_runtime_roles.get("package-function")),
        "rows": rows,
    }


def markdown(summary, limit):
    lines = ["# ELF UE Symbol Surface", ""]
    lines.append(f"- Symbols scanned: `{summary['symbolCount']}`")
    lines.append(f"- Matched symbols: `{summary['matchedCount']}`")
    lines.append(f"- Non-false-positive matches: `{summary['nonFalsePositiveMatchedCount']}`")
    lines.append(f"- Has ProcessEvent export: `{str(summary['hasProcessEventExport']).lower()}`")
    lines.append(f"- Has core global export: `{str(summary['hasCoreGlobalExport']).lower()}`")
    lines.append(f"- Has package function export: `{str(summary['hasPackageFunctionExport']).lower()}`")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    for name, counts in (
        ("groups", summary["groupCounts"]),
        ("non-false-positive groups", summary["nonFalsePositiveGroupCounts"]),
        ("roles", summary["roleCounts"]),
        ("exact runtime roles", summary["exactRuntimeRoleCounts"]),
    ):
        lines.append(f"- {name}: `{counts}`")
    lines.append("")
    lines.append("## Runtime-Relevant Matches")
    lines.append("")
    runtime_rows = [
        row for row in summary["rows"]
        if not row["falsePositive"] and row["role"] in ("process-event", "dispatch-function", "package-function", "global-symbol")
    ]
    if not runtime_rows:
        lines.append("- none")
    for row in runtime_rows[:limit]:
        lines.append(
            f"- `{row['role']}` value=`0x{row['value']:x}` type=`{row['type']}` "
            f"bind=`{row['bind']}` groups=`{','.join(row['groups'])}` `{row['demangled']}`"
        )
    if len(runtime_rows) > limit:
        lines.append(f"- ... +{len(runtime_rows) - limit} more")
    lines.append("")
    lines.append("## Sample Matches")
    lines.append("")
    for row in summary["rows"][:limit]:
        fp = " false-positive" if row["falsePositive"] else ""
        lines.append(
            f"- `{row['role']}`{fp} value=`0x{row['value']:x}` type=`{row['type']}` "
            f"groups=`{','.join(row['groups'])}` `{row['demangled']}`"
        )
    if len(summary["rows"]) > limit:
        lines.append(f"- ... +{len(summary['rows']) - limit} more")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize UE-like dynamic/static symbol surfaces from an ELF image.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args(argv)

    summary = summarize(args.binary)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit))


if __name__ == "__main__":
    main()
