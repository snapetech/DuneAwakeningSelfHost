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
        (self.workspace / ".env").write_text("", encoding="utf-8")
        self.panel = load_admin_panel(self.workspace)

    def tearDown(self):
        self.tmp.cleanup()

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
        self.assertIn("party-account-lifecycle-functions", by_id)
        self.assertEqual(by_id["recipe-vehicle-function-discovery"]["mutationRisk"], "blocked")

    def test_typed_knob_validation_and_backup_write(self):
        self.assertEqual(self.panel.validate_typed_knob_value("globalMiningMultiplier", "2.5"), "2.5")
        self.assertEqual(self.panel.validate_typed_knob_value("sandstormEnabled", "false"), "0")
        with self.assertRaises(ValueError):
            self.panel.validate_typed_knob_value("buildingShelterThreshold", "2")

        result = self.panel.write_typed_knobs({
            "globalMiningMultiplier": "2.5",
            "sandstormEnabled": "false",
            "forcePvpAllPartitions": "true",
        })
        self.assertTrue(result["ok"])
        self.assertTrue(result["restartRequired"])
        engine = (self.workspace / "config" / "UserEngine.ini").read_text(encoding="utf-8")
        game = (self.workspace / "config" / "UserGame.ini").read_text(encoding="utf-8")
        self.assertIn("Dune.GlobalMiningOutputMultiplier=2.5", engine)
        self.assertIn("Sandstorm.Enabled=0", engine)
        self.assertIn("m_bShouldForceEnablePvpOnAllPartitions=True", game)
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


if __name__ == "__main__":
    unittest.main()
