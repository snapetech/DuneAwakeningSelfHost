#!/usr/bin/env python3
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


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
        self.panel.validate_json_post = lambda request_handler: None
        self.panel.parse_body = lambda request_handler: body
        self.addCleanup(lambda: setattr(self.panel, "validate_json_post", original_validate))
        self.addCleanup(lambda: setattr(self.panel, "parse_body", original_parse))
        handler.do_POST()
        return captured

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


if __name__ == "__main__":
    unittest.main()
