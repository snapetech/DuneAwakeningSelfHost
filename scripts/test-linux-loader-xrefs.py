#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "summarize-linux-loader-xrefs.py",
    ROOT / "analysis" / "summarize-linux-loader-xrefs.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("summarize_linux_loader_xrefs", SCRIPT)
xrefs = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(xrefs)


class LinuxLoaderXrefTests(unittest.TestCase):
    def test_decodes_rip_relative_lea(self):
        base = 0x1000
        target = 0x2000
        disp = target - (base + 7)
        data = b"\x48\x8d\x05" + struct.pack("<i", disp)

        refs = xrefs.decode_rip_memory_refs(data, 0, base)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["kind"], "rip-memory")
        self.assertEqual(refs[0]["targetVaddr"], target)
        self.assertEqual(refs[0]["xrefVaddr"], base)
        self.assertEqual(refs[0]["dispOffset"], 3)

    def test_decodes_rel_call(self):
        base = 0x3000
        target = 0x3400
        disp = target - (base + 5)
        data = b"\xe8" + struct.pack("<i", disp)

        refs = xrefs.decode_rel_refs(data, 0, base)

        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["kind"], "rel-call-jump")
        self.assertEqual(refs[0]["targetVaddr"], target)
        self.assertEqual(refs[0]["dispOffset"], 1)

    def test_scans_executable_segment_for_target(self):
        base = 0x1000
        target_vaddr = 0x2000
        disp = target_vaddr - (base + 7)
        data = b"\x48\x8d\x05" + struct.pack("<i", disp) + b"\x90"
        segments = [xrefs.Segment(file_offset=0, file_size=len(data), vaddr=base, mem_size=len(data), flags=xrefs.PF_X)]
        target = xrefs.Target(
            name="PerformCanBePlaced",
            category="brt",
            kind="string",
            file_offset=0x2000,
            image_offset=0x2000,
            vaddr=target_vaddr,
            source="/game/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping",
        )

        found = xrefs.scan_xrefs(data, segments, [target])

        self.assertEqual(len(found[target]), 1)
        self.assertEqual(found[target][0]["xrefVaddr"], base)

        summary = xrefs.serializable(data, segments, [target], found, signature_prefix=0, signature_suffix=1)
        self.assertEqual(
            summary["targets"][0]["source"],
            "/game/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping",
        )
        seed = summary["targets"][0]["xrefs"][0]["signatureSeed"]
        self.assertEqual(seed["fileOffset"], "0x0")
        self.assertEqual(seed["pattern"], "48 8d 05 ?? ?? ?? ?? 90")

    def test_manual_targets_inherit_scanned_binary_source(self):
        segments = [xrefs.Segment(file_offset=0, file_size=0x3000, vaddr=0, mem_size=0x3000, flags=xrefs.PF_X)]

        targets = xrefs.targets_from_args(["GEngine=0x2000"], [], segments, default_source="/tmp/DuneSandboxServer-Linux-Shipping")
        summary = xrefs.serializable(
            b"\x90" * 0x3000,
            segments,
            targets,
            {},
            binary_path="/tmp/DuneSandboxServer-Linux-Shipping",
        )

        self.assertEqual(targets[0].source, "/tmp/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(summary["format"], "dune-linux-loader-xrefs/v1")
        self.assertEqual(summary["binary"], "/tmp/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(summary["targets"][0]["source"], "/tmp/DuneSandboxServer-Linux-Shipping")


if __name__ == "__main__":
    unittest.main()
