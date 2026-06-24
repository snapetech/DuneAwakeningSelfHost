#!/usr/bin/env python3
import argparse
import hashlib
import json
import shlex
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-live-stimulus-summary-verification/v1"
SUMMARY_SCHEMA_VERSION = "dune-ue4ss-package-live-stimulus-review-summary/v1"
EMBEDDED_EVIDENCE_FIELDS = (
    "reviewBundleVerification,reviewBundleVerificationSha256,"
    "routeSlotRecoveryVerification,routeSlotRecoveryVerificationSha256,"
    "prearmReadinessVerification,prearmReadinessVerificationSha256"
)
RUNBOOK_MODE = "default-source-runbook;trace-log-override-effective-runbook"
ORIGIN_REACHABILITY_CLASSIFICATION_STATUSES = {
    "missing",
    "inconclusive",
    "client-originated-pending-server-replay",
    "server-side-replay-proven",
    "server-originated",
    "not-required",
}


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


def non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def valid_sha256_text(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def json_sha256(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def same_path(left, right):
    if not left or not right:
        return False
    try:
        return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(strict=False)
    except OSError:
        return str(left) == str(right)


def readable_json_file(path):
    if not path:
        return None
    try:
        candidate = Path(path)
        if not candidate.exists() or not candidate.is_file():
            return None
        return load_json(candidate)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def summary_verifier_command_matches(command, summary_path, runbook_paths, next_action_path):
    if isinstance(runbook_paths, (str, Path)):
        runbook_paths = [runbook_paths]
    runbook_paths = [path for path in (runbook_paths or []) if path]
    if not command or not summary_path or not runbook_paths or not next_action_path:
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) < 5:
        return False
    if Path(parts[0]).name != "verify-ue4ss-package-live-stimulus-summary.py":
        return False
    if not same_path(parts[1], summary_path):
        return False
    flags = {}
    index = 2
    while index < len(parts):
        key = parts[index]
        if key == "--format":
            index += 2
            continue
        if index + 1 >= len(parts):
            return False
        flags[key] = parts[index + 1]
        index += 2
    command_runbook = flags.get("--runbook-json", "")
    return any(same_path(command_runbook, path) for path in runbook_paths) and same_path(
        flags.get("--next-action-json", ""), next_action_path
    )


def verify_summary(summary, runbook=None, next_action=None):
    blockers = []
    if summary.get("schemaVersion") != SUMMARY_SCHEMA_VERSION:
        blockers.append(f"summary schemaVersion must be {SUMMARY_SCHEMA_VERSION}")
    for key in (
        "runbook",
        "sourceRunbook",
        "traceRemote",
        "container",
        "traceLog",
        "runStartedUtc",
        "statusFinishedUtc",
        "verifyJson",
    ):
        if not single_line(summary.get(key, "")):
            blockers.append(f"summary {key} must be a non-empty single-line string")
    trace_override = summary.get("traceLogOverride", "")
    if trace_override not in ("", None) and not single_line(trace_override):
        blockers.append("summary traceLogOverride must be a single-line string when present")
    if not positive_int(summary.get("operatorWindowSeconds")):
        blockers.append("summary operatorWindowSeconds must be a positive integer")
    if not isinstance(summary.get("ready"), bool):
        blockers.append("summary ready must be a boolean")
    blockers_value = summary.get("blockers", [])
    if not isinstance(blockers_value, list) or any(not isinstance(item, str) for item in blockers_value):
        blockers.append("summary blockers must be a string array")
        blockers_value = []
    if summary.get("ready") is True and blockers_value:
        blockers.append("summary ready must not be true when blockers are present")
    if summary.get("ready") is False and not blockers_value:
        blockers.append("summary blockers must explain why ready is false")
    if summary.get("ready") is False and blockers_value:
        blockers.extend(f"summary is not ready: {item}" for item in blockers_value)
    for key in ("artifactCount", "checksumCount"):
        value = summary.get(key)
        if value is not None and not non_negative_int(value):
            blockers.append(f"summary {key} must be a non-negative integer when present")
    if summary.get("traceLogOverride"):
        if summary.get("traceLogOverride") != summary.get("traceLog"):
            blockers.append("summary traceLogOverride must match traceLog when an override was used")
        if summary.get("runbook") == summary.get("sourceRunbook"):
            blockers.append("summary runbook must be the effective override runbook when traceLogOverride is set")
    elif summary.get("runbook") != summary.get("sourceRunbook"):
        blockers.append("summary runbook must match sourceRunbook when no traceLogOverride is set")

    origin = summary.get("originClassification")
    if origin is not None and not isinstance(origin, dict):
        blockers.append("summary originClassification must be an object when present")
        origin = None
    if isinstance(origin, dict):
        status = origin.get("status", "")
        if status not in ORIGIN_REACHABILITY_CLASSIFICATION_STATUSES:
            blockers.append("summary originClassification.status is not recognized")
        for key in ("source", "probeCandidate", "serverSideFallbackCandidate", "decision"):
            value = origin.get(key, "")
            if value not in ("", None) and not single_line(value):
                blockers.append(f"summary originClassification.{key} must be a single-line string")
        if not isinstance(origin.get("requiresServerSideReplay"), bool):
            blockers.append("summary originClassification.requiresServerSideReplay must be a boolean")
        gate_blockers = origin.get("blockers", [])
        if not isinstance(gate_blockers, list) or any(not isinstance(item, str) for item in gate_blockers):
            blockers.append("summary originClassification.blockers must be a string array")
        if status == "client-originated-pending-server-replay" and origin.get("requiresServerSideReplay") is not True:
            blockers.append("summary originClassification requires server-side replay when client-originated")
        if status == "missing" and not gate_blockers:
            blockers.append("summary originClassification missing status requires a blocker")

    embedded_verify_data = summary.get("reviewBundleVerification")
    embedded_verify_sha256 = summary.get("reviewBundleVerificationSha256", "")
    if embedded_verify_data is not None and not isinstance(embedded_verify_data, dict):
        blockers.append("summary reviewBundleVerification must be an object when present")
        embedded_verify_data = None
    if embedded_verify_data is not None:
        if not valid_sha256_text(embedded_verify_sha256):
            blockers.append("summary reviewBundleVerificationSha256 must be a lowercase sha256 when reviewBundleVerification is present")
        elif json_sha256(embedded_verify_data) != embedded_verify_sha256:
            blockers.append("summary reviewBundleVerificationSha256 does not match embedded reviewBundleVerification")

    route_slot_data = summary.get("routeSlotRecoveryVerification")
    route_slot_sha256 = summary.get("routeSlotRecoveryVerificationSha256", "")
    if route_slot_data is not None and not isinstance(route_slot_data, dict):
        blockers.append("summary routeSlotRecoveryVerification must be an object when present")
        route_slot_data = None
    if route_slot_data is not None:
        if not valid_sha256_text(route_slot_sha256):
            blockers.append("summary routeSlotRecoveryVerificationSha256 must be a lowercase sha256 when routeSlotRecoveryVerification is present")
        elif json_sha256(route_slot_data) != route_slot_sha256:
            blockers.append("summary routeSlotRecoveryVerificationSha256 does not match embedded routeSlotRecoveryVerification")
    route_slot_next_trace = summary.get("routeSlotRecoveryNextTraceRequirement")
    if route_slot_next_trace is not None and not isinstance(route_slot_next_trace, dict):
        blockers.append("summary routeSlotRecoveryNextTraceRequirement must be an object when present")
    if route_slot_data is not None and isinstance(route_slot_next_trace, dict):
        expected_next_trace = route_slot_data.get("nextTraceRequirement")
        if expected_next_trace is not None:
            if route_slot_next_trace != expected_next_trace:
                blockers.append("summary routeSlotRecoveryNextTraceRequirement does not match embedded routeSlotRecoveryVerification")
        elif route_slot_next_trace:
            blockers.append("summary routeSlotRecoveryNextTraceRequirement must be empty when embedded routeSlotRecoveryVerification has no nextTraceRequirement")
    if route_slot_data is not None and route_slot_data.get("ready") is not True:
        expected_next_trace = route_slot_data.get("nextTraceRequirement")
        if isinstance(expected_next_trace, dict) and expected_next_trace and route_slot_next_trace != expected_next_trace:
            blockers.append("summary non-ready routeSlotRecoveryVerification requires matching routeSlotRecoveryNextTraceRequirement")

    prearm_data = summary.get("prearmReadinessVerification")
    prearm_sha256 = summary.get("prearmReadinessVerificationSha256", "")
    if prearm_data is not None and not isinstance(prearm_data, dict):
        blockers.append("summary prearmReadinessVerification must be an object when present")
        prearm_data = None
    if prearm_data is not None:
        if not valid_sha256_text(prearm_sha256):
            blockers.append("summary prearmReadinessVerificationSha256 must be a lowercase sha256 when prearmReadinessVerification is present")
        elif json_sha256(prearm_data) != prearm_sha256:
            blockers.append("summary prearmReadinessVerificationSha256 does not match embedded prearmReadinessVerification")

    readable_verify_data = readable_json_file(summary.get("verifyJson", ""))
    if readable_verify_data is not None and embedded_verify_data is not None and readable_verify_data != embedded_verify_data:
        blockers.append("summary embedded reviewBundleVerification does not match readable review bundle verification")
    verify_data = readable_verify_data
    if verify_data is None and embedded_verify_data is not None:
        verify_data = embedded_verify_data
    if summary.get("ready") is True and verify_data is None:
        blockers.append("summary ready requires readable or embedded review bundle verification evidence")
    if verify_data is not None:
        if verify_data.get("ready") is not summary.get("ready"):
            blockers.append("summary ready does not match review bundle verification ready")
        verify_blockers = verify_data.get("blockers", [])
        if not isinstance(verify_blockers, list) or any(not isinstance(item, str) for item in verify_blockers):
            blockers.append("review bundle verification blockers must be a string array")
            verify_blockers = []
        expected_blockers = list(verify_blockers)
        if route_slot_data is not None:
            route_blockers = route_slot_data.get("blockers", [])
            if isinstance(route_blockers, list):
                for blocker in route_blockers:
                    if isinstance(blocker, str) and blocker:
                        expected_blockers.append(f"route-slot recovery: {blocker}")
        if blockers_value != expected_blockers:
            blockers.append("summary blockers do not match review bundle verification blockers")
        for key in ("artifactCount", "checksumCount"):
            if key in verify_data and summary.get(key) != verify_data.get(key):
                blockers.append(f"summary {key} does not match review bundle verification {key}")
        if verify_data.get("bundle") and summary.get("bundle") != verify_data.get("bundle"):
            blockers.append("summary bundle does not match review bundle verification bundle")

    if runbook:
        runbook_paths = [value for value in (runbook.get("sourcePath", ""), runbook.get("_path", "")) if value]
        if not any(same_path(summary.get("sourceRunbook", ""), path) for path in runbook_paths):
            blockers.append("summary sourceRunbook does not match stimulus runbook path")
        if not summary.get("traceLogOverride") and summary.get("traceLog") != runbook.get("traceLog"):
            blockers.append("summary traceLog does not match stimulus runbook traceLog")
        if summary.get("traceRemote") != runbook.get("remote"):
            blockers.append("summary traceRemote does not match stimulus runbook remote")
        if summary.get("container") != runbook.get("container"):
            blockers.append("summary container does not match stimulus runbook container")
        window = runbook.get("operatorWindow", {}) or {}
        max_seconds = window.get("maxArmSeconds")
        if positive_int(max_seconds) and summary.get("operatorWindowSeconds", 0) > max_seconds:
            blockers.append("summary operatorWindowSeconds exceeds stimulus runbook maxArmSeconds")
        runbook_gate = runbook.get("originClassification", {})
        if isinstance(runbook_gate, dict) and runbook_gate:
            if origin is None:
                blockers.append("summary missing originClassification required by stimulus runbook")
            else:
                for key in ("probeCandidate", "serverSideFallbackCandidate"):
                    if runbook_gate.get(key, "") and origin.get(key, "") != runbook_gate.get(key, ""):
                        blockers.append(f"summary originClassification.{key} does not match stimulus runbook")
                if origin.get("status") == "not-required":
                    blockers.append("summary originClassification.status must classify the stimulus when runbook requires it")
    if next_action:
        live = next_action.get("liveTraceRunbook", {}) or {}
        expected_remote = live.get("remote", "")
        if expected_remote and summary.get("traceRemote") != expected_remote:
            blockers.append("summary traceRemote does not match next-action liveTraceRunbook remote")
        expected_container = live.get("container", "")
        if expected_container and summary.get("container") != expected_container:
            blockers.append("summary container does not match next-action liveTraceRunbook container")
        expected_trace_log = live.get("traceLog", "")
        if expected_trace_log and not summary.get("traceLogOverride") and summary.get("traceLog") != expected_trace_log:
            blockers.append("summary traceLog does not match next-action liveTraceRunbook traceLog")
        expected_summary_schema = live.get("localReviewSummarySchemaVersion", "")
        if expected_summary_schema and expected_summary_schema != summary.get("schemaVersion"):
            blockers.append("summary schemaVersion does not match next-action localReviewSummarySchemaVersion")
        expected_embedded_fields = live.get("localReviewSummaryEmbeddedEvidenceFields", "")
        if expected_embedded_fields:
            if expected_embedded_fields != EMBEDDED_EVIDENCE_FIELDS:
                blockers.append("next-action localReviewSummaryEmbeddedEvidenceFields has unexpected value")
            if "reviewBundleVerification" not in summary:
                blockers.append("summary missing reviewBundleVerification required by next-action")
            if "reviewBundleVerificationSha256" not in summary:
                blockers.append("summary missing reviewBundleVerificationSha256 required by next-action")
            if "routeSlotRecoveryVerification" not in summary:
                blockers.append("summary missing routeSlotRecoveryVerification required by next-action")
            if "routeSlotRecoveryVerificationSha256" not in summary:
                blockers.append("summary missing routeSlotRecoveryVerificationSha256 required by next-action")
            if live.get("prearmReadinessJson"):
                if "prearmReadinessVerification" not in summary:
                    blockers.append("summary missing prearmReadinessVerification required by next-action")
                if "prearmReadinessVerificationSha256" not in summary:
                    blockers.append("summary missing prearmReadinessVerificationSha256 required by next-action")
            if summary.get("ready") is True:
                if route_slot_data is None:
                    blockers.append("summary ready requires embedded routeSlotRecoveryVerification required by next-action")
                elif route_slot_data.get("ready") is not True:
                    blockers.append("summary ready requires routeSlotRecoveryVerification ready true")
                if live.get("prearmReadinessJson"):
                    if prearm_data is None:
                        blockers.append("summary ready requires embedded prearmReadinessVerification required by next-action")
                    elif prearm_data.get("ready") is not True:
                        blockers.append("summary ready requires prearmReadinessVerification ready true")
            if live.get("prearmReadinessJson") and prearm_data is not None and prearm_data.get("ready") is not True:
                blockers.append("summary requires prearmReadinessVerification ready true")
        expected_runbook_mode = live.get("localReviewSummaryRunbookMode", "")
        if expected_runbook_mode and expected_runbook_mode != RUNBOOK_MODE:
            blockers.append("next-action localReviewSummaryRunbookMode has unexpected value")
        expected_summary_path = live.get("localReviewSummaryJson", "")
        if expected_summary_path and summary.get("_path", "") and not same_path(expected_summary_path, summary.get("_path", "")):
            blockers.append("summary path does not match next-action localReviewSummaryJson")
        for source_name, command in (
            ("stimulus runbook", runbook.get("localReviewSummaryVerificationCommand", "") if runbook else ""),
            ("next-action", live.get("localReviewSummaryVerificationCommand", "")),
        ):
            expected_command_runbooks = [summary.get("sourceRunbook", "")]
            if summary.get("traceLogOverride"):
                expected_command_runbooks.append(summary.get("runbook", ""))
            if command and not summary_verifier_command_matches(
                command,
                expected_summary_path,
                expected_command_runbooks,
                next_action.get("_path", ""),
            ):
                blockers.append(
                    f"{source_name} localReviewSummaryVerificationCommand does not match expected verifier command"
                )
    return blockers


def report(summary_path, runbook_path=None, next_action_path=None):
    try:
        summary = load_json(summary_path)
    except FileNotFoundError:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ready": False,
            "summary": str(summary_path),
            "runbook": str(runbook_path) if runbook_path else "",
            "nextAction": str(next_action_path) if next_action_path else "",
            "blockers": ["summary JSON is missing"],
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ready": False,
            "summary": str(summary_path),
            "runbook": str(runbook_path) if runbook_path else "",
            "nextAction": str(next_action_path) if next_action_path else "",
            "blockers": [f"summary JSON is unreadable: {exc}"],
        }
    summary["_path"] = str(summary_path)
    runbook = None
    if runbook_path:
        runbook = load_json(runbook_path)
        runbook["_path"] = str(runbook_path)
    next_action = load_json(next_action_path) if next_action_path else None
    if next_action is not None:
        next_action["_path"] = str(next_action_path)
    blockers = verify_summary(summary, runbook=runbook, next_action=next_action)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ready": not blockers,
        "summary": str(summary_path),
        "runbook": str(runbook_path) if runbook_path else "",
        "nextAction": str(next_action_path) if next_action_path else "",
        "routeSlotRecoveryNextTraceRequirement": summary.get("routeSlotRecoveryNextTraceRequirement"),
        "originClassification": summary.get("originClassification"),
        "blockers": blockers,
    }


def markdown(data):
    lines = [
        "# UE4SS Package Live Stimulus Summary Verification",
        "",
        f"- Summary: `{data.get('summary', '')}`",
        f"- Ready: `{str(data.get('ready', False)).lower()}`",
    ]
    if data.get("runbook"):
        lines.append(f"- Runbook: `{data['runbook']}`")
    if data.get("nextAction"):
        lines.append(f"- Next action: `{data['nextAction']}`")
    requirement = data.get("routeSlotRecoveryNextTraceRequirement") or {}
    if requirement:
        lines.append(
            f"- Route slot next trace: marker=`{requirement.get('expectedTraceMarker', '')}` "
            f"route=`{requirement.get('routeAddress', '')}` "
            f"missingSlots=`{', '.join(requirement.get('missingSlots', [])) or 'none'}` "
            f"missingRegisters=`{', '.join(requirement.get('missingRegisters', [])) or 'none'}`"
        )
    classification = data.get("originClassification") or {}
    if classification:
        lines.append(
            f"- Origin/reachability classification: status=`{classification.get('status', '')}` "
            f"serverSideReplay=`{str(classification.get('requiresServerSideReplay', False)).lower()}`"
        )
    if data.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        for blocker in data["blockers"]:
            lines.append(f"- {blocker}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify a UE4SS package live stimulus local review summary.")
    parser.add_argument("summary", type=Path)
    parser.add_argument("--runbook-json", type=Path)
    parser.add_argument("--next-action-json", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    data = report(args.summary, runbook_path=args.runbook_json, next_action_path=args.next_action_json)
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(markdown(data), end="")
    return 0 if data["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
