#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT_RELEVANT_SECTIONS = (".bss", ".data", ".data.rel.ro")


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
        if row.get("verdict") in {"rejected", "weak-false-positive"}:
            offset = parse_int(row.get("imageOffset", ""))
            if offset is not None:
                rejected.add(offset)
        for anchor in row.get("anchorTargets", []):
            offset = parse_int(anchor.get("imageOffset", ""))
            if offset is not None:
                rejected.add(offset)
        for pointer in row.get("pointerTargets", []):
            offset = parse_int(pointer.get("imageOffset", ""))
            if offset is not None:
                rejected.add(offset)
    return rejected


def is_writable_root_ref(ref):
    return ref.get("kind") == "rip-memory" and ref.get("section") in ROOT_RELEVANT_SECTIONS


def is_write_like(ref):
    text = ref.get("text", "")
    if text.startswith("movzx "):
        return False
    return text.startswith(("mov ", "movabs ", "vmov", "lea "))


def is_pointer_like_ref(ref):
    text = ref.get("text", "")
    if text.startswith("movzx ") or "byte ptr" in text:
        return False
    if "qword ptr" in text or text.startswith(("lea ", "movabs ")):
        return True
    symbols = ref.get("symbols", [])
    return bool(symbols or ref.get("string", ""))


def is_byte_guard_ref(ref):
    text = ref.get("text", "")
    return text.startswith("movzx ") and "byte ptr" in text


def is_constant_store_ref(ref):
    text = ref.get("text", "")
    return " ptr [rip " in text and "], 0x" in text


def target_offset(ref):
    return parse_int(ref.get("target", ""))


def summarize_targets(refs, rejected, limit):
    counts = Counter()
    pointer_counts = Counter()
    byte_guard_counts = Counter()
    constant_store_counts = Counter()
    samples = {}
    for ref in refs:
        target = target_offset(ref)
        if target is None or target in rejected:
            continue
        counts[target] += 1
        if is_pointer_like_ref(ref):
            pointer_counts[target] += 1
        if is_byte_guard_ref(ref):
            byte_guard_counts[target] += 1
        if is_constant_store_ref(ref):
            constant_store_counts[target] += 1
        samples.setdefault(
            target,
            {
                "target": f"0x{target:x}",
                "section": ref.get("section", ""),
                "firstInstruction": ref.get("instruction", ""),
                "firstText": ref.get("text", ""),
                "symbols": ref.get("symbols", []),
                "string": ref.get("string", ""),
            },
        )
    rows = []
    for target, count in counts.most_common(limit):
        row = dict(samples[target])
        row["refCount"] = count
        row["pointerLikeRefCount"] = pointer_counts[target]
        row["byteGuardRefCount"] = byte_guard_counts[target]
        row["constantStoreRefCount"] = constant_store_counts[target]
        rows.append(row)
    return rows


def target_span(refs):
    values = [target_offset(ref) for ref in refs]
    values = [value for value in values if value is not None]
    if not values:
        return 0
    return max(values) - min(values)


def score_function(row, rejected):
    refs = [ref for ref in row.get("refs", []) if is_writable_root_ref(ref)]
    usable_refs = [ref for ref in refs if target_offset(ref) not in rejected]
    write_refs = [ref for ref in usable_refs if is_write_like(ref)]
    pointer_refs = [ref for ref in usable_refs if is_pointer_like_ref(ref)]
    section_counts = Counter(ref.get("section", "") for ref in usable_refs)
    span = target_span(usable_refs)
    constructor_bonus = 25 if row.get("sourceRole") == "constructor" else 0
    call_bonus = min(int(row.get("callCount", 0)), 20)
    group_bonus = 100 * len(row.get("requiredGroupCoverage", []))
    unique_target_bonus = 2 * len({target_offset(ref) for ref in usable_refs if target_offset(ref) is not None})
    span_penalty = min(span // 0x10000, 120)
    shared_table_penalty = 40 if any(target_offset(ref) == 0x1642A908 for ref in usable_refs) else 0
    score = (
        group_bonus
        + constructor_bonus
        + call_bonus
        + len(usable_refs)
        + 2 * len(write_refs)
        + 4 * len(pointer_refs)
        + unique_target_bonus
        + 5 * section_counts.get(".bss", 0)
        - span_penalty
        - shared_table_penalty
    )
    return score, refs, usable_refs, write_refs, pointer_refs, dict(sorted(section_counts.items())), span


def summarize(function_neighborhoods, outcomes, limit, target_limit):
    rejected = rejected_offsets(outcomes) if outcomes else set()
    rows = []
    for row in function_neighborhoods.get("functions", []):
        score, refs, usable_refs, write_refs, pointer_refs, section_counts, span = score_function(row, rejected)
        if not usable_refs:
            continue
        rows.append(
            {
                "function": row.get("function", ""),
                "fileOffset": row.get("fileOffset", ""),
                "score": score,
                "sourceName": row.get("sourceName", ""),
                "sourceRole": row.get("sourceRole", ""),
                "sourceSlot": row.get("sourceSlot", ""),
                "requiredGroupCoverage": row.get("requiredGroupCoverage", []),
                "groupCounts": row.get("groupCounts", {}),
                "callCount": row.get("callCount", 0),
                "writableRefCount": len(refs),
                "usableWritableRefCount": len(usable_refs),
                "writeLikeRefCount": len(write_refs),
                "pointerLikeRefCount": len(pointer_refs),
                "sectionCounts": section_counts,
                "targetSpan": span,
                "signature": row.get("signature", {}),
                "candidateTargets": summarize_targets(usable_refs, rejected, target_limit),
            }
        )
    rows.sort(
        key=lambda row: (
            -row["score"],
            -row["usableWritableRefCount"],
            -row["writeLikeRefCount"],
            row["function"],
        )
    )
    rows = rows[:limit]
    return {
        "schemaVersion": "dune-ue-root-recovery-queue/v1",
        "binary": function_neighborhoods.get("binary", ""),
        "sourceFunctionNeighborhoods": function_neighborhoods.get("schemaVersion", ""),
        "rejectedOffsetCount": len(rejected),
        "functionCount": len(function_neighborhoods.get("functions", [])),
        "queuedFunctionCount": len(rows),
        "rows": rows,
    }


def markdown(summary):
    lines = ["# UE Root Recovery Queue", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Functions analyzed: `{summary['functionCount']}`")
    lines.append(f"- Rejected offsets applied: `{summary['rejectedOffsetCount']}`")
    lines.append(f"- Queued functions: `{summary['queuedFunctionCount']}`")
    lines.append("")
    if not summary["rows"]:
        lines.append("- none")
        lines.append("")
        return "\n".join(lines)
    for row in summary["rows"]:
        sig = row.get("signature") or {}
        lines.append(
            f"- function=`{row['function']}` file=`{row['fileOffset']}` score=`{row['score']}` "
            f"source=`{row['sourceName']}` role=`{row['sourceRole']}` "
            f"usableWritableRefs=`{row['usableWritableRefCount']}` writeLikeRefs=`{row['writeLikeRefCount']}` "
            f"pointerLikeRefs=`{row.get('pointerLikeRefCount', 0)}` "
            f"span=`0x{row['targetSpan']:x}` sections=`{row['sectionCounts']}`"
        )
        if sig.get("sha256"):
            lines.append(
                f"  - signature file=`{sig.get('fileOffset', '')}` length=`{sig.get('length', '')}` "
                f"sha256=`{sig.get('sha256', '')}`"
            )
        for target in row["candidateTargets"]:
            detail = " | ".join(target.get("symbols", [])) or target.get("string", "")
            suffix = f" detail=`{detail}`" if detail else ""
            lines.append(
                f"  - target=`{target['target']}` section=`{target['section']}` refs=`{target['refCount']}` "
                f"pointerLikeRefs=`{target.get('pointerLikeRefCount', 0)}` "
                f"first=`{target['firstInstruction']}` `{target['firstText']}`{suffix}"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Rank static UE root-recovery functions after live candidate false-positive rejection."
    )
    parser.add_argument("function_neighborhoods_json", type=Path)
    parser.add_argument("--candidate-outcomes-json", type=Path)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--target-limit", type=int, default=8)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    function_neighborhoods = load_json(args.function_neighborhoods_json)
    outcomes = load_json(args.candidate_outcomes_json) if args.candidate_outcomes_json else {}
    summary = summarize(function_neighborhoods, outcomes, args.limit, args.target_limit)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
