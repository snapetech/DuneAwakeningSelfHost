#!/usr/bin/env python3
import argparse
from collections import Counter, defaultdict
import json
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-runtime-route-refinement/v1"
TRACE_EVIDENCE_SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-evidence/v1"


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def valid_hex(value):
    text = str(value)
    return text.startswith("0x") and len(text) > 2 and all(char in "0123456789abcdefABCDEF" for char in text[2:])


def normalize_hex(value):
    if not valid_hex(value):
        return ""
    return f"0x{int(str(value), 16):x}"


def route_hit_rows(evidence):
    rows = []
    for index, hit in enumerate(evidence.get("routeHits", []) or []):
        if not isinstance(hit, dict):
            continue
        route = normalize_hex(hit.get("ripImageOffset") or hit.get("imageOffset"))
        caller = normalize_hex(hit.get("callerImageOffset"))
        if not route or not caller:
            continue
        rows.append(
            {
                "hitIndex": index,
                "routeImageOffset": route,
                "callerImageOffset": caller,
                "rip": hit.get("rip", ""),
                "caller": hit.get("caller", {}) if isinstance(hit.get("caller"), dict) else {},
                "backtrace": hit.get("backtrace", []) if isinstance(hit.get("backtrace"), list) else [],
                "disassembly": hit.get("disassembly", []) if isinstance(hit.get("disassembly"), list) else [],
                "stack": hit.get("stack", []) if isinstance(hit.get("stack"), list) else [],
            }
        )
    return rows


def method_hit_rows(evidence):
    rows = []
    for index, hit in enumerate(evidence.get("methodHits", []) or []):
        if not isinstance(hit, dict):
            continue
        method = normalize_hex(hit.get("ripImageOffset") or hit.get("imageOffset"))
        caller = normalize_hex(hit.get("callerImageOffset"))
        if not method or not caller:
            continue
        rows.append(
            {
                "hitIndex": index,
                "methodImageOffset": method,
                "callerImageOffset": caller,
                "owner": hit.get("owner", ""),
                "slotIndex": hit.get("slotIndex", ""),
            }
        )
    return rows


def selected_routes(route_rows, method_rows, limit):
    route_count = Counter(row["routeImageOffset"] for row in route_rows)
    caller_count = Counter(row["callerImageOffset"] for row in route_rows)
    method_caller_count = Counter(row["callerImageOffset"] for row in method_rows)
    examples = defaultdict(list)
    for row in route_rows:
        if len(examples[row["callerImageOffset"]]) < 3:
            examples[row["callerImageOffset"]].append(row)
    rows = []
    for caller, count in caller_count.items():
        route_sources = sorted({row["routeImageOffset"] for row in route_rows if row["callerImageOffset"] == caller})
        rows.append(
            {
                "address": caller,
                "routeHitCount": count,
                "methodCallerHitCount": method_caller_count.get(caller, 0),
                "routeSourceCount": len(route_sources),
                "routeSources": route_sources,
                "score": count * 10 + method_caller_count.get(caller, 0) + len(route_sources),
                "promotion": "non-promotable-route-probe",
                "traceMode": "gdb-breakpoint",
                "use": "probe the caller of the current hot package-adjacent route; promote only after a package trace hit or reviewed package ABI proof",
                "examples": examples.get(caller, []),
            }
        )
    rows.sort(key=lambda row: (-int(row["score"]), int(row["address"], 16)))
    selected = rows[: max(0, limit)]
    return rows, selected, route_count


def summarize(evidence_path, limit=4):
    evidence = load_json(evidence_path)
    schema = evidence.get("schemaVersion", "")
    if schema != TRACE_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(f"{evidence_path} has schemaVersion {schema!r}; expected {TRACE_EVIDENCE_SCHEMA_VERSION!r}")
    route_rows = route_hit_rows(evidence)
    method_rows = method_hit_rows(evidence)
    candidates, selected, route_count = selected_routes(route_rows, method_rows, limit)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceEvidence": str(evidence_path),
        "sourceEvidenceSchemaVersion": schema,
        "sourceLog": evidence.get("sourceLog", ""),
        "sourceLogSha256": evidence.get("sourceLogSha256", ""),
        "hitCount": int(evidence.get("hitCount", 0) or 0),
        "methodHitCount": int(evidence.get("methodHitCount", 0) or 0),
        "routeHitCount": int(evidence.get("routeHitCount", 0) or 0),
        "candidateCount": len(candidates),
        "selectedCount": len(selected),
        "selectedAddresses": [row["address"] for row in selected],
        "recommendedRouteAddressEnv": ",".join(row["address"] for row in selected),
        "hotRouteOffsets": [
            {"address": address, "hitCount": count}
            for address, count in route_count.most_common(8)
        ],
        "candidates": candidates,
        "selectedRoutes": selected,
        "complete": False,
        "nextStep": (
            "regenerate the package runtime trace plan with selectedAddresses as --route-address values and run one bounded live stimulus"
            if selected
            else "capture route hits before refining package route probes"
        ),
        "blockers": [
            "runtime route probes are non-promotable until a package trace hit or reviewed package-loading ABI is captured"
        ],
    }


def markdown(summary):
    lines = ["# UE4SS Package Runtime Route Refinement", ""]
    lines.append(f"- Source evidence: `{summary['sourceEvidence']}`")
    if summary.get("sourceLogSha256"):
        lines.append(f"- Source log SHA-256: `{summary['sourceLogSha256']}`")
    lines.append(f"- Package hits: `{summary['hitCount']}`")
    lines.append(f"- Method hits: `{summary['methodHitCount']}`")
    lines.append(f"- Route hits: `{summary['routeHitCount']}`")
    lines.append(f"- Candidate caller routes: `{summary['candidateCount']}`")
    lines.append(f"- Selected caller routes: `{summary['selectedCount']}`")
    lines.append(f"- Recommended route env: `{summary['recommendedRouteAddressEnv']}`")
    lines.append(f"- Complete: `{str(summary['complete']).lower()}`")
    lines.append(f"- Next step: {summary['nextStep']}")
    lines.append("")
    lines.append("## Hot Route Offsets")
    lines.append("")
    for row in summary.get("hotRouteOffsets", []):
        lines.append(f"- `{row['address']}` hits=`{row['hitCount']}`")
    lines.append("")
    lines.append("## Selected Caller Routes")
    lines.append("")
    for row in summary.get("selectedRoutes", []):
        lines.append(
            f"- `{row['address']}` score=`{row['score']}` "
            f"routeHits=`{row['routeHitCount']}` methodCallerHits=`{row['methodCallerHitCount']}`"
        )
        if row.get("routeSources"):
            lines.append(f"  - route sources: `{','.join(row['routeSources'])}`")
        lines.append(f"  - use: {row['use']}")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    for blocker in summary.get("blockers", []):
        lines.append(f"- {blocker}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank next route probes from UE4SS package runtime route-hit evidence.")
    parser.add_argument("evidence_json")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize(args.evidence_json, limit=args.limit)
    if args.format == "json":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
