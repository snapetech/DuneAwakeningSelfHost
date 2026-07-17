#!/usr/bin/env python3
import io
import json
import os
import pathlib
import sqlite3
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import credential_lifecycle as lifecycle


def entry(source=None, backup=None, maximum_age=180):
    return {
        "id": "test-credential",
        "title": "Test credential",
        "category": "Tests",
        "source": source or {"type": "env", "key": "TEST_SECRET"},
        "requiredWhen": {"always": True},
        "minimumBytes": 16,
        "placeholders": ["change-me-test"],
        "rotationPolicy": "scheduled",
        "maximumAgeDays": maximum_age,
        "consumers": ["test consumer"],
        "backup": backup or {"type": "env-copy"},
        "documentation": "docs/test.md",
    }


class CredentialLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.env_file = self.root / ".env"
        self.env_file.write_text("TEST_SECRET=not-the-runtime-value\n", encoding="utf-8")
        self.env_file.chmod(0o600)
        self.backups = self.root / "backups"

    def catalog(self, row=None):
        return {"schemaVersion": 1, "credentials": [row or entry()]}

    def store(self, clock=None):
        return lifecycle.ObservationStore(self.root / "state" / "history.sqlite3", self.root / "secrets" / "history.secret", clock=clock)

    def backup(self, members=(), artifacts=(), include_env=True):
        target = self.backups / "20260717T010203Z"
        target.mkdir(parents=True)
        manifest = "created_utc=20260717T010203Z\nenv_archive=.env\nconfig_archive=config.tgz\n"
        (target / "manifest.txt").write_text(manifest, encoding="utf-8")
        if include_env:
            (target / ".env").write_text("redacted-for-test\n", encoding="utf-8")
        with tarfile.open(target / "config.tgz", "w:gz") as archive:
            for name in members:
                payload = b"private material"
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
        for name in artifacts:
            (target / name).write_bytes(b"artifact")
        return target

    def test_repository_catalog_is_strict_and_valid(self):
        catalog = lifecycle.load_catalog(ROOT / "config" / "credential-lifecycle.json")
        self.assertGreaterEqual(len(catalog["credentials"]), 19)
        self.assertEqual(len({row["id"] for row in catalog["credentials"]}), len(catalog["credentials"]))

    def test_secret_material_and_fingerprints_never_leave_result(self):
        secret = "a-private-secret-value-that-must-never-leak"
        self.backup()
        result = lifecycle.evaluate(self.catalog(), self.root, {"TEST_SECRET": secret}, self.env_file, self.backups, self.store(), now=1000)
        rendered = json.dumps(result, sort_keys=True)
        self.assertTrue(result["ok"])
        self.assertNotIn(secret, rendered)
        self.assertNotIn("materialHmac", rendered)
        self.assertNotIn("eventHmac", rendered)
        self.assertEqual(result["history"]["events"], 1)

    def test_observation_chain_deduplicates_and_records_rotation(self):
        now = [1000.0]
        store = self.store(lambda: now[0])
        first = store.observe("test-credential", b"first material long enough")
        same = store.observe("test-credential", b"first material long enough")
        now[0] = 2000.0
        changed = store.observe("test-credential", b"second material long enough")
        self.assertEqual((first["eventType"], same["changed"], changed["eventType"]), ("baseline", False, "rotation"))
        status = store.status()
        self.assertEqual((status["events"], status["rotations"], status["headSequence"]), (2, 1, 2))
        connection = sqlite3.connect(store.database)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("update observations set event_type='baseline' where sequence=2")
        finally:
            connection.close()

    def test_chain_tampering_fails_closed(self):
        store = self.store(lambda: 1000)
        store.observe("test-credential", b"first material long enough")
        connection = sqlite3.connect(store.database)
        try:
            connection.execute("drop trigger credential_observations_no_update")
            connection.execute("update observations set material_hmac=? where sequence=1", ("0" * 64,))
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, "chain invalid"):
            store.status()

    def test_authenticated_head_detects_clean_tail_truncation(self):
        now = [1000.0]
        store = self.store(lambda: now[0])
        store.observe("test-credential", b"first material long enough")
        now[0] = 2000.0
        store.observe("test-credential", b"second material long enough")
        connection = sqlite3.connect(store.database)
        try:
            connection.execute("drop trigger credential_observations_no_delete")
            connection.execute("delete from observations where sequence=2")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, "authenticated anchor"):
            store.status()

    def test_read_only_verification_never_creates_a_missing_key(self):
        store = self.store(lambda: 1000)
        store.observe("test-credential", b"first material long enough")
        store.key_path.unlink()
        with self.assertRaisesRegex(ValueError, "key is missing"):
            lifecycle.verify_database(store.database, store.key_path)
        self.assertFalse(store.key_path.exists())

    def test_read_only_verification_does_not_rewrite_key_mode(self):
        store = self.store(lambda: 1000)
        store.observe("test-credential", b"first material long enough")
        store.key_path.chmod(0o400)
        self.assertTrue(lifecycle.verify_database(store.database, store.key_path, store.anchor_path)["ok"])
        self.assertEqual(0o400, store.key_path.stat().st_mode & 0o777)

    def test_file_permissions_and_symlinks_fail_closed(self):
        secret = self.root / "config" / "secrets" / "test.secret"
        secret.parent.mkdir(parents=True)
        secret.write_bytes(b"long-enough-private-material")
        secret.chmod(0o644)
        row = entry({"type": "file", "pathKey": "TEST_SECRET_FILE", "defaultPath": "config/secrets/test.secret"}, {"type": "config-member", "member": "config/secrets/test.secret"})
        self.backup(["config/secrets/test.secret"])
        result = lifecycle.evaluate(self.catalog(row), self.root, {}, self.env_file, self.backups, None, now=1000)
        self.assertIn("insecure-source-permissions", result["credentials"][0]["findings"])
        secret.chmod(0o600)
        secret.unlink()
        outside = self.root / "outside.secret"
        outside.write_bytes(b"long-enough-private-material")
        secret.symlink_to(outside)
        result = lifecycle.evaluate(self.catalog(row), self.root, {}, self.env_file, self.backups, None, now=1000)
        self.assertEqual(result["credentials"][0]["state"], "invalid-source")

    def test_root_store_repairs_private_artifacts_to_backup_owner(self):
        database = self.root / "backups" / "credential" / "history.sqlite3"
        key = self.root / "config" / "secrets" / "credential.secret"
        anchor = self.root / "backups" / "credential" / "history.anchor.json"
        calls = []
        with mock.patch.object(lifecycle.os, "geteuid", return_value=0), mock.patch.object(lifecycle.os, "chown", side_effect=lambda path, uid, gid: calls.append((pathlib.Path(path), uid, gid))):
            store = lifecycle.ObservationStore(database, key, anchor, owner_uid="1000", owner_gid="1001", clock=lambda: 1000)
            store.observe("fixture", b"private fixture material")
        owned = {path for path, uid, gid in calls if uid == 1000 and gid == 1001}
        self.assertTrue({database, key, anchor, database.parent, key.parent}.issubset(owned))

    def test_backup_contracts_are_evaluated_without_reading_values(self):
        secret = self.root / "config" / "secrets" / "test.secret"
        secret.parent.mkdir(parents=True)
        secret.write_bytes(b"long-enough-private-material")
        secret.chmod(0o600)
        row = entry({"type": "file", "pathKey": "TEST_SECRET_FILE", "defaultPath": "config/secrets/test.secret"}, {"type": "config-member", "member": "config/secrets/test.secret"})
        self.backup([])
        missing = lifecycle.evaluate(self.catalog(row), self.root, {}, self.env_file, self.backups, None, now=1000)
        self.assertIn("backup-uncovered", missing["credentials"][0]["findings"])
        for path in (self.backups / "20260717T010203Z").iterdir():
            path.unlink()
        (self.backups / "20260717T010203Z").rmdir()
        self.backup(["config/secrets/test.secret"])
        covered = lifecycle.evaluate(self.catalog(row), self.root, {}, self.env_file, self.backups, None, now=1000)
        self.assertTrue(covered["credentials"][0]["backupCovered"])

    def test_required_gates_and_placeholder_are_distinct(self):
        row = entry()
        row["requiredWhen"] = {"allGates": ["FEATURE_ENABLED"]}
        optional = lifecycle.evaluate(self.catalog(row), self.root, {}, self.env_file, self.backups, None, now=1000)
        self.assertEqual(optional["credentials"][0]["state"], "not-required")
        required = lifecycle.evaluate(self.catalog(row), self.root, {"FEATURE_ENABLED": "true", "TEST_SECRET": "change-me-test"}, self.env_file, self.backups, None, now=1000)
        self.assertIn("placeholder", required["credentials"][0]["findings"])

    def test_rotation_age_and_label_free_metrics(self):
        now = [1000.0]
        store = self.store(lambda: now[0])
        self.backup()
        material = "long-enough-private-material"
        lifecycle.evaluate(self.catalog(), self.root, {"TEST_SECRET": material}, self.env_file, self.backups, store, now=now[0])
        now[0] += 181 * 86400
        result = lifecycle.evaluate(self.catalog(), self.root, {"TEST_SECRET": material}, self.env_file, self.backups, store, now=now[0])
        self.assertEqual(result["summary"]["overdue"], 1)
        output = lifecycle.metrics(result)
        self.assertIn("dash_credential_lifecycle_rotation_overdue 1\n", output)
        self.assertNotIn("{", output)

    def test_catalog_rejects_unknown_fields_and_escaping_paths(self):
        row = entry({"type": "file", "pathKey": "TEST_SECRET_FILE", "defaultPath": "../escape"})
        path = self.root / "catalog.json"
        path.write_text(json.dumps(self.catalog(row)), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "confined"):
            lifecycle.load_catalog(path)


if __name__ == "__main__":
    unittest.main()
