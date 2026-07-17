#!/usr/bin/env python3

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("character_backups", ROOT / "admin" / "character_backups.py")
character_backups = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(character_backups)


def capture_row(**updates):
    row = {
        "player_state_row_id": 7, "account_id": 42, "character_name": "Chani",
        "online_status": "Offline", "player_controller_id": 100,
        "player_state_id": 101, "player_pawn_id": 102, "fls_id": "private-fls-id",
        "native_offline": True, "export_available": True, "import_available": True,
        "patches_checksum": "patch-a",
    }
    row.update(updates)
    return row


def restore_row(**updates):
    row = {
        "account_id": 42, "player_state_row_id": 7, "character_name": "Current Chani",
        "online_status": "Offline", "player_controller_id": 100,
        "player_state_id": 101, "player_pawn_id": 102, "native_offline": True,
        "export_available": True, "import_available": True, "patches_checksum": "patch-a",
    }
    row.update(updates)
    return row


class CharacterBackupsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_snapshot(self, snapshot_id="character-20260717T000000Z-0123456789abcdef"):
        transfer = {"_patches_checksum": "patch-a", "funcom_id": "display", "entries": [{"kind": "acc"}]}
        envelope = {
            "schemaVersion": 1,
            "metadata": {
                "id": snapshot_id, "createdAt": "2026-07-17T00:00:00Z",
                "accountIdAtCapture": 42, "characterName": "Chani", "action": "manual",
                "reason": "test", "principal": "operator", "patchesChecksum": "patch-a",
                "bytes": len(character_backups._canonical(transfer)),
            },
            "flsId": "private-fls-id", "transfer": transfer,
        }
        envelope["metadata"]["snapshotSha256"] = character_backups._sha256(envelope)
        path = character_backups._snapshot_dir(self.root) / f"{snapshot_id}.json"
        character_backups._write_exclusive(path, envelope)
        return snapshot_id, path

    def test_capture_preview_is_dual_offline_and_fingerprint_bound(self):
        plan = character_backups.plan_capture(lambda _sql, _params: [capture_row()], 42)
        self.assertTrue(plan["canExecute"])
        self.assertEqual(character_backups.CAPTURE_CONFIRM, plan["confirm"])
        self.assertEqual(64, len(plan["expectedFingerprint"]))
        blocked = character_backups.plan_capture(
            lambda _sql, _params: [capture_row(online_status="Online", native_offline=False)], 42,
        )
        self.assertFalse(blocked["canExecute"])
        self.assertEqual(2, len(blocked["blockers"]))

    def test_snapshot_round_trip_list_download_delete(self):
        snapshot_id, path = self.write_snapshot()
        rows = character_backups.list_snapshots(self.root)
        self.assertEqual(snapshot_id, rows[0]["id"])
        self.assertTrue(rows[0]["verified"])
        self.assertNotIn("flsId", rows[0])
        data, name, digest = character_backups.download(self.root, snapshot_id)
        self.assertEqual(f"{snapshot_id}.json", name)
        self.assertEqual("patch-a", json.loads(data)["_patches_checksum"])
        self.assertEqual(64, len(digest))
        with self.assertRaises(PermissionError):
            character_backups.delete_snapshot(self.root, snapshot_id, "wrong")
        deleted = character_backups.delete_snapshot(self.root, snapshot_id, character_backups.DELETE_CONFIRM)
        self.assertEqual(snapshot_id, deleted["deleted"]["id"])
        self.assertFalse(path.exists())

    def test_tampered_snapshot_fails_closed(self):
        snapshot_id, path = self.write_snapshot()
        envelope = json.loads(path.read_text())
        envelope["transfer"]["entries"].append({"kind": "itm"})
        path.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            character_backups.download(self.root, snapshot_id)

    def test_restore_preview_requires_offline_and_matching_patch(self):
        snapshot_id, _ = self.write_snapshot()
        plan = character_backups.plan_restore(lambda _sql, _params: [restore_row()], self.root, snapshot_id)
        self.assertTrue(plan["canExecute"])
        self.assertEqual(character_backups.RESTORE_CONFIRM, plan["confirm"])
        self.assertEqual(64, len(plan["expectedFingerprint"]))
        blocked = character_backups.plan_restore(
            lambda _sql, _params: [restore_row(online_status="Online", native_offline=False, patches_checksum="patch-b")],
            self.root, snapshot_id,
        )
        self.assertFalse(blocked["canExecute"])
        self.assertEqual(3, len(blocked["blockers"]))

    def test_restore_accepts_identity_with_no_current_character(self):
        snapshot_id, _ = self.write_snapshot()
        row = restore_row(account_id=None, player_state_row_id=None, character_name=None,
                          online_status=None, player_controller_id=None, player_state_id=None,
                          player_pawn_id=None, native_offline=True)
        plan = character_backups.plan_restore(lambda _sql, _params: [row], self.root, snapshot_id)
        self.assertTrue(plan["canExecute"])
        self.assertEqual("absent", plan["current"]["onlineStatus"])

    def test_restore_confirmation_and_fingerprint_fail_before_backup(self):
        snapshot_id, _ = self.write_snapshot()
        with self.assertRaises(PermissionError):
            character_backups.restore(None, None, self.root, snapshot_id, "", "wrong")


if __name__ == "__main__":
    unittest.main()
