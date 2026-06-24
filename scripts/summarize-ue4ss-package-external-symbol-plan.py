#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-external-symbol-plan/v1"
DEFAULT_EVIDENCE = "build/server-ue4ss-package-route-evidence.json"
DEFAULT_BINARY = "/tmp/dune-live-server-extract/DuneSandboxServer-Linux-Shipping"
DEFAULT_HISTORICAL_SURFACES = (
    "backups/canary-linux-loader/20260618T163244Z/elf-ue-relocation-surface.md",
    "backups/canary-linux-loader/20260618T163244Z/ghidra-ue-core-anchor-xrefs.md",
    "docs/linux-server-loader-canary-2026-06-18.md",
)

PACKAGE_ANCHORS = (
    "StaticLoadObject",
    "StaticLoadClass",
    "LoadObject",
    "LoadPackage",
    "ResolveName",
)


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def load_optional_json(path):
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_file():
        return None
    try:
        with candidate.open("r", encoding="utf-8", errors="replace") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return None


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_build_id(path):
    try:
        proc = subprocess.run(
            ["readelf", "-n", str(path)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return ""
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("Build ID:"):
            return line.split(":", 1)[1].strip()
    return ""


def binary_identity(binary):
    path = Path(binary)
    if not path.exists():
        return {
            "path": str(binary),
            "present": False,
            "sha256": "",
            "buildId": "",
            "size": 0,
        }
    return {
        "path": str(binary),
        "present": True,
        "sha256": sha256_file(path),
        "buildId": read_build_id(path),
        "size": path.stat().st_size,
    }


def route_by_id(evidence):
    return {row.get("id"): row for row in evidence.get("routes", []) or []}


def evidence_state(evidence):
    routes = route_by_id(evidence)
    return {
        "completePackageRoute": bool(evidence.get("complete")),
        "promotableRouteCount": int(evidence.get("promotableRouteCount", 0) or 0),
        "decompileReviewQueueCount": int(evidence.get("decompileReviewQueueCount", 0) or 0),
        "packageLoaderSummary": routes.get("package-loader-vtables", {}).get("summary", ""),
        "staticWrapperSummary": routes.get("static-wrapper-candidates", {}).get("summary", ""),
        "symbolSurfaceSummary": routes.get("symbol-surface-callgraph", {}).get("summary", ""),
    }


def donor_requirements():
    return [
        "Linux x86_64 SysV Unreal Engine build with exported symbols, debug symbols, or a linker map",
        "same UE major/minor lineage as the target build; exact game build is ideal but not required for first signature transfer",
        "contains at least one of StaticLoadObject, StaticLoadClass, LoadObject, LoadPackage, or ResolveName",
        "allows extracting function byte windows and nearby call/string references for signature validation against the stripped target",
    ]


def donor_search_summary(search):
    if not isinstance(search, dict):
        return {}
    candidates = search.get("candidates", []) or []
    usable = [candidate for candidate in candidates if candidate.get("usable") is True]
    false_positive = [
        candidate
        for candidate in candidates
        if candidate.get("usable") is False and not candidate.get("completeAnchorFamilyCoverage")
    ]
    return {
        "schemaVersion": search.get("schemaVersion", ""),
        "sourcePath": search.get("sourcePath", ""),
        "candidateCount": int(search.get("candidateCount", len(candidates)) or 0),
        "usableCandidateCount": int(search.get("usableCandidateCount", len(usable)) or 0),
        "sourceCandidateCount": int(search.get("sourceCandidateCount", 0) or 0),
        "falsePositiveCandidateCount": len(false_positive),
        "nextStep": search.get(
            "nextStep",
            "provide an unstripped/symbolized Linux UE donor or linker map containing package-loading anchors",
        ),
        "usableCandidates": [
            {
                "path": candidate.get("path", ""),
                "anchorsPresent": candidate.get("anchorsPresent", []) or [],
                "promotableSymbolCount": candidate.get("promotableSymbolCount", 0),
            }
            for candidate in usable
        ],
        "candidatePreview": [
            {
                "path": candidate.get("path", ""),
                "usable": candidate.get("usable"),
                "anchorsPresent": candidate.get("anchorsPresent", []) or [],
                "promotableSymbolCount": candidate.get("promotableSymbolCount", 0),
                "completeAnchorFamilyCoverage": candidate.get("completeAnchorFamilyCoverage", False),
                "rejectionReason": candidate.get("rejectionReason", ""),
            }
            for candidate in candidates[:8]
        ],
        "sourceCandidatePreview": [
            {
                "path": candidate.get("path", ""),
                "anchorsPresent": candidate.get("anchorsPresent", []) or [],
                "anchorCount": candidate.get("anchorCount", len(candidate.get("anchorsPresent", []) or [])),
                "nextStep": candidate.get("nextStep", ""),
            }
            for candidate in (search.get("sourceCandidates", []) or [])[:8]
        ],
    }


def build_commands(binary, donor):
    donor_ref = donor or "/path/to/unstripped-or-symbolized-UE4-linux-binary"
    needles = "StaticLoadObject|StaticLoadClass|LoadObject|LoadPackage|ResolveName"
    return {
        "findLocalDonors": (
            "scripts/find-ue4ss-package-donors.py /home/keith /opt /tmp "
            f"--target-binary {binary} --max-depth 6 --source-max-depth 12 --format json "
            "> build/server-ue4ss-package-donor-search.json"
        ),
        "summarizeDonorSymbols": (
            "scripts/summarize-ue4ss-package-donor-symbols.py "
            f"{donor_ref} --target-binary {binary} --signature-bytes 96 --format json "
            "> build/server-ue4ss-package-donor-symbols.json"
        ),
        "exportDonorCandidateValidation": (
            "scripts/summarize-ue4ss-package-donor-symbols.py "
            f"{donor_ref} --target-binary {binary} --signature-bytes 96 --format candidate-validation "
            "> build/server-ue4ss-package-donor-candidate-validation.json"
        ),
        "listDonorSymbols": f"nm -an --demangle {donor_ref} | rg '{needles}'",
        "dumpDonorFunctions": (
            "objdump -d --demangle --no-show-raw-insn "
            f"{donor_ref} | rg -n -A80 -B12 '{needles}'"
        ),
        "validateTransferredSignature": (
            "scripts/validate-elf-signatures.py "
            f"{binary} --donor-candidate-validation-json build/server-ue4ss-package-donor-candidate-validation.json "
            "--category package --scope executable --max-matches 8 --format json "
            "> build/server-ue4ss-package-donor-target-validation.json"
        ),
        "exportPromotedManifest": (
            "scripts/export-elf-signature-manifest.py "
            f"{binary} --validation-json build/server-ue4ss-package-donor-target-validation.json "
            "--target-loader server --format anchor-signatures > build/server-ue4ss-package-anchor-signatures.txt"
        ),
    }


def promotion_acceptance():
    return {
        "schemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        "requiredAnchorFamilies": list(PACKAGE_ANCHORS),
        "acceptableProofPaths": [
            "external-symbol-signature-transfer",
            "runtime-call-frame-trace",
        ],
        "targetImageRequired": True,
        "tracePidMatchRequired": True,
        "sourceLogRequired": True,
        "requiredReviewFlags": {
            "common": ["--reviewed-target-image", "--reviewed-abi"],
            "StaticLoadClass": ["--reviewed-class-root"],
            "StaticLoadObject": ["--reviewed-tchar", "--tchar-unit-bytes <1|2|4>"],
            "LoadObject": ["--reviewed-tchar", "--tchar-unit-bytes <1|2|4>"],
            "LoadPackage": ["--reviewed-tchar", "--tchar-unit-bytes <1|2|4>"],
            "ResolveName": ["--reviewed-tchar", "--tchar-unit-bytes <1|2|4>"],
        },
        "nativeInvokePromotionRequires": [
            "--allow-native-invoke",
            "--final-native-call",
            "reviewed ABI/TCHAR or class-root evidence",
            "target-image caller/rip image offsets",
            "trace log armed PID matches requested runtime PID",
        ],
        "rejectProofKinds": [
            "async-package-vtable-method-only",
            "string-only-hit",
            "loader-image-anchor",
            "non-target-image-call-frame",
        ],
    }


def historical_string_seeds(paths):
    rows_by_key = {}
    pattern = re.compile(
        r"`(?P<name>StaticLoadObject|StaticLoadClass|LoadObject|LoadPackage|ResolveName)`"
        r".*?(?:value=`?|offset `?|hit `?)(?P<addr>0x[0-9a-fA-F]+)"
    )
    for path_text in paths:
        path = Path(path_text)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.search(line)
            if not match:
                continue
            key = (match.group("name"), match.group("addr").lower())
            row = rows_by_key.setdefault(
                key,
                {
                    "name": match.group("name"),
                    "address": match.group("addr").lower(),
                    "sources": [],
                    "promotion": "non-promotable-string-only",
                    "use": "runtime trace seed only; find code/data references or runtime call-frame evidence before promotion",
                },
            )
            if str(path) not in row["sources"]:
                row["sources"].append(str(path))
    return sorted(rows_by_key.values(), key=lambda row: (row["name"], int(row["address"], 16)))


def build_plan(evidence, binary, donor="", historical_surfaces=DEFAULT_HISTORICAL_SURFACES, donor_search=None):
    state = evidence_state(evidence)
    exhausted = (
        not state["completePackageRoute"]
        and state["promotableRouteCount"] == 0
        and state["decompileReviewQueueCount"] == 0
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceEvidence": DEFAULT_EVIDENCE,
        "binary": binary_identity(binary),
        "state": state,
        "anchorFamilies": list(PACKAGE_ANCHORS),
        "donorRequirements": donor_requirements(),
        "nextPath": (
            "external-symbol-or-runtime-trace"
            if exhausted
            else "finish queued local package-route evidence first"
        ),
        "runtimeTraceTarget": {
            "goal": "capture a concrete StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName call frame",
            "acceptance": [
                "target address is inside the target image executable mapping",
                "signature family and SysV x86_64 argument order are reviewed",
                "guarded LoadAsset or LoadClass native invoke returns a validated UObject/UClass handle",
            ],
        },
        "promotionAcceptance": promotion_acceptance(),
        "historicalStringSeeds": historical_string_seeds(historical_surfaces),
        "donorSearch": donor_search_summary(donor_search),
        "commands": build_commands(binary, donor) if exhausted else {},
    }


def markdown(plan):
    lines = ["# UE4SS Package External Symbol Plan", ""]
    state = plan["state"]
    ident = plan["binary"]
    lines.append(f"- Next path: `{plan['nextPath']}`")
    lines.append(f"- Complete package route: `{str(state['completePackageRoute']).lower()}`")
    lines.append(f"- Promotable routes: `{state['promotableRouteCount']}`")
    lines.append(f"- Decompile review queue: `{state['decompileReviewQueueCount']}`")
    lines.append(f"- Binary: `{ident['path']}` present=`{str(ident['present']).lower()}`")
    if ident.get("buildId"):
        lines.append(f"- Build ID: `{ident['buildId']}`")
    if ident.get("sha256"):
        lines.append(f"- SHA256: `{ident['sha256']}`")
    lines.append("")
    lines.append("## Required Donor")
    lines.append("")
    for item in plan["donorRequirements"]:
        lines.append(f"- {item}")
    donor_search = plan.get("donorSearch", {})
    if donor_search:
        lines.append("")
        lines.append("## Local Donor Search")
        lines.append("")
        lines.append(f"- Candidate count: `{donor_search.get('candidateCount', 0)}`")
        lines.append(f"- Usable candidate count: `{donor_search.get('usableCandidateCount', 0)}`")
        lines.append(f"- Source candidate count: `{donor_search.get('sourceCandidateCount', 0)}`")
        lines.append(f"- False-positive candidate count: `{donor_search.get('falsePositiveCandidateCount', 0)}`")
        lines.append(f"- Next step: {donor_search.get('nextStep', '')}")
        preview = donor_search.get("candidatePreview", [])
        if preview:
            lines.append("")
            for candidate in preview:
                anchors = candidate.get("anchorsPresent", []) or []
                lines.append(
                    f"- `{candidate.get('path', '')}` usable=`{str(candidate.get('usable')).lower()}` "
                    f"anchors=`{','.join(anchors)}` promotableSymbols=`{candidate.get('promotableSymbolCount', 0)}`"
                )
                if candidate.get("rejectionReason"):
                    lines.append(f"  - rejection: {candidate['rejectionReason']}")
        source_preview = donor_search.get("sourceCandidatePreview", [])
        if source_preview:
            lines.append("")
            lines.append("### Source Candidates")
            lines.append("")
            for candidate in source_preview:
                anchors = candidate.get("anchorsPresent", []) or []
                lines.append(
                    f"- `{candidate.get('path', '')}` anchors=`{','.join(anchors)}` "
                    f"anchorCount=`{candidate.get('anchorCount', 0)}`"
                )
                if candidate.get("nextStep"):
                    lines.append(f"  - next step: {candidate['nextStep']}")
    lines.append("")
    lines.append("## Anchor Families")
    lines.append("")
    lines.append("- `" + "`, `".join(plan["anchorFamilies"]) + "`")
    lines.append("")
    lines.append("## Runtime Trace Acceptance")
    lines.append("")
    lines.append(f"- {plan['runtimeTraceTarget']['goal']}")
    for item in plan["runtimeTraceTarget"]["acceptance"]:
        lines.append(f"- {item}")
    acceptance = plan.get("promotionAcceptance", {})
    if acceptance:
        lines.append("")
        lines.append("## Promotion Acceptance")
        lines.append("")
        lines.append("- Proof paths: `" + "`, `".join(acceptance.get("acceptableProofPaths", [])) + "`")
        lines.append("- Target image required: `" + str(acceptance.get("targetImageRequired", False)).lower() + "`")
        lines.append("- Trace PID match required: `" + str(acceptance.get("tracePidMatchRequired", False)).lower() + "`")
        lines.append("- Source log required: `" + str(acceptance.get("sourceLogRequired", False)).lower() + "`")
        lines.append("- Reject proof kinds: `" + "`, `".join(acceptance.get("rejectProofKinds", [])) + "`")
    seeds = plan.get("historicalStringSeeds", [])
    if seeds:
        lines.append("")
        lines.append("## Historical Trace Seeds")
        lines.append("")
        for seed in seeds:
            lines.append(
                f"- `{seed['name']}` `{seed['address']}` promotion=`{seed['promotion']}`"
            )
            lines.append("  - sources: `" + "`, `".join(seed["sources"]) + "`")
            lines.append(f"  - use: {seed['use']}")
    if plan.get("commands"):
        lines.append("")
        lines.append("## Commands")
        lines.append("")
        lines.append("```bash")
        for command in plan["commands"].values():
            lines.append(command)
        lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan the external-symbol/runtime trace path for UE4SS package parity.")
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    parser.add_argument("--binary", default=DEFAULT_BINARY)
    parser.add_argument("--donor-binary", default="")
    parser.add_argument("--donor-search", default="")
    parser.add_argument("--historical-surface", action="append", default=[])
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    historical_surfaces = args.historical_surface or list(DEFAULT_HISTORICAL_SURFACES)
    donor_search = load_optional_json(args.donor_search)
    if isinstance(donor_search, dict):
        donor_search.setdefault("sourcePath", args.donor_search)
    plan = build_plan(load_json(args.evidence), args.binary, args.donor_binary, historical_surfaces, donor_search)
    if args.format == "json":
        json.dump(plan, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
