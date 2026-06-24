#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-static-metadata-recovery.py"

spec = importlib.util.spec_from_file_location("static_metadata_recovery", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class StaticMetadataRecoveryTests(unittest.TestCase):
    def write_source_context(self, root, contexts):
        path = root / "source-context.json"
        path.write_text(
            json.dumps({"targets": [{"name": "AsyncLoading2Cpp"}], "contexts": contexts}),
            encoding="utf-8",
        )
        return path

    def test_reports_stripped_metadata_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = self.write_source_context(Path(tmp), [])
            with mock.patch.object(module, "run_text") as run_text:
                run_text.side_effect = [
                    ("", "", 0),
                    ("", "no symbols", 1),
                ]

                summary = module.summarize("/tmp/server", context)

        self.assertFalse(summary["complete"])
        self.assertEqual(summary["debugLines"]["lineCount"], 0)
        self.assertEqual(summary["symbolAnchors"]["anchorSymbolCount"], 0)
        self.assertEqual(summary["sourcePointerContext"]["contextCount"], 0)
        self.assertIn("no decoded DWARF", summary["blockers"][0])

    def test_marks_complete_when_metadata_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = self.write_source_context(Path(tmp), [{"function": "0x1234"}])
            with mock.patch.object(module, "run_text") as run_text:
                run_text.side_effect = [
                    ("UObjectGlobals.cpp 123 0x1000\n", "", 0),
                    ("0000000000010000 T StaticLoadObject\n", "", 0),
                ]

                summary = module.summarize("/tmp/server", context)

        self.assertTrue(summary["complete"])
        self.assertEqual(summary["symbolAnchors"]["anchorSymbolCount"], 1)
        self.assertEqual(summary["blockers"], [])


if __name__ == "__main__":
    unittest.main()
