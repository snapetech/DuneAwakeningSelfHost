#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-ue4ss-package-live-preflight-summary.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_live_preflight_summary", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def runbook(path):
    return {
        "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
        "sourcePath": str(path),
        "remote": "kspls0",
        "container": "dune_server-deep-desert-1",
        "traceLog": "/tmp/trace.log",
        "operatorWindow": {"maxArmSeconds": 120, "cleanupRequired": True},
    }


def runbook_with_route(path):
    payload = runbook(path)
    payload["traceInputs"] = {"routeAddress": "0x129d58a2"}
    payload["traceEnv"] = {"DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS": "0x129d58a2"}
    payload["cleanupCommand"] = (
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2 "
        "scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/trace.log"
    )
    return payload


def next_action():
    return {
        "schemaVersion": "dune-ue4ss-package-next-action/v1",
        "action": "recover-package-anchor",
        "liveTraceRunbook": {
            "remote": "kspls0",
            "container": "dune_server-deep-desert-1",
        },
    }


def summary(runbook_path):
    return {
        "schemaVersion": "dune-ue4ss-package-live-preflight-summary/v1",
        "createdUtc": "2026-06-24T00:40:40Z",
        "runbook": str(runbook_path),
        "sourceRunbook": str(runbook_path),
        "traceLogOverride": "",
        "traceRemote": "kspls0",
        "container": "dune_server-deep-desert-1",
        "traceLog": "/tmp/trace.log",
        "operatorWindowSeconds": 30,
        "ready": True,
        "blockers": [],
        "fields": {
            "remote_host": "kspls0",
            "player_guard_preflight_partition": "8",
            "player_guard_preflight_connected_players": "0",
            "preflight": "ok",
            "container": "dune_server-deep-desert-1",
            "server_pid": "2477302",
            "server_state": "S",
            "trace_log": "/tmp/trace.log",
            "route_address": "",
            "gdb_bin": "/usr/bin/gdb",
            "ptrace_scope": "1",
        },
    }


class VerifyLivePreflightSummaryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_missing_summary_reports_structured_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = self.module.report(root / "missing.json")
            rendered = self.module.markdown(report)

        self.assertFalse(report["ready"])
        self.assertEqual(report["blockers"], ["preflight summary JSON is missing"])
        self.assertIn("preflight summary JSON is missing", rendered)

    def test_malformed_summary_reports_structured_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "summary.json"
            path.write_text("{", encoding="utf-8")
            report = self.module.report(path)

        self.assertFalse(report["ready"])
        self.assertTrue(any(item.startswith("preflight summary JSON is unreadable:") for item in report["blockers"]))

    def test_valid_summary_matches_runbook_and_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            next_action_path = root / "next-action.json"
            summary_path = root / "preflight-summary.json"
            write_json(runbook_path, runbook(runbook_path))
            write_json(next_action_path, next_action())
            write_json(summary_path, summary(runbook_path))
            report = self.module.report(summary_path, runbook_path, next_action_path)

        self.assertTrue(report["ready"], report["blockers"])
        self.assertEqual(report["blockers"], [])

    def test_valid_override_summary_uses_effective_runbook_and_source_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_runbook = root / "runbook.json"
            effective_runbook = root / "effective-runbook.json"
            summary_path = root / "preflight-summary.json"
            rb = runbook(source_runbook)
            rb["traceLog"] = "/tmp/override.log"
            write_json(source_runbook, runbook(source_runbook))
            payload = summary(source_runbook)
            payload.update(
                {
                    "runbook": str(effective_runbook),
                    "traceLogOverride": "/tmp/override.log",
                    "traceLog": "/tmp/override.log",
                }
            )
            payload["fields"]["trace_log"] = "/tmp/override.log"
            write_json(summary_path, payload)
            report = self.module.report(summary_path, source_runbook)

        self.assertTrue(report["ready"], report["blockers"])

    def test_rejects_stale_zero_player_guard_and_trace_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "preflight-summary.json"
            payload = summary(runbook_path)
            payload["fields"]["player_guard_preflight_connected_players"] = "1"
            payload["fields"]["trace_log"] = "/tmp/stale.log"
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary player_guard_preflight_connected_players must be 0", report["blockers"])
        self.assertIn("summary fields.trace_log does not match traceLog", report["blockers"])

    def test_rejects_runbook_missing_required_route_address_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "preflight-summary.json"
            payload = runbook_with_route(runbook_path)
            payload["traceEnv"] = {}
            write_json(runbook_path, payload)
            write_json(summary_path, summary(runbook_path))
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn("runbook traceEnv route address does not match traceInputs routeAddress", report["blockers"])

    def test_requires_preflight_route_address_when_runbook_requires_route_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "preflight-summary.json"
            write_json(runbook_path, runbook_with_route(runbook_path))
            payload = summary(runbook_path)
            payload["fields"]["route_address"] = ""
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path)

        self.assertFalse(report["ready"])
        self.assertIn(
            "summary fields.route_address does not match runbook traceInputs routeAddress",
            report["blockers"],
        )

    def test_rejects_ready_summary_with_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "preflight-summary.json"
            payload = summary(root / "runbook.json")
            payload["blockers"] = ["preflight did not report ok"]
            write_json(summary_path, payload)
            report = self.module.report(summary_path)

        self.assertFalse(report["ready"])
        self.assertIn("summary ready must not be true when blockers are present", report["blockers"])

    def test_rejects_stale_preflight_when_max_age_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "preflight-summary.json"
            payload = summary(runbook_path)
            payload["createdUtc"] = "2026-06-24T00:00:00Z"
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path, max_age_seconds=60)

        self.assertFalse(report["ready"])
        self.assertTrue(
            any(blocker.startswith("summary createdUtc is stale:") for blocker in report["blockers"]),
            report["blockers"],
        )

    def test_accepts_recent_preflight_when_max_age_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook_path = root / "runbook.json"
            summary_path = root / "preflight-summary.json"
            payload = summary(runbook_path)
            payload["createdUtc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            write_json(runbook_path, runbook(runbook_path))
            write_json(summary_path, payload)
            report = self.module.report(summary_path, runbook_path, max_age_seconds=3600)

        self.assertTrue(report["ready"], report["blockers"])


if __name__ == "__main__":
    unittest.main()
