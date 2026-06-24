#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-promotion-env/v1"
TRACE_EVIDENCE_SCHEMA_VERSION = "dune-ue4ss-package-runtime-trace-evidence/v1"
ABI_REVIEW_SCHEMA_VERSION = "dune-ue4ss-package-abi-review/v1"
PROMOTION_ACCEPTANCE_SCHEMA_VERSION = "dune-ue4ss-package-anchor-promotion-acceptance/v1"
SIGNATURES = {
    "StaticLoadObject": "UObject*(UClass*,UObject*,const TCHAR*,const TCHAR*,uint32,UPackageMap*,bool)",
    "StaticLoadClass": "UClass*(UClass*,UObject*,const TCHAR*,const TCHAR*,uint32,UPackageMap*)",
    "LoadObject": "UObject*(UObject*,const TCHAR*,const TCHAR*,uint32,UPackageMap*,bool)",
    "LoadPackage": "UPackage*(UObject*,const TCHAR*,uint32)",
    "ResolveName": "bool(UObject**,FString&,bool,bool,uint32)",
}


def load_json(path):
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return json.load(handle)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_trace_evidence(path):
    evidence = load_json(path)
    if not isinstance(evidence, dict):
        raise ValueError(f"{path} is not a JSON object")
    schema = evidence.get("schemaVersion")
    if schema != TRACE_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(
            f"{path} has schemaVersion {schema!r}; expected {TRACE_EVIDENCE_SCHEMA_VERSION!r}"
        )
    evidence.setdefault("sourceEvidenceJson", str(path))
    evidence.setdefault("sourceEvidenceJsonSha256", file_sha256(path))
    return evidence


def load_abi_review(path):
    review = load_json(path)
    if not isinstance(review, dict):
        raise ValueError(f"{path} is not a JSON object")
    schema = review.get("schemaVersion")
    if schema != ABI_REVIEW_SCHEMA_VERSION:
        raise ValueError(
            f"{path} has schemaVersion {schema!r}; expected {ABI_REVIEW_SCHEMA_VERSION!r}"
        )
    return review


def sh_quote(value):
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./:=,+-]+", text):
        return text
    return "'" + text.replace("'", "'\"'\"'") + "'"


def present_non_true(value):
    return value is not None and value is not True


def family_for_hit(hit, explicit):
    if explicit:
        return explicit
    seed = hit.get("seed", "")
    if seed in SIGNATURES:
        return seed
    return "StaticLoadObject"


def trace_hits(evidence):
    hits = evidence.get("hits", [])
    if hits is None:
        return []
    return hits if isinstance(hits, list) else []


def evidence_shape_blockers(evidence):
    blockers = []
    if evidence.get("sourcePromotionAcceptanceSchemaVersion") != PROMOTION_ACCEPTANCE_SCHEMA_VERSION:
        blockers.append(
            "runtime trace evidence missing current package promotion acceptance schema provenance"
        )
    armed_count = evidence.get("armedCount")
    if armed_count == 0:
        blockers.append("missing trace armed record; cannot prove runtime trace session")
    elif isinstance(armed_count, int) and not isinstance(armed_count, bool) and armed_count > 1:
        blockers.append("multiple trace armed records; use a fresh single-session trace log")
    if present_non_true(evidence.get("tracePidMatchesRequested")):
        blockers.append("trace log armed PID does not match requested runtime PID")
    hits = evidence.get("hits", [])
    if hits is None:
        hits = []
    if not isinstance(hits, list):
        blockers.append("runtime trace hits must be a JSON array")
        return blockers
    for index, hit in enumerate(hits):
        if not isinstance(hit, dict):
            blockers.append(f"runtime trace hit {index} must be a JSON object")
            continue
        if present_non_true(hit.get("traceLogHasArmed")):
            blockers.append(f"runtime trace hit {index} missing trace armed record; cannot prove runtime trace session")
        if present_non_true(hit.get("tracePidMatchesRequested")):
            blockers.append(f"runtime trace hit {index} trace log armed PID does not match requested runtime PID")
        if hit.get("traceAddressMatchesBase") is not True:
            blockers.append(f"runtime trace hit {index} address does not match image base plus seed imageOffset")
        missing_required_memory = hit.get("missingRequiredMemoryRegisters", [])
        if missing_required_memory is None:
            missing_required_memory = []
        if not isinstance(missing_required_memory, list):
            blockers.append(f"runtime trace hit {index} missingRequiredMemoryRegisters must be a JSON array")
        else:
            invalid_memory_register = False
            for register_index, register in enumerate(missing_required_memory):
                if not isinstance(register, str):
                    blockers.append(
                        f"runtime trace hit {index} missingRequiredMemoryRegisters[{register_index}] must be a string"
                    )
                    invalid_memory_register = True
                    break
            if missing_required_memory and not invalid_memory_register:
                blockers.append(
                    f"runtime trace hit {index} is missing required memory registers: "
                    + ", ".join(missing_required_memory)
                )
        for key in ("backtrace", "disassembly", "stack", "parseWarnings"):
            value = hit.get(key, [])
            if value is not None and not isinstance(value, list):
                blockers.append(f"runtime trace hit {index} {key} must be a JSON array")
        registers = hit.get("registers", {})
        if registers is not None and not isinstance(registers, dict):
            blockers.append(f"runtime trace hit {index} registers must be a JSON object")
        elif isinstance(registers, dict):
            for register, value in registers.items():
                if not isinstance(register, str) or not register:
                    blockers.append(f"runtime trace hit {index} registers contains an invalid register key")
                    continue
                if not isinstance(value, str):
                    blockers.append(f"runtime trace hit {index} registers.{register} must be a string")
        register_memory = hit.get("registerMemory", {})
        if register_memory is not None and not isinstance(register_memory, dict):
            blockers.append(f"runtime trace hit {index} registerMemory must be a JSON object")
        elif isinstance(register_memory, dict):
            for register, rows in register_memory.items():
                if not isinstance(register, str) or not register:
                    blockers.append(f"runtime trace hit {index} registerMemory contains an invalid register key")
                    continue
                if rows is None:
                    continue
                if not isinstance(rows, list):
                    blockers.append(f"runtime trace hit {index} registerMemory.{register} must be a JSON array")
                    continue
                for row_index, row in enumerate(rows):
                    if not isinstance(row, str):
                        blockers.append(f"runtime trace hit {index} registerMemory.{register}[{row_index}] must be a string")
                        break
    recommended = evidence.get("recommendedReview", {})
    if recommended is not None and not isinstance(recommended, dict):
        blockers.append("recommendedReview must be a JSON object")
    concrete_priority = evidence.get("concreteReviewPriority", [])
    if concrete_priority is not None and not isinstance(concrete_priority, list):
        blockers.append("concreteReviewPriority must be a JSON array")
    return blockers


def selected_hit_index(evidence, hit_index=0, signature_family=""):
    hits = trace_hits(evidence)
    if not hits:
        return 0
    def concrete_hit_index(value):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if hit_index == "auto":
        recommended = evidence.get("recommendedReview", {}) or {}
        if not isinstance(recommended, dict):
            recommended = {}
        if (
            signature_family
            and recommended.get("seed") == signature_family
            and concrete_hit_index(recommended.get("hitIndex"))
        ):
            return recommended["hitIndex"]
        concrete_priority = evidence.get("concreteReviewPriority", []) or []
        if not isinstance(concrete_priority, list):
            concrete_priority = []
        for candidate in concrete_priority:
            if (
                isinstance(candidate, dict)
                and candidate.get("seed") == signature_family
                and concrete_hit_index(candidate.get("hitIndex"))
            ):
                return candidate["hitIndex"]
        if signature_family:
            raise ValueError(f"no concrete runtime trace review candidate for signature family {signature_family}")
        for candidate in concrete_priority:
            if isinstance(candidate, dict) and concrete_hit_index(candidate.get("hitIndex")):
                return candidate["hitIndex"]
        return 0
    if isinstance(hit_index, bool):
        raise ValueError("hit index must be auto or a non-negative integer")
    try:
        resolved = int(hit_index)
    except (TypeError, ValueError):
        raise ValueError("hit index must be auto or a non-negative integer") from None
    if resolved < 0:
        raise ValueError("hit index must be auto or a non-negative integer")
    return resolved


def required_review_flags(family):
    flags = ["--reviewed-target-image", "--reviewed-abi"]
    if family == "StaticLoadClass":
        flags.append("--reviewed-class-root")
    else:
        flags.extend(["--reviewed-tchar", "--tchar-unit-bytes <1|2|4>"])
    return flags


def native_invoke_flags():
    return ["--allow-native-invoke", "--final-native-call"]


def review_flag_status(
    family,
    reviewed_target_image=False,
    reviewed_abi=False,
    reviewed_tchar=False,
    reviewed_class_root=False,
    tchar_unit_bytes=0,
):
    status = [
        {
            "flag": "--reviewed-target-image",
            "ready": bool(reviewed_target_image),
            "description": "caller frame reviewed as target-image code",
        },
        {
            "flag": "--reviewed-abi",
            "ready": bool(reviewed_abi),
            "description": "SysV call frame and signature reviewed",
        },
    ]
    if family == "StaticLoadClass":
        status.append(
            {
                "flag": "--reviewed-class-root",
                "ready": bool(reviewed_class_root),
                "description": "root UClass argument reviewed",
            }
        )
    else:
        status.extend(
            [
                {
                    "flag": "--reviewed-tchar",
                    "ready": bool(reviewed_tchar),
                    "description": "TCHAR/FString layout reviewed for package path inputs",
                },
                {
                    "flag": "--tchar-unit-bytes <1|2|4>",
                    "ready": tchar_unit_bytes in (1, 2, 4),
                    "description": "TCHAR code unit width selected",
                },
            ]
        )
    return status


def native_flag_status(allow_native_invoke=False, final_native_call=False):
    return [
        {
            "flag": "--allow-native-invoke",
            "ready": bool(allow_native_invoke),
            "description": "operator allowed guarded native package invocation",
        },
        {
            "flag": "--final-native-call",
            "ready": bool(final_native_call),
            "description": "final native-call risk confirmation supplied",
        },
    ]


def pending_flags(status):
    return [item["flag"] for item in status if not item.get("ready")]


def scalar_provenance_blockers(payload, fields):
    blockers = []
    for field in fields:
        if field not in payload:
            continue
        value = payload.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, (str, int, float, bool)):
            blockers.append(f"{field} provenance must be a scalar")
            continue
        text = str(value)
        if not text.strip() or any(char in text for char in "\r\n\0"):
            blockers.append(f"{field} provenance must be a non-empty single-line value")
    return blockers


def promotion_next_step(has_hits, ready_for_non_invoking, ready_for_native, missing_review, missing_native):
    if not has_hits:
        return "capture package runtime trace hits"
    if not ready_for_non_invoking:
        if missing_review:
            return "complete manual review and rerun export with missing review flags: " + ", ".join(missing_review)
        return "resolve ABI review blockers before package promotion"
    if not ready_for_native:
        if missing_native:
            return "run non-invoking package canary, then enable native invoke with: " + ", ".join(missing_native)
        return "run native package invocation canary"
    return "feed promotion env into next lua-dispatch canary"


def abi_review_summary(abi_review):
    if not abi_review:
        return {
            "provided": False,
            "ready": False,
            "blockers": [],
            "arguments": [],
            "stackArguments": [],
        }
    shape_blockers = []
    raw_blockers = abi_review.get("blockers", [])
    if raw_blockers is None:
        raw_blockers = []
    if not isinstance(raw_blockers, list):
        shape_blockers.append("ABI review blockers must be a JSON array")
        raw_blockers = []
    blockers = []
    for index, blocker in enumerate(raw_blockers):
        if not isinstance(blocker, str):
            shape_blockers.append(f"ABI review blockers[{index}] must be a string")
            continue
        blockers.append(blocker)
    raw_arguments = abi_review.get("arguments", [])
    if raw_arguments is None:
        raw_arguments = []
    if not isinstance(raw_arguments, list):
        shape_blockers.append("ABI review arguments must be a JSON array")
        raw_arguments = []
    raw_stack_arguments = abi_review.get("stackArgumentDetails", [])
    if raw_stack_arguments is None:
        raw_stack_arguments = []
    if not isinstance(raw_stack_arguments, list):
        shape_blockers.append("ABI review stackArgumentDetails must be a JSON array")
        raw_stack_arguments = []
    arguments = []
    for item in raw_arguments:
        if not isinstance(item, dict):
            continue
        memory = item.get("memory", {}) or {}
        if not isinstance(memory, dict):
            shape_blockers.append("ABI review argument memory must be a JSON object")
            memory = {}
        hints = memory.get("hints", {}) or {}
        if not isinstance(hints, dict):
            shape_blockers.append("ABI review argument memory hints must be a JSON object")
            hints = {}
        line_count = memory.get("lineCount", 0) or 0
        if not isinstance(line_count, int) or isinstance(line_count, bool) or line_count < 0:
            shape_blockers.append("ABI review argument memory lineCount must be a non-negative integer")
            line_count = 0
        arguments.append(
            {
                "register": item.get("register", ""),
                "role": item.get("role", ""),
                "capturedValue": item.get("capturedValue", ""),
                "kind": item.get("kind", ""),
                "reviewCategory": item.get("reviewCategory", ""),
                "required": bool(item.get("required", False)),
                "looksSane": bool(item.get("looksSane", False)),
                "memory": {
                    "provided": bool(memory.get("provided", False)),
                    "lineCount": line_count,
                    "hints": dict(hints),
                },
            }
        )
    return {
        "provided": True,
        "sourceEvidence": abi_review.get("sourceEvidence", ""),
        "sourceEvidenceJson": abi_review.get("sourceEvidenceJson", ""),
        "sourceEvidenceJsonSha256": abi_review.get("sourceEvidenceJsonSha256", ""),
        "sourceLogSha256": abi_review.get("sourceLogSha256", ""),
        "sourceLogExists": abi_review.get("sourceLogExists"),
        "sourceTracePlan": abi_review.get("sourceTracePlan", ""),
        "sourceTracePlanSchemaVersion": abi_review.get("sourceTracePlanSchemaVersion", ""),
        "sourcePromotionAcceptanceSchemaVersion": abi_review.get("sourcePromotionAcceptanceSchemaVersion", ""),
        "sourceExternalPlan": abi_review.get("sourceExternalPlan", ""),
        "tracePid": abi_review.get("tracePid"),
        "imageRangeSource": abi_review.get("imageRangeSource", ""),
        "imageBase": abi_review.get("imageBase", ""),
        "imageStart": abi_review.get("imageStart", ""),
        "imageEnd": abi_review.get("imageEnd", ""),
        "imagePath": abi_review.get("imagePath", ""),
        "imagePerms": abi_review.get("imagePerms", ""),
        "hitIndex": abi_review.get("hitIndex"),
        "selectedHitSeed": abi_review.get("selectedHitSeed", ""),
        "signatureFamily": abi_review.get("signatureFamily", ""),
        "callerImageOffset": abi_review.get("callerImageOffset", ""),
        "ripImageOffset": abi_review.get("ripImageOffset", ""),
        "ready": abi_review.get("readyForManualAbiReview") is True and not shape_blockers,
        "blockers": blockers + shape_blockers,
        "arguments": arguments,
        "stackArguments": [
            {
                "slot": item.get("slot", ""),
                "role": item.get("role", ""),
                "capturedValue": item.get("capturedValue", ""),
                "kind": item.get("kind", ""),
                "required": bool(item.get("required", False)),
                "looksSane": bool(item.get("looksSane", False)),
            }
            for item in raw_stack_arguments
            if isinstance(item, dict)
        ],
    }


def abi_review_matches_hit(abi_review, evidence, hit, hit_index, family):
    if not abi_review:
        return False
    if (
        abi_review.get("hitIndex") != hit_index
        or abi_review.get("signatureFamily") != family
        or abi_review.get("sourceEvidence", "") != evidence.get("sourceLog", "")
    ):
        return False
    for key in ("sourceEvidenceJson", "sourceEvidenceJsonSha256", "sourceLogSha256"):
        reviewed = abi_review.get(key, "")
        expected = evidence.get(key, "")
        if expected and reviewed != expected:
            return False
        if reviewed and reviewed != expected:
            return False
    for key in (
        "sourceTracePlan",
        "sourceTracePlanSchemaVersion",
        "sourcePromotionAcceptanceSchemaVersion",
        "sourceExternalPlan",
    ):
        reviewed = abi_review.get(key, "")
        expected = evidence.get(key, "")
        if expected and reviewed != expected:
            return False
        if reviewed and reviewed != expected:
            return False
    if (
        "sourceLogExists" in abi_review
        and "sourceLogExists" in evidence
        and abi_review.get("sourceLogExists") is not evidence.get("sourceLogExists")
    ):
        return False
    for key in (
        "tracePid",
        "imageRangeSource",
        "imageBase",
        "imageStart",
        "imageEnd",
        "imagePath",
        "imagePerms",
    ):
        reviewed = abi_review.get(key)
        if key == "tracePid":
            expected = evidence.get("pid")
        else:
            expected = evidence.get(key)
        if reviewed in (None, "") and expected in (None, ""):
            continue
        if reviewed in (None, "") or expected in (None, ""):
            return False
        if str(reviewed) != str(expected):
            return False
    reviewed_seed = abi_review.get("selectedHitSeed", "")
    hit_seed = hit.get("seed", "")
    if reviewed_seed and hit_seed and reviewed_seed != hit_seed:
        return False
    for key in ("callerImageOffset", "ripImageOffset"):
        reviewed = abi_review.get(key, "")
        expected = hit.get(key, "")
        if expected and not reviewed:
            return False
        if reviewed and reviewed != expected:
            return False
    return True


def build_manifest(
    evidence,
    hit_index=0,
    signature_family="",
    abi_review=None,
    tchar_unit_bytes=0,
    reviewed_target_image=False,
    reviewed_abi=False,
    reviewed_tchar=False,
    reviewed_class_root=False,
    allow_native_invoke=False,
    final_native_call=False,
):
    hits = trace_hits(evidence)
    shape_blockers = evidence_shape_blockers(evidence)
    provenance = {
        "tracePid": evidence.get("pid"),
        "imageRangeSource": evidence.get("imageRangeSource", ""),
        "imageBase": evidence.get("imageBase", ""),
        "imageStart": evidence.get("imageStart", ""),
        "imageEnd": evidence.get("imageEnd", ""),
        "imagePath": evidence.get("imagePath", ""),
        "imagePerms": evidence.get("imagePerms", ""),
    }
    resolved_hit_index = selected_hit_index(evidence, hit_index=hit_index, signature_family=signature_family)
    if not hits:
        family = signature_family or "StaticLoadClass"
        if family not in SIGNATURES:
            raise ValueError(f"unsupported signature family: {family}")
        review_status = review_flag_status(family)
        native_status = native_flag_status()
        missing_review = pending_flags(review_status)
        missing_native = pending_flags(native_status)
        if family == "StaticLoadClass":
            env = {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "false",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "false",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE": "false",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL": "false",
            }
        else:
            env = {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "false",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE": "false",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL": "false",
            }
        return {
            "schemaVersion": SCHEMA_VERSION,
            "promotionAcceptanceSchemaVersion": PROMOTION_ACCEPTANCE_SCHEMA_VERSION,
            "sourceEvidence": evidence.get("sourceLog", ""),
            "sourceEvidenceJson": evidence.get("sourceEvidenceJson", ""),
            "sourceEvidenceJsonSha256": evidence.get("sourceEvidenceJsonSha256", ""),
            "sourceLogSha256": evidence.get("sourceLogSha256", ""),
            "sourceLogExists": evidence.get("sourceLogExists"),
            "sourceTracePlan": evidence.get("sourceTracePlan", ""),
            "sourceTracePlanSchemaVersion": evidence.get("sourceTracePlanSchemaVersion", ""),
            "sourcePromotionAcceptanceSchemaVersion": evidence.get("sourcePromotionAcceptanceSchemaVersion", ""),
            "sourceExternalPlan": evidence.get("sourceExternalPlan", ""),
            **provenance,
            "hitIndex": resolved_hit_index,
            "requestedHitIndex": hit_index,
            "signatureFamily": family,
            "requiredSignature": SIGNATURES[family],
            "targetImageReviewed": False,
            "abiReviewed": False,
            "tcharReviewed": False,
            "classRootReviewed": False,
            "nativeInvokeEnabled": False,
            "finalNativeCallConfirmed": False,
            "readyForNonInvokingCanary": False,
            "readyForNativeInvoke": False,
            "requiredPromotionFlags": required_review_flags(family),
            "nativeInvokePromotionFlags": native_invoke_flags(),
            "reviewFlagStatus": review_status,
            "nativeInvokeFlagStatus": native_status,
            "missingReviewFlags": missing_review,
            "missingNativeInvokeFlags": missing_native,
            "nextStep": promotion_next_step(False, False, False, missing_review, missing_native),
            "blockers": shape_blockers + ["no runtime trace hits available for package promotion"],
            "hit": {},
            "env": env,
        }
    if resolved_hit_index < 0 or resolved_hit_index >= len(hits):
        raise ValueError(f"hit index {resolved_hit_index} out of range for {len(hits)} hits")
    hit = hits[resolved_hit_index]
    if not isinstance(hit, dict):
        family = signature_family or "StaticLoadClass"
        if family not in SIGNATURES:
            raise ValueError(f"unsupported signature family: {family}")
        review_status = review_flag_status(family)
        native_status = native_flag_status()
        missing_review = pending_flags(review_status)
        missing_native = pending_flags(native_status)
        env = {
            "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "",
            "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "false",
            "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "false",
            "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE": "false",
            "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL": "false",
        } if family == "StaticLoadClass" else {
            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "",
            "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "false",
            "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE": "false",
            "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL": "false",
        }
        return {
            "schemaVersion": SCHEMA_VERSION,
            "promotionAcceptanceSchemaVersion": PROMOTION_ACCEPTANCE_SCHEMA_VERSION,
            "sourceEvidence": evidence.get("sourceLog", ""),
            "sourceEvidenceJson": evidence.get("sourceEvidenceJson", ""),
            "sourceEvidenceJsonSha256": evidence.get("sourceEvidenceJsonSha256", ""),
            "sourceLogSha256": evidence.get("sourceLogSha256", ""),
            "sourceLogExists": evidence.get("sourceLogExists"),
            "sourceTracePlan": evidence.get("sourceTracePlan", ""),
            "sourceTracePlanSchemaVersion": evidence.get("sourceTracePlanSchemaVersion", ""),
            "sourcePromotionAcceptanceSchemaVersion": evidence.get("sourcePromotionAcceptanceSchemaVersion", ""),
            "sourceExternalPlan": evidence.get("sourceExternalPlan", ""),
            **provenance,
            "hitIndex": resolved_hit_index,
            "requestedHitIndex": hit_index,
            "signatureFamily": family,
            "requiredSignature": SIGNATURES[family],
            "targetImageReviewed": False,
            "abiReviewed": False,
            "tcharReviewed": False,
            "classRootReviewed": False,
            "nativeInvokeEnabled": False,
            "finalNativeCallConfirmed": False,
            "readyForNonInvokingCanary": False,
            "readyForNativeInvoke": False,
            "requiredPromotionFlags": required_review_flags(family),
            "nativeInvokePromotionFlags": native_invoke_flags(),
            "reviewFlagStatus": review_status,
            "nativeInvokeFlagStatus": native_status,
            "missingReviewFlags": missing_review,
            "missingNativeInvokeFlags": missing_native,
            "nextStep": promotion_next_step(False, False, False, missing_review, missing_native),
            "blockers": shape_blockers + ["selected runtime trace hit must be a JSON object"],
            "hit": {},
            "env": env,
        }
    family = family_for_hit(hit, signature_family)
    if family not in SIGNATURES:
        raise ValueError(f"unsupported signature family: {family}")
    review_matches = True
    review_ready = False
    review_summary = abi_review_summary(abi_review)
    if abi_review:
        review_matches = abi_review_matches_hit(abi_review, evidence, hit, resolved_hit_index, family)
        review_ready = review_matches and review_summary.get("ready") is True
    target_image = reviewed_target_image and hit.get("targetImageCaller") is True
    abi_confirmed = target_image and reviewed_abi and (review_ready if abi_review else True)
    tchar_confirmed = reviewed_tchar and tchar_unit_bytes in (1, 2, 4)
    class_root_confirmed = family == "StaticLoadClass" and reviewed_class_root
    blockers = list(shape_blockers)
    blockers.extend(
        scalar_provenance_blockers(
            evidence,
            (
            "sourceLog",
            "sourceLogSha256",
            "sourceEvidenceJson",
            "sourceEvidenceJsonSha256",
            "sourceTracePlan",
                "sourceTracePlanSchemaVersion",
                "sourcePromotionAcceptanceSchemaVersion",
                "sourceExternalPlan",
                "pid",
                "imageRangeSource",
                "imageBase",
                "imageStart",
                "imageEnd",
                "imagePath",
                "imagePerms",
            ),
        )
    )
    blockers.extend(
        scalar_provenance_blockers(
            hit,
            ("seed", "callerImageOffset", "ripImageOffset"),
        )
    )
    for blocker in review_summary.get("blockers", []) or []:
        if blocker not in blockers:
            blockers.append(blocker)
    if not evidence.get("sourceLog", ""):
        blockers.append("missing runtime trace sourceLog provenance")
    if "sourceLogExists" not in evidence:
        blockers.append("missing runtime trace sourceLogExists provenance")
    elif evidence.get("sourceLogExists") is not True:
        blockers.append("runtime trace sourceLog does not exist")
    if evidence.get("tracePidMatchesRequested") is not True:
        blockers.append("missing runtime trace PID match provenance")
    hit_seed = hit.get("seed", "")
    if not hit_seed:
        blockers.append("missing trace hit seed provenance")
    if hit_seed and hit_seed != family:
        blockers.append(f"selected trace hit seed {hit_seed} does not match signature family {family}")
    if not hit.get("callerImageOffset"):
        blockers.append("missing callerImageOffset call-frame provenance")
    if not hit.get("ripImageOffset"):
        blockers.append("missing ripImageOffset call-frame provenance")
    if hit.get("tracePidMatchesRequested") is not True:
        blockers.append("selected runtime trace hit is missing PID match provenance")
    if hit.get("traceAddressMatchesBase") is not True:
        blockers.append("selected runtime trace hit address does not match image base plus seed imageOffset")
    if not target_image:
        blockers.append("reviewed target-image caller evidence is required")
    if abi_review and not review_matches:
        blockers.append("ABI review report does not match selected hit/signature/evidence")
    if abi_review and not review_ready:
        blockers.append("ABI review report is not ready for manual ABI review")
    if reviewed_abi and not abi_review:
        blockers.append("reviewed ABI promotion should include --abi-review-json")
    if not abi_confirmed:
        blockers.append("reviewed ABI evidence is required")
    if family in ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName") and not tchar_confirmed:
        blockers.append("reviewed TCHAR layout evidence is required for LoadAsset package promotion")
    if family == "StaticLoadClass" and not class_root_confirmed:
        blockers.append("reviewed root UClass evidence is required for LoadClass package promotion")
    if allow_native_invoke and not final_native_call:
        blockers.append("native invoke requested but final native-call confirmation is absent")
    ready_for_non_invoking = abi_confirmed and (tchar_confirmed or class_root_confirmed) and not blockers
    ready_for_native = ready_for_non_invoking and allow_native_invoke and final_native_call
    review_status = review_flag_status(
        family,
        reviewed_target_image=target_image,
        reviewed_abi=abi_confirmed,
        reviewed_tchar=tchar_confirmed,
        reviewed_class_root=class_root_confirmed,
        tchar_unit_bytes=tchar_unit_bytes,
    )
    native_status = native_flag_status(
        allow_native_invoke=allow_native_invoke,
        final_native_call=final_native_call,
    )
    missing_review = pending_flags(review_status)
    missing_native = pending_flags(native_status)
    asset_family = family in ("StaticLoadObject", "LoadObject", "LoadPackage", "ResolveName")
    class_family = family == "StaticLoadClass"
    caller_label = hit.get("callerImageOffset") or hit.get("caller", {}).get("ip", "")
    rip_label = hit.get("ripImageOffset") or hit.get("rip", {}).get("ip", "")
    evidence_markers = []
    if hit_seed:
        evidence_markers.append(f"seed={hit_seed}")
    evidence_markers.extend([f"caller={caller_label}", f"rip={rip_label}"])
    if evidence.get("pid") not in (None, ""):
        evidence_markers.append(f"pid={evidence.get('pid')}")
    if evidence.get("sourceEvidenceJsonSha256"):
        evidence_markers.append(f"evidenceJsonSha256={evidence.get('sourceEvidenceJsonSha256')}")
    if evidence.get("sourceLogSha256"):
        evidence_markers.append(f"sourceLogSha256={evidence.get('sourceLogSha256')}")
    evidence_label = f"runtime-trace:{family}:" + " ".join(evidence_markers)
    env = {}
    if asset_family:
        env.update(
            {
                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": evidence_label,
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true" if ready_for_non_invoking else "false",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_ASSET_PACKAGE_INVOKE": "true" if ready_for_native else "false",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_NATIVE_CALL": "true" if ready_for_native else "false",
            }
        )
    if class_family:
        env.update(
            {
                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": evidence_label,
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true" if ready_for_non_invoking else "false",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ROOT_CLASS": "true" if ready_for_non_invoking and class_root_confirmed else "false",
                "DUNE_PROBE_LOADER_ALLOW_LOAD_CLASS_PACKAGE_INVOKE": "true" if ready_for_native else "false",
                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_NATIVE_CALL": "true" if ready_for_native else "false",
            }
        )
    if asset_family and tchar_unit_bytes:
        env["DUNE_PROBE_LOADER_TCHAR_UNIT_BYTES"] = str(tchar_unit_bytes)
        env["DUNE_PROBE_LOADER_TCHAR_EVIDENCE"] = evidence_label
        env["DUNE_PROBE_LOADER_CONFIRM_TCHAR_LAYOUT"] = "true" if ready_for_non_invoking and tchar_confirmed else "false"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "promotionAcceptanceSchemaVersion": PROMOTION_ACCEPTANCE_SCHEMA_VERSION,
        "sourceEvidence": evidence.get("sourceLog", ""),
        "sourceEvidenceJson": evidence.get("sourceEvidenceJson", ""),
        "sourceEvidenceJsonSha256": evidence.get("sourceEvidenceJsonSha256", ""),
        "sourceLogSha256": evidence.get("sourceLogSha256", ""),
        "sourceLogExists": evidence.get("sourceLogExists"),
        "sourceTracePlan": evidence.get("sourceTracePlan", ""),
        "sourceTracePlanSchemaVersion": evidence.get("sourceTracePlanSchemaVersion", ""),
        "sourcePromotionAcceptanceSchemaVersion": evidence.get("sourcePromotionAcceptanceSchemaVersion", ""),
        "sourceExternalPlan": evidence.get("sourceExternalPlan", ""),
        **provenance,
        "hitIndex": resolved_hit_index,
        "requestedHitIndex": hit_index,
        "selectedHitSeed": hit_seed,
        "signatureFamily": family,
        "requiredSignature": SIGNATURES[family],
        "callerImageOffset": hit.get("callerImageOffset", ""),
        "ripImageOffset": hit.get("ripImageOffset", ""),
        "targetImageReviewed": target_image,
        "abiReviewSource": abi_review.get("sourceEvidence", "") if abi_review else "",
        "abiReviewReady": review_ready,
        "abiReview": review_summary,
        "abiReviewed": abi_confirmed,
        "tcharReviewed": tchar_confirmed,
        "classRootReviewed": class_root_confirmed,
        "nativeInvokeEnabled": allow_native_invoke,
        "finalNativeCallConfirmed": final_native_call,
        "readyForNonInvokingCanary": ready_for_non_invoking,
        "readyForNativeInvoke": ready_for_native,
        "requiredPromotionFlags": required_review_flags(family),
        "nativeInvokePromotionFlags": native_invoke_flags(),
        "reviewFlagStatus": review_status,
        "nativeInvokeFlagStatus": native_status,
        "missingReviewFlags": missing_review,
        "missingNativeInvokeFlags": missing_native,
        "nextStep": promotion_next_step(True, ready_for_non_invoking, ready_for_native, missing_review, missing_native),
        "blockers": blockers,
        "hit": hit,
        "env": env,
    }


def render_env(manifest):
    lines = [
        "# UE4SS package promotion env",
        f"# signatureFamily={manifest['signatureFamily']}",
        f"# requiredSignature={manifest['requiredSignature']}",
        f"# sourceEvidence={manifest['sourceEvidence']}",
        f"# sourceEvidenceJson={manifest.get('sourceEvidenceJson', '')}",
        f"# sourceEvidenceJsonSha256={manifest.get('sourceEvidenceJsonSha256', '')}",
        f"# sourceLogSha256={manifest.get('sourceLogSha256', '')}",
        f"# sourceLogExists={manifest.get('sourceLogExists', '')}",
        f"# sourceTracePlan={manifest.get('sourceTracePlan', '')}",
        f"# sourcePromotionAcceptanceSchemaVersion={manifest.get('sourcePromotionAcceptanceSchemaVersion', '')}",
        f"# sourceExternalPlan={manifest.get('sourceExternalPlan', '')}",
        f"# tracePid={manifest.get('tracePid', '')}",
        f"# imageRangeSource={manifest.get('imageRangeSource', '')}",
        f"# imageBase={manifest.get('imageBase', '')}",
        f"# imageStart={manifest.get('imageStart', '')}",
        f"# imageEnd={manifest.get('imageEnd', '')}",
        f"# imagePath={manifest.get('imagePath', '')}",
        f"# imagePerms={manifest.get('imagePerms', '')}",
        f"# hitIndex={manifest.get('hitIndex', '')}",
        f"# selectedHitSeed={manifest.get('selectedHitSeed', '')}",
        f"# callerImageOffset={manifest.get('callerImageOffset', '')}",
        f"# ripImageOffset={manifest.get('ripImageOffset', '')}",
    ]
    for blocker in manifest["blockers"]:
        lines.append(f"# blocker: {blocker}")
    for key in sorted(manifest["env"]):
        lines.append(f"export {key}={sh_quote(manifest['env'][key])}")
    return "\n".join(lines) + "\n"


def render_markdown(manifest):
    lines = ["# UE4SS Package Promotion Env", ""]
    lines.append(f"- Signature family: `{manifest['signatureFamily']}`")
    lines.append(f"- Required signature: `{manifest['requiredSignature']}`")
    if "sourceLogExists" in manifest:
        lines.append(f"- Source log exists: `{str(manifest.get('sourceLogExists')).lower()}`")
    if manifest.get("tracePid") not in (None, ""):
        lines.append(f"- Trace PID: `{manifest.get('tracePid')}`")
    if manifest.get("imageRangeSource"):
        lines.append(f"- Image range source: `{manifest.get('imageRangeSource')}`")
    if manifest.get("imageStart") or manifest.get("imageEnd") or manifest.get("imageBase"):
        lines.append(
            f"- Image range: `{manifest.get('imageStart', '')}-{manifest.get('imageEnd', '')}` "
            f"base=`{manifest.get('imageBase', '')}`"
        )
    if manifest.get("imagePath"):
        lines.append(f"- Image path: `{manifest.get('imagePath')}`")
    if manifest.get("imagePerms"):
        lines.append(f"- Image perms: `{manifest.get('imagePerms')}`")
    lines.append(f"- Ready for non-invoking canary: `{str(manifest['readyForNonInvokingCanary']).lower()}`")
    lines.append(f"- Ready for native invoke: `{str(manifest['readyForNativeInvoke']).lower()}`")
    lines.append(f"- Next step: {manifest.get('nextStep', '')}")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    if manifest["blockers"]:
        for blocker in manifest["blockers"]:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")
    abi_review = manifest.get("abiReview", {})
    if abi_review.get("provided"):
        lines.append("")
        lines.append("## ABI Review")
        lines.append("")
        lines.append(f"- Ready: `{str(abi_review.get('ready', False)).lower()}`")
        review_blockers = abi_review.get("blockers", []) or []
        if review_blockers:
            for blocker in review_blockers:
                lines.append(f"- blocker: {blocker}")
    lines.append("")
    lines.append("## Review Flags")
    lines.append("")
    for item in manifest.get("reviewFlagStatus", []):
        lines.append(
            f"- `{item['flag']}` ready=`{str(item.get('ready', False)).lower()}` - {item.get('description', '')}"
        )
    if not manifest.get("reviewFlagStatus"):
        for flag in manifest["requiredPromotionFlags"]:
            lines.append(f"- `{flag}`")
    lines.append("")
    lines.append("## Native Invoke Flags")
    lines.append("")
    for item in manifest.get("nativeInvokeFlagStatus", []):
        lines.append(
            f"- `{item['flag']}` ready=`{str(item.get('ready', False)).lower()}` - {item.get('description', '')}"
        )
    if not manifest.get("nativeInvokeFlagStatus"):
        for flag in manifest["nativeInvokePromotionFlags"]:
            lines.append(f"- `{flag}`")
    lines.append("")
    lines.append("## Env")
    lines.append("")
    lines.append("```bash")
    lines.append(render_env(manifest).rstrip())
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export reviewed package runtime trace evidence as guarded loader env.")
    parser.add_argument("evidence_json")
    parser.add_argument("--abi-review-json", default="")
    parser.add_argument("--hit-index", default="0")
    parser.add_argument("--signature-family", choices=sorted(SIGNATURES), default="")
    parser.add_argument("--tchar-unit-bytes", type=int, default=0)
    parser.add_argument("--reviewed-target-image", action="store_true")
    parser.add_argument("--reviewed-abi", action="store_true")
    parser.add_argument("--reviewed-tchar", action="store_true")
    parser.add_argument("--reviewed-class-root", action="store_true")
    parser.add_argument("--allow-native-invoke", action="store_true")
    parser.add_argument("--final-native-call", action="store_true")
    parser.add_argument("--format", choices=("env", "json", "markdown"), default="env")
    args = parser.parse_args(argv)
    manifest = build_manifest(
        load_trace_evidence(args.evidence_json),
        hit_index="auto" if args.hit_index == "auto" else int(args.hit_index),
        signature_family=args.signature_family,
        abi_review=load_abi_review(args.abi_review_json) if args.abi_review_json else None,
        tchar_unit_bytes=args.tchar_unit_bytes,
        reviewed_target_image=args.reviewed_target_image,
        reviewed_abi=args.reviewed_abi,
        reviewed_tchar=args.reviewed_tchar,
        reviewed_class_root=args.reviewed_class_root,
        allow_native_invoke=args.allow_native_invoke,
        final_native_call=args.final_native_call,
    )
    if args.format == "json":
        json.dump(manifest, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "markdown":
        sys.stdout.write(render_markdown(manifest))
    else:
        sys.stdout.write(render_env(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
