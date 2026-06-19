#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP


ROOT = Path(__file__).resolve().parents[1]
CLIENT_XREF_CANDIDATES = (
    ROOT / "scripts" / "summarize-client-loader-xrefs.py",
    ROOT / "analysis" / "summarize-client-loader-xrefs.py",
    Path(__file__).resolve().with_name("summarize-client-loader-xrefs.py"),
)
IMAGE_SCN_MEM_WRITE = 0x80000000
WRITABLE_ROOT_SECTIONS = {".data", ".rdata", ".pdata"}


def existing_path(candidates):
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value, default=None):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def rejected_offsets(outcomes):
    rejected = set()
    for row in outcomes.get("candidates", []):
        if row.get("verdict") not in {"rejected", "weak-false-positive"}:
            continue
        parsed = parse_int(row.get("imageOffset", ""))
        if parsed is not None:
            rejected.add(parsed)
        for field in ("anchorTargets", "pointerTargets"):
            for target in row.get(field, []):
                parsed = parse_int(target.get("imageOffset", ""))
                if parsed is not None:
                    rejected.add(parsed)
    return rejected


def included_targets(args):
    return {
        parsed
        for raw in getattr(args, "include_target", []) or []
        for parsed in [parse_int(raw)]
        if parsed is not None
    }


def section_for_rva(pe, rva):
    for section in pe.sections:
        if section.contains_rva(rva):
            return section
    return None


def flags_text(section):
    if not section:
        return ""
    return "".join(
        flag
        for bit, flag in (
            (0x40000000, "R"),
            (IMAGE_SCN_MEM_WRITE, "W"),
            (0x20000000, "X"),
        )
        if section.characteristics & bit
    )


def disassemble_one(md, code, pos, image_base, section_rva):
    for insn in md.disasm(code[pos : pos + 16], image_base + section_rva + pos, count=1):
        return insn
    return None


def classify_instruction(insn):
    text = f"{insn.mnemonic} {insn.op_str}".strip()
    size = 0
    for operand in insn.operands:
        if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
            size = max(size, int(getattr(operand, "size", 0) or 0))
    if insn.mnemonic == "lea":
        return "address", size, text
    if "byte ptr" in text or text.startswith("movzx "):
        return "byte-guard", size, text
    if " ptr [rip " in text and "], 0x" in text:
        return "constant-store", size, text
    if insn.mnemonic.startswith(("mov", "vmov")) and " ptr [rip " in text:
        if text.split(",", 1)[0].endswith("]"):
            return "write", size, text
        return "read", size, text
    if insn.mnemonic.startswith(("cmp", "test")):
        return "compare", size, text
    return "other", size, text


def scan_writable_shapes(xrefs, pe, rejected):
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    rows = defaultdict(lambda: {"refs": [], "functionBuckets": Counter(), "kindCounts": Counter(), "sizeCounts": Counter()})
    for section in pe.sections:
        if not section.is_executable:
            continue
        code = pe.data[section.raw_pointer : section.raw_pointer + section.raw_size]
        for pos in xrefs.iter_candidate_positions(code):
            for ref in xrefs.decode_rip_memory_refs(code, pos, section.virtual_address):
                target = int(ref["targetRva"])
                if target in rejected:
                    continue
                target_section = section_for_rva(pe, target)
                if (
                    not target_section
                    or target_section.name not in WRITABLE_ROOT_SECTIONS
                    or not (target_section.characteristics & IMAGE_SCN_MEM_WRITE)
                ):
                    continue
                insn = disassemble_one(md, code, pos, pe.image_base, section.virtual_address)
                if insn is None:
                    continue
                kind, size, text = classify_instruction(insn)
                row = rows[target]
                row["target"] = target
                row["section"] = target_section.name
                row["flags"] = flags_text(target_section)
                row["functionBuckets"][int(ref["xrefRva"]) & ~0xFF] += 1
                row["kindCounts"][kind] += 1
                row["sizeCounts"][str(size)] += 1
                if len(row["refs"]) < 8:
                    row["refs"].append(
                        {
                            "instruction": f"0x{pe.image_base + int(ref['xrefRva']):x}",
                            "xrefRva": f"0x{int(ref['xrefRva']):x}",
                            "kind": kind,
                            "size": size,
                            "text": text,
                        }
                    )
    return rows


def score_row(row):
    kinds = row["kindCounts"]
    sizes = row["sizeCounts"]
    function_count = len(row["functionBuckets"])
    pointer_like = kinds.get("read", 0) + kinds.get("write", 0) + kinds.get("address", 0)
    qword_refs = sizes.get("8", 0)
    guard_penalty = kinds.get("byte-guard", 0) * 5 + kinds.get("constant-store", 0) * 8
    fanout_penalty = max(0, function_count - 24) * 2
    return pointer_like * 8 + qword_refs * 5 + function_count * 3 - guard_penalty - fanout_penalty


def summarize(args):
    xrefs = import_script(existing_path(CLIENT_XREF_CANDIDATES), "summarize_client_loader_xrefs_for_pe_writable_shapes")
    pe = xrefs.load_pe_image(args.binary)
    outcomes = load_json(args.candidate_outcomes_json) if args.candidate_outcomes_json else {}
    rejected = rejected_offsets(outcomes)
    forced_targets = included_targets(args)
    raw_rows = scan_writable_shapes(xrefs, pe, rejected)
    rows = []
    for target, row in raw_rows.items():
        forced_include = target in forced_targets
        kind_counts = dict(sorted(row["kindCounts"].items()))
        size_counts = dict(sorted(row["sizeCounts"].items(), key=lambda item: int(item[0])))
        ref_count = sum(row["kindCounts"].values())
        read_refs = int(kind_counts.get("read", 0) or 0)
        write_refs = int(kind_counts.get("write", 0) or 0)
        address_refs = int(kind_counts.get("address", 0) or 0)
        qword_refs = int(size_counts.get("8", 0) or 0)
        scalar_refs = sum(count for size, count in size_counts.items() if parse_int(size, 0) in {1, 2, 4})
        address_ratio = address_refs / ref_count if ref_count else 0.0
        function_count = len(row["functionBuckets"])
        if args.require_read_write and (read_refs == 0 or write_refs == 0) and not forced_include:
            continue
        if args.require_qword and qword_refs == 0 and not forced_include:
            continue
        if args.min_qword_refs and qword_refs < args.min_qword_refs and not forced_include:
            continue
        if args.max_scalar_ratio is not None and ref_count and scalar_refs / ref_count > args.max_scalar_ratio and not forced_include:
            continue
        if args.min_read_refs and read_refs < args.min_read_refs and not forced_include:
            continue
        if args.min_write_refs and write_refs < args.min_write_refs and not forced_include:
            continue
        if args.max_function_buckets and function_count > args.max_function_buckets and not forced_include:
            continue
        if args.max_address_ratio is not None and ref_count and address_refs / ref_count > args.max_address_ratio and not forced_include:
            continue
        score = score_row(row)
        if score < args.min_score and not forced_include:
            continue
        rows.append(
            {
                "target": f"0x{target:x}",
                "imageOffset": f"0x{target:x}",
                "section": row.get("section", ""),
                "flags": row.get("flags", ""),
                "score": score,
                "refCount": ref_count,
                "functionBucketCount": function_count,
                "kindCounts": kind_counts,
                "sizeCounts": size_counts,
                "qwordRefCount": qword_refs,
                "scalarRefCount": scalar_refs,
                "scalarRatio": round(scalar_refs / ref_count, 6) if ref_count else 0.0,
                "addressRatio": round(address_ratio, 6),
                "forcedInclude": forced_include,
                "samples": row["refs"],
            }
        )
    rows.sort(key=lambda row: (-int(row.get("forcedInclude", False)), -row["score"], -row["functionBucketCount"], row["target"]))
    rows = rows[: args.limit]
    return {
        "schemaVersion": "dune-pe-writable-root-shapes/v1",
        "binary": str(args.binary),
        "imageBase": f"0x{pe.image_base:x}",
        "rejectedOffsetCount": len(rejected),
        "scannedTargetCount": len(raw_rows),
        "reportedTargetCount": len(rows),
        "sectionCounts": dict(sorted(Counter(row["section"] for row in rows).items())),
        "rows": rows,
    }


def markdown(summary):
    lines = ["# PE Writable Root Shapes", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Image base: `{summary['imageBase']}`")
    lines.append(f"- Rejected offsets applied: `{summary['rejectedOffsetCount']}`")
    lines.append(f"- Scanned writable targets: `{summary['scannedTargetCount']}`")
    lines.append(f"- Reported targets: `{summary['reportedTargetCount']}`")
    lines.append(f"- Sections: `{summary['sectionCounts']}`")
    lines.append("")
    if not summary["rows"]:
        lines.append("- none")
    for row in summary["rows"]:
        lines.append(
            f"- target=`{row['target']}` section=`{row['section']}` score=`{row['score']}` "
            f"refs=`{row['refCount']}` functions=`{row['functionBucketCount']}` "
            f"qwordRefs=`{row.get('qwordRefCount', 0)}` scalarRatio=`{row.get('scalarRatio', 0.0)}` "
            f"addressRatio=`{row.get('addressRatio', 0.0)}` "
            f"forcedInclude=`{str(row.get('forcedInclude', False)).lower()}` "
            f"kinds=`{row['kindCounts']}` sizes=`{row['sizeCounts']}`"
        )
        for sample in row["samples"][:4]:
            lines.append(
                f"  - `{sample['instruction']}` rva=`{sample['xrefRva']}` "
                f"kind=`{sample['kind']}` size=`{sample['size']}` `{sample['text']}`"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify anonymous writable PE root candidates by RIP-relative access shape.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("--candidate-outcomes-json", type=Path)
    parser.add_argument("--min-score", type=int, default=80)
    parser.add_argument("--require-read-write", action="store_true")
    parser.add_argument("--require-qword", action="store_true")
    parser.add_argument("--min-qword-refs", type=int, default=0)
    parser.add_argument("--max-scalar-ratio", type=float)
    parser.add_argument("--min-read-refs", type=int, default=0)
    parser.add_argument("--min-write-refs", type=int, default=0)
    parser.add_argument("--max-function-buckets", type=int, default=0)
    parser.add_argument("--max-address-ratio", type=float)
    parser.add_argument(
        "--include-target",
        action="append",
        default=[],
        help="force a writable target RVA into the report even when filters or ranking would omit it",
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
