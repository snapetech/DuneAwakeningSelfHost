#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ENV_NAMES = {
    "server": "DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS",
    "linux-client": "DUNE_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
    "windows": "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
}
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
    "package": ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
ANCHOR_GROUP = {
    anchor: group
    for group, anchors in ANCHOR_GROUPS.items()
    for anchor in anchors
}
GENERIC_CONTEXT_NEEDLES = (
    "Runtime/CoreUObject/Public\\UObject/Class.h",
    "Runtime/CoreUObject/Public/UObject/Class.h",
    "const FName &",
    "const FName&",
    "UObject *",
    "UObject*",
    "UClass *",
    "UClass*",
    "UFunction *",
    "UFunction*",
    "FProperty *",
    "FProperty*",
)


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def parse_include(raw):
    if "=" not in raw:
        raise ValueError(f"--include must be NAME=0xOFFSET, got {raw!r}")
    name, offset = raw.split("=", 1)
    int(offset, 0)
    return {"name": name, "imageOffset": offset, "hypothesis": "explicit-include"}


def parse_int(value):
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 16 if text.lower().startswith("0x") else 10)


def parse_int_or_none(value):
    try:
        return parse_int(value)
    except (TypeError, ValueError):
        return None


def target_offset(row):
    return parse_int_or_none(row.get("target") or row.get("imageOffset"))


def load_global_context_rows(paths):
    rows = {}
    for path in paths or []:
        data = load_json(path)
        source_rows = []
        for key in ("top", "rows", "writableTargets"):
            source_rows.extend(data.get(key, []) or [])
        for row in source_rows:
            offset = target_offset(row)
            if offset is None:
                continue
            current = rows.setdefault(
                offset,
                {
                    "context": [],
                    "groupCounts": Counter(),
                    "exactAnchorHintCounts": Counter(),
                },
            )
            current["context"].extend(row.get("context", []) or [])
            current["groupCounts"].update(row.get("groupCounts", {}) or {})
            current["exactAnchorHintCounts"].update(row.get("exactAnchorHintCounts", {}) or {})
    merged = {}
    for offset, row in rows.items():
        merged[offset] = {
            "context": row["context"],
            "groupCounts": dict(sorted(row["groupCounts"].items())),
            "exactAnchorHintCounts": dict(sorted(row["exactAnchorHintCounts"].items())),
        }
    return merged


def rows_with_global_context(shape_summary, global_context_rows):
    if not global_context_rows:
        return shape_summary
    summary = dict(shape_summary)
    rows = []
    for row in shape_summary.get("rows", []) or []:
        enriched = dict(row)
        context = global_context_rows.get(target_offset(row))
        if context:
            enriched["context"] = list(row.get("context", []) or []) + list(context.get("context", []) or [])
            enriched["groupCounts"] = {**(context.get("groupCounts", {}) or {}), **(row.get("groupCounts", {}) or {})}
            enriched["exactAnchorHintCounts"] = {
                **(context.get("exactAnchorHintCounts", {}) or {}),
                **(row.get("exactAnchorHintCounts", {}) or {}),
            }
        rows.append(enriched)
    summary["rows"] = rows
    return summary


def row_kind_count(row, kind):
    return int((row.get("kindCounts") or {}).get(kind, 0) or 0)


def row_passes_filters(
    row,
    min_score,
    max_ref_count=0,
    max_function_buckets=0,
    max_address_ratio=None,
    require_read_write=False,
    require_qword=False,
    min_qword_refs=0,
):
    if int(row.get("score", 0) or 0) < min_score:
        return False
    if max_ref_count and int(row.get("refCount", 0) or 0) > max_ref_count:
        return False
    if max_function_buckets and int(row.get("functionBucketCount", 0) or 0) > max_function_buckets:
        return False
    if max_address_ratio is not None and float(row.get("addressRatio", 0.0) or 0.0) > max_address_ratio:
        return False
    if require_read_write and (row_kind_count(row, "read") <= 0 or row_kind_count(row, "write") <= 0):
        return False
    qword_refs = int(row.get("qwordRefCount", 0) or 0)
    if require_qword and qword_refs <= 0:
        return False
    if min_qword_refs and qword_refs < min_qword_refs:
        return False
    return True


def row_filter_rejection_reason(
    row,
    min_score,
    max_ref_count=0,
    max_function_buckets=0,
    max_address_ratio=None,
    require_read_write=False,
    require_qword=False,
    min_qword_refs=0,
):
    if int(row.get("score", 0) or 0) < min_score:
        return "min-score"
    if max_ref_count and int(row.get("refCount", 0) or 0) > max_ref_count:
        return "max-ref-count"
    if max_function_buckets and int(row.get("functionBucketCount", 0) or 0) > max_function_buckets:
        return "max-function-buckets"
    if max_address_ratio is not None and float(row.get("addressRatio", 0.0) or 0.0) > max_address_ratio:
        return "max-address-ratio"
    if require_read_write and (row_kind_count(row, "read") <= 0 or row_kind_count(row, "write") <= 0):
        return "missing-read-write"
    qword_refs = int(row.get("qwordRefCount", 0) or 0)
    if require_qword and qword_refs <= 0:
        return "missing-qword"
    if min_qword_refs and qword_refs < min_qword_refs:
        return "min-qword-refs"
    return ""


def context_rows_for_anchor(row, anchor):
    group = ANCHOR_GROUP.get(anchor, "")
    contexts = []
    for context in row.get("context", []) or []:
        exact = context.get("exactAnchorHints", []) or []
        groups = context.get("groups", []) or []
        if anchor in exact or (group and group in groups):
            contexts.append(context)
    return contexts


def generic_context_row(context):
    haystack = "\n".join(
        str(value)
        for value in [
            context.get("string", ""),
            " ".join(context.get("symbols", []) or []),
        ]
        if value
    )
    return any(needle in haystack for needle in GENERIC_CONTEXT_NEEDLES)


def hint_quality(row, anchor):
    contexts = context_rows_for_anchor(row, anchor)
    exact_contexts = [
        context
        for context in contexts
        if anchor in (context.get("exactAnchorHints", []) or [])
    ]
    generic_contexts = [context for context in contexts if generic_context_row(context)]
    specific_contexts = [context for context in contexts if not generic_context_row(context)]
    return {
        "contextCount": len(contexts),
        "exactContextCount": len(exact_contexts),
        "specificContextCount": len(specific_contexts),
        "genericContextCount": len(generic_contexts),
        "sampleContext": contexts[:3],
    }


def select_candidates(
    summary,
    anchors,
    max_total,
    max_per_anchor,
    min_score,
    max_ref_count=0,
    max_function_buckets=0,
    max_address_ratio=None,
    require_read_write=False,
    require_qword=False,
    min_qword_refs=0,
    require_exact_anchor=False,
    require_specific_context=False,
    max_generic_context_ratio=None,
    rejected=None,
):
    selected = []
    counts = Counter()
    rejected = rejected if rejected is not None else []
    rows = []
    for row in summary.get("rows", []):
        reason = row_filter_rejection_reason(
            row,
            min_score,
            max_ref_count=max_ref_count,
            max_function_buckets=max_function_buckets,
            max_address_ratio=max_address_ratio,
            require_read_write=require_read_write,
            require_qword=require_qword,
            min_qword_refs=min_qword_refs,
        )
        if reason:
            for anchor in anchors:
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": reason})
            continue
        rows.append(row)
    for row in rows:
        for anchor in anchors:
            if max_per_anchor and counts[anchor] >= max_per_anchor:
                continue
            quality = hint_quality(row, anchor)
            if require_exact_anchor and quality["exactContextCount"] == 0:
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "missing-exact-anchor"})
                continue
            if require_specific_context and quality["specificContextCount"] == 0:
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "missing-specific-context"})
                continue
            if (
                max_generic_context_ratio is not None
                and quality["contextCount"]
                and quality["genericContextCount"] / quality["contextCount"] > max_generic_context_ratio
            ):
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "max-generic-context-ratio"})
                continue
            selected.append(
                {
                    "name": anchor,
                    "group": ANCHOR_GROUP.get(anchor, "unknown"),
                    "imageOffset": row.get("imageOffset") or row.get("target", ""),
                    "sourceTarget": row.get("target", ""),
                    "score": row.get("score", 0),
                    "section": row.get("section", ""),
                    "refCount": row.get("refCount", 0),
                    "functionBucketCount": row.get("functionBucketCount", 0),
                    "kindCounts": row.get("kindCounts", {}),
                    "sizeCounts": row.get("sizeCounts", {}),
                    "qwordRefCount": row.get("qwordRefCount", 0),
                    "scalarRefCount": row.get("scalarRefCount", 0),
                    "scalarRatio": row.get("scalarRatio", 0.0),
                    "addressRatio": row.get("addressRatio", 0.0),
                    "readRefCount": row_kind_count(row, "read"),
                    "writeRefCount": row_kind_count(row, "write"),
                    "hintQuality": quality,
                    "hypothesis": "writable-root-readwrite-shape",
                }
            )
            counts[anchor] += 1
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


def summarize(args):
    shape_summary = load_json(args.writable_root_shapes_json)
    global_context_rows = load_global_context_rows(getattr(args, "writable_global_refs_json", []))
    shape_summary = rows_with_global_context(shape_summary, global_context_rows)
    anchors = selected_anchors(args)
    selected = [parse_include(raw) for raw in args.include]
    rejected = []
    selected.extend(
        select_candidates(
            shape_summary,
            anchors,
            args.max_total - len(selected),
            args.max_per_anchor,
            args.min_score,
            max_ref_count=args.max_ref_count,
            max_function_buckets=args.max_function_buckets,
            max_address_ratio=args.max_address_ratio,
            require_read_write=args.require_read_write,
            require_qword=args.require_qword,
            min_qword_refs=args.min_qword_refs,
            require_exact_anchor=getattr(args, "require_exact_anchor", False),
            require_specific_context=getattr(args, "require_specific_context", False),
            max_generic_context_ratio=getattr(args, "max_generic_context_ratio", None),
            rejected=rejected,
        )
    )
    if args.max_total:
        selected = selected[: args.max_total]
    env_name = args.env_name or ENV_NAMES[args.platform]
    env_value = ";".join(f"{row['name']}={row['imageOffset']}" for row in selected)
    anchor_counts = dict(sorted(Counter(row["name"] for row in selected).items()))
    group_coverage = anchor_group_coverage(anchor_counts, anchors)
    rejected_reason_counts = dict(sorted(Counter(row.get("reason", "unknown") for row in rejected).items()))
    return {
        "schemaVersion": "dune-ue-writable-root-shape-candidates/v1",
        "sourceShapes": shape_summary.get("schemaVersion", ""),
        "sourceGlobalContextCount": len(global_context_rows),
        "platform": args.platform,
        "anchorPreset": "" if args.anchor else getattr(args, "anchor_preset", DEFAULT_ANCHOR_PRESET),
        "envName": env_name,
        "candidateCount": len(selected),
        "requestedAnchors": anchors,
        "anchorCounts": anchor_counts,
        "groupCoverage": group_coverage,
        "missingGroups": [name for name, group in group_coverage.items() if not group["ready"]],
        "env": f"{env_name}={env_value}",
        "candidates": selected,
        "rejectedReasonCounts": rejected_reason_counts,
        "rejected": rejected,
    }


def markdown(summary):
    lines = ["# UE Writable Root Shape Candidate Export", ""]
    lines.append(f"- Platform: `{summary['platform']}`")
    if summary.get("anchorPreset"):
        lines.append(f"- Anchor preset: `{summary['anchorPreset']}`")
    lines.append(f"- Candidates: `{summary['candidateCount']}`")
    lines.append(f"- Anchor counts: `{summary['anchorCounts']}`")
    lines.append(f"- Rejected reason counts: `{summary.get('rejectedReasonCounts', {})}`")
    if summary.get("groupCoverage"):
        ready_groups = [name for name, group in summary["groupCoverage"].items() if group["ready"]]
        lines.append(f"- Ready groups: `{ready_groups}`")
        lines.append(f"- Missing groups: `{summary.get('missingGroups', [])}`")
    lines.append("")
    lines.append("```dotenv")
    lines.append(summary["env"])
    lines.append("```")
    lines.append("")
    for row in summary["candidates"]:
        lines.append(
            f"- `{row['name']}` `{row['imageOffset']}` hypothesis=`{row['hypothesis']}` "
            f"score=`{row.get('score', '')}` refs=`{row.get('refCount', '')}` "
            f"functions=`{row.get('functionBucketCount', '')}` "
            f"qwordRefs=`{row.get('qwordRefCount', '')}` scalarRatio=`{row.get('scalarRatio', '')}` "
            f"addressRatio=`{row.get('addressRatio', '')}` readRefs=`{row.get('readRefCount', '')}` "
            f"writeRefs=`{row.get('writeRefCount', '')}` "
            f"hintExact=`{(row.get('hintQuality') or {}).get('exactContextCount', 0)}` "
            f"hintSpecific=`{(row.get('hintQuality') or {}).get('specificContextCount', 0)}` "
            f"hintGeneric=`{(row.get('hintQuality') or {}).get('genericContextCount', 0)}`"
        )
        for context in (row.get("hintQuality") or {}).get("sampleContext", [])[:2]:
            text = context.get("string") or " | ".join(context.get("symbols", []) or [])
            if text:
                lines.append(f"  - context `{text}`")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export read-only UE candidate globals from writable-root shape reports.")
    parser.add_argument("writable_root_shapes_json", type=Path)
    parser.add_argument("--writable-global-refs-json", type=Path, action="append", default=[])
    parser.add_argument("--platform", choices=sorted(ENV_NAMES), default="server")
    parser.add_argument("--env-name")
    parser.add_argument("--anchor", action="append", default=[])
    parser.add_argument(
        "--anchor-preset",
        choices=tuple(ANCHOR_PRESETS),
        default=DEFAULT_ANCHOR_PRESET,
        help="stage-oriented anchor set to emit when --anchor is not supplied",
    )
    parser.add_argument("--include", action="append", default=[], help="explicit candidate NAME=0xOFFSET")
    parser.add_argument("--max-total", type=int, default=12)
    parser.add_argument("--max-per-anchor", type=int, default=4)
    parser.add_argument("--min-score", type=int, default=0)
    parser.add_argument("--max-ref-count", type=int, default=0)
    parser.add_argument("--max-function-buckets", type=int, default=0)
    parser.add_argument("--max-address-ratio", type=float)
    parser.add_argument("--require-read-write", action="store_true")
    parser.add_argument("--require-qword", action="store_true")
    parser.add_argument("--min-qword-refs", type=int, default=0)
    parser.add_argument("--require-exact-anchor", action="store_true")
    parser.add_argument("--require-specific-context", action="store_true")
    parser.add_argument("--max-generic-context-ratio", type=float)
    parser.add_argument("--format", choices=("json", "markdown", "env"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize(args)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "env":
        sys.stdout.write(summary["env"] + "\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
