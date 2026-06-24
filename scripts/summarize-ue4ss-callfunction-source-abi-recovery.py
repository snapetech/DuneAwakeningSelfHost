#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-callfunction-source-abi-recovery/v1"

CALL_FUNCTION_TYPEDEF_RE = re.compile(
    r"typedef\s+int\s+\(\s*\*\s*(?P<name>CallFunctionByNameFn)\s*\)"
    r"\((?P<args>[^;]+)\);"
)


def load_json(path):
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.is_file():
        return {}
    try:
        return json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}


def bool_from_ready(data, key):
    ready = data.get("ready", {})
    if isinstance(ready, dict):
        return bool(ready.get(key))
    return False


def parse_loader_contract(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    typedefs = []
    for match in CALL_FUNCTION_TYPEDEF_RE.finditer(text):
        args = " ".join(match.group("args").split())
        typedefs.append(
            {
                "name": match.group("name"),
                "arguments": args,
                "argumentCount": len([part for part in args.split(",") if part.strip()]),
                "returnType": "int",
            }
        )
    return {
        "path": str(path),
        "typedefs": typedefs,
        "typedefCount": len(typedefs),
        "hasSysvCallFunctionTypedef": any(
            row["name"] == "CallFunctionByNameFn" and row["argumentCount"] == 5
            for row in typedefs
        ),
        "hasLiveHookReplacement": "call_function_live_hook_replacement" in text,
        "hasActiveValidation": "run_call_function_active_validation" in text,
        "hasTargetEntryValidation": "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET" in text,
        "hasNativeLuaExecutorState": "lua_get_call_function_native_executor_state_callback" in text,
        "hasNativeLuaInvoke": "lua_invoke_call_function_native_callback" in text,
        "hasRegisterPreHook": "RegisterCallFunctionByNameWithArgumentsPreHook" in text,
        "hasRegisterPostHook": "RegisterCallFunctionByNameWithArgumentsPostHook" in text,
    }


def target_recovery_state(target_recovery):
    hits = target_recovery.get("callFunctionStringHits", []) or []
    rejected = [row for row in hits if row.get("promotable") is False]
    return {
        "status": target_recovery.get("status", "missing"),
        "rejectedStringHitCount": len(rejected),
        "promotableStringHitCount": len([row for row in hits if row.get("promotable") is True]),
        "hasDataflowArtifacts": bool(target_recovery.get("dataflowArtifacts")),
    }


def readiness_state(readiness):
    return {
        "ueCallFunctionHookProbe": bool_from_ready(readiness, "ueCallFunctionHookProbe"),
        "ueCallFunctionHookRuntimeTarget": bool_from_ready(readiness, "ueCallFunctionHookRuntimeTarget"),
        "ueCallFunctionLiveHookRuntimeTarget": bool_from_ready(readiness, "ueCallFunctionLiveHookRuntimeTarget"),
        "ueCallFunctionActiveValidation": bool_from_ready(readiness, "ueCallFunctionActiveValidation"),
        "ueCallFunctionLiveLuaDispatch": bool_from_ready(readiness, "ueCallFunctionLiveLuaDispatch"),
        "luaCallFunctionNativeExecutorState": bool_from_ready(readiness, "luaCallFunctionNativeExecutorState"),
        "luaCallFunctionNativeInvoke": bool_from_ready(readiness, "luaCallFunctionNativeInvoke"),
        "luaCallFunctionNativeInvokeNonSelfTestInvoked": bool_from_ready(
            readiness,
            "luaCallFunctionNativeInvokeNonSelfTestInvoked",
        ),
    }


def summarize(loader, readiness=None, target_recovery=None):
    contract = parse_loader_contract(loader)
    target = target_recovery_state(target_recovery or {})
    ready = readiness_state(readiness or {})
    blockers = []
    if not contract["hasSysvCallFunctionTypedef"]:
        blockers.append("loader lacks CallFunctionByNameFn SysV five-argument typedef")
    for key in (
        "hasLiveHookReplacement",
        "hasActiveValidation",
        "hasTargetEntryValidation",
        "hasNativeLuaExecutorState",
        "hasNativeLuaInvoke",
        "hasRegisterPreHook",
        "hasRegisterPostHook",
    ):
        if not contract[key]:
            blockers.append(f"loader contract missing {key}")
    if target["promotableStringHitCount"] == 0:
        blockers.append("no promotable CallFunctionByNameWithArguments string-derived target")
    if not ready["ueCallFunctionHookRuntimeTarget"]:
        blockers.append("no non-self-test CallFunction hook runtime target proof")
    if not ready["ueCallFunctionActiveValidation"]:
        blockers.append("no active CallFunction target-entry validation proof")
    source_abi_ready = not [
        blocker
        for blocker in blockers
        if blocker.startswith("loader")
    ]
    complete = not blockers
    if target["promotableStringHitCount"] == 0 and not ready["ueCallFunctionHookRuntimeTarget"]:
        next_step = "recover a non-self-test CallFunctionByNameWithArguments target, then run hook and target-entry active validation"
    elif source_abi_ready:
        next_step = "run guarded hook/live active validation against the recovered CallFunction target"
    else:
        next_step = "finish the loader-side CallFunction ABI bridge before selecting a runtime target"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "complete": complete,
        "sourceAbiReady": source_abi_ready,
        "loaderContract": contract,
        "targetRecovery": target,
        "readiness": ready,
        "blockers": blockers,
        "nextStep": next_step,
    }


def markdown(summary):
    contract = summary["loaderContract"]
    lines = ["# UE4SS CallFunction Source ABI Recovery", ""]
    lines.append(f"- Complete: `{str(summary['complete']).lower()}`")
    lines.append(f"- Source ABI ready: `{str(summary['sourceAbiReady']).lower()}`")
    lines.append(f"- Loader: `{contract['path']}`")
    lines.append(f"- Typedefs: `{contract['typedefCount']}`")
    lines.append(f"- SysV CallFunction typedef: `{str(contract['hasSysvCallFunctionTypedef']).lower()}`")
    lines.append(f"- Active validation: `{str(contract['hasActiveValidation']).lower()}`")
    lines.append(f"- Target-entry validation: `{str(contract['hasTargetEntryValidation']).lower()}`")
    lines.append(f"- Native Lua executor state: `{str(contract['hasNativeLuaExecutorState']).lower()}`")
    lines.append(f"- Native Lua invoke: `{str(contract['hasNativeLuaInvoke']).lower()}`")
    lines.append("")
    lines.append("## Typedefs")
    lines.append("")
    for row in contract.get("typedefs", []):
        lines.append(f"- `{row['name']}` returns=`{row['returnType']}` args=`{row['argumentCount']}` `{row['arguments']}`")
    lines.append("")
    target = summary["targetRecovery"]
    lines.append("## Target Recovery")
    lines.append("")
    lines.append(f"- Status: `{target['status']}`")
    lines.append(f"- Rejected string hits: `{target['rejectedStringHitCount']}`")
    lines.append(f"- Promotable string hits: `{target['promotableStringHitCount']}`")
    lines.append(f"- Dataflow artifacts present: `{str(target['hasDataflowArtifacts']).lower()}`")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    for blocker in summary.get("blockers", []):
        lines.append(f"- {blocker}")
    if not summary.get("blockers"):
        lines.append("- none")
    lines.append("")
    lines.append(f"Next step: {summary['nextStep']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize UE4SS CallFunction source-level ABI recovery state.")
    parser.add_argument("--loader", default="tools/linux-server-loader/dune_server_probe_loader.c")
    parser.add_argument("--readiness-json", default="build/server-current-anchor-prep/ue4ss-readiness.json")
    parser.add_argument(
        "--target-recovery-json",
        default="build/server-current-anchor-prep/callfunction-target-recovery-status.json",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize(
        args.loader,
        readiness=load_json(args.readiness_json),
        target_recovery=load_json(args.target_recovery_json),
    )
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(markdown(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
