#!/usr/bin/env python3
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import alert_inbox


def response(*alerts):
    return {"status": "success", "data": {"alerts": list(alerts)}}


def alert(name="DiskFull", state="firing", severity="critical", **labels):
    return {
        "labels": {"alertname": name, "severity": severity, "instance": "server", **labels},
        "annotations": {"summary": f"{name} summary", "description": f"{name} detail"},
        "state": state,
        "activeAt": "2026-07-17T12:00:00Z",
    }


class AlertInboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = alert_inbox.Store(pathlib.Path(self.tmp.name) / "inbox.sqlite3", retention_days=30).initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_poll_creates_one_durable_firing_transition(self):
        result = self.store.sync(response(alert()), now=1000)
        self.assertEqual("firing", result["transitions"][0]["transition"])
        status = self.store.status(now=1000)
        self.assertTrue(status["ok"])
        self.assertEqual(1, status["summary"]["active"])
        self.assertEqual(1, status["summary"]["unacknowledged"])

    def test_identical_poll_is_deduplicated(self):
        self.store.sync(response(alert()), now=1000)
        result = self.store.sync(response(alert()), now=1030)
        self.assertEqual([], result["transitions"])
        self.assertEqual(1, len(self.store.status(now=1030)["history"]))

    def test_successful_absence_resolves_but_failed_poll_does_not(self):
        self.store.sync(response(alert()), now=1000)
        self.store.record_poll_error("connection refused", now=1030)
        failed = self.store.status(now=1030)
        self.assertEqual(1, failed["summary"]["active"])
        self.assertFalse(failed["ok"])
        result = self.store.sync(response(), now=1060)
        self.assertEqual("resolved", result["transitions"][0]["transition"])
        self.assertEqual(0, self.store.status(now=1060)["summary"]["active"])

    def test_refire_starts_new_generation_and_clears_acknowledgement(self):
        result = self.store.sync(response(alert()), now=1000)
        fp = result["transitions"][0]["fingerprint"]
        self.store.acknowledge(fp, "operator", "investigating", now=1010)
        self.store.sync(response(), now=1020)
        refire = self.store.sync(response(alert()), now=1030)
        self.assertEqual("refiring", refire["transitions"][0]["transition"])
        current = self.store.status(now=1030)["alerts"][0]
        self.assertEqual(2, current["generation"])
        self.assertFalse(current["acknowledged"])

    def test_acknowledgement_is_attributed_and_idempotent(self):
        fp = self.store.sync(response(alert()), now=1000)["transitions"][0]["fingerprint"]
        first = self.store.acknowledge(fp, "alice", "ticket 42", now=1010)
        second = self.store.acknowledge(fp, "bob", "duplicate", now=1020)
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual("alice", second["alert"]["acknowledgedBy"])
        self.assertEqual("ticket 42", second["alert"]["acknowledgementNote"])

    def test_sensitive_labels_are_redacted_before_fingerprinting_and_storage(self):
        raw = alert(api_token="do-not-store")
        result = self.store.sync(response(raw), now=1000)
        current = self.store.status(now=1000)["alerts"][0]
        self.assertEqual("[redacted]", current["labels"]["api_token"])
        self.assertNotIn("do-not-store", self.store.database.read_bytes().decode("latin1"))
        self.assertRegex(result["transitions"][0]["fingerprint"], r"^[0-9a-f]{64}$")

    def test_malformed_authoritative_response_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "not successful"):
            self.store.sync({"status": "error"}, now=1000)
        with self.assertRaisesRegex(ValueError, "data.alerts"):
            self.store.sync({"status": "success", "data": {}}, now=1000)
        malformed = alert()
        malformed["activeAt"] = "not-a-time"
        with self.assertRaisesRegex(ValueError, "activeAt is invalid"):
            self.store.sync(response(malformed), now=1000)

    def test_duplicate_bounded_identities_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate bounded label identities"):
            self.store.sync(response(alert(), alert()), now=1000)
        self.assertEqual(0, self.store.status(now=1000)["summary"]["active"])

    def test_metrics_are_bounded_and_label_free(self):
        self.store.sync(response(alert(), alert("Lag", severity="warning", instance="gateway")), now=1000)
        metrics = self.store.prometheus(now=1000, stale_after_seconds=60)
        self.assertIn("dash_alert_inbox_collector_up 1\n", metrics)
        self.assertIn("dash_alert_inbox_active 2\n", metrics)
        self.assertIn("dash_alert_inbox_critical 1\n", metrics)
        self.assertNotIn("{", metrics)

    def test_briefing_summary_excludes_its_meta_alert_namespace(self):
        self.store.sync(response(
            alert("DashOperationsBriefingCriticalActions"),
            alert("Lag", severity="warning", instance="gateway"),
        ), now=1000)
        status = self.store.status(now=1000)
        self.assertEqual({
            "active": 2, "firing": 2, "pending": 0, "unacknowledged": 2,
            "critical": 1, "warning": 1, "history": 2,
        }, status["summary"])
        self.assertEqual({
            "active": 1, "unacknowledged": 1, "critical": 0,
            "warning": 1, "feedbackExcluded": 1,
        }, status["briefingSummary"])
        self.assertTrue(status["executionContract"]["briefingMetaAlertsExcludedFromBriefingScore"])

    def test_database_symlink_is_rejected(self):
        real = pathlib.Path(self.tmp.name) / "real.sqlite3"
        link = pathlib.Path(self.tmp.name) / "link.sqlite3"
        real.touch()
        link.symlink_to(real)
        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            alert_inbox.Store(link).initialize()


if __name__ == "__main__":
    unittest.main()
