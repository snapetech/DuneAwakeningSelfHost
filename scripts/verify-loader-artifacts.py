#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TARGETS = {
    "linux-server": {
        "paths": (
            ROOT / "build" / "linux-server-loader" / "libdune_server_probe_loader.so",
            ROOT / "lib" / "libdune_server_probe_loader.so",
        ),
        "kind": "elf",
        "soname": "libdune_server_probe_loader.so",
    },
    "linux-client": {
        "paths": (
            ROOT / "build" / "linux-client-loader" / "libdune_client_probe_loader.so",
            ROOT / "lib" / "libdune_client_probe_loader.so",
        ),
        "kind": "elf",
        "soname": "libdune_client_probe_loader.so",
    },
    "windows-client": {
        "paths": (
            ROOT / "build" / "windows-client-loader" / "dune_win_client_probe_loader.dll",
            ROOT / "lib" / "dune_win_client_probe_loader.dll",
            ROOT / "lib" / "version.dll",
        ),
        "kind": "pe",
        "exports": (
            "DuneWinClientProbeSmoke",
            "DuneWinClientProbeForwardSmoke",
            "DuneWinClientProbeMarker",
            "GetFileVersionInfoA",
            "GetFileVersionInfoW",
            "GetFileVersionInfoSizeA",
            "GetFileVersionInfoSizeW",
            "VerQueryValueA",
            "VerQueryValueW",
        ),
    },
}

PACKAGE_LAYOUTS = {
    "linux-server": (
        "lib/libdune_server_probe_loader.so",
        "src/dune_server_probe_loader.c",
        "src/CMakeLists.txt",
        "build-linux-server-loader.sh",
        "examples/smoke-linux-server-loader.sh",
        "examples/smoke-cached-funcom-image.sh",
        "scripts/ue4ss-port-readiness.py",
        "scripts/summarize-ue4ss-port-gaps.py",
        "scripts/summarize-ue4ss-evidence-inventory.py",
        "scripts/ue4ss-portability-contract.py",
        "scripts/verify-loader-artifacts.py",
        "scripts/ue4ss-package-runtime-trace.sh",
        "scripts/ue4ss-package-remote-trace.sh",
        "scripts/run-ue4ss-package-live-stimulus-trace.sh",
        "scripts/plan-ue4ss-package-runtime-trace.py",
        "scripts/summarize-ue4ss-package-runtime-trace-evidence.py",
        "scripts/plan-ue4ss-package-stimulus.py",
        "scripts/plan-ue4ss-package-stimulus-trace.py",
        "scripts/plan-ue4ss-package-live-call-frame-recovery.py",
        "scripts/plan-ue4ss-package-server-replay.py",
        "scripts/export-ue4ss-package-promotion-env.py",
        "scripts/review-ue4ss-package-abi.py",
        "scripts/summarize-ue4ss-package-promotion-dir.py",
        "scripts/plan-ue4ss-package-next-action.py",
        "scripts/verify-ue4ss-package-review-bundle.py",
        "scripts/verify-ue4ss-package-route-slot-recovery.py",
        "scripts/verify-ue4ss-package-live-stimulus-summary.py",
        "scripts/verify-ue4ss-package-live-preflight-summary.py",
        "scripts/verify-ue4ss-package-prearm-readiness.py",
        "scripts/audit-ue4ss-linux-port-completion.py",
        "tests/test-ue4ss-port-readiness.py",
        "tests/test-ue4ss-port-gaps.py",
        "tests/test-ue4ss-evidence-inventory.py",
        "tests/test-ue4ss-portability-contract.py",
        "tests/test-verify-loader-artifacts.py",
        "tests/test-ue4ss-package-runtime-trace-runner.py",
        "tests/test-ue4ss-package-remote-trace.py",
        "tests/test-ue4ss-package-live-stimulus-trace-runner.py",
        "tests/test-ue4ss-package-runtime-trace-plan.py",
        "tests/test-ue4ss-package-runtime-trace-evidence.py",
        "tests/test-ue4ss-package-stimulus.py",
        "tests/test-ue4ss-package-stimulus-trace.py",
        "tests/test-ue4ss-package-live-call-frame-recovery.py",
        "tests/test-ue4ss-package-server-replay.py",
        "tests/test-export-ue4ss-package-promotion-env.py",
        "tests/test-review-ue4ss-package-abi.py",
        "tests/test-ue4ss-package-promotion-dir-summary.py",
        "tests/test-ue4ss-package-next-action.py",
        "tests/test-verify-ue4ss-package-review-bundle.py",
        "tests/test-verify-ue4ss-package-route-slot-recovery.py",
        "tests/test-verify-ue4ss-package-live-stimulus-summary.py",
        "tests/test-verify-ue4ss-package-live-preflight-summary.py",
        "tests/test-verify-ue4ss-package-prearm-readiness.py",
        "tests/test-audit-ue4ss-linux-port-completion.py",
        "docs/ue4ss-linux-loader-evaluation.md",
        "docs/ue4ss-portability-contract.json",
        "docs/ue4ss-portability-contract.md",
        "README.md",
    ),
    "linux-client": (
        "lib/libdune_client_probe_loader.so",
        "src/dune_client_probe_loader.c",
        "src/CMakeLists.txt",
        "build-linux-client-loader.sh",
        "examples/launch-native-client.sh",
        "examples/verify-client-probe-canary.sh",
        "examples/smoke-linux-client-loader.sh",
        "analysis/ue4ss-port-readiness.py",
        "analysis/summarize-ue4ss-port-gaps.py",
        "analysis/summarize-ue4ss-evidence-inventory.py",
        "analysis/ue4ss-portability-contract.py",
        "analysis/verify-loader-artifacts.py",
        "tests/test-ue4ss-port-readiness.py",
        "tests/test-ue4ss-port-gaps.py",
        "tests/test-ue4ss-evidence-inventory.py",
        "tests/test-ue4ss-portability-contract.py",
        "tests/test-verify-loader-artifacts.py",
        "docs/client-loader-support.md",
        "docs/linux-client-loader.md",
        "docs/ue4ss-portability-contract.json",
        "docs/ue4ss-portability-contract.md",
    ),
    "windows-client": (
        "lib/dune_win_client_probe_loader.dll",
        "lib/version.dll",
        "src/dune_win_client_probe_loader.c",
        "build-windows-client-loader.sh",
        "examples/launch-proton-client-probe.sh",
        "examples/verify-client-probe-canary.sh",
        "examples/smoke-windows-client-loader.sh",
        "examples/smoke-windows-client-loader-lua.sh",
        "analysis/ue4ss-port-readiness.py",
        "analysis/summarize-ue4ss-port-gaps.py",
        "analysis/summarize-ue4ss-evidence-inventory.py",
        "analysis/ue4ss-portability-contract.py",
        "analysis/verify-loader-artifacts.py",
        "tests/test-ue4ss-port-readiness.py",
        "tests/test-ue4ss-port-gaps.py",
        "tests/test-ue4ss-evidence-inventory.py",
        "tests/test-ue4ss-portability-contract.py",
        "tests/test-verify-loader-artifacts.py",
        "docs/client-loader-support.md",
        "docs/windows-client-loader.md",
        "docs/ue4ss-portability-contract.json",
        "docs/ue4ss-portability-contract.md",
    ),
}

PACKAGE_EXECUTABLES = {
    "linux-server": (
        "build-linux-server-loader.sh",
        "examples/smoke-linux-server-loader.sh",
        "examples/smoke-cached-funcom-image.sh",
        "scripts/ue4ss-port-readiness.py",
        "scripts/summarize-ue4ss-port-gaps.py",
        "scripts/summarize-ue4ss-evidence-inventory.py",
        "scripts/ue4ss-portability-contract.py",
        "scripts/verify-loader-artifacts.py",
        "scripts/ue4ss-package-runtime-trace.sh",
        "scripts/ue4ss-package-remote-trace.sh",
        "scripts/run-ue4ss-package-live-stimulus-trace.sh",
        "scripts/plan-ue4ss-package-runtime-trace.py",
        "scripts/summarize-ue4ss-package-runtime-trace-evidence.py",
        "scripts/plan-ue4ss-package-stimulus.py",
        "scripts/plan-ue4ss-package-stimulus-trace.py",
        "scripts/plan-ue4ss-package-live-call-frame-recovery.py",
        "scripts/export-ue4ss-package-promotion-env.py",
        "scripts/review-ue4ss-package-abi.py",
        "scripts/summarize-ue4ss-package-promotion-dir.py",
        "scripts/plan-ue4ss-package-next-action.py",
        "scripts/verify-ue4ss-package-review-bundle.py",
        "scripts/verify-ue4ss-package-route-slot-recovery.py",
        "scripts/verify-ue4ss-package-live-stimulus-summary.py",
        "scripts/verify-ue4ss-package-live-preflight-summary.py",
        "scripts/verify-ue4ss-package-prearm-readiness.py",
        "scripts/audit-ue4ss-linux-port-completion.py",
    ),
    "linux-client": (
        "build-linux-client-loader.sh",
        "examples/launch-native-client.sh",
        "examples/verify-client-probe-canary.sh",
        "examples/smoke-linux-client-loader.sh",
        "analysis/ue4ss-port-readiness.py",
        "analysis/summarize-ue4ss-port-gaps.py",
        "analysis/summarize-ue4ss-evidence-inventory.py",
        "analysis/ue4ss-portability-contract.py",
        "analysis/verify-loader-artifacts.py",
    ),
    "windows-client": (
        "build-windows-client-loader.sh",
        "examples/launch-proton-client-probe.sh",
        "examples/verify-client-probe-canary.sh",
        "examples/smoke-windows-client-loader.sh",
        "examples/smoke-windows-client-loader-lua.sh",
        "analysis/ue4ss-port-readiness.py",
        "analysis/summarize-ue4ss-port-gaps.py",
        "analysis/summarize-ue4ss-evidence-inventory.py",
        "analysis/ue4ss-portability-contract.py",
        "analysis/verify-loader-artifacts.py",
    ),
}

PACKAGE_DOC_MARKERS = {
    "linux-server": {
        "docs/ue4ss-linux-loader-evaluation.md": (
            "# UE4SS Linux Server Loader Evaluation",
            "Repo-Side Loader Foundation",
            "ue4ss-package-runtime-trace.sh",
            "ue4ss-package-remote-trace.sh",
            "plan-ue4ss-package-stimulus.py",
            "plan-ue4ss-package-stimulus-trace.py",
            "plan-ue4ss-package-server-replay.py",
            "ue4ss-package-stimulus-trace-runbook.json",
            "ue4ss-package-server-replay-plan.json",
            "verify-ue4ss-package-review-bundle.py",
            "plan-ue4ss-package-next-action.py",
            "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true",
            "--require-complete",
            "ue4ss-evidence-inventory.json",
            "ue4ss-evidence-inventory.md",
            "summarize-ue4ss-evidence-inventory.py",
            "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceEvidenceJsonSha256",
            "cleanupCommand",
            "matching `stop` command",
        ),
        "README.md": (
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
            "verify-ue4ss-package-live-stimulus-summary.py",
            "verify-ue4ss-package-route-slot-recovery.py <ue4ss-package-runtime-trace-evidence.json> --next-action-json ue4ss-package-next-action.json",
            "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "routeVtableStaticSlotMatches",
            "routeSlotTraceRequirement",
            "expectedTraceMarker=UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "reviewField=routeVtableStaticSlotMatches",
            "requiredSlots=[0x3a0,0x3d8]",
            "requiredRegisters=[rbx,r14]",
            "0x129d58a2",
            "0x3a0, 0x3d8",
            "rbx, r14",
        ),
    },
    "linux-client": {
        "docs/client-loader-support.md": (
            "# Client Loader Support Matrix",
            "Linux native client",
            "Windows/Proton client",
            "verify-client-probe-canary.sh --strict",
            "--require-complete",
            "ue4ss-evidence-inventory.json",
            "ue4ss-evidence-inventory.md",
            "summarize-ue4ss-evidence-inventory.py",
        ),
        "docs/linux-client-loader.md": (
            "# Linux Client Loader",
            "LD_PRELOAD",
            "--strict",
            "--require-complete",
            "ue4ss-evidence-inventory.json",
            "ue4ss-evidence-inventory.md",
            "summarize-ue4ss-evidence-inventory.py",
        ),
    },
    "windows-client": {
        "docs/client-loader-support.md": (
            "# Client Loader Support Matrix",
            "Windows/Proton client",
            "verify-client-probe-canary.sh --strict",
            "--require-complete",
            "ue4ss-evidence-inventory.json",
            "ue4ss-evidence-inventory.md",
            "summarize-ue4ss-evidence-inventory.py",
        ),
        "docs/windows-client-loader.md": (
            "# Windows Client Loader",
            "version.dll",
            "--strict",
            "--require-complete",
            "ue4ss-evidence-inventory.json",
            "ue4ss-evidence-inventory.md",
            "summarize-ue4ss-evidence-inventory.py",
        ),
    },
}

PACKAGE_DOC_MIN_BYTES = 128

PACKAGE_FILE_MARKERS = {
    "linux-server": {
        "scripts/ue4ss-package-runtime-trace.sh": (
            "local gdb_pid=$!",
            "package trace gdb exited before the arm window could be used",
            'echo "gdb_running=true"',
            'echo "gdb_running=false"',
            "package trace gdb pid file exists but gdb is not running",
        ),
        "scripts/ue4ss-package-remote-trace.sh": (
            "live_trace_runbook_json=",
            "require_trace_log_matches_runbook",
            "trace_log must match live trace runbook traceLog",
            "require_cleanup_matches_runbook",
            "cleanupCommand must match stop",
            "DUNE_UE4SS_PACKAGE_TRACE_LIVE_RUNBOOK_JSON",
        ),
        "scripts/ue4ss-port-readiness.py": (
            "validate_runtime_log_path",
            "runtime log must be a regular file",
            "runtime log must not be empty",
        ),
        "tests/test-ue4ss-port-readiness.py": (
            "test_cli_rejects_empty_runtime_log",
            "test_cli_rejects_special_device_runtime_log",
        ),
        "scripts/run-ue4ss-package-live-stimulus-trace.sh": (
            "operatorWindow.maxArmSeconds",
            "--dry-run|--describe",
            "--trace-log",
            "source_runbook=\"$2\"",
            "source_runbook=",
            "trace_log_override",
            "DUNE_UE4SS_PACKAGE_STIMULUS_PREFLIGHT_SUMMARY_JSON",
            "dune-ue4ss-package-live-preflight-summary/v1",
            "preflight_summary_ready=",
            '"sourceRunbook"',
            '"traceLogOverride"',
            "coordinator_dry_run=",
            "preflight_command=",
            "wait_seconds > max_arm_seconds",
            "trap cleanup EXIT",
            "operator_instruction=perform client login/travel/map-entry",
            '"$repo_root/scripts/ue4ss-package-remote-trace.sh" preflight',
            '"$repo_root/scripts/ue4ss-package-remote-trace.sh" arm',
            '"$repo_root/scripts/ue4ss-package-remote-trace.sh" status',
            "print_review_verification_summary",
            "review_bundle_ready=",
            "review_bundle_blocker=",
            "review_bundle_summary_json=",
            "local_review_summary_verification_command=",
            "local_review_summary_verification=begin",
            "local_review_summary_ready=",
            "local_review_summary_blocker=",
            "DUNE_UE4SS_PACKAGE_STIMULUS_REVIEW_SUMMARY_JSON",
            "print_route_slot_trace_requirement",
            "route_slot_expected_trace_marker",
            "route_slot_route_address",
            "route_slot_review_field",
            "route_slot_required_slots",
            "route_slot_missing_slots",
            "route_slot_required_registers",
            "route_slot_missing_registers",
            '"operatorWindowSeconds"',
            '"runStartedUtc"',
            '"statusFinishedUtc"',
            '"sourceRunbook"',
            '"traceLogOverride"',
            "operator_stimulus_window_started_utc=",
            "operator_stimulus_window_finished_utc=",
            '"traceRemote"',
            '"traceLog"',
            "noDebuggerCheckCommand",
        ),
        "scripts/plan-ue4ss-package-stimulus-trace.py": (
            'DEFAULT_ANCHORS = "LoadPackage,LoadObject"',
            'DEFAULT_TRACE_LOG_PREFIX = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry"',
            "DEFAULT_OPERATOR_ARM_WINDOW_SECONDS = 120",
            '"operatorWindow"',
            '"no-debugger-check"',
            '"noDebuggerCheckCommand"',
            "docker top",
            '"traceLogUniqueness"',
            '"utc-timestamp-default"',
            '"cleanupCommand"',
            '"coordinatorCommand"',
            '"coordinatorDryRunCommand"',
            '"coordinatorFreshPreflightCommand"',
            '"coordinatorFreshTraceCommand"',
            "$(date -u +%Y%m%dT%H%M%SZ)",
            '"localReviewSummaryJson"',
            '"localReviewSummarySchemaVersion"',
            '"localReviewSummaryRunbookMode"',
            '"localReviewSummaryVerificationCommand"',
            '"routeSlotTraceRequirement"',
            "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "routeVtableStaticSlotMatches",
            "0x3a0",
            "0x3d8",
            "rbx",
            "r14",
            "--dry-run --wait 30",
            "run cleanupCommand",
            "## Coordinator",
            "## Route Slot Trace Requirement",
            "## Cleanup",
        ),
        "scripts/plan-ue4ss-package-live-call-frame-recovery.py": (
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject",
        ),
        "scripts/plan-ue4ss-package-server-replay.py": (
            "client-originated-pending-server-replay",
            "requiresServerSideReplay",
            "readyForNonInvokingCanary",
            "readyForNativeInvoke",
            "DUNE_LINUX_SERVER_CANARY_EXTRA_ENV",
            "server-side-client-call-emulation",
        ),
        "scripts/plan-ue4ss-package-next-action.py": (
            '"cleanupCommand": runbook.get("cleanupCommand", "")',
            '"coordinatorCommand": runbook.get("coordinatorCommand", "")',
            '"coordinatorDryRunCommand": runbook.get("coordinatorDryRunCommand", "")',
            '"coordinatorFreshPreflightCommand": runbook.get("coordinatorFreshPreflightCommand", "")',
            '"coordinatorFreshTraceCommand": runbook.get("coordinatorFreshTraceCommand", "")',
            '"routeSlotTraceRequirement": route_slot_trace_requirement',
            '"localReviewSummaryJson": review_artifacts.get("localReviewSummaryJson", "")',
            '"localReviewSummarySchemaVersion": review_artifacts.get("localReviewSummarySchemaVersion", "")',
            '"localReviewSummaryRunbookMode": review_artifacts.get("localReviewSummaryRunbookMode", "")',
            '"localReviewSummaryVerificationCommand": review_artifacts.get("localReviewSummaryVerificationCommand", "")',
            '"prearmReadinessReady": prearm_readiness.get("ready")',
            '"prearmReadinessNextStep": prearm_readiness.get("nextStep", "")',
            '"completionAuditNextClientGateClassification": prearm_readiness.get(',
            '"completionAuditNextRuntimeRootRecoveryPlan": prearm_readiness.get(',
            "Completion audit origin classification",
            "Completion audit runtime-root recovery",
            "server-side-client-call-emulation",
            '"operatorWindow": operator_window',
            '"noDebuggerCheckCommand": runbook.get("noDebuggerCheckCommand", "")',
            "max arm seconds",
            "cleanup:",
        ),
        "scripts/verify-ue4ss-package-review-bundle.py": (
            "LIVE_TRACE_RUNBOOK_OPERATOR_SEQUENCE",
            "LIVE_TRACE_RUNBOOK_NO_DEBUGGER_NEEDLE",
            "noDebuggerCheckCommand must be a non-empty single-line string",
            "operatorWindow sequence must preserve bounded cleanup handoff",
            '"noDebuggerCheckCommand": no_debugger_check',
            '"operatorWindow": operator_window',
            '"localReviewSummaryJson"',
            '"localReviewSummarySchemaVersion"',
            '"localReviewSummaryRunbookMode"',
            '"localReviewSummaryVerificationCommand"',
            "routeSlotTraceRequirement",
            "routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "liveTraceRunbook routeSlotTraceRequirement does not match bundled stimulus trace runbook",
            "routeSlotRecovery requiredSlots do not match bundled routeSlotTraceRequirement",
            "verify_trace_plan_supports_route_slot_requirement",
            "requestedRouteAddresses does not include bundled routeSlotTraceRequirement routeAddress",
            "routeGdb is missing required object capture",
            "routeGdb is missing required vtable capture",
            "f\"liveTraceRunbook {key} does not match bundled stimulus trace runbook\"",
        ),
        "scripts/verify-ue4ss-package-route-slot-recovery.py": (
            "dune-ue4ss-package-route-slot-recovery-verification/v1",
            "routeVtableStaticSlotMatches",
            "nextTraceRequirement",
            "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "expectedReviewField",
            "missingSlots",
            "missingRegisters",
            "liveTraceRunbook.routeSlotTraceRequirement requiredSlots do not match required route trace",
        ),
        "scripts/verify-ue4ss-package-live-stimulus-summary.py": (
            "SUMMARY_SCHEMA_VERSION",
            "EMBEDDED_EVIDENCE_FIELDS",
            "traceLogOverride",
            "sourceRunbook",
            "localReviewSummarySchemaVersion",
            "localReviewSummaryEmbeddedEvidenceFields",
            "localReviewSummaryRunbookMode",
            "summary embedded reviewBundleVerification does not match readable review bundle verification",
            "summary missing reviewBundleVerification required by next-action",
            "summary missing reviewBundleVerificationSha256 required by next-action",
            "summary missing prearmReadinessVerification required by next-action",
            "summary missing prearmReadinessVerificationSha256 required by next-action",
            "next-action localReviewSummaryEmbeddedEvidenceFields has unexpected value",
            "next-action localReviewSummaryRunbookMode has unexpected value",
            "summary traceLogOverride must match traceLog when an override was used",
            "summary schemaVersion does not match next-action localReviewSummarySchemaVersion",
            "routeSlotRecoveryNextTraceRequirement",
            "ORIGIN_REACHABILITY_CLASSIFICATION_STATUSES",
            "summary missing originClassification required by stimulus runbook",
            "summary originClassification requires server-side replay when client-originated",
            "summary routeSlotRecoveryNextTraceRequirement does not match embedded routeSlotRecoveryVerification",
            "summary non-ready routeSlotRecoveryVerification requires matching routeSlotRecoveryNextTraceRequirement",
            "summary routeSlotRecoveryNextTraceRequirement must be empty when embedded routeSlotRecoveryVerification has no nextTraceRequirement",
        ),
        "scripts/verify-ue4ss-package-live-preflight-summary.py": (
            "dune-ue4ss-package-live-preflight-summary-verification/v1",
            "dune-ue4ss-package-live-preflight-summary/v1",
            "summary fields.preflight must be ok",
            "summary player_guard_preflight_connected_players must be 0",
            "summary fields.trace_log does not match traceLog",
            "summary createdUtc is stale",
            "--max-age-seconds",
            "summary sourceRunbook does not match stimulus runbook path",
            "summary traceRemote does not match next-action liveTraceRunbook remote",
        ),
        "scripts/verify-ue4ss-package-prearm-readiness.py": (
            "dune-ue4ss-package-prearm-readiness/v1",
            "verify-ue4ss-package-live-preflight-summary.py",
            "TRACE_PLAN_SCHEMA_VERSION",
            "REQUIRED_ROUTE_CAPTURE_REGISTERS",
            "REQUIRED_ROUTE_CAPTURE_STACK_LABELS",
            "trace plan routeGdb is missing expanded register route capture",
            "trace plan routeGdb is missing expanded stack route capture",
            "freshPreflightCommand",
            "Fresh Preflight Command",
            "FRESH_TRACE_LOG_PATTERN",
            "command must use timestamped /tmp package trace log",
            "validate_route_slot_trace_requirement",
            "runbook routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "next-action liveTraceRunbook.routeSlotTraceRequirement does not match runbook",
            "audit_has_route_slot_blocker",
            "completion audit route-slot blocker must include nextRouteSlotTraceRequirement",
            "completionAuditNextRouteSlotTraceRequirement",
            "Completion Audit Route Slot Trace Requirement",
            "completionAuditNextClientGateClassification",
            "Completion Audit Origin/Reachability Classification",
            "server-side-client-call-emulation",
            "completionAuditNextRuntimeRootRecoveryPlan",
            "Completion Audit Runtime Root Recovery",
            "Runtime Root Canary",
            "operator must refresh the live preflight with coordinatorFreshPreflightCommand before arming the live package trace",
            "operator may run coordinatorFreshTraceCommand",
        ),
        "scripts/audit-ue4ss-linux-port-completion.py": (
            "dune-ue4ss-linux-port-completion-audit/v1",
            "package-verification",
            "portability-contract",
            "port-gap-summary",
            "package-next-action",
            "live-preflight-summary",
            "preflight_max_age_seconds",
            "live-stimulus-summary",
            "import_preflight_summary_verifier",
            "nextLivePreflightCommand",
            "next_live_preflight_command_from_action",
            "coordinatorFreshPreflightCommand",
            "next-action coordinatorFreshPreflightCommand must use --preflight-only",
            "run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log",
            "Next Live Preflight Command",
            "next_live_command_from_action",
            "coordinatorFreshTraceCommand",
            "next-action coordinatorFreshTraceCommand must use --trace-log",
            "validate_route_slot_trace_requirement",
            "stimulus-runbook",
            "runbook routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "next-action liveTraceRunbook.routeSlotTraceRequirement does not match runbook",
            "live_report = live_verifier.report",
            "nextRouteSlotTraceRequirement",
            "routeSlotRecoveryNextTraceRequirement",
            "route_slot_next_requirement",
            "has_route_slot_blocker",
            "route-slot recovery next trace requirement is missing",
            "Next Route Slot Trace Requirement",
            "expectedTraceMarker",
            "missingSlots",
            "missingRegisters",
            "nextOriginClassification",
            "Next Origin/Reachability Classification",
            "server-side-client-call-emulation",
            "replay/spoof the equivalent call server-side",
            "nextRuntimeRootRecoveryPlan",
            "validate_runtime_root_recovery_plan",
            "Next Runtime Root Recovery",
            "Runtime Root Preflight",
            "Runtime Root Canary",
            "runtime root recovery requiredLogPath must be /tmp/dune-server-probe-loader.log",
            "runtime root recovery run command must enable strict verification",
            "runtime root recovery guards must mention kspls0",
            "nextRuntimeRootRecoveryPlan",
            "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true",
            "blockers.extend",
            "run-ue4ss-package-live-stimulus-trace.sh --trace-log",
        ),
        "scripts/summarize-ue4ss-port-gaps.py": (
            '"cleanupCommand"',
            "Package live trace runbook",
            "LIVE_TRACE_RUNBOOK_REQUIRED_CLEANUP_ANCHOR",
            "LIVE_TRACE_RUNBOOK_TRACE_LOG_PREFIX",
            "LIVE_TRACE_RUNBOOK_OPERATOR_SEQUENCE",
            "liveTraceRunbook.operatorWindow.sequence",
            "liveTraceRunbook.noDebuggerCheckCommand",
            "liveTraceRunbook.coordinatorCommand",
            "liveTraceRunbook.coordinatorDryRunCommand",
            "liveTraceRunbook.coordinatorFreshPreflightCommand",
            "liveTraceRunbook.coordinatorFreshTraceCommand",
            "liveTraceRunbook.cleanupCommand must include",
            "liveTraceRunbook.traceLog must use timestamped",
            "validate_route_slot_trace_requirement",
            "liveTraceRunbook.routeSlotTraceRequirement",
            "routeSlotTraceRequirement",
            "package route-slot proof must capture",
            "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "routeVtableStaticSlotMatches",
        ),
    },
}


def run_command(argv):
    return subprocess.run(
        [str(arg) for arg in argv],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def command_text(argv, missing_ok=False):
    result = run_command(argv)
    if result.returncode != 0:
        if missing_ok:
            return None, result.stdout + result.stderr
        raise RuntimeError(f"{' '.join(str(arg) for arg in argv)} failed:\n{result.stdout}{result.stderr}")
    return result.stdout, ""


def require_contains(text, needle, missing):
    if needle not in text:
        missing.append(needle)


def resolve_path(config):
    if "path" in config:
        return Path(config["path"])
    for path in config.get("paths", ()):
        candidate = Path(path)
        if candidate.is_file():
            return candidate
    paths = list(config.get("paths", ()))
    return Path(paths[0]) if paths else Path("")


def verify_elf(target, config):
    path = resolve_path(config)
    missing = []
    details = {"path": str(path), "kind": "elf"}
    if not path.is_file():
        return {"target": target, "passed": False, "missing": [f"file:{path}"], "details": details}

    file_text, _ = command_text(["file", path])
    header_text, _ = command_text(["readelf", "-h", path])
    dynamic_text, _ = command_text(["readelf", "-d", path])

    require_contains(file_text, "ELF 64-bit LSB shared object", missing)
    require_contains(file_text, "x86-64", missing)
    require_contains(header_text, "Type:                              DYN (Shared object file)", missing)
    require_contains(header_text, "Machine:                           Advanced Micro Devices X86-64", missing)
    require_contains(dynamic_text, f"Library soname: [{config['soname']}]", missing)
    require_contains(dynamic_text, "Shared library: [libc.so.6]", missing)

    details.update(
        {
            "file": file_text.strip(),
            "soname": config["soname"],
        }
    )
    return {"target": target, "passed": not missing, "missing": missing, "details": details}


def objdump_output(path):
    for command in ("x86_64-w64-mingw32-objdump", "llvm-objdump", "objdump"):
        result = run_command([command, "-x", path])
        if result.returncode == 0:
            return result.stdout, command
    raise RuntimeError(f"no objdump variant could inspect {path}")


def verify_pe(target, config):
    path = resolve_path(config)
    missing = []
    details = {"path": str(path), "kind": "pe"}
    if not path.is_file():
        return {"target": target, "passed": False, "missing": [f"file:{path}"], "details": details}

    file_text, _ = command_text(["file", path])
    objdump_text, objdump_command = objdump_output(path)

    require_contains(file_text, "PE32+ executable", missing)
    require_contains(file_text, "x86-64", missing)
    require_contains(file_text, "(DLL)", missing)
    require_contains(objdump_text, "DLL Name: KERNEL32.dll", missing)
    require_contains(objdump_text, "Subsystem", missing)
    require_contains(objdump_text, "(Windows GUI)", missing)
    require_contains(objdump_text, "Export Tables", missing)
    for export in config["exports"]:
        require_contains(objdump_text, export, missing)

    details.update(
        {
            "file": file_text.strip(),
            "objdump": objdump_command,
            "requiredExports": list(config["exports"]),
        }
    )
    return {"target": target, "passed": not missing, "missing": missing, "details": details}


def verify_target(target):
    config = TARGETS[target]
    if config["kind"] == "elf":
        return verify_elf(target, config)
    if config["kind"] == "pe":
        return verify_pe(target, config)
    raise ValueError(f"unknown target kind: {config['kind']}")


def verify_package_root(target, package_root):
    root = Path(package_root)
    required = PACKAGE_LAYOUTS[target]
    missing = [relative for relative in required if not (root / relative).is_file()]
    for relative in PACKAGE_EXECUTABLES[target]:
        path = root / relative
        if path.is_file():
            if not (path.stat().st_mode & 0o111):
                missing.append(f"{relative}:not-executable")
            try:
                first_two = path.read_bytes()[:2]
            except OSError:
                missing.append(f"{relative}:unreadable")
            else:
                if first_two != b"#!":
                    missing.append(f"{relative}:missing-shebang")
            if relative.endswith(".sh"):
                result = run_command(["bash", "-n", path])
                if result.returncode != 0:
                    missing.append(f"{relative}:shell-syntax")
    for relative, markers in PACKAGE_DOC_MARKERS[target].items():
        path = root / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            missing.append(f"{relative}:unreadable")
            continue
        if len(text.encode("utf-8")) < PACKAGE_DOC_MIN_BYTES:
            missing.append(f"{relative}:too-small")
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative}:missing-marker:{marker}")
    for relative, markers in PACKAGE_FILE_MARKERS.get(target, {}).items():
        path = root / relative
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            missing.append(f"{relative}:unreadable")
            continue
        for marker in markers:
            if marker not in text:
                missing.append(f"{relative}:missing-marker:{marker}")
    checksum_path = root / "SHA256SUMS"
    checksum_rows = {}
    if not checksum_path.is_file():
        missing.append("SHA256SUMS")
    else:
        try:
            checksum_text = checksum_path.read_text(encoding="utf-8")
        except OSError:
            missing.append("SHA256SUMS:unreadable")
        else:
            for line_number, line in enumerate(checksum_text.splitlines(), start=1):
                if not line.strip():
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) != 2 or len(parts[0]) != 64:
                    missing.append(f"SHA256SUMS:{line_number}:malformed")
                    continue
                if any(char not in "0123456789abcdefABCDEF" for char in parts[0]):
                    missing.append(f"SHA256SUMS:{line_number}:malformed")
                    continue
                relative = parts[1].lstrip("*")
                relative_path = Path(relative)
                if relative_path.is_absolute() or relative.startswith("../") or "/../" in relative or relative.startswith("./"):
                    missing.append(f"SHA256SUMS:{line_number}:unsafe-path")
                    continue
                if relative in checksum_rows:
                    missing.append(f"SHA256SUMS:{line_number}:duplicate")
                    continue
                checksum_rows[relative] = parts[0].lower()
            for relative in required:
                path = root / relative
                if not path.is_file():
                    continue
                expected = checksum_rows.get(relative)
                if not expected:
                    missing.append(f"SHA256SUMS:{relative}:missing")
                    continue
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != expected:
                    missing.append(f"SHA256SUMS:{relative}:mismatch")
    contract_path = root / "docs" / "ue4ss-portability-contract.json"
    contract = None
    if contract_path.is_file():
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            missing.append("docs/ue4ss-portability-contract.json:invalid-json")
        else:
            if not isinstance(contract, dict):
                missing.append("docs/ue4ss-portability-contract.json:not-object")
            else:
                if contract.get("schemaVersion") != "dune-ue4ss-portability-contract/v1":
                    missing.append("docs/ue4ss-portability-contract.json:schemaVersion")
                if contract.get("passed") is not True:
                    missing.append("docs/ue4ss-portability-contract.json:passed")
    contract_md_path = root / "docs" / "ue4ss-portability-contract.md"
    if contract_md_path.is_file():
        try:
            contract_md = contract_md_path.read_text(encoding="utf-8")
        except OSError:
            missing.append("docs/ue4ss-portability-contract.md:unreadable")
        else:
            if "# UE4SS Portability Contract" not in contract_md:
                missing.append("docs/ue4ss-portability-contract.md:heading")
            if "- Passed: `true`" not in contract_md:
                missing.append("docs/ue4ss-portability-contract.md:passed")
    return {
        "target": target,
        "passed": not missing,
        "missing": missing,
        "details": {
            "path": str(root),
            "kind": "package-root",
            "required": list(required),
            "checksumPath": str(checksum_path),
            "portabilityContractPath": str(contract_path),
            "portabilityContractMarkdownPath": str(contract_md_path),
        },
    }


def parse_single_sha256_file(path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "", "unreadable"
    rows = [line for line in text.splitlines() if line.strip()]
    if len(rows) != 1:
        return "", "row-count"
    parts = rows[0].split(maxsplit=1)
    if len(parts) < 1 or len(parts[0]) != 64:
        return "", "malformed"
    digest = parts[0].strip().lower()
    if any(char not in "0123456789abcdef" for char in digest):
        return "", "malformed"
    return digest, ""


def verify_package_archive(archive_path, checksum_path=None):
    archive_path = Path(archive_path)
    checksum_path = Path(checksum_path) if checksum_path else Path(str(archive_path) + ".sha256")
    missing = []
    expected = ""
    if not archive_path.is_file():
        missing.append("packageArchive:missing")
    if not checksum_path.is_file():
        missing.append("packageArchiveSha256:missing")
    else:
        expected, error = parse_single_sha256_file(checksum_path)
        if error:
            missing.append(f"packageArchiveSha256:{error}")
    if archive_path.is_file() and expected:
        actual = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        if actual != expected:
            missing.append("packageArchiveSha256:mismatch")
    return {
        "passed": not missing,
        "missing": missing,
        "details": {
            "path": str(archive_path),
            "kind": "package-archive",
            "checksumPath": str(checksum_path),
        },
    }


def target_has_existing_artifact(target):
    return resolve_path(TARGETS[target]).is_file()


def default_targets():
    existing = [target for target in TARGETS if target_has_existing_artifact(target)]
    return existing or list(TARGETS)


def render_text(report):
    lines = [f"loader_artifacts_ok={str(report['passed']).lower()}"]
    for target, row in report["targets"].items():
        lines.append(
            f"{target} passed={str(row['passed']).lower()} "
            f"path={row['details'].get('path', '')} "
            f"missing={','.join(row.get('missing', [])) or 'none'}"
        )
    for target, row in report.get("packages", {}).items():
        lines.append(
            f"{target} package_passed={str(row['passed']).lower()} "
            f"path={row['details'].get('path', '')} "
            f"missing={','.join(row.get('missing', [])) or 'none'}"
        )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify built Dune UE4SS-style loader artifacts.")
    parser.add_argument(
        "--target",
        action="append",
        choices=tuple(TARGETS) + ("all",),
        default=[],
        help="Artifact target to verify. Defaults to all.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--package-root", type=Path, help="staged package root to verify for portability tooling")
    parser.add_argument("--package-archive", type=Path, help="packaged tarball to verify against its sha256 sidecar")
    parser.add_argument(
        "--package-archive-sha256",
        type=Path,
        help="sha256 sidecar for --package-archive; defaults to <archive>.sha256",
    )
    parser.add_argument(
        "--package-only",
        action="store_true",
        help="with --package-root, skip built binary inspection and verify only the staged package layout",
    )
    parser.add_argument(
        "--package-target",
        choices=tuple(TARGETS),
        help="target layout to use with --package-root; defaults to the single selected target",
    )
    args = parser.parse_args(argv)

    if args.package_only and not args.package_root:
        parser.error("--package-only requires --package-root")
    if args.package_archive_sha256 and not args.package_archive:
        parser.error("--package-archive-sha256 requires --package-archive")

    selected = args.target or default_targets()
    if "all" in selected:
        selected = list(TARGETS)

    targets = {} if args.package_only else {target: verify_target(target) for target in selected}
    packages = {}
    if args.package_root:
        package_target = args.package_target
        if not package_target:
            if len(selected) != 1:
                parser.error("--package-target is required when --package-root is used with zero or multiple selected targets")
            package_target = selected[0]
        packages[package_target] = verify_package_root(package_target, args.package_root)
        if args.package_archive:
            packages[f"{package_target}-archive"] = verify_package_archive(
                args.package_archive,
                args.package_archive_sha256,
            )
    report = {
        "schemaVersion": "dune-loader-artifact-verification/v1",
        "passed": all(row["passed"] for row in targets.values()) and all(row["passed"] for row in packages.values()),
        "targets": targets,
    }
    if packages:
        report["packages"] = packages

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_text(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
