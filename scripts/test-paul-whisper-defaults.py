#!/usr/bin/env python3
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PaulWhisperDefaultsTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_publishers_default_to_confirmed_whisper_timestamp_field(self):
        self.assertIn(
            'env("DUNE_ANNOUNCE_CHAT_TIMESTAMP_FIELD", "m_TimeStamp")',
            self.read("scripts/announce.sh"),
        )
        self.assertIn(
            'env("DUNE_ANNOUNCE_CHAT_TIMESTAMP_FIELD", "m_TimeStamp")',
            self.read("scripts/announce_pika.py"),
        )

    def test_env_template_pins_confirmed_whisper_timestamp_field(self):
        self.assertIn(
            "DUNE_ANNOUNCE_CHAT_TIMESTAMP_FIELD=m_TimeStamp",
            self.read(".env.example"),
        )

    def test_private_callers_do_not_bind_all_online_queues(self):
        for relative_path in (
            "scripts/admin-chat-commands.py",
            "scripts/player-presence-announcer.py",
            "scripts/artificial-exchange-bot.py",
        ):
            with self.subTest(relative_path=relative_path):
                self.assertIn(
                    'DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES"] = "false"',
                    self.read(relative_path),
                )


if __name__ == "__main__":
    unittest.main()
