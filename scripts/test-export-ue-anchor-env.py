#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "export-ue-anchor-env.py",
    ROOT / "analysis" / "export-ue-anchor-env.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("export_ue_anchor_env", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(exporter)


WINDOWS_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=signature name=FNamePool addr=0x140010000 rva=0x10000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor name=GUObjectArray status=mapped addr=0x140020000 rva=0x20000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor name=GWorld status=unmapped addr=0x1
"""


WINDOWS_ALIAS_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=signature name=sig-core-fnamepool addr=0x140010000 rva=0x10000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=signature name=gu-object-array-candidate addr=0x140020000 rva=0x20000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=scan-hit kind=signature name=uobject-static-load-class addr=0x140030000 rva=0x30000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
"""


WINDOWS_SIGNATURE_ANCHOR_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=FNamePool status=resolved hit=0x140001000 addr=0x140010000 transform=riprel32+3 rva=0x10000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GUObjectArray status=resolved hit=0x140002000 addr=0x140020000 transform=riprel32+3 rva=0x20000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GWorld status=resolved hit=0x140003000 addr=0x140030000 transform=riprel32+3 rva=0x30000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=ProcessEvent status=resolved hit=0x140004000 addr=0x140040000 transform=callrel32 rva=0x40000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=CallFunctionByNameWithArguments status=resolved hit=0x140004800 addr=0x140048000 transform=callrel32 rva=0x48000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=StaticLoadObject status=resolved hit=0x140004c00 addr=0x14004c000 transform=callrel32 rva=0x4c000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=StaticLoadClass status=resolved hit=0x140004d00 addr=0x14004d000 transform=callrel32 rva=0x4d000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=LoadAsset status=resolved hit=0x140004e00 addr=0x14004e000 transform=callrel32 rva=0x4e000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=LoadClass status=resolved hit=0x140004f00 addr=0x14004f000 transform=callrel32 rva=0x4f000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=UObject status=resolved hit=0x140005000 addr=0x140050000 transform=hit rva=0x50000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=UFunction status=resolved hit=0x140006000 addr=0x140060000 transform=hit rva=0x60000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=FProperty status=ambiguous hits=2 firstHit=0x140007000 firstAddr=0x140070000 transform=hit
"""


WINDOWS_RUNTIME_CANDIDATE_LOG = """\
2026-06-18T00:00:00Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-start phase=thread maxRegionBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x140060000 blockSlot=0x140060010 firstBlock=0x140080000 blocksOffset=0x10 stride=2 hit=1 rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x140070000 base=0x140070000 numElements=42 numChunks=1 hit=1 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-finish phase=thread fnameHits=1 objectArrayHits=1 targetWritableRegions=2 oversizedRegions=1 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=0
"""


WINDOWS_AMBIGUOUS_RUNTIME_CANDIDATE_LOG = """\
2026-06-18T00:00:00Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-start phase=thread maxRegionBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x140060000 blockSlot=0x140060010 firstBlock=0x140080000 blocksOffset=0x10 stride=2 hit=1 rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x140061000 blockSlot=0x140061010 firstBlock=0x140081000 blocksOffset=0x10 stride=2 hit=2 rva=0x61000 allocationBase=0x140000000 regionBase=0x140061000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x140070000 base=0x140070000 numElements=42 numChunks=1 hit=1 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery name=RuntimeFNamePool status=ambiguous hits=2
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-finish phase=thread fnameHits=2 objectArrayHits=1 targetWritableRegions=2 oversizedRegions=1 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=0
"""


LINUX_LOG = """\
2026-06-16T17:43:39Z pid=112 loader=client event=loaded exe=/game/DuneSandbox-Linux-Shipping native=elf
2026-06-16T17:43:39Z pid=112 loader=client event=scan-hit kind=string name=ProcessEvent addr=0x7f000100 imageOffset=0x100 fileOffset=0x100 perms=r-xp map=/game/DuneSandbox-Linux-Shipping
"""


LINUX_RUNTIME_CANDIDATE_LOG = """\
2026-06-18T00:00:00Z pid=112 loader=client event=loaded exe=/game/DuneSandbox-Linux-Shipping native=elf
2026-06-18T00:00:01Z pid=112 loader=client event=ue-runtime-discovery-start phase=thread mappings=12 maxMappingBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=112 loader=client event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x7f060000 blockSlot=0x7f060010 firstBlock=0x7f080000 blocksOffset=0x10 stride=2 hit=1 imageOffset=0x60000 fileOffset=0x60000 perms=rw-p map=/game/DuneSandbox-Linux-Shipping
2026-06-18T00:00:01Z pid=112 loader=client event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x7f070000 base=0x7f070000 numElements=42 numChunks=1 hit=1 imageOffset=0x70000 fileOffset=0x70000 perms=rw-p map=/game/DuneSandbox-Linux-Shipping
2026-06-18T00:00:01Z pid=112 loader=client event=ue-runtime-discovery-finish phase=thread fnameHits=1 objectArrayHits=1 targetWritableMappings=2 oversizedMappings=1 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=0
"""


SERVER_LOG = """\
2026-06-16T17:43:39Z pid=100 loader=server event=loaded exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping native=elf
2026-06-16T17:43:39Z pid=100 loader=server event=scan-hit kind=string name=FNamePool addr=0x7f000100 imageOffset=0x100 fileOffset=0x100 perms=r-xp map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-16T17:43:39Z pid=100 loader=server event=ue-anchor name=GUObjectArray status=mapped addr=0x7f000200 imageOffset=0x200 fileOffset=0x200 perms=r-xp map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
"""


SERVER_RUNTIME_CANDIDATE_LOG = """\
2026-06-18T00:00:00Z pid=100 loader=server event=loaded exe=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping native=elf
2026-06-18T00:00:01Z pid=100 loader=server event=ue-runtime-discovery-start phase=snapshot mappings=12 maxMappingBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=100 loader=server event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x5628a0060000 blockSlot=0x5628a0060010 firstBlock=0x5628a0080000 blocksOffset=0x10 stride=2 hit=1 imageOffset=0x60000 fileOffset=0x60000 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=100 loader=server event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x5628a0070000 base=0x5628a0070000 numElements=42 numChunks=1 hit=1 imageOffset=0x70000 fileOffset=0x70000 perms=rw-p map=/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping
2026-06-18T00:00:01Z pid=100 loader=server event=ue-runtime-discovery-finish phase=snapshot fnameHits=1 objectArrayHits=1 targetWritableMappings=2 oversizedMappings=1 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=0
"""


class ExportUeAnchorEnvTests(unittest.TestCase):
    def test_exports_windows_env_from_mapped_anchor_hits_not_raw_scan_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "win.log"
            log.write_text(WINDOWS_LOG, encoding="utf-8")
            export = exporter.build_export(
                log,
                ["win-client"],
                [],
                [],
                ["FNamePool", "GUObjectArray", "GWorld"],
                "auto",
            )
            text = exporter.env_text(export)

        self.assertEqual(export["envName"], "DUNE_WIN_CLIENT_PROBE_UE_ANCHORS")
        self.assertEqual(export["pointerProbeEnvName"], "DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE")
        self.assertEqual(export["layoutProbeEnvName"], "DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE")
        self.assertEqual(export["uobjectProbeEnvName"], "DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE")
        self.assertEqual(export["objectArrayProbeEnvName"], "DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE")
        self.assertEqual(export["fnameProbeEnvName"], "DUNE_WIN_CLIENT_PROBE_UE_FNAME_PROBE")
        self.assertEqual(export["anchorSignatureFileEnvName"], "DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE")
        self.assertFalse(export["includeScanHits"])
        self.assertEqual(export["entryCount"], 1)
        self.assertNotIn("FNamePool=0x140010000", text)
        self.assertIn("GUObjectArray=0x140020000", text)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_POINTER_PROBE=true", text)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_LAYOUT_PROBE=true", text)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_UOBJECT_PROBE=true", text)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE=true", text)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_FNAME_PROBE=true", text)
        self.assertIn("FNamePool", export["missing"])
        self.assertIn("GWorld", export["missing"])

    def test_can_export_scan_hits_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "win.log"
            log.write_text(WINDOWS_ALIAS_LOG, encoding="utf-8")
            export = exporter.build_export(
                log,
                ["win-client"],
                [],
                [],
                ["FNamePool", "GUObjectArray", "StaticLoadClass"],
                "auto",
                include_scan_hits=True,
            )
            text = exporter.env_text(export)

        self.assertTrue(export["includeScanHits"])
        self.assertEqual(export["entryCount"], 3)
        self.assertIn("FNamePool=0x140010000", text)
        self.assertIn("GUObjectArray=0x140020000", text)
        self.assertIn("StaticLoadClass=0x140030000", text)
        self.assertEqual(export["entries"][0]["matchedName"], "sig-core-fnamepool")

    def test_exports_resolved_signature_anchors_by_default_including_reflection(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "win.log"
            log.write_text(WINDOWS_SIGNATURE_ANCHOR_LOG, encoding="utf-8")
            export = exporter.build_export(log, ["win-client"], [], [], list(exporter.DEFAULT_ANCHORS), "auto")
            text = exporter.env_text(export)

        self.assertEqual(export["entryCount"], 11)
        self.assertIn("FNamePool=0x140010000", text)
        self.assertIn("GUObjectArray=0x140020000", text)
        self.assertIn("GWorld=0x140030000", text)
        self.assertIn("ProcessEvent=0x140040000", text)
        self.assertIn("CallFunctionByNameWithArguments=0x140048000", text)
        self.assertIn("StaticLoadObject=0x14004c000", text)
        self.assertIn("StaticLoadClass=0x14004d000", text)
        self.assertIn("LoadAsset=0x14004e000", text)
        self.assertIn("LoadClass=0x14004f000", text)
        self.assertIn("UObject=0x140050000", text)
        self.assertIn("UFunction=0x140060000", text)
        self.assertNotIn("FProperty=0x140070000", text)
        self.assertIn("FProperty", export["missing"])
        self.assertEqual(export["entries"][0]["kind"], "ue-anchor-signature")

    def test_can_export_unique_runtime_root_candidates_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "win-runtime.log"
            log.write_text(WINDOWS_RUNTIME_CANDIDATE_LOG, encoding="utf-8")
            export = exporter.build_export(
                log,
                ["win-client"],
                [],
                [],
                ["FNamePool", "GUObjectArray"],
                "auto",
                include_runtime_candidates=True,
            )
            text = exporter.env_text(export)

        self.assertTrue(export["includeRuntimeCandidates"])
        self.assertEqual(export["entryCount"], 2)
        self.assertIn("FNamePool=0x140060000", text)
        self.assertIn("GUObjectArray=0x140070000", text)
        self.assertEqual(export["entries"][0]["kind"], "ue-runtime-discovery-candidate")
        self.assertEqual(export["entries"][0]["matchedName"], "RuntimeFNamePool")

    def test_runtime_root_candidates_stay_blocked_when_ambiguous_without_selector(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "win-runtime.log"
            log.write_text(WINDOWS_AMBIGUOUS_RUNTIME_CANDIDATE_LOG, encoding="utf-8")
            export = exporter.build_export(
                log,
                ["win-client"],
                [],
                [],
                ["FNamePool", "GUObjectArray"],
                "auto",
                include_runtime_candidates=True,
            )

        self.assertEqual(export["entryCount"], 1)
        self.assertEqual(export["entries"][0]["name"], "GUObjectArray")
        self.assertIn("FNamePool", export["missing"])

    def test_can_export_reviewed_ambiguous_runtime_root_candidate_by_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "win-runtime.log"
            log.write_text(WINDOWS_AMBIGUOUS_RUNTIME_CANDIDATE_LOG, encoding="utf-8")
            export = exporter.build_export(
                log,
                ["win-client"],
                [],
                [],
                ["FNamePool"],
                "auto",
                runtime_candidate_selectors=["FNamePool=0x61000"],
            )
            text = exporter.env_text(export)

        self.assertEqual(export["runtimeCandidateSelectors"], ["FNamePool=0x61000"])
        self.assertEqual(export["entryCount"], 1)
        self.assertIn("FNamePool=0x140061000", text)

    def test_exports_linux_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "linux.log"
            log.write_text(LINUX_LOG, encoding="utf-8")
            export = exporter.build_export(log, ["linux-client"], [], [], ["ProcessEvent"], "linux")

        self.assertEqual(export["envName"], "DUNE_CLIENT_PROBE_UE_ANCHORS")
        self.assertEqual(export["pointerProbeEnvName"], "DUNE_CLIENT_PROBE_UE_POINTER_PROBE")
        self.assertEqual(export["layoutProbeEnvName"], "DUNE_CLIENT_PROBE_UE_LAYOUT_PROBE")
        self.assertEqual(export["uobjectProbeEnvName"], "DUNE_CLIENT_PROBE_UE_UOBJECT_PROBE")
        self.assertEqual(export["objectArrayProbeEnvName"], "DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_PROBE")
        self.assertEqual(export["fnameProbeEnvName"], "DUNE_CLIENT_PROBE_UE_FNAME_PROBE")
        self.assertEqual(export["anchorSignatureFileEnvName"], "DUNE_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE")
        self.assertEqual(export["entryCount"], 0)
        self.assertIn("ProcessEvent", export["missing"])

    def test_can_export_linux_runtime_root_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "linux-runtime.log"
            log.write_text(LINUX_RUNTIME_CANDIDATE_LOG, encoding="utf-8")
            export = exporter.build_export(
                log,
                ["linux-client"],
                [],
                [],
                ["FNamePool", "GUObjectArray"],
                "linux",
                include_runtime_candidates=True,
            )
            text = exporter.env_text(export)

        self.assertEqual(export["envName"], "DUNE_CLIENT_PROBE_UE_ANCHORS")
        self.assertEqual(export["entryCount"], 2)
        self.assertIn("FNamePool=0x7f060000", text)
        self.assertIn("GUObjectArray=0x7f070000", text)
        self.assertEqual(export["entries"][0]["imageOffset"], "0x60000")

    def test_exports_server_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "server.log"
            log.write_text(SERVER_LOG, encoding="utf-8")
            export = exporter.build_export(
                log,
                ["server"],
                [],
                [],
                ["FNamePool", "GUObjectArray"],
                "auto",
            )
            text = exporter.env_text(export)

        self.assertEqual(export["envName"], "DUNE_PROBE_LOADER_UE_ANCHORS")
        self.assertEqual(export["pointerProbeEnvName"], "DUNE_PROBE_LOADER_UE_POINTER_PROBE")
        self.assertEqual(export["layoutProbeEnvName"], "DUNE_PROBE_LOADER_UE_LAYOUT_PROBE")
        self.assertEqual(export["uobjectProbeEnvName"], "DUNE_PROBE_LOADER_UE_UOBJECT_PROBE")
        self.assertEqual(export["objectArrayProbeEnvName"], "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE")
        self.assertEqual(export["fnameProbeEnvName"], "DUNE_PROBE_LOADER_UE_FNAME_PROBE")
        self.assertEqual(export["anchorSignatureFileEnvName"], "DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE")
        self.assertIn("DUNE_PROBE_LOADER_UE_ANCHORS='GUObjectArray=0x7f000200'", text)
        self.assertNotIn("FNamePool=0x7f000100", text)
        self.assertIn("DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_PROBE=true", text)
        self.assertIn("DUNE_PROBE_LOADER_UE_FNAME_PROBE=true", text)

    def test_can_export_server_runtime_root_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "server-runtime.log"
            log.write_text(SERVER_RUNTIME_CANDIDATE_LOG, encoding="utf-8")
            export = exporter.build_export(
                log,
                ["server"],
                [],
                [],
                ["FNamePool", "GUObjectArray"],
                "server",
                include_runtime_candidates=True,
            )
            text = exporter.env_text(export)

        self.assertEqual(export["envName"], "DUNE_PROBE_LOADER_UE_ANCHORS")
        self.assertEqual(export["entryCount"], 2)
        self.assertIn("FNamePool=0x5628a0060000", text)
        self.assertIn("GUObjectArray=0x5628a0070000", text)
        self.assertEqual(export["entries"][1]["fileOffset"], "0x70000")

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "win.log"
            log.write_text(WINDOWS_LOG, encoding="utf-8")
            result = subprocess.run(
                [str(SCRIPT), str(log), "--loader", "win-client", "--name", "FNamePool", "--format", "json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        export = json.loads(result.stdout)
        self.assertEqual(export["schemaVersion"], "dune-ue-anchor-env/v1")
        self.assertEqual(export["entryCount"], 0)


if __name__ == "__main__":
    unittest.main()
