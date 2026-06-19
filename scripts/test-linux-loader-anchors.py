#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "summarize-linux-loader-anchors.py",
    ROOT / "analysis" / "summarize-linux-loader-anchors.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("summarize_linux_loader_anchors", SCRIPT)
anchors = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(anchors)


class LinuxLoaderAnchorTests(unittest.TestCase):
    def test_containing_c_string(self):
        data = b"\x00alpha-BravoCharlie\x00tail"
        found = anchors.containing_c_string(data, 9, 64)

        self.assertEqual(found["offset"], 1)
        self.assertEqual(found["text"], "alpha-BravoCharlie")

    def test_nearby_strings_prefers_containing_string(self):
        data = b"left\x00needle_target\x00right_context\x00"
        rows = anchors.nearby_strings(data, data.index(b"target"), 32, 5, 3)

        self.assertEqual(rows[0]["text"], "needle_target")
        self.assertTrue(any(row["text"] == "right_context" for row in rows))


if __name__ == "__main__":
    unittest.main()
