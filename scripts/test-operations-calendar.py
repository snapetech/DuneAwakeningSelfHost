#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import operations_calendar


def window(identifier, impact, start, end, **metadata):
    return {
        "id": identifier, "source": identifier.split(":", 1)[0], "title": identifier,
        "impact": impact, "startsAt": start, "endsAt": end, "metadata": metadata,
    }


class OperationsCalendarTest(unittest.TestCase):
    def test_disruptive_recovery_overlap_is_critical(self):
        status = operations_calendar.analyze([
            window("backup:one", "recovery", 1100, 1400),
            window("restart:one", "disruptive", 1200, 1500, execute=True),
        ], now=1000)
        self.assertFalse(status["ok"])
        self.assertEqual(1, status["summary"]["criticalConflicts"])
        self.assertEqual(200, status["conflicts"][0]["overlapSeconds"])

    def test_touching_windows_do_not_conflict(self):
        status = operations_calendar.analyze([
            window("backup:one", "recovery", 1100, 1200),
            window("restart:one", "disruptive", 1200, 1300, execute=True),
        ], now=1000)
        self.assertEqual([], status["conflicts"])

    def test_recovery_overlap_is_warning(self):
        status = operations_calendar.analyze([
            window("backup:one", "recovery", 1100, 1300),
            window("backup:two", "recovery", 1200, 1400),
        ], now=1000)
        self.assertTrue(status["ok"])
        self.assertEqual(1, status["summary"]["warningConflicts"])

    def test_maintenance_exclusion_covers_disruptive_window(self):
        status = operations_calendar.analyze([
            window("slo:one", "exclusion", 1000, 1600, maintenanceExclusion=True),
            window("restart:one", "disruptive", 1100, 1500, execute=True),
        ], now=900)
        self.assertEqual([], status["coverageFindings"])
        self.assertEqual([], status["conflicts"])

    def test_partial_exclusion_does_not_claim_coverage(self):
        status = operations_calendar.analyze([
            window("slo:one", "exclusion", 1100, 1400, maintenanceExclusion=True),
            window("restart:one", "disruptive", 1100, 1500, execute=True),
        ], now=1000)
        self.assertEqual(1, status["summary"]["uncoveredDisruptive"])

    def test_invalid_sources_fail_collector_without_hiding_valid_rows(self):
        status = operations_calendar.analyze([
            window("backup:one", "recovery", 1100, 1300),
            {"id": "bad"},
        ], now=1000)
        self.assertEqual(1, len(status["windows"]))
        self.assertEqual(1, status["summary"]["sourceErrors"])
        self.assertFalse(status["ok"])

    def test_upstream_source_errors_fail_metrics_and_change_fingerprint(self):
        rows = [window("backup:one", "recovery", 1100, 1300)]
        healthy = operations_calendar.analyze(rows, now=1000)
        failed = operations_calendar.analyze(
            rows, now=1000,
            source_errors=[{"source": "slo-maintenance", "error": "database unavailable"}],
        )
        self.assertFalse(failed["ok"])
        self.assertEqual(1, failed["summary"]["sourceErrors"])
        self.assertEqual("slo-maintenance", failed["errors"][0]["source"])
        self.assertNotEqual(healthy["fingerprint"], failed["fingerprint"])
        self.assertIn("dash_operations_calendar_collector_up 0\n", operations_calendar.prometheus(failed, now=1000))

    def test_non_json_metadata_is_a_bounded_source_error(self):
        row = window("event:one", "planning", 1100, 1200)
        row["metadata"] = {"invalid": {"set"}}
        status = operations_calendar.analyze([row], now=1000)
        self.assertEqual([], status["windows"])
        self.assertEqual("calendar window metadata is not JSON-serializable", status["errors"][0]["error"])

    def test_horizon_and_expired_filtering_are_bounded(self):
        status = operations_calendar.analyze([
            window("expired:one", "planning", 800, 900),
            window("inside:one", "planning", 1100, 1200),
            window("outside:one", "planning", 5000, 5100),
        ], now=1000, horizon_seconds=3600)
        self.assertEqual(["inside:one"], [row["id"] for row in status["windows"]])

    def test_metrics_are_label_free(self):
        status = operations_calendar.analyze([
            window("backup:one", "recovery", 1100, 1400),
            window("restart:one", "disruptive", 1200, 1500, execute=True),
        ], now=1000)
        metrics = operations_calendar.prometheus(status, now=1000)
        self.assertIn("dash_operations_calendar_critical_conflicts 1\n", metrics)
        self.assertIn("dash_operations_calendar_next_window_seconds 100.0\n", metrics)
        self.assertNotIn("{", metrics)


if __name__ == "__main__":
    unittest.main()
