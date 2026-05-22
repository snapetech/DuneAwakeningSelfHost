#!/usr/bin/env python3
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(args, input_text=None):
    return subprocess.run(args, cwd=ROOT, input=input_text, text=True, capture_output=True, check=True)


class DiscoveryToolsTest(unittest.TestCase):
    def test_surface_jsonl_validates(self):
        result = run(["python3", "scripts/generate-surface-docs.py", "--validate"])
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["surfaces"], 1)

    def test_discovery_queue_buckets_candidates(self):
        result = run(["python3", "scripts/generate-discovery-queue.py"])
        self.assertIn("needs-startup-parse-test", result.stdout)
        self.assertIn("ready-or-promoted", result.stdout)

    def test_binary_candidate_scoring_prioritizes_key_companions(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("WBP_MenuWidget\nm_CrashSitePriorityOverrides_Key\nm_TreasureSpawnRateMinMax\n")
            path = pathlib.Path(handle.name)
        try:
            result = run(["python3", "scripts/score-binary-candidates.py", str(path)])
            payload = json.loads(result.stdout)
            strings = [row["string"] for row in payload["candidates"]]
            self.assertLess(strings.index("m_CrashSitePriorityOverrides_Key"), strings.index("WBP_MenuWidget"))
        finally:
            path.unlink(missing_ok=True)

    def test_db_classifier_marks_dangerous_write(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            json.dump({"functions": [{"schema": "dune", "name": "delete_all_static_shifting_sand", "args": "", "returns": "void"}]}, handle)
            path = pathlib.Path(handle.name)
        try:
            result = run(["python3", "scripts/classify-db-functions.py", str(path)])
            payload = json.loads(result.stdout)
            self.assertIn("dangerous", payload["functions"][0]["classes"])
            self.assertIn("state-write", payload["functions"][0]["classes"])
        finally:
            path.unlink(missing_ok=True)

    def test_asset_reference_graph_extracts_game_paths(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("[/Script/DuneSandbox.TravelDestinationSubsystem]\nDest=/Game/Dune/DA_TravelDestinations.DA_TravelDestinations\n")
            path = pathlib.Path(handle.name)
        try:
            result = run(["python3", "scripts/build-asset-reference-graph.py", str(path)])
            payload = json.loads(result.stdout)
            self.assertTrue(any(edge["target"].startswith("/Game/Dune/DA_TravelDestinations") for edge in payload["edges"]))
        finally:
            path.unlink(missing_ok=True)

    def test_fixture_catalogs_are_valid_json_with_ids(self):
        fixtures = sorted((ROOT / "fixtures").glob("*.json"))
        self.assertGreaterEqual(len(fixtures), 5)
        for path in fixtures:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("id", data)
            self.assertIn("before", data)
            self.assertIn("after", data)

    def test_experiment_catalogs_are_valid_json_with_observation(self):
        catalogs = sorted((ROOT / "experiments" / "catalog").glob("*.json"))
        self.assertGreaterEqual(len(catalogs), 1)
        for path in catalogs:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("id", data)
            self.assertIn("config", data)
            self.assertIn("observe", data)

    def test_rmq_capture_diff_reports_added_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            before = tmp_path / "before.json"
            after = tmp_path / "after.json"
            before.write_text(json.dumps({"queues": [], "exchanges": [], "bindings": [], "consumers": []}), encoding="utf-8")
            after.write_text(json.dumps({"queues": [{"vhost": "/", "name": "q1"}], "exchanges": [], "bindings": [], "consumers": []}), encoding="utf-8")
            result = run(["python3", "scripts/diff-rmq-captures.py", str(before), str(after), "--format", "json"])
            payload = json.loads(result.stdout)
            self.assertEqual("q1", payload["diff"]["queues"]["added"][0]["name"])

    def test_game_rmq_snapshot_prefers_management_credentials(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(
                "\n".join([
                    "DUNE_ANNOUNCE_RMQ_USER=management-user",
                    "DUNE_ANNOUNCE_RMQ_PASSWORD=management-password",
                    "DUNE_ANNOUNCE_CHAT_USER=chat-user",
                    "DUNE_ANNOUNCE_CHAT_PASSWORD=chat-password",
                ])
            )
            path = pathlib.Path(handle.name)
        try:
            source = (ROOT / "scripts" / "research" / "snapshot-rmq-topology.py").read_text(encoding="utf-8")
            self.assertIn('env("DUNE_ANNOUNCE_RMQ_USER"', source)
            self.assertIn('env("DUNE_ANNOUNCE_RMQ_PASSWORD"', source)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
