#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_CANDIDATES = (
    ROOT / "scripts" / "promote-ue-anchor-xref-candidates.py",
    ROOT / "analysis" / "promote-ue-anchor-xref-candidates.py",
)
SCRIPT = next((path for path in SCRIPT_CANDIDATES if path.exists()), SCRIPT_CANDIDATES[0])


spec = importlib.util.spec_from_file_location("promote_ue_anchor_xref_candidates", SCRIPT)
promoter = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(promoter)


def xref(pattern="48 8b 0d ?? ?? ?? ??", file_offset="0x200"):
    return {
        "kind": "rip-memory",
        "xrefRva": "0x1000",
        "targetRva": "0x3000",
        "signatureSeed": {
            "fileOffset": file_offset,
            "rva": "0x1000",
            "pattern": pattern,
        },
    }


class PromoteUeAnchorXrefCandidatesTests(unittest.TestCase):
    def test_promotes_non_string_ue_core_anchor_candidates(self):
        summary = {
            "format": "pe64",
            "targets": [
                {
                    "name": "GUObjectArray",
                    "category": "ue",
                    "kind": "signature",
                    "rva": "0x3000",
                    "xrefs": [xref()],
                },
                {
                    "name": "CheatManager",
                    "category": "cheat",
                    "kind": "string",
                    "rva": "0x4000",
                    "xrefs": [xref(file_offset="0x240")],
                },
            ],
        }

        result = promoter.promote_candidates(summary)

        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(result["targets"][0]["name"], "GUObjectArray")
        self.assertEqual(result["targets"][0]["category"], "ue")
        self.assertEqual(result["targets"][0]["source"], "ue-anchor-xref-candidate")
        self.assertEqual(result["anchorCounts"], {"GUObjectArray": 1})
        self.assertEqual(result["groups"]["objects"]["present"], 1)
        self.assertIn("names", result["missingRequiredGroups"])
        self.assertFalse(result["readyForObjectDiscoveryCandidateCoverage"])

    def test_rejects_string_anchor_targets_by_default(self):
        summary = {
            "format": "elf64",
            "targets": [
                {
                    "name": "FNamePool",
                    "category": "ue",
                    "kind": "string",
                    "vaddr": "0x5000",
                    "xrefs": [xref()],
                }
            ],
        }

        result = promoter.promote_candidates(summary)

        self.assertEqual(result["candidateCount"], 0)
        self.assertFalse(result["readyForValidation"])
        self.assertEqual(result["rejected"][0]["reason"], "string-target")

    def test_can_allow_string_targets_explicitly(self):
        summary = {
            "format": "elf64",
            "targets": [
                {
                    "name": "FNamePool",
                    "category": "ue",
                    "kind": "string",
                    "vaddr": "0x5000",
                    "xrefs": [xref()],
                }
            ],
        }

        result = promoter.promote_candidates(summary, allow_string_targets=True)

        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(result["targets"][0]["name"], "FNamePool")

    def test_rejects_loader_owned_sources_by_default(self):
        summary = {
            "format": "elf64",
            "targets": [
                {
                    "name": "ProcessEvent",
                    "category": "ue",
                    "kind": "signature",
                    "vaddr": "0x5000",
                    "source": "/tmp/linux-client-loader/libdune_client_probe_loader.so",
                    "xrefs": [xref(pattern="e8 ?? ?? ?? ??")],
                }
            ],
        }

        result = promoter.promote_candidates(summary)

        self.assertEqual(result["candidateCount"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "loader-source")

    def test_can_allow_loader_sources_only_when_explicit(self):
        summary = {
            "format": "elf64",
            "targets": [
                {
                    "name": "ProcessEvent",
                    "category": "ue",
                    "kind": "signature",
                    "vaddr": "0x5000",
                    "source": "/tmp/linux-client-loader/libdune_client_probe_loader.so",
                    "xrefs": [xref(pattern="e8 ?? ?? ?? ??")],
                }
            ],
        }

        result = promoter.promote_candidates(summary, allow_loader_sources=True)

        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(result["targets"][0]["sourceProvenance"], "loader")
        self.assertEqual(result["sourceProvenanceCounts"], {"loader": 1})

    def test_strict_target_source_rejects_unknown_manual_candidates(self):
        summary = {
            "format": "elf64",
            "targets": [
                {
                    "name": "GUObjectArray",
                    "category": "ue",
                    "kind": "manual",
                    "vaddr": "0x5000",
                    "xrefs": [xref()],
                }
            ],
        }

        result = promoter.promote_candidates(summary, require_target_source=True)

        self.assertEqual(result["candidateCount"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "non-target-source")

    def test_promotes_target_source_with_provenance(self):
        summary = {
            "format": "elf64",
            "targets": [
                {
                    "name": "GUObjectArray",
                    "category": "ue",
                    "kind": "signature",
                    "vaddr": "0x5000",
                    "source": "/game/DuneSandbox/Binaries/Linux/DuneSandbox-Linux-Shipping",
                    "xrefs": [xref()],
                }
            ],
        }

        result = promoter.promote_candidates(summary, require_target_source=True)

        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(result["targets"][0]["sourceProvenance"], "target")
        self.assertEqual(
            result["targets"][0]["sourcePath"],
            "/game/DuneSandbox/Binaries/Linux/DuneSandbox-Linux-Shipping",
        )

    def test_promotes_widened_anchor_aliases_as_first_class_candidates(self):
        summary = {
            "format": "pe64",
            "targets": [
                {"name": "NamePoolData", "category": "ue", "kind": "signature", "rva": "0x1000", "xrefs": [xref(file_offset="0x100")]},
                {"name": "GNames", "category": "ue", "kind": "signature", "rva": "0x2000", "xrefs": [xref(file_offset="0x200")]},
                {"name": "GObjects", "category": "ue", "kind": "signature", "rva": "0x3000", "xrefs": [xref(file_offset="0x300")]},
                {"name": "FUObjectArray", "category": "ue", "kind": "signature", "rva": "0x4000", "xrefs": [xref(file_offset="0x400")]},
                {"name": "CallFunctionByName", "category": "ue", "kind": "signature", "rva": "0x5000", "xrefs": [xref(file_offset="0x500")]},
                {"name": "StaticLoadObject", "category": "ue", "kind": "signature", "rva": "0x6000", "xrefs": [xref(file_offset="0x600")]},
                {"name": "StaticLoadClass", "category": "ue", "kind": "signature", "rva": "0x6800", "xrefs": [xref(file_offset="0x680")]},
                {"name": "LoadObject", "category": "ue", "kind": "signature", "rva": "0x7000", "xrefs": [xref(file_offset="0x700")]},
                {"name": "LoadPackage", "category": "ue", "kind": "signature", "rva": "0x8000", "xrefs": [xref(file_offset="0x800")]},
                {"name": "ResolveName", "category": "ue", "kind": "signature", "rva": "0x9000", "xrefs": [xref(file_offset="0x900")]},
                {"name": "LoadAsset", "category": "ue", "kind": "signature", "rva": "0x9800", "xrefs": [xref(file_offset="0x980")]},
                {"name": "LoadClass", "category": "ue", "kind": "signature", "rva": "0x9900", "xrefs": [xref(file_offset="0x990")]},
                {"name": "UStruct", "category": "ue", "kind": "signature", "rva": "0xa000", "xrefs": [xref(file_offset="0xa00")]},
                {"name": "UEnum", "category": "ue", "kind": "signature", "rva": "0xb000", "xrefs": [xref(file_offset="0xb00")]},
            ],
        }

        result = promoter.promote_candidates(summary)

        self.assertEqual(result["candidateCount"], 14)
        self.assertEqual(
            result["anchorCounts"],
            {
                "NamePoolData": 1,
                "GNames": 1,
                "GObjects": 1,
                "FUObjectArray": 1,
                "CallFunctionByName": 1,
                "StaticLoadObject": 1,
                "StaticLoadClass": 1,
                "LoadObject": 1,
                "LoadPackage": 1,
                "ResolveName": 1,
                "LoadAsset": 1,
                "LoadClass": 1,
                "UStruct": 1,
                "UEnum": 1,
            },
        )
        self.assertEqual(result["groups"]["names"]["present"], 2)
        self.assertEqual(result["groups"]["objects"]["present"], 2)
        self.assertEqual(result["groups"]["dispatch"]["present"], 1)
        self.assertEqual(result["groups"]["package"]["present"], 7)
        self.assertTrue(result["groups"]["package"]["complete"])
        self.assertEqual(result["groups"]["reflection"]["present"], 2)

    def test_promotes_package_anchor_aliases(self):
        summary = {
            "format": "elf64",
            "targets": [
                {"name": "uobject-static-load-object", "category": "ue", "kind": "signature", "vaddr": "0x6000", "xrefs": [xref(file_offset="0x600")]},
                {"name": "uobject-static-load-class", "category": "ue", "kind": "signature", "vaddr": "0x6800", "xrefs": [xref(file_offset="0x680")]},
                {"name": "load-asset-package-path", "category": "ue", "kind": "signature", "vaddr": "0x7000", "xrefs": [xref(file_offset="0x700")]},
                {"name": "load-class-package-path", "category": "ue", "kind": "signature", "vaddr": "0x7800", "xrefs": [xref(file_offset="0x780")]},
            ],
        }

        result = promoter.promote_candidates(summary)

        self.assertEqual(result["candidateCount"], 4)
        self.assertEqual(
            result["anchorCounts"],
            {
                "StaticLoadObject": 1,
                "StaticLoadClass": 1,
                "LoadAsset": 1,
                "LoadClass": 1,
            },
        )
        self.assertEqual(result["groups"]["package"]["present"], 4)

    def test_cli_outputs_validator_ready_xref_json(self):
        summary = {
            "format": "pe64",
            "targets": [
                {
                    "name": "ProcessInternal",
                    "category": "ue",
                    "kind": "signature",
                    "rva": "0x7000",
                    "xrefs": [xref(pattern="e8 ?? ?? ?? ??")],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "xrefs.json"
            path.write_text(json.dumps(summary), encoding="utf-8")

            completed = subprocess.run(
                [str(SCRIPT), str(path), "--format", "json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            result = json.loads(completed.stdout)

        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(result["targets"][0]["name"], "ProcessEvent")
        self.assertEqual(result["targets"][0]["xrefs"][0]["signatureSeed"]["pattern"], "e8 ?? ?? ?? ??")


if __name__ == "__main__":
    unittest.main()
