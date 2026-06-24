#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-loader-artifacts.py"

spec = importlib.util.spec_from_file_location("verify_loader_artifacts", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class Result:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


ELF_FILE = "loader.so: ELF 64-bit LSB shared object, x86-64, dynamically linked\n"
ELF_HEADER = "\n".join(
    [
        "Type:                              DYN (Shared object file)",
        "Machine:                           Advanced Micro Devices X86-64",
    ]
)
ELF_DYNAMIC = "\n".join(
    [
        "Shared library: [libc.so.6]",
        "Library soname: [libdune_client_probe_loader.so]",
    ]
)
PE_FILE = "loader.dll: PE32+ executable for MS Windows 5.02 (DLL), x86-64, 18 sections\n"
PE_OBJDUMP = "\n".join(
    [
        "Subsystem\t\t00000002\t(Windows GUI)",
        "DLL Name: KERNEL32.dll",
        "Export Tables",
        "DuneWinClientProbeSmoke",
        "DuneWinClientProbeForwardSmoke",
        "DuneWinClientProbeMarker",
        "GetFileVersionInfoA",
        "GetFileVersionInfoW",
        "GetFileVersionInfoSizeA",
        "GetFileVersionInfoSizeW",
        "VerQueryValueA",
        "VerQueryValueW",
    ]
)


def write_required_package_layout(root, target, skip=()):
    skip = set(skip)
    for relative in module.PACKAGE_LAYOUTS[target]:
        if relative in skip:
            continue
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == "docs/ue4ss-portability-contract.json":
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-portability-contract/v1",
                        "passed": True,
                    }
                ),
                encoding="utf-8",
            )
        elif relative == "docs/ue4ss-portability-contract.md":
            path.write_text("# UE4SS Portability Contract\n\n- Passed: `true`\n", encoding="utf-8")
        elif relative in module.PACKAGE_DOC_MARKERS[target]:
            path.write_text(
                "\n".join(module.PACKAGE_DOC_MARKERS[target][relative])
                + "\n"
                + ("operator documentation body\n" * 8),
                encoding="utf-8",
            )
        elif relative in module.PACKAGE_FILE_MARKERS.get(target, {}):
            prefix = "# " if relative.endswith(".sh") else ""
            path.write_text(
                ("#!/usr/bin/env bash\n" if relative.endswith(".sh") else "#!/usr/bin/env python3\n")
                + "\n".join(f"{prefix}{marker}" for marker in module.PACKAGE_FILE_MARKERS[target][relative])
                + "\nexit 0\n",
                encoding="utf-8",
            )
        elif relative in module.PACKAGE_EXECUTABLES[target]:
            path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        else:
            path.write_text("ok", encoding="utf-8")
        if relative in module.PACKAGE_EXECUTABLES[target]:
            path.chmod(0o755)
    write_package_checksums(root, target, skip=skip)


def write_package_checksums(root, target, skip=()):
    skip = set(skip)
    rows = []
    for relative in module.PACKAGE_LAYOUTS[target]:
        if relative in skip:
            continue
        path = root / relative
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}")
    (root / "SHA256SUMS").write_text("\n".join(rows) + "\n", encoding="utf-8")


class VerifyLoaderArtifactsTests(unittest.TestCase):
    def test_verify_elf_accepts_shared_object_with_expected_soname(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = Path(tmp) / "libdune_client_probe_loader.so"
            loader.write_bytes(b"elf")
            config = {"path": loader, "kind": "elf", "soname": "libdune_client_probe_loader.so"}

            def fake_run(argv):
                if argv[0] == "file":
                    return Result(ELF_FILE)
                if argv[:2] == ["readelf", "-h"]:
                    return Result(ELF_HEADER)
                if argv[:2] == ["readelf", "-d"]:
                    return Result(ELF_DYNAMIC)
                return Result("", 1, "unexpected")

            with mock.patch.object(module, "run_command", side_effect=fake_run):
                row = module.verify_elf("linux-client", config)

        self.assertTrue(row["passed"], row)
        self.assertEqual(row["missing"], [])

    def test_verify_pe_requires_proxy_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = Path(tmp) / "dune_win_client_probe_loader.dll"
            loader.write_bytes(b"pe")
            config = module.TARGETS["windows-client"] | {"path": loader}

            def fake_run(argv):
                if argv[0] == "file":
                    return Result(PE_FILE)
                if argv[0] == "x86_64-w64-mingw32-objdump":
                    return Result(PE_OBJDUMP)
                return Result("", 1, "unexpected")

            with mock.patch.object(module, "run_command", side_effect=fake_run):
                row = module.verify_pe("windows-client", config)

        self.assertTrue(row["passed"], row)
        self.assertIn("VerQueryValueW", row["details"]["requiredExports"])

    def test_verify_pe_fails_when_version_proxy_export_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = Path(tmp) / "dune_win_client_probe_loader.dll"
            loader.write_bytes(b"pe")
            config = module.TARGETS["windows-client"] | {"path": loader}

            def fake_run(argv):
                if argv[0] == "file":
                    return Result(PE_FILE)
                if argv[0] == "x86_64-w64-mingw32-objdump":
                    return Result(PE_OBJDUMP.replace("VerQueryValueW", ""))
                return Result("", 1, "unexpected")

            with mock.patch.object(module, "run_command", side_effect=fake_run):
                row = module.verify_pe("windows-client", config)

        self.assertFalse(row["passed"], row)
        self.assertIn("VerQueryValueW", row["missing"])

    def test_text_renderer_reports_all_targets(self):
        text = module.render_text(
            {
                "passed": False,
                "targets": {
                    "linux-client": {
                        "passed": True,
                        "missing": [],
                        "details": {"path": "/tmp/libdune_client_probe_loader.so"},
                    },
                    "windows-client": {
                        "passed": False,
                        "missing": ["VerQueryValueW"],
                        "details": {"path": "/tmp/dune_win_client_probe_loader.dll"},
                    },
                },
                "packages": {
                    "linux-server": {
                        "passed": False,
                        "missing": ["tests/test-ue4ss-portability-contract.py"],
                        "details": {"path": "/tmp/package"},
                    },
                },
            }
        )

        self.assertIn("loader_artifacts_ok=false", text)
        self.assertIn("linux-client passed=true", text)
        self.assertIn("windows-client passed=false", text)
        self.assertIn("VerQueryValueW", text)
        self.assertIn("linux-server package_passed=false", text)
        self.assertIn("test-ue4ss-portability-contract.py", text)

    def test_resolve_path_accepts_packaged_lib_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_build = Path(tmp) / "build" / "linux-client-loader" / "libdune_client_probe_loader.so"
            packaged = Path(tmp) / "lib" / "libdune_client_probe_loader.so"
            packaged.parent.mkdir(parents=True)
            packaged.write_bytes(b"elf")

            resolved = module.resolve_path({"paths": (missing_build, packaged)})

        self.assertEqual(resolved, packaged)

    def test_default_targets_prefers_existing_artifacts(self):
        with mock.patch.object(
            module,
            "target_has_existing_artifact",
            side_effect=lambda target: target == "windows-client",
        ):
            self.assertEqual(module.default_targets(), ["windows-client"])

    def test_verify_package_root_accepts_required_portability_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client")

            row = module.verify_package_root("linux-client", root)

        self.assertTrue(row["passed"], row)
        self.assertEqual(row["missing"], [])
        self.assertIn("tests/test-ue4ss-portability-contract.py", row["details"]["required"])

    def test_verify_package_root_rejects_missing_portability_contract_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server", skip={"tests/test-ue4ss-portability-contract.py"})

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("tests/test-ue4ss-portability-contract.py", row["missing"])

    def test_verify_package_root_rejects_missing_packaged_loader_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server", skip={"lib/libdune_server_probe_loader.so"})

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("lib/libdune_server_probe_loader.so", row["missing"])

    def test_verify_package_root_requires_windows_proxy_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "windows-client", skip={"lib/version.dll"})

            row = module.verify_package_root("windows-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("lib/version.dll", row["missing"])

    def test_verify_package_root_rejects_missing_packaged_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client", skip={"src/dune_client_probe_loader.c"})

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("src/dune_client_probe_loader.c", row["missing"])

    def test_verify_package_root_rejects_missing_rebuild_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "windows-client", skip={"build-windows-client-loader.sh"})

            row = module.verify_package_root("windows-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("build-windows-client-loader.sh", row["missing"])

    def test_verify_package_root_rejects_missing_client_operator_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client", skip={"docs/linux-client-loader.md"})

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("docs/linux-client-loader.md", row["missing"])

    def test_verify_package_root_rejects_missing_server_operator_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server", skip={"docs/ue4ss-linux-loader-evaluation.md"})

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("docs/ue4ss-linux-loader-evaluation.md", row["missing"])

    def test_verify_package_root_rejects_stale_operator_doc_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "windows-client")
            (root / "docs" / "windows-client-loader.md").write_text("# Wrong Doc\n", encoding="utf-8")

            row = module.verify_package_root("windows-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("docs/windows-client-loader.md:missing-marker:# Windows Client Loader", row["missing"])

    def test_verify_package_root_rejects_server_doc_without_package_closure_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            (root / "docs" / "ue4ss-linux-loader-evaluation.md").write_text(
                "# UE4SS Linux Server Loader Evaluation\n\nRepo-Side Loader Foundation\n"
                + ("operator documentation body\n" * 8),
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:ue4ss-package-runtime-trace.sh",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:plan-ue4ss-package-stimulus-trace.py",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:ue4ss-package-stimulus-trace-runbook.json",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:verify-ue4ss-package-review-bundle.py",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:ue4ss-evidence-inventory.md",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:ue4ss-evidence-inventory.json",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:summarize-ue4ss-evidence-inventory.py",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:dune-ue4ss-package-anchor-promotion-acceptance/v1",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:cleanupCommand",
            row["missing"],
        )
        self.assertIn(
            "docs/ue4ss-linux-loader-evaluation.md:missing-marker:matching `stop` command",
            row["missing"],
        )

    def test_verify_package_root_rejects_server_readme_without_live_trace_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            (root / "README.md").write_text(
                "# Dune Linux Server Loader\n\noperator documentation body\n" * 8,
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "README.md:missing-marker:scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
            row["missing"],
        )
        self.assertIn(
            "README.md:missing-marker:verify-ue4ss-package-route-slot-recovery.py <ue4ss-package-runtime-trace-evidence.json> --next-action-json ue4ss-package-next-action.json",
            row["missing"],
        )
        self.assertIn(
            "README.md:missing-marker:UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            row["missing"],
        )
        self.assertIn(
            "README.md:missing-marker:routeSlotTraceRequirement",
            row["missing"],
        )
        self.assertIn(
            "README.md:missing-marker:requiredSlots=[0x3a0,0x3d8]",
            row["missing"],
        )

    def test_verify_package_root_rejects_client_doc_without_evidence_inventory_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client")
            (root / "docs" / "linux-client-loader.md").write_text(
                "# Linux Client Loader\n\nLD_PRELOAD\n" + ("operator documentation body\n" * 8),
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "docs/linux-client-loader.md:missing-marker:ue4ss-evidence-inventory.md",
            row["missing"],
        )
        self.assertIn(
            "docs/linux-client-loader.md:missing-marker:ue4ss-evidence-inventory.json",
            row["missing"],
        )
        self.assertIn(
            "docs/linux-client-loader.md:missing-marker:--strict",
            row["missing"],
        )
        self.assertIn(
            "docs/linux-client-loader.md:missing-marker:summarize-ue4ss-evidence-inventory.py",
            row["missing"],
        )

    def test_verify_package_root_rejects_tiny_operator_doc_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client")
            (root / "docs" / "linux-client-loader.md").write_text(
                "# Linux Client Loader\nLD_PRELOAD\n",
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("docs/linux-client-loader.md:too-small", row["missing"])

    def test_verify_package_root_rejects_missing_client_launch_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client", skip={"examples/launch-native-client.sh"})

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("examples/launch-native-client.sh", row["missing"])

    def test_verify_package_root_rejects_non_executable_launch_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client")
            (root / "examples" / "launch-native-client.sh").chmod(0o644)

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("examples/launch-native-client.sh:not-executable", row["missing"])

    def test_verify_package_root_rejects_non_executable_prearm_readiness_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            (root / "scripts" / "verify-ue4ss-package-prearm-readiness.py").chmod(0o644)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("scripts/verify-ue4ss-package-prearm-readiness.py:not-executable", row["missing"])

    def test_verify_package_root_rejects_executable_without_shebang(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            script = root / "examples" / "smoke-linux-server-loader.sh"
            script.write_text("exit 0\n", encoding="utf-8")
            script.chmod(0o755)

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("examples/smoke-linux-server-loader.sh:missing-shebang", row["missing"])

    def test_verify_package_root_rejects_shell_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            script = root / "examples" / "smoke-linux-server-loader.sh"
            script.write_text("#!/usr/bin/env bash\nif true\n", encoding="utf-8")
            script.chmod(0o755)
            write_package_checksums(
                root,
                "linux-server",
                skip=("scripts/verify-ue4ss-package-route-slot-recovery.py",),
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("examples/smoke-linux-server-loader.sh:shell-syntax", row["missing"])
        self.assertNotIn("SHA256SUMS:examples/smoke-linux-server-loader.sh:mismatch", row["missing"])

    def test_verify_package_root_rejects_missing_server_smoke_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server", skip={"examples/smoke-linux-server-loader.sh"})

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("examples/smoke-linux-server-loader.sh", row["missing"])

    def test_verify_package_root_rejects_missing_server_package_trace_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server", skip={"scripts/ue4ss-package-runtime-trace.sh"})

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("scripts/ue4ss-package-runtime-trace.sh", row["missing"])

    def test_verify_package_root_rejects_runtime_trace_runner_without_arm_and_status_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "ue4ss-package-runtime-trace.sh"
            path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(
                root,
                "linux-server",
                skip=("scripts/verify-ue4ss-package-route-slot-recovery.py",),
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/ue4ss-package-runtime-trace.sh:missing-marker:package trace gdb exited before the arm window could be used",
            row["missing"],
        )
        self.assertIn(
            'scripts/ue4ss-package-runtime-trace.sh:missing-marker:echo "gdb_running=true"',
            row["missing"],
        )
        self.assertIn(
            "scripts/ue4ss-package-runtime-trace.sh:missing-marker:package trace gdb pid file exists but gdb is not running",
            row["missing"],
        )

    def test_verify_package_root_rejects_remote_trace_wrapper_without_runbook_identity_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "ue4ss-package-remote-trace.sh"
            path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(
                root,
                "linux-server",
                skip=("scripts/verify-ue4ss-package-route-slot-recovery.py",),
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/ue4ss-package-remote-trace.sh:missing-marker:trace_log must match live trace runbook traceLog",
            row["missing"],
        )
        self.assertIn(
            "scripts/ue4ss-package-remote-trace.sh:missing-marker:DUNE_UE4SS_PACKAGE_TRACE_LIVE_RUNBOOK_JSON",
            row["missing"],
        )
        self.assertIn(
            "scripts/ue4ss-package-remote-trace.sh:missing-marker:require_cleanup_matches_runbook",
            row["missing"],
        )
        self.assertIn(
            "scripts/ue4ss-package-remote-trace.sh:missing-marker:cleanupCommand must match stop",
            row["missing"],
        )

    def test_verify_package_root_rejects_stimulus_trace_planner_without_timestamped_log_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "plan-ue4ss-package-stimulus-trace.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            'scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:DEFAULT_TRACE_LOG_PREFIX = "/tmp/ue4ss-package-runtime-trace-live-client-map-entry"',
            row["missing"],
        )
        self.assertIn(
            'scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:DEFAULT_ANCHORS = "LoadPackage,LoadObject"',
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:DEFAULT_OPERATOR_ARM_WINDOW_SECONDS = 120",
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:\"operatorWindow\"",
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:\"noDebuggerCheckCommand\"",
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:\"traceLogUniqueness\"",
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:\"cleanupCommand\"",
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:run cleanupCommand",
            row["missing"],
        )

    def test_verify_package_root_rejects_live_call_frame_planner_without_corrected_anchor_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "plan-ue4ss-package-live-call-frame-recovery.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/plan-ue4ss-package-live-call-frame-recovery.py:missing-marker:DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=LoadPackage,LoadObject",
            row["missing"],
        )

    def test_verify_package_root_rejects_server_replay_planner_without_replay_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "plan-ue4ss-package-server-replay.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/plan-ue4ss-package-server-replay.py:missing-marker:client-originated-pending-server-replay",
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-server-replay.py:missing-marker:DUNE_LINUX_SERVER_CANARY_EXTRA_ENV",
            row["missing"],
        )

    def test_verify_package_root_rejects_next_action_without_cleanup_summary_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "plan-ue4ss-package-next-action.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            'scripts/plan-ue4ss-package-next-action.py:missing-marker:"cleanupCommand": runbook.get("cleanupCommand", "")',
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-next-action.py:missing-marker:cleanup:",
            row["missing"],
        )
        self.assertIn(
            'scripts/plan-ue4ss-package-next-action.py:missing-marker:"operatorWindow": operator_window',
            row["missing"],
        )
        self.assertIn(
            'scripts/plan-ue4ss-package-next-action.py:missing-marker:"noDebuggerCheckCommand": runbook.get("noDebuggerCheckCommand", "")',
            row["missing"],
        )
        self.assertIn(
            'scripts/plan-ue4ss-package-next-action.py:missing-marker:"completionAuditNextClientGateClassification": prearm_readiness.get(',
            row["missing"],
        )
        self.assertIn(
            'scripts/plan-ue4ss-package-next-action.py:missing-marker:"completionAuditNextRuntimeRootRecoveryPlan": prearm_readiness.get(',
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-next-action.py:missing-marker:server-side-client-call-emulation",
            row["missing"],
        )

    def test_verify_package_root_rejects_stimulus_trace_planner_without_route_slot_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "plan-ue4ss-package-stimulus-trace.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            'scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:"routeSlotTraceRequirement"',
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            row["missing"],
        )
        self.assertIn(
            "scripts/plan-ue4ss-package-stimulus-trace.py:missing-marker:## Route Slot Trace Requirement",
            row["missing"],
        )

    def test_verify_package_root_rejects_live_coordinator_without_route_slot_requirement_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "run-ue4ss-package-live-stimulus-trace.sh"
            text = path.read_text(encoding="utf-8")
            for marker in (
                "print_route_slot_trace_requirement",
                "route_slot_expected_trace_marker",
                "route_slot_route_address",
                "route_slot_review_field",
                "route_slot_required_slots",
                "route_slot_missing_slots",
                "route_slot_required_registers",
                "route_slot_missing_registers",
            ):
                text = text.replace(f"# {marker}", "")
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/run-ue4ss-package-live-stimulus-trace.sh:missing-marker:route_slot_expected_trace_marker",
            row["missing"],
        )
        self.assertIn(
            "scripts/run-ue4ss-package-live-stimulus-trace.sh:missing-marker:route_slot_required_slots",
            row["missing"],
        )
        self.assertIn(
            "scripts/run-ue4ss-package-live-stimulus-trace.sh:missing-marker:route_slot_required_registers",
            row["missing"],
        )

    def test_verify_package_root_rejects_review_bundle_verifier_without_live_trace_handoff_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "verify-ue4ss-package-review-bundle.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/verify-ue4ss-package-review-bundle.py:missing-marker:LIVE_TRACE_RUNBOOK_OPERATOR_SEQUENCE",
            row["missing"],
        )
        self.assertIn(
            'scripts/verify-ue4ss-package-review-bundle.py:missing-marker:"noDebuggerCheckCommand": no_debugger_check',
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-review-bundle.py:missing-marker:routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-review-bundle.py:missing-marker:routeSlotRecovery requiredSlots do not match bundled routeSlotTraceRequirement",
            row["missing"],
        )

    def test_verify_package_root_rejects_live_summary_verifier_without_embedded_evidence_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "verify-ue4ss-package-live-stimulus-summary.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:EMBEDDED_EVIDENCE_FIELDS",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary embedded reviewBundleVerification does not match readable review bundle verification",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary missing reviewBundleVerification required by next-action",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary missing reviewBundleVerificationSha256 required by next-action",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary missing prearmReadinessVerification required by next-action",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary missing prearmReadinessVerificationSha256 required by next-action",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:next-action localReviewSummaryEmbeddedEvidenceFields has unexpected value",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:next-action localReviewSummaryRunbookMode has unexpected value",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:routeSlotRecoveryNextTraceRequirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:ORIGIN_REACHABILITY_CLASSIFICATION_STATUSES",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary missing originClassification required by stimulus runbook",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary originClassification requires server-side replay when client-originated",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary routeSlotRecoveryNextTraceRequirement does not match embedded routeSlotRecoveryVerification",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary non-ready routeSlotRecoveryVerification requires matching routeSlotRecoveryNextTraceRequirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-stimulus-summary.py:missing-marker:summary routeSlotRecoveryNextTraceRequirement must be empty when embedded routeSlotRecoveryVerification has no nextTraceRequirement",
            row["missing"],
        )

    def test_verify_package_root_rejects_missing_route_slot_recovery_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_path = "scripts/verify-ue4ss-package-route-slot-recovery.py"
            write_required_package_layout(
                root,
                "linux-server",
                skip=(missing_path,),
            )
            write_package_checksums(
                root,
                "linux-server",
                skip=(missing_path,),
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(missing_path, row["missing"])

    def test_verify_package_root_rejects_route_slot_verifier_without_next_trace_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "verify-ue4ss-package-route-slot-recovery.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/verify-ue4ss-package-route-slot-recovery.py:missing-marker:nextTraceRequirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-route-slot-recovery.py:missing-marker:UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            row["missing"],
        )

    def test_verify_package_root_rejects_live_preflight_verifier_without_zero_player_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "verify-ue4ss-package-live-preflight-summary.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/verify-ue4ss-package-live-preflight-summary.py:missing-marker:dune-ue4ss-package-live-preflight-summary-verification/v1",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-live-preflight-summary.py:missing-marker:summary player_guard_preflight_connected_players must be 0",
            row["missing"],
        )

    def test_verify_package_root_rejects_missing_prearm_readiness_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(
                root,
                "linux-server",
                skip={"scripts/verify-ue4ss-package-prearm-readiness.py"},
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py",
            row["missing"],
        )

    def test_verify_package_root_rejects_prearm_readiness_without_fresh_preflight_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "verify-ue4ss-package-prearm-readiness.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:freshPreflightCommand",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:Fresh Preflight Command",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:FRESH_TRACE_LOG_PATTERN",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:command must use timestamped /tmp package trace log",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:runbook routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:next-action liveTraceRunbook.routeSlotTraceRequirement does not match runbook",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:audit_has_route_slot_blocker",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:completion audit route-slot blocker must include nextRouteSlotTraceRequirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:completionAuditNextRouteSlotTraceRequirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:Completion Audit Route Slot Trace Requirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:completionAuditNextClientGateClassification",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:Completion Audit Origin/Reachability Classification",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:server-side-client-call-emulation",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:completionAuditNextRuntimeRootRecoveryPlan",
            row["missing"],
        )
        self.assertIn(
            "scripts/verify-ue4ss-package-prearm-readiness.py:missing-marker:Completion Audit Runtime Root Recovery",
            row["missing"],
        )

    def test_verify_package_root_rejects_missing_completion_audit_tooling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(
                root,
                "linux-server",
                skip={
                    "scripts/audit-ue4ss-linux-port-completion.py",
                    "tests/test-audit-ue4ss-linux-port-completion.py",
                },
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("scripts/audit-ue4ss-linux-port-completion.py", row["missing"])
        self.assertIn("tests/test-audit-ue4ss-linux-port-completion.py", row["missing"])

    def test_verify_package_root_rejects_completion_audit_without_final_gate_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "audit-ue4ss-linux-port-completion.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:dune-ue4ss-linux-port-completion-audit/v1",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:live-stimulus-summary",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:live-preflight-summary",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:import_preflight_summary_verifier",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:preflight_max_age_seconds",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:run-ue4ss-package-live-stimulus-trace.sh --trace-log",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:nextLivePreflightCommand",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:next_live_preflight_command_from_action",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:next-action coordinatorFreshPreflightCommand must use --preflight-only",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:Next Live Preflight Command",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:next_live_command_from_action",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:next-action coordinatorFreshTraceCommand must use --trace-log",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:stimulus-runbook",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:runbook routeSlotTraceRequirement expectedTraceMarker must be UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:next-action liveTraceRunbook.routeSlotTraceRequirement does not match runbook",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:live_report = live_verifier.report",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:nextRouteSlotTraceRequirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:routeSlotRecoveryNextTraceRequirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:route_slot_next_requirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:has_route_slot_blocker",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:route-slot recovery next trace requirement is missing",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:Next Route Slot Trace Requirement",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:expectedTraceMarker",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:missingSlots",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:missingRegisters",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:nextOriginClassification",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:server-side-client-call-emulation",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:nextRuntimeRootRecoveryPlan",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:validate_runtime_root_recovery_plan",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:runtime root recovery run command must enable strict verification",
            row["missing"],
        )
        self.assertIn(
            "scripts/audit-ue4ss-linux-port-completion.py:missing-marker:DUNE_LINUX_SERVER_CANARY_STRICT_VERIFY=true",
            row["missing"],
        )

    def test_verify_package_root_rejects_port_gap_summary_without_cleanup_handoff_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            path = root / "scripts" / "summarize-ue4ss-port-gaps.py"
            path.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
            path.chmod(0o755)
            write_package_checksums(root, "linux-server")

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(
            'scripts/summarize-ue4ss-port-gaps.py:missing-marker:"cleanupCommand"',
            row["missing"],
        )
        self.assertIn(
            "scripts/summarize-ue4ss-port-gaps.py:missing-marker:Package live trace runbook",
            row["missing"],
        )
        self.assertIn(
            "scripts/summarize-ue4ss-port-gaps.py:missing-marker:LIVE_TRACE_RUNBOOK_REQUIRED_CLEANUP_ANCHOR",
            row["missing"],
        )
        self.assertIn(
            "scripts/summarize-ue4ss-port-gaps.py:missing-marker:liveTraceRunbook.traceLog must use timestamped",
            row["missing"],
        )
        self.assertIn(
            "scripts/summarize-ue4ss-port-gaps.py:missing-marker:LIVE_TRACE_RUNBOOK_OPERATOR_SEQUENCE",
            row["missing"],
        )
        self.assertIn(
            "scripts/summarize-ue4ss-port-gaps.py:missing-marker:liveTraceRunbook.noDebuggerCheckCommand",
            row["missing"],
        )

    def test_verify_package_root_rejects_missing_evidence_inventory_tooling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(
                root,
                "linux-server",
                skip={
                    "scripts/summarize-ue4ss-evidence-inventory.py",
                    "tests/test-ue4ss-evidence-inventory.py",
                },
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("scripts/summarize-ue4ss-evidence-inventory.py", row["missing"])
        self.assertIn("tests/test-ue4ss-evidence-inventory.py", row["missing"])

    def test_verify_package_root_rejects_failed_portability_contract_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "windows-client")
            (root / "docs" / "ue4ss-portability-contract.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-portability-contract/v1",
                        "passed": False,
                    }
                ),
                encoding="utf-8",
            )

            row = module.verify_package_root("windows-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("docs/ue4ss-portability-contract.json:passed", row["missing"])

    def test_verify_package_root_rejects_wrong_portability_contract_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client")
            (root / "docs" / "ue4ss-portability-contract.json").write_text(
                json.dumps({"schemaVersion": "old", "passed": True}),
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("docs/ue4ss-portability-contract.json:schemaVersion", row["missing"])

    def test_verify_package_root_rejects_failed_portability_contract_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            (root / "docs" / "ue4ss-portability-contract.md").write_text(
                "# UE4SS Portability Contract\n\n- Passed: `false`\n",
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("docs/ue4ss-portability-contract.md:passed", row["missing"])

    def test_verify_package_root_rejects_missing_checksum_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client")
            checksum_path = root / "SHA256SUMS"
            checksum_path.write_text(
                "\n".join(
                    line
                    for line in checksum_path.read_text(encoding="utf-8").splitlines()
                    if "tests/test-verify-loader-artifacts.py" not in line
                )
                + "\n",
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("SHA256SUMS:tests/test-verify-loader-artifacts.py:missing", row["missing"])

    def test_verify_package_root_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "windows-client")
            (root / "analysis" / "verify-loader-artifacts.py").write_text("tampered", encoding="utf-8")

            row = module.verify_package_root("windows-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn("SHA256SUMS:analysis/verify-loader-artifacts.py:mismatch", row["missing"])

    def test_verify_package_root_rejects_unsafe_checksum_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            checksum_path = root / "SHA256SUMS"
            checksum_path.write_text(
                checksum_path.read_text(encoding="utf-8")
                + "0" * 64
                + "  ../outside\n",
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-server", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(f"SHA256SUMS:{len(module.PACKAGE_LAYOUTS['linux-server']) + 1}:unsafe-path", row["missing"])

    def test_verify_package_root_rejects_non_hex_checksum_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client")
            checksum_path = root / "SHA256SUMS"
            checksum_path.write_text(
                checksum_path.read_text(encoding="utf-8")
                + "z" * 64
                + "  tests/test-verify-loader-artifacts.py\n",
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(f"SHA256SUMS:{len(module.PACKAGE_LAYOUTS['linux-client']) + 1}:malformed", row["missing"])

    def test_verify_package_root_rejects_duplicate_checksum_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-client")
            checksum_path = root / "SHA256SUMS"
            first_line = checksum_path.read_text(encoding="utf-8").splitlines()[0]
            checksum_path.write_text(
                checksum_path.read_text(encoding="utf-8") + first_line + "\n",
                encoding="utf-8",
            )

            row = module.verify_package_root("linux-client", root)

        self.assertFalse(row["passed"], row)
        self.assertIn(f"SHA256SUMS:{len(module.PACKAGE_LAYOUTS['linux-client']) + 1}:duplicate", row["missing"])

    def test_verify_package_archive_accepts_matching_sidecar_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "package.tar.gz"
            archive.write_bytes(b"archive bytes")
            checksum = root / "package.tar.gz.sha256"
            checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="utf-8")

            row = module.verify_package_archive(archive)

        self.assertTrue(row["passed"], row)
        self.assertEqual(row["missing"], [])
        self.assertEqual(row["details"]["kind"], "package-archive")

    def test_verify_package_archive_rejects_mismatched_sidecar_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "package.tar.gz"
            archive.write_bytes(b"archive bytes")
            checksum = root / "package.tar.gz.sha256"
            checksum.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")

            row = module.verify_package_archive(archive, checksum)

        self.assertFalse(row["passed"], row)
        self.assertIn("packageArchiveSha256:mismatch", row["missing"])

    def test_verify_package_archive_rejects_missing_sidecar_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "package.tar.gz"
            archive.write_bytes(b"archive bytes")

            row = module.verify_package_archive(archive)

        self.assertFalse(row["passed"], row)
        self.assertIn("packageArchiveSha256:missing", row["missing"])

    def test_verify_package_archive_rejects_malformed_sidecar_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "package.tar.gz"
            archive.write_bytes(b"archive bytes")
            checksum = root / "package.tar.gz.sha256"
            checksum.write_text("not-a-sha  package.tar.gz\n", encoding="utf-8")

            row = module.verify_package_archive(archive, checksum)

        self.assertFalse(row["passed"], row)
        self.assertIn("packageArchiveSha256:malformed", row["missing"])

    def test_package_only_cli_skips_binary_artifact_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "windows-client")

            with mock.patch.object(module, "verify_target", side_effect=AssertionError("binary verifier should not run")):
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "verify-loader-artifacts.py",
                        "--target",
                        "windows-client",
                        "--package-root",
                        str(root),
                        "--package-target",
                        "windows-client",
                        "--package-only",
                        "--format",
                        "json",
                    ],
                ):
                    with mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as stdout:
                        code = module.main()

        self.assertEqual(code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["targets"], {})
        self.assertTrue(report["packages"]["windows-client"]["passed"])

    def test_package_only_cli_verifies_package_archive_when_provided(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_required_package_layout(root, "linux-server")
            archive = root.parent / "package.tar.gz"
            archive.write_bytes(b"archive bytes")
            checksum = root.parent / "package.tar.gz.sha256"
            checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  package.tar.gz\n", encoding="utf-8")

            with mock.patch.object(module, "verify_target", side_effect=AssertionError("binary verifier should not run")):
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "verify-loader-artifacts.py",
                        "--target",
                        "linux-server",
                        "--package-root",
                        str(root),
                        "--package-target",
                        "linux-server",
                        "--package-archive",
                        str(archive),
                        "--package-only",
                        "--format",
                        "json",
                    ],
                ):
                    with mock.patch("sys.stdout", new_callable=__import__("io").StringIO) as stdout:
                        code = module.main()

        self.assertEqual(code, 0)
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["packages"]["linux-server"]["passed"])
        self.assertTrue(report["packages"]["linux-server-archive"]["passed"])

    def test_package_only_requires_package_root(self):
        with self.assertRaises(SystemExit):
            with mock.patch.object(sys, "argv", ["verify-loader-artifacts.py", "--package-only"]):
                module.main()

    def test_package_archive_sha256_requires_package_archive(self):
        with self.assertRaises(SystemExit):
            with mock.patch.object(sys, "argv", ["verify-loader-artifacts.py", "--package-archive-sha256", "/tmp/package.sha256"]):
                module.main()


if __name__ == "__main__":
    unittest.main()
