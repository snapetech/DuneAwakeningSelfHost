#!/usr/bin/env python3

import json
import pathlib
import sqlite3
import stat
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import peer_watch


class PeerWatchTests(unittest.TestCase):
    def test_real_catalog_is_machine_readable_and_contains_current_dapdsm_pin(self):
        peers = peer_watch.parse_catalog(ROOT / "docs" / "ecosystem-feature-parity-audit.md")
        self.assertGreaterEqual(len(peers), 30)
        self.assertEqual(len(peers), len({row["id"].lower() for row in peers}))
        dapdsm = next(row for row in peers if row["id"] == "bsmr/dapdsm")
        self.assertEqual("900915eb35bb11708d85add4b86090709d34519c", dapdsm["pinned"])
        self.assertEqual("github", dapdsm["provider"])
        sponge = next(row for row in peers if row["id"] == "Sponge/Dune-Awakening-Server-Tools")
        self.assertEqual("forgejo", sponge["provider"])

    def test_catalog_rejects_unsupported_hosts_shapes_duplicates_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "audit.md"
            for body, message in (
                ("| [Bad](https://example.com/o/r) | `" + "a" * 40 + "` | x |", "allowlist"),
                ("| [Bad](https://github.com/o/r/extra) | `" + "a" * 40 + "` | x |", "owner and repository"),
                ("| [Bad](https://github.com/o/r) | `short-pin` | x |", "malformed"),
                ("\n".join(["| [One](https://github.com/o/r) | `" + "a" * 40 + "` | x |"] * 2), "duplicate"),
            ):
                source.write_text("## Peer catalogue\n\n" + body + "\n\n## End\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    peer_watch.parse_catalog(source)
            actual = root / "actual.md"
            actual.write_text("## Peer catalogue\n\n| [One](https://github.com/o/r) | `" + "a" * 40 + "` | x |\n\n## End\n", encoding="utf-8")
            source.unlink()
            source.symlink_to(actual)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                peer_watch.parse_catalog(source)

    def test_fetch_is_fixed_provider_api_bounded_and_token_scoped_to_github(self):
        calls = []
        def fetch(url, headers, timeout, maximum):
            calls.append((url, headers, timeout, maximum))
            return [{"sha": "b" * 40}] if "api.github.com" in url else [{"id": "c" * 40}]
        github = {"id": "owner/repo", "provider": "github", "pinned": "a" * 40}
        forgejo = {"id": "owner/repo", "provider": "forgejo", "pinned": "a" * 40}
        self.assertEqual("b" * 40, peer_watch.fetch_head(github, token="secret", timeout=999, fetch_json=fetch))
        self.assertEqual("c" * 40, peer_watch.fetch_head(forgejo, token="secret", fetch_json=fetch))
        self.assertEqual("https://api.github.com/repos/owner/repo/commits?per_page=1", calls[0][0])
        self.assertEqual("Bearer secret", calls[0][1]["Authorization"])
        self.assertNotIn("Authorization", calls[1][1])
        self.assertEqual("https://git.unityailab.com/api/v1/repos/owner/repo/commits?limit=1", calls[1][0])
        self.assertEqual(60, calls[0][2])
        self.assertEqual(peer_watch.MAX_RESPONSE_BYTES, calls[0][3])

    def test_collection_isolates_one_peer_failure(self):
        peers = [
            {"id": "a/one", "name": "One", "url": "https://github.com/a/one", "provider": "github", "pinned": "a" * 40},
            {"id": "b/two", "name": "Two", "url": "https://github.com/b/two", "provider": "github", "pinned": "b" * 40},
        ]
        def fetch(url, headers, timeout, maximum):
            if "/a/one/" in url:
                return [{"sha": "a" * 40}]
            raise OSError("isolated outage")
        rows = peer_watch.collect(peers, fetch_json=fetch, now=1000)
        self.assertEqual("current", rows[0]["state"])
        self.assertEqual("error", rows[1]["state"])
        self.assertIn("isolated outage", rows[1]["error"])

    def test_store_retains_drift_error_and_pin_update_transitions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "peer-watch" / "watch.sqlite3"
            store = peer_watch.Store(path, history_limit=100).initialize()
            peer = {"id": "owner/repo", "name": "Peer", "url": "https://github.com/owner/repo", "provider": "github", "pinned": "a" * 40}
            current = [{**peer, "head": "a" * 40, "state": "current", "error": None}]
            self.assertEqual(1, len(store.sync([peer], current, now=1000)["transitions"]))
            drift = [{**peer, "head": "b" * 40, "state": "drifted", "error": None}]
            self.assertEqual("drift-detected", store.sync([peer], drift, now=1100)["transitions"][0]["transition"])
            failed = [{**peer, "head": None, "state": "error", "error": "rate limited"}]
            self.assertEqual("collection-error", store.sync([peer], failed, now=1200)["transitions"][0]["transition"])
            updated_peer = {**peer, "pinned": "b" * 40}
            updated = [{**updated_peer, "head": "b" * 40, "state": "current", "error": None}]
            self.assertEqual("pin-updated", store.sync([updated_peer], updated, now=1300)["transitions"][0]["transition"])
            status = store.status(now=1301)
            self.assertTrue(status["ok"])
            self.assertTrue(peer_watch.verify_database(path)["ok"])
            self.assertEqual({"total": 1, "current": 1, "drifted": 0, "error": 0, "transitions": 4}, status["summary"])
            self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
            metrics = store.prometheus(enabled=True, worker_running=True, stale_after_seconds=10, now=1301)
            self.assertIn("dash_peer_watch_current 1", metrics)
            self.assertIn("dash_peer_watch_collector_up 1", metrics)
            self.assertNotIn("{", metrics)
            connection = sqlite3.connect(path)
            connection.execute("update peers set state='drifted',head=pinned")
            connection.commit()
            connection.close()
            self.assertFalse(peer_watch.verify_database(path)["ok"])

    def test_store_rejects_mismatched_observation_set_and_records_total_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = peer_watch.Store(pathlib.Path(directory) / "watch.sqlite3").initialize()
            peer = {"id": "owner/repo", "name": "Peer", "url": "https://github.com/owner/repo", "provider": "github", "pinned": "a" * 40}
            with self.assertRaisesRegex(ValueError, "exactly match"):
                store.sync([peer], [], now=100)
            store.record_poll_error("catalog unreadable", now=200)
            status = store.status(now=201)
            self.assertFalse(status["ok"])
            self.assertFalse(peer_watch.verify_database(store.database)["ok"])
            self.assertEqual(1, status["collector"]["consecutiveFailures"])
            self.assertIn("catalog unreadable", status["collector"]["lastError"])

    def test_limited_status_keeps_global_summary_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = peer_watch.Store(pathlib.Path(directory) / "watch.sqlite3").initialize()
            peers = [
                {"id": f"owner/repo-{index}", "name": f"Peer {index}", "url": f"https://github.com/owner/repo-{index}", "provider": "github", "pinned": "a" * 40}
                for index in range(3)
            ]
            observations = [
                {**peer, "head": "a" * 40 if index < 2 else "b" * 40, "state": "current" if index < 2 else "drifted", "error": None}
                for index, peer in enumerate(peers)
            ]
            store.sync(peers, observations, now=1000)
            status = store.status(limit=1, now=1001)
            self.assertEqual(1, len(status["peers"]))
            self.assertEqual({"total": 3, "current": 2, "drifted": 1, "error": 0, "transitions": 3}, status["summary"])

    def test_repository_wiring_includes_metrics_alerts_readiness_backup_and_restore(self):
        panel = (ROOT / "admin" / "admin_panel.py").read_text(encoding="utf-8")
        rules = (ROOT / "config" / "metrics" / "rules" / "dash.yml").read_text(encoding="utf-8")
        readiness = json.loads((ROOT / "config" / "feature-readiness.json").read_text(encoding="utf-8"))
        backup = (ROOT / "scripts" / "backup-state.sh").read_text(encoding="utf-8")
        restore = (ROOT / "scripts" / "restore-state.sh").read_text(encoding="utf-8")
        assurance = (ROOT / "scripts" / "deployment-assurance.py").read_text(encoding="utf-8")
        assured_push = (ROOT / "scripts" / "push-assured-control-plane.sh").read_text(encoding="utf-8")
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        feature = next(row for row in readiness["features"] if row["id"] == "peer-watch")
        self.assertEqual(["DUNE_PEER_WATCH_ENABLED"], feature["gates"])
        self.assertEqual("peer-watch", feature["probe"])
        self.assertEqual([], feature["dependencies"])
        for metric in ("dash_peer_watch_collector_up", "dash_peer_watch_drifted", "dash_peer_watch_errors"):
            self.assertIn(metric, panel)
            self.assertIn(metric, rules)
        for alert in ("DashPeerWatchCollectorInvalid", "DashPeerRevisionDrift", "DashPeerWatchSourceErrors"):
            self.assertIn(alert, rules)
        for source in (backup, restore):
            self.assertIn("peer-watch.sqlite3", source)
        self.assertIn("--peer-watch", restore)
        self.assertIn('"admin/peer_watch.py"', assurance)
        self.assertIn('"docs/ecosystem-feature-parity-audit.md"', assurance)
        self.assertIn("admin/peer_watch.py", assured_push)
        self.assertIn("/source-workspace/docs/ecosystem-feature-parity-audit.md", compose)


if __name__ == "__main__":
    unittest.main()
