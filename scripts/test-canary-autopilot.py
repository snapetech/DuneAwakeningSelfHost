#!/usr/bin/env python3

import copy
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import canary_autopilot


def evidence(*, age=100, max_age=1000, ready=True, valid=True, current_inputs=True):
    verification = {
        "ok": valid, "ready": ready, "ageCurrent": age <= max_age,
        "ageSeconds": age, "inputsCurrent": current_inputs,
        "currentReady": bool(valid and ready and age <= max_age and current_inputs),
    }
    return {
        "ok": valid, "currentReady": verification["currentReady"],
        "maxAgeSeconds": max_age,
        "latest": {"id": "receipt-1", "ready": ready, "verification": verification},
    }


class CanaryAutopilotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="test-canary-autopilot-")
        self.addCleanup(self.temporary.cleanup)
        self.path = pathlib.Path(self.temporary.name) / "private" / "state.json"
        self.store = canary_autopilot.Store(self.path, retention=10)

    def test_store_is_atomic_private_and_strict(self):
        self.store.initialize()
        state = self.store.load()
        self.assertEqual(state["schemaVersion"], canary_autopilot.SCHEMA)
        self.assertEqual(self.path.stat().st_mode & 0o077, 0)
        self.assertEqual(self.path.parent.stat().st_mode & 0o077, 0)
        bad = copy.deepcopy(state)
        bad["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            self.store.save(bad)
        self.path.write_text("not-json\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "decoded"):
            self.store.load()

    def test_symlink_state_is_refused(self):
        target = pathlib.Path(self.temporary.name) / "target.json"
        target.write_text("{}\n", encoding="utf-8")
        self.path.parent.mkdir(mode=0o700)
        self.path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.store.initialize()

    def test_planner_handles_current_expiring_drift_invalid_and_missing(self):
        retry = canary_autopilot.fresh_state(now=1000)["targets"]["community"]
        current = canary_autopilot.target_status("community", True, evidence(age=100), retry, refresh_before_seconds=200, now=1000)
        self.assertEqual((current["due"], current["reason"]), (False, "current"))
        expiring = canary_autopilot.target_status("community", True, evidence(age=850), retry, refresh_before_seconds=200, now=1000)
        self.assertEqual((expiring["due"], expiring["reason"]), (True, "expiring"))
        drift = canary_autopilot.target_status("community", True, evidence(current_inputs=False), retry, refresh_before_seconds=200, now=1000)
        self.assertEqual((drift["due"], drift["reason"]), (True, "input-drift"))
        invalid = canary_autopilot.target_status("community", True, evidence(valid=False), retry, refresh_before_seconds=200, now=1000)
        self.assertEqual((invalid["due"], invalid["reason"]), (True, "evidence-invalid"))
        missing = canary_autopilot.target_status("community", True, {"ok": True, "maxAgeSeconds": 1000}, retry, refresh_before_seconds=200, now=1000)
        self.assertEqual((missing["due"], missing["reason"]), (True, "missing"))
        disabled = canary_autopilot.target_status("community", False, {}, retry, refresh_before_seconds=200, now=1000)
        self.assertFalse(disabled["due"])

    def test_failures_back_off_exponentially_and_success_resets(self):
        self.store.initialize()
        self.store.record("community", trigger="automatic", started_at=1000, completed_at=1001, ready=False, error="first", base_backoff_seconds=10, max_backoff_seconds=25)
        first = self.store.load()["targets"]["community"]
        self.assertEqual(first["consecutiveFailures"], 1)
        self.assertEqual(canary_autopilot.epoch(first["nextAttemptAt"]), 1011)
        self.store.record("community", trigger="automatic", started_at=1011, completed_at=1012, ready=False, error="second", base_backoff_seconds=10, max_backoff_seconds=25)
        second = self.store.load()["targets"]["community"]
        self.assertEqual(canary_autopilot.epoch(second["nextAttemptAt"]), 1032)
        self.store.record("community", trigger="manual", started_at=1030, completed_at=1031, ready=True, receipt_id="community-canary-1", base_backoff_seconds=10, max_backoff_seconds=25)
        final = self.store.load()
        row = final["targets"]["community"]
        self.assertEqual(row["consecutiveFailures"], 0)
        self.assertIsNone(row["nextAttemptAt"])
        self.assertEqual(final["attemptsTotal"], 3)
        self.assertEqual(final["failuresTotal"], 2)
        self.assertEqual([item["trigger"] for item in final["history"]], ["manual", "automatic", "automatic"])

    def test_public_status_and_metrics_are_label_free(self):
        state = canary_autopilot.fresh_state(now=1000)
        status = canary_autopilot.public_status(
            state,
            {"community": evidence(), "creator-modding": evidence(), "public-ip-repair": evidence()},
            {target: True for target in canary_autopilot.TARGETS},
            enabled=True, running=True, refresh_before_seconds=200, now=1000,
        )
        self.assertEqual(status["summary"], {"targets": 3, "current": 3, "due": 0, "runnable": 0, "backoff": 0})
        metrics = canary_autopilot.prometheus(status)
        self.assertIn("dash_canary_autopilot_current 3", metrics)
        self.assertIn("dash_canary_autopilot_worker_running 1", metrics)
        self.assertNotIn("{", metrics)

    def test_repository_integration_is_complete(self):
        admin = (ROOT / "admin/admin_panel.py").read_text(encoding="utf-8")
        access = (ROOT / "admin/access_control.py").read_text(encoding="utf-8")
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        rules = (ROOT / "config/metrics/rules/dash.yml").read_text(encoding="utf-8")
        feature = json.loads((ROOT / "config/feature-readiness.json").read_text(encoding="utf-8"))
        deploy = (ROOT / "scripts/deployment-assurance.py").read_text(encoding="utf-8")
        push = (ROOT / "scripts/push-assured-control-plane.sh").read_text(encoding="utf-8")
        backup = (ROOT / "scripts/backup-state.sh").read_text(encoding="utf-8")
        verify = (ROOT / "scripts/verify-backup.sh").read_text(encoding="utf-8")
        self.assertIn('"/api/ops/canary-autopilot"', admin)
        self.assertIn("ensure_canary_autopilot_thread()", admin)
        self.assertIn("dash_canary_autopilot_due", admin)
        self.assertIn('"/api/ops/canary-autopilot"', access)
        self.assertIn("DUNE_CANARY_AUTOPILOT_ENABLED", compose)
        self.assertIn("DUNE_CANARY_AUTOPILOT_REFRESH_BEFORE_HOURS=24", env)
        self.assertIn("DashCanaryAutopilotRefreshOverdue", rules)
        self.assertIn("canary-autopilot", {row["id"] for row in feature["features"]})
        self.assertIn('"admin/canary_autopilot.py"', deploy)
        self.assertIn("admin/canary_autopilot.py", push)
        self.assertIn("canary_autopilot.validate_state", backup)
        self.assertIn("canary_autopilot.validate_state", verify)


if __name__ == "__main__":
    unittest.main()
