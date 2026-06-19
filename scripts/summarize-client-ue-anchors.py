#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from pathlib import Path


ANCHOR_GROUPS = {
    "names": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "UStruct", "UEnum"),
    "cheat": ("CheatManager", "CheatClass", "EnableCheats", "AdminLogin"),
    "brt": ("ServerRequestBaseBackup", "BaseBackupActionPlace", "PerformCanBePlaced", "Fail_InvalidMap"),
    "deep-desert": ("DeepDesert", "DeepDesert_1", "m_DeepDesertGameplay"),
}


def normalize_anchor_name(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


ANCHOR_ALIASES = {
    "FNamePool": ("fnamepool", "fnamepoolanchor", "namepool", "globalnamepool"),
    "NamePoolData": ("namepooldata",),
    "GName": ("gname", "gnames", "globalnames"),
    "GNames": ("gnames", "globalnames"),
    "GUObjectArray": ("guobjectarray", "guobjects", "globaluobjectarray"),
    "GObjectArray": ("gobjectarray", "gobjects", "globalobjectarray"),
    "GObjects": ("gobjects", "globalobjects"),
    "FUObjectArray": ("fuobjectarray",),
    "GWorld": ("gworld", "uworldglobal", "globalworld"),
    "GEngine": ("gengine", "uengineglobal", "globalengine"),
    "ProcessEvent": ("processevent", "uobjectprocessevent", "processinternal"),
    "StaticFindObject": ("staticfindobject", "findobject"),
    "CallFunctionByNameWithArguments": (
        "callfunctionbynamewitharguments",
        "uobjectcallfunctionbynamewitharguments",
    ),
    "CallFunctionByName": ("callfunctionbyname",),
    "StaticLoadObject": ("staticloadobject",),
    "LoadObject": ("loadobject",),
    "LoadPackage": ("loadpackage",),
    "ResolveName": ("resolvename",),
    "UObject": ("uobject", "uobjectbase"),
    "UFunction": ("ufunction",),
    "UClass": ("uclass",),
    "FProperty": ("fproperty", "uproperty"),
    "UStruct": ("ustruct",),
    "UEnum": ("uenum",),
    "CheatManager": ("cheatmanager", "dunecheatmanager"),
    "CheatClass": ("cheatclass",),
    "EnableCheats": ("enablecheats",),
    "AdminLogin": ("adminlogin",),
    "ServerRequestBaseBackup": ("serverrequestbasebackup", "requestbasebackup"),
    "BaseBackupActionPlace": ("basebackupactionplace",),
    "PerformCanBePlaced": ("performcanbeplaced", "canbeplaced"),
    "Fail_InvalidMap": ("failinvalidmap", "invalidmap"),
    "DeepDesert": ("deepdesert",),
    "DeepDesert_1": ("deepdesert1",),
    "m_DeepDesertGameplay": ("mdeepdesertgameplay", "deepdesertgameplay"),
}


def canonical_anchor_name(name):
    normalized = normalize_anchor_name(name)
    if not normalized or normalized.startswith("selftest"):
        return None
    for canonical, aliases in ANCHOR_ALIASES.items():
        if normalized == normalize_anchor_name(canonical) or any(alias in normalized for alias in aliases):
            return canonical
    return name if any(name in anchors for anchors in ANCHOR_GROUPS.values()) else None


def hit_has_proven_anchor_kind(data):
    kinds = data.get("kinds", {})
    return bool(kinds.get("ue-anchor") or kinds.get("ue-anchor-signature"))


def matching_hits(hits, anchor, proven_only=False):
    rows = []
    for hit_name, data in hits.items():
        if hit_name == anchor or canonical_anchor_name(hit_name) == anchor:
            if proven_only and not hit_has_proven_anchor_kind(data):
                continue
            rows.append((hit_name, data))
    return rows


def merge_sources(rows):
    merged = {}
    for _, data in rows:
        for source, count in data.get("sources", {}).items():
            merged[source] = merged.get(source, 0) + count
    return merged


def is_loader_source(source):
    normalized = str(source or "").lower().replace("\\", "/")
    loader_needles = (
        "dune_client_probe_loader",
        "dune_server_probe_loader",
        "dune_win_client_probe_loader",
        "linux-client-loader",
        "linux-server-loader",
        "windows-client-loader",
        "libdune_",
    )
    return any(needle in normalized for needle in loader_needles)


def source_counts(rows):
    target_count = 0
    loader_count = 0
    unknown_count = 0
    for _, data in rows:
        offsets = data.get("offsets") or []
        if offsets:
            for offset in offsets:
                source = offset.get("source", "")
                if not source:
                    unknown_count += 1
                elif is_loader_source(source):
                    loader_count += 1
                else:
                    target_count += 1
        else:
            for source, count in data.get("sources", {}).items():
                if not source:
                    unknown_count += count
                elif is_loader_source(source):
                    loader_count += count
                else:
                    target_count += count
    return target_count, loader_count, unknown_count


def import_scan_summary():
    script = Path(__file__).resolve().parent / "summarize-client-loader-scan.py"
    spec = importlib.util.spec_from_file_location("summarize_client_loader_scan", script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def summarize(summary, proven_only=False):
    hits = summary["hitsByName"]
    groups = {}
    for group, anchors in ANCHOR_GROUPS.items():
        rows = []
        present = 0
        for anchor in anchors:
            matches = matching_hits(hits, anchor, proven_only=proven_only)
            if matches:
                target_count, loader_count, unknown_count = source_counts(matches)
                present += 1
                first_name, first_data = matches[0]
                rows.append(
                    {
                        "name": anchor,
                        "matchedNames": [name for name, _ in matches],
                        "present": True,
                        "targetPresent": target_count > 0,
                        "loaderPresent": loader_count > 0,
                        "count": sum(data.get("count", 0) for _, data in matches),
                        "targetSourceCount": target_count,
                        "loaderSourceCount": loader_count,
                        "unknownSourceCount": unknown_count,
                        "first": first_data.get("first", {}),
                        "sources": merge_sources(matches),
                    }
                )
            else:
                rows.append(
                    {
                        "name": anchor,
                        "matchedNames": [],
                        "present": False,
                        "targetPresent": False,
                        "loaderPresent": False,
                        "count": 0,
                        "targetSourceCount": 0,
                        "loaderSourceCount": 0,
                        "unknownSourceCount": 0,
                        "first": {},
                        "sources": {},
                    }
                )
        target_present = sum(1 for row in rows if row["targetPresent"])
        groups[group] = {
            "present": present,
            "targetPresent": target_present,
            "total": len(anchors),
            "complete": present == len(anchors),
            "targetComplete": target_present == len(anchors),
            "anchors": rows,
        }

    required = ("names", "objects", "world", "dispatch")
    ready_for_object_discovery = all(groups[group]["present"] > 0 for group in required)
    ready_for_target_object_discovery = all(groups[group]["targetPresent"] > 0 for group in required)
    ready_for_hooks = ready_for_object_discovery and any(
        anchor["name"] == "ProcessEvent" and anchor["present"]
        for anchor in groups["dispatch"]["anchors"]
    )
    ready_for_target_hooks = ready_for_target_object_discovery and any(
        anchor["name"] == "ProcessEvent" and anchor["targetPresent"]
        for anchor in groups["dispatch"]["anchors"]
    )
    next_steps = []
    if not groups["names"]["present"]:
        next_steps.append("find FNamePool/GName signature or string xrefs")
    if not groups["objects"]["present"]:
        next_steps.append("find GUObjectArray/GObjectArray signature or string xrefs")
    if not groups["world"]["present"]:
        next_steps.append("find GWorld signature or world-context xrefs")
    if not groups["dispatch"]["present"]:
        next_steps.append("find ProcessEvent/StaticFindObject/CallFunctionByNameWithArguments xrefs")
    if ready_for_object_discovery:
        next_steps.append("add read-only memory readers for FName/GUObject/GWorld layouts")
    if ready_for_object_discovery and not ready_for_target_object_discovery:
        next_steps.append("rerun anchor validation with core groups resolved in the target executable/module, not the loader image")
    if ready_for_hooks:
        next_steps.append("defer hook/trampoline work until read-only layout validation passes")
    if ready_for_hooks and not ready_for_target_hooks:
        next_steps.append("rerun hook planning with ProcessEvent resolved in the target executable/module")

    return {
        "provenOnly": proven_only,
        "readyForObjectDiscovery": ready_for_object_discovery,
        "readyForTargetObjectDiscovery": ready_for_target_object_discovery,
        "readyForHooks": ready_for_hooks,
        "readyForTargetHooks": ready_for_target_hooks,
        "groups": groups,
        "nextSteps": next_steps,
    }


def markdown(report):
    lines = []
    lines.append("# Client UE Anchor Readiness")
    lines.append("")
    lines.append(f"- Ready for object discovery: `{str(report['readyForObjectDiscovery']).lower()}`")
    lines.append(f"- Ready for target-image object discovery: `{str(report['readyForTargetObjectDiscovery']).lower()}`")
    lines.append(f"- Ready for hooks: `{str(report['readyForHooks']).lower()}`")
    lines.append(f"- Ready for target-image hooks: `{str(report['readyForTargetHooks']).lower()}`")
    lines.append(f"- Proven anchors only: `{str(report.get('provenOnly', False)).lower()}`")
    lines.append("")
    for group, data in report["groups"].items():
        lines.append(f"## {group}")
        lines.append("")
        lines.append(f"- Present: `{data['present']}/{data['total']}`")
        lines.append(f"- Target-image present: `{data['targetPresent']}/{data['total']}`")
        for anchor in data["anchors"]:
            marker = "present" if anchor["present"] else "missing"
            first = anchor["first"].get("offset", "")
            suffix = f" first=`{first}`" if first else ""
            matched = ""
            if anchor.get("matchedNames") and anchor["matchedNames"] != [anchor["name"]]:
                matched = f" matched=`{', '.join(anchor['matchedNames'])}`"
            provenance = (
                f" target=`{anchor['targetSourceCount']}`"
                f" loader=`{anchor['loaderSourceCount']}`"
                f" unknown=`{anchor['unknownSourceCount']}`"
            )
            lines.append(f"- `{anchor['name']}`: `{marker}` count=`{anchor['count']}`{provenance}{suffix}{matched}")
        lines.append("")
    lines.append("## Next Steps")
    lines.append("")
    for step in report["nextSteps"]:
        lines.append(f"- {step}")
    if not report["nextSteps"]:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize client UE anchor readiness from client loader logs.")
    parser.add_argument("log", type=Path)
    parser.add_argument("--loader", action="append", choices=("client", "win-client", "linux-client", "server"), default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    scan_summary = import_scan_summary()
    summary = scan_summary.summarize(
        scan_summary.load_records(args.log),
        loader_filter=args.loader,
        pid_filter=args.pid,
        exe_substrings=args.exe_substring,
    )
    report = summarize(summary)
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(report))


if __name__ == "__main__":
    main()
