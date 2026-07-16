#!/usr/bin/env python3

import importlib.util
import json
import pathlib
import struct
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).with_name("discord-bot.py")
SPEC = importlib.util.spec_from_file_location("dash_discord_bot", SCRIPT)
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)


class DiscordBotTests(unittest.TestCase):
    def test_client_frames_are_masked_and_round_trip_payload(self):
        frame = BOT.encode_client_frame(b"hello")
        self.assertEqual(frame[0], 0x81)
        self.assertTrue(frame[1] & 0x80)
        length = frame[1] & 0x7F
        mask = frame[2:6]
        payload = frame[6:6 + length]
        decoded = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.assertEqual(decoded, b"hello")

    def test_server_frame_decoder_handles_short_and_extended_frames(self):
        short = bytes((0x81, 5)) + b"hello" + b"tail"
        decoded = BOT.decode_server_frame(short)
        self.assertEqual(decoded["payload"], b"hello")
        self.assertEqual(decoded["consumed"], 7)
        payload = b"x" * 130
        extended = bytes((0x81, 126)) + struct.pack("!H", len(payload)) + payload
        self.assertEqual(BOT.decode_server_frame(extended)["payload"], payload)
        with self.assertRaises(ValueError):
            BOT.decode_server_frame(bytes((0x81, 0x81)) + b"x")

    def test_command_catalog_uses_one_guild_only_slash_command(self):
        definition = BOT.command_definition()
        self.assertEqual(definition["name"], "dune")
        self.assertFalse(definition["dm_permission"])
        self.assertEqual({item["name"] for item in definition["options"]}, set(BOT.COMMAND_GROUPS))
        nested = {item["name"] for group in definition["options"] for item in group["options"]}
        self.assertEqual(nested, set(BOT.COMMANDS))
        self.assertEqual(len(BOT.COMMANDS), 37)
        buy = next(item for group in definition["options"] if group["name"] == "shop" for item in group["options"] if item["name"] == "buy")
        self.assertEqual([option["name"] for option in buy["options"]], ["offer", "quantity"])

    def test_grouped_interaction_resolves_nested_subcommand(self):
        command = BOT.interaction_command({"data": {"name": "dune", "options": [{"name": "ops", "options": [{"name": "inventory"}]}]}})
        self.assertEqual(command, "inventory")

    def test_actor_context_preserves_discord_roles(self):
        actor = BOT.actor_from_interaction({
            "guild_id": "1", "channel_id": "2",
            "member": {"roles": ["10", "11"], "user": {"id": "3", "username": "operator"}},
        })
        self.assertEqual(actor, {"guildId": "1", "channelId": "2", "userId": "3", "username": "operator", "roleIds": ["10", "11"]})

    def test_adapter_request_has_bearer_host_and_actor(self):
        config = {"adapterUrl": "http://127.0.0.1:18081", "adapterHost": "admin-panel:8080", "adapterToken": "secret", "requestTimeout": 2.5}
        actor = {"guildId": "1"}
        with mock.patch.object(BOT, "http_json", return_value={"ok": True}) as request:
            BOT.adapter_request(config, "population", actor)
        request.assert_called_once_with(
            "http://127.0.0.1:18081/api/integrations/discord/population",
            method="POST", data={"actor": actor, "arguments": {}}, timeout=2.5,
            headers={"Authorization": "Bearer secret", "Host": "admin-panel:8080"},
        )

    def test_ops_adapter_request_includes_bounded_domain(self):
        config = {"adapterUrl": "http://127.0.0.1:18081", "adapterHost": "admin-panel:8080", "adapterToken": "secret", "requestTimeout": 2.5}
        actor = {"guildId": "1"}
        with mock.patch.object(BOT, "http_json", return_value={"ok": True}) as request:
            BOT.adapter_request(config, "inventory", actor)
        self.assertEqual(request.call_args.kwargs["data"], {"actor": actor, "arguments": {}, "domain": "inventory"})

    def test_shop_arguments_are_bounded_and_forwarded_to_community_adapter(self):
        interaction = {"data": {"name": "dune", "options": [{"name": "shop", "options": [{"name": "buy", "options": [{"name": "offer", "value": "field-kit"}, {"name": "quantity", "value": 2}]}]}]}}
        self.assertEqual(BOT.interaction_arguments(interaction), {"offer": "field-kit", "quantity": 2})
        config = {"adapterUrl": "http://127.0.0.1:18081", "adapterHost": "admin-panel:8080", "adapterToken": "secret", "requestTimeout": 2.5}
        actor = {"guildId": "1", "userId": "2", "requestId": "3"}
        with mock.patch.object(BOT, "http_json", return_value={"ok": True}) as request:
            BOT.adapter_request(config, "buy", actor, {"offer": "field-kit", "quantity": 2})
        self.assertEqual(request.call_args.kwargs["data"], {"actor": actor, "arguments": {"offer": "field-kit", "quantity": 2}, "action": "buy"})

    def test_bot_rejects_wrong_guild_and_channel_before_adapter(self):
        config = {"guildId": "1", "channelIds": {"2"}}
        bot = BOT.Bot(config)
        base = {
            "id": "i", "token": "t", "guild_id": "9", "channel_id": "2",
            "data": {"name": "dune", "options": [{"name": "status"}]},
            "member": {"roles": [], "user": {"id": "3", "username": "operator"}},
        }
        with mock.patch.object(BOT, "adapter_request") as adapter, mock.patch.object(BOT, "interaction_response", return_value={}) as response:
            bot.handle_interaction(base)
            adapter.assert_not_called()
            self.assertIn("not configured", response.call_args.args[1])
            base["guild_id"] = "1"
            base["channel_id"] = "8"
            bot.handle_interaction(base)
            adapter.assert_not_called()
            self.assertIn("not enabled", response.call_args.args[1])

    def test_bot_routes_authorized_command_and_formats_ephemeral_response(self):
        config = {"guildId": "1", "channelIds": set()}
        bot = BOT.Bot(config)
        interaction = {
            "id": "i", "token": "t", "guild_id": "1", "channel_id": "2",
            "data": {"name": "dune", "options": [{"name": "population"}]},
            "member": {"roles": ["10"], "user": {"id": "3", "username": "operator"}},
        }
        with mock.patch.object(BOT, "adapter_request", return_value={"result": {"onlinePlayers": 4, "totalPlayers": 12}}) as adapter, mock.patch.object(BOT, "interaction_response", return_value={}) as response, mock.patch.object(BOT, "write_state"):
            bot.handle_interaction(interaction)
        self.assertEqual(adapter.call_args.args[0], config)
        self.assertEqual(adapter.call_args.args[1], "population")
        self.assertIn("**4**", response.call_args.args[1])

    def test_config_never_exposes_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            env = pathlib.Path(directory) / ".env"
            env.write_text("\n".join([
                "DUNE_DISCORD_BOT_TOKEN=bot-secret",
                "DUNE_DISCORD_APPLICATION_ID=1",
                "DUNE_DISCORD_GUILD_ID=2",
                "DUNE_BOT_API_TOKEN=adapter-secret",
            ]))
            public = BOT.public_config(BOT.load_config(env))
        serialized = json.dumps(public)
        self.assertTrue(public["configured"])
        self.assertNotIn("bot-secret", serialized)
        self.assertNotIn("adapter-secret", serialized)
        self.assertFalse(public["messageContentIntent"])


if __name__ == "__main__":
    unittest.main()
