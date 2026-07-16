#!/usr/bin/env python3

import importlib.util
import json
import os
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("progression_admin", ROOT / "admin" / "progression_admin.py")
progression = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progression)


def properties(points=10, recipes=None, research=None):
    return {
        "Unrelated": {"keep": True},
        "TechKnowledgePlayerComponent": {
            "m_TechKnowledgePoints": points,
            "m_TechKnowledge": {"m_TechKnowledgeData": research or []},
        },
        "CraftingRecipesLibraryActorComponent": {"m_KnownItemRecipes": recipes or []},
    }


class FakeDatabase:
    def __init__(self, payload=None, online="Offline"):
        self.properties = payload or properties()
        self.online = online
        self.sql = []

    def connect(self):
        database = self

        class Cursor:
            rowcount = 0
            description = None
            response = None

            def __enter__(self): return self
            def __exit__(self, *args): return False

            def execute(self, sql, params=()):
                database.sql.append(sql)
                if "from dune.player_state ps" in sql:
                    self.response = {
                        "account_id": 7, "character_name": "Tester",
                        "online_status": database.online, "player_pawn_id": 42,
                        "properties": database.properties,
                    }
                elif sql.startswith("update dune.actors"):
                    expected = json.loads(params[2])
                    if expected == database.properties:
                        database.properties = json.loads(params[0])
                        self.rowcount = 1
                    else:
                        self.rowcount = 0
                    self.response = None
                elif sql.startswith("select properties"):
                    self.response = {"properties": database.properties}

            def fetchone(self): return self.response

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()

        return Connection()


class ProgressionAdminTest(unittest.TestCase):
    def test_capture_and_replace_only_touch_selected_state(self):
        original = properties(points=12, recipes=[{"BaseRecipeId": {"Name": "A"}}])
        before = progression.capture_state("add-intel", original)
        updated = progression.replace_state("add-intel", original, {"intelPoints": 99})
        self.assertEqual(before, {"intelPoints": 12})
        self.assertEqual(updated["Unrelated"], {"keep": True})
        self.assertEqual(updated["CraftingRecipesLibraryActorComponent"], original["CraftingRecipesLibraryActorComponent"])
        self.assertEqual(progression.capture_state("add-intel", updated), {"intelPoints": 99})

    def test_research_can_atomically_include_derived_recipe_state(self):
        original = properties(research=[{"ItemKey": "RCP_A", "UnlockedState": "Available"}])
        state = {
            "research": [{"ItemKey": "RCP_A", "UnlockedState": "Purchased"}],
            "recipes": [{"BaseRecipeId": {"Name": "A"}}],
        }
        updated = progression.replace_state("unlock-research", original, state, include_recipe=True)
        self.assertEqual(progression.capture_state("unlock-research", updated, include_recipe=True), state)

    def test_state_is_bounded_and_shape_checked(self):
        with self.assertRaisesRegex(ValueError, "fields"):
            progression.normalize_state("add-intel", {"intelPoints": 1, "extra": True})
        with self.assertRaisesRegex(ValueError, "bounded array"):
            progression.normalize_state("unlock-recipe", {"recipes": [None] * 10001})

    def test_apply_locks_compares_and_post_verifies(self):
        database = FakeDatabase(properties(points=10))
        result = progression.apply(database.connect, 42, "add-intel", {"intelPoints": 10}, {"intelPoints": 25})
        self.assertTrue(result["verified"])
        self.assertEqual(progression.capture_state("add-intel", database.properties), {"intelPoints": 25})
        self.assertTrue(any("for update of ps, a" in sql for sql in database.sql))
        self.assertTrue(any("properties=%s::jsonb" in sql for sql in database.sql))

    def test_apply_refuses_changed_preview_or_online_player(self):
        with self.assertRaisesRegex(RuntimeError, "changed after preview"):
            progression.apply(FakeDatabase(properties(points=11)).connect, 42, "add-intel", {"intelPoints": 10}, {"intelPoints": 25})
        with self.assertRaisesRegex(PermissionError, "Offline"):
            progression.apply(FakeDatabase(properties(points=10), online="Online").connect, 42, "add-intel", {"intelPoints": 10}, {"intelPoints": 25})

    def test_receipt_is_private_self_hashed_and_confined(self):
        result = {
            "action": "add-intel", "player": {"account_id": 7, "player_pawn_id": 42},
            "before": {"intelPoints": 10}, "after": {"intelPoints": 25},
            "beforeHash": progression.state_hash({"intelPoints": 10}),
            "afterHash": progression.state_hash({"intelPoints": 25}),
            "includeRecipe": False, "changed": True, "verified": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            receipt = progression.write_receipt(directory, result, "dune", "intel:+15", {"path": "backup.dump"}, {"id": "admin"})
            path = pathlib.Path(receipt["path"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(progression.load_receipt(directory, receipt["id"])["target"], "intel:+15")
            payload = json.loads(path.read_text())
            payload["target"] = "tampered"
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "digest"):
                progression.load_receipt(directory, receipt["id"])
            with self.assertRaisesRegex(ValueError, "invalid"):
                progression.load_receipt(directory, "../../etc/passwd")

    def test_receipt_loader_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt_dir = progression.receipt_root(directory)
            receipt_dir.mkdir(parents=True)
            receipt_id = "20260716T000000Z-0123456789abcdef"
            target = pathlib.Path(directory) / "target.json"
            target.write_text("{}")
            os.symlink(target, receipt_dir / f"{receipt_id}.json")
            with self.assertRaisesRegex(ValueError, "regular file"):
                progression.load_receipt(directory, receipt_id)


if __name__ == "__main__":
    unittest.main()
