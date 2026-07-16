#!/usr/bin/env python3
import json
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"admin"))
import gameplay_presets

BASE="""[/Script/DuneSandbox.CoriolisSubsystem]
m_CycleDurationInDays=7

[/Script/DuneSandbox.SandwormSettings]
; preserve me
ThreatScale=1.0
WalkingThreatPerSec=15

[/Script/DuneSandbox.SandStormConfig]
m_bCoriolisAutoSpawnEnabled=False
"""

class GameplayPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.temp.name); self.config=self.root/"config";self.config.mkdir();self.backups=self.root/"backups"
        for name in gameplay_presets.TARGETS: (self.config/name).write_text(BASE,encoding="utf-8")
        self.catalog=self.root/"presets.json"; self.catalog.write_text(json.dumps({"schemaVersion":1,"presets":[{"id":"test-preset","label":"Test","settings":[{"group":"Sandworm","key":"ThreatScale","value":"2.5"},{"group":"TimeOfDay","key":"m_DayLengthMinutes","value":"90"}]}]}),encoding="utf-8")
    def tearDown(self): self.temp.cleanup()

    def test_shipped_catalog_validates_all_presets(self):
        catalog=gameplay_presets.load_catalog(ROOT/"config/gameplay-presets.json")
        self.assertGreaterEqual(len(catalog["presets"]),9)
        self.assertEqual({"calm-worms","standard-worms","wormageddon"}-{p["id"] for p in catalog["presets"]},set())

    def test_value_and_catalog_validation(self):
        with self.assertRaises(ValueError): gameplay_presets.validate_value("unknown","1")
        with self.assertRaises(ValueError): gameplay_presets.validate_value("m_DayLengthMinutes","0")
        with self.assertRaises(ValueError): gameplay_presets.validate_value("m_bHydrationEnabled","maybe")

    def test_merge_updates_and_adds_without_losing_comments(self):
        preset=gameplay_presets.load_catalog(self.catalog)["presets"][0]
        merged=gameplay_presets.merge(BASE,preset["settings"])
        self.assertIn("; preserve me",merged);self.assertIn("ThreatScale=2.5",merged);self.assertEqual(merged.count("ThreatScale="),1);self.assertIn("[/Script/DuneSandbox.TimeOfDaySettings]\nm_DayLengthMinutes=90",merged)

    def test_plan_is_diff_only_and_restart_explicit(self):
        result=gameplay_presets.plan(self.config,self.catalog,"test-preset","UserGame.ini")
        self.assertTrue(result["dryRun"]);self.assertTrue(result["changed"]);self.assertTrue(result["restartRequired"]);self.assertTrue(result["landsraadCycleValidated"]);self.assertEqual(len(result["changes"]),2)
        self.assertEqual((self.config/"UserGame.ini").read_text(),BASE)

    def test_landsraad_cycle_guard_refuses_bad_duration(self):
        (self.config/"UserGame.deep-desert-coriolis.ini").write_text(BASE.replace("m_CycleDurationInDays=7","m_CycleDurationInDays=999"))
        with self.assertRaisesRegex(ValueError,"must keep"): gameplay_presets.plan(self.config,self.catalog,"test-preset","UserGame.ini")

    def test_apply_backup_idempotency_and_rollback(self):
        result=gameplay_presets.apply(self.config,self.catalog,"test-preset","UserGame.ini",self.backups)
        self.assertFalse(result["dryRun"]);self.assertTrue(pathlib.Path(result["backup"]).is_file());self.assertIn("ThreatScale=2.5",(self.config/"UserGame.ini").read_text())
        same=gameplay_presets.apply(self.config,self.catalog,"test-preset","UserGame.ini",self.backups);self.assertTrue(same["idempotent"])
        rolled=gameplay_presets.rollback(self.config,result["backup"],self.backups);self.assertTrue(rolled["ok"]);self.assertEqual((self.config/"UserGame.ini").read_text(),BASE)

    def test_target_and_rollback_paths_are_bounded(self):
        with self.assertRaises(ValueError): gameplay_presets.plan(self.config,self.catalog,"test-preset","../../etc/passwd")
        outside=self.root/"UserGame.ini";outside.write_text(BASE)
        with self.assertRaises(ValueError): gameplay_presets.rollback(self.config,outside,self.backups)

if __name__=="__main__": unittest.main()
