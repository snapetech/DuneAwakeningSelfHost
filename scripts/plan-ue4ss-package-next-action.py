#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-next-action/v1"
PROMOTION_SUMMARY_SCHEMA_VERSION = "dune-ue4ss-package-promotion-dir-summary/v1"
TRACE_PLAN_SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-plan/v1"
PROMOTION_ACCEPTANCE_SCHEMA_VERSION = "dune-ue4ss-package-anchor-promotion-acceptance/v1"
DEFAULT_WRAPPER = "scripts/ue4ss-package-runtime-trace.sh"
PACKAGE_TRACE_ANCHORS = {"StaticLoadObject", "StaticLoadClass", "LoadObject", "LoadPackage", "ResolveName"}
CLIENT_ORIGIN_SERVER_SIDE_FALLBACK = "server-side-client-call-emulation"


def non_negative_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def positive_decimal_text(value):
    text = str(value)
    return text.isascii() and text.isdecimal() and int(text) > 0


def valid_image_offset(value):
    text = str(value)
    return text.startswith("0x") and len(text) > 2 and all(char in "0123456789abcdefABCDEF" for char in text[2:])


def valid_sha256_text(value):
    text = str(value)
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def present_non_true(value):
    return value is not None and value is not True


def runtime_trace_evidence_tokens(value):
    parts = str(value).split(":", 2)
    tail = parts[2] if len(parts) > 2 else ""
    tokens = {}
    for item in tail.split():
        if "=" not in item:
            continue
        key, token_value = item.split("=", 1)
        if key:
            tokens[key] = token_value
    return tokens


def load_json(path):
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        with candidate.open("r", encoding="utf-8", errors="replace") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return None


def load_trace_history(path):
    data = load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        entries = data.get("entries")
        if isinstance(entries, list):
            return entries
        return [data]
    return []


def load_donor_target_validation(path):
    data = load_json(path)
    if isinstance(data, dict):
        data.setdefault("sourcePath", str(path))
        return data
    return {}


def load_route_evidence(path):
    data = load_json(path)
    if isinstance(data, dict):
        data.setdefault("sourcePath", str(path))
        return data
    return {}


def load_route_static_review(path):
    data = load_json(path)
    if isinstance(data, dict):
        data.setdefault("sourcePath", str(path))
        return data
    return {}


def load_method_probe_refinement(path):
    data = load_json(path)
    if isinstance(data, dict):
        data.setdefault("sourcePath", str(path))
        return data
    return {}


def load_live_trace_runbook(path):
    data = load_json(path)
    if isinstance(data, dict):
        data.setdefault("sourcePath", str(path))
        return data
    return {}


def trace_plan_error(path, error):
    return {
        "schemaVersion": TRACE_PLAN_SCHEMA_VERSION,
        "sourcePath": str(path),
        "sourceExternalPlan": "build/server-ue4ss-package-external-symbol-plan.json",
        "base": "0x100000",
        "recommendedTraceEnv": {},
        "blockers": [error],
    }


def load_trace_plan(path):
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return trace_plan_error(path, "runtime trace plan file is not readable")
    try:
        with candidate.open("r", encoding="utf-8", errors="replace") as handle:
            plan = json.load(handle)
    except json.JSONDecodeError as exc:
        return trace_plan_error(path, f"invalid JSON in runtime trace plan: {exc}")
    if not isinstance(plan, dict):
        return trace_plan_error(path, "runtime trace plan is not a JSON object")
    plan.setdefault("sourcePath", str(path))
    if plan.get("schemaVersion") != TRACE_PLAN_SCHEMA_VERSION:
        blockers = list(plan.get("blockers", []) or [])
        blockers.append("not a UE4SS package runtime trace plan")
        plan["blockers"] = blockers
        plan.setdefault("sourceExternalPlan", "build/server-ue4ss-package-external-symbol-plan.json")
        plan.setdefault("base", "0x100000")
        plan["recommendedTraceEnv"] = {}
    return plan


def load_promotion_summary(path):
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return {
            "schemaVersion": PROMOTION_SUMMARY_SCHEMA_VERSION,
            "sourcePath": str(path),
            "sourceArg": "--package-promotion-summary-json",
            "readyManifestPaths": [],
            "manifests": [],
            "errors": [{"path": str(path), "error": "promotion summary file is not readable"}],
        }
    try:
        with candidate.open("r", encoding="utf-8", errors="replace") as handle:
            summary = json.load(handle)
    except json.JSONDecodeError as exc:
        return {
            "schemaVersion": PROMOTION_SUMMARY_SCHEMA_VERSION,
            "sourcePath": str(path),
            "sourceArg": "--package-promotion-summary-json",
            "readyManifestPaths": [],
            "manifests": [],
            "errors": [{"path": str(path), "error": f"invalid JSON in promotion summary: {exc}"}],
        }
    if not isinstance(summary, dict):
        return {
            "schemaVersion": PROMOTION_SUMMARY_SCHEMA_VERSION,
            "sourcePath": str(path),
            "sourceArg": "--package-promotion-summary-json",
            "readyManifestPaths": [],
            "manifests": [],
            "errors": [{"path": str(path), "error": "promotion summary must be a JSON object"}],
        }
    summary["sourcePath"] = str(path)
    summary["sourceArg"] = "--package-promotion-summary-json"
    if summary.get("schemaVersion") != PROMOTION_SUMMARY_SCHEMA_VERSION:
        errors = list(summary.get("errors", []) or [])
        errors.append(
            {
                "path": str(path),
                "error": "not a UE4SS package promotion directory summary",
            }
        )
        summary["errors"] = errors
    return summary


def load_promotion_manifest(path):
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return {
            "schemaVersion": PROMOTION_SUMMARY_SCHEMA_VERSION,
            "sourcePath": str(path),
            "sourceArg": "--package-promotion-json",
            "readyManifestPaths": [],
            "manifests": [],
            "errors": [{"path": str(path), "error": "promotion manifest file is not readable"}],
        }
    try:
        with candidate.open("r", encoding="utf-8", errors="replace") as handle:
            manifest = json.load(handle)
    except json.JSONDecodeError as exc:
        return {
            "schemaVersion": PROMOTION_SUMMARY_SCHEMA_VERSION,
            "sourcePath": str(path),
            "sourceArg": "--package-promotion-json",
            "readyManifestPaths": [],
            "manifests": [],
            "errors": [{"path": str(path), "error": f"invalid JSON in promotion manifest: {exc}"}],
        }
    if not isinstance(manifest, dict):
        return {
            "schemaVersion": PROMOTION_SUMMARY_SCHEMA_VERSION,
            "sourcePath": str(path),
            "sourceArg": "--package-promotion-json",
            "readyManifestPaths": [],
            "manifests": [],
            "errors": [{"path": str(path), "error": "promotion manifest must be a JSON object"}],
        }
    if manifest.get("schemaVersion") != "dune-ue4ss-package-promotion-env/v1":
        return {
            "schemaVersion": PROMOTION_SUMMARY_SCHEMA_VERSION,
            "sourcePath": str(path),
            "sourceArg": "--package-promotion-json",
            "readyManifestPaths": [],
            "manifests": [],
            "errors": [{"path": str(path), "error": "not a UE4SS package promotion env manifest"}],
        }
    return summary_from_single_manifest(candidate, manifest)


def import_sibling(script_name, module_name):
    script = Path(__file__).resolve().parent / script_name
    spec = importlib.util.spec_from_file_location(module_name, script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"unable to import {script}")
    spec.loader.exec_module(module)
    return module


def verify_review_bundle(bundle):
    if not bundle:
        return None
    verifier = import_sibling("verify-ue4ss-package-review-bundle.py", "verify_package_review_bundle")
    return verifier.verify_bundle(bundle)


def summarize_promotion_dir(root):
    candidate = Path(root)
    if not candidate.is_dir():
        return {}
    summarizer = import_sibling("summarize-ue4ss-package-promotion-dir.py", "summarize_package_promotion_dir")
    return summarizer.build_summary(candidate)


def resolve_review_bundle(bundle):
    if not bundle:
        return None
    root = Path(bundle)
    if (root / "review-bundle-manifest.txt").is_file():
        return root
    if not root.is_dir():
        return root
    candidates = [
        child
        for child in root.iterdir()
        if child.is_dir() and (child / "review-bundle-manifest.txt").is_file()
    ]
    if not candidates:
        return root
    return sorted(candidates, key=review_bundle_sort_key, reverse=True)[0]


def review_bundle_sort_key(path):
    match = re.fullmatch(r"(\d{8}T\d{6}Z)(?:-(\d+))?", path.name)
    if match:
        return (match.group(1), int(match.group(2) or "0"), path.stat().st_mtime)
    return ("", -1, path.stat().st_mtime)


def summary_from_single_manifest(path, manifest):
    ready = manifest.get("readyForNonInvokingCanary") is True or manifest.get("readyForNativeInvoke") is True
    raw_env = manifest.get("env", {}) or {}
    env_errors = []
    env = raw_env if isinstance(raw_env, dict) else {}
    if not isinstance(raw_env, dict):
        env_errors.append("package promotion env must be an object")
    else:
        for key, value in raw_env.items():
            if not isinstance(key, str) or not key:
                env_errors.append("package promotion env contains an invalid key")
                break
            if isinstance(value, (dict, list)):
                env_errors.append(f"package promotion env contains a non-scalar value for {key}")
                break
    missing_review, missing_review_errors = string_list_field(manifest, "missingReviewFlags")
    missing_native, missing_native_errors = string_list_field(manifest, "missingNativeInvokeFlags")
    blockers, blocker_errors = string_list_field(manifest, "blockers")
    abi_review, abi_review_errors = object_field(manifest, "abiReview")
    abi_review_blockers, abi_review_blocker_errors = string_list_field(abi_review, "blockers")
    shape_errors = (
        missing_review_errors
        + missing_native_errors
        + blocker_errors
        + abi_review_errors
        + [f"abiReview.{error}" for error in abi_review_blocker_errors]
        + abi_review_argument_shape_errors(abi_review)
    )
    row = {
        "path": str(path),
        "promotionAcceptanceSchemaVersion": manifest.get("promotionAcceptanceSchemaVersion", ""),
        "signatureFamily": manifest.get("signatureFamily", "unknown"),
        "hitIndex": manifest.get("hitIndex"),
        "selectedHitSeed": manifest.get("selectedHitSeed", ""),
        "sourceEvidence": manifest.get("sourceEvidence", ""),
        "sourceEvidenceJson": manifest.get("sourceEvidenceJson", ""),
        "sourceEvidenceJsonSha256": manifest.get("sourceEvidenceJsonSha256", ""),
        "sourceLogSha256": manifest.get("sourceLogSha256", ""),
        "tracePid": manifest.get("tracePid"),
        "sourceTracePlan": manifest.get("sourceTracePlan", ""),
        "sourceTracePlanSchemaVersion": manifest.get("sourceTracePlanSchemaVersion", ""),
        "sourcePromotionAcceptanceSchemaVersion": manifest.get("sourcePromotionAcceptanceSchemaVersion", ""),
        "sourceExternalPlan": manifest.get("sourceExternalPlan", ""),
        "tracePidMatchesRequested": manifest.get("tracePidMatchesRequested"),
        "imageRangeSource": manifest.get("imageRangeSource", ""),
        "imageBase": manifest.get("imageBase", ""),
        "imageStart": manifest.get("imageStart", ""),
        "imageEnd": manifest.get("imageEnd", ""),
        "imagePath": manifest.get("imagePath", ""),
        "imagePerms": manifest.get("imagePerms", ""),
        "callerImageOffset": manifest.get("callerImageOffset", ""),
        "ripImageOffset": manifest.get("ripImageOffset", ""),
        "abiReviewReady": manifest.get("abiReviewReady") is True or abi_review.get("ready") is True,
        "abiReviewed": manifest.get("abiReviewed") is True,
        "targetImageReviewed": manifest.get("targetImageReviewed") is True,
        "tcharReviewed": manifest.get("tcharReviewed") is True,
        "classRootReviewed": manifest.get("classRootReviewed") is True,
        "nativeInvokeEnabled": manifest.get("nativeInvokeEnabled") is True,
        "finalNativeCallConfirmed": manifest.get("finalNativeCallConfirmed") is True,
        "readyForNonInvokingCanary": manifest.get("readyForNonInvokingCanary") is True,
        "readyForNativeInvoke": manifest.get("readyForNativeInvoke") is True,
        "missingReviewFlags": missing_review,
        "missingNativeInvokeFlags": missing_native,
        "blockers": blockers + env_errors + shape_errors,
        "abiReviewBlockers": abi_review_blockers,
        "env": dict(env),
        "hit": dict(manifest.get("hit", {}) or {}) if isinstance(manifest.get("hit", {}), dict) else {},
        "nextStep": manifest.get("nextStep", ""),
    }
    if "sourceLogExists" in manifest:
        row["sourceLogExists"] = manifest.get("sourceLogExists")
    errors = list(row["blockers"])
    if ready and manifest.get("promotionAcceptanceSchemaVersion") != PROMOTION_ACCEPTANCE_SCHEMA_VERSION:
        errors.append("ready package promotion manifest is missing current package promotion acceptance schema")
    row["blockers"] = errors
    ready = ready and not errors
    return {
        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
        "sourcePath": str(path),
        "sourceArg": "--package-promotion-json",
        "readyManifestPaths": [str(path)] if ready else [],
        "manifests": [row],
    }


def bundle_inputs(bundle):
    if not bundle:
        return {}, {}, None
    root = resolve_review_bundle(bundle)
    verification = verify_review_bundle(root)
    if verification and not verification.get("ready"):
        return {}, {}, verification
    promotion_dir_path = root / "ue4ss-package-family-reviews"
    promotion_summary = summarize_promotion_dir(promotion_dir_path)
    if promotion_summary and promotion_summary.get("manifestCount", 0) > 0:
        promotion_summary["sourcePath"] = str(promotion_dir_path)
        promotion_summary["sourceArg"] = "--package-promotion-dir"
    else:
        summary_path = root / "ue4ss-package-family-reviews.json"
        promotion_summary = load_promotion_summary(summary_path) if summary_path.is_file() else {}
        if promotion_summary:
            promotion_summary["sourceArg"] = "--package-promotion-summary-json"
        else:
            promotion_manifest_path = root / "ue4ss-package-promotion-env.json"
            promotion_manifest = load_json(promotion_manifest_path)
            if promotion_manifest:
                promotion_summary = summary_from_single_manifest(promotion_manifest_path, promotion_manifest)
    trace_plan = load_json(root / "ue4ss-package-runtime-trace-plan.json") or {}
    return promotion_summary, trace_plan, verification


def bundle_runtime_evidence_summary(bundle):
    if not bundle:
        return {}
    root = resolve_review_bundle(bundle)
    evidence = load_json(root / "ue4ss-package-runtime-trace-evidence.json") or {}
    if not isinstance(evidence, dict):
        return {}
    route_slot = evidence.get("routeSlotRecovery") if isinstance(evidence.get("routeSlotRecovery"), dict) else {}
    route_hits = [
        {
            "hitIndex": index,
            "imageOffset": hit.get("imageOffset", ""),
            "callerImageOffset": hit.get("callerImageOffset", ""),
            "staticSlotMatchCount": len(hit.get("routeVtableStaticSlotMatches", []) or [])
            if isinstance(hit.get("routeVtableStaticSlotMatches", []), list)
            else 0,
        }
        for index, hit in enumerate(evidence.get("routeHits", []) or [])
        if isinstance(hit, dict)
    ]
    return {
        "sourcePath": str(root / "ue4ss-package-runtime-trace-evidence.json"),
        "hitCount": evidence.get("hitCount", 0),
        "routeHitCount": evidence.get("routeHitCount", 0),
        "methodHitCount": evidence.get("methodHitCount", 0),
        "routeSlotRecoveryReady": route_slot.get("ready"),
        "routeSlotRecoveryBlockers": route_slot.get("blockers", []) if isinstance(route_slot.get("blockers", []), list) else [],
        "routeSlotRecoveryMissingSlots": route_slot.get("missingSlots", []) if isinstance(route_slot.get("missingSlots", []), list) else [],
        "routeHits": route_hits[:4],
    }


def bundled_route_slot_requirement(bundle_verification):
    if not isinstance(bundle_verification, dict):
        return None
    bundle = bundle_verification.get("bundle", "")
    if not bundle:
        return None
    runbook = load_json(Path(bundle) / "ue4ss-package-stimulus-trace-runbook.json")
    if not isinstance(runbook, dict):
        return None
    requirement = runbook.get("routeSlotTraceRequirement")
    return requirement if isinstance(requirement, dict) else None


def current_route_slot_requirement(runbook):
    if not isinstance(runbook, dict):
        return None
    requirement = runbook.get("routeSlotTraceRequirement")
    return requirement if isinstance(requirement, dict) else None


def stale_bundle_route_slot_blocker(bundle_verification, live_trace_runbook):
    current_requirement = current_route_slot_requirement(live_trace_runbook)
    if not current_requirement:
        return ""
    bundled_requirement = bundled_route_slot_requirement(bundle_verification)
    if bundled_requirement != current_requirement:
        return "review bundle stimulus trace runbook routeSlotTraceRequirement is stale or missing"
    return ""


def sh_quote(value):
    text = str(value)
    if text and all(ch.isalnum() or ch in "_./:=,+-" for ch in text):
        return text
    return "'" + text.replace("'", "'\"'\"'") + "'"


def shell_env(env):
    return " ".join(f"{key}={sh_quote(value)}" for key, value in env.items())


def shell_command(argv, env=None):
    prefix = shell_env(env or {})
    body = " ".join(sh_quote(arg) for arg in argv)
    return f"{prefix} {body}".strip()


def live_trace_runbook_commands(runbook):
    if not isinstance(runbook, dict):
        return []
    commands = runbook.get("commands", [])
    if not isinstance(commands, list):
        return []
    return [command for command in commands if isinstance(command, str) and command]


def live_trace_runbook_summary(runbook):
    if not isinstance(runbook, dict) or not runbook:
        return {}
    review_artifacts = runbook.get("reviewArtifacts", {}) or {}
    if not isinstance(review_artifacts, dict):
        review_artifacts = {}
    operator_window = runbook.get("operatorWindow", {}) or {}
    if not isinstance(operator_window, dict):
        operator_window = {}
    route_slot_trace_requirement = runbook.get("routeSlotTraceRequirement", {}) or {}
    if not isinstance(route_slot_trace_requirement, dict):
        route_slot_trace_requirement = {}
    prearm_readiness_json = review_artifacts.get("prearmReadinessJson", "") or runbook.get("prearmReadinessJson", "")
    prearm_readiness = load_json(prearm_readiness_json)
    if not isinstance(prearm_readiness, dict):
        prearm_readiness = {}
    return {
        "sourcePath": runbook.get("sourcePath", ""),
        "recommendedCandidate": runbook.get("recommendedCandidate", ""),
        "remote": runbook.get("remote", ""),
        "container": runbook.get("container", ""),
        "traceLog": runbook.get("traceLog", ""),
        "coordinatorCommand": runbook.get("coordinatorCommand", ""),
        "coordinatorDryRunCommand": runbook.get("coordinatorDryRunCommand", ""),
        "coordinatorFreshPreflightCommand": runbook.get("coordinatorFreshPreflightCommand", ""),
        "coordinatorFreshTraceCommand": runbook.get("coordinatorFreshTraceCommand", ""),
        "cleanupCommand": runbook.get("cleanupCommand", ""),
        "noDebuggerCheckCommand": runbook.get("noDebuggerCheckCommand", ""),
        "reviewBundleVerificationJson": review_artifacts.get("reviewBundleVerificationJson", ""),
        "localReviewSummaryJson": review_artifacts.get("localReviewSummaryJson", ""),
        "localReviewSummarySchemaVersion": review_artifacts.get("localReviewSummarySchemaVersion", ""),
        "localReviewSummaryEmbeddedEvidenceFields": review_artifacts.get("localReviewSummaryEmbeddedEvidenceFields", ""),
        "localReviewSummaryRunbookMode": review_artifacts.get("localReviewSummaryRunbookMode", "")
        or runbook.get("localReviewSummaryRunbookMode", ""),
        "localReviewSummaryVerificationCommand": review_artifacts.get("localReviewSummaryVerificationCommand", "")
        or runbook.get("localReviewSummaryVerificationCommand", ""),
        "prearmReadinessJson": prearm_readiness_json,
        "prearmReadinessMarkdown": review_artifacts.get("prearmReadinessMarkdown", "")
        or runbook.get("prearmReadinessMarkdown", ""),
        "prearmReadinessVerificationCommand": review_artifacts.get("prearmReadinessVerificationCommand", "")
        or runbook.get("prearmReadinessVerificationCommand", ""),
        "prearmReadinessReady": prearm_readiness.get("ready") if "ready" in prearm_readiness else None,
        "prearmReadinessNextStep": prearm_readiness.get("nextStep", ""),
        "completionAuditNextOriginClassification": prearm_readiness.get(
            "completionAuditNextOriginClassification",
            prearm_readiness.get("completionAuditNextClientGateClassification", {}),
        ),
        "completionAuditNextClientGateClassification": prearm_readiness.get(
            "completionAuditNextClientGateClassification",
            {},
        ),
        "completionAuditNextRuntimeRootRecoveryPlan": prearm_readiness.get(
            "completionAuditNextRuntimeRootRecoveryPlan",
            {},
        ),
        "digestProvenanceFields": review_artifacts.get("digestProvenanceFields", ""),
        "commandCount": len(live_trace_runbook_commands(runbook)),
        "operatorWindow": operator_window,
        "routeSlotTraceRequirement": route_slot_trace_requirement,
    }


def route_slot_recovery_summary(route_static_review):
    if not isinstance(route_static_review, dict) or not route_static_review:
        return {}
    review = route_static_review.get("staticVtableTargetReview") or {}
    artifacts = route_static_review.get("artifacts") or {}
    route_address = route_static_review.get("routeAddress", "")
    if not route_address:
        return {}
    companion_slots = []
    route_shape = route_static_review.get("routeShape") or {}
    source_shape = route_static_review.get("sourceShape") or {}
    for slot in (source_shape.get("callsite", ""), route_shape.get("callsite", "")):
        match = re.search(r"0x[0-9a-fA-F]+", str(slot))
        if match:
            value = f"0x{int(match.group(0), 16):x}"
            if value not in companion_slots:
                companion_slots.append(value)
    if not companion_slots:
        companion_slots = ["0x3a0", "0x3d8"]
    return {
        "sourcePath": route_static_review.get("sourcePath", "build/server-current-anchor-prep/ue4ss-package-route-129d58a2-static-review.json"),
        "routeAddress": route_address,
        "routeSourceAddress": route_static_review.get("routeSourceAddress", ""),
        "finding": route_static_review.get("finding", ""),
        "staticVtableFinding": review.get("finding", ""),
        "staticVtableImplication": review.get("implication", ""),
        "wrapperStaticRefCount": review.get("wrapperStaticRefCount"),
        "childHelperStaticRefCount": review.get("childHelperStaticRefCount"),
        "callgraphNodeCount": review.get("callgraphNodeCount"),
        "packageAnchorNodeCount": review.get("packageAnchorNodeCount"),
        "streamableNodeCount": review.get("streamableNodeCount"),
        "requiredRouteTrace": {
            "address": route_address,
            "reviewField": "routeVtableStaticSlotMatches",
            "slots": companion_slots,
            "registers": ["rbx", "r14"],
        },
        "verificationCommand": (
            "scripts/verify-ue4ss-package-route-slot-recovery.py "
            "/tmp/ue4ss-package-runtime-trace-evidence.json "
            "--next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json"
        ),
        "artifacts": {
            key: artifacts.get(key, "")
            for key in (
                "routeVtableTargetsJson",
                "routeVtableTargetsMarkdown",
                "routeVtableTargetCallgraphJson",
                "routeVtableTargetCallgraphMarkdown",
            )
            if artifacts.get(key, "")
        },
    }


def attach_current_runtime_evidence(recovery, evidence):
    if recovery and evidence:
        recovery = dict(recovery)
        recovery["currentRuntimeEvidence"] = evidence
    return recovery


def bundle_blockers_are_only_missing_runtime_hits(blockers):
    normalized = [str(blocker) for blocker in blockers or []]
    return bool(normalized) and all(
        "selected runtime trace hit is missing for hitIndex" in blocker
        for blocker in normalized
    )


def ready_manifest_paths(summary):
    raw_paths = (summary or {}).get("readyManifestPaths", [])
    return raw_paths if isinstance(raw_paths, list) else []


SUMMARY_MANIFEST_MATCH_FIELDS = (
    "signatureFamily",
    "hitIndex",
    "selectedHitSeed",
    "sourceEvidence",
    "sourceLogExists",
    "tracePid",
    "sourceTracePlan",
    "sourceTracePlanSchemaVersion",
    "sourcePromotionAcceptanceSchemaVersion",
    "sourceExternalPlan",
    "imageRangeSource",
    "imageBase",
    "imageStart",
    "imageEnd",
    "imagePath",
    "imagePerms",
    "callerImageOffset",
    "ripImageOffset",
    "abiReviewReady",
    "abiReviewed",
    "targetImageReviewed",
    "tcharReviewed",
    "classRootReviewed",
    "readyForNonInvokingCanary",
    "readyForNativeInvoke",
    "nativeInvokeEnabled",
    "finalNativeCallConfirmed",
)

PACKAGE_CLASS_ENV_KEYS = {
    "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL",
}

PACKAGE_ASSET_ENV_KEYS = {
    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI",
    "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE",
    "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL",
}

ASSET_FAMILIES = {"StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName"}


def string_list_field(payload, key):
    raw = (payload or {}).get(key, [])
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [f"{key} must be a JSON array"]
    values = []
    errors = []
    for index, value in enumerate(raw):
        if not isinstance(value, str):
            errors.append(f"{key}[{index}] must be a string")
            continue
        values.append(value)
    return values, errors


def missing_required_memory_registers(hit):
    return string_list_field(hit, "missingRequiredMemoryRegisters")


def register_memory_shape_errors(hit):
    register_memory = (hit or {}).get("registerMemory", {})
    if register_memory is None:
        return []
    if not isinstance(register_memory, dict):
        return ["registerMemory must be a JSON object"]
    errors = []
    for register, rows in register_memory.items():
        if not isinstance(register, str) or not register:
            errors.append("registerMemory contains an invalid register key")
            continue
        if not isinstance(rows, list):
            errors.append(f"registerMemory.{register} must be a JSON array")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, str):
                errors.append(f"registerMemory.{register}[{index}] must be a string")
                break
    return errors


def abi_review_argument_shape_errors(abi_review):
    arguments = (abi_review or {}).get("arguments", [])
    if arguments is None:
        return []
    if not isinstance(arguments, list):
        return ["abiReview.arguments must be a JSON array"]
    errors = []
    for arg_index, argument in enumerate(arguments):
        if not isinstance(argument, dict):
            errors.append(f"abiReview.arguments[{arg_index}] must be a JSON object")
            continue
        memory = argument.get("memory", {})
        if memory is None:
            continue
        if not isinstance(memory, dict):
            errors.append(f"abiReview.arguments[{arg_index}].memory must be a JSON object")
            continue
        line_count = memory.get("lineCount", 0)
        if (
            not isinstance(line_count, int)
            or isinstance(line_count, bool)
            or line_count < 0
        ):
            errors.append(
                f"abiReview.arguments[{arg_index}].memory.lineCount must be a non-negative integer"
            )
        hints = memory.get("hints", {})
        if hints is not None and not isinstance(hints, dict):
            errors.append(f"abiReview.arguments[{arg_index}].memory.hints must be a JSON object")
    return errors


def object_field(payload, key):
    raw = (payload or {}).get(key, {}) or {}
    if not isinstance(raw, dict):
        return {}, [f"{key} must be a JSON object"]
    return raw, []


def scalar_identity_errors(path, row, fields):
    errors = []
    for field in fields:
        if field not in row:
            continue
        value = row.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, (str, int, float, bool)):
            errors.append({"path": str(path), "error": f"ready package promotion summary row {field} must be a scalar"})
            continue
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            errors.append(
                {
                    "path": str(path),
                    "error": f"ready package promotion summary row {field} must be a non-empty single-line value",
                }
            )
    return errors


def blocked_manifest_rows(summary):
    manifest_rows = (summary or {}).get("manifests", [])
    if not isinstance(manifest_rows, list):
        return []
    return [
        row
        for row in manifest_rows
        if isinstance(row, dict)
        if not row.get("readyForNonInvokingCanary") and not row.get("readyForNativeInvoke")
    ]


def first_pending_review(summary):
    for row in blocked_manifest_rows(summary):
        missing_review, missing_review_errors = string_list_field(row, "missingReviewFlags")
        missing_native, missing_native_errors = string_list_field(row, "missingNativeInvokeFlags")
        blockers, blocker_errors = string_list_field(row, "blockers")
        abi_review_blockers, abi_review_blocker_errors = string_list_field(row, "abiReviewBlockers")
        if any("no runtime trace hits" in blocker for blocker in blockers + abi_review_blockers):
            continue
        shape_errors = missing_review_errors + missing_native_errors + blocker_errors
        abi_shape_errors = [f"abiReview.{error}" for error in abi_review_blocker_errors]
        if missing_review or missing_native or blockers or abi_review_blockers or shape_errors or abi_shape_errors:
            return {
                "signatureFamily": row.get("signatureFamily", ""),
                "hitIndex": row.get("hitIndex", "auto"),
                "missingReviewFlags": missing_review,
                "missingNativeInvokeFlags": missing_native,
                "blockers": blockers + shape_errors,
                "abiReviewBlockers": abi_review_blockers + abi_shape_errors,
                "nextStep": row.get("nextStep", ""),
            }
    return None


def trace_env_from_plan(trace_plan):
    recommended = (trace_plan or {}).get("recommendedTraceEnv", {})
    if recommended is None:
        return {}, []
    if not isinstance(recommended, dict):
        return {}, [{"path": "recommendedTraceEnv", "error": "runtime trace plan recommendedTraceEnv must be an object"}]
    errors = []
    env = {}
    for key, value in recommended.items():
        if not isinstance(key, str) or not key:
            errors.append({"path": "recommendedTraceEnv", "error": "runtime trace plan recommendedTraceEnv keys must be non-empty strings"})
            continue
        if key == "selectedByFamily":
            if not isinstance(value, dict):
                errors.append({"path": "selectedByFamily", "error": "runtime trace plan recommendedTraceEnv selectedByFamily must be an object"})
                continue
            for family, count in value.items():
                if not isinstance(family, str) or not family:
                    errors.append({"path": "selectedByFamily", "error": "runtime trace plan recommendedTraceEnv selectedByFamily keys must be non-empty strings"})
                    break
                if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                    errors.append({"path": "selectedByFamily", "error": "runtime trace plan recommendedTraceEnv selectedByFamily values must be positive integers"})
                    break
            continue
        if not key.replace("_", "").isalnum() or not key.startswith("DUNE_UE4SS_PACKAGE_TRACE_"):
            errors.append({"path": "recommendedTraceEnv", "error": f"runtime trace plan recommendedTraceEnv key is not a supported trace env variable: {key}"})
            continue
        if not isinstance(value, (str, int, float, bool)):
            errors.append({"path": key, "error": f"runtime trace plan {key} must be a scalar"})
            continue
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            errors.append({"path": key, "error": f"runtime trace plan {key} must be a non-empty single-line value"})
            continue
        env[key] = value
    anchor_text = str(env.get("DUNE_UE4SS_PACKAGE_TRACE_ANCHOR", "")).strip()
    anchors = [anchor.strip() for anchor in anchor_text.split(",") if anchor.strip()]
    if not anchors:
        errors.append({"path": "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR", "error": "runtime trace plan anchor list is empty"})
    for anchor in anchors:
        if anchor not in PACKAGE_TRACE_ANCHORS:
            errors.append({"path": "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR", "error": f"unsupported runtime trace anchor: {anchor}"})
            break
    signature_family = str(env.get("DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY", "")).strip()
    if signature_family and signature_family not in PACKAGE_TRACE_ANCHORS:
        errors.append({"path": "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY", "error": f"unsupported runtime trace signature family: {signature_family}"})
    limit = env.get("DUNE_UE4SS_PACKAGE_TRACE_LIMIT")
    if limit is not None:
        try:
            if int(str(limit)) < 1:
                errors.append({"path": "DUNE_UE4SS_PACKAGE_TRACE_LIMIT", "error": "runtime trace limit must be positive"})
        except ValueError:
            errors.append({"path": "DUNE_UE4SS_PACKAGE_TRACE_LIMIT", "error": "runtime trace limit must be an integer"})
    hit_index = env.get("DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX")
    if hit_index is not None and str(hit_index) != "auto":
        try:
            if int(str(hit_index)) < 0:
                errors.append({"path": "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX", "error": "runtime trace hit index must be non-negative or auto"})
        except ValueError:
            errors.append({"path": "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX", "error": "runtime trace hit index must be an integer or auto"})
    route_addresses = []
    for value in (trace_plan or {}).get("requestedRouteAddresses", []) or []:
        if not isinstance(value, str) or not valid_image_offset(value):
            errors.append({"path": "requestedRouteAddresses", "error": "runtime trace plan route addresses must be hex image offsets"})
            break
        route_addresses.append(f"0x{int(value, 16):x}")
    if not route_addresses:
        for route in (trace_plan or {}).get("routeProbes", []) or []:
            if not isinstance(route, dict):
                errors.append({"path": "routeProbes", "error": "runtime trace plan route probes must be objects"})
                break
            value = route.get("address") or route.get("imageOffset")
            if not isinstance(value, str) or not valid_image_offset(value):
                errors.append({"path": "routeProbes", "error": "runtime trace plan route probe addresses must be hex image offsets"})
                break
            route_addresses.append(f"0x{int(value, 16):x}")
    if route_addresses:
        seen = set()
        deduped = []
        for address in route_addresses:
            if address not in seen:
                seen.add(address)
                deduped.append(address)
        env["DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS"] = ",".join(deduped)
    if errors:
        return {}, errors
    return env, []


def selector_value_errors(trace_host="", process_pattern=""):
    errors = []
    for path, value in (("--trace-host", trace_host), ("--process-pattern", process_pattern)):
        if value is None or value == "":
            continue
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            errors.append({"path": path, "error": f"{path[2:]} must be a non-empty single-line value"})
    return errors


def output_path_errors(next_canary_json="", next_canary_env=""):
    errors = []
    for path, value in (("--next-canary-json", next_canary_json), ("--next-canary-env", next_canary_env)):
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            errors.append({"path": path, "error": f"{path[2:]} must be a non-empty single-line path"})
    return errors


def log_path_errors(trace_log="", canary_log=""):
    errors = []
    for path, value in (("--trace-log", trace_log), ("--canary-log", canary_log)):
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            errors.append({"path": path, "error": f"{path[2:]} must be a non-empty single-line path"})
    return errors


def trace_plan_refresh_paths(trace_plan):
    raw_source_path = (trace_plan or {}).get("sourcePath", "")
    source_path = raw_source_path if isinstance(raw_source_path, str) else ""
    if source_path.endswith(".json"):
        json_path = source_path
        markdown_path = str(Path(source_path).with_suffix(".md"))
    else:
        json_path = "/tmp/ue4ss-package-runtime-trace-plan.json"
        markdown_path = "/tmp/ue4ss-package-runtime-trace-plan.md"
    return json_path, markdown_path


def trace_plan_blocker_messages(trace_plan):
    blockers, errors = string_list_field(trace_plan or {}, "blockers")
    return blockers, [{"path": "blockers", "error": f"runtime trace plan {error}"} for error in errors]


def trace_plan_refresh_input_errors(trace_plan):
    errors = []
    for key in ("sourceExternalPlan", "base", "sourcePath"):
        value = (trace_plan or {}).get(key)
        if value is not None and not isinstance(value, (str, int, float, bool)):
            errors.append({"path": key, "error": f"runtime trace plan {key} must be a scalar"})
    return errors


def trace_plan_refresh_commands(trace_plan):
    trace_plan = trace_plan or {}
    recommended, _ = trace_env_from_plan(trace_plan)
    source_external_plan = trace_plan.get("sourceExternalPlan", "build/server-ue4ss-package-external-symbol-plan.json")
    if not isinstance(source_external_plan, (str, int, float, bool)):
        source_external_plan = "build/server-ue4ss-package-external-symbol-plan.json"
    base = trace_plan.get("base", "0x100000")
    if not isinstance(base, (str, int, float, bool)):
        base = "0x100000"
    base_args = [
        "scripts/plan-ue4ss-package-runtime-trace.py",
        "--external-plan",
        source_external_plan,
        "--base",
        base,
    ]
    for anchor in str(recommended.get("DUNE_UE4SS_PACKAGE_TRACE_ANCHOR", "")).split(","):
        anchor = anchor.strip()
        if anchor:
            base_args.extend(["--anchor", anchor])
    if recommended.get("DUNE_UE4SS_PACKAGE_TRACE_LIMIT"):
        base_args.extend(["--limit", str(recommended["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"])])
    for address in str(recommended.get("DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS", "")).split(","):
        address = address.strip()
        if address:
            base_args.extend(["--route-address", address])
    json_path, markdown_path = trace_plan_refresh_paths(trace_plan)
    return [
        shell_command([*base_args, "--format", "json"]) + " >" + sh_quote(json_path),
        shell_command([*base_args, "--format", "markdown"]) + " >" + sh_quote(markdown_path),
    ]


def planned_seed_keys(trace_plan):
    keys = set()
    for seed in (trace_plan or {}).get("seeds", []) or []:
        if not isinstance(seed, dict):
            continue
        name = seed.get("name")
        address = seed.get("address") or seed.get("imageOffset")
        if isinstance(name, str) and name and isinstance(address, str) and address:
            keys.add((name, address.lower()))
    return keys


def planned_method_keys(trace_plan):
    keys = set()
    for method in (trace_plan or {}).get("methodProbes", []) or []:
        if not isinstance(method, dict):
            continue
        address = method.get("address") or method.get("imageOffset")
        owner = method.get("owner", "")
        slot = method.get("slotIndex", "")
        if isinstance(address, str) and address:
            keys.add((str(owner), str(slot), address.lower()))
    return keys


def evidence_seed_keys(entry):
    keys = set()
    plan = entry.get("tracePlan") if isinstance(entry.get("tracePlan"), dict) else entry
    for seed in (plan or {}).get("seeds", []) or []:
        if not isinstance(seed, dict):
            continue
        name = seed.get("name")
        address = seed.get("address") or seed.get("imageOffset")
        if isinstance(name, str) and name and isinstance(address, str) and address:
            keys.add((name, address.lower()))
    if keys:
        return keys
    for armed_seed in entry.get("armedSeeds", []) or []:
        if not isinstance(armed_seed, dict):
            continue
        name = armed_seed.get("name")
        address = armed_seed.get("address") or armed_seed.get("imageOffset")
        if isinstance(name, str) and name and isinstance(address, str) and address:
            keys.add((name, address.lower()))
    return keys


def evidence_method_keys(entry):
    keys = set()
    plan = entry.get("tracePlan") if isinstance(entry.get("tracePlan"), dict) else entry
    for method in (plan or {}).get("methodProbes", []) or []:
        if not isinstance(method, dict):
            continue
        address = method.get("address") or method.get("imageOffset")
        owner = method.get("owner", "")
        slot = method.get("slotIndex", "")
        if isinstance(address, str) and address:
            keys.add((str(owner), str(slot), address.lower()))
    if keys:
        return keys
    for method in entry.get("armedMethodProbes", []) or []:
        if not isinstance(method, dict):
            continue
        address = method.get("address") or method.get("imageOffset")
        owner = method.get("owner", "")
        slot = method.get("slotIndex", "")
        if isinstance(address, str) and address:
            keys.add((str(owner), str(slot), address.lower()))
    return keys


def format_method_key(method):
    owner, slot, address = method
    if owner or slot:
        return f"{owner}:slot{slot}@{address}"
    return address


def no_hit_trace_exhaustion(trace_plan, trace_history):
    planned = planned_seed_keys(trace_plan)
    planned_methods = planned_method_keys(trace_plan)
    if not planned and not planned_methods:
        return {}
    covered = set()
    covered_methods = set()
    no_hit_runs = []
    for entry in trace_history or []:
        if not isinstance(entry, dict):
            continue
        if int(entry.get("armedCount", 0) or 0) < 1:
            continue
        if int(entry.get("hitCount", 0) or 0) != 0:
            continue
        if int(entry.get("methodHitCount", 0) or 0) != 0:
            continue
        keys = evidence_seed_keys(entry)
        method_keys = evidence_method_keys(entry)
        covered.update(keys & planned)
        covered_methods.update(method_keys & planned_methods)
        if (keys & planned) or (method_keys & planned_methods):
            no_hit_runs.append(
                {
                    "sourceLog": entry.get("sourceLog", ""),
                    "armedCount": entry.get("armedCount", 0),
                    "hitCount": entry.get("hitCount", 0),
                    "coveredSeeds": sorted(f"{name}@{address}" for name, address in (keys & planned)),
                    "coveredMethodProbes": sorted(format_method_key(method) for method in (method_keys & planned_methods)),
                }
            )
    exhausted = planned <= covered and planned_methods <= covered_methods
    if not exhausted:
        return {}
    return {
        "plannedSeeds": sorted(f"{name}@{address}" for name, address in planned),
        "coveredSeeds": sorted(f"{name}@{address}" for name, address in covered),
        "plannedMethodProbes": sorted(format_method_key(method) for method in planned_methods),
        "coveredMethodProbes": sorted(format_method_key(method) for method in covered_methods),
        "noHitRuns": no_hit_runs,
    }


def reviewed_non_promotable_method_routes(route_evidence):
    reviewed = set()
    for route in (route_evidence or {}).get("routes", []) or []:
        if not isinstance(route, dict) or route.get("id") != "runtime-method-route-review":
            continue
        if route.get("finding") != "negative":
            continue
        metrics = route.get("metrics", {}) or {}
        if int(metrics.get("nonPromotableRouteCount", 0) or 0) <= 0:
            continue
        reviewed.add(("vtable for FLinkerLoad", "31", "0x9b04600"))
        reviewed.add(("vtable for FLinkerLoad", "32", "0x9b04610"))
    return reviewed


def method_route_evidence(trace_history, route_evidence=None):
    reviewed = reviewed_non_promotable_method_routes(route_evidence)
    rows = []
    for entry in trace_history or []:
        if not isinstance(entry, dict):
            continue
        method_hits = entry.get("methodHits", []) or []
        if not isinstance(method_hits, list) or not method_hits:
            continue
        source_log = entry.get("sourceLog", "")
        for index, hit in enumerate(method_hits):
            if not isinstance(hit, dict):
                continue
            rows.append(
                {
                    "sourceLog": source_log,
                    "methodHitIndex": index,
                    "owner": hit.get("owner", ""),
                    "slotIndex": hit.get("slotIndex", ""),
                    "imageOffset": hit.get("imageOffset", ""),
                    "ripImageOffset": hit.get("ripImageOffset", ""),
                    "callerImageOffset": hit.get("callerImageOffset", ""),
                    "targetImageCaller": hit.get("targetImageCaller"),
                    "disassemblyLines": len(hit.get("disassembly", []) or []),
                    "stackLines": len(hit.get("stack", []) or []),
                }
            )
            key = (
                str(rows[-1].get("owner", "")),
                str(rows[-1].get("slotIndex", "")),
                str(rows[-1].get("imageOffset", "")).lower(),
            )
            if key in reviewed:
                rows.pop()
    rows.sort(
        key=lambda row: (
            row.get("targetImageCaller") is True,
            bool(row.get("callerImageOffset")),
            row.get("disassemblyLines", 0),
            row.get("stackLines", 0),
        ),
        reverse=True,
    )
    return rows


def promotable_package_donor_patterns(validation):
    rows = []
    if not isinstance(validation, dict):
        return rows
    for row in validation.get("patterns", []) or []:
        if not isinstance(row, dict):
            continue
        if row.get("category") != "package" or row.get("promotable") is not True:
            continue
        name = row.get("name", "")
        if name not in PACKAGE_TRACE_ANCHORS:
            continue
        matches = row.get("matches", []) or []
        first_match = matches[0] if matches and isinstance(matches[0], dict) else {}
        if not first_match.get("imageOffset") or not first_match.get("vaddr"):
            continue
        rows.append(
            {
                "name": name,
                "status": row.get("status", ""),
                "sourceProvenance": row.get("sourceProvenance", ""),
                "matchImageOffset": first_match.get("imageOffset", ""),
                "matchVaddr": first_match.get("vaddr", ""),
                "pattern": row.get("pattern", ""),
            }
        )
    return rows


def trace_plan_wrapper_env(trace_plan):
    trace_plan = trace_plan or {}
    env = {}
    source_external_plan = trace_plan.get("sourceExternalPlan")
    if isinstance(source_external_plan, (str, int, float, bool)) and str(source_external_plan).strip():
        env["DUNE_UE4SS_PACKAGE_TRACE_PLAN"] = str(source_external_plan)
    json_path, markdown_path = trace_plan_refresh_paths(trace_plan)
    env["DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON"] = json_path
    env["DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD"] = markdown_path
    return env


def manifest_family_env_errors(path, manifest):
    family = manifest.get("signatureFamily", "")
    env = manifest.get("env") or {}
    errors = []
    if family not in PACKAGE_TRACE_ANCHORS:
        errors.append({"path": str(path), "error": f"unsupported package promotion signatureFamily: {family}"})
    if not isinstance(env, dict):
        errors.append({"path": str(path), "error": "package promotion env must be an object"})
        return errors
    for key, value in env.items():
        if not isinstance(key, str) or not key:
            errors.append({"path": str(path), "error": "package promotion env contains an invalid key"})
            return errors
        if isinstance(value, (dict, list)):
            errors.append({"path": str(path), "error": f"package promotion env contains a non-scalar value for {key}"})
            return errors
    if family == "StaticLoadClass":
        if any(key in PACKAGE_ASSET_ENV_KEYS and env.get(key) for key in env):
            errors.append({"path": str(path), "error": "StaticLoadClass promotion env includes LoadAsset package keys"})
    elif family in ASSET_FAMILIES:
        if any(key in PACKAGE_CLASS_ENV_KEYS and env.get(key) for key in env):
            errors.append({"path": str(path), "error": f"{family} promotion env includes LoadClass package keys"})
    return errors


def embedded_hit_identity_errors(path, manifest):
    errors = []
    family = manifest.get("signatureFamily", "")
    selected_hit_seed = manifest.get("selectedHitSeed", "")
    caller_offset = manifest.get("callerImageOffset", "")
    rip_offset = manifest.get("ripImageOffset", "")
    if selected_hit_seed and family and selected_hit_seed != family:
        errors.append({"path": str(path), "error": "selectedHitSeed does not match signatureFamily"})
    hit = manifest.get("hit", {}) or {}
    if not isinstance(hit, dict) or not hit:
        return errors
    if present_non_true(hit.get("traceLogHasArmed")):
        errors.append({"path": str(path), "error": "embedded trace hit missing trace armed record; cannot prove runtime trace session"})
    if present_non_true(hit.get("tracePidMatchesRequested")):
        errors.append({"path": str(path), "error": "embedded trace hit trace log armed PID does not match requested runtime PID"})
    if hit.get("traceAddressMatchesBase") is not True:
        errors.append({"path": str(path), "error": "embedded trace hit address does not match image base plus seed imageOffset"})
    for error in register_memory_shape_errors(hit):
        errors.append({"path": str(path), "error": f"embedded trace hit {error}"})
    missing_required_memory, missing_required_memory_errors = missing_required_memory_registers(hit)
    for error in missing_required_memory_errors:
        errors.append({"path": str(path), "error": f"embedded trace hit {error}"})
    if missing_required_memory:
        errors.append(
            {
                "path": str(path),
                "error": "embedded trace hit is missing required memory registers: "
                + ", ".join(str(item) for item in missing_required_memory),
            }
        )
    hit_seed = hit.get("seed", "")
    if selected_hit_seed and hit_seed and selected_hit_seed != hit_seed:
        errors.append({"path": str(path), "error": "selectedHitSeed does not match embedded trace hit seed"})
    if hit_seed and family and hit_seed != family:
        errors.append({"path": str(path), "error": "embedded trace hit seed does not match signatureFamily"})
    if hit.get("callerImageOffset", "") and hit.get("callerImageOffset", "") != caller_offset:
        errors.append({"path": str(path), "error": "embedded trace hit callerImageOffset does not match manifest"})
    if hit.get("ripImageOffset", "") and hit.get("ripImageOffset", "") != rip_offset:
        errors.append({"path": str(path), "error": "embedded trace hit ripImageOffset does not match manifest"})
    return errors


def abi_review_shape_errors(path, manifest):
    abi_review, abi_review_errors = object_field(manifest, "abiReview")
    return [
        {"path": str(path), "error": error}
        for error in abi_review_errors + abi_review_argument_shape_errors(abi_review)
    ]


def runtime_trace_env_evidence_errors(path, manifest):
    family = manifest.get("signatureFamily", "")
    caller_offset = manifest.get("callerImageOffset", "")
    rip_offset = manifest.get("ripImageOffset", "")
    trace_pid = manifest.get("tracePid")
    evidence_json_sha256 = manifest.get("sourceEvidenceJsonSha256", "")
    source_log_sha256 = manifest.get("sourceLogSha256", "")
    env = manifest.get("env") or {}
    errors = []
    if not isinstance(env, dict):
        return [{"path": str(path), "error": "package promotion env must be an object"}]
    evidence_values = [
        str(value)
        for key, value in env.items()
        if key in (
            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE",
            "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE",
            "DUNE_PROBE_LOADER_TCHAR_EVIDENCE",
        )
        and str(value).startswith("runtime-trace:")
    ]
    ready_claimed = manifest.get("readyForNonInvokingCanary") is True or manifest.get("readyForNativeInvoke") is True
    if ready_claimed and not evidence_values:
        errors.append({"path": str(path), "error": "ready package promotion env is missing runtime trace evidence"})
    evidence_tokens = [runtime_trace_evidence_tokens(value) for value in evidence_values]
    if family:
        for value in evidence_values:
            parts = value.split(":", 2)
            evidence_family = parts[1] if len(parts) > 1 else ""
            if evidence_family != family:
                errors.append({"path": str(path), "error": "env evidence family does not match signatureFamily"})
                break
        for tokens in evidence_tokens:
            if tokens.get("seed", family) != family:
                errors.append({"path": str(path), "error": "env evidence seed does not match signatureFamily"})
                break
    if caller_offset:
        for tokens in evidence_tokens:
            if tokens.get("caller", "") != caller_offset:
                errors.append({"path": str(path), "error": "env evidence caller does not match callerImageOffset"})
                break
    if rip_offset:
        for tokens in evidence_tokens:
            if tokens.get("rip", "") != rip_offset:
                errors.append({"path": str(path), "error": "env evidence rip does not match ripImageOffset"})
                break
    if trace_pid not in (None, ""):
        for tokens in evidence_tokens:
            if tokens.get("pid", "") != str(trace_pid):
                errors.append({"path": str(path), "error": "env evidence pid does not match tracePid"})
                break
    if evidence_json_sha256:
        for tokens in evidence_tokens:
            if tokens.get("evidenceJsonSha256", "") != str(evidence_json_sha256):
                errors.append({"path": str(path), "error": "env evidence digest does not match sourceEvidenceJsonSha256"})
                break
    if source_log_sha256:
        for tokens in evidence_tokens:
            if tokens.get("sourceLogSha256", "") != str(source_log_sha256):
                errors.append({"path": str(path), "error": "env evidence log digest does not match sourceLogSha256"})
                break
    return errors


def promotion_summary_errors(summary, target_pid=""):
    errors = []
    raw_errors = (summary or {}).get("errors", [])
    if raw_errors is None:
        raw_errors = []
    if not isinstance(raw_errors, list):
        errors.append({"path": str((summary or {}).get("sourcePath", "")), "error": "promotion summary errors must be a JSON array"})
        raw_errors = []
    errors.extend(raw_errors)
    raw_ready_paths = (summary or {}).get("readyManifestPaths", [])
    if raw_ready_paths is None:
        raw_ready_paths = []
    if not isinstance(raw_ready_paths, list):
        errors.append({"path": str((summary or {}).get("sourcePath", "")), "error": "promotion summary readyManifestPaths must be a JSON array"})
        raw_ready_paths = []
    manifest_rows = (summary or {}).get("manifests", [])
    if manifest_rows is None:
        manifest_rows = []
    if not isinstance(manifest_rows, list):
        errors.append({"path": str((summary or {}).get("sourcePath", "")), "error": "promotion summary manifests must be a JSON array"})
        manifest_rows = []
    ready_rows = {}
    for index, row in enumerate(manifest_rows):
        if not isinstance(row, dict):
            errors.append({"path": str((summary or {}).get("sourcePath", "")), "error": f"promotion summary manifest row {index} must be a JSON object"})
            continue
        if row.get("readyForNonInvokingCanary") is not True and row.get("readyForNativeInvoke") is not True:
            continue
        raw_path = str(row.get("path", ""))
        if raw_path in ready_rows:
            errors.append({"path": raw_path, "error": "duplicate ready package promotion summary row"})
            continue
        ready_rows[raw_path] = row
    summary_source = Path(str((summary or {}).get("sourcePath", "")))
    should_check_manifest_files = (summary or {}).get("sourceArg") == "--package-promotion-summary-json"
    ready_paths = []
    seen_ready_paths = set()
    for raw_path in raw_ready_paths:
        if not isinstance(raw_path, str) or not raw_path:
            errors.append({"path": str(raw_path), "error": "invalid readyManifestPaths entry"})
            continue
        if raw_path in seen_ready_paths:
            errors.append({"path": raw_path, "error": "duplicate readyManifestPaths entry"})
            continue
        seen_ready_paths.add(raw_path)
        ready_paths.append(raw_path)
        row = ready_rows.get(raw_path)
        if row is None:
            errors.append({"path": raw_path, "error": "ready manifest path is not backed by a ready manifest row"})
            continue
        if should_check_manifest_files:
            manifest = load_json(raw_path)
            if manifest is None:
                errors.append({"path": raw_path, "error": "ready manifest path is not readable from promotion summary"})
                continue
            if manifest.get("schemaVersion") != "dune-ue4ss-package-promotion-env/v1":
                errors.append({"path": raw_path, "error": "ready manifest path is not a UE4SS package promotion env manifest"})
                continue
            for field in SUMMARY_MANIFEST_MATCH_FIELDS:
                if field in row and row.get(field) != manifest.get(field):
                    errors.append(
                        {
                            "path": raw_path,
                            "error": f"summary row {field} does not match promotion manifest",
                            "sourcePath": str(summary_source) if str(summary_source) else "",
                        }
                    )
                    break
            priority_path = Path(raw_path).parent / "review-priority.json"
            if priority_path.is_file():
                priority = load_json(priority_path)
                if priority is None:
                    errors.append(
                        {
                            "path": raw_path,
                            "error": f"invalid JSON in review priority {priority_path}",
                            "sourcePath": str(summary_source) if str(summary_source) else "",
                        }
                    )
                    priority = {}
                if "reviewPriority" in row and row.get("reviewPriority") != priority.get("rank"):
                    errors.append(
                        {
                            "path": raw_path,
                            "error": "summary row reviewPriority does not match review priority",
                            "sourcePath": str(summary_source) if str(summary_source) else "",
                        }
                    )
                if "reviewPriorityHitIndex" in row and row.get("reviewPriorityHitIndex") != priority.get("hitIndex"):
                    errors.append(
                        {
                            "path": raw_path,
                            "error": "summary row reviewPriorityHitIndex does not match review priority",
                            "sourcePath": str(summary_source) if str(summary_source) else "",
                        }
                    )
            errors.extend(manifest_family_env_errors(raw_path, manifest))
            errors.extend(abi_review_shape_errors(raw_path, manifest))
            errors.extend(embedded_hit_identity_errors(raw_path, manifest))
            errors.extend(runtime_trace_env_evidence_errors(raw_path, manifest))
    if ready_paths and not str((summary or {}).get("sourcePath", "")):
        errors.append({"path": "", "error": "ready package promotion summary is missing sourcePath"})
    for raw_path in sorted(set(ready_rows) - set(ready_paths)):
        errors.append({"path": raw_path, "error": "ready manifest row is missing from readyManifestPaths"})
    for raw_path, row in ready_rows.items():
        errors.extend(
            scalar_identity_errors(
                raw_path,
                row,
                (
                    "sourceEvidence",
                    "sourceEvidenceJson",
                    "sourceEvidenceJsonSha256",
                    "sourceLogSha256",
                    "tracePid",
                    "sourceTracePlan",
                    "sourceTracePlanSchemaVersion",
                    "sourcePromotionAcceptanceSchemaVersion",
                    "sourceExternalPlan",
                    "imageRangeSource",
                    "imageBase",
                    "imageStart",
                    "imageEnd",
                    "imagePath",
                    "imagePerms",
                    "callerImageOffset",
                    "ripImageOffset",
                    "selectedHitSeed",
                ),
            )
        )
        row_blockers, row_blocker_errors = string_list_field(row, "blockers")
        for error in row_blocker_errors:
            errors.append({"path": raw_path, "error": f"ready package promotion summary row {error}"})
        row_missing_flags, row_missing_flag_errors = string_list_field(row, "missingReviewFlags")
        for error in row_missing_flag_errors:
            errors.append({"path": raw_path, "error": f"ready package promotion summary row {error}"})
        row_abi_blockers, row_abi_blocker_errors = string_list_field(row, "abiReviewBlockers")
        for error in row_abi_blocker_errors:
            errors.append({"path": raw_path, "error": f"ready package promotion summary row {error}"})
        row_missing_native_flags, row_missing_native_flag_errors = string_list_field(
            row,
            "missingNativeInvokeFlags",
        )
        for error in row_missing_native_flag_errors:
            errors.append({"path": raw_path, "error": f"ready package promotion summary row {error}"})
        if row_blockers:
            errors.append({"path": raw_path, "error": "ready package promotion summary row still has blockers"})
            for blocker in row_blockers:
                errors.append({"path": raw_path, "error": blocker})
        if row_abi_blockers:
            errors.append({"path": raw_path, "error": "ready package promotion summary row still has ABI review blockers"})
        if row.get("abiReviewReady") is not True:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing ABI review readiness"})
        if row.get("abiReviewed") is not True:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing reviewed ABI confirmation"})
        family = row.get("signatureFamily", "")
        if family not in PACKAGE_TRACE_ANCHORS:
            errors.append({"path": raw_path, "error": f"unsupported package promotion signatureFamily: {family}"})
        if row.get("targetImageReviewed") is not True:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing reviewed target-image confirmation"})
        if family == "StaticLoadClass" and row.get("classRootReviewed") is not True:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing reviewed class-root confirmation"})
        if family in ASSET_FAMILIES and row.get("tcharReviewed") is not True:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing reviewed TCHAR confirmation"})
        if row.get("readyForNativeInvoke") is True and row.get("nativeInvokeEnabled") is not True:
            errors.append({"path": raw_path, "error": "ready native package promotion summary row is missing native invoke enablement"})
        if row.get("readyForNativeInvoke") is True and row.get("finalNativeCallConfirmed") is not True:
            errors.append({"path": raw_path, "error": "ready native package promotion summary row is missing final native-call confirmation"})
        if row_missing_flags:
            errors.append({"path": raw_path, "error": "ready package promotion summary row still has missing review flags"})
        if row.get("readyForNativeInvoke") is True and row.get("readyForNonInvokingCanary") is not True:
            errors.append({"path": raw_path, "error": "ready native package promotion summary row is missing non-invoking canary readiness"})
        if row.get("readyForNativeInvoke") is True and row_missing_native_flags:
            errors.append({"path": raw_path, "error": "ready native package promotion summary row still has missing native invoke flags"})
        if not row.get("sourceEvidence", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing sourceEvidence"})
        if not row.get("sourceEvidenceJson", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing sourceEvidenceJson provenance"})
        if not row.get("sourceEvidenceJsonSha256", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing sourceEvidenceJsonSha256 provenance"})
        elif not valid_sha256_text(row.get("sourceEvidenceJsonSha256", "")):
            errors.append({"path": raw_path, "error": "ready package promotion summary row has invalid sourceEvidenceJsonSha256"})
        if not row.get("sourceLogSha256", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing sourceLogSha256 provenance"})
        elif not valid_sha256_text(row.get("sourceLogSha256", "")):
            errors.append({"path": raw_path, "error": "ready package promotion summary row has invalid sourceLogSha256"})
        if "sourceLogExists" not in row:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing sourceLogExists"})
        elif row.get("sourceLogExists") is not True:
            errors.append({"path": raw_path, "error": "ready package promotion summary row sourceLog does not exist"})
        if not row.get("sourceTracePlan", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing sourceTracePlan provenance"})
        if row.get("sourceTracePlanSchemaVersion") != TRACE_PLAN_SCHEMA_VERSION:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing current sourceTracePlanSchemaVersion provenance"})
        if row.get("sourcePromotionAcceptanceSchemaVersion") != PROMOTION_ACCEPTANCE_SCHEMA_VERSION:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing current sourcePromotionAcceptanceSchemaVersion provenance"})
        if not row.get("sourceExternalPlan", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing sourceExternalPlan provenance"})
        if "tracePidMatchesRequested" not in row:
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing runtime trace PID match provenance"})
        elif row.get("tracePidMatchesRequested") is not True:
            errors.append({"path": raw_path, "error": "trace log armed PID does not match requested runtime PID"})
        if not non_negative_int(row.get("hitIndex")):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing concrete hitIndex"})
        if not row.get("selectedHitSeed", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing selectedHitSeed"})
        if not row.get("callerImageOffset", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing callerImageOffset"})
        elif not valid_image_offset(row.get("callerImageOffset", "")):
            errors.append({"path": raw_path, "error": "ready package promotion summary row has invalid callerImageOffset"})
        if not row.get("ripImageOffset", ""):
            errors.append({"path": raw_path, "error": "ready package promotion summary row is missing ripImageOffset"})
        elif not valid_image_offset(row.get("ripImageOffset", "")):
            errors.append({"path": raw_path, "error": "ready package promotion summary row has invalid ripImageOffset"})
        if target_pid:
            row_trace_pid = row.get("tracePid")
            if row_trace_pid in (None, ""):
                errors.append({"path": raw_path, "error": "ready package promotion summary row is missing tracePid for explicit target PID"})
            elif str(row_trace_pid) != str(target_pid):
                errors.append({"path": raw_path, "error": "ready package promotion summary row tracePid does not match explicit target PID"})
        if (summary or {}).get("sourceArg") != "--package-promotion-summary-json":
            errors.extend(manifest_family_env_errors(raw_path, row))
            errors.extend(abi_review_shape_errors(raw_path, row))
            errors.extend(embedded_hit_identity_errors(raw_path, row))
            errors.extend(runtime_trace_env_evidence_errors(raw_path, row))
    return errors


def build_action(
    promotion_summary=None,
    trace_plan=None,
    trace_history=None,
    donor_target_validation=None,
    route_evidence=None,
    route_static_review=None,
    current_runtime_evidence=None,
    method_probe_refinement=None,
    live_trace_runbook=None,
    bundle_verification=None,
    wrapper=DEFAULT_WRAPPER,
    container="dune_server-deep-desert-1",
    process_pattern="",
    target_pid="",
    trace_host="",
    trace_log="/tmp/ue4ss-package-runtime-trace-live.log",
    canary_log="/tmp/dune-server-probe-loader.log",
    next_canary_json="/tmp/ue4ss-package-next-canary.json",
    next_canary_env="/tmp/ue4ss-package-next-canary.env",
):
    promotion_summary = promotion_summary or {}
    trace_plan = trace_plan or {}
    trace_history = trace_history or []
    donor_target_validation = donor_target_validation or {}
    route_evidence = route_evidence or {}
    route_static_review = route_static_review or {}
    current_runtime_evidence = current_runtime_evidence or {}
    method_probe_refinement = method_probe_refinement or {}
    live_trace_runbook = live_trace_runbook or {}
    if bundle_verification and not bundle_verification.get("ready"):
        bundle_next_step = "fix or regenerate the package review bundle before using it for review or canary planning"
        bundle_blockers = list(bundle_verification.get("blockers", []) or [])
        if bundle_blockers_are_only_missing_runtime_hits(bundle_blockers):
            route_slot = attach_current_runtime_evidence(
                route_slot_recovery_summary(route_static_review),
                current_runtime_evidence,
            )
            action_blockers = list(bundle_blockers)
            route_slot_blockers = list(route_slot.get("routeSlotRecoveryBlockers", []) or [])
            current_route_slot = route_slot.get("currentRuntimeEvidence", {}) or {}
            if isinstance(current_route_slot, dict):
                route_slot_blockers.extend(current_route_slot.get("routeSlotRecoveryBlockers", []) or [])
            for blocker in route_slot_blockers:
                if blocker:
                    action_blockers.append(f"route-slot recovery: {blocker}")
            stale_route_slot_blocker = stale_bundle_route_slot_blocker(bundle_verification, live_trace_runbook)
            if stale_route_slot_blocker:
                action_blockers.append(stale_route_slot_blocker)
            commands = [
                shell_command(
                    [
                        "scripts/verify-ue4ss-package-review-bundle.py",
                        bundle_verification.get("bundle", ""),
                    ]
                )
            ]
            runbook_commands = live_trace_runbook_commands(live_trace_runbook)
            if runbook_commands:
                commands.extend(
                    [
                        shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-live-call-frame-recovery-plan.json"]),
                        shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-server-replay-plan.json"]),
                    ]
                )
                commands.extend(runbook_commands)
            coordinator_command = live_trace_runbook_summary(live_trace_runbook).get("coordinatorCommand", "")
            next_step = (
                "run the live trace coordinator during the approved client login/travel/map-entry package-load classification stimulus, "
                "then verify the new review bundle and local review summary; if the evidence is client-originated, recover the call frame and replay/spoof the equivalent call server-side"
                if coordinator_command
                else (
                    "capture one bounded all-family trace during the approved client login/travel/map-entry "
                    "package-load classification stimulus, then rerun status and verify the new review bundle and local review summary; if client-originated, switch to server-side replay/spoofing"
                )
            )
            return {
                "schemaVersion": SCHEMA_VERSION,
                "action": "recover-package-anchor",
                "confidence": "moderate",
                "reason": "review bundle integrity is usable but the runtime trace captured no package hit",
                "blockers": action_blockers,
                "bundleVerification": bundle_verification,
                "liveTraceRunbook": live_trace_runbook_summary(live_trace_runbook),
                "routeSlotRecovery": route_slot,
                "commands": commands,
                "nextStep": next_step,
            }
        if any(
            "tracePidMatchesRequested" in str(blocker)
            or "PID match provenance" in str(blocker)
            or "tracePid does not match runtime trace evidence pid" in str(blocker)
            or "DUNE_UE4SS_PACKAGE_TRACE_PID does not match" in str(blocker)
            for blocker in bundle_blockers
        ):
            bundle_next_step = (
                "rerun package trace status with a resolved target PID so the bundle records "
                "tracePidMatchesRequested=true and manifest tracePid matches runtime evidence pid"
            )
        elif any("playerGuard" in str(blocker) for blocker in bundle_blockers):
            bundle_next_step = (
                "rerun remote package trace status on kspls0 after the zero-player guard passes so "
                "the bundle records playerGuardPhase=status and playerGuardConnectedPlayers=0"
            )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "verify-bundle",
            "confidence": "high",
            "reason": "review bundle verification failed; do not use bundled package evidence",
            "bundleVerification": bundle_verification,
            "commands": [
                shell_command(
                    [
                        "scripts/verify-ue4ss-package-review-bundle.py",
                        bundle_verification.get("bundle", ""),
                    ]
                )
            ],
            "nextStep": bundle_next_step,
        }
    ready_paths = ready_manifest_paths(promotion_summary)
    trace_env, trace_env_errors = trace_env_from_plan(trace_plan)
    target_pid_text = str(target_pid)
    summary_errors = promotion_summary_errors(promotion_summary, target_pid=target_pid_text)
    trace_plan_blockers, trace_plan_blocker_errors = trace_plan_blocker_messages(trace_plan)
    trace_plan_blockers.extend(error["error"] for error in trace_plan_blocker_errors)
    trace_plan_blockers.extend(error["error"] for error in trace_plan_refresh_input_errors(trace_plan))
    trace_plan_blockers.extend(error["error"] for error in trace_env_errors)
    selector_errors = selector_value_errors(trace_host=trace_host, process_pattern=process_pattern)
    canary_output_errors = output_path_errors(next_canary_json=next_canary_json, next_canary_env=next_canary_env)
    package_log_errors = log_path_errors(trace_log=trace_log, canary_log=canary_log)
    if target_pid_text and not positive_decimal_text(target_pid_text):
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "complete-review",
            "confidence": "high",
            "reason": "explicit package trace PID is invalid; do not emit replay commands until it is numeric",
            "promotionSummaryErrors": [{"path": "--target-pid", "error": "target PID must be numeric"}],
            "commands": [],
            "nextStep": "rerun next-action planning with a numeric --target-pid or omit it for Docker process discovery",
        }
    if selector_errors:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "complete-review",
            "confidence": "high",
            "reason": "package trace selector is invalid; do not emit replay commands until selectors are single-line values",
            "promotionSummaryErrors": selector_errors,
            "commands": [],
            "nextStep": "rerun next-action planning with valid --trace-host and --process-pattern values",
        }
    if canary_output_errors:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "complete-review",
            "confidence": "high",
            "reason": "package canary output path is invalid; do not emit canary planning commands until output paths are single-line values",
            "promotionSummaryErrors": canary_output_errors,
            "commands": [],
            "nextStep": "rerun next-action planning with valid --next-canary-json and --next-canary-env paths",
        }
    if package_log_errors:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "complete-review",
            "confidence": "high",
            "reason": "package trace log path is invalid; do not emit replay commands until log paths are single-line values",
            "promotionSummaryErrors": package_log_errors,
            "commands": [],
            "nextStep": "rerun next-action planning with valid --trace-log and --canary-log paths",
        }
    selector_env = {}
    if trace_host:
        selector_env["DUNE_UE4SS_PACKAGE_TRACE_HOST"] = trace_host
    if process_pattern:
        selector_env["DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN"] = process_pattern
    if target_pid:
        selector_env["DUNE_UE4SS_PACKAGE_TRACE_PID"] = str(target_pid)
    trace_target = container
    if target_pid and container == "dune_server-deep-desert-1":
        trace_target = f"pid-{target_pid}"

    if summary_errors:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "complete-review",
            "confidence": "high",
            "reason": "package promotion summary has validation errors; do not plan package canary until review metadata is fixed",
            "promotionSummaryErrors": summary_errors,
            "liveTraceRunbook": live_trace_runbook_summary(live_trace_runbook),
            "commands": [
                shell_command(
                    [wrapper, "status", trace_target, trace_log],
                    env=selector_env,
                ),
            ],
            "nextStep": "fix malformed package promotion review metadata, then rerun package trace status or next-action planning",
        }

    if ready_paths:
        promotion_arg = promotion_summary.get("sourceArg", "--package-promotion-summary-json")
        canary_args = [
            "scripts/plan-ue4ss-canary-env.py",
            "--platform",
            "server",
            "--server-log",
            canary_log,
            "--max-stage",
            "lua-dispatch",
            promotion_arg,
            promotion_summary.get("sourcePath", "/tmp/ue4ss-package-family-reviews.json"),
            "--format",
            "json",
        ]
        env_args = [*canary_args[:-1], "env"]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "plan-canary",
            "confidence": "high",
            "reason": "ready package promotion manifests are available",
            "readyManifestPaths": ready_paths,
            "promotionSummaryErrors": summary_errors,
            "outputFiles": {
                "nextCanaryJson": next_canary_json,
                "nextCanaryEnv": next_canary_env,
            },
            "commands": [
                shell_command(canary_args) + " >" + sh_quote(next_canary_json),
                shell_command(env_args) + " >" + sh_quote(next_canary_env),
            ],
            "nextStep": "review generated canary env, then run the guarded lua-dispatch canary",
        }

    pending = first_pending_review(promotion_summary)
    if pending:
        env = {
            "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": pending["signatureFamily"] or "LoadPackage",
            "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": pending["hitIndex"] if pending["hitIndex"] is not None else "auto",
        }
        env.update(selector_env)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "complete-review",
            "confidence": "moderate",
            "reason": "trace evidence exists but promotion is blocked on review or native-invoke flags",
            "pending": pending,
            "promotionSummaryErrors": summary_errors,
            "commands": [
                shell_command([wrapper, "status", trace_target, trace_log], env=env),
            ],
            "nextStep": "complete the listed review flags only after ABI/TCHAR evidence has been manually verified",
        }

    donor_patterns = promotable_package_donor_patterns(donor_target_validation)
    if donor_patterns:
        validation_path = donor_target_validation.get(
            "sourcePath",
            "build/server-ue4ss-package-donor-target-validation.json",
        )
        anchor_signatures = "build/server-ue4ss-package-anchor-signatures.txt"
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "plan-signature-anchor-canary",
            "confidence": "moderate",
            "reason": "validated donor-derived package signatures are available; run a signature-anchor canary before package native invocation",
            "donorTargetValidation": {
                "sourcePath": validation_path,
                "promotablePackagePatterns": donor_patterns,
                "promotablePackagePatternCount": len(donor_patterns),
            },
            "commands": [
                shell_command(
                    [
                        "scripts/export-elf-signature-manifest.py",
                        "/tmp/dune-live-server-extract/DuneSandboxServer-Linux-Shipping",
                        "--validation-json",
                        validation_path,
                        "--target-loader",
                        "server",
                        "--format",
                        "anchor-signatures",
                    ]
                )
                + " >"
                + sh_quote(anchor_signatures),
                shell_command(
                    [
                        "scripts/plan-ue4ss-canary-env.py",
                        "--platform",
                        "server",
                        "--server-log",
                        canary_log,
                        "--max-stage",
                        "lua-dispatch",
                        "--signature-validation-json",
                        validation_path,
                        "--anchor-signatures-file",
                        anchor_signatures,
                        "--format",
                        "json",
                    ]
                )
                + " >"
                + sh_quote(next_canary_json),
            ],
            "outputFiles": {
                "anchorSignatures": anchor_signatures,
                "nextCanaryJson": next_canary_json,
            },
            "nextStep": "review the generated signature-anchor canary plan, then run the canary to prove target-image package anchor coverage before package native invocation",
        }

    if trace_plan_blockers:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "refresh-trace-plan",
            "confidence": "high",
            "reason": "runtime trace plan has blockers; do not arm package trace until seed selection is fixed",
            "tracePlanBlockers": trace_plan_blockers,
            "commands": trace_plan_refresh_commands(trace_plan),
            "nextStep": "fix package runtime trace seed selection, then rerun next-action planning",
        }

    exhaustion = no_hit_trace_exhaustion(trace_plan, trace_history)
    if exhaustion:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "recover-package-anchor",
            "confidence": "moderate",
            "reason": "all planned runtime string seeds were armed with zero hits; recover package-anchor evidence through external symbols, targeted runtime call-frame tracing, or any remaining static/decompile route",
            "traceNoHitExhaustion": exhaustion,
            "commands": [
                shell_command(
                    [
                        "cat",
                        "build/server-current-anchor-prep/ue4ss-package-route-evidence.json",
                    ]
                ),
                shell_command(
                    [
                        "cat",
                        "build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json",
                    ]
                ),
            ],
            "nextStep": "recover a package anchor via external donor symbols or targeted runtime call-frame proof for StaticLoadObject/StaticLoadClass/LoadObject/LoadPackage/ResolveName, promote the reviewed ABI, then run the guarded native LoadAsset/LoadClass invocation",
        }

    method_routes = method_route_evidence(trace_history, route_evidence=route_evidence)
    if method_routes:
        best_route = method_routes[0]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "review-method-route",
            "confidence": "moderate",
            "reason": "runtime method probes hit target-image FLinkerLoad routes; review caller frames before arming another trace",
            "methodRouteEvidence": {
                "routeCount": len(method_routes),
                "bestRoute": best_route,
                "routes": method_routes[:8],
            },
            "commands": [
                shell_command(
                    [
                        "cat",
                        best_route.get("sourceLog", "")
                        or "build/server-current-anchor-prep/ue4ss-package-runtime-trace-combined-evidence.md",
                    ]
                ),
                shell_command(
                    [
                        "cat",
                        "build/server-current-anchor-prep/ue4ss-package-route-evidence.json",
                    ]
                ),
            ],
            "nextStep": "map the hot method caller offsets back to target functions, promote only if a reviewed package-load call frame is recovered, otherwise refine method probes around the caller route",
        }
    if reviewed_non_promotable_method_routes(route_evidence) and any(
        isinstance(entry, dict) and int(entry.get("methodHitCount", 0) or 0) > 0
        for entry in trace_history
    ):
        selected_probe_count = method_probe_refinement.get("selectedCount")
        no_unreviewed_method_probes = selected_probe_count == 0
        commands = [
            shell_command(["cat", route_evidence.get("sourcePath", "build/server-current-anchor-prep/ue4ss-package-route-evidence.json")]),
            shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-external-symbol-plan.json"]),
        ]
        if method_probe_refinement.get("sourcePath"):
            commands.insert(1, shell_command(["cat", method_probe_refinement["sourcePath"]]))
        commands.insert(
            -1,
            shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-source-abi-recovery.json"]),
        )
        commands.insert(
            -1,
            shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-static-metadata-recovery.json"]),
        )
        commands.insert(
            -1,
            shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-live-call-frame-recovery-plan.json"]),
        )
        commands.insert(
            -1,
            shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-server-replay-plan.json"]),
        )
        commands.insert(
            -1,
            shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-stimulus-plan.json"]),
        )
        commands.insert(
            -1,
            shell_command(["cat", "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json"]),
        )
        runbook_commands = live_trace_runbook_commands(live_trace_runbook)
        if no_unreviewed_method_probes and runbook_commands:
            commands.extend(runbook_commands)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "recover-package-anchor",
            "confidence": "moderate",
            "reason": (
                "runtime method hits were reviewed and are non-promotable; no unreviewed call-bearing package method probes remain"
                if no_unreviewed_method_probes
                else "runtime method hits were reviewed and are non-promotable; recover or refine package-specific anchor evidence"
            ),
            "methodProbeRefinement": {
                "sourcePath": method_probe_refinement.get("sourcePath", ""),
                "candidateCount": method_probe_refinement.get("candidateCount"),
                "selectedCount": selected_probe_count,
                "selectedAddresses": method_probe_refinement.get("selectedAddresses", []),
            },
            "liveTraceRunbook": live_trace_runbook_summary(live_trace_runbook),
            "commands": commands,
            "nextStep": (
                "use the live call-frame stimulus plan to classify the operator-selected client login/travel/map-entry package-load action; if it is client-originated, recover the call frame and replay/spoof the equivalent call server-side"
                if no_unreviewed_method_probes
                else "refine method probes around package-specific FLinkerLoad callers or recover external/static package ABI evidence; do not reuse reviewed slot 31/32 method hits for promotion"
            ),
        }

    if trace_env:
        env = {
            key: value
            for key, value in trace_env.items()
            if key.startswith("DUNE_UE4SS_PACKAGE_TRACE_")
        }
        env.update(trace_plan_wrapper_env(trace_plan))
        env.update(selector_env)
        return {
            "schemaVersion": SCHEMA_VERSION,
            "action": "arm-trace",
            "confidence": "moderate",
            "reason": "no ready package promotion manifest is available; runtime trace is the current shortest path",
            "traceEnv": env,
            "commands": [
                shell_command([wrapper, "preflight", trace_target, trace_log], env=env),
                shell_command([wrapper, "arm", trace_target, trace_log], env=env),
                shell_command([wrapper, "status", trace_target, trace_log], env=env),
            ],
            "nextStep": "capture a target-image package call frame, then rerun status to produce ABI review and promotion manifests",
        }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "action": "refresh-trace-plan",
        "confidence": "low",
        "reason": "no ready promotion summary or runtime trace recommendation was supplied",
        "commands": trace_plan_refresh_commands(trace_plan),
        "nextStep": "refresh the external-symbol trace plan and rerun this helper with its JSON output",
    }


def markdown(action):
    lines = ["# UE4SS Package Next Action", ""]
    lines.append(f"- Action: `{action['action']}`")
    lines.append(f"- Confidence: `{action['confidence']}`")
    lines.append(f"- Reason: {action['reason']}")
    if action.get("readyManifestPaths"):
        lines.append("- Ready manifests:")
        for path in action["readyManifestPaths"]:
            lines.append(f"  - `{path}`")
    if action.get("pending"):
        pending = action["pending"]
        lines.append(f"- Pending family: `{pending.get('signatureFamily', '')}` hitIndex=`{pending.get('hitIndex', '')}`")
        for flag in pending.get("missingReviewFlags", []):
            lines.append(f"  - missing review flag: `{flag}`")
        for flag in pending.get("missingNativeInvokeFlags", []):
            lines.append(f"  - missing native flag: `{flag}`")
        for blocker in pending.get("blockers", []):
            lines.append(f"  - blocker: {blocker}")
        for blocker in pending.get("abiReviewBlockers", []):
            lines.append(f"  - ABI review blocker: {blocker}")
    if action.get("promotionSummaryErrors"):
        lines.append("- Promotion summary errors:")
        for row in action["promotionSummaryErrors"]:
            lines.append(f"  - `{row.get('path', '')}`: {row.get('error', '')}")
    if action.get("tracePlanBlockers"):
        lines.append("- Trace plan blockers:")
        for blocker in action["tracePlanBlockers"]:
            lines.append(f"  - {blocker}")
    if action.get("traceNoHitExhaustion"):
        exhaustion = action["traceNoHitExhaustion"]
        lines.append("- Runtime trace no-hit exhaustion:")
        for seed in exhaustion.get("plannedSeeds", []):
            lines.append(f"  - planned seed: `{seed}`")
        for method in exhaustion.get("plannedMethodProbes", []):
            lines.append(f"  - planned method probe: `{method}`")
        for run in exhaustion.get("noHitRuns", []):
            lines.append(
                f"  - no-hit run: `{run.get('sourceLog', '')}` "
                f"armed=`{run.get('armedCount', '')}` hits=`{run.get('hitCount', '')}`"
            )
    if action.get("methodRouteEvidence"):
        evidence = action["methodRouteEvidence"]
        best = evidence.get("bestRoute", {}) or {}
        lines.append(f"- Method route candidates: `{evidence.get('routeCount', 0)}`")
        lines.append(
            f"  - best: `{best.get('owner', '')}` slot=`{best.get('slotIndex', '')}` "
            f"method=`{best.get('imageOffset', '')}` caller=`{best.get('callerImageOffset', '')}`"
        )
        for route in evidence.get("routes", []):
            lines.append(
                f"  - route: `{route.get('owner', '')}` slot=`{route.get('slotIndex', '')}` "
                f"method=`{route.get('imageOffset', '')}` caller=`{route.get('callerImageOffset', '')}`"
            )
    if action.get("donorTargetValidation"):
        donor = action["donorTargetValidation"]
        lines.append(f"- Donor target validation: `{donor.get('sourcePath', '')}`")
        lines.append(f"  - promotable package patterns: `{donor.get('promotablePackagePatternCount', 0)}`")
        for row in donor.get("promotablePackagePatterns", []):
            lines.append(
                f"  - `{row.get('name', '')}` image=`{row.get('matchImageOffset', '')}` "
                f"vaddr=`{row.get('matchVaddr', '')}` status=`{row.get('status', '')}`"
            )
    if action.get("traceEnv"):
        lines.append("- Trace env:")
        for key, value in action["traceEnv"].items():
            lines.append(f"  - `{key}={value}`")
    if action.get("liveTraceRunbook"):
        runbook = action["liveTraceRunbook"]
        lines.append("- Live trace runbook:")
        lines.append(f"  - source: `{runbook.get('sourcePath', '')}`")
        lines.append(f"  - candidate: `{runbook.get('recommendedCandidate', '')}`")
        if runbook.get("remote"):
            lines.append(f"  - remote: `{runbook.get('remote', '')}`")
        if runbook.get("container"):
            lines.append(f"  - container: `{runbook.get('container', '')}`")
        lines.append(f"  - trace log: `{runbook.get('traceLog', '')}`")
        if runbook.get("coordinatorDryRunCommand"):
            lines.append(f"  - coordinator dry-run: `{runbook.get('coordinatorDryRunCommand', '')}`")
        if runbook.get("coordinatorFreshPreflightCommand"):
            lines.append(f"  - coordinator fresh preflight: `{runbook.get('coordinatorFreshPreflightCommand', '')}`")
        if runbook.get("coordinatorFreshTraceCommand"):
            lines.append(f"  - coordinator fresh trace: `{runbook.get('coordinatorFreshTraceCommand', '')}`")
        if runbook.get("coordinatorCommand"):
            lines.append(f"  - coordinator: `{runbook.get('coordinatorCommand', '')}`")
        if runbook.get("cleanupCommand"):
            lines.append(f"  - cleanup: `{runbook.get('cleanupCommand', '')}`")
        if runbook.get("noDebuggerCheckCommand"):
            lines.append(f"  - no-debugger check: `{runbook.get('noDebuggerCheckCommand', '')}`")
        lines.append(f"  - review verifier: `{runbook.get('reviewBundleVerificationJson', '')}`")
        if runbook.get("localReviewSummaryJson"):
            lines.append(f"  - local review summary: `{runbook.get('localReviewSummaryJson', '')}`")
        if runbook.get("localReviewSummarySchemaVersion"):
            lines.append(f"  - local review summary schema: `{runbook.get('localReviewSummarySchemaVersion', '')}`")
        if runbook.get("localReviewSummaryEmbeddedEvidenceFields"):
            lines.append(
                f"  - local review summary embedded evidence: `{runbook.get('localReviewSummaryEmbeddedEvidenceFields', '')}`"
            )
        if runbook.get("localReviewSummaryRunbookMode"):
            lines.append(f"  - local review summary runbook mode: `{runbook.get('localReviewSummaryRunbookMode', '')}`")
        if runbook.get("localReviewSummaryVerificationCommand"):
            lines.append(f"  - local review summary verifier: `{runbook.get('localReviewSummaryVerificationCommand', '')}`")
        if runbook.get("prearmReadinessJson"):
            lines.append(f"  - prearm readiness: `{runbook.get('prearmReadinessJson', '')}`")
        if runbook.get("prearmReadinessReady") is not None:
            lines.append(f"  - prearm readiness ready: `{str(runbook.get('prearmReadinessReady')).lower()}`")
        if runbook.get("prearmReadinessNextStep"):
            lines.append(f"  - prearm readiness next step: {runbook.get('prearmReadinessNextStep', '')}")
        if runbook.get("prearmReadinessVerificationCommand"):
            lines.append(f"  - prearm readiness verifier: `{runbook.get('prearmReadinessVerificationCommand', '')}`")
        classification = runbook.get("completionAuditNextOriginClassification") or runbook.get("completionAuditNextClientGateClassification") or {}
        if isinstance(classification, dict) and classification:
            lines.append("- Completion audit origin classification:")
            lines.append(f"  - status: `{classification.get('status', '')}`")
            lines.append(f"  - server-side fallback: `{classification.get('serverSideFallbackCandidate', '')}`")
        runtime_root = runbook.get("completionAuditNextRuntimeRootRecoveryPlan") or {}
        if isinstance(runtime_root, dict) and runtime_root:
            lines.append("- Completion audit runtime-root recovery:")
            lines.append(f"  - required log: `{runtime_root.get('requiredLogPath', '')}`")
            lines.append(f"  - missing keys: `{', '.join(runtime_root.get('missingKeys', []) or [])}`")
            if runtime_root.get("preflightCommand"):
                lines.append(f"  - preflight: `{runtime_root.get('preflightCommand', '')}`")
            if runtime_root.get("runCommand"):
                lines.append(f"  - canary: `{runtime_root.get('runCommand', '')}`")
        lines.append(f"  - digest provenance: `{runbook.get('digestProvenanceFields', '')}`")
        lines.append(f"  - command count: `{runbook.get('commandCount', 0)}`")
        operator_window = runbook.get("operatorWindow") or {}
        if isinstance(operator_window, dict) and operator_window:
            lines.append(f"  - max arm seconds: `{operator_window.get('maxArmSeconds', '')}`")
            lines.append(f"  - cleanup required: `{operator_window.get('cleanupRequired', '')}`")
            sequence = operator_window.get("sequence") or []
            if isinstance(sequence, list):
                lines.append(f"  - operator sequence: `{', '.join(str(item) for item in sequence)}`")
    if action.get("routeSlotRecovery"):
        recovery = action["routeSlotRecovery"]
        lines.append("- Route slot recovery:")
        lines.append(f"  - source: `{recovery.get('sourcePath', '')}`")
        lines.append(f"  - route: `{recovery.get('routeAddress', '')}` source=`{recovery.get('routeSourceAddress', '')}`")
        if recovery.get("staticVtableFinding"):
            lines.append(f"  - static vtable finding: `{recovery.get('staticVtableFinding', '')}`")
        if recovery.get("staticVtableImplication"):
            lines.append(f"  - implication: {recovery.get('staticVtableImplication', '')}")
        required = recovery.get("requiredRouteTrace") or {}
        if required:
            lines.append(
                f"  - required trace review: `{required.get('reviewField', '')}` "
                f"route=`{required.get('address', '')}` "
                f"slots=`{', '.join(str(slot) for slot in required.get('slots', []))}` "
                f"registers=`{', '.join(str(register) for register in required.get('registers', []))}`"
            )
        if recovery.get("verificationCommand"):
            lines.append(f"  - verifier: `{recovery.get('verificationCommand', '')}`")
        current = recovery.get("currentRuntimeEvidence") or {}
        if current:
            lines.append(
                "  - current evidence: "
                f"hits=`{current.get('hitCount', 0)}` "
                f"routeHits=`{current.get('routeHitCount', 0)}` "
                f"methodHits=`{current.get('methodHitCount', 0)}` "
                f"routeSlotReady=`{str(current.get('routeSlotRecoveryReady')).lower()}`"
            )
            if current.get("routeSlotRecoveryMissingSlots"):
                lines.append(
                    "  - current missing slots: `"
                    + ", ".join(str(slot) for slot in current.get("routeSlotRecoveryMissingSlots", []))
                    + "`"
                )
            for blocker in current.get("routeSlotRecoveryBlockers", []):
                lines.append(f"  - current blocker: {blocker}")
            for hit in current.get("routeHits", []):
                lines.append(
                    "  - current route hit: "
                    f"hitIndex=`{hit.get('hitIndex', '')}` "
                    f"imageOffset=`{hit.get('imageOffset', '')}` "
                    f"callerImageOffset=`{hit.get('callerImageOffset', '')}` "
                    f"staticSlotMatches=`{hit.get('staticSlotMatchCount', 0)}`"
                )
        artifacts = recovery.get("artifacts") or {}
        for key, value in artifacts.items():
            lines.append(f"  - artifact `{key}`: `{value}`")
    if action.get("outputFiles"):
        lines.append("- Output files:")
        for key, value in action["outputFiles"].items():
            lines.append(f"  - `{key}={value}`")
    if action.get("bundleVerification"):
        verification = action["bundleVerification"]
        lines.append(f"- Bundle verification ready: `{str(verification.get('ready')).lower()}`")
        for blocker in verification.get("blockers", []):
            lines.append(f"  - bundle blocker: {blocker}")
    lines.append("- Commands:")
    for command in action.get("commands", []):
        lines.append(f"  - `{command}`")
    lines.append(f"- Next step: {action['nextStep']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan the next shortest UE4SS package-loading action.")
    parser.add_argument("--promotion-summary-json", default="")
    parser.add_argument("--promotion-json", default="")
    parser.add_argument("--trace-plan-json", default="")
    parser.add_argument("--trace-history-json", default="")
    parser.add_argument("--donor-target-validation-json", default="")
    parser.add_argument("--route-evidence-json", default="")
    parser.add_argument("--route-static-review-json", default="build/server-current-anchor-prep/ue4ss-package-route-129d58a2-static-review.json")
    parser.add_argument("--method-probe-refinement-json", default="")
    parser.add_argument("--live-trace-runbook-json", default="build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json")
    parser.add_argument("--review-bundle", default="")
    parser.add_argument("--wrapper", default=DEFAULT_WRAPPER)
    parser.add_argument("--container", default="dune_server-deep-desert-1")
    parser.add_argument("--process-pattern", default="")
    parser.add_argument("--target-pid", default="")
    parser.add_argument("--trace-host", default="")
    parser.add_argument("--trace-log", default="/tmp/ue4ss-package-runtime-trace-live.log")
    parser.add_argument("--canary-log", default="/tmp/dune-server-probe-loader.log")
    parser.add_argument("--next-canary-json", default="/tmp/ue4ss-package-next-canary.json")
    parser.add_argument("--next-canary-env", default="/tmp/ue4ss-package-next-canary.env")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    promotion_summary = load_promotion_summary(args.promotion_summary_json)
    if args.promotion_json:
        promotion_summary = load_promotion_manifest(args.promotion_json)
    bundle_summary, bundle_trace_plan, bundle_verification = bundle_inputs(args.review_bundle)
    current_runtime_evidence = bundle_runtime_evidence_summary(args.review_bundle)
    if bundle_summary:
        promotion_summary = bundle_summary
    trace_plan = load_trace_plan(args.trace_plan_json)
    trace_history = load_trace_history(args.trace_history_json)
    donor_target_validation = load_donor_target_validation(args.donor_target_validation_json)
    route_evidence = load_route_evidence(args.route_evidence_json)
    route_static_review = load_route_static_review(args.route_static_review_json)
    method_probe_refinement = load_method_probe_refinement(args.method_probe_refinement_json)
    live_trace_runbook = load_live_trace_runbook(args.live_trace_runbook_json)
    if bundle_trace_plan:
        trace_plan = bundle_trace_plan
    action = build_action(
        promotion_summary=promotion_summary,
        trace_plan=trace_plan,
        trace_history=trace_history,
        donor_target_validation=donor_target_validation,
        route_evidence=route_evidence,
        route_static_review=route_static_review,
        current_runtime_evidence=current_runtime_evidence,
        method_probe_refinement=method_probe_refinement,
        live_trace_runbook=live_trace_runbook,
        bundle_verification=bundle_verification,
        wrapper=args.wrapper,
        container=args.container,
        process_pattern=args.process_pattern,
        target_pid=args.target_pid,
        trace_host=args.trace_host,
        trace_log=args.trace_log,
        canary_log=args.canary_log,
        next_canary_json=args.next_canary_json,
        next_canary_env=args.next_canary_env,
    )
    if args.format == "json":
        json.dump(action, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(markdown(action))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
