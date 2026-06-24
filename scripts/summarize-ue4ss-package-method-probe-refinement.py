#!/usr/bin/env python3
import argparse
import importlib.util
import json
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-method-probe-refinement/v1"


def load_route_module():
    path = Path(__file__).with_name("summarize-ue4ss-package-route-evidence.py")
    spec = importlib.util.spec_from_file_location("package_route_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def reviewed_method_addresses(method_review):
    addresses = set()
    if not method_review:
        return addresses
    for row in method_review.get("reviewedRoutes", []) or []:
        for key in ("imageOffset", "target", "address"):
            value = row.get(key)
            if value:
                addresses.add(str(value).lower())
    return addresses


def owner_priority(owner):
    if "FLinkerLoad" in owner:
        return 0
    if "FAsyncPackage2" in owner:
        return 20
    if "FAsyncPackage" in owner:
        return 30
    if "FBootLoadObjectData" in owner or "FBootLoadClassData" in owner:
        return 45
    return 80


def slot_score(owner, slot):
    shape = slot.get("shape", {}) or {}
    score = owner_priority(owner)
    if shape.get("hasIndirectCall"):
        score -= 8
    if shape.get("hasCall"):
        score -= 5
    if int(shape.get("callOpcodeCount", 0) or 0) >= 2:
        score -= 2
    if shape.get("returnsConstantZero"):
        score += 20
    if slot.get("candidateKind") != "method":
        score += 25
    return score


def build_refinement(vtables, method_review=None, limit=12):
    route_module = load_route_module()
    known_non_package = set(route_module.KNOWN_NON_PACKAGE_FUNCTIONS)
    reviewed = reviewed_method_addresses(method_review)
    candidates = []
    excluded = []
    for row in vtables.get("rows", []) or []:
        owner = row.get("demangled", "")
        for slot in row.get("executableSlots", []) or []:
            address = str(slot.get("value") or slot.get("target") or "").lower()
            if not address:
                continue
            reason = ""
            if address in known_non_package:
                reason = "known-non-package-function"
            elif address in reviewed:
                reason = "reviewed-runtime-method-route"
            elif slot.get("candidateKind") != "method":
                reason = "not-method-slot"
            elif not (slot.get("shape", {}) or {}).get("hasCall") and not (
                slot.get("shape", {}) or {}
            ).get("hasIndirectCall"):
                reason = "method-slot-without-call-edge"
            if reason:
                excluded.append(
                    {
                        "address": address,
                        "owner": owner,
                        "slotIndex": slot.get("index"),
                        "reason": reason,
                    }
                )
                continue
            shape = slot.get("shape", {}) or {}
            candidates.append(
                {
                    "address": address,
                    "owner": owner,
                    "slotIndex": slot.get("index"),
                    "score": slot_score(owner, slot),
                    "shape": {
                        "hasCall": bool(shape.get("hasCall")),
                        "hasIndirectCall": bool(shape.get("hasIndirectCall")),
                        "callOpcodeCount": int(shape.get("callOpcodeCount", 0) or 0),
                        "jumpOpcodeCount": int(shape.get("jumpOpcodeCount", 0) or 0),
                    },
                    "reason": "unreviewed package-adjacent method slot; probe explicitly before broad vtable retry",
                }
            )
    candidates.sort(key=lambda row: (row["score"], row["address"], row.get("slotIndex") or 0))
    selected = candidates[:limit]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "candidateCount": len(candidates),
        "selectedCount": len(selected),
        "excludedCount": len(excluded),
        "selectedAddresses": [row["address"] for row in selected],
        "selectedCandidates": selected,
        "excludedSample": excluded[:limit],
        "nextStep": (
            "run a guarded runtime trace with these explicit --method-address probes plus package string watchpoints"
            if selected
            else "no unreviewed package-adjacent method probes remain; recover external/static symbol evidence"
        ),
    }


def markdown(summary):
    lines = ["# UE4SS Package Method Probe Refinement", ""]
    lines.append(f"- Candidates: `{summary['candidateCount']}`")
    lines.append(f"- Selected: `{summary['selectedCount']}`")
    lines.append(f"- Excluded: `{summary['excludedCount']}`")
    lines.append(f"- Next step: {summary['nextStep']}")
    lines.append("")
    lines.append("## Selected")
    lines.append("")
    for row in summary.get("selectedCandidates", []):
        lines.append(
            f"- `{row['address']}` owner=`{row['owner']}` slot=`{row['slotIndex']}` score=`{row['score']}`"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Rank unreviewed UE4SS package method probes.")
    parser.add_argument("vtables", nargs="?", default="build/server-ue-package-loader-vtables.json")
    parser.add_argument(
        "--method-review",
        default="build/server-current-anchor-prep/ue4ss-package-method-route-review.json",
    )
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    method_review = None
    review_path = Path(args.method_review)
    if review_path.exists():
        method_review = load_json(review_path)
    summary = build_refinement(load_json(args.vtables), method_review, args.limit)
    if args.format == "markdown":
        print(markdown(summary), end="")
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
