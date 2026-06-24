#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "dune-root-candidate-focused-offsets/v1"


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
        except (TypeError, ValueError):
            continue
    return rows


def candidate_target(row):
    try:
        return parse_int(row.get("target"))
    except (TypeError, ValueError):
        return None


def sample_rank(sample):
    kind = sample.get("kind", "")
    kind_score = {"write": 0, "read": 1, "compare": 2, "other": 3, "address": 4}.get(kind, 5)
    try:
        offset = parse_int(sample.get("instruction"))
    except (TypeError, ValueError):
        offset = 0
    return kind_score, offset


def selected_samples(shape, limit):
    samples = [sample for sample in (shape.get("samples") or []) if sample.get("instruction")]
    samples.sort(key=sample_rank)
    return samples[:limit]


def summarize(candidates_report, shape_report, args):
    shapes = shape_by_target(shape_report)
    rows = []
    offsets = []
    for candidate in candidates_report.get("candidates", []) or []:
        if args.only_promotable and not candidate.get("promotable"):
            continue
        target = candidate_target(candidate)
        if target is None:
            continue
        shape = shapes.get(target)
        if not shape:
            continue
        samples = selected_samples(shape, args.samples_per_candidate)
        if not samples:
            continue
        item_offsets = []
        for sample in samples:
            try:
                instruction = parse_int(sample.get("instruction"))
            except (TypeError, ValueError):
                continue
            text = f"0x{instruction:x}"
            item_offsets.append(text)
            if text not in offsets:
                offsets.append(text)
        if not item_offsets:
            continue
        rows.append(
            {
                "target": f"0x{target:x}",
                "evidenceKind": candidate.get("evidenceKind", ""),
                "rootGroups": candidate.get("rootGroups", []),
                "promotable": bool(candidate.get("promotable")),
                "shape": {
                    "refCount": shape.get("refCount", 0),
                    "qwordRefCount": shape.get("qwordRefCount", 0),
                    "functionBucketCount": shape.get("functionBucketCount", 0),
                    "addressRatio": shape.get("addressRatio", 0),
                    "kindCounts": shape.get("kindCounts", {}),
                },
                "offsets": item_offsets,
                "samples": samples,
            }
        )
        if len(rows) >= args.limit:
            break
    return {
        "schemaVersion": SCHEMA_VERSION,
        "candidateCount": len(rows),
        "offsetCount": len(offsets),
        "offsetsCsv": ",".join(offsets),
        "selection": {
            "limit": args.limit,
            "samplesPerCandidate": args.samples_per_candidate,
            "onlyPromotable": args.only_promotable,
        },
        "candidates": rows,
    }


def markdown(report):
    lines = [
        "# Root Candidate Focused Offsets",
        "",
        f"- Schema: `{report['schemaVersion']}`",
        f"- Candidates: `{report['candidateCount']}`",
        f"- Offsets: `{report['offsetCount']}`",
        "",
        "## Ghidra",
        "",
        "```bash",
        f"DUNE_GHIDRA_OFFSETS='{report['offsetsCsv']}' \\",
        "  scripts/research/run-ghidra-headless.sh --script DumpFocusedFunctions.java --mode process --analysis off",
        "```",
        "",
        "## Candidates",
        "",
    ]
    if not report["candidates"]:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for row in report["candidates"]:
        shape = row["shape"]
        lines.append(
            f"- `{row['target']}` groups=`{','.join(row['rootGroups'])}` kind=`{row['evidenceKind']}` "
            f"promotable=`{str(row['promotable']).lower()}` refs=`{shape.get('refCount')}` "
            f"qword=`{shape.get('qwordRefCount')}` addressRatio=`{shape.get('addressRatio')}` "
            f"offsets=`{','.join(row['offsets'])}`"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export Ghidra focused-function offsets for ranked writable root candidates."
    )
    parser.add_argument("root_candidates_json", type=Path)
    parser.add_argument("writable_root_shapes_json", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--samples-per-candidate", type=int, default=3)
    parser.add_argument("--all-candidates", action="store_false", dest="only_promotable")
    parser.set_defaults(only_promotable=True)
    parser.add_argument("--format", choices=("json", "markdown", "csv"), default="json")
    args = parser.parse_args(argv)
    report = summarize(load_json(args.root_candidates_json), load_json(args.writable_root_shapes_json), args)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(markdown(report), end="")
    else:
        print(report["offsetsCsv"])


if __name__ == "__main__":
    raise SystemExit(main())
