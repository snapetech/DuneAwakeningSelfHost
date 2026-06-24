#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import os
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit-ue4ss-linux-port-completion.py"
LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS = (
    "reviewBundleVerification,reviewBundleVerificationSha256,"
    "routeSlotRecoveryVerification,routeSlotRecoveryVerificationSha256,"
    "prearmReadinessVerification,prearmReadinessVerificationSha256"
)


def load_module():
    spec = importlib.util.spec_from_file_location("audit_ue4ss_linux_port_completion", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_sha256(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def args(root):
    return Namespace(
        package_verification=root / "package-verification.json",
        portability_check=root / "portability.json",
        port_gaps=root / "port-gaps.json",
        next_action=root / "next-action.json",
        runbook=root / "runbook.json",
        preflight_summary=root / "preflight-summary.json",
        preflight_max_age_seconds=3600,
        prearm_readiness=root / "prearm-readiness.json",
        live_summary=root / "live-summary.json",
    )


def write_base_inputs(root, ready=False):
    write_json(root / "package-verification.json", {"schemaVersion": "dune-loader-artifact-verification/v1", "passed": True})
    write_json(root / "portability.json", {"schemaVersion": "dune-ue4ss-portability-contract/v1", "passed": True})
    write_json(root / "port-gaps.json", {"schemaVersion": "dune-ue4ss-port-gap-summary/v1", "ready": ready})
    write_json(
        root / "runbook.json",
        {
            "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
            "sourcePath": str(root / "runbook.json"),
            "remote": "kspls0",
            "container": "dune_server-deep-desert-1",
            "traceLog": "/tmp/trace.log",
            "operatorWindow": {"maxArmSeconds": 120, "cleanupRequired": True},
            "traceInputs": {"routeAddress": "0x129d58a2"},
            "traceEnv": {"DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS": "0x129d58a2"},
            "originClassification": {
                "status": "unknown",
                "probeCandidate": "operator-client-map-entry",
                "serverSideFallbackCandidate": "server-side-client-call-emulation",
                "decision": (
                    "trace first; if package-load evidence only appears from the client-originated "
                    "action, recover and replay/spoof the equivalent call server-side"
                ),
            },
            "routeSlotTraceRequirement": {
                "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                "routeAddress": "0x129d58a2",
                "reviewField": "routeVtableStaticSlotMatches",
                "requiredSlots": ["0x3a0", "0x3d8"],
                "requiredRegisters": ["rbx", "r14"],
            },
            "cleanupCommand": "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2 scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/trace.log",
        },
    )
    write_json(
        root / "next-action.json",
        {
            "schemaVersion": "dune-ue4ss-package-next-action/v1",
            "action": "complete" if ready else "recover-package-anchor",
            "reason": "" if ready else "review bundle integrity is usable but the runtime trace captured no package hit",
            "nextStep": "" if ready else "run the live trace coordinator during the approved client login/travel/map-entry package-load stimulus",
            "liveTraceRunbook": {
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "traceLog": "/tmp/trace.log",
                "coordinatorFreshTraceCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                "localReviewSummaryJson": str(root / "live-summary.json"),
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                "localReviewSummaryEmbeddedEvidenceFields": LOCAL_REVIEW_SUMMARY_EMBEDDED_EVIDENCE_FIELDS,
                "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "routeSlotTraceRequirement": {
                    "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                    "routeAddress": "0x129d58a2",
                    "reviewField": "routeVtableStaticSlotMatches",
                    "requiredSlots": ["0x3a0", "0x3d8"],
                    "requiredRegisters": ["rbx", "r14"],
                },
            },
            "routeSlotRecovery": {
                "requiredRouteTrace": {
                    "address": "0x129d58a2",
                    "slots": ["0x3a0", "0x3d8"],
                    "registers": ["rbx", "r14"],
                    "reviewField": "routeVtableStaticSlotMatches",
                },
            },
        },
    )


def write_ready_live_summary(root):
    verifier = {
        "schemaVersion": "dune-ue4ss-package-review-bundle-verification/v1",
        "ready": True,
        "bundle": "/tmp/review-bundles/ready",
        "blockers": [],
        "artifactCount": 14,
        "checksumCount": 15,
    }
    route_slot_verifier = {
        "schemaVersion": "dune-ue4ss-package-route-slot-recovery-verification/v1",
        "ready": True,
        "blockers": [],
        "routeAddress": "0x129d58a2",
        "requiredSlots": ["0x3a0", "0x3d8"],
    }
    prearm_verifier = {
        "schemaVersion": "dune-ue4ss-package-prearm-readiness/v1",
        "ready": True,
        "blockers": [],
        "tracePlan": {"expandedRouteCaptureReady": True},
    }
    write_json(
        root / "live-summary.json",
        {
            "schemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
            "runbook": str(root / "runbook.json"),
            "sourceRunbook": str(root / "runbook.json"),
            "traceLogOverride": "",
            "traceRemote": "kspls0",
            "container": "dune_server-deep-desert-1",
            "traceLog": "/tmp/trace.log",
            "operatorWindowSeconds": 30,
            "runStartedUtc": "2026-06-23T22:00:00Z",
            "statusFinishedUtc": "2026-06-23T22:00:30Z",
            "bundle": "/tmp/review-bundles/ready",
            "verifyJson": "/tmp/remote-review-verification.json",
            "ready": True,
            "blockers": [],
            "artifactCount": 14,
            "checksumCount": 15,
            "reviewBundleVerification": verifier,
            "reviewBundleVerificationSha256": json_sha256(verifier),
            "routeSlotRecoveryVerification": route_slot_verifier,
            "routeSlotRecoveryVerificationSha256": json_sha256(route_slot_verifier),
            "prearmReadinessJson": str(root / "prearm-readiness.json"),
            "prearmReadinessVerification": prearm_verifier,
            "prearmReadinessVerificationSha256": json_sha256(prearm_verifier),
            "originClassification": {
                "status": "missing",
                "source": "local-review-summary",
                "probeCandidate": "operator-client-map-entry",
                "serverSideFallbackCandidate": "server-side-client-call-emulation",
                "requiresServerSideReplay": False,
                "decision": (
                    "trace first; if package-load evidence only appears from the client-originated "
                    "action, recover and replay/spoof the equivalent call server-side"
                ),
                "blockers": ["selected runtime trace hit is missing"],
            },
        },
    )


def write_ready_preflight_summary(root):
    write_json(
        root / "preflight-summary.json",
        {
            "schemaVersion": "dune-ue4ss-package-live-preflight-summary/v1",
            "createdUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runbook": str(root / "runbook.json"),
            "sourceRunbook": str(root / "runbook.json"),
            "traceLogOverride": "",
            "traceRemote": "kspls0",
            "container": "dune_server-deep-desert-1",
            "traceLog": "/tmp/trace.log",
            "operatorWindowSeconds": 30,
            "ready": True,
            "blockers": [],
            "fields": {
                "remote_host": "kspls0",
                "player_guard_preflight_partition": "8",
                "player_guard_preflight_connected_players": "0",
                "preflight": "ok",
                "container": "dune_server-deep-desert-1",
                "server_pid": "2477302",
                "trace_log": "/tmp/trace.log",
                "route_address": "0x129d58a2",
            },
        },
    )


def write_ready_prearm_readiness(root):
    write_json(
        root / "prearm-readiness.json",
        {
            "schemaVersion": "dune-ue4ss-package-prearm-readiness/v1",
            "ready": True,
            "preflightReady": True,
            "auditReady": False,
            "routeAddress": "0x129d58a2",
            "freshTraceCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
            "blockers": [],
        },
    )


class AuditUe4ssLinuxPortCompletionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_audit_reports_current_style_live_summary_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_ready_prearm_readiness(root)
            data = self.module.audit(args(root))
            rendered = self.module.markdown(data)

        self.assertFalse(data["ready"])
        self.assertIn("live-preflight-summary: preflight summary JSON is missing", data["blockers"])
        self.assertIn("live-stimulus-summary: summary JSON is missing", data["blockers"])
        self.assertIn("package-next-action: package next-action is not complete", "\n".join(data["blockers"]))
        self.assertIn("run-ue4ss-package-live-stimulus-trace.sh", rendered)
        self.assertIn("## Next Live Preflight Command", rendered)
        self.assertIn("--preflight-only --wait 30 --trace-log", rendered)
        self.assertIn("## Next Live Command", rendered)
        self.assertEqual(data["nextOriginClassification"]["status"], "pending")
        self.assertEqual(
            data["nextOriginClassification"]["serverSideFallbackCandidate"],
            "server-side-client-call-emulation",
        )
        self.assertIn("## Next Origin/Reachability Classification", rendered)
        self.assertIn("replay/spoof", rendered)

    def test_audit_passes_through_port_gap_blocker_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_json(
                root / "port-gaps.json",
                {
                    "schemaVersion": "dune-ue4ss-port-gap-summary/v1",
                    "ready": False,
                    "blockers": ["package-loading missing ready keys: luaLoadClassPackageNativeInvocation"],
                },
            )
            write_ready_prearm_readiness(root)
            data = self.module.audit(args(root))

        self.assertIn("port-gap-summary: port gap summary is not ready", data["blockers"])
        self.assertIn(
            "port-gap-summary: port gap: package-loading missing ready keys: luaLoadClassPackageNativeInvocation",
            data["blockers"],
        )

    def test_audit_surfaces_runtime_root_recovery_canary_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_json(
                root / "port-gaps.json",
                {
                    "schemaVersion": "dune-ue4ss-port-gap-summary/v1",
                    "ready": False,
                    "blockers": ["runtime-anchors missing ready keys: runtimeRootDiscovery"],
                    "runtimeRootRecoveryPlan": {
                        "needed": True,
                        "action": "recover-runtime-roots",
                        "confidence": "high",
                        "reason": "current readiness has no target-image runtime root discovery proof",
                        "missingKeys": ["runtimeRootDiscovery", "runtimeRootValidation"],
                        "blockedByMissingLog": True,
                        "requiredLogPath": "/tmp/dune-server-probe-loader.log",
                        "outputFiles": {
                            "nextCanaryJson": "build/server-current-anchor-prep/ue4ss-runtime-root-recovery-next-canary.json"
                        },
                        "canaryWrapper": {
                            "preflightCommand": (
                                "DUNE_LINUX_SERVER_CANARY_LOG_PATH=/tmp/dune-server-probe-loader.log "
                                "DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=true "
                                "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true scripts/canary-linux-server-loader.sh .env"
                            ),
                            "runCommand": (
                                "DUNE_LINUX_SERVER_CANARY_LOG_PATH=/tmp/dune-server-probe-loader.log "
                                "DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=false "
                                "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true scripts/canary-linux-server-loader.sh .env"
                            ),
                            "guards": [
                                "must run on kspls0 unless overridden",
                                "requires zero connected players unless explicitly allowed",
                                "restores DUNE_ENABLE_LINUX_SERVER_PRELOAD during cleanup",
                            ],
                        },
                        "postCanaryVerificationOutputs": {"readinessJson": "ue4ss-readiness.json"},
                    },
                },
            )
            write_ready_prearm_readiness(root)

            data = self.module.audit(args(root))
            rendered = self.module.markdown(data)

        plan = data["nextRuntimeRootRecoveryPlan"]
        self.assertTrue(plan["needed"])
        self.assertEqual(plan["requiredLogPath"], "/tmp/dune-server-probe-loader.log")
        self.assertTrue(plan["blockedByMissingLog"])
        self.assertIn("runtimeRootDiscovery", plan["missingKeys"])
        self.assertIn("scripts/canary-linux-server-loader.sh", plan["preflightCommand"])
        self.assertIn("scripts/canary-linux-server-loader.sh", plan["runCommand"])
        self.assertIn("## Next Runtime Root Recovery", rendered)
        self.assertIn("### Runtime Root Preflight", rendered)
        self.assertIn("### Runtime Root Canary", rendered)

    def test_audit_rejects_stale_runtime_root_recovery_canary_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_json(
                root / "port-gaps.json",
                {
                    "schemaVersion": "dune-ue4ss-port-gap-summary/v1",
                    "ready": False,
                    "blockers": ["runtime-anchors missing ready keys: runtimeRootDiscovery"],
                    "runtimeRootRecoveryPlan": {
                        "needed": True,
                        "action": "recover-runtime-roots",
                        "missingKeys": ["unrelatedRuntimeKey"],
                        "blockedByMissingLog": True,
                        "requiredLogPath": "/tmp/wrong.log",
                        "canaryWrapper": {
                            "preflightCommand": "scripts/canary-linux-server-loader.sh .env",
                            "runCommand": "DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=true scripts/canary-linux-server-loader.sh .env",
                            "guards": ["must run somewhere"],
                        },
                        "postCanaryVerificationOutputs": {},
                    },
                },
            )
            write_ready_prearm_readiness(root)

            data = self.module.audit(args(root))

        self.assertFalse(data["ready"])
        self.assertIn(
            "port-gap-summary: runtime root recovery requiredLogPath must be /tmp/dune-server-probe-loader.log",
            data["blockers"],
        )
        self.assertIn(
            "port-gap-summary: runtime root recovery missingKeys must include a runtime anchor recovery key",
            data["blockers"],
        )
        self.assertIn(
            "port-gap-summary: runtime root recovery run command has wrong DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY value",
            data["blockers"],
        )
        self.assertIn(
            "port-gap-summary: runtime root recovery run command must enable strict verification",
            data["blockers"],
        )
        self.assertIn(
            "port-gap-summary: runtime root recovery guards must mention kspls0",
            data["blockers"],
        )

    def test_audit_passes_when_all_completion_evidence_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=True)
            write_ready_preflight_summary(root)
            write_ready_live_summary(root)
            data = self.module.audit(args(root))

        self.assertTrue(data["ready"], data["blockers"])
        self.assertEqual(data["blockers"], [])
        self.assertTrue(all(item["ready"] for item in data["gates"]))
        self.assertEqual(
            data["nextLiveCommand"],
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
        )
        self.assertEqual(data["nextOriginClassification"]["status"], "missing")

    def test_audit_surfaces_route_slot_next_trace_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_ready_prearm_readiness(root)
            write_ready_preflight_summary(root)
            write_ready_live_summary(root)
            live_path = root / "live-summary.json"
            payload = json.loads(live_path.read_text(encoding="utf-8"))
            requirement = {
                "expectedReviewField": "routeVtableStaticSlotMatches",
                "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                "missingRegisters": ["r14", "rbx"],
                "missingSlots": ["0x3a0", "0x3d8"],
                "requiredRegisters": ["rbx", "r14"],
                "requiredSlots": ["0x3a0", "0x3d8"],
                "reviewField": "routeVtableStaticSlotMatches",
                "routeAddress": "0x129d58a2",
            }
            route_slot = payload["routeSlotRecoveryVerification"]
            route_slot["ready"] = False
            route_slot["blockers"] = ["route hits did not contain all required static vtable slot matches"]
            route_slot["nextTraceRequirement"] = requirement
            payload["ready"] = False
            payload["blockers"] = [
                "route-slot recovery: route hits did not contain all required static vtable slot matches"
            ]
            payload["routeSlotRecoveryVerification"] = route_slot
            payload["routeSlotRecoveryVerificationSha256"] = json_sha256(route_slot)
            payload["routeSlotRecoveryNextTraceRequirement"] = requirement
            write_json(live_path, payload)

            data = self.module.audit(args(root))
            rendered = self.module.markdown(data)

        self.assertEqual(data["nextRouteSlotTraceRequirement"], requirement)
        self.assertIn("## Next Route Slot Trace Requirement", rendered)
        self.assertIn("Missing slots: `0x3a0, 0x3d8`", rendered)

    def test_audit_blocks_route_slot_failure_without_next_trace_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_ready_prearm_readiness(root)
            write_ready_preflight_summary(root)
            write_ready_live_summary(root)
            live_path = root / "live-summary.json"
            payload = json.loads(live_path.read_text(encoding="utf-8"))
            route_slot = payload["routeSlotRecoveryVerification"]
            route_slot["ready"] = False
            route_slot["blockers"] = ["route hits did not contain all required static vtable slot matches"]
            payload["ready"] = False
            payload["blockers"] = [
                "route-slot recovery: route hits did not contain all required static vtable slot matches"
            ]
            payload["routeSlotRecoveryVerification"] = route_slot
            payload["routeSlotRecoveryVerificationSha256"] = json_sha256(route_slot)
            payload.pop("routeSlotRecoveryNextTraceRequirement", None)
            write_json(live_path, payload)

            data = self.module.audit(args(root))

        self.assertFalse(data["ready"])
        self.assertIn(
            "live-stimulus-summary: route-slot recovery next trace requirement is missing",
            data["blockers"],
        )

    def test_audit_blocks_mismatched_next_action_route_slot_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_ready_prearm_readiness(root)
            next_action_path = root / "next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["routeSlotTraceRequirement"]["requiredSlots"] = ["0x3a0"]
            write_json(next_action_path, payload)

            data = self.module.audit(args(root))

        self.assertFalse(data["ready"])
        self.assertIn(
            "stimulus-runbook: next-action liveTraceRunbook.routeSlotTraceRequirement does not match runbook",
            data["blockers"],
        )

    def test_audit_rejects_stale_next_action_live_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_ready_prearm_readiness(root)
            next_action_path = root / "next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["coordinatorFreshTraceCommand"] = "scripts/run-ue4ss-package-live-stimulus-trace.sh"
            write_json(next_action_path, payload)

            data = self.module.audit(args(root))

        self.assertFalse(data["ready"])
        self.assertIn(
            "package-next-action: next-action coordinatorFreshTraceCommand must use --trace-log",
            data["blockers"],
        )
        self.assertIn(
            "package-next-action: next-action coordinatorFreshTraceCommand must generate a timestamped trace log",
            data["blockers"],
        )

    def test_audit_rejects_stale_preflight_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_ready_prearm_readiness(root)
            write_ready_preflight_summary(root)
            preflight_path = root / "preflight-summary.json"
            payload = json.loads(preflight_path.read_text(encoding="utf-8"))
            payload["createdUtc"] = "2026-06-24T00:00:00Z"
            write_json(preflight_path, payload)
            opts = args(root)
            opts.preflight_max_age_seconds = 60

            data = self.module.audit(opts)

        self.assertFalse(data["ready"])
        self.assertTrue(
            any(blocker.startswith("live-preflight-summary: summary createdUtc is stale:") for blocker in data["blockers"]),
            data["blockers"],
        )
        self.assertEqual(
            data["nextLivePreflightCommand"],
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
        )

    def test_audit_requires_prearm_readiness_while_package_recovery_is_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)

            data = self.module.audit(args(root))

        self.assertFalse(data["ready"])
        self.assertIn("package-prearm-readiness: " + str(root / "prearm-readiness.json") + " is missing", data["blockers"])

    def test_audit_rejects_prearm_readiness_route_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_base_inputs(root, ready=False)
            write_ready_prearm_readiness(root)
            payload = json.loads((root / "prearm-readiness.json").read_text(encoding="utf-8"))
            payload["routeAddress"] = "0xdeadbeef"
            write_json(root / "prearm-readiness.json", payload)

            data = self.module.audit(args(root))

        self.assertFalse(data["ready"])
        self.assertIn(
            "package-prearm-readiness: prearm readiness routeAddress does not match required route trace address",
            data["blockers"],
        )

    def test_latest_package_verification_uses_newest_archive_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_path = root / "old.tar.gz.verification.json"
            new_path = root / "new.tar.gz.verification.json"
            write_json(old_path, {"passed": True})
            write_json(new_path, {"passed": True})
            os.utime(old_path, (100, 100))
            os.utime(new_path, (200, 200))

            selected = self.module.latest_package_verification(root)

        self.assertEqual(selected.name, "new.tar.gz.verification.json")

    def test_cli_default_package_verification_discovers_current_dist_artifact(self):
        if not (ROOT / "dist/linux-server-loader").exists():
            self.skipTest("dist/linux-server-loader is not present")

        exit_code = self.module.main(["--format", "json"])

        self.assertIn(exit_code, (0, 1))


if __name__ == "__main__":
    unittest.main()
