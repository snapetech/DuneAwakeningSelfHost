#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-ue4ss-package-prearm-readiness.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_prearm_readiness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def runbook(path, trace_plan_path):
    return {
        "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
        "sourcePath": str(path),
        "remote": "kspls0",
        "container": "dune_server-deep-desert-1",
        "traceLog": "/tmp/trace.log",
        "traceInputs": {
            "routeAddress": "0x129d58a2",
            "tracePlanJson": str(trace_plan_path),
            "tracePlanMarkdown": str(trace_plan_path.with_suffix(".md")),
        },
        "traceEnv": {"DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS": "0x129d58a2"},
        "routeSlotTraceRequirement": {
            "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "routeAddress": "0x129d58a2",
            "reviewField": "routeVtableStaticSlotMatches",
            "requiredSlots": ["0x3a0", "0x3d8"],
            "requiredRegisters": ["rbx", "r14"],
        },
        "cleanupCommand": (
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2 "
            "scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/trace.log"
        ),
        "operatorWindow": {"maxArmSeconds": 120, "cleanupRequired": True},
    }


def preflight_summary(runbook_path):
    return {
        "schemaVersion": "dune-ue4ss-package-live-preflight-summary/v1",
        "createdUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runbook": str(runbook_path),
        "sourceRunbook": str(runbook_path),
        "traceLogOverride": "",
        "traceRemote": "kspls0",
        "container": "dune_server-deep-desert-1",
        "traceLog": "/tmp/trace.log",
        "operatorWindowSeconds": 30,
        "ready": True,
        "blockers": [],
        "fields": {
            "remote_host": "kspls0",
            "player_guard_preflight_connected_players": "0",
            "preflight": "ok",
            "container": "dune_server-deep-desert-1",
            "server_pid": "2477302",
            "trace_log": "/tmp/trace.log",
            "route_address": "0x129d58a2",
        },
    }


def next_action():
    return {
        "schemaVersion": "dune-ue4ss-package-next-action/v1",
        "action": "recover-package-anchor",
        "liveTraceRunbook": {
            "remote": "kspls0",
            "container": "dune_server-deep-desert-1",
            "routeSlotTraceRequirement": {
                "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                "routeAddress": "0x129d58a2",
                "reviewField": "routeVtableStaticSlotMatches",
                "requiredSlots": ["0x3a0", "0x3d8"],
                "requiredRegisters": ["rbx", "r14"],
            },
            "coordinatorFreshPreflightCommand": (
                "scripts/run-ue4ss-package-live-stimulus-trace.sh "
                "--preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log"
            ),
            "coordinatorFreshTraceCommand": (
                "scripts/run-ue4ss-package-live-stimulus-trace.sh "
                "--trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log"
            ),
        },
        "routeSlotRecovery": {
            "requiredRouteTrace": {
                "address": "0x129d58a2",
                "reviewField": "routeVtableStaticSlotMatches",
                "slots": ["0x3a0", "0x3d8"],
                "registers": ["rbx", "r14"],
            }
        },
    }


def trace_plan(expanded=True):
    registers = ["rbx", "r14"]
    stack_labels = []
    if expanded:
        registers = ["rdi", "rsi", "rdx", "rcx", "r8", "r9", "rbx", "r12", "r13", "r14", "r15"]
        stack_labels = ["rsp0", "rsp8", "rsp10", "rsp18", "rsp20", "rsp28"]
    route_gdb_lines = ["UE4SS_PACKAGE_ROUTE_TRACE_HIT"]
    for register in registers:
        route_gdb_lines.append(f"UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg={register}")
        route_gdb_lines.append(f"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={register}")
    for label in stack_labels:
        route_gdb_lines.append(f"UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg={label}")
        route_gdb_lines.append(f"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={label}")
    return {
        "schemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
        "requestedRouteAddresses": ["0x129d58a2"],
        "routeProbeCount": 1,
        "routeProbes": [{"address": "0x129d58a2"}],
        "routeGdb": "\n".join(route_gdb_lines),
    }


def audit():
    return {
        "schemaVersion": "dune-ue4ss-linux-port-completion-audit/v1",
        "ready": False,
        "gates": [
            {"name": "live-preflight-summary", "ready": True, "blockers": []},
            {"name": "live-stimulus-summary", "ready": False, "blockers": ["summary is not ready: missing hit"]},
        ],
        "blockers": [
            "port-gap-summary: port gap summary is not ready",
            "package-next-action: package next-action is not complete: review bundle integrity is usable but the runtime trace captured no package hit",
            "live-stimulus-summary: summary is not ready: missing hit",
        ],
        "nextRouteSlotTraceRequirement": {},
    }


def route_slot_requirement():
    return {
        "expectedReviewField": "routeVtableStaticSlotMatches",
        "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
        "missingRegisters": ["r14", "rbx"],
        "missingSlots": ["0x3a0", "0x3d8"],
        "requiredRegisters": ["rbx", "r14"],
        "requiredSlots": ["0x3a0", "0x3d8"],
        "reviewField": "routeVtableStaticSlotMatches",
        "routeAddress": "0x129d58a2",
    }


def origin_classification():
    return {
        "status": "pending",
        "source": "stimulus-runbook",
        "probeCandidate": "operator-client-map-entry",
        "serverSideFallbackCandidate": "server-side-client-call-emulation",
        "requiresServerSideReplay": False,
        "decision": "trace first; replay/spoof equivalent call server-side if client-originated",
    }


def runtime_root_recovery_plan():
    return {
        "needed": True,
        "action": "recover-runtime-roots",
        "requiredLogPath": "/tmp/dune-server-probe-loader.log",
        "blockedByMissingLog": True,
        "missingKeys": ["runtimeRootDiscovery", "runtimeRootValidation"],
        "preflightCommand": (
            "DUNE_LINUX_SERVER_CANARY_LOG_PATH=/tmp/dune-server-probe-loader.log "
            "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true scripts/canary-linux-server-loader.sh .env"
        ),
        "runCommand": (
            "DUNE_LINUX_SERVER_CANARY_LOG_PATH=/tmp/dune-server-probe-loader.log "
            "DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true scripts/canary-linux-server-loader.sh .env"
        ),
    }


class VerifyPackagePrearmReadinessTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def write_inputs(self, root):
        runbook_path = root / "runbook.json"
        preflight_path = root / "preflight.json"
        next_action_path = root / "next-action.json"
        audit_path = root / "audit.json"
        trace_plan_path = root / "trace-plan.json"
        write_json(runbook_path, runbook(runbook_path, trace_plan_path))
        write_json(preflight_path, preflight_summary(runbook_path))
        write_json(next_action_path, next_action())
        write_json(audit_path, audit())
        write_json(trace_plan_path, trace_plan())
        return preflight_path, runbook_path, next_action_path, audit_path

    def test_ready_when_preflight_is_ready_and_only_post_stimulus_blockers_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.write_inputs(Path(tmp))
            report = self.module.report(*paths, max_age_seconds=3600)
            rendered = self.module.markdown(report)

        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(report["routeAddress"], "0x129d58a2")
        self.assertTrue(report["tracePlan"]["expandedRouteCaptureReady"])
        self.assertIn("--preflight-only", report["freshPreflightCommand"])
        self.assertIn("run-ue4ss-package-live-stimulus-trace.sh", report["freshTraceCommand"])
        self.assertIn("Ready: `true`", rendered)
        self.assertIn("## Fresh Preflight Command", rendered)
        self.assertIn("## Trace Plan", rendered)
        self.assertIn("- Expanded route capture ready: `true`", rendered)
        self.assertIn("- Required capture registers: `rdi, rsi, rdx, rcx, r8, r9, rbx, r12, r13, r14, r15`", rendered)
        self.assertIn("- Required stack candidates: `rsp0, rsp8, rsp10, rsp18, rsp20, rsp28`", rendered)

    def test_batch_preflight_trace_env_drives_matching_fresh_trace_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            preflight = json.loads(paths[0].read_text(encoding="utf-8"))
            preflight["traceLog"] = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-batch3-20260624T064554Z.log"
            preflight["traceLogOverride"] = preflight["traceLog"]
            preflight["runbook"] = "/tmp/ue4ss-package-live-stimulus-runbook.batch3.json"
            preflight["fields"]["trace_log"] = preflight["traceLog"]
            preflight["traceEnv"] = {
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR": "LoadObject",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT": "3",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS": "0x129d58a2",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SEED_ADDRESS": "0x622e3ac,0x622e425,0x622e4a5",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY": "LoadObject",
            }
            write_json(paths[0], preflight)

            report = self.module.report(*paths, max_age_seconds=3600)

        self.assertTrue(report["ready"], report["blockers"])
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SEED_ADDRESS=0x622e3ac,0x622e425,0x622e4a5", report["freshTraceCommand"])
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT=3", report["freshTraceCommand"])
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY=LoadObject", report["freshTraceCommand"])
        self.assertIn(
            "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-batch3-$(date -u +%Y%m%dT%H%M%SZ).log",
            report["freshTraceCommand"],
        )
        self.assertIn("--preflight-only", report["freshPreflightCommand"])

    def test_blocks_stale_route_plan_without_expanded_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            trace_plan_path = root / "trace-plan.json"
            write_json(trace_plan_path, trace_plan(expanded=False))
            report = self.module.report(*paths, max_age_seconds=3600)

        self.assertFalse(report["ready"])
        self.assertIn("rdi", report["tracePlan"]["missingRouteCaptureRegisters"])
        self.assertIn("rsp0", report["tracePlan"]["missingRouteCaptureStackLabels"])
        self.assertIn(
            "trace plan routeGdb is missing expanded register route capture: rdi, rsi, rdx, rcx, r8, r9, r12, r13, r15",
            report["blockers"],
        )

    def test_blocks_when_remote_preflight_route_address_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            preflight = json.loads(paths[0].read_text(encoding="utf-8"))
            preflight["fields"]["route_address"] = ""
            write_json(paths[0], preflight)
            report = self.module.report(*paths, max_age_seconds=3600)

        self.assertFalse(report["ready"])
        self.assertIn(
            "preflight: summary fields.route_address does not match runbook traceInputs routeAddress",
            report["blockers"],
        )

    def test_blocks_fresh_commands_without_timestamped_tmp_trace_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            next_action_payload = json.loads(paths[2].read_text(encoding="utf-8"))
            live = next_action_payload["liveTraceRunbook"]
            live["coordinatorFreshPreflightCommand"] = (
                "scripts/run-ue4ss-package-live-stimulus-trace.sh "
                "--preflight-only --wait 30 --trace-log /tmp/static.log"
            )
            live["coordinatorFreshTraceCommand"] = (
                "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log relative.log"
            )
            write_json(paths[2], next_action_payload)

            report = self.module.report(*paths, max_age_seconds=3600)

        self.assertFalse(report["ready"])
        self.assertIn(
            "next-action fresh preflight command must use timestamped /tmp package trace log "
            "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
            report["blockers"],
        )
        self.assertIn(
            "next-action fresh trace command must use timestamped /tmp package trace log "
            "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
            report["blockers"],
        )

    def test_blocks_unexpected_completion_audit_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            audit_payload = json.loads(paths[3].read_text(encoding="utf-8"))
            audit_payload["blockers"].append("unexpected: stale package artifact")
            write_json(paths[3], audit_payload)
            report = self.module.report(*paths, max_age_seconds=3600)

        self.assertFalse(report["ready"])
        self.assertIn("completion audit has unexpected blockers for prearm state", report["blockers"])

    def test_tolerates_detailed_port_gap_audit_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            audit_payload = json.loads(paths[3].read_text(encoding="utf-8"))
            audit_payload["blockers"].append("port-gap-summary: port gap: package-next-action: missing runtime hit")
            write_json(paths[3], audit_payload)

            report = self.module.report(*paths, max_age_seconds=3600)

        self.assertTrue(report["ready"], report["blockers"])

    def test_blocks_route_slot_audit_blocker_without_next_trace_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            audit_payload = json.loads(paths[3].read_text(encoding="utf-8"))
            audit_payload["blockers"].append(
                "live-stimulus-summary: summary is not ready: route-slot recovery: route hits did not contain all required static vtable slot matches"
            )
            audit_payload["nextRouteSlotTraceRequirement"] = {}
            write_json(paths[3], audit_payload)

            report = self.module.report(*paths, max_age_seconds=3600)

        self.assertFalse(report["ready"])
        self.assertIn(
            "completion audit route-slot blocker must include nextRouteSlotTraceRequirement",
            report["blockers"],
        )

    def test_blocks_mismatched_next_action_route_slot_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            next_action_payload = json.loads(paths[2].read_text(encoding="utf-8"))
            next_action_payload["liveTraceRunbook"]["routeSlotTraceRequirement"]["requiredSlots"] = ["0x3a0"]
            write_json(paths[2], next_action_payload)

            report = self.module.report(*paths, max_age_seconds=3600)

        self.assertFalse(report["ready"])
        self.assertIn(
            "next-action liveTraceRunbook.routeSlotTraceRequirement does not match runbook",
            report["blockers"],
        )

    def test_allows_route_slot_audit_blocker_with_next_trace_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            audit_payload = json.loads(paths[3].read_text(encoding="utf-8"))
            audit_payload["blockers"].append(
                "live-stimulus-summary: summary is not ready: route-slot recovery: route hits did not contain all required static vtable slot matches"
            )
            audit_payload["nextRouteSlotTraceRequirement"] = route_slot_requirement()
            write_json(paths[3], audit_payload)

            report = self.module.report(*paths, max_age_seconds=3600)
            rendered = self.module.markdown(report)

        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(report["completionAuditNextRouteSlotTraceRequirement"], route_slot_requirement())
        self.assertIn("## Completion Audit Route Slot Trace Requirement", rendered)
        self.assertIn("- Marker: `UE4SS_PACKAGE_ROUTE_TRACE_HIT`", rendered)
        self.assertIn("- Missing slots: `0x3a0, 0x3d8`", rendered)

    def test_carries_completion_audit_client_gate_and_runtime_root_next_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            audit_payload = json.loads(paths[3].read_text(encoding="utf-8"))
            audit_payload["nextOriginClassification"] = origin_classification()
            audit_payload["nextRuntimeRootRecoveryPlan"] = runtime_root_recovery_plan()
            write_json(paths[3], audit_payload)

            report = self.module.report(*paths, max_age_seconds=3600)
            rendered = self.module.markdown(report)

        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(
            report["completionAuditNextClientGateClassification"]["serverSideFallbackCandidate"],
            "server-side-client-call-emulation",
        )
        self.assertEqual(
            report["completionAuditNextRuntimeRootRecoveryPlan"]["requiredLogPath"],
            "/tmp/dune-server-probe-loader.log",
        )
        self.assertIn("## Completion Audit Origin/Reachability Classification", rendered)
        self.assertIn("server-side-client-call-emulation", rendered)
        self.assertIn("## Completion Audit Runtime Root Recovery", rendered)
        self.assertIn("### Runtime Root Canary", rendered)

    def test_stale_preflight_points_next_step_at_fresh_preflight_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self.write_inputs(root)
            preflight = json.loads(paths[0].read_text(encoding="utf-8"))
            preflight["createdUtc"] = "2026-06-24T00:00:00Z"
            preflight["ready"] = True
            write_json(paths[0], preflight)
            audit_payload = json.loads(paths[3].read_text(encoding="utf-8"))
            audit_payload["gates"][0]["ready"] = False
            audit_payload["gates"][0]["blockers"] = ["summary createdUtc is stale: ageSeconds=120 maxAgeSeconds=60"]
            audit_payload["blockers"].append("live-preflight-summary: summary createdUtc is stale: ageSeconds=120 maxAgeSeconds=60")
            audit_payload["blockers"].append("package-prearm-readiness: prearm readiness is not ready")
            write_json(paths[3], audit_payload)

            report = self.module.report(*paths, max_age_seconds=60)
            rendered = self.module.markdown(report)

        self.assertFalse(report["ready"])
        self.assertIn("--preflight-only", report["freshPreflightCommand"])
        self.assertNotIn("completion audit has unexpected blockers for prearm state", report["blockers"])
        self.assertEqual(
            report["nextStep"],
            "operator must refresh the live preflight with coordinatorFreshPreflightCommand before arming the live package trace",
        )
        self.assertIn("## Fresh Preflight Command", rendered)


if __name__ == "__main__":
    unittest.main()
