#!/usr/bin/env python3
import importlib.util
import base64
import hashlib
import hmac
import io
import json
import os
import pathlib
import sys
import tempfile
import tarfile
import time
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


try:
    import psycopg2  # noqa: F401
except ModuleNotFoundError:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
    psycopg2_extras_stub.RealDictCursor = object
    psycopg2_stub.extras = psycopg2_extras_stub
    psycopg2_stub.connect = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database access is not available in unit tests"))
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub


def load_admin_panel(workspace):
    os.environ["ADMIN_WORKSPACE"] = str(workspace)
    spec = importlib.util.spec_from_file_location("admin_panel_under_test", ROOT / "admin" / "admin_panel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AdminPanelSafeSurfacesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = pathlib.Path(self.tmp.name)
        (self.workspace / "config").mkdir(parents=True)
        (self.workspace / "scripts").mkdir(parents=True)
        (self.workspace / "config" / "UserEngine.ini").write_text(
            "\n".join([
                "[ConsoleVariables]",
                "Dune.GlobalMiningOutputMultiplier=1.0",
                "Dune.GlobalVehicleMiningOutputMultiplier=1.0",
                "SecurityZones.PvpResourceMultiplier=2.5",
                "Sandstorm.Enabled=1",
                "Sandstorm.Treasure.Enabled=1",
                "",
            ]),
            encoding="utf-8",
        )
        (self.workspace / "config" / "UserGame.ini").write_text(
            "\n".join([
                "[/Script/DuneSandbox.PvpPveSettings]",
                "m_bShouldForceEnablePvpOnAllPartitions=False",
                "",
                "[/Script/DuneSandbox.SecurityZonesSubsystem]",
                "m_bAreSecurityZonesEnabled=True",
                "",
                "[/Script/DuneSandbox.SandStormConfig]",
                "m_bCoriolisAutoSpawnEnabled=False",
                "",
            ]),
            encoding="utf-8",
        )
        (self.workspace / "config" / "director.ini").write_text("[ Battlegroup ]\n", encoding="utf-8")
        (self.workspace / "config" / "gateway.ini").write_text("", encoding="utf-8")
        (self.workspace / "config" / "rabbitmq-admin.conf").write_text("", encoding="utf-8")
        (self.workspace / "config" / "rabbitmq-game.conf").write_text("", encoding="utf-8")
        (self.workspace / "research" / "surfaces").mkdir(parents=True)
        (self.workspace / "research" / "surfaces" / "test.jsonl").write_text(
            json.dumps({
                "id": "ini.test.surface",
                "build": "test-build",
                "surface": "ini",
                "scope": "global",
                "name": "Test surface",
                "status": "validated",
                "confidence": "high",
                "risk": "low",
                "validated": True,
                "evidence": ["unit test"],
            }) + "\n" + json.dumps({
                "id": "binary.test.candidate",
                "build": "test-build",
                "surface": "binary-candidate",
                "scope": "global",
                "name": "Test binary candidate",
                "status": "candidate",
                "confidence": "low",
                "risk": "medium",
                "validated": False,
                "evidence": ["unit test"],
            }) + "\n",
            encoding="utf-8",
        )
        (self.workspace / ".env").write_text("", encoding="utf-8")
        self.panel = load_admin_panel(self.workspace)
        self.handler = object.__new__(self.panel.Handler)

    def tearDown(self):
        self.tmp.cleanup()

    def patch_db(self, query_fn=None, execute_fn=None):
        original_query = self.panel.query
        original_execute = self.panel.execute
        self.panel.query = query_fn or (lambda sql, params=None: [])
        self.panel.execute = execute_fn or (lambda sql, params=None: None)
        self.addCleanup(lambda: setattr(self.panel, "query", original_query))
        self.addCleanup(lambda: setattr(self.panel, "execute", original_execute))

    def patch_flag(self, name, value):
        original = getattr(self.panel, name)
        setattr(self.panel, name, value)
        self.addCleanup(lambda: setattr(self.panel, name, original))

    def patch_connect(self, connect_fn):
        original = self.panel.db_connect
        self.panel.db_connect = connect_fn
        self.addCleanup(lambda: setattr(self.panel, "db_connect", original))

    def make_route_handler(self, path):
        captured = {"json": None, "errors": [], "audits": []}
        handler = object.__new__(self.panel.Handler)
        handler.path = path
        handler.validate_host = lambda: None
        handler.validate_same_origin = lambda: None
        handler.require_token = lambda: None
        handler.json = lambda value, head_only=False: captured.__setitem__("json", value)

        def fake_error(status, message, head_only=False):
            captured["errors"].append({"status": status, "message": str(message)})

        def fake_audit(action, ok=True, **fields):
            captured["audits"].append(dict(action=action, ok=ok, **fields))

        handler.error = fake_error
        handler.audit = fake_audit
        return handler, captured

    def invoke_post_route(self, path, body):
        handler, captured = self.make_route_handler(path)
        original_validate = self.panel.validate_json_post
        original_parse = self.panel.parse_body
        self.panel.validate_json_post = lambda request_handler, **kwargs: None
        self.panel.parse_body = lambda request_handler, **kwargs: body
        self.addCleanup(lambda: setattr(self.panel, "validate_json_post", original_validate))
        self.addCleanup(lambda: setattr(self.panel, "parse_body", original_parse))
        handler.do_POST()
        return captured

    def test_healthz_is_minimal_and_does_not_require_admin_token(self):
        handler, captured = self.make_route_handler("/healthz")
        handler.is_app_route = lambda path: False
        handler.require_token = lambda: self.fail("healthz must remain usable by the container healthcheck")
        handler.do_GET()
        self.assertEqual({"ok": True, "service": "dune-admin-panel"}, captured["json"])

    def test_detailed_status_requires_admin_token(self):
        handler, captured = self.make_route_handler("/api/status")
        handler.is_app_route = lambda path: False
        handler.require_token = lambda: (_ for _ in ()).throw(PermissionError("admin token required"))
        handler.do_GET()
        self.assertEqual(401, captured["errors"][0]["status"])
        self.assertIsNone(captured["json"])

    def test_api_head_requires_admin_token(self):
        handler, captured = self.make_route_handler("/api/status")
        handler.is_app_route = lambda path: False
        handler.require_token = lambda: (_ for _ in ()).throw(PermissionError("admin token required"))
        handler.do_HEAD()
        self.assertEqual(401, captured["errors"][0]["status"])
        self.assertIsNone(captured["json"])

    def test_server_banner_does_not_disclose_python_runtime(self):
        self.assertEqual("DASH", self.panel.Handler.server_version)
        self.assertEqual("", self.panel.Handler.sys_version)

    def test_admin_http_concurrency_is_bounded(self):
        self.assertGreaterEqual(self.panel.MAX_CONCURRENT_REQUESTS, 4)
        self.assertLessEqual(self.panel.MAX_CONCURRENT_REQUESTS, 128)
        self.assertTrue(self.panel.BoundedThreadingHTTPServer.daemon_threads)
        self.assertLessEqual(self.panel.BoundedThreadingHTTPServer.request_queue_size, 64)

    def test_catalog_schema_has_required_fields(self):
        entries = self.panel.content_catalog_entries()
        self.assertGreaterEqual(len(entries), 5)
        required = {
            "surface",
            "capability",
            "evidence",
            "confidence",
            "mutationRisk",
            "restartRequired",
            "validationCommand",
            "rollback",
        }
        for entry in entries:
            self.assertTrue(required.issubset(entry), entry)
        payload = self.panel.catalog_payload()
        self.assertIn("Deep Desert", payload["groups"])
        self.assertTrue(payload["enabled"])
        by_id = {entry["id"]: entry for entry in entries}
        self.assertIn("faction-reputation-plan", by_id)
        self.assertIn("set_player_faction_reputation", " ".join(by_id["faction-reputation-plan"]["evidence"]))
        self.assertIn("journey-server-functions", by_id)
        self.assertIn("respawn-location-delete", by_id)
        self.assertIn("landsraad-term-admin", by_id)
        self.assertIn("guild-admin-functions", by_id)
        self.assertIn("world-state-function-discovery", by_id)
        self.assertIn("marker-delete-functions", by_id)
        self.assertIn("landclaim-segment-functions", by_id)
        self.assertIn("exchange-solari-balance", by_id)
        self.assertIn("exchange-order-functions", by_id)
        self.assertIn("vehicle-restore-functions", by_id)
        self.assertIn("base-backup-functions", by_id)
        self.assertIn("player-tag-functions", by_id)
        self.assertIn("player-access-code-functions", by_id)
        self.assertIn("communinet-functions", by_id)
        self.assertIn("tutorial-entry-functions", by_id)
        self.assertIn("permission-actor-functions", by_id)
        self.assertIn("vendor-cycle-timestamp-functions", by_id)
        self.assertIn("taxation-landsraad-vendor-functions", by_id)
        self.assertIn("vendor-tutorial-lore-dungeon-overmap-functions", by_id)
        self.assertIn("party-account-lifecycle-functions", by_id)
        self.assertEqual(by_id["recipe-vehicle-function-discovery"]["mutationRisk"], "blocked")

    def test_typed_knob_validation_and_backup_write(self):
        self.assertEqual(self.panel.validate_typed_knob_value("globalMiningMultiplier", "2.5"), "2.5")
        self.assertEqual(self.panel.validate_typed_knob_value("sandstormEnabled", "false"), "0")
        self.assertEqual(self.panel.validate_typed_knob_value("characterRecustomizationCost", "0"), "0")
        with self.assertRaises(ValueError):
            self.panel.validate_typed_knob_value("buildingShelterThreshold", "2")
        with self.assertRaises(ValueError):
            self.panel.validate_typed_knob_value("characterRecustomizationCost", "-1")

        result = self.panel.write_typed_knobs({
            "globalMiningMultiplier": "2.5",
            "sandstormEnabled": "false",
            "forcePvpAllPartitions": "true",
            "characterRecustomizationCost": "0",
        })
        self.assertTrue(result["ok"])
        self.assertTrue(result["restartRequired"])
        engine = (self.workspace / "config" / "UserEngine.ini").read_text(encoding="utf-8")
        game = (self.workspace / "config" / "UserGame.ini").read_text(encoding="utf-8")
        self.assertIn("Dune.GlobalMiningOutputMultiplier=2.5", engine)
        self.assertIn("Sandstorm.Enabled=0", engine)
        self.assertIn("m_bShouldForceEnablePvpOnAllPartitions=True", game)
        self.assertIn("[/Script/DuneSandbox.CharacterRecustomizerSubsystem]", game)
        self.assertIn("m_CostAmount=0", game)
        backups = list((self.workspace / "backups" / "admin-panel").glob("*User*.ini"))
        self.assertGreaterEqual(len(backups), 2)

    def test_spice_caps_render_structured_input(self):
        rendered = self.panel.validate_typed_knob_value(
            "spiceDeepDesertCaps",
            {
                "Medium": {"primed": 24, "active": 24},
                "Large": {"primed": 3, "active": 3},
            },
        )
        self.assertIn('Name="Medium"', rendered)
        self.assertIn("MaxGloballyPrimed=24", rendered)
        self.assertIn('Name="Large"', rendered)
        self.assertIn("MaxGloballyActive=3", rendered)

    def test_catalog_validation_and_gate_metadata(self):
        validation = self.panel.catalog_validation_payload()
        commands = {row["name"]: row["command"] for row in validation["commands"]}
        self.assertIn("Static compile", commands)
        self.assertIn("Repo validation", commands)
        self.assertIn("Spice state", commands)

        evidence = self.panel.catalog_evidence_payload()
        self.assertIn("schema", evidence)
        self.assertIn("rules", evidence)
        self.assertGreaterEqual(len(evidence["entries"]), 20)

        self.patch_flag("CATALOG_ENABLED", False)
        with self.assertRaises(PermissionError):
            self.handler.require_catalog()

    def test_discovery_payload_reads_surface_ledger(self):
        payload = self.panel.discovery_payload()
        self.assertTrue(payload["ok"])
        ids = {entry["id"] for entry in payload["surfaces"]}
        self.assertIn("ini.test.surface", ids)
        self.assertIn("binary.test.candidate", ids)
        self.assertIn("ready-or-promoted", payload["queue"])
        self.assertIn("needs-startup-parse-test", payload["queue"])

    def test_discovery_routes_are_read_only_catalog_gated(self):
        for route in ("/api/discovery", "/api/discovery/surfaces", "/api/discovery/queue", "/api/discovery/builds"):
            handler, captured = self.make_route_handler(route)
            handler.do_GET()
            self.assertEqual([], captured["errors"], route)
            self.assertIsNotNone(captured["json"], route)

    def test_read_only_inspectors_expose_safe_mutator_metadata(self):
        def fake_query(sql, params=None):
            if "from dune.player_state" in sql:
                return [{
                    "account_id": 10,
                    "character_name": "Tester",
                    "online_status": "Offline",
                    "player_controller_id": 201,
                    "player_pawn_id": 200,
                }]
            if "from dune.player_faction " in sql:
                return [{"actor_id": 200, "faction_id": 3}]
            if "from dune.player_faction_reputation" in sql:
                return [{"actor_id": 200, "faction_id": 1, "reputation_amount": 50}]
            if "get_guild_for_player" in sql:
                return [{"guild_id": 9}]
            if "get_guild_data" in sql:
                return [{"guild_id": 9, "guild_description": "old"}]
            if "get_guild_members" in sql:
                return [{"guild_id": 9, "player_id": 200, "role_id": 1}]
            if "admin_read_player_tags" in sql:
                return [{"tags": "event"}]
            if "get_player_access_codes" in sql:
                return [{"access_code": 111, "access_code_type": 0}]
            if "load_communinet_player_data" in sql:
                return [{"is_active": True, "selected_channel_name": "general"}]
            if "get_all_tutorial_entries" in sql:
                return [{"tutorial_id": 7, "tutorial_state": 1}]
            if "vendor_stock_cycle" in sql:
                return [{"vendor_id": "ScrapVendor", "player_id": 200}]
            if "dune_exchange_retrieve_solari_balance" in sql:
                return [{"solari_balance": 500}]
            if "dune_exchange_users" in sql:
                return [{"owner_id": 200}]
            if "dune_exchange_orders" in sql:
                return [{"id": 1, "owner_id": 200}]
            if "spicefield_types" in sql:
                return [{"map": "DeepDesert", "field_kind_id": 1, "max_globally_active": 24}]
            if "spicefield_server_availability" in sql:
                return [{"server_id": 1, "field_kind_id": 1}]
            if "resourcefield_state" in sql:
                return [{"map": "DeepDesert", "field_kind_id": 1, "count": 3}]
            if "pg_proc" in sql:
                return [{"schema": "dune", "name": "example_function", "args": "", "result": "void"}]
            if "information_schema.columns" in sql:
                return [{"table_name": "example", "column_name": "id", "data_type": "bigint", "udt_name": "int8"}]
            if "count(*)" in sql:
                return [{"table_name": "example", "rows": 1}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("inspectors must not execute SQL writes")))

        progression = self.handler.progression_inspect({"account_id": 10})
        self.assertEqual(progression["player"]["player_pawn_id"], 200)
        self.assertEqual(progression["mutators"]["journey"]["executionGate"], "DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED")
        self.assertEqual(progression["mutators"]["playerFaction"]["confirm"], "CHANGE FACTION")
        self.assertEqual(progression["mutators"]["journeyRecipeVehicle"]["status"], "inspect-only")

        world = self.handler.world_state_inspect({"account_id": 10})
        self.assertEqual(world["guildId"], 9)
        self.assertEqual(world["mutators"]["marker"]["confirm"], "DELETE MARKERS")
        self.assertEqual(world["mutators"]["vehicleRecipeMarkerLandclaim"]["status"], "inspect-only")

        economy = self.handler.economy_inspect({"account_id": 10})
        self.assertEqual(economy["ownerId"], 200)
        self.assertEqual(economy["exchangeBalance"]["solari_balance"], 500)
        self.assertEqual(economy["mutators"]["exchangeSolari"]["executionGate"], "DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED")

        lifecycle = self.handler.player_lifecycle_inspect({"account_id": 10})
        self.assertEqual(lifecycle["playerId"], 200)
        self.assertEqual(lifecycle["mutators"]["playerTags"]["confirm"], "WRITE PLAYER TAGS")
        self.assertEqual(lifecycle["mutators"]["partyAccountCommuninet"]["status"], "inspect-only")

        spice = self.handler.spice_field_inspect()
        self.assertEqual(spice["caps"][0]["map"], "DeepDesert")
        self.assertIn("typedKnob", spice)

    def test_event_dry_run_is_plan_only(self):
        plan = self.panel.event_dry_run({
            "name": "test",
            "actions": [
                {"type": "spice-cap-proposal", "caps": {"Medium": {"primed": 24, "active": 24}}},
                {"type": "economy-bundle", "payload": {"currency": []}},
            ],
        })
        self.assertTrue(plan["dryRun"])
        actions = plan["event"]["plan"]
        self.assertEqual(actions[0]["type"], "spice-cap-proposal")
        self.assertTrue(actions[0]["dryRunOnly"])
        self.assertEqual(actions[1]["payload"]["dry_run"], True)

    def test_event_persistence_and_cancel(self):
        event = self.panel.create_event({"name": "persisted", "actions": [{"type": "typed-knob-plan", "updates": {}}]})
        state_path = self.workspace / "backups" / "admin-panel" / "events.json"
        self.assertTrue(state_path.exists())
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["events"][0]["id"], event["id"])
        result = self.panel.cancel_event(event["id"])
        self.assertEqual(result["cancelled"], 1)
        self.assertEqual(self.panel.read_event_state()["events"][0]["status"], "cancelled")

    def test_execute_event_fails_closed_by_default(self):
        event = self.panel.create_event({"name": "blocked", "actions": [{"type": "typed-knob-plan", "updates": {}}]})
        with self.assertRaises(PermissionError):
            self.panel.execute_event(event["id"])

    def test_recurring_event_executes_safe_primitives_and_records_runs(self):
        self.patch_flag("EVENT_EXECUTION_ENABLED", True)
        announcement_calls = []
        restart_calls = []
        original_announcement = self.panel.schedule_announcement
        original_restart = self.panel.schedule_restart
        self.panel.schedule_announcement = lambda payload: announcement_calls.append(payload) or {"id": "announce-1"}
        self.panel.schedule_restart = lambda payload: restart_calls.append(payload) or {"id": "restart-1"}
        self.addCleanup(lambda: setattr(self.panel, "schedule_announcement", original_announcement))
        self.addCleanup(lambda: setattr(self.panel, "schedule_restart", original_restart))
        event = self.panel.create_event({
            "name": "recurring operations",
            "runAt": "2020-01-01T00:00:00Z",
            "repeatSeconds": 60,
            "maxRuns": 2,
            "actions": [
                {"type": "announcement", "message": "test notice"},
                {"type": "restart", "target": "deep-desert"},
                {"type": "typed-knob-plan", "updates": {}},
            ],
        })
        self.assertEqual(self.panel.due_event_ids(now=1_700_000_000), [event["id"]])
        first = self.panel.execute_event(event["id"], trigger="schedule")
        self.assertTrue(first["ok"])
        self.assertTrue(first["nextRunAt"])
        self.assertEqual(announcement_calls[0]["message"], "test notice")
        self.assertFalse(restart_calls[0]["execute"])
        state = self.panel.read_event_state()
        self.assertEqual(state["events"][0]["status"], "scheduled")
        self.assertEqual(state["events"][0]["runCount"], 1)
        self.assertEqual(state["runs"][0]["trigger"], "schedule")
        second = self.panel.execute_event(event["id"], trigger="schedule")
        self.assertTrue(second["ok"])
        state = self.panel.read_event_state()
        self.assertEqual(state["events"][0]["status"], "executed")
        self.assertEqual(state["events"][0]["runCount"], 2)
        self.assertEqual(len(state["runs"]), 2)

    def test_event_recurrence_bounds_fail_closed(self):
        with self.assertRaises(ValueError):
            self.panel.event_dry_run({"repeatSeconds": 10, "actions": [{"type": "typed-knob-plan", "updates": {}}]})
        with self.assertRaises(ValueError):
            self.panel.event_dry_run({"runAt": "not-a-date", "actions": [{"type": "typed-knob-plan", "updates": {}}]})

    def test_player_tags_dry_run_and_gate(self):
        calls = []

        def fake_query(sql, params=None):
            calls.append((sql, params))
            if "admin_read_player_tags" in sql:
                return [{"tags": "old_tag"}]
            return []

        def forbidden_execute(sql, params=None):
            raise AssertionError("dry-run or gated path executed SQL")

        self.patch_db(fake_query, forbidden_execute)
        result = self.handler.player_tags_mutation({
            "dry_run": True,
            "account_id": 10,
            "tags_to_add": ["event"],
            "tags_to_remove": ["old_tag"],
        })
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["executionGate"], "DUNE_ADMIN_PLAYER_TAG_MUTATIONS_ENABLED")
        self.assertEqual(result["confirm"], "WRITE PLAYER TAGS")
        self.assertEqual(result["plan"]["rollback"]["tags_to_add"], ["old_tag"])
        self.assertEqual(result["plan"]["rollback"]["tags_to_remove"], ["event"])

        with self.assertRaises(PermissionError):
            self.handler.player_tags_mutation({
                "dry_run": False,
                "account_id": 10,
                "tags_to_add": ["event"],
                "confirm": "WRITE PLAYER TAGS",
            })

    def test_access_code_dry_run_and_gate(self):
        self.patch_db(
            lambda sql, params=None: [{"access_code": 111, "access_code_type": 0}] if "get_player_access_codes" in sql else [],
            lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")),
        )
        result = self.handler.access_code_mutation({
            "dry_run": True,
            "action": "create",
            "account_id": 10,
            "access_code": 222,
            "access_code_type": 0,
        })
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["executionGate"], "DUNE_ADMIN_ACCESS_CODE_MUTATIONS_ENABLED")
        self.assertEqual(result["confirm"], "WRITE ACCESS CODES")
        self.assertEqual(result["plan"]["rollback"]["action"], "delete")

        with self.assertRaises(PermissionError):
            self.handler.access_code_mutation({
                "dry_run": False,
                "action": "delete",
                "account_id": 10,
                "access_code": 111,
                "access_code_type": 0,
                "confirm": "WRITE ACCESS CODES",
            })

    def test_character_slot_discovery_and_plan_shape(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline", "player_controller_id": 100, "player_pawn_id": 200, "fls_id": "fls"}]
            if "with target_account as" in sql:
                return [{"account_id": 11, "character_name": "Stored", "online_status": "Offline", "ownership_evidence": "same-account-user"}]
            if "from pg_proc" in sql:
                return [{"name": "login_account", "args": "", "result": "bigint"}]
            if "information_schema.columns" in sql:
                return [{"table_name": "player_state", "column_name": "account_id"}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("dry-run executed SQL")))
        slots = self.handler.character_slots(10)
        self.assertTrue(slots["ok"])
        self.assertEqual(slots["activeCharacter"]["character_name"], "Active")
        self.assertEqual(slots["candidates"][0]["character_name"], "Stored")
        self.assertEqual(slots["executionGate"], "DUNE_ADMIN_CHARACTER_SWAP_ENABLED")

        plan = self.handler.character_slot_plan({"account_id": 10, "action": "new-character"})
        self.assertTrue(plan["dryRun"])
        self.assertFalse(plan["executable"])
        self.assertIn("No validated first-party", " ".join(plan["plan"]["blockers"]))

    def test_character_slot_dry_run_never_executes_sql(self):
        executed = []

        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: executed.append((sql, params)))
        result = self.handler.character_slot_execute({"dry_run": True, "account_id": 10, "action": "new-character"})
        self.assertTrue(result["dryRun"])
        self.assertEqual(executed, [])

    def test_character_slot_online_players_are_refused(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Online"}]
            return []

        self.patch_db(fake_query)
        result = self.handler.character_slot_plan({"account_id": 10, "action": "new-character"})
        self.assertFalse(result["executable"])
        self.assertIn("online", " ".join(result["plan"]["blockers"]))

    def test_character_slot_missing_native_contract_is_not_executable(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            return []

        self.patch_db(fake_query)
        result = self.handler.character_slot_plan({"account_id": 10, "action": "new-character"})
        self.assertFalse(result["executable"])
        self.assertIn("is mapped", " ".join(result["plan"]["blockers"]))

    def test_character_slot_execute_fails_closed_without_gate_and_confirmation(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))
        with self.assertRaises(PermissionError):
            self.handler.character_slot_execute({"dry_run": False, "account_id": 10, "action": "new-character", "confirm": "SWAP CHARACTER"})

        self.patch_flag("CHARACTER_SWAP_ENABLED", True)
        with self.assertRaises(PermissionError):
            self.handler.character_slot_execute({"dry_run": False, "account_id": 10, "action": "new-character"})

    def test_character_slot_switch_requires_native_owned_target(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            if "with target_account as" in sql:
                return [{"account_id": 11, "character_name": "Stored", "online_status": "Offline", "ownership_evidence": "same-account-user"}]
            return []

        self.patch_db(fake_query)
        with self.assertRaises(ValueError):
            self.handler.character_slot_plan({"account_id": 10, "action": "switch-character"})
        with self.assertRaises(ValueError):
            self.handler.character_slot_plan({"account_id": 10, "action": "switch-character", "target_account_id": 99})

        plan = self.handler.character_slot_plan({"account_id": 10, "action": "switch-character", "target_account_id": 11})
        self.assertEqual(plan["targetAccountId"], 11)
        self.assertEqual(plan["plan"]["targetCharacter"]["character_name"], "Stored")
        self.assertFalse(plan["executable"])

    def test_character_slot_online_target_candidate_blocks_switch(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            if "with target_account as" in sql:
                return [{"account_id": 11, "character_name": "Stored", "online_status": "Online", "ownership_evidence": "same-account-user"}]
            return []

        self.patch_db(fake_query)
        plan = self.handler.character_slot_plan({"account_id": 10, "action": "restore-character", "target_account_id": 11})
        self.assertFalse(plan["executable"])
        self.assertIn("online", " ".join(plan["plan"]["blockers"]))

    def test_character_slot_contract_reports_evidence_but_not_execution(self):
        def fake_query(sql, params=None):
            if "from pg_proc" in sql:
                return [
                    {"name": "login_account", "args": "", "result": "bigint"},
                    {"name": "save_player", "args": "", "result": "void"},
                    {"name": "save_player_pawn", "args": "", "result": "void"},
                ]
            if "information_schema.columns" in sql:
                return [{"table_name": "accounts", "column_name": "id", "data_type": "bigint", "udt_name": "int8"}]
            return []

        self.patch_db(fake_query)
        contract = self.handler.character_slot_contract()
        self.assertEqual(contract["confidence"], "moderate")
        self.assertIn("login_account", contract["observedLifecycleEvidence"])
        self.assertFalse(contract["safeNativeSwapPath"])

    def test_character_slot_takeover_contract_enables_switch_plan(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline", "fls_id": "active-fls"}]
            if "with target_account as" in sql:
                return [{"account_id": 11, "character_name": "Stored", "online_status": "Offline", "fls_id": "stored-fls", "ownership_evidence": "same-account-user"}]
            if "from pg_proc" in sql:
                return [{"name": "takeover_account", "args": "in_user_to_takeover text, in_current_user text", "result": "void"}]
            return []

        self.patch_db(fake_query)
        plan = self.handler.character_slot_plan({"account_id": 10, "action": "switch-character", "target_account_id": 11})
        self.assertTrue(plan["executable"])
        self.assertEqual(plan["plan"]["nativeCall"]["function"], "dune.takeover_account")
        self.assertEqual(plan["plan"]["nativeCall"]["in_user_to_takeover"], "stored-fls")
        self.assertEqual(plan["plan"]["nativeCall"]["in_current_user"], "active-fls")
        self.assertTrue(plan["plan"]["transactionSafety"]["offlineRecheckInsideTransaction"])
        self.assertTrue(plan["plan"]["transactionSafety"]["commitRequiresPostSwapVerification"])

        new_plan = self.handler.character_slot_plan({"account_id": 10, "action": "new-character"})
        self.assertFalse(new_plan["executable"])
        self.assertIn("delete_account", " ".join(new_plan["plan"]["blockers"]))

    def test_character_slot_switch_execute_uses_takeover_with_backup_and_audit_rows(self):
        calls = []
        backups = []
        original_backup = self.panel.create_db_backup
        original_takeover = self.panel.character_swap_takeover

        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline", "fls_id": "active-fls"}]
            if "with target_account as" in sql:
                return [{"account_id": 11, "character_name": "Stored", "online_status": "Offline", "fls_id": "stored-fls", "ownership_evidence": "same-account-user"}]
            if "from pg_proc" in sql:
                return [{"name": "takeover_account", "args": "in_user_to_takeover text, in_current_user text", "result": "void"}]
            return []

        def fake_takeover(active_account_id, target_account_id, active_user, target_user):
            calls.append((active_account_id, target_account_id, active_user, target_user))
            return (
                [{"account_id": active_account_id, "online_status": "Offline", "fls_id": active_user}, {"account_id": target_account_id, "online_status": "Offline", "fls_id": target_user}],
                [{"account_id": active_account_id, "online_status": "Offline", "fls_id": target_user}, {"account_id": target_account_id, "online_status": "Offline", "fls_id": active_user}],
                True,
            )

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected raw execute")))
        self.patch_flag("CHARACTER_SWAP_ENABLED", True)
        self.panel.create_db_backup = lambda: backups.append("backup") or {"path": "backup.dump", "bytes": 1}
        self.panel.character_swap_takeover = fake_takeover
        self.addCleanup(lambda: setattr(self.panel, "create_db_backup", original_backup))
        self.addCleanup(lambda: setattr(self.panel, "character_swap_takeover", original_takeover))

        result = self.handler.character_slot_execute({
            "dry_run": False,
            "account_id": 10,
            "action": "switch-character",
            "target_account_id": 11,
            "confirm": "SWAP CHARACTER",
        })
        self.assertFalse(result["dryRun"])
        self.assertEqual(backups, ["backup"])
        self.assertEqual(calls, [(10, 11, "active-fls", "stored-fls")])
        self.assertTrue(result["verified"])
        self.assertEqual(result["rollback"]["inversePayload"]["account_id"], 11)

    def test_character_slot_execute_rechecks_offline_after_backup(self):
        calls = []
        original_backup = self.panel.create_db_backup
        original_takeover = self.panel.character_swap_takeover

        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline", "fls_id": "active-fls"}]
            if "with target_account as" in sql:
                return [{"account_id": 11, "character_name": "Stored", "online_status": "Offline", "fls_id": "stored-fls", "ownership_evidence": "same-account-user"}]
            if "from pg_proc" in sql:
                return [{"name": "takeover_account", "args": "in_user_to_takeover text, in_current_user text", "result": "void"}]
            return []

        def fake_takeover(active_account_id, target_account_id, active_user, target_user):
            calls.append((active_account_id, target_account_id, active_user, target_user))
            raise RuntimeError("character swap aborted after backup because active or target account came online")

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected raw execute")))
        self.patch_flag("CHARACTER_SWAP_ENABLED", True)
        self.panel.create_db_backup = lambda: {"path": "backup.dump", "bytes": 1}
        self.panel.character_swap_takeover = fake_takeover
        self.addCleanup(lambda: setattr(self.panel, "create_db_backup", original_backup))
        self.addCleanup(lambda: setattr(self.panel, "character_swap_takeover", original_takeover))

        with self.assertRaises(RuntimeError):
            self.handler.character_slot_execute({
                "dry_run": False,
                "account_id": 10,
                "action": "switch-character",
                "target_account_id": 11,
                "confirm": "SWAP CHARACTER",
            })
        self.assertEqual(calls, [(10, 11, "active-fls", "stored-fls")])

    def test_character_swap_takeover_commits_only_after_verified_swap(self):
        events = []

        class FakeCursor:
            description = True

            def __init__(self):
                self.select_count = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                events.append(("execute", " ".join(sql.split()), params))

            def fetchall(self):
                self.select_count += 1
                if self.select_count == 1:
                    return [{"account_id": 10, "online_status": "Offline", "fls_id": "active-fls"}, {"account_id": 11, "online_status": "Offline", "fls_id": "stored-fls"}]
                return [{"account_id": 10, "online_status": "Offline", "fls_id": "stored-fls"}, {"account_id": 11, "online_status": "Offline", "fls_id": "active-fls"}]

        class FakeConn:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self, cursor_factory=None):
                return self.cursor_obj

            def commit(self):
                events.append(("commit",))

            def rollback(self):
                events.append(("rollback",))

        self.patch_connect(lambda: FakeConn())
        before, after, verified = self.panel.character_swap_takeover(10, 11, "active-fls", "stored-fls")
        self.assertTrue(verified)
        self.assertEqual(before[0]["fls_id"], "active-fls")
        self.assertEqual(after[0]["fls_id"], "stored-fls")
        self.assertIn(("commit",), events)
        self.assertNotIn(("rollback",), events)

    def test_character_swap_takeover_rolls_back_on_failed_verification(self):
        events = []

        class FakeCursor:
            def __init__(self):
                self.select_count = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                events.append(("execute", " ".join(sql.split()), params))

            def fetchall(self):
                self.select_count += 1
                return [{"account_id": 10, "online_status": "Offline", "fls_id": "active-fls"}, {"account_id": 11, "online_status": "Offline", "fls_id": "stored-fls"}]

        class FakeConn:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self, cursor_factory=None):
                return self.cursor_obj

            def commit(self):
                events.append(("commit",))

            def rollback(self):
                events.append(("rollback",))

        self.patch_connect(lambda: FakeConn())
        with self.assertRaises(RuntimeError):
            self.panel.character_swap_takeover(10, 11, "active-fls", "stored-fls")
        self.assertIn(("rollback",), events)
        self.assertNotIn(("commit",), events)

    def test_character_swap_takeover_rolls_back_on_stale_planned_identity(self):
        events = []

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                events.append(("execute", " ".join(sql.split()), params))

            def fetchall(self):
                return [{"account_id": 10, "online_status": "Offline", "fls_id": "different-fls"}, {"account_id": 11, "online_status": "Offline", "fls_id": "stored-fls"}]

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self, cursor_factory=None):
                return FakeCursor()

            def commit(self):
                events.append(("commit",))

            def rollback(self):
                events.append(("rollback",))

        self.patch_connect(lambda: FakeConn())
        with self.assertRaises(RuntimeError):
            self.panel.character_swap_takeover(10, 11, "active-fls", "stored-fls")
        takeover_calls = [
            event for event in events
            if event[0] == "execute" and "takeover_account" in event[1]
        ]
        self.assertEqual(takeover_calls, [])
        self.assertIn(("rollback",), events)
        self.assertNotIn(("commit",), events)

    def test_character_slot_execution_block_does_not_create_backup(self):
        backups = []
        original_backup = self.panel.create_db_backup

        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))
        self.patch_flag("CHARACTER_SWAP_ENABLED", True)
        self.panel.create_db_backup = lambda: backups.append("backup") or {"path": "backup.dump", "bytes": 1}
        self.addCleanup(lambda: setattr(self.panel, "create_db_backup", original_backup))

        with self.assertRaises(NotImplementedError):
            self.handler.character_slot_execute({"dry_run": False, "account_id": 10, "action": "new-character", "confirm": "SWAP CHARACTER"})
        self.assertEqual(backups, [])

    def test_character_slot_get_route_returns_discovery_payload(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            if "with target_account as" in sql:
                return [{"account_id": 11, "character_name": "Stored", "online_status": "Offline", "ownership_evidence": "same-account-user"}]
            return []

        self.patch_db(fake_query)
        handler, captured = self.make_route_handler("/api/admin/character-slots?account_id=10")
        handler.do_GET()
        self.assertFalse(captured["errors"])
        self.assertEqual(captured["json"]["accountId"], 10)
        self.assertEqual(captured["json"]["candidates"][0]["account_id"], 11)

    def test_character_slot_plan_route_audits_preview(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            return []

        self.patch_db(fake_query)
        captured = self.invoke_post_route("/api/admin/character-slots/plan", {
            "dry_run": True,
            "account_id": 10,
            "action": "new-character",
        })
        self.assertFalse(captured["errors"])
        self.assertEqual(captured["json"]["accountId"], 10)
        self.assertEqual(captured["audits"][0]["action"], "character-slot-plan")
        self.assertFalse(captured["audits"][0]["executable"])

    def test_character_slot_execute_route_dry_run_is_audited_preview(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))
        captured = self.invoke_post_route("/api/admin/character-slots/execute", {
            "dry_run": True,
            "account_id": 10,
            "action": "new-character",
        })
        self.assertFalse(captured["errors"])
        self.assertTrue(captured["json"]["dryRun"])
        self.assertEqual(captured["audits"][0]["action"], "character-slot-execute")

    def test_character_slot_execute_route_rejects_blocked_live_attempt(self):
        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline"}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))
        captured = self.invoke_post_route("/api/admin/character-slots/execute", {
            "dry_run": False,
            "account_id": 10,
            "action": "new-character",
            "confirm": "SWAP CHARACTER",
        })
        self.assertIsNone(captured["json"])
        self.assertEqual(captured["errors"][0]["status"], self.panel.HTTPStatus.UNAUTHORIZED)
        self.assertIn("DUNE_ADMIN_CHARACTER_SWAP_ENABLED", captured["errors"][0]["message"])
        self.assertEqual(captured["audits"][0]["action"], "post-rejected")

    def test_character_slot_execute_route_returns_success_payload(self):
        original_backup = self.panel.create_db_backup
        original_takeover = self.panel.character_swap_takeover

        def fake_query(sql, params=None):
            if "where ps.account_id=%s" in sql and "left join dune.accounts" in sql:
                return [{"account_id": 10, "character_name": "Active", "online_status": "Offline", "fls_id": "active-fls"}]
            if "with target_account as" in sql:
                return [{"account_id": 11, "character_name": "Stored", "online_status": "Offline", "fls_id": "stored-fls", "ownership_evidence": "same-account-user"}]
            if "from pg_proc" in sql:
                return [{"name": "takeover_account", "args": "in_user_to_takeover text, in_current_user text", "result": "void"}]
            return []

        def fake_takeover(active_account_id, target_account_id, active_user, target_user):
            return (
                [{"account_id": active_account_id, "online_status": "Offline", "fls_id": active_user}, {"account_id": target_account_id, "online_status": "Offline", "fls_id": target_user}],
                [{"account_id": active_account_id, "online_status": "Offline", "fls_id": target_user}, {"account_id": target_account_id, "online_status": "Offline", "fls_id": active_user}],
                True,
            )

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected raw execute")))
        self.patch_flag("CHARACTER_SWAP_ENABLED", True)
        self.panel.create_db_backup = lambda: {"path": "backup.dump", "bytes": 1}
        self.panel.character_swap_takeover = fake_takeover
        self.addCleanup(lambda: setattr(self.panel, "create_db_backup", original_backup))
        self.addCleanup(lambda: setattr(self.panel, "character_swap_takeover", original_takeover))

        captured = self.invoke_post_route("/api/admin/character-slots/execute", {
            "dry_run": False,
            "account_id": 10,
            "action": "switch-character",
            "target_account_id": 11,
            "confirm": "SWAP CHARACTER",
        })
        self.assertFalse(captured["errors"])
        self.assertFalse(captured["json"]["dryRun"])
        self.assertTrue(captured["json"]["verified"])
        self.assertEqual(captured["audits"][0]["action"], "character-slot-execute")
        self.assertTrue(captured["audits"][0]["executable"])

    def test_offline_teleport_dry_run_uses_first_party_helper(self):
        calls = []

        def fake_query(sql, params=None):
            calls.append((sql, params))
            if "from dune.player_state ps" in sql and "left join dune.accounts" in sql:
                return [{
                    "account_id": 10,
                    "character_name": "Target",
                    "online_status": "Offline",
                    "server_id": 1,
                    "previous_server_partition_id": 5,
                    "funcom_id": "funcom-user",
                    "fls_id": "fls-user",
                }]
            if "from dune.world_partition" in sql:
                return [{"partition_id": 12, "server_id": 1, "map": "Survival_1", "dimension_index": 0, "label": "Hagga Basin", "blocked": False}]
            if "dune.is_player_offline" in sql:
                return [{"offline": False}]
            if "join dune.actors" in sql:
                return [{"actor_id": 200, "class": "Pawn", "partition_id": 5, "x": 1, "y": 2, "z": 3}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("dry-run executed SQL write")))
        result = self.handler.offline_player_recovery({
            "dry_run": True,
            "account_id": 10,
            "partition_id": 12,
            "location": {"x": 100, "y": 200, "z": 9000},
        })

        self.assertTrue(result["dryRun"])
        self.assertEqual(result["plan"]["function"], "dune.admin_move_offline_player_to_partition")
        self.assertFalse(result["plan"]["executable"])
        self.assertIn("dune.is_player_offline", result["plan"]["blockers"][0])
        self.assertFalse(any("update dune.actors" in sql.lower() for sql, _ in calls))

    def test_offline_teleport_execute_calls_first_party_helper_once(self):
        calls = []

        def fake_query(sql, params=None):
            calls.append((sql, params))
            if "from dune.player_state ps" in sql and "left join dune.accounts" in sql:
                return [{
                    "account_id": 10,
                    "character_name": "Target",
                    "online_status": "Offline",
                    "server_id": 1,
                    "previous_server_partition_id": 5,
                    "funcom_id": "funcom-user",
                    "fls_id": "fls-user",
                }]
            if "from dune.world_partition" in sql:
                return [{"partition_id": 12, "server_id": 1, "map": "Survival_1", "dimension_index": 0, "label": "Hagga Basin", "blocked": False}]
            if "dune.is_player_offline" in sql:
                return [{"offline": True}]
            if "dune.admin_move_offline_player_to_partition" in sql:
                return [{"admin_move_offline_player_to_partition": None}]
            if "join dune.actors" in sql:
                return [{"actor_id": 200, "class": "Pawn", "partition_id": 12, "x": 100, "y": 200, "z": 9000}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected raw execute")))
        self.patch_flag("MUTATIONS_ENABLED", True)
        result = self.handler.offline_player_recovery({
            "dry_run": False,
            "account_id": 10,
            "partition_id": 12,
            "location": {"x": 100, "y": 200, "z": 9000},
            "confirm": "MOVE OFFLINE PLAYER",
        })

        helper_calls = [call for call in calls if "dune.admin_move_offline_player_to_partition" in call[0]]
        self.assertFalse(result["dryRun"])
        self.assertEqual(len(helper_calls), 1)
        self.assertEqual(helper_calls[0][1], ("fls-user", 12, 100.0, 200.0, 9000.0))
        self.assertIn("previousActors", result["rollback"])
        self.assertFalse(any("update dune.actors" in sql.lower() for sql, _ in calls))

    def test_communinet_tutorial_vendor_dry_runs_are_plan_only(self):
        def fake_query(sql, params=None):
            if "load_communinet_player_data" in sql:
                return [{"is_active": True, "selected_channel_name": "general", "channel_name": "general", "is_tuned": True}]
            if "get_all_tutorial_entries" in sql:
                return [{"tutorial_id": 7, "tutorial_state": 1}]
            if "tutorials" in sql:
                return [{"id": 7, "name": "Intro"}]
            if "vendor_stock_cycle" in sql:
                return [{"vendor_id": "ScrapVendor", "player_id": 17, "last_interacted_timestamp": 100}]
            if "interact_get_vendor_items_bought_from_player" in sql:
                return [{"out_template_id": "Item", "out_amount_bought": 1}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))

        communinet = self.handler.communinet_mutation({
            "dry_run": True,
            "action": "update-channel",
            "account_id": 10,
            "channel_name": "general",
            "is_tuned": "false",
        })
        self.assertEqual(communinet["executionGate"], "DUNE_ADMIN_COMMUNINET_MUTATIONS_ENABLED")
        self.assertEqual(communinet["confirm"], "WRITE COMMUNINET")

        tutorial = self.handler.tutorial_mutation({
            "dry_run": True,
            "player_id": 20,
            "tutorial_id": 7,
            "tutorial_state": 2,
        })
        self.assertEqual(tutorial["executionGate"], "DUNE_ADMIN_TUTORIAL_MUTATIONS_ENABLED")
        self.assertEqual(tutorial["confirm"], "WRITE TUTORIAL")
        self.assertEqual(tutorial["plan"]["rollback"]["tutorial_state"], 1)

        vendor = self.handler.vendor_mutation({
            "dry_run": True,
            "vendor_id": "ScrapVendor",
            "player_id": 17,
            "timestamp": 200,
        })
        self.assertEqual(vendor["executionGate"], "DUNE_ADMIN_VENDOR_MUTATIONS_ENABLED")
        self.assertEqual(vendor["confirm"], "WRITE VENDOR")
        self.assertEqual(vendor["plan"]["rollback"]["timestamp"], 100)

    def test_permission_exchange_guild_dry_runs_and_gates(self):
        def fake_query(sql, params=None):
            if "permission_actor_rank" in sql:
                return [{"permission_actor_id": 100, "player_id": 20, "rank": 1}]
            if "permission_actor" in sql:
                return [{"actor_id": 100, "actor_name": "Base", "access_level": 1}]
            if "dune_exchange_retrieve_solari_balance" in sql:
                return [{"solari_balance": 500}]
            if "guilds" in sql:
                return [{"guild_id": 9, "guild_description": "old"}]
            if "guild_members" in sql:
                return [{"guild_id": 9, "player_id": 20, "role_id": 1}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))

        permission = self.handler.permission_mutation({
            "dry_run": True,
            "action": "set-player-rank",
            "actor_id": 100,
            "player_id": 20,
            "rank": 2,
            "map_id": "HaggaBasin",
        })
        self.assertEqual(permission["executionGate"], "DUNE_ADMIN_PERMISSION_MUTATIONS_ENABLED")
        self.assertEqual(permission["confirm"], "WRITE PERMISSION")
        self.assertEqual(permission["plan"]["rollback"]["rank"], 1)

        exchange = self.handler.exchange_mutation({
            "dry_run": True,
            "owner_id": 20,
            "controller_id": 21,
            "amount": 700,
            "mode": "set",
        })
        self.assertEqual(exchange["executionGate"], "DUNE_ADMIN_EXCHANGE_MUTATIONS_ENABLED")
        self.assertEqual(exchange["confirm"], "WRITE EXCHANGE")
        self.assertEqual(exchange["plan"]["delta"], 200)
        self.assertEqual(exchange["plan"]["targetBalance"], 700)

        guild = self.handler.guild_mutation({
            "dry_run": True,
            "action": "edit-description",
            "guild_id": 9,
            "description": "new",
        })
        self.assertEqual(guild["executionGate"], "DUNE_ADMIN_GUILD_MUTATIONS_ENABLED")
        self.assertEqual(guild["confirm"], "WRITE GUILD")
        self.assertEqual(guild["plan"]["rollback"]["description"], "old")

        with self.assertRaises(PermissionError):
            self.handler.permission_mutation({
                "dry_run": False,
                "action": "set-access-level",
                "actor_id": 100,
                "access_level": 2,
                "confirm": "WRITE PERMISSION",
            })

    def test_solari_inventory_grant_dry_run_creates_solaris_coin_stack(self):
        def fake_query(sql, params=None):
            if "from dune.inventories inv" in sql:
                return [{"inventory_id": 14, "account_id": 10, "online_status": "Offline", "max_item_count": 35}]
            if "generate_series" in sql:
                return [{"position_index": 4}]
            if "known_templates" in sql:
                return [{"exists": 1}]
            raise AssertionError(f"unexpected query: {sql}")

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("dry-run executed SQL")))
        result = self.handler.grant_player_inventory_solari({
            "dry_run": True,
            "player_controller_id": 21,
            "inventory_id": 14,
            "amount": 125,
        })
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["location"], "inventory")
        self.assertEqual(result["plan"]["templateId"], "SolarisCoin")
        self.assertEqual(result["plan"]["itemId"], None)
        self.assertEqual(result["plan"]["beforeStack"], 0)
        self.assertEqual(result["plan"]["afterStack"], 125)
        self.assertEqual(result["plan"]["positionIndex"], 4)
        self.assertEqual(result["confirm"], "GRANT SOLARI")

    def test_solari_inventory_grant_execute_requires_confirmation(self):
        self.patch_flag("MUTATIONS_ENABLED", True)
        self.patch_db(
            lambda sql, params=None: [{"inventory_id": 14, "account_id": 10, "online_status": "Offline", "max_item_count": 35}] if "from dune.inventories inv" in sql else ([{"position_index": 4}] if "generate_series" in sql else []),
            lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")),
        )
        with self.assertRaises(PermissionError):
            self.handler.grant_player_inventory_solari({
                "dry_run": False,
                "player_controller_id": 21,
                "inventory_id": 14,
                "amount": 125,
            })

    def test_solari_inventory_grant_execute_creates_stack(self):
        self.patch_flag("MUTATIONS_ENABLED", True)
        executed = []

        def fake_query(sql, params=None):
            if "from dune.inventories inv" in sql:
                return [{"inventory_id": 14, "account_id": 10, "online_status": "Offline", "max_item_count": 35}]
            if "generate_series" in sql:
                return [{"position_index": 4}]
            if "known_templates" in sql:
                return [{"exists": 1}]
            if "advance_items_id_sequencer" in sql:
                return [{"item_id": 100}]
            if "where inventory_id=%s and position_index=%s" in sql:
                return []
            if "from dune.items where id=%s" in sql:
                return [{"id": 100, "inventory_id": 14, "stack_size": 125, "position_index": 4, "template_id": "SolarisCoin"}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: executed.append((" ".join(sql.split()), params)))
        result = self.handler.grant_player_inventory_solari({
            "dry_run": False,
            "player_controller_id": 21,
            "inventory_id": 14,
            "amount": 125,
            "confirm": "GRANT SOLARI",
        })
        self.assertFalse(result["dryRun"])
        self.assertEqual(executed[0][1][0], 100)
        self.assertEqual(executed[0][1][2], 125)
        self.assertEqual(result["after"][0]["stack_size"], 125)

    def test_solari_bank_grant_sets_exchange_balance_directly(self):
        def fake_query(sql, params=None):
            if "player_state" in sql:
                return [{"account_id": 10, "character_name": "Paul", "player_controller_id": 21, "player_pawn_id": 20}]
            if "dune_exchange_retrieve_solari_balance" in sql:
                return [{"solari_balance": 500}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("dry-run executed SQL")))
        result = self.handler.grant_player_bank_solari({
            "dry_run": True,
            "account_id": 10,
            "amount": 125,
        })
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["location"], "bank")
        self.assertEqual(result["ownerId"], 21)
        self.assertEqual(result["controllerId"], 21)
        self.assertEqual(result["plan"]["function"], "direct-update:dune.player_virtual_currency_balances")
        self.assertEqual(result["plan"]["delta"], 125)
        self.assertEqual(result["plan"]["targetBalance"], 625)

    def test_faction_reputation_and_faction_dry_runs(self):
        self.handler.resolve_player_identity = lambda account_id: ({
            "account_id": account_id,
            "character_name": "Tester",
            "online_status": "Offline",
            "player_pawn_id": 200,
        }, "fls-test")

        def fake_query(sql, params=None):
            if "from dune.player_state" in sql:
                return [{"account_id": 10, "character_name": "Tester", "online_status": "Offline", "player_pawn_id": 200}]
            if "information_schema.columns" in sql:
                return [{"column_name": "actor_id"}, {"column_name": "faction_id"}, {"column_name": "reputation_amount"}]
            if "set_player_faction_reputation" in sql:
                return [{"name": "get_player_current_faction_reputation"}, {"name": "set_player_faction_reputation"}]
            if "player_faction_reputation" in sql:
                return [{"actor_id": 200, "faction_id": 1, "reputation_amount": 50}]
            if "select id, name from dune.factions" in sql:
                return [{"id": 1, "name": "Atreides"}, {"id": 2, "name": "Harkonnen"}, {"id": 3, "name": "None"}]
            if "change_player_faction" in sql:
                return [{"name": "change_player_faction"}, {"name": "get_player_faction"}]
            if "player_faction where actor_id" in sql:
                return [{"actor_id": 200, "faction_id": 3}]
            if "get_player_faction" in sql:
                return [{"faction_id": 3}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))

        rep = self.handler.faction_reputation_mutation({
            "dry_run": True,
            "account_id": 10,
            "faction_id": 1,
            "amount": 25,
            "mode": "add",
        })
        self.assertEqual(rep["executionGate"], "DUNE_ADMIN_REPUTATION_MUTATIONS_ENABLED")
        self.assertEqual(rep["plan"]["currentValue"], 50)
        self.assertEqual(rep["plan"]["newValue"], 75)

        faction = self.handler.faction_change_mutation({
            "dry_run": True,
            "account_id": 10,
            "faction_id": 1,
            "neutral_faction_id": 3,
        })
        self.assertEqual(faction["executionGate"], "DUNE_ADMIN_FACTION_MUTATIONS_ENABLED")
        self.assertEqual(faction["confirm"], "CHANGE FACTION")
        self.assertEqual(faction["plan"]["currentFactionId"], 3)

        with self.assertRaises(PermissionError):
            self.handler.faction_change_mutation({
                "dry_run": False,
                "account_id": 10,
                "faction_id": 1,
                "neutral_faction_id": 3,
                "confirm": "CHANGE FACTION",
            })

    def test_journey_respawn_landsraad_dry_runs(self):
        self.handler.resolve_player_identity = lambda account_id: ({
            "account_id": account_id,
            "character_name": "Tester",
            "online_status": "Offline",
            "player_pawn_id": 200,
        }, "fls-test")

        def fake_query(sql, params=None):
            if "admin_get_journey_details" in sql:
                return [{"story_node_id": params[1], "state": "unknown"}]
            if params and params[0] == "complete_journey_story_nodes_for_player":
                return [{"name": "complete_journey_story_nodes_for_player"}]
            if "player_respawn_locations" in sql:
                return [{
                    "id": "0a0556f6-a387-41f2-b613-deacee4e2bd0",
                    "account_id": 10,
                    "map": "HaggaBasin",
                    "last_used_timestamp": 100,
                }]
            if "landsraad_load_current_term" in sql:
                return [{"term_id": 1, "end_time": "2026-05-26 04:55:00", "testterm": False}]
            if "landsraad_decree_term" in sql:
                return [{"term_id": 1, "end_time": "2026-05-26 04:55:00", "testterm": False}]
            if "landsraad_change_term_end_time" in sql or "landsraad_force_end_term" in sql:
                return [{"name": "landsraad_change_term_end_time"}, {"name": "landsraad_force_end_term"}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))

        journey = self.handler.journey_mutation({
            "dry_run": True,
            "account_id": 10,
            "action": "complete",
            "story_node_ids": ["StoryA"],
        })
        self.assertEqual(journey["executionGate"], "DUNE_ADMIN_JOURNEY_MUTATIONS_ENABLED")
        self.assertEqual(journey["confirm"], "WRITE JOURNEY")
        self.assertEqual(journey["plan"]["function"], "dune.complete_journey_story_nodes_for_player")

        respawn = self.handler.respawn_location_mutation({
            "dry_run": True,
            "account_id": 10,
            "respawn_id": "0a0556f6-a387-41f2-b613-deacee4e2bd0",
        })
        self.assertEqual(respawn["executionGate"], "DUNE_ADMIN_RESPAWN_MUTATIONS_ENABLED")
        self.assertEqual(respawn["confirm"], "DELETE RESPAWN")
        self.assertEqual(respawn["plan"]["remainingCount"], 0)

        landsraad = self.handler.landsraad_mutation({
            "dry_run": True,
            "action": "change-end-time",
            "term_id": 1,
            "new_end_time": "2026-05-27 04:55:00",
        })
        self.assertEqual(landsraad["executionGate"], "DUNE_ADMIN_LANDSRAAD_MUTATIONS_ENABLED")
        self.assertEqual(landsraad["confirm"], "WRITE LANDSRAAD")
        self.assertEqual(landsraad["plan"]["rollback"]["new_end_time"], "2026-05-26 04:55:00")

    def test_marker_landclaim_dry_runs_and_gates(self):
        def fake_query(sql, params=None):
            if "from dune.markers" in sql:
                return [{"marker_hash_id": 123, "dimension_index": -1, "map_name": "HaggaBasin"}]
            if "get_landclaim_segments" in sql:
                return [{"grid_location_x": 1, "grid_location_y": 2}]
            return []

        self.patch_db(fake_query, lambda sql, params=None: (_ for _ in ()).throw(AssertionError("unexpected execute")))

        marker = self.handler.marker_mutation({
            "dry_run": True,
            "action": "delete-by-id",
            "marker_ids": [123],
        })
        self.assertEqual(marker["executionGate"], "DUNE_ADMIN_MARKER_MUTATIONS_ENABLED")
        self.assertEqual(marker["confirm"], "DELETE MARKERS")
        self.assertEqual(marker["markerCount"], 1)

        landclaim = self.handler.landclaim_mutation({
            "dry_run": True,
            "action": "add-segment",
            "totem_id": 100,
            "grid_location_x": 3,
            "grid_location_y": 4,
        })
        self.assertEqual(landclaim["executionGate"], "DUNE_ADMIN_LANDCLAIM_MUTATIONS_ENABLED")
        self.assertEqual(landclaim["confirm"], "WRITE LANDCLAIM")

        with self.assertRaises(PermissionError):
            self.handler.marker_mutation({
                "dry_run": False,
                "action": "delete-by-id",
                "marker_ids": [123],
                "confirm": "DELETE MARKERS",
            })

    def test_restart_start_sigpipe_is_success_when_farm_recovers(self):
        command = self.workspace / "scripts" / "restart-target.sh"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        self.panel.RESTART_COMMAND = str(command)
        self.panel.soft_disconnect_online_players = lambda job: {"ok": True}
        self.panel.run_restart_command = lambda command, job, phase: {
            "ok": phase != "start",
            "phase": phase,
            "returncode": 141 if phase == "start" else 0,
            "output": phase,
        }
        self.panel.wait_for_restart_online = lambda: {
            "ok": True,
            "expected": 30,
            "online": 30,
            "readyOnline": 30,
            "alive": 30,
            "active": 30,
        }

        result = self.panel.execute_restart({
            "id": "sigpipe",
            "execute": True,
            "action": "restart",
            "target": "all",
            "services": [],
            "backup": False,
        })

        self.assertTrue(result["ok"])
        self.assertEqual(result["returncode"], 141)
        self.assertIn("141", result["warning"])

    def test_restart_can_skip_soft_disconnect_for_daily_maintenance(self):
        command = self.workspace / "scripts" / "restart-target.sh"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        self.panel.RESTART_COMMAND = str(command)
        self.panel.soft_disconnect_online_players = lambda job: (_ for _ in ()).throw(AssertionError("soft disconnect should be skipped"))
        phases = []
        self.panel.run_restart_command = lambda command, job, phase: phases.append(phase) or {
            "ok": True,
            "phase": phase,
            "returncode": 0,
            "output": phase,
        }
        self.panel.wait_for_restart_online = lambda: {
            "ok": True,
            "expected": 30,
            "online": 30,
            "readyOnline": 30,
            "alive": 30,
            "active": 30,
        }

        result = self.panel.execute_restart({
            "id": "daily",
            "execute": True,
            "action": "restart",
            "target": "all",
            "services": [],
            "backup": False,
            "requireSoftDisconnect": False,
        })

        self.assertTrue(result["ok"])
        self.assertEqual(phases, ["stop", "update", "start"])
        self.assertEqual(result["disconnect"]["skipped"], "soft disconnect not required for this maintenance job")

    def test_partition_31_adds_deep_desert_pvp_to_restart_targets(self):
        workspace = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(workspace, ignore_errors=True))
        workspace.joinpath(".env").write_text("DUNE_WORLD_PARTITION_COUNT=31\n", encoding="utf-8")
        panel = load_admin_panel(workspace)

        self.assertIn("deep-desert-pvp", panel.GAME_MAP_SERVICES)
        self.assertIn("deep-desert-pvp", panel.RESTART_TARGETS["all"]["services"])

    def test_restart_fails_closed_after_update_check_failure(self):
        command = self.workspace / "scripts" / "restart-target.sh"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        self.panel.RESTART_COMMAND = str(command)
        self.panel.soft_disconnect_online_players = lambda job: {"ok": True}
        phases = []

        def fake_run_restart_command(command, job, phase):
            phases.append(phase)
            if phase == "update":
                return {
                    "ok": False,
                    "phase": phase,
                    "returncode": 75,
                    "output": "missing helper image",
                    "error": "Steam package update check failed",
                }
            return {"ok": True, "phase": phase, "returncode": 0, "output": phase}

        self.panel.run_restart_command = fake_run_restart_command
        self.panel.wait_for_restart_online = lambda: {
            "ok": True,
            "expected": 30,
            "online": 30,
            "readyOnline": 30,
            "alive": 30,
            "active": 30,
        }

        result = self.panel.execute_restart({
            "id": "update-failure",
            "execute": True,
            "action": "restart",
            "target": "all",
            "services": [],
            "backup": False,
        })

        self.assertFalse(result["ok"])
        self.assertEqual(phases, ["stop", "update"])
        self.assertEqual(result["error"], "Steam package update check failed")
        self.assertIn("missing helper image", result["output"])

    def test_full_restart_reboots_after_applied_steam_update_when_enabled(self):
        command = self.workspace / "scripts" / "restart-target.sh"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        self.panel.RESTART_COMMAND = str(command)
        self.panel.REBOOT_AFTER_STEAM_UPDATE = True
        self.panel.soft_disconnect_online_players = lambda job: {"ok": True}
        phases = []

        def fake_run(command, job, phase):
            phases.append(phase)
            output = "DUNE_STEAM_UPDATE_APPLIED=100-0:101-0" if phase == "update" else phase
            return {"ok": True, "phase": phase, "returncode": 0, "output": output}

        self.panel.run_restart_command = fake_run
        result = self.panel.execute_restart({
            "id": "updated",
            "execute": True,
            "action": "restart",
            "target": "all",
            "services": [],
            "backup": False,
        })

        self.assertTrue(result["ok"])
        self.assertTrue(result["deferred"])
        self.assertEqual(phases, ["stop", "update", "reboot"])

    def test_full_restart_does_not_reboot_when_steam_build_is_current(self):
        command = self.workspace / "scripts" / "restart-target.sh"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        self.panel.RESTART_COMMAND = str(command)
        self.panel.REBOOT_AFTER_STEAM_UPDATE = True
        self.panel.soft_disconnect_online_players = lambda job: {"ok": True}
        phases = []
        self.panel.run_restart_command = lambda command, job, phase: phases.append(phase) or {
            "ok": True, "phase": phase, "returncode": 0, "output": "status: current" if phase == "update" else phase,
        }
        self.panel.wait_for_restart_online = lambda: {"ok": True}

        result = self.panel.execute_restart({
            "id": "current",
            "execute": True,
            "action": "restart",
            "target": "all",
            "services": [],
            "backup": False,
        })

        self.assertTrue(result["ok"])
        self.assertEqual(phases, ["stop", "update", "start"])

    def test_restart_start_runs_after_maintenance_backup_failure(self):
        command = self.workspace / "scripts" / "restart-target.sh"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        self.panel.RESTART_COMMAND = str(command)
        self.panel.MAINTENANCE_BACKUP_ENABLED = True
        self.panel.soft_disconnect_online_players = lambda job: {"ok": True}
        phases = []
        self.panel.run_restart_command = lambda command, job, phase: phases.append(phase) or {
            "ok": True,
            "phase": phase,
            "returncode": 0,
            "output": phase,
        }
        self.panel.create_maintenance_backup = lambda job: (_ for _ in ()).throw(RuntimeError("backup path unavailable"))
        self.panel.wait_for_restart_online = lambda: {
            "ok": True,
            "expected": 30,
            "online": 30,
            "readyOnline": 30,
            "alive": 30,
            "active": 30,
        }

        result = self.panel.execute_restart({
            "id": "backup-failure",
            "execute": True,
            "action": "restart",
            "target": "all",
            "services": [],
            "backup": True,
        })

        self.assertTrue(result["ok"])
        self.assertEqual(phases, ["stop", "update", "start"])
        self.assertIn("maintenance backup failed", result["warning"])
        self.assertIn("backup path unavailable", result["output"])

    def test_restart_runs_recovery_when_farm_readiness_is_incomplete(self):
        command = self.workspace / "scripts" / "restart-target.sh"
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        self.panel.RESTART_COMMAND = str(command)
        self.panel.soft_disconnect_online_players = lambda job: {"ok": True}
        self.panel.run_restart_command = lambda command, job, phase: {
            "ok": True,
            "phase": phase,
            "returncode": 0,
            "output": phase,
        }
        snapshots = [
            {"ok": False, "expected": 30, "online": 29, "readyOnline": 29, "alive": 29, "active": 29},
            {"ok": True, "expected": 30, "online": 30, "readyOnline": 30, "alive": 30, "active": 30},
        ]
        recoveries = []
        self.panel.wait_for_restart_online = lambda: snapshots.pop(0)
        self.panel.run_restart_recovery = lambda job: recoveries.append(job["id"]) or {"ok": True, "output": "recovered"}

        result = self.panel.execute_restart({
            "id": "recover",
            "execute": True,
            "action": "restart",
            "target": "all",
            "services": [],
            "backup": False,
        })

        self.assertTrue(result["ok"])
        self.assertEqual(recoveries, ["recover"])
        self.assertEqual(result["recovery"]["output"], "recovered")

    def test_artificial_exchange_install_actions_use_explicit_unit_paths(self):
        captured = []
        original = self.panel.run_workspace_command

        def fake_run(command, timeout=60, **kwargs):
            captured.append((list(command), timeout))
            return {"ok": True, "stdout": '{"ok":true}', "stderr": ""}

        self.panel.run_workspace_command = fake_run
        self.addCleanup(lambda: setattr(self.panel, "run_workspace_command", original))

        self.panel.artificial_exchange_action("install-buyer-service")
        self.panel.artificial_exchange_action("install-populator-service")
        self.panel.artificial_exchange_action("install-watchdog-timer")
        self.panel.artificial_exchange_action("watchdog-once")

        commands = [item[0] for item in captured]
        self.assertEqual(commands[0][-2:], ["/etc/systemd/system/dune-artificial-exchange-bot.service", "buyer"])
        self.assertEqual(commands[1][-2:], ["/etc/systemd/system/dune-artificial-exchange-populator.service", "populator"])
        self.assertTrue(commands[2][0].endswith("install-artificial-exchange-watchdog-timer.sh"))
        self.assertTrue(commands[3][0].endswith("artificial-exchange-watchdog.sh"))

    def test_item_catalog_missing_file_is_safe_and_empty(self):
        result = self.panel.load_item_catalog()

        self.assertEqual(result["items"], [])
        self.assertIn("not been generated", result["warning"])

    def test_item_catalog_loads_visual_metadata(self):
        payload = {
            "schemaVersion": 1,
            "source": {"label": "test"},
            "items": [{"templateId": "WeldingTool_01", "name": "Welding Tool", "imageUrl": "https://media.awakening.wiki/wiki/a/a0/tool.png"}],
        }
        self.panel.ITEM_CATALOG_FILE.write_text(json.dumps(payload), encoding="utf-8")

        result = self.panel.load_item_catalog()

        self.assertEqual(result["items"][0]["templateId"], "WeldingTool_01")
        self.assertEqual(self.panel.catalog_item("WeldingTool_01")["name"], "Welding Tool")
        self.assertIsNone(self.panel.catalog_item("HouseWeldingTool"))

    def test_docker_log_stream_decoder_handles_framed_and_plain_logs(self):
        first = b"stdout line\n"
        second = b"stderr line\n"
        framed = b"\x01\x00\x00\x00" + len(first).to_bytes(4, "big") + first
        framed += b"\x02\x00\x00\x00" + len(second).to_bytes(4, "big") + second

        self.assertEqual(self.panel.decode_docker_log_stream(framed), "stdout line\nstderr line\n")
        self.assertEqual(self.panel.decode_docker_log_stream(b"plain tty log\n"), "plain tty log\n")

    def test_service_logs_only_accept_project_service_names(self):
        original_containers = self.panel.docker_project_containers
        original_http = self.panel.docker_http_get
        self.panel.docker_project_containers = lambda: [{
            "Id": "a" * 64,
            "Names": ["/dune_server-director-1"],
            "Labels": {"com.docker.compose.service": "director"},
            "Created": 10,
        }]
        self.panel.docker_http_get = lambda path, **kwargs: ({}, b"director ready\n")
        self.addCleanup(lambda: setattr(self.panel, "docker_project_containers", original_containers))
        self.addCleanup(lambda: setattr(self.panel, "docker_http_get", original_http))

        result = self.panel.docker_service_logs("director", 250)

        self.assertEqual(result["tail"], 250)
        self.assertEqual(result["logs"], "director ready\n")
        with self.assertRaises(ValueError):
            self.panel.docker_service_logs("../../postgres", 10)
        with self.assertRaises(ValueError):
            self.panel.docker_service_logs("not-in-project", 10)

    def test_backup_inventory_and_verifier_reject_path_traversal(self):
        backup_set = self.workspace / "backups" / "20260715T120000Z"
        backup_set.mkdir(parents=True)
        (backup_set / "manifest.txt").write_text("WORLD_NAME=test\n", encoding="utf-8")
        (backup_set / "postgres.dump").write_bytes(b"test")
        verifier = self.workspace / "scripts" / "verify-backup.sh"
        verifier.write_text("#!/bin/sh\ntest -f \"$1/manifest.txt\"\n", encoding="utf-8")
        verifier.chmod(0o755)

        inventory = self.panel.backup_inventory()
        verified = self.panel.verify_backup_set("20260715T120000Z")

        self.assertEqual(inventory["sets"][0]["path"], "20260715T120000Z")
        self.assertTrue(verified["ok"])
        with self.assertRaises(ValueError):
            self.panel.resolve_backup_set("../outside")
        with self.assertRaises(ValueError):
            self.panel.resolve_backup_set("/tmp/outside")

    def test_database_browser_is_allowlisted_capped_and_redacted(self):
        def fake_query(sql, params=None):
            if "from information_schema.tables" in sql and "table_name=%s" in sql:
                return [{"table_type": "BASE TABLE"}]
            if sql.startswith('SELECT * FROM "dune"."accounts"'):
                return [{"id": 1, "service_auth_token": "secret-token", "display_name": "Tester"}]
            if "from information_schema.columns" in sql:
                return [
                    {"name": "id", "type": "bigint", "nullable": "NO"},
                    {"name": "service_auth_token", "type": "text", "nullable": "YES"},
                ]
            if "from information_schema.tables" in sql:
                return [{"schema": "dune", "name": "accounts", "type": "BASE TABLE"}]
            raise AssertionError(sql)

        self.patch_db(fake_query)

        catalog = self.panel.database_browser_catalog()
        preview = self.panel.database_table_preview("dune", "accounts", 999)

        self.assertEqual(catalog["tables"][0]["name"], "accounts")
        self.assertEqual(preview["limit"], 200)
        self.assertEqual(preview["rows"][0]["service_auth_token"], "[redacted]")
        self.assertEqual(preview["rows"][0]["display_name"], "Tester")
        with self.assertRaises(ValueError):
            self.panel.database_table_preview("pg_catalog", "pg_authid", 10)
        with self.assertRaises(ValueError):
            self.panel.database_table_preview("dune", "accounts; drop table dune.accounts", 10)

    def test_infrastructure_page_and_routes_are_registered(self):
        self.assertTrue(self.handler.is_app_route("/infrastructure"))
        self.assertIn('data-tab="infrastructure"', self.panel.INDEX)
        self.assertIn("/api/ops/services", self.panel.INDEX)
        self.assertIn("/api/ops/backups/verify", self.panel.INDEX)
        self.assertIn("/api/ops/database/table", self.panel.INDEX)

    def test_world_views_are_read_only_bounded_and_registered(self):
        executed = []

        def fake_query(sql, params=None):
            if "from dune.guilds g" in sql:
                return [{"guild_id": 9, "guild_name": "Test Guild", "member_count": 1}]
            if "get_guild_data" in sql:
                return [{"guild_id": 9, "guild_name": "Test Guild"}]
            if "get_guild_members" in sql:
                return [{"guild_id": 9, "player_id": 200, "role_id": 1}]
            if "get_guild_invites" in sql:
                return []
            if "landsraad_load_current_term" in sql:
                return [{"term_id": 4, "end_time": "2026-07-20"}]
            if "landsraad_decree_term" in sql:
                return [{"term_id": 4}]
            if "landsraad_decrees" in sql:
                return [{"id": 1, "decree_name": "Test Decree"}]
            if "landsraad_tasks" in sql and "landsraad_task_" not in sql:
                return [{"id": 10, "term_id": 4, "board_index": 0}]
            if "landsraad_task_rewards" in sql:
                return [{"task_id": 10, "threshold": 100}]
            if "landsraad_task_faction_contributions" in sql:
                return [{"task_id": 10, "amount": 25}]
            if "landsraad_task_player_contributions" in sql:
                return [{"task_id": 10, "amount": 10}]
            if "landsraad_task_guild_contributions" in sql:
                return [{"task_id": 10, "amount": 15}]
            if "from dune.placeables p" in sql:
                return [{"id": 55, "class": "StorageContainer_Placeable", "item_count": 3, "owner_name": "Tester"}]
            raise AssertionError(sql)

        self.patch_db(fake_query, lambda sql, params=None: executed.append((sql, params)))

        guilds = self.panel.world_guilds("Test")
        members = self.panel.world_guild_members(9)
        landsraad = self.panel.world_landsraad()
        storage = self.panel.world_storage()

        self.assertTrue(guilds["readOnly"])
        self.assertEqual(guilds["maxRows"], 500)
        self.assertEqual(members["members"][0]["player_id"], 200)
        self.assertEqual(landsraad["tasks"][0]["term_id"], 4)
        self.assertEqual(storage["maxRows"], 2000)
        self.assertEqual(storage["rows"][0]["item_count"], 3)
        self.assertEqual(executed, [])
        self.assertTrue(self.handler.is_app_route("/world"))
        self.assertIn('data-tab="world"', self.panel.INDEX)
        self.assertIn("/api/world/guilds", self.panel.INDEX)
        self.assertIn("/api/world/landsraad", self.panel.INDEX)
        self.assertIn("/api/world/storage", self.panel.INDEX)

    def test_world_routes_require_valid_guild_ids_and_return_reads(self):
        self.patch_db(lambda sql, params=None: [] if "get_guild" in sql else [{"guild_id": 9}] if "from dune.guilds g" in sql else [])
        handler, captured = self.make_route_handler("/api/world/guilds?q=Test")
        handler.do_GET()
        self.assertEqual(captured["errors"], [])
        self.assertTrue(captured["json"]["readOnly"])

        handler, captured = self.make_route_handler("/api/world/guild-members?guild_id=bad")
        handler.do_GET()
        self.assertEqual(len(captured["errors"]), 1)
        self.assertIn("positive integer", captured["errors"][0]["message"])

    def test_blueprint_archive_validation_normalizes_ids_and_rejects_bad_rows(self):
        archive = self.panel.blueprint_admin.validate_archive({
            "name": "Test_Base.v1",
            "instances": [{"instance_id": 0, "building_type": "MTX_Smug_Foundation", "x": 1, "y": 2, "z": 3, "rotation": 90}],
            "placeables": [{"placeable_id": 0, "building_type": "Generator_Placeable", "x": 4, "y": 5, "z": 6}],
            "pentashields": [{"placeable_id": 0, "scale": [10, 2, 10]}],
        })

        self.assertEqual(archive["name"], "Test Base v1")
        self.assertEqual(archive["instances"][0]["instance_id"], 1)
        self.assertTrue(archive["instances"][0]["provides_stability"])
        self.assertEqual(archive["placeables"][0]["placeable_id"], 1)
        self.assertEqual(archive["pentashields"][0]["placeable_id"], 1)

        with self.assertRaises(ValueError):
            self.panel.blueprint_admin.validate_archive({"instances": []})
        with self.assertRaises(ValueError):
            self.panel.blueprint_admin.validate_archive({"instances": [{"building_type": "bad type with spaces"}]})
        with self.assertRaises(ValueError):
            self.panel.blueprint_admin.validate_archive({"placeables": [
                {"placeable_id": 2, "building_type": "A"},
                {"placeable_id": 2, "building_type": "B"},
            ]})

    def test_blueprint_import_plan_checks_player_inventory_without_writing(self):
        executed = []

        def fake_query(sql, params=None):
            if "from dune.player_state" in sql:
                return [{"player_pawn_id": 200, "character_name": "Tester", "online_status": "Offline"}]
            if "from dune.inventories" in sql:
                return [{"id": 300, "max_item_count": 40, "used_slots": 2}]
            raise AssertionError(sql)

        plan = self.panel.blueprint_admin.plan_import(fake_query, 200, {
            "name": "Base",
            "instances": [{"building_type": "MTX_Smug_Foundation", "x": 0, "y": 0, "z": 0, "rotation": 0}],
        })

        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["inventory"]["available_slots"], 38)
        self.assertEqual(plan["counts"]["instances"], 1)
        self.assertEqual(executed, [])

    def test_blueprint_routes_are_registered_and_execution_is_backed_up(self):
        originals = {
            "capabilities": self.panel.blueprint_admin.capabilities,
            "list_blueprints": self.panel.blueprint_admin.list_blueprints,
            "plan_import": self.panel.blueprint_admin.plan_import,
            "import_blueprint": self.panel.blueprint_admin.import_blueprint,
            "create_db_backup": self.panel.create_db_backup,
        }
        self.panel.blueprint_admin.capabilities = lambda query_fn: {"supported": True, "tables": {}}
        self.panel.blueprint_admin.list_blueprints = lambda query_fn: [{"id": 1, "name": "Base"}]
        self.panel.blueprint_admin.plan_import = lambda query_fn, player_id, payload, filename="": {
            "ok": True, "dryRun": True, "playerPawnId": int(player_id), "archive": {"name": "Base", "instances": [{"building_type": "Foundation"}], "placeables": [], "pentashields": []}
        }
        imports = []
        backups = []
        self.panel.blueprint_admin.import_blueprint = lambda connect_fn, player_id, archive, fallback="": imports.append((player_id, archive)) or {"ok": True, "blueprintId": 4, "playerPawnId": player_id, "verified": True}
        self.panel.create_db_backup = lambda: backups.append(True) or {"path": "backup.dump", "bytes": 1}
        for name, value in originals.items():
            target = self.panel if name == "create_db_backup" else self.panel.blueprint_admin
            self.addCleanup(lambda target=target, name=name, value=value: setattr(target, name, value))

        handler, captured = self.make_route_handler("/api/admin/blueprints")
        handler.do_GET()
        self.assertEqual(captured["errors"], [])
        self.assertEqual(captured["json"]["rows"][0]["name"], "Base")
        self.assertTrue(self.handler.is_app_route("/blueprints"))
        self.assertIn('data-tab="blueprints"', self.panel.INDEX)

        preview = self.invoke_post_route("/api/admin/blueprints", {
            "action": "import", "dry_run": True, "player_pawn_id": 200,
            "blueprint": {"instances": [{"building_type": "Foundation"}]},
        })
        self.assertEqual(preview["errors"], [])
        self.assertEqual(preview["json"]["confirm"], "IMPORT BLUEPRINT")
        self.assertEqual(backups, [])

        self.patch_flag("BLUEPRINT_MUTATIONS_ENABLED", True)
        handler = self.make_route_handler("/api/admin/blueprints")[0]
        handler.require_mutations = lambda: None
        handler.require_item_grants = lambda: None
        original_validate = self.panel.validate_json_post
        original_parse = self.panel.parse_body
        self.panel.validate_json_post = lambda request_handler, max_bytes=self.panel.MAX_BODY_BYTES: None
        self.panel.parse_body = lambda request_handler, max_bytes=self.panel.MAX_BODY_BYTES: {
            "action": "import", "dry_run": False, "player_pawn_id": 200,
            "blueprint": {"instances": [{"building_type": "Foundation"}]},
            "confirm": "IMPORT BLUEPRINT",
        }
        self.addCleanup(lambda: setattr(self.panel, "validate_json_post", original_validate))
        self.addCleanup(lambda: setattr(self.panel, "parse_body", original_parse))
        handler.do_POST()
        self.assertEqual(backups, [True])
        self.assertEqual(imports[0][0], 200)

    def test_structured_augment_catalog_enforces_item_limits_and_builds_stats(self):
        item = {
            "templateId": "Combat_Heavy_Unique_Reinforced_Boots_06",
            "name": "Bulwark Boots",
            "category": "armor/combat",
        }
        compatibility = self.panel.augment_admin.compatible_augments(item)
        self.assertTrue(compatibility["supported"])
        self.assertEqual(compatibility["kind"], "clothing")
        self.assertEqual(compatibility["limit"], 2)
        self.assertEqual(self.panel.augment_admin.slot_keystone_ids(compatibility), [42, 43])
        augment_id = compatibility["augments"][0]["templateId"]
        queries = []

        def fake_query(sql, params=None):
            queries.append((sql, params))
            return []

        built = self.panel.augment_admin.build_stats(fake_query, item, [augment_id], 5, {})
        payload = built["stats"]["FAugmentedItemStats"][1]
        self.assertEqual(payload["AppliedAugments"], [{"Name": augment_id}])
        self.assertEqual(payload["AppliedAugmentQualities"], [5])
        self.assertTrue(all(value == 1 for value in payload["AppliedAugmentRollData"][0]["StatRolls"]))
        self.assertEqual(len(queries), 2)

        with self.assertRaises(ValueError):
            self.panel.augment_admin.validate_selection(item, [row["templateId"] for row in compatibility["augments"][:3]], 1)
        with self.assertRaises(ValueError):
            self.panel.augment_admin.validate_selection(item, ["T6_Augment_Acuracy1"], 1)

    def test_augment_routes_preview_and_back_up_execution(self):
        item = {
            "id": 41,
            "template_id": "Combat_Heavy_Unique_Reinforced_Boots_06",
            "stats": {},
            "account_id": 10,
            "character_name": "Tester",
            "player_controller_id": 11,
            "online_status": "Offline",
        }
        self.patch_db(lambda sql, params=None: [item] if "from dune.items i join dune.inventories" in sql else [])
        originals = {
            "catalog_item": self.panel.catalog_item,
            "build_stats": self.panel.augment_admin.build_stats,
            "apply_to_item": self.panel.augment_admin.apply_to_item,
            "create_db_backup": self.panel.create_db_backup,
        }
        self.panel.catalog_item = lambda template: {"templateId": template, "name": "Bulwark Boots", "category": "armor/combat"}
        compatibility = {"kind": "clothing", "limit": 2, "itemTags": ["Items.Clothes.HeavyArmor"], "augments": [], "supported": True}
        self.panel.augment_admin.build_stats = lambda query_fn, metadata, augments, grade, stats=None: {
            "stats": {"FAugmentedItemStats": [[], {}]}, "augments": list(augments), "grade": int(grade), "compatibility": compatibility,
        }
        applied = []
        self.panel.augment_admin.apply_to_item = lambda connect_fn, item_id, augments, grade, metadata: applied.append((item_id, augments, grade)) or {"ok": True, "itemId": item_id, "augments": augments, "grade": int(grade), "verified": True}
        backups = []
        self.panel.create_db_backup = lambda: backups.append(True) or {"path": "backup.dump", "bytes": 1}
        for name, value in originals.items():
            target = self.panel.augment_admin if name in ("build_stats", "apply_to_item") else self.panel
            self.addCleanup(lambda target=target, name=name, value=value: setattr(target, name, value))

        preview = self.invoke_post_route("/api/admin/augments", {
            "action": "apply", "item_id": 41, "augments": ["T6_Augment_Armor1"], "grade": 5, "dry_run": True,
        })
        self.assertEqual(preview["errors"], [])
        self.assertTrue(preview["json"]["eligible"])
        self.assertEqual(preview["json"]["confirm"], "APPLY AUGMENTS")
        self.assertEqual(backups, [])

        self.patch_flag("AUGMENT_MUTATIONS_ENABLED", True)
        handler, captured = self.make_route_handler("/api/admin/augments")
        handler.require_mutations = lambda: None
        handler.require_item_grants = lambda: None
        original_validate = self.panel.validate_json_post
        original_parse = self.panel.parse_body
        self.panel.validate_json_post = lambda request_handler, **kwargs: None
        self.panel.parse_body = lambda request_handler, **kwargs: {
            "action": "apply", "item_id": 41, "augments": ["T6_Augment_Armor1"], "grade": 5,
            "dry_run": False, "confirm": "APPLY AUGMENTS",
        }
        self.addCleanup(lambda: setattr(self.panel, "validate_json_post", original_validate))
        self.addCleanup(lambda: setattr(self.panel, "parse_body", original_parse))
        handler.do_POST()
        self.assertEqual(captured["errors"], [])
        self.assertEqual(backups, [True])
        self.assertEqual(applied[0][0], 41)
        self.assertEqual(captured["json"]["backup"]["path"], "backup.dump")

    def test_database_sql_console_classifies_bounds_and_gates_writes(self):
        self.assertTrue(self.panel.database_sql_is_read_only("-- note\nWITH rows AS (SELECT 1) SELECT * FROM rows"))
        self.assertFalse(self.panel.database_sql_is_read_only("update dune.items set stack_size=1"))
        with self.assertRaises(ValueError):
            self.panel.normalize_database_sql("select 1; select 2")

        original_runner = self.panel.run_database_sql
        original_backup = self.panel.create_db_backup
        calls = []
        backups = []
        self.panel.run_database_sql = lambda connect_fn, sql, allow_write=False, max_rows=200: calls.append((sql, allow_write, int(max_rows))) or {"ok": True, "readOnly": not allow_write, "rows": [], "rowCount": 0, "affectedRows": 1 if allow_write else None}
        self.panel.create_db_backup = lambda: backups.append(True) or {"path": "backup.dump", "bytes": 1}
        self.addCleanup(lambda: setattr(self.panel, "run_database_sql", original_runner))
        self.addCleanup(lambda: setattr(self.panel, "create_db_backup", original_backup))
        self.patch_flag("DATABASE_QUERY_ENABLED", True)

        read = self.invoke_post_route("/api/ops/database/query", {"sql": "select 1", "max_rows": 50})
        self.assertEqual(read["errors"], [])
        self.assertTrue(read["json"]["readOnly"])
        self.assertEqual(backups, [])

        self.patch_flag("DATABASE_WRITE_ENABLED", True)
        handler, captured = self.make_route_handler("/api/ops/database/query")
        handler.require_mutations = lambda: None
        original_validate = self.panel.validate_json_post
        original_parse = self.panel.parse_body
        self.panel.validate_json_post = lambda request_handler, **kwargs: None
        self.panel.parse_body = lambda request_handler, **kwargs: {"sql": "update dune.items set stack_size=1 where false", "confirm": "EXECUTE DATABASE WRITE"}
        self.addCleanup(lambda: setattr(self.panel, "validate_json_post", original_validate))
        self.addCleanup(lambda: setattr(self.panel, "parse_body", original_parse))
        handler.do_POST()
        self.assertEqual(captured["errors"], [])
        self.assertEqual(backups, [True])
        self.assertTrue(calls[-1][1])

    def test_backup_import_rejects_traversal_and_verifies_valid_archive(self):
        original_verify = self.panel.verify_backup_set
        self.panel.verify_backup_set = lambda path: {"ok": True, "path": path}
        self.addCleanup(lambda: setattr(self.panel, "verify_backup_set", original_verify))

        valid_buffer = io.BytesIO()
        with tarfile.open(fileobj=valid_buffer, mode="w:gz") as archive:
            payload = b"postgres custom dump fixture"
            info = tarfile.TarInfo("export/postgres-dune_sb_1_4_0_0.dump")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
            manifest = b"created_utc=test\n"
            info = tarfile.TarInfo("export/manifest.txt")
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
        encoded = base64.b64encode(valid_buffer.getvalue()).decode()
        result = self.panel.import_backup_archive("fixture.tar.gz", encoded, "")
        self.assertTrue(result["ok"])
        self.assertTrue((self.panel.BACKUPS_ROOT / result["path"] / "manifest.txt").exists())

        bad_buffer = io.BytesIO()
        with tarfile.open(fileobj=bad_buffer, mode="w:gz") as archive:
            payload = b"bad"
            info = tarfile.TarInfo("../escape.dump")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        with self.assertRaises(ValueError):
            self.panel.import_backup_archive("bad.tar.gz", base64.b64encode(bad_buffer.getvalue()).decode(), "")

    def test_native_restore_dry_run_resolves_current_backup_layout(self):
        backup_set = self.panel.BACKUPS_ROOT / "maintenance" / "fixture"
        backup_set.mkdir(parents=True)
        (backup_set / "postgres-dune_sb_1_4_0_0.dump").write_bytes(b"fixture")
        for name in ("server-saved.tgz", "rabbitmq.tgz", "config-and-env.tgz"):
            with tarfile.open(backup_set / name, "w:gz"):
                pass
        original_verify = self.panel.verify_backup_set
        self.panel.verify_backup_set = lambda path: {"ok": True, "path": path}
        self.addCleanup(lambda: setattr(self.panel, "verify_backup_set", original_verify))

        result = self.panel.restore_backup_set(
            "maintenance/fixture",
            {"serverSaved": True, "rabbitmq": True, "config": True, "tls": True},
            dry_run=True,
        )

        self.assertTrue(result["dryRun"])
        self.assertEqual(result["plan"]["postgres"], "postgres-dune_sb_1_4_0_0.dump")
        self.assertTrue(result["layers"]["serverSaved"])
        self.assertEqual(result["confirm"], "RESTORE BACKUP")

    def test_native_restore_stops_writers_backs_up_restores_and_restarts(self):
        backup_set = self.panel.BACKUPS_ROOT / "fixture"
        backup_set.mkdir(parents=True)
        (backup_set / "postgres-dune_sb_1_4_0_0.dump").write_bytes(b"fixture")
        originals = {
            "verify_backup_set": self.panel.verify_backup_set,
            "stop_restore_writers": self.panel.stop_restore_writers,
            "create_full_backup": self.panel.create_full_backup,
            "restore_postgres_dump": self.panel.restore_postgres_dump,
            "restore_selected_file_layers": self.panel.restore_selected_file_layers,
            "start_restore_writers": self.panel.start_restore_writers,
        }
        calls = []
        self.panel.verify_backup_set = lambda path: {"ok": True, "path": path}
        self.panel.stop_restore_writers = lambda: calls.append("stop") or [{"service": "survival", "containerId": "a" * 64}]
        self.panel.create_full_backup = lambda: calls.append("backup") or {"ok": True, "path": "maintenance/pre-restore"}
        self.panel.restore_postgres_dump = lambda path: calls.append("postgres") or {"ok": True}
        self.panel.restore_selected_file_layers = lambda artifacts, requested, staging: calls.append("layers") or {}
        self.panel.start_restore_writers = lambda stopped: calls.append("restart") or [{"ok": True, "service": "survival"}]
        for name, value in originals.items():
            self.addCleanup(lambda name=name, value=value: setattr(self.panel, name, value))
        self.patch_db(lambda sql, params=None: [{"count": 0}])

        result = self.panel.restore_backup_set("fixture", {}, dry_run=False)

        self.assertTrue(result["ok"])
        self.assertEqual(calls, ["stop", "backup", "postgres", "layers", "restart"])
        self.assertFalse(result["worldStartRequired"])

    def test_restore_post_hooks_only_reconcile_maps_that_were_running(self):
        original_action = self.panel.docker_container_action
        original_run = self.panel.subprocess.run
        starts = []
        commands = []
        self.panel.docker_container_action = lambda container_id, action, timeout=120: starts.append((container_id, action))
        self.panel.subprocess.run = lambda argv, **kwargs: commands.append((argv, kwargs["env"])) or types.SimpleNamespace(returncode=0, stdout="ok", stderr="")
        self.addCleanup(lambda: setattr(self.panel, "docker_container_action", original_action))
        self.addCleanup(lambda: setattr(self.panel.subprocess, "run", original_run))

        result = self.panel.start_restore_writers([
            {"service": "survival", "containerId": "a" * 64},
            {"service": "prometheus", "containerId": "b" * 64},
        ])

        self.assertEqual(len(starts), 2)
        self.assertEqual(commands[0][1]["DUNE_RESTART_SERVICES"], "survival")
        self.assertNotIn("deep-desert", commands[0][1]["DUNE_RESTART_SERVICES"])
        self.assertTrue(all(row["ok"] for row in result))

    def test_memory_balancer_transfers_one_gib_and_restores_baselines(self):
        gib = 1024 ** 3
        rows = [
            {"service": "survival", "containerId": "a" * 64, "memoryUsageBytes": int(9.5 * gib), "memoryLimitBytes": 10 * gib, "memoryPercent": 95.0},
            {"service": "deep-desert", "containerId": "b" * 64, "memoryUsageBytes": 2 * gib, "memoryLimitBytes": 10 * gib, "memoryPercent": 20.0},
        ]
        original_rows = self.panel.map_memory_rows
        original_update = self.panel.update_container_memory
        self.panel.map_memory_rows = lambda: [dict(row) for row in rows]
        updates = []
        self.panel.update_container_memory = lambda container_id, limit: updates.append((container_id, limit)) or {"ok": True, "limitBytes": limit}
        self.addCleanup(lambda: setattr(self.panel, "map_memory_rows", original_rows))
        self.addCleanup(lambda: setattr(self.panel, "update_container_memory", original_update))

        enabled = self.panel.set_memory_balancer_enabled(True)
        ticked = self.panel.memory_balancer_tick()
        disabled = self.panel.set_memory_balancer_enabled(False)

        self.assertTrue(enabled["enabled"])
        self.assertEqual(updates[:2], [("a" * 64, 11 * gib), ("b" * 64, 9 * gib)])
        self.assertIn("deep-desert -> survival", ticked["lastAction"])
        self.assertFalse(disabled["enabled"])
        self.assertIn(("a" * 64, 10 * gib), updates[2:])
        self.assertIn(("b" * 64, 10 * gib), updates[2:])

    def test_autoscaler_stops_idle_dynamic_map_and_restarts_on_demand(self):
        original_inventory = self.panel.docker_service_inventory
        original_counts = self.panel.autoscaler_player_counts
        original_control = self.panel.autoscaler_service_action
        original_travel_demand = self.panel.autoscaler_collect_travel_demand
        running = {"value": True}
        self.panel.docker_service_inventory = lambda: [{
            "service": "deep-desert", "state": "running" if running["value"] else "exited",
            "containerId": "a" * 12,
        }]
        self.panel.autoscaler_player_counts = lambda: {"deep-desert": 0}
        self.panel.autoscaler_collect_travel_demand = lambda state, now=None: []
        actions = []
        def control(service, action):
            actions.append((service, action))
            running["value"] = action == "start"
            return {"ok": True, "service": service, "action": action}
        self.panel.autoscaler_service_action = control
        self.addCleanup(lambda: setattr(self.panel, "docker_service_inventory", original_inventory))
        self.addCleanup(lambda: setattr(self.panel, "autoscaler_player_counts", original_counts))
        self.addCleanup(lambda: setattr(self.panel, "autoscaler_service_action", original_control))
        self.addCleanup(lambda: setattr(self.panel, "autoscaler_collect_travel_demand", original_travel_demand))
        state = self.panel.read_autoscaler_state()
        state.update({
            "enabled": True,
            "profile": "custom",
            "idleSeconds": 60,
            "retentionSeconds": 60,
            "retentionByService": {},
            "maxWarmDynamicMaps": 0,
            "modes": {"deep-desert": "dynamic"},
            "idleSince": {"deep-desert": 1},
            "demand": {},
        })
        self.panel.write_autoscaler_state(state)

        stopped = self.panel.autoscaler_tick()
        started = self.panel.autoscaler_control("demand", "deep-desert")

        self.assertEqual(actions, [("deep-desert", "stop"), ("deep-desert", "start")])
        self.assertFalse(stopped["lastError"])
        self.assertFalse(started["lastError"])
        self.assertIn("deep-desert", self.panel.read_autoscaler_state()["demand"])

    def test_autoscaler_start_uses_guarded_fast_start(self):
        original_control = self.panel.control_docker_service
        original_fast_start = self.panel.AUTOSCALER_FAST_START
        calls = []
        self.panel.AUTOSCALER_FAST_START = True
        self.panel.control_docker_service = lambda service, action, fast_dynamic_start=False: calls.append(
            (service, action, fast_dynamic_start)
        ) or {"ok": True}
        self.addCleanup(lambda: setattr(self.panel, "control_docker_service", original_control))
        self.addCleanup(lambda: setattr(self.panel, "AUTOSCALER_FAST_START", original_fast_start))

        result = self.panel.autoscaler_service_action("arrakeen", "start")

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("arrakeen", "start", True)])

    def test_autoscaler_mode_change_clears_stale_demand(self):
        state = self.panel.read_autoscaler_state()
        state.update({"enabled": False, "demand": {"arrakeen": time.time()}})
        self.panel.write_autoscaler_state(state)

        self.panel.autoscaler_control("set-mode", "arrakeen", "dynamic")

        self.assertNotIn("arrakeen", self.panel.read_autoscaler_state()["demand"])

    def test_autoscaler_profiles_cover_minimum_balanced_and_full_warm(self):
        minimum = self.panel.autoscaler_apply_profile({}, "minimum-footprint")
        balanced = self.panel.autoscaler_apply_profile({}, "balanced")
        full = self.panel.autoscaler_apply_profile({}, "full-warm")

        self.assertEqual(minimum["modes"]["survival"], "always-on")
        self.assertEqual(minimum["modes"]["arrakeen"], "dynamic")
        self.assertEqual(balanced["maxWarmDynamicMaps"], self.panel.AUTOSCALER_BALANCED_MAX_WARM_MAPS)
        self.assertEqual(balanced["retentionByService"]["arrakeen"], 2700)
        self.assertTrue(all(mode == "always-on" for mode in full["modes"].values()))

    def test_autoscaler_balanced_budget_evicts_oldest_optional_warm_map(self):
        original_inventory = self.panel.docker_service_inventory
        original_counts = self.panel.autoscaler_player_counts
        original_demand = self.panel.autoscaler_collect_travel_demand
        original_action = self.panel.autoscaler_service_action
        services = ["arrakeen", "harko-village", "testing-hephaestus"]
        self.panel.docker_service_inventory = lambda: [{"service": service, "state": "running"} for service in services]
        self.panel.autoscaler_player_counts = lambda: {}
        self.panel.autoscaler_collect_travel_demand = lambda state, now=None: []
        actions = []
        self.panel.autoscaler_service_action = lambda service, action: actions.append((service, action)) or {"ok": True}
        self.addCleanup(lambda: setattr(self.panel, "docker_service_inventory", original_inventory))
        self.addCleanup(lambda: setattr(self.panel, "autoscaler_player_counts", original_counts))
        self.addCleanup(lambda: setattr(self.panel, "autoscaler_collect_travel_demand", original_demand))
        self.addCleanup(lambda: setattr(self.panel, "autoscaler_service_action", original_action))
        now = time.time()
        state = self.panel.read_autoscaler_state()
        state.update({
            "enabled": True, "profile": "balanced", "retentionSeconds": 3600,
            "maxWarmDynamicMaps": 2, "minAvailableMemoryBytes": 0,
            "modes": {service: "dynamic" for service in services},
            "idleSince": {service: now - 10 for service in services},
            "lastActivity": {"arrakeen": now - 300, "harko-village": now - 200, "testing-hephaestus": now - 100},
            "demand": {},
        })
        self.panel.write_autoscaler_state(state)

        result = self.panel.autoscaler_tick()

        self.assertFalse(result["lastError"])
        self.assertEqual(actions, [("arrakeen", "stop")])
        self.assertEqual(self.panel.read_autoscaler_state()["lastEvictionReason"]["arrakeen"], "warm-budget-lru")

    def test_autoscaler_memory_floor_evicts_only_until_available_recovers(self):
        originals = {
            "docker_service_inventory": self.panel.docker_service_inventory,
            "autoscaler_player_counts": self.panel.autoscaler_player_counts,
            "autoscaler_collect_travel_demand": self.panel.autoscaler_collect_travel_demand,
            "autoscaler_service_action": self.panel.autoscaler_service_action,
            "autoscaler_host_memory": self.panel.autoscaler_host_memory,
        }
        services = ["arrakeen", "harko-village"]
        self.panel.docker_service_inventory = lambda: [{"service": service, "state": "running"} for service in services]
        self.panel.autoscaler_player_counts = lambda: {}
        self.panel.autoscaler_collect_travel_demand = lambda state, now=None: []
        actions = []
        self.panel.autoscaler_service_action = lambda service, action: actions.append((service, action)) or {"ok": True}
        available = [8 * 1024 ** 3, 20 * 1024 ** 3]
        self.panel.autoscaler_host_memory = lambda: {
            "totalBytes": 64 * 1024 ** 3,
            "availableBytes": available.pop(0) if len(available) > 1 else available[0],
            "swapTotalBytes": 0, "swapFreeBytes": 0,
        }
        for name, value in originals.items():
            self.addCleanup(lambda name=name, value=value: setattr(self.panel, name, value))
        now = time.time()
        state = self.panel.read_autoscaler_state()
        state.update({
            "enabled": True, "retentionSeconds": 3600,
            "maxWarmDynamicMaps": 0, "minAvailableMemoryBytes": 16 * 1024 ** 3,
            "modes": {service: "dynamic" for service in services},
            "idleSince": {service: now - 10 for service in services},
            "lastActivity": {"arrakeen": now - 300, "harko-village": now - 100},
            "demand": {},
        })
        self.panel.write_autoscaler_state(state)

        self.panel.autoscaler_tick()

        self.assertEqual(actions, [("arrakeen", "stop")])
        self.assertEqual(self.panel.read_autoscaler_state()["lastEvictionReason"]["arrakeen"], "memory-pressure-lru")

    def test_discord_adapter_role_mapping_and_sanitization(self):
        old = {name: os.environ.get(name) for name in (
            "DISCORD_OBSERVER_ROLE_IDS", "DISCORD_MODERATOR_ROLE_IDS",
            "DISCORD_ADMIN_ROLE_IDS", "DISCORD_OWNER_ROLE_IDS",
        )}
        os.environ["DISCORD_OBSERVER_ROLE_IDS"] = "observer"
        os.environ["DISCORD_MODERATOR_ROLE_IDS"] = "moderator"
        self.addCleanup(lambda: [os.environ.pop(name, None) if value is None else os.environ.__setitem__(name, value) for name, value in old.items()])
        actor = {"guildId": "1", "channelId": "2", "userId": "3", "username": "tester", "roleIds": ["moderator"]}

        self.assertEqual(self.panel.discord_require_tier(actor, "observer"), "moderator")
        self.assertEqual(self.panel.discord_require_tier(actor, "moderator"), "moderator")
        with self.assertRaises(PermissionError):
            self.panel.discord_require_tier(dict(actor, roleIds=[]), "observer")
        sanitized = self.panel.discord_sanitize({"database": "dune", "apiToken": "secret", "nested": {"password": "secret"}})
        self.assertEqual(sanitized["apiToken"], "[redacted]")
        self.assertEqual(sanitized["nested"]["password"], "[redacted]")

    def test_discord_ops_domains_are_allowlisted_and_bounded(self):
        original_query = self.panel.query
        self.panel.query = lambda sql, params=None: [{"active_last_1h": 2, "active_last_24h": 5, "active_last_7d": 8}]
        self.addCleanup(lambda: setattr(self.panel, "query", original_query))
        self.assertEqual(self.panel.discord_ops_result("activity")["active_last_1h"], 2)
        dashboard = self.panel.discord_ops_result("dashboard")
        self.assertTrue(dashboard["private"])
        self.assertNotIn("url", dashboard)
        prometheus = self.panel.discord_ops_result("prometheus")
        self.assertTrue(prometheus["private"])
        with self.assertRaises(ValueError):
            self.panel.discord_ops_result("shell")

    def test_addon_manifest_permissions_and_paths_are_bounded(self):
        manifest = self.panel.addon_admin.normalize_manifest({
            "schemaVersion": 1, "id": "ops-addon", "name": "Ops", "version": "1.0.0",
            "type": "ui", "entry": {"path": "web/index.html"},
            "permissions": {"ops": ["read"]},
        })
        self.assertEqual(manifest["permissions"], ["ops:read"])
        self.assertEqual(manifest["entry"]["path"], "web/index.html")
        with self.assertRaises(ValueError):
            self.panel.addon_admin.normalize_manifest({
                "id": "bad-addon", "name": "Bad", "version": "1", "type": "ui",
                "entry": {"path": "../escape.html"}, "permissions": [],
            })
        with self.assertRaises(ValueError):
            self.panel.addon_admin.normalize_manifest({
                "id": "bad-addon", "name": "Bad", "version": "1", "type": "ui",
                "entry": {"path": "index.html"}, "permissions": ["shell:execute"],
            })

    def test_service_control_route_is_separately_gated_and_audited(self):
        original_control = self.panel.control_docker_service
        calls = []
        self.panel.control_docker_service = lambda service, action: calls.append((service, action)) or {"ok": True, "service": service, "action": action, "exitCode": 0, "postState": {"state": "running"}}
        self.addCleanup(lambda: setattr(self.panel, "control_docker_service", original_control))
        self.patch_flag("SERVICE_CONTROL_ENABLED", True)
        handler, captured = self.make_route_handler("/api/ops/services/control")
        handler.require_mutations = lambda: None
        original_validate = self.panel.validate_json_post
        original_parse = self.panel.parse_body
        self.panel.validate_json_post = lambda request_handler, **kwargs: None
        self.panel.parse_body = lambda request_handler, **kwargs: {"service": "survival", "action": "restart", "confirm": "CONTROL SERVICE"}
        self.addCleanup(lambda: setattr(self.panel, "validate_json_post", original_validate))
        self.addCleanup(lambda: setattr(self.panel, "parse_body", original_parse))
        handler.do_POST()
        self.assertEqual(captured["errors"], [])
        self.assertEqual(calls, [("survival", "restart")])
        self.assertEqual(captured["audits"][0]["action"], "service-control")

    def test_care_package_preview_targets_selected_player(self):
        self.panel.CARE_PACKAGES_FILE.write_text(json.dumps({
            "schemaVersion": 1,
            "packages": [{
                "id": "starter",
                "label": "Starter",
                "enabled": True,
                "oncePerAccount": True,
                "items": [{"template_id": "BasicBuildingTool", "stack_size": 1}],
                "currency": [{"currency_id": 1, "amount": 500}],
                "xp": [{"track_type": "Combat", "amount": 100}],
            }],
        }), encoding="utf-8")
        self.patch_db(lambda sql, params=None: [{
            "account_id": 10,
            "character_name": "Tester",
            "online_status": "Offline",
            "player_controller_id": 200,
            "player_pawn_id": 201,
        }] if "from dune.player_state" in sql else [])
        bundles = []
        self.handler.economy_bundle = lambda body: bundles.append(body) or {"ok": True, "dryRun": True, "plan": []}

        result = self.handler.care_package_grant({"package_id": "starter", "account_id": 10, "dry_run": True})

        self.assertTrue(result["eligible"])
        self.assertEqual(bundles[0]["items"][0]["account_id"], 10)
        self.assertEqual(bundles[0]["currency"][0]["player_controller_id"], 200)
        self.assertEqual(bundles[0]["xp"][0]["player_id"], 200)

    def test_care_package_execution_is_gated_backed_up_and_recorded(self):
        self.panel.CARE_PACKAGES_FILE.write_text(json.dumps({
            "schemaVersion": 1,
            "packages": [{
                "id": "manual",
                "enabled": True,
                "items": [{"template_id": "BasicBuildingTool", "stack_size": 1}],
                "currency": [],
                "xp": [],
            }],
        }), encoding="utf-8")
        self.patch_db(lambda sql, params=None: [{
            "account_id": 10,
            "character_name": "Tester",
            "online_status": "Offline",
            "player_controller_id": 200,
            "player_pawn_id": 201,
        }] if "from dune.player_state" in sql else [])
        self.patch_flag("CARE_PACKAGES_ENABLED", True)
        self.patch_flag("BUNDLE_MUTATIONS_ENABLED", True)
        self.handler.require_mutations = lambda: None
        calls = []
        self.handler.economy_bundle = lambda body: calls.append(body) or {"ok": True, "dryRun": body.get("dry_run"), "plan": []}
        original_backup = self.panel.create_db_backup
        self.panel.create_db_backup = lambda: {"path": "backup.dump", "bytes": 4}
        self.addCleanup(lambda: setattr(self.panel, "create_db_backup", original_backup))

        result = self.handler.care_package_grant({
            "package_id": "manual",
            "account_id": 10,
            "dry_run": False,
            "confirm": "GRANT CARE PACKAGE",
        })

        self.assertFalse(result["dryRun"])
        self.assertEqual(result["backup"]["path"], "backup.dump")
        self.assertEqual(calls[-1]["confirm"], "EXECUTE BUNDLE")
        history = self.panel.care_package_history()
        self.assertEqual(history[0]["packageId"], "manual")
        self.assertEqual(history[0]["accountId"], 10)

    def test_care_package_execution_refuses_disabled_package(self):
        self.panel.CARE_PACKAGES_FILE.write_text(json.dumps({
            "schemaVersion": 1,
            "packages": [{
                "id": "disabled",
                "enabled": False,
                "items": [{"template_id": "BasicBuildingTool", "stack_size": 1}],
                "currency": [],
                "xp": [],
            }],
        }), encoding="utf-8")
        self.patch_db(lambda sql, params=None: [{
            "account_id": 10,
            "character_name": "Tester",
            "online_status": "Offline",
            "player_controller_id": 200,
            "player_pawn_id": 201,
        }] if "from dune.player_state" in sql else [])
        self.patch_flag("CARE_PACKAGES_ENABLED", True)
        self.patch_flag("BUNDLE_MUTATIONS_ENABLED", True)
        self.handler.require_mutations = lambda: None
        self.handler.economy_bundle = lambda body: {"ok": True, "dryRun": True, "plan": []}

        with self.assertRaises(PermissionError):
            self.handler.care_package_grant({
                "package_id": "disabled",
                "account_id": 10,
                "dry_run": False,
                "confirm": "GRANT CARE PACKAGE",
            })

    def test_automatic_care_package_claim_prevents_duplicate_grant(self):
        self.panel.CARE_PACKAGES_FILE.write_text(json.dumps({
            "schemaVersion": 2,
            "automatic": {
                "enabled": True,
                "intervalSeconds": 60,
                "rules": [{
                    "id": "starter-first-online",
                    "enabled": True,
                    "packageId": "starter",
                    "grantWhen": "first_online",
                }],
            },
            "packages": [{
                "id": "starter",
                "enabled": True,
                "oncePerAccount": True,
                "items": [{"template_id": "BasicBuildingTool", "stack_size": 1}],
                "currency": [],
                "xp": [],
            }],
        }), encoding="utf-8")
        self.patch_db(lambda sql, params=None: [{
            "account_id": 10,
            "character_name": "Tester",
            "online_status": "Online",
            "player_controller_id": 200,
            "player_pawn_id": 201,
            "last_login_time": "2026-07-15T00:00:00+00:00",
        }] if "from dune.player_state" in sql else [])
        original_grant = self.panel.Handler.care_package_grant
        grants = []
        self.panel.Handler.care_package_grant = lambda handler, body: grants.append(body) or {
            "ok": True, "packageId": body["package_id"], "accountId": body["account_id"]
        }
        self.addCleanup(lambda: setattr(self.panel.Handler, "care_package_grant", original_grant))

        first = self.panel.care_package_auto_scan(dry_run=False)
        second = self.panel.care_package_auto_scan(dry_run=False)

        self.assertEqual(first["granted"], 1)
        self.assertEqual(second["granted"], 0)
        self.assertEqual(len(grants), 1)
        claims = json.loads(self.panel.CARE_PACKAGE_CLAIMS_FILE.read_text(encoding="utf-8"))
        self.assertIn("starter-first-online:starter:10", claims["claims"])

    def test_returning_player_is_persisted_pending_until_online(self):
        self.panel.CARE_PACKAGES_FILE.write_text(json.dumps({
            "schemaVersion": 2,
            "automatic": {
                "enabled": True,
                "intervalSeconds": 60,
                "rules": [{
                    "id": "returning",
                    "enabled": True,
                    "packageId": "return-kit",
                    "grantWhen": "last_seen",
                    "lastSeenDays": 30,
                }],
            },
            "packages": [{
                "id": "return-kit", "enabled": True, "oncePerAccount": True,
                "items": [], "currency": [{"currency_id": 1, "amount": 100}], "xp": [],
            }],
        }), encoding="utf-8")
        online = {"value": False}
        self.patch_db(lambda sql, params=None: [{
            "account_id": 10, "character_name": "Tester",
            "online_status": "Online" if online["value"] else "Offline",
            "player_controller_id": 200, "player_pawn_id": 201,
            "last_login_time": "2025-01-01T00:00:00+00:00",
        }] if "from dune.player_state" in sql else [])
        original_grant = self.panel.Handler.care_package_grant
        grants = []
        self.panel.Handler.care_package_grant = lambda handler, body: grants.append(body) or {"ok": True}
        self.addCleanup(lambda: setattr(self.panel.Handler, "care_package_grant", original_grant))

        offline_scan = self.panel.care_package_auto_scan(dry_run=False)
        online["value"] = True
        online_scan = self.panel.care_package_auto_scan(dry_run=False)

        self.assertEqual(offline_scan["pending"], 1)
        self.assertEqual(online_scan["granted"], 1)
        self.assertEqual(len(grants), 1)

    def test_native_player_command_contract_and_redaction(self):
        modules = self.panel.native_command_admin.load_catalog(ROOT / "config" / "admin-skill-modules.json")
        vehicles = self.panel.native_command_admin.load_catalog(ROOT / "config" / "admin-vehicles.json")
        skill, meta = self.panel.native_command_admin.build_inner(
            "skill-module", "FLS#123", {"module": modules[0]["id"], "level": 1}, modules, vehicles
        )
        self.assertEqual(skill["ServerCommand"], "SkillsSetModuleLevel")
        self.assertEqual(skill["PlayerId"], "FLS#123")
        self.assertEqual(meta["skillModule"]["id"], modules[0]["id"])
        spawned, _ = self.panel.native_command_admin.build_inner(
            "spawn-vehicle", "FLS#123",
            {"vehicle": vehicles[0]["id"], "x": 1, "y": 2, "z": 3, "rotation": 90},
            modules, vehicles,
        )
        self.assertEqual(spawned["ServerCommand"], "SpawnVehicleAt")
        self.assertEqual(spawned["Persistent"], 1.0)
        outer = self.panel.native_command_admin.build_outer("secret", spawned)
        self.assertEqual(outer["Version"], 2)
        self.assertEqual(outer["AuthToken"], "secret")
        preview = self.panel.native_command_admin.public_preview(outer)
        self.assertEqual(preview["AuthToken"], "<redacted>")
        self.assertNotIn("FLS#123", preview["MessageContent"])
        with self.assertRaises(ValueError):
            self.panel.native_command_admin.build_inner(
                "skill-points", "FLS#123", {"skill_points": 100001}, modules, vehicles
            )
        teleported, _ = self.panel.native_command_admin.build_inner(
            "teleport", "FLS#123", {"x": 1, "y": 2, "z": 3, "yaw": 90}, modules, vehicles
        )
        self.assertEqual(teleported["ServerCommand"], "TeleportTo")
        self.assertEqual(teleported["Yaw"], 90.0)
        self.assertEqual(
            self.panel.native_command_admin.build_inner("clean-inventory", "FLS#123", {}, modules, vehicles)[0]["ServerCommand"],
            "CleanPlayerInventory",
        )

    def test_native_notification_uses_game_rmq_heartbeats_notifications(self):
        original_service = self.panel.docker_service_container
        original_exec = self.panel.docker_container_exec
        old_token = os.environ.get("DUNE_SERVER_COMMANDS_AUTH_TOKEN")
        captured = {}
        self.panel.docker_service_container = lambda service, running=True: {"Id": "a" * 64}
        self.panel.docker_container_exec = lambda container, argv, timeout=20: captured.update(container=container, argv=argv) or {"ok": True, "exitCode": 0, "output": "publish=ok"}
        os.environ["DUNE_SERVER_COMMANDS_AUTH_TOKEN"] = "unit-test-token"
        self.addCleanup(lambda: setattr(self.panel, "docker_service_container", original_service))
        self.addCleanup(lambda: setattr(self.panel, "docker_container_exec", original_exec))
        self.addCleanup(lambda: os.environ.__setitem__("DUNE_SERVER_COMMANDS_AUTH_TOKEN", old_token) if old_token is not None else os.environ.pop("DUNE_SERVER_COMMANDS_AUTH_TOKEN", None))
        result = self.panel.publish_native_player_notification({"ServerCommand": "KickPlayer", "PlayerId": "*"})
        self.assertTrue(result["queued"])
        command = captured["argv"][2]
        self.assertIn('<<"heartbeats">>', command)
        self.assertIn('<<"notifications">>', command)
        self.assertNotIn("unit-test-token", command)

    def test_runtime_action_preview_resolves_funcom_id_without_publish(self):
        self.panel.ADMIN_SKILL_MODULES_FILE = ROOT / "config" / "admin-skill-modules.json"
        self.panel.ADMIN_VEHICLES_FILE = ROOT / "config" / "admin-vehicles.json"
        self.patch_db(lambda sql, params=None: [{
            "account_id": 10, "character_name": "Tester", "online_status": "Online",
            "player_controller_id": 20, "player_pawn_id": 21, "funcom_id": "FLS#123",
        }] if "join dune.accounts" in sql else [])
        original_publish = self.panel.publish_native_player_notification
        self.panel.publish_native_player_notification = lambda inner: (_ for _ in ()).throw(AssertionError("dry-run must not publish"))
        self.addCleanup(lambda: setattr(self.panel, "publish_native_player_notification", original_publish))
        result = self.handler.runtime_player_action({"action": "refill-water", "account_id": 10, "dry_run": True})
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["path"], "game-rmq:heartbeats/notifications")
        self.assertNotIn("FLS#123", json.dumps(result))

    def test_autoscaler_parses_director_travel_demand_once(self):
        line_a = "Processing travel queue for ClassicalInstancing group SH_Arrakeen (servers: [], num: 2)"
        line_b = "Received travel request for 1 player(s) to DeepDesert_1 (instancingMode=Dimension)"
        line_c = "Processing travel queue for DeepDesert_1 (02 PVE Hardcore, id=abc, dimension=1, partition=31, num=3)"
        events = self.panel.parse_director_travel_demand(f"{line_a}\n{line_a}\n{line_b}\n{line_c}\n")
        self.assertEqual(
            [(row["map"], row["count"]) for row in events],
            [("SH_Arrakeen", 2), ("DeepDesert_1", 1), ("DeepDesert_1", 3)],
        )
        self.assertEqual(len({row["id"] for row in events}), 3)

    def test_minimum_footprint_profile_keeps_only_core_always_on(self):
        original_inventory = self.panel.docker_service_inventory
        original_counts = self.panel.autoscaler_player_counts
        original_control = self.panel.autoscaler_service_action
        original_always_on = self.panel.AUTOSCALER_ALWAYS_ON_SERVICES
        self.panel.AUTOSCALER_ALWAYS_ON_SERVICES = {"survival", "overmap"}
        self.panel.docker_service_inventory = lambda: [
            {"service": "survival", "state": "running"},
            {"service": "overmap", "state": "running"},
            {"service": "arrakeen", "state": "running"},
        ]
        self.panel.autoscaler_player_counts = lambda: {}
        actions = []
        self.panel.autoscaler_service_action = lambda service, action: actions.append((service, action)) or {"ok": True}
        self.addCleanup(lambda: setattr(self.panel, "docker_service_inventory", original_inventory))
        self.addCleanup(lambda: setattr(self.panel, "autoscaler_player_counts", original_counts))
        self.addCleanup(lambda: setattr(self.panel, "autoscaler_service_action", original_control))
        self.addCleanup(lambda: setattr(self.panel, "AUTOSCALER_ALWAYS_ON_SERVICES", original_always_on))

        result = self.panel.autoscaler_control("minimum-footprint")
        state = self.panel.read_autoscaler_state()

        self.assertTrue(result["enabled"])
        self.assertEqual(state["modes"]["survival"], "always-on")
        self.assertEqual(state["modes"]["arrakeen"], "dynamic")
        self.assertEqual(actions, [])

    def test_backup_schedule_tick_creates_one_verified_backup(self):
        self.panel.BACKUP_SCHEDULE_FILE = self.workspace / "backups" / "admin-panel" / "backup-schedule.json"
        self.panel.configure_backup_schedule({"enabled": True, "time": "05:00", "interval_hours": 12, "retention_days": 0})
        state = self.panel.read_backup_schedule()
        state["nextRun"] = 100
        self.panel.write_backup_schedule(state)
        original_create = self.panel.create_full_backup
        calls = []
        self.panel.create_full_backup = lambda: calls.append(True) or {"ok": True, "path": "admin-panel/maintenance/test", "verification": {"ok": True}}
        self.addCleanup(lambda: setattr(self.panel, "create_full_backup", original_create))
        result = self.panel.backup_schedule_tick(now=200)
        second = self.panel.backup_schedule_tick(now=201)
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["lastResult"]["ok"])
        self.assertGreater(second["nextRun"], 201)

    def test_landsraad_reward_and_contribution_plans_preserve_rollback(self):
        def fake_query(sql, params=None):
            if "landsraad_load_current_term" in sql:
                return [{"term_id": 7, "end_time": "2026-07-22T00:00:00Z", "testterm": False}]
            if "landsraad_decree_term" in sql:
                return [{"term_id": 7}]
            if "from pg_proc" in sql:
                return []
            if "landsraad_task_rewards" in sql:
                return [{"task_id": 44, "threshold": 10, "template_id": "OldReward", "amount": 1}]
            if "from dune.player_state" in sql:
                return [{"account_id": 10, "player_controller_id": 200, "player_pawn_id": 201, "online_status": "Offline"}]
            if "from dune.player_faction" in sql:
                return [{"faction_id": 2}]
            if "landsraad_task_player_contributions" in sql:
                return [{"player_id": 200, "task_id": 44, "amount": 25}]
            return []

        self.patch_db(fake_query)
        reward = self.handler.landsraad_mutation({
            "action": "reward-tier", "task_id": 44, "threshold": 10,
            "new_threshold": 20, "template_id": "NewReward", "amount": 2,
            "dry_run": True,
        })
        contribution = self.handler.landsraad_mutation({
            "action": "player-contribution", "task_id": 44,
            "account_id": 10, "amount": 50, "dry_run": True,
        })
        self.assertEqual(reward["plan"]["rollback"]["new_threshold"], 10)
        self.assertEqual(reward["plan"]["rollback"]["template_id"], "OldReward")
        self.assertEqual(contribution["plan"]["rollback"]["amount"], 25)
        self.assertEqual(contribution["plan"]["factionId"], 2)

    def test_bootstrap_status_reports_secrets_only_as_configured_flags(self):
        original_read_env = self.panel.read_env
        original_socket = self.panel.DOCKER_SOCKET
        self.panel.read_env = lambda: {
            "DUNE_STEAM_SERVER_DIR": "/srv/dune", "DUNE_IMAGE_TAG": "1",
            "WORLD_NAME": "world", "WORLD_UNIQUE_NAME": "unique",
            "WORLD_REGION": "us", "EXTERNAL_ADDRESS": "example.test",
            "FLS_SECRET": "private-secret", "POSTGRES_DUNE_PASSWORD": "private-db",
            "DUNE_ADMIN_TOKEN": "private-admin",
        }
        self.panel.DOCKER_SOCKET = str(self.workspace / "missing-docker.sock")
        self.patch_db(lambda sql, params=None: [{"database": "dune_sb_1_4_0_0", "schema_ready": True}])
        self.addCleanup(lambda: setattr(self.panel, "read_env", original_read_env))
        self.addCleanup(lambda: setattr(self.panel, "DOCKER_SOCKET", original_socket))

        status = self.panel.bootstrap_status()

        rendered = json.dumps(status)
        self.assertTrue(status["ok"])
        self.assertNotIn("private-secret", rendered)
        self.assertNotIn("private-db", rendered)
        self.assertNotIn("private-admin", rendered)

    def test_player_maintenance_previews_gear_and_login_queue(self):
        def fake_query(sql, params=None):
            if "join dune.accounts" in sql:
                return [{"account_id": 10, "player_pawn_id": 201, "player_controller_id": 301, "online_status": "Offline", "character_name": "Tester", "funcom_id": "FLS#123"}]
            if "from dune.items" in sql:
                return [{"id": 1, "template_id": "Knife", "stats": {"FItemStackAndDurabilityStats": [{}, {"MaxDurability": 100, "CurrentDurability": 25, "DecayedDurability": 20}]}}]
            return []

        self.patch_db(fake_query)
        original_service = self.panel.docker_service_container
        original_exec = self.panel.docker_container_exec
        self.panel.docker_service_container = lambda service, running=True: {"Id": "a" * 64}
        self.panel.docker_container_exec = lambda container, argv, timeout=20: {"ok": True, "output": "FLS#123_queue\t0\t1\trunning\n"}
        self.addCleanup(lambda: setattr(self.panel, "docker_service_container", original_service))
        self.addCleanup(lambda: setattr(self.panel, "docker_container_exec", original_exec))

        gear = self.handler.player_maintenance_mutation({"action": "repair-gear", "account_id": 10, "dry_run": True})
        queue = self.handler.player_maintenance_mutation({"action": "repair-login-queue", "account_id": 10, "dry_run": True})

        self.assertEqual(gear["plan"]["repairable"][0]["target"], 100)
        self.assertTrue(queue["plan"]["exists"])
        self.assertEqual(queue["plan"]["queue"]["messages"], 1)

    def test_player_progression_maintenance_previews_intel_recipe_and_research(self):
        def fake_query(sql, params=None):
            if "join dune.accounts" in sql:
                return [{"account_id": 10, "player_pawn_id": 201, "online_status": "Offline", "character_name": "Tester", "funcom_id": "FLS#123"}]
            if "m_TechKnowledgePoints" in sql:
                return [{"value": 2700}]
            if "select exists" in sql:
                return [{"found": True}]
            if "m_KnownItemRecipes' as values" in sql:
                return [{"values": []}]
            if "m_TechKnowledgeData' as values" in sql:
                return [{"values": [{"ItemKey": "RCP_Test", "UnlockedState": "Available"}]}]
            return []
        self.patch_db(fake_query)

        intel = self.handler.player_maintenance_mutation({"action": "add-intel", "account_id": 10, "amount": 100, "dry_run": True})
        recipe = self.handler.player_maintenance_mutation({"action": "unlock-recipe", "account_id": 10, "key": "Test_Recipe", "dry_run": True})
        research = self.handler.player_maintenance_mutation({"action": "unlock-research", "account_id": 10, "key": "RCP_Test", "dry_run": True})

        self.assertEqual(intel["plan"]["newValue"], 2779)
        self.assertEqual(recipe["plan"]["key"], "Test_Recipe")
        self.assertEqual(research["plan"]["key"], "RCP_Test")
        self.assertEqual(research["plan"]["recipeId"], "Test")
        self.assertTrue(research["plan"]["recipeMaterialized"])
        self.assertEqual(research["confirm"], "WRITE PLAYER PROGRESSION")

    def test_player_progression_previews_specialization_and_all_keystones(self):
        def fake_query(sql, params=None):
            if "join dune.accounts" in sql:
                return [{"account_id": 10, "player_pawn_id": 201, "player_controller_id": 301, "online_status": "Offline", "character_name": "Tester", "funcom_id": "FLS#123"}]
            if "enum_range" in sql:
                return [{"found": True}]
            if "from dune.specialization_tracks" in sql:
                return [{"xp_amount": 100, "level": 2}]
            if "specialization_keystones_map" in sql:
                return [{"available": 20, "purchased": 3}]
            return []
        self.patch_db(fake_query)

        maximum = self.handler.player_maintenance_mutation({"action": "specialization-max", "account_id": 10, "track_type": "Combat", "dry_run": True})
        reset = self.handler.player_maintenance_mutation({"action": "specialization-reset", "account_id": 10, "track_type": "Combat", "dry_run": True})
        keystones = self.handler.player_maintenance_mutation({"action": "keystones-grant-all", "account_id": 10, "dry_run": True})

        self.assertEqual(maximum["plan"]["xp"], 44182)
        self.assertEqual(maximum["plan"]["level"], 100)
        self.assertEqual(reset["plan"]["xp"], 0)
        self.assertEqual(keystones["plan"]["available"], 20)

    def test_world_storage_items_are_bounded_to_selected_actor(self):
        calls = []
        def fake_query(sql, params=None):
            calls.append((sql, params))
            if "from dune.placeables" in sql:
                return [{"id": 88, "building_type": "GenericContainer_Placeable", "owner_entity_id": 2}]
            if "from dune.inventories" in sql:
                return [{"id": 99, "actor_id": 88}]
            if "from dune.items" in sql:
                return [{"id": 100, "inventory_id": 99, "template_id": "Water"}]
            return []
        self.patch_db(fake_query)

        result = self.panel.world_storage_items(88)

        self.assertEqual(result["actorId"], 88)
        self.assertTrue(result["readOnly"])
        self.assertEqual(result["items"][0]["template_id"], "Water")
        self.assertTrue(all(params == (88,) for _, params in calls))

    def test_community_delivery_uses_offline_grant_path_and_completes_receipt(self):
        config_path = self.workspace / "config" / "community-rewards.json"
        config_path.write_text((ROOT / "config" / "community-rewards.example.json").read_text(), encoding="utf-8")
        store = self.panel.community_rewards.Store(self.workspace / "backups" / "community.sqlite3", config_path)
        store.initialize()
        store.credit(42, 100, "manual", "test:seed")
        order = store.purchase(42, "starter-water", 1, "test:purchase")
        original_store = self.panel.COMMUNITY_STORE
        original_initialized = self.panel.COMMUNITY_STORE_INITIALIZED
        original_config = self.panel.COMMUNITY_REWARDS_FILE
        self.panel.COMMUNITY_STORE = store
        self.panel.COMMUNITY_STORE_INITIALIZED = True
        self.panel.COMMUNITY_REWARDS_FILE = config_path
        self.addCleanup(lambda: setattr(self.panel, "COMMUNITY_STORE", original_store))
        self.addCleanup(lambda: setattr(self.panel, "COMMUNITY_STORE_INITIALIZED", original_initialized))
        self.addCleanup(lambda: setattr(self.panel, "COMMUNITY_REWARDS_FILE", original_config))
        self.patch_flag("COMMUNITY_REWARDS_ENABLED", True)
        self.patch_flag("COMMUNITY_DELIVERY_ENABLED", True)
        self.patch_flag("MUTATIONS_ENABLED", True)
        self.patch_flag("ITEM_GRANTS_ENABLED", True)
        self.patch_db(lambda sql, params=None: [{"online_status": "Offline", "account_id": 42, "character_name": "Tester"}])

        class GrantAdapter:
            def __init__(self):
                self.calls = []

            def grant_item(self, body):
                self.calls.append(dict(body))
                return {"ok": True, "dry_run": bool(body["dry_run"]), "item_id": None if body["dry_run"] else 99}

        adapter = GrantAdapter()
        result = self.panel.community_delivery_tick(adapter)
        self.assertEqual("delivered", result["delivery"]["status"])
        self.assertEqual([True, False], [row["dry_run"] for row in adapter.calls])
        self.assertEqual("delivered", store.status(42)["purchases"][0]["status"])
        self.assertEqual(order["id"], store.status(42)["purchases"][0]["id"])

    def test_community_webhook_requires_fresh_hmac_and_is_idempotent(self):
        config_path = self.workspace / "config" / "community-rewards.json"
        config = json.loads((ROOT / "config" / "community-rewards.example.json").read_text())
        config["webhooks"]["vote"]["enabled"] = True
        config_path.write_text(json.dumps(config), encoding="utf-8")
        store = self.panel.community_rewards.Store(self.workspace / "backups" / "community-webhook.sqlite3", config_path)
        store.initialize()
        original_store = self.panel.COMMUNITY_STORE
        original_initialized = self.panel.COMMUNITY_STORE_INITIALIZED
        original_config = self.panel.COMMUNITY_REWARDS_FILE
        self.panel.COMMUNITY_STORE = store
        self.panel.COMMUNITY_STORE_INITIALIZED = True
        self.panel.COMMUNITY_REWARDS_FILE = config_path
        self.addCleanup(lambda: setattr(self.panel, "COMMUNITY_STORE", original_store))
        self.addCleanup(lambda: setattr(self.panel, "COMMUNITY_STORE_INITIALIZED", original_initialized))
        self.addCleanup(lambda: setattr(self.panel, "COMMUNITY_REWARDS_FILE", original_config))
        self.patch_flag("COMMUNITY_REWARDS_ENABLED", True)
        old_secret = os.environ.get("DUNE_COMMUNITY_VOTE_WEBHOOK_SECRET")
        os.environ["DUNE_COMMUNITY_VOTE_WEBHOOK_SECRET"] = "test-secret"
        self.addCleanup(lambda: os.environ.pop("DUNE_COMMUNITY_VOTE_WEBHOOK_SECRET", None) if old_secret is None else os.environ.__setitem__("DUNE_COMMUNITY_VOTE_WEBHOOK_SECRET", old_secret))
        payload = {"eventId": "vote-1", "duneAccountId": 42, "amount": 5}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(b"test-secret", timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()

        class Headers(dict):
            def get_all(self, key, default=None):
                return [self[key]] if key in self else (default or [])

        def request(sig):
            return types.SimpleNamespace(headers=Headers({"Content-Length": str(len(raw)), "Content-Type": "application/json", "X-DASH-Timestamp": timestamp, "X-DASH-Signature": sig}), rfile=io.BytesIO(raw))

        first = self.panel.community_webhook_request(request(signature), "vote")
        replay = self.panel.community_webhook_request(request(signature), "vote")
        self.assertFalse(first["idempotent"])
        self.assertTrue(replay["idempotent"])
        with self.assertRaises(PermissionError):
            self.panel.community_webhook_request(request("0" * 64), "vote")


if __name__ == "__main__":
    unittest.main()
