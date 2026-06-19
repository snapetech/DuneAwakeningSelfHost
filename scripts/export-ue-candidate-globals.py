#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
SCAN_SUMMARY_SCRIPTS = (
    ROOT / "scripts" / "summarize-linux-loader-scan.py",
    ROOT / "scripts" / "summarize-client-loader-scan.py",
    SCRIPT_DIR / "summarize-linux-loader-scan.py",
    SCRIPT_DIR / "summarize-client-loader-scan.py",
)

GROUP_ANCHORS = {
    "names": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
ANCHOR_GROUP = {
    anchor: group
    for group, anchors in GROUP_ANCHORS.items()
    for anchor in anchors
}
DEFAULT_GROUP_ANCHOR = {
    "names": "FNamePool",
    "objects": "GUObjectArray",
    "world": "GWorld",
    "dispatch": "ProcessEvent",
    "package": "StaticLoadObject",
    "reflection": "UObject",
}
NAME_ANCHORS = set(GROUP_ANCHORS["names"])
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


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value):
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 16 if text.lower().startswith("0x") else 10)


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def load_root_shape_rows(path):
    if not path:
        return {}
    data = load_json(path)
    rows = {}
    for row in data.get("rows", []):
        offset = parse_int_or_none(row.get("target") or row.get("imageOffset"))
        if offset is not None:
            rows[offset] = row
    return rows


def load_rejected_offsets(log_paths, outcome_paths=None):
    if not log_paths and not outcome_paths:
        return set()
    rejected = load_rejected_offsets_from_outcomes(outcome_paths or [])
    if not log_paths:
        return rejected
    scan = None
    for script in SCAN_SUMMARY_SCRIPTS:
        if script.exists():
            scan = import_script(script, "summarize_loader_scan_for_candidate_globals")
            break
    if scan is None:
        raise RuntimeError("missing summarize-linux-loader-scan.py or summarize-client-loader-scan.py")
    for path in log_paths:
        records = scan.load_records(path)
        candidates_by_name = defaultdict(list)
        candidates_by_name_anchor = {}
        ready_fname_by_anchor = set()
        for record in records:
            if record.get("event") == "ue-candidate-global" and record.get("status") == "added":
                try:
                    image_offset = parse_int(record.get("imageOffset", ""))
                except (TypeError, ValueError):
                    continue
                name = record.get("name", "")
                candidates_by_name[name].append(image_offset)
                address = record.get("address", "")
                if address:
                    candidates_by_name_anchor[(name, address.lower())] = image_offset
            if record.get("event") in {"ue-fname-start", "ue-fname-finish"} and record.get("status") == "ready":
                pool = (record.get("pool") or "").lower()
                if pool:
                    ready_fname_by_anchor.add(pool)
            if record.get("event") == "ue-pointer" and record.get("status") in {"null", "anchor-unmapped"}:
                reject_record_candidate(record, candidates_by_name, candidates_by_name_anchor, rejected, ready_fname_by_anchor)
            if record.get("event") == "ue-object-array" and record.get("status") in {"empty", "anchor-unmapped"}:
                reject_record_candidate(record, candidates_by_name, candidates_by_name_anchor, rejected, ready_fname_by_anchor)
            if (
                record.get("event") == "ue-object-array"
                and record.get("status") == "finished"
                and record.get("mode") == "direct"
                and record_int(record, "scanned") == 0
                and record_int(record, "registered") == 0
            ):
                reject_record_candidate(record, candidates_by_name, candidates_by_name_anchor, rejected, ready_fname_by_anchor)
            if record.get("event") == "ue-uobject" and record.get("status") in {"target-unmapped", "class-unmapped"}:
                reject_record_candidate(record, candidates_by_name, candidates_by_name_anchor, rejected, ready_fname_by_anchor)
            if record.get("event") == "ue-uobject" and record.get("status") == "candidate":
                if record.get("classMapped") == "false" or record.get("vtableMapped") == "false":
                    reject_record_candidate(record, candidates_by_name, candidates_by_name_anchor, rejected, ready_fname_by_anchor)
    return rejected


def reject_record_candidate(record, candidates_by_name, candidates_by_name_anchor, rejected, ready_fname_by_anchor=None):
    name = record.get("name", "")
    anchor = (record.get("anchor") or record.get("base") or "").lower()
    if name in NAME_ANCHORS and anchor and anchor in (ready_fname_by_anchor or set()):
        return
    if anchor:
        image_offset = candidates_by_name_anchor.get((name, anchor))
        if image_offset is not None:
            rejected.add((name, image_offset))
            return
    if name in NAME_ANCHORS:
        return
    for image_offset in candidates_by_name.get(name, []):
        rejected.add((name, image_offset))


def load_rejected_offsets_from_outcomes(outcome_paths):
    rejected = set()
    for path in outcome_paths:
        data = load_json(path)
        for candidate in data.get("candidates", []):
            name = candidate.get("name", "")
            offset = parse_int_or_none(candidate.get("imageOffset", ""))
            if not name or offset is None:
                continue
            if name in NAME_ANCHORS:
                continue
            if candidate.get("verdict") in {"rejected", "weak-false-positive"}:
                rejected.add((name, offset))
    return rejected


def parse_int_or_none(value):
    try:
        return parse_int(value)
    except (TypeError, ValueError):
        return None


def fname_ready(candidate):
    positives = candidate.get("positives") or {}
    fname_statuses = candidate.get("fnameStatuses") or {}
    return bool(positives.get("fname-ready") or fname_statuses.get("ready"))


def record_int(record, key, default=0):
    try:
        return int(str(record.get(key, default)), 0)
    except (TypeError, ValueError):
        return default


def candidate_anchor_names(row, include_reflection):
    exact = row.get("exactAnchorHintCounts") or {}
    names = [name for name, count in sorted(exact.items()) if count > 0]
    if names:
        return names
    groups = row.get("groupCounts") or {}
    selected = []
    for group, count in sorted(groups.items(), key=lambda item: (-item[1], item[0])):
        if count <= 0:
            continue
        if group == "reflection" and not include_reflection:
            continue
        anchor = DEFAULT_GROUP_ANCHOR.get(group)
        if anchor and anchor not in selected:
            selected.append(anchor)
    return selected


def context_rows_for_anchor(row, anchor):
    group = ANCHOR_GROUP.get(anchor, "")
    rows = []
    for context in row.get("context", []) or []:
        exact = context.get("exactAnchorHints", []) or []
        groups = context.get("groups", []) or []
        if anchor in exact or (group and group in groups):
            rows.append(context)
    return rows


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


def rank_rows(rows):
    def key(row):
        exact_total = sum((row.get("exactAnchorHintCounts") or {}).values())
        group_total = sum((row.get("groupCounts") or {}).values())
        return (
            -exact_total,
            -group_total,
            -int(row.get("score", 0)),
            -int(row.get("refCount", 0)),
            row.get("target", ""),
        )
    return sorted(rows, key=key)


def export_candidates(summary, args):
    rejected_offsets = load_rejected_offsets(args.reject_log, getattr(args, "candidate_outcomes_json", []))
    root_shape_rows = load_root_shape_rows(getattr(args, "writable_root_shapes_json", None))
    counts = Counter()
    candidates = []
    rejected = []
    seen = set()
    for row in rank_rows(summary.get("top", [])):
        try:
            offset = parse_int(row["target"])
        except (KeyError, ValueError):
            continue
        root_shape = root_shape_rows.get(offset)
        if getattr(args, "require_root_shape", False) and root_shape is None:
            rejected.append({"target": row.get("target", ""), "reason": "missing-root-shape"})
            continue
        if root_shape is not None:
            if getattr(args, "min_qword_refs", 0) and int(root_shape.get("qwordRefCount", 0) or 0) < args.min_qword_refs:
                rejected.append({"target": row.get("target", ""), "reason": "min-qword-refs"})
                continue
            if (
                getattr(args, "max_scalar_ratio", None) is not None
                and float(root_shape.get("scalarRatio", 0.0) or 0.0) > args.max_scalar_ratio
            ):
                rejected.append({"target": row.get("target", ""), "reason": "max-scalar-ratio"})
                continue
            if (
                getattr(args, "max_address_ratio", None) is not None
                and float(root_shape.get("addressRatio", 0.0) or 0.0) > args.max_address_ratio
            ):
                rejected.append({"target": row.get("target", ""), "reason": "max-address-ratio"})
                continue
            kind_counts = root_shape.get("kindCounts", {}) or {}
            if getattr(args, "min_read_refs", 0) and int(kind_counts.get("read", 0) or 0) < args.min_read_refs:
                rejected.append({"target": row.get("target", ""), "reason": "min-read-refs"})
                continue
            if getattr(args, "min_write_refs", 0) and int(kind_counts.get("write", 0) or 0) < args.min_write_refs:
                rejected.append({"target": row.get("target", ""), "reason": "min-write-refs"})
                continue
        if args.min_refs and int(row.get("refCount", 0) or 0) < args.min_refs:
            rejected.append({"target": row.get("target", ""), "reason": "min-refs"})
            continue
        if args.max_refs and int(row.get("refCount", 0) or 0) > args.max_refs:
            rejected.append({"target": row.get("target", ""), "reason": "max-refs"})
            continue
        if args.max_function_buckets and int(row.get("functionBucketCount", 0) or 0) > args.max_function_buckets:
            rejected.append({"target": row.get("target", ""), "reason": "max-function-buckets"})
            continue
        anchors = candidate_anchor_names(row, args.include_reflection)
        if not anchors:
            rejected.append({"target": row.get("target", ""), "reason": "no-anchor-hints"})
            continue
        for anchor in anchors:
            group = ANCHOR_GROUP.get(anchor, "unknown")
            if args.groups and group not in args.groups:
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "group-filter"})
                continue
            if args.max_per_anchor and counts[anchor] >= args.max_per_anchor:
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "anchor-limit"})
                continue
            key = (anchor, offset)
            if key in rejected_offsets:
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "rejected-by-log"})
                continue
            if key in seen:
                continue
            quality = hint_quality(row, anchor)
            if getattr(args, "require_exact_anchor", False) and quality["exactContextCount"] == 0:
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "missing-exact-anchor"})
                continue
            if getattr(args, "require_specific_context", False) and quality["specificContextCount"] == 0:
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "missing-specific-context"})
                continue
            if (
                getattr(args, "max_generic_context_ratio", None) is not None
                and quality["contextCount"]
                and quality["genericContextCount"] / quality["contextCount"] > args.max_generic_context_ratio
            ):
                rejected.append({"target": row.get("target", ""), "anchor": anchor, "reason": "max-generic-context-ratio"})
                continue
            seen.add(key)
            counts[anchor] += 1
            candidates.append(
                {
                    "name": anchor,
                    "group": group,
                    "imageOffset": f"0x{offset:x}",
                    "sourceTarget": row.get("target", ""),
                    "sourceFileOffset": row.get("fileOffset", ""),
                    "refCount": row.get("refCount", 0),
                    "functionBucketCount": row.get("functionBucketCount", 0),
                    "score": row.get("score", 0),
                    "groupCounts": row.get("groupCounts", {}),
                    "exactAnchorHintCounts": row.get("exactAnchorHintCounts", {}),
                    "hintQuality": quality,
                    "qwordRefCount": root_shape.get("qwordRefCount", 0) if root_shape else 0,
                    "scalarRefCount": root_shape.get("scalarRefCount", 0) if root_shape else 0,
                    "scalarRatio": root_shape.get("scalarRatio", 0.0) if root_shape else 0.0,
                    "addressRatio": root_shape.get("addressRatio", 0.0) if root_shape else 0.0,
                    "kindCounts": root_shape.get("kindCounts", {}) if root_shape else {},
                    "rootShape": {
                        "present": root_shape is not None,
                        "score": root_shape.get("score", 0) if root_shape else 0,
                        "refCount": root_shape.get("refCount", 0) if root_shape else 0,
                        "functionBucketCount": root_shape.get("functionBucketCount", 0) if root_shape else 0,
                        "qwordRefCount": root_shape.get("qwordRefCount", 0) if root_shape else 0,
                        "scalarRatio": root_shape.get("scalarRatio", 0.0) if root_shape else 0.0,
                        "addressRatio": root_shape.get("addressRatio", 0.0) if root_shape else 0.0,
                        "kindCounts": root_shape.get("kindCounts", {}) if root_shape else {},
                    },
                }
            )
            if args.max_total and len(candidates) >= args.max_total:
                break
        if args.max_total and len(candidates) >= args.max_total:
            break
    env_value = ";".join(f"{row['name']}={row['imageOffset']}" for row in candidates)
    rejected_reason_counts = dict(sorted(Counter(row.get("reason", "unknown") for row in rejected).items()))
    return {
        "schemaVersion": "dune-ue-candidate-globals/v1",
        "sourceFormat": summary.get("schemaVersion", ""),
        "candidateCount": len(candidates),
        "anchorCounts": dict(sorted(counts.items())),
        "groups": dict(sorted(Counter(row["group"] for row in candidates).items())),
        "env": f"DUNE_PROBE_LOADER_UE_CANDIDATE_GLOBALS={env_value}",
        "candidates": candidates,
        "rejectedReasonCounts": rejected_reason_counts,
        "rejected": rejected,
    }


def markdown(result, limit):
    lines = ["# UE Candidate Globals", ""]
    lines.append(f"- Candidates: `{result['candidateCount']}`")
    lines.append(f"- Anchor counts: `{result['anchorCounts']}`")
    lines.append(f"- Groups: `{result['groups']}`")
    lines.append(f"- Rejected reason counts: `{result.get('rejectedReasonCounts', {})}`")
    lines.append("")
    lines.append("```dotenv")
    lines.append(result["env"])
    lines.append("```")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    for row in result["candidates"][:limit]:
        root_shape = row.get("rootShape") or {}
        root_kinds = root_shape.get("kindCounts") or {}
        hint = row.get("hintQuality") or {}
        lines.append(
            f"- `{row['name']}` `{row['imageOffset']}` group=`{row['group']}` "
            f"refs=`{row['refCount']}` score=`{row['score']}` "
            f"rootQwordRefs=`{root_shape.get('qwordRefCount', 0)}` "
            f"rootKinds=`{root_kinds}` rootScalarRatio=`{root_shape.get('scalarRatio', 0.0)}` "
            f"rootAddressRatio=`{root_shape.get('addressRatio', 0.0)}` "
            f"hintExact=`{hint.get('exactContextCount', 0)}` "
            f"hintSpecific=`{hint.get('specificContextCount', 0)}` "
            f"hintGeneric=`{hint.get('genericContextCount', 0)}` "
            f"exact=`{row['exactAnchorHintCounts']}` groups=`{row['groupCounts']}`"
        )
        for context in hint.get("sampleContext", [])[:2]:
            text = context.get("string") or " | ".join(context.get("symbols", []) or [])
            if text:
                lines.append(f"  - context `{text}`")
    if len(result["candidates"]) > limit:
        lines.append(f"- ... +{len(result['candidates']) - limit} more")
    if not result["candidates"]:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export loader candidate-global env from writable-global clustering evidence."
    )
    parser.add_argument("writable_global_refs_json", type=Path)
    parser.add_argument("--reject-log", type=Path, action="append", default=[])
    parser.add_argument("--candidate-outcomes-json", type=Path, action="append", default=[])
    parser.add_argument("--writable-root-shapes-json", type=Path)
    parser.add_argument("--require-root-shape", action="store_true")
    parser.add_argument("--min-qword-refs", type=int, default=0)
    parser.add_argument("--max-scalar-ratio", type=float)
    parser.add_argument("--max-address-ratio", type=float)
    parser.add_argument("--min-read-refs", type=int, default=0)
    parser.add_argument("--min-write-refs", type=int, default=0)
    parser.add_argument("--require-exact-anchor", action="store_true")
    parser.add_argument("--require-specific-context", action="store_true")
    parser.add_argument("--max-generic-context-ratio", type=float)
    parser.add_argument("--groups", action="append", choices=tuple(GROUP_ANCHORS))
    parser.add_argument("--include-reflection", action="store_true")
    parser.add_argument("--min-refs", type=int, default=0)
    parser.add_argument("--max-refs", type=int, default=0)
    parser.add_argument("--max-function-buckets", type=int, default=0)
    parser.add_argument("--max-per-anchor", type=int, default=4)
    parser.add_argument("--max-total", type=int, default=16)
    parser.add_argument("--format", choices=("dotenv", "json", "markdown"), default="dotenv")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)

    result = export_candidates(load_json(args.writable_global_refs_json), args)
    if args.format == "json":
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "markdown":
        sys.stdout.write(markdown(result, args.limit))
    else:
        sys.stdout.write(result["env"] + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
