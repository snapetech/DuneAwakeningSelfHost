#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "dune-callfunction-hook-validation-candidates/v1"
DEFAULT_ENV_PREFIX = "DUNE_PROBE_LOADER"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def candidate_offset(row):
    return row.get("function") or row.get("imageOffset") or row.get("fileOffset") or ""


def candidate_score(row):
    narrowing = row.get("narrowing") or {}
    return int(narrowing.get("score") or row.get("score") or 0)


def build_env(prefix, image_offset, *, stage):
    env = {
        f"{prefix}_UE_CALL_FUNCTION_HOOK_PROBE": "true",
        f"{prefix}_UE_CALL_FUNCTION_HOOK_IMAGE_OFFSET": image_offset,
        f"{prefix}_UE_CALL_FUNCTION_IMAGE_OFFSET": image_offset,
        f"{prefix}_UE_CALL_FUNCTION_HOOK_SELF_TEST_TARGET": "false",
        f"{prefix}_UE_CALL_FUNCTION_HOOK_INSTALL": "true",
        f"{prefix}_UE_CALL_FUNCTION_HOOK_CALL_SELF_TEST": "false",
        f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE": "false",
        f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL": "false",
    }
    if stage in {"live-hook", "active-validation"}:
        env.update(
            {
                f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK": "true",
                f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_IMAGE_OFFSET": image_offset,
                f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_SELF_TEST_TARGET": "false",
                f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_CALL_SELF_TEST": "false",
                f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_LOG_CALLS": "true",
                f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK_CALL_LOG_LIMIT": "16",
            }
        )
    else:
        env[f"{prefix}_UE_CALL_FUNCTION_LIVE_HOOK"] = "false"
    return env


def shell_env(env):
    return " ".join(f"{key}={value}" for key, value in env.items())


def build_candidates(shape_summary, *, prefix=DEFAULT_ENV_PREFIX, limit=16, stage="hook-probe"):
    rows = shape_summary.get("narrowedCandidates") or shape_summary.get("candidates") or []
    candidates = []
    for rank, row in enumerate(rows[:limit], 1):
        offset = candidate_offset(row)
        narrowing = row.get("narrowing") or {}
        env = build_env(prefix, offset, stage=stage)
        candidates.append(
            {
                "rank": rank,
                "imageOffset": offset,
                "rawScore": row.get("score"),
                "narrowScore": narrowing.get("score"),
                "signatureSha256": (row.get("signature") or {}).get("sha256", ""),
                "signatureRepeatCount": narrowing.get("signatureRepeatCount"),
                "indirectPatternRepeatCount": narrowing.get("indirectPatternRepeatCount"),
                "directTargetPatternRepeatCount": narrowing.get("directTargetPatternRepeatCount"),
                "uniqueDirectTargetCount": narrowing.get("uniqueDirectTargetCount"),
                "repeatedVtableShape": narrowing.get("repeatedVtableShape"),
                "promotable": False,
                "promotionBlocker": "requires guarded hook probe and target-entry active validation",
                "validationStage": stage,
                "env": env,
                "shellEnv": shell_env(env),
                "requiredPassEvents": [
                    "event=ue-call-function-hook status=passed selfTestTarget=false callSelfTest=false",
                ],
                "activeValidationPending": {
                    "reason": "runtime object address and reviewed CallFunction command are required before native active validation",
                    "requiredEnv": [
                        f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE=true",
                        f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_ALLOW_NATIVE_CALL=true",
                        f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_OBJECT_ADDRESS=0x...",
                        f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_COMMAND=...",
                        f"{prefix}_UE_CALL_FUNCTION_ACTIVE_VALIDATE_THROUGH_TARGET=true",
                    ],
                    "requiredPassEvent": "event=ue-call-function-active-validate status=invoked targetEntry=true",
                },
            }
        )
    candidates.sort(key=lambda row: (row["rank"], -candidate_score(row)))
    return candidates


def summarize(shape_path, *, prefix=DEFAULT_ENV_PREFIX, limit=16, stage="hook-probe"):
    shape_summary = load_json(shape_path)
    candidates = build_candidates(shape_summary, prefix=prefix, limit=limit, stage=stage)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceShapeSummary": str(shape_path),
        "sourceCandidateCount": shape_summary.get("candidateCount", 0),
        "sourceNarrowedCandidateCount": len(shape_summary.get("narrowedCandidates") or []),
        "candidateCount": len(candidates),
        "envPrefix": prefix,
        "validationStage": stage,
        "nativeCallAllowed": False,
        "reviewRequired": True,
        "promotable": False,
        "promotionBlockers": [
            "static target candidates require guarded hook probe",
            "full promotion requires target-entry active validation with reviewed runtime object and command",
        ],
        "candidates": candidates,
    }


def markdown(report):
    lines = [
        "# CallFunction Hook Validation Candidates",
        "",
        f"- Schema: `{report['schemaVersion']}`",
        f"- Source candidates: `{report['sourceCandidateCount']}`",
        f"- Narrowed source candidates: `{report['sourceNarrowedCandidateCount']}`",
        f"- Exported candidates: `{report['candidateCount']}`",
        f"- Stage: `{report['validationStage']}`",
        f"- Native call allowed: `{str(report['nativeCallAllowed']).lower()}`",
        f"- Promotable: `{str(report['promotable']).lower()}`",
        "",
        "## Promotion Blockers",
        "",
    ]
    for blocker in report["promotionBlockers"]:
        lines.append(f"- {blocker}")
    lines.extend(
        [
            "",
            "| Rank | Image Offset | Narrow Score | Raw Score | Repeats | Env |",
            "| ---: | --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in report["candidates"]:
        repeats = (
            f"sig={row['signatureRepeatCount']} "
            f"indirect={row['indirectPatternRepeatCount']} "
            f"direct={row['directTargetPatternRepeatCount']}"
        )
        lines.append(
            f"| {row['rank']} | `{row['imageOffset']}` | {row['narrowScore']} | {row['rawScore']} | "
            f"`{repeats}` | `{row['shellEnv']}` |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Export guarded CallFunction hook-probe env candidates from narrowed static shape evidence."
    )
    parser.add_argument("shape_candidates_json", type=Path)
    parser.add_argument("--env-prefix", default=DEFAULT_ENV_PREFIX)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--stage", choices=("hook-probe", "live-hook", "active-validation"), default="hook-probe")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    report = summarize(
        args.shape_candidates_json,
        prefix=args.env_prefix,
        limit=args.limit,
        stage=args.stage,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(markdown(report), end="")


if __name__ == "__main__":
    main()
