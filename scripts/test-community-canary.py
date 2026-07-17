#!/usr/bin/env python3
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import community_canary


class CommunityCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.config = self.root / "community-rewards.json"
        self.config.write_text((ROOT / "config" / "community-rewards.example.json").read_text(encoding="utf-8"), encoding="utf-8")
        self.secret = b"c" * 64
        self.store = community_canary.Store(self.root / "evidence", self.secret, max_age_seconds=3600)

    def tearDown(self):
        self.temp.cleanup()

    def test_full_isolated_flow_records_current_signed_receipt(self):
        clock = iter((1000.0, 1000.125))
        result = community_canary.run_canary(self.config, self.store, principal_id="owner", now=lambda: next(clock))
        receipt = result["document"]["receipt"]
        self.assertTrue(receipt["ready"], result.get("error"))
        self.assertTrue(all(receipt["checks"].values()))
        self.assertEqual(2, receipt["evidence"]["deliveriesCompleted"])
        self.assertTrue(receipt["evidence"]["purchaseIdempotent"])
        self.assertTrue(receipt["evidence"]["webhookIdempotent"])
        self.assertTrue(receipt["evidence"]["trackIdempotent"])
        self.assertEqual(community_canary.ISOLATION, receipt["isolation"])
        self.assertTrue(result["verification"]["ok"])
        status = self.store.status(community_canary.file_sha256(self.config), now=1001)
        self.assertTrue(status["ok"])
        self.assertTrue(status["currentReady"])
        self.assertIn("dash_community_canary_current_ready 1", self.store.prometheus(community_canary.file_sha256(self.config), now=1001))

    def test_policy_change_and_age_invalidate_readiness_without_invalidating_signature(self):
        clock = iter((1000.0, 1000.0))
        community_canary.run_canary(self.config, self.store, now=lambda: next(clock))
        original_sha = community_canary.file_sha256(self.config)
        self.assertTrue(self.store.status(original_sha, now=1001)["currentReady"])
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["currency"]["name"] = "Changed Credits"
        self.config.write_text(json.dumps(config), encoding="utf-8")
        changed = self.store.status(community_canary.file_sha256(self.config), now=1001)
        self.assertTrue(changed["latest"]["verification"]["ok"])
        self.assertFalse(changed["latest"]["verification"]["policyCurrent"])
        self.assertFalse(changed["currentReady"])
        stale = self.store.status(original_sha, now=5001)
        self.assertFalse(stale["latest"]["verification"]["ageCurrent"])
        self.assertFalse(stale["currentReady"])

    def test_tampering_and_incomplete_catalog_fail_closed(self):
        clock = iter((1000.0, 1000.0))
        result = community_canary.run_canary(self.config, self.store, now=lambda: next(clock))
        document = json.loads(json.dumps(result["document"]))
        document["receipt"]["isolation"]["gameDeliveryInvoked"] = True
        self.assertFalse(community_canary.verify_signed_document(document, self.secret)["ok"])

        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["tracks"] = []
        config["engagementRewards"]["hourly"]["enabled"] = False
        config["engagementRewards"]["hourly"]["tiers"] = []
        self.config.write_text(json.dumps(config), encoding="utf-8")
        second = community_canary.Store(self.root / "failed-evidence", self.secret)
        failed_clock = iter((2000.0, 2000.0))
        failed = community_canary.run_canary(self.config, second, now=lambda: next(failed_clock))
        receipt = failed["document"]["receipt"]
        self.assertFalse(receipt["ready"])
        self.assertFalse(receipt["checks"]["catalogLoaded"])
        self.assertTrue(receipt["isolation"]["temporaryStateRemoved"])
        self.assertTrue(failed["verification"]["ok"])
        self.assertFalse(second.status(community_canary.file_sha256(self.config), now=2001)["currentReady"])

    def test_backup_deployment_readiness_and_metrics_integration_is_manifest_bound(self):
        panel = (ROOT / "admin" / "admin_panel.py").read_text(encoding="utf-8")
        verifier = (ROOT / "scripts" / "verify-backup.sh").read_text(encoding="utf-8")
        deployment = (ROOT / "scripts" / "deployment-assurance.py").read_text(encoding="utf-8")
        push = (ROOT / "scripts" / "push-assured-control-plane.sh").read_text(encoding="utf-8")
        catalog = json.loads((ROOT / "config" / "feature-readiness.json").read_text(encoding="utf-8"))
        feature = next(row for row in catalog["features"] if row["id"] == "community-rewards")
        self.assertEqual("operator-canary-pending", feature["canary"])
        self.assertEqual("community-rewards", feature["probe"])
        self.assertIn({"path": "admin/community_canary.py", "minimumBytes": 1000}, feature["files"])
        for source in (panel, verifier):
            self.assertIn("community_canary.verify_signed_document", source)
            self.assertIn("community_canary.SCHEMA", source)
        for source in (deployment, push):
            self.assertIn("admin/community_canary.py", source)
            self.assertIn("admin/community_rewards.py", source)
        self.assertIn('"state": "canary-proven"', panel)
        self.assertIn("dash_community_canary_current_ready", panel)


if __name__ == "__main__":
    unittest.main()
