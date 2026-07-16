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
import datetime as dt

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

    @staticmethod
    def engagement_policy(**overrides):
        policy = {
            "enabled": True,
            "maxObservationGapSeconds": 120,
            "minimumMovementDistance": 50,
            "movementGraceSeconds": 180,
            "hourly": {"enabled": False},
            "daily": {"enabled": False},
            "weekly": {"enabled": False},
        }
        policy.update(overrides)
        return policy

    @staticmethod
    def location(x, map_name="HaggaBasin", partition=1):
        return {"map": map_name, "partitionId": partition, "x": x, "y": 0, "z": 0}

    def test_engagement_requires_movement_then_uses_bounded_grace(self):
        policy = self.engagement_policy()
        first = self.store.observe_engagement(42, True, 1000, self.location(0), policy)
        still = self.store.observe_engagement(42, True, 1060, self.location(0), policy)
        moved = self.store.observe_engagement(42, True, 1120, self.location(54), policy)
        grace = self.store.observe_engagement(42, True, 1180, self.location(54), policy)
        idle = self.store.observe_engagement(42, True, 1361, self.location(54), policy)
        replay = self.store.observe_engagement(42, True, 1361, self.location(200), policy)

        self.assertTrue(first["firstObservation"])
        self.assertFalse(still["active"])
        self.assertTrue(moved["moved"])
        self.assertEqual(50.0, moved["distance"])
        self.assertEqual(60, moved["activeSeconds"])
        self.assertEqual(60, grace["activeSeconds"])
        self.assertEqual(0, idle["activeSeconds"])
        self.assertTrue(replay["replay"])
        self.assertEqual(50.0, self.store.status(42)["engagementCheckpoint"]["x"])

    def test_engagement_does_not_infer_activity_without_coordinates(self):
        policy = self.engagement_policy()
        self.store.observe_engagement(42, True, 1000, {"map": "HaggaBasin"}, policy)
        result = self.store.observe_engagement(42, True, 1060, {"map": "HaggaBasin"}, policy)
        self.assertFalse(result["active"])
        self.assertEqual([], result["rewards"])

    def test_daily_streak_rewards_are_idempotent_and_reset_after_gap(self):
        policy = self.engagement_policy(daily={
            "enabled": True,
            "repeatLast": True,
            "tiers": [
                {"day": 1, "reward": {"credits": 5}},
                {"day": 3, "reward": {"credits": 10}},
            ],
        })
        start = int(dt.datetime(2026, 7, 13, 12, tzinfo=dt.timezone.utc).timestamp())
        x = 0
        for day in (0, 1, 2, 4):
            base = start + day * 86400
            x += 100
            self.store.observe_engagement(42, True, base, self.location(x), policy)
            x += 100
            result = self.store.observe_engagement(42, True, base + 60, self.location(x), policy)
            self.assertEqual(1, len(result["rewards"]))
            replay = self.store.observe_engagement(42, True, base + 60, self.location(x + 100), policy)
            self.assertTrue(replay["replay"])

        status = self.store.status(42)
        self.assertEqual([1, 1, 2, 3], sorted(row["streak"] for row in status["engagementDays"]))
        self.assertEqual(25, status["account"]["balance"])
        self.assertEqual(4, len(status["engagementClaims"]))

    def test_hourly_scaling_and_weekly_thresholds_share_receipted_rewards(self):
        policy = self.engagement_policy(
            hourly={
                "enabled": True,
                "intervalSeconds": 60,
                "maxRewardsPerSession": 3,
                "tiers": [
                    {"fromHour": 1, "reward": {"credits": 1}},
                    {"fromHour": 2, "reward": {"credits": 2, "items": [
                        {"type": "item", "templateId": "WaterPack_Consumable", "count": 1}
                    ]}},
                ],
            },
            weekly={
                "enabled": True,
                "thresholds": [
                    {"activeSeconds": 60, "reward": {"credits": 3}},
                    {"activeSeconds": 120, "reward": {"credits": 4}},
                ],
            },
        )
        self.store.observe_engagement(42, True, 1000, self.location(0), policy)
        first = self.store.observe_engagement(42, True, 1060, self.location(100), policy)
        second = self.store.observe_engagement(42, True, 1120, self.location(200), policy)

        self.assertEqual({"hourly", "weekly"}, {row["kind"] for row in first["rewards"]})
        self.assertEqual({"hourly", "weekly"}, {row["kind"] for row in second["rewards"]})
        status = self.store.status(42)
        self.assertEqual(10, status["account"]["balance"])
        self.assertEqual(4, len(status["engagementClaims"]))
        self.assertEqual(1, status["deliveryCounts"]["queued"])

    def test_engagement_track_reward_is_idempotent_and_session_resets_offline(self):
        policy = self.engagement_policy(hourly={
            "enabled": True,
            "intervalSeconds": 60,
            "maxRewardsPerSession": 1,
            "tiers": [{"fromHour": 1, "reward": {"track": {"id": "season-1", "xp": 7}}}],
        })
        self.store.observe_engagement(42, True, 1000, self.location(0), policy)
        self.store.observe_engagement(42, True, 1060, self.location(100), policy)
        self.store.observe_engagement(42, False, 1120, self.location(100), policy)
        self.store.observe_engagement(42, True, 1180, self.location(200), policy)
        second_session = self.store.observe_engagement(42, True, 1240, self.location(300), policy)

        self.assertEqual(1, len(second_session["rewards"]))
        status = self.store.status(42)
        self.assertEqual(14, status["progress"][0]["xp"])
        self.assertEqual(2, len(status["engagementClaims"]))

    def test_engagement_claims_are_append_only(self):
        policy = self.engagement_policy(daily={
            "enabled": True,
            "repeatLast": True,
            "tiers": [{"day": 1, "reward": {"credits": 1}}],
        })
        self.store.observe_engagement(42, True, 1000, self.location(0), policy)
        self.store.observe_engagement(42, True, 1060, self.location(100), policy)
        with contextlib.closing(self.store.connect()) as conn:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("update engagement_claims set tier=2")
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("delete from engagement_claims")

    def test_engagement_config_rejects_unsorted_thresholds(self):
        with self.assertRaisesRegex(ValueError, "increasing activeSeconds"):
            community_rewards.engagement_config({"engagementRewards": {
                "weekly": {"enabled": True, "thresholds": [
                    {"activeSeconds": 120, "reward": {"credits": 1}},
                    {"activeSeconds": 60, "reward": {"credits": 1}},
                ]}
            }})

    def test_config_rejects_engagement_reward_with_missing_track(self):
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["engagementRewards"]["hourly"]["tiers"][0]["reward"]["track"]["id"] = "missing-track"
        self.config.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unavailable tracks: missing-track"):
            community_rewards.load_config(self.config)

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
