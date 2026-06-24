#!/usr/bin/env python3
import argparse
import importlib.util
import json
import sys
from pathlib import Path


DEFAULT_ANCHORS = (
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
    "StaticLoadObject",
    "StaticLoadClass",
    "LoadObject",
    "LoadPackage",
    "ResolveName",
    "LoadAsset",
    "LoadClass",
    "UObject",
    "UFunction",
    "UClass",
    "FProperty",
    "UStruct",
    "UEnum",
)
LOADER_ALIASES = {
    "linux-client": ("linux-client", "client"),
    "client": ("client", "linux-client"),
    "linux-server": ("linux-server", "server"),
    "server": ("server", "linux-server"),
    "windows-client": ("windows-client", "win-client"),
    "win-client": ("win-client", "windows-client"),
}


def normalize_anchor_name(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


ANCHOR_ALIASES = {
    "FNamePool": ("fnamepool", "namepool", "globalnamepool"),
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
    "StaticLoadObject": ("staticloadobject", "loadobjectstatic", "uobjectstaticloadobject"),
    "StaticLoadClass": ("staticloadclass", "loadclassstatic", "uobjectstaticloadclass"),
    "LoadObject": ("loadobject", "uobjectloadobject"),
    "LoadPackage": ("loadpackage",),
    "ResolveName": ("resolvename",),
    "LoadAsset": ("loadasset",),
    "LoadClass": ("loadclass",),
    "UObject": ("uobject", "uobjectbase"),
    "UFunction": ("ufunction",),
    "UClass": ("uclass",),
    "FProperty": ("fproperty", "uproperty"),
    "UStruct": ("ustruct",),
    "UEnum": ("uenum",),
}
RUNTIME_CANDIDATE_ANCHORS = {
    "RuntimeFNamePool": "FNamePool",
    "RuntimeGUObjectArray": "GUObjectArray",
}


def canonical_anchor_name(name):
    normalized = normalize_anchor_name(name)
    if not normalized or normalized.startswith("selftest"):
        return None
    for canonical, aliases in ANCHOR_ALIASES.items():
        if normalized == normalize_anchor_name(canonical) or any(alias in normalized for alias in aliases):
            return canonical
    return name if name in DEFAULT_ANCHORS else None


def expand_loader_filter(loader_filter):
    expanded = []
    seen = set()
    for loader in loader_filter:
        for candidate in LOADER_ALIASES.get(loader, (loader,)):
            if candidate not in seen:
                expanded.append(candidate)
                seen.add(candidate)
    return expanded


def import_script(script_name, module_name):
    script = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(module_name, script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def infer_env_name(platform, loaders):
    if platform == "server":
        return "DUNE_PROBE_LOADER_UE_ANCHORS"
    if platform == "windows":
        return "DUNE_WIN_CLIENT_PROBE_UE_ANCHORS"
    if platform == "linux":
        return "DUNE_CLIENT_PROBE_UE_ANCHORS"
    if any(loader == "server" for loader in loaders):
        return "DUNE_PROBE_LOADER_UE_ANCHORS"
    if any(loader == "win-client" for loader in loaders):
        return "DUNE_WIN_CLIENT_PROBE_UE_ANCHORS"
    return "DUNE_CLIENT_PROBE_UE_ANCHORS"


def env_prefix(anchor_env_name):
    if anchor_env_name == "DUNE_PROBE_LOADER_UE_ANCHORS":
        return "DUNE_PROBE_LOADER"
    if anchor_env_name.startswith("DUNE_WIN_"):
        return "DUNE_WIN_CLIENT_PROBE"
    return "DUNE_CLIENT_PROBE"


def pointer_env_name(anchor_env_name):
    return f"{env_prefix(anchor_env_name)}_UE_POINTER_PROBE"


def layout_env_name(anchor_env_name):
    return f"{env_prefix(anchor_env_name)}_UE_LAYOUT_PROBE"


def uobject_env_name(anchor_env_name):
    return f"{env_prefix(anchor_env_name)}_UE_UOBJECT_PROBE"


def object_array_env_name(anchor_env_name):
    return f"{env_prefix(anchor_env_name)}_UE_OBJECT_ARRAY_PROBE"


def fname_env_name(anchor_env_name):
    return f"{env_prefix(anchor_env_name)}_UE_FNAME_PROBE"


def anchor_signature_file_env_name(anchor_env_name):
    return f"{env_prefix(anchor_env_name)}_UE_ANCHOR_SIGNATURES_FILE"


def collect_entries(summary, names, include_scan_hits=False):
    entries = []
    seen = set()
    hits = summary.get("hitsByName", {})
    for name in names:
        canonical = canonical_anchor_name(name) or name
        if canonical in seen:
            continue
        seen.add(canonical)
        first = {}
        matched_name = ""
        hit = {}
        for hit_name, data in hits.items():
            if hit_name == canonical or canonical_anchor_name(hit_name) == canonical:
                candidates = data.get("offsets", [])
                if include_scan_hits:
                    candidate = next((item for item in candidates if item.get("addr")), {})
                else:
                    candidate = next(
                        (
                            item for item in candidates
                            if item.get("addr") and item.get("kind") in ("ue-anchor", "ue-anchor-signature")
                        ),
                        {},
                    )
                if candidate.get("addr"):
                    first = candidate
                    matched_name = hit_name
                    hit = data
                    break
        if not first:
            continue
        address = first.get("addr", "")
        if not address:
            continue
        entries.append(
            {
                "name": canonical,
                "matchedName": matched_name,
                "address": address,
                "kind": first.get("kind", ""),
                "offset": first.get("offset", ""),
                "imageOffset": first.get("imageOffset", ""),
                "fileOffset": first.get("fileOffset", ""),
                "rva": first.get("rva", ""),
                "source": first.get("source", ""),
                "count": hit.get("count", 0),
            }
        )
    return entries


def parse_runtime_candidate_selectors(selectors):
    selected = {}
    for selector in selectors or []:
        if "=" not in selector:
            raise ValueError(f"runtime candidate selector must be NAME=OFFSET, got {selector!r}")
        name, offset = selector.split("=", 1)
        canonical = canonical_anchor_name(name.strip()) or name.strip()
        selected.setdefault(canonical, set()).add(offset.strip().lower())
    return selected


def runtime_candidate_offset(row):
    return str(row.get("imageOffset") or row.get("rva") or row.get("fileOffset") or "").lower()


def collect_runtime_candidate_entries(summary, names, selectors=None):
    requested = {canonical_anchor_name(name) or name for name in names}
    selected = parse_runtime_candidate_selectors(selectors or [])
    entries = []
    by_anchor = {}
    for row in (summary.get("ueRuntimeDiscovery") or {}).get("candidateLocations", []):
        canonical = RUNTIME_CANDIDATE_ANCHORS.get(row.get("name", ""))
        if not canonical or canonical not in requested:
            continue
        by_anchor.setdefault(canonical, []).append(row)
    for canonical, rows in by_anchor.items():
        if canonical in selected:
            rows = [
                row for row in rows
                if runtime_candidate_offset(row) in selected[canonical]
            ]
        elif len(rows) != 1:
            continue
        for row in rows:
            address = row.get("addr", "")
            if not address:
                continue
            entries.append(
                {
                    "name": canonical,
                    "matchedName": row.get("name", ""),
                    "address": address,
                    "kind": "ue-runtime-discovery-candidate",
                    "offset": row.get("imageOffset", ""),
                    "imageOffset": row.get("imageOffset", ""),
                    "fileOffset": row.get("fileOffset", ""),
                    "rva": row.get("imageOffset", ""),
                    "source": "runtime-discovery-candidate",
                    "count": len(rows),
                }
            )
    return entries


def build_export(
    log,
    loader,
    pid,
    exe_substrings,
    names,
    platform,
    include_scan_hits=False,
    include_runtime_candidates=False,
    runtime_candidate_selectors=None,
):
    scan_mod = import_script("summarize-client-loader-scan.py", "summarize_client_loader_scan")
    summary = scan_mod.summarize(
        scan_mod.load_records(log),
        loader_filter=expand_loader_filter(loader),
        pid_filter=pid,
        exe_substrings=exe_substrings,
    )
    entries = collect_entries(summary, names, include_scan_hits=include_scan_hits)
    if include_runtime_candidates or runtime_candidate_selectors:
        existing_names = {entry["name"] for entry in entries}
        runtime_entries = collect_runtime_candidate_entries(
            summary,
            [name for name in names if (canonical_anchor_name(name) or name) not in existing_names],
            runtime_candidate_selectors,
        )
        entries.extend(runtime_entries)
    env_name = infer_env_name(platform, summary.get("loaders", []))
    return {
        "schemaVersion": "dune-ue-anchor-env/v1",
        "log": str(log),
        "envName": env_name,
        "pointerProbeEnvName": pointer_env_name(env_name),
        "layoutProbeEnvName": layout_env_name(env_name),
        "uobjectProbeEnvName": uobject_env_name(env_name),
        "objectArrayProbeEnvName": object_array_env_name(env_name),
        "fnameProbeEnvName": fname_env_name(env_name),
        "anchorSignatureFileEnvName": anchor_signature_file_env_name(env_name),
        "includeScanHits": include_scan_hits,
        "includeRuntimeCandidates": include_runtime_candidates,
        "runtimeCandidateSelectors": list(runtime_candidate_selectors or []),
        "entryCount": len(entries),
        "entries": entries,
        "missing": [
            canonical_anchor_name(name) or name
            for name in names
            if (canonical_anchor_name(name) or name) not in {entry["name"] for entry in entries}
        ],
    }


def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"


def env_text(export):
    value = ";".join(f"{entry['name']}={entry['address']}" for entry in export["entries"])
    lines = []
    lines.append("# Explicit UE anchor validation input")
    lines.append("# Feed this into the matching probe for a second read-only validation launch.")
    lines.append("# Raw scan-hit rows are excluded unless --include-scan-hits was used.")
    lines.append("# Runtime discovery candidates are excluded unless --include-runtime-candidates or --runtime-candidate was used.")
    lines.append(f"# Entries: {export['entryCount']}")
    if export["missing"]:
        lines.append(f"# Missing: {', '.join(export['missing'])}")
    lines.append(f"{export['envName']}={shell_quote(value)}")
    lines.append(f"{export['pointerProbeEnvName']}=true")
    lines.append(f"{export['layoutProbeEnvName']}=true")
    lines.append(f"{export['uobjectProbeEnvName']}=true")
    lines.append(f"{export['objectArrayProbeEnvName']}=true")
    lines.append(f"{export['fnameProbeEnvName']}=true")
    lines.append("")
    return "\n".join(lines)


def markdown(export):
    lines = ["# UE Anchor Env Export", ""]
    lines.append(f"- Env: `{export['envName']}`")
    lines.append(f"- Pointer probe env: `{export['pointerProbeEnvName']}`")
    lines.append(f"- Layout probe env: `{export['layoutProbeEnvName']}`")
    lines.append(f"- UObject probe env: `{export['uobjectProbeEnvName']}`")
    lines.append(f"- Object-array probe env: `{export['objectArrayProbeEnvName']}`")
    lines.append(f"- FName probe env: `{export['fnameProbeEnvName']}`")
    lines.append(f"- Anchor signature file env: `{export['anchorSignatureFileEnvName']}`")
    lines.append(f"- Include scan hits: `{str(export.get('includeScanHits', False)).lower()}`")
    lines.append(f"- Include runtime candidates: `{str(export.get('includeRuntimeCandidates', False)).lower()}`")
    lines.append(f"- Entries: `{export['entryCount']}`")
    if export["missing"]:
        lines.append(f"- Missing: `{', '.join(export['missing'])}`")
    lines.append("")
    for entry in export["entries"]:
        lines.append(
            f"- `{entry['name']}` addr=`{entry['address']}` kind=`{entry['kind']}` "
            f"offset=`{entry['offset']}` source=`{entry['source']}` matched=`{entry.get('matchedName', '')}`"
        )
    if not export["entries"]:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export explicit UE anchor validation env from loader scan logs.")
    parser.add_argument("log", type=Path)
    parser.add_argument("--loader", action="append", default=[])
    parser.add_argument("--pid", action="append", default=[])
    parser.add_argument("--exe-substring", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--platform", choices=("auto", "linux", "windows", "server"), default="auto")
    parser.add_argument(
        "--include-scan-hits",
        action="store_true",
        help="also export raw scan-hit addresses; unsafe for string hits unless manually reviewed",
    )
    parser.add_argument(
        "--include-runtime-candidates",
        action="store_true",
        help="export unique RuntimeFNamePool/RuntimeGUObjectArray candidate addresses as explicit anchors",
    )
    parser.add_argument(
        "--runtime-candidate",
        action="append",
        default=[],
        metavar="NAME=OFFSET",
        help="export a reviewed ambiguous runtime root candidate by canonical name and image offset/RVA",
    )
    parser.add_argument("--format", choices=("env", "json", "markdown"), default="env")
    args = parser.parse_args(argv)

    export = build_export(
        args.log,
        args.loader,
        args.pid,
        args.exe_substring,
        args.name or list(DEFAULT_ANCHORS),
        args.platform,
        include_scan_hits=args.include_scan_hits,
        include_runtime_candidates=args.include_runtime_candidates,
        runtime_candidate_selectors=args.runtime_candidate,
    )
    if args.format == "json":
        json.dump(export, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "markdown":
        sys.stdout.write(markdown(export))
    else:
        sys.stdout.write(env_text(export))


if __name__ == "__main__":
    main()
