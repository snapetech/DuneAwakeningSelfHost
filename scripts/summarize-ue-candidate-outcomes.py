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


def import_script(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {path}")
    spec.loader.exec_module(module)
    return module


def parse_int(value, default=0):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def load_records(path):
    for script in SCAN_SUMMARY_SCRIPTS:
        if script.exists():
            scan = import_script(script, "summarize_loader_scan_for_candidate_outcomes")
            return scan.load_records(path)
    raise RuntimeError("missing summarize-linux-loader-scan.py or summarize-client-loader-scan.py")


def candidate_key(record):
    return (
        record.get("pid", ""),
        record.get("name", ""),
        (record.get("address") or record.get("anchor") or record.get("base") or "").lower(),
    )


def event_anchor(record):
    return (record.get("anchor") or record.get("base") or record.get("addr") or record.get("pool") or "").lower()


def classify_candidate(candidate):
    reasons = []
    positive = []
    name = candidate.get("name", "")
    is_name_pool = name in {"FNamePool", "GName", "GNames", "RuntimeFNamePool"}
    for runtime in candidate.get("runtimeDiscoveries", []):
        status = runtime.get("status", "")
        if status == "promoted":
            positive.append("runtime-discovery-promoted")
        elif status:
            reasons.append(f"runtime-discovery-{status}")
    for status, count in candidate.get("runtimeFinalStatuses", {}).items():
        for _ in range(count):
            if status == "promoted":
                positive.append("runtime-discovery-final-promoted")
            elif status:
                reasons.append(f"runtime-discovery-final-{status}")
    for pointer in candidate["pointers"]:
        status = pointer.get("status", "")
        if status == "target-mapped":
            positive.append("pointer-target-mapped")
            if pointer.get("executable") == "true":
                reasons.append("pointer-target-executable")
        elif status in {"null", "anchor-unmapped"}:
            reasons.append(f"pointer-{status}")
    for layout in candidate["layouts"]:
        if layout.get("status") == "target-readable":
            positive.append("layout-target-readable")
            if layout.get("perms", "").startswith("r-x") or layout.get("executable") == "true":
                reasons.append("layout-target-executable")
    for uobject in candidate["uobjects"]:
        status = uobject.get("status", "")
        if status == "candidate":
            positive.append("uobject-candidate")
            if uobject.get("classMapped") == "true" and uobject.get("vtableMapped") == "true":
                positive.append("uobject-class-vtable-mapped")
            else:
                reasons.append("uobject-class-or-vtable-unmapped")
        elif status in {"target-unmapped", "class-unmapped"}:
            reasons.append(f"uobject-{status}")
    for object_array in candidate["objectArrays"]:
        status = object_array.get("status", "")
        if status in {"anchor-unmapped", "empty", "anchor-pointer-unreadable"}:
            reasons.append(f"object-array-{status}")
        if status == "finished":
            scanned = parse_int(object_array.get("scanned"))
            registered = parse_int(object_array.get("registered"))
            if registered > 0:
                positive.append("object-array-registered")
            elif scanned == 0 and registered == 0:
                reasons.append("object-array-zero-scan")
    for fname in candidate["fnames"]:
        status = fname.get("status", "")
        if status == "decoded":
            positive.append("fname-decoded")
        elif status:
            reasons.append(f"fname-{status}")
    if is_name_pool:
        for fname_start in candidate["fnameStarts"]:
            if fname_start.get("status") == "ready":
                positive.append("fname-pool-ready")
            elif fname_start.get("status"):
                reasons.append(f"fname-start-{fname_start.get('status')}")
        for fname_finish in candidate["fnameFinishes"]:
            if fname_finish.get("status") == "ready":
                positive.append("fname-pool-ready")
            elif fname_finish.get("status"):
                reasons.append(f"fname-finish-{fname_finish.get('status')}")

    reason_counts = Counter(reasons)
    positive_counts = Counter(positive)
    if positive_counts.get("object-array-registered") or positive_counts.get("uobject-class-vtable-mapped"):
        verdict = "promotable"
    elif positive_counts.get("fname-decoded") or positive_counts.get("fname-pool-ready"):
        verdict = "promising"
    elif reason_counts.get("runtime-discovery-final-ambiguous") or reason_counts.get("runtime-discovery-final-missing"):
        verdict = "weak-false-positive"
    elif positive and reasons:
        verdict = "weak-false-positive"
    elif positive:
        verdict = "weak"
    else:
        verdict = "rejected"
    recommendation = recommendation_for(verdict, reason_counts, positive_counts)
    return verdict, dict(sorted(reason_counts.items())), dict(sorted(positive_counts.items())), recommendation


def recommendation_for(verdict, reasons, positives):
    if verdict == "promotable":
        return "promote-to-anchor-canary"
    if verdict == "promising":
        return "rerun-with-deeper-fname-or-reflection-probes"
    if reasons.get("pointer-target-executable") or reasons.get("layout-target-executable"):
        return "reject-code-pointer-and-trace-caller-dataflow"
    if reasons.get("pointer-null") or reasons.get("object-array-empty"):
        return "reject-null-or-empty-global"
    if reasons.get("uobject-class-or-vtable-unmapped"):
        return "reject-uobject-shape"
    if reasons.get("runtime-discovery-final-ambiguous") or reasons.get("runtime-discovery-final-missing"):
        return "reject-runtime-auto-discovery-candidate"
    if positives:
        return "manual-review"
    return "reject"


def summarize(records, server_pid=None):
    if server_pid:
        records = [record for record in records if record.get("pid") == server_pid]
    candidates = {}
    by_pid_name_anchor = {}
    runtime_candidates_by_pid_name = defaultdict(list)
    for record in records:
        if record.get("event") == "ue-candidate-global" and record.get("status") == "added":
            key = candidate_key(record)
            row = {
                "pid": record.get("pid", ""),
                "name": record.get("name", ""),
                "address": record.get("address", "").lower(),
                "imageOffset": record.get("imageOffset", ""),
                "fileOffset": record.get("fileOffset", ""),
                "targetImage": record.get("targetImage", ""),
                "runtimeRwFileOffset": record.get("runtimeRwFileOffset", ""),
                "perms": record.get("perms", ""),
                "map": record.get("map", "") or record.get("module", ""),
                "absolute": record.get("absolute", ""),
                "source": "candidate-global",
                "runtimeDiscoveries": [],
                "runtimeFinalStatuses": {},
                "anchors": [],
                "pointers": [],
                "layouts": [],
                "uobjects": [],
                "objectArrays": [],
                "fnames": [],
                "fnameStarts": [],
                "fnameFinishes": [],
            }
            candidates[key] = row
            by_pid_name_anchor[(row["pid"], row["name"], row["address"])] = row
            continue
        if record.get("event") == "ue-runtime-discovery-candidate":
            address = (record.get("addr") or "").lower()
            key = (record.get("pid", ""), record.get("name", ""), address)
            image_offset = record.get("imageOffset", "") or record.get("rva", "")
            row = {
                "pid": record.get("pid", ""),
                "name": record.get("name", ""),
                "address": address,
                "imageOffset": image_offset,
                "fileOffset": record.get("fileOffset", ""),
                "targetImage": record.get("targetImage", ""),
                "runtimeRwFileOffset": record.get("runtimeRwFileOffset", ""),
                "perms": record.get("perms", ""),
                "map": record.get("map", "") or record.get("module", ""),
                "absolute": "",
                "source": "runtime-discovery",
                "runtimeDiscoveries": [record],
                "runtimeFinalStatuses": {},
                "anchors": [],
                "pointers": [],
                "layouts": [],
                "uobjects": [],
                "objectArrays": [],
                "fnames": [],
                "fnameStarts": [],
                "fnameFinishes": [],
            }
            candidates[key] = row
            by_pid_name_anchor[(row["pid"], row["name"], row["address"])] = row
            runtime_candidates_by_pid_name[(row["pid"], row["name"])].append(row)

    def find_candidate(record):
        pid = record.get("pid", "")
        name = record.get("name", "")
        anchor = event_anchor(record)
        if anchor:
            if not name:
                matches = [row for (row_pid, _row_name, row_anchor), row in by_pid_name_anchor.items() if row_pid == pid and row_anchor == anchor]
                if len(matches) == 1:
                    return matches[0]
            return by_pid_name_anchor.get((pid, name, anchor))
        return None

    for record in records:
        event = record.get("event", "")
        candidate = find_candidate(record)
        if not candidate:
            continue
        if event == "ue-anchor":
            candidate["anchors"].append(record)
        elif event == "ue-pointer":
            candidate["pointers"].append(record)
        elif event == "ue-layout":
            candidate["layouts"].append(record)
        elif event == "ue-uobject":
            candidate["uobjects"].append(record)
        elif event == "ue-object-array":
            candidate["objectArrays"].append(record)
        elif event == "ue-fname":
            candidate["fnames"].append(record)
        elif event == "ue-fname-start":
            candidate["fnameStarts"].append(record)
        elif event == "ue-fname-finish":
            candidate["fnameFinishes"].append(record)
        elif event == "ue-runtime-anchor":
            candidate["runtimeDiscoveries"].append({**record, "status": record.get("status", "promoted")})

    for record in records:
        if record.get("event") != "ue-runtime-discovery" or not record.get("name"):
            continue
        key = (record.get("pid", ""), record.get("name", ""))
        status = record.get("status", "")
        for candidate in runtime_candidates_by_pid_name.get(key, []):
            candidate["runtimeFinalStatuses"][status] = candidate["runtimeFinalStatuses"].get(status, 0) + 1

    rows = []
    for candidate in candidates.values():
        verdict, reasons, positives, recommendation = classify_candidate(candidate)
        rows.append(
            {
                "pid": candidate["pid"],
                "name": candidate["name"],
                "address": candidate["address"],
                "imageOffset": candidate["imageOffset"],
                "fileOffset": candidate.get("fileOffset", ""),
                "targetImage": candidate.get("targetImage", ""),
                "runtimeRwFileOffset": candidate.get("runtimeRwFileOffset", ""),
                "perms": candidate.get("perms", ""),
                "map": candidate.get("map", ""),
                "source": candidate.get("source", ""),
                "verdict": verdict,
                "recommendation": recommendation,
                "reasons": reasons,
                "positives": positives,
                "anchorTargets": summarize_anchor_targets(candidate["anchors"]),
                "pointerTargets": summarize_pointer_targets(candidate["pointers"]),
                "layoutTargets": summarize_layout_targets(candidate["layouts"]),
                "uobjectTargets": summarize_uobject_targets(candidate["uobjects"]),
                "anchorStatuses": dict(Counter(row.get("status", "") for row in candidate["anchors"])),
                "pointerStatuses": dict(Counter(row.get("status", "") for row in candidate["pointers"])),
                "layoutStatuses": dict(Counter(row.get("status", "") for row in candidate["layouts"])),
                "uobjectStatuses": dict(Counter(row.get("status", "") for row in candidate["uobjects"])),
                "objectArrayStatuses": dict(Counter(row.get("status", "") for row in candidate["objectArrays"])),
                "fnameStatuses": dict(Counter(row.get("status", "") for row in candidate["fnames"])),
                "fnameStartStatuses": dict(Counter(row.get("status", "") for row in candidate["fnameStarts"])),
                "fnameFinishStatuses": dict(Counter(row.get("status", "") for row in candidate["fnameFinishes"])),
            }
        )
    rows.sort(key=lambda row: (row["pid"], row["name"], parse_int(row["imageOffset"]), row["address"]))
    return {
        "schemaVersion": "dune-ue-candidate-outcomes/v1",
        "candidateCount": len(rows),
        "verdictCounts": dict(sorted(Counter(row["verdict"] for row in rows).items())),
        "recommendationCounts": dict(sorted(Counter(row["recommendation"] for row in rows).items())),
        "nameCounts": dict(sorted(Counter(row["name"] for row in rows).items())),
        "candidates": rows,
    }


def summarize_pointer_targets(records):
    rows = []
    for record in records:
        if record.get("status") != "target-mapped":
            continue
        rows.append(
            {
                "value": record.get("value", ""),
                "imageOffset": record.get("imageOffset", ""),
                "fileOffset": record.get("fileOffset", ""),
                "perms": record.get("perms", ""),
                "readable": record.get("readable", ""),
                "writable": record.get("writable", ""),
                "executable": record.get("executable", ""),
                "map": record.get("map", ""),
            }
        )
    return rows


def summarize_anchor_targets(records):
    rows = []
    for record in records:
        if record.get("status") != "mapped":
            continue
        rows.append(
            {
                "addr": record.get("addr", ""),
                "imageOffset": record.get("imageOffset", ""),
                "fileOffset": record.get("fileOffset", ""),
                "perms": record.get("perms", ""),
                "readable": record.get("readable", ""),
                "writable": record.get("writable", ""),
                "executable": record.get("executable", ""),
                "map": record.get("map", ""),
            }
        )
    return rows


def summarize_layout_targets(records):
    rows = []
    for record in records:
        if record.get("status") != "target-readable":
            continue
        rows.append(
            {
                "target": record.get("target", ""),
                "slots": record.get("slots", ""),
                "perms": record.get("perms", ""),
                "map": record.get("map", ""),
            }
        )
    return rows


def summarize_uobject_targets(records):
    rows = []
    for record in records:
        if record.get("status") != "candidate":
            continue
        rows.append(
            {
                "target": record.get("target", ""),
                "vtable": record.get("vtable", ""),
                "vtableMapped": record.get("vtableMapped", ""),
                "class": record.get("class", ""),
                "classMapped": record.get("classMapped", ""),
                "outer": record.get("outer", ""),
                "outerMapped": record.get("outerMapped", ""),
                "nameComparisonIndex": record.get("nameComparisonIndex", ""),
                "nameNumber": record.get("nameNumber", ""),
            }
        )
    return rows


def markdown(summary, limit):
    lines = ["# UE Candidate Outcomes", ""]
    lines.append(f"- Candidates: `{summary['candidateCount']}`")
    lines.append(f"- Verdicts: `{summary['verdictCounts']}`")
    lines.append(f"- Recommendations: `{summary['recommendationCounts']}`")
    lines.append(f"- Names: `{summary['nameCounts']}`")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    if not summary["candidates"]:
        lines.append("- none")
    for row in summary["candidates"][:limit]:
        lines.append(
            f"- pid=`{row['pid']}` `{row['name']}` `{row['imageOffset']}` "
            f"verdict=`{row['verdict']}` recommendation=`{row['recommendation']}` "
            f"positives=`{row['positives']}` reasons=`{row['reasons']}`"
        )
        for pointer in row["pointerTargets"]:
            lines.append(
                f"  - pointer value=`{pointer['value']}` image=`{pointer['imageOffset']}` "
                f"file=`{pointer['fileOffset']}` perms=`{pointer['perms']}` executable=`{pointer['executable']}`"
            )
        for uobject in row["uobjectTargets"]:
            lines.append(
                f"  - uobject target=`{uobject['target']}` vtableMapped=`{uobject['vtableMapped']}` "
                f"classMapped=`{uobject['classMapped']}` class=`{uobject['class']}`"
            )
    if len(summary["candidates"]) > limit:
        lines.append(f"- ... +{len(summary['candidates']) - limit} more")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize runtime outcomes for UE candidate globals.")
    parser.add_argument("loader_log", type=Path)
    parser.add_argument("--server-pid")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args(argv)

    summary = summarize(load_records(args.loader_log), server_pid=args.server_pid)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary, args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
