#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-live-call-frame-recovery-plan/v1"


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


def trace_history_entries(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        entries = data.get("entries")
        if isinstance(entries, list):
            return entries
        return [data]
    return []


def no_promotable_route(route_evidence):
    return int(route_evidence.get("promotableRouteCount", 0) or 0) == 0


def method_probes_exhausted(method_refinement):
    return method_refinement.get("selectedCount") == 0


def static_metadata_exhausted(static_metadata):
    return static_metadata.get("complete") is False and bool(static_metadata.get("blockers"))


def source_abi_contract_ready(source_abi):
    contract = source_abi.get("loaderContract", {}) or {}
    return (
        int(contract.get("typedefCount", 0) or 0) >= 2
        and int(contract.get("requiredSignatureCount", 0) or 0) >= 2
        and contract.get("requiresObservedTcharUnitMatch") is True
        and contract.get("hasGuardedNativeCallAdapter") is True
    )


def donor_unavailable(external_plan):
    donor = external_plan.get("donorSearch", {}) or {}
    return int(donor.get("usableCandidateCount", 0) or 0) == 0


def trace_history_summary(trace_history):
    entries = trace_history_entries(trace_history)
    return {
        "entryCount": len(entries),
        "packageHitCount": sum(int(entry.get("hitCount", 0) or 0) for entry in entries if isinstance(entry, dict)),
        "methodHitCount": sum(int(entry.get("methodHitCount", 0) or 0) for entry in entries if isinstance(entry, dict)),
        "zeroPackageHitRunCount": sum(
            1
            for entry in entries
            if isinstance(entry, dict)
            and int(entry.get("armedCount", 0) or 0) > 0
            and int(entry.get("hitCount", 0) or 0) == 0
        ),
    }


def stimulus_summary(stimulus_plan):
    candidates = stimulus_plan.get("candidates", []) if isinstance(stimulus_plan, dict) else []
    recommended = stimulus_plan.get("recommendedCandidate", "") if isinstance(stimulus_plan, dict) else ""
    recommended_row = {}
    for row in candidates:
        if isinstance(row, dict) and row.get("id") == recommended:
            recommended_row = row
            break
    return {
        "sourcePath": stimulus_plan.get("sourcePath", "") if isinstance(stimulus_plan, dict) else "",
        "recommendedCandidate": recommended,
        "loaderOnlyStimulusCanHitTargetPackageLoad": stimulus_plan.get("loaderOnlyStimulusCanHitTargetPackageLoad")
        if isinstance(stimulus_plan, dict)
        else None,
        "recommendedPromotableStimulus": recommended_row.get("promotableStimulus"),
        "originClassification": stimulus_plan.get("originClassification", {})
        if isinstance(stimulus_plan.get("originClassification", {}), dict)
        else {},
        "nextStep": stimulus_plan.get("nextStep", "") if isinstance(stimulus_plan, dict) else "",
    }


def trace_runbook_summary(trace_runbook):
    if not isinstance(trace_runbook, dict):
        return {}
    return {
        "schemaVersion": trace_runbook.get("schemaVersion", ""),
        "recommendedCandidate": trace_runbook.get("recommendedCandidate", ""),
        "blockerCount": len(trace_runbook.get("blockers", []) or []),
        "commandCount": len(trace_runbook.get("commands", []) or []),
        "traceLog": trace_runbook.get("traceLog", ""),
        "nextStep": trace_runbook.get("nextStep", ""),
    }


def trace_runbook_commands(trace_runbook):
    if not isinstance(trace_runbook, dict):
        return []
    commands = trace_runbook.get("commands", [])
    if not isinstance(commands, list):
        return []
    return [command for command in commands if isinstance(command, str) and command]


def prearm_readiness_summary(prearm_readiness):
    if not isinstance(prearm_readiness, dict):
        return {}
    return {
        "ready": prearm_readiness.get("ready"),
        "blockers": prearm_readiness.get("blockers", []) if isinstance(prearm_readiness.get("blockers", []), list) else [],
        "preflightReady": prearm_readiness.get("preflightReady"),
        "routeAddress": prearm_readiness.get("routeAddress", ""),
        "freshPreflightCommand": prearm_readiness.get("freshPreflightCommand", ""),
        "freshTraceCommand": prearm_readiness.get("freshTraceCommand", ""),
        "nextStep": prearm_readiness.get("nextStep", ""),
    }


def build_plan(
    route_evidence,
    method_refinement,
    static_metadata,
    source_abi,
    external_plan,
    trace_history,
    stimulus_plan=None,
    trace_runbook=None,
    prearm_readiness=None,
):
    history = trace_history_summary(trace_history)
    stimulus = stimulus_summary(stimulus_plan or {})
    runbook = trace_runbook_summary(trace_runbook or {})
    prearm = prearm_readiness_summary(prearm_readiness or {})
    blockers = []
    if not no_promotable_route(route_evidence):
        blockers.append("route evidence already has a promotable package route; use promotion/canary planning instead")
    if not method_probes_exhausted(method_refinement):
        blockers.append("unreviewed method probes remain; review or trace those before planning a new live call-frame route")
    if not static_metadata_exhausted(static_metadata):
        blockers.append("static metadata recovery is not exhausted; finish that local route first")
    if not source_abi_contract_ready(source_abi):
        blockers.append("loader-side source ABI contract is incomplete")
    if not donor_unavailable(external_plan):
        blockers.append("usable external donor evidence exists; validate donor signatures before live tracing")
    if prearm and prearm.get("ready") is not True:
        blockers.append("package live-stimulus prearm readiness is not ready")

    repeat_trace_useful = False
    repeat_trace_reason = (
        "previous traces armed package watchpoints but produced zero package hits; repeating without a new package-load stimulus is not useful"
        if history["zeroPackageHitRunCount"]
        else "no prior armed package trace history is available"
    )
    live_route_available = not blockers
    commands = []
    if live_route_available:
        if prearm.get("freshTraceCommand"):
            commands = [
                "cat build/server-current-anchor-prep/ue4ss-package-prearm-readiness.json",
                prearm["freshTraceCommand"],
            ]
        else:
            commands = trace_runbook_commands(trace_runbook)
        if commands and commands[0] != "cat build/server-current-anchor-prep/ue4ss-package-prearm-readiness.json":
            commands = ["cat build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json"] + commands
        elif not commands:
            commands = [
                "cat build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT=5 DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false scripts/ue4ss-package-remote-trace.sh print",
            ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "action": "plan-live-call-frame-stimulus" if live_route_available else "defer-live-call-frame-trace",
        "liveRouteAvailable": live_route_available,
        "repeatTraceUsefulWithoutStimulus": repeat_trace_useful,
        "repeatTraceReason": repeat_trace_reason,
        "routeEvidence": {
            "routeCount": int(route_evidence.get("routeCount", 0) or 0),
            "promotableRouteCount": int(route_evidence.get("promotableRouteCount", 0) or 0),
        },
        "methodProbeRefinement": {
            "candidateCount": method_refinement.get("candidateCount"),
            "selectedCount": method_refinement.get("selectedCount"),
        },
        "staticMetadataRecovery": {
            "complete": static_metadata.get("complete"),
            "blockers": static_metadata.get("blockers", []) or [],
        },
        "sourceAbiRecovery": {
            "contractReady": source_abi_contract_ready(source_abi),
            "blockers": source_abi.get("blockers", []) or [],
        },
        "externalSymbols": {
            "usableDonorCandidateCount": int((external_plan.get("donorSearch", {}) or {}).get("usableCandidateCount", 0) or 0),
            "falsePositiveCandidateCount": int((external_plan.get("donorSearch", {}) or {}).get("falsePositiveCandidateCount", 0) or 0),
        },
        "traceHistory": history,
        "stimulusPlan": stimulus,
        "traceRunbook": runbook,
        "prearmReadiness": prearm,
        "blockers": blockers,
        "requiredStimulus": [
            "operator-visible classification action that proves whether UE package/class loading reaches the server from the natural client path",
            "fresh package live-stimulus prearm readiness is true before attaching gdb",
            "zero connected players on the target partition before attaching gdb",
            "unique trace log path and verified post-stop no lingering gdb",
            "if the only package-load trigger is client-originated, capture the call frame and replay/spoof the equivalent call server-side instead of requiring client modification",
        ],
        "acceptance": [
            "captured hit includes target-image caller/backtrace for StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName",
            "captured frame is reviewed against SysV x86_64 argument order and loader TCHAR unit-size evidence",
            "classification records server-originated, client-originated, or missing package-load evidence",
            "client-originated evidence is promoted only through server-side replay/spoof planning, not client file edits",
            "promotion proceeds only through reviewed ABI metadata and guarded non-invoking canary before final native invocation",
            "review bundle verification matches sourceEvidenceJson, sourceLogSha256, and sourceEvidenceJsonSha256 before replaying next-action or canary planning",
        ],
        "commands": commands,
        "nextStep": (
            "select the recommended classification stimulus, preflight zero-player live target, then arm one bounded all-family call-frame trace; if the result is client-originated, move to server-side replay/spoof planning"
            if live_route_available
            else "resolve listed blockers before live call-frame tracing"
        ),
    }


def markdown(plan):
    lines = ["# UE4SS Package Live Call-Frame Recovery Plan", ""]
    lines.append(f"- Action: `{plan['action']}`")
    lines.append(f"- Live route available: `{str(plan['liveRouteAvailable']).lower()}`")
    lines.append(f"- Repeat trace useful without stimulus: `{str(plan['repeatTraceUsefulWithoutStimulus']).lower()}`")
    lines.append(f"- Repeat trace reason: {plan['repeatTraceReason']}")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    for blocker in plan.get("blockers", []):
        lines.append(f"- {blocker}")
    if not plan.get("blockers"):
        lines.append("- none")
    lines.append("")
    lines.append("## Required Stimulus")
    lines.append("")
    stimulus = plan.get("stimulusPlan", {}) or {}
    if stimulus.get("recommendedCandidate"):
        lines.append(f"- recommended candidate: `{stimulus['recommendedCandidate']}`")
        lines.append(
            f"- loader-only can hit target package load: `{str(stimulus.get('loaderOnlyStimulusCanHitTargetPackageLoad')).lower()}`"
        )
        classification = stimulus.get("originClassification", {}) or {}
        if classification:
            lines.append(f"- origin classification: `{classification.get('status', '')}`")
            lines.append(f"- server-side fallback: `{classification.get('serverSideFallbackCandidate', '')}`")
    prearm = plan.get("prearmReadiness", {}) or {}
    if prearm:
        lines.append(f"- prearm readiness: `{str(prearm.get('ready')).lower()}`")
        lines.append(f"- preflight ready: `{str(prearm.get('preflightReady')).lower()}`")
        if prearm.get("routeAddress"):
            lines.append(f"- route address: `{prearm.get('routeAddress')}`")
    for item in plan.get("requiredStimulus", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Acceptance")
    lines.append("")
    for item in plan.get("acceptance", []):
        lines.append(f"- {item}")
    if plan.get("commands"):
        lines.append("")
        lines.append("## Commands")
        lines.append("")
        lines.append("```bash")
        for command in plan["commands"]:
            lines.append(command)
        lines.append("```")
    lines.append("")
    lines.append(f"Next step: {plan['nextStep']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan the remaining UE4SS package live call-frame recovery route.")
    parser.add_argument("--route-evidence-json", default="build/server-current-anchor-prep/ue4ss-package-route-evidence.json")
    parser.add_argument("--method-probe-refinement-json", default="build/server-current-anchor-prep/ue4ss-package-method-probe-refinement.json")
    parser.add_argument("--static-metadata-json", default="build/server-current-anchor-prep/ue4ss-package-static-metadata-recovery.json")
    parser.add_argument("--source-abi-json", default="build/server-current-anchor-prep/ue4ss-package-source-abi-recovery.json")
    parser.add_argument("--external-plan-json", default="build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json")
    parser.add_argument("--trace-history-json", default="build/server-current-anchor-prep/ue4ss-package-runtime-trace-history.json")
    parser.add_argument("--stimulus-plan-json", default="build/server-current-anchor-prep/ue4ss-package-stimulus-plan.json")
    parser.add_argument("--trace-runbook-json", default="build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json")
    parser.add_argument("--prearm-readiness-json", default="build/server-current-anchor-prep/ue4ss-package-prearm-readiness.json")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    plan = build_plan(
        load_json(args.route_evidence_json),
        load_json(args.method_probe_refinement_json),
        load_json(args.static_metadata_json),
        load_json(args.source_abi_json),
        load_json(args.external_plan_json),
        load_json(args.trace_history_json),
        load_json(args.stimulus_plan_json),
        load_json(args.trace_runbook_json),
        load_json(args.prearm_readiness_json),
    )
    if args.format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(markdown(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
