#!/usr/bin/env python3

import importlib.util
import json
import pathlib
import stat
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("player_identity", ROOT / "admin" / "player_identity.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeConnection:
    def __init__(self):
        self.autocommit = True
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class PlayerIdentityTests(unittest.TestCase):
    def test_integrity_reports_duplicates_orphans_and_never_repairs_duplicates(self):
        def query(sql, params=()):
            if "with counts as" in sql:
                return [{
                    "player_state_rows": 8, "account_rows": 5, "duplicate_accounts": 1,
                    "duplicate_excess_rows": 2, "orphan_rows": 1,
                    "missing_pawn_references": 1, "missing_controller_references": 0,
                }]
            if "having count(*)>1" in sql:
                return [{"account_id": 7, "row_count": 3, "player_state_ids": [13, 12, 11]}]
            if "not exists" in sql and "last_login_time" in sql:
                return [{"player_state_id": 99, "account_id": 88}]
            raise AssertionError(sql)

        result = MODULE.integrity(query)
        self.assertFalse(result["summary"]["healthy"])
        self.assertEqual(result["summary"]["duplicate_excess_rows"], 2)
        self.assertEqual(result["repairable"], {"orphanRows": 1})
        self.assertIn("never deleted", result["duplicatePolicy"])

    def test_cleanup_plan_fingerprint_changes_with_orphan_evidence(self):
        first = MODULE.cleanup_plan(lambda sql, params=(): [{"orphan_rows": 2, "orphan_digest": "a", "first_id": 4, "last_id": 8}])
        second = MODULE.cleanup_plan(lambda sql, params=(): [{"orphan_rows": 2, "orphan_digest": "b", "first_id": 4, "last_id": 8}])
        self.assertTrue(first["canExecute"])
        self.assertNotEqual(first["expectedFingerprint"], second["expectedFingerprint"])
        self.assertEqual(first["confirm"], MODULE.CONFIRM_CLEANUP)

    def test_character_plan_selects_canonical_row_and_requires_every_row_offline(self):
        calls = []

        def query(sql, params=()):
            calls.append(sql)
            return [{
                "account_id": 42, "fls_id": "FLS-42", "funcom_id": "funcom-42",
                "platform_name": "Steam", "platform_id": "7656", "player_state_id": 9,
                "character_name": "Chani", "online_status": "Offline", "life_state": "Alive",
                "last_login_time": "2026-07-17", "player_controller_id": 100,
                "player_pawn_id": 101, "state_row_count": 2, "non_offline_rows": 0,
                "native_delete_available": True,
            }]

        plan = MODULE.character_plan(query, 42)
        self.assertTrue(plan["canExecute"])
        self.assertEqual(plan["confirm"], "DELETE CHARACTER 42")
        self.assertIn("order by ps2.last_login_time desc nulls last,ps2.id desc", calls[0])
        blocked = MODULE.character_plan(lambda sql, params=(): [{**query(sql, params)[0], "non_offline_rows": 1}], 42)
        self.assertFalse(blocked["canExecute"])
        self.assertIn("offline", blocked["blockers"][0])

    def test_canonical_lateral_rejects_untrusted_sql_fragments(self):
        self.assertIn("limit 1", MODULE.canonical_lateral("a.id"))
        with self.assertRaises(ValueError):
            MODULE.canonical_lateral("a.id); drop table dune.accounts;--")

    def test_cleanup_is_backup_first_transactional_verified_and_receipted(self):
        conn = FakeConnection()
        plans = [
            {"canExecute": True, "expectedFingerprint": "f" * 64, "evidence": {"orphanRows": 2}},
            {"canExecute": True, "expectedFingerprint": "f" * 64, "evidence": {"orphanRows": 2}},
            {"canExecute": False, "expectedFingerprint": "z" * 64, "evidence": {"orphanRows": 0}},
        ]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(MODULE, "cleanup_plan", side_effect=plans), \
             mock.patch.object(MODULE, "_connection_query", return_value=[{"id": 10, "account_id": 90}, {"id": 11, "account_id": 91}]):
            result = MODULE.cleanup_orphans(
                lambda: conn, lambda: {"path": "/backup/full.dump", "bytes": 4}, tmp,
                "f" * 64, MODULE.CONFIRM_CLEANUP, "operator-a",
            )
            receipt = pathlib.Path(result["receipt"]["path"])
            self.assertEqual(json.loads(receipt.read_text())["action"], "cleanup-orphans")
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            self.assertFalse(list(pathlib.Path(tmp).glob("pending-*.json")))
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertTrue(conn.closed)
        self.assertEqual(result["deletedRows"], 2)

    def test_cleanup_rejects_stale_preview_before_backup(self):
        backup = mock.Mock()
        with mock.patch.object(MODULE, "cleanup_plan", return_value={"canExecute": True, "expectedFingerprint": "a", "evidence": {"orphanRows": 1}}):
            with self.assertRaisesRegex(RuntimeError, "changed after preview"):
                MODULE.cleanup_orphans(lambda: FakeConnection(), backup, "/tmp/nope", "b", MODULE.CONFIRM_CLEANUP)
        backup.assert_not_called()

    def test_committed_cleanup_reports_pending_receipt_when_finalization_fails(self):
        conn = FakeConnection()
        plans = [
            {"canExecute": True, "expectedFingerprint": "f" * 64, "evidence": {"orphanRows": 1}},
            {"canExecute": True, "expectedFingerprint": "f" * 64, "evidence": {"orphanRows": 1}},
            {"canExecute": False, "expectedFingerprint": "z", "evidence": {"orphanRows": 0}},
        ]
        original_write = MODULE._write_receipt
        writes = []

        def fail_final(path, value):
            writes.append(path)
            if len(writes) == 2:
                raise OSError("receipt disk full")
            return original_write(path, value)

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(MODULE, "cleanup_plan", side_effect=plans), \
             mock.patch.object(MODULE, "_connection_query", return_value=[{"id": 10, "account_id": 90}]), \
             mock.patch.object(MODULE, "_write_receipt", side_effect=fail_final):
            result = MODULE.cleanup_orphans(lambda: conn, lambda: {"path": "/b", "bytes": 1}, tmp, "f" * 64, MODULE.CONFIRM_CLEANUP)
            self.assertEqual("pending-finalization-failed", result["receipt"]["status"])
            self.assertIn("disk full", result["receipt"]["error"])
            self.assertTrue(pathlib.Path(result["receipt"]["path"]).exists())
        self.assertTrue(conn.committed)

    def test_delete_character_uses_native_function_cleans_orphans_and_verifies(self):
        conn = FakeConnection()
        plan = {
            "canExecute": True, "blockers": [], "expectedFingerprint": "f" * 64,
            "accountId": 42, "character": {"flsId": "FLS-42", "characterName": "Chani"},
        }
        query_results = [
            [],
            [{"id": 9}],
            [{"deleted": True}],
            [{"id": 9, "account_id": 42}, {"id": 77, "account_id": 999}],
            [{"account_exists": False, "player_state_exists": False, "orphan_rows": 0}],
        ]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(MODULE, "character_plan", side_effect=[plan, plan]), \
             mock.patch.object(MODULE, "_connection_query", side_effect=query_results):
            result = MODULE.delete_character(
                lambda: conn, lambda: {"path": "/backup/full.dump", "bytes": 5}, tmp,
                42, "requested by account owner", "f" * 64, "DELETE CHARACTER 42", "operator-a",
            )
        self.assertTrue(result["nativeDeleted"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["orphanRowsCleaned"], 2)
        self.assertTrue(conn.committed)

    def test_delete_character_rolls_back_failed_verification(self):
        conn = FakeConnection()
        plan = {
            "canExecute": True, "blockers": [], "expectedFingerprint": "f" * 64,
            "accountId": 42, "character": {"flsId": "FLS-42", "characterName": "Chani"},
        }
        results = [[], [{"id": 9}], [{"deleted": True}], [{"id": 9, "account_id": 42}], [{"account_exists": True, "player_state_exists": False, "orphan_rows": 0}]]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(MODULE, "character_plan", side_effect=[plan, plan]), \
             mock.patch.object(MODULE, "_connection_query", side_effect=results):
            with self.assertRaisesRegex(RuntimeError, "verification failed"):
                MODULE.delete_character(lambda: conn, lambda: {"path": "/b", "bytes": 1}, tmp, 42, "operator request", "f" * 64, "DELETE CHARACTER 42")
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)


if __name__ == "__main__":
    unittest.main()
