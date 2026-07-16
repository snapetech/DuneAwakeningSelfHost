#!/usr/bin/env python3

import importlib.util
import json
import pathlib
import stat
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("base_retirement", ROOT / "admin" / "base_retirement.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def source_row(**overrides):
    value = {
        "totem_id": 44,
        "owner_entity_id": 4444,
        "fgl_entity_count": 1,
        "actor_name": "Sietch Tabr",
        "map": "HaggaBasin",
        "partition_id": 3,
        "partition_server_id": None,
        "active_server_id": None,
        "building_count": 2,
        "piece_count": 80,
        "placeable_count": 5,
        "existing_backup_count": 0,
        "native_function_available": True,
        "piece_hash": "a" * 32,
        "placeable_hash": "b" * 32,
        "permission_hash": "c" * 32,
        "owners": [{"playerId": 46, "rank": 1, "accountId": 9, "characterName": "Chani", "onlineStatus": "Offline"}],
    }
    value.update(overrides)
    return value


class FakeCursor:
    description = None

    def __init__(self, calls):
        self.calls = calls
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.sql = " ".join(sql.split())
        self.calls.append((self.sql, tuple(params)))

    def fetchone(self):
        if "from dune.totems" in self.sql:
            return (44,)
        if "base_backup_save_from_totem" in self.sql:
            return (77,)
        return (1,)


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.autocommit = True
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return FakeCursor(self.calls)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class BaseRetirementTests(unittest.TestCase):
    def query(self, row=None, recovery_status="Offline"):
        row = row or source_row()

        def query(sql, params=()):
            if "with base as" in sql:
                return [row]
            if "from dune.player_state ps where ps.player_controller_id" in sql:
                return [{"player_controller_id": 46, "account_id": 9, "character_name": "Chani", "online_status": recovery_status}]
            raise AssertionError(sql)

        return query

    def test_scan_classifies_owned_and_fingerprints_content(self):
        first = MODULE.scan(self.query())[0]
        second = MODULE.scan(self.query(source_row(piece_hash="d" * 32)))[0]
        self.assertEqual(first["status"], "owned")
        self.assertEqual(first["pieceCount"], 80)
        self.assertEqual(len(first["fingerprint"]), 64)
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_scan_classifies_orphan_partial_and_unknown(self):
        orphan = source_row(owners=[{"playerId": 99, "rank": 1, "accountId": None, "onlineStatus": "unknown"}])
        partial = source_row(owners=[
            {"playerId": 46, "rank": 1, "accountId": 9, "onlineStatus": "Offline"},
            {"playerId": 99, "rank": 2, "accountId": None, "onlineStatus": "unknown"},
        ])
        unknown = source_row(owners=[])
        self.assertEqual(MODULE.scan(self.query(orphan))[0]["status"], "orphaned")
        self.assertEqual(MODULE.scan(self.query(partial))[0]["status"], "partial-missing")
        self.assertEqual(MODULE.scan(self.query(unknown))[0]["status"], "unknown-owner")

    def test_plan_auto_selects_the_single_rank_one_owner(self):
        plan = MODULE.plan(self.query(), 44)
        self.assertTrue(plan["canExecute"])
        self.assertEqual(plan["recoveryPlayer"]["playerId"], 46)
        self.assertEqual(plan["confirm"], "ARCHIVE BASE 44")
        self.assertTrue(plan["gameRecoverable"])
        self.assertFalse(plan["destructiveDelete"])

    def test_plan_blocks_active_partition_online_owner_and_existing_backup(self):
        row = source_row(
            partition_server_id="server-1",
            active_server_id="server-1",
            existing_backup_count=1,
            fgl_entity_count=2,
            native_function_available=False,
            owners=[{"playerId": 46, "rank": 1, "accountId": 9, "characterName": "Chani", "onlineStatus": "Online"}],
        )
        plan = MODULE.plan(self.query(row, recovery_status="Online"), 44, 46)
        self.assertFalse(plan["canExecute"])
        self.assertEqual(len(plan["blockers"]), 6)

    def test_plan_requires_unambiguous_recovery_owner(self):
        row = source_row(owners=[])
        with self.assertRaisesRegex(ValueError, "choose one current offline"):
            MODULE.plan(self.query(row), 44)

    def ready_plan(self, fingerprint="f" * 64):
        return {
            "canExecute": True,
            "blockers": [],
            "expectedFingerprint": fingerprint,
            "base": {"totemId": 44},
            "recoveryPlayer": {"playerId": 46},
        }

    def test_archive_is_backup_first_native_verified_and_receipted(self):
        conn = FakeConnection()
        verification = [{"id": 77, "player_id": 46, "linked_actor_count": 6, "permission_actor_count": 0, "permission_rank_count": 0, "totem_linked": True}]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(MODULE, "plan", return_value=self.ready_plan()), \
             mock.patch.object(MODULE, "_connection_query", return_value=verification):
            result = MODULE.archive(
                lambda: conn,
                lambda: {"path": "/safe/full.dump", "bytes": 1234},
                pathlib.Path(tmp),
                totem_id=44,
                recovery_player_id=46,
                expected_fingerprint="f" * 64,
                confirm="ARCHIVE BASE 44",
                principal="operator-a",
            )
            receipt = pathlib.Path(result["receipt"])
            payload = json.loads(receipt.read_text())
            self.assertEqual(payload["status"], "committed")
            self.assertEqual(payload["baseBackupId"], 77)
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            self.assertFalse(list(pathlib.Path(tmp).glob("pending-*.json")))
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertTrue(conn.closed)
        self.assertTrue(any("base_backup_save_from_totem" in sql for sql, _ in conn.calls))

    def test_archive_rejects_stale_preview_before_backup(self):
        conn = FakeConnection()
        backup = mock.Mock(return_value={"path": "/unsafe.dump", "bytes": 1})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(MODULE, "plan", return_value=self.ready_plan("e" * 64)):
            with self.assertRaisesRegex(RuntimeError, "changed after preview"):
                MODULE.archive(lambda: conn, backup, tmp, totem_id=44, recovery_player_id=46, expected_fingerprint="f" * 64, confirm="ARCHIVE BASE 44")
        backup.assert_not_called()
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)

    def test_archive_rolls_back_failed_native_verification_and_keeps_pending_receipt(self):
        conn = FakeConnection()
        verification = [{"id": 77, "player_id": 46, "linked_actor_count": 0, "permission_actor_count": 1, "permission_rank_count": 1, "totem_linked": False}]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(MODULE, "plan", return_value=self.ready_plan()), \
             mock.patch.object(MODULE, "_connection_query", return_value=verification):
            with self.assertRaisesRegex(RuntimeError, "verification failed"):
                MODULE.archive(lambda: conn, lambda: {"path": "/safe/full.dump", "bytes": 4}, tmp, totem_id=44, recovery_player_id=46, expected_fingerprint="f" * 64, confirm="ARCHIVE BASE 44")
            pending = list(pathlib.Path(tmp).glob("pending-*.json"))
            self.assertEqual(len(pending), 1)
            self.assertEqual(json.loads(pending[0].read_text())["status"], "pending")
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)

    def test_archive_reports_committed_when_final_receipt_write_fails(self):
        conn = FakeConnection()
        verification = [{"id": 77, "player_id": 46, "linked_actor_count": 6, "permission_actor_count": 0, "permission_rank_count": 0, "totem_linked": True}]
        original_write = MODULE._write_receipt
        writes = []

        def fail_second_write(path, value):
            writes.append(path)
            if len(writes) == 2:
                raise OSError("receipt disk full")
            return original_write(path, value)

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(MODULE, "plan", return_value=self.ready_plan()), \
             mock.patch.object(MODULE, "_connection_query", return_value=verification), \
             mock.patch.object(MODULE, "_write_receipt", side_effect=fail_second_write):
            result = MODULE.archive(lambda: conn, lambda: {"path": "/safe/full.dump", "bytes": 4}, tmp, totem_id=44, recovery_player_id=46, expected_fingerprint="f" * 64, confirm="ARCHIVE BASE 44")
            self.assertTrue(result["committed"])
            self.assertEqual(result["receiptStatus"], "pending-finalization-failed")
            self.assertIn("disk full", result["receiptFinalizeError"])
            self.assertTrue(pathlib.Path(result["receipt"]).exists())
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)

    def test_archive_requires_actor_specific_confirmation(self):
        with self.assertRaisesRegex(PermissionError, "ARCHIVE BASE 44"):
            MODULE.archive(lambda: FakeConnection(), lambda: {}, "/tmp/nope", totem_id=44, recovery_player_id=46, expected_fingerprint="f" * 64, confirm="ARCHIVE BASE")

    def test_receipt_paths_reject_or_ignore_symbolic_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            actual = root / "actual"
            actual.mkdir()
            linked_root = root / "linked"
            linked_root.symlink_to(actual, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                MODULE._write_receipt(linked_root / "receipt.json", {"status": "pending"})
            real = actual / "real.json"
            MODULE._write_receipt(real, {"status": "committed", "receiptId": "one"})
            (actual / "fake.json").symlink_to(real)
            rows = MODULE.list_receipts(actual)
            self.assertEqual(["one"], [row.get("receiptId") for row in rows])


if __name__ == "__main__":
    unittest.main()
