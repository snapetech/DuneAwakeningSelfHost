#!/usr/bin/env python3
import importlib.util
import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-ue4ss-package-stimulus-trace.py"

spec = importlib.util.spec_from_file_location("package_stimulus_trace_runbook", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageStimulusTraceRunbookTests(unittest.TestCase):
    def stimulus_plan(self):
        return {
            "recommendedCandidate": "operator-client-map-entry",
            "originClassification": {
                "status": "unknown",
                "probeCandidate": "operator-client-map-entry",
                "serverSideFallbackCandidate": "server-side-client-call-emulation",
            },
            "operationScriptCapabilities": {
                "scripts/ue4ss-package-remote-trace.sh": {
                    "hasZeroPlayerGuard": True,
                }
            },
            "candidates": [
                {
                    "id": "operator-client-map-entry",
                    "kind": "game-action",
                    "safe": "requires-operator-selection",
                    "promotableStimulus": True,
                }
            ],
        }

    def test_runbook_places_manual_stimulus_between_arm_and_status(self):
        runbook = module.build_runbook(
            self.stimulus_plan(),
            {"liveRouteAvailable": True},
            trace_log="/tmp/package-trace.log",
        )

        self.assertFalse(runbook["blockers"])
        self.assertEqual(
            runbook["sourcePath"],
            "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
        )
        self.assertEqual(runbook["recommendedCandidate"], "operator-client-map-entry")
        self.assertEqual(runbook["originClassification"]["status"], "unknown")
        self.assertEqual(
            runbook["originClassification"]["serverSideFallbackCandidate"],
            "server-side-client-call-emulation",
        )
        self.assertEqual(runbook["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS"], "false")
        self.assertEqual(
            runbook["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN"],
            "build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json",
        )
        self.assertEqual(
            runbook["traceInputs"]["methodCandidates"],
            "build/server-ue-package-loader-vtables.json",
        )
        self.assertEqual(
            runbook["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR"],
            "LoadPackage,LoadObject",
        )
        self.assertEqual(runbook["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT"], "4")
        self.assertIn(
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=true is forbidden when the required remote host is kspls0",
            runbook["guards"],
        )
        self.assertEqual(runbook["operatorWindow"]["maxArmSeconds"], 120)
        self.assertEqual(
            runbook["operatorWindow"]["sequence"],
            [
                "preflight",
                "arm",
                "operator-client-login-travel-map-entry",
                "status",
                "cleanupCommand",
                "no-debugger-check",
            ],
        )
        self.assertIn("under 120 seconds", runbook["guards"][4])
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES=", runbook["commands"][0])
        self.assertIn("preflight", runbook["commands"][1])
        self.assertIn(" arm ", runbook["commands"][2])
        self.assertIn("operator performs", runbook["commands"][3])
        self.assertIn("classification stimulus", runbook["commands"][3])
        self.assertIn("replay/spoof", runbook["commands"][3])
        self.assertIn(" status ", runbook["commands"][4])
        self.assertIn(" stop ", runbook["commands"][5])
        self.assertEqual(runbook["cleanupCommand"], runbook["commands"][5])
        self.assertIn(" stop ", runbook["cleanupCommand"])
        self.assertEqual(runbook["coordinatorCommand"], "scripts/run-ue4ss-package-live-stimulus-trace.sh")
        self.assertEqual(
            runbook["coordinatorFreshTraceCommand"],
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
        )
        self.assertEqual(
            runbook["coordinatorFreshPreflightCommand"],
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
        )
        self.assertEqual(
            runbook["reviewArtifacts"]["reviewBundleVerificationJson"],
            "/tmp/ue4ss-package-review-bundle-verification.json",
        )
        self.assertEqual(
            runbook["reviewArtifacts"]["localReviewSummarySchemaVersion"],
            "dune-ue4ss-package-live-stimulus-review-summary/v1",
        )
        self.assertEqual(
            runbook["localReviewSummaryJson"],
            "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json",
        )
        self.assertEqual(
            runbook["localReviewSummarySchemaVersion"],
            "dune-ue4ss-package-live-stimulus-review-summary/v1",
        )
        self.assertEqual(
            runbook["localReviewSummaryVerificationCommand"],
            runbook["reviewArtifacts"]["localReviewSummaryVerificationCommand"],
        )
        self.assertEqual(
            runbook["prearmReadinessJson"],
            "build/server-current-anchor-prep/ue4ss-package-prearm-readiness.json",
        )
        self.assertEqual(
            runbook["prearmReadinessVerificationCommand"],
            runbook["reviewArtifacts"]["prearmReadinessVerificationCommand"],
        )
        self.assertIn("verify-ue4ss-package-prearm-readiness.py", runbook["prearmReadinessVerificationCommand"])
        self.assertEqual(
            runbook["localReviewSummaryRunbookMode"],
            "default-source-runbook;trace-log-override-effective-runbook",
        )
        self.assertEqual(
            runbook["reviewArtifacts"]["localReviewSummaryRunbookMode"],
            "default-source-runbook;trace-log-override-effective-runbook",
        )
        self.assertIn("sourceEvidenceJson", runbook["reviewArtifacts"]["digestProvenanceFields"])
        self.assertIn("sourceLogSha256", runbook["reviewArtifacts"]["digestProvenanceFields"])
        self.assertIn("sourceEvidenceJsonSha256", runbook["reviewArtifacts"]["digestProvenanceFields"])
        self.assertEqual(
            runbook["routeSlotTraceRequirement"],
            {
                "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                "routeAddress": "0x129d58a2",
                "reviewField": "routeVtableStaticSlotMatches",
                "requiredSlots": ["0x3a0", "0x3d8"],
                "requiredRegisters": ["rbx", "r14"],
            },
        )
        self.assertIn("review bundle verification reports ready", runbook["postStatusAcceptance"][3])
        self.assertIn("sourceEvidenceJson", runbook["postStatusAcceptance"][4])
        self.assertIn("sourceLogSha256", runbook["postStatusAcceptance"][4])
        self.assertIn("sourceEvidenceJsonSha256", runbook["postStatusAcceptance"][4])
        self.assertIn("routeVtableStaticSlotMatches", runbook["postStatusAcceptance"][5])
        self.assertIn("UE4SS_PACKAGE_ROUTE_TRACE_HIT", runbook["postStatusAcceptance"][5])
        self.assertIn("effective temporary runbook", runbook["postStatusAcceptance"][6])
        self.assertIn("origin/reachability classification", runbook["postStatusAcceptance"][7])
        self.assertIn("server-side call-frame replay/spoofing", runbook["postStatusAcceptance"][7])
        self.assertIn("verify the review bundle", runbook["nextStep"])
        self.assertIn("coordinatorCommand", runbook["nextStep"])
        self.assertIn("server-side call-frame replay/spoofing", runbook["nextStep"])
        self.assertIn("noDebuggerCheckCommand", runbook)
        self.assertIn('grep -E "gdb|ue4ss-package-runtime-trace"', runbook["noDebuggerCheckCommand"])
        self.assertIn("docker top dune_server-deep-desert-1 -eo pid,stat,comm", runbook["noDebuggerCheckCommand"])
        rendered = module.markdown(runbook)
        self.assertIn("Max arm window seconds: `120`", rendered)
        self.assertIn("## Route Slot Trace Requirement", rendered)
        self.assertIn("Origin/reachability classification: `unknown`", rendered)
        self.assertIn("Server-side fallback: `server-side-client-call-emulation`", rendered)
        self.assertIn("Marker: `UE4SS_PACKAGE_ROUTE_TRACE_HIT`", rendered)
        self.assertIn("Route: `0x129d58a2`", rendered)
        self.assertIn("Review field: `routeVtableStaticSlotMatches`", rendered)
        self.assertIn("Required slots: `0x3a0, 0x3d8`", rendered)
        self.assertIn("Required registers: `rbx, r14`", rendered)
        self.assertIn("## Coordinator", rendered)
        self.assertIn(runbook["coordinatorCommand"], rendered)
        self.assertIn(runbook["coordinatorFreshPreflightCommand"], rendered)
        self.assertIn(runbook["coordinatorFreshTraceCommand"], rendered)
        self.assertIn("## Cleanup", rendered)
        self.assertIn(runbook["cleanupCommand"], rendered)
        self.assertIn("## No-Debugger Check", rendered)
        self.assertIn(runbook["noDebuggerCheckCommand"], rendered)

    def test_default_trace_log_is_timestamped_and_used_by_all_remote_commands(self):
        runbook = module.build_runbook(
            self.stimulus_plan(),
            {"liveRouteAvailable": True},
        )

        self.assertRegex(
            runbook["traceLog"],
            r"^/tmp/ue4ss-package-runtime-trace-live-client-map-entry-\d{8}T\d{6}Z\.log$",
        )
        self.assertEqual(runbook["traceLogUniqueness"]["strategy"], "utc-timestamp-default")
        for index in (0, 1, 2, 4, 5):
            self.assertIn(runbook["traceLog"], runbook["commands"][index])
            self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2", runbook["commands"][index])
        self.assertEqual(runbook["traceInputs"]["routeAddress"], "0x129d58a2")
        self.assertEqual(runbook["routeSlotTraceRequirement"]["routeAddress"], "0x129d58a2")

    def test_route_address_is_forwarded_to_remote_trace_commands(self):
        runbook = module.build_runbook(
            self.stimulus_plan(),
            {"liveRouteAvailable": True},
            trace_log="/tmp/package-trace.log",
            route_address="0xf94711c,0xf9492bc",
        )

        self.assertEqual(
            runbook["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS"],
            "0xf94711c,0xf9492bc",
        )
        self.assertEqual(runbook["traceInputs"]["routeAddress"], "0xf94711c,0xf9492bc")
        self.assertEqual(runbook["routeSlotTraceRequirement"]["routeAddress"], "0xf94711c,0xf9492bc")
        self.assertEqual(runbook["routeSlotTraceRequirement"]["requiredSlots"], ["0x3a0", "0x3d8"])
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=", runbook["commands"][0])
        self.assertIn("0xf94711c,0xf9492bc", runbook["commands"][2])

    def test_remote_commands_shell_quote_paths_and_preserve_split_arguments(self):
        runbook = module.build_runbook(
            self.stimulus_plan(),
            {"liveRouteAvailable": True},
            trace_log="/tmp/package trace; unsafe.log",
            external_plan="plans/external plan.json",
            trace_plan_json="plans/runtime trace plan.json",
            method_candidates="plans/method candidates.json",
        )

        command = runbook["commands"][0]
        split = shlex.split(command)

        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN=plans/external plan.json", split)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PLAN_JSON=plans/runtime trace plan.json", split)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES=plans/method candidates.json", split)
        self.assertEqual(split[-4:], ["print", "kspls0", "dune_server-deep-desert-1", "/tmp/package trace; unsafe.log"])
        self.assertIn("'/tmp/package trace; unsafe.log'", command)
        self.assertNotIn(" unsafe.log", command.replace("'/tmp/package trace; unsafe.log'", ""))

    def test_blocks_when_recommended_stimulus_is_not_promotable(self):
        stimulus = self.stimulus_plan()
        stimulus["candidates"][0]["promotableStimulus"] = False

        runbook = module.build_runbook(stimulus, {"liveRouteAvailable": True})

        self.assertFalse(runbook["commands"])
        self.assertEqual(runbook["cleanupCommand"], "")
        self.assertEqual(runbook["coordinatorCommand"], "")
        self.assertEqual(runbook["coordinatorFreshPreflightCommand"], "")
        self.assertEqual(runbook["coordinatorFreshTraceCommand"], "")
        self.assertEqual(runbook["noDebuggerCheckCommand"], "")
        self.assertIn("recommended stimulus is not promotable", runbook["blockers"])

    def test_cli_generates_package_local_trace_input_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stimulus_path = root / "ue4ss-package-stimulus-plan.json"
            live_path = root / "ue4ss-package-live-call-frame-recovery-plan.json"
            stimulus_path.write_text(json.dumps(self.stimulus_plan()), encoding="utf-8")
            live_path.write_text(json.dumps({"liveRouteAvailable": True}), encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--stimulus-plan-json",
                    str(stimulus_path),
                    "--live-plan-json",
                    str(live_path),
                    "--external-plan",
                    "ue4ss-package-external-symbol-plan.json",
                    "--trace-plan-json",
                    "ue4ss-package-runtime-trace-plan.json",
                    "--trace-plan-md",
                    "ue4ss-package-runtime-trace-plan.md",
                    "--method-candidates",
                    "ue-package-loader-vtables.json",
                    "--route-address",
                    "0xf94711c,0xf9492bc",
                    "--format",
                    "json",
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )

        runbook = json.loads(proc.stdout)

        self.assertFalse(runbook["blockers"])
        self.assertEqual(runbook["traceInputs"]["externalPlan"], "ue4ss-package-external-symbol-plan.json")
        self.assertEqual(runbook["traceInputs"]["tracePlanJson"], "ue4ss-package-runtime-trace-plan.json")
        self.assertEqual(runbook["traceInputs"]["tracePlanMarkdown"], "ue4ss-package-runtime-trace-plan.md")
        self.assertEqual(runbook["traceInputs"]["methodCandidates"], "ue-package-loader-vtables.json")
        self.assertEqual(runbook["traceInputs"]["routeAddress"], "0xf94711c,0xf9492bc")
        self.assertIn(
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_EXTERNAL_PLAN=ue4ss-package-external-symbol-plan.json",
            runbook["commands"][0],
        )
        self.assertIn(
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_METHOD_CANDIDATES=ue-package-loader-vtables.json",
            runbook["commands"][0],
        )
        self.assertIn(
            "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0xf94711c,0xf9492bc",
            runbook["commands"][0],
        )


if __name__ == "__main__":
    unittest.main()
