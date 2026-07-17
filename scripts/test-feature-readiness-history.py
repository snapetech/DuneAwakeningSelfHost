#!/usr/bin/env python3
import importlib.util
import contextlib
import pathlib
import shutil
import sqlite3
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("feature_readiness_history", ROOT / "admin" / "feature_readiness_history.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def readiness(*states):
    features = [
        {"id": feature_id, "state": state, "active": active}
        for feature_id, state, active in states
    ]
    return {
        "schemaVersion": "dash-feature-readiness/v1",
        "features": features,
        "secretValuesReturned": False,
    }


class FeatureReadinessHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        self.clock = [1000.0]
        self.store = MODULE.Store(root / "history.sqlite3", root / "history.secret", now=lambda: self.clock[0])
        self.store.initialize()

    def record(self, *states, commit="a" * 40):
        result = self.store.record(readiness(*states), source="test", commit=commit)
        self.clock[0] += 1
        return result

    def test_baseline_deduplicates_and_returns_no_secret_material(self):
        first = self.record(("alpha", "ready", True), ("beta", "disabled", False))
        duplicate = self.record(("beta", "disabled", False), ("alpha", "ready", True))
        self.assertEqual("baseline", first["kind"])
        self.assertFalse(duplicate["changed"])
        status = self.store.status()
        self.assertTrue(status["ok"])
        self.assertEqual(1, status["summary"]["events"])
        rendered = str(status)
        self.assertNotIn(self.store.secret_file.read_text().strip(), rendered)

    def test_regression_improvement_and_mixed_transitions_are_exact(self):
        self.record(("alpha", "ready", True), ("beta", "external-blocked", True))
        regression = self.record(("alpha", "degraded", True), ("beta", "external-blocked", True))
        self.assertEqual("regression", regression["kind"])
        self.assertEqual(["alpha"], [row["id"] for row in regression["changes"]])
        improvement = self.record(("alpha", "ready", True), ("beta", "external-blocked", True))
        self.assertEqual("improvement", improvement["kind"])
        mixed = self.record(("alpha", "blocked", True), ("beta", "ready", True))
        self.assertEqual("mixed", mixed["kind"])
        directions = {row["id"]: row["direction"] for row in mixed["changes"]}
        self.assertEqual({"alpha": "regression", "beta": "improvement"}, directions)

    def test_chain_and_database_tampering_fail_closed(self):
        self.record(("alpha", "ready", True))
        self.record(("alpha", "degraded", True))
        with contextlib.closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute("drop trigger transitions_no_update")
            connection.execute("update transitions set kind='change' where sequence=2")
        self.assertFalse(self.store.integrity()["ok"])
        with self.assertRaisesRegex(RuntimeError, "schema|HMAC chain"):
            self.record(("alpha", "ready", True))

    def test_append_only_triggers_reject_update_and_delete(self):
        self.record(("alpha", "ready", True))
        with contextlib.closing(sqlite3.connect(self.store.path)) as connection, connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("update transitions set source='changed'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("delete from transitions")

    def test_missing_append_only_trigger_invalidates_integrity(self):
        self.record(("alpha", "ready", True))
        with contextlib.closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute("drop trigger transitions_no_delete")
        self.assertFalse(self.store.integrity()["ok"])

    def test_input_validation_rejects_unknown_schema_duplicate_ids_and_states(self):
        cases = [
            {"schemaVersion": "wrong", "features": []},
            readiness(("alpha", "ready", True), ("alpha", "ready", True)),
            readiness(("alpha", "invented", True)),
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.record(value)

    def test_metrics_are_label_free_and_include_chain_state(self):
        self.record(("alpha", "ready", True))
        self.record(("alpha", "blocked", True))
        metrics = self.store.prometheus()
        self.assertIn("dash_feature_readiness_history_valid 1", metrics)
        self.assertIn("dash_feature_readiness_history_regressions_total 1", metrics)
        self.assertNotIn("{", metrics)

    def test_detached_database_and_matching_key_verify_together(self):
        self.record(("alpha", "ready", True))
        root = pathlib.Path(self.temp.name)
        snapshot = root / "snapshot.sqlite3"
        key = root / "snapshot.secret"
        with contextlib.closing(sqlite3.connect(f"file:{self.store.path}?mode=ro", uri=True)) as source, contextlib.closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
        shutil.copyfile(self.store.secret_file, key)
        key.chmod(0o600)
        self.assertTrue(MODULE.verify_database(snapshot, key)["ok"])
        key.write_text("00" * 32 + "\n", encoding="utf-8")
        key.chmod(0o600)
        self.assertFalse(MODULE.verify_database(snapshot, key)["ok"])


if __name__ == "__main__":
    unittest.main()
