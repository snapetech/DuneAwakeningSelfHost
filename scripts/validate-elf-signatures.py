#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PatternSpec:
    name: str
    pattern: str
    bytes_: bytes
    mask: bytes
    expected_file_offset: Optional[int]
    category: str
    source: str
    xref_vaddr: str
    target_vaddr: str


def import_xrefs():
    script = Path(__file__).resolve().parent / "summarize-linux-loader-xrefs.py"
    spec = importlib.util.spec_from_file_location("summarize_linux_loader_xrefs", script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def parse_int(value):
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    return int(value, 16 if value.lower().startswith("0x") else 10)


def format_hex(value):
    if value is None:
        return ""
    return f"0x{value:x}"


def parse_pattern(pattern):
    values = []
    mask = []
    for token in pattern.replace(",", " ").split():
        token = token.strip()
        if not token:
            continue
        if token in ("?", "??"):
            values.append(0)
            mask.append(0)
            continue
        if len(token) != 2:
            raise ValueError(f"invalid pattern token {token!r}")
        try:
            values.append(int(token, 16))
        except ValueError as exc:
            raise ValueError(f"invalid hex token {token!r}") from exc
        mask.append(1)
    if not values:
        raise ValueError("empty pattern")
    return bytes(values), bytes(mask)


def normalized_pattern(values, mask):
    return " ".join("??" if not fixed else f"{value:02x}" for value, fixed in zip(values, mask))


def pattern_from_assignment(raw, category="manual", source="manual"):
    if "=" in raw:
        name, pattern = raw.split("=", 1)
        name = name.strip()
    else:
        name = "manual"
        pattern = raw
    values, mask = parse_pattern(pattern)
    return PatternSpec(
        name=name or "manual",
        pattern=normalized_pattern(values, mask),
        bytes_=values,
        mask=mask,
        expected_file_offset=None,
        category=category,
        source=source,
        xref_vaddr="",
        target_vaddr="",
    )


def patterns_from_file(path):
    specs = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                specs.append(pattern_from_assignment(line, source=f"{path}:{line_number}"))
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
    return specs


def patterns_from_manifest(path, categories, names, max_seeds, ignore_expected_offsets=False):
    category_filter = set(categories or [])
    name_filter = set(names or [])
    specs = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        manifest = json.load(handle)
    for entry in manifest.get("entries", []):
        category = entry.get("category", "")
        name = entry.get("name", "")
        if category_filter and category not in category_filter:
            continue
        if name_filter and name not in name_filter and entry.get("id", "") not in name_filter:
            continue
        pattern = entry.get("pattern", "")
        if not pattern:
            continue
        values, mask = parse_pattern(pattern)
        expected = None if ignore_expected_offsets else parse_int(entry.get("expectedFileOffset"))
        specs.append(
            PatternSpec(
                name=entry.get("id") or name or f"manifest-entry-{len(specs) + 1}",
                pattern=normalized_pattern(values, mask),
                bytes_=values,
                mask=mask,
                expected_file_offset=expected,
                category=category or "manifest",
                source=str(path),
                xref_vaddr=entry.get("xrefVaddr", ""),
                target_vaddr=entry.get("targetVaddr", ""),
            )
        )
        if max_seeds and len(specs) >= max_seeds:
            break
    return specs


def patterns_from_xref_summary(summary, categories, names, max_seeds):
    category_filter = set(categories or [])
    name_filter = set(names or [])
    specs = []
    for target in summary.get("targets", []):
        category = target.get("category", "")
        name = target.get("name", "")
        if category_filter and category not in category_filter:
            continue
        if name_filter and name not in name_filter:
            continue
        target_vaddr = target.get("vaddr", "")
        for index, ref in enumerate(target.get("xrefs", []), 1):
            seed = ref.get("signatureSeed") or {}
            pattern = seed.get("pattern", "")
            if not pattern:
                continue
            values, mask = parse_pattern(pattern)
            expected = parse_int(seed.get("fileOffset"))
            specs.append(
                PatternSpec(
                    name=f"{name}@{target_vaddr}#{index}" if target_vaddr else f"{name}#{index}",
                    pattern=normalized_pattern(values, mask),
                    bytes_=values,
                    mask=mask,
                    expected_file_offset=expected,
                    category=category,
                    source=target.get("source", ""),
                    xref_vaddr=ref.get("xrefVaddr", ""),
                    target_vaddr=ref.get("targetVaddr", ""),
                )
            )
            if max_seeds and len(specs) >= max_seeds:
                return specs
    return specs


def xref_summary_from_log(binary, loader_log, exe_substring, pid, categories, names, prefix, suffix):
    xrefs = import_xrefs()
    binary_data, segments = xrefs.load_elf_segments(binary)
    targets = xrefs.targets_from_log(loader_log, segments, exe_substring, pid, categories, names)
    found = xrefs.scan_xrefs(binary_data, segments, targets)
    return binary_data, segments, xrefs.serializable(binary_data, segments, targets, found, prefix, suffix)


def xref_summary_from_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def best_anchor(values, mask):
    best_offset = None
    best_value = b""
    cursor = 0
    while cursor < len(values):
        while cursor < len(values) and not mask[cursor]:
            cursor += 1
        start = cursor
        while cursor < len(values) and mask[cursor]:
            cursor += 1
        if cursor > start and cursor - start > len(best_value):
            best_offset = start
            best_value = values[start:cursor]
    if best_offset is None:
        raise ValueError("pattern has no fixed bytes")
    return best_offset, best_value


def pattern_matches_at(data, offset, values, mask):
    if offset < 0 or offset + len(values) > len(data):
        return False
    for index, fixed in enumerate(mask):
        if fixed and data[offset + index] != values[index]:
            return False
    return True


def scan_ranges(segments, scope, data_len):
    if scope == "all":
        return [(0, data_len)]
    xrefs = import_xrefs()
    return [
        (segment.file_offset, min(data_len, segment.file_offset + segment.file_size))
        for segment in segments
        if segment.flags & xrefs.PF_X
    ]


def scan_pattern(data, values, mask, ranges, max_recorded):
    anchor_offset, anchor = best_anchor(values, mask)
    matches = []
    total = 0
    truncated = False
    for range_start, range_end in ranges:
        search_start = range_start
        while True:
            found = data.find(anchor, search_start, range_end)
            if found < 0:
                break
            candidate = found - anchor_offset
            search_start = found + 1
            if candidate < range_start or candidate + len(values) > range_end:
                continue
            if not pattern_matches_at(data, candidate, values, mask):
                continue
            total += 1
            if len(matches) < max_recorded:
                matches.append(candidate)
            elif not truncated:
                truncated = True
    return total, matches, truncated


def image_base(segments):
    if not segments:
        return 0
    return min(segment.vaddr for segment in segments)


def match_row(segments, base_vaddr, spec, match_offset):
    xrefs = import_xrefs()
    try:
        vaddr = xrefs.file_offset_to_vaddr(segments, match_offset)
        segment = xrefs.segment_for_file_offset(segments, match_offset)
        executable = bool(segment.flags & xrefs.PF_X)
        image_offset = vaddr - base_vaddr
    except ValueError:
        vaddr = None
        executable = False
        image_offset = None
    return {
        "fileOffset": format_hex(match_offset),
        "imageOffset": format_hex(image_offset),
        "vaddr": format_hex(vaddr),
        "executable": executable,
        "expected": spec.expected_file_offset == match_offset if spec.expected_file_offset is not None else False,
    }


def validate_patterns(binary_data, segments, specs, scope, max_matches):
    ranges = scan_ranges(segments, scope, len(binary_data))
    base_vaddr = image_base(segments)
    rows = []
    for spec in specs:
        total, matches, truncated = scan_pattern(binary_data, spec.bytes_, spec.mask, ranges, max_matches)
        unique = total == 1
        expected_seen = False
        if spec.expected_file_offset is not None:
            expected_in_scope = any(
                start <= spec.expected_file_offset and spec.expected_file_offset + len(spec.bytes_) <= end
                for start, end in ranges
            )
            expected_seen = expected_in_scope and pattern_matches_at(
                binary_data,
                spec.expected_file_offset,
                spec.bytes_,
                spec.mask,
            )
        expected_only = unique and expected_seen
        promotable = unique and (spec.expected_file_offset is None or expected_seen)
        if total == 0:
            status = "missing"
        elif expected_only:
            status = "unique-expected"
        elif unique:
            status = "unique-unexpected"
        elif expected_seen:
            status = "ambiguous-expected"
        else:
            status = "ambiguous"
        rows.append(
            {
                "name": spec.name,
                "category": spec.category,
                "source": spec.source,
                "xrefVaddr": spec.xref_vaddr,
                "targetVaddr": spec.target_vaddr,
                "pattern": spec.pattern,
                "length": len(spec.bytes_),
                "fixedBytes": sum(1 for value in spec.mask if value),
                "expectedFileOffset": format_hex(spec.expected_file_offset),
                "matchCount": total,
                "matchesTruncated": truncated,
                "status": status,
                "promotable": promotable,
                "matches": [match_row(segments, base_vaddr, spec, offset) for offset in matches],
            }
        )
    return rows


def summarize(segments, rows, scope):
    status_counts = {}
    category_counts = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
    return {
        "format": "elf64",
        "imageBase": format_hex(image_base(segments)),
        "scope": scope,
        "patternCount": len(rows),
        "promotableCount": sum(1 for row in rows if row["promotable"]),
        "statusCounts": dict(sorted(status_counts.items())),
        "categoryCounts": dict(sorted(category_counts.items())),
        "patterns": rows,
    }


def markdown(summary, limit, show_patterns):
    lines = []
    lines.append("# ELF Signature Validation")
    lines.append("")
    lines.append(f"- Format: `{summary['format']}`")
    lines.append(f"- Image base: `{summary['imageBase']}`")
    lines.append(f"- Scope: `{summary['scope']}`")
    lines.append(f"- Patterns: `{summary['patternCount']}`")
    lines.append(f"- Promotable: `{summary['promotableCount']}`")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    for status, count in summary["statusCounts"].items():
        lines.append(f"- `{status}`: `{count}`")
    if not summary["statusCounts"]:
        lines.append("- none")
    lines.append("")

    rows = sorted(summary["patterns"], key=lambda row: (not row["promotable"], row["category"], row["name"]))
    lines.append("## Patterns")
    lines.append("")
    for row in rows[:limit]:
        lines.append(
            f"- `{row['status']}` `{row['category']}` `{row['name']}` "
            f"matches=`{row['matchCount']}` expected=`{row['expectedFileOffset'] or 'none'}`"
        )
        for match in row["matches"][:3]:
            marker = " expected" if match["expected"] else ""
            lines.append(
                f"  - file=`{match['fileOffset']}` image=`{match['imageOffset']}` "
                f"vaddr=`{match['vaddr']}`{marker}"
            )
        if row["matchesTruncated"]:
            lines.append("  - matches truncated")
        if show_patterns:
            lines.append(f"  - pattern `{row['pattern']}`")
    if len(rows) > limit:
        lines.append(f"- ... +{len(rows) - limit} more")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate Linux ELF signature seed uniqueness.")
    parser.add_argument("binary", type=Path, help="DuneSandboxServer-Linux-Shipping or native ELF client binary")
    parser.add_argument("--loader-log", type=Path, help="build xref signature seeds from this Linux probe log")
    parser.add_argument("--xref-json", type=Path, help="load signature seeds from summarize-linux-loader-xrefs.py JSON")
    parser.add_argument("--manifest-json", type=Path, action="append", default=[], help="load signatures from exported manifest JSON")
    parser.add_argument(
        "--ignore-expected-offsets",
        action="store_true",
        help="when using --manifest-json, treat unique matches at moved offsets as promotable",
    )
    parser.add_argument("--exe-substring", default="DuneSandboxServer")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--pattern", action="append", default=[], help="manual NAME=HEX ?? pattern")
    parser.add_argument("--pattern-file", type=Path, action="append", default=[], help="one NAME=pattern per line")
    parser.add_argument("--signature-prefix", type=int, default=8)
    parser.add_argument("--signature-suffix", type=int, default=16)
    parser.add_argument("--scope", choices=("executable", "all"), default="executable")
    parser.add_argument("--max-seeds", type=int, default=0, help="maximum generated xref seeds to validate, 0 for all")
    parser.add_argument("--max-matches", type=int, default=16)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--show-patterns", action="store_true")
    args = parser.parse_args(argv)

    xrefs = import_xrefs()
    binary_data, segments = xrefs.load_elf_segments(args.binary)
    specs = []
    specs.extend(pattern_from_assignment(raw) for raw in args.pattern)
    for path in args.pattern_file:
        specs.extend(patterns_from_file(path))
    for path in args.manifest_json:
        specs.extend(patterns_from_manifest(path, args.category, args.name, args.max_seeds, args.ignore_expected_offsets))
    if args.xref_json:
        specs.extend(patterns_from_xref_summary(xref_summary_from_json(args.xref_json), args.category, args.name, args.max_seeds))
    if args.loader_log:
        binary_data, segments, xref_summary = xref_summary_from_log(
            args.binary,
            args.loader_log,
            args.exe_substring,
            args.pid,
            args.category,
            args.name,
            args.signature_prefix,
            args.signature_suffix,
        )
        specs.extend(patterns_from_xref_summary(xref_summary, [], [], args.max_seeds))

    if not specs:
        parser.error("provide --pattern, --pattern-file, --manifest-json, --xref-json, or --loader-log")

    rows = validate_patterns(binary_data, segments, specs, args.scope, args.max_matches)
    summary = summarize(segments, rows, args.scope)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit, args.show_patterns))


if __name__ == "__main__":
    main()
