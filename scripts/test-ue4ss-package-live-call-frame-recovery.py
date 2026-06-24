#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-ue4ss-package-live-call-frame-recovery.py"

spec = importlib.util.spec_from_file_location("live_call_frame_plan", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class LiveCallFrameRecoveryPlanTests(unittest.TestCase):
    def base_inputs(self):
        return {
            "route_evidence": {"routeCount": 13, "promotableRouteCount": 0},
            "method_refinement": {"candidateCount": 0, "selectedCount": 0},
            "static_metadata": {
                "complete": False,
                "blockers": ["target binary has no decoded DWARF line table entries"],
            },
            "source_abi": {
                "loaderContract": {
                    "typedefCount": 2,
                    "requiredSignatureCount": 2,
                    "requiresObservedTcharUnitMatch": True,
                    "hasGuardedNativeCallAdapter": True,
                },
                "blockers": ["no target-image package-loading anchor has been promoted"],
            },
            "external_plan": {"donorSearch": {"usableCandidateCount": 0, "falsePositiveCandidateCount": 6}},
            "trace_history": {
                "entries": [
                    {"armedCount": 1, "hitCount": 0, "methodHitCount": 5970},
                ]
            },
            "stimulus_plan": {
                "sourcePath": "/tmp/stimulus-plan.json",
                "loaderOnlyStimulusCanHitTargetPackageLoad": False,
                "recommendedCandidate": "operator-client-map-entry",
                "originClassification": {
                    "status": "unknown",
                    "probeCandidate": "operator-client-map-entry",
                    "serverSideFallbackCandidate": "server-side-client-call-emulation",
                },
                "nextStep": "select an operator-approved client login/travel/map-entry package-load stimulus",
                "candidates": [
                    {
                        "id": "operator-client-map-entry",
                        "promotableStimulus": True,
                    }
                ],
            },
            "trace_runbook": {
                "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
                "recommendedCandidate": "operator-client-map-entry",
                "blockers": [],
                "commands": [
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh print",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh preflight",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh arm",
                    "operator performs the approved client login/travel/map-entry package-load classification stimulus; if it is client-originated, recover the call frame and replay/spoof the equivalent call server-side",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh status",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject scripts/ue4ss-package-remote-trace.sh stop",
                ],
                "traceLog": "/tmp/package-trace.log",
                "nextStep": "run preflight",
            },
            "prearm_readiness": {
                "ready": True,
                "blockers": [],
                "preflightReady": True,
                "routeAddress": "0x129d58a2",
                "freshPreflightCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/package-$(date -u +%Y%m%dT%H%M%SZ).log",
                "freshTraceCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/package-$(date -u +%Y%m%dT%H%M%SZ).log",
                "nextStep": "operator may run coordinatorFreshTraceCommand",
            },
        }

    def test_plans_live_route_only_with_required_stimulus(self):
        data = self.base_inputs()

        plan = module.build_plan(**data)

        self.assertEqual(plan["action"], "plan-live-call-frame-stimulus")
        self.assertTrue(plan["liveRouteAvailable"])
        self.assertFalse(plan["repeatTraceUsefulWithoutStimulus"])
        self.assertIn("not useful", plan["repeatTraceReason"])
        self.assertEqual(plan["stimulusPlan"]["recommendedCandidate"], "operator-client-map-entry")
        self.assertEqual(plan["stimulusPlan"]["originClassification"]["status"], "unknown")
        self.assertFalse(plan["stimulusPlan"]["loaderOnlyStimulusCanHitTargetPackageLoad"])
        self.assertTrue(plan["stimulusPlan"]["recommendedPromotableStimulus"])
        self.assertEqual(plan["traceRunbook"]["recommendedCandidate"], "operator-client-map-entry")
        self.assertEqual(plan["traceRunbook"]["commandCount"], 6)
        self.assertTrue(plan["prearmReadiness"]["ready"])
        self.assertTrue(plan["prearmReadiness"]["preflightReady"])
        self.assertEqual(plan["prearmReadiness"]["routeAddress"], "0x129d58a2")
        self.assertIn("operator-visible classification action", plan["requiredStimulus"][0])
        self.assertIn("prearm readiness is true", plan["requiredStimulus"][1])
        self.assertIn("replay/spoof", plan["requiredStimulus"][4])
        self.assertIn("ue4ss-package-prearm-readiness.json", plan["commands"][0])
        self.assertIn("run-ue4ss-package-live-stimulus-trace.sh --trace-log", plan["commands"][1])
        self.assertNotIn("ue4ss-package-runtime-trace-live-client-map-entry-20260624T044051Z", "\n".join(plan["commands"]))
        self.assertNotIn("DUNE_UE4SS_PACKAGE_TRACE_ANCHOR", "\n".join(plan["commands"]))
        self.assertIn("classification records", plan["acceptance"][2])
        self.assertIn("server-side replay/spoof", plan["acceptance"][3])
        self.assertIn("sourceLogSha256", plan["acceptance"][5])
        self.assertIn("sourceEvidenceJsonSha256", plan["acceptance"][5])

    def test_defers_when_unreviewed_method_probes_remain(self):
        data = self.base_inputs()
        data["method_refinement"] = {"candidateCount": 3, "selectedCount": 2}

        plan = module.build_plan(**data)

        self.assertEqual(plan["action"], "defer-live-call-frame-trace")
        self.assertFalse(plan["liveRouteAvailable"])
        self.assertIn("unreviewed method probes remain", plan["blockers"][0])

    def test_defers_when_prearm_readiness_is_not_ready(self):
        data = self.base_inputs()
        data["prearm_readiness"] = {
            "ready": False,
            "blockers": ["preflight summary is stale"],
            "preflightReady": False,
        }

        plan = module.build_plan(**data)

        self.assertEqual(plan["action"], "defer-live-call-frame-trace")
        self.assertFalse(plan["liveRouteAvailable"])
        self.assertIn("package live-stimulus prearm readiness is not ready", plan["blockers"])


if __name__ == "__main__":
    unittest.main()
