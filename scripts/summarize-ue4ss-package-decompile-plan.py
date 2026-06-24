#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-decompile-plan/v1"
DEFAULT_EVIDENCE = "build/server-ue4ss-package-route-evidence.json"
DEFAULT_BINARY = "/tmp/dune-live-server-extract/DuneSandboxServer-Linux-Shipping"


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def unique_preserve(values):
    seen = set()
    out = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def queue_entries(evidence, limit):
    entries = list(evidence.get("decompileReviewQueue", []) or [])
    return entries[:limit]


def suppressed_entries(evidence, limit):
    entries = list(evidence.get("suppressedKnownNonPackageQueue", []) or [])
    return entries[:limit]


def route_by_id(evidence):
    return {row.get("id"): row for row in evidence.get("routes", []) or []}


def classify_plan(evidence):
    routes = route_by_id(evidence)
    package_route = routes.get("package-loader-vtables", {})
    streamable_route = routes.get("streamable-reviewed-callgraph", {})
    raw_route = routes.get("raw-typeinfo-linker-async-callgraph", {})
    blockers = []
    for route in (package_route, raw_route, streamable_route):
        blockers.extend(route.get("blockers", []) or [])
    return {
        "packageLoaderStatus": package_route.get("summary", ""),
        "streamableStatus": streamable_route.get("summary", ""),
        "rawTypeinfoStatus": raw_route.get("summary", ""),
        "knownBlockers": unique_preserve(blockers)[:12],
    }


def build_plan(evidence, binary, review_limit):
    queue = queue_entries(evidence, review_limit)
    suppressed = suppressed_entries(evidence, review_limit)
    offsets = unique_preserve([entry.get("address") for entry in queue])
    output = "build/server-ue4ss-focused-functions.txt"
    if offsets:
        env = (
            "DUNE_GHIDRA_FOCUSED_OUT='" + output + "' "
            + "DUNE_GHIDRA_OFFSETS='"
            + ",".join(offsets)
            + "' "
        )
        commands = {
            "ghidraDryRun": (
                env
                + "scripts/research/run-ghidra-headless.sh --script DumpFocusedFunctions.java "
                + "--mode process --analysis off --binary "
                + binary
                + " --dry-run"
            ),
            "ghidraRunWhenUnlocked": (
                env
                + "scripts/research/run-ghidra-headless.sh --script DumpFocusedFunctions.java "
                + "--mode process --analysis off --binary "
                + binary
            ),
        }
    else:
        commands = {}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceEvidence": DEFAULT_EVIDENCE,
        "binary": binary,
        "completePackageRoute": bool(evidence.get("complete")),
        "promotableRouteCount": int(evidence.get("promotableRouteCount", 0) or 0),
        "reviewLimit": review_limit,
        "focusedOutput": output,
        "ghidraOffsets": offsets,
        "reviewQueue": queue,
        "suppressedKnownNonPackageQueue": suppressed,
        "suppressedKnownNonPackageQueueCount": int(evidence.get("suppressedKnownNonPackageQueueCount", len(suppressed)) or 0),
        "classification": classify_plan(evidence),
        "acceptanceCriteria": [
            "decompile or runtime trace identifies a target-image StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName-equivalent entry",
            "entry has a callable ABI and argument contract compatible with a guarded UE4SS Linux bridge",
            "proof includes at least one successful guarded native LoadAsset or LoadClass invocation against the target image",
            "promoted evidence updates package route summary to complete=true without relying on streamable/delegate/type-erasure false positives",
        ],
        "quickestPath": (
            "tracked local static/decompile candidates are exhausted; next fastest path is external symbol/version matching "
            "or a targeted runtime trace that captures the native StaticLoadObject/LoadPackage call-frame"
            if not offsets and not bool(evidence.get("complete"))
            else "decompile queued offsets and promote only a callable target-image package-loading ABI"
        ),
        "commands": commands,
    }


def markdown(plan):
    lines = ["# UE4SS Package Decompile Plan", ""]
    lines.append(f"- Complete package route: `{str(plan['completePackageRoute']).lower()}`")
    lines.append(f"- Promotable routes: `{plan['promotableRouteCount']}`")
    lines.append(f"- Binary: `{plan['binary']}`")
    lines.append(f"- Review offsets: `{','.join(plan['ghidraOffsets'])}`")
    lines.append("")
    lines.append("## Next Review Targets")
    lines.append("")
    for entry in plan.get("reviewQueue", []):
        lines.append(
            f"- priority `{entry.get('priority')}` `{entry.get('address')}` "
            f"route=`{entry.get('route')}` kind=`{entry.get('kind')}`"
        )
        lines.append(f"  - {entry.get('label')}")
        lines.append(f"  - reason: {entry.get('reason')}")
    suppressed = plan.get("suppressedKnownNonPackageQueue", [])
    if suppressed:
        lines.append("")
        lines.append("## Suppressed Known Non-Package")
        lines.append("")
        for entry in suppressed:
            lines.append(
                f"- `{entry.get('address')}` route=`{entry.get('route')}` kind=`{entry.get('kind')}`"
            )
            lines.append(f"  - {entry.get('label')}")
            lines.append(f"  - reason: {entry.get('reason')}")
    lines.append("")
    lines.append("## Acceptance Criteria")
    lines.append("")
    for item in plan.get("acceptanceCriteria", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Commands")
    lines.append("")
    if plan.get("commands"):
        lines.append("```bash")
        lines.append(plan["commands"]["ghidraDryRun"])
        lines.append(plan["commands"]["ghidraRunWhenUnlocked"])
        lines.append("```")
    else:
        lines.append(plan.get("quickestPath", "no queued decompile commands"))
    lines.append("")
    blockers = plan.get("classification", {}).get("knownBlockers", [])
    if blockers:
        lines.append("## Known Negative Evidence")
        lines.append("")
        for blocker in blockers:
            lines.append(f"- {blocker}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a focused package ABI decompile plan.")
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    parser.add_argument("--binary", default=DEFAULT_BINARY)
    parser.add_argument("--review-limit", type=int, default=12)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    evidence = load_json(args.evidence)
    plan = build_plan(evidence, args.binary, args.review_limit)
    if args.format == "json":
        json.dump(plan, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
