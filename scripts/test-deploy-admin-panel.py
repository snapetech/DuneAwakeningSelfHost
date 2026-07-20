#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = (ROOT / "scripts" / "deploy-admin-panel.sh").read_text(encoding="utf-8")
ADMIN = (ROOT / "admin" / "admin_panel.py").read_text(encoding="utf-8")


class DeployAdminPanelSafetyTests(unittest.TestCase):
    def test_deploy_holds_marker_before_recreate_and_repairs_after(self):
        marker = DEPLOY.index('maintenance_marker_created=true')
        drain = DEPLOY.index('wait_for_autoscaler_idle', marker)
        recreate = DEPLOY.index('up -d --no-deps --force-recreate admin-panel', drain)
        repair = DEPLOY.index('repair_running_map_runtime_patches', recreate)
        self.assertLess(marker, drain)
        self.assertLess(drain, recreate)
        self.assertLess(recreate, repair)
        self.assertIn('trap cleanup EXIT', DEPLOY)

    def test_runtime_repair_requires_apply_and_dry_run(self):
        match = re.search(r'^repair_running_map_runtime_patches\(\) \{\n(?P<body>.*?)\n\}', DEPLOY, re.M | re.S)
        self.assertIsNotNone(match)
        body = match.group('body')
        self.assertIn('patch-logoff-timers-runtime.sh" --local', body)
        self.assertIn('patch-logoff-timers-runtime.sh" --local --dry-run', body)

    def test_autoscaler_observes_shared_maintenance_marker(self):
        self.assertIn('AUTOSCALER_MAINTENANCE_MARKER = pathlib.Path(', ADMIN)
        self.assertGreaterEqual(ADMIN.count('marker_held = autoscaler_maintenance_requested()'), 2)
        self.assertGreaterEqual(ADMIN.count('if restart_executing or marker_held:'), 2)


if __name__ == "__main__":
    unittest.main()
