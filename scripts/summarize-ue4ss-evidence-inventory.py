#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


TARGET_GROUPS = ("names", "objects", "world", "dispatch", "package")
TARGET_GROUP_NEXT_ACTIONS = {
    "names": "recover target-image FNamePool/GNames anchor evidence",
    "objects": "recover target-image GUObjectArray/GObjects anchor evidence",
    "world": "recover target-image GWorld/GEngine anchor evidence",
    "dispatch": "recover target-image ProcessEvent/CallFunction dispatch anchor evidence",
    "package": "recover target-image StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName package-loading anchor evidence",
}
DEFAULT_SEARCH_ROOTS = (
    Path("build"),
    Path("backups"),
    Path("/tmp"),
)


def load_json(path):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def group_counts(coverage):
    groups = {}
    for name, group in sorted((coverage.get("groups") or {}).items()):
        if not isinstance(group, dict):
            continue
        groups[name] = {
            "present": int(group.get("present", 0) or 0),
            "total": int(group.get("total", 0) or 0),
            "targetPresent": int(group.get("targetPresent", 0) or 0),
            "loaderPresent": int(group.get("loaderPresent", 0) or 0),
            "unknownPresent": int(group.get("unknownPresent", 0) or 0),
            "targetComplete": bool(group.get("targetComplete", False)),
        }
    return groups


def coverage_summary(coverage):
    if not isinstance(coverage, dict):
        return {"provided": False, "groups": {}, "missingTargetGroups": list(TARGET_GROUPS)}
    groups = group_counts(coverage)
    target_fields = any(
        key in coverage
        for key in (
            "readyForTargetObjectDiscovery",
            "readyForTargetHookPlanning",
            "readyForTargetPackageLoading",
            "targetCoverageFieldsPresent",
        )
    ) or any("targetPresent" in group for group in (coverage.get("groups") or {}).values() if isinstance(group, dict))
    missing_target = [
        name for name in TARGET_GROUPS
        if int(groups.get(name, {}).get("targetPresent", 0) or 0) <= 0
    ]
    present_groups = [
        name for name in TARGET_GROUPS
        if int(groups.get(name, {}).get("present", 0) or 0) > 0
    ]
    return {
        "provided": True,
        "schemaVersion": coverage.get("schemaVersion", ""),
        "targetCoverageFieldsPresent": bool(target_fields),
        "readyForTargetObjectDiscovery": bool(coverage.get("readyForTargetObjectDiscovery", False)),
        "readyForTargetHookPlanning": bool(coverage.get("readyForTargetHookPlanning", False)),
        "readyForTargetPackageLoading": bool(coverage.get("readyForTargetPackageLoading", False)),
        "readyForObjectDiscovery": bool(coverage.get("readyForObjectDiscovery", False)) or all(
            name in present_groups for name in ("names", "objects", "world")
        ),
        "readyForHookPlanning": bool(coverage.get("readyForHookPlanning", False)) or all(
            name in present_groups for name in ("names", "objects", "world", "dispatch")
        ),
        "readyForPackageLoading": bool(coverage.get("readyForPackageLoading", False)) or "package" in present_groups,
        "missingTargetGroups": missing_target,
        "presentGroups": present_groups,
        "groups": groups,
    }


def readiness_summary(readiness):
    ready = readiness.get("ready", {}) if isinstance(readiness, dict) else {}
    contract = readiness.get("liveTargetImageCanaryContract", {}) if isinstance(readiness, dict) else {}
    missing_live = list(contract.get("missingKeys", []) or []) if isinstance(contract, dict) else []
    live_contract_ready = bool(contract.get("ready", False)) if isinstance(contract, dict) else False
    lua_api_complete = bool(ready.get("ue4ssLuaApiComplete", False))
    live_groups = contract.get("groups", {}) if isinstance(contract, dict) else {}
    group_missing = {}
    group_ready = {}
    if isinstance(live_groups, dict):
        for group_name, group in sorted(live_groups.items()):
            if not isinstance(group, dict):
                continue
            group_missing[group_name] = list(group.get("missingKeys", []) or [])
            group_ready[group_name] = bool(group.get("ready", False))
    blocked_groups = [
        name for name, is_ready in group_ready.items()
        if not is_ready or group_missing.get(name)
    ]
    contradictions = []
    if lua_api_complete and (not live_contract_ready or missing_live or blocked_groups):
        contradictions.append("ue4ssLuaApiComplete is true without a ready live target-image contract")
    if live_contract_ready and missing_live:
        contradictions.append("liveTargetImageCanaryContract.ready is true while missingKeys is non-empty")
    if live_contract_ready and blocked_groups:
        contradictions.append("liveTargetImageCanaryContract.ready is true while one or more groups are blocked")
    for group_name in blocked_groups:
        if group_ready.get(group_name) and group_missing.get(group_name):
            contradictions.append(f"liveTargetImageCanaryContract group {group_name} is ready while missingKeys is non-empty")
    strict_live_ready = live_contract_ready and not missing_live and not blocked_groups
    return {
        "provided": isinstance(readiness, dict),
        "complete": lua_api_complete and strict_live_ready,
        "ue4ssLuaApiComplete": lua_api_complete,
        "liveTargetImageCanaryReady": live_contract_ready,
        "strictLiveTargetImageReady": strict_live_ready,
        "targetImageProcess": bool(ready.get("targetImageProcess", False)),
        "runtimeRootDiscovery": bool(ready.get("runtimeRootDiscovery", False)),
        "targetObjectDiscovery": bool(ready.get("targetObjectDiscovery", False)),
        "targetHooks": bool(ready.get("targetHooks", False)),
        "targetPackageLoadingSurface": bool(ready.get("targetPackageLoadingSurface", False)),
        "anchorCoverageObjectDiscovery": bool(ready.get("anchorCoverageObjectDiscovery", False)),
        "anchorCoverageHookPlanning": bool(ready.get("anchorCoverageHookPlanning", False)),
        "anchorCoveragePackageLoading": bool(ready.get("anchorCoveragePackageLoading", False)),
        "missingLiveTargetImageKeys": missing_live,
        "blockedLiveTargetImageGroups": blocked_groups,
        "liveTargetImageGroupMissingKeys": group_missing,
        "contradictions": contradictions,
    }


def score_entry(entry):
    score = 0
    readiness = entry["readiness"]
    coverage = entry["anchorCoverage"]
    for key in (
        "targetImageProcess",
        "runtimeRootDiscovery",
        "targetObjectDiscovery",
        "targetHooks",
        "targetPackageLoadingSurface",
        "anchorCoverageObjectDiscovery",
        "anchorCoverageHookPlanning",
        "anchorCoveragePackageLoading",
    ):
        score += 10 if readiness.get(key) else 0
    if coverage.get("provided"):
        score += 5
    if coverage.get("targetCoverageFieldsPresent"):
        score += 10
    score += 3 * len([g for g in TARGET_GROUPS if g not in coverage.get("missingTargetGroups", [])])
    if readiness.get("complete"):
        score += 100
    score -= 25 * len(readiness.get("contradictions", []) or [])
    score -= 5 * len(readiness.get("blockedLiveTargetImageGroups", []) or [])
    return score


def next_canary_focus(entry):
    if not entry:
        return {
            "ready": False,
            "phase": "collect-evidence",
            "missingTargetGroups": list(TARGET_GROUPS),
            "missingLiveTargetImageKeys": [],
            "blockedLiveTargetImageGroups": [],
            "summary": "collect UE4SS readiness and anchor coverage evidence",
            "actions": ["run a canary that writes ue4ss-readiness.json and anchor-coverage.json"],
        }
    readiness = entry["readiness"]
    coverage = entry["anchorCoverage"]
    missing_target = list(coverage.get("missingTargetGroups", []) or [])
    missing_live = list(readiness.get("missingLiveTargetImageKeys", []) or [])
    blocked_groups = list(readiness.get("blockedLiveTargetImageGroups", []) or [])
    if readiness.get("complete") and not missing_target:
        return {
            "ready": True,
            "phase": "complete",
            "missingTargetGroups": [],
            "missingLiveTargetImageKeys": [],
            "blockedLiveTargetImageGroups": [],
            "summary": "strict UE4SS target-image canary evidence is complete",
            "actions": [],
        }
    if not coverage.get("provided") or not coverage.get("targetCoverageFieldsPresent"):
        return {
            "ready": False,
            "phase": "target-anchor-inventory",
            "missingTargetGroups": missing_target or list(TARGET_GROUPS),
            "missingLiveTargetImageKeys": missing_live,
            "blockedLiveTargetImageGroups": blocked_groups,
            "summary": "generate target-image-aware anchor coverage before attempting live UE4SS completion",
            "actions": [
                "run prepare-ue-anchor-canary.py so anchor-coverage.json carries targetCoverageFieldsPresent=true",
            ],
        }
    if missing_target:
        actions = [TARGET_GROUP_NEXT_ACTIONS.get(group, f"recover target-image {group} anchor evidence") for group in missing_target]
        return {
            "ready": False,
            "phase": "target-anchor-coverage",
            "missingTargetGroups": missing_target,
            "missingLiveTargetImageKeys": missing_live,
            "blockedLiveTargetImageGroups": blocked_groups,
            "summary": "complete target-image anchor coverage before live runtime promotion",
            "actions": actions,
        }
    if missing_live or blocked_groups:
        actions = []
        if blocked_groups:
            actions.append("run the strict post-canary verifier against live target-image runtime groups: " + ", ".join(blocked_groups))
        if missing_live:
            actions.append("collect missing live target-image readiness keys: " + ", ".join(missing_live[:12]))
        return {
            "ready": False,
            "phase": "live-target-image-contract",
            "missingTargetGroups": [],
            "missingLiveTargetImageKeys": missing_live,
            "blockedLiveTargetImageGroups": blocked_groups,
            "summary": "prove the live target-image runtime contract with strict post-canary evidence",
            "actions": actions,
        }
    return {
        "ready": False,
        "phase": "lua-api-completion",
        "missingTargetGroups": [],
        "missingLiveTargetImageKeys": missing_live,
        "blockedLiveTargetImageGroups": blocked_groups,
        "summary": "strict live target-image contract is present but ue4ssLuaApiComplete is not proven",
        "actions": ["collect the remaining UE4SS Lua API parity readiness keys under strict runtime verification"],
    }


def evidence_entry(directory):
    readiness_path = directory / "ue4ss-readiness.json"
    coverage_path = directory / "anchor-coverage.json"
    readiness = load_json(readiness_path)
    coverage = load_json(coverage_path)
    if coverage is None and isinstance(readiness, dict):
        coverage = readiness.get("anchorCoverage")
    if readiness is None and coverage is None:
        return None
    readiness_summary_payload = readiness_summary(readiness)
    coverage_summary_payload = coverage_summary(coverage)
    coverage_complete = (
        bool(coverage_summary_payload.get("provided"))
        and bool(coverage_summary_payload.get("targetCoverageFieldsPresent"))
        and not coverage_summary_payload.get("missingTargetGroups")
    )
    if readiness_summary_payload.get("complete") and not coverage_complete:
        readiness_summary_payload["contradictions"].append(
            "readiness is complete without complete target-image anchor coverage"
        )
        readiness_summary_payload["complete"] = False
    entry = {
        "directory": str(directory),
        "readinessPath": str(readiness_path) if readiness_path.exists() else "",
        "anchorCoveragePath": str(coverage_path) if coverage_path.exists() else "",
        "readiness": readiness_summary_payload,
        "anchorCoverage": coverage_summary_payload,
    }
    entry["score"] = score_entry(entry)
    return entry


def find_evidence_dirs(roots):
    dirs = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            dirs.add(root.parent)
            continue
        for path in root.rglob("ue4ss-readiness.json"):
            dirs.add(path.parent)
        for path in root.rglob("anchor-coverage.json"):
            dirs.add(path.parent)
    return sorted(dirs)


def build_inventory(roots, limit):
    entries = [entry for directory in find_evidence_dirs(roots) if (entry := evidence_entry(directory))]
    entries.sort(key=lambda item: (item["score"], item["directory"]), reverse=True)
    complete_entries = [entry for entry in entries if entry["readiness"].get("complete")]
    return {
        "schemaVersion": "dune-ue4ss-evidence-inventory/v1",
        "searchRoots": [str(root) for root in roots],
        "entryCount": len(entries),
        "completeEntryCount": len(complete_entries),
        "entries": entries[:limit],
        "best": entries[0] if entries else None,
        "bestComplete": complete_entries[0] if complete_entries else None,
        "nextCanaryFocus": next_canary_focus(entries[0] if entries else None),
    }


def markdown(inventory):
    lines = ["# UE4SS Evidence Inventory", ""]
    lines.append(f"- Entries: `{inventory['entryCount']}`")
    lines.append(f"- Complete entries: `{inventory.get('completeEntryCount', 0)}`")
    best = inventory.get("best")
    if best:
        lines.append(f"- Best evidence: `{best['directory']}` score=`{best['score']}`")
        lines.append(
            "- Best missing target groups: `"
            + (", ".join(best["anchorCoverage"].get("missingTargetGroups", [])) or "none")
            + "`"
        )
    best_complete = inventory.get("bestComplete")
    if best_complete:
        lines.append(f"- Best complete evidence: `{best_complete['directory']}` score=`{best_complete['score']}`")
    focus = inventory.get("nextCanaryFocus") or {}
    if focus:
        lines.append(f"- Next canary phase: `{focus.get('phase', 'unknown')}`")
        lines.append(f"- Next canary focus: `{focus.get('summary', '')}`")
        actions = focus.get("actions") or []
        if actions:
            lines.append("- Next canary actions: `" + " | ".join(actions) + "`")
    lines.append("")
    lines.append("## Entries")
    lines.append("")
    for entry in inventory.get("entries", []):
        readiness = entry["readiness"]
        coverage = entry["anchorCoverage"]
        lines.append(
            f"- score=`{entry['score']}` dir=`{entry['directory']}` "
            f"complete=`{str(readiness['complete']).lower()}` "
            f"luaApiComplete=`{str(readiness.get('ue4ssLuaApiComplete', False)).lower()}` "
            f"liveTargetImage=`{str(readiness.get('liveTargetImageCanaryReady', False)).lower()}` "
            f"strictLiveTargetImage=`{str(readiness.get('strictLiveTargetImageReady', False)).lower()}` "
            f"targetImage=`{str(readiness['targetImageProcess']).lower()}` "
            f"coverage=`{str(coverage['provided']).lower()}` "
            f"targetFields=`{str(coverage['targetCoverageFieldsPresent']).lower()}` "
            f"missingTarget=`{', '.join(coverage.get('missingTargetGroups', [])) or 'none'}` "
            f"missingLive=`{', '.join(readiness.get('missingLiveTargetImageKeys', [])) or 'none'}` "
            f"blockedLiveGroups=`{', '.join(readiness.get('blockedLiveTargetImageGroups', [])) or 'none'}`"
        )
        for contradiction in readiness.get("contradictions", []):
            lines.append(f"  - contradiction: {contradiction}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inventory UE4SS readiness and anchor coverage evidence directories.")
    parser.add_argument("paths", nargs="*", type=Path, help="Evidence roots or files to scan")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="exit nonzero unless at least one evidence directory proves strict UE4SS completion",
    )
    args = parser.parse_args(argv)
    roots = args.paths or list(DEFAULT_SEARCH_ROOTS)
    inventory = build_inventory(roots, args.limit)
    if args.format == "json":
        json.dump(inventory, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(inventory))
    if args.require_complete and not inventory.get("bestComplete"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
