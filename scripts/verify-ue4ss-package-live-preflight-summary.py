#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-live-preflight-summary-verification/v1"
SUMMARY_SCHEMA_VERSION = "dune-ue4ss-package-live-preflight-summary/v1"


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def single_line(value):
    return isinstance(value, str) and value != "" and "\n" not in value and "\r" not in value


def positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def same_path(left, right):
    if not left or not right:
        return False
    try:
        return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(strict=False)
    except OSError:
        return str(left) == str(right)


def parse_utc(value):
    if not isinstance(value, str) or not value:
        return None
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def verify_summary(summary, runbook=None, next_action=None, max_age_seconds=None, now=None):
    blockers = []
    if summary.get("schemaVersion") != SUMMARY_SCHEMA_VERSION:
        blockers.append(f"summary schemaVersion must be {SUMMARY_SCHEMA_VERSION}")
    for key in ("runbook", "sourceRunbook", "traceRemote", "container", "traceLog", "createdUtc"):
        if not single_line(summary.get(key, "")):
            blockers.append(f"summary {key} must be a non-empty single-line string")
    trace_override = summary.get("traceLogOverride", "")
    if trace_override not in ("", None) and not single_line(trace_override):
        blockers.append("summary traceLogOverride must be a single-line string when present")
    if not positive_int(summary.get("operatorWindowSeconds")):
        blockers.append("summary operatorWindowSeconds must be a positive integer")
    created = parse_utc(summary.get("createdUtc", ""))
    if created is None:
        blockers.append("summary createdUtc must be an ISO-8601 UTC timestamp")
    elif max_age_seconds is not None:
        now = now or datetime.now(timezone.utc)
        age_seconds = int((now - created).total_seconds())
        if age_seconds < 0:
            blockers.append("summary createdUtc is in the future")
        elif age_seconds > int(max_age_seconds):
            blockers.append(f"summary createdUtc is stale: ageSeconds={age_seconds} maxAgeSeconds={int(max_age_seconds)}")
    if not isinstance(summary.get("ready"), bool):
        blockers.append("summary ready must be a boolean")
    summary_blockers = summary.get("blockers", [])
    if not isinstance(summary_blockers, list) or any(not isinstance(item, str) for item in summary_blockers):
        blockers.append("summary blockers must be a string array")
        summary_blockers = []
    if summary.get("ready") is True and summary_blockers:
        blockers.append("summary ready must not be true when blockers are present")
    if summary.get("ready") is False and not summary_blockers:
        blockers.append("summary blockers must explain why ready is false")
    fields = summary.get("fields", {})
    if not isinstance(fields, dict):
        blockers.append("summary fields must be an object")
        fields = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not isinstance(value, str) or "\n" in key or "\r" in key or "\n" in value or "\r" in value:
            blockers.append("summary fields must contain only single-line string keys and values")
            break
    if summary.get("traceLogOverride"):
        if summary.get("traceLogOverride") != summary.get("traceLog"):
            blockers.append("summary traceLogOverride must match traceLog when an override was used")
        if summary.get("runbook") == summary.get("sourceRunbook"):
            blockers.append("summary runbook must be the effective override runbook when traceLogOverride is set")
    elif summary.get("runbook") != summary.get("sourceRunbook"):
        blockers.append("summary runbook must match sourceRunbook when no traceLogOverride is set")
    if fields.get("preflight") != "ok":
        blockers.append("summary fields.preflight must be ok")
    if fields.get("remote_host") and fields.get("remote_host") != summary.get("traceRemote"):
        blockers.append("summary fields.remote_host does not match traceRemote")
    if fields.get("container") and fields.get("container") != summary.get("container"):
        blockers.append("summary fields.container does not match container")
    if fields.get("trace_log") and fields.get("trace_log") != summary.get("traceLog"):
        blockers.append("summary fields.trace_log does not match traceLog")
    if fields.get("player_guard_preflight_connected_players") != "0":
        blockers.append("summary player_guard_preflight_connected_players must be 0")
    if not fields.get("server_pid", "").isdigit():
        blockers.append("summary fields.server_pid must be numeric")

    if runbook:
        runbook_paths = [value for value in (runbook.get("sourcePath", ""), runbook.get("_path", "")) if value]
        if not any(same_path(summary.get("sourceRunbook", ""), path) for path in runbook_paths):
            blockers.append("summary sourceRunbook does not match stimulus runbook path")
        if summary.get("traceRemote") != runbook.get("remote"):
            blockers.append("summary traceRemote does not match stimulus runbook remote")
        if summary.get("container") != runbook.get("container"):
            blockers.append("summary container does not match stimulus runbook container")
        if not summary.get("traceLogOverride") and summary.get("traceLog") != runbook.get("traceLog"):
            blockers.append("summary traceLog does not match stimulus runbook traceLog")
        window = runbook.get("operatorWindow", {}) or {}
        max_seconds = window.get("maxArmSeconds")
        if positive_int(max_seconds) and summary.get("operatorWindowSeconds", 0) > max_seconds:
            blockers.append("summary operatorWindowSeconds exceeds stimulus runbook maxArmSeconds")
        trace_inputs = runbook.get("traceInputs", {}) or {}
        trace_env = runbook.get("traceEnv", {}) or {}
        route_address = trace_inputs.get("routeAddress", "")
        if route_address:
            if trace_env.get("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS") != route_address:
                blockers.append("runbook traceEnv route address does not match traceInputs routeAddress")
            cleanup_command = runbook.get("cleanupCommand", "")
            if f"DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS={route_address}" not in cleanup_command:
                blockers.append("runbook cleanupCommand is missing required route address export")
            if fields.get("route_address") != route_address:
                blockers.append("summary fields.route_address does not match runbook traceInputs routeAddress")
    if next_action:
        live = next_action.get("liveTraceRunbook", {}) or {}
        if live.get("remote") and summary.get("traceRemote") != live.get("remote"):
            blockers.append("summary traceRemote does not match next-action liveTraceRunbook remote")
        if live.get("container") and summary.get("container") != live.get("container"):
            blockers.append("summary container does not match next-action liveTraceRunbook container")
    return blockers


def report(summary_path, runbook_path=None, next_action_path=None, max_age_seconds=None):
    try:
        summary = load_json(summary_path)
    except FileNotFoundError:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ready": False,
            "summary": str(summary_path),
            "runbook": str(runbook_path) if runbook_path else "",
            "nextAction": str(next_action_path) if next_action_path else "",
            "blockers": ["preflight summary JSON is missing"],
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ready": False,
            "summary": str(summary_path),
            "runbook": str(runbook_path) if runbook_path else "",
            "nextAction": str(next_action_path) if next_action_path else "",
            "blockers": [f"preflight summary JSON is unreadable: {exc}"],
        }
    runbook = None
    if runbook_path:
        runbook = load_json(runbook_path)
        runbook["_path"] = str(runbook_path)
    next_action = None
    if next_action_path:
        next_action = load_json(next_action_path)
        next_action["_path"] = str(next_action_path)
    blockers = verify_summary(
        summary,
        runbook=runbook,
        next_action=next_action,
        max_age_seconds=max_age_seconds,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ready": not blockers,
        "summary": str(summary_path),
        "runbook": str(runbook_path) if runbook_path else "",
        "nextAction": str(next_action_path) if next_action_path else "",
        "blockers": blockers,
    }


def markdown(data):
    lines = [
        "# UE4SS Package Live Preflight Summary Verification",
        "",
        f"- Summary: `{data.get('summary', '')}`",
        f"- Ready: `{str(data.get('ready', False)).lower()}`",
    ]
    if data.get("runbook"):
        lines.append(f"- Runbook: `{data['runbook']}`")
    if data.get("nextAction"):
        lines.append(f"- Next action: `{data['nextAction']}`")
    if data.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in data["blockers"])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify a UE4SS package live preflight summary.")
    parser.add_argument("summary", type=Path)
    parser.add_argument("--runbook-json", type=Path)
    parser.add_argument("--next-action-json", type=Path)
    parser.add_argument("--max-age-seconds", type=int)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    data = report(
        args.summary,
        runbook_path=args.runbook_json,
        next_action_path=args.next_action_json,
        max_age_seconds=args.max_age_seconds,
    )
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(markdown(data), end="")
    return 0 if data["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
