#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SCHEMA_VERSION = "dune-ue4ss-package-server-replay-plan/v1"
LIVE_SUMMARY_SCHEMA_VERSION = "dune-ue4ss-package-live-stimulus-review-summary/v1"
PROMOTION_SCHEMA_VERSION = "dune-ue4ss-package-promotion-env/v1"
REPLAY_STRATEGY = "server-side-client-call-emulation"


def load_json(path):
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.is_file():
        return {}
    try:
        data = json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def origin_summary(live_summary):
    origin = live_summary.get("originClassification", {})
    if not isinstance(origin, dict):
        origin = {}
    return {
        "source": origin.get("source", ""),
        "status": origin.get("status", "missing" if live_summary else ""),
        "probeCandidate": origin.get("probeCandidate", ""),
        "serverSideFallbackCandidate": origin.get("serverSideFallbackCandidate", ""),
        "requiresServerSideReplay": origin.get("requiresServerSideReplay"),
        "blockers": origin.get("blockers", []) if isinstance(origin.get("blockers", []), list) else [],
        "decision": origin.get("decision", ""),
    }


def promotion_summary(promotion):
    return {
        "signatureFamily": promotion.get("signatureFamily", ""),
        "sourceEvidence": promotion.get("sourceEvidence", ""),
        "sourceEvidenceJson": promotion.get("sourceEvidenceJson", ""),
        "sourceEvidenceJsonSha256": promotion.get("sourceEvidenceJsonSha256", ""),
        "sourceLogSha256": promotion.get("sourceLogSha256", ""),
        "hitIndex": promotion.get("hitIndex"),
        "callerImageOffset": promotion.get("callerImageOffset", ""),
        "ripImageOffset": promotion.get("ripImageOffset", ""),
        "readyForNonInvokingCanary": promotion.get("readyForNonInvokingCanary"),
        "readyForNativeInvoke": promotion.get("readyForNativeInvoke"),
        "missingReviewFlags": promotion.get("missingReviewFlags", [])
        if isinstance(promotion.get("missingReviewFlags", []), list)
        else [],
        "missingNativeInvokeFlags": promotion.get("missingNativeInvokeFlags", [])
        if isinstance(promotion.get("missingNativeInvokeFlags", []), list)
        else [],
        "blockers": promotion.get("blockers", []) if isinstance(promotion.get("blockers", []), list) else [],
        "nextStep": promotion.get("nextStep", ""),
    }


def build_plan(live_summary, promotion, promotion_env_path=""):
    origin = origin_summary(live_summary)
    promo = promotion_summary(promotion)
    blockers = []
    if live_summary and live_summary.get("schemaVersion") != LIVE_SUMMARY_SCHEMA_VERSION:
        blockers.append("live stimulus summary schema is not recognized")
    if promotion and promotion.get("schemaVersion") != PROMOTION_SCHEMA_VERSION:
        blockers.append("package promotion manifest schema is not recognized")
    if not live_summary:
        blockers.append("live stimulus summary is missing")
    if not promotion:
        blockers.append("package promotion manifest is missing")
    status = origin.get("status", "")
    if status == "missing":
        blockers.append("package-load origin classification is missing")
    elif status == "inconclusive":
        blockers.append("package-load origin classification is inconclusive")
    elif status == "server-originated":
        blockers.append("package-load evidence is server-originated; fix/promote the reached server-side package path instead of replaying a client-originated call")
    elif status == "client-originated-pending-server-replay":
        if origin.get("requiresServerSideReplay") is not True:
            blockers.append("client-originated classification must require server-side replay")
    elif status == "server-side-replay-proven":
        if origin.get("requiresServerSideReplay") not in (False, None):
            blockers.append("server-side replay proven status must not still require replay")
    elif status not in ("", "not-required"):
        blockers.append(f"unsupported package-load origin classification status: {status}")

    for blocker in origin.get("blockers", []) or []:
        if status in ("missing", "inconclusive") and isinstance(blocker, str) and blocker:
            blockers.append(f"origin classification: {blocker}")
    for blocker in promo.get("blockers", []) or []:
        if isinstance(blocker, str) and blocker:
            blockers.append(f"promotion manifest: {blocker}")

    ready_non_invoking = (
        status == "client-originated-pending-server-replay"
        and origin.get("requiresServerSideReplay") is True
        and promotion.get("readyForNonInvokingCanary") is True
        and not promo.get("blockers")
        and not blockers
    )
    ready_native = ready_non_invoking and promotion.get("readyForNativeInvoke") is True
    if ready_native:
        action = "run-final-guarded-server-side-native-invoke"
    elif ready_non_invoking:
        action = "run-non-invoking-server-side-replay-canary"
    else:
        action = "collect-server-side-replay-evidence"

    commands = []
    if action == "run-non-invoking-server-side-replay-canary" and promotion_env_path:
        commands = [
            f"cat {promotion_env_path}",
            f"DUNE_LINUX_SERVER_CANARY_EXTRA_ENV={promotion_env_path} DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=true scripts/canary-linux-server-loader.sh .env",
            f"DUNE_LINUX_SERVER_CANARY_EXTRA_ENV={promotion_env_path} DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=false scripts/canary-linux-server-loader.sh .env",
        ]
    elif action == "run-final-guarded-server-side-native-invoke" and promotion_env_path:
        commands = [
            f"cat {promotion_env_path}",
            f"DUNE_LINUX_SERVER_CANARY_EXTRA_ENV={promotion_env_path} DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=true scripts/canary-linux-server-loader.sh .env",
            f"DUNE_LINUX_SERVER_CANARY_EXTRA_ENV={promotion_env_path} DUNE_LINUX_SERVER_CANARY_PREFLIGHT_ONLY=false scripts/canary-linux-server-loader.sh .env",
        ]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "action": action,
        "readyForNonInvokingReplayCanary": ready_non_invoking,
        "readyForNativeReplayInvoke": ready_native,
        "replayStrategy": REPLAY_STRATEGY,
        "originClassification": origin,
        "promotion": promo,
        "promotionEnvPath": promotion_env_path,
        "blockers": blockers,
        "commands": commands,
        "nextStep": next_step(action, blockers, promo),
    }


def next_step(action, blockers, promo):
    if blockers:
        if promo.get("missingReviewFlags"):
            return "complete ABI/promotion review flags: " + ", ".join(promo["missingReviewFlags"])
        return "resolve server-side replay blockers"
    if action == "run-non-invoking-server-side-replay-canary":
        return "run guarded non-invoking server-side replay canary, then require explicit native invoke flags"
    if action == "run-final-guarded-server-side-native-invoke":
        return "run final guarded native server-side replay canary"
    return "capture live package hit and export package promotion manifest"


def render_markdown(plan):
    lines = ["# UE4SS Package Server-Side Replay Plan", ""]
    lines.append(f"- Action: `{plan['action']}`")
    lines.append(f"- Ready for non-invoking replay canary: `{str(plan['readyForNonInvokingReplayCanary']).lower()}`")
    lines.append(f"- Ready for native replay invoke: `{str(plan['readyForNativeReplayInvoke']).lower()}`")
    lines.append(f"- Replay strategy: `{plan.get('replayStrategy', '')}`")
    origin = plan.get("originClassification", {})
    lines.append(f"- Origin classification: `{origin.get('status', '')}`")
    lines.append(f"- Server-side fallback: `{origin.get('serverSideFallbackCandidate', '')}`")
    promotion = plan.get("promotion", {})
    lines.append(f"- Signature family: `{promotion.get('signatureFamily', '')}`")
    lines.append(f"- Source evidence: `{promotion.get('sourceEvidence', '')}`")
    lines.append("")
    lines.append("## Blockers")
    lines.append("")
    if plan.get("blockers"):
        for blocker in plan["blockers"]:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")
    if plan.get("commands"):
        lines.extend(["", "## Commands", "", "```bash"])
        lines.extend(plan["commands"])
        lines.append("```")
    lines.append("")
    lines.append(f"Next step: {plan['nextStep']}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan server-side replay/spoofing for client-originated package-load evidence.")
    parser.add_argument("--live-summary-json", default="build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json")
    parser.add_argument("--promotion-json", default="build/server-current-anchor-prep/ue4ss-package-promotion-env.json")
    parser.add_argument("--promotion-env", default="build/server-current-anchor-prep/ue4ss-package-promotion-env.env")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    plan = build_plan(load_json(args.live_summary_json), load_json(args.promotion_json), args.promotion_env)
    if args.format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(render_markdown(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
