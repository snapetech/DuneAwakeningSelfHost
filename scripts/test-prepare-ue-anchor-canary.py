#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "prepare-ue-anchor-canary.py",
    ROOT / "analysis" / "prepare-ue-anchor-canary.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


ANCHOR_LOG = """\
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=FNamePool status=resolved hit=0x140001000 addr=0x140010000 transform=riprel32+3 rva=0x10000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GUObjectArray status=resolved hit=0x140002000 addr=0x140020000 transform=riprel32+3 rva=0x20000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=GWorld status=resolved hit=0x140003000 addr=0x140030000 transform=riprel32+3 rva=0x30000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=ProcessEvent status=resolved hit=0x140004000 addr=0x140040000 transform=callrel32 rva=0x40000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=CallFunctionByNameWithArguments status=resolved hit=0x140004800 addr=0x140048000 transform=callrel32 rva=0x48000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=StaticLoadObject status=resolved hit=0x140004c00 addr=0x14004c000 transform=callrel32 rva=0x4c000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=UObject status=resolved hit=0x140005000 addr=0x140050000 transform=hit rva=0x50000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-16T17:43:39Z pid=312 loader=win-client event=ue-anchor-signature name=UFunction status=resolved hit=0x140006000 addr=0x140060000 transform=hit rva=0x60000 allocationBase=0x140000000 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
"""


RUNTIME_CANDIDATE_LOG = """\
2026-06-18T00:00:00Z pid=312 loader=win-client event=loaded phase=thread exe=C:\\game\\DuneSandbox-Win64-Shipping.exe native=pe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-start phase=thread maxRegionBytes=33554432 maxCandidates=8
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeFNamePool addr=0x140060000 blockSlot=0x140060010 firstBlock=0x140080000 blocksOffset=0x10 stride=2 hit=1 rva=0x60000 allocationBase=0x140000000 regionBase=0x140060000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray addr=0x140070000 base=0x140070000 numElements=42 numChunks=1 hit=1 rva=0x70000 allocationBase=0x140000000 regionBase=0x140070000 protect=0x4 module=C:\\game\\DuneSandbox-Win64-Shipping.exe
2026-06-18T00:00:01Z pid=312 loader=win-client event=ue-runtime-discovery-finish phase=thread fnameHits=1 objectArrayHits=1 targetWritableRegions=2 oversizedRegions=1 scannedSlots=2048 fnameProbes=2048 objectArrayProbes=2048 anchors=0
"""


def pe_row(name, xref, pattern, category="ue", source="test", source_provenance=None):
    row = {
        "name": f"{name}@0x{xref + 0x1000:x}#1",
        "category": category,
        "source": source,
        "xrefRva": f"0x{xref:x}",
        "targetRva": f"0x{xref + 0x1000:x}",
        "pattern": pattern,
        "length": len(pattern.split()),
        "fixedBytes": sum(1 for part in pattern.split() if part != "??"),
        "expectedFileOffset": f"0x{xref:x}",
        "matchCount": 1,
        "status": "unique-expected",
        "promotable": True,
        "matches": [{"fileOffset": f"0x{xref:x}", "rva": f"0x{xref:x}", "section": ".text", "expected": True}],
    }
    if source_provenance:
        row["sourceProvenance"] = source_provenance
    return row


def elf_row(name, xref, pattern, category="ue", source="test", source_provenance=None):
    row = {
        "name": f"{name}@0x{xref + 0x1000:x}#1",
        "category": category,
        "source": source,
        "xrefVaddr": f"0x{xref:x}",
        "targetVaddr": f"0x{xref + 0x1000:x}",
        "pattern": pattern,
        "length": len(pattern.split()),
        "fixedBytes": sum(1 for part in pattern.split() if part != "??"),
        "expectedFileOffset": f"0x{xref:x}",
        "matchCount": 1,
        "status": "unique-expected",
        "promotable": True,
        "matches": [
            {
                "fileOffset": f"0x{xref:x}",
                "imageOffset": f"0x{xref:x}",
                "vaddr": f"0x{xref:x}",
                "expected": True,
            }
        ],
    }
    if source_provenance:
        row["sourceProvenance"] = source_provenance
    return row


def legacy_pe_row(name, xref, pattern, category="ue"):
    return {
        "name": f"{name}@0x{xref + 0x1000:x}#1",
        "category": category,
        "source": "test",
        "xrefRva": f"0x{xref:x}",
        "targetRva": f"0x{xref + 0x1000:x}",
        "pattern": pattern,
        "length": len(pattern.split()),
        "fixedBytes": sum(1 for part in pattern.split() if part != "??"),
        "expectedFileOffset": f"0x{xref:x}",
        "matchCount": 1,
        "status": "unique-expected",
        "promotable": True,
        "matches": [{"fileOffset": f"0x{xref:x}", "rva": f"0x{xref:x}", "section": ".text", "expected": True}],
    }


def legacy_elf_row(name, xref, pattern, category="ue"):
    return {
        "name": f"{name}@0x{xref + 0x1000:x}#1",
        "category": category,
        "source": "test",
        "xrefVaddr": f"0x{xref:x}",
        "targetVaddr": f"0x{xref + 0x1000:x}",
        "pattern": pattern,
        "length": len(pattern.split()),
        "fixedBytes": sum(1 for part in pattern.split() if part != "??"),
        "expectedFileOffset": f"0x{xref:x}",
        "matchCount": 1,
        "status": "unique-expected",
        "promotable": True,
        "matches": [
            {
                "fileOffset": f"0x{xref:x}",
                "imageOffset": f"0x{xref:x}",
                "vaddr": f"0x{xref:x}",
                "expected": True,
            }
        ],
    }


def validation(rows):
    category_counts = {}
    for row in rows:
        category = row.get("category") or "unknown"
        category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "scope": "executable",
        "patternCount": len(rows),
        "promotableCount": len(rows),
        "statusCounts": {"unique-expected": len(rows)},
        "categoryCounts": category_counts,
        "patterns": rows,
    }


def symbol_surface(binary, rows):
    return {
        "schemaVersion": "dune-elf-ue-symbol-surface/v1",
        "binary": binary,
        "symbolCount": len(rows),
        "matchedCount": len(rows),
        "nonFalsePositiveMatchedCount": sum(1 for row in rows if not row.get("falsePositive")),
        "rows": rows,
    }


def symbol_row(name, demangled, role, value, groups=None, false_positive=False):
    return {
        "section": ".dynsym",
        "name": name,
        "demangled": demangled,
        "value": value,
        "size": 16,
        "bind": "STB_GLOBAL",
        "type": "STT_FUNC" if role in ("process-event", "dispatch-function", "package-function") else "STT_OBJECT",
        "visibility": "STV_DEFAULT",
        "shndx": "1",
        "groups": groups or [],
        "falsePositive": false_positive,
        "role": role,
    }


def candidate_globals(binary, candidates):
    return {
        "schemaVersion": "dune-ue-candidate-globals/v1",
        "binary": binary,
        "candidateCount": len(candidates),
        "anchorCounts": {},
        "groups": {},
        "candidates": candidates,
    }


def vtable_candidates(binary):
    return {
        "schemaVersion": "dune-ue-vtable-candidates/v1",
        "binary": binary,
        "hookProbeShortlist": [
            {
                "slot": 64,
                "score": 2.26,
                "candidateCount": 252,
                "objectCoverage": 1.0,
                "topTargetShare": 1.0,
                "reasons": [
                    "ue4-uobject-process-event-slot-heuristic",
                    "present-on-most-scanned-objects",
                    "stable-target-for-slot",
                    "observed-across-multiple-vtables",
                ],
                "topTarget": {
                    "targetName": "ProcessEvent",
                    "targetSource": "vtable-candidate",
                    "imageOffset": "0xfb4b060",
                    "map": binary,
                },
            },
            {
                "slot": 32,
                "score": 1.1,
                "candidateCount": 8,
                "objectCoverage": 0.2,
                "topTargetShare": 0.4,
                "reasons": [],
                "topTarget": {
                    "targetName": "ProcessEvent",
                    "targetSource": "vtable-candidate",
                    "imageOffset": "0x111",
                    "map": binary,
                },
            },
        ],
        "rankedSlots": [],
    }


def package_loader_vtables(binary):
    return {
        "schemaVersion": "dune-elf-ue-package-loader-vtables/v1",
        "binary": binary,
        "vtables": [
            {
                "name": "_ZTV14FAsyncPackage2",
                "demangled": "vtable for FAsyncPackage2",
                "slots": [
                    {
                        "slot": 66,
                        "target": "0xfa7a630",
                        "candidateKind": "method",
                        "demangled": "FAsyncPackage2::TickAsyncPackage(bool, bool)",
                        "sourceHints": ["Runtime/CoreUObject/Private/Serialization/AsyncLoading2.cpp"],
                    },
                    {
                        "slot": 67,
                        "target": "0xfa7a680",
                        "candidateKind": "trap",
                        "demangled": "FAsyncPackage2::Trap()",
                    },
                ],
            }
        ],
    }


class PrepareUeAnchorCanaryTests(unittest.TestCase):
    def run_prepare(self, tmp, platform, binary_name, rows, log_text, skip_readiness=True, extra_args=None):
        binary = Path(tmp) / binary_name
        log = Path(tmp) / "loader.log"
        validation_json = Path(tmp) / "validation.json"
        output_dir = Path(tmp) / "out"
        binary.write_bytes(b"MZ-test" if platform == "windows" else b"\x7fELF-test")
        log.write_text(log_text, encoding="utf-8")
        validation_json.write_text(json.dumps(validation(rows)), encoding="utf-8")

        command = [
            str(SCRIPT),
            "--platform",
            platform,
            "--binary",
            str(binary),
            "--loader-log",
            str(log),
            "--validation-json",
            str(validation_json),
            "--output-dir",
            str(output_dir),
            "--format",
            "json",
        ]
        if skip_readiness:
            command.append("--skip-readiness")
        if extra_args:
            command.extend(extra_args)

        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return json.loads(result.stdout), output_dir

    def test_symbol_surface_json_counts_target_elf_exports_as_anchor_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            symbol_json = Path(tmp) / "elf-ue-symbol-surface.json"
            symbols = symbol_surface(
                str(binary),
                [
                    symbol_row("GName", "GName", "global-symbol", 0x1000, ["names"]),
                    symbol_row("GUObjectArray", "GUObjectArray", "global-symbol", 0x2000, ["objects"]),
                    symbol_row("GWorld", "GWorld", "global-symbol", 0x3000, ["world"]),
                    symbol_row("_ZN7UObject12ProcessEventEP9UFunctionPv", "UObject::ProcessEvent(UFunction*, void*)", "process-event", 0x4000, ["dispatch"]),
                    symbol_row("_Z16StaticLoadObjectv", "StaticLoadObject()", "package-function", 0x5000, ["package"]),
                    symbol_row("SDL_LoadObject", "SDL_LoadObject", "package-function", 0x6000, ["package"], false_positive=True),
                ],
            )
            symbol_json.write_text(json.dumps(symbols), encoding="utf-8")
            result, output_dir = self.run_prepare(
                tmp,
                "server",
                binary.name,
                [],
                "",
                extra_args=["--symbol-surface-json", str(symbol_json)],
            )
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))
            prep_summary = (output_dir / "README.md").read_text(encoding="utf-8")

        self.assertEqual(result["manifestEntryCount"], 0)
        self.assertEqual(result["anchorSignatureEntryCount"], 0)
        self.assertEqual(result["symbolSurfaceAnchorEntryCount"], 5)
        self.assertEqual(result["symbolSurfaceAnchorCount"], 5)
        self.assertTrue(result["readyForTargetObjectDiscovery"])
        self.assertTrue(result["readyForTargetHookPlanning"])
        self.assertTrue(result["readyForTargetPackageLoading"])
        self.assertEqual(coverage["groups"]["names"]["targetPresent"], 1)
        self.assertEqual(coverage["groups"]["objects"]["targetPresent"], 1)
        self.assertEqual(coverage["groups"]["world"]["targetPresent"], 1)
        self.assertEqual(coverage["groups"]["dispatch"]["targetPresent"], 1)
        self.assertEqual(coverage["groups"]["package"]["targetPresent"], 1)
        process_event = coverage["groups"]["dispatch"]["anchors"][0]
        self.assertIn("symbol-surface", process_event["sources"])
        self.assertEqual(process_event["targetSourceCount"], 1)
        self.assertIn("process-event", process_event["symbolSurfaceRoles"])
        self.assertNotIn("SDL_LoadObject", json.dumps(coverage))
        self.assertIn("- Symbol-surface anchors: `5`", prep_summary)

    def test_candidate_globals_json_counts_reviewed_target_globals_as_anchor_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            candidates_json = Path(tmp) / "ue-candidate-globals.json"
            candidates_json.write_text(
                json.dumps(
                    candidate_globals(
                        str(binary),
                        [
                            {
                                "name": "GUObjectArray",
                                "group": "objects",
                                "imageOffset": "0x165ff4a8",
                                "source": str(binary),
                                "sourceProvenance": "target",
                                "score": 2336,
                            },
                            {
                                "name": "GEngine",
                                "group": "world",
                                "imageOffset": "0x1686df70",
                                "source": str(binary),
                                "sourceProvenance": "target",
                                "score": 8703,
                            },
                        ],
                    )
                ),
                encoding="utf-8",
            )
            result, output_dir = self.run_prepare(
                tmp,
                "server",
                binary.name,
                [],
                "",
                extra_args=["--candidate-globals-json", str(candidates_json)],
            )
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))
            prep_summary = (output_dir / "README.md").read_text(encoding="utf-8")

        self.assertEqual(result["candidateGlobalAnchorEntryCount"], 2)
        self.assertEqual(result["candidateGlobalAnchorCount"], 2)
        self.assertFalse(result["readyForTargetObjectDiscovery"])
        self.assertEqual(coverage["groups"]["objects"]["targetPresent"], 1)
        self.assertEqual(coverage["groups"]["world"]["targetPresent"], 1)
        object_anchor = coverage["groups"]["objects"]["anchors"][0]
        world_anchor = coverage["groups"]["world"]["anchors"][1]
        self.assertIn("candidate-global", object_anchor["sources"])
        self.assertIn("candidate-global", world_anchor["sources"])
        self.assertEqual(object_anchor["candidateGlobalOffsets"], ["0x165ff4a8"])
        self.assertEqual(world_anchor["candidateGlobalOffsets"], ["0x1686df70"])
        self.assertIn("- Candidate-global anchors: `2`", prep_summary)

    def test_vtable_candidates_json_counts_stable_target_process_event_as_dispatch_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            vtable_json = Path(tmp) / "ue-vtable-candidates.json"
            vtable_json.write_text(json.dumps(vtable_candidates(str(binary))), encoding="utf-8")
            result, output_dir = self.run_prepare(
                tmp,
                "server",
                binary.name,
                [],
                "",
                extra_args=["--vtable-candidates-json", str(vtable_json)],
            )
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))
            prep_summary = (output_dir / "README.md").read_text(encoding="utf-8")

        self.assertEqual(result["vtableCandidateAnchorEntryCount"], 1)
        self.assertEqual(result["vtableCandidateAnchorCount"], 1)
        process_event = coverage["groups"]["dispatch"]["anchors"][0]
        self.assertIn("vtable-candidate", process_event["sources"])
        self.assertTrue(process_event["targetPresent"])
        self.assertEqual(process_event["targetSourceCount"], 1)
        self.assertEqual(process_event["vtableCandidateSlots"], [64])
        self.assertEqual(process_event["vtableCandidateOffsets"], ["0xfb4b060"])
        self.assertFalse(result["readyForTargetHookPlanning"])
        self.assertFalse(result["readyForTargetPackageLoading"])
        self.assertIn("- VTable candidate anchors: `1`", prep_summary)

    def test_vtable_candidates_accept_noisy_high_count_process_event_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            vtable_json = Path(tmp) / "ue-vtable-candidates.json"
            noisy = vtable_candidates(str(binary))
            noisy["hookProbeShortlist"][0]["objectCoverage"] = 0.5
            noisy["hookProbeShortlist"][0]["candidateCount"] = 217
            vtable_json.write_text(json.dumps(noisy), encoding="utf-8")
            result, output_dir = self.run_prepare(
                tmp,
                "server",
                binary.name,
                [],
                "",
                extra_args=["--vtable-candidates-json", str(vtable_json)],
            )
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))

        self.assertEqual(result["vtableCandidateAnchorEntryCount"], 1)
        process_event = coverage["groups"]["dispatch"]["anchors"][0]
        self.assertTrue(process_event["targetPresent"])
        self.assertEqual(process_event["vtableCandidateSlots"], [64])

    def test_package_loader_vtables_are_recorded_but_do_not_unlock_package_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "DuneSandboxServer-Linux-Shipping"
            package_vtables_json = Path(tmp) / "ue-package-loader-vtables.json"
            package_vtables_json.write_text(json.dumps(package_loader_vtables(str(binary))), encoding="utf-8")
            result, output_dir = self.run_prepare(
                tmp,
                "server",
                binary.name,
                [],
                "",
                extra_args=["--package-loader-vtables-json", str(package_vtables_json)],
            )
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))
            prep_summary = (output_dir / "README.md").read_text(encoding="utf-8")

        self.assertEqual(result["packageLoaderVTableCandidateEntryCount"], 2)
        self.assertEqual(result["packageLoaderVTableMethodCandidateCount"], 1)
        self.assertEqual(result["packageLoaderVTableCount"], 1)
        self.assertFalse(result["packageLoaderVTablePromotable"])
        self.assertFalse(result["readyForTargetObjectDiscovery"])
        self.assertFalse(result["readyForTargetHookPlanning"])
        self.assertFalse(result["readyForTargetPackageLoading"])
        self.assertEqual(result["combinedAnchorCount"], 0)
        self.assertEqual(coverage["groups"]["package"]["targetPresent"], 0)
        self.assertEqual(coverage["packageLoaderVTableStrongestMethods"][0]["target"], "0xfa7a630")
        self.assertIn("StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName", coverage["packageLoaderVTableNonPromotableReason"])
        self.assertIn("- Package-loader vtable method candidates: `1`", prep_summary)
        self.assertIn("- Package-loader vtable promotable: `false`", prep_summary)
        self.assertIn("## Package Loader VTable Candidates", prep_summary)
        self.assertIn("Package-loading anchors require a callable target-image StaticLoadObject", prep_summary)
        self.assertIn("summarize-ue4ss-package-route-evidence.py", prep_summary)
        self.assertIn("summarize-ue4ss-package-external-symbol-plan.py", prep_summary)
        self.assertIn("ue4ss-package-external-symbol-plan.json", prep_summary)

    def test_prepared_canary_can_include_unique_runtime_root_candidates(self):
        rows = [
            pe_row("ProcessEvent", 0x2000, "e8 ?? ?? ?? ??"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result, output_dir = self.run_prepare(
                tmp,
                "windows",
                "DuneSandbox-Win64-Shipping.exe",
                rows,
                RUNTIME_CANDIDATE_LOG,
                extra_args=["--include-runtime-candidates"],
            )
            env_text = (output_dir / "ue-anchors.env").read_text(encoding="utf-8")
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))
            prep_summary = (output_dir / "README.md").read_text(encoding="utf-8")

        self.assertTrue(result["includeRuntimeCandidates"])
        self.assertEqual(result["anchorEnvEntryCount"], 2)
        self.assertIn("FNamePool=0x140060000", env_text)
        self.assertIn("GUObjectArray=0x140070000", env_text)
        self.assertTrue(coverage["provided"])
        self.assertTrue(coverage["targetCoverageFieldsPresent"])
        self.assertEqual(coverage["runtimeCandidateAnchorCount"], 2)
        self.assertEqual(coverage["runtimeCandidateAnchors"], ["FNamePool", "GUObjectArray"])
        names_group = coverage["groups"]["names"]
        objects_group = coverage["groups"]["objects"]
        self.assertEqual(names_group["targetPresent"], 1)
        self.assertEqual(objects_group["targetPresent"], 1)
        self.assertIn("runtime-candidate", names_group["anchors"][0]["sources"])
        self.assertIn("runtime-candidate", objects_group["anchors"][0]["sources"])
        self.assertIn("- Runtime candidate anchors: `2`", prep_summary)

    def test_post_canary_verifier_reports_runtime_candidate_promotion(self):
        rows = [
            pe_row("ProcessEvent", 0x2000, "e8 ?? ?? ?? ??"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            _, output_dir = self.run_prepare(
                tmp,
                "windows",
                "DuneSandbox-Win64-Shipping.exe",
                rows,
                RUNTIME_CANDIDATE_LOG,
                extra_args=["--include-runtime-candidates"],
            )
            log = Path(tmp) / "post-canary.log"
            log.write_text(RUNTIME_CANDIDATE_LOG, encoding="utf-8")
            fake_readiness = Path(tmp) / "fake-readiness.py"
            fake_report = {
                "schemaVersion": "dune-ue4ss-port-readiness/v1",
                "loaders": ["win-client"],
                "logCount": 1,
                "ready": {
                    "targetImageProcess": True,
                    "runtimeRootDiscovery": True,
                    "runtimeRootValidation": True,
                    "targetObjectDiscovery": False,
                    "objectDiscoveryCoverage": True,
                },
                "gates": [],
                "objectDiscoveryCoverage": {
                    "schemaVersion": "dune-ue-object-discovery-coverage/v1",
                    "missingObjectDiscoveryComponents": [],
                    "missingFindObjectComponents": [],
                },
                "liveTargetImageCanaryContract": {
                    "ready": True,
                    "missingKeys": [],
                    "groups": {
                        "targetImageAnchors": {"ready": True, "missingKeys": []},
                        "runtimePackageLoading": {"ready": True, "missingKeys": []},
                        "runtimeObjectRegistry": {"ready": True, "missingKeys": []},
                        "runtimeReflection": {"ready": True, "missingKeys": []},
                        "runtimeProcessEventDispatch": {"ready": True, "missingKeys": []},
                        "runtimeCallFunctionDispatch": {"ready": True, "missingKeys": []},
                    },
                },
                "anchorCoverage": {"provided": True},
                "runtimeDiscovery": {
                    "promotedNames": ["RuntimeFNamePool", "RuntimeGUObjectArray"],
                    "validatedNames": ["RuntimeFNamePool", "RuntimeGUObjectArray"],
                    "failureCounts": {},
                    "coverage": {
                        "targetWritableRegions": 2,
                        "oversizedRegions": 1,
                        "scannedSlots": 2048,
                        "fnameProbes": 2048,
                        "objectArrayProbes": 2048,
                    },
                },
                "nextSteps": [],
            }
            fake_readiness.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                f"json.dump({fake_report!r}, sys.stdout)\n",
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["DUNE_UE4SS_READINESS_SCRIPT"] = str(fake_readiness)
            result = subprocess.run(
                [str(output_dir / "post-canary-verify.sh"), str(log)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            summary = (output_dir / "post-canary-summary.md").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- Runtime discovery promoted roots: `RuntimeFNamePool, RuntimeGUObjectArray`", summary)
        self.assertIn("- Runtime discovery validated roots: `RuntimeFNamePool, RuntimeGUObjectArray`", summary)
        self.assertIn("- Runtime candidate anchors injected: `FNamePool, GUObjectArray`", summary)
        self.assertIn("- Runtime candidate anchors promoted: `FNamePool, GUObjectArray`", summary)
        self.assertIn("- Runtime candidate anchors validated: `FNamePool, GUObjectArray`", summary)
        self.assertIn("- Runtime candidate anchors still missing: `none`", summary)

    def test_prepares_windows_anchor_canary_outputs(self):
        rows = [
            pe_row("GUObjectArray", 0x1000, "48 8d 0d ?? ?? ?? ??"),
            pe_row("ProcessEvent", 0x2000, "e8 ?? ?? ?? ??"),
            pe_row("StaticLoadObject", 0x2800, "e8 ?? ?? ?? ??"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result, output_dir = self.run_prepare(
                tmp,
                "windows",
                "DuneSandbox-Win64-Shipping.exe",
                rows,
                ANCHOR_LOG,
                skip_readiness=False,
            )
            signatures = (output_dir / "client-anchor-signatures.txt").read_text(encoding="utf-8")
            env_text = (output_dir / "ue-anchors.env").read_text(encoding="utf-8")
            validation_summary = json.loads((output_dir / "signature-validation.json").read_text(encoding="utf-8"))
            readiness = (output_dir / "ue4ss-readiness.md").read_text(encoding="utf-8")
            readiness_json = json.loads((output_dir / "ue4ss-readiness.json").read_text(encoding="utf-8"))
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))
            object_coverage = json.loads((output_dir / "object-discovery-coverage.json").read_text(encoding="utf-8"))
            prep_summary = (output_dir / "README.md").read_text(encoding="utf-8")
            verifier = output_dir / "post-canary-verify.sh"
            verifier_text = verifier.read_text(encoding="utf-8")
            verifier_mode = verifier.stat().st_mode
            strict_verifier = output_dir / "post-canary-verify-strict.sh"
            strict_verifier_text = strict_verifier.read_text(encoding="utf-8")
            strict_verifier_mode = strict_verifier.stat().st_mode

        self.assertEqual(result["platform"], "windows")
        self.assertEqual(result["manifestEntryCount"], 3)
        self.assertEqual(result["anchorEnvEntryCount"], 8)
        self.assertEqual(result["anchorSignatureEntryCount"], 3)
        self.assertEqual(result["combinedAnchorCount"], 8)
        self.assertTrue(result["readyForTargetObjectDiscovery"])
        self.assertTrue(result["readyForTargetHookPlanning"])
        self.assertTrue(result["readyForTargetPackageLoading"])
        self.assertIn("anchorCoverage", result["outputs"])
        self.assertIn("readinessJson", result["outputs"])
        self.assertIn("objectDiscoveryCoverage", result["outputs"])
        self.assertIn("postCanaryVerify", result["outputs"])
        self.assertIn("postCanaryVerifyStrict", result["outputs"])
        self.assertIn("GUObjectArray@riprel32+3=48 8d 0d ?? ?? ?? ??", signatures)
        self.assertIn("ProcessEvent@callrel32=e8 ?? ?? ?? ??", signatures)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_ANCHORS=", env_text)
        self.assertIn("DUNE_WIN_CLIENT_PROBE_UE_ANCHOR_SIGNATURES_FILE=", env_text)
        self.assertIn("client-anchor-signatures.txt", env_text)
        self.assertIn("FNamePool=0x140010000", env_text)
        self.assertEqual(validation_summary["patternCount"], 3)
        self.assertIn("signature-manifest-exact", readiness)
        self.assertEqual(readiness_json["schemaVersion"], "dune-ue4ss-port-readiness/v1")
        self.assertEqual(object_coverage["schemaVersion"], "dune-ue-object-discovery-coverage/v1")
        self.assertEqual(object_coverage, readiness_json["objectDiscoveryCoverage"])
        self.assertIn("objectRegistry", object_coverage["missingFindObjectComponents"])
        self.assertTrue(coverage["readyForObjectDiscovery"])
        self.assertTrue(coverage["readyForHookPlanning"])
        self.assertTrue(coverage["readyForPackageLoading"])
        self.assertTrue(coverage["readyForTargetObjectDiscovery"])
        self.assertTrue(coverage["readyForTargetHookPlanning"])
        self.assertTrue(coverage["readyForTargetPackageLoading"])
        self.assertEqual(coverage["signatureAnchorEntryCount"], 3)
        self.assertEqual(coverage["runtimeCandidateAnchorCount"], 0)
        self.assertEqual(coverage["groups"]["names"]["present"], 1)
        self.assertEqual(coverage["groups"]["objects"]["present"], 1)
        self.assertEqual(coverage["groups"]["world"]["present"], 1)
        self.assertEqual(coverage["groups"]["dispatch"]["present"], 2)
        self.assertEqual(coverage["groups"]["package"]["present"], 1)
        self.assertEqual(coverage["groups"]["package"]["targetPresent"], 1)
        self.assertEqual(coverage["groups"]["reflection"]["present"], 2)
        self.assertIn("explicit", coverage["groups"]["dispatch"]["anchors"][0]["sources"])
        self.assertIn("signature", coverage["groups"]["dispatch"]["anchors"][0]["sources"])
        self.assertTrue(coverage["groups"]["dispatch"]["anchors"][0]["targetPresent"])
        self.assertIn("explicit", coverage["groups"]["dispatch"]["anchors"][2]["sources"])
        self.assertNotIn("signature", coverage["groups"]["dispatch"]["anchors"][2]["sources"])
        self.assertTrue(coverage["groups"]["package"]["anchors"][0]["targetPresent"])
        self.assertEqual(coverage["groups"]["package"]["anchors"][0]["targetSourceCount"], 2)
        self.assertIn("Ready for target-image package loading anchors: `true`", prep_summary)
        self.assertIn("- package: `1/7` target=`1/7`", prep_summary)
        self.assertTrue(verifier_mode & 0o111)
        self.assertTrue(strict_verifier_mode & 0o111)
        self.assertIn("DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true", strict_verifier_text)
        self.assertIn("post-canary-verify.sh", strict_verifier_text)
        self.assertIn("'runtimeRootDiscovery': 'ue-runtime-root-discovery'", verifier_text)
        self.assertIn("'luaStaticConstructObjectNativeExecutorReady': 'lua-static-construct-object-native-executor-ready'", verifier_text)
        self.assertIn("'luaLoadClassPackageNativeInvocation': 'lua-load-class-package-native-invocation'", verifier_text)
        self.assertIn("'luaLoadClassPackageNativeInvocation'", verifier_text)
        self.assertIn("Runtime discovery promoted roots", verifier_text)
        self.assertIn("Runtime discovery validated roots", verifier_text)
        self.assertIn("--client-log", verifier_text)
        self.assertIn("/tmp/dune-win-client-probe-loader.log", verifier_text)
        self.assertIn("--loader win-client", verifier_text)
        self.assertIn("summarize-ue4ss-port-gaps.py", verifier_text)
        self.assertIn("summarize-ue4ss-evidence-inventory.py", verifier_text)
        self.assertIn("--require-complete", verifier_text)
        self.assertIn("--canary-plan-json", verifier_text)
        self.assertIn("--format json", verifier_text)

    def test_loader_provenance_signature_does_not_unlock_target_anchor_coverage(self):
        rows = [
            pe_row(
                "GUObjectArray",
                0x1000,
                "48 8d 0d ?? ?? ?? ??",
                source="C:\\tools\\windows-client-loader\\dune_win_client_probe_loader.dll",
                source_provenance="loader",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result, output_dir = self.run_prepare(
                tmp,
                "windows",
                "DuneSandbox-Win64-Shipping.exe",
                rows,
                "",
            )
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))

        object_anchor = coverage["groups"]["objects"]["anchors"][0]
        self.assertEqual(result["anchorSignatureEntryCount"], 1)
        self.assertEqual(coverage["groups"]["objects"]["present"], 1)
        self.assertEqual(coverage["groups"]["objects"]["targetPresent"], 0)
        self.assertEqual(coverage["groups"]["objects"]["loaderPresent"], 1)
        self.assertFalse(coverage["readyForTargetObjectDiscovery"])
        self.assertFalse(object_anchor["targetPresent"])
        self.assertTrue(object_anchor["loaderPresent"])
        self.assertEqual(object_anchor["targetSourceCount"], 0)
        self.assertEqual(object_anchor["loaderSourceCount"], 1)

    def test_post_canary_verifier_rebuilds_readiness_sidecars(self):
        rows = [
            pe_row("GUObjectArray", 0x1000, "48 8d 0d ?? ?? ?? ??"),
            pe_row("ProcessEvent", 0x2000, "e8 ?? ?? ?? ??"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result, output_dir = self.run_prepare(
                tmp,
                "windows",
                "DuneSandbox-Win64-Shipping.exe",
                rows,
                ANCHOR_LOG,
            )
            log = Path(tmp) / "post-canary.log"
            log.write_text(ANCHOR_LOG, encoding="utf-8")
            (output_dir / "next-canary.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
                        "platform": "windows",
                        "loader": "win-client",
                        "selectedStage": "object-discovery",
                        "nextCanaryContract": {
                            "rootRecoveryCandidateInput": {
                                "provided": True,
                                "envName": "DUNE_WIN_CLIENT_PROBE_UE_CANDIDATE_GLOBALS",
                                "candidateCount": 2,
                                "emittedCount": 1,
                                "filteredRejectedShapeCount": 1,
                                "sourceAnchorPresets": ["object-discovery"],
                                "anchorCounts": {"GUObjectArray": 1},
                                "missingGroups": ["world"],
                                "groupCoverage": {
                                    "objects": {"ready": True},
                                    "world": {"ready": False},
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            readiness_json = output_dir / "ue4ss-readiness.json"
            object_coverage = output_dir / "object-discovery-coverage.json"
            post_summary = output_dir / "post-canary-summary.md"
            gap_summary_json = output_dir / "ue4ss-port-gaps.json"
            gap_summary = output_dir / "ue4ss-port-gaps.md"
            evidence_inventory_json = output_dir / "ue4ss-evidence-inventory.json"
            evidence_inventory = output_dir / "ue4ss-evidence-inventory.md"
            self.assertNotIn("readinessJson", result["outputs"])
            self.assertFalse(readiness_json.exists())
            self.assertFalse(object_coverage.exists())
            self.assertFalse(post_summary.exists())
            self.assertFalse(gap_summary_json.exists())
            self.assertFalse(gap_summary.exists())
            self.assertFalse(evidence_inventory_json.exists())
            self.assertFalse(evidence_inventory.exists())
            subprocess.run(
                [str(output_dir / "post-canary-verify.sh"), str(log)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            readiness = json.loads(readiness_json.read_text(encoding="utf-8"))
            coverage = json.loads(object_coverage.read_text(encoding="utf-8"))
            summary = post_summary.read_text(encoding="utf-8")
            gaps_json = json.loads(gap_summary_json.read_text(encoding="utf-8"))
            gaps = gap_summary.read_text(encoding="utf-8")
            inventory_json = json.loads(evidence_inventory_json.read_text(encoding="utf-8"))
            inventory = evidence_inventory.read_text(encoding="utf-8")

        self.assertEqual(readiness["schemaVersion"], "dune-ue4ss-port-readiness/v1")
        self.assertEqual(coverage, readiness["objectDiscoveryCoverage"])
        self.assertTrue(readiness["anchorCoverage"]["provided"])
        self.assertIn("# UE4SS Post-Canary Summary", summary)
        self.assertIn("- Ready objectDiscovery:", summary)
        self.assertIn("- ueProcessEventHookRuntimeTarget:", summary)
        self.assertIn("- ueCallFunctionHookRuntimeTarget:", summary)
        self.assertIn("- ueProcessEventActiveValidation:", summary)
        self.assertIn("- ueCallFunctionActiveValidation:", summary)
        self.assertIn("- ueCallFunctionLiveLuaDispatch:", summary)
        self.assertIn("- luaCallFunctionNativeInvokeNonSelfTestGate:", summary)
        self.assertIn("- ueProcessEventLiveLuaDispatch:", summary)
        self.assertIn("- ueProcessEventLuaHookAliasRouting:", summary)
        self.assertIn("## Runtime Evidence Contract", summary)
        self.assertIn("registryProvenance=runtime", summary)
        self.assertIn("functionProvenance=runtime", summary)
        self.assertIn("luaDispatch=true", summary)
        self.assertIn("ue-process-event-active-validate", summary)
        self.assertIn("ue-call-function-active-validate", summary)
        self.assertIn("Package native executor readiness requires", summary)
        self.assertIn("FinalNativeCallEligible=true", summary)
        self.assertIn("- Strict runtime contract: `disabled`", summary)
        self.assertIn("- Missing strict runtime keys:", summary)
        self.assertIn("- Missing strict signature/anchor keys:", summary)
        self.assertIn("- Live target-image canary contract ready:", summary)
        self.assertIn("- Missing live target-image canary keys:", summary)
        self.assertIn("- Live target-image runtimePackageLoading:", summary)
        self.assertIn("- Live target-image runtimeProcessEventDispatch:", summary)
        self.assertIn("## Signature And Anchor Coverage", summary)
        self.assertIn("- signatureManifestExact:", summary)
        self.assertIn("- anchorCoverageHookPlanning:", summary)
        self.assertIn("- targetPackageLoadingSurface:", summary)
        self.assertIn("## Reflection Runtime Evidence", summary)
        self.assertIn("- luaReflectionLiveDescriptorTypedValuesRuntime:", summary)
        self.assertIn("## Next Steps", summary)
        self.assertIn("# UE4SS Port Gap Summary", gaps)
        self.assertIn("Recommended next stage", gaps)
        self.assertIn("Root-Recovery Candidate Coverage", gaps)
        self.assertEqual(inventory_json["schemaVersion"], "dune-ue4ss-evidence-inventory/v1")
        self.assertIn("# UE4SS Evidence Inventory", inventory)
        self.assertIn("Missing groups: `world`", gaps)
        self.assertEqual(gaps_json["schemaVersion"], "dune-ue4ss-port-gap-summary/v1")
        self.assertEqual(gaps_json["rootRecoveryCandidateCoverage"]["missingGroups"], ["world"])

    def test_post_canary_verifier_strict_runtime_contract_fails_without_runtime_evidence(self):
        rows = [
            pe_row("GUObjectArray", 0x1000, "48 8d 0d ?? ?? ?? ??"),
            pe_row("ProcessEvent", 0x2000, "e8 ?? ?? ?? ??"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            _, output_dir = self.run_prepare(
                tmp,
                "windows",
                "DuneSandbox-Win64-Shipping.exe",
                rows,
                ANCHOR_LOG,
            )
            log = Path(tmp) / "post-canary.log"
            log.write_text(ANCHOR_LOG, encoding="utf-8")
            env = dict(os.environ)
            env["DUNE_UE4SS_STRICT_RUNTIME_CONTRACT"] = "true"
            result = subprocess.run(
                [str(output_dir / "post-canary-verify.sh"), str(log)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            wrapper_result = subprocess.run(
                [str(output_dir / "post-canary-verify-strict.sh"), str(log)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            summary = (output_dir / "post-canary-summary.md").read_text(encoding="utf-8")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(wrapper_result.returncode, 0)
        self.assertIn("missing strict UE4SS contract keys", result.stderr)
        self.assertIn("missing strict UE4SS contract keys", wrapper_result.stderr)
        self.assertIn("- Strict runtime contract: `enabled`", summary)
        self.assertIn("ueProcessEventHookRuntimeTarget", summary)
        self.assertIn("ueProcessEventActiveValidation", summary)
        self.assertIn("ueCallFunctionActiveValidation", summary)
        self.assertIn("ueProcessEventLiveLuaDispatch", summary)
        self.assertIn("luaCallFunctionNativeInvokeNonSelfTestGate", summary)
        self.assertIn("luaFunctionRegistryRuntime", summary)
        self.assertIn("signatureManifestPromotable", summary)
        self.assertIn("anchorCoverageHookPlanning", summary)

    def test_post_canary_verifier_strict_runtime_contract_accepts_gate_only_evidence(self):
        rows = [
            pe_row("GUObjectArray", 0x1000, "48 8d 0d ?? ?? ?? ??"),
            pe_row("ProcessEvent", 0x2000, "e8 ?? ?? ?? ??"),
        ]
        gate_names = [
            "ue-target-names",
            "ue-target-objects",
            "ue-target-world",
            "ue-target-dispatch",
            "ue-process-event-hook-runtime-target",
            "ue-call-function-hook-runtime-target",
            "ue-process-event-live-hook-runtime-target",
            "ue-call-function-live-hook-runtime-target",
            "ue-process-event-active-validation",
            "ue-call-function-active-validation",
            "ue-call-function-live-lua-dispatch",
            "lua-call-function-native-invoke",
            "lua-call-function-native-invoke-preflight",
            "lua-call-function-native-executor-state",
            "lua-call-function-native-invoke-non-self-test-gate",
            "lua-call-function-native-invoke-non-self-test-invoked",
            "lua-process-event-native-invoke",
            "lua-process-event-native-invoke-descriptor-preflight",
            "lua-process-event-native-executor-state",
            "lua-process-event-native-invoke-non-self-test-gate",
            "lua-process-event-native-invoke-non-self-test-invoked",
            "ue-process-event-live-lua-dispatch",
            "ue-process-event-live-function-path",
            "ue-process-event-live-runtime-context",
            "ue-process-event-live-registry-context",
            "ue-process-event-live-runtime-registry-context",
            "ue-process-event-live-param-values",
            "ue-process-event-live-raw-param-values",
            "ue-process-event-live-container-param-values",
            "ue-process-event-live-array-container-param-values",
            "ue-process-event-live-set-container-param-values",
            "ue-process-event-live-map-container-param-values",
            "ue-process-event-live-set-map-container-param-values",
            "ue-process-event-live-container-data-samples",
            "ue-process-event-lua-context-handles",
            "ue-process-event-lua-param-accessors",
            "ue-process-event-live-class-aware-param-values",
            "ue-process-event-function-param-method",
            "ue-process-event-function-param-lookup-method",
            "ue-process-event-function-param-iteration-method",
            "ue-process-event-container-alias-methods",
            "ue-process-event-container-storage-layout-methods",
            "ue-process-event-lua-scalar-param-accessors",
            "ue-process-event-lua-name-string-param-accessors",
            "ue-process-event-lua-struct-param-accessors",
            "ue-process-event-lua-enum-param-accessors",
            "ue-process-event-lua-object-param-accessors",
            "ue-process-event-lua-bool-param-accessors",
            "ue-process-event-lua-hook-routing",
            "ue-process-event-lua-hook-alias-routing",
            "lua-object-registry-runtime",
            "lua-function-registry-runtime",
            "lua-decoded-object-aliases-runtime",
            "ue-object-array-shape",
            "ue-object-array-registry-runtime",
            "ue-object-native-identities",
            "ue-object-internal-flags",
            "ue-fname-decoder",
            "lua-object-outer-chain-identities",
            "lua-object-api",
            "lua-function-iteration-runtime",
            "lua-static-construct-object-native-executor-state",
            "lua-static-construct-object-native-executor-ready",
            "lua-static-construct-object-native-invoke",
            "ue-reflection-property-descriptors-runtime",
            "ue-reflection-property-values-runtime",
            "lua-reflection-for-each-property-runtime",
            "lua-reflection-live-descriptor-typed-class-runtime",
            "lua-reflection-live-descriptor-typed-values-runtime",
            "lua-reflection-live-descriptor-typed-set-values-runtime",
            "lua-reflection-live-descriptor-values-runtime",
            "lua-load-asset-package-crash-guard",
            "lua-load-asset-package-guarded-call",
            "lua-load-asset-package-return-validation",
            "lua-load-asset-package-native-call-adapter",
            "lua-load-asset-package-invocation-descriptor",
            "lua-load-asset-package-native-executor",
            "lua-load-asset-package-native-invocation",
            "lua-load-asset-package",
            "lua-load-class-package-abi-state",
            "lua-load-class-package-call-frame-verification",
            "lua-load-class-package-native-executor",
            "lua-load-class-package-native-invocation",
            "signature-manifest-exact",
            "signature-manifest-promotable",
            "anchor-coverage-object-discovery",
            "anchor-coverage-hook-planning",
            "anchor-coverage-package-loading",
            "ue-target-package-loading-surface",
            "target-image-process",
            "ue-runtime-root-discovery",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            _, output_dir = self.run_prepare(
                tmp,
                "windows",
                "DuneSandbox-Win64-Shipping.exe",
                rows,
                ANCHOR_LOG,
            )
            (output_dir / "anchor-coverage.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue-anchor-coverage/v1",
                        "targetCoverageFieldsPresent": True,
                        "groups": {
                            "names": {"present": 1, "targetPresent": 1, "total": 1},
                            "objects": {"present": 1, "targetPresent": 1, "total": 1},
                            "world": {"present": 1, "targetPresent": 1, "total": 1},
                            "dispatch": {"present": 1, "targetPresent": 1, "total": 1},
                            "package": {"present": 1, "targetPresent": 1, "total": 1},
                        },
                    }
                ),
                encoding="utf-8",
            )
            log = Path(tmp) / "post-canary.log"
            log.write_text(ANCHOR_LOG, encoding="utf-8")
            fake_readiness = Path(tmp) / "fake-readiness.py"
            fake_report = {
                "schemaVersion": "dune-ue4ss-port-readiness/v1",
                "loaders": ["win-client"],
                "logCount": 1,
                "ready": {
                    "objectDiscovery": True,
                    "targetImageProcess": True,
                    "runtimeRootDiscovery": True,
                    "runtimeRootValidation": True,
                    "targetObjectDiscovery": True,
                    "objectDiscoveryCoverage": True,
                    "anchorCoverageObjectDiscovery": True,
                    "anchorCoverageHookPlanning": True,
                    "anchorCoveragePackageLoading": True,
                    "signatureManifestExact": True,
                    "signatureManifestPromotable": True,
                    "findObjectSemantics": True,
                    "ueObjectArrayShape": True,
                    "ueObjectArrayRegistryRuntime": True,
                    "ueObjectNativeIdentities": True,
                    "ueObjectInternalFlags": True,
                    "ueFNameDecoder": True,
                    "luaObjectOuterChainIdentities": True,
                    "luaObjectApi": True,
                    "luaObjectRegistryRuntime": True,
                    "luaFunctionRegistryRuntime": True,
                    "luaDecodedObjectAliasesRuntime": True,
                    "luaFunctionIterationRuntime": True,
                    "luaStaticConstructObjectNativeExecutorState": True,
                    "luaStaticConstructObjectNativeExecutorReady": True,
                    "luaStaticConstructObjectNativeInvoke": True,
                    "ueReflectionPropertyDescriptorsRuntime": True,
                    "ueReflectionPropertyValuesRuntime": True,
                    "reflection": True,
                    "hooks": True,
                    "targetHooks": True,
                    "targetPackageLoadingSurface": True,
                    "luaLoadAssetPackageCrashGuard": True,
                    "luaLoadAssetPackageGuardedCall": True,
                    "luaLoadAssetPackageReturnValidation": True,
                    "luaLoadAssetPackageNativeCallAdapter": True,
                    "luaLoadAssetPackageInvocationDescriptor": True,
                    "luaLoadAssetPackageNativeExecutor": True,
                    "luaLoadAssetPackageNativeInvocation": True,
                    "luaLoadAssetPackage": True,
                    "luaLoadClassPackageAbiState": True,
                    "luaLoadClassPackageCallFrameVerification": True,
                    "luaLoadClassPackageNativeExecutor": True,
                    "luaLoadClassPackageNativeInvocation": True,
                    "ueProcessEventActiveValidation": True,
                    "ueCallFunctionActiveValidation": True,
                    "luaCallFunctionNativeInvoke": True,
                    "luaCallFunctionNativeInvokePreflight": True,
                    "luaCallFunctionNativeExecutorState": True,
                    "luaCallFunctionNativeInvokeNonSelfTestGate": True,
                    "luaCallFunctionNativeInvokeNonSelfTestInvoked": True,
                    "luaProcessEventNativeInvoke": True,
                    "luaProcessEventNativeInvokeDescriptorPreflight": True,
                    "luaProcessEventNativeExecutorState": True,
                    "luaProcessEventNativeInvokeNonSelfTestGate": True,
                    "luaProcessEventNativeInvokeNonSelfTestInvoked": True,
                    "luaDispatch": True,
                    "ue4ssLuaApiComplete": True,
                },
                "gates": [{"name": name, "passed": True} for name in gate_names],
                "objectDiscoveryCoverage": {
                    "schemaVersion": "dune-ue-object-discovery-coverage/v1",
                    "missingObjectDiscoveryComponents": [],
                    "missingFindObjectComponents": [],
                },
                "liveTargetImageCanaryContract": {
                    "ready": True,
                    "missingKeys": [],
                    "groups": {
                        "targetImageAnchors": {"ready": True, "missingKeys": []},
                        "runtimePackageLoading": {"ready": True, "missingKeys": []},
                        "runtimeObjectRegistry": {"ready": True, "missingKeys": []},
                        "runtimeReflection": {"ready": True, "missingKeys": []},
                        "runtimeProcessEventDispatch": {"ready": True, "missingKeys": []},
                        "runtimeCallFunctionDispatch": {"ready": True, "missingKeys": []},
                    },
                },
                "anchorCoverage": {"provided": True},
                "runtimeDiscovery": {
                    "promotedNames": ["RuntimeFNamePool", "RuntimeGUObjectArray"],
                    "validatedNames": ["RuntimeFNamePool", "RuntimeGUObjectArray"],
                    "failureCounts": {},
                    "coverage": {
                        "targetWritableRegions": 2,
                        "oversizedRegions": 0,
                        "scannedSlots": 128,
                        "fnameProbes": 1,
                        "objectArrayProbes": 1,
                    },
                },
                "nextSteps": [],
            }
            fake_readiness.write_text(
                "#!/usr/bin/env python3\n"
                "import json,sys\n"
                f"json.dump({fake_report!r}, sys.stdout)\n",
                encoding="utf-8",
            )
            fake_readiness.chmod(0o755)
            env = dict(os.environ)
            env["DUNE_UE4SS_READINESS_SCRIPT"] = str(fake_readiness)
            env["DUNE_UE4SS_STRICT_RUNTIME_CONTRACT"] = "true"
            result = subprocess.run(
                [str(output_dir / "post-canary-verify.sh"), str(log)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            wrapper_result = subprocess.run(
                [str(output_dir / "post-canary-verify-strict.sh"), str(log)],
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            summary = (output_dir / "post-canary-summary.md").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(wrapper_result.returncode, 0, wrapper_result.stderr)
        self.assertIn("- Strict runtime contract: `enabled`", summary)
        self.assertIn("- Ready runtimeRootDiscovery: `true`", summary)
        self.assertIn("- Missing strict runtime keys: `none`", summary)
        self.assertIn("- Missing strict signature/anchor keys: `none`", summary)
        self.assertIn("- Live target-image canary contract ready: `true`", summary)
        self.assertIn("- Missing live target-image canary keys: `none`", summary)
        self.assertIn("- runtimeRootDiscovery: `true`", summary)
        self.assertIn("- Runtime discovery promoted roots: `RuntimeFNamePool, RuntimeGUObjectArray`", summary)
        self.assertIn("- Runtime discovery validated roots: `RuntimeFNamePool, RuntimeGUObjectArray`", summary)
        self.assertIn("- Runtime candidate anchors injected: `none`", summary)
        self.assertIn("- Runtime discovery failures: `none`", summary)
        self.assertIn("- Live target-image runtimePackageLoading: `ready=true, missing=none`", summary)
        self.assertIn("- luaLoadClassPackageNativeInvocation: `true`", summary)
        self.assertIn("- luaStaticConstructObjectNativeExecutorReady: `true`", summary)
        self.assertIn("- Live target-image runtimeProcessEventDispatch: `ready=true, missing=none`", summary)
        self.assertIn("- Live target-image runtimeCallFunctionDispatch: `ready=true, missing=none`", summary)
        self.assertIn("- ueProcessEventActiveValidation: `true`", summary)
        self.assertIn("- ueCallFunctionActiveValidation: `true`", summary)
        self.assertIn("- luaCallFunctionNativeExecutorState: `true`", summary)
        self.assertIn("- luaCallFunctionNativeInvokeNonSelfTestGate: `true`", summary)
        self.assertIn("- luaCallFunctionNativeInvokeNonSelfTestInvoked: `true`", summary)
        self.assertIn("- luaProcessEventNativeExecutorState: `true`", summary)
        self.assertIn("- luaProcessEventNativeInvokeNonSelfTestInvoked: `true`", summary)
        self.assertIn("- signatureManifestExact: `true`", summary)
        self.assertIn("- anchorCoverageHookPlanning: `true`", summary)
        self.assertIn("- anchorCoveragePackageLoading: `true`", summary)
        self.assertIn("- targetPackageLoadingSurface: `true`", summary)
        self.assertIn("- luaReflectionLiveDescriptorValuesRuntime: `true`", summary)

    def test_prepares_linux_server_anchor_canary_outputs(self):
        server_log = ANCHOR_LOG.replace("loader=win-client", "loader=server").replace("rva=", "imageOffset=")
        rows = [
            elf_row("GWorld", 0x1000, "48 8b 0d ?? ?? ?? ??"),
            elf_row("ProcessEvent", 0x2000, "e8 ?? ?? ?? ??"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result, output_dir = self.run_prepare(
                tmp,
                "server",
                "DuneSandboxServer-Linux-Shipping",
                rows,
                server_log,
            )
            signatures = (output_dir / "server-anchor-signatures.txt").read_text(encoding="utf-8")
            env_text = (output_dir / "ue-server-anchors.env").read_text(encoding="utf-8")
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))
            verifier_text = (output_dir / "post-canary-verify.sh").read_text(encoding="utf-8")

        self.assertEqual(result["platform"], "server")
        self.assertEqual(result["anchorSignatureEntryCount"], 2)
        self.assertEqual(result["combinedAnchorCount"], 8)
        self.assertIn("GWorld@riprel32+3=48 8b 0d ?? ?? ?? ??", signatures)
        self.assertIn("DUNE_PROBE_LOADER_UE_ANCHORS=", env_text)
        self.assertIn("DUNE_PROBE_LOADER_UE_ANCHOR_SIGNATURES_FILE=", env_text)
        self.assertIn("server-anchor-signatures.txt", env_text)
        self.assertIn("ProcessEvent=0x140040000", env_text)
        self.assertTrue(coverage["readyForObjectDiscovery"])
        self.assertTrue(coverage["readyForHookPlanning"])
        self.assertTrue(coverage["readyForPackageLoading"])
        self.assertEqual(coverage["groups"]["package"]["present"], 1)
        self.assertEqual(coverage["signatureAnchors"], ["GWorld", "ProcessEvent"])
        self.assertIn("--server-log", verifier_text)
        self.assertIn("/tmp/dune-server-probe-loader.log", verifier_text)
        self.assertIn("--loader server", verifier_text)

    def test_prepares_linux_client_post_canary_verifier(self):
        linux_log = ANCHOR_LOG.replace("loader=win-client", "loader=client").replace("rva=", "imageOffset=")
        rows = [
            elf_row("GUObjectArray", 0x1000, "48 8d 0d ?? ?? ?? ??"),
            elf_row("ProcessEvent", 0x2000, "e8 ?? ?? ?? ??"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result, output_dir = self.run_prepare(
                tmp,
                "linux-client",
                "DuneSandbox-Linux-Shipping",
                rows,
                linux_log,
            )
            verifier_text = (output_dir / "post-canary-verify.sh").read_text(encoding="utf-8")

        self.assertEqual(result["platform"], "linux-client")
        self.assertIn("--client-log", verifier_text)
        self.assertIn("/tmp/dune-client-probe-loader.log", verifier_text)
        self.assertIn("--loader client", verifier_text)

    def test_readme_includes_linux_target_anchor_recovery_commands_when_not_ready(self):
        rows = [
            elf_row("GWorld", 0x1000, "48 8b 0d ?? ?? ?? ??"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            _result, output_dir = self.run_prepare(
                tmp,
                "linux-client",
                "DuneSandbox-Linux-Shipping",
                rows,
                "",
                extra_args=[
                    "--loader",
                    "client",
                    "--pid",
                    "1234",
                    "--exe-substring",
                    "DuneSandbox",
                    "--exe-substring",
                    "DuneClient",
                ],
            )
            summary = (output_dir / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Target-Image Anchor Recovery", summary)
        self.assertIn("- Recovery reasons: `", summary)
        self.assertIn("missing-target-object-anchor-groups", summary)
        self.assertIn("- Missing target groups: `object=names, objects", summary)
        self.assertIn("scripts/summarize-linux-loader-xrefs.py", summary)
        self.assertIn("--pid 1234", summary)
        self.assertIn("--exe-substring DuneSandbox", summary)
        self.assertIn("--exe-substring DuneClient", summary)
        self.assertIn("scripts/promote-ue-anchor-xref-candidates.py", summary)
        self.assertIn("--require-target-source", summary)
        self.assertIn("ue-anchor-candidates.json", summary)
        self.assertIn("scripts/prepare-ue-anchor-canary.py --platform linux-client", summary)
        self.assertIn("--xref-json", summary)
        self.assertIn("--loader client", summary)
        self.assertIn("--pid 1234", summary)
        self.assertIn("recovered-target-anchors/post-canary-verify.sh", summary)

    def test_non_anchor_signature_manifest_does_not_create_ue_anchor_coverage(self):
        rows = [
            pe_row("ServerRequestBaseBackup", 0x1000, "48 8d 0d ?? ?? ?? ??", category="brt"),
            pe_row("CheatManagerSurface", 0x2000, "e8 ?? ?? ?? ??", category="cheat"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result, output_dir = self.run_prepare(
                tmp,
                "windows",
                "DuneSandbox-Win64-Shipping.exe",
                rows,
                "",
            )
            signatures = (output_dir / "client-anchor-signatures.txt").read_text(encoding="utf-8")
            summary = (output_dir / "README.md").read_text(encoding="utf-8")
            coverage = json.loads((output_dir / "anchor-coverage.json").read_text(encoding="utf-8"))

        self.assertEqual(result["manifestEntryCount"], 2)
        self.assertEqual(result["anchorSignatureEntryCount"], 0)
        self.assertEqual(result["combinedAnchorCount"], 0)
        self.assertFalse(coverage["readyForObjectDiscovery"])
        self.assertFalse(coverage["readyForHookPlanning"])
        self.assertEqual(coverage["signatureAnchorEntryCount"], 0)
        self.assertEqual(coverage["signatureAnchorCount"], 0)
        self.assertEqual(coverage["manifestEntryCategoryCounts"], {"brt": 1, "cheat": 1})
        self.assertEqual(
            coverage["missingRequiredSignatureAnchorGroups"],
            ["names", "objects", "world", "dispatch"],
        )
        self.assertIn("# Anchor entries: 0", signatures)
        self.assertIn("UE anchor signature coverage: `none`", summary)
        self.assertIn("validated signatures exist, but none map to core UE anchors", summary)


if __name__ == "__main__":
    unittest.main()
