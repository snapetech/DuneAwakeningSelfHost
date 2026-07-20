#!/usr/bin/env python3
import json
import importlib.util
import os
import pathlib
import sqlite3
import stat
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import audit_ledger

SNAPSHOT_SPEC = importlib.util.spec_from_file_location(
    "snapshot_audit_ledger", ROOT / "scripts" / "snapshot-audit-ledger.py"
)
snapshot_audit_ledger = importlib.util.module_from_spec(SNAPSHOT_SPEC)
SNAPSHOT_SPEC.loader.exec_module(snapshot_audit_ledger)


class AuditLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.database = self.root / "private" / "audit-ledger.sqlite3"
        self.store = audit_ledger.Store(self.database)
        self.store.initialize()
        self.counter = 0

    def test_verification_cache_extends_on_append_and_invalidates_on_artifact_change(self):
        first = self.event("cached")
        self.store.append(first)
        with mock.patch.object(self.store, "_verify_connection", wraps=self.store._verify_connection) as verify:
            self.assertTrue(self.store.status()["ok"])
            self.assertEqual(0, verify.call_count)
            self.store.append(self.event("extended"))
            self.assertTrue(self.store.status()["ok"])
            self.assertEqual(0, verify.call_count)
            (self.database.parent / "unrelated-state.tmp").write_text("changed", encoding="utf-8")
            self.assertTrue(self.store.status()["ok"])
            self.assertEqual(0, verify.call_count)
            os.utime(self.database, None)
            self.assertTrue(self.store.status()["ok"])
            self.assertEqual(1, verify.call_count)

    def tearDown(self):
        self.temporary.cleanup()

    def event(self, action="test-action", ok=True, **fields):
        self.counter += 1
        return {
            "ts": f"2026-07-16T20:00:{self.counter:02d}Z",
            "action": action,
            "ok": ok,
            "eventId": f"audit-{self.counter:032x}",
            **fields,
        }

    def test_private_initialization_and_empty_anchor(self):
        self.assertEqual(stat.S_IMODE(self.database.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.database.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.store.key_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.store.anchor_path.stat().st_mode), 0o600)
        status = self.store.status()
        self.assertTrue(status["ok"])
        self.assertEqual(status["ledger"]["events"], 0)
        self.assertEqual(status["ledger"]["headHmacSha256"], audit_ledger.ZERO_HMAC)

    def test_append_verify_and_list(self):
        first = self.store.append(self.event(peer="127.0.0.1"))
        second = self.store.append(self.event("other-action", ok=False))
        self.assertEqual(first["sequence"], 1)
        self.assertEqual(second["sequence"], 2)
        verified = self.store.verify()
        self.assertTrue(verified["ok"])
        self.assertEqual(verified["events"], 2)
        rows = self.store.list(10)
        self.assertEqual([row["ledgerSequence"] for row in rows], [1, 2])
        self.assertEqual(rows[1]["action"], "other-action")

    def test_idempotency_and_collision_refusal(self):
        event = self.event()
        first = self.store.append(event)
        second = self.store.append(dict(event))
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        changed = dict(event, action="changed")
        with self.assertRaisesRegex(RuntimeError, "collision"):
            self.store.append(changed)

    def test_payload_tampering_is_detected(self):
        self.store.append(self.event())
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("drop trigger audit_events_no_update")
            payload = json.loads(connection.execute("select event_json from events").fetchone()[0])
            payload["action"] = "forged"
            connection.execute("update events set event_json=? where sequence=1", (json.dumps(payload),))
            connection.execute("""create trigger audit_events_no_update before update on events begin
                select raise(abort, 'audit ledger events are append-only'); end""")
            connection.commit()
        with self.assertRaisesRegex(RuntimeError, "payload digest"):
            self.store.verify()
        with self.assertRaisesRegex(RuntimeError, "payload digest"):
            self.store.append(self.event("must-not-admit"), verify_chain=True)

    def test_hmac_tampering_is_detected(self):
        self.store.append(self.event())
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("drop trigger audit_events_no_update")
            connection.execute("update events set event_hmac_sha256=? where sequence=1", ("f" * 64,))
            connection.execute("""create trigger audit_events_no_update before update on events begin
                select raise(abort, 'audit ledger events are append-only'); end""")
            connection.commit()
        with self.assertRaisesRegex(RuntimeError, "HMAC verification"):
            self.store.verify()

    def test_tail_deletion_is_detected_by_authenticated_anchor(self):
        self.store.append(self.event())
        self.store.append(self.event())
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("drop trigger audit_events_no_delete")
            connection.execute("delete from events where sequence=2")
            connection.execute("""create trigger audit_events_no_delete before delete on events begin
                select raise(abort, 'audit ledger events are append-only'); end""")
            connection.commit()
        with self.assertRaisesRegex(RuntimeError, "tail deletion"):
            self.store.verify()

    def test_anchor_tampering_and_missing_anchor_fail_closed(self):
        self.store.append(self.event())
        anchor = json.loads(self.store.anchor_path.read_text(encoding="utf-8"))
        anchor["sequence"] = 0
        self.store.anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "anchor HMAC"):
            self.store.verify()
        self.store.anchor_path.unlink()
        with self.assertRaisesRegex(RuntimeError, "anchor is missing"):
            audit_ledger.Store(self.database).initialize()

    def test_privileged_request_correlation_finds_incomplete_work(self):
        request_one = "request-" + "1" * 32
        request_two = "request-" + "2" * 32
        self.store.append(self.event("privileged-request-admitted", request_id=request_one))
        self.store.append(self.event("privileged-request-completed", request_id=request_one))
        self.store.append(self.event("privileged-request-admitted", request_id=request_two))
        status = self.store.status()["requests"]
        self.assertEqual(status["admitted"], 2)
        self.assertEqual(status["completed"], 1)
        self.assertEqual(status["open"], 1)
        self.assertGreater(status["oldestOpenAgeSeconds"], 0)
        self.assertEqual(status["openRequests"][0]["id"], request_two)

        self.store.append(self.event(
            "privileged-request-reconciled", request_id=request_two,
            outcome="no-effect", reason="authoritative state showed no effect",
        ))
        reconciled = self.store.status()["requests"]
        self.assertEqual(reconciled["completed"], 2)
        self.assertEqual(reconciled["reconciled"], 1)
        self.assertEqual(reconciled["open"], 0)
        self.assertFalse(self.store.request_state(request_two)["open"])

    def test_same_store_concurrent_appends_are_serialized(self):
        barrier = threading.Barrier(8)
        errors = []

        def worker(index):
            try:
                barrier.wait()
                self.store.append({
                    "ts": f"2026-07-16T21:00:{index:02d}Z",
                    "action": "concurrent",
                    "ok": True,
                    "eventId": f"audit-{100 + index:032x}",
                })
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.store.verify()["events"], 8)

    def test_request_state_finds_open_request_beyond_public_list_limit(self):
        target = None
        for index in range(101):
            target = f"request-{index:032x}"
            self.store.append(self.event(
                "privileged-request-admitted", request_id=target,
                ts="2026-07-16T20:00:00Z", path="/api/test",
                capability="infrastructure.write", principal_id="tester",
            ))

        status = self.store.status()["requests"]
        self.assertEqual(101, status["open"])
        self.assertEqual(100, len(status["openRequests"]))
        state = self.store.request_state(target)
        self.assertTrue(state["open"])
        self.assertEqual("/api/test", state["path"])

    def test_append_only_triggers_refuse_update_delete_and_are_verified(self):
        self.store.append(self.event())
        with closing(sqlite3.connect(self.database)) as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("update events set action='forged' where sequence=1")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                connection.execute("delete from events where sequence=1")
            connection.execute("drop trigger audit_events_no_update")
            connection.commit()
        with self.assertRaisesRegex(RuntimeError, "append-only triggers"):
            self.store.verify()

    def test_metrics_are_label_free_and_do_not_expose_hmacs(self):
        self.store.append(self.event())
        metrics = self.store.prometheus(enabled=True)
        self.assertIn("dash_admin_audit_ledger_valid 1", metrics)
        self.assertIn("dash_admin_audit_ledger_events 1", metrics)
        self.assertNotIn("{", metrics)
        self.assertNotIn(self.store.verify()["headHmacSha256"], metrics)

    def test_consistent_backup_snapshot_copies_and_verifies_all_three_artifacts(self):
        self.store.append(self.event())
        destination = self.root / "backup"
        result = snapshot_audit_ledger.snapshot(
            self.database, self.store.key_path, self.store.anchor_path, destination
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["events"], 1)
        copied = audit_ledger.Store(
            destination / "audit-ledger.sqlite3",
            key_path=destination / "audit-ledger.hmac.key",
            anchor_path=destination / "audit-ledger.anchor.json",
        ).verify()
        self.assertTrue(copied["ok"])
        for name in result["files"]:
            self.assertEqual(stat.S_IMODE((destination / name).stat().st_mode), 0o600)

        direct_destination = self.root / "direct-backup" / "audit-ledger.sqlite3"
        direct = self.store.backup(direct_destination)
        self.assertTrue(direct["ok"])
        self.assertEqual(direct["events"], 1)
        self.assertTrue(audit_ledger.Store(
            direct_destination,
            key_path=direct_destination.with_name("audit-ledger.hmac.key"),
            anchor_path=direct_destination.with_name("audit-ledger.anchor.json"),
        ).verify()["ok"])

    def test_backup_snapshot_refuses_partial_source_set(self):
        self.store.append(self.event())
        self.store.anchor_path.unlink()
        with self.assertRaisesRegex(ValueError, "requires regular"):
            snapshot_audit_ledger.snapshot(
                self.database, self.store.key_path, self.store.anchor_path, self.root / "backup"
            )

    def test_invalid_event_shapes_are_refused(self):
        with self.assertRaises(ValueError):
            self.store.append({"eventId": "bad", "ts": "never", "action": "x", "ok": True})
        with self.assertRaisesRegex(ValueError, "request_id"):
            self.store.append(self.event(request_id="not-valid"))
        with self.assertRaisesRegex(ValueError, "JSON-compatible"):
            self.store.append(self.event(value=object()))

    def test_permission_drift_and_symlinks_fail_verification(self):
        self.store.append(self.event())
        os.chmod(self.store.anchor_path, 0o644)
        with self.assertRaisesRegex(RuntimeError, "permissions must be 0600"):
            self.store.verify()
        os.chmod(self.store.anchor_path, 0o600)
        linked_key = self.root / "linked.key"
        linked_key.symlink_to(self.store.key_path)
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            audit_ledger.Store(
                self.database, key_path=linked_key, anchor_path=self.store.anchor_path
            ).verify()


if __name__ == "__main__":
    unittest.main()
