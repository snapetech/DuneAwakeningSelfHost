#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "dune-elf-exact-root-context-candidates/v1"
ROOT_CONTEXT_GROUPS = {"names", "objects", "world"}
ROOT_ANCHORS = {
    "FNamePool",
    "NamePoolData",
    "GName",
    "GNames",
    "GUObjectArray",
    "GObjectArray",
    "GObjects",
    "FUObjectArray",
    "GWorld",
    "GEngine",
}
ROOT_GROUPS = {
    "FNamePool": "names",
    "NamePoolData": "names",
    "GName": "names",
    "GNames": "names",
    "GUObjectArray": "objects",
    "GObjectArray": "objects",
    "GObjects": "objects",
    "FUObjectArray": "objects",
    "GWorld": "world",
    "GEngine": "world",
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def parse_int(value):
    return int(str(value), 0)


def shape_by_target(shape_report):
    rows = {}
    for row in shape_report.get("rows", []) or []:
        target = row.get("target") or row.get("imageOffset")
        if not target:
            continue
        try:
            rows[parse_int(target)] = row
        except ValueError:
            continue
    return rows


def root_exact_counts(row):
    counts = {}
    for anchor, count in (row.get("exactAnchorHintCounts") or {}).items():
        if anchor in ROOT_ANCHORS:
            counts[anchor] = int(count or 0)
    return counts


def root_context_rows(row):
    rows = []
    for context in row.get("context", []) or []:
        anchors = [anchor for anchor in context.get("exactAnchorHints", []) or [] if anchor in ROOT_ANCHORS]
        if not anchors:
            continue
        item = dict(context)
        item["rootExactAnchorHints"] = anchors
        rows.append(item)
    return rows


def root_group_counts(row):
    return {
        group: int(count or 0)
        for group, count in (row.get("groupCounts") or {}).items()
        if group in ROOT_CONTEXT_GROUPS
    }


def root_group_context_rows(row):
    rows = []
    for context in row.get("context", []) or []:
        groups = [group for group in context.get("groups", []) or [] if group in ROOT_CONTEXT_GROUPS]
        if not groups:
            continue
        item = dict(context)
        item["rootGroups"] = groups
        rows.append(item)
    return rows


def blocker_reasons(shape, args):
    if not shape:
        return ["missing writable-root shape row"]
    blockers = []
    kind_counts = shape.get("kindCounts") or {}
    address_ratio = float(shape.get("addressRatio", 0.0) or 0.0)
    qword_refs = int(shape.get("qwordRefCount", 0) or 0)
    read_refs = int(kind_counts.get("read", 0) or 0)
    write_refs = int(kind_counts.get("write", 0) or 0)
    function_buckets = int(shape.get("functionBucketCount", 0) or 0)
    if address_ratio > args.max_address_ratio:
        blockers.append(f"addressRatio {address_ratio:.6f} > {args.max_address_ratio:.6f}")
    if qword_refs < args.min_qword_refs:
        blockers.append(f"qwordRefCount {qword_refs} < {args.min_qword_refs}")
    if args.require_read and read_refs <= 0:
        blockers.append("missing read refs")
    if args.require_write and write_refs <= 0:
        blockers.append("missing write refs")
    if args.max_function_buckets and function_buckets > args.max_function_buckets:
        blockers.append(f"functionBucketCount {function_buckets} > {args.max_function_buckets}")
    return blockers


def candidate_score(row):
    shape = row.get("shape") or {}
    return (
        1000 if row.get("promotable") else 0,
        200 if row.get("evidenceKind") == "exact-root-context" else 0,
        50 * len(row.get("rootGroups") or []),
        5 * sum((row.get("rootExactAnchorHintCounts") or {}).values()),
        2 * sum((row.get("rootGroupContextCounts") or {}).values()),
        int(shape.get("qwordRefCount", 0) or 0),
        int(shape.get("readRefCount", 0) or 0),
        -int(shape.get("functionBucketCount", 0) or 0),
        -int(float(shape.get("addressRatio", 1.0) or 1.0) * 1000000),
    )


def summarize(global_refs, shape_report, args):
    shapes = shape_by_target(shape_report)
    candidates = []
    for row in global_refs.get("top", []) or []:
        counts = root_exact_counts(row)
        group_counts = root_group_counts(row)
        if not counts and (not args.include_group_context or not group_counts):
            continue
        try:
            target_value = parse_int(row.get("target"))
        except (TypeError, ValueError):
            continue
        shape = shapes.get(target_value)
        blockers = blocker_reasons(shape, args)
        groups = sorted({ROOT_GROUPS[anchor] for anchor in counts} | set(group_counts))
        evidence_kind = "exact-root-context" if counts else "root-group-context"
        candidate = {
            "target": f"0x{target_value:x}",
            "section": row.get("section", ""),
            "evidenceKind": evidence_kind,
            "rootExactAnchorHintCounts": counts,
            "rootGroupContextCounts": group_counts,
            "rootGroups": groups,
            "contextCount": len(root_context_rows(row)),
            "sampleContext": root_context_rows(row)[: args.context_limit],
            "groupContextCount": len(root_group_context_rows(row)),
            "sampleGroupContext": root_group_context_rows(row)[: args.context_limit],
            "shape": {},
            "promotable": not blockers,
            "blockers": blockers,
        }
        if shape:
            kind_counts = shape.get("kindCounts") or {}
            candidate["shape"] = {
                "score": shape.get("score", 0),
                "refCount": shape.get("refCount", 0),
                "qwordRefCount": shape.get("qwordRefCount", 0),
                "functionBucketCount": shape.get("functionBucketCount", 0),
                "addressRatio": shape.get("addressRatio", 0),
                "readRefCount": kind_counts.get("read", 0),
                "writeRefCount": kind_counts.get("write", 0),
                "kindCounts": kind_counts,
                "section": shape.get("section", ""),
            }
        candidates.append(candidate)
    candidates.sort(key=lambda row: (*[-value for value in candidate_score(row)], row["target"]))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "candidateCount": len(candidates),
        "exactCandidateCount": sum(1 for row in candidates if row["evidenceKind"] == "exact-root-context"),
        "groupContextCandidateCount": sum(1 for row in candidates if row["evidenceKind"] == "root-group-context"),
        "promotableCount": sum(1 for row in candidates if row["promotable"]),
        "rootGroupCounts": {
            group: sum(1 for row in candidates if group in row["rootGroups"])
            for group in ("names", "objects", "world")
        },
        "shapeGate": {
            "maxAddressRatio": args.max_address_ratio,
            "minQwordRefs": args.min_qword_refs,
            "requireRead": args.require_read,
            "requireWrite": args.require_write,
            "maxFunctionBuckets": args.max_function_buckets,
            "includeGroupContext": args.include_group_context,
        },
        "candidates": candidates[: args.limit],
    }


def markdown(report):
    lines = [
        "# Exact Root Context Candidates",
        "",
        f"- Schema: `{report['schemaVersion']}`",
        f"- Candidates: `{report['candidateCount']}`",
        f"- Exact candidates: `{report.get('exactCandidateCount', 0)}`",
        f"- Group-context candidates: `{report.get('groupContextCandidateCount', 0)}`",
        f"- Promotable: `{report['promotableCount']}`",
        f"- Root group counts: `{report['rootGroupCounts']}`",
        "",
        "## Candidates",
        "",
    ]
    if not report["candidates"]:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for row in report["candidates"]:
        shape = row.get("shape") or {}
        lines.append(
            f"- `{row['target']}` kind=`{row.get('evidenceKind', '')}` groups=`{','.join(row['rootGroups'])}` "
            f"exact=`{row['rootExactAnchorHintCounts']}` promotable=`{str(row['promotable']).lower()}` "
            f"addressRatio=`{shape.get('addressRatio', '')}` qwordRefs=`{shape.get('qwordRefCount', '')}` "
            f"read=`{shape.get('readRefCount', '')}` write=`{shape.get('writeRefCount', '')}` "
            f"functionBuckets=`{shape.get('functionBucketCount', '')}`"
        )
        if row.get("rootGroupContextCounts"):
            lines.append(f"  - group context: `{row['rootGroupContextCounts']}`")
        for blocker in row.get("blockers", []):
            lines.append(f"  - blocker: {blocker}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Classify exact root-context writable globals against root-shape promotion gates."
    )
    parser.add_argument("writable_global_refs_json", type=Path)
    parser.add_argument("writable_root_shapes_json", type=Path)
    parser.add_argument("--max-address-ratio", type=float, default=0.05)
    parser.add_argument("--min-qword-refs", type=int, default=1)
    parser.add_argument("--require-read", action="store_true", default=True)
    parser.add_argument("--no-require-read", action="store_false", dest="require_read")
    parser.add_argument("--require-write", action="store_true", default=False)
    parser.add_argument("--max-function-buckets", type=int, default=0)
    parser.add_argument("--context-limit", type=int, default=3)
    parser.add_argument("--include-group-context", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    report = summarize(load_json(args.writable_global_refs_json), load_json(args.writable_root_shapes_json), args)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(markdown(report), end="")


if __name__ == "__main__":
    raise SystemExit(main())
