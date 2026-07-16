#!/usr/bin/env python3

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cosmetics_admin", ROOT / "admin" / "cosmetics_admin.py")
cosmetics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cosmetics)


def catalog():
    return {"items": [
        {"id": "DyePack_A", "name": "A", "category": "Dye Packs", "unlockMode": "customization", "enabled": True},
        {"id": "MTX_B", "name": "B", "category": "Armor Skins", "unlockMode": "customization", "enabled": True},
        {"id": "Swatch_X", "name": "X", "category": "Tokens", "unlockMode": "inventory", "enabled": True},
    ]}


class CosmeticsTest(unittest.TestCase):
    @staticmethod
    def properties(ids):
        return {"CustomizationLibraryActorComponent": {"m_UnlockedCustomizationSerializableList": {"m_UnlockedCustomizationIds": [{"m_CustomizationId": value} for value in ids]}}}

    def test_catalog_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "catalog.json"
            path.write_text(json.dumps({"version": 1, "items": [{"id": "A"}, {"id": "A"}]}))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                cosmetics.load_catalog(path)

    def test_add_is_catalog_only_and_idempotent(self):
        rows = [{"m_CustomizationId": "Existing"}]
        planned = cosmetics.plan_entries(rows, catalog(), "add", "DyePack_A")
        self.assertEqual(planned["added"], ["DyePack_A"])
        self.assertEqual(planned["afterCount"], 2)
        again = cosmetics.plan_entries(planned["after"], catalog(), "add", "DyePack_A")
        self.assertFalse(again["changed"])
        with self.assertRaisesRegex(ValueError, "reviewed catalog"):
            cosmetics.plan_entries(rows, catalog(), "add", "NotReviewed")

    def test_remove_preserves_unknown_entries(self):
        rows = [{"m_CustomizationId": "Unknown"}, {"m_CustomizationId": "DyePack_A"}]
        planned = cosmetics.plan_entries(rows, catalog(), "remove", "DyePack_A")
        self.assertEqual(cosmetics.ids_from_entries(planned["after"]), ["Unknown"])

    def test_unlock_all_excludes_inventory_tokens(self):
        planned = cosmetics.plan_entries([], catalog(), "unlock-all")
        self.assertEqual(cosmetics.ids_from_entries(planned["after"]), ["DyePack_A", "MTX_B"])

    def test_receipt_is_private_and_tamper_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            planned = cosmetics.plan_entries([], catalog(), "add", "DyePack_A")
            planned["player"] = {"player_pawn_id": 42, "online_status": "Offline"}
            planned["database"] = "dune_sb_current"
            receipt = cosmetics.write_receipt(directory, planned, {"path": "/backup.dump"}, {"id": "admin"})
            path = pathlib.Path(receipt["path"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            loaded = cosmetics.load_receipt(directory, receipt["id"])
            self.assertEqual(loaded["beforeHash"], planned["beforeHash"])
            self.assertEqual(loaded["database"], "dune_sb_current")
            data = json.loads(path.read_text())
            data["before"].append({"m_CustomizationId": "tampered"})
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "hashes"):
                cosmetics.load_receipt(directory, receipt["id"])

    def test_receipt_path_is_confined(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "invalid"):
                cosmetics.load_receipt(directory, "../../etc/passwd")

    def test_apply_locks_offline_player_and_verifies(self):
        state = {"properties": self.properties(["Existing"]), "sql": []}

        class Cursor:
            rowcount = 0
            description = None
            response = None

            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=()):
                state["sql"].append(sql)
                if "for update of ps, a" in sql:
                    self.response = {"account_id": 1, "character_name": "Tester", "online_status": "Offline", "player_pawn_id": 42, "properties": state["properties"]}
                elif sql.startswith("update dune.actors"):
                    state["properties"] = json.loads(params[0]); self.rowcount = 1; self.response = None
                elif sql.startswith("select properties"):
                    self.response = {"properties": state["properties"]}
            def fetchone(self): return self.response

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()

        result = cosmetics.apply(lambda: Connection(), 42, catalog(), "add", "DyePack_A")
        self.assertTrue(result["verified"])
        self.assertIn("DyePack_A", cosmetics.ids_from_entries(cosmetics._entries(state["properties"])))
        self.assertTrue(any("for update of ps, a" in sql for sql in state["sql"]))
        self.assertTrue(any("properties=%s::jsonb" in sql and "properties=%s::jsonb" in sql for sql in state["sql"]))

    def test_apply_refuses_non_offline_player_at_locked_write(self):
        class Cursor:
            description = None
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, sql, params=()): pass
            def fetchone(self): return {"account_id": 1, "character_name": "Tester", "online_status": "Online", "player_pawn_id": 42, "properties": CosmeticsTest.properties([])}
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()
        with self.assertRaisesRegex(PermissionError, "Offline"):
            cosmetics.apply(lambda: Connection(), 42, catalog(), "add", "DyePack_A")

    def test_compose_binds_admin_to_active_game_database(self):
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("DUNE_ADMIN_DB_NAME: ${DUNE_GAME_DB_NAME:-dune_sb_1_4_0_0}", source)
        self.assertIn("DUNE_DATABASE: ${DUNE_GAME_DB_NAME:-dune_sb_1_4_0_0}", source)


if __name__ == "__main__":
    unittest.main()
