#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SUMMARY_SCHEMA_VERSION = "dune-ue4ss-package-live-stimulus-review-summary/v1"
REFRESH_SCHEMA_VERSION = "dune-ue4ss-package-live-stimulus-classification-refresh/v1"


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def no_selected_runtime_hit(blockers):
    return any(
        "selected runtime trace hit is missing" in str(blocker) or str(blocker).strip() == "missing hit"
        for blocker in blockers or []
    )


def build_origin_classification(summary, runbook):
    runbook_origin = runbook.get("originClassification") or {}
    if not isinstance(runbook_origin, dict):
        runbook_origin = {}
    blockers = summary.get("blockers") or []
    ready = summary.get("ready") is True
    classification_blockers = []
    if no_selected_runtime_hit(blockers):
        status = "missing"
        classification_blockers.append("package-load classification has no selected runtime package hit")
    elif ready:
        status = "client-originated-pending-server-replay"
    else:
        status = "inconclusive"
        classification_blockers.append("package-load classification evidence is not ready")
    return {
        "status": status,
        "source": "live-stimulus-classification-refresh",
        "probeCandidate": runbook_origin.get("probeCandidate", ""),
        "serverSideFallbackCandidate": runbook_origin.get("serverSideFallbackCandidate", ""),
        "decision": runbook_origin.get(
            "decision",
            "trace first; classify whether the normal request reaches a usable server-side path; "
            "if it does not, recover and replay/spoof the equivalent call server-side",
        ),
        "requiresServerSideReplay": status == "client-originated-pending-server-replay",
        "blockers": classification_blockers,
    }


def refresh(summary, runbook):
    if summary.get("schemaVersion") != SUMMARY_SCHEMA_VERSION:
        raise ValueError(f"summary schemaVersion must be {SUMMARY_SCHEMA_VERSION}")
    if runbook.get("originClassification") is None:
        raise ValueError("runbook must contain originClassification")
    updated = dict(summary)
    updated["originClassification"] = build_origin_classification(summary, runbook)
    return updated


def refresh_report(summary_path, runbook_path, output_path=None):
    summary = load_json(summary_path)
    runbook = load_json(runbook_path)
    updated = refresh(summary, runbook)
    target = Path(output_path) if output_path else Path(summary_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "schemaVersion": REFRESH_SCHEMA_VERSION,
        "summary": str(summary_path),
        "runbook": str(runbook_path),
        "output": str(target),
        "originClassification": updated.get("originClassification"),
        "ready": updated.get("ready") is True,
        "blockers": updated.get("blockers", []),
    }


def markdown(report):
    origin = report.get("originClassification") or {}
    lines = [
        "# UE4SS Package Live Stimulus Classification Refresh",
        "",
        f"- Output: `{report.get('output', '')}`",
        f"- Summary ready: `{str(report.get('ready', False)).lower()}`",
        f"- Origin status: `{origin.get('status', '')}`",
        f"- Server-side replay required: `{str(origin.get('requiresServerSideReplay', False)).lower()}`",
    ]
    for blocker in origin.get("blockers", []) or []:
        lines.append(f"- Classification blocker: {blocker}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Refresh originClassification in a UE4SS package live-stimulus summary."
    )
    parser.add_argument("summary_json", type=Path)
    parser.add_argument("--runbook-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    report = refresh_report(args.summary_json, args.runbook_json, args.output_json)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(markdown(report), end="")


if __name__ == "__main__":
    raise SystemExit(main())
