#!/usr/bin/env python3

import importlib.util
import json
import pathlib
import stat
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("vehicle_retirement", ROOT / "admin" / "vehicle_retirement.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def source_row(**overrides):
    value = {
        "vehicle_id": 22279,
        "actor_name": "Shadow 1",
        "actor_class": "BP_MediumOrnithopter_CHOAM",
        "map": "Survival_1",
        "partition_id": 1,
        "dimension_index": 0,
        "transform": {"x": 1, "y": 2, "z": 3},
        "actor_state": "",
        "partition_server_id": "",
        "active_server_id": None,
        "customization_id": "None",
        "backup_exists": False,
        "recovered_exists": False,
        "inventory_count": 1,
        "item_count": 0,
        "module_count": 14,
        "actor_hash": "a" * 32,
        "permission_hash": "b" * 32,
        "item_hash": "c" * 32,
        "module_hash": "d" * 32,
        "native_function_available": True,
        "owners": [{
            "playerId": 16031,
            "rank": 1,
            "accountId": 5247,
            "characterName": "Mara Jade Skywalker",
            "onlineStatus": "Offline",
        }],
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

    def fetchall(self):
        if "from dune.vehicles" in self.sql:
            return [(22279,), (22296,)]
        return []


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


class VehicleRetirementTests(unittest.TestCase):
    def query(self, rows):
        def query(sql, params=()):
            if "with vehicle_rows" in sql:
                return rows
            raise AssertionError(sql)

        return query

    def test_scan_normalizes_class_owner_and_fingerprint(self):
        row = MODULE.scan(self.query([source_row()]))[0]
        self.assertEqual(row["vehicleId"], 22279)
        self.assertTrue(row["isOrnithopter"])
        self.assertEqual(row["ownerAccountId"], 5247)
        self.assertEqual(row["ownerOnlineStatus"], "Offline")
        self.assertEqual(len(row["fingerprint"]), 64)

    def test_plan_preserves_cargo_by_default_and_requires_exact_wipe_confirmation(self):
        row = source_row(item_count=13)
        preserved = MODULE.plan(self.query([row]), [22279], 5247)
        self.assertTrue(preserved["canExecute"])
        self.assertFalse(preserved["inventoryWipeRequired"])
        self.assertTrue(preserved["inventoryPreserved"])
        self.assertEqual(preserved["confirm"], "ARCHIVE THOPTERS 22279")
        wiped = MODULE.plan(self.query([row]), [22279], 5247, allow_inventory_wipe=True)
        self.assertTrue(wiped["canExecute"])
        self.assertTrue(wiped["inventoryWipeRequired"])
        self.assertEqual(wiped["confirm"], "ARCHIVE THOPTERS 22279 AND WIPE VEHICLE INVENTORY")

    def test_plan_blocks_active_map_online_owner_and_existing_state(self):
        row = source_row(
            active_server_id="server-1",
            actor_state="VehicleBackup",
            backup_exists=True,
            owners=[{
                "playerId": 16031,
                "rank": 1,
                "accountId": 5247,
                "characterName": "Mara Jade Skywalker",
                "onlineStatus": "Online",
            }],
        )
        result = MODULE.plan(self.query([row]), [22279], 5247)
        self.assertFalse(result["canExecute"])
        self.assertTrue(any("active server" in item for item in result["blockers"]))
        self.assertTrue(any("explicitly offline" in item for item in result["blockers"]))
        self.assertTrue(any("VehicleBackup" in item for item in result["blockers"]))
        self.assertFalse(any("native vehicle backup" in item for item in result["blockers"]))

    def ready_plan(self, fingerprint="f" * 64):
        return {
            "canExecute": True,
            "blockers": [],
            "expectedFingerprint": fingerprint,
            "confirm": "ARCHIVE THOPTERS 22279,22296 AND WIPE VEHICLE INVENTORY",
            "vehicleIds": [22279, 22296],
            "accountId": 5247,
            "vehicles": [
                {"vehicleId": 22279, "customizationId": "None"},
                {"vehicleId": 22296, "customizationId": "None"},
            ],
            "inventoryWipeRequired": True,
            "nativeDeleteItems": True,
        }

    def test_archive_is_backup_first_native_verified_and_receipted(self):
        conn = FakeConnection()
        plan = self.ready_plan()
        verification = [
            {"vehicle_id": 22279, "actor_exists": True, "recovery_exists": True, "vehicle_recovery_state": True, "permission_actor_count": 0, "permission_rank_count": 0, "item_count_after": 0},
            {"vehicle_id": 22296, "actor_exists": True, "recovery_exists": True, "vehicle_recovery_state": True, "permission_actor_count": 0, "permission_rank_count": 0, "item_count_after": 0},
        ]
        snapshot = [{"vehicleId": 22279, "items": []}, {"vehicleId": 22296, "items": [{"id": 1}]}]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(MODULE, "plan", return_value=plan), \
             mock.patch.object(MODULE, "_snapshot", return_value=snapshot), \
             mock.patch.object(MODULE, "_connection_query", return_value=verification):
            result = MODULE.archive(
                lambda: conn,
                lambda: {"path": "/safe/full.dump", "bytes": 1234},
                pathlib.Path(tmp),
                vehicle_ids=[22279, 22296],
                account_id=5247,
                expected_fingerprint="f" * 64,
                confirm="ARCHIVE THOPTERS 22279,22296 AND WIPE VEHICLE INVENTORY",
                principal="operator-a",
                allow_inventory_wipe=True,
            )
            receipt = pathlib.Path(result["receipt"])
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "committed")
            self.assertEqual(payload["inventorySnapshot"], snapshot)
            self.assertTrue(result["nativeInventoryWipe"])
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            self.assertFalse(list(pathlib.Path(tmp).glob("pending-*.json")))
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertTrue(any("store_recovered_vehicles_wiped_before_spawn" in sql for sql, _ in conn.calls))

    def test_archive_rejects_stale_preview_before_backup(self):
        conn = FakeConnection()
        backup = mock.Mock(return_value={"path": "/unsafe.dump", "bytes": 1})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(MODULE, "plan", return_value=self.ready_plan("e" * 64)):
            with self.assertRaisesRegex(RuntimeError, "changed after preview"):
                MODULE.archive(
                    lambda: conn, backup, tmp, vehicle_ids=[22279, 22296], account_id=5247,
                    expected_fingerprint="f" * 64,
                    confirm="ARCHIVE THOPTERS 22279,22296 AND WIPE VEHICLE INVENTORY",
                    allow_inventory_wipe=True,
                )
        backup.assert_not_called()
        self.assertTrue(conn.rolled_back)

    def test_archive_requires_exact_inventory_wipe_phrase(self):
        plan = self.ready_plan()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(MODULE, "plan", return_value=plan):
            with self.assertRaisesRegex(PermissionError, "exactly ARCHIVE THOPTERS"):
                MODULE.archive(
                    lambda: FakeConnection(), lambda: {"path": "/safe.dump", "bytes": 1}, tmp,
                    vehicle_ids=[22279, 22296], account_id=5247, expected_fingerprint="f" * 64,
                    confirm="ARCHIVE THOPTERS 22279,22296", allow_inventory_wipe=True,
                )


if __name__ == "__main__":
    unittest.main()
