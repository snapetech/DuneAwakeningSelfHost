#!/usr/bin/env python3
import argparse
import json
import shlex
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-seed-batches/v1"
SUPPORTED_FAMILIES = {"StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName"}
DEFAULT_EXTERNAL_PLAN = "build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json"
DEFAULT_TRACE_LOG_PREFIX = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def parse_int(value):
    text = str(value)
    return int(text, 16 if text.lower().startswith("0x") else 10)


def normalize_seed(seed):
    if not isinstance(seed, dict):
        return None
    name = seed.get("name", "")
    address = seed.get("address", "")
    if name not in SUPPORTED_FAMILIES:
        return None
    try:
        parsed = parse_int(address)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return {
        "name": name,
        "address": f"0x{parsed:x}",
        "promotion": seed.get("promotion", ""),
        "use": seed.get("use", ""),
    }


def unique_seeds(external_plan):
    seen = set()
    rows = []
    for raw in external_plan.get("historicalStringSeeds", []) or []:
        seed = normalize_seed(raw)
        if not seed:
            continue
        key = (seed["name"], seed["address"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(seed)
    # Keep LoadPackage visible in batch 1 while preserving stable order within
    # each family. The remaining seeds rotate deterministically.
    family_rank = {
        "LoadPackage": 0,
        "StaticLoadObject": 1,
        "StaticLoadClass": 2,
        "LoadObject": 3,
        "ResolveName": 4,
    }
    return sorted(rows, key=lambda item: (family_rank.get(item["name"], 99), parse_int(item["address"])))


def chunked(rows, size):
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def env_command(env, command):
    parts = [f"{key}={shlex.quote(str(value))}" for key, value in env.items()]
    parts.append(command)
    return " ".join(parts)


def build_batches(
    external_plan,
    batch_size=4,
    trace_log_prefix=DEFAULT_TRACE_LOG_PREFIX,
    coordinator="scripts/run-ue4ss-package-live-stimulus-trace.sh",
    wait_seconds=30,
):
    if batch_size <= 0:
        raise ValueError("batch size must be positive")
    seeds = unique_seeds(external_plan)
    batches = []
    for index, rows in enumerate(chunked(seeds, batch_size), start=1):
        addresses = ",".join(row["address"] for row in rows)
        anchors = ",".join(dict.fromkeys(row["name"] for row in rows))
        trace_log = f"{trace_log_prefix}-batch{index}-$(date -u +%Y%m%dT%H%M%SZ).log"
        env = {
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR": anchors,
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SEED_ADDRESS": addresses,
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT": str(len(rows)),
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY": rows[0]["name"],
        }
        batches.append(
            {
                "index": index,
                "seedCount": len(rows),
                "anchors": anchors,
                "seedAddresses": addresses,
                "signatureFamily": rows[0]["name"],
                "seeds": rows,
                "freshPreflightCommand": env_command(
                    env,
                    f"{coordinator} --preflight-only --wait {wait_seconds} --trace-log {trace_log}",
                ),
                "freshTraceCommand": env_command(
                    env,
                    f"{coordinator} --wait {wait_seconds} --trace-log {trace_log}",
                ),
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceExternalPlan": external_plan.get("sourcePath", DEFAULT_EXTERNAL_PLAN),
        "batchSize": batch_size,
        "seedCount": len(seeds),
        "batchCount": len(batches),
        "hardwareWatchpointReason": "x86_64 hardware watchpoints are limited; rotate package string seeds instead of repeating the same selection",
        "batches": batches,
        "nextStep": "run the next batch freshTraceCommand during a package-load stimulus window; if a package hit appears, classify client-originated versus server-side and replay/spoof server-side only when needed",
    }


def markdown(report):
    lines = ["# UE4SS Package Seed Batch Plan", ""]
    lines.append(f"- Seeds: `{report['seedCount']}`")
    lines.append(f"- Batch size: `{report['batchSize']}`")
    lines.append(f"- Batches: `{report['batchCount']}`")
    lines.append(f"- Reason: {report['hardwareWatchpointReason']}")
    lines.append("")
    for batch in report["batches"]:
        lines.append(f"## Batch {batch['index']}")
        lines.append("")
        lines.append(f"- Anchors: `{batch['anchors']}`")
        lines.append(f"- Seed addresses: `{batch['seedAddresses']}`")
        lines.append(f"- Signature family: `{batch['signatureFamily']}`")
        lines.append(f"- Preflight: `{batch['freshPreflightCommand']}`")
        lines.append(f"- Trace: `{batch['freshTraceCommand']}`")
        for seed in batch["seeds"]:
            lines.append(f"  - `{seed['name']}` `{seed['address']}`")
        lines.append("")
    lines.append(f"Next step: {report['nextStep']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan rotated UE4SS package string seed trace batches.")
    parser.add_argument("--external-plan-json", default=DEFAULT_EXTERNAL_PLAN)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--trace-log-prefix", default=DEFAULT_TRACE_LOG_PREFIX)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    plan = load_json(args.external_plan_json)
    plan.setdefault("sourcePath", args.external_plan_json)
    report = build_batches(plan, batch_size=args.batch_size, trace_log_prefix=args.trace_log_prefix)
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(report))


if __name__ == "__main__":
    main()
