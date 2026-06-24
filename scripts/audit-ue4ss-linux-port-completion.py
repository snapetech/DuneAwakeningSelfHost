#!/usr/bin/env python3
import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "dune-ue4ss-linux-port-completion-audit/v1"


DEFAULT_PACKAGE_VERIFICATION_GLOB = ROOT / "dist/linux-server-loader"
DEFAULT_PORTABILITY_CHECK = ROOT / "build/server-current-anchor-prep/ue4ss-portability-contract-latest-check.json"
DEFAULT_PORT_GAPS = ROOT / "build/server-current-anchor-prep/ue4ss-port-gaps.json"
DEFAULT_NEXT_ACTION = ROOT / "build/server-current-anchor-prep/ue4ss-package-next-action.json"
DEFAULT_RUNBOOK = ROOT / "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json"
DEFAULT_PREFLIGHT_SUMMARY = ROOT / "build/server-current-anchor-prep/ue4ss-package-live-preflight-summary.json"
DEFAULT_PREARM_READINESS = ROOT / "build/server-current-anchor-prep/ue4ss-package-prearm-readiness.json"
DEFAULT_LIVE_SUMMARY = ROOT / "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json"
DEFAULT_PREFLIGHT_MAX_AGE_SECONDS = 3600
PREFLIGHT_SUMMARY_VERIFIER = ROOT / "scripts/verify-ue4ss-package-live-preflight-summary.py"
LIVE_SUMMARY_VERIFIER = ROOT / "scripts/verify-ue4ss-package-live-stimulus-summary.py"
DEFAULT_NEXT_LIVE_COMMAND = (
    "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log "
    "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log"
)
DEFAULT_NEXT_LIVE_PREFLIGHT_COMMAND = (
    "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log "
    "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log"
)
CLIENT_ORIGIN_SERVER_SIDE_FALLBACK = "server-side-client-call-emulation"
RUNTIME_ROOT_RUN_STRICT_VERIFY_BLOCKER = "runtime root recovery run command must enable strict verification"
RUNTIME_ROOT_GUARD_KSPLS0_BLOCKER = "runtime root recovery guards must mention kspls0"
RUNTIME_ROOT_RECOVERY_KEYS = {
    "runtimeRootDiscovery",
    "runtimeRootValidation",
    "targetObjectDiscovery",
    "anchorCoverageObjectDiscovery",
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def optional_json(path):
    try:
        return load_json(path), None
    except FileNotFoundError:
        return None, f"{path} is missing"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, f"{path} is unreadable: {exc}"


def latest_package_verification(root=DEFAULT_PACKAGE_VERIFICATION_GLOB):
    try:
        candidates = sorted(
            Path(root).glob("*.tar.gz.verification.json"),
            key=lambda path: (path.stat().st_mtime, path.name),
            reverse=True,
        )
    except OSError:
        candidates = []
    return candidates[0] if candidates else Path(root) / "*.tar.gz.verification.json"


def import_live_summary_verifier():
    spec = importlib.util.spec_from_file_location("verify_live_stimulus_summary", LIVE_SUMMARY_VERIFIER)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {LIVE_SUMMARY_VERIFIER}")
    spec.loader.exec_module(module)
    return module


def import_preflight_summary_verifier():
    spec = importlib.util.spec_from_file_location("verify_live_preflight_summary", PREFLIGHT_SUMMARY_VERIFIER)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {PREFLIGHT_SUMMARY_VERIFIER}")
    spec.loader.exec_module(module)
    return module


def gate(name, ready, evidence="", blockers=None):
    blockers = blockers or []
    return {
        "name": name,
        "ready": bool(ready),
        "evidence": evidence,
        "blockers": blockers,
    }


def next_live_command_from_action(next_action):
    if not isinstance(next_action, dict):
        return ""
    live = next_action.get("liveTraceRunbook", {}) or {}
    if not isinstance(live, dict):
        return ""
    command = live.get("coordinatorFreshTraceCommand", "")
    return command if isinstance(command, str) else ""


def next_live_preflight_command_from_action(next_action):
    if not isinstance(next_action, dict):
        return ""
    live = next_action.get("liveTraceRunbook", {}) or {}
    if not isinstance(live, dict):
        return ""
    command = live.get("coordinatorFreshPreflightCommand", "")
    return command if isinstance(command, str) else ""


def required_route_address(next_action):
    if not isinstance(next_action, dict):
        return ""
    route = (next_action.get("routeSlotRecovery", {}) or {}).get("requiredRouteTrace", {}) or {}
    address = route.get("address", "")
    return address if isinstance(address, str) else ""


def runbook_route_address(runbook):
    if not isinstance(runbook, dict):
        return ""
    trace_inputs = runbook.get("traceInputs", {}) or {}
    address = trace_inputs.get("routeAddress", "")
    return address if isinstance(address, str) else ""


def validate_route_slot_trace_requirement(runbook, next_action, blockers):
    if not isinstance(runbook, dict):
        return {}
    requirement = runbook.get("routeSlotTraceRequirement")
    if not isinstance(requirement, dict):
        blockers.append("runbook routeSlotTraceRequirement must be an object")
        return {}
    if requirement.get("expectedTraceMarker") != "UE4SS_PACKAGE_ROUTE_TRACE_HIT":
        blockers.append("runbook routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT")
    if requirement.get("reviewField") != "routeVtableStaticSlotMatches":
        blockers.append("runbook routeSlotTraceRequirement reviewField must be routeVtableStaticSlotMatches")
    for key in ("requiredSlots", "requiredRegisters"):
        values = requirement.get(key, [])
        if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
            blockers.append(f"runbook routeSlotTraceRequirement {key} must be a non-empty string array")
    route_address = requirement.get("routeAddress", "")
    if route_address and route_address != runbook_route_address(runbook):
        blockers.append("runbook routeSlotTraceRequirement routeAddress does not match traceInputs.routeAddress")
    live = (next_action.get("liveTraceRunbook", {}) or {}) if isinstance(next_action, dict) else {}
    if isinstance(live, dict):
        summary_requirement = live.get("routeSlotTraceRequirement")
        if summary_requirement is not None and summary_requirement != requirement:
            blockers.append("next-action liveTraceRunbook.routeSlotTraceRequirement does not match runbook")
    return requirement


def runbook_origin_classification(runbook):
    if not isinstance(runbook, dict):
        return {}
    classification = runbook.get("originClassification", {}) or {}
    return classification if isinstance(classification, dict) else {}


def next_origin_classification(live_report, runbook):
    live_classification = {}
    if isinstance(live_report, dict):
        candidate = live_report.get("originClassification", {}) or {}
        if isinstance(candidate, dict):
            live_classification = candidate
    if live_classification:
        return live_classification

    runbook_classification = runbook_origin_classification(runbook)
    if not runbook_classification:
        return {}
    return {
        "status": "pending",
        "source": "stimulus-runbook",
        "probeCandidate": runbook_classification.get("probeCandidate", ""),
        "serverSideFallbackCandidate": runbook_classification.get(
            "serverSideFallbackCandidate",
            CLIENT_ORIGIN_SERVER_SIDE_FALLBACK,
        ),
        "requiresServerSideReplay": False,
        "decision": runbook_classification.get("decision", ""),
        "nextStep": (
            "refresh the live stimulus summary with originClassification; "
            "if the package/BRT evidence is client-originated, recover the call "
            "frame and replay/spoof the equivalent call server-side"
        ),
    }


def next_runtime_root_recovery_plan(gaps):
    if not isinstance(gaps, dict):
        return {}
    plan = gaps.get("runtimeRootRecoveryPlan", {}) or {}
    if not isinstance(plan, dict) or plan.get("needed") is not True:
        return {}
    wrapper = plan.get("canaryWrapper", {}) or {}
    if not isinstance(wrapper, dict):
        wrapper = {}
    return {
        "needed": True,
        "action": plan.get("action", "recover-runtime-roots"),
        "confidence": plan.get("confidence", ""),
        "reason": plan.get("reason", ""),
        "blockedByMissingLog": plan.get("blockedByMissingLog", False),
        "requiredLogPath": plan.get("requiredLogPath", ""),
        "missingKeys": plan.get("missingKeys", []),
        "preflightCommand": wrapper.get("preflightCommand", ""),
        "runCommand": wrapper.get("runCommand", ""),
        "guards": wrapper.get("guards", []),
        "outputFiles": plan.get("outputFiles", {}),
        "postCanaryVerificationOutputs": plan.get("postCanaryVerificationOutputs", {}),
    }


def validate_runtime_root_recovery_plan(plan, blockers):
    if not isinstance(plan, dict) or not plan:
        return
    if plan.get("needed") is not True:
        return
    required_log = plan.get("requiredLogPath", "")
    if required_log != "/tmp/dune-server-probe-loader.log":
        blockers.append("runtime root recovery requiredLogPath must be /tmp/dune-server-probe-loader.log")
    missing = plan.get("missingKeys", [])
    if not isinstance(missing, list) or not all(isinstance(item, str) and item for item in missing):
        blockers.append("runtime root recovery missingKeys must be a non-empty string array")
    elif not any(item in RUNTIME_ROOT_RECOVERY_KEYS for item in missing):
        blockers.append(
            "runtime root recovery missingKeys must include a runtime anchor recovery key"
        )
    for key, expected_preflight in (("preflightCommand", "true"), ("runCommand", "false")):
        command = plan.get(key, "")
        label = "preflight" if key == "preflightCommand" else "run"
        if not isinstance(command, str) or not command:
            blockers.append(f"runtime root recovery {label} command is missing")
            continue
        if "\n" in command or "\r" in command:
            blockers.append(f"runtime root recovery {label} command must be a single line")
        if "scripts/canary-linux-server-loader.sh" not in command:
            blockers.append(f"runtime root recovery {label} command must invoke canary-linux-server-loader.sh")
        if "DUNE_LINUX_SERVER_CANARY_LOG_PATH=/tmp/dune-server-probe-loader.log" not in command:
            blockers.append(f"runtime root recovery {label} command must capture /tmp/dune-server-probe-loader.log")
        if (
            plan.get("blockedByMissingLog") is not True
            and "DUNE_LINUX_SERVER_CANARY_PLAN_JSON=build/server-current-anchor-prep/ue4ss-runtime-root-recovery-next-canary.json" not in command
        ):
            blockers.append(f"runtime root recovery {label} command must consume the runtime-root next-canary JSON")
        if f"DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY={expected_preflight}" not in command:
            blockers.append(f"runtime root recovery {label} command has wrong DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY value")
        if "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true" not in command:
            if key == "runCommand":
                blockers.append(RUNTIME_ROOT_RUN_STRICT_VERIFY_BLOCKER)
            else:
                blockers.append(f"runtime root recovery {label} command must enable strict verification")
    guards = plan.get("guards", [])
    if not isinstance(guards, list) or any(not isinstance(item, str) for item in guards):
        blockers.append("runtime root recovery guards must be a string array")
        guards = []
    guard_text = "\n".join(guards)
    for required in ("kspls0", "zero connected players", "restores DUNE_ENABLE_LINUX_SERVER_PRELOAD"):
        if required not in guard_text:
            if required == "kspls0":
                blockers.append(RUNTIME_ROOT_GUARD_KSPLS0_BLOCKER)
            else:
                blockers.append(f"runtime root recovery guards must mention {required}")
    outputs = plan.get("postCanaryVerificationOutputs", {})
    if not isinstance(outputs, dict) or outputs.get("readinessJson") != "ue4ss-readiness.json":
        blockers.append("runtime root recovery post-canary outputs must include readinessJson=ue4ss-readiness.json")


def prearm_readiness_gate(path, runbook, next_action):
    data, error = optional_json(path)
    if error:
        return gate("package-prearm-readiness", False, str(path), [error])

    blockers = []
    if data.get("schemaVersion") != "dune-ue4ss-package-prearm-readiness/v1":
        blockers.append("prearm readiness schema is not dune-ue4ss-package-prearm-readiness/v1")
    if data.get("ready") is not True:
        blockers.append("prearm readiness is not ready")
    if data.get("preflightReady") is not True:
        blockers.append("prearm readiness preflightReady is not true")
    if data.get("auditReady") is True:
        blockers.append("prearm readiness was generated after a complete audit; it is stale for recovery prearm")

    expected_route = required_route_address(next_action) or runbook_route_address(runbook)
    if expected_route and data.get("routeAddress") != expected_route:
        blockers.append("prearm readiness routeAddress does not match required route trace address")
    route_slot_requirement = validate_route_slot_trace_requirement(runbook, next_action, blockers)
    if expected_route and route_slot_requirement.get("routeAddress") and route_slot_requirement.get("routeAddress") != expected_route:
        blockers.append("runbook routeSlotTraceRequirement routeAddress does not match required route trace address")

    command = data.get("freshTraceCommand", "")
    if not isinstance(command, str) or "run-ue4ss-package-live-stimulus-trace.sh" not in command or "--trace-log" not in command:
        blockers.append("prearm readiness freshTraceCommand must invoke live stimulus coordinator with --trace-log")

    return gate("package-prearm-readiness", not blockers, str(path), blockers)


def audit(args):
    gates = []
    next_live_command = DEFAULT_NEXT_LIVE_COMMAND
    next_live_preflight_command = DEFAULT_NEXT_LIVE_PREFLIGHT_COMMAND

    package_data, package_error = optional_json(args.package_verification)
    if package_error:
        gates.append(gate("package-verification", False, str(args.package_verification), [package_error]))
    else:
        gates.append(
            gate(
                "package-verification",
                package_data.get("passed") is True,
                str(args.package_verification),
                [] if package_data.get("passed") is True else ["package verification did not pass"],
            )
        )

    portability_data, portability_error = optional_json(args.portability_check)
    if portability_error:
        gates.append(gate("portability-contract", False, str(args.portability_check), [portability_error]))
    else:
        gates.append(
            gate(
                "portability-contract",
                portability_data.get("passed") is True,
                str(args.portability_check),
                [] if portability_data.get("passed") is True else ["portability contract did not pass"],
            )
        )

    gaps_data, gaps_error = optional_json(args.port_gaps)
    runtime_root_recovery_plan = {}
    if gaps_error:
        gates.append(gate("port-gap-summary", False, str(args.port_gaps), [gaps_error]))
    else:
        blockers = []
        if gaps_data.get("schemaVersion") != "dune-ue4ss-port-gap-summary/v1":
            blockers.append("port gap summary schema is not dune-ue4ss-port-gap-summary/v1")
        runtime_root_recovery_plan = next_runtime_root_recovery_plan(gaps_data)
        validate_runtime_root_recovery_plan(runtime_root_recovery_plan, blockers)
        if gaps_data.get("ready") is not True:
            blockers.append("port gap summary is not ready")
            blockers.extend(f"port gap: {item}" for item in gaps_data.get("blockers", []) or [])
        gates.append(gate("port-gap-summary", not blockers, str(args.port_gaps), blockers))

    next_action_data, next_action_error = optional_json(args.next_action)
    if next_action_error:
        gates.append(gate("package-next-action", False, str(args.next_action), [next_action_error]))
    else:
        blockers = []
        if next_action_data.get("schemaVersion") != "dune-ue4ss-package-next-action/v1":
            blockers.append("next-action schema is not dune-ue4ss-package-next-action/v1")
        derived_next_live_preflight_command = next_live_preflight_command_from_action(next_action_data)
        if derived_next_live_preflight_command:
            next_live_preflight_command = derived_next_live_preflight_command
            if "run-ue4ss-package-live-stimulus-trace.sh" not in derived_next_live_preflight_command:
                blockers.append("next-action coordinatorFreshPreflightCommand does not invoke live stimulus coordinator")
            if "--preflight-only" not in derived_next_live_preflight_command:
                blockers.append("next-action coordinatorFreshPreflightCommand must use --preflight-only")
            if "--trace-log" not in derived_next_live_preflight_command:
                blockers.append("next-action coordinatorFreshPreflightCommand must use --trace-log")
            if "$(date -u +%Y%m%dT%H%M%SZ)" not in derived_next_live_preflight_command:
                blockers.append("next-action coordinatorFreshPreflightCommand must generate a timestamped trace log")
        derived_next_live_command = next_live_command_from_action(next_action_data)
        if derived_next_live_command:
            next_live_command = derived_next_live_command
            if "run-ue4ss-package-live-stimulus-trace.sh" not in derived_next_live_command:
                blockers.append("next-action coordinatorFreshTraceCommand does not invoke live stimulus coordinator")
            if "--trace-log" not in derived_next_live_command:
                blockers.append("next-action coordinatorFreshTraceCommand must use --trace-log")
            if "$(date -u +%Y%m%dT%H%M%SZ)" not in derived_next_live_command:
                blockers.append("next-action coordinatorFreshTraceCommand must generate a timestamped trace log")
        elif next_action_data.get("action") != "complete":
            blockers.append("next-action liveTraceRunbook.coordinatorFreshTraceCommand is missing")
        if next_action_data.get("action") != "complete":
            reason = next_action_data.get("reason", "")
            next_step = next_action_data.get("nextStep", "")
            blockers.append(
                "package next-action is not complete"
                + (f": {reason}" if reason else "")
                + (f"; next: {next_step}" if next_step else "")
            )
        gates.append(gate("package-next-action", not blockers, str(args.next_action), blockers))

    runbook_data, _runbook_error = optional_json(args.runbook)
    if _runbook_error:
        gates.append(gate("stimulus-runbook", False, str(args.runbook), [_runbook_error]))
    else:
        blockers = []
        validate_route_slot_trace_requirement(runbook_data or {}, next_action_data or {}, blockers)
        gates.append(gate("stimulus-runbook", not blockers, str(args.runbook), blockers))
    package_recovery_pending = bool(
        isinstance(next_action_data, dict) and next_action_data.get("action") == "recover-package-anchor"
    )
    if package_recovery_pending:
        gates.append(prearm_readiness_gate(args.prearm_readiness, runbook_data or {}, next_action_data or {}))

    preflight_verifier = import_preflight_summary_verifier()
    preflight_report = preflight_verifier.report(
        args.preflight_summary,
        runbook_path=args.runbook,
        next_action_path=args.next_action,
        max_age_seconds=args.preflight_max_age_seconds,
    )
    gates.append(
        gate(
            "live-preflight-summary",
            preflight_report.get("ready") is True,
            str(args.preflight_summary),
            list(preflight_report.get("blockers", []) or []),
        )
    )

    live_verifier = import_live_summary_verifier()
    live_report = live_verifier.report(args.live_summary, runbook_path=args.runbook, next_action_path=args.next_action)
    live_blockers = list(live_report.get("blockers", []) or [])
    route_slot_next_requirement = live_report.get("routeSlotRecoveryNextTraceRequirement") or {}
    origin_next_classification = next_origin_classification(live_report, runbook_data or {})
    has_route_slot_blocker = any(
        isinstance(blocker, str) and "route-slot recovery:" in blocker
        for blocker in live_blockers
    )
    if has_route_slot_blocker and not route_slot_next_requirement:
        live_blockers.append("route-slot recovery next trace requirement is missing")
    gates.append(
        gate(
            "live-stimulus-summary",
            live_report.get("ready") is True,
            str(args.live_summary),
            live_blockers,
        )
    )

    blockers = []
    for item in gates:
        blockers.extend(f"{item['name']}: {blocker}" for blocker in item["blockers"])
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ready": not blockers,
        "gates": gates,
        "blockers": blockers,
        "nextLivePreflightCommand": next_live_preflight_command,
        "nextLiveCommand": next_live_command,
        "nextRouteSlotTraceRequirement": route_slot_next_requirement,
        "nextOriginClassification": origin_next_classification,
        "nextRuntimeRootRecoveryPlan": runtime_root_recovery_plan,
    }


def markdown(data):
    lines = [
        "# UE4SS Linux Port Completion Audit",
        "",
        f"- Ready: `{str(data.get('ready', False)).lower()}`",
    ]
    if data.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in data["blockers"])
    lines.extend(["", "## Gates", ""])
    for item in data.get("gates", []):
        lines.append(f"- `{item['name']}` ready=`{str(item.get('ready', False)).lower()}` evidence=`{item.get('evidence', '')}`")
    if data.get("nextLivePreflightCommand"):
        lines.extend(["", "## Next Live Preflight Command", "", f"```bash\n{data['nextLivePreflightCommand']}\n```"])
    classification = data.get("nextOriginClassification") or {}
    if classification:
        lines.extend(
            [
                "",
                "## Next Origin/Reachability Classification",
                "",
                f"- Status: `{classification.get('status', '')}`",
                f"- Probe: `{classification.get('probeCandidate', '')}`",
                f"- Server-side fallback: `{classification.get('serverSideFallbackCandidate', '')}`",
                f"- Requires server-side replay: `{str(classification.get('requiresServerSideReplay', False)).lower()}`",
            ]
        )
        if classification.get("decision"):
            lines.append(f"- Decision: `{classification.get('decision', '')}`")
        if classification.get("nextStep"):
            lines.append(f"- Next step: `{classification.get('nextStep', '')}`")
    runtime_root = data.get("nextRuntimeRootRecoveryPlan") or {}
    if runtime_root:
        lines.extend(
            [
                "",
                "## Next Runtime Root Recovery",
                "",
                f"- Action: `{runtime_root.get('action', '')}`",
                f"- Required log: `{runtime_root.get('requiredLogPath', '')}`",
                f"- Blocked by missing log: `{str(runtime_root.get('blockedByMissingLog', False)).lower()}`",
                f"- Missing keys: `{', '.join(runtime_root.get('missingKeys', [])) or 'none'}`",
            ]
        )
        if runtime_root.get("preflightCommand"):
            lines.extend(["", "### Runtime Root Preflight", "", f"```bash\n{runtime_root['preflightCommand']}\n```"])
        if runtime_root.get("runCommand"):
            lines.extend(["", "### Runtime Root Canary", "", f"```bash\n{runtime_root['runCommand']}\n```"])
    requirement = data.get("nextRouteSlotTraceRequirement") or {}
    if requirement:
        lines.extend(
            [
                "",
                "## Next Route Slot Trace Requirement",
                "",
                f"- Marker: `{requirement.get('expectedTraceMarker', '')}`",
                f"- Route: `{requirement.get('routeAddress', '')}`",
                f"- Field: `{requirement.get('expectedReviewField', '')}`",
                f"- Missing slots: `{', '.join(requirement.get('missingSlots', [])) or 'none'}`",
                f"- Missing registers: `{', '.join(requirement.get('missingRegisters', [])) or 'none'}`",
            ]
        )
    if data.get("nextLiveCommand"):
        lines.extend(["", "## Next Live Command", "", f"```bash\n{data['nextLiveCommand']}\n```"])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit completion evidence for the UE4SS Linux port goal.")
    parser.add_argument("--package-verification", type=Path)
    parser.add_argument("--portability-check", type=Path, default=DEFAULT_PORTABILITY_CHECK)
    parser.add_argument("--port-gaps", type=Path, default=DEFAULT_PORT_GAPS)
    parser.add_argument("--next-action", type=Path, default=DEFAULT_NEXT_ACTION)
    parser.add_argument("--runbook", type=Path, default=DEFAULT_RUNBOOK)
    parser.add_argument("--preflight-summary", type=Path, default=DEFAULT_PREFLIGHT_SUMMARY)
    parser.add_argument("--preflight-max-age-seconds", type=int, default=DEFAULT_PREFLIGHT_MAX_AGE_SECONDS)
    parser.add_argument("--prearm-readiness", type=Path, default=DEFAULT_PREARM_READINESS)
    parser.add_argument("--live-summary", type=Path, default=DEFAULT_LIVE_SUMMARY)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    if args.package_verification is None:
        args.package_verification = latest_package_verification()
    data = audit(args)
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(markdown(data), end="")
    return 0 if data["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
