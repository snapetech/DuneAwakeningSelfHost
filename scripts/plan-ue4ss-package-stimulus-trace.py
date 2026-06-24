#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex


SCHEMA_VERSION = "dune-ue4ss-package-stimulus-trace-runbook/v1"
DEFAULT_ANCHORS = "LoadPackage,LoadObject"
DEFAULT_TRACE_LOG_PREFIX = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry"
DEFAULT_OPERATOR_ARM_WINDOW_SECONDS = 120
LOCAL_REVIEW_SUMMARY_SCHEMA_VERSION = "dune-ue4ss-package-live-stimulus-review-summary/v1"
LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS = (
    "reviewBundleVerification,reviewBundleVerificationSha256,"
    "routeSlotRecoveryVerification,routeSlotRecoveryVerificationSha256,"
    "prearmReadinessVerification,prearmReadinessVerificationSha256"
)
LOCAL_REVIEW_SUMMARY_RUNBOOK_MODE = "default-source-runbook;trace-log-override-effective-runbook"
DEFAULT_TRACE_LIMIT = "4"
DEFAULT_ROUTE_ADDRESS = "0x129d58a2"
DEFAULT_ROUTE_SLOT_TRACE_REQUIREMENT = {
    "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
    "routeAddress": DEFAULT_ROUTE_ADDRESS,
    "reviewField": "routeVtableStaticSlotMatches",
    "requiredSlots": ["0x3a0", "0x3d8"],
    "requiredRegisters": ["rbx", "r14"],
}
DEFAULT_RUNBOOK_PATH = "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json"
DEFAULT_LOCAL_REVIEW_SUMMARY_JSON = "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json"
DEFAULT_PREARM_READINESS_JSON = "build/server-current-anchor-prep/ue4ss-package-prearm-readiness.json"
DEFAULT_PREARM_READINESS_MD = "build/server-current-anchor-prep/ue4ss-package-prearm-readiness.md"


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


def recommended_candidate(stimulus_plan):
    recommended = stimulus_plan.get("recommendedCandidate", "")
    for row in stimulus_plan.get("candidates", []) or []:
        if isinstance(row, dict) and row.get("id") == recommended:
            return row
    return {}


def origin_classification(stimulus_plan):
    if not isinstance(stimulus_plan, dict):
        return {}
    classification = stimulus_plan.get("originClassification", {})
    return classification if isinstance(classification, dict) else {}


def env_prefix(
    anchor,
    limit,
    signature_family,
    hit_index,
    partition,
    remote_host,
    trace_log,
    external_plan,
    trace_plan_json,
    trace_plan_md,
    method_candidates,
    route_address=DEFAULT_ROUTE_ADDRESS,
):
    env = {
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR": anchor,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT": limit,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY": signature_family,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HIT_INDEX": hit_index,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PARTITION": partition,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST": remote_host,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN": external_plan,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON": trace_plan_json,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD": trace_plan_md,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES": method_candidates,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS": "false",
    }
    if route_address:
        env["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS"] = route_address
    return (
        " ".join(f"{name}={shlex.quote(str(value))}" for name, value in env.items())
        + " "
    )


def default_trace_log():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{DEFAULT_TRACE_LOG_PREFIX}-{stamp}.log"


def build_runbook(
    stimulus_plan,
    live_plan,
    remote="kspls0",
    container="dune_server-deep-desert-1",
    trace_log=None,
    partition="8",
    anchor=DEFAULT_ANCHORS,
    limit=DEFAULT_TRACE_LIMIT,
    signature_family="LoadPackage",
    hit_index="auto",
    external_plan="build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json",
    trace_plan_json="build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.json",
    trace_plan_md="build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.md",
    method_candidates="build/server-ue-package-loader-vtables.json",
    route_address=DEFAULT_ROUTE_ADDRESS,
    operator_arm_window_seconds=DEFAULT_OPERATOR_ARM_WINDOW_SECONDS,
):
    if trace_log is None:
        trace_log = default_trace_log()
    no_debugger_check_command = (
        "ssh "
        + shlex.quote(str(remote))
        + " "
        + shlex.quote(
            'ps -eo pid,stat,comm,args | grep -E "gdb|ue4ss-package-runtime-trace" | grep -v grep || true; '
            "docker top "
            + shlex.quote(str(container))
            + " -eo pid,stat,comm 2>/dev/null | awk 'NR==1 || /DuneSandboxServ/'"
        )
    )
    candidate = recommended_candidate(stimulus_plan)
    blockers = []
    if not candidate:
        blockers.append("stimulus plan has no resolvable recommended candidate")
    if candidate and candidate.get("promotableStimulus") is not True:
        blockers.append("recommended stimulus is not promotable")
    if live_plan.get("liveRouteAvailable") is not True:
        blockers.append("live call-frame route is not available")
    if not ((stimulus_plan.get("operationScriptCapabilities", {}) or {}).get("scripts/ue4ss-package-remote-trace.sh", {}) or {}).get(
        "hasZeroPlayerGuard"
    ):
        blockers.append("remote trace wrapper zero-player guard was not detected")

    prefix = env_prefix(
        anchor,
        limit,
        signature_family,
        hit_index,
        partition,
        remote,
        trace_log,
        external_plan,
        trace_plan_json,
        trace_plan_md,
        method_candidates,
        route_address=route_address,
    )
    base = " ".join(
        [
            "scripts/ue4ss-package-remote-trace.sh",
            "{action}",
            shlex.quote(str(remote)),
            shlex.quote(str(container)),
            shlex.quote(str(trace_log)),
        ]
    )
    review_artifacts = {
        "evidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
        "evidenceMarkdown": "/tmp/ue4ss-package-runtime-trace-evidence.md",
        "abiReviewJson": "/tmp/ue4ss-package-abi-review.json",
        "promotionEnvJson": "/tmp/ue4ss-package-promotion-env.json",
        "familyReviewsDir": "/tmp/ue4ss-package-family-reviews",
        "familyReviewsSummaryJson": "/tmp/ue4ss-package-family-reviews.json",
        "nextActionJson": "/tmp/ue4ss-package-next-action.json",
        "reviewBundleRoot": "/tmp/ue4ss-package-review-bundles",
        "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
        "localReviewSummaryJson": DEFAULT_LOCAL_REVIEW_SUMMARY_JSON,
        "localReviewSummarySchemaVersion": LOCAL_REVIEW_SUMMARY_SCHEMA_VERSION,
        "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
        "localReviewSummaryRunbookMode": LOCAL_REVIEW_SUMMARY_RUNBOOK_MODE,
        "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
    }
    local_review_summary_verification_command = (
        ""
        if blockers
        else (
            "scripts/verify-ue4ss-package-live-stimulus-summary.py "
            + shlex.quote(review_artifacts["localReviewSummaryJson"])
            + " --runbook-json "
            + shlex.quote(DEFAULT_RUNBOOK_PATH)
            + " --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json"
        )
    )
    prearm_readiness_verification_command = (
        ""
        if blockers
        else (
            "scripts/verify-ue4ss-package-prearm-readiness.py "
            "--preflight-summary build/server-current-anchor-prep/ue4ss-package-live-preflight-summary.json "
            "--runbook-json "
            + shlex.quote(DEFAULT_RUNBOOK_PATH)
            + " --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json "
            "--completion-audit-json build/server-current-anchor-prep/ue4ss-linux-port-completion-audit.json"
        )
    )
    review_artifacts["localReviewSummaryVerificationCommand"] = local_review_summary_verification_command
    review_artifacts["prearmReadinessJson"] = DEFAULT_PREARM_READINESS_JSON
    review_artifacts["prearmReadinessMarkdown"] = DEFAULT_PREARM_READINESS_MD
    review_artifacts["prearmReadinessVerificationCommand"] = prearm_readiness_verification_command
    cleanup_command = "" if blockers else prefix + base.format(action="stop")
    coordinator_command = "" if blockers else "scripts/run-ue4ss-package-live-stimulus-trace.sh"
    coordinator_dry_run_command = "" if blockers else "scripts/run-ue4ss-package-live-stimulus-trace.sh --dry-run --wait 30"
    coordinator_fresh_trace_command = (
        ""
        if blockers
        else "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log"
    )
    coordinator_fresh_preflight_command = (
        ""
        if blockers
        else "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log"
    )
    operator_stimulus_command = (
        "operator performs the approved client login/travel/map-entry package-load classification stimulus; "
        "if it is client-originated, recover the call frame and replay/spoof the equivalent call server-side"
    )
    commands = [] if blockers else [
        prefix + base.format(action="print"),
        prefix + base.format(action="preflight"),
        prefix + base.format(action="arm"),
        operator_stimulus_command,
        prefix + base.format(action="status"),
        cleanup_command,
    ]
    trace_env = {
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR": anchor,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT": limit,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY": signature_family,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HIT_INDEX": hit_index,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PARTITION": partition,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST": remote,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN": external_plan,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON": trace_plan_json,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_MD": trace_plan_md,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES": method_candidates,
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS": "false",
    }
    if route_address:
        trace_env["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS"] = route_address
    route_slot_trace_requirement = dict(DEFAULT_ROUTE_SLOT_TRACE_REQUIREMENT)
    route_slot_trace_requirement["routeAddress"] = route_address
    classification = origin_classification(stimulus_plan)
    if not classification:
        classification = {
            "status": "unknown",
            "probeCandidate": candidate.get("id", ""),
            "serverSideFallbackCandidate": "server-side-client-call-emulation",
            "decision": "trace first; classify whether the normal request reaches a usable server-side path; if it does not, recover and replay/spoof the equivalent call server-side",
        }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourcePath": DEFAULT_RUNBOOK_PATH,
        "recommendedCandidate": candidate.get("id", ""),
        "stimulusKind": candidate.get("kind", ""),
        "safe": candidate.get("safe", ""),
        "promotableStimulus": candidate.get("promotableStimulus"),
        "originClassification": classification,
        "remote": remote,
        "container": container,
        "partition": partition,
        "traceLog": trace_log,
        "traceLogUniqueness": {
            "strategy": "utc-timestamp-default",
            "defaultPrefix": DEFAULT_TRACE_LOG_PREFIX,
            "operatorOverride": "--trace-log",
        },
        "operatorWindow": {
            "maxArmSeconds": int(operator_arm_window_seconds),
            "sequence": [
                "preflight",
                "arm",
                "operator-client-login-travel-map-entry",
                "status",
                "cleanupCommand",
                "no-debugger-check",
            ],
            "cleanupRequired": True,
        },
        "traceEnv": trace_env,
        "traceInputs": {
            "externalPlan": external_plan,
            "tracePlanJson": trace_plan_json,
            "tracePlanMarkdown": trace_plan_md,
            "methodCandidates": method_candidates,
            "routeAddress": route_address,
        },
        "routeSlotTraceRequirement": route_slot_trace_requirement,
        "guards": [
            "remote hostname must match kspls0 unless explicitly overridden",
            "remote preflight and arm must report connected_players=0 for the target partition",
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=true is forbidden when the required remote host is kspls0",
            "do not perform database/admin/player mutations as the client map-entry stimulus",
            f"keep the arm-to-status stimulus window under {int(operator_arm_window_seconds)} seconds unless a new runbook is generated",
            "run cleanupCommand and a no-debugger check after status",
        ],
        "reviewArtifacts": review_artifacts,
        "cleanupCommand": cleanup_command,
        "coordinatorCommand": coordinator_command,
        "coordinatorDryRunCommand": coordinator_dry_run_command,
        "coordinatorFreshPreflightCommand": coordinator_fresh_preflight_command,
        "coordinatorFreshTraceCommand": coordinator_fresh_trace_command,
        "localReviewSummaryJson": review_artifacts["localReviewSummaryJson"],
        "localReviewSummarySchemaVersion": review_artifacts["localReviewSummarySchemaVersion"],
        "localReviewSummaryRunbookMode": review_artifacts["localReviewSummaryRunbookMode"],
        "localReviewSummaryVerificationCommand": local_review_summary_verification_command,
        "prearmReadinessJson": DEFAULT_PREARM_READINESS_JSON,
        "prearmReadinessMarkdown": DEFAULT_PREARM_READINESS_MD,
        "prearmReadinessVerificationCommand": prearm_readiness_verification_command,
        "noDebuggerCheckCommand": no_debugger_check_command if not blockers else "",
        "postStatusAcceptance": [
            "runtime trace evidence has at least one package hit for a selected package anchor family",
            "ABI review identifies target-image caller/rip image offsets and the selected signature family",
            "promotion env is ready for non-invoking canary only after ABI, target-image, TCHAR, and class-root review gates pass",
            "review bundle verification reports ready before replaying next-action or canary planning from captured evidence",
            "review bundle verification matches sourceEvidenceJson, sourceLogSha256, and sourceEvidenceJsonSha256 across evidence, ABI review, promotion env, family summaries, and manifest",
            "route-slot recovery verification reports routeVtableStaticSlotMatches for slots 0x3a0 and 0x3d8 from UE4SS_PACKAGE_ROUTE_TRACE_HIT evidence before package route recovery is accepted",
            "local live stimulus review summary embeds reviewBundleVerification, routeSlotRecoveryVerification, and prearmReadinessVerification with matching sha256 fields and verifies ready against the default source runbook, or the effective temporary runbook when --trace-log overrides traceLog",
            "origin/reachability classification is recorded as server-originated, client-originated, or missing; if the normal request does not reach a usable server-side path, the next promotion path is server-side call-frame replay/spoofing rather than client file modification",
        ],
        "blockers": blockers,
        "commands": commands,
        "nextStep": (
            "run coordinatorCommand, perform the approved map-entry reachability stimulus inside operatorWindow.maxArmSeconds, then verify the review bundle and local review summary; if the normal request does not reach a usable server-side path, proceed through server-side call-frame replay/spoofing"
            if not blockers
            else "resolve runbook blockers before arming the live package trace"
        ),
    }


def markdown(runbook):
    lines = ["# UE4SS Package Stimulus Trace Runbook", ""]
    lines.append(f"- Recommended candidate: `{runbook['recommendedCandidate']}`")
    classification = runbook.get("originClassification", {}) or {}
    if classification:
        lines.append(f"- Origin/reachability classification: `{classification.get('status', '')}`")
        lines.append(f"- Server-side fallback: `{classification.get('serverSideFallbackCandidate', '')}`")
    lines.append(f"- Remote: `{runbook['remote']}`")
    lines.append(f"- Container: `{runbook['container']}`")
    lines.append(f"- Partition: `{runbook['partition']}`")
    lines.append(f"- Trace log: `{runbook['traceLog']}`")
    operator_window = runbook.get("operatorWindow", {}) or {}
    if operator_window:
        lines.append(f"- Max arm window seconds: `{operator_window.get('maxArmSeconds')}`")
    lines.append("")
    lines.append("## Guards")
    lines.append("")
    for guard in runbook.get("guards", []):
        lines.append(f"- {guard}")
    lines.append("")
    lines.append("## Post-Status Acceptance")
    lines.append("")
    for item in runbook.get("postStatusAcceptance", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Review Artifacts")
    lines.append("")
    for key, value in (runbook.get("reviewArtifacts", {}) or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    route_slot = runbook.get("routeSlotTraceRequirement", {}) or {}
    if route_slot:
        lines.append("")
        lines.append("## Route Slot Trace Requirement")
        lines.append("")
        lines.append(f"- Marker: `{route_slot.get('expectedTraceMarker', '')}`")
        lines.append(f"- Route: `{route_slot.get('routeAddress', '')}`")
        lines.append(f"- Review field: `{route_slot.get('reviewField', '')}`")
        lines.append("- Required slots: `" + ", ".join(route_slot.get("requiredSlots", []) or []) + "`")
        lines.append("- Required registers: `" + ", ".join(route_slot.get("requiredRegisters", []) or []) + "`")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    for blocker in runbook.get("blockers", []):
        lines.append(f"- {blocker}")
    if not runbook.get("blockers"):
        lines.append("- none")
    if runbook.get("commands"):
        lines.append("")
        if runbook.get("coordinatorCommand"):
            lines.append("## Coordinator")
            lines.append("")
            lines.append("```bash")
            if runbook.get("coordinatorDryRunCommand"):
                lines.append("# Rehearse without arming")
                lines.append(runbook["coordinatorDryRunCommand"])
            if runbook.get("coordinatorFreshPreflightCommand"):
                lines.append("# Validate a fresh trace log against the remote target without arming")
                lines.append(runbook["coordinatorFreshPreflightCommand"])
            if runbook.get("coordinatorFreshTraceCommand"):
                lines.append("# Live run with a fresh trace log")
                lines.append(runbook["coordinatorFreshTraceCommand"])
                lines.append("# Live run")
            lines.append(runbook["coordinatorCommand"])
            lines.append("```")
            lines.append("")
        lines.append("## Commands")
        lines.append("")
        lines.append("```bash")
        for command in runbook["commands"]:
            lines.append(command)
        lines.append("```")
    if runbook.get("cleanupCommand"):
        lines.append("")
        lines.append("## Cleanup")
        lines.append("")
        lines.append("```bash")
        lines.append(runbook["cleanupCommand"])
        lines.append("```")
    if runbook.get("noDebuggerCheckCommand"):
        lines.append("")
        lines.append("## No-Debugger Check")
        lines.append("")
        lines.append("```bash")
        lines.append(runbook["noDebuggerCheckCommand"])
        lines.append("```")
    lines.append("")
    lines.append(f"Next step: {runbook['nextStep']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan a guarded UE4SS package stimulus trace runbook.")
    parser.add_argument("--stimulus-plan-json", default="build/server-current-anchor-prep/ue4ss-package-stimulus-plan.json")
    parser.add_argument("--live-plan-json", default="build/server-current-anchor-prep/ue4ss-package-live-call-frame-recovery-plan.json")
    parser.add_argument("--remote", default="kspls0")
    parser.add_argument("--container", default="dune_server-deep-desert-1")
    parser.add_argument("--trace-log", default=None)
    parser.add_argument("--partition", default="8")
    parser.add_argument("--anchor", default=DEFAULT_ANCHORS)
    parser.add_argument("--limit", default=DEFAULT_TRACE_LIMIT)
    parser.add_argument("--signature-family", default="LoadPackage")
    parser.add_argument("--hit-index", default="auto")
    parser.add_argument("--external-plan", default="build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json")
    parser.add_argument("--trace-plan-json", default="build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.json")
    parser.add_argument("--trace-plan-md", default="build/server-current-anchor-prep/ue4ss-package-runtime-trace-plan.md")
    parser.add_argument("--method-candidates", default="build/server-ue-package-loader-vtables.json")
    parser.add_argument("--route-address", default=DEFAULT_ROUTE_ADDRESS)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    runbook = build_runbook(
        load_json(args.stimulus_plan_json),
        load_json(args.live_plan_json),
        remote=args.remote,
        container=args.container,
        trace_log=args.trace_log,
        partition=args.partition,
        anchor=args.anchor,
        limit=args.limit,
        signature_family=args.signature_family,
        hit_index=args.hit_index,
        external_plan=args.external_plan,
        trace_plan_json=args.trace_plan_json,
        trace_plan_md=args.trace_plan_md,
        method_candidates=args.method_candidates,
        route_address=args.route_address,
    )
    if args.format == "json":
        print(json.dumps(runbook, indent=2, sort_keys=True))
    else:
        print(markdown(runbook), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
