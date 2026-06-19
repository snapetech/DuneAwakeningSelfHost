#!/usr/bin/env python3
import importlib.util
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
            }
        )

        self.assertIn("loader_artifacts_ok=false", text)
        self.assertIn("linux-client passed=true", text)
        self.assertIn("windows-client passed=false", text)
        self.assertIn("VerQueryValueW", text)

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


if __name__ == "__main__":
    unittest.main()
