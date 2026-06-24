#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-ue4ss-package-server-replay.py"

spec = importlib.util.spec_from_file_location("package_server_replay", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def live_summary(status="client-originated-pending-server-replay", requires=True):
    return {
        "schemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
        "originClassification": {
            "status": status,
            "source": "live-stimulus-review-summary",
            "probeCandidate": "operator-client-map-entry",
            "serverSideFallbackCandidate": "server-side-client-call-emulation",
            "requiresServerSideReplay": requires,
            "blockers": [] if status != "missing" else ["package-load classification has no selected runtime package hit"],
            "decision": "if client-originated, replay/spoof server-side",
        },
    }


def promotion(ready_non_invoking=True, ready_native=False):
    return {
        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
        "signatureFamily": "LoadPackage",
        "sourceEvidence": "/tmp/trace.log",
        "sourceEvidenceJson": "/tmp/evidence.json",
        "sourceEvidenceJsonSha256": "evidence-json-sha256",
        "sourceLogSha256": "trace-log-sha256",
        "hitIndex": 0,
        "callerImageOffset": "0x129d58a2",
        "ripImageOffset": "0x1268545",
        "readyForNonInvokingCanary": ready_non_invoking,
        "readyForNativeInvoke": ready_native,
        "missingReviewFlags": [],
        "missingNativeInvokeFlags": [] if ready_native else ["--allow-native-invoke", "--final-native-call"],
        "blockers": [],
        "nextStep": "run non-invoking package canary",
    }


class PackageServerReplayPlanTests(unittest.TestCase):
    def test_missing_classification_blocks_replay(self):
        plan = module.build_plan(live_summary(status="missing", requires=False), promotion())

        self.assertEqual(plan["action"], "collect-server-side-replay-evidence")
        self.assertFalse(plan["readyForNonInvokingReplayCanary"])
        self.assertIn("package-load origin classification is missing", plan["blockers"])
        self.assertIn("origin classification: package-load classification has no selected runtime package hit", plan["blockers"])

    def test_client_originated_ready_manifest_plans_non_invoking_canary(self):
        plan = module.build_plan(live_summary(), promotion(), "build/server-current-anchor-prep/ue4ss-package-promotion-env.env")

        self.assertEqual(plan["action"], "run-non-invoking-server-side-replay-canary")
        self.assertTrue(plan["readyForNonInvokingReplayCanary"])
        self.assertFalse(plan["readyForNativeReplayInvoke"])
        self.assertEqual(plan["blockers"], [])
        self.assertIn("DUNE_LINUX_SERVER_CANARY_EXTRA_ENV=build/server-current-anchor-prep/ue4ss-package-promotion-env.env", plan["commands"][1])
        self.assertIn("explicit native invoke flags", plan["nextStep"])

    def test_final_native_invoke_requires_promotion_native_readiness(self):
        plan = module.build_plan(live_summary(), promotion(ready_native=True), "build/server-current-anchor-prep/ue4ss-package-promotion-env.env")

        self.assertEqual(plan["action"], "run-final-guarded-server-side-native-invoke")
        self.assertTrue(plan["readyForNonInvokingReplayCanary"])
        self.assertTrue(plan["readyForNativeReplayInvoke"])
        self.assertEqual(plan["blockers"], [])

    def test_server_originated_evidence_blocks_replay_branch(self):
        plan = module.build_plan(live_summary(status="server-originated", requires=False), promotion())

        self.assertEqual(plan["action"], "collect-server-side-replay-evidence")
        self.assertIn("package-load evidence is server-originated", plan["blockers"][0])


if __name__ == "__main__":
    unittest.main()
