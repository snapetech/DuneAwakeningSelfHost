#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def parse_int(value, default=None):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def target_values(row):
    values = []
    for target in row.get("candidateTargets", []):
        value = parse_int(target.get("target", ""))
        if value is not None:
            values.append(value)
    return sorted(set(values))


def source_family(row):
    source = row.get("sourceName", "")
    if "[" in source:
        return source.split("[", 1)[0]
    return source or "unknown"


def ranges_overlap_or_touch(left, right, gap):
    return left["minTarget"] <= right["maxTarget"] + gap and right["minTarget"] <= left["maxTarget"] + gap


def make_cluster(rows):
    targets = sorted({value for row in rows for value in row["targetValues"]})
    sections = Counter()
    for row in rows:
        sections.update(row.get("sectionCounts", {}))
    return {
        "functionCount": len(rows),
        "functions": [row["function"] for row in rows],
        "fileOffsets": [row["fileOffset"] for row in rows],
        "sourceFamilies": dict(sorted(Counter(row["sourceFamily"] for row in rows).items())),
        "sourceNames": [row["sourceName"] for row in rows[:12]],
        "minTarget": f"0x{targets[0]:x}" if targets else "",
        "maxTarget": f"0x{targets[-1]:x}" if targets else "",
        "targetCount": len(targets),
        "sectionCounts": dict(sorted(sections.items())),
        "maxScore": max((row.get("score", 0) for row in rows), default=0),
        "totalUsableWritableRefs": sum(row.get("usableWritableRefCount", 0) for row in rows),
        "totalWriteLikeRefs": sum(row.get("writeLikeRefCount", 0) for row in rows),
        "sampleTargets": [f"0x{value:x}" for value in targets[:16]],
        "sampleSignatures": [
            {
                "function": row["function"],
                "fileOffset": row["fileOffset"],
                "sha256": (row.get("signature") or {}).get("sha256", ""),
                "length": (row.get("signature") or {}).get("length", ""),
            }
            for row in rows[:8]
            if (row.get("signature") or {}).get("sha256")
        ],
    }


def cluster_rows(rows, gap):
    normalized = []
    for row in rows:
        values = target_values(row)
        if not values:
            continue
        normalized.append(
            {
                **row,
                "targetValues": values,
                "minTarget": values[0],
                "maxTarget": values[-1],
                "sourceFamily": source_family(row),
            }
        )
    normalized.sort(key=lambda row: (row["sourceFamily"], row["minTarget"], row["function"]))
    clusters = []
    for row in normalized:
        if not clusters:
            clusters.append([row])
            continue
        current = clusters[-1]
        current_summary = {
            "minTarget": min(item["minTarget"] for item in current),
            "maxTarget": max(item["maxTarget"] for item in current),
        }
        if row["sourceFamily"] == current[-1]["sourceFamily"] and ranges_overlap_or_touch(current_summary, row, gap):
            current.append(row)
        else:
            clusters.append([row])
    return [make_cluster(cluster) for cluster in clusters]


def summarize(queue, gap, limit):
    clusters = cluster_rows(queue.get("rows", []), gap)
    clusters.sort(
        key=lambda row: (
            -row["functionCount"],
            -row["targetCount"],
            -row["maxScore"],
            row["minTarget"],
        )
    )
    clusters = clusters[:limit]
    return {
        "schemaVersion": "dune-ue-root-recovery-clusters/v1",
        "sourceQueue": queue.get("schemaVersion", ""),
        "binary": queue.get("binary", ""),
        "queuedFunctionCount": queue.get("queuedFunctionCount", 0),
        "clusterCount": len(clusters),
        "gap": gap,
        "clusters": clusters,
    }


def markdown(summary):
    lines = ["# UE Root Recovery Clusters", ""]
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Queued functions: `{summary['queuedFunctionCount']}`")
    lines.append(f"- Clusters: `{summary['clusterCount']}`")
    lines.append(f"- Gap: `{summary['gap']}`")
    lines.append("")
    if not summary["clusters"]:
        lines.append("- none")
        lines.append("")
        return "\n".join(lines)
    for cluster in summary["clusters"]:
        lines.append(
            f"- range=`{cluster['minTarget']}`..`{cluster['maxTarget']}` "
            f"functions=`{cluster['functionCount']}` targets=`{cluster['targetCount']}` "
            f"families=`{cluster['sourceFamilies']}` sections=`{cluster['sectionCounts']}` "
            f"maxScore=`{cluster['maxScore']}`"
        )
        if cluster["sampleTargets"]:
            lines.append(f"  - sample targets: `{', '.join(cluster['sampleTargets'])}`")
        for sig in cluster["sampleSignatures"][:4]:
            lines.append(
                f"  - signature function=`{sig['function']}` file=`{sig['fileOffset']}` "
                f"length=`{sig['length']}` sha256=`{sig['sha256']}`"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cluster queued UE root-recovery functions by writable target range.")
    parser.add_argument("root_recovery_queue_json", type=Path)
    parser.add_argument("--gap", type=lambda value: int(value, 0), default=0x100)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    summary = summarize(load_json(args.root_recovery_queue_json), args.gap, args.limit)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
