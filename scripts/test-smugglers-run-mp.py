#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import tempfile
import types
import unittest


SCRIPT_PATH = pathlib.Path(__file__).with_name("smugglers-run-mp.py")


def load_module(capture_root):
    os.environ["DUNE_SMUGGLERS_RUN_CAPTURE_ROOT"] = str(capture_root)
    spec = importlib.util.spec_from_file_location("smugglers_run_mp", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmugglersRunMpTests(unittest.TestCase):
    def test_compare_snapshots_flags_recovered_vehicle_growth(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = load_module(pathlib.Path(tmp))
            before = {
                "vehicleCounts": {"rows": [
                    {"table_name": "vehicles", "count": 2},
                    {"table_name": "recovered_vehicles", "count": 0},
                ]},
                "playerVehicles": {"rows": [
                    {"character_name": "RacerOne", "out_actor_id": 10},
                ]},
            }
            after = {
                "vehicleCounts": {"rows": [
                    {"table_name": "vehicles", "count": 2},
                    {"table_name": "recovered_vehicles", "count": 1},
                ]},
                "playerVehicles": {"rows": [
                    {"character_name": "RacerOne", "out_actor_id": 10},
                ]},
            }

            comparison = module.compare_snapshots(before, after)

            self.assertFalse(comparison["ownedVehicleSafetyPass"])
            self.assertIn("recovered_vehicles increased by 1", comparison["warnings"])

    def test_compare_snapshots_flags_player_vehicle_row_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = load_module(pathlib.Path(tmp))
            before = {
                "vehicleCounts": {"rows": [{"table_name": "recovered_vehicles", "count": 0}]},
                "playerVehicles": {"rows": [{"character_name": "RacerOne", "out_actor_id": 10}]},
            }
            after = {
                "vehicleCounts": {"rows": [{"table_name": "recovered_vehicles", "count": 0}]},
                "playerVehicles": {"rows": [{"character_name": "RacerOne", "out_actor_id": 11}]},
            }

            comparison = module.compare_snapshots(before, after)

            self.assertFalse(comparison["ownedVehicleSafetyPass"])
            self.assertIn("player vehicle rows changed for RacerOne", comparison["warnings"])

    def test_loaner_command_is_preview_only_without_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = load_module(pathlib.Path(tmp))
            session = {
                "sessionId": "race-test",
                "entrants": ["RacerOne"],
                "events": [],
                "snapshots": {},
                "results": [],
            }
            module.write_session(session)
            args = types.SimpleNamespace(
                session_id="race-test",
                entrant=[],
                template="Sandbike_Test_Template",
                extra_args=[],
                route="",
                admin_player="DASH",
                transport="amqp",
                execute=False,
                allow_unsafe_gm=False,
                scope="lab",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                module.command_loaner(args)
            result = json.loads(output.getvalue())

            self.assertFalse(result["ok"])
            self.assertTrue(result["results"][0]["blocked"])
            self.assertEqual(result["results"][0]["preview"]["commandText"], "SpawnVehicle Sandbike_Test_Template")
            self.assertEqual(result["results"][0]["preview"]["route"], "CB_Overland_S_0626")


if __name__ == "__main__":
    unittest.main()
