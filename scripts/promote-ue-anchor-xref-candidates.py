#!/usr/bin/env python3
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


CORE_ANCHOR_GROUPS = {
    "names": ("FNamePool", "NamePoolData", "GName", "GNames"),
    "objects": ("GUObjectArray", "GObjectArray", "GObjects", "FUObjectArray"),
    "world": ("GWorld", "GEngine"),
    "dispatch": ("ProcessEvent", "StaticFindObject", "CallFunctionByNameWithArguments", "CallFunctionByName"),
    "package": ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName", "LoadAsset", "LoadClass"),
    "reflection": ("UObject", "UFunction", "UClass", "FProperty", "FObjectProperty", "FArrayProperty", "FBoolProperty", "FStructProperty", "UStruct", "UEnum"),
}
REQUIRED_DISCOVERY_GROUPS = ("names", "objects", "world", "dispatch")
UE_ANCHORS = tuple(anchor for anchors in CORE_ANCHOR_GROUPS.values() for anchor in anchors)
UE_ANCHOR_ALIASES = {
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
    "LoadPackage": ("loadpackage", "upackageloadpackage"),
    "ResolveName": ("resolvename", "uresolvename"),
    "LoadAsset": ("loadasset",),
    "LoadClass": ("loadclass",),
    "UObject": ("uobject", "uobjectbase"),
    "UFunction": ("ufunction",),
    "UClass": ("uclass",),
    "FProperty": ("fproperty", "uproperty"),
    "FObjectProperty": ("fobjectproperty",),
    "FArrayProperty": ("farrayproperty",),
    "FBoolProperty": ("fboolproperty",),
    "FStructProperty": ("fstructproperty",),
    "UStruct": ("ustruct",),
    "UEnum": ("uenum",),
}


def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def canonical_anchor_name(value):
    normalized = normalize_name(value or "")
    if not normalized:
        return None
    for canonical in UE_ANCHORS:
        if normalized == normalize_name(canonical):
            return canonical
    for canonical, aliases in UE_ANCHOR_ALIASES.items():
        if normalized in aliases:
            return canonical
    for canonical in UE_ANCHORS:
        if normalize_name(canonical) in normalized:
            return canonical
    for canonical, aliases in UE_ANCHOR_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical
    return None


def anchor_sort_key(name):
    try:
        return (0, UE_ANCHORS.index(name))
    except ValueError:
        return (1, name)


def load_json(path):
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def target_coordinate(target):
    return target.get("rva") or target.get("vaddr") or target.get("imageOffset") or target.get("fileOffset") or ""


def xref_coordinate(ref):
    return ref.get("xrefRva") or ref.get("xrefVaddr") or ref.get("xrefFileOffset") or ""


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


def target_provenance(target):
    source = target.get("source", "")
    if not source:
        return "unknown"
    if is_loader_source(source):
        return "loader"
    return "target"


def promote_candidates(
    summary,
    allow_string_targets=False,
    require_ue_category=True,
    max_per_anchor=4,
    allow_loader_sources=False,
    require_target_source=False,
):
    targets = []
    rejected = []
    counts = defaultdict(int)
    provenance_counts = defaultdict(int)
    seen = set()

    for target in summary.get("targets", []):
        anchor = canonical_anchor_name(target.get("name", ""))
        if not anchor:
            rejected.append({"name": target.get("name", ""), "reason": "not-core-anchor"})
            continue
        provenance = target_provenance(target)
        if provenance == "loader" and not allow_loader_sources:
            rejected.append({"name": target.get("name", ""), "anchor": anchor, "reason": "loader-source"})
            continue
        if provenance != "target" and require_target_source:
            rejected.append({"name": target.get("name", ""), "anchor": anchor, "reason": "non-target-source"})
            continue
        category = target.get("category", "")
        if require_ue_category and category != "ue":
            rejected.append({"name": target.get("name", ""), "anchor": anchor, "reason": "non-ue-category"})
            continue
        kind = target.get("kind", "")
        if kind == "string" and not allow_string_targets:
            rejected.append({"name": target.get("name", ""), "anchor": anchor, "reason": "string-target"})
            continue
        for ref in target.get("xrefs", []):
            seed = ref.get("signatureSeed") or {}
            pattern = seed.get("pattern", "")
            if not pattern:
                rejected.append({"name": target.get("name", ""), "anchor": anchor, "reason": "missing-signature-seed"})
                continue
            if max_per_anchor and counts[anchor] >= max_per_anchor:
                continue
            key = (anchor, pattern, xref_coordinate(ref), target_coordinate(target))
            if key in seen:
                continue
            seen.add(key)
            counts[anchor] += 1
            promoted = dict(target)
            promoted["name"] = anchor
            promoted["category"] = "ue"
            promoted["source"] = "ue-anchor-xref-candidate"
            promoted["sourcePath"] = target.get("source", "")
            promoted["sourceProvenance"] = provenance
            promoted["originalName"] = target.get("name", "")
            promoted["originalCategory"] = category
            promoted["originalKind"] = kind
            promoted["xrefs"] = [ref]
            promoted["xrefCount"] = 1
            targets.append(promoted)
            provenance_counts[provenance] += 1

    present_anchors = sorted(counts, key=anchor_sort_key)
    groups = {}
    for group_name, anchors in CORE_ANCHOR_GROUPS.items():
        present = [anchor for anchor in anchors if counts.get(anchor, 0)]
        groups[group_name] = {
            "present": len(present),
            "total": len(anchors),
            "anchors": list(anchors),
            "presentAnchors": present,
            "complete": len(present) == len(anchors),
        }
    missing_required_groups = [
        group_name for group_name in REQUIRED_DISCOVERY_GROUPS
        if groups[group_name]["present"] == 0
    ]

    return {
        "schemaVersion": "dune-ue-anchor-xref-candidates/v1",
        "sourceFormat": summary.get("format", ""),
        "candidateCount": len(targets),
        "sourceProvenanceCounts": dict(sorted(provenance_counts.items())),
        "anchorCounts": dict(sorted(counts.items(), key=lambda item: anchor_sort_key(item[0]))),
        "presentAnchors": present_anchors,
        "missingAnchors": [anchor for anchor in UE_ANCHORS if anchor not in counts],
        "groups": groups,
        "missingRequiredGroups": missing_required_groups,
        "readyForValidation": bool(targets),
        "readyForObjectDiscoveryCandidateCoverage": not missing_required_groups,
        "targets": targets,
        "rejected": rejected,
    }


def markdown(result, limit):
    lines = []
    lines.append("# UE Anchor Xref Candidates")
    lines.append("")
    lines.append(f"- Source format: `{result['sourceFormat'] or 'unknown'}`")
    lines.append(f"- Candidates: `{result['candidateCount']}`")
    lines.append(f"- Source provenance: `{result.get('sourceProvenanceCounts', {})}`")
    lines.append(f"- Present anchors: `{', '.join(result['presentAnchors']) or 'none'}`")
    lines.append(f"- Missing required groups: `{', '.join(result['missingRequiredGroups']) or 'none'}`")
    lines.append(f"- Ready for validation: `{str(result['readyForValidation']).lower()}`")
    lines.append(
        "- Ready for object-discovery candidate coverage: "
        f"`{str(result['readyForObjectDiscoveryCandidateCoverage']).lower()}`"
    )
    lines.append("")
    lines.append("## Groups")
    lines.append("")
    for group_name, group in result["groups"].items():
        lines.append(f"- {group_name}: `{group['present']}/{group['total']}`")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")
    for target in result["targets"][:limit]:
        ref = target["xrefs"][0]
        seed = ref.get("signatureSeed", {})
        lines.append(
            f"- `{target['name']}` from `{target.get('originalName', '')}` "
            f"kind=`{target.get('originalKind', '')}` xref=`{xref_coordinate(ref)}` "
            f"seedFile=`{seed.get('fileOffset', '')}` provenance=`{target.get('sourceProvenance', '')}`"
        )
    if len(result["targets"]) > limit:
        lines.append(f"- ... +{len(result['targets']) - limit} more")
    if not result["targets"]:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Promote xref summary rows into conservative UE core-anchor signature candidates."
    )
    parser.add_argument("xref_json", type=Path, help="summarize-*-loader-xrefs.py JSON output")
    parser.add_argument("--allow-string-targets", action="store_true")
    parser.add_argument("--allow-loader-sources", action="store_true")
    parser.add_argument("--require-target-source", action="store_true")
    parser.add_argument("--no-require-ue-category", action="store_true")
    parser.add_argument("--max-per-anchor", type=int, default=4)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)

    result = promote_candidates(
        load_json(args.xref_json),
        allow_string_targets=args.allow_string_targets,
        require_ue_category=not args.no_require_ue_category,
        max_per_anchor=args.max_per_anchor,
        allow_loader_sources=args.allow_loader_sources,
        require_target_source=args.require_target_source,
    )
    if args.format == "json":
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(result, args.limit))


if __name__ == "__main__":
    main()
