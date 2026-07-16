#!/usr/bin/env python3
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import change_intelligence


class ChangeIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.policy = self.root / "change-intelligence.json"
        self.policy.write_text((ROOT / "config" / "change-intelligence.json").read_text(encoding="utf-8"), encoding="utf-8")
        self.secret = self.root / "change-intelligence-hmac.secret"
        self.secret.write_text("d" * 64 + "\n", encoding="utf-8")
        self.secret.chmod(0o600)
        self.database = self.root / "state" / "change-intelligence.sqlite3"
        self.store = change_intelligence.Store(self.database, self.policy, self.secret)
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def record(self, action, epoch, **fields):
        return self.store.record({"action": action, "ts": epoch, "ok": True, **fields}, ingested_at=epoch + 0.5)

    def test_private_modes_policy_and_secret_validation(self):
        self.assertEqual(0o700, self.database.parent.stat().st_mode & 0o777)
        self.assertEqual(0o600, self.database.stat().st_mode & 0o777)
        self.assertEqual(3600, self.store.policy["correlationWindowBeforeSeconds"])
        self.secret.chmod(0o644)
        with self.assertRaises(PermissionError):
            change_intelligence.read_secret(self.secret)

    def test_redaction_hashes_identity_paths_and_credentials(self):
        self.record(
            "service-control", 1000, method="POST", target="Alice", subject="FLS-123",
            peer="203.0.113.42", password="plain-password", api_token="plain-token",
            actor="Operator Alice",
            filesystem_path="/srv/private/world", path="/api/ops/services",
            message="https://operator:password@example.test/x Bearer abcdefghijklmnop",
        )
        encoded = json.dumps(self.store.status()["recentEvents"])
        for forbidden in ("Alice", "Operator Alice", "FLS-123", "203.0.113.42", "plain-password", "plain-token", "/srv/private/world", "operator:password", "abcdefghijklmnop"):
            self.assertNotIn(forbidden, encoded)
        self.assertIn("/api/ops/services", encoded)
        self.assertIn("hmac:", encoded)
        self.assertIn("path-hmac:", encoded)
        self.assertIn("<redacted>", encoded)

    def test_classification_temporal_ranking_and_noncausal_capsule(self):
        settings = self.record("settings-write", 1000, method="POST", path="/api/settings/env", actor="operator")
        service = self.record("service-control", 1100, method="POST", service="director", actor="operator")
        opened = self.record("slo-incident-opened", 1200, incident_id="slo-1")
        self.assertEqual("incident-open", opened["kind"])
        candidates = opened["candidates"]
        self.assertEqual([service["id"], settings["id"]], [row["id"] for row in candidates[:2]])
        self.assertGreater(candidates[0]["score"], candidates[1]["score"])
        capsule = self.store.capsule("slo:slo-1")
        self.assertFalse(capsule["causalityClaimed"])
        self.assertIn("not proof of causality", capsule["interpretation"])
        self.assertEqual("open", capsule["status"])

    def test_incident_resolution_and_followup_evidence(self):
        self.record("settings-write", 1000, method="POST")
        self.record("desired-state-drift-opened", 1100, finding_id="drift-1", subject=".env")
        self.record("backup-finished", 1150, path="backups/test")
        self.record("desired-state-drift-resolved", 1200, finding_id="drift-1", subject=".env")
        status = self.store.status()
        self.assertFalse(status["openIncidents"])
        self.assertEqual("resolved", status["incidents"][0]["status"])
        capsule = self.store.capsule("desired:drift-1")
        self.assertEqual("resolved", capsule["status"])
        self.assertTrue(any(row["action"] == "backup-finished" for row in capsule["followupEvidence"]))
        self.record("desired-state-drift-opened", 1300, finding_id="drift-1", subject=".env")
        reopened = self.store.capsule("desired:drift-1")
        self.assertEqual("open", reopened["status"])
        self.assertEqual("1970-01-01T00:21:40+00:00", reopened["opened"]["occurredAt"])
        with self.assertRaises(ValueError):
            self.store.capsule("../../invalid")

    def test_post_fallback_is_change_and_read_is_observation(self):
        write = self.record("new-admin-surface", 1000, method="POST")
        read = self.record("new-read-surface", 1001, method="GET")
        self.assertEqual("change", write["kind"])
        self.assertEqual("observation", read["kind"])

    def test_source_fingerprint_makes_history_import_idempotent(self):
        event = {"action": "settings-write", "ts": 1000, "ok": True, "method": "POST", "eventId": "audit-1"}
        first = self.store.record(event, source="audit-history", ingested_at=1001)
        second = self.store.record(event, source="audit-history", ingested_at=1002)
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(1, self.store.status()["eventCount"])

    def test_batch_import_is_atomic_bounded_and_can_skip_invalid_legacy_rows(self):
        events = [
            {"action": "settings-write", "ts": 1000 + index, "ok": True, "method": "POST", "eventId": f"audit-{index}"}
            for index in range(100)
        ]
        events.append({"action": "invalid action", "ts": 1200})
        first = self.store.record_many(events, skip_invalid=True, ingested_at=1300)
        second = self.store.record_many(events[:-1], skip_invalid=True, ingested_at=1400)
        self.assertEqual(100, first["insertedCount"])
        self.assertEqual(1, first["errors"])
        self.assertEqual(100, second["duplicates"])
        self.assertEqual(100, self.store.status()["eventCount"])
        self.assertTrue(self.store.verify()["eventChainValid"])

    def test_append_only_hmac_chain_detects_tampering_and_missing_trigger(self):
        self.record("settings-write", 1000, method="POST")
        self.record("service-control", 1100, method="POST")
        self.assertTrue(self.store.verify()["ok"])
        connection = sqlite3.connect(self.database)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("update events set action='forged' where sequence=1")
        connection.rollback()
        connection.execute("drop trigger change_events_no_update")
        connection.execute("update events set action='forged' where sequence=1")
        connection.commit()
        connection.close()
        result = self.store.verify()
        self.assertFalse(result["ok"])
        self.assertFalse(result["appendOnlyTriggers"])
        self.assertFalse(result["eventChainValid"])

    def test_payload_bounds_and_invalid_actions_fail_closed(self):
        with self.assertRaises(ValueError):
            self.store.record({"action": "bad action", "ts": 1000})
        bounded = self.store.record({"action": "settings-write", "ts": 1000, "value": "x" * 100000})
        stored = next(row for row in self.store.status()["recentEvents"] if row["id"] == bounded["id"])
        self.assertLessEqual(len(stored["data"]["value"]), 514)
        with self.assertRaises(ValueError):
            self.store.record({"action": "settings-write", "ts": 1001, **{f"field_{index}": "x" * 1000 for index in range(64)}})
        with self.assertRaises(ValueError):
            self.store.record({"action": "settings-write", "ts": 1000}, source="bad source")

    def test_backup_is_private_and_fully_verified(self):
        self.record("settings-write", 1000, method="POST")
        target = self.root / "archive" / "change-intelligence.sqlite3"
        result = self.store.backup(target)
        self.assertTrue(result["integrity"]["ok"])
        self.assertEqual(64, len(result["sha256"]))
        self.assertEqual(0o600, target.stat().st_mode & 0o777)

    def test_metrics_are_label_free_and_bounded(self):
        self.record("settings-write", 1000, method="POST")
        self.record("slo-incident-opened", 1100, incident_id="private-incident")
        metrics = self.store.prometheus()
        self.assertIn("dash_change_intelligence_collector_up 1", metrics)
        self.assertIn("dash_change_intelligence_events_total 2", metrics)
        self.assertIn("dash_change_intelligence_open_incidents 1", metrics)
        self.assertNotIn("private-incident", metrics)
        self.assertNotIn("{", metrics)


if __name__ == "__main__":
    unittest.main()
