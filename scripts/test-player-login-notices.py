#!/usr/bin/env python3

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

import player_login_notices as registry


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "player-login-notice.py"


class RegistryTests(unittest.TestCase):
    def test_upsert_list_replace_and_remove_are_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "notices.json"
            first = registry.upsert_notice(105, "First notice.", path)
            self.assertEqual(first["message"], "First notice.")
            replaced = registry.upsert_notice(105, "Updated notice.", path)
            self.assertEqual(replaced["createdAt"], first["createdAt"])
            self.assertEqual(registry.list_notices(path)[0]["message"], "Updated notice.")
            removed = registry.remove_notice(105, path)
            self.assertEqual(removed["accountId"], 105)
            self.assertEqual(registry.list_notices(path), [])

    def test_validation_rejects_bad_ids_and_oversized_messages(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            registry.normalize_notice({"accountId": 0})
        with self.assertRaisesRegex(ValueError, "4096"):
            registry.normalize_notice({"accountId": 1, "message": "x" * 4097})

    def test_runtime_merge_exposes_delivery_and_online_state(self):
        notice = registry.normalize_notice({"accountId": 105, "message": "Notice."})
        rows = registry.merge_runtime([notice], {
            "playerLoginNotices": {
                "105": {"active": False, "deliveredAt": "2026-08-01T15:00:00Z"},
            },
            "onlinePlayers": {"105": {"name": "Snootchy Bootchy"}},
        })
        self.assertFalse(rows[0]["active"])
        self.assertEqual(rows[0]["deliveredAt"], "2026-08-01T15:00:00Z")
        self.assertTrue(rows[0]["online"])
        self.assertEqual(rows[0]["playerName"], "Snootchy Bootchy")


class CliTests(unittest.TestCase):
    def run_cli(self, path, *args):
        return subprocess.run(
            [sys.executable, str(CLI), "--file", str(path), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_cli_add_list_remove_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "notices.json"
            added = self.run_cli(path, "--json", "add", "--account-id", "105", "--message", "Queued.")
            self.assertEqual(added.returncode, 0, added.stderr)
            self.assertEqual(json.loads(added.stdout)["notice"]["accountId"], 105)
            listed = self.run_cli(path, "--json", "list")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(len(json.loads(listed.stdout)["notices"]), 1)
            removed = self.run_cli(path, "--json", "remove", "--account-id", "105")
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertIsNotNone(json.loads(removed.stdout)["removed"])


if __name__ == "__main__":
    unittest.main()
