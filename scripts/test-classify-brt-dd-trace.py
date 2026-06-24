#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "classify-brt-dd-trace.py"
SPEC = importlib.util.spec_from_file_location("classify_brt_dd_trace", SCRIPT)
classifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(classifier)


class ClassifyBrtDdTraceTests(unittest.TestCase):
    def test_missing_rpc_markers_selects_server_side_emulation(self):
        result = classifier.classify_trace(
            "BRT_PLACE_TRACE armed\nBRT_PLACE hit RESTRICTION-GATE rdi=0x1\n",
            "/tmp/brt-place.log",
        )
        self.assertFalse(result["rpcReachedServer"])
        self.assertEqual(result["rpcClassification"], "normal-request-not-observed")
        self.assertEqual(result["emulatorRpcClassification"], "normal-request-not-observed")
        self.assertTrue(result["serverSideEmulationAllowed"])
        self.assertFalse(result["clientModificationRequired"])
        self.assertEqual(result["nextAction"], "server-side-request-emulation")

    def test_rpc_markers_select_reached_server_branch(self):
        result = classifier.classify_trace(
            "BRT_PLACE hit SERVER-RPC-ENTRY request-reached-server rdi=0x1\n",
            "/tmp/brt-place.log",
        )
        self.assertTrue(result["rpcReachedServer"])
        self.assertEqual(result["rpcClassification"], "normal-request-reached-server")
        self.assertEqual(result["emulatorRpcClassification"], "operator-controlled-fallback")
        self.assertFalse(result["serverSideEmulationAllowed"])
        self.assertFalse(result["clientModificationRequired"])
        self.assertEqual(result["nextAction"], "fix-reached-server-side-branch")
        self.assertEqual(result["markerHits"][0]["marker"], "SERVER-RPC-ENTRY")

    def test_uprobe_rpc_markers_select_reached_server_branch(self):
        result = classifier.classify_trace(
            "brt_rpc_impl_server_request_basebackup_args: rdi=0x1 rsi=0x44 rdx=0x8\n",
            "/tmp/brt-dd-live-canary-trace.log",
        )
        self.assertTrue(result["rpcReachedServer"])
        self.assertEqual(result["rpcClassification"], "normal-request-reached-server")
        self.assertEqual(result["emulatorRpcClassification"], "operator-controlled-fallback")
        self.assertFalse(result["serverSideEmulationAllowed"])
        self.assertEqual(result["markerHits"][0]["marker"], "brt_rpc_impl_server_request_basebackup")

    def test_cli_outputs_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "trace.log"
            log.write_text("BRT_PLACE hit SERVER-RPC-EXEC request-dispatched-to-native-exec\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(log)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
        result = json.loads(proc.stdout)
        self.assertTrue(result["rpcReachedServer"])
        self.assertEqual(result["markerHits"][0]["marker"], "SERVER-RPC-EXEC")


if __name__ == "__main__":
    unittest.main()
