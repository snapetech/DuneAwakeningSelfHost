#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-static-metadata-recovery/v1"
PACKAGE_ANCHORS = ("StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName")


def run_text(args):
    try:
        proc = subprocess.run(args, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        return "", str(exc), 127
    return proc.stdout, proc.stderr, proc.returncode


def has_debug_lines(binary):
    stdout, stderr, returncode = run_text(["readelf", "--debug-dump=decodedline", str(binary)])
    meaningful = [
        line
        for line in stdout.splitlines()
        if line.strip() and "Contents of the" not in line and "Raw dump" not in line
    ]
    return {
        "available": bool(meaningful),
        "lineCount": len(meaningful),
        "returncode": returncode,
        "stderr": stderr.strip()[:200],
    }


def symbol_anchor_state(binary):
    stdout, stderr, returncode = run_text(["nm", "-an", "--demangle", str(binary)])
    rows = []
    for line in stdout.splitlines():
        if any(anchor in line for anchor in PACKAGE_ANCHORS):
            rows.append(line)
    return {
        "anchorSymbolCount": len(rows),
        "anchorSymbols": rows[:16],
        "returncode": returncode,
        "stderr": stderr.strip()[:200],
    }


def load_json(path):
    candidate = Path(path)
    if not candidate.is_file():
        return {}
    try:
        return json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}


def source_pointer_state(path):
    data = load_json(path)
    targets = data.get("targets", []) or []
    contexts = data.get("contexts", []) or []
    return {
        "path": str(path),
        "targetCount": len(targets),
        "contextCount": len(contexts),
        "targetNames": [row.get("name", "") for row in targets if isinstance(row, dict)][:16],
    }


def summarize(binary, source_pointer_json):
    debug = has_debug_lines(binary)
    symbols = symbol_anchor_state(binary)
    source_pointers = source_pointer_state(source_pointer_json)
    blockers = []
    if not debug["available"]:
        blockers.append("target binary has no decoded DWARF line table entries for source-line recovery")
    if symbols["anchorSymbolCount"] == 0:
        blockers.append("target binary exposes no package-loading anchor symbols through nm")
    if source_pointers["contextCount"] == 0:
        blockers.append("source-path pointer context JSON has no structured code/function contexts")
    complete = not blockers
    return {
        "schemaVersion": SCHEMA_VERSION,
        "complete": complete,
        "binary": str(binary),
        "debugLines": debug,
        "symbolAnchors": symbols,
        "sourcePointerContext": source_pointers,
        "blockers": blockers,
        "nextStep": (
            "use decoded source-line/symbol metadata to recover package ABI candidates"
            if complete
            else "local stripped metadata cannot recover the package entry; use external symbols or live runtime call-frame evidence"
        ),
    }


def markdown(summary):
    lines = ["# UE4SS Package Static Metadata Recovery", ""]
    lines.append(f"- Complete: `{str(summary['complete']).lower()}`")
    lines.append(f"- Binary: `{summary['binary']}`")
    lines.append(f"- Debug line entries: `{summary['debugLines']['lineCount']}`")
    lines.append(f"- Anchor symbols: `{summary['symbolAnchors']['anchorSymbolCount']}`")
    lines.append(f"- Source pointer contexts: `{summary['sourcePointerContext']['contextCount']}`")
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
    parser = argparse.ArgumentParser(description="Summarize target static metadata available for UE4SS package ABI recovery.")
    parser.add_argument("--binary", default="/tmp/dune-live-server-extract/DuneSandboxServer-Linux-Shipping")
    parser.add_argument("--source-pointer-json", default="build/server-package-source-path-pointer-context.json")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    summary = summarize(args.binary, args.source_pointer_json)
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(markdown(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
