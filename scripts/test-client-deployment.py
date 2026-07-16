#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/client-deployment.py"
CONFIRM = "MUTATE DUNE CLIENT FILES"
ADOPT_CONFIRM = "ADOPT EXISTING DUNE CLIENT FILES"


def load_manager():
    spec = importlib.util.spec_from_file_location("client_deployment", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClientDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.game = self.root / "game"
        self.bin = self.game / "DuneSandbox/Binaries/Win64"
        self.paks = self.game / "DuneSandbox/Content/Paks"
        self.bin.mkdir(parents=True); self.paks.mkdir(parents=True)
        (self.bin / "DuneSandbox-Win64-Shipping.exe").write_bytes(b"current-game")
        (self.bin / "version.dll").write_bytes(b"original-version")
        self.loader = self.root / "loader.dll"; self.loader.write_bytes(b"new-loader")
        self.pak = self.root / "overlay.pak"; self.pak.write_bytes(b"overlay")
        self.state = self.root / "state"

    def tearDown(self): self.tmp.cleanup()

    def invoke(self, *args, ok=True):
        command = [str(SCRIPT), "--state-root", str(self.state), *map(str, args)]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ok and result.returncode: self.fail(f"{command}\n{result.stdout}\n{result.stderr}")
        return result

    def files(self):
        return ["--file", f"{self.loader}::DuneSandbox/Binaries/Win64/version.dll",
                "--file", f"{self.pak}::DuneSandbox/Content/Paks/zzz_dash_test.pak"]

    def test_plan_is_non_mutating(self):
        result = self.invoke("plan", "--game-dir", self.game, "--deployment", "test", *self.files())
        self.assertTrue(json.loads(result.stdout)["mutationRequired"])
        self.assertFalse(self.state.exists())
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"original-version")

    def test_install_verify_and_rollback(self):
        self.invoke("install", "--game-dir", self.game, "--deployment", "test", *self.files(), "--confirm", CONFIRM)
        self.assertEqual((self.bin / "version.dll").read_bytes(), b"new-loader")
        self.assertEqual((self.paks / "zzz_dash_test.pak").read_bytes(), b"overlay")
        manifest=json.loads((self.state/"test/manifest.json").read_text())
        self.assertEqual(manifest["status"],"installed")
        self.assertTrue((self.state/"test/backups/DuneSandbox/Binaries/Win64/version.dll").is_file())
        self.assertEqual(self.invoke("verify","--deployment","test").returncode,0)
        self.invoke("rollback","--deployment","test","--confirm",CONFIRM)
        self.assertEqual((self.bin/"version.dll").read_bytes(),b"original-version")
        self.assertFalse((self.paks/"zzz_dash_test.pak").exists())

    def test_confirmation_and_target_allowlist(self):
        result=self.invoke("install","--game-dir",self.game,"--deployment","bad",*self.files(),"--confirm","yes",ok=False)
        self.assertNotEqual(result.returncode,0); self.assertFalse(self.state.exists())
        result=self.invoke("plan","--game-dir",self.game,"--deployment","bad","--file",f"{self.pak}::DuneSandbox/Content/Paks/Systems.pak",ok=False)
        self.assertNotEqual(result.returncode,0)

    def test_rollback_refuses_drift(self):
        self.invoke("install","--game-dir",self.game,"--deployment","test",*self.files(),"--confirm",CONFIRM)
        (self.bin/"version.dll").write_bytes(b"foreign-change")
        result=self.invoke("rollback","--deployment","test","--confirm",CONFIRM,ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.bin/"version.dll").read_bytes(),b"foreign-change")

    def test_active_target_collision_is_rejected(self):
        self.invoke("install","--game-dir",self.game,"--deployment","one",*self.files(),"--confirm",CONFIRM)
        result=self.invoke("install","--game-dir",self.game,"--deployment","two",*self.files(),"--confirm",CONFIRM,ok=False)
        self.assertNotEqual(result.returncode,0)

    def test_game_update_invalidates_verify_and_rollback(self):
        self.invoke("install","--game-dir",self.game,"--deployment","test",*self.files(),"--confirm",CONFIRM)
        (self.bin/"DuneSandbox-Win64-Shipping.exe").write_bytes(b"updated-game")
        self.assertNotEqual(self.invoke("verify","--deployment","test",ok=False).returncode,0)
        result=self.invoke("rollback","--deployment","test","--confirm",CONFIRM,ok=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.bin/"version.dll").read_bytes(),b"new-loader")

    def test_running_client_detection_reads_process_cmdline(self):
        proc = self.root / "proc"
        (proc / "321").mkdir(parents=True)
        (proc / "321/cmdline").write_bytes(b"wine\0DuneSandbox-Win64-Shipping.exe\0")
        (proc / "654").mkdir(parents=True)
        (proc / "654/cmdline").write_bytes(b"unrelated\0")
        self.assertEqual(
            load_manager().running_client_processes(proc),
            [{"pid": 321, "command": "wine DuneSandbox-Win64-Shipping.exe"}],
        )

    def test_adopt_legacy_install_then_rollback(self):
        original=self.root/"original-version.dll"; original.write_bytes(b"original-version")
        (self.bin/"version.dll").write_bytes(b"legacy-probe")
        sidecar=self.bin/"dune-win-client-probe.env"; sidecar.write_bytes(b"legacy-sidecar")
        self.invoke("adopt","--game-dir",self.game,"--deployment","legacy",
                    "--installed",f"DuneSandbox/Binaries/Win64/version.dll::{original}",
                    "--installed","DuneSandbox/Binaries/Win64/dune-win-client-probe.env::ABSENT",
                    "--confirm",ADOPT_CONFIRM)
        self.assertEqual(self.invoke("verify","--deployment","legacy").returncode,0)
        self.invoke("rollback","--deployment","legacy","--confirm",CONFIRM)
        self.assertEqual((self.bin/"version.dll").read_bytes(),b"original-version")
        self.assertFalse(sidecar.exists())


if __name__ == "__main__": unittest.main()
