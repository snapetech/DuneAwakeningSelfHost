#!/usr/bin/env python3
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-base-cap-tooling.py"

spec = importlib.util.spec_from_file_location("plan_base_cap_tooling", SCRIPT)
tooling = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tooling)


class BaseCapToolingTest(unittest.TestCase):
    def test_current_config_classifies_ready_and_unproven_surfaces(self):
        report = tooling.build_report(ROOT / "config" / "UserGame.ini")
        surfaces = report["surfaces"]
        self.assertEqual("buildable", surfaces["logoffTimerRuntimePatch"]["status"])
        self.assertTrue(surfaces["logoffTimerRuntimePatch"]["ready"])
        self.assertEqual("buildable", surfaces["subfiefTotemCap"]["status"])
        self.assertTrue(surfaces["subfiefTotemCap"]["ready"])
        self.assertEqual("partially-buildable", surfaces["brtDeepDesertBackupRestore"]["status"])
        self.assertTrue(surfaces["brtDeepDesertBackupRestore"]["ready"])
        self.assertEqual("lab-ready", surfaces["ue4ssBuildingPieceCap"]["status"])
        self.assertTrue(surfaces["ue4ssBuildingPieceCap"]["ready"])
        self.assertEqual("moderate", surfaces["ue4ssBuildingPieceCap"]["confidence"])
        self.assertEqual("needs-proof", surfaces["horizontalExtensionCap"]["status"])
        self.assertFalse(surfaces["horizontalExtensionCap"]["ready"])
        self.assertTrue(surfaces["horizontalExtensionCap"]["configCandidatePresent"])

    def test_config_parser_keeps_duplicate_append_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "UserGame.ini"
            path.write_text(
                "[/Script/DuneSandbox.BuildingSettings]\n"
                "m_MaxNumLandclaimSegments=30\n"
                "+m_BaseBackupToolMapRestriction=(Name=\"DeepDesert\")\n"
                "+m_BaseBackupToolMapRestriction=(Name=\"DeepDesert_1\")\n",
                encoding="utf-8",
            )
            values = tooling.config_values(path)
        self.assertEqual(["30"], values["m_MaxNumLandclaimSegments"])
        self.assertEqual(
            ["(Name=\"DeepDesert\")", "(Name=\"DeepDesert_1\")"],
            values["m_BaseBackupToolMapRestriction"],
        )


if __name__ == "__main__":
    unittest.main()
