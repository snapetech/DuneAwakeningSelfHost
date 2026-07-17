#!/usr/bin/env python3
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("offline_teleport", ROOT / "admin" / "offline_teleport.py")
teleport = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(teleport)


def player_row(**changes):
    row = {
        "player_state_id": 91, "account_id": 42, "character_name": "Test Character",
        "online_status": "Offline", "life_state": "Alive", "server_id": 7,
        "previous_server_partition_id": 3, "player_controller_id": 100,
        "player_pawn_id": 101, "fls_id": "FLS-test", "native_offline": True,
        "pawn_actor_id": 101, "pawn_class": "PlayerPawn", "pawn_map": "Survival_1",
        "pawn_partition_id": 3, "pawn_dimension_index": 0,
        "pawn_x": 1.0, "pawn_y": 2.0, "pawn_z": 3.0,
        "native_function_available": True,
    }
    row.update(changes)
    return row


def partition_row(**changes):
    row = {
        "partition_id": 12, "server_id": 7, "map": "Survival_1",
        "dimension_index": 0, "label": "Hagga Basin", "blocked": False,
        "expected_pawn_map": "Survival_1",
    }
    row.update(changes)
    return row


class Cursor:
    def __init__(self, state, partition, events, refuse_move=False):
        self.state = state
        self.partition = partition
        self.events = events
        self.refuse_move = refuse_move
        self.rows = []
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        self.description = [("value",)]
        if "from dune.encrypted_player_state eps" in normalized and "native_function_available" in normalized:
            self.rows = [dict(self.state)]
        elif "from dune.world_partition" in normalized and "expected_pawn_map" in normalized:
            self.rows = [dict(self.partition)]
        elif "pg_advisory_xact_lock" in normalized:
            self.events.append("advisory-lock")
            self.rows = [(None,)]
        elif "select player_pawn_id from dune.encrypted_player_state" in normalized:
            self.rows = [{"player_pawn_id": self.state["player_pawn_id"]}]
        elif "select id from dune.actors" in normalized:
            self.rows = [{"id": self.state["pawn_actor_id"]}]
        elif "select partition_id from dune.world_partition" in normalized:
            self.rows = [{"partition_id": self.partition["partition_id"]}]
        elif 'select ea."user" as fls_id' in normalized:
            self.rows = [{"fls_id": self.state["fls_id"]}]
        elif "dune.admin_move_offline_player_to_partition" in normalized:
            self.events.append("native-call")
            if not self.refuse_move:
                self.state.update({
                    "pawn_partition_id": self.partition["partition_id"],
                    "pawn_dimension_index": self.partition["dimension_index"],
                    "pawn_map": self.partition["expected_pawn_map"],
                    "pawn_x": float(params[2]), "pawn_y": float(params[3]), "pawn_z": float(params[4]),
                })
            self.rows = [(None,)]
        else:
            raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class Connection:
    def __init__(self, state, partition, events, refuse_move=False):
        self.state = state
        self.partition = partition
        self.events = events
        self.refuse_move = refuse_move
        self.autocommit = True
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return Cursor(self.state, self.partition, self.events, self.refuse_move)

    def commit(self):
        self.committed = True
        self.events.append("commit")

    def rollback(self):
        self.rolled_back = True
        self.events.append("rollback")

    def close(self):
        pass


def preview_query(state, partition):
    def run(sql, params=()):
        normalized = " ".join(str(sql).split())
        if "from dune.encrypted_player_state eps" in normalized:
            return [dict(state)]
        if "from dune.world_partition" in normalized:
            return [dict(partition)]
        raise AssertionError(normalized)
    return run


class OfflineTeleportTests(unittest.TestCase):
    def test_preview_is_private_fingerprint_bound_and_bounded(self):
        result = teleport.plan(preview_query(player_row(), partition_row()), 42, 12, {"x": 100, "y": 200, "z": 9000})
        self.assertTrue(result["canExecute"])
        self.assertEqual(teleport.CONFIRM, result["confirm"])
        self.assertEqual(64, len(result["expectedFingerprint"]))
        self.assertEqual("<private FLS identity>", result["plan"]["args"][0])
        self.assertNotIn("fls_id", str(result).lower())
        self.assertTrue(result["backupRequired"])
        self.assertFalse(result["restartRequired"])
        with self.assertRaisesRegex(ValueError, "within"):
            teleport.plan(preview_query(player_row(), partition_row()), 42, 12, {"x": 10_000_001, "y": 0, "z": 0})

    def test_preview_blocks_online_native_presence_missing_pawn_function_and_partition(self):
        cases = [
            (player_row(online_status="Online"), partition_row()),
            (player_row(native_offline=False), partition_row()),
            (player_row(pawn_actor_id=None), partition_row()),
            (player_row(native_function_available=False), partition_row()),
            (player_row(), partition_row(blocked=True)),
        ]
        for state, partition in cases:
            with self.subTest(state=state, partition=partition):
                self.assertFalse(teleport.plan(preview_query(state, partition), 42, 12, {"x": 1, "y": 2, "z": 3})["canExecute"])

    def test_execute_backups_locks_calls_native_verifies_and_receipts(self):
        state, partition, events, connections = player_row(), partition_row(), [], []

        def connect():
            connection = Connection(state, partition, events)
            connections.append(connection)
            return connection

        preview = teleport.plan(preview_query(state, partition), 42, 12, {"x": 100, "y": 200, "z": 9000})
        with tempfile.TemporaryDirectory() as tmp:
            def backup():
                events.append("backup")
                return {"path": "/private/test.dump", "bytes": 123}

            result = teleport.execute(connect, backup, tmp, 42, 12, {"x": 100, "y": 200, "z": 9000}, preview["expectedFingerprint"], teleport.CONFIRM, principal="unit-test")
            self.assertTrue(result["verified"])
            self.assertLess(events.index("backup"), events.index("advisory-lock"))
            self.assertLess(events.index("advisory-lock"), events.index("native-call"))
            self.assertLess(events.index("native-call"), events.index("commit"))
            self.assertTrue(connections[-1].committed)
            self.assertEqual("committed", result["receipt"]["status"])
            receipts = teleport.list_receipts(tmp)
            self.assertEqual(1, len(receipts))
            self.assertTrue(receipts[0]["receiptHashValid"])

    def test_execute_rejects_stale_preview_before_backup(self):
        state, partition, events = player_row(), partition_row(), []
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "changed after preview"):
                teleport.execute(lambda: Connection(state, partition, events), lambda: events.append("backup"), tmp, 42, 12, {"x": 1, "y": 2, "z": 3}, "0" * 64, teleport.CONFIRM)
        self.assertNotIn("backup", events)

    def test_execute_rolls_back_failed_readback(self):
        state, partition, events = player_row(), partition_row(), []
        preview = teleport.plan(preview_query(state, partition), 42, 12, {"x": 100, "y": 200, "z": 9000})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "readback verification failed"):
                teleport.execute(lambda: Connection(state, partition, events, refuse_move=True), lambda: {"path": "/private/test.dump"}, tmp, 42, 12, {"x": 100, "y": 200, "z": 9000}, preview["expectedFingerprint"], teleport.CONFIRM)
        self.assertIn("rollback", events)
        self.assertNotIn("commit", events)

    def test_confirmation_is_exact(self):
        with self.assertRaisesRegex(PermissionError, "confirmation"):
            teleport.execute(lambda: None, lambda: None, "/tmp", 42, 12, {"x": 1, "y": 2, "z": 3}, "x", "move")


if __name__ == "__main__":
    unittest.main()
