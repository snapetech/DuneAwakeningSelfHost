#!/usr/bin/env python3
import datetime
import contextlib
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "admin"))
import moderation


class ModerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.temp.name) / "state" / "moderation.sqlite3"
        self.store = moderation.Store(self.path, owner_uid=os.getuid(), owner_gid=os.getgid()).initialize()
        self.case = self.store.create_case({"accountId": 42, "characterName": "Chani", "funcomId": "fls-42", "platformId": "steam-42", "summary": "test case", "severity": "high"}, "tester")

    def tearDown(self):
        self.temp.cleanup()

    def test_case_note_and_status_history_is_append_only(self):
        self.store.add_note(self.case["id"], "first note", "tester")
        updated = self.store.update_case(self.case["id"], {"status": "investigating", "note": "triaged"}, "tester")
        self.assertEqual(updated["status"], "investigating")
        self.assertGreaterEqual(len(updated["events"]), 3)
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("delete from case_events")

    def test_permanent_ban_matches_every_identity(self):
        result = self.store.ban(self.case["id"], {"reason": "policy"}, "tester")
        ban = result["ban"]
        self.assertEqual(ban["account_id"], 42)
        self.assertEqual(self.store.active_ban(42)["id"], ban["id"])
        self.assertEqual(self.store.active_ban(None, "fls-42")["id"], ban["id"])
        self.assertEqual(self.store.active_ban(None, "", "steam-42")["id"], ban["id"])

    def test_unban_is_idempotent(self):
        ban_id = self.store.ban(self.case["id"], {"reason": "policy"}, "tester")["ban"]["id"]
        first = self.store.unban(ban_id, "tester", "appeal accepted")
        second = self.store.unban(ban_id, "tester", "again")
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertIsNone(self.store.active_ban(42))

    def test_temporary_ban_expires(self):
        ban_id = self.store.ban(self.case["id"], {"reason": "short", "durationHours": 1}, "tester")["ban"]["id"]
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            connection.execute("update bans set expires_at=? where id=?", ((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=1)).isoformat(), ban_id))
            connection.commit()
        self.assertEqual(self.store.expire_bans(), 1)
        self.assertIsNone(self.store.active_ban(42))

    def test_allowlist_registry_and_explicit_policy(self):
        self.store.set_allowlist("account", "42", "Chani", "tester")
        self.assertTrue(self.store.allowlisted(42))
        self.assertFalse(self.store.allowlisted(43))
        self.assertFalse(self.store.allowlist_enforcement_enabled())
        self.store.set_allowlist_enforcement(True)
        self.assertTrue(self.store.allowlist_enforcement_enabled())
        self.store.set_allowlist("account", "42", "", "tester", remove=True)
        self.assertFalse(self.store.allowlisted(42))

    def test_presence_sessions_and_coarse_heatmap(self):
        first = self.store.record_presence([{"account_id": 42, "character_name": "Chani", "funcom_id": "fls-42", "platform_id": "steam-42", "actor_map": "HaggaBasin", "x": 25100, "y": -100}], cell_size=25000)
        self.assertEqual(first["online"], 1)
        self.store.record_presence([], cell_size=25000)
        status = self.store.status(account_id=42)
        self.assertIsNotNone(status["sessions"][0]["ended_at"])
        self.assertEqual(status["heatmap"][0]["cell_x"], 1)
        self.assertEqual(status["heatmap"][0]["cell_y"], -1)

    def test_security_normalization_redacts_and_deduplicates(self):
        line = "2026 BattleEye authentication failed from 192.168.1.22:7777 user admin@example.test token=secret"
        event = moderation.normalize_security_line("login", line)
        self.assertEqual(event["category"], "anti-cheat")
        self.assertNotIn("192.168.1.22", event["summary"])
        self.assertNotIn("admin@example.test", event["summary"])
        self.assertNotIn("token=secret", event["summary"])
        self.assertNotIn("\x1b", moderation.redact_security_text("\x1b[0mBattleEye alert"))
        self.assertEqual(self.store.ingest_security([event, event]), 1)
        self.assertEqual(len(self.store.status()["securityEvents"]), 1)

    def test_internal_http_disconnect_is_not_a_moderation_event(self):
        self.assertIsNone(moderation.normalize_security_line("survival", "LogHttp: libcurl: Too old connection, disconnect it"))

    def test_enforcement_cooldowns_are_separate(self):
        ban_id = self.store.ban(self.case["id"], {"reason": "policy"}, "tester")["ban"]["id"]
        self.store.record_enforcement(ban_id, 42, True, "queued")
        self.assertTrue(self.store.recently_enforced(ban_id, 42, 60))
        self.assertFalse(self.store.recently_policy_enforced(42, 60))
        self.store.record_policy_enforcement(42, True, "queued")
        self.assertTrue(self.store.recently_policy_enforced(42, 60))

    def test_permissions_are_private(self):
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_validation_rejects_empty_or_invalid_cases(self):
        with self.assertRaises(ValueError):
            self.store.create_case({"summary": ""}, "tester")
        with self.assertRaises(ValueError):
            self.store.create_case({"summary": "x", "severity": "catastrophic"}, "tester")


if __name__ == "__main__":
    unittest.main()
