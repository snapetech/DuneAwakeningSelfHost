#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export-ue4ss-package-promotion-env.py"


def load_module():
    spec = importlib.util.spec_from_file_location("promotion_env", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(seed="StaticLoadClass"):
    return {
        "schemaVersion": "dune-ue4ss-package-runtime-trace-evidence/v1",
        "sourceLog": "/tmp/trace.log",
        "sourceLogSha256": "trace-log-sha256",
        "sourceEvidenceJson": "/tmp/evidence.json",
        "sourceEvidenceJsonSha256": "evidence-json-sha256",
        "sourceLogExists": True,
        "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
        "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
        "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        "sourceExternalPlan": "/tmp/external-plan.json",
        "pid": 4242,
        "imageRangeSource": "pid",
        "imageBase": "0x100000",
        "imageStart": "0x200000",
        "imageEnd": "0x7000000",
        "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
        "imagePerms": "r-xp",
        "armedCount": 1,
        "tracePidMatchesRequested": True,
        "hits": [
            {
                "seed": seed,
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "targetImageCaller": True,
                "tracePidMatchesRequested": True,
                "traceAddressMatchesBase": True,
                "caller": {"ip": "0x6000"},
            }
        ],
    }


def multi_hit_evidence():
    payload = evidence("LoadPackage")
    payload["hits"].append(
        {
            "seed": "StaticLoadClass",
            "callerImageOffset": "0x7000",
            "ripImageOffset": "0x6ff0",
            "targetImageCaller": True,
            "tracePidMatchesRequested": True,
            "traceAddressMatchesBase": True,
            "caller": {"ip": "0x8000"},
        }
    )
    payload["concreteReviewPriority"] = [
        {
            "hitIndex": 1,
            "seed": "StaticLoadClass",
            "reviewScore": 18,
        }
    ]
    return payload


def ranked_multi_hit_evidence():
    payload = evidence("LoadPackage")
    payload["hits"].append(
        {
            "seed": "LoadPackage",
            "callerImageOffset": "0x9000",
            "ripImageOffset": "0x8ff0",
            "targetImageCaller": True,
            "tracePidMatchesRequested": True,
            "traceAddressMatchesBase": True,
            "caller": {"ip": "0xa000"},
        }
    )
    payload["familyCandidates"] = {
        "LoadPackage": {
            "hitIndex": 1,
            "seed": "LoadPackage",
            "reviewScore": 18,
        }
    }
    payload["recommendedReview"] = {
        "hitIndex": 1,
        "seed": "LoadPackage",
        "reviewScore": 18,
    }
    payload["concreteReviewPriority"] = [
        {
            "hitIndex": 1,
            "seed": "LoadPackage",
            "reviewScore": 18,
        }
    ]
    return payload


def non_concrete_family_candidate_evidence():
    payload = evidence("LoadPackage")
    payload["familyCandidates"] = {
        "LoadPackage": {
            "hitIndex": 0,
            "seed": "LoadPackage",
            "missingCallFrameOffsets": [],
            "missingRequiredMemoryRegisters": ["rsi"],
            "reviewScore": 18,
        }
    }
    payload["concreteReviewPriority"] = []
    payload["recommendedReview"] = {}
    return payload


def malformed_auto_hit_index_evidence(hit_index):
    payload = evidence("LoadPackage")
    payload["recommendedReview"] = {
        "hitIndex": hit_index,
        "seed": "LoadPackage",
        "reviewScore": 18,
    }
    payload["concreteReviewPriority"] = [
        {
            "hitIndex": hit_index,
            "seed": "LoadPackage",
            "reviewScore": 18,
        }
    ]
    return payload


def concrete_priority_evidence():
    payload = evidence("LoadPackage")
    payload["hits"][0].pop("callerImageOffset")
    payload["hits"].append(
        {
            "seed": "LoadPackage",
            "callerImageOffset": "0x9100",
            "ripImageOffset": "0x9000",
            "targetImageCaller": True,
            "tracePidMatchesRequested": True,
            "traceAddressMatchesBase": True,
            "caller": {"ip": "0xa100"},
        }
    )
    payload["familyCandidates"] = {
        "LoadPackage": {
            "hitIndex": 0,
            "seed": "LoadPackage",
            "missingCallFrameOffsets": ["callerImageOffset"],
            "reviewScore": 16,
        }
    }
    payload["concreteReviewPriority"] = [
        {
            "hitIndex": 1,
            "seed": "LoadPackage",
            "reviewScore": 18,
        }
    ]
    return payload


def abi_review(
    seed="StaticLoadClass",
    ready=True,
    source="/tmp/trace.log",
    hit_index=0,
    caller_offset="0x5000",
    rip_offset="0x4ff0",
):
    role = "PackageName" if seed == "LoadPackage" else "Name"
    return {
        "schemaVersion": "dune-ue4ss-package-abi-review/v1",
        "sourceEvidence": source,
        "sourceLogSha256": "trace-log-sha256",
        "sourceEvidenceJson": "/tmp/evidence.json",
        "sourceEvidenceJsonSha256": "evidence-json-sha256",
        "sourceLogExists": True,
        "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
        "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
        "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        "sourceExternalPlan": "/tmp/external-plan.json",
        "tracePid": 4242,
        "imageRangeSource": "pid",
        "imageBase": "0x100000",
        "imageStart": "0x200000",
        "imageEnd": "0x7000000",
        "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
        "imagePerms": "r-xp",
        "hitIndex": hit_index,
        "selectedHitSeed": seed,
        "signatureFamily": seed,
        "callerImageOffset": caller_offset,
        "ripImageOffset": rip_offset,
        "readyForManualAbiReview": ready,
        "blockers": [] if ready else ["required argument roles are missing or null: rdx:Name"],
        "arguments": [
            {
                "register": "rdx",
                "role": role,
                "capturedValue": "0x0" if not ready else "0x3",
                "kind": "pointer",
                "reviewCategory": "path-or-name-pointer",
                "required": True,
                "looksSane": ready,
                "memory": {
                    "provided": ready,
                    "lineCount": 2 if ready else 0,
                    "hints": {
                        "candidateTcharLayouts": [{"unitBytes": 2, "sample": "/Game"}] if ready else [],
                        "quotedStrings": ["/Game/Probe"] if ready else [],
                    },
                },
            }
        ],
        "stackArgumentDetails": [],
    }


class PackagePromotionEnvTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_static_load_class_review_exports_non_invoking_class_env(self):
        data = evidence("StaticLoadClass")
        data["sourceLogExists"] = True
        manifest = self.module.build_manifest(
            data,
            abi_review=abi_review("StaticLoadClass"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )
        self.assertTrue(manifest["readyForNonInvokingCanary"])
        self.assertEqual(
            manifest["promotionAcceptanceSchemaVersion"],
            "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        )
        self.assertIs(manifest["sourceLogExists"], True)
        self.assertEqual(manifest["sourceEvidenceJsonSha256"], "evidence-json-sha256")
        self.assertEqual(manifest["sourceLogSha256"], "trace-log-sha256")
        self.assertEqual(manifest["tracePid"], 4242)
        self.assertEqual(manifest["imageRangeSource"], "pid")
        self.assertEqual(manifest["imageBase"], "0x100000")
        self.assertEqual(manifest["imageStart"], "0x200000")
        self.assertEqual(manifest["imageEnd"], "0x7000000")
        self.assertEqual(manifest["imagePath"], "/srv/dune/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(manifest["imagePerms"], "r-xp")
        self.assertFalse(manifest["readyForNativeInvoke"])
        self.assertEqual(manifest["callerImageOffset"], "0x5000")
        self.assertEqual(manifest["ripImageOffset"], "0x4ff0")
        self.assertEqual(manifest["selectedHitSeed"], "StaticLoadClass")
        self.assertEqual(manifest["env"]["DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI"], "true")
        self.assertIn("pid=4242", manifest["env"]["DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"])
        self.assertIn(
            "evidenceJsonSha256=evidence-json-sha256",
            manifest["env"]["DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"],
        )
        self.assertIn(
            "sourceLogSha256=trace-log-sha256",
            manifest["env"]["DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"],
        )
        self.assertNotIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", manifest["env"])
        self.assertEqual(manifest["env"]["DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS"], "true")
        self.assertEqual(manifest["env"]["DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE"], "false")
        self.assertEqual(
            manifest["requiredPromotionFlags"],
            ["--reviewed-target-image", "--reviewed-abi", "--reviewed-class-root"],
        )
        self.assertEqual(manifest["missingReviewFlags"], [])
        self.assertEqual(
            manifest["missingNativeInvokeFlags"],
            ["--allow-native-invoke", "--final-native-call"],
        )
        self.assertIn("--allow-native-invoke", manifest["nextStep"])
        rendered = self.module.render_env(manifest)
        self.assertIn("# sourceEvidenceJsonSha256=evidence-json-sha256", rendered)
        self.assertIn("# sourceLogSha256=trace-log-sha256", rendered)
        self.assertIn("# sourceLogExists=True", rendered)
        self.assertIn("# tracePid=4242", rendered)
        self.assertIn("# imageRangeSource=pid", rendered)
        self.assertIn("# imageBase=0x100000", rendered)
        self.assertIn("# imagePath=/srv/dune/DuneSandboxServer-Linux-Shipping", rendered)
        self.assertIn("# hitIndex=0", rendered)
        self.assertIn("# selectedHitSeed=StaticLoadClass", rendered)
        self.assertIn("# callerImageOffset=0x5000", rendered)
        self.assertIn("# ripImageOffset=0x4ff0", rendered)

        markdown = self.module.render_markdown(manifest)
        self.assertIn("Trace PID: `4242`", markdown)
        self.assertIn("Image range source: `pid`", markdown)
        self.assertIn("Image path: `/srv/dune/DuneSandboxServer-Linux-Shipping`", markdown)

    def test_mismatched_abi_review_evidence_digest_blocks_promotion(self):
        review = abi_review("LoadPackage")
        review["sourceEvidenceJsonSha256"] = "stale-evidence-json-sha256"

        manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            signature_family="LoadPackage",
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("ABI review report does not match selected hit/signature/evidence", manifest["blockers"])

    def test_cli_rejects_wrong_schema_trace_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "not-trace-evidence.json"
            payload = evidence("LoadPackage")
            payload["schemaVersion"] = "dune-ue4ss-package-runtime-trace-plan/v1"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                self.module.main([str(path), "--format", "json"])

        self.assertIn("expected 'dune-ue4ss-package-runtime-trace-evidence/v1'", str(raised.exception))

    def test_cli_rejects_wrong_schema_abi_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_path = Path(temp_dir) / "trace-evidence.json"
            review_path = Path(temp_dir) / "not-abi-review.json"
            evidence_path.write_text(json.dumps(evidence("LoadPackage")), encoding="utf-8")
            review = abi_review("LoadPackage")
            review["schemaVersion"] = "dune-ue4ss-package-promotion-env/v1"
            review_path.write_text(json.dumps(review), encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                self.module.main(
                    [
                        str(evidence_path),
                        "--abi-review-json",
                        str(review_path),
                        "--format",
                        "json",
                    ]
                )

        self.assertIn("expected 'dune-ue4ss-package-abi-review/v1'", str(raised.exception))

    def test_static_load_object_review_requires_tchar_for_asset_path(self):
        manifest = self.module.build_manifest(
            evidence("StaticLoadObject"),
            abi_review=abi_review("StaticLoadObject"),
            reviewed_target_image=True,
            reviewed_abi=True,
            tchar_unit_bytes=2,
            reviewed_tchar=True,
        )
        self.assertTrue(manifest["readyForNonInvokingCanary"])
        self.assertEqual(manifest["env"]["DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI"], "true")
        self.assertNotIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI", manifest["env"])
        self.assertEqual(manifest["env"]["DUNE_PROBE_LOADER_CONFIRM_TCHAR_LAYOUT"], "true")
        self.assertEqual(manifest["env"]["DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE"], "false")
        self.assertEqual(
            manifest["requiredPromotionFlags"],
            ["--reviewed-target-image", "--reviewed-abi", "--reviewed-tchar", "--tchar-unit-bytes <1|2|4>"],
        )
        self.assertEqual(manifest["missingReviewFlags"], [])

    def test_exported_env_keys_match_signature_family(self):
        class_manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            abi_review=abi_review("StaticLoadClass"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )
        asset_manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(any("LOAD_ASSET_PACKAGE" in key for key in class_manifest["env"]))
        self.assertFalse(any("TCHAR" in key for key in class_manifest["env"]))
        self.assertFalse(any("LOAD_CLASS_PACKAGE" in key for key in asset_manifest["env"]))

    def test_blocked_asset_path_reports_missing_review_flags(self):
        manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
        )
        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertEqual(
            manifest["missingReviewFlags"],
            ["--reviewed-abi", "--reviewed-tchar", "--tchar-unit-bytes <1|2|4>"],
        )
        self.assertIn("--reviewed-tchar", manifest["nextStep"])

    def test_target_image_review_must_match_evidence(self):
        bad = evidence("StaticLoadClass")
        bad["hits"][0]["targetImageCaller"] = False
        manifest = self.module.build_manifest(
            bad,
            abi_review=abi_review("StaticLoadClass"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )
        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("reviewed target-image caller evidence is required", manifest["blockers"])

    def test_missing_source_log_blocks_promotion_readiness(self):
        data = evidence("LoadPackage")
        data.pop("sourceLog")
        review = abi_review("LoadPackage", source="")

        manifest = self.module.build_manifest(
            data,
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertFalse(manifest["readyForNativeInvoke"])
        self.assertEqual(manifest["sourceEvidence"], "")
        self.assertIn("missing runtime trace sourceLog provenance", manifest["blockers"])

    def test_missing_source_log_file_blocks_promotion_readiness(self):
        data = evidence("LoadPackage")
        data["sourceLogExists"] = False

        manifest = self.module.build_manifest(
            data,
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertFalse(manifest["readyForNativeInvoke"])
        self.assertEqual(manifest["sourceEvidence"], "/tmp/trace.log")
        self.assertIn("runtime trace sourceLog does not exist", manifest["blockers"])

    def test_missing_source_log_exists_blocks_promotion_readiness(self):
        data = evidence("LoadPackage")
        data.pop("sourceLogExists")

        manifest = self.module.build_manifest(
            data,
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertFalse(manifest["readyForNativeInvoke"])
        self.assertEqual(manifest["sourceEvidence"], "/tmp/trace.log")
        self.assertIn("missing runtime trace sourceLogExists provenance", manifest["blockers"])

    def test_native_invoke_requires_final_confirmation(self):
        manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            abi_review=abi_review("StaticLoadClass"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
            allow_native_invoke=True,
        )
        self.assertFalse(manifest["readyForNativeInvoke"])
        self.assertIn("native invoke requested but final native-call confirmation is absent", manifest["blockers"])

    def test_native_invoke_readiness_requires_non_invoking_readiness(self):
        manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            allow_native_invoke=True,
            final_native_call=True,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertFalse(manifest["readyForNativeInvoke"])
        self.assertIn("reviewed TCHAR layout evidence is required for LoadAsset package promotion", manifest["blockers"])

    def test_empty_evidence_emits_placeholder_manifest(self):
        manifest = self.module.build_manifest({"sourceLog": "/tmp/missing.log", "hits": []})
        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertEqual(manifest["env"]["DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI"], "false")
        self.assertIn("no runtime trace hits available for package promotion", manifest["blockers"])

    def test_empty_evidence_placeholder_env_matches_requested_family(self):
        class_manifest = self.module.build_manifest(
            {"sourceLog": "/tmp/missing.log", "hits": []},
            signature_family="StaticLoadClass",
        )
        asset_manifest = self.module.build_manifest(
            {"sourceLog": "/tmp/missing.log", "hits": []},
            signature_family="LoadPackage",
        )

        self.assertFalse(any("LOAD_ASSET_PACKAGE" in key for key in class_manifest["env"]))
        self.assertFalse(any("LOAD_CLASS_PACKAGE" in key for key in asset_manifest["env"]))

    def test_empty_auto_evidence_emits_blocked_manifest_without_crashing(self):
        manifest = self.module.build_manifest(
            {"sourceLog": "/tmp/missing.log", "hits": []},
            hit_index="auto",
            signature_family="LoadPackage",
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertEqual(manifest["hitIndex"], 0)
        self.assertEqual(manifest["requestedHitIndex"], "auto")
        self.assertIn("no runtime trace hits available for package promotion", manifest["blockers"])

    def test_explicit_hit_index_must_be_non_negative_integer(self):
        for hit_index in ("later", -1, True, None):
            with self.subTest(hit_index=hit_index):
                with self.assertRaises(ValueError) as raised:
                    self.module.build_manifest(
                        evidence("LoadPackage"),
                        hit_index=hit_index,
                        signature_family="LoadPackage",
                    )

                self.assertIn("hit index must be auto or a non-negative integer", str(raised.exception))

    def test_non_array_hits_emit_blocked_manifest_without_crashing(self):
        data = evidence("LoadPackage")
        data["hits"] = {}

        manifest = self.module.build_manifest(data, signature_family="LoadPackage")

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertFalse(manifest["readyForNativeInvoke"])
        self.assertIn("runtime trace hits must be a JSON array", manifest["blockers"])
        self.assertIn("no runtime trace hits available for package promotion", manifest["blockers"])
        self.assertIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", manifest["env"])
        self.assertNotIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI", manifest["env"])

    def test_non_object_selected_hit_emits_blocked_manifest_without_crashing(self):
        data = evidence("LoadPackage")
        data["hits"] = [[]]

        manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("runtime trace hit 0 must be a JSON object", manifest["blockers"])
        self.assertIn("selected runtime trace hit must be a JSON object", manifest["blockers"])

    def test_malformed_selected_hit_context_shape_blocks_promotion_without_crashing(self):
        cases = (
            ("registers", ["not-object"], "runtime trace hit 0 registers must be a JSON object"),
            ("registers", {"": "0x0"}, "runtime trace hit 0 registers contains an invalid register key"),
            ("registers", {"rsi": 42}, "runtime trace hit 0 registers.rsi must be a string"),
            (
                "missingRequiredMemoryRegisters",
                "rsi",
                "runtime trace hit 0 missingRequiredMemoryRegisters must be a JSON array",
            ),
            (
                "missingRequiredMemoryRegisters",
                ["rsi", 42],
                "runtime trace hit 0 missingRequiredMemoryRegisters[1] must be a string",
            ),
            ("registerMemory", ["not-object"], "runtime trace hit 0 registerMemory must be a JSON object"),
            ("registerMemory", {"": ["0x3:\t0x2f"]}, "runtime trace hit 0 registerMemory contains an invalid register key"),
            ("registerMemory", {"rsi": "0x3:\t0x2f"}, "runtime trace hit 0 registerMemory.rsi must be a JSON array"),
            (
                "registerMemory",
                {"rsi": ["0x3:\t0x2f", 42]},
                "runtime trace hit 0 registerMemory.rsi[1] must be a string",
            ),
            ("disassembly", "not-array", "runtime trace hit 0 disassembly must be a JSON array"),
            ("stack", "not-array", "runtime trace hit 0 stack must be a JSON array"),
            ("backtrace", "not-array", "runtime trace hit 0 backtrace must be a JSON array"),
            ("parseWarnings", "not-array", "runtime trace hit 0 parseWarnings must be a JSON array"),
        )
        for key, value, message in cases:
            with self.subTest(message=message):
                data = evidence("LoadPackage")
                data["hits"][0][key] = value

                manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

                self.assertFalse(manifest["readyForNonInvokingCanary"])
                self.assertFalse(manifest["readyForNativeInvoke"])
                self.assertIn(message, manifest["blockers"])

    def test_selected_hit_missing_required_memory_blocks_promotion(self):
        data = evidence("LoadPackage")
        data["hits"][0]["missingRequiredMemoryRegisters"] = ["rsi", "rdx"]

        manifest = self.module.build_manifest(
            data,
            hit_index=0,
            signature_family="LoadPackage",
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertFalse(manifest["readyForNativeInvoke"])
        self.assertIn(
            "runtime trace hit 0 is missing required memory registers: rsi, rdx",
            manifest["blockers"],
        )

    def test_non_object_recommended_review_blocks_auto_promotion_without_crashing(self):
        data = ranked_multi_hit_evidence()
        data["recommendedReview"] = []

        manifest = self.module.build_manifest(
            data,
            hit_index="auto",
            signature_family="LoadPackage",
            abi_review=abi_review("LoadPackage", hit_index=1, caller_offset="0x9000", rip_offset="0x8ff0"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("recommendedReview must be a JSON object", manifest["blockers"])

    def test_non_array_concrete_review_priority_blocks_auto_promotion_without_crashing(self):
        data = ranked_multi_hit_evidence()
        data["recommendedReview"] = {}
        data["concreteReviewPriority"] = {}

        with self.assertRaises(ValueError) as raised:
            self.module.build_manifest(data, hit_index="auto", signature_family="LoadPackage")

        self.assertIn("no concrete runtime trace review candidate", str(raised.exception))

    def test_missing_armed_session_blocks_direct_promotion(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                data = evidence("LoadPackage")
                data["armedCount"] = 0
                data["hits"][0]["traceLogHasArmed"] = stale_value

                manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

                self.assertFalse(manifest["readyForNonInvokingCanary"])
                self.assertIn("missing trace armed record; cannot prove runtime trace session", manifest["blockers"])
                self.assertIn(
                    "runtime trace hit 0 missing trace armed record; cannot prove runtime trace session",
                    manifest["blockers"],
                )

    def test_multiple_armed_sessions_block_direct_promotion(self):
        data = evidence("LoadPackage")
        data["armedCount"] = 2

        manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("multiple trace armed records; use a fresh single-session trace log", manifest["blockers"])

    def test_stale_trace_pid_session_blocks_direct_promotion(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                data = evidence("LoadPackage")
                data["tracePidMatchesRequested"] = stale_value
                data["hits"][0]["tracePidMatchesRequested"] = stale_value

                manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

                self.assertFalse(manifest["readyForNonInvokingCanary"])
                self.assertIn("trace log armed PID does not match requested runtime PID", manifest["blockers"])
                self.assertIn(
                    "runtime trace hit 0 trace log armed PID does not match requested runtime PID",
                    manifest["blockers"],
                )

    def test_bad_hit_address_base_provenance_blocks_direct_promotion(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                data = evidence("LoadPackage")
                data["hits"][0]["traceAddressMatchesBase"] = stale_value

                manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

                self.assertFalse(manifest["readyForNonInvokingCanary"])
                self.assertIn(
                    "runtime trace hit 0 address does not match image base plus seed imageOffset",
                    manifest["blockers"],
                )
                self.assertIn(
                    "selected runtime trace hit address does not match image base plus seed imageOffset",
                    manifest["blockers"],
                )

    def test_missing_hit_address_base_provenance_blocks_direct_promotion(self):
        data = evidence("LoadPackage")
        data["hits"][0].pop("traceAddressMatchesBase", None)

        manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn(
            "runtime trace hit 0 address does not match image base plus seed imageOffset",
            manifest["blockers"],
        )
        self.assertIn(
            "selected runtime trace hit address does not match image base plus seed imageOffset",
            manifest["blockers"],
        )

    def test_missing_trace_pid_match_provenance_blocks_direct_promotion(self):
        data = evidence("LoadPackage")
        data.pop("tracePidMatchesRequested", None)
        data["hits"][0].pop("tracePidMatchesRequested", None)

        manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("missing runtime trace PID match provenance", manifest["blockers"])
        self.assertIn("selected runtime trace hit is missing PID match provenance", manifest["blockers"])

    def test_missing_trace_plan_acceptance_schema_blocks_direct_promotion(self):
        data = evidence("LoadPackage")
        data.pop("sourcePromotionAcceptanceSchemaVersion")

        manifest = self.module.build_manifest(data, hit_index=0, signature_family="LoadPackage")

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn(
            "runtime trace evidence missing current package promotion acceptance schema provenance",
            manifest["blockers"],
        )

    def test_reviewed_abi_without_abi_review_is_blocked(self):
        manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )
        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI", manifest["env"])
        self.assertNotIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", manifest["env"])
        self.assertIn("reviewed ABI promotion should include --abi-review-json", manifest["blockers"])

    def test_mismatched_abi_review_is_blocked(self):
        manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            abi_review=abi_review("StaticLoadObject"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )
        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("ABI review report does not match selected hit/signature/evidence", manifest["blockers"])
        self.assertIn("ABI review report is not ready for manual ABI review", manifest["blockers"])

    def test_stale_abi_review_caller_offset_is_blocked(self):
        review = abi_review("StaticLoadClass")
        review["callerImageOffset"] = "0xdeadbeef"

        manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("ABI review report does not match selected hit/signature/evidence", manifest["blockers"])
        self.assertIn("ABI review report is not ready for manual ABI review", manifest["blockers"])

    def test_stale_abi_review_selected_hit_seed_is_blocked(self):
        review = abi_review("LoadPackage")
        review["selectedHitSeed"] = "LoadObject"

        manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("ABI review report does not match selected hit/signature/evidence", manifest["blockers"])

    def test_stale_abi_review_trace_pid_is_blocked(self):
        review = abi_review("StaticLoadClass")
        review["tracePid"] = 9999

        manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("ABI review report does not match selected hit/signature/evidence", manifest["blockers"])

    def test_stale_abi_review_image_identity_is_blocked(self):
        review = abi_review("StaticLoadClass")
        review["imagePath"] = "/tmp/other/DuneSandboxServer-Linux-Shipping"

        manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("ABI review report does not match selected hit/signature/evidence", manifest["blockers"])

    def test_missing_abi_review_caller_offset_is_blocked_when_trace_has_offset(self):
        review = abi_review("StaticLoadClass")
        review.pop("callerImageOffset")

        manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("ABI review report does not match selected hit/signature/evidence", manifest["blockers"])

    def test_missing_trace_rip_offset_blocks_promotion_even_with_ready_review(self):
        data = evidence("StaticLoadClass")
        data["hits"][0].pop("ripImageOffset")
        review = abi_review("StaticLoadClass")
        review.pop("ripImageOffset")

        manifest = self.module.build_manifest(
            data,
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("missing ripImageOffset call-frame provenance", manifest["blockers"])

    def test_failed_abi_review_details_are_carried_into_manifest(self):
        manifest = self.module.build_manifest(
            evidence("StaticLoadClass"),
            abi_review=abi_review("StaticLoadClass", ready=False),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )
        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertTrue(manifest["abiReview"]["provided"])
        self.assertFalse(manifest["abiReview"]["ready"])
        self.assertIn("required argument roles are missing or null: rdx:Name", manifest["abiReview"]["blockers"])
        self.assertEqual(manifest["abiReview"]["sourceEvidence"], "/tmp/trace.log")
        self.assertEqual(manifest["abiReview"]["tracePid"], 4242)
        self.assertEqual(manifest["abiReview"]["imageRangeSource"], "pid")
        self.assertEqual(manifest["abiReview"]["imagePath"], "/srv/dune/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(manifest["abiReview"]["hitIndex"], 0)
        self.assertEqual(manifest["abiReview"]["signatureFamily"], "StaticLoadClass")
        self.assertEqual(manifest["abiReview"]["arguments"][0]["role"], "Name")
        self.assertFalse(manifest["abiReview"]["arguments"][0]["looksSane"])

    def test_abi_review_argument_memory_summary_is_carried_into_manifest(self):
        manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )
        package_name = next(item for item in manifest["abiReview"]["arguments"] if item["role"] == "PackageName")
        self.assertEqual(package_name["reviewCategory"], "path-or-name-pointer")
        self.assertTrue(package_name["memory"]["provided"])
        self.assertEqual(package_name["memory"]["lineCount"], 2)
        self.assertEqual(package_name["memory"]["hints"]["candidateTcharLayouts"][0]["unitBytes"], 2)

    def test_malformed_abi_review_shapes_are_carried_as_blockers(self):
        review = abi_review("LoadPackage")
        review["blockers"] = [{"message": "bad role"}]
        review["arguments"] = {
            "register": "rsi",
            "role": "PackageName",
        }
        review["stackArgumentDetails"] = {"slot": 0}

        manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertFalse(manifest["abiReview"]["ready"])
        self.assertIn("ABI review blockers[0] must be a string", manifest["abiReview"]["blockers"])
        self.assertIn("ABI review arguments must be a JSON array", manifest["abiReview"]["blockers"])
        self.assertIn("ABI review stackArgumentDetails must be a JSON array", manifest["abiReview"]["blockers"])
        self.assertIn("ABI review report is not ready for manual ABI review", manifest["blockers"])

    def test_malformed_abi_review_argument_memory_is_carried_as_blocker(self):
        review = abi_review("LoadPackage")
        review["arguments"][0]["memory"] = ["not-object"]
        review["arguments"].append(
            {
                "register": "rdx",
                "role": "Name",
                "memory": {"hints": ["not-object"]},
            }
        )
        review["arguments"].append(
            {
                "register": "rcx",
                "role": "Filename",
                "memory": {"lineCount": "many", "hints": {}},
            }
        )

        manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            abi_review=review,
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertFalse(manifest["abiReview"]["ready"])
        self.assertIn("ABI review argument memory must be a JSON object", manifest["abiReview"]["blockers"])
        self.assertIn("ABI review argument memory hints must be a JSON object", manifest["abiReview"]["blockers"])
        self.assertIn("ABI review argument memory lineCount must be a non-negative integer", manifest["abiReview"]["blockers"])

    def test_hit_index_selects_matching_hit_for_promotion(self):
        manifest = self.module.build_manifest(
            multi_hit_evidence(),
            hit_index=1,
            abi_review=abi_review("StaticLoadClass", hit_index=1, caller_offset="0x7000", rip_offset="0x6ff0"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )
        self.assertTrue(manifest["readyForNonInvokingCanary"])
        self.assertEqual(manifest["hitIndex"], 1)
        self.assertEqual(manifest["signatureFamily"], "StaticLoadClass")
        self.assertEqual(manifest["selectedHitSeed"], "StaticLoadClass")
        self.assertIn("caller=0x7000", manifest["env"]["DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"])
        self.assertIn("rip=0x6ff0", manifest["env"]["DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"])

    def test_auto_hit_index_selects_matching_signature_family_for_promotion(self):
        manifest = self.module.build_manifest(
            multi_hit_evidence(),
            hit_index="auto",
            signature_family="StaticLoadClass",
            abi_review=abi_review("StaticLoadClass", hit_index=1, caller_offset="0x7000", rip_offset="0x6ff0"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )
        self.assertTrue(manifest["readyForNonInvokingCanary"])
        self.assertEqual(manifest["hitIndex"], 1)
        self.assertEqual(manifest["requestedHitIndex"], "auto")
        self.assertEqual(manifest["signatureFamily"], "StaticLoadClass")

    def test_auto_hit_index_uses_ranked_family_candidate_for_promotion(self):
        manifest = self.module.build_manifest(
            ranked_multi_hit_evidence(),
            hit_index="auto",
            signature_family="LoadPackage",
            abi_review=abi_review("LoadPackage", hit_index=1, caller_offset="0x9000", rip_offset="0x8ff0"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )
        self.assertTrue(manifest["readyForNonInvokingCanary"])
        self.assertEqual(manifest["hitIndex"], 1)
        self.assertIn("caller=0x9000", manifest["env"]["DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE"])
        self.assertIn("rip=0x8ff0", manifest["env"]["DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE"])

    def test_auto_hit_index_prefers_concrete_review_priority_for_promotion(self):
        manifest = self.module.build_manifest(
            concrete_priority_evidence(),
            hit_index="auto",
            signature_family="LoadPackage",
            abi_review=abi_review("LoadPackage", hit_index=1, caller_offset="0x9100", rip_offset="0x9000"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )
        self.assertTrue(manifest["readyForNonInvokingCanary"])
        self.assertEqual(manifest["hitIndex"], 1)
        self.assertEqual(manifest["callerImageOffset"], "0x9100")
        self.assertNotIn("missing callerImageOffset call-frame provenance", manifest["blockers"])

    def test_auto_hit_index_rejects_non_concrete_family_candidate(self):
        with self.assertRaises(ValueError) as raised:
            self.module.build_manifest(
                non_concrete_family_candidate_evidence(),
                hit_index="auto",
                signature_family="LoadPackage",
            )

        self.assertIn(
            "no concrete runtime trace review candidate for signature family LoadPackage",
            str(raised.exception),
        )

    def test_auto_hit_index_rejects_malformed_concrete_candidate_index_for_promotion(self):
        for hit_index in (True, -1):
            with self.subTest(hit_index=hit_index):
                with self.assertRaises(ValueError) as raised:
                    self.module.build_manifest(
                        malformed_auto_hit_index_evidence(hit_index),
                        hit_index="auto",
                        signature_family="LoadPackage",
                    )

                self.assertIn(
                    "no concrete runtime trace review candidate for signature family LoadPackage",
                    str(raised.exception),
                )

    def test_explicit_signature_family_must_match_known_hit_seed_for_promotion(self):
        manifest = self.module.build_manifest(
            evidence("LoadPackage"),
            hit_index=0,
            signature_family="StaticLoadClass",
            abi_review=abi_review("StaticLoadClass", hit_index=0),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_class_root=True,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI", manifest["env"])
        self.assertNotIn("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", manifest["env"])
        self.assertIn(
            "selected trace hit seed LoadPackage does not match signature family StaticLoadClass",
            manifest["blockers"],
        )

    def test_explicit_signature_family_must_match_unknown_hit_seed_for_promotion(self):
        payload = evidence("LoadPackage")
        payload["hits"][0]["seed"] = "LoadPackag"

        manifest = self.module.build_manifest(
            payload,
            hit_index=0,
            signature_family="LoadPackage",
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn(
            "selected trace hit seed LoadPackag does not match signature family LoadPackage",
            manifest["blockers"],
        )

    def test_missing_trace_hit_seed_blocks_promotion(self):
        payload = evidence("LoadPackage")
        payload["hits"][0].pop("seed")

        manifest = self.module.build_manifest(
            payload,
            hit_index=0,
            signature_family="LoadPackage",
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("missing trace hit seed provenance", manifest["blockers"])
        self.assertNotIn("seed=", manifest["env"]["DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE"])

    def test_multiline_trace_provenance_blocks_promotion(self):
        payload = evidence("LoadPackage")
        payload["sourceLog"] = "/tmp/trace.log\nold"
        payload["imagePath"] = "/srv/dune/DuneSandboxServer-Linux-Shipping\nold"
        payload["hits"][0]["ripImageOffset"] = "0x4ff0\nold"

        manifest = self.module.build_manifest(
            payload,
            hit_index=0,
            signature_family="LoadPackage",
            abi_review=abi_review("LoadPackage"),
            reviewed_target_image=True,
            reviewed_abi=True,
            reviewed_tchar=True,
            tchar_unit_bytes=2,
        )

        self.assertFalse(manifest["readyForNonInvokingCanary"])
        self.assertIn("sourceLog provenance must be a non-empty single-line value", manifest["blockers"])
        self.assertIn("imagePath provenance must be a non-empty single-line value", manifest["blockers"])
        self.assertIn("ripImageOffset provenance must be a non-empty single-line value", manifest["blockers"])

    def test_markdown_includes_manual_promotion_flags(self):
        manifest = self.module.build_manifest(evidence("StaticLoadClass"), abi_review=abi_review("StaticLoadClass"))
        rendered = self.module.render_markdown(manifest)
        self.assertIn("## Review Flags", rendered)
        self.assertIn("`--reviewed-target-image`", rendered)
        self.assertIn("ready=`false`", rendered)
        self.assertIn("`--reviewed-class-root`", rendered)
        self.assertIn("## Native Invoke Flags", rendered)
        self.assertIn("`--final-native-call`", rendered)
        self.assertIn("Next step:", rendered)

    def test_markdown_includes_abi_review_blockers(self):
        manifest = self.module.build_manifest(evidence("StaticLoadClass"), abi_review=abi_review("StaticLoadClass", ready=False))
        rendered = self.module.render_markdown(manifest)
        self.assertIn("## ABI Review", rendered)
        self.assertIn("required argument roles are missing or null: rdx:Name", rendered)


if __name__ == "__main__":
    unittest.main()
