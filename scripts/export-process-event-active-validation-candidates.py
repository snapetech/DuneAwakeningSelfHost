#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path


SCHEMA_VERSION = "dune-process-event-active-validation-candidates/v1"
LOG_EVENT_FILTERS = (
    "event=ue-object-native-identity",
    "event=ue-object-array-class-reflection",
    "event=ue-function-native-identity",
    "event=ue-function-param",
    "event=lua-object-registry",
)


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_log_line(line):
    line = line.strip()
    if not line:
        return None
    record = {}
    for index, token in enumerate(line.split()):
        if index == 0 and "=" not in token:
            record["timestamp"] = token
            continue
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        record[key] = value
    return record or None


def load_summary_from_log(path):
    summary = {
        "ueObjectNativeIdentities": [],
        "ueClassObjectIdentities": [],
        "ueFunctionNativeIdentities": [],
        "ueFunctionParams": [],
        "luaObjectRegistry": [],
    }
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not any(marker in line for marker in LOG_EVENT_FILTERS):
                continue
            record = parse_log_line(line)
            if not record:
                continue
            event = record.get("event")
            if event == "ue-object-native-identity":
                summary["ueObjectNativeIdentities"].append(record)
            elif event == "ue-object-array-class-reflection" and record.get("status") == "scanning":
                summary["ueClassObjectIdentities"].append(
                    {
                        "event": event,
                        "status": "promoted",
                        "name": record.get("name", ""),
                        "object": record.get("object", ""),
                        "className": record.get("className", ""),
                        "index": record.get("index", ""),
                        "source": "ue-object-array-class-reflection",
                    }
                )
            elif event == "ue-function-native-identity":
                summary["ueFunctionNativeIdentities"].append(record)
            elif event == "ue-function-param":
                summary["ueFunctionParams"].append(record)
            elif event == "lua-object-registry":
                summary["luaObjectRegistry"].append(record)
    return summary


def strip_function_name(path):
    value = str(path or "")
    if not value:
        return ""
    leaf = value.rsplit(".", 1)[-1]
    if leaf.endswith(":Function"):
        leaf = leaf[: -len(":Function")]
    return leaf


def object_path(row, registry_by_address):
    address = row.get("object") or row.get("address")
    registry = registry_by_address.get(address or "")
    if registry and registry.get("path"):
        return registry["path"]
    name = row.get("name") or row.get("objectName") or "Unknown"
    return f"/RuntimeProbe/{name}"


def function_param_counts(summary):
    counts = defaultdict(int)
    for row in summary.get("ueFunctionParams", []) or []:
        if row.get("status") != "candidate":
            continue
        if row.get("descriptorSane") != "true":
            continue
        function = row.get("function")
        if function:
            counts[function] += 1
    return counts


def registry_paths(summary):
    paths = {}
    for row in summary.get("luaObjectRegistry", []) or []:
        if row.get("status") != "added":
            continue
        address = row.get("address")
        if address and address not in paths:
            paths[address] = row
    return paths


def promoted_objects(summary):
    rows = []
    for row in summary.get("ueObjectNativeIdentities", []) or []:
        if row.get("status") in {"promoted", "skipped"} and row.get("object") and row.get("className"):
            rows.append(row)
    return rows


def promoted_class_objects(summary):
    rows = []
    for row in summary.get("ueClassObjectIdentities", []) or []:
        if row.get("status") == "promoted" and row.get("object") and row.get("name"):
            rows.append(row)
    return rows


def promoted_functions(summary):
    seen = set()
    rows = []
    param_counts = function_param_counts(summary)
    for row in summary.get("ueFunctionNativeIdentities", []) or []:
        if row.get("status") != "promoted":
            continue
        function = row.get("function")
        path = row.get("functionRuntimePath") or row.get("functionPath")
        owner = row.get("name")
        if not function or not path or not owner:
            continue
        key = (function, path, owner)
        if key in seen:
            continue
        seen.add(key)
        item = dict(row)
        item["paramDescriptorCount"] = param_counts.get(function, 0)
        rows.append(item)
    return rows


def side_effect_like_function_name(function_name):
    prefixes = (
        "Add",
        "Apply",
        "Begin",
        "Cancel",
        "Clear",
        "Close",
        "Create",
        "Destroy",
        "Disable",
        "Enable",
        "End",
        "Execute",
        "Fire",
        "Init",
        "Launch",
        "Load",
        "Open",
        "Play",
        "Remove",
        "Reset",
        "Run",
        "Save",
        "Send",
        "Set",
        "Spawn",
        "Start",
        "Stop",
        "Toggle",
        "Trigger",
        "Unload",
        "Update",
        "Wait",
    )
    return str(function_name or "").startswith(prefixes)


def query_like_function_name(function_name):
    prefixes = (
        "Are",
        "Can",
        "Contains",
        "Find",
        "Get",
        "Has",
        "Is",
        "K2_Get",
        "ToString",
        "Was",
    )
    return str(function_name or "").startswith(prefixes)


def preferred_validation_call(function_owner, function_name):
    preferred_pairs = {
        ("Actor", "WasRecentlyRendered"),
        ("PrimitiveComponent", "WasRecentlyRendered"),
        ("SceneComponent", "GetRelativeLocation"),
        ("SceneComponent", "GetComponentLocation"),
    }
    return (str(function_owner or ""), str(function_name or "")) in preferred_pairs


def classify_risk(function_name, object_name, object_class, param_count, source_kind="object"):
    reasons = []
    risk = "moderate"
    if source_kind == "class-object":
        risk = "high"
        reasons.append("class-object-not-instance")
    elif object_name.startswith("Default__"):
        reasons.append("class-default-object")
    else:
        risk = "high"
        reasons.append("non-cdo-object")
    if function_name == "ExecuteUbergraph":
        risk = "high"
        reasons.append("execute-ubergraph")
    elif side_effect_like_function_name(function_name):
        risk = "high"
        reasons.append("side-effect-like-function-name")
    elif query_like_function_name(function_name):
        reasons.append("query-like-function-name")
    if param_count:
        reasons.append("descriptor-backed-params")
    else:
        risk = "high"
        reasons.append("missing-param-descriptors")
    if object_class == "Object" and function_name == "ExecuteUbergraph":
        risk = "high"
        reasons.append("weak-object-function-semantic-value")
    return risk, reasons


def build_candidates(summary, include_high_risk=False, limit=16):
    registry = registry_paths(summary)
    objects_by_class = defaultdict(list)
    for row in promoted_objects(summary):
        objects_by_class[row.get("className", "")].append(row)
    class_objects_by_name = defaultdict(list)
    for row in promoted_class_objects(summary):
        class_objects_by_name[row.get("name", "")].append(row)

    candidates = []
    for function in promoted_functions(summary):
        owner = function.get("name", "")
        object_rows = [(obj, "object") for obj in objects_by_class.get(owner, [])]
        object_rows.extend((obj, "class-object") for obj in class_objects_by_name.get(owner, []))
        for obj, source_kind in object_rows:
            function_name = function.get("functionName") or strip_function_name(function.get("functionRuntimePath"))
            param_count = int(function.get("paramDescriptorCount") or 0)
            risk, reasons = classify_risk(
                function_name,
                obj.get("name", ""),
                obj.get("className", ""),
                param_count,
                source_kind=source_kind,
            )
            if risk == "high" and not include_high_risk:
                continue
            score = 0
            if obj.get("name", "").startswith("Default__"):
                score += 50
            if source_kind == "class-object":
                score -= 25
            if param_count:
                score += 25
            if risk == "moderate":
                score += 10
            if function_name == "ExecuteUbergraph":
                score -= 40
            if side_effect_like_function_name(function_name):
                score -= 60
            if query_like_function_name(function_name):
                score += 20
            if preferred_validation_call(owner, function_name):
                score += 40
            candidate = {
                "objectAddress": obj["object"],
                "functionAddress": function["function"],
                "functionPath": function.get("functionRuntimePath") or function.get("functionPath"),
                "ue4ssFunctionPath": function.get("functionPath", ""),
                "objectPath": object_path(obj, registry),
                "objectName": obj.get("name", ""),
                "objectClass": obj.get("className", ""),
                "objectSourceKind": source_kind,
                "functionName": function_name,
                "functionOwner": owner,
                "functionProvenance": "runtime",
                "callFunctionCommand": function_name,
                "functionParamDescriptorCount": param_count,
                "risk": risk,
                "reviewRequired": True,
                "nativeCallAllowed": False,
                "score": score,
                "reasons": reasons,
            }
            candidates.append(candidate)

    candidates.sort(key=lambda row: (-int(row["score"]), row["risk"], row["functionPath"], row["objectPath"]))
    return candidates[:limit]


def summarize(summary_path, include_high_risk=False, limit=16):
    summary = load_json(summary_path)
    return summarize_payload(summary, summary_path, include_high_risk=include_high_risk, limit=limit)


def summarize_log(log_path, include_high_risk=False, limit=16):
    summary = load_summary_from_log(log_path)
    return summarize_payload(summary, log_path, include_high_risk=include_high_risk, limit=limit)


def summarize_payload(summary, source_path, include_high_risk=False, limit=16):
    candidates = build_candidates(summary, include_high_risk=include_high_risk, limit=limit)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceSummary": str(source_path),
        "candidateCount": len(candidates),
        "includeHighRisk": include_high_risk,
        "nativeCallAllowed": False,
        "reviewRequired": True,
        "sourceCounts": {
            "ueObjectNativeIdentities": len(summary.get("ueObjectNativeIdentities", []) or []),
            "ueClassObjectIdentities": len(summary.get("ueClassObjectIdentities", []) or []),
            "ueFunctionNativeIdentities": len(summary.get("ueFunctionNativeIdentities", []) or []),
            "ueFunctionParams": len(summary.get("ueFunctionParams", []) or []),
            "luaObjectRegistry": len(summary.get("luaObjectRegistry", []) or []),
        },
        "candidates": candidates,
        "activeValidationCandidates": [
            {
                "objectAddress": row["objectAddress"],
                "functionAddress": row["functionAddress"],
                "functionPath": row["functionPath"],
                "objectPath": row["objectPath"],
                "functionProvenance": row["functionProvenance"],
                "callFunctionCommand": row["callFunctionCommand"],
            }
            for row in candidates
        ],
    }


def markdown(report):
    lines = [
        "# ProcessEvent Active Validation Candidates",
        "",
        f"- Schema: `{report['schemaVersion']}`",
        f"- Candidates: `{report['candidateCount']}`",
        f"- Review required: `{str(report['reviewRequired']).lower()}`",
        f"- Native call allowed: `{str(report['nativeCallAllowed']).lower()}`",
        "",
        "| Rank | Risk | Score | Object | Function | Params | Reasons |",
        "| ---: | --- | ---: | --- | --- | ---: | --- |",
    ]
    for index, row in enumerate(report["candidates"], 1):
        lines.append(
            f"| {index} | `{row['risk']}` | {row['score']} | "
            f"`{row['objectPath']}` `{row['objectAddress']}` | "
            f"`{row['functionPath']}` `{row['functionAddress']}` | "
            f"{row['functionParamDescriptorCount']} | "
            f"`{', '.join(row['reasons'])}` |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Export reviewable ProcessEvent active-validation candidates from a loader scan summary."
    )
    parser.add_argument("summary_json", nargs="?", type=Path, help="JSON summary from summarize-*-loader-scan.py")
    parser.add_argument("--loader-log", type=Path, help="raw loader log to stream directly")
    parser.add_argument("--include-high-risk", action="store_true", help="include weak/high-risk candidates for review")
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    if args.loader_log:
        report = summarize_log(args.loader_log, include_high_risk=args.include_high_risk, limit=args.limit)
    elif args.summary_json:
        report = summarize(args.summary_json, include_high_risk=args.include_high_risk, limit=args.limit)
    else:
        parser.error("summary_json or --loader-log is required")
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(markdown(report), end="")


if __name__ == "__main__":
    main()
