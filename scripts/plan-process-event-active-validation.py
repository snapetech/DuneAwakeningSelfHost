#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "dune-process-event-active-validation-plan/v1"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def first_process_event_target(observed):
    direct_hook_offset = observed.get("hookOffset")
    if isinstance(direct_hook_offset, str) and direct_hook_offset:
        return direct_hook_offset
    direct = observed.get("firstObservedProcessEventHookPass") or observed.get("firstObservedHookProbePass")
    if isinstance(direct, dict):
        return direct.get("imageOffset") or direct.get("fileOffset") or ""
    if isinstance(direct, str) and direct:
        return direct
    for row in observed.get("hookProbeShortlist", []) or []:
        target = row.get("topTarget") if isinstance(row.get("topTarget"), dict) else row
        if str(target.get("targetName") or row.get("targetName") or "") in {"ProcessEvent", "UObject::ProcessEvent"}:
            return target.get("imageOffset") or target.get("fileOffset") or row.get("imageOffset") or ""
    for row in observed.get("candidates", []) or []:
        observed_log = row.get("observedLog") or {}
        if observed_log.get("hookProbePassed") or observed_log.get("liveHookInstalled"):
            if str(row.get("targetName") or "ProcessEvent") in {"ProcessEvent", "UObject::ProcessEvent"}:
                return row.get("imageOffset") or row.get("fileOffset") or ""
    for path in (
        ("nextCanaryContract", "processEventRuntimeEvidence"),
        ("processEventRuntimeEvidence",),
    ):
        current = observed
        for key in path:
            current = current.get(key) if isinstance(current, dict) else None
        if not isinstance(current, dict):
            continue
        for key in ("hookOffset", "imageOffset", "fileOffset", "targetImageOffset"):
            value = current.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def active_candidates(summary):
    rows = summary.get("activeValidationCandidates") or summary.get("candidates") or []
    candidates = []
    for row in rows:
        if not row.get("objectAddress") or not row.get("functionAddress"):
            continue
        candidates.append(row)
    return candidates


def reviewed_native_candidates(summary):
    return [
        row
        for row in active_candidates(summary)
        if row.get("nativeCallAllowed") is True and row.get("reviewRequired") is not True
    ]


def build_read_only_env(hook_offset):
    return [
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET", "value": hook_offset},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_IMAGE_OFFSET", "value": hook_offset},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_INSTALL", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET", "value": hook_offset},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_LOG_CALLS", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_CALL_LOG_LIMIT", "value": "16"},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_DISPATCH_SELF_TEST", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_SYNTHETIC_RUNTIME_VALIDATE", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_MAX_OBJECTS", "value": "32768"},
        {"name": "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX", "value": "512"},
        {"name": "DUNE_PROBE_LOADER_UE_REFLECTION_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_WALK", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_REFLECTION_PROPERTY_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_REFLECTION_VALUE_PROBE", "value": "true"},
    ]


def build_synthetic_runtime_env(hook_offset):
    env = build_read_only_env(hook_offset)
    values = {item["name"]: item for item in env}
    values["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE"]["value"] = "true"
    values["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"]["value"] = "false"
    values["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_SYNTHETIC_RUNTIME_VALIDATE"]["value"] = "true"
    env.extend(
        [
            {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET", "value": "true"},
            {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL", "value": "true"},
            {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_LUA_DISPATCH", "value": "true"},
        ]
    )
    return env


def build_active_env(hook_offset, candidate):
    env = build_read_only_env(hook_offset)
    values = {item["name"]: item for item in env}
    values["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE"]["value"] = "true"
    values["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL"]["value"] = "true"
    values["DUNE_PROBE_LOADER_UE_PROCESS_EVENT_SYNTHETIC_RUNTIME_VALIDATE"]["value"] = "false"
    env.extend(
        [
            {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET", "value": "true"},
            {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS", "value": candidate["objectAddress"]},
            {"name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_ADDRESS", "value": candidate["functionAddress"]},
        ]
    )
    if candidate.get("paramsAddress"):
        env.append(
            {
                "name": "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_PARAMS_ADDRESS",
                "value": candidate["paramsAddress"],
            }
        )
    return env


def summarize(args):
    observed = load_json(args.observed_json)
    hook_offset = args.hook_offset or first_process_event_target(observed)
    if not hook_offset:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "blocked",
            "nativeCallAllowed": False,
            "reviewRequired": True,
            "blockers": ["no ProcessEvent hook target found"],
            "env": [],
        }
    candidates = []
    reviewed = []
    if args.active_validation_candidates_json and args.active_validation_candidates_json.exists():
        payload = load_json(args.active_validation_candidates_json)
        candidates = active_candidates(payload)
        reviewed = reviewed_native_candidates(payload)
    if reviewed and args.allow_native_call:
        candidate = reviewed[0]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "active-validation-ready",
            "hookOffset": hook_offset,
            "nativeCallAllowed": True,
            "reviewRequired": False,
            "selectedCandidate": candidate,
            "requiredPassEvent": "event=ue-process-event-active-validate status=invoked targetEntry=true originalCalled=true",
            "env": build_active_env(hook_offset, candidate),
            "blockers": [],
        }
    blockers = []
    if not candidates:
        blockers.append("missing runtime object/function active-validation candidate")
    if candidates and not reviewed:
        blockers.append("no candidate is explicitly reviewed with nativeCallAllowed=true and reviewRequired=false")
    if reviewed and not args.allow_native_call:
        blockers.append("reviewed native ProcessEvent candidate exists but --allow-native-call was not set")
    synthetic_runtime_validate = getattr(args, "synthetic_runtime_validate", False)
    if synthetic_runtime_validate:
        blockers.append(
            "strict native active validation remains blocked until a reviewed real UObject/UFunction candidate can call the original trampoline"
        )
    env = build_synthetic_runtime_env(hook_offset) if synthetic_runtime_validate else build_read_only_env(hook_offset)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": (
            "synthetic-runtime-validation-ready"
            if synthetic_runtime_validate
            else "needs-reviewed-runtime-object-function-evidence"
        ),
        "hookOffset": hook_offset,
        "nativeCallAllowed": False,
        "reviewRequired": not synthetic_runtime_validate,
        "candidateCount": len(candidates),
        "reviewedNativeCandidateCount": len(reviewed),
        "requiredEvidence": [
            "runtime UObject address",
            "runtime UFunction address",
            "reviewed candidate JSON with nativeCallAllowed=true and reviewRequired=false",
            "operator opt-in via --allow-native-call",
        ],
        "nextCanaryPurpose": (
            "prove no-native ProcessEvent live-hook runtime context, descriptor params, and Lua routing through the patched target entry"
            if synthetic_runtime_validate
            else "preserve proven ProcessEvent hook target and collect safer runtime object/function candidates without native invocation"
        ),
        "env": env,
        "blockers": blockers,
    }


def markdown(report):
    lines = [
        "# ProcessEvent Active Validation Plan",
        "",
        f"- Schema: `{report['schemaVersion']}`",
        f"- Status: `{report['status']}`",
        f"- Hook offset: `{report.get('hookOffset', '')}`",
        f"- Native call allowed: `{str(report.get('nativeCallAllowed', False)).lower()}`",
        f"- Review required: `{str(report.get('reviewRequired', True)).lower()}`",
        "",
    ]
    if report.get("blockers"):
        lines.extend(["## Blockers", ""])
        for blocker in report["blockers"]:
            lines.append(f"- {blocker}")
        lines.append("")
    lines.extend(["## Env", ""])
    for item in report.get("env", []):
        lines.append(f"{item['name']}={item['value']}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Plan guarded ProcessEvent target-entry active validation.")
    parser.add_argument("observed_json", type=Path)
    parser.add_argument("--active-validation-candidates-json", type=Path)
    parser.add_argument("--hook-offset", default="")
    parser.add_argument("--allow-native-call", action="store_true")
    parser.add_argument(
        "--synthetic-runtime-validate",
        action="store_true",
        help="emit a no-native synthetic runtime ProcessEvent validation through the patched target entry",
    )
    parser.add_argument("--format", choices=("json", "markdown", "env"), default="json")
    args = parser.parse_args()
    report = summarize(args)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.format == "env":
        for item in report.get("env", []):
            print(f"{item['name']}={item['value']}")
    else:
        print(markdown(report), end="")


if __name__ == "__main__":
    main()
