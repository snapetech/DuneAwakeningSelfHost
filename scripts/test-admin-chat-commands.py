#!/usr/bin/env python3
import contextlib
import io
import importlib.util
import pathlib
import tempfile
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
            sender_name = "AdminUser"
            sender_fls_id = "TEST_FLS_ID"
            resolved_admin = ""
            return admin_chat_commands.run_announce("private reply")

        with unittest.mock.patch.object(admin_chat_commands.subprocess, "run", fake_run), \
             unittest.mock.patch.object(admin_chat_commands, "env", fake_env):
            result = handle_command()

        self.assertTrue(result["ok"])
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_EXCHANGE"], "chat.whispers")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_CHANNEL"], "Whispers")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"], "AdminUser")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS"], "TEST_FLS_ID")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"], "TEST_FLS_ID_queue")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"], "TEST_FLS_ID")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES"], "false")

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

        with unittest.mock.patch.object(admin_chat_commands, "resolve_sender_character", lambda conn, sender_name, sender_fls_id: "AdminUser"), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: ({"character_name": "AdminUser"}, [])), \
             unittest.mock.patch.object(admin_chat_commands, "auction_item", fake_auction_item), \
             unittest.mock.patch.object(admin_chat_commands, "run_announce", fake_run_announce):
            result = admin_chat_commands.handle_command(
                object(),
                "&auction PwerPck 1 456",
                sender_name="AdminUser",
                sender_fls_id="TEST_FLS_ID",
                reply=True,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["reply"]["ok"])
        self.assertIn("did you mean PowerPack2", captured["message"])
        self.assertEqual(captured["targetName"], "AdminUser")
        self.assertEqual(captured["targetFlsId"], "TEST_FLS_ID")

    def test_list_replies_with_online_players_and_maps(self):
        captured = {}

        def fake_run_announce(message, target_name="", target_fls_id=""):
            captured["message"] = message
            captured["targetName"] = target_name
            captured["targetFlsId"] = target_fls_id
            return {"ok": True, "stdout": '{"transport":"chat.whispers"}', "stderr": ""}

        players = [
            {"character_name": "Lukano", "map_label": "Abbir"},
            {"character_name": "Pablo", "map_label": "HaggaBasin"},
        ]

        with unittest.mock.patch.object(admin_chat_commands, "online_player_list", lambda conn: players), \
             unittest.mock.patch.object(admin_chat_commands, "run_announce", fake_run_announce):
            result = admin_chat_commands.handle_command(
                object(),
                "&list",
                sender_name="Pablo",
                sender_fls_id="TEST_FLS_ID",
                reply=True,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "list")
        self.assertEqual(result["message"], "online players: Lukano (Abbir), Pablo (HaggaBasin)")
        self.assertEqual(captured["message"], result["message"])
        self.assertEqual(captured["targetName"], "Pablo")
        self.assertEqual(captured["targetFlsId"], "TEST_FLS_ID")

    def test_list_handles_empty_roster(self):
        with unittest.mock.patch.object(admin_chat_commands, "online_player_list", lambda conn: []):
            result = admin_chat_commands.handle_command(object(), "&list", sender_name="Pablo", sender_fls_id="TEST_FLS_ID")

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "no players online")

    def test_inv_list_replies_with_item_codes(self):
        captured = {}
        items = [{"id": 123, "template_id": "SteelBar", "stack_size": 500}]

        def fake_run_announce(message, target_name="", target_fls_id=""):
            captured["message"] = message
            captured["targetName"] = target_name
            captured["targetFlsId"] = target_fls_id
            return {"ok": True, "stdout": '{"transport":"chat.whispers"}', "stderr": ""}

        with unittest.mock.patch.object(admin_chat_commands, "resolve_sender_character", lambda conn, sender_name, sender_fls_id: "Lukano"), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: ({"character_name": "Lukano"}, [])), \
             unittest.mock.patch.object(admin_chat_commands, "inventory_list_for_player", lambda conn, player: (items, "inventory: 500x Steel Ingot code=SteelBar item-id=123")), \
             unittest.mock.patch.object(admin_chat_commands, "run_announce", fake_run_announce):
            result = admin_chat_commands.handle_command(
                object(),
                "&inv_list",
                sender_name="Lukano",
                sender_fls_id="TEST_FLS_ID",
                reply=True,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "inv_list")
        self.assertEqual(result["message"], "inventory: 500x Steel Ingot code=SteelBar item-id=123")
        self.assertEqual(captured["targetName"], "Lukano")
        self.assertEqual(captured["targetFlsId"], "TEST_FLS_ID")

    def test_bare_auction_replies_with_usage_and_inventory_list(self):
        items = [{"id": 123, "template_id": "SteelBar", "stack_size": 500}]

        with unittest.mock.patch.object(admin_chat_commands, "resolve_sender_character", lambda conn, sender_name, sender_fls_id: "Lukano"), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: ({"character_name": "Lukano"}, [])), \
             unittest.mock.patch.object(admin_chat_commands, "inventory_list_for_player", lambda conn, player: (items, "inventory: 500x Steel Ingot code=SteelBar item-id=123")):
            result = admin_chat_commands.handle_command(
                object(),
                "&auction",
                sender_name="Lukano",
                sender_fls_id="TEST_FLS_ID",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "auction.help")
        self.assertIn("usage: &auction --item-id <item-id> <count> <price>", result["message"])
        self.assertIn("inventory: 500x Steel Ingot code=SteelBar item-id=123", result["message"])

    def test_exchange_list_replies_with_sender_active_sales(self):
        captured = {}
        calls = {}
        player = {"character_name": "Lukano", "player_controller_id": 17}
        orders = [{"id": 456, "template_id": "SteelBar", "stack_size": 100, "item_price": 1200}]

        def fake_run_announce(message, target_name="", target_fls_id=""):
            captured["message"] = message
            captured["targetName"] = target_name
            captured["targetFlsId"] = target_fls_id
            return {"ok": True, "stdout": '{"transport":"chat.whispers"}', "stderr": ""}

        def fake_player_exchange_list_rows(conn, resolved_player, limit):
            calls["player"] = resolved_player
            calls["limit"] = limit
            return orders, 1

        with unittest.mock.patch.object(admin_chat_commands, "resolve_sender_character", lambda conn, sender_name, sender_fls_id: "Lukano"), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (player, [])), \
             unittest.mock.patch.object(admin_chat_commands, "player_exchange_list_rows", fake_player_exchange_list_rows), \
             unittest.mock.patch.object(admin_chat_commands, "item_display_names", lambda: {"SteelBar": "Steel Ingot"}), \
             unittest.mock.patch.object(admin_chat_commands, "run_announce", fake_run_announce):
            result = admin_chat_commands.handle_command(
                object(),
                "&exchange_list 10",
                sender_name="Lukano",
                sender_fls_id="TEST_FLS_ID",
                reply=True,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "exchange_list")
        self.assertEqual(calls["player"], player)
        self.assertEqual(calls["limit"], 10)
        self.assertEqual(result["message"], "exchange: showing 1/1 active sales: order 456: 100x Steel Ingot code=SteelBar price=1200")
        self.assertEqual(captured["message"], result["message"])
        self.assertEqual(captured["targetName"], "Lukano")
        self.assertEqual(captured["targetFlsId"], "TEST_FLS_ID")

    def test_exchange_list_handles_no_active_sales(self):
        player = {"character_name": "Lukano", "player_controller_id": 17}

        with unittest.mock.patch.object(admin_chat_commands, "resolve_sender_character", lambda conn, sender_name, sender_fls_id: "Lukano"), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (player, [])), \
             unittest.mock.patch.object(admin_chat_commands, "player_exchange_list_rows", lambda conn, resolved_player, limit: ([], 0)):
            result = admin_chat_commands.handle_command(
                object(),
                "&exchange_list",
                sender_name="Lukano",
                sender_fls_id="TEST_FLS_ID",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message"], "exchange: you have no active sales")

    def test_exchange_cashout_previews_when_disabled(self):
        player = {"character_name": "Lukano", "player_controller_id": 17}
        calls = {}

        def fake_player_exchange_cashout(conn, resolved_player, dry_run=True):
            calls["player"] = resolved_player
            calls["dryRun"] = dry_run
            return {"ok": True, "dryRun": True, "candidateCount": 2, "total": 2, "expectedSolari": 2400, "claimed": []}

        with unittest.mock.patch.object(admin_chat_commands, "resolve_sender_character", lambda conn, sender_name, sender_fls_id: "Lukano"), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (player, [])), \
             unittest.mock.patch.object(admin_chat_commands, "chat_exchange_cashout_enabled", lambda: False), \
             unittest.mock.patch.object(admin_chat_commands, "player_exchange_cashout", fake_player_exchange_cashout):
            result = admin_chat_commands.handle_command(
                object(),
                "&exchange_cashout",
                sender_name="Lukano",
                sender_fls_id="TEST_FLS_ID",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "exchange_cashout")
        self.assertTrue(calls["dryRun"])
        self.assertEqual(calls["player"], player)
        self.assertEqual(result["message"], "exchange cashout preview: 2400 Solaris from 2/2 completed sales; enable DUNE_CHAT_COMMAND_EXCHANGE_CASHOUT_ENABLED=true to execute")

    def test_exchange_cashout_executes_when_enabled(self):
        player = {"character_name": "Lukano", "player_controller_id": 17}
        calls = {}

        def fake_player_exchange_cashout(conn, resolved_player, dry_run=True):
            calls["player"] = resolved_player
            calls["dryRun"] = dry_run
            return {"ok": True, "dryRun": False, "claimed": [{"orderId": 456, "credited": 1200}], "candidateCount": 1, "total": 1, "credited": 1200}

        with unittest.mock.patch.object(admin_chat_commands, "resolve_sender_character", lambda conn, sender_name, sender_fls_id: "Lukano"), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (player, [])), \
             unittest.mock.patch.object(admin_chat_commands, "chat_exchange_cashout_enabled", lambda: True), \
             unittest.mock.patch.object(admin_chat_commands, "player_exchange_cashout", fake_player_exchange_cashout):
            result = admin_chat_commands.handle_command(
                object(),
                "&exchange_cashout",
                sender_name="Lukano",
                sender_fls_id="TEST_FLS_ID",
            )

        self.assertTrue(result["ok"])
        self.assertFalse(calls["dryRun"])
        self.assertEqual(calls["player"], player)
        self.assertEqual(result["message"], "exchange cashout: credited 1200 Solaris from 1 completed sales")

    def test_gm_subcommand_includes_inferred_private_reply_metadata(self):
        def fake_run_announce(message, target_name="", target_fls_id=""):
            admin_chat_commands.LAST_ANNOUNCE_RESULT = {"ok": True, "stdout": '{"transport":"chat.whispers"}', "stderr": ""}
            return admin_chat_commands.LAST_ANNOUNCE_RESULT

        with unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "AdminUser")), \
             unittest.mock.patch.object(admin_chat_commands, "run_announce", fake_run_announce):
            result = admin_chat_commands.handle_command(
                object(),
                "&gm",
                sender_name="AdminUser",
                sender_fls_id="TEST_FLS_ID",
                reply=True,
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["reply"]["ok"])
        self.assertIn("chat.whispers", result["reply"]["stdout"])

    def test_gm_catalog_reports_wiring_status(self):
        with unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "AdminUser")), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (None, [])):
            result = admin_chat_commands.handle_command(object(), "&gm catalog", sender_name="AdminUser")

        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "gm.catalog")
        self.assertIn("wired-preview", result["message"])
        command_names = {command["name"] for command in result["catalog"]["commands"]}
        self.assertIn("PrintPos", command_names)
        self.assertIn("DestroyEntireBuilding", command_names)

    def test_missing_sender_fls_id_is_resolved_for_private_reply(self):
        captured = {}

        def fake_run(command, **kwargs):
            captured["env"] = kwargs["env"]

            class Result:
                returncode = 0
                stdout = '{"transport":"chat.whispers","exchange":"chat.whispers"}'
                stderr = ""

            return Result()

        def fake_env(name, default=""):
            values = {
                "DUNE_CHAT_COMMAND_REPLY_COMMAND": "/bin/echo",
                "DUNE_CHAT_COMMAND_TARGET_REPLY_MODE": "whisper",
                "DUNE_CHAT_COMMAND_PRIVATE_REPLY_EXCHANGE": "chat.whispers",
                "DUNE_CHAT_COMMAND_PRIVATE_REPLY_CHANNEL": "Whispers",
                "DUNE_CHAT_COMMAND_REPLY_TIMEOUT_SECONDS": "10",
            }
            return values.get(name, default)

        with unittest.mock.patch.object(admin_chat_commands, "fls_id_for_sender", lambda conn, sender_name: "FLS_FROM_DB"), \
             unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Lukano")), \
             unittest.mock.patch.object(admin_chat_commands.subprocess, "run", fake_run), \
             unittest.mock.patch.object(admin_chat_commands, "env", fake_env):
            result = admin_chat_commands.handle_command(object(), "&test", sender_name="Lukano", reply=True)

        self.assertTrue(result["ok"])
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_EXCHANGE"], "chat.whispers")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS"], "FLS_FROM_DB")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"], "FLS_FROM_DB_queue")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_BIND_ONLINE_QUEUES"], "false")

    def test_whisper_reply_does_not_fall_back_to_public_without_target(self):
        def fake_env(name, default=""):
            values = {
                "DUNE_CHAT_COMMAND_TARGET_REPLY_MODE": "whisper",
            }
            return values.get(name, default)

        with unittest.mock.patch.object(admin_chat_commands, "env", fake_env), \
             unittest.mock.patch.object(admin_chat_commands.subprocess, "run") as run:
            result = admin_chat_commands.run_announce("must stay private")

        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertIn("refusing public fallback", result["reason"])
        run.assert_not_called()


class OnlineTeleportSafetyTests(unittest.TestCase):
    def row(self, name, partition_id=1, status="Online", x=10.0):
        return {
            "account_id": 1,
            "character_name": name,
            "online_status": status,
            "life_state": "Alive",
            "server_id": f"Survival_1{partition_id}",
            "player_controller_id": 100 + partition_id,
            "player_pawn_id": 200 + partition_id,
            "fls_id": f"fls-{name}",
            "funcom_id": f"funcom-{name}",
            "actor_map": "HaggaBasin",
            "partition_id": partition_id,
            "dimension_index": 0,
            "partition_label": f"Partition {partition_id}",
            "partition_map": "Survival_1",
            "x": x,
            "y": 20.0,
            "z": 30.0,
        }

    def test_online_goto_blocks_different_routes_before_publish(self):
        admin = self.row("AdminUser", partition_id=1)
        target = self.row("Tester", partition_id=2)

        def fake_character_row(conn, name):
            return (admin if name == "AdminUser" else target), []

        with unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "AdminUser")), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", fake_character_row), \
             unittest.mock.patch.object(admin_chat_commands, "send_gm_command") as send_gm:
            result = admin_chat_commands.handle_command(object(), "&goto Tester", sender_name="AdminUser")

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertIn("same-route live teleport guard", result["reason"])
        send_gm.assert_not_called()

    def test_online_bring_same_route_requires_arm_even_when_gates_are_enabled(self):
        admin = self.row("AdminUser", partition_id=1)
        target = self.row("Tester", partition_id=1)

        def fake_character_row(conn, name):
            return (admin if name == "AdminUser" else target), []

        def fake_env(name, default=""):
            values = {
                "DUNE_ADMIN_GM_COMMANDS_ENABLED": "true",
                "DUNE_GM_COMMAND_PAYLOAD_VERIFIED": "true",
                "DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT": "true",
            }
            return values.get(name, default)

        with unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "AdminUser")), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", fake_character_row), \
             unittest.mock.patch.object(admin_chat_commands, "env", fake_env), \
             unittest.mock.patch.object(admin_chat_commands, "publish_command", lambda command_text, route, **kwargs: {"ok": True, "commandText": command_text, "route": route, **kwargs}):
            result = admin_chat_commands.handle_command(object(), "&bring Tester", sender_name="AdminUser")

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertIn("not armed", result["gm"]["reason"])

    def test_armbring_allows_one_same_route_publish(self):
        admin = self.row("AdminUser", partition_id=1)
        target = self.row("Tester", partition_id=1)

        def fake_character_row(conn, name):
            return (admin if name == "AdminUser" else target), []

        def fake_env(name, default=""):
            values = {
                "DUNE_ADMIN_GM_COMMANDS_ENABLED": "true",
                "DUNE_GM_COMMAND_PAYLOAD_VERIFIED": "true",
                "DUNE_CHAT_COMMAND_EXECUTE_ONLINE_GM_TELEPORT": "true",
                "DUNE_CHAT_COMMAND_ONLINE_GM_TELEPORT_ARM_SECONDS": "30",
            }
            return values.get(name, default)

        with tempfile.TemporaryDirectory() as tmpdir:
            arm_file = pathlib.Path(tmpdir) / "online-gm-teleport-arm.json"
            with unittest.mock.patch.object(admin_chat_commands, "ONLINE_GM_TELEPORT_ARM_FILE", arm_file), \
                 unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "AdminUser")), \
                 unittest.mock.patch.object(admin_chat_commands, "character_row", fake_character_row), \
                 unittest.mock.patch.object(admin_chat_commands, "env", fake_env), \
                 unittest.mock.patch.object(admin_chat_commands, "publish_command", lambda command_text, route, **kwargs: {"ok": True, "commandText": command_text, "route": route, **kwargs}):
                arm = admin_chat_commands.handle_command(object(), "&armbring Tester", sender_name="AdminUser")
                first = admin_chat_commands.handle_command(object(), "&bring Tester", sender_name="AdminUser")
                second = admin_chat_commands.handle_command(object(), "&bring Tester", sender_name="AdminUser")

        self.assertTrue(arm["ok"])
        self.assertTrue(first["ok"])
        self.assertFalse(first["blocked"])
        self.assertEqual(first["gm"]["commandText"], "TeleportToExact 10.000 20.000 30.000")
        self.assertEqual(first["gm"]["route"], "Survival_11")
        self.assertFalse(second["ok"])
        self.assertTrue(second["blocked"])
        self.assertIn("not armed", second["gm"]["reason"])


class OfflineTeleportCommandTests(unittest.TestCase):
    def row(self, name, partition_id=1, status="Offline", x=10.0):
        return {
            "account_id": 1,
            "character_name": name,
            "online_status": status,
            "life_state": "Alive",
            "server_id": f"Survival_1{partition_id}",
            "player_controller_id": 100 + partition_id,
            "player_pawn_id": 200 + partition_id,
            "fls_id": f"fls-{name}",
            "funcom_id": f"funcom-{name}",
            "actor_map": "HaggaBasin",
            "partition_id": partition_id,
            "dimension_index": 0,
            "partition_label": f"Partition {partition_id}",
            "partition_map": "Survival_1",
            "x": x,
            "y": 20.0,
            "z": 30.0,
        }

    def test_offline_teleport_execute_uses_first_party_helper(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)
        target = self.row("Tester", partition_id=7, status="Offline", x=1.0)
        events = []

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                events.append(("execute", sql, params))

            def fetchall(self):
                return [(None,)]

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def commit(self):
                events.append(("commit",))

        def fake_character_row(conn, name):
            return (admin if name == "Admin" else target), []

        def fake_env(name, default=""):
            values = {
                "DUNE_CHAT_COMMAND_EXECUTE_TELEPORT": "true",
                "DUNE_CHAT_COMMAND_DRY_RUN": "false",
            }
            return values.get(name, default)

        with unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", fake_character_row), \
             unittest.mock.patch.object(admin_chat_commands, "env", fake_env), \
             unittest.mock.patch.object(admin_chat_commands, "run_announce", lambda message, **kwargs: {"ok": True, "message": message}):
            result = admin_chat_commands.handle_command(FakeConn(), "&teleport Tester", sender_name="Admin")

        helper_calls = [event for event in events if event[0] == "execute" and "dune.admin_move_offline_player_to_partition" in event[1]]
        self.assertTrue(result["ok"])
        self.assertFalse(result["dryRun"])
        self.assertEqual(len(helper_calls), 1)
        self.assertEqual(helper_calls[0][2], ("fls-Tester", 7, 100.0, 20.0, 30.0))
        self.assertEqual(result["moveResult"]["function"], "dune.admin_move_offline_player_to_partition")
        self.assertIn(("commit",), events)
        self.assertFalse(any(event[0] == "execute" and "update dune.actors" in event[1].lower() for event in events))

    def test_offline_teleport_dry_run_does_not_call_helper(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)
        target = self.row("Tester", partition_id=7, status="Offline", x=1.0)

        def fake_character_row(conn, name):
            return (admin if name == "Admin" else target), []

        with unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
             unittest.mock.patch.object(admin_chat_commands, "character_row", fake_character_row), \
             unittest.mock.patch.object(admin_chat_commands, "move_offline_player_to_partition") as move:
            result = admin_chat_commands.handle_command(object(), "&teleport Tester", sender_name="Admin")

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        move.assert_not_called()

    def test_teleport_set_creates_empty_slot_from_admin_location(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            slot_file = pathlib.Path(tmpdir) / "teleport-slots.json"
            with unittest.mock.patch.object(admin_chat_commands, "TELEPORT_SLOT_FILE", slot_file), \
                 unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
                 unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (admin, [])):
                result = admin_chat_commands.handle_command(object(), "&teleport set 0 arrakeen", sender_name="Admin")

        self.assertTrue(result["ok"])
        self.assertEqual(result["location"]["slot"], 0)
        self.assertEqual(result["location"]["name"], "arrakeen")
        self.assertEqual(result["location"]["partitionId"], 7)
        self.assertEqual(result["location"]["x"], 100.0)

    def test_teleport_set_refuses_overwrite_and_reports_next_free_slot(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            slot_file = pathlib.Path(tmpdir) / "teleport-slots.json"
            with unittest.mock.patch.object(admin_chat_commands, "TELEPORT_SLOT_FILE", slot_file), \
                 unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
                 unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (admin, [])):
                first = admin_chat_commands.handle_command(object(), "&teleport set 0 arrakeen", sender_name="Admin")
                second = admin_chat_commands.handle_command(object(), "&teleport set 0 harko", sender_name="Admin")

        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(second["nextFreeSlot"], 1)
        self.assertIn("slot 0", second["error"])
        self.assertIn("next free slot is 1", second["error"])
        self.assertIn("&teleport replace 0", second["error"])

    def test_teleport_replace_overwrites_existing_slot(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)
        moved_admin = self.row("Admin", partition_id=8, status="Online", x=500.0)
        calls = {"count": 0}

        def fake_character_row(conn, name):
            calls["count"] += 1
            return (admin if calls["count"] == 1 else moved_admin), []

        with tempfile.TemporaryDirectory() as tmpdir:
            slot_file = pathlib.Path(tmpdir) / "teleport-slots.json"
            with unittest.mock.patch.object(admin_chat_commands, "TELEPORT_SLOT_FILE", slot_file), \
                 unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
                 unittest.mock.patch.object(admin_chat_commands, "character_row", fake_character_row):
                admin_chat_commands.handle_command(object(), "&teleport set 0 arrakeen", sender_name="Admin")
                result = admin_chat_commands.handle_command(object(), "&teleport replace 0 harko", sender_name="Admin")

        self.assertTrue(result["ok"])
        self.assertEqual(result["location"]["name"], "harko")
        self.assertEqual(result["location"]["partitionId"], 8)
        self.assertEqual(result["location"]["x"], 500.0)

    def test_teleport_delete_removes_slot(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            slot_file = pathlib.Path(tmpdir) / "teleport-slots.json"
            with unittest.mock.patch.object(admin_chat_commands, "TELEPORT_SLOT_FILE", slot_file), \
                 unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
                 unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (admin, [])):
                admin_chat_commands.handle_command(object(), "&teleport set 0 arrakeen", sender_name="Admin")
                deleted = admin_chat_commands.handle_command(object(), "&teleport delete 0", sender_name="Admin")
                listed = admin_chat_commands.handle_command(object(), "&teleport list", sender_name="Admin")

        self.assertTrue(deleted["ok"])
        self.assertEqual(listed["locations"], [])

    def test_teleport_list_returns_slots_in_numeric_order(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            slot_file = pathlib.Path(tmpdir) / "teleport-slots.json"
            with unittest.mock.patch.object(admin_chat_commands, "TELEPORT_SLOT_FILE", slot_file), \
                 unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
                 unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (admin, [])):
                admin_chat_commands.handle_command(object(), "&teleport set 10 ten", sender_name="Admin")
                admin_chat_commands.handle_command(object(), "&teleport set 2 two", sender_name="Admin")
                result = admin_chat_commands.handle_command(object(), "&teleport locations", sender_name="Admin")

        self.assertEqual([location["slot"] for location in result["locations"]], [2, 10])

    def test_offline_teleport_to_slot_uses_first_party_helper(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)
        target = self.row("Tester", partition_id=1, status="Offline", x=1.0)

        def fake_character_row(conn, name):
            return (admin if name == "Admin" else target), []

        def fake_env(name, default=""):
            values = {
                "DUNE_CHAT_COMMAND_EXECUTE_TELEPORT": "true",
                "DUNE_CHAT_COMMAND_DRY_RUN": "false",
            }
            return values.get(name, default)

        with tempfile.TemporaryDirectory() as tmpdir:
            slot_file = pathlib.Path(tmpdir) / "teleport-slots.json"
            with unittest.mock.patch.object(admin_chat_commands, "TELEPORT_SLOT_FILE", slot_file), \
                 unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
                 unittest.mock.patch.object(admin_chat_commands, "character_row", fake_character_row), \
                 unittest.mock.patch.object(admin_chat_commands, "env", fake_env), \
                 unittest.mock.patch.object(admin_chat_commands, "move_offline_player_to_partition", return_value={"function": "dune.admin_move_offline_player_to_partition"}) as move:
                class FakeConn:
                    def commit(self):
                        pass

                admin_chat_commands.handle_command(FakeConn(), "&teleport set 0 arrakeen", sender_name="Admin")
                result = admin_chat_commands.handle_command(FakeConn(), "&teleport Tester 0", sender_name="Admin")

        self.assertTrue(result["ok"])
        self.assertFalse(result["dryRun"])
        move.assert_called_once_with(unittest.mock.ANY, "fls-Tester", 7, 100.0, 20.0, 30.0)

    def test_teleport_slot_returns_gated_native_preview(self):
        admin = self.row("Admin", partition_id=7, status="Online", x=100.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            slot_file = pathlib.Path(tmpdir) / "teleport-slots.json"
            with unittest.mock.patch.object(admin_chat_commands, "TELEPORT_SLOT_FILE", slot_file), \
                 unittest.mock.patch.object(admin_chat_commands, "is_admin", lambda conn, sender_name, sender_fls_id: (True, "Admin")), \
                 unittest.mock.patch.object(admin_chat_commands, "character_row", lambda conn, name: (admin, [])):
                admin_chat_commands.handle_command(object(), "&teleport set 0 arrakeen", sender_name="Admin")
                result = admin_chat_commands.handle_command(object(), "&teleport 0", sender_name="Admin")

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["gm"]["preview"]["commandText"], "TeleportToExact 100.000 20.000 30.000")
        self.assertEqual(result["gm"]["preview"]["route"], "Survival_17")


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
                "DUNE_CHAT_COMMAND_EXCHANGE": "chat.whispers",
                "DUNE_CHAT_COMMAND_QUEUE": "dash_admin_chat_commands",
                "DUNE_CHAT_COMMAND_ROUTING_KEY": "ADMIN#00001",
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
