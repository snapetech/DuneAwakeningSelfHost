#!/usr/bin/env python3
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "summarize-client-loader-xrefs.py",
    ROOT / "analysis" / "summarize-client-loader-xrefs.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("summarize_client_loader_xrefs", SCRIPT)
xrefs = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(xrefs)


def make_synthetic_pe():
    image_base = 0x140000000
    text_rva = 0x1000
    rdata_rva = 0x2000
    text_raw = 0x200
    rdata_raw = 0x400
    hit_rva = rdata_rva + 0x27
    string_start_rva = rdata_rva + 0x20
    data = bytearray(0x600)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)

    pe = 0x80
    data[pe : pe + 4] = b"PE\0\0"
    file_header = pe + 4
    optional_size = 0xF0
    struct.pack_into("<HHIIIHH", data, file_header, 0x8664, 2, 0, 0, 0, optional_size, 0x22)

    optional = file_header + 20
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<Q", data, optional + 24, image_base)
    struct.pack_into("<II", data, optional + 32, 0x1000, 0x200)
    struct.pack_into("<II", data, optional + 56, 0x3000, 0x200)
    struct.pack_into("<I", data, optional + 108, 16)

    sections = optional + optional_size
    data[sections : sections + 8] = b".text\0\0\0"
    struct.pack_into("<IIIIIIHHI", data, sections + 8, 0x100, text_rva, 0x200, text_raw, 0, 0, 0, 0, 0x60000020)
    rdata_section = sections + 40
    data[rdata_section : rdata_section + 8] = b".rdata\0\0"
    struct.pack_into(
        "<IIIIIIHHI",
        data,
        rdata_section + 8,
        0x100,
        rdata_rva,
        0x200,
        rdata_raw,
        0,
        0,
        0,
        0,
        0x40000040,
    )

    disp = string_start_rva - (text_rva + 7)
    data[text_raw : text_raw + 7] = b"\x48\x8d\x0d" + struct.pack("<i", disp)
    data[rdata_raw + 0x20 : rdata_raw + 0x20 + len(b"Prefix-CheatManager\0")] = b"Prefix-CheatManager\0"
    return bytes(data), hit_rva, string_start_rva


class ClientLoaderXrefTests(unittest.TestCase):
    def test_parses_pe_sections_and_offsets(self):
        binary, hit_rva, _string_start_rva = make_synthetic_pe()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DuneSandbox-Win64-Shipping.exe"
            path.write_bytes(binary)

            pe = xrefs.load_pe_image(path)

            self.assertEqual(pe.machine, 0x8664)
            self.assertEqual(xrefs.rva_to_file_offset(pe, hit_rva), 0x427)
            self.assertEqual(xrefs.file_offset_to_rva(pe, 0x427), hit_rva)

    def test_scans_log_hit_using_containing_ascii_string_start(self):
        binary, hit_rva, string_start_rva = make_synthetic_pe()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_path = tmp_path / "DuneSandbox-Win64-Shipping.exe"
            log_path = tmp_path / "probe.log"
            binary_path.write_bytes(binary)
            log_path.write_text(
                "2026-06-16T00:00:00Z pid=1 loader=win-client event=scan-hit "
                f"kind=string name=CheatManager addr=0x140002027 rva=0x{hit_rva:x} "
                "allocationBase=0x140000000 regionBase=0x140002000 protect=0x2 type=0x1000000 "
                "module=Z:\\DuneSandbox-Win64-Shipping.exe\n",
                encoding="utf-8",
            )

            pe = xrefs.load_pe_image(binary_path)
            targets = xrefs.targets_from_log(
                pe,
                log_path,
                loader=["win-client"],
                pid=[],
                exe_substrings=["DuneSandbox-Win64-Shipping"],
                categories=["cheat"],
                names=[],
            )
            found = xrefs.scan_xrefs(pe, targets)

            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0].rva, hit_rva)
            self.assertEqual(targets[0].string_start_rva, string_start_rva)
            self.assertEqual(len(found[targets[0]]), 1)
            self.assertEqual(found[targets[0]][0]["xrefRva"], 0x1000)
            self.assertEqual(found[targets[0]][0]["targetRva"], string_start_rva)

    def test_main_json_reports_xref(self):
        binary, hit_rva, _string_start_rva = make_synthetic_pe()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            binary_path = tmp_path / "DuneSandbox-Win64-Shipping.exe"
            log_path = tmp_path / "probe.log"
            binary_path.write_bytes(binary)
            log_path.write_text(
                "2026-06-16T00:00:00Z pid=1 loader=win-client event=scan-hit "
                f"kind=string name=CheatManager addr=0x140002027 rva=0x{hit_rva:x} "
                "allocationBase=0x140000000 regionBase=0x140002000 protect=0x2 type=0x1000000 "
                "module=Z:\\DuneSandbox-Win64-Shipping.exe\n",
                encoding="utf-8",
            )

            pe = xrefs.load_pe_image(binary_path)
            targets = xrefs.targets_from_log(
                pe,
                log_path,
                loader=["win-client"],
                pid=[],
                exe_substrings=["DuneSandbox-Win64-Shipping"],
                categories=["cheat"],
                names=[],
            )
            summary = xrefs.serializable(pe, targets, xrefs.scan_xrefs(pe, targets), context_radius=32)

            self.assertEqual(json.loads(json.dumps(summary))["targetsWithXrefs"], 1)
            self.assertEqual(summary["targets"][0]["xrefCount"], 1)
            self.assertEqual(summary["targets"][0]["xrefs"][0]["xrefFileOffset"], "0x200")
            seed = summary["targets"][0]["xrefs"][0]["signatureSeed"]
            self.assertEqual(seed["fileOffset"], "0x200")
            self.assertIn("48 8d 0d ?? ?? ?? ??", seed["pattern"])


if __name__ == "__main__":
    unittest.main()
