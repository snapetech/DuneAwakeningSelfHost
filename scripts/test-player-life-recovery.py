#!/usr/bin/env python3
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("player_life_recovery", ROOT / "admin" / "player_life_recovery.py")
life = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(life)


def dead_row(**changes):
    row = {
        "player_state_id": 91, "account_id": 42, "character_name": "Test Character",
        "online_status": "Offline", "life_state": "DeadBySandworm", "server_id": 7,
        "player_controller_id": 100, "player_pawn_id": 101,
        "death_location_present": True, "death_location_text": "(test)", "fls_id": "FLS-test",
        "native_offline": True, "pawn_actor_id": 101, "pawn_class": "PlayerPawn",
        "pawn_map": "Survival_1", "pawn_partition_id": 3, "pawn_dimension_index": 0,
        "pawn_x": 1.0, "pawn_y": 2.0, "pawn_z": 3.0,
        "get_player_pawn_available": True, "update_death_location_available": True,
    }
    row.update(changes)
    return row


class Cursor:
    def __init__(self, state, events, refuse_transition=False):
        self.state = state
        self.events = events
        self.refuse_transition = refuse_transition
        self.rows = []
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        self.description = [("value",)]
        if "from dune.encrypted_player_state eps" in normalized and "death_location_present" in normalized:
            self.rows = [dict(self.state)]
        elif "pg_advisory_xact_lock" in normalized:
            self.events.append("advisory-lock")
            self.rows = [{"pg_advisory_xact_lock": None}]
        elif "select player_pawn_id from dune.encrypted_player_state" in normalized:
            self.rows = [{"player_pawn_id": self.state["player_pawn_id"]}]
        elif "select id from dune.actors" in normalized:
            self.rows = [{"id": self.state["pawn_actor_id"]}]
        elif "dune.update_death_location" in normalized:
            self.events.append("native-call")
            if not self.refuse_transition:
                self.state["life_state"] = "Alive"
                self.state["death_location_present"] = False
                self.state["death_location_text"] = ""
            self.rows = [(None,)]
        else:
            raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class Connection:
    def __init__(self, state, events, refuse_transition=False):
        self.state = state
        self.events = events
        self.refuse_transition = refuse_transition
        self.autocommit = True
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return Cursor(self.state, self.events, self.refuse_transition)

    def commit(self):
        self.committed = True
        self.events.append("commit")

    def rollback(self):
        self.rolled_back = True
        self.events.append("rollback")

    def close(self):
        pass


class PlayerLifeRecoveryTests(unittest.TestCase):
    def test_preview_is_fingerprint_bound_and_precisely_scoped(self):
        result = life.plan(lambda sql, params=(): [dead_row()], 42)
        self.assertTrue(result["canExecute"])
        self.assertEqual("DeadBySandworm -> Alive", result["transition"])
        self.assertEqual(life.CONFIRM, result["confirm"])
        self.assertEqual(64, len(result["expectedFingerprint"]))
        self.assertIn("health", result["scope"])
        self.assertTrue(result["backupRequired"])
        self.assertFalse(result["restartRequired"])

    def test_preview_blocks_online_alive_missing_pawn_and_missing_contract(self):
        cases = [
            dead_row(online_status="Online"), dead_row(native_offline=False),
            dead_row(life_state="Alive", death_location_present=False),
            dead_row(pawn_actor_id=None), dead_row(update_death_location_available=False),
        ]
        for row in cases:
            with self.subTest(row=row):
                self.assertFalse(life.plan(lambda sql, params=(): [row], 42)["canExecute"])

    def test_execute_backups_before_lock_calls_native_verifies_and_receipts(self):
        state = dead_row()
        events = []
        connections = []

        def connect():
            connection = Connection(state, events)
            connections.append(connection)
            return connection

        preview = life.plan(lambda sql, params=(): [dict(state)], 42)
        with tempfile.TemporaryDirectory() as tmp:
            def backup():
                events.append("backup")
                return {"path": "/private/test.dump", "bytes": 123}

            result = life.execute(
                connect, backup, pathlib.Path(tmp), 42,
                preview["expectedFingerprint"], life.CONFIRM, principal="unit-test",
            )
            self.assertTrue(result["verified"])
            self.assertEqual("Alive", result["after"]["lifeState"])
            self.assertFalse(result["after"]["deathLocationPresent"])
            self.assertLess(events.index("backup"), events.index("advisory-lock"))
            self.assertLess(events.index("advisory-lock"), events.index("native-call"))
            self.assertLess(events.index("native-call"), events.index("commit"))
            self.assertTrue(connections[-1].committed)
            self.assertEqual("committed", result["receipt"]["status"])
            receipts = life.list_receipts(tmp)
            self.assertEqual(1, len(receipts))
            self.assertTrue(receipts[0]["receiptHashValid"])

    def test_execute_rejects_stale_preview_before_backup(self):
        state = dead_row()
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "changed after preview"):
                life.execute(
                    lambda: Connection(state, events), lambda: events.append("backup"), tmp,
                    42, "0" * 64, life.CONFIRM,
                )
        self.assertNotIn("backup", events)

    def test_execute_rolls_back_when_native_readback_is_not_alive(self):
        state = dead_row()
        events = []
        preview = life.plan(lambda sql, params=(): [dict(state)], 42)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "post-write verification failed"):
                life.execute(
                    lambda: Connection(state, events, refuse_transition=True),
                    lambda: {"path": "/private/test.dump", "bytes": 123}, tmp,
                    42, preview["expectedFingerprint"], life.CONFIRM,
                )
        self.assertIn("rollback", events)
        self.assertNotIn("commit", events)

    def test_confirmation_is_exact(self):
        with self.assertRaisesRegex(PermissionError, "confirmation"):
            life.execute(lambda: None, lambda: None, "/tmp", 42, "x", "recover")


if __name__ == "__main__":
    unittest.main()
