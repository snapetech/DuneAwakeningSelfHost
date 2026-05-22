#!/usr/bin/env python3
import unittest

from dune_whisper_route import normalize_fls_id, whisper_queue_for_fls_id, whisper_route_for_fls_id


class WhisperRouteTests(unittest.TestCase):
    def test_normalizes_hex_fls_id_to_uppercase(self):
        self.assertEqual(normalize_fls_id("6ff6498f4074e3de"), "6FF6498F4074E3DE")

    def test_derives_player_queue_from_fls_id(self):
        self.assertEqual(whisper_queue_for_fls_id("6ff6498f4074e3de"), "6FF6498F4074E3DE_queue")

    def test_derives_complete_whisper_route(self):
        route = whisper_route_for_fls_id("6ff6498f4074e3de")
        self.assertTrue(route["ok"])
        self.assertEqual(route["exchange"], "chat.whispers")
        self.assertEqual(route["routingKey"], "6FF6498F4074E3DE")
        self.assertEqual(route["queue"], "6FF6498F4074E3DE_queue")
        self.assertEqual(route["channel"], "Whispers")

    def test_rejects_missing_fls_id(self):
        route = whisper_route_for_fls_id("")
        self.assertFalse(route["ok"])
        self.assertEqual(route["error"], "missing FLS id")


if __name__ == "__main__":
    unittest.main()
