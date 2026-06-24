#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCRIPTS = {
    "linux-server": ROOT / "scripts" / "package-linux-server-loader.sh",
    "linux-client": ROOT / "scripts" / "package-linux-client-loader.sh",
    "windows-client": ROOT / "scripts" / "package-windows-client-loader.sh",
}
RUNBOOK_DOCS = {
    "linux-server": ROOT / "docs" / "ue4ss-linux-loader-evaluation.md",
    "linux-client": ROOT / "docs" / "linux-client-loader.md",
    "windows-client": ROOT / "docs" / "windows-client-loader.md",
    "windows-client-support": ROOT / "docs" / "client-loader-support.md",
}
PACKAGE_ANCHOR_SCRIPT_SOURCES = (
    ROOT / "scripts" / "plan-ue4ss-canary-env.py",
    ROOT / "scripts" / "prepare-ue-anchor-canary.py",
    ROOT / "scripts" / "promote-ue-anchor-xref-candidates.py",
    ROOT / "scripts" / "export-ue-candidate-globals.py",
    ROOT / "scripts" / "export-ue-root-recovery-candidates.py",
    ROOT / "scripts" / "export-ue-writable-root-shape-candidates.py",
    ROOT / "scripts" / "export-client-pe-signature-manifest.py",
    ROOT / "scripts" / "export-elf-signature-manifest.py",
    ROOT / "scripts" / "summarize-client-loader-scan.py",
    ROOT / "scripts" / "summarize-linux-loader-scan.py",
    ROOT / "scripts" / "summarize-client-ue-anchors.py",
)
PACKAGE_PROVENANCE_SCRIPT_SOURCES = (
    ROOT / "scripts" / "promote-ue-anchor-xref-candidates.py",
    ROOT / "scripts" / "prepare-ue-anchor-canary.py",
    ROOT / "scripts" / "ue4ss-port-readiness.py",
    ROOT / "scripts" / "validate-client-pe-signatures.py",
    ROOT / "scripts" / "validate-elf-signatures.py",
    ROOT / "scripts" / "export-client-pe-signature-manifest.py",
    ROOT / "scripts" / "export-elf-signature-manifest.py",
    ROOT / "scripts" / "summarize-client-loader-xrefs.py",
    ROOT / "scripts" / "summarize-linux-loader-xrefs.py",
)
LOADER_SOURCES = {
    "linux-server": ROOT / "tools" / "linux-server-loader" / "dune_server_probe_loader.c",
    "linux-client": ROOT / "tools" / "linux-client-loader" / "dune_client_probe_loader.c",
    "windows-client": ROOT / "tools" / "windows-client-loader" / "dune_win_client_probe_loader.c",
}


class LoaderPackageAnalysisParityTests(unittest.TestCase):
    def test_static_load_class_is_in_package_anchor_contract_scripts(self):
        for source_path in PACKAGE_ANCHOR_SCRIPT_SOURCES:
            with self.subTest(source=source_path.name):
                source = source_path.read_text(encoding="utf-8")
                self.assertIn("StaticLoadClass", source)

    def test_static_load_class_package_surface_is_reported_on_all_loaders(self):
        required = [
            '"StaticLoadClass"',
            "StaticLoadClassResolved",
            "StaticLoadClassAddress",
            "staticLoadClass=",
            "loadAssetStaticLoadClassResolved",
            "lua_load_asset_backend_static_load_class_resolved",
            "lua_load_asset_backend_static_load_class_address",
        ]
        for platform, source_path in LOADER_SOURCES.items():
            with self.subTest(platform=platform):
                source = source_path.read_text(encoding="utf-8")
                for marker in required:
                    self.assertIn(marker, source)

    def test_load_class_lua_api_is_registered_and_exercised_on_all_loaders(self):
        required = [
            "lua_load_class_callback",
            'set_global(state, "LoadClass")',
            "push_lua_class_handle_for_object",
            "LoadClass(",
            "loadedClass.Name",
            "loadedClass.ClassName=='UClass'",
            "classFromObject.Name",
            "classFromObject.ClassName=='UClass'",
        ]
        for platform, source_path in LOADER_SOURCES.items():
            with self.subTest(platform=platform):
                source = source_path.read_text(encoding="utf-8")
                for marker in required:
                    self.assertIn(marker, source)

    def test_load_class_package_preflight_is_available_on_all_loaders(self):
        common_required = [
            "lua_load_class_package_requested",
            "log_load_class_package_preflight",
            "event=lua-load-class-package-preflight",
            "targetName=StaticLoadClass",
            'get_field(state, 2, "Backend")',
            '"package"',
            'get_field(state, 2, "Package")',
            'get_field(state, 2, "TryPackage")',
            "nativeBridgeArmed=false",
            "nativeCallable=false",
            "nativeInvoked=false",
            "abiVerified=false",
            "tcharLayoutVerified=false",
            "callFrameReady=false",
        ]
        per_loader_required = {
            "linux-server": [
                "platformAbi=sysv-x86_64",
                "targetPerms=%s",
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_DRY_RUN",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE",
            ],
            "linux-client": [
                "platformAbi=sysv-x86_64",
                "targetPerms=%s",
                "DUNE_CLIENT_PROBE_LOAD_CLASS_PACKAGE_DRY_RUN",
                "DUNE_CLIENT_PROBE_ALLOW_LOAD_CLASS_PACKAGE_INVOKE",
            ],
            "windows-client": [
                "platformAbi=win64-ms-abi",
                "targetProtect=",
                "DUNE_WIN_CLIENT_PROBE_LOAD_CLASS_PACKAGE_DRY_RUN",
                "DUNE_WIN_CLIENT_PROBE_ALLOW_LOAD_CLASS_PACKAGE_INVOKE",
            ],
        }
        for platform, source_path in LOADER_SOURCES.items():
            with self.subTest(platform=platform):
                source = source_path.read_text(encoding="utf-8")
                for marker in common_required + per_loader_required[platform]:
                    self.assertIn(marker, source)

    def test_load_class_package_native_readiness_surface_is_available_on_all_loaders(self):
        common_required = [
            "load_class_package_probe_state",
            "lua_get_load_class_package_bridge_state_callback",
            "lua_get_load_class_package_abi_state_callback",
            "lua_get_load_class_package_call_frame_verification_state_callback",
            "lua_get_load_class_package_native_executor_state_callback",
            "lua_invoke_load_class_package_native_callback",
            'set_global(state, "GetLoadClassPackageBridgeState")',
            'set_global(state, "GetLoadClassPackageAbiState")',
            'set_global(state, "GetLoadClassPackageCallFrameVerificationState")',
            'set_global(state, "GetLoadClassPackageNativeExecutorState")',
            'set_global(state, "InvokeLoadClassPackageNative")',
            "event=lua-load-class-package-bridge-state",
            "event=lua-load-class-package-abi-state",
            "event=lua-load-class-package-call-frame-verification-state",
            "event=lua-load-class-package-native-executor-state",
            "event=lua-load-class-package-native-invoke",
            "guarded-class-package-native-executor",
            "SignatureFamily",
            "StaticLoadClass",
            "ClassRootReady",
            "nativeCallPlanAccepted",
            "nativeInvoked=false",
        ]
        per_loader_required = {
            "linux-server": [
                "platformAbi=sysv-x86_64",
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL",
            ],
            "linux-client": [
                "platformAbi=sysv-x86_64",
                "DUNE_CLIENT_PROBE_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
                "DUNE_CLIENT_PROBE_CONFIRM_LOAD_CLASS_PACKAGE_ABI",
                "DUNE_CLIENT_PROBE_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS",
                "DUNE_CLIENT_PROBE_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL",
            ],
            "windows-client": [
                "platformAbi=win64-ms-abi",
                "TargetProtect",
                "DUNE_WIN_CLIENT_PROBE_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
                "DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_CLASS_PACKAGE_ABI",
                "DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS",
                "DUNE_WIN_CLIENT_PROBE_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL",
            ],
        }
        for platform, source_path in LOADER_SOURCES.items():
            with self.subTest(platform=platform):
                source = source_path.read_text(encoding="utf-8")
                for marker in common_required + per_loader_required[platform]:
                    self.assertIn(marker, source)

    def test_candidate_global_analysis_tools_ship_with_all_loader_packages(self):
        common_required = [
            "export-ue-candidate-globals.py",
            "summarize-ue-candidate-outcomes.py",
            "summarize-ue-candidate-shapes.py",
            "summarize-ue-code-pointer-context.py",
            "summarize-ue-vtable-candidates.py",
            "export-process-event-active-validation-candidates.py",
            "summarize-ue-root-recovery-queue.py",
            "cluster-ue-root-recovery-queue.py",
            "export-ue-root-recovery-candidates.py",
            "summarize-ue4ss-port-gaps.py",
            "summarize-ue4ss-evidence-inventory.py",
            "test-export-ue-candidate-globals.py",
            "test-ue-candidate-outcomes.py",
            "test-ue-candidate-shapes.py",
            "test-ue-code-pointer-context.py",
            "test-ue-vtable-candidates.py",
            "test-export-process-event-active-validation-candidates.py",
            "test-ue-root-recovery-queue.py",
            "test-ue-root-recovery-clusters.py",
            "test-export-ue-root-recovery-candidates.py",
            "test-ue4ss-port-gaps.py",
            "test-ue4ss-evidence-inventory.py",
            "UE_CANDIDATE_GLOBALS=",
            "--root-recovery-candidates-json",
            "--candidate-shapes-json",
            "--canary-plan-json",
            "next-canary.json",
            "process-event-active-validation-candidates.json",
            "--active-validation-candidates-json",
            "ue4ss-evidence-inventory.md",
            "ensure-loader-build-toolchain.sh",
            "verify-loader-artifacts.py",
            "test-verify-loader-artifacts.py",
        ]
        platform_required = {
            "linux-server": [
                "summarize-elf-writable-global-refs.py",
                "summarize-elf-writable-root-shapes.py",
                "summarize-elf-ue-function-neighborhoods.py",
                "summarize-elf-ue-function-callgraph.py",
                "summarize-elf-ue-package-loader-vtables.py",
                "summarize-elf-ue-package-wrapper-candidates.py",
                "summarize-elf-ue-package-static-wrapper-candidates.py",
                "summarize-elf-ue-rtti-function-object-vtables.py",
                "summarize-ue4ss-package-route-evidence.py",
                "summarize-ue4ss-package-decompile-plan.py",
                "summarize-ue4ss-package-external-symbol-plan.py",
                "plan-ue4ss-package-runtime-trace.py",
                "summarize-ue4ss-package-runtime-trace-evidence.py",
                "export-ue4ss-package-promotion-env.py",
                "summarize-ue4ss-package-promotion-dir.py",
                "plan-ue4ss-package-next-action.py",
                "verify-ue4ss-package-review-bundle.py",
                "review-ue4ss-package-abi.py",
                "ue4ss-package-runtime-trace.sh",
                "test-elf-writable-global-refs.py",
                "test-elf-writable-root-shapes.py",
                "test-elf-ue-function-neighborhoods.py",
                "test-elf-ue-function-callgraph.py",
                "test-elf-ue-package-loader-vtables.py",
                "test-elf-ue-package-wrapper-candidates.py",
                "test-elf-ue-package-static-wrapper-candidates.py",
                "test-elf-ue-rtti-function-object-vtables.py",
                "test-ue4ss-package-route-evidence.py",
                "test-ue4ss-package-decompile-plan.py",
                "test-ue4ss-package-external-symbol-plan.py",
                "test-ue4ss-package-runtime-trace-plan.py",
                "test-ue4ss-package-runtime-trace-evidence.py",
                "test-export-ue4ss-package-promotion-env.py",
                "test-ue4ss-package-promotion-dir-summary.py",
                "test-ue4ss-package-next-action.py",
                "test-verify-ue4ss-package-review-bundle.py",
                "test-review-ue4ss-package-abi.py",
                "test-ue4ss-package-runtime-trace-runner.py",
                "test-prepare-ue-anchor-canary.py",
                "test-plan-ue4ss-canary-env.py",
                "ue4ss-package-route-evidence.md",
                "ue4ss-package-decompile-plan.md",
                "ue4ss-package-external-symbol-plan.md",
                "ue4ss-package-runtime-trace-plan.md",
                "ue4ss-package-runtime-trace-plan.json",
                "Recommended wrapper env",
                "ue4ss-package-runtime-trace-evidence.md",
                "ue4ss-package-abi-review.md",
                "ue4ss-package-promotion-env.md",
                "ue4ss-package-promotion-env.json",
                "ue4ss-package-promotion-dir.md",
                "ue4ss-package-promotion-dir.json",
                "ue4ss-package-next-action.md",
                "ue4ss-package-next-action.json",
                "--live-trace-runbook-json ue4ss-package-stimulus-trace-runbook.json",
                "ue4ss-port-gaps.md",
                "ue4ss-port-gaps.json",
                "ue4ss-package-next-action-from-promotion.md",
                "ue4ss-package-next-action-from-promotion.json",
                "ue4ss-package-next-action-from-bundle.md",
                "ue4ss-package-next-action-from-latest-bundle.md",
                "review-bundle-manifest.txt",
                "SHA256SUMS",
                "ue4ss-package-review-bundle-verification.md",
                "ue4ss-package-review-bundle-verification.json",
                "registerMemory",
                "memoryLines",
                "familyCandidates",
                "Family Candidates",
                "reviewPriority",
                "concreteReviewPriority",
                "recommendedReview",
                "missingCallFrameOffsets",
                "missingRequiredMemoryRegisters",
                "required package ABI argument registers",
                "registerMemory",
                "memoryLines",
                "embedded trace hit is missing required memory registers",
                "penalized in review scoring",
                "\\`targetImageRip\\` from \\`targetImageCaller\\`",
                "non-target RIP frame",
                "\\`targetImageRip\\`",
                "missing call-frame offsets:",
                "not only in JSON",
                "excluded from \\`recommendedReview\\`",
                "call-frame offsets are concrete",
                "fastest-promotable order",
                "review-priority.json",
                "--hit-index auto",
                "PACKAGE_SIGNATURE_FAMILY=\"\\${PACKAGE_SIGNATURE_FAMILY:-LoadPackage}\"",
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage",
                "current server external-symbol plan exposes \\`LoadPackage\\` and \\`LoadObject\\`",
                "but not \\`StaticLoadObject\\`, \\`StaticLoadClass\\`, or \\`ResolveName\\`",
                "\\`ue4ss-package-runtime-trace-plan.json\\` also carries trace-plan blockers",
                "refuses to arm GDB",
                "\\`refresh-trace-plan\\` instead of \\`arm-trace\\`",
                "runtime trace plan still has blockers",
                "DUNE_UE4SS_PACKAGE_TRACE_ALL_FAMILY_DIR",
                "/tmp/ue4ss-package-family-reviews",
                "DUNE_UE4SS_PACKAGE_TRACE_PID",
                "without Docker discovery",
                "current host",
                "Docker/container",
                "traces still",
                "DUNE_UE4SS_PACKAGE_TRACE_HOST",
                "tracePid",
                "per-family ABI review and promotion manifests",
                "Ready for non-invoking canary",
                "reviewPriority\\` ranks",
                "review hit indexes",
                "requires concrete integer hit indexes",
                "skips malformed candidate rows",
                "ambiguous \\`auto\\` review metadata",
                "summarize-ue4ss-port-gaps.py",
                "--package-next-action-json",
                "dune-ue4ss-package-next-action/v1",
                "non-empty string",
                "string \\`commands\\` entries",
                "object \\`traceEnv\\`",
                "non-empty",
                "scalar \\`traceEnv\\` values",
                "malformed next-action file",
                "silently dropping the package trace",
                "Per-family ABI review",
                "and promotion export prefer \\`concreteReviewPriority\\`",
                "before legacy",
                "\\`familyCandidates\\`",
                "same concrete candidate",
                "does not fall back to raw family candidates",
                "callerImageOffset",
                "ripImageOffset",
                "missingRequiredMemoryRegisters",
                "call-frame",
                "provenance",
                "copied package env evidence",
                "embedded trace-hit identity",
                "must carry both offsets itself",
                "reuse that recorded hit index",
                "malformed",
                "invalid hit",
                "\\`review-priority.json\\` metadata, including invalid hit",
                "indexes, promotion-manifest family",
                "reported as summary errors",
                "promotion manifest",
                "\\`signatureFamily\\` / parent-directory mismatches",
                "\\`review-priority.json\\` hit-index drift",
                "promotion-manifest family",
                "demotes otherwise ready rows out of",
                "\\`readyManifestPaths\\` until the priority metadata is regenerated",
                "Bundled",
                "top-level and per-family promotion manifests",
                "block bundle verification",
                "readyManifestPaths",
                "missing review flag",
                "demote",
                "claimed-ready manifests",
                "missing \\`abiReviewReady\\`",
                "missing \\`abiReviewed\\`",
                "missing \\`targetImageReviewed\\`",
                "missing family review confirmation",
                "\\`tcharReviewed\\` or \\`classRootReviewed\\`",
                "missing \\`sourceEvidence\\`",
                "missing \\`sourceLogExists\\`",
                "\\`sourceLogExists=false\\`",
                "non-concrete \\`hitIndex\\`",
                "stale",
                "ready booleans do not reach canary planning",
                "Direct",
                "--package-promotion-json",
                "same ready-claim",
                "next-action summary rows",
                "Native-ready manifests must also",
                "non-invoking canary first",
                "native-only ready claims",
                "readyForNonInvokingCanary=true",
                "cannot skip the non-invoking package ABI/call-frame gate",
                "Promotion export blocks selected trace hits that are missing seed",
                "provenance, and promotion directory summaries",
                "embedded selected \\`hit\\`",
                "hit seed",
                "manifest-level",
                "\\`signatureFamily\\`",
                "top-level \\`selectedHitSeed\\` provenance",
                "same selected hit",
                "\\`hit.callerImageOffset\\`",
                "\\`hit.ripImageOffset\\`",
                "manifest-level \\`callerImageOffset\\` and \\`ripImageOffset\\`",
                "\\`traceAddressMatchesBase=false\\`",
                "image base plus seed imageOffset",
                "ready rows and",
                "\\`readyManifestPaths\\` closed over the same manifest set",
                "ready row omitted",
                "listed ready path without a ready row",
                "Promotion export emits only",
                "family-specific env keys",
                "promotion env keys must match",
                "StaticLoadClass\\` manifests cannot emit LoadAsset",
                "LoadAsset-family manifests cannot emit LoadClass",
                "directory summaries and review-bundle verification",
                "same family env",
                "key shape before marking copied manifests ready",
                "promotion directory",
                "demote ready \\`runtime-trace:<family>\\` env evidence",
                "family label",
                "or \\`seed=...\\` marker",
                "Next-action also treats",
                "claimed-ready summary rows",
                "errors before it recommends canary planning",
                "missing \\`selectedHitSeed\\`",
                "Copied summary rows",
                "reviewPriorityHitIndex",
                "must also match the adjacent \\`review-priority.json\\`",
                "stale review ordering metadata",
                "--promotion-json",
                "top-level",
                "--package-promotion-summary-json",
                "--package-promotion-dir",
                "Raw directory canary planning",
                "honors \\`review-priority.json\\` ordering",
                "standalone canary planning",
                "next-action planner",
                "repeats promotion",
                "summary errors and blocks package canary planning",
                "blocked manifests remain closed by the canary planner",
                "clears stale generated evidence",
                "generated per-family review directory",
                "failed or no-candidate status",
                "runs cannot accidentally reuse an older",
                "ready manifest or family review",
                "\\`runtime-trace:<family>\\` env evidence label or \\`seed=...\\`",
                "\\`seed=...\\`",
                "manifest-level \\`signatureFamily\\`",
                "\\`caller=...\\` marker",
                "conflicts with the manifest-level \\`callerImageOffset\\`",
                "\\`runtime-trace:\\` env evidence",
                "\\`rip=...\\` marker conflicts",
                "supporting review evidence only",
                "non-null pointer value alone is not enough",
                "ABI review also requires",
                "trace hit seed provenance plus",
                "\\`callerImageOffset\\` and \\`ripImageOffset\\`",
                "\\`tracePid\\` plus image range identity",
                "single-manifest planner path preserves",
                "same \\`tracePid\\` and",
                "image range identity fields",
                "manual ABI review",
                "ABI review manifest and markdown carry the",
                "\\`selectedHitSeed\\`",
                "ABI review markdown prints both the caller and RIP image",
                "complete call-frame identity",
                "DUNE_UE4SS_PACKAGE_TRACE_PID",
                "explicit process without Docker discovery",
                "pid-<pid>",
                "neutral",
                "next-action replay commands",
                "passes",
                "explicit PID into next-action replay commands",
                "\\`tracePid\\` in review-bundle manifests",
                "DUNE_UE4SS_PACKAGE_TRACE_HOST",
                "next-action replay",
                "\\`traceHost\\` in review-bundle manifests",
                "match both values",
                "DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN",
                "docker-top process",
                "regex while the default remains",
                "DuneSandboxServer-Linux-Shipping",
                "candidateTcharLayouts",
                "ABI review and promotion export require explicit",
                "\\`sourceLogExists=true\\` trace provenance",
                "Promotion export also requires ABI review \\`selectedHitSeed\\`",
                "plus call-frame",
                "missing provenance",
                "blocks the promotion manifest",
                "missing trace identity",
                "trace-to-env audit trail",
                "DUNE_UE4SS_PACKAGE_TRACE_REVIEW_BUNDLE_DIR",
                "dune-ue4ss-package-review-bundle/v1",
                "trace-plan provenance",
                "\\`tracePlanSourceExternalPlan\\`",
                "\\`tracePlanBase\\`",
                "\\`tracePlanExpectedBuildId\\`",
                "\\`tracePlanRuntimeBuildId\\`",
                "\\`tracePlanSeedCount\\`",
                "\\`tracePlanSeedOffsets\\`",
                "\\`tracePlanSelectedByFamily\\`",
                "\\`tracePlanBlockerCount\\`",
                "recommended trace env provenance",
                "\\`tracePlanRecommendedAnchor\\`",
                "\\`tracePlanRecommendedLimit\\`",
                "\\`tracePlanRecommendedSignatureFamily\\`",
                "\\`tracePlanRecommendedHitIndex\\`",
                "process selector provenance",
                "\\`processPattern\\`",
                "optional \\`tracePid\\`",
                "optional \\`traceHost\\`",
                "trace evidence source provenance",
                "\\`sourceLogExists\\`",
                "\\`sourceLogSha256\\`",
                "\\`sourceEvidenceJson\\`",
                "\\`sourceEvidenceJsonSha256\\`",
                "image range provenance",
                "\\`evidencePid\\`",
                "\\`imageRangeSource\\`",
                "\\`imageBase\\`",
                "\\`imageStart\\`",
                "\\`imageEnd\\`",
                "\\`imagePath\\`",
                "\\`imagePerms\\`",
                "checksum coverage",
                "top-level trace/ABI/promotion identity",
                "Top-level ABI review artifacts",
                "missing \\`sourceLogExists\\`",
                "\\`sourceLogExists=false\\` also block bundle verification",
                "missing \\`sourceEvidenceJson\\`",
                "missing \\`sourceEvidenceJsonSha256\\`",
                "\\`sourceLogSha256\\`",
                "top-level promotion, and nested",
                "per-family promotion \\`sourceLogExists\\`, \\`sourceLogSha256\\`, and",
                "\\`sourceEvidenceJsonSha256\\` values",
                "match the copied",
                "runtime trace",
                "ABI-review-to-promotion offset",
                "and \\`selectedHitSeed\\` matches",
                "trace-hit lookup is unavailable",
                "promotion schema/family consistency",
                "schema/family consistency",
                "markdown output includes the bundle \\`traceLog\\`",
                "exact trace source",
                "copied \\`ue4ss-package-family-reviews.json\\`",
                "listed in \\`review-bundle-manifest.txt\\`",
                "artifact rows",
                "prove where that summary came from",
                "bundled runtime trace \\`sourceEvidence\\`",
                "\\`sourceLogExists\\`",
                "\\`sourceLogSha256\\`",
                "\\`sourceEvidenceJsonSha256\\`",
                "selected \\`hitIndex\\`",
                "stale family review cannot be promoted",
                "replay commands",
                "\\`arm\\` and \\`status\\`",
                "each replay command",
                "reference the manifest",
                "\\`container\\` and \\`traceLog\\`",
                "unexpected",
                "\\`DUNE_UE4SS_PACKAGE_TRACE_*\\` assignments",
                "runtime trace plan exactly",
                "except the process selector, explicit \\`tracePid\\`, and explicit",
                "\\`traceHost\\`",
                "\\`recommendedTraceEnv\\` must also match",
                "selected trace seed count",
                "selected trace seed families",
                "stale anchor or limit recommendations",
                "review-bundle manifest mirrors",
                "recommended anchor, limit, signature family, and hit-index",
                "plain-text fields",
                "For \\`plan-canary\\` actions",
                "consume bundled promotion inputs",
                "\\`ue4ss-package-next-canary.json\\`",
                "\\`ue4ss-package-next-canary.env\\`",
                "same source paths recorded in",
                "Stale next-canary output redirections block",
                "\\`outputFiles.nextCanaryJson\\`",
                "\\`outputFiles.nextCanaryEnv\\`",
                "machine-readable proof",
                "shell redirection parsing",
                "--review-bundle <bundle>",
                "bundled per-family review directory",
                "prefers it over copied summary paths",
                "self-contained",
                "bundled top-level promotion manifest",
                "the synthesized summary row preserves \\`sourceEvidence\\`, \\`sourceEvidenceJson\\`,",
                "\\`sourceEvidenceJsonSha256\\`, \\`sourceLogSha256\\`, \\`sourceLogExists\\`",
                "\\`abiReviewReady\\`",
                "\\`abiReviewed\\`",
                "\\`targetImageReviewed\\`",
                "\\`tcharReviewed\\`",
                "\\`classRootReviewed\\`",
                "replay keeps the same trace identity",
                "same trace identity surface",
                "missing \\`sourceLogExists\\`",
                "--review-bundle /tmp/ue4ss-package-review-bundles",
                "newest timestamped bundle",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto",
                "matching selected anchor",
                "selected seed count limit",
                "first captured",
                "matches the selected signature family",
            ],
            "linux-client": [
                "summarize-elf-writable-global-refs.py",
                "summarize-elf-writable-root-shapes.py",
                "summarize-elf-ue-function-neighborhoods.py",
                "summarize-elf-ue-function-callgraph.py",
                "summarize-elf-ue-package-loader-vtables.py",
                "summarize-elf-ue-package-wrapper-candidates.py",
                "summarize-elf-ue-package-static-wrapper-candidates.py",
                "summarize-elf-ue-rtti-function-object-vtables.py",
                "summarize-ue4ss-package-route-evidence.py",
                "summarize-ue4ss-package-decompile-plan.py",
                "summarize-ue4ss-package-external-symbol-plan.py",
                "plan-ue4ss-package-runtime-trace.py",
                "test-elf-writable-global-refs.py",
                "test-elf-writable-root-shapes.py",
                "test-elf-ue-function-neighborhoods.py",
                "test-elf-ue-function-callgraph.py",
                "test-elf-ue-package-loader-vtables.py",
                "test-elf-ue-package-wrapper-candidates.py",
                "test-elf-ue-package-static-wrapper-candidates.py",
                "test-elf-ue-rtti-function-object-vtables.py",
                "test-ue4ss-package-route-evidence.py",
                "test-ue4ss-package-decompile-plan.py",
                "test-ue4ss-package-external-symbol-plan.py",
                "test-ue4ss-package-runtime-trace-plan.py",
                "ue4ss-package-route-evidence.md",
                "ue4ss-package-decompile-plan.md",
                "ue4ss-package-external-symbol-plan.md",
                "ue4ss-package-runtime-trace-plan.md",
            ],
            "windows-client": [
                "summarize-pe-writable-root-shapes.py",
                "test-pe-writable-root-shapes.py",
            ],
        }
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(script=script.name):
                source = script.read_text(encoding="utf-8")
                for item in common_required + platform_required[platform]:
                    self.assertIn(item, source)

    def test_package_analysis_runbooks_are_target_filter_parameterized(self):
        common_required = [
            'TARGET_BINARY="\\${TARGET_BINARY:-',
            'TARGET_FILTER_ARGS=(\\${TARGET_FILTER_ARGS[@]:---exe-substring',
            '"\\$TARGET_BINARY"',
            '"\\${TARGET_FILTER_ARGS[@]}"',
            "plan-ue4ss-canary-env.py",
            "ue4ss-port-readiness.py",
        ]
        platform_required = {
            "linux-server": [
                "--server-log /path/to/loader.log",
                "--loader server \"\\${TARGET_FILTER_ARGS[@]}\"",
                "--target-loader server \"\\${TARGET_FILTER_ARGS[@]}\"",
                "DuneSandboxServer --exe-substring DuneSandbox",
            ],
            "linux-client": [
                "--client-log /tmp/dune-client-probe-loader.log",
                "--loader linux-client \"\\${TARGET_FILTER_ARGS[@]}\"",
                "--target-loader linux-client \"\\${TARGET_FILTER_ARGS[@]}\"",
                "/path/to/DuneSandbox-Linux-Shipping",
            ],
            "windows-client": [
                "--client-log /tmp/dune-win-client-probe-loader.log",
                "--loader win-client \"\\${TARGET_FILTER_ARGS[@]}\"",
                'proton-proxy-candidates.py "\\$TARGET_BINARY"',
                "/path/to/DuneSandbox-Win64-Shipping.exe",
            ],
        }
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(platform=platform):
                source = script.read_text(encoding="utf-8")
                for marker in common_required + platform_required[platform]:
                    self.assertIn(marker, source)

    def test_linux_package_analysis_runbooks_include_kismet_loadasset_route(self):
        required = [
            "UKismetSystemLibrary::LoadAsset",
            "FLoadAssetAction",
            "FLoadAssetClassAction",
            "ue-kismet-loadasset-vtables.json",
            "ue-kismet-loadasset-callgraph.md",
            "FLoadAssetActionBase_dispatch=0x0",
            "KismetLoadAsset_helper=0x0",
        ]
        for platform in ("linux-server", "linux-client"):
            with self.subTest(platform=platform):
                source = PACKAGE_SCRIPTS[platform].read_text(encoding="utf-8")
                for marker in required:
                    self.assertIn(marker, source)

    def test_linux_package_analysis_runbooks_include_raw_typeinfo_linker_async_route(self):
        required = [
            "--raw-typeinfo-needle FLinkerLoad",
            "--raw-typeinfo-needle FAsyncPackage",
            "--raw-typeinfo-needle FAsyncLoadingThread",
            "--raw-typeinfo-needle FAsyncArchive",
            "ue-raw-typeinfo-linker-async-vtables.json",
            "ue-raw-typeinfo-linker-async-callgraph.md",
            "--seed-limit 16 --format seeds",
            "RAW_TYPEINFO_SEEDS",
            '"\\${RAW_TYPEINFO_SEEDS[@]}"',
        ]
        for platform in ("linux-server", "linux-client"):
            with self.subTest(platform=platform):
                source = PACKAGE_SCRIPTS[platform].read_text(encoding="utf-8")
                for marker in required:
                    self.assertIn(marker, source)

    def test_target_image_anchor_recovery_docs_require_target_source_promotion(self):
        required = [
            "promote-ue-anchor-xref-candidates.py",
            "--require-target-source",
            "ue-anchor-candidates.json",
        ]
        for platform, doc in RUNBOOK_DOCS.items():
            with self.subTest(platform=platform):
                source = doc.read_text(encoding="utf-8")
                for marker in required:
                    self.assertIn(marker, source)

    def test_package_analysis_scripts_preserve_target_source_provenance(self):
        per_source_required = {
            "promote-ue-anchor-xref-candidates.py": ["sourceProvenance", "is_loader_source", "target_provenance"],
            "prepare-ue-anchor-canary.py": ["targetPresent", "loaderPresent", "source_provenance_from_entry"],
            "ue4ss-port-readiness.py": ["targetPresent", "loaderPresent", "targetComplete"],
            "validate-client-pe-signatures.py": ["sourceProvenance", "source_provenance", "is_loader_source"],
            "validate-elf-signatures.py": ["sourceProvenance", "source_provenance", "is_loader_source"],
            "export-client-pe-signature-manifest.py": ["sourceProvenance", "source_provenance", "is_loader_source"],
            "export-elf-signature-manifest.py": ["sourceProvenance", "source_provenance", "is_loader_source"],
            "summarize-client-loader-xrefs.py": ['"source": target.source'],
            "summarize-linux-loader-xrefs.py": ['"source": target.source'],
        }
        for source_path in PACKAGE_PROVENANCE_SCRIPT_SOURCES:
            with self.subTest(source=source_path.name):
                source = source_path.read_text(encoding="utf-8")
                for marker in per_source_required[source_path.name]:
                    self.assertIn(marker, source)

    def test_package_analysis_scripts_reject_loader_anchor_promotion_by_default(self):
        source = (ROOT / "scripts" / "promote-ue-anchor-xref-candidates.py").read_text(encoding="utf-8")
        for marker in (
            "loader-source",
            "non-target-source",
            "--require-target-source",
            "--allow-loader-sources",
            "sourceProvenanceCounts",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_loader_packages_run_target_anchor_recovery_regressions(self):
        required = [
            "tests/test-promote-ue-anchor-xref-candidates.py",
            "tests/test-prepare-ue-anchor-canary.py",
            "tests/test-plan-ue4ss-canary-env.py",
        ]
        server_required = [
            "tests/test-verify-loader-artifacts.py",
            "tests/test-ue4ss-package-next-action.py",
            "tests/test-verify-ue4ss-package-review-bundle.py",
            "tests/test-verify-ue4ss-package-prearm-readiness.py",
        ]
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(platform=platform):
                source = script.read_text(encoding="utf-8")
                markers = required + (server_required if platform == "linux-server" else [])
                for marker in markers:
                    self.assertIn(marker, source)

    def test_server_package_documents_package_promotion_metadata_error_handoff(self):
        source = PACKAGE_SCRIPTS["linux-server"].read_text(encoding="utf-8")
        for marker in (
            "promotionSummaryErrors",
            "package promotion metadata error",
            "promotion-env.json",
            "review-priority.json",
            "summarize-ue4ss-port-gaps.py --package-next-action-json",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_loader_packages_feed_prepared_anchor_coverage_into_readiness(self):
        required = {
            "linux-server": [
                "--anchor-coverage-json build/server-anchor-canary/anchor-coverage.json",
                "scripts/ue4ss-port-readiness.py",
            ],
            "linux-client": [
                "--anchor-coverage-json build/linux-client-anchor-canary/anchor-coverage.json",
                "analysis/ue4ss-port-readiness.py",
            ],
            "windows-client": [
                "--anchor-coverage-json build/windows-client-anchor-canary/anchor-coverage.json",
                "analysis/ue4ss-port-readiness.py",
            ],
        }
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(platform=platform):
                source = script.read_text(encoding="utf-8")
                for marker in required[platform]:
                    self.assertIn(marker, source)

    def test_runbooks_feed_prepared_anchor_coverage_into_readiness(self):
        required = {
            "linux-server": [
                "--anchor-coverage-json build/linux-server-loader/server-anchor-canary/anchor-coverage.json",
                "scripts/ue4ss-port-readiness.py",
            ],
            "linux-client": [
                "--anchor-coverage-json build/linux-client-loader/client-anchor-canary/anchor-coverage.json",
                "scripts/ue4ss-port-readiness.py",
            ],
            "windows-client": [
                "--anchor-coverage-json build/windows-client-loader/client-anchor-canary/anchor-coverage.json",
                "scripts/ue4ss-port-readiness.py",
            ],
            "windows-client-support": [
                "--anchor-coverage-json build/windows-client-loader/client-anchor-canary/anchor-coverage.json",
                "scripts/ue4ss-port-readiness.py",
            ],
        }
        for platform, doc in RUNBOOK_DOCS.items():
            with self.subTest(platform=platform):
                source = doc.read_text(encoding="utf-8")
                for marker in required[platform]:
                    self.assertIn(marker, source)

    def test_runbooks_document_evidence_inventory_output(self):
        required = [
            "summarize-ue4ss-evidence-inventory.py",
            "ue4ss-evidence-inventory.md",
        ]
        for platform, doc in RUNBOOK_DOCS.items():
            with self.subTest(platform=platform):
                source = doc.read_text(encoding="utf-8")
                for marker in required:
                    self.assertIn(marker, source)

    def test_client_evidence_wrapper_preserves_anchor_coverage(self):
        source = (ROOT / "scripts" / "verify-client-probe-canary.sh").read_text(encoding="utf-8")
        for marker in (
            "$prep_dir/anchor-coverage.json",
            "$output_dir/anchor-coverage.json",
            "ue4ss-readiness.json",
            "ue4ss-port-gaps.json",
            "summarize-ue4ss-evidence-inventory.py",
            "ue4ss-evidence-inventory.md",
            "ue4ss-evidence-inventory.json",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_packages_document_strict_process_event_dispatch_contract(self):
        required = [
            "runtimeProcessEventDispatch",
            "more than a live hook row",
            "decoded live function path",
            "runtime registry context",
            "raw and",
            "container param samples",
            "Lua context handles",
            "descriptor-backed param accessors",
            "typed scalar/name/string/struct/enum/object/bool accessor coverage",
            "container alias/layout methods",
            "hook routing/alias routing",
            "luaProcessEventNativeInvokeNonSelfTestInvoked=true",
            "luaCallFunctionNativeInvokeNonSelfTestInvoked=true",
        ]
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(script=script.name):
                source = script.read_text(encoding="utf-8")
                for marker in required:
                    self.assertIn(marker, source)

    def test_packages_document_canary_next_plan_chaining(self):
        common_required = [
            "summarize-ue-vtable-candidates.py",
            "ue-vtable-candidates.json",
            "ue-vtable-candidates.md",
            "next-canary-plan.json",
            "next-canary-plan.env",
            "next-canary-plan.md",
            "--hook-targets-json",
            "plan-ue4ss-canary-env.py",
        ]
        platform_required = {
            "linux-server": [
                "canary-linux-server-loader.sh",
                "DUNE_LINUX_SERVER_CANARY_PLAN_JSON",
            ],
            "linux-client": [
                "verify-client-probe-canary.sh",
                "--platform linux-client",
            ],
            "windows-client": [
                "verify-client-probe-canary.sh",
                "--platform windows",
                "win-client",
            ],
        }
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(script=script.name):
                source = script.read_text(encoding="utf-8")
                for marker in common_required + platform_required[platform]:
                    self.assertIn(marker, source)

    def test_load_asset_package_preflight_logs_target_image_evidence_on_all_loaders(self):
        common_required = [
            "event=lua-load-asset-package-preflight status=",
            "native-executor-ready",
            "native-bridge-missing",
            "targetName=",
            "targetImage=",
            "targetMapped=",
            "targetReadable=",
            "targetExecutable=",
            "invokeEnabled=",
            "nativeBridgeArmed=",
            "nativeCallable=",
            "nativeInvoked=false",
            "packageAvailable=",
            "abiVerified=",
            "tcharLayoutVerified=",
            "callFrameReady=",
            "finalInvokeConfirmed=",
            "crashGuardArmed=",
            "guardedCallReady=",
            "returnValidationReady=",
            "lua_load_asset_backend_package_target_image = 0;",
        ]
        per_loader_required = {
            "linux-server": [
                "platformAbi=sysv-x86_64",
                "targetPerms=%s",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_DRY_RUN",
            ],
            "linux-client": [
                "platformAbi=sysv-x86_64",
                "targetPerms=%s",
                "DUNE_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
                "DUNE_CLIENT_PROBE_LOAD_ASSET_PACKAGE_DRY_RUN",
            ],
            "windows-client": [
                "platformAbi=win64-ms-abi",
                "targetProtect=",
                "DUNE_WIN_CLIENT_PROBE_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
                "DUNE_WIN_CLIENT_PROBE_LOAD_ASSET_PACKAGE_DRY_RUN",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)
        server_source = LOADER_SOURCES["linux-server"].read_text(encoding="utf-8")
        self.assertLess(
            server_source.index("start_delayed_ue_probe();"),
            server_source.index("snapshot();", server_source.index("dune_server_probe_loader_init")),
        )
        linux_client_source = LOADER_SOURCES["linux-client"].read_text(encoding="utf-8")
        self.assertLess(
            linux_client_source.index("start_delayed_ue_probe();"),
            linux_client_source.index("snapshot();", linux_client_source.index("dune_client_probe_loader_init")),
        )
        windows_source = LOADER_SOURCES["windows-client"].read_text(encoding="utf-8")
        self.assertLess(
            windows_source.index("start_delayed_ue_probe();", windows_source.index("probe_thread")),
            windows_source.index('probe_run("thread");'),
        )

    def test_load_asset_package_native_invoke_lua_result_exposes_target_image_on_all_loaders(self):
        common_required = [
            "event=lua-load-asset-package-native-invoke status=",
            " targetImage=",
            'active_lua_api->set_field(state, -2, "TargetImage");',
            'active_lua_api->set_field(state, -2, "NativeCallable");',
            'active_lua_api->set_field(state, -2, "NativeReturnValidated");',
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)
                self.assertLess(
                    source.index('active_lua_api->set_field(state, -2, "TargetAddress");'),
                    source.index('active_lua_api->set_field(state, -2, "TargetImage");'),
                )

    def test_runtime_probe_seed_refreshes_registry_metadata_on_all_loaders(self):
        common_required = [
            'const char *path = "/RuntimeProbe/RuntimeProbeObject";',
            'const char *name = "RuntimeProbeObject";',
            'const char *class_name = "DuneProbeRuntimeClass";',
            "int registered_candidate = add_ue_candidate_object_handle(path, name, class_name, address);",
            "update_ue_candidate_object_metadata(address, (uintptr_t)&ue_self_test_class, 0, 0);",
            'registered_candidate ? "added" : "skipped"',
            "registry_value_provenance(name, path, class_name)",
            'log_lua_object_registry_check("runtime-probe", name, path, class_name, address);',
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                start = source.index("static void seed_runtime_probe_surfaces(void)")
                end = source.index("add_ue_reflection_property_candidate(", start)
                seed_block = source[start:end]
                for item in common_required:
                    self.assertIn(item, seed_block)
                self.assertNotIn("registryProvenance=runtime", seed_block)

    def test_linux_server_loader_skips_non_target_helper_processes(self):
        source = LOADER_SOURCES["linux-server"].read_text(encoding="utf-8")
        for item in [
            "DUNE_PROBE_LOADER_TARGET",
            "DUNE_PROBE_LOADER_FORCE",
            "event=target-skip",
            "is_target_process(exe)",
            "DuneSandboxServer",
            "DuneSandbox",
        ]:
            self.assertIn(item, source)
        self.assertLess(source.index("event=target-skip"), source.index('log_modules("initial")'))

    def test_runtime_auto_discovery_logs_scan_coverage_on_all_loaders(self):
        common_required = [
            "event=ue-runtime-discovery-start",
            "event=ue-runtime-discovery-candidate name=RuntimeGUObjectArray",
            "scannedSlots=",
            "fnameProbes=",
            "objectArrayProbes=",
            "event=ue-runtime-discovery-limited",
            "limited=",
            "rejectedFNameSamples=",
            "event=ue-runtime-discovery-rejected name=RuntimeFNamePool",
            "UeFNameCandidateMetrics",
            "plausibleEntries=",
            "firstEntry=",
            "firstHeader=",
            "firstLength=",
            "firstWide=",
            "firstBlockEntryPlausible=",
            "firstBlockEntryNone=",
            "firstBlockHeader=",
            "firstBlockLength=",
            "firstBlockWide=",
            "currentBlock=",
            "currentByteCursor=",
            "allocatorStatePlausible=",
            "targetImage=",
            "chunksReadable=",
            "firstChunkReadable=",
            "firstObjectReadable=",
            "MAX_REJECTED_FNAME_SAMPLES",
        ]
        per_loader_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW",
                "targetWritableMappings=",
                "privateWritableMappings=",
                "oversizedMappings=",
                "event=ue-runtime-discovery name=target-writable-image-mappings status=missing",
                "firstBlockSameMapping=",
                "firstBlockTargetImage=",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW",
                "targetWritableMappings=",
                "privateWritableMappings=",
                "oversizedMappings=",
                "event=ue-runtime-discovery name=target-writable-image-mappings status=missing",
                "firstBlockSameMapping=",
                "firstBlockTargetImage=",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW",
                "targetWritableRegions=",
                "privateWritableRegions=",
                "oversizedRegions=",
                "event=ue-runtime-discovery name=target-writable-image-regions status=missing",
                "firstBlockSameRegion=",
                "firstBlockTargetImage=",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)

    def test_delayed_runtime_root_probe_is_available_on_all_loaders(self):
        common_required = [
            "event=ue-delayed-probe-config",
            "event=ue-delayed-probe-start",
            "event=ue-delayed-probe-finish",
            'validate_ue_anchors("ue-delayed")',
        ]
        per_loader_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_DELAYED_PROBE_SECONDS",
                "pthread_create",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS",
                "pthread_create",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_DELAYED_PROBE_SECONDS",
                "Sleep((DWORD)(delay * 1000))",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)

    def test_object_array_ufunction_identity_promotion_is_available_on_all_loaders(self):
        common_required = [
            "add_ue_function_identity_descriptor(",
            'contains_ci(native_class_name, "Function")',
            "event=ue-function-native-identity source=",
            "status=promoted",
            "log_lua_function_registry_check_with_provenance(",
            '"ue-object-array"',
            '"runtime"',
            '"objectArray"',
            '"UFunction"',
            "decoded_outer_name",
            "outer_private ? outer_private : class_private",
            'decoded_outer_name[0] ? decoded_outer_name : array_name',
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_function_only_identities_do_not_count_as_param_descriptors(self):
        common_required = [
            "ue_function_descriptor_has_param_field(",
            "descriptor && descriptor->field != 0",
            "count_ue_function_param_descriptors(",
            "!ue_function_descriptor_has_param_field(descriptor)",
            "descriptor->function != function || !ue_function_descriptor_has_param_field(descriptor)",
            "find_ue_function_descriptor_by_path_or_name(",
            "push_ue_function_handle_from_descriptor(",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_lua_reflection_self_test_searches_runtime_function_owners(self):
        common_required = [
            "GetKnownObjects();if kos then for _,x in pairs(kos)",
            "x.ForEachFunction",
            "not tostring(x.Name or",
            "find('SelfTest')",
            "if rfi>0 then ro=x;break end",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_runtime_function_owner_iteration_native_check_is_available_on_all_loaders(self):
        common_required = [
            "maybe_log_runtime_for_each_function_native_check(",
            "ue_function_descriptor_owner_name(owner_descriptor, owner, sizeof(owner))",
            "log_lua_function_registry_check_with_provenance(descriptor, \"ForEachFunction\", \"runtime\")",
            "log_lua_function_iteration_check(owner, \"UClass\", \"owner\", callbacks)",
            "process_event_function_provenance(",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_hook_runtime_target_provenance_is_logged_on_all_loaders(self):
        common_required = [
            "process_event_hook_target_source(",
            "process_event_live_hook_target_source(",
            "call_function_hook_target_source(",
            "call_function_live_hook_target_source(",
            "targetSource=",
            "targetName=ProcessEvent",
            "targetName=CallFunctionByNameWithArguments",
            "explicit-hook-address",
            "explicit-live-hook-address",
            "explicit-process-event-address",
            "explicit-call-function-address",
        ]
        per_loader_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET",
                "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_IMAGE_OFFSET",
                "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET",
                "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE",
                "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
                "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET",
                "event=ue-call-function-active-validate",
                "targetEntry=",
                "image-offset-call-function-address",
                "image-offset-live-hook-address",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET",
                "DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_IMAGE_OFFSET",
                "DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET",
                "DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE",
                "DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
                "DUNE_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET",
                "event=ue-call-function-active-validate",
                "targetEntry=",
                "image-offset-call-function-address",
                "image-offset-live-hook-address",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_HOOK_RVA",
                "DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_RVA",
                "DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_LIVE_HOOK_RVA",
                "DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE",
                "DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
                "DUNE_WIN_CLIENT_PROBE_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET",
                "event=ue-call-function-active-validate",
                "targetEntry=",
                "rva-call-function-address",
                "rva-live-hook-address",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)

    def test_process_event_vtable_candidate_scan_is_available_on_all_loaders(self):
        common_required = [
            "ue_process_event_vtable_scan_enabled(",
            "ue_process_event_vtable_scan_slots(",
            "ue_process_event_vtable_scan_max_objects(",
            "event=ue-process-event-vtable-candidate",
            "event=ue-process-event-vtable-scan",
            "status=limit-reached",
            "maxObjects=",
            "status=scanned",
            "executableSlots=",
            "readableSlots=",
            "targetName=ProcessEvent targetSource=vtable-candidate",
        ]
        per_loader_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_IMAGE_OFFSET",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL",
                "originalSuppressed=",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_PATH",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_NAME",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_PATH",
                "event=ue-process-event-active-validate",
                "targetEntry=",
                "image-offset-hook-address",
                "image-offset-live-hook-address",
                "imageOffset=0x%lx fileOffset=0x%lx perms=%s map=%s",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_IMAGE_OFFSET",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL",
                "originalSuppressed=",
                "event=ue-process-event-active-validate",
                "targetEntry=",
                "image-offset-hook-address",
                "image-offset-live-hook-address",
                "imageOffset=0x%lx fileOffset=0x%lx perms=%s map=%s",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_RVA",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_RVA",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_RVA",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL",
                "originalSuppressed=",
                "event=ue-process-event-active-validate",
                "targetEntry=",
                "rva-hook-address",
                "rva-live-hook-address",
                "rva=",
                "protect=",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)

        package_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN=false",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS=96",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS=0",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET=",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_IMAGE_OFFSET=",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET=",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE=false",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET=false",
                "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL=false",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN=false",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS=96",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS=0",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET=",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_IMAGE_OFFSET=",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET=",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE=false",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET=false",
                "DUNE_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL=false",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN=false",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS=96",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS=0",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_HOOK_RVA=",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_RVA=",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_LIVE_HOOK_RVA=",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE=false",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=false",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET=false",
                "DUNE_WIN_CLIENT_PROBE_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL=false",
            ],
        }
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(package=platform):
                source = script.read_text(encoding="utf-8")
                for item in package_required[platform]:
                    self.assertIn(item, source)

        server_wrapper = (ROOT / "scripts" / "run_server_safe.sh").read_text(encoding="utf-8")
        for item in [
            "load_workspace_bool DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_IMAGE_OFFSET",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET",
            "load_workspace_value DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET",
            "load_workspace_value DUNE_PROBE_LOADER_UE_CALL_FUNCTION_IMAGE_OFFSET",
            "load_workspace_value DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET",
            "load_workspace_bool DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE",
            "load_workspace_bool DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
            "load_workspace_bool DUNE_PROBE_LOADER_UE_PROCESS_EVENT_SYNTHETIC_RUNTIME_VALIDATE",
            "load_workspace_bool DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET",
            "load_workspace_bool DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_ADDRESS",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_PATH",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_NAME",
            "load_workspace_value DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_PATH",
            "load_workspace_bool DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE",
            "load_workspace_bool DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL",
            "load_workspace_bool DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET",
            "load_workspace_value DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_SLOTS:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_VTABLE_SCAN_MAX_OBJECTS:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_HOOK_IMAGE_OFFSET:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_IMAGE_OFFSET=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_IMAGE_OFFSET:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_LIVE_HOOK_IMAGE_OFFSET:-}",
            "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET=${DUNE_PROBE_LOADER_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET:-}",
            "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_IMAGE_OFFSET=${DUNE_PROBE_LOADER_UE_CALL_FUNCTION_IMAGE_OFFSET:-}",
            "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET=${DUNE_PROBE_LOADER_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_THROUGH_TARGET:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_SUPPRESS_ORIGINAL:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_PATH=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_PATH:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_NAME=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_OBJECT_NAME:-}",
            "DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_PATH=${DUNE_PROBE_LOADER_UE_PROCESS_EVENT_ACTIVE_VALIDATE_FUNCTION_PATH:-}",
            "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE=${DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE:-}",
            "DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET=${DUNE_PROBE_LOADER_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET:-}",
        ]:
            self.assertIn(item, server_wrapper)

    def test_runtime_root_consumer_validation_is_logged_on_all_loaders(self):
        common_required = [
            "event=ue-runtime-root-validation phase=",
            "name=RuntimeFNamePool status=validated consumer=fname",
            "name=RuntimeGUObjectArray status=validated consumer=object-array",
            "RuntimeGUObjectArray",
            "RuntimeFNamePool",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_native_reflection_descriptor_provenance_is_logged_on_all_loaders(self):
        common_required = [
            "reflection_descriptor_provenance(",
            "descriptorProvenance=",
            "fieldTargetImage=",
            "objectTargetImage=",
            "valueTargetImage=",
            "event=ue-reflection-property name=",
            "event=ue-reflection-value name=",
            "self-test",
            "runtime",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_runtime_candidate_global_restart_stable_modes_are_platform_specific(self):
        linux_required = [
            "@rwfile",
            "resolve_runtime_rw_file_offset",
            "runtimeRwFileOffset=%s",
            "runtime-rw-file-offset-missing",
        ]
        for loader in ("linux-server", "linux-client"):
            with self.subTest(loader=loader):
                source = LOADER_SOURCES[loader].read_text(encoding="utf-8")
                for item in linux_required:
                    self.assertIn(item, source)

        windows_source = LOADER_SOURCES["windows-client"].read_text(encoding="utf-8")
        for item in [
            "@private-rva",
            "resolve_runtime_private_rva",
            "runtimePrivateRva=",
            "runtime-private-rva-missing",
            "runtime-private-rva-ambiguous",
        ]:
            self.assertIn(item, windows_source)

    def test_fname_decode_diagnostics_are_available_on_all_loaders(self):
        common_required = [
            "event=ue-fname-diagnostic",
            "event=ue-fname-resolver-reject",
            "event=ue-object-array-class-reflection",
            "lenShift1",
            "wideBit0",
            "lenShift6",
            "wideBit15",
            "entryReadable",
        ]
        per_loader_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE",
                "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX",
                "DUNE_PROBE_LOADER_UE_FNAME_ALLOW_MISSING_NONE",
                "DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS",
                "DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS_MAX",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE",
                "DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX",
                "DUNE_CLIENT_PROBE_UE_FNAME_ALLOW_MISSING_NONE",
                "DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS",
                "DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS_MAX",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE",
                "DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_MAX",
                "DUNE_WIN_CLIENT_PROBE_UE_FNAME_ALLOW_MISSING_NONE",
                "DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS",
                "DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS_MAX",
            ],
        }
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required + per_loader_required[loader]:
                    self.assertIn(item, source)

        package_required = {
            "linux-server": [
                "DUNE_PROBE_LOADER_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE=false",
                "DUNE_PROBE_LOADER_UE_FNAME_ALLOW_MISSING_NONE=false",
                "DUNE_PROBE_LOADER_UE_FNAME_DIAGNOSTICS=false",
                "DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false",
                "DUNE_PROBE_LOADER_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0",
            ],
            "linux-client": [
                "DUNE_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE=false",
                "DUNE_CLIENT_PROBE_UE_FNAME_ALLOW_MISSING_NONE=false",
                "DUNE_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS=false",
                "DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false",
                "DUNE_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0",
            ],
            "windows-client": [
                "DUNE_WIN_CLIENT_PROBE_UE_OBJECT_ARRAY_CLASS_REFLECTION_PROBE=false",
                "DUNE_WIN_CLIENT_PROBE_UE_FNAME_ALLOW_MISSING_NONE=false",
                "DUNE_WIN_CLIENT_PROBE_UE_FNAME_DIAGNOSTICS=false",
                "DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_INCLUDE_PRIVATE_RW=false",
                "DUNE_WIN_CLIENT_PROBE_UE_AUTO_DISCOVER_MAX_REJECTED_FNAME_SAMPLES=0",
            ],
        }
        for platform, script in PACKAGE_SCRIPTS.items():
            with self.subTest(package=platform):
                source = script.read_text(encoding="utf-8")
                for item in package_required[platform]:
                    self.assertIn(item, source)

    def test_fname_pool_resolver_rejects_pointer_table_false_positives(self):
        common_required = [
            "plausible_entries",
            "scan_limit = 4096",
            "plausible_entries >= 4",
            "plausible_entries >= 32",
            "first_block_entry_plausible",
            "first_block_entry_none",
            "allocator_state_plausible",
            "current_byte_cursor < (2U * 1024U * 1024U)",
            "pool == (uintptr_t)&ue_self_test_fname_pool",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_object_array_scan_limit_supports_wide_active_validation_discovery(self):
        common_required = [
            "#define MAX_UE_OBJECT_ARRAY_SCAN_OBJECTS 65536",
            "options.max_objects > MAX_UE_OBJECT_ARRAY_SCAN_OBJECTS",
            "options.max_objects = MAX_UE_OBJECT_ARRAY_SCAN_OBJECTS;",
        ]
        for loader, source_path in LOADER_SOURCES.items():
            with self.subTest(loader=loader):
                source = source_path.read_text(encoding="utf-8")
                for item in common_required:
                    self.assertIn(item, source)

    def test_client_packages_ship_non_mutating_launch_preflight_tests(self):
        for platform in ("linux-client", "windows-client"):
            with self.subTest(platform=platform):
                source = PACKAGE_SCRIPTS[platform].read_text(encoding="utf-8")
                self.assertIn("test-client-launch-preflight.py", source)
                self.assertIn("tests/test-client-launch-preflight.py", source)

    def test_server_package_ships_zero_player_canary_preflight_test(self):
        source = PACKAGE_SCRIPTS["linux-server"].read_text(encoding="utf-8")
        self.assertIn("canary-linux-server-loader.sh", source)
        self.assertIn("test-canary-linux-server-loader.py", source)

    def test_server_package_ships_remote_package_trace_wrapper(self):
        source = PACKAGE_SCRIPTS["linux-server"].read_text(encoding="utf-8")
        self.assertIn("ue4ss-package-remote-trace.sh", source)
        self.assertIn("test-ue4ss-package-remote-trace.py", source)

    def test_server_package_writes_post_archive_verification_reports(self):
        source = PACKAGE_SCRIPTS["linux-server"].read_text(encoding="utf-8")
        required = [
            '--package-archive "$archive"',
            '--format text > "${archive}.verification.txt"',
            '--format json > "${archive}.verification.json"',
            "package verification: %s",
        ]
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_server_package_stimulus_runbook_workflow_order(self):
        source = PACKAGE_SCRIPTS["linux-server"].read_text(encoding="utf-8")
        required = [
            "scripts/plan-ue4ss-package-stimulus.py --format json > ue4ss-package-stimulus-plan.json",
            "scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --format json > ue4ss-package-live-call-frame-recovery-plan.json",
            "PACKAGE_STIMULUS_TRACE_LOG=\"/tmp/ue4ss-package-runtime-trace-live-client-map-entry-\\$(date -u +%Y%m%dT%H%M%SZ).log\"",
            "scripts/plan-ue4ss-package-stimulus-trace.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --live-plan-json ue4ss-package-live-call-frame-recovery-plan.json --external-plan ue4ss-package-external-symbol-plan.json --trace-plan-json ue4ss-package-runtime-trace-plan.json --trace-plan-md ue4ss-package-runtime-trace-plan.md --method-candidates ue-package-loader-vtables.json --trace-log \"\\$PACKAGE_STIMULUS_TRACE_LOG\" --format json > ue4ss-package-stimulus-trace-runbook.json",
            "scripts/plan-ue4ss-package-live-call-frame-recovery.py --stimulus-plan-json ue4ss-package-stimulus-plan.json --trace-runbook-json ue4ss-package-stimulus-trace-runbook.json --format json > ue4ss-package-live-call-frame-recovery-plan.json",
            "PACKAGE_NEXT_ACTION_INPUTS=(--promotion-summary-json ue4ss-package-promotion-dir.json --trace-plan-json ue4ss-package-runtime-trace-plan.json --live-trace-runbook-json ue4ss-package-stimulus-trace-runbook.json)",
            "[ -f ue4ss-package-runtime-trace-history.json ] && PACKAGE_NEXT_ACTION_INPUTS+=(--trace-history-json ue4ss-package-runtime-trace-history.json)",
            "[ -f ue4ss-package-route-evidence.json ] && PACKAGE_NEXT_ACTION_INPUTS+=(--route-evidence-json ue4ss-package-route-evidence.json)",
            "[ -f ue4ss-package-method-probe-refinement.json ] && PACKAGE_NEXT_ACTION_INPUTS+=(--method-probe-refinement-json ue4ss-package-method-probe-refinement.json)",
            "scripts/plan-ue4ss-package-next-action.py \"\\${PACKAGE_NEXT_ACTION_INPUTS[@]}\" --format json > ue4ss-package-next-action.json",
        ]
        positions = []
        for item in required:
            position = source.find(item)
            self.assertNotEqual(position, -1, item)
            positions.append(position)
        self.assertEqual(positions, sorted(positions))

    def test_server_package_documents_live_stimulus_preflight_only(self):
        source = PACKAGE_SCRIPTS["linux-server"].read_text(encoding="utf-8")
        self.assertIn("run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-\\$(date -u +%Y%m%dT%H%M%SZ).log", source)
        self.assertIn("run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-\\$(date -u +%Y%m%dT%H%M%SZ).log", source)
        self.assertIn("same timestamped trace-log pattern", source)
        self.assertIn("approved login/travel/map-entry stimulus", source)
        self.assertIn("without arming gdb", source)
        self.assertIn("reviewBundleVerification", source)
        self.assertIn("reviewBundleVerificationSha256", source)
        self.assertIn("routeSlotRecoveryVerification", source)
        self.assertIn("prearmReadinessVerification", source)
        self.assertIn("self-contained after the remote \\`/tmp\\` verifier path expires", source)
        self.assertIn("rejects claimed-ready summaries that lack readable or embedded verifier", source)
        self.assertIn("evidence", source)
        self.assertIn("verify-ue4ss-package-route-slot-recovery.py <ue4ss-package-runtime-trace-evidence.json> --next-action-json ue4ss-package-next-action.json", source)
        self.assertIn("nextTraceRequirement", source)
        self.assertIn("UE4SS_PACKAGE_ROUTE_TRACE_HIT", source)
        self.assertIn("routeVtableStaticSlotMatches", source)
        self.assertIn("0x129d58a2", source)
        self.assertIn("0x3a0, 0x3d8", source)
        self.assertIn("rbx, r14", source)


if __name__ == "__main__":
    unittest.main()
