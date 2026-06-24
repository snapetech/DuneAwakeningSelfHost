#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "brt-dd-trace.sh"
ANCHORS = ROOT / "scripts" / "research" / "DumpBrtTraceAnchors.java"


class BrtDdTraceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_arm_instruction_does_not_preclassify_missing_rpc_as_client_requirement(self):
        self.assertIn("SERVER-RPC-ENTRY/SERVER-RPC-EXEC fires", self.source)
        self.assertIn("normal request as not observed", self.source)
        self.assertIn("server-side emulation path", self.source)
        self.assertIn("scripts/classify-brt-dd-trace.py $trace_log --format json", self.source)
        self.assertNotIn("the block\nis client-side", self.source)

    def test_anchor_dumper_frames_keystone_as_rpc_arrival(self):
        source = ANCHORS.read_text(encoding="utf-8")
        self.assertIn("RPC arrival", source)
        self.assertIn("did the request reach the server", source)
        self.assertNotIn("client-vs-server block", source)


if __name__ == "__main__":
    unittest.main()
