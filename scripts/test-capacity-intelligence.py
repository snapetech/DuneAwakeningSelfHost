#!/usr/bin/env python3
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest

import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import capacity_intelligence


def map_row(service="arrakeen", state="exited", players=0, demanded=False, ready=False, retention=900, mode="dynamic"):
    return {
        "service": service, "mode": mode, "state": state, "players": players,
        "demanded": demanded, "ready": ready, "optionalWarm": state == "running" and not players and not demanded,
        "retentionSeconds": retention,
    }


class CapacityIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.policy = self.root / "policy.json"
        self.policy.write_text((ROOT / "config" / "capacity-intelligence.json").read_text(encoding="utf-8"), encoding="utf-8")
        self.database = self.root / "private" / "capacity.sqlite3"
        self.store = capacity_intelligence.Store(self.database, self.policy)
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_policy_and_private_modes(self):
        policy = capacity_intelligence.load_policy(self.policy)
        self.assertEqual(policy["schemaVersion"], 1)
        self.assertEqual(self.database.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.database.parent.stat().st_mode & 0o777, 0o700)
        payload = json.loads(self.policy.read_text())
        payload["maximumRetentionSeconds"] = 30
        self.policy.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            capacity_intelligence.load_policy(self.policy)

    def test_start_request_completes_on_ready(self):
        self.store.observe([map_row()], observed_at=1000)
        event_id = self.store.record_start("arrakeen", at=1010, details={"reason": "travel"})
        self.store.observe([map_row(state="running", demanded=True, ready=False)], observed_at=1020)
        result = self.store.observe([map_row(state="running", demanded=True, ready=True)], observed_at=1085)
        self.assertEqual(result["startsCompleted"][0]["durationSeconds"], 75)
        status = self.store.status(now=1100)
        self.assertEqual(status["recentStarts"][0]["id"], event_id)
        self.assertEqual(status["recentStarts"][0]["outcome"], "ready")

    def test_start_failure_and_timeout(self):
        self.store.observe([map_row()], observed_at=1000)
        self.store.record_start("arrakeen", at=1010)
        self.store.fail_start("arrakeen", "boom", at=1012)
        self.assertEqual(self.store.status(now=1020)["recentStarts"][0]["outcome"], "failed")
        self.store.record_start("arrakeen", at=1100)
        result = self.store.observe([map_row()], observed_at=1401)
        self.assertEqual(result["startsCompleted"][0]["outcome"], "timeout")

    def test_warm_and_cold_revisit_classification(self):
        self.store.observe([map_row(state="running", ready=True)], observed_at=1000)
        self.store.observe([map_row(state="running", players=1, ready=True)], observed_at=1100)
        self.store.observe([map_row(state="running", ready=True)], observed_at=1200)
        warm = self.store.observe([map_row(state="running", players=1, ready=True)], observed_at=1300)
        self.assertEqual(warm["revisits"][0]["outcome"], "warm")
        self.store.observe([map_row(state="running", ready=True)], observed_at=1400)
        self.store.observe([map_row(state="exited")], observed_at=1500)
        self.store.record_start("arrakeen", at=1590)
        cold = self.store.observe([map_row(state="running", players=1, demanded=True, ready=False)], observed_at=1600)
        self.assertEqual(cold["revisits"][0]["outcome"], "cold")

    def test_time_weighted_efficiency(self):
        self.store.observe([map_row(state="running", ready=True)], observed_at=1000)
        self.store.observe([map_row(state="running", players=1, ready=True)], observed_at=1100)
        self.store.observe([map_row(state="exited")], observed_at=1200)
        status = self.store.status(now=1200)
        fleet = status["windows"]["86400"]["fleet"]
        self.assertGreater(fleet["runningSeconds"], 0)
        self.assertGreater(fleet["activeSeconds"], 0)
        self.assertGreater(fleet["savedSeconds"], 0)
        self.assertAlmostEqual(fleet["mapHoursSaved"], fleet["savedSeconds"] / 3600)

    def test_recommendation_becomes_eligible(self):
        # Five revisit gaps plus two measured starts satisfy the committed policy.
        clock = 1000
        self.store.observe([map_row(state="running", ready=True)], observed_at=clock)
        for index, gap in enumerate((120, 180, 240, 300, 360)):
            clock += 30
            self.store.observe([map_row(state="running", players=1, ready=True)], observed_at=clock)
            clock += 30
            self.store.observe([map_row(state="running", ready=True)], observed_at=clock)
            clock += gap
            self.store.observe([map_row(state="running", players=1, ready=True)], observed_at=clock)
        for duration in (80, 100):
            clock += 30
            self.store.observe([map_row(state="exited")], observed_at=clock)
            self.store.record_start("arrakeen", at=clock + 1)
            clock += duration
            self.store.observe([map_row(state="running", ready=True)], observed_at=clock)
        rec = self.store.status(now=clock)["recommendations"]["arrakeen"]
        self.assertTrue(rec["eligible"])
        self.assertEqual(rec["confidence"], "moderate")
        self.assertGreaterEqual(rec["recommendedRetentionSeconds"], 60)
        self.assertLessEqual(rec["recommendedRetentionSeconds"], 3600)

    def test_application_is_tamper_evident_and_append_only(self):
        receipt = self.store.record_application("operator", "manual", [{"service": "arrakeen", "before": 900, "after": 600}], applied_at=1000)
        self.assertTrue(self.store.verify()["ok"])
        connection = sqlite3.connect(self.database)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("delete from applications where id=?", (receipt["id"],))
        connection.execute("drop trigger capacity_applications_no_update")
        connection.execute("drop trigger capacity_applications_no_delete")
        connection.execute("update applications set sha256='bad' where id=?", (receipt["id"],))
        connection.commit()
        connection.close()
        self.assertFalse(self.store.verify()["ok"])

    def test_backup_and_prometheus(self):
        self.store.observe([map_row()], observed_at=1000)
        backup = self.store.backup(self.root / "backup" / "capacity.sqlite3")
        self.assertEqual(backup["integrity"], "ok")
        self.assertEqual((self.root / "backup" / "capacity.sqlite3").stat().st_mode & 0o777, 0o600)
        metrics = self.store.prometheus(now=1001)
        self.assertIn("dash_capacity_collector_up 1", metrics)
        self.assertIn('dash_capacity_map_hours_saved{window_seconds="86400"}', metrics)

    def test_missing_or_duplicate_maps_fail_closed(self):
        with self.assertRaises(ValueError):
            self.store.observe([], observed_at=1000)
        with self.assertRaises(ValueError):
            self.store.observe([map_row(), map_row()], observed_at=1000)


if __name__ == "__main__":
    unittest.main()
