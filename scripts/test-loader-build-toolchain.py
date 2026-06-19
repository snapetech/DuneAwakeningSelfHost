#!/usr/bin/env python3
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ensure-loader-build-toolchain.sh"
MAKEFILE = ROOT / "Makefile"


class LoaderBuildToolchainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_script_checks_linux_and_windows_loader_requirements(self):
        for marker in [
            "linux_loader_toolchain=ok",
            "windows_loader_toolchain=ok",
            "cmake",
            "ninja-or-make",
            "c-compiler",
            "x86_64-w64-mingw32-gcc",
            "ld.lld",
            "/usr/lib/wine/x86_64-windows/libkernel32.a",
        ]:
            self.assertIn(marker, self.source)

    def test_script_has_explicit_install_mode_with_common_package_managers(self):
        for marker in [
            "--install",
            "apt-get install -y",
            "dnf install -y",
            "pacman -S --needed --noconfirm",
            "zypper --non-interactive install",
            "mingw-w64",
            "mingw64-gcc",
            "mingw-w64-gcc",
            "lld",
        ]:
            self.assertIn(marker, self.source)

    def test_makefile_exposes_toolchain_targets(self):
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("loader-build-toolchain-check", makefile)
        self.assertIn("loader-build-toolchain-install", makefile)
        self.assertIn("./scripts/ensure-loader-build-toolchain.sh --check", makefile)
        self.assertIn("./scripts/ensure-loader-build-toolchain.sh --install", makefile)

    def test_loader_build_scripts_attempt_install_before_building(self):
        build_scripts = [
            ROOT / "scripts" / "build-linux-server-loader.sh",
            ROOT / "scripts" / "build-linux-client-loader.sh",
            ROOT / "scripts" / "build-windows-client-loader.sh",
        ]
        for script in build_scripts:
            with self.subTest(script=script.name):
                text = script.read_text(encoding="utf-8")
                self.assertIn("ensure-loader-build-toolchain.sh", text)
                self.assertIn("--install", text)

    def test_current_host_has_required_loader_toolchain(self):
        result = subprocess.run(
            [str(SCRIPT), "--check"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("linux_loader_toolchain=ok", result.stdout)
        self.assertIn("windows_loader_toolchain=ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
