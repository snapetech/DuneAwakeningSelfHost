#!/usr/bin/env python3
import importlib.util
import pathlib
import tempfile
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
            "name": "AdminUser",
            "flsId": "TEST_FLS_ID",
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
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"], "AdminUser")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_TARGET_FLS_IDS"], "TEST_FLS_ID")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"], "TEST_FLS_ID_queue")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"], "TEST_FLS_ID")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_CLEANUP_TARGET_BINDINGS"], "true")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES"], "false")


class PublicAnnouncementRoutingTests(unittest.TestCase):
    def test_public_presence_announcement_defaults_to_single_routing_key(self):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs["env"]

            class Result:
                returncode = 0
                stdout = "{}"
                stderr = ""

            return Result()

        file_env = {
            "DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND": "/bin/echo",
            "DUNE_PLAYER_PRESENCE_ANNOUNCE_TIMEOUT_SECONDS": "10",
            "DUNE_ANNOUNCE_CHAT_ROUTING_KEYS": "HaggaBasin.0,Survival_1.dim_0,<empty>",
        }

        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.object(player_presence_announcer.subprocess, "run", fake_run):
            result = player_presence_announcer.announce("joined")

        self.assertTrue(result["ok"])
        self.assertEqual(captured["command"], ["/bin/echo", "joined"])
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_ENV_OVERRIDES_FILE"], "true")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_EXCHANGE"], "chat.map")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_CHANNEL"], "Map")
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"], "<empty>")
        self.assertEqual(result["routingKeys"], "<empty>")

    def test_public_presence_announcement_can_opt_into_multiple_routing_keys(self):
        captured = {}

        def fake_run(command, **kwargs):
            captured["env"] = kwargs["env"]

            class Result:
                returncode = 0
                stdout = "{}"
                stderr = ""

            return Result()

        file_env = {
            "DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND": "/bin/echo",
            "DUNE_PLAYER_PRESENCE_ANNOUNCE_ROUTING_KEYS": "HaggaBasin.0,<empty>",
        }

        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.object(player_presence_announcer.subprocess, "run", fake_run):
            result = player_presence_announcer.announce("joined")

        self.assertTrue(result["ok"])
        self.assertEqual(captured["env"]["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"], "HaggaBasin.0,<empty>")
        self.assertEqual(result["routingKeys"], "HaggaBasin.0,<empty>")

    def test_join_announcement_splits_first_timer_and_returning_players(self):
        snapshots = [
            {"123": {"name": "FirstTimer", "flsId": "FIRST_FLS"}, "456": {"name": "Returner", "flsId": "RETURN_FLS"}},
        ]
        state = {
            "onlinePlayers": {},
            "seenAccounts": ["456"],
        }
        announced = []

        def fake_online_players():
            return snapshots.pop(0)

        def fake_save_state(next_state):
            state.clear()
            state.update(next_state)

        def fake_announce(message):
            announced.append(message)
            return {"ok": True}

        file_env = {
            "DUNE_PLAYER_PRESENCE_ANNOUNCE_ENABLED": "true",
            "DUNE_PLAYER_PRESENCE_JOIN_TEMPLATE": "Welcome {playername}! Current player count is now {count}.",
            "DUNE_PLAYER_PRESENCE_RETURN_JOIN_TEMPLATE": "Welcome back {playername}! Current player count is now {count}.",
            "DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_STARTER_EMOTES_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DAILY_ENABLED": "false",
        }

        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True), \
             unittest.mock.patch.object(player_presence_announcer, "online_players", fake_online_players), \
             unittest.mock.patch.object(player_presence_announcer, "load_state", lambda: state.copy()), \
             unittest.mock.patch.object(player_presence_announcer, "save_state", fake_save_state), \
             unittest.mock.patch.object(player_presence_announcer, "announce", fake_announce):
            result = player_presence_announcer.check_once()

        messages = {item["accountId"]: item for item in result["announcements"]}
        self.assertEqual(messages["123"]["event"], "join-first-time")
        self.assertEqual(messages["123"]["message"], "Welcome FirstTimer! Current player count is now 2.")
        self.assertEqual(messages["456"]["event"], "join-returning")
        self.assertEqual(messages["456"]["message"], "Welcome back Returner! Current player count is now 2.")
        self.assertEqual(
            announced,
            [
                "Welcome FirstTimer! Current player count is now 2.",
                "Welcome back Returner! Current player count is now 2.",
            ],
        )
        self.assertEqual(state["seenAccounts"], ["123", "456"])


class StarterEmoteGrantTests(unittest.TestCase):
    def test_joined_player_gets_quiet_starter_emotes_once(self):
        player = {"name": "FirstTimer", "flsId": "FIRST_FLS"}
        state = {
            "onlinePlayers": {},
            "seenAccounts": [],
        }
        grants = []
        sent = []

        def fake_save_state(next_state):
            state.clear()
            state.update(next_state)

        def fake_grant(account_id):
            grants.append(account_id)
            return {"ok": True, "accountId": account_id, "granted": 4}

        def fake_private_message(target, message, job_id="player-presence-private-message"):
            sent.append({"target": target, "message": message, "jobId": job_id})
            return {"ok": True}

        file_env = {
            "DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_STARTER_EMOTES_ENABLED": "true",
            "DUNE_PLAYER_PRESENCE_REPO_STAR_THIRD_JOIN_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DAILY_ENABLED": "false",
        }

        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True), \
             unittest.mock.patch.object(player_presence_announcer, "online_players", lambda: {"123": player}), \
             unittest.mock.patch.object(player_presence_announcer, "load_state", lambda: state.copy()), \
             unittest.mock.patch.object(player_presence_announcer, "save_state", fake_save_state), \
             unittest.mock.patch.object(player_presence_announcer, "grant_starter_emotes", fake_grant), \
             unittest.mock.patch.object(player_presence_announcer, "private_message", fake_private_message):
            result = player_presence_announcer.check_once()

        self.assertEqual(grants, ["123"])
        self.assertEqual(result["starterEmoteGrants"][0]["grant"]["granted"], 4)
        self.assertEqual(state["starterEmotesGranted"], ["123"])
        self.assertEqual(sent, [])

    def test_starter_emote_templates_are_configurable(self):
        file_env = {
            "DUNE_PLAYER_PRESENCE_STARTER_EMOTE_TEMPLATES": " Emote_A , Emote_B ,, ",
        }
        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True):
            self.assertEqual(player_presence_announcer.starter_emote_templates(), ["Emote_A", "Emote_B"])

    def test_quick_rejoin_session_change_triggers_join_and_private_messages(self):
        player = {"name": "Returner", "flsId": "RETURN_FLS", "lastLoginTime": "2026-05-22 19:05:00+00"}
        snapshots = [
            {**player, "lastLoginTime": "2026-05-22 19:06:00+00"},
        ]
        state = {
            "onlinePlayers": {"456": player},
            "seenAccounts": ["456"],
            "recentLeaves": {},
        }
        announced = []
        sent = []

        def fake_online_players():
            return {"456": snapshots.pop(0)}

        def fake_save_state(next_state):
            state.clear()
            state.update(next_state)

        def fake_announce(message):
            announced.append(message)
            return {"ok": True}

        def fake_private_message(target, message, job_id="player-presence-private-message"):
            sent.append({"target": target, "message": message, "jobId": job_id})
            return {"ok": True}

        file_env = {
            "DUNE_PLAYER_PRESENCE_ANNOUNCE_ENABLED": "true",
            "DUNE_PLAYER_PRESENCE_RETURN_JOIN_TEMPLATE": "Welcome back {playername}! Current player count is now {count}.",
            "DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_ENABLED": "true",
            "DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_TEMPLATE": "Private welcome {playername}",
            "DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_ENABLED": "true",
            "DUNE_PLAYER_PRESENCE_RECONNECT_RECOVERY_TEMPLATE": "Reconnect help {playername}",
            "DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_STARTER_EMOTES_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DAILY_ENABLED": "false",
        }

        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True), \
             unittest.mock.patch.object(player_presence_announcer, "online_players", fake_online_players), \
             unittest.mock.patch.object(player_presence_announcer, "load_state", lambda: state.copy()), \
             unittest.mock.patch.object(player_presence_announcer, "save_state", fake_save_state), \
             unittest.mock.patch.object(player_presence_announcer, "announce", fake_announce), \
             unittest.mock.patch.object(player_presence_announcer, "private_message", fake_private_message):
            result = player_presence_announcer.check_once()

        self.assertEqual(result["joined"], ["Returner"])
        self.assertEqual(result["sessionRejoined"], ["Returner"])
        self.assertEqual(result["announcements"][0]["event"], "join-returning")
        self.assertEqual(announced, ["Welcome back Returner! Current player count is now 1."])
        self.assertEqual(result["privateWelcomeMessages"][0]["message"], "Private welcome Returner")
        self.assertEqual(result["automatedPrivateMessages"][0]["event"], "reconnect-recovery")
        self.assertEqual(result["automatedPrivateMessages"][0]["message"], "Reconnect help Returner")
        self.assertEqual([item["jobId"] for item in sent], ["player-presence-private-welcome", "player-presence-reconnect-recovery"])

    def test_existing_online_player_without_old_session_marker_is_not_reannounced(self):
        state = {
            "onlinePlayers": {"456": {"name": "Returner", "flsId": "RETURN_FLS"}},
            "seenAccounts": ["456"],
        }

        def fake_save_state(next_state):
            state.clear()
            state.update(next_state)

        file_env = {
            "DUNE_PLAYER_PRESENCE_ANNOUNCE_ENABLED": "true",
            "DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_ENABLED": "true",
            "DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_STARTER_EMOTES_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DAILY_ENABLED": "false",
        }

        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True), \
             unittest.mock.patch.object(player_presence_announcer, "online_players", lambda: {"456": {"name": "Returner", "flsId": "RETURN_FLS", "lastLoginTime": "2026-05-22 19:06:00+00"}}), \
             unittest.mock.patch.object(player_presence_announcer, "load_state", lambda: state.copy()), \
             unittest.mock.patch.object(player_presence_announcer, "save_state", fake_save_state):
            result = player_presence_announcer.check_once()

        self.assertEqual(result["joined"], [])
        self.assertEqual(result["sessionRejoined"], [])
        self.assertEqual(result["announcements"], [])
        self.assertEqual(result["privateWelcomeMessages"], [])
        self.assertEqual(state["onlinePlayers"]["456"]["lastLoginTime"], "2026-05-22 19:06:00+00")


class ServiceHealthCheckTests(unittest.TestCase):
    def test_default_freshness_check_excludes_derived_hagga_map_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            static = root / "public-site" / "static"
            static.mkdir(parents=True)
            (static / "players.json").write_text("{}", encoding="utf-8")

            file_env = {
                "DUNE_PLAYER_PRESENCE_SERVICE_HEALTH_UNITS": ",",
                "DUNE_PLAYER_PRESENCE_FRESHNESS_MAX_AGE_SECONDS": "300",
                "DUNE_PLAYER_PRESENCE_FLS_PUBLICATION_HEALTH_ENABLED": "false",
            }
            with unittest.mock.patch.object(player_presence_announcer, "ROOT", root), \
                 unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
                 unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True):
                checks = player_presence_announcer.service_health_checks()

        self.assertEqual([check["name"] for check in checks], ["public-site/static/players.json"])
        self.assertTrue(checks[0]["ok"])

    def test_configured_freshness_files_can_still_include_hagga_map_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            static = root / "public-site" / "static"
            static.mkdir(parents=True)
            (static / "players.json").write_text("{}", encoding="utf-8")

            file_env = {
                "DUNE_PLAYER_PRESENCE_SERVICE_HEALTH_UNITS": ",",
                "DUNE_PLAYER_PRESENCE_FRESHNESS_FILES": "public-site/static/players.json,public-site/static/hagga-map.svg",
                "DUNE_PLAYER_PRESENCE_FRESHNESS_MAX_AGE_SECONDS": "300",
                "DUNE_PLAYER_PRESENCE_FLS_PUBLICATION_HEALTH_ENABLED": "false",
            }
            with unittest.mock.patch.object(player_presence_announcer, "ROOT", root), \
                 unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
                 unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True):
                checks = player_presence_announcer.service_health_checks()

        by_name = {check["name"]: check for check in checks}
        self.assertTrue(by_name["public-site/static/players.json"]["ok"])
        self.assertFalse(by_name["public-site/static/hagga-map.svg"]["ok"])
        self.assertEqual(by_name["public-site/static/hagga-map.svg"]["status"], "missing")


class AdminAnomalyDigestTests(unittest.TestCase):
    def test_default_digest_omits_zero_value_categories(self):
        self.assertEqual(
            player_presence_announcer.admin_anomaly_digest_template(1, "AdminUser", 0),
            "Admin digest: stuck/recent anomalies=1 (AdminUser).",
        )
        self.assertEqual(
            player_presence_announcer.admin_anomaly_digest_template(0, "none", 2),
            "Admin digest: over base cap=2.",
        )
        self.assertEqual(
            player_presence_announcer.admin_anomaly_digest_template(0, "none", 0),
            "",
        )

    def test_digest_signature_tracks_actionable_values(self):
        stuck = [
            {"accountId": "2", "name": "AdminUser"},
            {"accountId": "10", "name": "Other"},
        ]
        self.assertEqual(
            player_presence_announcer.admin_anomaly_digest_signature(stuck, 0),
            '{"overBaseCap": 0, "stuck": ["10", "2"]}',
        )
        self.assertEqual(
            player_presence_announcer.admin_anomaly_digest_signature([], 0),
            '{"overBaseCap": 0, "stuck": []}',
        )


class BaseCapConfigTests(unittest.TestCase):
    def test_base_cap_defaults_to_usergame_hagga_basin_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            config = root / "config"
            config.mkdir()
            (config / "UserGame.ini").write_text(
                'm_MaxLandclaimSegmentsPerMap=(((Name="HaggaBasin"), 8),((Name="Survival_1"), 4))\n',
                encoding="utf-8",
            )

            with unittest.mock.patch.object(player_presence_announcer, "ROOT", root), \
                 unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", {}), \
                 unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True):
                self.assertEqual(player_presence_announcer.configured_base_cap(), 8)

    def test_legacy_base_cap_env_is_only_a_fallback_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)

            with unittest.mock.patch.object(player_presence_announcer, "ROOT", root), \
                 unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", {"DUNE_PLAYER_PRESENCE_BASE_CAP": "10"}), \
                 unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True):
                self.assertEqual(player_presence_announcer.configured_base_cap(), 10)


class RepoStarThirdJoinTests(unittest.TestCase):
    def test_repo_star_private_message_sends_once_on_third_join(self):
        player = {
            "name": "AdminUser",
            "flsId": "TEST_FLS_ID",
        }
        snapshots = [
            {"123": player},
            {},
            {"123": player},
            {},
            {"123": player},
            {},
            {"123": player},
        ]
        state = {"onlinePlayers": {}}
        sent = []

        def fake_online_players():
            return snapshots.pop(0)

        def fake_save_state(next_state):
            state.clear()
            state.update(next_state)

        def fake_private_message(target, message, job_id="player-presence-private-message"):
            sent.append({"target": target, "message": message, "jobId": job_id})
            return {"ok": True}

        file_env = {
            "DUNE_PLAYER_PRESENCE_REPO_STAR_THIRD_JOIN_ENABLED": "true",
            "DUNE_PLAYER_PRESENCE_REPO_STAR_JOIN_COUNT": "3",
            "DUNE_PLAYER_PRESENCE_REPO_STAR_TEMPLATE": "Please star https://github.com/snapetech/DuneAwakeningSelfHost",
            "DUNE_PLAYER_PRESENCE_STARTER_BASE_TOOL_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_STARTER_EMOTES_ENABLED": "false",
            "DUNE_PLAYER_PRESENCE_ADMIN_FIRST_LOGIN_DAILY_ENABLED": "false",
        }

        with unittest.mock.patch.object(player_presence_announcer, "FILE_ENV", file_env), \
             unittest.mock.patch.dict(player_presence_announcer.os.environ, {}, clear=True), \
             unittest.mock.patch.object(player_presence_announcer, "online_players", fake_online_players), \
             unittest.mock.patch.object(player_presence_announcer, "load_state", lambda: state.copy()), \
             unittest.mock.patch.object(player_presence_announcer, "save_state", fake_save_state), \
             unittest.mock.patch.object(player_presence_announcer, "private_message", fake_private_message):
            results = [player_presence_announcer.check_once() for _ in range(7)]

        third_join_messages = [
            item
            for result in results
            for item in result["automatedPrivateMessages"]
            if item["event"] == "repo-star-third-join"
        ]
        self.assertEqual(len(third_join_messages), 1)
        self.assertEqual(third_join_messages[0]["accountId"], "123")
        self.assertEqual(sent[0]["jobId"], "player-presence-repo-star-third-join")
        self.assertEqual(state["joinCounts"]["123"], 4)
        self.assertEqual(state["repoStarMessaged"], ["123"])


if __name__ == "__main__":
    unittest.main()
