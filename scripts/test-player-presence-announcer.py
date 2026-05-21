#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest
import unittest.mock


SCRIPT_PATH = pathlib.Path(__file__).with_name("player-presence-announcer.py")
SPEC = importlib.util.spec_from_file_location("player_presence_announcer", SCRIPT_PATH)
player_presence_announcer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(player_presence_announcer)


class PrivateMessageRoutingTests(unittest.TestCase):
    def test_private_message_uses_whisper_exchange_and_target_queue(self):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs["env"]

            class Result:
                returncode = 0
                stdout = "{}"
                stderr = ""

            return Result()

        player = {
            "name": "Lukano",
            "flsId": "6FF6498F4074E3DE",
        }
        file_env = {
            "DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_EXCHANGE": "chat.whispers",
            "DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL": "Whispers",
            "DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_ROUTING_KEY": "",
            "DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_COMMAND": "/bin/echo",
            "DUNE_PLAYER_PRESENCE_ANNOUNCE_TIMEOUT_SECONDS": "10",
        }

        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.object(player_presence_announcer.subprocess, "run", fake_run):
            result = player_presence_announcer.private_message(player, "private test")

        self.assertTrue(result["ok"])
        self.assertEqual(captured["command"], ["/bin/echo", "private test"])
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_ENV_OVERRIDES_FILE"], "true")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_EXCHANGE"], "chat.whispers")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_CHANNEL"], "Whispers")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"], "Lukano")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"], "6FF6498F4074E3DE_queue")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"], "6FF6498F4074E3DE")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS"], "true")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES"], "false")


if __name__ == "__main__":
    unittest.main()
