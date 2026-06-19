#!/usr/bin/env python3
import argparse
import importlib.util
import json
import string
import sys
from pathlib import Path


PRINTABLE = set(bytes(string.printable, "ascii")) - {0x0b, 0x0c}


def import_script(script_name, module_name):
    script = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(module_name, script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def containing_c_string(data, offset, limit):
    start = offset
    floor = max(0, offset - limit)
    while start > floor and data[start - 1] not in (0, 10, 13):
        start -= 1
    end = offset
    ceiling = min(len(data), offset + limit)
    while end < ceiling and data[end] not in (0, 10, 13):
        end += 1
    raw = data[start:end]
    if not raw or any(byte not in PRINTABLE for byte in raw):
        return None
    text = raw.decode("ascii", errors="replace")
    if len(text.strip()) < 3:
        return None
    return {"offset": start, "text": text}


def iter_ascii_strings(data, start, end, min_length):
    cursor = start
    current = bytearray()
    current_start = None
    while cursor < end:
        byte = data[cursor]
        if byte in PRINTABLE and byte not in (0, 9, 10, 13):
            if current_start is None:
                current_start = cursor
            current.append(byte)
        else:
            if current_start is not None and len(current) >= min_length:
                yield current_start, current.decode("ascii", errors="replace")
            current = bytearray()
            current_start = None
        cursor += 1
    if current_start is not None and len(current) >= min_length:
        yield current_start, current.decode("ascii", errors="replace")


def nearby_strings(data, offset, window, min_length, limit):
    start = max(0, offset - window)
    end = min(len(data), offset + window)
    rows = []
    seen = set()
    containing = containing_c_string(data, offset, window)
    if containing:
        rows.append(containing)
        seen.add((containing["offset"], containing["text"]))
    for string_offset, text in iter_ascii_strings(data, start, end, min_length):
        key = (string_offset, text)
        if key in seen:
            continue
        rows.append({"offset": string_offset, "text": text})
        seen.add(key)
    rows.sort(key=lambda row: (abs(row["offset"] - offset), row["offset"]))
    return rows[:limit]


def summarize(binary, loader_log, exe_substring, pid, categories, names, window, min_length, limit, include_xrefs):
    xref_mod = import_script("summarize-linux-loader-xrefs.py", "summarize_linux_loader_xrefs")
    data, segments = xref_mod.load_elf_segments(binary)
    targets = xref_mod.targets_from_log(loader_log, segments, exe_substring, pid, categories, names)
    xrefs = xref_mod.scan_xrefs(data, segments, targets) if include_xrefs else {}

    rows = []
    for target in targets:
        refs = xrefs.get(target, [])
        rows.append(
            {
                "name": target.name,
                "category": target.category,
                "kind": target.kind,
                "fileOffset": f"0x{target.file_offset:x}",
                "imageOffset": f"0x{target.image_offset:x}",
                "vaddr": f"0x{target.vaddr:x}",
                "strings": [
                    {"offset": f"0x{row['offset']:x}", "text": row["text"]}
                    for row in nearby_strings(data, target.file_offset, window, min_length, limit)
                ],
                "xrefs": [
                    {
                        "kind": ref["kind"],
                        "xrefVaddr": f"0x{ref['xrefVaddr']:x}",
                        "bytes": ref["bytes"],
                    }
                    for ref in refs[:limit]
                ],
                "xrefCount": len(refs),
            }
        )
    return {"targetCount": len(targets), "targets": rows}


def markdown(summary):
    lines = ["# Linux Loader Anchor Context", ""]
    lines.append(f"- Targets: `{summary['targetCount']}`")
    lines.append("")
    current_category = None
    for row in sorted(summary["targets"], key=lambda item: (item["category"], item["name"], item["fileOffset"])):
        if row["category"] != current_category:
            current_category = row["category"]
            lines.append(f"## {current_category}")
            lines.append("")
        lines.append(
            f"- `{row['name']}` file=`{row['fileOffset']}` image=`{row['imageOffset']}` "
            f"xrefs=`{row['xrefCount']}`"
        )
        if row["xrefs"]:
            xrefs = ", ".join(ref["xrefVaddr"] for ref in row["xrefs"])
            lines.append(f"  - xrefs: `{xrefs}`")
        if row["strings"]:
            context = "; ".join(f"{item['offset']} {item['text']!r}" for item in row["strings"])
            lines.append(f"  - strings: {context}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize nearby strings and simple xrefs for loader anchors.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("--loader-log", type=Path, required=True)
    parser.add_argument("--exe-substring", default="DuneSandboxServer")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--window", type=int, default=512)
    parser.add_argument("--min-length", type=int, default=5)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--no-xrefs", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    summary = summarize(
        args.binary,
        args.loader_log,
        args.exe_substring,
        args.pid,
        args.category,
        args.name,
        args.window,
        args.min_length,
        args.limit,
        not args.no_xrefs,
    )
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))


if __name__ == "__main__":
    main()
