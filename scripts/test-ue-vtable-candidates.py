#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue-vtable-candidates.py"


class UeVtableCandidateSummaryTests(unittest.TestCase):
    def run_summary(self, log_text, *extra_args):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "loader.log"
            log_path.write_text(log_text, encoding="utf-8")
            result = subprocess.run(
                ["python3", str(SCRIPT), str(log_path), *extra_args],
                cwd=ROOT,
                text=True,
                check=True,
                stdout=subprocess.PIPE,
            )
            return result.stdout

    def test_json_summary_ranks_heuristic_and_stable_slots(self):
        log = "\n".join(
            [
                "event=ue-process-event-vtable-scan status=scanned platform=linux readableSlots=3 executableSlots=3 zeroSlots=0",
                "event=ue-process-event-vtable-scan status=scanned platform=linux readableSlots=3 executableSlots=3 zeroSlots=0",
                "event=ue-process-event-vtable-candidate platform=linux objectName=Foo className=Class vtable=0x100 slot=67 target=0x500 imageOffset=0x1500 fileOffset=0x500 map=/game/DuneSandbox targetName=ProcessEvent targetSource=vtable-candidate",
                "event=ue-process-event-vtable-candidate platform=linux objectName=Bar className=Class vtable=0x200 slot=67 target=0x500 imageOffset=0x1500 fileOffset=0x500 map=/game/DuneSandbox targetName=ProcessEvent targetSource=vtable-candidate",
                "event=ue-process-event-vtable-candidate platform=linux objectName=Foo className=Class vtable=0x100 slot=3 target=0x700 imageOffset=0x1700 fileOffset=0x700 map=/game/DuneSandbox targetName=ProcessEvent targetSource=vtable-candidate",
                "event=ue-process-event-vtable-candidate platform=linux objectName=Bar className=Function vtable=0x200 slot=3 target=0x710 imageOffset=0x1710 fileOffset=0x710 map=/game/DuneSandbox targetName=ProcessEvent targetSource=vtable-candidate",
            ]
        )
        data = json.loads(self.run_summary(log, "--heuristic-slot", "67"))
        self.assertEqual("dune-ue-vtable-candidates/v1", data["schemaVersion"])
        self.assertEqual(4, data["candidateCount"])
        self.assertEqual(2, data["scanCount"])
        self.assertEqual({"scanned": 2}, data["scanStatusCounts"])
        self.assertEqual(2, data["slotCount"])
        self.assertEqual(3, data["targetCount"])
        self.assertEqual(67, data["hookProbeShortlist"][0]["slot"])
        self.assertEqual("0x1500", data["hookProbeShortlist"][0]["topTarget"]["imageOffset"])
        self.assertIn("ue4-uobject-process-event-slot-heuristic", data["hookProbeShortlist"][0]["reasons"])

    def test_markdown_summary_contains_shortlist_table(self):
        log = "\n".join(
            [
                "event=ue-process-event-vtable-scan status=vtable-unmapped platform=windows readableSlots=0 executableSlots=0",
                "event=ue-process-event-vtable-candidate platform=windows objectName=Baz className=Object vtable=0x300 slot=64 target=0x800 rva=0x1800 module=DuneSandbox-Win64-Shipping.exe targetName=ProcessEvent targetSource=vtable-candidate",
            ]
        )
        output = self.run_summary(log, "--format", "markdown", "--limit", "4")
        self.assertIn("# UE VTable Candidate Summary", output)
        self.assertIn("Hook Probe Shortlist", output)
        self.assertIn("| 1 | 64 |", output)
        self.assertIn("`0x1800`", output)


if __name__ == "__main__":
    unittest.main()
