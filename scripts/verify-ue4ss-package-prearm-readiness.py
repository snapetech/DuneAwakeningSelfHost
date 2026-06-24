#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import shlex
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "dune-ue4ss-package-prearm-readiness/v1"
PREFLIGHT_VERIFIER = ROOT / "scripts" / "verify-ue4ss-package-live-preflight-summary.py"
DEFAULT_PREFLIGHT_SUMMARY = ROOT / "build/server-current-anchor-prep/ue4ss-package-live-preflight-summary.json"
DEFAULT_RUNBOOK = ROOT / "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json"
DEFAULT_NEXT_ACTION = ROOT / "build/server-current-anchor-prep/ue4ss-package-next-action.json"
DEFAULT_AUDIT = ROOT / "build/server-current-anchor-prep/ue4ss-linux-port-completion-audit.json"
TRACE_PLAN_SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-plan/v1"
REQUIRED_ROUTE_CAPTURE_REGISTERS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9", "rbx", "r12", "r13", "r14", "r15")
REQUIRED_ROUTE_CAPTURE_STACK_LABELS = ("rsp0", "rsp8", "rsp10", "rsp18", "rsp20", "rsp28")
FRESH_TRACE_LOG_PATTERN = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log"
FRESH_TRACE_LOG_RE = re.compile(
    r"/tmp/ue4ss-package-runtime-trace-live-client-map-entry(?:-batch[0-9]+)?-\$\(date -u \+%Y%m%dT%H%M%SZ\)\.log"
)
CLIENT_ORIGIN_SERVER_SIDE_FALLBACK = "server-side-client-call-emulation"

ALLOWED_AUDIT_BLOCKER_PREFIXES = (
    "port-gap-summary: port gap summary is not ready",
    "port-gap-summary: port gap:",
    "package-next-action: package next-action is not complete:",
    "package-prearm-readiness:",
    "live-preflight-summary:",
    "live-stimulus-summary:",
)


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def import_preflight_verifier():
    spec = importlib.util.spec_from_file_location("verify_live_preflight_summary", PREFLIGHT_VERIFIER)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {PREFLIGHT_VERIFIER}")
    spec.loader.exec_module(module)
    return module


def add_blocker(blockers, text):
    if text not in blockers:
        blockers.append(text)


def single_line(value):
    return isinstance(value, str) and value != "" and "\n" not in value and "\r" not in value


def preflight_trace_env(preflight_summary):
    trace_env = preflight_summary.get("traceEnv", {}) if isinstance(preflight_summary, dict) else {}
    if not isinstance(trace_env, dict):
        return {}
    result = {}
    for key, value in trace_env.items():
        if (
            isinstance(key, str)
            and key.startswith("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_")
            and key != "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON"
            and key.replace("_", "").isalnum()
            and single_line(str(value))
        ):
            result[key] = str(value)
    return result


def render_coordinator_command(base_command, trace_env, trace_log=None, preflight=False):
    if not isinstance(base_command, str) or not base_command:
        return base_command
    command = base_command
    if trace_log:
        command = FRESH_TRACE_LOG_RE.sub(trace_log, command)
    if preflight and "--preflight-only" not in command:
        command = command.replace(
            "scripts/run-ue4ss-package-live-stimulus-trace.sh",
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only",
            1,
        )
    assignments = [f"{key}={shlex.quote(trace_env[key])}" for key in sorted(trace_env)]
    return " ".join(assignments + [command])


def fresh_trace_log_pattern_from_preflight(trace_log):
    if not isinstance(trace_log, str) or not trace_log:
        return ""
    match = re.fullmatch(
        r"(/tmp/ue4ss-package-runtime-trace-live-client-map-entry(?:-batch[0-9]+)?)-[0-9]{8}T[0-9]{6}Z\.log",
        trace_log,
    )
    if not match:
        return trace_log
    return f"{match.group(1)}-$(date -u +%Y%m%dT%H%M%SZ).log"


def audit_gate(audit, name):
    for gate in audit.get("gates", []) or []:
        if isinstance(gate, dict) and gate.get("name") == name:
            return gate
    return {}


def audit_blockers_are_expected(audit):
    blockers = audit.get("blockers", []) or []
    if not isinstance(blockers, list):
        return False
    for blocker in blockers:
        if not isinstance(blocker, str):
            return False
        if not any(blocker.startswith(prefix) for prefix in ALLOWED_AUDIT_BLOCKER_PREFIXES):
            return False
    return True


def audit_has_route_slot_blocker(audit):
    blockers = audit.get("blockers", []) or []
    if not isinstance(blockers, list):
        return False
    return any(
        isinstance(blocker, str) and "route-slot recovery:" in blocker
        for blocker in blockers
    )


def resolve_repo_path(path):
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


def verify_trace_plan(trace_plan_path, route_address, route_recovery, blockers):
    result = {
        "path": str(trace_plan_path or ""),
        "ready": False,
        "routeAddress": route_address,
        "routeProbeCount": 0,
        "expandedRouteCaptureReady": False,
    }
    if not trace_plan_path:
        add_blocker(blockers, "runbook traceInputs.tracePlanJson is missing")
        return result
    try:
        plan = load_json(resolve_repo_path(trace_plan_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        add_blocker(blockers, f"trace plan is unreadable: {exc}")
        return result
    result["schemaVersion"] = plan.get("schemaVersion", "")
    if plan.get("schemaVersion") != TRACE_PLAN_SCHEMA_VERSION:
        add_blocker(blockers, "trace plan schemaVersion is not the package runtime trace plan schema")
    requested_routes = plan.get("requestedRouteAddresses", []) or []
    result["requestedRouteAddresses"] = requested_routes
    if route_address and route_address not in requested_routes:
        add_blocker(blockers, "trace plan requestedRouteAddresses does not include runbook routeAddress")
    route_probes = plan.get("routeProbes", []) or []
    result["routeProbeCount"] = len(route_probes) if isinstance(route_probes, list) else 0
    if not isinstance(route_probes, list) or not any(probe.get("address") == route_address for probe in route_probes if isinstance(probe, dict)):
        add_blocker(blockers, "trace plan routeProbes does not contain the runbook routeAddress")
    route_gdb = plan.get("routeGdb", "")
    if not isinstance(route_gdb, str) or "UE4SS_PACKAGE_ROUTE_TRACE_HIT" not in route_gdb:
        add_blocker(blockers, "trace plan routeGdb is missing route hit capture")
        route_gdb = ""
    required_route = route_recovery.get("requiredRouteTrace", {}) or {}
    if required_route.get("reviewField") == "routeVtableStaticSlotMatches":
        missing_registers = [
            register
            for register in REQUIRED_ROUTE_CAPTURE_REGISTERS
            if f"UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg={register}" not in route_gdb
            or f"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={register}" not in route_gdb
        ]
        missing_stack = [
            label
            for label in REQUIRED_ROUTE_CAPTURE_STACK_LABELS
            if f"UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg={label}" not in route_gdb
            or f"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={label}" not in route_gdb
        ]
        result["requiredRouteCaptureRegisters"] = list(REQUIRED_ROUTE_CAPTURE_REGISTERS)
        result["requiredRouteCaptureStackLabels"] = list(REQUIRED_ROUTE_CAPTURE_STACK_LABELS)
        result["missingRouteCaptureRegisters"] = missing_registers
        result["missingRouteCaptureStackLabels"] = missing_stack
        if missing_registers:
            add_blocker(blockers, "trace plan routeGdb is missing expanded register route capture: " + ", ".join(missing_registers))
        if missing_stack:
            add_blocker(blockers, "trace plan routeGdb is missing expanded stack route capture: " + ", ".join(missing_stack))
        result["expandedRouteCaptureReady"] = not missing_registers and not missing_stack
    result["ready"] = not any(str(blocker).startswith("trace plan ") for blocker in blockers)
    return result


def validate_coordinator_command(command, *, preflight, blockers):
    label = "fresh preflight" if preflight else "fresh trace"
    if not isinstance(command, str) or not command:
        add_blocker(blockers, f"next-action {label} command is missing")
        return
    if "\n" in command or "\r" in command:
        add_blocker(blockers, f"next-action {label} command must be a single line")
    if "scripts/run-ue4ss-package-live-stimulus-trace.sh" not in command:
        add_blocker(blockers, f"next-action {label} command must invoke coordinator")
    if preflight and "--preflight-only" not in command:
        add_blocker(blockers, "next-action fresh preflight command must include --preflight-only")
    if "--trace-log" not in command:
        add_blocker(blockers, f"next-action {label} command must include --trace-log")
    if not FRESH_TRACE_LOG_RE.search(command):
        add_blocker(
            blockers,
            f"next-action {label} command must use timestamped /tmp package trace log {FRESH_TRACE_LOG_PATTERN}",
        )


def validate_route_slot_trace_requirement(runbook, next_action, route_address, blockers):
    requirement = runbook.get("routeSlotTraceRequirement")
    if not isinstance(requirement, dict):
        add_blocker(blockers, "runbook routeSlotTraceRequirement must be an object")
        return {}
    if requirement.get("expectedTraceMarker") != "UE4SS_PACKAGE_ROUTE_TRACE_HIT":
        add_blocker(blockers, "runbook routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT")
    if requirement.get("reviewField") != "routeVtableStaticSlotMatches":
        add_blocker(blockers, "runbook routeSlotTraceRequirement reviewField must be routeVtableStaticSlotMatches")
    for key in ("requiredSlots", "requiredRegisters"):
        values = requirement.get(key, [])
        if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
            add_blocker(blockers, f"runbook routeSlotTraceRequirement {key} must be a non-empty string array")
    if route_address and requirement.get("routeAddress") != route_address:
        add_blocker(blockers, "runbook routeSlotTraceRequirement routeAddress does not match traceInputs.routeAddress")
    live = next_action.get("liveTraceRunbook", {}) or {}
    if isinstance(live, dict):
        summary_requirement = live.get("routeSlotTraceRequirement")
        if summary_requirement is not None and summary_requirement != requirement:
            add_blocker(blockers, "next-action liveTraceRunbook.routeSlotTraceRequirement does not match runbook")
    return requirement


def report(preflight_summary, runbook_path, next_action_path, audit_path, max_age_seconds=None):
    blockers = []
    try:
        preflight_summary_data = load_json(preflight_summary)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        preflight_summary_data = {}
        add_blocker(blockers, f"preflight summary is unreadable: {exc}")
    preflight_module = import_preflight_verifier()
    preflight_report = preflight_module.report(
        preflight_summary,
        runbook_path=runbook_path,
        next_action_path=next_action_path,
        max_age_seconds=max_age_seconds,
    )
    if preflight_report.get("ready") is not True:
        for blocker in preflight_report.get("blockers", []) or []:
            add_blocker(blockers, f"preflight: {blocker}")

    try:
        runbook = load_json(runbook_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        runbook = {}
        add_blocker(blockers, f"runbook is unreadable: {exc}")
    try:
        next_action = load_json(next_action_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        next_action = {}
        add_blocker(blockers, f"next-action is unreadable: {exc}")
    try:
        audit = load_json(audit_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        audit = {}
        add_blocker(blockers, f"completion audit is unreadable: {exc}")

    trace_inputs = runbook.get("traceInputs", {}) or {}
    trace_env = runbook.get("traceEnv", {}) or {}
    route_address = trace_inputs.get("routeAddress", "")
    if not route_address:
        add_blocker(blockers, "runbook traceInputs.routeAddress is missing")
    elif trace_env.get("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS") != route_address:
        add_blocker(blockers, "runbook traceEnv route address does not match traceInputs.routeAddress")
    route_slot_requirement = validate_route_slot_trace_requirement(runbook, next_action, route_address, blockers)

    if next_action.get("action") != "recover-package-anchor":
        add_blocker(blockers, "next-action action must be recover-package-anchor before live package stimulus")
    route_recovery = next_action.get("routeSlotRecovery", {}) or {}
    required_route = route_recovery.get("requiredRouteTrace", {}) or {}
    if route_address and required_route.get("address") != route_address:
        add_blocker(blockers, "next-action required route trace address does not match runbook routeAddress")
    if required_route.get("address") and route_slot_requirement.get("routeAddress") and route_slot_requirement.get("routeAddress") != required_route.get("address"):
        add_blocker(blockers, "runbook routeSlotTraceRequirement routeAddress does not match next-action required route trace address")
    trace_plan_report = verify_trace_plan(
        trace_inputs.get("tracePlanJson", ""),
        route_address,
        route_recovery,
        blockers,
    )
    live = next_action.get("liveTraceRunbook", {}) or {}
    fresh_preflight = live.get("coordinatorFreshPreflightCommand", "")
    trace_env_override = preflight_trace_env(preflight_summary_data)
    trace_log_override = preflight_summary_data.get("traceLog", "") if isinstance(preflight_summary_data, dict) else ""
    fresh_trace_log_override = fresh_trace_log_pattern_from_preflight(trace_log_override)
    if trace_env_override:
        fresh_preflight = render_coordinator_command(
            fresh_preflight,
            trace_env_override,
            trace_log=fresh_trace_log_override,
            preflight=True,
        )
    validate_coordinator_command(fresh_preflight, preflight=True, blockers=blockers)
    fresh_trace = live.get("coordinatorFreshTraceCommand", "")
    if trace_env_override:
        fresh_trace = render_coordinator_command(
            fresh_trace,
            trace_env_override,
            trace_log=fresh_trace_log_override,
            preflight=False,
        )
    validate_coordinator_command(fresh_trace, preflight=False, blockers=blockers)

    preflight_gate = audit_gate(audit, "live-preflight-summary")
    if preflight_gate.get("ready") is not True:
        add_blocker(blockers, "completion audit live-preflight-summary gate is not ready")
    if audit.get("ready") is True:
        add_blocker(blockers, "completion audit is already ready; prearm readiness is no longer the right gate")
    if not audit_blockers_are_expected(audit):
        add_blocker(blockers, "completion audit has unexpected blockers for prearm state")
    audit_route_slot_requirement = audit.get("nextRouteSlotTraceRequirement") or {}
    if audit_has_route_slot_blocker(audit) and not audit_route_slot_requirement:
        add_blocker(blockers, "completion audit route-slot blocker must include nextRouteSlotTraceRequirement")
    audit_origin_classification = audit.get("nextOriginClassification") or {}
    if audit_origin_classification and not isinstance(audit_origin_classification, dict):
        add_blocker(blockers, "completion audit nextOriginClassification must be an object")
        audit_origin_classification = {}
    audit_runtime_root_plan = audit.get("nextRuntimeRootRecoveryPlan") or {}
    if audit_runtime_root_plan and not isinstance(audit_runtime_root_plan, dict):
        add_blocker(blockers, "completion audit nextRuntimeRootRecoveryPlan must be an object")
        audit_runtime_root_plan = {}

    return {
        "schemaVersion": SCHEMA_VERSION,
        "ready": not blockers,
        "preflightSummary": str(preflight_summary),
        "runbook": str(runbook_path),
        "nextAction": str(next_action_path),
        "completionAudit": str(audit_path),
        "routeAddress": route_address,
        "tracePlan": trace_plan_report,
        "freshPreflightCommand": fresh_preflight,
        "freshTraceCommand": fresh_trace,
        "completionAuditNextRouteSlotTraceRequirement": audit_route_slot_requirement,
        "completionAuditNextOriginClassification": audit_origin_classification,
        "completionAuditNextClientGateClassification": audit_origin_classification,
        "completionAuditNextRuntimeRootRecoveryPlan": audit_runtime_root_plan,
        "preflightReady": preflight_report.get("ready") is True,
        "auditReady": audit.get("ready") is True,
        "blockers": blockers,
        "nextStep": (
            "operator may run coordinatorFreshTraceCommand during the approved login/travel/map-entry stimulus window"
            if not blockers
            else "operator must refresh the live preflight with coordinatorFreshPreflightCommand before arming the live package trace"
            if preflight_report.get("ready") is not True and fresh_preflight
            else "resolve prearm blockers before arming the live package trace"
        ),
    }


def markdown(data):
    trace_plan = data.get("tracePlan", {}) or {}
    lines = [
        "# UE4SS Package Prearm Readiness",
        "",
        f"- Ready: `{str(data.get('ready', False)).lower()}`",
        f"- Route address: `{data.get('routeAddress', '')}`",
        f"- Preflight ready: `{str(data.get('preflightReady', False)).lower()}`",
        f"- Completion audit ready: `{str(data.get('auditReady', False)).lower()}`",
    ]
    if trace_plan:
        lines.extend(
            [
                "",
                "## Trace Plan",
                "",
                f"- Path: `{trace_plan.get('path', '')}`",
                f"- Ready: `{str(trace_plan.get('ready', False)).lower()}`",
                f"- Route probes: `{trace_plan.get('routeProbeCount', 0)}`",
                f"- Requested route addresses: `{', '.join(trace_plan.get('requestedRouteAddresses', []) or [])}`",
                f"- Expanded route capture ready: `{str(trace_plan.get('expandedRouteCaptureReady', False)).lower()}`",
            ]
        )
        required_registers = trace_plan.get("requiredRouteCaptureRegisters", []) or []
        required_stack = trace_plan.get("requiredRouteCaptureStackLabels", []) or []
        missing_registers = trace_plan.get("missingRouteCaptureRegisters", []) or []
        missing_stack = trace_plan.get("missingRouteCaptureStackLabels", []) or []
        if required_registers:
            lines.append(f"- Required capture registers: `{', '.join(required_registers)}`")
        if required_stack:
            lines.append(f"- Required stack candidates: `{', '.join(required_stack)}`")
        if missing_registers:
            lines.append(f"- Missing capture registers: `{', '.join(missing_registers)}`")
        if missing_stack:
            lines.append(f"- Missing stack candidates: `{', '.join(missing_stack)}`")
    if data.get("freshPreflightCommand"):
        lines.extend(["", "## Fresh Preflight Command", "", f"```bash\n{data['freshPreflightCommand']}\n```"])
    if data.get("freshTraceCommand"):
        lines.extend(["", "## Fresh Trace Command", "", f"```bash\n{data['freshTraceCommand']}\n```"])
    requirement = data.get("completionAuditNextRouteSlotTraceRequirement") or {}
    if requirement:
        lines.extend(
            [
                "",
                "## Completion Audit Route Slot Trace Requirement",
                "",
                f"- Marker: `{requirement.get('expectedTraceMarker', '')}`",
                f"- Route: `{requirement.get('routeAddress', '')}`",
                f"- Field: `{requirement.get('expectedReviewField', '')}`",
                f"- Missing slots: `{', '.join(requirement.get('missingSlots', [])) or 'none'}`",
                f"- Missing registers: `{', '.join(requirement.get('missingRegisters', [])) or 'none'}`",
            ]
        )
    classification = data.get("completionAuditNextClientGateClassification") or {}
    if classification:
        lines.extend(
            [
                "",
                "## Completion Audit Origin/Reachability Classification",
                "",
                f"- Status: `{classification.get('status', '')}`",
                f"- Probe: `{classification.get('probeCandidate', '')}`",
                f"- Server-side fallback: `{classification.get('serverSideFallbackCandidate', '')}`",
                f"- Requires server-side replay: `{str(classification.get('requiresServerSideReplay', False)).lower()}`",
            ]
        )
    runtime_root = data.get("completionAuditNextRuntimeRootRecoveryPlan") or {}
    if runtime_root:
        lines.extend(
            [
                "",
                "## Completion Audit Runtime Root Recovery",
                "",
                f"- Required log: `{runtime_root.get('requiredLogPath', '')}`",
                f"- Blocked by missing log: `{str(runtime_root.get('blockedByMissingLog', False)).lower()}`",
                f"- Missing keys: `{', '.join(runtime_root.get('missingKeys', [])) or 'none'}`",
            ]
        )
        if runtime_root.get("preflightCommand"):
            lines.extend(["", "### Runtime Root Preflight", "", f"```bash\n{runtime_root['preflightCommand']}\n```"])
        if runtime_root.get("runCommand"):
            lines.extend(["", "### Runtime Root Canary", "", f"```bash\n{runtime_root['runCommand']}\n```"])
    if data.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in data["blockers"])
    if data.get("nextStep"):
        lines.extend(["", "## Next Step", "", data["nextStep"]])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify UE4SS package live-stimulus prearm readiness.")
    parser.add_argument("--preflight-summary", type=Path, default=DEFAULT_PREFLIGHT_SUMMARY)
    parser.add_argument("--runbook-json", type=Path, default=DEFAULT_RUNBOOK)
    parser.add_argument("--next-action-json", type=Path, default=DEFAULT_NEXT_ACTION)
    parser.add_argument("--completion-audit-json", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--max-age-seconds", type=int, default=3600)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    data = report(
        args.preflight_summary,
        args.runbook_json,
        args.next_action_json,
        args.completion_audit_json,
        max_age_seconds=args.max_age_seconds,
    )
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(markdown(data), end="")
    return 0 if data["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
