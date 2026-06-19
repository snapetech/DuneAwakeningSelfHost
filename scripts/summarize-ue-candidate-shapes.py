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


def load_records(path):
    for script in SCAN_SUMMARY_SCRIPTS:
        if script.exists():
            return import_script(script, "summarize_loader_scan_for_candidate_shapes").load_records(path)
    raise RuntimeError("missing summarize-linux-loader-scan.py or summarize-client-loader-scan.py")


def parse_int(value, default=0):
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return default


def same_anchor(record, candidate):
    anchor = (record.get("anchor") or record.get("base") or record.get("pool") or "").lower()
    addresses = {address.lower() for address in candidate.get("addresses", [])}
    return bool(anchor and anchor in addresses)


def candidate_label_matches(value, candidate):
    label = str(value or "")
    name = str(candidate.get("name", ""))
    return bool(label and name and (label == name or label.startswith(f"{name}_") or label.startswith(f"{name}[")))


def candidate_key(record):
    return (record.get("name", ""), record.get("imageOffset", ""))


def candidate_template(record):
    return {
        "name": record.get("name", ""),
        "imageOffset": record.get("imageOffset", ""),
        "address": record.get("address", ""),
        "addresses": [record.get("address", "")] if record.get("address", "") else [],
        "absolute": record.get("absolute", ""),
        "events": [],
        "statusCounts": {},
        "pointer": {},
        "layout": {"readable": 0, "mappedSlots": 0, "executableSlots": 0},
        "uobject": {},
        "objectArray": {
            "finished": 0,
            "registered": 0,
            "scanned": 0,
            "empty": 0,
            "registeredItems": 0,
            "shape": {},
            "implausibleHeaders": 0,
            "plausibleHeaders": 0,
        },
        "runtimeRegistry": {
            "objectRuntime": 0,
            "decodedAliasRuntime": 0,
            "objectArrayRuntime": 0,
            "nativeIdentityPromoted": 0,
            "sources": [],
        },
        "fname": {"decoded": 0, "ready": 0, "readySources": []},
    }


def attach_record(candidate, record):
    event = record.get("event", "")
    status = record.get("status", "")
    candidate["events"].append(event)
    candidate["statusCounts"][f"{event}:{status}"] = candidate["statusCounts"].get(f"{event}:{status}", 0) + 1
    if event == "ue-pointer" and same_anchor(record, candidate):
        current = candidate.get("pointer", {})
        if current.get("status") == "target-mapped" and status != "target-mapped":
            return
        candidate["pointer"] = {
            "status": status,
            "value": record.get("value", ""),
            "readable": record.get("readable", ""),
            "writable": record.get("writable", ""),
            "executable": record.get("executable", ""),
            "perms": record.get("perms", ""),
        }
    elif event == "ue-layout" and same_anchor(record, candidate):
        if status == "target-readable":
            candidate["layout"]["readable"] += 1
            candidate["layout"]["target"] = record.get("target", "")
            candidate["layout"]["slots"] = parse_int(record.get("slots", "0"))
    elif event == "ue-layout-slot":
        target = candidate.get("pointer", {}).get("value", "")
        if target and record.get("target", "").lower() == target.lower():
            if status == "target-mapped":
                candidate["layout"]["mappedSlots"] += 1
                if record.get("executable") == "true":
                    candidate["layout"]["executableSlots"] += 1
    elif event == "ue-uobject" and same_anchor(record, candidate):
        candidate["uobject"] = {
            "status": status,
            "target": record.get("target", ""),
            "vtableMapped": record.get("vtableMapped", ""),
            "classMapped": record.get("classMapped", ""),
            "objectFlags": record.get("objectFlags", ""),
            "internalIndex": record.get("internalIndex", ""),
        }
    elif event == "ue-object-array" and same_anchor(record, candidate):
        if status == "header-implausible":
            candidate["objectArray"]["implausibleHeaders"] += 1
        if status == "empty":
            candidate["objectArray"]["empty"] += 1
        if status == "finished":
            candidate["objectArray"]["finished"] += 1
            candidate["objectArray"]["registered"] += parse_int(record.get("registered", "0"))
            candidate["objectArray"]["scanned"] += parse_int(record.get("scanned", "0"))
    elif event == "ue-object-array-shape" and same_anchor(record, candidate):
        candidate["objectArray"]["shape"] = {
            "status": status,
            "mode": record.get("mode", ""),
            "countsPlausible": record.get("countsPlausible", ""),
            "chunkSlotReadable": record.get("chunkSlotReadable", ""),
            "firstChunk": record.get("firstChunk", ""),
            "firstChunkMapped": record.get("firstChunkMapped", ""),
            "maxElements": record.get("maxElements", ""),
            "numElements": record.get("numElements", ""),
            "maxChunks": record.get("maxChunks", ""),
            "numChunks": record.get("numChunks", ""),
        }
        if status == "header-implausible" or record.get("countsPlausible") == "false":
            candidate["objectArray"]["implausibleHeaders"] += 1
        elif status == "header-plausible" or record.get("countsPlausible") == "true":
            candidate["objectArray"]["plausibleHeaders"] += 1
    elif event == "ue-object-array-item" and candidate_label_matches(record.get("name", ""), candidate):
        if status == "registered":
            candidate["objectArray"]["registeredItems"] += 1
            candidate["runtimeRegistry"]["objectArrayRuntime"] += 1
    elif event == "ue-fname" and record.get("status") == "decoded":
        if candidate_label_matches(record.get("objectName", ""), candidate):
            candidate["fname"]["decoded"] += 1
            candidate["runtimeRegistry"]["decodedAliasRuntime"] += 1
    elif event == "lua-object-registry" and record.get("registryProvenance") == "runtime":
        source = record.get("source", "")
        if (
            source in {"ue-uobject", "ue-uobject-fname", "ue-object-array", "ue-object-array-fname"}
            and (
                candidate_label_matches(record.get("name", ""), candidate)
                or candidate_label_matches(record.get("path", ""), candidate)
                or candidate_label_matches(record.get("aliasOf", ""), candidate)
            )
        ):
            candidate["runtimeRegistry"]["objectRuntime"] += 1
            if source in {"ue-uobject-fname", "ue-object-array-fname"}:
                candidate["runtimeRegistry"]["decodedAliasRuntime"] += 1
            if source in {"ue-object-array", "ue-object-array-fname"}:
                candidate["runtimeRegistry"]["objectArrayRuntime"] += 1
            if source and source not in candidate["runtimeRegistry"]["sources"]:
                candidate["runtimeRegistry"]["sources"].append(source)
    elif event == "ue-object-native-identity" and record.get("status") == "promoted":
        source = record.get("source", "")
        if (
            source == "ue-uobject"
            and candidate_label_matches(record.get("name", ""), candidate)
        ) or (
            source == "ue-object-array"
            and candidate_label_matches(record.get("arrayName", ""), candidate)
        ):
            candidate["runtimeRegistry"]["nativeIdentityPromoted"] += 1
            if source and source not in candidate["runtimeRegistry"]["sources"]:
                candidate["runtimeRegistry"]["sources"].append(source)
    elif event in {"ue-fname-start", "ue-fname-finish"} and same_anchor(record, candidate):
        if status == "ready":
            candidate["fname"]["ready"] += 1
            source = record.get("source", "")
            if source and source not in candidate["fname"]["readySources"]:
                candidate["fname"]["readySources"].append(source)


def verdict(candidate):
    pointer = candidate.get("pointer", {})
    uobject = candidate.get("uobject", {})
    array = candidate.get("objectArray", {})
    layout = candidate.get("layout", {})
    fname = candidate.get("fname", {})
    registry = candidate.get("runtimeRegistry", {})
    if candidate.get("name") in {"FNamePool", "GName", "GNames"} and fname.get("ready", 0) > 0:
        return "promising-fname-pool", "FNamePool probe reported ready"
    if (
        array.get("registered", 0) > 0
        and candidate.get("fname", {}).get("decoded", 0) > 0
        and registry.get("objectArrayRuntime", 0) > 0
        and registry.get("decodedAliasRuntime", 0) > 0
        and registry.get("nativeIdentityPromoted", 0) > 0
    ):
        return "promotable-object-array", "object array produced runtime registry, decoded alias, and native identity evidence"
    if array.get("registered", 0) > 0 and candidate.get("fname", {}).get("decoded", 0) > 0:
        return "promising-object-array", "object array registered objects and decoded names but lacks full runtime registry/native identity proof"
    if uobject.get("status") == "candidate" and uobject.get("classMapped") == "true" and uobject.get("vtableMapped") == "true":
        return "promising-uobject", "UObject-shaped candidate has mapped class and vtable"
    if pointer.get("executable") == "true" or layout.get("executableSlots", 0) > 0:
        return "weak-code-pointer", "candidate points into executable code/table context"
    if uobject.get("status") == "candidate" and (
        uobject.get("classMapped") == "false" or uobject.get("vtableMapped") == "false"
    ):
        return "rejected-uobject-shape", "UObject candidate lacks mapped class or vtable"
    if pointer.get("status") == "null":
        return "rejected-null", "candidate anchor points to null"
    if pointer.get("status") == "anchor-unmapped":
        return "rejected-anchor-unmapped", "candidate anchor is not mapped"
    if array.get("implausibleHeaders", 0) > 0 and array.get("plausibleHeaders", 0) == 0:
        return "rejected-object-array-header", "object-array header counters are implausible"
    if array.get("finished", 0) and array.get("registered", 0) == 0:
        return "rejected-empty-object-array", "object-array probe finished without registered objects"
    if array.get("empty", 0):
        return "rejected-empty-object-array", "object-array header reports empty"
    if layout.get("readable", 0) > 0 or pointer.get("status") == "target-mapped":
        return "weak-mapped", "candidate mapped but lacks UObject/object-array/FName proof"
    return "unknown", "no decisive pointer/layout/UObject/object-array evidence"


def summarize_records(records):
    candidates = {}
    order = []
    for record in records:
        if record.get("event") == "ue-candidate-global" and record.get("status") == "added":
            key = candidate_key(record)
            if key not in candidates:
                candidates[key] = candidate_template(record)
                order.append(key)
            elif record.get("address", "") and record.get("address", "") not in candidates[key]["addresses"]:
                candidates[key]["addresses"].append(record.get("address", ""))
    for record in records:
        if record.get("event") == "ue-candidate-global":
            continue
        for candidate in candidates.values():
            if (
                candidate_label_matches(record.get("name", ""), candidate)
                or candidate_label_matches(record.get("objectName", ""), candidate)
                or candidate_label_matches(record.get("arrayName", ""), candidate)
                or candidate_label_matches(record.get("path", ""), candidate)
                or candidate_label_matches(record.get("aliasOf", ""), candidate)
                or (record.get("event") in {"ue-fname-start", "ue-fname-finish"} and same_anchor(record, candidate))
            ):
                attach_record(candidate, record)
    rows = []
    for key in order:
        row = candidates[key]
        row["verdict"], row["reason"] = verdict(row)
        rows.append(row)
    return {
        "schemaVersion": "dune-ue-candidate-shapes/v1",
        "candidateCount": len(rows),
        "verdictCounts": dict(sorted(Counter(row["verdict"] for row in rows).items())),
        "candidates": rows,
    }


def summarize_paths(paths):
    records = []
    for path in paths:
        records.extend(load_records(path))
    return summarize_records(records)


def markdown(summary):
    lines = ["# UE Candidate Shape Summary", ""]
    lines.append(f"- Candidates: `{summary['candidateCount']}`")
    lines.append(f"- Verdicts: `{summary['verdictCounts']}`")
    lines.append("")
    for row in summary["candidates"]:
        lines.append(
            f"- `{row['name']}` `{row['imageOffset']}` verdict=`{row['verdict']}` reason=`{row['reason']}`"
        )
        pointer = row.get("pointer", {})
        if pointer:
            lines.append(
                f"  - pointer status=`{pointer.get('status', '')}` value=`{pointer.get('value', '')}` "
                f"exec=`{pointer.get('executable', '')}` perms=`{pointer.get('perms', '')}`"
            )
        uobject = row.get("uobject", {})
        if uobject:
            lines.append(
                f"  - uobject status=`{uobject.get('status', '')}` classMapped=`{uobject.get('classMapped', '')}` "
                f"vtableMapped=`{uobject.get('vtableMapped', '')}`"
            )
        array = row.get("objectArray", {})
        shape = array.get("shape", {})
        if shape:
            lines.append(
                f"  - objectArrayShape status=`{shape.get('status', '')}` countsPlausible=`{shape.get('countsPlausible', '')}` "
                f"chunkSlotReadable=`{shape.get('chunkSlotReadable', '')}` firstChunkMapped=`{shape.get('firstChunkMapped', '')}` "
                f"numElements=`{shape.get('numElements', '')}` numChunks=`{shape.get('numChunks', '')}`"
            )
        if array.get("finished") or array.get("empty"):
            lines.append(
                f"  - objectArray finished=`{array.get('finished', 0)}` scanned=`{array.get('scanned', 0)}` "
                f"registered=`{array.get('registered', 0)}` registeredItems=`{array.get('registeredItems', 0)}` "
                f"empty=`{array.get('empty', 0)}`"
            )
        fname = row.get("fname", {})
        if fname.get("ready") or fname.get("decoded"):
            lines.append(
                f"  - fname ready=`{fname.get('ready', 0)}` decoded=`{fname.get('decoded', 0)}` "
                f"sources=`{fname.get('readySources', [])}`"
            )
        registry = row.get("runtimeRegistry", {})
        if any(registry.get(name, 0) for name in ("objectRuntime", "decodedAliasRuntime", "objectArrayRuntime", "nativeIdentityPromoted")):
            lines.append(
                f"  - runtimeRegistry objectRuntime=`{registry.get('objectRuntime', 0)}` "
                f"decodedAliasRuntime=`{registry.get('decodedAliasRuntime', 0)}` "
                f"objectArrayRuntime=`{registry.get('objectArrayRuntime', 0)}` "
                f"nativeIdentityPromoted=`{registry.get('nativeIdentityPromoted', 0)}` "
                f"sources=`{registry.get('sources', [])}`"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify UE candidate-global runtime shape evidence from loader logs.")
    parser.add_argument("loader_log", type=Path, nargs="+")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize_paths(args.loader_log)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
