#!/usr/bin/env python3
import hashlib
import hmac
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
import contextlib

import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))

import community_rewards


class CommunityRewardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.config = self.root / "config.json"
        self.config.write_text((ROOT / "config" / "community-rewards.example.json").read_text(), encoding="utf-8")
        self.clock = ["2026-07-15T00:00:00Z"]
        self.store = community_rewards.Store(self.root / "state" / "rewards.sqlite3", self.config, now=lambda: self.clock[0])
        self.store.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_link_code_is_one_time_and_wallet_isolated(self):
        link = self.store.create_link_code(42)
        self.assertNotIn(link["code"], (self.root / "state" / "rewards.sqlite3").read_bytes().decode("latin1", errors="ignore"))
        linked = self.store.redeem_link_code("discord-123", link["code"])
        self.assertEqual(42, linked["duneAccountId"])
        self.assertEqual(0, self.store.account_for_discord("discord-123")["balance"])
        with self.assertRaises(ValueError):
            self.store.redeem_link_code("discord-456", link["code"])

    def test_credit_is_idempotent_and_ledger_verifies(self):
        first = self.store.credit(42, 100, "manual", "manual:test")
        second = self.store.credit(42, 100, "manual", "manual:test")
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(100, self.store.status(42)["account"]["balance"])
        self.assertTrue(self.store.verify_ledger()["ok"])

    def test_ledger_cannot_be_updated_or_deleted(self):
        self.store.credit(42, 10, "manual", "manual:immutable")
        with contextlib.closing(self.store.connect()) as conn:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("update ledger set delta=20")
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("delete from ledger")

    def test_purchase_debits_stock_and_completes_delivery(self):
        self.store.credit(42, 100, "manual", "manual:purchase")
        order = self.store.purchase(42, "field-kit", 1, "request-1")
        replay = self.store.purchase(42, "field-kit", 1, "request-1")
        self.assertFalse(order["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(50, self.store.status(42)["account"]["balance"])
        claimed = self.store.claim_delivery(order["deliveryId"])
        self.assertEqual(2, len(claimed["rewards"]))
        result = self.store.complete_delivery(claimed["id"], claimed["claim_token"], {"itemIds": [1, 2]})
        self.assertEqual("delivered", result["status"])
        self.assertEqual("delivered", self.store.status(42)["purchases"][0]["status"])

    def test_definitive_failure_refunds_once_and_restores_stock(self):
        self.store.credit(42, 100, "manual", "manual:refund")
        before_stock = next(row for row in self.store.status()["offers"] if row["id"] == "field-kit")["stock"]
        order = self.store.purchase(42, "field-kit", 1, "refund-request")
        claimed = self.store.claim_delivery(order["deliveryId"])
        failed = self.store.fail_delivery(claimed["id"], claimed["claim_token"], "inventory full", definitive=True)
        self.assertTrue(failed["refunded"])
        status = self.store.status(42)
        self.assertEqual(100, status["account"]["balance"])
        self.assertEqual(before_stock, next(row for row in status["offers"] if row["id"] == "field-kit")["stock"])
        with self.assertRaises(ValueError):
            self.store.fail_delivery(claimed["id"], claimed["claim_token"], "again", definitive=True)

    def test_ambiguous_failure_does_not_refund(self):
        self.store.credit(42, 100, "manual", "manual:ambiguous")
        order = self.store.purchase(42, "starter-water", 1, "ambiguous-request")
        claimed = self.store.claim_delivery(order["deliveryId"])
        failed = self.store.fail_delivery(claimed["id"], claimed["claim_token"], "timeout after send", definitive=False)
        self.assertFalse(failed["refunded"])
        self.assertEqual(90, self.store.status(42)["account"]["balance"])

    def test_webhook_signature_replay_and_payload_collision(self):
        payload = {"eventId": "vote-1", "duneAccountId": 42, "amount": 5}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new(b"secret", b"1000." + raw, hashlib.sha256).hexdigest()
        self.assertTrue(community_rewards.verify_webhook("secret", "1000", raw, signature, now_epoch=1001))
        self.assertFalse(community_rewards.verify_webhook("secret", "1000", raw, signature, now_epoch=2000))
        first = self.store.ingest_webhook("vote", "vote-1", 42, 5, payload)
        replay = self.store.ingest_webhook("vote", "vote-1", 42, 5, payload)
        self.assertFalse(first["idempotent"])
        self.assertTrue(replay["idempotent"])
        with self.assertRaises(ValueError):
            self.store.ingest_webhook("vote", "vote-1", 42, 6, dict(payload, amount=6))

    def test_playtime_accrual_is_bounded_and_idempotent_by_checkpoint(self):
        self.store.observe_playtime(42, True, 1000, 60, 2, 120)
        result = self.store.observe_playtime(42, True, 1060, 60, 2, 120)
        replay = self.store.observe_playtime(42, True, 1060, 60, 2, 120)
        capped = self.store.observe_playtime(42, True, 2060, 60, 2, 120)
        self.assertEqual(2, result["credited"])
        self.assertEqual(0, replay["credited"])
        self.assertEqual(4, capped["credited"])
        self.assertEqual(6, self.store.status(42)["account"]["balance"])

    def test_track_progress_and_claim_are_versioned_and_idempotent(self):
        first = self.store.add_track_progress(42, "season-1", 10, "vote:1")
        replay = self.store.add_track_progress(42, "season-1", 10, "vote:1")
        self.assertEqual(10, first["xp"])
        self.assertTrue(replay["idempotent"])
        claim = self.store.claim_track_level(42, "season-1", 1)
        claim_replay = self.store.claim_track_level(42, "season-1", 1)
        self.assertFalse(claim["idempotent"])
        self.assertTrue(claim_replay["idempotent"])
        self.assertEqual(claim["deliveryId"], claim_replay["deliveryId"])

    def test_config_update_preserves_stock_within_version_and_resets_on_version(self):
        self.store.credit(42, 100, "manual", "manual:config")
        self.store.purchase(42, "field-kit", 1, "stock-use")
        self.store.sync_config()
        self.assertEqual(24, next(row for row in self.store.status()["offers"] if row["id"] == "field-kit")["stock"])
        config = json.loads(self.config.read_text())
        offer = next(row for row in config["offers"] if row["id"] == "field-kit")
        offer["version"] = 2
        offer["stock"] = 50
        self.config.write_text(json.dumps(config), encoding="utf-8")
        self.store.sync_config()
        self.assertEqual(50, next(row for row in self.store.status()["offers"] if row["id"] == "field-kit")["stock"])

    def test_database_and_directory_are_locked_to_configured_host_owner(self):
        owned = community_rewards.Store(self.root / "owned" / "state.sqlite3", self.config, owner_uid=os.getuid(), owner_gid=os.getgid())
        owned.initialize()
        self.assertEqual(0o700, (self.root / "owned").stat().st_mode & 0o777)
        self.assertEqual(0o600, (self.root / "owned" / "state.sqlite3").stat().st_mode & 0o777)
        self.assertEqual(os.getuid(), (self.root / "owned" / "state.sqlite3").stat().st_uid)


if __name__ == "__main__":
    unittest.main()
