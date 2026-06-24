#!/usr/bin/env python3
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-ue4ss-package-stimulus.py"

spec = importlib.util.spec_from_file_location("package_stimulus_plan", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PackageStimulusPlanTests(unittest.TestCase):
    def test_loader_dry_run_is_safe_but_not_promotable_stimulus(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = Path(tmp) / "loader.c"
            trace = Path(tmp) / "ue4ss-package-remote-trace.sh"
            start = Path(tmp) / "start-map-with-post-hooks.sh"
            recover = Path(tmp) / "recover-map.sh"
            loader.write_text(
                """
                const char *a = "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_DRY_RUN";
                const char *b = "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE";
                const char *c = "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL";
                int x = lua_load_asset_backend_package_target_image;
                int call_frame_ready = path && target != 0 && lua_load_asset_backend_package_target_image;
                """,
                encoding="utf-8",
            )
            trace.write_text("require_zero_players arm\nconnected_players\n", encoding="utf-8")
            start.write_text(
                "DUNE_PRODUCTION_HOSTNAME=kspls0\nrestart-post-start-health.sh\npatch-logoff-timers-runtime.sh --local --dry-run\n",
                encoding="utf-8",
            )
            recover.write_text("restart-post-start-health.sh\n", encoding="utf-8")

            original = module.GUARDED_OPERATION_SCRIPTS
            module.GUARDED_OPERATION_SCRIPTS = (str(trace), str(start), str(recover))
            try:
                plan = module.build_plan(loader)
            finally:
                module.GUARDED_OPERATION_SCRIPTS = original

        self.assertFalse(plan["loaderOnlyStimulusCanHitTargetPackageLoad"])
        self.assertTrue(plan["loaderOnlyStimulusSafe"])
        self.assertEqual(plan["recommendedCandidate"], "operator-client-map-entry")
        self.assertEqual(plan["originClassification"]["status"], "unknown")
        self.assertEqual(
            plan["originClassification"]["serverSideFallbackCandidate"],
            "server-side-client-call-emulation",
        )
        dry_run = plan["candidates"][0]
        self.assertEqual(dry_run["id"], "loader-package-dry-run")
        self.assertFalse(dry_run["promotableStimulus"])
        self.assertIn("cannot invoke target package loading", dry_run["reason"])
        client_entry = plan["candidates"][1]
        self.assertEqual(client_entry["id"], "operator-client-map-entry")
        self.assertEqual(client_entry["kind"], "client-server-reachability-probe")
        self.assertEqual(client_entry["rank"], 1)
        self.assertIn("server-side", client_entry["reason"])
        self.assertTrue(client_entry["evidence"]["remoteTraceHasZeroPlayerGuard"])
        server_emulation = plan["candidates"][2]
        self.assertEqual(server_emulation["id"], "server-side-client-call-emulation")
        self.assertEqual(server_emulation["rank"], 2)
        self.assertEqual(server_emulation["safe"], "requires-captured-call-frame")
        guarded_restart = plan["candidates"][4]
        self.assertEqual(guarded_restart["id"], "guarded-map-recreate")
        self.assertEqual(guarded_restart["safe"], "last-resort")
        self.assertTrue(guarded_restart["evidence"]["startMapWrapperRunsPostStartHooks"])

    def test_packaged_src_loader_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "dune_server_probe_loader.c").write_text(
                """
                const char *a = "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_DRY_RUN";
                const char *b = "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE";
                const char *c = "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL";
                int x = lua_load_asset_backend_package_target_image;
                int call_frame_ready = path && target != 0 && lua_load_asset_backend_package_target_image;
                """,
                encoding="utf-8",
            )
            old_cwd = Path.cwd()
            os.chdir(root)
            try:
                plan = module.build_plan("tools/linux-server-loader/dune_server_probe_loader.c")
            finally:
                os.chdir(old_cwd)

        self.assertEqual(plan["loaderGates"]["path"], "src/dune_server_probe_loader.c")
        self.assertTrue(plan["loaderOnlyStimulusSafe"])


if __name__ == "__main__":
    unittest.main()
