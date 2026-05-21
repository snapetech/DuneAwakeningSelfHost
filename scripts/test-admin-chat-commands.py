#!/usr/bin/env python3
import contextlib
import io
import importlib.util
import pathlib
import unittest.mock
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("admin-chat-commands.py")
SPEC = importlib.util.spec_from_file_location("admin_chat_commands", SCRIPT_PATH)
admin_chat_commands = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(admin_chat_commands)


class AuctionCommandParserTests(unittest.TestCase):
    def parse(self, argv):
        return admin_chat_commands.parse_auction_command_args(argv)

    def test_name_listing_defaults_to_personal_inventory(self):
        self.assertEqual(
            self.parse(["PowerPack", "1", "456"]),
            ("personal", None, None, "PowerPack", 1, 456),
        )

    def test_quoted_name_can_contain_spaces(self):
        self.assertEqual(
            self.parse(["power pack", "2", "456"]),
            ("personal", None, None, "power pack", 2, 456),
        )

    def test_base_storage_source(self):
        self.assertEqual(
            self.parse(["--base", "PowerPack", "1", "456"]),
            ("base", None, None, "PowerPack", 1, 456),
        )

    def test_explicit_inventory_source(self):
        self.assertEqual(
            self.parse(["--inventory", "413", "PowerPack", "1", "456"]),
            ("inventory", 413, None, "PowerPack", 1, 456),
        )

    def test_item_id_source(self):
        self.assertEqual(
            self.parse(["--item-id", "33256803", "1", "456"]),
            ("personal", None, 33256803, "item-id:33256803", 1, 456),
        )

    def test_item_id_can_be_combined_with_explicit_inventory(self):
        self.assertEqual(
            self.parse(["--inventory", "413", "--item-id", "33256594", "1", "456"]),
            ("inventory", 413, 33256594, "item-id:33256594", 1, 456),
        )

    def test_item_id_rejects_extra_name(self):
        with self.assertRaisesRegex(ValueError, "do not provide an item name"):
            self.parse(["--item-id", "33256803", "PowerPack", "1", "456"])

    def test_count_must_be_positive_integer(self):
        with self.assertRaisesRegex(ValueError, "count must be a positive integer"):
            self.parse(["PowerPack", "zero", "456"])

    def test_price_must_be_positive_integer(self):
        with self.assertRaisesRegex(ValueError, "price must be a positive integer"):
            self.parse(["PowerPack", "1", "0"])


class CommandReplyTargetTests(unittest.TestCase):
    def test_run_announce_infers_command_sender_for_private_reply(self):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs["env"]

            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return Result()

        def fake_env(name, default=""):
            values = {
                "DUNE_CHAT_COMMAND_REPLY_COMMAND": "/bin/echo",
                "DUNE_CHAT_COMMAND_TARGET_REPLY_MODE": "whisper",
                "DUNE_CHAT_COMMAND_PRIVATE_REPLY_EXCHANGE": "chat.whispers",
                "DUNE_CHAT_COMMAND_PRIVATE_REPLY_CHANNEL": "Whispers",
                "DUNE_CHAT_COMMAND_PRIVATE_REPLY_ROUTING_KEY": "",
                "DUNE_CHAT_COMMAND_REPLY_TIMEOUT_SECONDS": "10",
            }
            return values.get(name, default)

        def handle_command():
            sender_name = "Lukano"
            sender_fls_id = "6FF6498F4074E3DE"
            resolved_admin = ""
            return admin_chat_commands.run_announce("private reply")

        with unittest.mock.patch.object(admin_chat_commands.subprocess, "run", fake_run), \
             unittest.mock.patch.object(admin_chat_commands, "env", fake_env):
            result = handle_command()

        self.assertTrue(result["ok"])
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_EXCHANGE"], "chat.whispers")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_CHANNEL"], "Whispers")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"], "Lukano")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"], "6FF6498F4074E3DE_queue")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"], "6FF6498F4074E3DE")

    def test_auction_suggestion_reply_returns_private_publish_metadata(self):
        captured = {}

        def fake_run_announce(message, target_name="", target_fls_id=""):
            captured["message"] = message
            captured["targetName"] = target_name
            captured["targetFlsId"] = target_fls_id
            return {"ok": True, "stdout": '{"transport":"chat.whispers","exchange":"chat.whispers"}', "stderr": ""}

        def fake_auction_item(conn, player, search_text, count, price, **kwargs):
            return {
                "ok": False,
                "error": "no allowed inventory item matched 'PwerPck'",
                "suggestion": {
                    "itemId": 95039169,
                    "templateId": "PowerPack2",
                    "inventoryId": 15,
                    "score": 0.824,
                },
            }

        with unittest.mock.patch.object(admin_chat_commands, "resolve_sender_character", lambda conn, sender_name, sender_fls_id: "Lukano"), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: ({"character_name": "Lukano"}, [])), \
             unittest.mock.patch.object(admin_chat_commands, "auction_item", fake_auction_item), \
             unittest.mock.patch.object(admin_chat_commands, "run_announce", fake_run_announce):
            result = admin_chat_commands.handle_command(
                object(),
                "&auction PwerPck 1 456",
                sender_name="Lukano",
                sender_fls_id="6FF6498F4074E3DE",
                reply=True,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["reply"]["ok"])
        self.assertIn("did you mean PowerPack2", captured["message"])
        self.assertEqual(captured["targetName"], "Lukano")
        self.assertEqual(captured["targetFlsId"], "6FF6498F4074E3DE")


class CommandListenerRetryTests(unittest.TestCase):
    def test_consume_forever_retries_amqp_connection(self):
        attempts = {"count": 0, "slept": []}

        class FakeChannel:
            def queue_declare(self, **kwargs):
                pass

            def queue_bind(self, **kwargs):
                pass

            def basic_qos(self, **kwargs):
                pass

            def basic_consume(self, **kwargs):
                pass

            def start_consuming(self):
                raise KeyboardInterrupt()

        class FakeConnection:
            def channel(self):
                return FakeChannel()

        def fake_blocking_connection(parameters):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise admin_chat_commands.pika.exceptions.AMQPConnectionError()
            return FakeConnection()

        def fake_env(name, default=""):
            values = {
                "DUNE_CHAT_COMMAND_AMQP_HOST": "game-rmq",
                "DUNE_CHAT_COMMAND_AMQP_PORT": "5672",
                "DUNE_CHAT_COMMAND_AMQP_TLS": "false",
                "DUNE_CHAT_COMMAND_AMQP_USER": "guest",
                "DUNE_CHAT_COMMAND_AMQP_PASSWORD": "guest",
                "DUNE_CHAT_COMMAND_AMQP_RETRY_SECONDS": "0.01",
                "DUNE_CHAT_COMMAND_AMQP_CONNECT_ATTEMPTS": "0",
                "DUNE_CHAT_COMMAND_EXCHANGE": "chat.intercept",
                "DUNE_CHAT_COMMAND_QUEUE": "dash_admin_chat_commands",
                "DUNE_CHAT_COMMAND_ROUTING_KEY": "#",
            }
            return values.get(name, default)

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with unittest.mock.patch.object(admin_chat_commands, "env", fake_env), \
                 unittest.mock.patch.object(admin_chat_commands, "env_chat_or_announce", lambda name, fallback, default="": fake_env(name, default)), \
                 unittest.mock.patch.object(admin_chat_commands.pika, "BlockingConnection", fake_blocking_connection), \
                 unittest.mock.patch.object(admin_chat_commands, "connect_db", lambda: object()), \
                 unittest.mock.patch.object(admin_chat_commands.time, "sleep", lambda seconds: attempts["slept"].append(seconds)):
                with self.assertRaises(KeyboardInterrupt):
                    admin_chat_commands.consume_forever()

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(attempts["slept"], [0.01])


if __name__ == "__main__":
    unittest.main()
