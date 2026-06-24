#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-source-abi-recovery/v1"


TYPEDEF_RE = re.compile(
    r"typedef\s+void\s+\*\(\s*\*\s*(?P<name>LoadAssetPackage(?:StaticLoadObject|LoadPackage)Fn)\s*\)"
    r"\((?P<args>[^;]+)\);"
)
REQUIRED_SIGNATURE_RE = re.compile(r'"(?P<signature>(?:UObject|UPackage)\*\([^"]+\))"')


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


def parse_loader_contract(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    typedefs = []
    for match in TYPEDEF_RE.finditer(text):
        typedefs.append(
            {
                "name": match.group("name"),
                "arguments": " ".join(match.group("args").split()),
                "argumentCount": len([part for part in match.group("args").split(",") if part.strip()]),
            }
        )
    signatures = sorted({match.group("signature") for match in REQUIRED_SIGNATURE_RE.finditer(text)})
    tchar_unit_match = re.search(r"observed_unit_bytes\s*==\s*sizeof\(wchar_t\)", text) is not None
    guarded_call = "load_asset_package_run_guarded_native_call" in text
    return {
        "path": str(path),
        "typedefs": typedefs,
        "typedefCount": len(typedefs),
        "requiredSignatures": signatures,
        "requiredSignatureCount": len(signatures),
        "usesHostWcharTForTcharCandidate": "wchar_t" in text,
        "requiresObservedTcharUnitMatch": tchar_unit_match,
        "hasGuardedNativeCallAdapter": guarded_call,
    }


def donor_state(donor_search):
    candidates = donor_search.get("candidates", []) or []
    usable = [row for row in candidates if row.get("usable") is True]
    rejected = [row for row in candidates if row.get("usable") is False]
    return {
        "candidateCount": int(donor_search.get("candidateCount", len(candidates)) or 0),
        "usableCandidateCount": int(donor_search.get("usableCandidateCount", len(usable)) or 0),
        "sourceCandidateCount": int(donor_search.get("sourceCandidateCount", 0) or 0),
        "rejectedCandidateCount": len(rejected),
        "topRejectionReasons": sorted(
            {
                row.get("rejectionReason", "")
                for row in rejected
                if row.get("rejectionReason")
            }
        ),
    }


def route_state(route_evidence):
    return {
        "routeCount": int(route_evidence.get("routeCount", 0) or 0),
        "promotableRouteCount": int(route_evidence.get("promotableRouteCount", 0) or 0),
        "complete": bool(route_evidence.get("complete", False)),
    }


def summarize(loader, route_evidence=None, donor_search=None):
    route = route_state(route_evidence or {})
    donor = donor_state(donor_search or {})
    contract = parse_loader_contract(loader)
    blockers = []
    if route["promotableRouteCount"] == 0:
        blockers.append("no target-image package-loading anchor has been promoted from route evidence")
    if donor["usableCandidateCount"] == 0:
        blockers.append("no usable external Linux UE donor or linker-map symbol source is available")
    if not contract["requiresObservedTcharUnitMatch"]:
        blockers.append("loader does not enforce observed TCHAR unit-size evidence")
    if not contract["hasGuardedNativeCallAdapter"]:
        blockers.append("loader does not expose a guarded native call adapter")
    complete = not blockers and contract["typedefCount"] >= 2 and contract["requiredSignatureCount"] >= 2
    return {
        "schemaVersion": SCHEMA_VERSION,
        "complete": complete,
        "loaderContract": contract,
        "routeEvidence": route,
        "donorSearch": donor,
        "blockers": blockers,
        "nextStep": (
            "promote the reviewed source-level package ABI contract into native invoke canary planning"
            if complete
            else "recover one target-image package anchor, then verify SysV argument order and observed TCHAR unit size against the loader contract"
        ),
    }


def markdown(summary):
    contract = summary["loaderContract"]
    lines = ["# UE4SS Package Source ABI Recovery", ""]
    lines.append(f"- Complete: `{str(summary['complete']).lower()}`")
    lines.append(f"- Loader: `{contract['path']}`")
    lines.append(f"- Typedefs: `{contract['typedefCount']}`")
    lines.append(f"- Required signatures: `{contract['requiredSignatureCount']}`")
    lines.append(f"- Requires observed TCHAR unit match: `{str(contract['requiresObservedTcharUnitMatch']).lower()}`")
    lines.append(f"- Guarded native call adapter: `{str(contract['hasGuardedNativeCallAdapter']).lower()}`")
    lines.append("")
    lines.append("## Typedefs")
    lines.append("")
    for row in contract.get("typedefs", []):
        lines.append(f"- `{row['name']}` args=`{row['argumentCount']}` `{row['arguments']}`")
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
    parser = argparse.ArgumentParser(description="Summarize UE4SS package source-level ABI recovery state.")
    parser.add_argument("--loader", default="tools/linux-server-loader/dune_server_probe_loader.c")
    parser.add_argument("--route-evidence-json", default="build/server-current-anchor-prep/ue4ss-package-route-evidence.json")
    parser.add_argument("--donor-search-json", default="build/server-ue4ss-package-donor-search.json")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize(
        args.loader,
        route_evidence=load_json(args.route_evidence_json),
        donor_search=load_json(args.donor_search_json),
    )
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(markdown(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
