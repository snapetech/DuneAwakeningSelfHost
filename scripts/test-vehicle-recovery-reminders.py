#!/usr/bin/env python3

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import vehicle_recovery_reminders as registry


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "vehicle-recovery-reminder.py"


class RegistryTests(unittest.TestCase):
    def test_upsert_replace_list_and_remove_are_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "reminders.json"
            first = registry.upsert_reminder(5247, [22279, 22296], "Contact an admin.", path)
            replaced = registry.upsert_reminder(5247, [22296], "Updated.", path)
            self.assertEqual(first["createdAt"], replaced["createdAt"])
            self.assertEqual(registry.list_reminders(path)[0]["vehicleIds"], [22296])
            self.assertEqual(registry.remove_reminder(5247, path)["accountId"], 5247)
            self.assertEqual(registry.list_reminders(path), [])

    def test_validation_rejects_bad_ids_and_oversized_messages(self):
        with self.assertRaisesRegex(ValueError, "positive integer"):
            registry.normalize_reminder({"accountId": 0, "vehicleIds": [1]})
        with self.assertRaisesRegex(ValueError, "at most 4096"):
            registry.normalize_reminder({"accountId": 1, "vehicleIds": [1], "message": "x" * 4097})
        with self.assertRaisesRegex(ValueError, "at least one"):
            registry.normalize_reminder({"accountId": 1, "vehicleIds": []})

    def test_status_parser_and_sql_are_conservative(self):
        status = registry.parse_status_output(json.dumps([
            {"vehicleId": 22279, "actorExists": True, "backupExists": True, "vehicleBackupState": True, "ownerActive": True, "restored": False},
            {"vehicleId": 22296, "actorExists": True, "backupExists": False, "vehicleBackupState": False, "ownerActive": True, "restored": True},
        ]))
        self.assertFalse(status["restored"])
        self.assertTrue(registry.parse_status_output(json.dumps([
            {"vehicleId": 22279, "restored": True}, {"vehicleId": 22296, "restored": True}
        ]))["restored"])
        self.assertFalse(registry.parse_status_output("bad")["ok"])
        sql = registry.status_sql({"accountId": 5247, "vehicleIds": [22279, 22296]})
        self.assertIn("account_id=5247", sql)
        self.assertIn("array[22279,22296]::bigint[]", sql)
        self.assertIn("state='VehicleBackup'", sql)
        self.assertIn("state='VehicleRecovery'", sql)

    def test_runtime_merge_exposes_status_and_online_state(self):
        reminder = registry.normalize_reminder({"accountId": 5247, "vehicleIds": [22279, 22296]})
        rows = registry.merge_runtime([reminder], {
            "vehicleRecoveryReminders": {"5247": {
                "active": True,
                "lastStatus": {"restored": False},
                "lastSentAt": "2026-07-31T19:00:00Z",
            }},
            "onlinePlayers": {"5247": {"name": "Mara Jade Skywalker"}},
        })
        self.assertTrue(rows[0]["online"])
        self.assertEqual(rows[0]["playerName"], "Mara Jade Skywalker")
        self.assertFalse(rows[0]["lastStatus"]["restored"])


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
            added = self.run_cli(path, "--json", "add", "--account-id", "5247", "--vehicle-id", "22279", "--vehicle-id", "22296")
            self.assertEqual(added.returncode, 0, added.stderr)
            self.assertEqual(json.loads(added.stdout)["reminder"]["vehicleIds"], [22279, 22296])
            listed = self.run_cli(path, "--json", "list")
            self.assertEqual(len(json.loads(listed.stdout)["reminders"]), 1)
            removed = self.run_cli(path, "--json", "remove", "--account-id", "5247")
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertEqual(json.loads(removed.stdout)["removed"]["accountId"], 5247)


if __name__ == "__main__":
    unittest.main()
