#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "dune-callfunction-active-validation-plan/v1"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def first_hook_pass(observed):
    direct = observed.get("firstObservedHookProbePass")
    if isinstance(direct, dict):
        return direct.get("imageOffset") or ""
    if isinstance(direct, str) and direct:
        return direct
    for row in observed.get("candidates", []) or []:
        if (row.get("observedLog") or {}).get("hookProbePassed"):
            return row.get("imageOffset") or ""
    return ""


def active_candidates(summary):
    rows = summary.get("activeValidationCandidates") or []
    return [row for row in rows if row.get("objectAddress") and row.get("callFunctionCommand")]


def build_read_only_env(hook_offset):
    return [
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET", "value": hook_offset},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_IMAGE_OFFSET", "value": hook_offset},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_INSTALL", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_MAX_OBJECTS", "value": "256"},
        {"name": "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX", "value": "128"},
        {"name": "DUNE_PROBE_LOADER_UE_REFLECTION_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_REFLECTION_FIELD_WALK", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_REFLECTION_MAX_FIELDS", "value": "128"},
    ]


def build_active_env(hook_offset, candidate):
    return [
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_PROBE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET", "value": hook_offset},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_IMAGE_OFFSET", "value": hook_offset},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET", "value": hook_offset},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST", "value": "false"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET", "value": "true"},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS", "value": candidate["objectAddress"]},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND", "value": candidate["callFunctionCommand"]},
        {"name": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_FORCE_CALL", "value": "true"},
    ]


def summarize(args):
    observed = load_json(args.observed_json)
    hook_offset = args.hook_offset or first_hook_pass(observed)
    if not hook_offset:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "blocked",
            "nativeCallAllowed": False,
            "reviewRequired": True,
            "blockers": ["no hook-probe-passed CallFunction target found"],
            "env": [],
        }
    candidates = []
    if args.active_validation_candidates_json and args.active_validation_candidates_json.exists():
        candidates = active_candidates(load_json(args.active_validation_candidates_json))
    if candidates and args.allow_native_call:
        candidate = candidates[0]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "active-validation-ready",
            "hookOffset": hook_offset,
            "nativeCallAllowed": True,
            "reviewRequired": True,
            "selectedCandidate": candidate,
            "requiredPassEvent": "event=ue-call-function-active-validate status=invoked targetEntry=true",
            "env": build_active_env(hook_offset, candidate),
            "blockers": [],
        }
    blockers = []
    if not candidates:
        blockers.append("missing runtime object address plus reviewed CallFunction command candidate")
    if candidates and not args.allow_native_call:
        blockers.append("native active validation candidate exists but --allow-native-call was not set")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "needs-runtime-object-command-evidence",
        "hookOffset": hook_offset,
        "nativeCallAllowed": False,
        "reviewRequired": True,
        "candidateCount": len(candidates),
        "requiredEvidence": [
            "runtime object address",
            "reviewed CallFunction command or command address",
            "operator approval to set active validate native-call env",
        ],
        "nextCanaryPurpose": "read-only runtime object/function discovery while preserving proven CallFunction hook target",
        "env": build_read_only_env(hook_offset),
        "blockers": blockers,
    }


def markdown(report):
    lines = [
        "# CallFunction Active Validation Plan",
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
    parser = argparse.ArgumentParser(description="Plan guarded CallFunction target-entry active validation.")
    parser.add_argument("observed_json", type=Path)
    parser.add_argument("--active-validation-candidates-json", type=Path)
    parser.add_argument("--hook-offset", default="")
    parser.add_argument("--allow-native-call", action="store_true")
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
