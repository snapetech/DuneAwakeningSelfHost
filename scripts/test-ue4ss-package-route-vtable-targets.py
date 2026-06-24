#!/usr/bin/env python3
import importlib.util
import struct
import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-route-vtable-targets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("route_vtable_targets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Section:
    name: str
    addr: int
    offset: int
    size: int

    def contains_addr(self, addr):
        return self.addr <= addr < self.addr + self.size

    def contains_file_offset(self, offset):
        return self.offset <= offset < self.offset + self.size


class FakePointerContext:
    def section_for_addr(self, sections, addr):
        return next((section for section in sections if section.contains_addr(addr)), None)

    def section_for_file_offset(self, sections, offset):
        return next((section for section in sections if section.contains_file_offset(offset)), None)

    def qword_at_addr(self, data, sections, relocations, addr):
        if addr in relocations:
            return relocations[addr], "rela"
        section = self.section_for_addr(sections, addr)
        if section is None:
            return None, ""
        file_offset = section.offset + (addr - section.addr)
        if file_offset + 8 > len(data):
            return None, ""
        return struct.unpack_from("<Q", data, file_offset)[0], "file"

    def classify_value(self, data, sections, symbols, value):
        del data
        section = self.section_for_addr(sections, value)
        return {
            "value": f"0x{value:x}",
            "section": section.name if section else "",
            "flags": "AX" if section and section.name == ".text" else ("A" if section else ""),
            "symbols": symbols.get(value, [])[:4],
            "string": "",
        }

    def find_qword_refs(self, data, target):
        pattern = struct.pack("<Q", target)
        hits = []
        pos = 0
        while True:
            hit = data.find(pattern, pos)
            if hit < 0:
                return hits
            hits.append(hit)
            pos = hit + 1


class PackageRouteVtableTargetTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_parse_slot_target_requires_target_and_slot(self):
        parsed = self.module.parse_slot_target("wrapper=0x129d5880@0x3d8")
        self.assertEqual(parsed["name"], "wrapper")
        self.assertEqual(parsed["target"], 0x129D5880)
        self.assertEqual(parsed["slotOffset"], 0x3D8)
        with self.assertRaises(ValueError):
            self.module.parse_slot_target("wrapper=0x129d5880")

    def test_infers_vtable_base_from_relocation_slot(self):
        ptrctx = FakePointerContext()
        data = bytearray(0x2000)
        sections = [
            Section(".data.rel.ro", 0x500000, 0, 0x1000),
            Section(".text", 0x100000, 0x1000, 0x1000),
        ]
        symbols = {
            0x500000: ["vtable for SyntheticPackageRoute"],
            0x101000: ["SyntheticPackageRoute::slot3a0()"],
            0x101100: ["SyntheticPackageRoute::slot3d8()"],
        }
        relocations = {
            0x500000 + 0x3A0: 0x101000,
            0x500000 + 0x3D8: 0x101100,
        }

        summary = self.module.summarize_slot_target(
            ptrctx,
            bytes(data),
            sections,
            symbols,
            relocations,
            {"name": "wrapper", "target": 0x101100, "slotOffset": 0x3D8},
            [0x3A0, 0x3D8],
            1,
        )

        self.assertEqual(summary["refCount"], 1)
        ref = summary["refs"][0]
        self.assertEqual(ref["inferredVtableBase"], "0x500000")
        self.assertEqual(ref["vtableSymbols"], ["vtable for SyntheticPackageRoute"])
        self.assertEqual(ref["companionSlots"][0]["slotOffset"], "0x3a0")
        self.assertEqual(ref["companionSlots"][0]["value"], "0x101000")
        self.assertEqual(ref["companionSlots"][0]["symbols"], ["SyntheticPackageRoute::slot3a0()"])
        self.assertEqual(ref["companionSlots"][1]["slotOffset"], "0x3d8")
        self.assertEqual(ref["companionSlots"][1]["value"], "0x101100")

    def test_markdown_renders_companion_slots(self):
        rendered = self.module.markdown(
            {
                "ready": True,
                "binary": "/tmp/server",
                "companionSlots": ["0x3a0", "0x3d8"],
                "blockers": [],
                "targets": [
                    {
                        "name": "wrapper",
                        "target": "0x101100",
                        "expectedSlotOffset": "0x3d8",
                        "refCount": 1,
                        "refs": [
                            {
                                "source": "rela",
                                "slotAddress": "0x5003d8",
                                "slotSection": ".data.rel.ro",
                                "inferredVtableBase": "0x500000",
                                "inferredVtableSection": ".data.rel.ro",
                                "vtableSymbols": ["vtable for SyntheticPackageRoute"],
                                "companionSlots": [
                                    {
                                        "slotOffset": "0x3a0",
                                        "slotAddress": "0x5003a0",
                                        "value": "0x101000",
                                        "section": ".text",
                                        "flags": "AX",
                                        "symbols": ["slot3a0"],
                                        "string": "",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        self.assertIn("wrapper `0x101100@0x3d8`", rendered)
        self.assertIn("companion slot=0x3a0", rendered)
        self.assertIn("slot3a0", rendered)


if __name__ == "__main__":
    unittest.main()
