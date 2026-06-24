#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ANCHOR_PRESETS = {
    "object-discovery": (
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
    ),
    "hook-planning": (
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
        "ProcessEvent",
        "StaticFindObject",
        "CallFunctionByNameWithArguments",
        "CallFunctionByName",
    ),
    "package-loading": (
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
        "StaticLoadObject",
        "LoadObject",
        "LoadPackage",
        "ResolveName",
        "LoadAsset",
        "LoadClass",
    ),
    "reflection": (
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
        "UObject",
        "UFunction",
        "UClass",
        "FProperty",
        "FObjectProperty",
        "FArrayProperty",
        "FBoolProperty",
        "FStructProperty",
        "UStruct",
        "UEnum",
    ),
}
ANCHOR_PRESETS["complete"] = tuple(
    dict.fromkeys(
        anchor
        for preset in ("hook-planning", "package-loading", "reflection")
        for anchor in ANCHOR_PRESETS[preset]
    )
)
DEFAULT_ANCHOR_PRESET = "object-discovery"
DEFAULT_ANCHORS = ANCHOR_PRESETS[DEFAULT_ANCHOR_PRESET]
ANCHOR_GROUPS = {
    "names": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
ANCHOR_TO_GROUP = {
    anchor: group
    for group, anchors in ANCHOR_GROUPS.items()
    for anchor in anchors
}
ENV_NAMES = {
    "server": "DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS",
    "linux-client": "DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
    "windows": "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
}


def parse_int(value, default=None):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def merge_outcomes(summaries):
    merged = {"candidates": []}
    for summary in summaries:
        if not summary:
            continue
        merged["candidates"].extend(summary.get("candidates", []) or [])
    return merged


def target_rows(queue):
    rows = []
    for row in queue.get("rows", []):
        source = row.get("sourceName", "")
        source_family = source.split("[", 1)[0] if "[" in source else source
        for target in row.get("candidateTargets", []):
            value = parse_int(target.get("target", ""))
            if value is None:
                continue
            rows.append(
                {
                    "target": value,
                    "targetText": f"0x{value:x}",
                    "sourceFunction": row.get("function", ""),
                    "sourceFileOffset": row.get("fileOffset", ""),
                    "sourceName": source,
                    "sourceFamily": source_family or "unknown",
                    "score": row.get("score", 0),
                    "targetSpan": row.get("targetSpan", 0),
                    "sourceGroupCoverage": list(row.get("requiredGroupCoverage", []) or []),
                    "sourceGroupCounts": dict(row.get("groupCounts", {}) or {}),
                    "section": target.get("section", ""),
                    "refCount": target.get("refCount", 0),
                    "pointerLikeRefCount": target.get("pointerLikeRefCount", 0),
                    "byteGuardRefCount": target.get("byteGuardRefCount", 0),
                    "constantStoreRefCount": target.get("constantStoreRefCount", 0),
                    "firstInstruction": target.get("firstInstruction", ""),
                    "firstText": target.get("firstText", ""),
                    "signature": row.get("signature", {}),
                }
            )
    return rows


def cluster_for_target(clusters, value):
    for index, cluster in enumerate(clusters.get("clusters", []), 1):
        minimum = parse_int(cluster.get("minTarget", ""))
        maximum = parse_int(cluster.get("maxTarget", ""))
        if minimum is not None and maximum is not None and minimum <= value <= maximum:
            return {
                "index": index,
                "minTarget": cluster.get("minTarget", ""),
                "maxTarget": cluster.get("maxTarget", ""),
                "functionCount": cluster.get("functionCount", 0),
                "targetCount": cluster.get("targetCount", 0),
                "sourceFamilies": cluster.get("sourceFamilies", {}),
            }
        if value in {parse_int(target) for target in cluster.get("sampleTargets", [])}:
            return {
                "index": index,
                "minTarget": cluster.get("minTarget", ""),
                "maxTarget": cluster.get("maxTarget", ""),
                "functionCount": cluster.get("functionCount", 0),
                "targetCount": cluster.get("targetCount", 0),
                "sourceFamilies": cluster.get("sourceFamilies", {}),
            }
    return {"index": 0, "minTarget": "", "maxTarget": "", "functionCount": 0, "targetCount": 0, "sourceFamilies": {}}


def rejected_pairs(outcomes):
    rejected = set()
    for candidate in outcomes.get("candidates", []):
        if candidate.get("verdict") not in {"rejected", "weak-false-positive"}:
            continue
        name = candidate.get("name", "")
        if candidate.get("runtimeRwFileOffset") != "true":
            offset = parse_int(candidate.get("imageOffset", ""))
            if name and offset is not None:
                rejected.add((name, offset))
        for anchor in candidate.get("anchorTargets", []):
            offset = parse_int(anchor.get("imageOffset", ""))
            if name and offset is not None:
                rejected.add((name, offset))
    return rejected


def rejected_offsets(outcomes):
    rejected = set()
    for candidate in outcomes.get("candidates", []):
        if candidate.get("verdict") not in {"rejected", "weak-false-positive"}:
            continue
        if candidate.get("runtimeRwFileOffset") != "true":
            offset = parse_int(candidate.get("imageOffset", ""))
            if offset is not None:
                rejected.add(offset)
        for field in ("anchorTargets", "pointerTargets"):
            for target in candidate.get(field, []):
                offset = parse_int(target.get("imageOffset", ""))
                if offset is not None:
                    rejected.add(offset)
    return rejected


def cluster_index_for_target(clusters, value):
    return cluster_for_target(clusters, value).get("index", 0)


def rejected_cluster_indexes(clusters, rejected):
    return {
        cluster_index_for_target(clusters, offset)
        for offset in rejected
        if cluster_index_for_target(clusters, offset)
    }


def near_rejected(value, rejected, gap):
    return bool(gap and any(abs(value - offset) <= gap for offset in rejected))


def select_rows(
    rows,
    clusters,
    anchors,
    rejected,
    rejected_global_offsets,
    max_total,
    max_per_anchor,
    max_per_cluster,
    min_gap,
    reject_near_gap,
    suppress_rejected_clusters,
    min_pointer_like_refs,
    max_byte_guard_refs,
    max_constant_store_refs,
    require_source_group_match,
):
    selected = []
    seen_targets_by_anchor = {anchor: [] for anchor in anchors}
    counts_by_anchor = Counter()
    counts_by_cluster_anchor = Counter()
    suppressed_clusters = rejected_cluster_indexes(clusters, rejected_global_offsets) if suppress_rejected_clusters else set()
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -int(row.get("score", 0)),
            -int(row.get("refCount", 0)),
            row["target"],
        ),
    )
    for row in sorted_rows:
        cluster = cluster_for_target(clusters, row["target"])
        if cluster["index"] in suppressed_clusters:
            continue
        if near_rejected(row["target"], rejected_global_offsets, reject_near_gap):
            continue
        if min_pointer_like_refs and int(row.get("pointerLikeRefCount", 0) or 0) < min_pointer_like_refs:
            continue
        if max_byte_guard_refs is not None and int(row.get("byteGuardRefCount", 0) or 0) > max_byte_guard_refs:
            continue
        if (
            max_constant_store_refs is not None
            and int(row.get("constantStoreRefCount", 0) or 0) > max_constant_store_refs
        ):
            continue
        for anchor in anchors:
            anchor_group = ANCHOR_TO_GROUP.get(anchor, "")
            source_group_coverage = set(row.get("sourceGroupCoverage", []) or [])
            if require_source_group_match and anchor_group and anchor_group not in source_group_coverage:
                continue
            if (anchor, row["target"]) in rejected:
                continue
            if max_per_anchor and counts_by_anchor[anchor] >= max_per_anchor:
                continue
            cluster_key = (anchor, cluster["index"])
            if max_per_cluster and counts_by_cluster_anchor[cluster_key] >= max_per_cluster:
                continue
            if min_gap and any(abs(row["target"] - previous) < min_gap for previous in seen_targets_by_anchor[anchor]):
                continue
            counts_by_anchor[anchor] += 1
            counts_by_cluster_anchor[cluster_key] += 1
            seen_targets_by_anchor[anchor].append(row["target"])
            selected.append(
                {
                    "name": anchor,
                    "imageOffset": row["targetText"],
                    "cluster": cluster,
                    "sourceFunction": row["sourceFunction"],
                    "sourceFileOffset": row["sourceFileOffset"],
                    "sourceName": row["sourceName"],
                    "sourceFamily": row["sourceFamily"],
                    "sourceGroupCoverage": row.get("sourceGroupCoverage", []),
                    "sourceGroupCounts": row.get("sourceGroupCounts", {}),
                    "anchorGroup": anchor_group,
                    "anchorGroupMatched": bool(anchor_group and anchor_group in source_group_coverage),
                    "score": row["score"],
                    "section": row["section"],
                    "refCount": row["refCount"],
                    "pointerLikeRefCount": row.get("pointerLikeRefCount", 0),
                    "byteGuardRefCount": row.get("byteGuardRefCount", 0),
                    "constantStoreRefCount": row.get("constantStoreRefCount", 0),
                    "firstInstruction": row["firstInstruction"],
                    "firstText": row["firstText"],
                    "signature": row.get("signature", {}),
                    "hypothesis": "root-recovery-writable-global",
                }
            )
            if max_total and len(selected) >= max_total:
                return selected
    return selected


def selected_anchors(args):
    if args.anchor:
        return list(args.anchor)
    return list(ANCHOR_PRESETS[getattr(args, "anchor_preset", DEFAULT_ANCHOR_PRESET)])


def anchor_group_coverage(anchor_counts, requested_anchors):
    requested = set(requested_anchors)
    coverage = {}
    for group_name, group_anchors in ANCHOR_GROUPS.items():
        required = [anchor for anchor in group_anchors if anchor in requested]
        if not required:
            continue
        emitted = [anchor for anchor in required if int(anchor_counts.get(anchor, 0) or 0) > 0]
        coverage[group_name] = {
            "requiredAnchors": required,
            "emittedAnchors": emitted,
            "missingAnchors": [anchor for anchor in required if anchor not in emitted],
            "ready": bool(emitted),
            "complete": len(emitted) == len(required),
        }
    return coverage


def summarize(queue, clusters, outcomes, args):
    anchors = selected_anchors(args)
    rows = target_rows(queue)
    outcomes = outcomes or {}
    rejected_global = rejected_offsets(outcomes)
    suppressed_clusters = rejected_cluster_indexes(clusters or {}, rejected_global) if args.suppress_rejected_clusters else set()
    selected = select_rows(
        rows,
        clusters or {},
        anchors,
        rejected_pairs(outcomes),
        rejected_global,
        args.max_total,
        args.max_per_anchor,
        args.max_per_cluster,
        args.min_gap,
        args.reject_near_gap,
        args.suppress_rejected_clusters,
        args.min_pointer_like_refs,
        args.max_byte_guard_refs,
        args.max_constant_store_refs,
        args.require_source_group_match,
    )
    env_name = args.env_name or ENV_NAMES[args.platform]
    env_value = ";".join(f"{row['name']}={row['imageOffset']}" for row in selected)
    anchor_counts = dict(sorted(Counter(row["name"] for row in selected).items()))
    group_coverage = anchor_group_coverage(anchor_counts, anchors)
    return {
        "schemaVersion": "dune-ue-root-recovery-candidate-export/v1",
        "sourceQueue": queue.get("schemaVersion", ""),
        "sourceClusters": (clusters or {}).get("schemaVersion", ""),
        "platform": args.platform,
        "anchorPreset": "" if args.anchor else getattr(args, "anchor_preset", DEFAULT_ANCHOR_PRESET),
        "envName": env_name,
        "candidateCount": len(selected),
        "requestedAnchors": anchors,
        "anchorCounts": anchor_counts,
        "groupCoverage": group_coverage,
        "missingGroups": [name for name, group in group_coverage.items() if not group["ready"]],
        "clusterCounts": dict(sorted(Counter(str(row["cluster"]["index"]) for row in selected).items())),
        "rejectedOffsetCount": len(rejected_global),
        "rejectNearGap": args.reject_near_gap,
        "minPointerLikeRefs": args.min_pointer_like_refs,
        "maxByteGuardRefs": args.max_byte_guard_refs,
        "maxConstantStoreRefs": args.max_constant_store_refs,
        "requireSourceGroupMatch": args.require_source_group_match,
        "suppressedRejectedClusters": sorted(suppressed_clusters),
        "env": f"{env_name}={env_value}",
        "candidates": selected,
    }


def markdown(summary, limit):
    lines = ["# UE Root Recovery Candidate Export", ""]
    lines.append(f"- Candidates: `{summary['candidateCount']}`")
    lines.append(f"- Platform: `{summary['platform']}`")
    if summary.get("anchorPreset"):
        lines.append(f"- Anchor preset: `{summary['anchorPreset']}`")
    lines.append(f"- Anchor counts: `{summary['anchorCounts']}`")
    if summary.get("groupCoverage"):
        ready_groups = [name for name, group in summary["groupCoverage"].items() if group["ready"]]
        missing_groups = summary.get("missingGroups", [])
        lines.append(f"- Ready groups: `{ready_groups}`")
        lines.append(f"- Missing groups: `{missing_groups}`")
    lines.append(f"- Cluster counts: `{summary['clusterCounts']}`")
    lines.append(f"- Rejected offsets applied: `{summary.get('rejectedOffsetCount', 0)}`")
    lines.append(f"- Reject-near gap: `0x{int(summary.get('rejectNearGap', 0)):x}`")
    lines.append(f"- Min pointer-like refs: `{summary.get('minPointerLikeRefs', 0)}`")
    lines.append(f"- Max byte-guard refs: `{summary.get('maxByteGuardRefs')}`")
    lines.append(f"- Max constant-store refs: `{summary.get('maxConstantStoreRefs')}`")
    lines.append(f"- Require source group match: `{str(summary.get('requireSourceGroupMatch', False)).lower()}`")
    lines.append(f"- Suppressed rejected clusters: `{summary.get('suppressedRejectedClusters', [])}`")
    lines.append("")
    lines.append("```dotenv")
    lines.append(summary["env"])
    lines.append("```")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    for row in summary["candidates"][:limit]:
        cluster = row["cluster"]
        lines.append(
            f"- `{row['name']}` `{row['imageOffset']}` cluster=`{cluster['index']}` "
            f"range=`{cluster['minTarget']}..{cluster['maxTarget']}` score=`{row['score']}` "
            f"refs=`{row['refCount']}` pointerLikeRefs=`{row.get('pointerLikeRefCount', 0)}` "
            f"byteGuardRefs=`{row.get('byteGuardRefCount', 0)}` "
            f"constantStoreRefs=`{row.get('constantStoreRefCount', 0)}` "
            f"anchorGroup=`{row.get('anchorGroup', '')}` "
            f"anchorGroupMatched=`{str(row.get('anchorGroupMatched', False)).lower()}` "
            f"sourceGroups=`{row.get('sourceGroupCoverage', [])}` source=`{row['sourceName']}`"
        )
        lines.append(f"  - first=`{row['firstInstruction']}` `{row['firstText']}`")
    if len(summary["candidates"]) > limit:
        lines.append(f"- ... +{len(summary['candidates']) - limit} more")
    if not summary["candidates"]:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export bounded UE candidate globals from root-recovery queue/cluster evidence."
    )
    parser.add_argument("root_recovery_queue_json", type=Path)
    parser.add_argument("--clusters-json", type=Path)
    parser.add_argument("--candidate-outcomes-json", type=Path, action="append", default=[])
    parser.add_argument("--platform", choices=tuple(ENV_NAMES), default="server")
    parser.add_argument("--env-name")
    parser.add_argument("--anchor", action="append", default=[])
    parser.add_argument(
        "--anchor-preset",
        choices=tuple(ANCHOR_PRESETS),
        default=DEFAULT_ANCHOR_PRESET,
        help="stage-oriented anchor set to emit when --anchor is not supplied",
    )
    parser.add_argument("--max-total", type=int, default=8)
    parser.add_argument("--max-per-anchor", type=int, default=8)
    parser.add_argument("--max-per-cluster", type=int, default=2)
    parser.add_argument("--min-gap", type=lambda value: int(value, 0), default=0x40)
    parser.add_argument(
        "--min-pointer-like-refs",
        type=int,
        default=0,
        help="require this many pointer-like static references for each emitted candidate target",
    )
    parser.add_argument(
        "--max-byte-guard-refs",
        type=int,
        default=0,
        help="suppress candidates with more byte-guard reads than this; use -1 to disable",
    )
    parser.add_argument(
        "--max-constant-store-refs",
        type=int,
        default=0,
        help="suppress candidates with more immediate constant stores than this; use -1 to disable",
    )
    parser.add_argument(
        "--reject-near-gap",
        type=lambda value: int(value, 0),
        default=0x40,
        help="also suppress candidate offsets this close to prior rejected live offsets",
    )
    parser.add_argument(
        "--suppress-rejected-clusters",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="suppress any static target cluster that already produced rejected live evidence",
    )
    parser.add_argument(
        "--require-source-group-match",
        action="store_true",
        help="only emit an anchor when the source function neighborhood covered that anchor's UE group",
    )
    parser.add_argument("--format", choices=("dotenv", "json", "markdown"), default="dotenv")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)
    if args.max_byte_guard_refs < 0:
        args.max_byte_guard_refs = None
    if args.max_constant_store_refs < 0:
        args.max_constant_store_refs = None

    summary = summarize(
        load_json(args.root_recovery_queue_json),
        load_json(args.clusters_json) if args.clusters_json else {},
        merge_outcomes(load_json(path) for path in args.candidate_outcomes_json),
        args,
    )
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "markdown":
        sys.stdout.write(markdown(summary, args.limit))
    else:
        sys.stdout.write(summary["env"] + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
