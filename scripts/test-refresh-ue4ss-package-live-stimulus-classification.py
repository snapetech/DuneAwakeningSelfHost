#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh-ue4ss-package-live-stimulus-classification.py"

spec = importlib.util.spec_from_file_location("refresh_live_stimulus_classification", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class RefreshLiveStimulusClassificationTests(unittest.TestCase):
    def summary(self, **overrides):
        payload = {
            "schemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
            "ready": False,
            "blockers": ["ue4ss-package-abi-review.json selected runtime trace hit is missing for hitIndex 0"],
        }
        payload.update(overrides)
        return payload

    def runbook(self):
        return {
            "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
            "originClassification": {
                "status": "unknown",
                "probeCandidate": "operator-client-map-entry",
                "serverSideFallbackCandidate": "server-side-client-call-emulation",
                "decision": "trace first; classify whether the normal request reaches a usable server-side path; if it does not, recover and replay/spoof the equivalent call server-side",
            },
        }

    def test_missing_runtime_hit_refreshes_to_missing_without_replay_requirement(self):
        updated = module.refresh(self.summary(), self.runbook())

        origin = updated["originClassification"]
        self.assertEqual(origin["status"], "missing")
        self.assertFalse(origin["requiresServerSideReplay"])
        self.assertEqual(origin["probeCandidate"], "operator-client-map-entry")
        self.assertEqual(origin["serverSideFallbackCandidate"], "server-side-client-call-emulation")
        self.assertIn("no selected runtime package hit", origin["blockers"][0])
        self.assertFalse(updated["ready"])

    def test_ready_review_classifies_client_originated_requiring_server_replay(self):
        updated = module.refresh(self.summary(ready=True, blockers=[]), self.runbook())

        origin = updated["originClassification"]
        self.assertEqual(origin["status"], "client-originated-pending-server-replay")
        self.assertTrue(origin["requiresServerSideReplay"])

    def test_writes_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "summary.json"
            runbook_path = root / "runbook.json"
            out_path = root / "out.json"
            summary_path.write_text(json.dumps(self.summary()), encoding="utf-8")
            runbook_path.write_text(json.dumps(self.runbook()), encoding="utf-8")

            report = module.refresh_report(summary_path, runbook_path, out_path)
            written = json.loads(out_path.read_text(encoding="utf-8"))

        self.assertEqual(report["output"], str(out_path))
        self.assertEqual(written["originClassification"]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
