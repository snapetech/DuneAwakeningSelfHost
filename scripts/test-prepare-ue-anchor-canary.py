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


def pe_row(name, xref, pattern, category="ue"):
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


def elf_row(name, xref, pattern, category="ue"):
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
        self.assertIn("- package: `1/6` target=`1/6`", prep_summary)
        self.assertTrue(verifier_mode & 0o111)
        self.assertTrue(strict_verifier_mode & 0o111)
        self.assertIn("DUNE_UE4SS_STRICT_RUNTIME_CONTRACT=true", strict_verifier_text)
        self.assertIn("post-canary-verify.sh", strict_verifier_text)
        self.assertIn("'runtimeRootDiscovery': 'ue-runtime-root-discovery'", verifier_text)
        self.assertIn("Runtime discovery promoted roots", verifier_text)
        self.assertIn("Runtime discovery validated roots", verifier_text)
        self.assertIn("--client-log", verifier_text)
        self.assertIn("/tmp/dune-win-client-probe-loader.log", verifier_text)
        self.assertIn("--loader win-client", verifier_text)
        self.assertIn("summarize-ue4ss-port-gaps.py", verifier_text)
        self.assertIn("--canary-plan-json", verifier_text)
        self.assertIn("--format json", verifier_text)

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
            self.assertNotIn("readinessJson", result["outputs"])
            self.assertFalse(readiness_json.exists())
            self.assertFalse(object_coverage.exists())
            self.assertFalse(post_summary.exists())
            self.assertFalse(gap_summary_json.exists())
            self.assertFalse(gap_summary.exists())
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

        self.assertEqual(readiness["schemaVersion"], "dune-ue4ss-port-readiness/v1")
        self.assertEqual(coverage, readiness["objectDiscoveryCoverage"])
        self.assertTrue(readiness["anchorCoverage"]["provided"])
        self.assertIn("# UE4SS Post-Canary Summary", summary)
        self.assertIn("- Ready objectDiscovery:", summary)
        self.assertIn("- ueProcessEventHookRuntimeTarget:", summary)
        self.assertIn("- ueCallFunctionHookRuntimeTarget:", summary)
        self.assertIn("- ueCallFunctionLiveLuaDispatch:", summary)
        self.assertIn("- ueProcessEventLiveLuaDispatch:", summary)
        self.assertIn("- ueProcessEventLuaHookAliasRouting:", summary)
        self.assertIn("## Runtime Evidence Contract", summary)
        self.assertIn("registryProvenance=runtime", summary)
        self.assertIn("functionProvenance=runtime", summary)
        self.assertIn("luaDispatch=true", summary)
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
        self.assertIn("ueProcessEventLiveLuaDispatch", summary)
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
            "ue-call-function-live-lua-dispatch",
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
            "lua-load-asset-package",
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
                    "luaLoadAssetPackage": True,
                    "luaDispatch": True,
                },
                "gates": [{"name": name, "passed": True} for name in gate_names],
                "objectDiscoveryCoverage": {
                    "schemaVersion": "dune-ue-object-discovery-coverage/v1",
                    "missingObjectDiscoveryComponents": [],
                    "missingFindObjectComponents": [],
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
        self.assertIn("- Live target-image runtimeProcessEventDispatch: `ready=true, missing=none`", summary)
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
