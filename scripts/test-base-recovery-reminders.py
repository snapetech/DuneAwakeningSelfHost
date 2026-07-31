#!/usr/bin/env python3

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

import base_recovery_reminders as registry


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "base-recovery-reminder.py"
sys.path.insert(0, str(ROOT / "scripts"))


class RegistryTests(unittest.TestCase):
    def test_upsert_list_replace_and_remove_are_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "reminders.json"
            first = registry.upsert_reminder(5247, 127, 22323, "Contact an admin.", path)
            self.assertEqual(first["message"], "Contact an admin.")
            replaced = registry.upsert_reminder(5247, 128, 22324, "Updated.", path)
            self.assertEqual(replaced["createdAt"], first["createdAt"])
            self.assertEqual(registry.list_reminders(path)[0]["backupId"], 128)
            removed = registry.remove_reminder(5247, path)
            self.assertEqual(removed["totemId"], 22324)
            self.assertEqual(registry.list_reminders(path), [])

    def test_validation_rejects_bad_ids_and_oversized_messages(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            registry.normalize_reminder({"accountId": 0, "backupId": 1, "totemId": 1})
        with self.assertRaisesRegex(ValueError, "4096"):
            registry.normalize_reminder({"accountId": 1, "backupId": 1, "totemId": 1, "message": "x" * 4097})

    def test_runtime_merge_exposes_active_restored_online_and_send_state(self):
        reminder = registry.normalize_reminder({"accountId": 5247, "backupId": 127, "totemId": 22323})
        rows = registry.merge_runtime([reminder], {
            "baseRecoveryReminders": {
                "5247": {
                    "active": False,
                    "restoredAt": "2026-07-31T20:00:00Z",
                    "lastSentAt": "2026-07-31T19:00:00Z",
                    "lastStatus": {"restored": True},
                }
            },
            "onlinePlayers": {"5247": {"name": "Mara Jade Skywalker"}},
        })
        self.assertFalse(rows[0]["active"])
        self.assertTrue(rows[0]["online"])
        self.assertEqual(rows[0]["playerName"], "Mara Jade Skywalker")
        self.assertEqual(rows[0]["lastSentAt"], "2026-07-31T19:00:00Z")

    def test_status_parser_only_declares_restore_for_all_conservative_conditions(self):
        self.assertTrue(registry.parse_status_output("f\tt\tf\tt\n")["restored"])
        self.assertFalse(registry.parse_status_output("f\tf\tf\tt\n")["restored"])
        self.assertFalse(registry.parse_status_output("f\tt\tt\tt\n")["restored"])
        self.assertFalse(registry.parse_status_output("f\tt\tf\tf\n")["restored"])
        self.assertFalse(registry.parse_status_output("bad")["ok"])

    def test_status_sql_binds_all_native_recovery_identifiers(self):
        sql = registry.status_sql({"accountId": 5247, "backupId": 127, "totemId": 22323})
        self.assertIn("bb.id = 127", sql)
        self.assertIn("par.permission_actor_id = 22323", sql)
        self.assertIn("ps.account_id = 5247", sql)


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
            path = pathlib.Path(tmp) / "reminders.json"
            added = self.run_cli(path, "--json", "add", "--account-id", "5247", "--backup-id", "127", "--totem-id", "22323")
            self.assertEqual(added.returncode, 0, added.stderr)
            self.assertEqual(json.loads(added.stdout)["reminder"]["accountId"], 5247)
            listed = self.run_cli(path, "--json", "list")
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(len(json.loads(listed.stdout)["reminders"]), 1)
            removed = self.run_cli(path, "--json", "remove", "--account-id", "5247")
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertIsNotNone(json.loads(removed.stdout)["removed"])


if __name__ == "__main__":
    unittest.main()
