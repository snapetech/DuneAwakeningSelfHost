#!/usr/bin/env python3
import datetime
import json
import pathlib
import tempfile
import unittest
from zoneinfo import ZoneInfo

import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import maintenance_planner


class MaintenancePlannerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.policy_path = root / "policy.json"
        self.policy = dict(maintenance_planner.DEFAULT_POLICY)
        self.policy.update({"minimumSampleDays": 2, "weekdayWeightingMinimumDays": 5})
        self.policy_path.write_text(json.dumps(self.policy), encoding="utf-8")
        self.store = maintenance_planner.Store(root / "moderation.sqlite3", self.policy_path).initialize()
        self.zone = ZoneInfo("America/Regina")

    def tearDown(self):
        self.temp.cleanup()

    def epoch(self, year, month, day, hour, minute=0):
        return datetime.datetime(year, month, day, hour, minute, tzinfo=self.zone).timestamp()

    def record_window(self, day, hour, players):
        for minute in range(0, 30, 5):
            self.store.record(players, 2, self.epoch(2026, 7, day, hour, minute))

    def test_policy_validation_rejects_cross_midnight_window(self):
        self.policy["eligibleLocalStart"] = "23:00"
        self.policy["eligibleLocalEnd"] = "02:00"
        self.policy_path.write_text(json.dumps(self.policy), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not cross midnight"):
            maintenance_planner.load_policy(self.policy_path)

    def test_observations_are_bucketed_without_identity(self):
        first = self.store.record(3, 2, self.epoch(2026, 7, 10, 4, 1))
        second = self.store.record(5, 3, self.epoch(2026, 7, 10, 4, 2))
        self.assertFalse(first["identitiesStored"])
        self.assertEqual(first["bucketStart"], second["bucketStart"])
        rows = self.store._rows(0)
        self.assertEqual(1, len(rows))
        self.assertEqual(2, rows[0]["samples"])
        self.assertEqual(8, rows[0]["player_sum"])
        self.assertEqual(5, rows[0]["player_max"])

    def test_measured_recommendation_avoids_populated_default_window(self):
        for day in (10, 11, 12, 13):
            self.record_window(day, 4, 0)
            self.record_window(day, 6, 6)
        now = self.epoch(2026, 7, 14, 0)
        status = self.store.status(now=now)
        self.assertEqual("measured-presence", status["source"])
        self.assertIn("04:00", status["recommendation"]["localStart"])
        self.assertEqual(0, status["recommendation"]["expectedConcurrentPlayers"])
        self.assertEqual(6, status["baseline"]["expectedConcurrentPlayers"])
        self.assertEqual(180, status["comparison"]["expectedPlayerMinutesSaved"])
        self.assertFalse(status["evidence"]["identitiesStored"])

    def test_empty_history_uses_named_policy_fallback(self):
        status = self.store.status(now=self.epoch(2026, 7, 14, 0))
        self.assertEqual("policy-fallback-learning", status["source"])
        self.assertIn("06:00", status["recommendation"]["localStart"])
        self.assertEqual("low-learning", status["confidence"])
        self.assertIn("dash_maintenance_planner_collector_up 1", self.store.prometheus(now=self.epoch(2026, 7, 14, 0)))


if __name__ == "__main__":
    unittest.main()
