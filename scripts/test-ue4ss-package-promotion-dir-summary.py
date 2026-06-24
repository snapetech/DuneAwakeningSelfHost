#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize-ue4ss-package-promotion-dir.py"
LOAD_PACKAGE_TRACE_EVIDENCE = (
    "runtime-trace:LoadPackage:seed=LoadPackage caller=0x5000 rip=0x4ff0 "
    "pid=4242 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)


def load_module():
    spec = importlib.util.spec_from_file_location("package_promotion_dir_summary", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(family, ready=False, native=False):
    return {
        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
        "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        "signatureFamily": family,
        "hitIndex": 0,
        "selectedHitSeed": family,
        "sourceEvidence": "/tmp/trace.log",
        "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
        "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "sourceLogExists": True,
        "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
        "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
        "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
        "sourceExternalPlan": "/tmp/external-plan.json",
        "tracePidMatchesRequested": True,
        "tracePid": 4242,
        "callerImageOffset": "0x5000",
        "ripImageOffset": "0x4ff0",
        "readyForNonInvokingCanary": ready,
        "readyForNativeInvoke": native,
        "abiReviewReady": ready,
        "targetImageReviewed": ready,
        "abiReviewed": ready,
        "tcharReviewed": family != "StaticLoadClass" and ready,
        "classRootReviewed": family == "StaticLoadClass" and ready,
        "missingReviewFlags": [] if ready else ["--reviewed-abi"],
        "missingNativeInvokeFlags": [] if native else ["--allow-native-invoke", "--final-native-call"],
        "blockers": [] if ready else ["reviewed ABI evidence is required"],
        "abiReview": {
            "ready": ready,
            "blockers": [] if ready else ["required argument roles are missing or null: rdx:Name"],
        },
        "nextStep": "feed promotion env into next lua-dispatch canary" if native else "complete manual review",
        "env": (
            {
                (
                    "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"
                    if family == "StaticLoadClass"
                    else "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE"
                ): (
                    f"runtime-trace:{family}:seed={family} caller=0x5000 rip=0x4ff0 "
                    "pid=4242 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                ),
            }
            if ready or native
            else {}
        ),
    }


class PackagePromotionDirSummaryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_summarizes_ready_and_blocked_family_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            (root / "LoadPackage").mkdir()
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(manifest("StaticLoadClass", ready=True)),
                encoding="utf-8",
            )
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(manifest("LoadPackage")),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)

        self.assertEqual(summary["manifestCount"], 2)
        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 1)
        self.assertEqual(summary["blockedCount"], 1)
        self.assertEqual(summary["readyFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertEqual(len(summary["readyManifestPaths"]), 1)
        self.assertIn("StaticLoadClass/promotion-env.json", summary["readyManifestPaths"][0])
        self.assertEqual(summary["nextCanaryArgs"][0], "--package-promotion-dir")
        self.assertEqual(summary["nextCanaryReadyArgs"][0], "--package-promotion-json")
        self.assertIn("StaticLoadClass/promotion-env.json", summary["nextCanaryReadyArgs"][1])
        blocked = next(row for row in summary["manifests"] if row["signatureFamily"] == "LoadPackage")
        self.assertIn("--reviewed-abi", blocked["missingReviewFlags"])
        self.assertEqual(blocked["callerImageOffset"], "0x5000")
        self.assertEqual(blocked["ripImageOffset"], "0x4ff0")
        self.assertEqual(blocked["selectedHitSeed"], "LoadPackage")
        self.assertEqual(blocked["sourceEvidenceJsonSha256"], "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertEqual(blocked["sourceLogSha256"], "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        self.assertIs(blocked["sourceLogExists"], True)
        self.assertIs(blocked["tracePidMatchesRequested"], True)
        self.assertIn("feed ready non-invoking package promotion manifests", summary["nextStep"])

    def test_summary_rows_preserve_source_log_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage")
            payload["sourceLogExists"] = True
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        row = summary["manifests"][0]
        self.assertIs(row["sourceLogExists"], True)
        self.assertEqual(row["sourceEvidenceJson"], "/tmp/ue4ss-package-runtime-trace-evidence.json")
        self.assertEqual(row["sourceEvidenceJsonSha256"], "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertEqual(row["sourceLogSha256"], "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        self.assertIn("sourceLogExists=`true`", rendered)
        self.assertIs(row["tracePidMatchesRequested"], True)
        self.assertIn("tracePidMatchesRequested=`true`", rendered)

    def test_summary_rows_preserve_runtime_target_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload.update(
                {
                    "tracePid": 4242,
                    "imageRangeSource": "pid",
                    "imageBase": "0x100000",
                    "imageStart": "0x200000",
                    "imageEnd": "0x7000000",
                    "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
                    "imagePerms": "r-xp",
                }
            )
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)

        row = summary["manifests"][0]
        self.assertEqual(row["tracePid"], 4242)
        self.assertEqual(row["imageRangeSource"], "pid")
        self.assertEqual(row["imageBase"], "0x100000")
        self.assertEqual(row["imageStart"], "0x200000")
        self.assertEqual(row["imageEnd"], "0x7000000")
        self.assertEqual(row["imagePath"], "/srv/dune/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(row["imagePerms"], "r-xp")

    def test_non_object_manifest_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            (root / "LoadPackage" / "promotion-env.json").write_text("[]", encoding="utf-8")
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["manifestCount"], 1)
        self.assertEqual(summary["errorCount"], 1)
        self.assertEqual(summary["blockedCount"], 1)
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertEqual(summary["errors"][0]["error"], "promotion manifest must be a JSON object")
        self.assertIn("promotion manifest must be a JSON object", summary["manifests"][0]["blockers"])
        self.assertIn("promotion manifest must be a JSON object", rendered)

    def test_non_object_review_priority_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(manifest("LoadPackage", ready=True)),
                encoding="utf-8",
            )
            (root / "LoadPackage" / "review-priority.json").write_text("[]", encoding="utf-8")
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["manifestCount"], 1)
        self.assertEqual(summary["errorCount"], 2)
        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertIn("review priority must be a JSON object", [row["error"] for row in summary["errors"]])
        self.assertIn("review priority must be a JSON object", summary["manifests"][0]["blockers"])
        self.assertIn("review priority must be a JSON object", rendered)

    def test_summary_rows_preserve_env_and_embedded_hit_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": LOAD_PACKAGE_TRACE_EVIDENCE,
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true",
            }
            payload["hit"] = {
                "seed": "LoadPackage",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "traceAddressMatchesBase": True,
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)

        row = summary["manifests"][0]
        self.assertEqual(
            row["env"]["DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE"],
            LOAD_PACKAGE_TRACE_EVIDENCE,
        )
        self.assertEqual(row["hit"]["seed"], "LoadPackage")
        self.assertIs(row["hit"]["traceAddressMatchesBase"], True)

    def test_ready_manifest_with_malformed_env_values_is_demoted(self):
        cases = (
            ("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", "", "package promotion env contains a non-empty single-line scalar violation for DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI"),
            ("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", "true\nfalse", "package promotion env contains a non-empty single-line scalar violation for DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI"),
            ("DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI", ["true"], "package promotion env contains a non-scalar value for DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI"),
        )
        for key, value, message in cases:
            with self.subTest(key=key, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "LoadPackage").mkdir()
                    payload = manifest("LoadPackage", ready=True)
                    payload["env"] = {key: value}
                    (root / "LoadPackage" / "promotion-env.json").write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    summary = self.module.build_summary(root)

                self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
                self.assertEqual(summary["readyManifestPaths"], [])
                self.assertIn(message, summary["manifests"][0]["blockers"])

    def test_markdown_reports_missing_flags_and_abi_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(manifest("LoadPackage")),
                encoding="utf-8",
            )
            rendered = self.module.markdown(self.module.build_summary(root))

        self.assertIn("# UE4SS Package Promotion Directory", rendered)
        self.assertIn("`LoadPackage`", rendered)
        self.assertIn("missing review flag: `--reviewed-abi`", rendered)
        self.assertIn("ABI review blocker: required argument roles are missing or null: rdx:Name", rendered)

    def test_markdown_reports_ready_only_canary_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(manifest("StaticLoadClass", ready=True)),
                encoding="utf-8",
            )
            rendered = self.module.markdown(self.module.build_summary(root))

        self.assertIn("Ready-only canary args:", rendered)
        self.assertIn("--package-promotion-json", rendered)

    def test_review_priority_orders_manifest_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            (root / "StaticLoadClass").mkdir()
            (root / "LoadPackage" / "review-priority.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                        "rank": 0,
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 3,
                    }
                ),
                encoding="utf-8",
            )
            (root / "StaticLoadClass" / "review-priority.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                        "rank": 1,
                        "signatureFamily": "StaticLoadClass",
                        "hitIndex": "auto",
                    }
                ),
                encoding="utf-8",
            )
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(manifest("StaticLoadClass", ready=True)),
                encoding="utf-8",
            )
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(manifest("LoadPackage")),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["manifests"][0]["signatureFamily"], "LoadPackage")
        self.assertEqual(summary["manifests"][0]["reviewPriority"], 0)
        self.assertEqual(summary["manifests"][0]["reviewPriorityHitIndex"], 3)
        self.assertEqual(summary["manifests"][1]["signatureFamily"], "StaticLoadClass")
        self.assertEqual(summary["readyFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("`LoadPackage` reviewPriority=`0` reviewHitIndex=`3`", rendered)
        self.assertIn("`StaticLoadClass` reviewPriority=`1` reviewHitIndex=`auto`", rendered)

    def test_invalid_review_priority_metadata_reports_errors(self):
        for rank, hit_index in (("0", "bad"), (True, True), (-1, -1)):
            with self.subTest(rank=rank, hit_index=hit_index):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "LoadPackage").mkdir()
                    (root / "LoadPackage" / "review-priority.json").write_text(
                        json.dumps(
                            {
                                "schemaVersion": "wrong",
                                "rank": rank,
                                "hitIndex": hit_index,
                                "signatureFamily": "StaticLoadClass",
                            }
                        ),
                        encoding="utf-8",
                    )
                    (root / "LoadPackage" / "promotion-env.json").write_text(
                        json.dumps(manifest("LoadPackage")),
                        encoding="utf-8",
                    )
                    summary = self.module.build_summary(root)
                    rendered = self.module.markdown(summary)

                self.assertEqual(summary["errorCount"], 5)
                self.assertIsNone(summary["manifests"][0]["reviewPriority"])
                self.assertIn("unsupported review priority schemaVersion", rendered)
                self.assertIn("invalid review priority rank", rendered)
                self.assertIn("invalid review priority hitIndex", rendered)
                self.assertIn("review priority signatureFamily does not match parent directory", rendered)
                self.assertIn("review priority signatureFamily does not match promotion manifest", rendered)

    def test_ready_manifest_with_invalid_review_priority_is_demoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            (root / "LoadPackage" / "review-priority.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "wrong",
                        "rank": "0",
                        "hitIndex": "bad",
                        "signatureFamily": "StaticLoadClass",
                    }
                ),
                encoding="utf-8",
            )
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(manifest("LoadPackage", ready=True)),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        blockers = summary["manifests"][0]["blockers"]
        self.assertIn("unsupported review priority schemaVersion", blockers)
        self.assertIn("invalid review priority rank", blockers)
        self.assertIn("invalid review priority hitIndex", blockers)
        self.assertIn("unsupported review priority schemaVersion", rendered)

    def test_manifest_family_must_match_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["errorCount"], 1)
        self.assertEqual(summary["manifests"][0]["signatureFamily"], "StaticLoadClass")
        self.assertIn("promotion manifest signatureFamily does not match parent directory", rendered)

    def test_ready_manifest_with_unsupported_signature_family_is_demoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadAsset").mkdir()
            payload = manifest("LoadAsset", ready=True)
            (root / "LoadAsset" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadAsset"])
        self.assertIn("unsupported package promotion signatureFamily: LoadAsset", summary["manifests"][0]["blockers"])
        self.assertIn("unsupported package promotion signatureFamily: LoadAsset", rendered)

    def test_review_priority_hit_index_must_match_promotion_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            (root / "LoadPackage" / "review-priority.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                        "rank": 0,
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 1,
                    }
                ),
                encoding="utf-8",
            )
            payload = manifest("LoadPackage", ready=True)
            payload["hitIndex"] = 0
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["errorCount"], 1)
        self.assertEqual(summary["manifests"][0]["reviewPriorityHitIndex"], 1)
        self.assertEqual(summary["manifests"][0]["hitIndex"], 0)
        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("review priority hitIndex does not match promotion manifest", summary["manifests"][0]["blockers"])
        self.assertIn("review priority hitIndex does not match promotion manifest", rendered)

    def test_invalid_ready_manifest_schema_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["schemaVersion"] = "wrong"
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["manifestCount"], 1)
        self.assertEqual(summary["errorCount"], 1)
        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("invalid package promotion manifest schema", rendered)

    def test_ready_manifest_with_blockers_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["blockers"] = ["manual blocker left behind"]
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn("ready package promotion manifest still has blockers", rendered)

    def test_manifest_list_fields_must_be_json_arrays_of_strings(self):
        cases = (
            ("missingReviewFlags", "--reviewed-abi", "missingReviewFlags must be a JSON array"),
            ("missingNativeInvokeFlags", ["--allow-native-invoke", 42], "missingNativeInvokeFlags[1] must be a string"),
            ("blockers", "manual blocker left behind", "blockers must be a JSON array"),
        )
        for key, value, message in cases:
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "LoadPackage").mkdir()
                    payload = manifest("LoadPackage")
                    payload[key] = value
                    (root / "LoadPackage" / "promotion-env.json").write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    summary = self.module.build_summary(root)

                self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
                self.assertIn(message, summary["manifests"][0]["blockers"])
                self.assertIn(message, [row["error"] for row in summary["errors"]])

    def test_ready_manifest_with_malformed_list_fields_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["missingReviewFlags"] = "--reviewed-abi"
            payload["missingNativeInvokeFlags"] = ["--final-native-call", 42]
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)

        blockers = summary["manifests"][0]["blockers"]
        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertIn("missingReviewFlags must be a JSON array", blockers)
        self.assertIn("missingNativeInvokeFlags[1] must be a string", blockers)

    def test_malformed_abi_review_shape_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload["abiReview"] = ["not-object"]
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertIn("abiReview must be a JSON object", summary["manifests"][0]["blockers"])
        self.assertIn("abiReview must be a JSON object", [row["error"] for row in summary["errors"]])

    def test_malformed_abi_review_blockers_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload["abiReview"]["blockers"] = [{"message": "missing role"}]
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertIn("abiReview.blockers[0] must be a string", summary["manifests"][0]["blockers"])

    def test_malformed_abi_review_argument_memory_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload["abiReview"]["arguments"] = [
                {"memory": {"lineCount": "many", "hints": []}},
                {"memory": []},
            ]
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertIn("abiReview.arguments[0].memory.lineCount must be a non-negative integer", rendered)
        self.assertIn("abiReview.arguments[0].memory.hints must be a JSON object", rendered)
        self.assertIn("abiReview.arguments[1].memory must be a JSON object", rendered)

    def test_ready_manifest_missing_rip_offset_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload.pop("ripImageOffset")
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn("ready package promotion manifest is missing ripImageOffset", rendered)

    def test_ready_manifest_missing_trace_identity_is_not_counted_ready(self):
        for hit_index in ("auto", True, -1):
            with self.subTest(hit_index=hit_index):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "StaticLoadClass").mkdir()
                    payload = manifest("StaticLoadClass", ready=True)
                    payload.pop("sourceEvidence")
                    payload["hitIndex"] = hit_index
                    payload.pop("selectedHitSeed")
                    (root / "StaticLoadClass" / "promotion-env.json").write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    summary = self.module.build_summary(root)
                    rendered = self.module.markdown(summary)

                self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
                self.assertEqual(summary["readyManifestPaths"], [])
                self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
                self.assertEqual(summary["errorCount"], 3)
                self.assertIn("ready package promotion manifest is missing sourceEvidence", rendered)
                self.assertIn("ready package promotion manifest is missing concrete hitIndex", rendered)
                self.assertIn("ready package promotion manifest is missing selectedHitSeed", rendered)

    def test_ready_manifest_multiline_identity_fields_are_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload["sourceEvidence"] = "/tmp/trace.log\nstale"
            payload["imagePath"] = "/srv/dune/DuneSandboxServer-Linux-Shipping\nold"
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 2)
        self.assertIn(
            "package promotion manifest sourceEvidence must be a non-empty single-line scalar",
            rendered,
        )
        self.assertIn(
            "package promotion manifest imagePath must be a non-empty single-line scalar",
            rendered,
        )

    def test_ready_manifest_missing_source_log_file_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload["sourceLogExists"] = False
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn("ready package promotion manifest sourceLog does not exist", rendered)

    def test_ready_manifest_missing_source_log_exists_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload.pop("sourceLogExists")
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn("ready package promotion manifest is missing sourceLogExists", rendered)

    def test_ready_manifest_missing_digest_provenance_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload.pop("sourceEvidenceJson")
            payload.pop("sourceEvidenceJsonSha256")
            payload.pop("sourceLogSha256")
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 3)
        self.assertIn("ready package promotion manifest is missing sourceEvidenceJson provenance", rendered)
        self.assertIn("ready package promotion manifest is missing sourceEvidenceJsonSha256 provenance", rendered)
        self.assertIn("ready package promotion manifest is missing sourceLogSha256 provenance", rendered)

    def test_ready_manifest_malformed_digest_provenance_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload["sourceEvidenceJsonSha256"] = "not-a-sha256"
            payload["sourceLogSha256"] = "also-not-a-sha256"
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertIn("ready package promotion manifest has invalid sourceEvidenceJsonSha256", rendered)
        self.assertIn("ready package promotion manifest has invalid sourceLogSha256", rendered)

    def test_ready_manifest_missing_trace_pid_match_provenance_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload.pop("tracePidMatchesRequested")
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn(
            "ready package promotion manifest is missing runtime trace PID match provenance",
            rendered,
        )

    def test_ready_manifest_missing_or_zero_trace_pid_is_not_counted_ready(self):
        for trace_pid in (None, 0):
            with self.subTest(trace_pid=trace_pid):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "StaticLoadClass").mkdir()
                    payload = manifest("StaticLoadClass", ready=True)
                    if trace_pid is None:
                        payload.pop("tracePid")
                    else:
                        payload["tracePid"] = trace_pid
                    (root / "StaticLoadClass" / "promotion-env.json").write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    summary = self.module.build_summary(root)
                    rendered = self.module.markdown(summary)

                self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
                self.assertEqual(summary["readyManifestPaths"], [])
                self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
                self.assertIn("ready package promotion manifest is missing concrete tracePid", rendered)

    def test_ready_manifest_missing_acceptance_schema_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload.pop("promotionAcceptanceSchemaVersion")
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn(
            "ready package promotion manifest is missing current package promotion acceptance schema",
            rendered,
        )

    def test_ready_manifest_missing_trace_plan_provenance_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload.pop("sourceTracePlan")
            payload.pop("sourceTracePlanSchemaVersion")
            payload.pop("sourcePromotionAcceptanceSchemaVersion")
            payload.pop("sourceExternalPlan")
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 4)
        self.assertIn("ready package promotion manifest is missing sourceTracePlan provenance", rendered)
        self.assertIn("ready package promotion manifest is missing sourceTracePlanSchemaVersion provenance", rendered)
        self.assertIn(
            "ready package promotion manifest is missing current source promotion acceptance schema provenance",
            rendered,
        )
        self.assertIn("ready package promotion manifest is missing sourceExternalPlan provenance", rendered)

    def test_ready_manifest_missing_abi_review_ready_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload.pop("abiReviewReady")
            payload["abiReview"]["ready"] = False
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn("ready package promotion manifest is missing ABI review readiness", rendered)

    def test_ready_manifest_missing_abi_reviewed_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload["abiReviewed"] = False
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn("ready package promotion manifest is missing reviewed ABI confirmation", rendered)

    def test_ready_manifest_missing_target_and_family_review_confirmations_is_not_counted_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["targetImageReviewed"] = False
            payload["tcharReviewed"] = False
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertEqual(summary["errorCount"], 2)
        self.assertIn("ready package promotion manifest is missing reviewed target-image confirmation", rendered)
        self.assertIn("ready package promotion manifest is missing reviewed TCHAR confirmation", rendered)

    def test_ready_manifest_embedded_hit_identity_must_match(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "LoadPackage").mkdir()
                    payload = manifest("LoadPackage", ready=True)
                    payload["hit"] = {
                        "seed": "LoadObject",
                        "callerImageOffset": "0x6000",
                        "ripImageOffset": "0x5ff0",
                        "traceAddressMatchesBase": stale_value,
                    }
                    (root / "LoadPackage" / "promotion-env.json").write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    summary = self.module.build_summary(root)
                    rendered = self.module.markdown(summary)

                self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
                self.assertEqual(summary["readyManifestPaths"], [])
                self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
                self.assertEqual(summary["errorCount"], 5)
                self.assertIn("selectedHitSeed does not match embedded trace hit seed", rendered)
                self.assertIn("embedded trace hit seed does not match signatureFamily", rendered)
                self.assertIn("embedded trace hit callerImageOffset does not match manifest", rendered)
                self.assertIn("embedded trace hit ripImageOffset does not match manifest", rendered)
                self.assertIn("embedded trace hit address does not match image base plus seed imageOffset", rendered)

    def test_ready_manifest_embedded_hit_requires_trace_base_match_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["hit"] = {
                "seed": "LoadPackage",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("embedded trace hit address does not match image base plus seed imageOffset", rendered)

    def test_ready_manifest_embedded_hit_must_have_required_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["hit"] = {
                "seed": "LoadPackage",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "traceAddressMatchesBase": True,
                "missingRequiredMemoryRegisters": ["rsi"],
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("embedded trace hit is missing required memory registers: rsi", rendered)

    def test_ready_manifest_embedded_hit_rejects_malformed_missing_required_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["hit"] = {
                "seed": "LoadPackage",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "traceAddressMatchesBase": True,
                "missingRequiredMemoryRegisters": "rsi",
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("embedded trace hit missingRequiredMemoryRegisters must be a JSON array", rendered)

    def test_ready_manifest_embedded_hit_rejects_malformed_register_memory(self):
        cases = (
            (["not-object"], "embedded trace hit registerMemory must be a JSON object"),
            ({"": ["0x3:\t0x2f"]}, "embedded trace hit registerMemory contains an invalid register key"),
            ({"rsi": "0x3:\t0x2f"}, "embedded trace hit registerMemory.rsi must be a JSON array"),
            ({"rsi": ["0x3:\t0x2f", 42]}, "embedded trace hit registerMemory.rsi[1] must be a string"),
        )
        for register_memory, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "LoadPackage").mkdir()
                    payload = manifest("LoadPackage", ready=True)
                    payload["hit"] = {
                        "seed": "LoadPackage",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "traceAddressMatchesBase": True,
                        "registerMemory": register_memory,
                    }
                    (root / "LoadPackage" / "promotion-env.json").write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    summary = self.module.build_summary(root)
                    rendered = self.module.markdown(summary)

                self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
                self.assertEqual(summary["readyManifestPaths"], [])
                self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
                self.assertIn(message, rendered)

    def test_ready_manifest_rejects_stale_session_flags(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "LoadPackage").mkdir()
                    payload = manifest("LoadPackage", ready=True)
                    payload["tracePidMatchesRequested"] = stale_value
                    payload["hit"] = {
                        "seed": "LoadPackage",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "traceAddressMatchesBase": True,
                        "traceLogHasArmed": stale_value,
                        "tracePidMatchesRequested": stale_value,
                    }
                    (root / "LoadPackage" / "promotion-env.json").write_text(
                        json.dumps(payload),
                        encoding="utf-8",
                    )
                    summary = self.module.build_summary(root)
                    rendered = self.module.markdown(summary)

                self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
                self.assertEqual(summary["readyManifestPaths"], [])
                self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
                self.assertIn("trace log armed PID does not match requested runtime PID", rendered)
                self.assertIn("embedded trace hit missing trace armed record; cannot prove runtime trace session", rendered)
                self.assertIn("embedded trace hit trace log armed PID does not match requested runtime PID", rendered)

    def test_ready_manifest_selected_hit_seed_must_match_signature_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["selectedHitSeed"] = "LoadObject"
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertIn("selectedHitSeed does not match signatureFamily", rendered)

    def test_native_ready_manifest_requires_non_invoking_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True, native=True)
            payload["readyForNonInvokingCanary"] = False
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyForNativeInvokeCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("ready native package promotion manifest is missing non-invoking canary readiness", rendered)

    def test_ready_manifest_runtime_trace_env_evidence_must_match_call_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:caller=0x5000 rip=0x5ff0",
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("env evidence rip does not match ripImageOffset", rendered)

    def test_ready_manifest_runtime_trace_env_family_must_match_signature_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadObject:caller=0x5000 rip=0x4ff0",
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("env evidence family does not match signatureFamily", rendered)

    def test_ready_manifest_runtime_trace_env_seed_must_match_signature_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:seed=LoadObject caller=0x5000 rip=0x4ff0",
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("env evidence seed does not match signatureFamily", rendered)

    def test_ready_manifest_runtime_trace_env_provenance_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                    "runtime-trace:LoadPackage:seed=LoadPackage caller=0x5000 rip=0x4ff0 "
                    "pid=999 evidenceJsonSha256=stale-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=stale-log-sha256"
                ),
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("env evidence pid does not match tracePid", rendered)
        self.assertIn("env evidence digest does not match sourceEvidenceJsonSha256", rendered)
        self.assertIn("env evidence log digest does not match sourceLogSha256", rendered)

    def test_ready_manifest_runtime_trace_env_provenance_requires_exact_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                    "runtime-trace:LoadPackage:seed=LoadPackage caller=0x50000 rip=0x4ff00 "
                    "pid=42424 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-stale "
                    "sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-stale"
                ),
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("env evidence caller does not match callerImageOffset", rendered)
        self.assertIn("env evidence rip does not match ripImageOffset", rendered)
        self.assertIn("env evidence pid does not match tracePid", rendered)
        self.assertIn("env evidence digest does not match sourceEvidenceJsonSha256", rendered)
        self.assertIn("env evidence log digest does not match sourceLogSha256", rendered)

    def test_ready_manifest_requires_hex_image_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["callerImageOffset"] = "5000"
            payload["ripImageOffset"] = "0xnothex"
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                    "runtime-trace:LoadPackage:seed=LoadPackage caller=5000 rip=0xnothex "
                    "pid=4242 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                ),
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertIn("ready package promotion manifest has invalid callerImageOffset", rendered)
        self.assertIn("ready package promotion manifest has invalid ripImageOffset", rendered)

    def test_manifest_env_keys_must_match_signature_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StaticLoadClass").mkdir()
            payload = manifest("StaticLoadClass", ready=True)
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                    "runtime-trace:StaticLoadClass:seed=StaticLoadClass caller=0x5000 rip=0x4ff0 "
                    "pid=4242 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                ),
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true",
            }
            (root / "StaticLoadClass" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["StaticLoadClass"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn("StaticLoadClass promotion env includes LoadAsset package keys", rendered)

    def test_ready_manifest_env_must_be_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["env"] = ["DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI=true"]
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertEqual(summary["errorCount"], 1)
        self.assertIn("package promotion env must be an object", rendered)

    def test_ready_manifest_env_values_must_be_scalar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LoadPackage").mkdir()
            payload = manifest("LoadPackage", ready=True)
            payload["env"] = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": {
                    "source": "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0"
                },
            }
            (root / "LoadPackage" / "promotion-env.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            summary = self.module.build_summary(root)
            rendered = self.module.markdown(summary)

        self.assertEqual(summary["readyForNonInvokingCanaryCount"], 0)
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertEqual(summary["blockedFamilies"], ["LoadPackage"])
        self.assertEqual(summary["errorCount"], 2)
        self.assertIn("package promotion env contains a non-scalar value", rendered)
        self.assertIn("ready package promotion env is missing runtime trace evidence", rendered)

    def test_missing_directory_is_empty_summary(self):
        summary = self.module.build_summary("/tmp/definitely-missing-ue4ss-package-dir")
        self.assertEqual(summary["manifestCount"], 0)
        self.assertEqual(summary["nextStep"], "run package runtime trace status to generate per-family promotion manifests")


if __name__ == "__main__":
    unittest.main()
