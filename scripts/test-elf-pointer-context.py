#!/usr/bin/env python3
import importlib.util
import contextlib
import io
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "research" / "summarize-elf-pointer-context.py"


spec = importlib.util.spec_from_file_location("summarize_elf_pointer_context", SCRIPT)
ptrctx = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ptrctx)


class ElfPointerContextTests(unittest.TestCase):
    def test_find_qword_refs(self):
        data = b"\x00" * 4 + struct.pack("<Q", 0x12345678) + b"\x00" * 4
        self.assertEqual(ptrctx.find_qword_refs(data, 0x12345678), [4])

    def test_parse_targets(self):
        self.assertEqual(ptrctx.parse_targets(["name=0x20", "other=32"]), [("name", 32), ("other", 32)])

    def test_cli_requires_target_or_context(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    ptrctx.main([tmp.name])


if __name__ == "__main__":
    unittest.main()
