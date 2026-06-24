#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-ue4ss-package-live-stimulus-trace.sh"
SUMMARY_VERIFIER = ROOT / "scripts" / "verify-ue4ss-package-live-stimulus-summary.py"


def write_runbook(path, max_seconds=2):
    path.write_text(
        json.dumps(
            {
                "remote": "not-a-real-host",
                "container": "dune_server-deep-desert-1",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log",
                "operatorWindow": {
                    "cleanupRequired": True,
                    "maxArmSeconds": max_seconds,
                    "sequence": [
                        "preflight",
                        "arm",
                        "operator-client-login-travel-map-entry",
                        "status",
                        "cleanupCommand",
                        "no-debugger-check",
                    ],
                },
                "traceEnv": {
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS": "false",
                },
                "originClassification": {
                    "status": "unknown",
                    "probeCandidate": "operator-client-map-entry",
                    "serverSideFallbackCandidate": "server-side-client-call-emulation",
                    "decision": "trace first; replay/spoof server-side if client-originated",
                },
                "cleanupCommand": "printf cleanup-command\\n",
                "noDebuggerCheckCommand": "printf no-debugger-command\\n",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def write_fake_prearm_verifier(scripts):
    verifier = scripts / "verify-ue4ss-package-prearm-readiness.py"
    verifier.write_text(
        "#!/usr/bin/env python3\n"
        "print('{\"schemaVersion\":\"dune-ue4ss-package-prearm-readiness/v1\",\"ready\":true,\"blockers\":[]}')\n",
        encoding="utf-8",
    )
    verifier.chmod(0o755)


class LiveStimulusTraceRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_runner_is_bounded_and_cleanup_guarded(self):
        self.assertIn("operatorWindow.maxArmSeconds", self.source)
        self.assertIn("--dry-run|--describe", self.source)
        self.assertIn("coordinator_dry_run=", self.source)
        self.assertIn("--preflight-only", self.source)
        self.assertIn("coordinator_preflight_only=", self.source)
        self.assertIn("preflight_only=done", self.source)
        self.assertIn("ue4ss-package-live-preflight-summary.json", self.source)
        self.assertIn("dune-ue4ss-package-live-preflight-summary/v1", self.source)
        self.assertIn("preflight_summary_ready=", self.source)
        self.assertIn("write_preflight_summary_from_output", self.source)
        self.assertIn("refusing to arm", self.source)
        self.assertIn("prearm_readiness_ready=", self.source)
        self.assertIn("verify-ue4ss-package-prearm-readiness.py", self.source)
        self.assertIn("preflight_command=", self.source)
        self.assertIn("wait_seconds > max_arm_seconds", self.source)
        self.assertIn("trap cleanup EXIT", self.source)
        self.assertIn("cleanupCommand", self.source)
        self.assertIn("noDebuggerCheckCommand", self.source)
        self.assertIn("operator_instruction=perform client login/travel/map-entry", self.source)
        self.assertIn("ue4ss-package-remote-trace.sh\" preflight", self.source)
        self.assertIn("ue4ss-package-remote-trace.sh\" arm", self.source)
        self.assertIn("ue4ss-package-remote-trace.sh\" status", self.source)
        self.assertIn("print_review_verification_summary", self.source)
        self.assertIn("review_bundle_ready=", self.source)
        self.assertIn("review_bundle_blocker=", self.source)
        self.assertIn("route_slot_recovery_verify_json=", self.source)
        self.assertIn("route_slot_recovery_ready=", self.source)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=$route_address", self.source)
        self.assertIn("runbook traceEnv must export DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS", self.source)
        self.assertIn("runbook cleanupCommand must include DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS", self.source)
        self.assertIn('"routeSlotRecoveryVerification"', self.source)
        self.assertIn('"routeSlotRecoveryVerificationSha256"', self.source)
        self.assertIn('"prearmReadinessVerification"', self.source)
        self.assertIn('"prearmReadinessVerificationSha256"', self.source)
        self.assertIn('"originClassification"', self.source)
        self.assertIn("origin_classification_status=", self.source)
        self.assertIn("client_gate_requires_server_side_replay=true", self.source)
        self.assertIn("--trace-log", self.source)
        self.assertIn('"sourceRunbook"', self.source)
        self.assertIn('"traceLogOverride"', self.source)
        self.assertIn("verify-ue4ss-package-live-stimulus-summary.py", self.source)
        self.assertIn("local_review_summary_verification_command=", self.source)
        self.assertIn("local_review_summary_ready=", self.source)
        self.assertIn("print_route_slot_trace_requirement", self.source)
        self.assertIn("route_slot_expected_trace_marker", self.source)
        self.assertIn("route_slot_required_slots", self.source)
        self.assertIn("route_slot_required_registers", self.source)

    def test_runner_rejects_wait_longer_than_runbook_window_before_remote_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=2)
            proc = subprocess.run(
                ["bash", str(SCRIPT), "3"],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_STIMULUS_RUNBOOK": str(runbook),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("exceeds runbook maxArmSeconds", proc.stderr)
        self.assertNotIn("operator_stimulus_window=begin", proc.stdout)

    def test_dry_run_validates_runbook_and_prints_commands_without_remote_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["traceInputs"] = {"routeAddress": "0x129d58a2"}
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS"] = "0x129d58a2"
            payload["cleanupCommand"] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2 "
                "scripts/ue4ss-package-remote-trace.sh stop not-a-real-host dune_server-deep-desert-1 "
                "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log"
            )
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            fake_bin = Path(tmp) / "bin"
            fake_bin.mkdir()
            fake_ssh = fake_bin / "ssh"
            fake_ssh.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
            fake_ssh.chmod(0o755)
            proc = subprocess.run(
                ["bash", str(SCRIPT), "--dry-run", "--wait", "30", "--runbook", str(runbook)],
                env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("coordinator_dry_run=1", proc.stdout)
        self.assertIn("operator_window_seconds=30", proc.stdout)
        self.assertIn("preflight_command=", proc.stdout)
        self.assertIn("arm_command=", proc.stdout)
        self.assertIn("status_command=", proc.stdout)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2", proc.stdout)
        self.assertIn("cleanup_command=DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2", proc.stdout)
        self.assertIn("review_bundle_summary_json=", proc.stdout)
        self.assertIn("preflight_summary_json=", proc.stdout)
        self.assertIn("local_review_summary_verification_command=", proc.stdout)
        self.assertIn("verify-ue4ss-package-live-stimulus-summary.py", proc.stdout)
        self.assertNotIn("operator_stimulus_window=begin", proc.stdout)
        self.assertEqual(proc.stderr, "")

    def test_dry_run_quotes_local_summary_verifier_command_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            summary_json = Path(tmp) / "review summary.json"
            proc = subprocess.run(
                ["bash", str(SCRIPT), "--dry-run", "--wait", "30", "--runbook", str(runbook)],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_STIMULUS_REVIEW_SUMMARY_JSON": str(summary_json),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("local_review_summary_verification_command=", proc.stdout)
        self.assertIn(r"review\ summary.json", proc.stdout)

    def test_dry_run_prints_route_slot_trace_requirement_from_prearm_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["traceInputs"] = {"routeAddress": "0x129d58a2"}
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS"] = "0x129d58a2"
            payload["cleanupCommand"] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2 "
                "scripts/ue4ss-package-remote-trace.sh stop not-a-real-host dune_server-deep-desert-1 "
                "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log"
            )
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            prearm = Path(tmp) / "prearm.json"
            prearm.write_text(
                json.dumps(
                    {
                        "completionAuditNextRouteSlotTraceRequirement": {
                            "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                            "routeAddress": "0x129d58a2",
                            "reviewField": "routeVtableStaticSlotMatches",
                            "requiredSlots": ["0x3a0", "0x3d8"],
                            "missingSlots": ["0x3a0", "0x3d8"],
                            "requiredRegisters": ["rbx", "r14"],
                            "missingRegisters": ["r14", "rbx"],
                        }
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["bash", str(SCRIPT), "--dry-run", "--wait", "30", "--runbook", str(runbook)],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_STIMULUS_PREARM_READINESS_JSON": str(prearm),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("route_slot_expected_trace_marker=UE4SS_PACKAGE_ROUTE_TRACE_HIT", proc.stdout)
        self.assertIn("route_slot_route_address=0x129d58a2", proc.stdout)
        self.assertIn("route_slot_review_field=routeVtableStaticSlotMatches", proc.stdout)
        self.assertIn("route_slot_required_slots=0x3a0,0x3d8", proc.stdout)
        self.assertIn("route_slot_missing_slots=0x3a0,0x3d8", proc.stdout)
        self.assertIn("route_slot_required_registers=rbx,r14", proc.stdout)
        self.assertIn("route_slot_missing_registers=r14,rbx", proc.stdout)

    def test_trace_log_override_updates_dry_run_commands_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["cleanupCommand"] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject "
                "scripts/ue4ss-package-remote-trace.sh stop not-a-real-host dune_server-deep-desert-1 "
                "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log"
            )
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            override_log = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T235959Z.log"
            proc = subprocess.run(
                [
                    "bash",
                    str(SCRIPT),
                    "--dry-run",
                    "--wait",
                    "30",
                    "--runbook",
                    str(runbook),
                    "--trace-log",
                    override_log,
                ],
                env={"PATH": "/usr/bin:/bin"},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"source_runbook={runbook}", proc.stdout)
        self.assertIn(f"trace_log={override_log}", proc.stdout)
        self.assertNotIn(f"--runbook-json {runbook}", proc.stdout)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON=", proc.stdout)
        self.assertIn(f"{ROOT}/scripts/ue4ss-package-remote-trace.sh preflight not-a-real-host dune_server-deep-desert-1 {override_log}", proc.stdout)
        self.assertIn(f"{ROOT}/scripts/ue4ss-package-remote-trace.sh status not-a-real-host dune_server-deep-desert-1 {override_log}", proc.stdout)
        self.assertIn(
            "cleanup_command=DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject "
            f"scripts/ue4ss-package-remote-trace.sh stop not-a-real-host dune_server-deep-desert-1 {override_log}",
            proc.stdout,
        )
        self.assertNotIn("20260623T213923Z.log", proc.stdout)

    def test_dry_run_preserves_explicit_trace_env_over_runbook_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY"] = "LoadPackage"
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR"] = "LoadPackage,LoadObject"
            payload["cleanupCommand"] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject "
                "scripts/ue4ss-package-remote-trace.sh stop not-a-real-host dune_server-deep-desert-1 "
                "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log"
            )
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            proc = subprocess.run(
                ["bash", str(SCRIPT), "--dry-run", "--wait", "30", "--runbook", str(runbook)],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR": "LoadObject",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SEED_ADDRESS": "0x1268545,0x59afafa",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY": "LoadObject",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT": "2",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadObject", proc.stdout)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SEED_ADDRESS=0x1268545,0x59afafa", proc.stdout)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY=LoadObject", proc.stdout)
        self.assertIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIMIT=2", proc.stdout)
        self.assertNotIn("DUNE_UE4SS_PACKAGE_REMOTE_TRACE_SIGNATURE_FAMILY=LoadPackage", proc.stdout)

    def test_dry_run_rejects_stale_remote_trace_cleanup_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["cleanupCommand"] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject "
                "scripts/ue4ss-package-remote-trace.sh stop other-host dune_server-deep-desert-1 "
                "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log"
            )
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            proc = subprocess.run(
                ["bash", str(SCRIPT), "--dry-run", "--wait", "30", "--runbook", str(runbook)],
                env={"PATH": "/usr/bin:/bin"},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertIn(
            "runbook cleanupCommand must match stop not-a-real-host dune_server-deep-desert-1",
            proc.stderr,
        )

    def test_dry_run_rejects_missing_required_route_address_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["traceInputs"] = {"routeAddress": "0x129d58a2"}
            payload["cleanupCommand"] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject "
                "scripts/ue4ss-package-remote-trace.sh stop not-a-real-host dune_server-deep-desert-1 "
                "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log"
            )
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            proc = subprocess.run(
                ["bash", str(SCRIPT), "--dry-run", "--wait", "30", "--runbook", str(runbook)],
                env={"PATH": "/usr/bin:/bin"},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertIn(
            "runbook traceEnv must export DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2",
            proc.stderr,
        )

    def test_trace_log_override_requires_absolute_remote_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            proc = subprocess.run(
                ["bash", str(SCRIPT), "--dry-run", "--runbook", str(runbook), "--trace-log", "relative.log"],
                env={"PATH": "/usr/bin:/bin"},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertIn("--trace-log must be an absolute remote path", proc.stderr)

    def test_preflight_only_uses_effective_override_runbook_without_arming(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["traceInputs"] = {"routeAddress": "0x129d58a2"}
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS"] = "0x129d58a2"
            payload["cleanupCommand"] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2 "
                "scripts/ue4ss-package-remote-trace.sh stop not-a-real-host dune_server-deep-desert-1 "
                "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log"
            )
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            fake_repo = Path(tmp) / "repo"
            scripts = fake_repo / "scripts"
            scripts.mkdir(parents=True)
            calls = Path(tmp) / "calls.log"
            preflight_summary = Path(tmp) / "preflight-summary.json"
            fake_runner = scripts / "ue4ss-package-remote-trace.sh"
            fake_runner.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s %s %s %s %s\\n' \"$1\" \"$2\" \"$3\" \"$4\" \"${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON:-}\" >> \"$REMOTE_TRACE_CALLS\"\n",
                encoding="utf-8",
            )
            fake_runner.chmod(0o755)
            script = scripts / "run-ue4ss-package-live-stimulus-trace.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            override_log = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260624T000001Z.log"
            proc = subprocess.run(
                [
                    "bash",
                    str(script),
                    "--preflight-only",
                    "--runbook",
                    str(runbook),
                    "--trace-log",
                    override_log,
                ],
                env={
                    "PATH": "/usr/bin:/bin",
                    "REMOTE_TRACE_CALLS": str(calls),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_RUNBOOK": str(runbook),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_PREFLIGHT_SUMMARY_JSON": str(preflight_summary),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            call_text = calls.read_text(encoding="utf-8")
            summary = json.loads(preflight_summary.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("coordinator_preflight_only=1", proc.stdout)
        self.assertIn(f"preflight_summary_json={preflight_summary}", proc.stdout)
        self.assertIn("preflight_summary_ready=false", proc.stdout)
        self.assertIn("preflight_only=done", proc.stdout)
        self.assertNotIn("operator_stimulus_window=begin", proc.stdout)
        self.assertEqual(summary["schemaVersion"], "dune-ue4ss-package-live-preflight-summary/v1")
        self.assertEqual(summary["sourceRunbook"], str(runbook))
        self.assertNotEqual(summary["runbook"], str(runbook))
        self.assertEqual(summary["traceLogOverride"], override_log)
        self.assertEqual(summary["traceLog"], override_log)
        self.assertFalse(summary["ready"])
        self.assertIn("preflight did not report ok", summary["blockers"])
        lines = call_text.splitlines()
        self.assertEqual(len(lines), 1, call_text)
        fields = lines[0].split()
        self.assertEqual(fields[:4], ["preflight", "not-a-real-host", "dune_server-deep-desert-1", override_log])
        self.assertTrue(fields[4] and fields[4] != str(runbook), call_text)

    def test_preflight_only_writes_ready_summary_from_remote_preflight_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=120)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["traceInputs"] = {"routeAddress": "0x129d58a2"}
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS"] = "0x129d58a2"
            payload["cleanupCommand"] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ROUTE_ADDRESS=0x129d58a2 "
                "scripts/ue4ss-package-remote-trace.sh stop not-a-real-host dune_server-deep-desert-1 "
                "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log"
            )
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            fake_repo = Path(tmp) / "repo"
            scripts = fake_repo / "scripts"
            scripts.mkdir(parents=True)
            fake_runner = scripts / "ue4ss-package-remote-trace.sh"
            fake_runner.write_text(
                "#!/usr/bin/env bash\n"
                "echo remote_host=not-a-real-host\n"
                "echo player_guard_preflight_partition=8\n"
                "echo player_guard_preflight_connected_players=0\n"
                "echo preflight=ok\n"
                "echo container=dune_server-deep-desert-1\n"
                "echo route_address=0x129d58a2\n",
                encoding="utf-8",
            )
            fake_runner.chmod(0o755)
            script = scripts / "run-ue4ss-package-live-stimulus-trace.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            preflight_summary = Path(tmp) / "preflight-summary.json"

            proc = subprocess.run(
                ["bash", str(script), "--preflight-only", "--wait", "30", "--runbook", str(runbook)],
                env={
                    "PATH": "/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_STIMULUS_PREFLIGHT_SUMMARY_JSON": str(preflight_summary),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            summary = json.loads(preflight_summary.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("preflight_summary_ready=true", proc.stdout)
        self.assertTrue(summary["ready"], summary["blockers"])
        self.assertEqual(summary["fields"]["remote_host"], "not-a-real-host")
        self.assertEqual(summary["fields"]["player_guard_preflight_connected_players"], "0")
        self.assertEqual(summary["fields"]["route_address"], "0x129d58a2")
        self.assertEqual(summary["runbook"], str(runbook))
        self.assertEqual(summary["sourceRunbook"], str(runbook))

    def test_live_run_refuses_to_arm_when_fresh_preflight_summary_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=1)
            fake_repo = Path(tmp) / "repo"
            scripts = fake_repo / "scripts"
            scripts.mkdir(parents=True)
            fake_runner = scripts / "ue4ss-package-remote-trace.sh"
            calls = Path(tmp) / "calls.log"
            fake_runner.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$1\" >> \"$REMOTE_TRACE_CALLS\"\n"
                "if [[ \"$1\" == preflight ]]; then echo preflight=fail; fi\n"
                "if [[ \"$1\" == arm ]]; then echo should-not-arm; fi\n",
                encoding="utf-8",
            )
            fake_runner.chmod(0o755)
            script = scripts / "run-ue4ss-package-live-stimulus-trace.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            preflight_summary = Path(tmp) / "preflight-summary.json"

            proc = subprocess.run(
                ["bash", str(script), "1", "--runbook", str(runbook)],
                env={
                    "PATH": "/usr/bin:/bin",
                    "REMOTE_TRACE_CALLS": str(calls),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_PREFLIGHT_SUMMARY_JSON": str(preflight_summary),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            summary = json.loads(preflight_summary.read_text(encoding="utf-8"))
            call_text = calls.read_text(encoding="utf-8")

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(call_text.splitlines(), ["preflight"])
        self.assertIn("preflight_summary_ready=false", proc.stdout)
        self.assertIn("refusing to arm", proc.stderr)
        self.assertFalse(summary["ready"])
        self.assertIn("preflight did not report ok", summary["blockers"])

    def test_runner_sequences_preflight_arm_wait_status_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=1)
            fake_repo = Path(tmp) / "repo"
            scripts = fake_repo / "scripts"
            scripts.mkdir(parents=True)
            fake_runner = scripts / "ue4ss-package-remote-trace.sh"
            calls = Path(tmp) / "calls.log"
            fake_runner.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s %s %s %s %s\\n' \"$1\" \"$2\" \"$3\" \"$4\" \"${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON:-}\" >> \"$REMOTE_TRACE_CALLS\"\n"
                "if [[ \"$1\" == preflight ]]; then echo preflight=ok; echo player_guard_preflight_connected_players=0; fi\n"
                "if [[ \"$1\" == status ]]; then echo review_bundle_verify_json=/tmp/review.json; echo route_slot_recovery_verify_json=/tmp/route.json; fi\n",
                encoding="utf-8",
            )
            fake_runner.chmod(0o755)
            fake_summary_verifier = scripts / "verify-ue4ss-package-live-stimulus-summary.py"
            fake_summary_verifier.write_text(
                "#!/usr/bin/env python3\n"
                "print('{\"ready\":true,\"blockers\":[]}')\n",
                encoding="utf-8",
            )
            fake_summary_verifier.chmod(0o755)
            write_fake_prearm_verifier(scripts)
            fake_bin = Path(tmp) / "bin"
            fake_bin.mkdir()
            fake_ssh = fake_bin / "ssh"
            fake_ssh.write_text(
                "#!/usr/bin/env bash\n"
                "printf '{\"ready\":false,\"blockers\":[\"missing hit\"]}'\n",
                encoding="utf-8",
            )
            fake_ssh.chmod(0o755)
            script = scripts / "run-ue4ss-package-live-stimulus-trace.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            summary_json = Path(tmp) / "review-summary.json"

            proc = subprocess.run(
                ["bash", str(script), "1"],
                env={
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "REMOTE_TRACE_CALLS": str(calls),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_RUNBOOK": str(runbook),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_REVIEW_SUMMARY_JSON": str(summary_json),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            call_text = calls.read_text(encoding="utf-8")
            summary = json.loads(summary_json.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("operator_stimulus_window=begin", proc.stdout)
        self.assertIn("operator_stimulus_window_started_utc=", proc.stdout)
        self.assertIn("operator_stimulus_window_finished_utc=", proc.stdout)
        self.assertIn("operator_stimulus_window=end", proc.stdout)
        self.assertIn("run_started_utc=", proc.stdout)
        self.assertIn("status_finished_utc=", proc.stdout)
        self.assertIn("review_bundle_verify_json=/tmp/review.json", proc.stdout)
        self.assertIn("route_slot_recovery_verify_json=/tmp/route.json", proc.stdout)
        self.assertIn("route_slot_recovery_ready=false", proc.stdout)
        self.assertIn("route_slot_recovery_blocker=missing hit", proc.stdout)
        self.assertIn("origin_classification_status=missing", proc.stdout)
        self.assertIn("origin_classification_blocker=package-load classification has no selected runtime package hit", proc.stdout)
        self.assertIn("review_bundle_ready=false", proc.stdout)
        self.assertIn("review_bundle_blocker=missing hit", proc.stdout)
        self.assertIn(f"review_bundle_summary_json={summary_json}", proc.stdout)
        self.assertIn("local_review_summary_verification=begin", proc.stdout)
        self.assertIn("local_review_summary_ready=true", proc.stdout)
        self.assertIn("local_review_summary_verification=done", proc.stdout)
        self.assertEqual(summary["schemaVersion"], "dune-ue4ss-package-live-stimulus-review-summary/v1")
        self.assertEqual(summary["runbook"], str(runbook))
        self.assertEqual(summary["sourceRunbook"], str(runbook))
        self.assertEqual(summary["traceLogOverride"], "")
        self.assertEqual(summary["traceRemote"], "not-a-real-host")
        self.assertEqual(summary["container"], "dune_server-deep-desert-1")
        self.assertEqual(summary["traceLog"], "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T213923Z.log")
        self.assertEqual(summary["operatorWindowSeconds"], 1)
        self.assertRegex(summary["runStartedUtc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertRegex(summary["statusFinishedUtc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(summary["verifyJson"], "/tmp/review.json")
        self.assertEqual(summary["routeSlotRecoveryVerifyJson"], "/tmp/route.json")
        self.assertEqual(summary["routeSlotRecoveryVerification"]["blockers"], ["missing hit"])
        self.assertTrue(summary["routeSlotRecoveryVerificationSha256"])
        self.assertTrue(summary["prearmReadinessVerification"]["ready"])
        self.assertTrue(summary["prearmReadinessVerificationSha256"])
        self.assertEqual(summary["originClassification"]["status"], "missing")
        self.assertEqual(
            summary["originClassification"]["serverSideFallbackCandidate"],
            "server-side-client-call-emulation",
        )
        self.assertFalse(summary["originClassification"]["requiresServerSideReplay"])
        self.assertEqual(summary["bundle"], "")
        self.assertEqual(summary["ready"], False)
        self.assertEqual(summary["blockers"], ["missing hit", "route-slot recovery: missing hit"])
        self.assertIn("cleanup-command", proc.stdout)
        self.assertIn("no-debugger-command", proc.stdout)
        self.assertEqual(
            [line.split()[0] for line in call_text.splitlines()],
            ["preflight", "arm", "status"],
        )

    def test_live_summary_marks_missing_route_slot_verification_as_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=1)
            fake_repo = Path(tmp) / "repo"
            scripts = fake_repo / "scripts"
            scripts.mkdir(parents=True)
            fake_runner = scripts / "ue4ss-package-remote-trace.sh"
            fake_runner.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$1\" == preflight ]]; then echo preflight=ok; echo player_guard_preflight_connected_players=0; fi\n"
                "if [[ \"$1\" == status ]]; then echo review_bundle_verify_json=/tmp/review.json; echo route_slot_recovery_verify_json=/tmp/route.json; fi\n",
                encoding="utf-8",
            )
            fake_runner.chmod(0o755)
            fake_summary_verifier = scripts / "verify-ue4ss-package-live-stimulus-summary.py"
            fake_summary_verifier.write_text(
                "#!/usr/bin/env python3\n"
                "print('{\"ready\":false,\"blockers\":[\"summary route-slot blocker expected\"]}')\n",
                encoding="utf-8",
            )
            fake_summary_verifier.chmod(0o755)
            write_fake_prearm_verifier(scripts)
            fake_bin = Path(tmp) / "bin"
            fake_bin.mkdir()
            fake_ssh = fake_bin / "ssh"
            fake_ssh.write_text(
                "#!/usr/bin/env bash\n"
                "case \"$*\" in\n"
                "  *review.json*) printf '{\"ready\":true,\"bundle\":\"/tmp/bundle\",\"blockers\":[],\"artifactCount\":14,\"checksumCount\":15}' ;;\n"
                "  *) exit 0 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            fake_ssh.chmod(0o755)
            script = scripts / "run-ue4ss-package-live-stimulus-trace.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            summary_json = Path(tmp) / "review-summary.json"

            proc = subprocess.run(
                ["bash", str(script), "1"],
                env={
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "DUNE_UE4SS_PACKAGE_STIMULUS_RUNBOOK": str(runbook),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_REVIEW_SUMMARY_JSON": str(summary_json),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            summary = json.loads(summary_json.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(summary["ready"])
        self.assertIsNone(summary["routeSlotRecoveryVerification"])
        self.assertEqual(summary["routeSlotRecoveryVerificationSha256"], "")
        self.assertIn("route-slot recovery verification JSON is missing", summary["blockers"])
        self.assertIn("local_review_summary_ready=false", proc.stdout)

    def test_trace_log_override_is_recorded_in_live_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            runbook = Path(tmp) / "runbook.json"
            write_runbook(runbook, max_seconds=1)
            fake_repo = Path(tmp) / "repo"
            scripts = fake_repo / "scripts"
            scripts.mkdir(parents=True)
            fake_runner = scripts / "ue4ss-package-remote-trace.sh"
            calls = Path(tmp) / "calls.log"
            fake_runner.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s %s %s %s %s\\n' \"$1\" \"$2\" \"$3\" \"$4\" \"${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON:-}\" >> \"$REMOTE_TRACE_CALLS\"\n"
                "if [[ \"$1\" == preflight ]]; then echo preflight=ok; echo player_guard_preflight_connected_players=0; fi\n"
                "if [[ \"$1\" == status ]]; then echo review_bundle_verify_json=/tmp/review.json; echo route_slot_recovery_verify_json=/tmp/route.json; fi\n",
                encoding="utf-8",
            )
            fake_runner.chmod(0o755)
            fake_summary_verifier = scripts / "verify-ue4ss-package-live-stimulus-summary.py"
            fake_summary_verifier.write_text(
                "#!/usr/bin/env python3\n"
                "print('{\"ready\":true,\"blockers\":[]}')\n",
                encoding="utf-8",
            )
            fake_summary_verifier.chmod(0o755)
            write_fake_prearm_verifier(scripts)
            fake_bin = Path(tmp) / "bin"
            fake_bin.mkdir()
            fake_ssh = fake_bin / "ssh"
            fake_ssh.write_text(
                "#!/usr/bin/env bash\nprintf '{\"ready\":true,\"artifactCount\":4,\"checksumCount\":4}'\n",
                encoding="utf-8",
            )
            fake_ssh.chmod(0o755)
            script = scripts / "run-ue4ss-package-live-stimulus-trace.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            summary_json = Path(tmp) / "review-summary.json"
            override_log = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260623T235959Z.log"

            proc = subprocess.run(
                ["bash", str(script), "1", "--trace-log", override_log],
                env={
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "REMOTE_TRACE_CALLS": str(calls),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_RUNBOOK": str(runbook),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_REVIEW_SUMMARY_JSON": str(summary_json),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            call_text = calls.read_text(encoding="utf-8")
            summary = json.loads(summary_json.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"source_runbook={runbook}", proc.stdout)
        self.assertIn(f"trace_log_override={override_log}", proc.stdout)
        verifier_line = next(
            line for line in proc.stdout.splitlines() if line.startswith("local_review_summary_verification_command=")
        )
        self.assertNotIn(str(runbook), verifier_line)
        self.assertNotEqual(summary["runbook"], str(runbook))
        self.assertEqual(summary["sourceRunbook"], str(runbook))
        self.assertEqual(summary["traceLogOverride"], override_log)
        self.assertEqual(summary["traceLog"], override_log)
        self.assertEqual(summary["ready"], True)
        self.assertEqual(
            [line.split()[3] for line in call_text.splitlines()],
            [override_log, override_log, override_log],
        )
        self.assertTrue(
            all(line.split()[4] and line.split()[4] != str(runbook) for line in call_text.splitlines()),
            call_text,
        )

    def test_runner_uses_real_local_summary_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook = root / "runbook.json"
            write_runbook(runbook, max_seconds=1)
            fake_repo = root / "repo"
            scripts = fake_repo / "scripts"
            scripts.mkdir(parents=True)
            fake_runner = scripts / "ue4ss-package-remote-trace.sh"
            calls = root / "calls.log"
            fake_runner.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s %s %s %s\\n' \"$1\" \"$2\" \"$3\" \"$4\" >> \"$REMOTE_TRACE_CALLS\"\n"
                "if [[ \"$1\" == preflight ]]; then echo preflight=ok; echo player_guard_preflight_connected_players=0; fi\n"
                "if [[ \"$1\" == status ]]; then echo review_bundle_verify_json=/tmp/review.json; echo route_slot_recovery_verify_json=/tmp/route.json; fi\n",
                encoding="utf-8",
            )
            fake_runner.chmod(0o755)
            summary_verifier = scripts / "verify-ue4ss-package-live-stimulus-summary.py"
            summary_verifier.write_text(SUMMARY_VERIFIER.read_text(encoding="utf-8"), encoding="utf-8")
            summary_verifier.chmod(0o755)
            write_fake_prearm_verifier(scripts)
            script = scripts / "run-ue4ss-package-live-stimulus-trace.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            summary_json = root / "review-summary.json"
            next_action = fake_repo / "build" / "server-current-anchor-prep" / "ue4ss-package-next-action.json"
            next_action.parent.mkdir(parents=True)
            next_action.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-next-action/v1",
                        "action": "recover-package-anchor",
                        "liveTraceRunbook": {
                            "localReviewSummaryJson": str(summary_json),
                            "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_ssh = fake_bin / "ssh"
            fake_ssh.write_text(
                "#!/usr/bin/env bash\n"
                "printf '{\"ready\":true,\"bundle\":\"/tmp/bundle\",\"blockers\":[],\"artifactCount\":14,\"checksumCount\":15}'\n",
                encoding="utf-8",
            )
            fake_ssh.chmod(0o755)

            proc = subprocess.run(
                ["bash", str(script), "1"],
                env={
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "REMOTE_TRACE_CALLS": str(calls),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_RUNBOOK": str(runbook),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_REVIEW_SUMMARY_JSON": str(summary_json),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("local_review_summary_verification=begin", proc.stdout)
        self.assertIn("local_review_summary_ready=true", proc.stdout)
        self.assertIn("local_review_summary_verification=done", proc.stdout)

    def test_trace_log_override_uses_effective_runbook_for_real_local_summary_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runbook = root / "runbook.json"
            write_runbook(runbook, max_seconds=1)
            payload = json.loads(runbook.read_text(encoding="utf-8"))
            payload["sourcePath"] = str(runbook)
            payload["cleanupCommand"] = "printf cleanup-command\\n"
            payload["noDebuggerCheckCommand"] = "printf no-debugger-command\\n"
            runbook.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            fake_repo = root / "repo"
            scripts = fake_repo / "scripts"
            scripts.mkdir(parents=True)
            fake_runner = scripts / "ue4ss-package-remote-trace.sh"
            calls = root / "calls.log"
            fake_runner.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s %s %s %s %s\\n' \"$1\" \"$2\" \"$3\" \"$4\" \"${DUNE_UE4SS_PACKAGE_REMOTE_TRACE_LIVE_RUNBOOK_JSON:-}\" >> \"$REMOTE_TRACE_CALLS\"\n"
                "if [[ \"$1\" == preflight ]]; then echo preflight=ok; echo player_guard_preflight_connected_players=0; fi\n"
                "if [[ \"$1\" == status ]]; then echo review_bundle_verify_json=/tmp/review.json; echo route_slot_recovery_verify_json=/tmp/route.json; fi\n",
                encoding="utf-8",
            )
            fake_runner.chmod(0o755)
            summary_verifier = scripts / "verify-ue4ss-package-live-stimulus-summary.py"
            summary_verifier.write_text(SUMMARY_VERIFIER.read_text(encoding="utf-8"), encoding="utf-8")
            summary_verifier.chmod(0o755)
            write_fake_prearm_verifier(scripts)
            script = scripts / "run-ue4ss-package-live-stimulus-trace.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            summary_json = root / "review-summary.json"
            next_action = fake_repo / "build" / "server-current-anchor-prep" / "ue4ss-package-next-action.json"
            next_action.parent.mkdir(parents=True)
            next_action.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-next-action/v1",
                        "action": "recover-package-anchor",
                        "liveTraceRunbook": {
                            "localReviewSummaryJson": str(summary_json),
                            "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                            "localReviewSummaryEmbeddedEvidenceFields": "reviewBundleVerification,reviewBundleVerificationSha256,routeSlotRecoveryVerification,routeSlotRecoveryVerificationSha256,prearmReadinessVerification,prearmReadinessVerificationSha256",
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_ssh = fake_bin / "ssh"
            fake_ssh.write_text(
                "#!/usr/bin/env bash\n"
                "printf '{\"ready\":true,\"bundle\":\"/tmp/bundle\",\"blockers\":[],\"artifactCount\":14,\"checksumCount\":15}'\n",
                encoding="utf-8",
            )
            fake_ssh.chmod(0o755)
            override_log = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry-20260624T010101Z.log"

            proc = subprocess.run(
                ["bash", str(script), "1", "--trace-log", override_log],
                env={
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "REMOTE_TRACE_CALLS": str(calls),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_RUNBOOK": str(runbook),
                    "DUNE_UE4SS_PACKAGE_STIMULUS_REVIEW_SUMMARY_JSON": str(summary_json),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            call_text = calls.read_text(encoding="utf-8")
            summary = json.loads(summary_json.read_text(encoding="utf-8"))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("local_review_summary_ready=true", proc.stdout)
        self.assertNotEqual(summary["runbook"], str(runbook))
        self.assertEqual(summary["sourceRunbook"], str(runbook))
        self.assertEqual(summary["traceLog"], override_log)
        self.assertTrue(
            all(line.split()[4] and line.split()[4] == summary["runbook"] for line in call_text.splitlines()),
            call_text,
        )


if __name__ == "__main__":
    unittest.main()
