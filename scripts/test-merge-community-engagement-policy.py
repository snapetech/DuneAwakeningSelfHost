#!/usr/bin/env python3
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("merge_engagement", ROOT / "scripts" / "merge-community-engagement-policy.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MergeCommunityEngagementPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.active = self.root / "community-rewards.json"
        self.example = self.root / "community-rewards.example.json"
        self.backups = self.root / "backups"
        example = json.loads((ROOT / "config" / "community-rewards.example.json").read_text(encoding="utf-8"))
        active = dict(example)
        active.pop("engagementRewards")
        active["offers"] = [dict(example["offers"][0], id="private", name="Private Offer", operatorMarker=True)]
        active["tracks"] = []
        self.active.write_text(json.dumps(active), encoding="utf-8")
        self.active.chmod(0o600)
        self.example.write_text(json.dumps(example), encoding="utf-8")
        self.now = dt.datetime(2026, 7, 16, 15, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_merge_preserves_private_catalog_and_creates_locked_backup(self):
        before = self.active.read_bytes()
        result = MODULE.merge(self.active, self.example, self.backups, now=self.now)
        merged = json.loads(self.active.read_text(encoding="utf-8"))

        self.assertTrue(result["changed"])
        self.assertEqual("private", merged["offers"][0]["id"])
        self.assertTrue(merged["offers"][0]["operatorMarker"])
        self.assertTrue(merged["engagementRewards"]["enabled"])
        self.assertEqual(["season-1"], result["tracksAdded"])
        self.assertEqual("season-1", merged["tracks"][0]["id"])
        backup = Path(result["backup"])
        self.assertEqual(before, backup.read_bytes())
        self.assertEqual(0o600, backup.stat().st_mode & 0o777)
        self.assertEqual(0o600, self.active.stat().st_mode & 0o777)
        self.assertEqual(0o700, self.backups.stat().st_mode & 0o777)

    def test_existing_policy_is_never_overwritten(self):
        active = json.loads(self.active.read_text(encoding="utf-8"))
        active["engagementRewards"] = {"enabled": False, "operatorChoice": True}
        self.active.write_text(json.dumps(active), encoding="utf-8")
        before = self.active.read_bytes()

        result = MODULE.merge(self.active, self.example, self.backups, now=self.now)

        self.assertFalse(result["changed"])
        self.assertEqual(before, self.active.read_bytes())
        self.assertFalse(self.backups.exists())

    def test_dry_run_does_not_write_or_create_backup(self):
        before = self.active.read_bytes()
        result = MODULE.merge(self.active, self.example, self.backups, dry_run=True, now=self.now)
        self.assertTrue(result["planned"])
        self.assertFalse(result["changed"])
        self.assertEqual(before, self.active.read_bytes())
        self.assertFalse(self.backups.exists())

    def test_schema_mismatch_fails_without_writes(self):
        example = json.loads(self.example.read_text(encoding="utf-8"))
        example["version"] = 2
        self.example.write_text(json.dumps(example), encoding="utf-8")
        before = self.active.read_bytes()
        with self.assertRaisesRegex(ValueError, "schema versions differ"):
            MODULE.merge(self.active, self.example, self.backups, now=self.now)
        self.assertEqual(before, self.active.read_bytes())
        self.assertFalse(self.backups.exists())

    def test_disabled_required_track_fails_without_writes(self):
        active = json.loads(self.active.read_text(encoding="utf-8"))
        active["tracks"] = [{"id": "season-1", "enabled": False}]
        self.active.write_text(json.dumps(active), encoding="utf-8")
        before = self.active.read_bytes()
        with self.assertRaisesRegex(ValueError, "requires disabled operator track"):
            MODULE.merge(self.active, self.example, self.backups, now=self.now)
        self.assertEqual(before, self.active.read_bytes())
        self.assertFalse(self.backups.exists())

    def test_existing_backup_name_is_not_overwritten(self):
        self.backups.mkdir()
        collision = self.backups / "community-rewards-before-engagement-20260716T150000Z.json"
        collision.write_text("evidence", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
            MODULE.merge(self.active, self.example, self.backups, now=self.now)
        self.assertEqual("evidence", collision.read_text(encoding="utf-8"))
        self.assertNotIn("engagementRewards", json.loads(self.active.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
