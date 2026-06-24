#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import shlex
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-ue4ss-package-review-bundle.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_package_review_bundle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, dict):
        path.write_text(json.dumps(content, sort_keys=True), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote_trace_command(action, trace_log="/tmp/trace.log"):
    return (
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST=kspls0 "
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false "
        f"scripts/ue4ss-package-remote-trace.sh {action} "
        f"kspls0 dune_server-deep-desert-1 {trace_log}"
    )


NO_DEBUGGER_CHECK_COMMAND = (
    'ssh kspls0 \'ps -eo pid,stat,comm,args | grep -E "gdb|ue4ss-package-runtime-trace" '
    "| grep -v grep || true; docker top dune_server-deep-desert-1 -eo pid,stat,comm "
    "2>/dev/null | awk '\"'\"'NR==1 || /DuneSandboxServ/'\"'\"''"
)
ROUTE_SLOT_TRACE_REQUIREMENT = {
    "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
    "routeAddress": "0x129d58a2",
    "reviewField": "routeVtableStaticSlotMatches",
    "requiredSlots": ["0x3a0", "0x3d8"],
    "requiredRegisters": ["rbx", "r14"],
}


def route_gdb(route_address="0x129d58a2", registers=None):
    registers = registers or ["rbx", "r14"]
    register_prints = " ".join(f"{register}=%p" for register in registers)
    register_args = ", ".join(f"${register}" for register in registers)
    lines = [
        "set pagination off",
        "printf \"UE4SS_PACKAGE_ROUTE_TRACE armed pid=%d base=0x%lx build_id=%s routes=%d\\n\", 123, 0x100000, \"abc123\", 1",
        f"break *0x12ad58a2",
        "commands",
        " silent",
        (
            f' printf "UE4SS_PACKAGE_ROUTE_TRACE_HIT imageOffset={route_address} '
            'addr=0x12ad58a2 rip=%p rdi=%p rsi=%p rdx=%p rcx=%p r8=%p r9=%p '
            f'{register_prints} rsp=%p rbp=%p\\n", '
            f"$rip, $rdi, $rsi, $rdx, $rcx, $r8, $r9, {register_args}, $rsp, $rbp"
        ),
    ]
    for register in registers:
        lines.extend(
            [
                f' printf "UE4SS_PACKAGE_ROUTE_OBJECT_BEGIN reg={register}\\n"',
                f" if ${register} > 0x10000",
                f"  x/24gx ${register}",
                f"  if *(void**){'$'}{register} > 0x10000",
                f"   printf \"UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={register}\\n\"",
                f"   x/160gx *(void**){'$'}{register}",
                f"   printf \"UE4SS_PACKAGE_ROUTE_VTABLE_END reg={register}\\n\"",
                "  end",
                " end",
                f' printf "UE4SS_PACKAGE_ROUTE_OBJECT_END reg={register}\\n"',
            ]
        )
    lines.extend([" continue", "end", "continue"])
    return "\n".join(lines) + "\n"


OPERATOR_WINDOW = {
    "cleanupRequired": True,
    "maxArmSeconds": 120,
    "sequence": [
        "preflight",
        "arm",
        "operator-client-login-travel-map-entry",
        "status",
        "cleanupCommand",
        "no-debugger-check",
    ],
}


def quoted_remote_trace_command(action, trace_log="/tmp/trace log; final.log"):
    env = {
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST": "kspls0",
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS": "false",
    }
    prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
    args = [
        "scripts/ue4ss-package-remote-trace.sh",
        action,
        "kspls0",
        "dune_server-deep-desert-1",
        trace_log,
    ]
    return prefix + " " + " ".join(shlex.quote(arg) for arg in args)


def next_canary_plan(output_overrides=None):
    output_files = {
        "readinessJson": "ue4ss-readiness.json",
        "objectDiscoveryCoverage": "object-discovery-coverage.json",
        "postCanaryGapSummaryJson": "ue4ss-port-gaps.json",
        "postCanaryGapSummary": "ue4ss-port-gaps.md",
        "evidenceInventoryJson": "ue4ss-evidence-inventory.json",
        "evidenceInventory": "ue4ss-evidence-inventory.md",
        "postCanarySummary": "post-canary-summary.md",
    }
    if output_overrides:
        output_files.update(output_overrides)
    return {
        "schemaVersion": "dune-ue4ss-canary-env-plan/v1",
        "stage": "lua-dispatch",
        "env": [],
        "nextCanaryContract": {
            "postCanaryVerification": {
                "schemaVersion": "dune-ue4ss-post-canary-verification/v1",
                "outputFiles": output_files,
            }
        },
    }


class PackageReviewBundleVerifierTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def make_bundle(self, root):
        files = {
            "ue4ss-package-runtime-trace-plan.json": {
                "schemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "base": "0x100000",
                "expectedBuildId": "abc123",
                "runtimeBuildId": "abc123",
                "seedCount": 2,
                "seeds": [
                    {"name": "LoadPackage", "address": "0x5ae6260"},
                    {"name": "LoadObject", "address": "0x814c33"},
                ],
                "seedSelection": {
                    "selectedByFamily": {
                        "LoadPackage": 1,
                        "LoadObject": 1,
                    },
                },
                "blockers": [],
                "requestedRouteAddresses": ["0x129d58a2"],
                "routeProbes": [
                    {
                        "address": "0x129d58a2",
                        "absoluteAddress": "0x12ad58a2",
                        "promotion": "non-promotable-route-probe",
                    }
                ],
                "routeGdb": route_gdb(),
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                    "DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS": "0x129d58a2",
                    "selectedByFamily": {
                        "LoadPackage": 1,
                        "LoadObject": 1,
                    },
                },
            },
            "ue4ss-package-runtime-trace-evidence.json": {
                "schemaVersion": "dune-ue4ss-package-runtime-trace-evidence/v1",
                "sourceLog": "/tmp/trace.log",
                "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
                "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                "pid": 123,
                "tracePidMatchesRequested": True,
                "imageRangeSource": "pid",
                "imageBase": "0x100000",
                "imageStart": "0x200000",
                "imageEnd": "0x7000000",
                "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
                "imagePerms": "r-xp",
                "hits": [
                    {
                        "seed": "LoadPackage",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "traceAddressMatchesBase": True,
                    }
                ],
            },
            "ue4ss-package-abi-review.json": {
                "schemaVersion": "dune-ue4ss-package-abi-review/v1",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
                "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                "tracePid": 123,
                "imageRangeSource": "pid",
                "imageBase": "0x100000",
                "imageStart": "0x200000",
                "imageEnd": "0x7000000",
                "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
                "imagePerms": "r-xp",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "signatureFamily": "LoadPackage",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForManualAbiReview": False,
            },
            "ue4ss-package-promotion-env.json": {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                    "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
                "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                "tracePid": 123,
                "imageRangeSource": "pid",
                "imageBase": "0x100000",
                "imageStart": "0x200000",
                "imageEnd": "0x7000000",
                "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
                "imagePerms": "r-xp",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "signatureFamily": "LoadPackage",
                "readyForNonInvokingCanary": False,
            },
            "ue4ss-package-next-action.json": {
                "schemaVersion": "dune-ue4ss-package-next-action/v1",
                "action": "arm-trace",
                "traceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_HOST": "kspls0",
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                    "DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS": "0x129d58a2",
                },
                "commands": [
                    "DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0 DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0x129d58a2 scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                    "DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0 DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0x129d58a2 scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log",
                ],
                "liveTraceRunbook": {
                    "sourcePath": "/tmp/ue4ss-package-stimulus-trace-runbook.json",
                    "recommendedCandidate": "operator-client-map-entry",
                    "remote": "kspls0",
                    "container": "dune_server-deep-desert-1",
                    "traceLog": "/tmp/trace.log",
                    "coordinatorFreshPreflightCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                    "cleanupCommand": remote_trace_command("stop"),
                    "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
                    "operatorWindow": OPERATOR_WINDOW,
                    "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                    "localReviewSummaryJson": "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json",
                    "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                    "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                    "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                    "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                    "commandCount": 6,
                    "routeSlotTraceRequirement": ROUTE_SLOT_TRACE_REQUIREMENT,
                },
            },
            "ue4ss-package-stimulus-trace-runbook.json": {
                "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
                "sourcePath": "build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json",
                "recommendedCandidate": "operator-client-map-entry",
                "remote": "kspls0",
                "container": "dune_server-deep-desert-1",
                "partition": "8",
                "traceLog": "/tmp/trace.log",
                "traceEnv": {
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST": "kspls0",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS": "false",
                    "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_PARTITION": "8",
                },
                "traceInputs": {
                    "routeAddress": "0x129d58a2",
                },
                "routeSlotTraceRequirement": ROUTE_SLOT_TRACE_REQUIREMENT,
                "reviewArtifacts": {
                    "evidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
                    "evidenceMarkdown": "/tmp/ue4ss-package-runtime-trace-evidence.md",
                    "abiReviewJson": "/tmp/ue4ss-package-abi-review.json",
                    "promotionEnvJson": "/tmp/ue4ss-package-promotion-env.json",
                    "familyReviewsDir": "/tmp/ue4ss-package-family-reviews",
                    "familyReviewsSummaryJson": "/tmp/ue4ss-package-family-reviews.json",
                    "nextActionJson": "/tmp/ue4ss-package-next-action.json",
                    "reviewBundleRoot": "/tmp/ue4ss-package-review-bundles",
                    "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                    "localReviewSummaryJson": "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json",
                    "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                    "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                    "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                    "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                },
                "commands": [
                    remote_trace_command("print"),
                    remote_trace_command("preflight"),
                    remote_trace_command("arm"),
                    "operator performs the approved client login/travel/map-entry package-load stimulus",
                    remote_trace_command("status"),
                    remote_trace_command("stop"),
                ],
                "coordinatorFreshPreflightCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                "cleanupCommand": remote_trace_command("stop"),
                "noDebuggerCheckCommand": NO_DEBUGGER_CHECK_COMMAND,
                "operatorWindow": OPERATOR_WINDOW,
                "localReviewSummaryJson": "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json",
                "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                    "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
            },
            "ue4ss-package-family-reviews/LoadPackage/review-priority.json": {
                "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                "rank": 0,
                "signatureFamily": "LoadPackage",
                "hitIndex": "auto",
            },
            "ue4ss-package-family-reviews/LoadPackage/promotion-env.json": {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                    "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
                "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "readyForNonInvokingCanary": False,
            },
            "ue4ss-package-runtime-trace-evidence.md": "# evidence\n",
            "ue4ss-package-runtime-trace-plan.md": "# plan\n",
            "ue4ss-package-abi-review.md": "# abi\n",
            "ue4ss-package-promotion-env.md": "# promotion\n",
            "ue4ss-package-stimulus-trace-runbook.md": "# runbook\n",
            "ue4ss-package-next-action.md": "# next\n",
            "trace.log": "trace log bytes\n",
        }
        manifest_lines = [
            "schema=dune-ue4ss-package-review-bundle/v1",
            "createdUtc=20260622T000000Z",
            "container=dune_server-deep-desert-1",
            "traceHost=kspls0",
            "playerGuardPhase=status",
            "playerGuardPartition=8",
            "playerGuardConnectedPlayers=0",
            "processPattern=DuneSandboxServer-Linux-Shipping",
            "signatureFamily=LoadPackage",
            "hitIndex=auto",
            "traceLog=/tmp/trace.log",
            "sourceLogExists=True",
            "sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "sourceEvidenceJson=/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "sourceTracePlan=/tmp/ue4ss-package-runtime-trace-plan.json",
            "tracePidMatchesRequested=True",
            "tracePlanSourceExternalPlan=/tmp/external-plan.json",
            "tracePlanPromotionAcceptanceSchema=dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "tracePlanBase=0x100000",
            "tracePlanExpectedBuildId=abc123",
            "tracePlanRuntimeBuildId=abc123",
            "tracePlanSeedCount=2",
            "tracePlanSeedOffsets=LoadPackage@0x5ae6260,LoadObject@0x814c33",
            "tracePlanSelectedByFamily=LoadObject:1,LoadPackage:1",
            "tracePlanBlockerCount=0",
            "tracePlanRecommendedAnchor=LoadPackage,LoadObject",
            "tracePlanRecommendedLimit=2",
            "tracePlanRecommendedSignatureFamily=LoadPackage",
            "tracePlanRecommendedHitIndex=auto",
            "evidencePid=123",
            "imageRangeSource=pid",
            "imageBase=0x100000",
            "imageStart=0x200000",
            "imageEnd=0x7000000",
            "imagePath=/srv/dune/DuneSandboxServer-Linux-Shipping",
            "imagePerms=r-xp",
        ]
        for name, content in files.items():
            write(root / name, content)
            manifest_lines.append(f"artifact={name} source=/tmp/{name}")
        trace_log_sha256 = file_sha(root / "trace.log")
        for rel_path in (
            "ue4ss-package-runtime-trace-evidence.json",
            "ue4ss-package-abi-review.json",
            "ue4ss-package-promotion-env.json",
            "ue4ss-package-family-reviews/LoadPackage/promotion-env.json",
        ):
            path = root / rel_path
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["sourceLogSha256"] = trace_log_sha256
            write(path, payload)
        evidence_json_sha256 = file_sha(root / "ue4ss-package-runtime-trace-evidence.json")
        manifest_lines = [
            (
                f"sourceEvidenceJsonSha256={evidence_json_sha256}"
                if line == "sourceEvidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                else f"sourceLogSha256={trace_log_sha256}"
                if line == "sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                else line
            )
            for line in manifest_lines
        ]
        write(root / "review-bundle-manifest.txt", "\n".join(manifest_lines) + "\n")
        self.refresh_checksums(root)

    def refresh_checksums(self, root):
        checksum_rows = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                rel = path.relative_to(root).as_posix()
                checksum_rows.append(f"{file_sha(path)}  {rel}")
        write(root / "SHA256SUMS", "\n".join(checksum_rows) + "\n")

    def add_bundled_trace_log_artifact(self, root):
        write(root / "trace.log", "trace log bytes\n")
        trace_log_sha256 = file_sha(root / "trace.log")
        for rel_path in (
            "ue4ss-package-runtime-trace-evidence.json",
            "ue4ss-package-abi-review.json",
            "ue4ss-package-promotion-env.json",
            "ue4ss-package-family-reviews/LoadPackage/promotion-env.json",
        ):
            path = root / rel_path
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["sourceLogSha256"] = trace_log_sha256
            write(path, payload)
        manifest_path = root / "review-bundle-manifest.txt"
        text = manifest_path.read_text(encoding="utf-8")
        text = text.replace("sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", f"sourceLogSha256={trace_log_sha256}")
        text += "artifact=trace.log source=/tmp/trace.log\n"
        write(manifest_path, text)
        self.refresh_checksums(root)
        return trace_log_sha256

    def test_valid_bundle_is_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            expected_evidence_json_sha256 = file_sha(root / "ue4ss-package-runtime-trace-evidence.json")
            expected_trace_log_sha256 = file_sha(root / "trace.log")
            report = self.module.verify_bundle(root)
            rendered = self.module.markdown(report)

        self.assertTrue(report["ready"])
        self.assertEqual(report["manifest"]["schema"], "dune-ue4ss-package-review-bundle/v1")
        self.assertEqual(report["manifest"]["signatureFamily"], "LoadPackage")
        self.assertEqual(report["blockers"], [])
        self.assertIn("Container: `dune_server-deep-desert-1`", rendered)
        self.assertIn("Process pattern: `DuneSandboxServer-Linux-Shipping`", rendered)
        self.assertIn("Trace log: `/tmp/trace.log`", rendered)
        self.assertIn("Trace plan external plan: `/tmp/external-plan.json`", rendered)
        self.assertIn("Trace plan base: `0x100000`", rendered)
        self.assertIn("Trace plan expected Build ID: `abc123`", rendered)
        self.assertIn("Trace plan runtime Build ID: `abc123`", rendered)
        self.assertIn("Trace plan seed count: `2`", rendered)
        self.assertIn("Trace plan seed offsets: `LoadPackage@0x5ae6260,LoadObject@0x814c33`", rendered)
        self.assertIn("Trace plan selected by family: `LoadObject:1,LoadPackage:1`", rendered)
        self.assertIn("Trace plan blocker count: `0`", rendered)
        self.assertIn("Trace plan recommended anchor: `LoadPackage,LoadObject`", rendered)
        self.assertIn("Trace plan recommended limit: `2`", rendered)
        self.assertIn("Trace plan recommended signature family: `LoadPackage`", rendered)
        self.assertIn("Trace plan recommended hit index: `auto`", rendered)
        self.assertIn("Player guard phase: `status`", rendered)
        self.assertIn("Player guard partition: `8`", rendered)
        self.assertIn("Player guard connected players: `0`", rendered)
        self.assertIn("Source log exists: `True`", rendered)
        self.assertEqual(report["manifest"]["sourceLogSha256"], expected_trace_log_sha256)
        self.assertEqual(report["manifest"]["sourceEvidenceJsonSha256"], expected_evidence_json_sha256)
        self.assertIn("Evidence PID: `123`", rendered)
        self.assertIn("Trace PID matches requested: `True`", rendered)
        self.assertIn("Image range source: `pid`", rendered)
        self.assertIn("Image range: `0x200000-0x7000000` base=`0x100000`", rendered)
        self.assertIn("Image path: `/srv/dune/DuneSandboxServer-Linux-Shipping`", rendered)
        self.assertIn("Image perms: `r-xp`", rendered)

    def test_runtime_route_hits_require_route_slot_recovery_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["routeHitCount"] = 1
            evidence["routeHits"] = [{"imageOffset": "0x129d58a2"}]
            evidence.pop("routeSlotRecovery", None)
            write(evidence_path, evidence)
            evidence_sha = file_sha(evidence_path)
            for rel_path in (
                "ue4ss-package-abi-review.json",
                "ue4ss-package-promotion-env.json",
            ):
                payload = json.loads((root / rel_path).read_text(encoding="utf-8"))
                payload["sourceEvidenceJsonSha256"] = evidence_sha
                write(root / rel_path, payload)
            manifest_path = root / "review-bundle-manifest.txt"
            lines = manifest_path.read_text(encoding="utf-8").splitlines()
            lines = [
                f"sourceEvidenceJsonSha256={evidence_sha}"
                if line.startswith("sourceEvidenceJsonSha256=")
                else line
                for line in lines
            ]
            write(manifest_path, "\n".join(lines) + "\n")
            self.refresh_checksums(root)

            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json routeSlotRecovery is missing for route hit evidence",
            report["blockers"],
        )

    def test_runtime_route_slot_recovery_summary_must_be_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["routeHitCount"] = 1
            evidence["routeHits"] = [{"imageOffset": "0x129d58a2"}]
            evidence["routeSlotRecovery"] = {
                "ready": True,
                "routeHitCount": 2,
                "requiredSlots": ["0x3a0", "0x3d8"],
                "presentSlots": ["0x3a0"],
                "missingSlots": ["0x3d8"],
                "matchCount": 0,
                "matches": [{"slotOffset": "0x3a0"}],
                "blockers": [],
            }
            write(evidence_path, evidence)
            evidence_sha = file_sha(evidence_path)
            for rel_path in (
                "ue4ss-package-abi-review.json",
                "ue4ss-package-promotion-env.json",
            ):
                payload = json.loads((root / rel_path).read_text(encoding="utf-8"))
                payload["sourceEvidenceJsonSha256"] = evidence_sha
                write(root / rel_path, payload)
            manifest_path = root / "review-bundle-manifest.txt"
            lines = manifest_path.read_text(encoding="utf-8").splitlines()
            lines = [
                f"sourceEvidenceJsonSha256={evidence_sha}"
                if line.startswith("sourceEvidenceJsonSha256=")
                else line
                for line in lines
            ]
            write(manifest_path, "\n".join(lines) + "\n")
            self.refresh_checksums(root)

            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json routeSlotRecovery routeHitCount does not match routeHitCount",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json routeSlotRecovery matchCount does not match matches length",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json routeSlotRecovery ready cannot be true while missingSlots is non-empty",
            report["blockers"],
        )

    def test_markdown_prints_optional_trace_host_and_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace(
                "processPattern=DuneSandboxServer-Linux-Shipping",
                "processPattern=DuneSandboxServer-Linux-Shipping\ntracePid=123",
            )
            write(manifest_path, text)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PID"] = "123"
            payload["commands"] = [
                (
                    "DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0 "
                    "DUNE_UE4SS_PACKAGE_TRACE_PID=123 "
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject "
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 "
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage "
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto "
                    "DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0x129d58a2 "
                    "scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log"
                ),
                (
                    "DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0 "
                    "DUNE_UE4SS_PACKAGE_TRACE_PID=123 "
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject "
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 "
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage "
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto "
                    "DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0x129d58a2 "
                    "scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log"
                ),
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)
            rendered = self.module.markdown(report)

        self.assertTrue(report["ready"])
        self.assertIn("Trace host: `kspls0`", rendered)
        self.assertIn("Trace PID: `123`", rendered)

    def test_live_bundle_requires_status_player_guard_zero_players(self):
        cases = (
            ("playerGuardPhase=status\n", "playerGuardPhase=preflight\n", "review-bundle-manifest.txt playerGuardPhase must be status for live kspls0 package trace evidence"),
            ("playerGuardPartition=8\n", "playerGuardPartition=\n", "review-bundle-manifest.txt playerGuardPartition must be numeric for live kspls0 package trace evidence"),
            ("playerGuardConnectedPlayers=0\n", "playerGuardConnectedPlayers=1\n", "review-bundle-manifest.txt playerGuardConnectedPlayers must be 0 for live kspls0 package trace evidence"),
        )
        for old, new, blocker in cases:
            with self.subTest(blocker=blocker):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    manifest = root / "review-bundle-manifest.txt"
                    manifest.write_text(manifest.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(blocker, report["blockers"])

    def test_checksum_mismatch_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(root / "ue4ss-package-next-action.md", "# tampered\n")
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("checksum mismatch: ue4ss-package-next-action.md", report["blockers"])

    def test_duplicate_checksum_rows_block_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            sums = root / "SHA256SUMS"
            text = sums.read_text(encoding="utf-8")
            first = next(line for line in text.splitlines() if line.endswith("  ue4ss-package-next-action.md"))
            sums.write_text(text + first + "\n", encoding="utf-8")
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("SHA256SUMS has duplicate checksum row: ue4ss-package-next-action.md", report["blockers"])

    def test_unsafe_checksum_paths_block_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            sums = root / "SHA256SUMS"
            sums.write_text(
                sums.read_text(encoding="utf-8")
                + ("0" * 64)
                + "  ../outside.json\n"
                + ("1" * 64)
                + "  /tmp/outside.json\n"
                + ("2" * 64)
                + "  ./ue4ss-package-next-action.json\n",
                encoding="utf-8",
            )
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertTrue(
            any(blocker.endswith("has unsafe path: ../outside.json") for blocker in report["blockers"]),
            report["blockers"],
        )
        self.assertTrue(
            any(blocker.endswith("has unsafe path: /tmp/outside.json") for blocker in report["blockers"]),
            report["blockers"],
        )
        self.assertTrue(
            any(blocker.endswith("has unsafe path: ./ue4ss-package-next-action.json") for blocker in report["blockers"]),
            report["blockers"],
        )

    def test_malformed_checksum_rows_block_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            sums = root / "SHA256SUMS"
            sums.write_text(
                sums.read_text(encoding="utf-8")
                + "not-a-checksum  ue4ss-package-next-action.json\n"
                + "missing-path-only\n",
                encoding="utf-8",
            )
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertTrue(any(blocker.endswith("has malformed digest") for blocker in report["blockers"]), report["blockers"])
        self.assertTrue(any(blocker.endswith("is malformed") for blocker in report["blockers"]), report["blockers"])

    def test_optional_next_canary_json_schema_is_verified_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                {
                    "schemaVersion": "wrong",
                    "stage": "lua-dispatch",
                    "env": [],
                },
            )
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-next-canary.json has unsupported schemaVersion", report["blockers"])

    def test_top_level_json_artifact_must_be_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            (root / "ue4ss-package-next-action.json").write_text("[]", encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-next-action.json must be a JSON object", report["blockers"])

    def test_missing_required_artifact_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            (root / "ue4ss-package-abi-review.json").unlink()
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("missing required artifact: ue4ss-package-abi-review.json", report["blockers"])

    def test_optional_family_summary_must_be_listed_in_manifest_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": [],
                    "manifests": [],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json missing from review-bundle-manifest.txt artifact rows",
            report["blockers"],
        )

    def test_missing_trace_plan_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            (root / "ue4ss-package-runtime-trace-plan.json").unlink()
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("missing required artifact: ue4ss-package-runtime-trace-plan.json", report["blockers"])

    def test_required_artifacts_must_be_listed_in_manifest_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest = root / "review-bundle-manifest.txt"
            lines = [
                line
                for line in manifest.read_text(encoding="utf-8").splitlines()
                if not line.startswith("artifact=ue4ss-package-runtime-trace-plan.json ")
            ]
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "required artifact not listed in review-bundle-manifest.txt artifact rows: ue4ss-package-runtime-trace-plan.json",
            report["blockers"],
        )

    def test_manifest_artifact_rows_must_stay_inside_bundle_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest = root / "review-bundle-manifest.txt"
            text = manifest.read_text(encoding="utf-8")
            text = text.replace(
                "artifact=ue4ss-package-runtime-trace-plan.json source=/tmp/ue4ss-package-runtime-trace-plan.json",
                "artifact=../ue4ss-package-runtime-trace-plan.json source=/tmp/ue4ss-package-runtime-trace-plan.json",
            )
            manifest.write_text(text, encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt has artifact row outside bundle namespace: ../ue4ss-package-runtime-trace-plan.json",
            report["blockers"],
        )

    def test_manifest_metadata_keys_must_not_be_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest = root / "review-bundle-manifest.txt"
            text = manifest.read_text(encoding="utf-8")
            text = text.replace(
                "traceLog=/tmp/trace.log",
                "traceLog=/tmp/stale.log\ntraceLog=/tmp/trace.log",
            )
            manifest.write_text(text, encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt has duplicate metadata key: traceLog",
            report["blockers"],
        )

    def test_manifest_runtime_selectors_must_be_non_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest = root / "review-bundle-manifest.txt"
            text = manifest.read_text(encoding="utf-8")
            text = text.replace("processPattern=DuneSandboxServer-Linux-Shipping", "processPattern=")
            manifest.write_text(text, encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt processPattern must be non-empty and single-line",
            report["blockers"],
        )

    def test_manifest_trace_pid_must_be_numeric_when_present(self):
        for trace_pid in ("not-a-pid", "0", "\u0660"):
            with self.subTest(trace_pid=trace_pid):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    manifest = root / "review-bundle-manifest.txt"
                    text = manifest.read_text(encoding="utf-8")
                    text = text.replace(
                        "processPattern=DuneSandboxServer-Linux-Shipping",
                        f"processPattern=DuneSandboxServer-Linux-Shipping\ntracePid={trace_pid}",
                    )
                    manifest.write_text(text, encoding="utf-8")
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn("review-bundle-manifest.txt tracePid must be numeric", report["blockers"])

    def test_manifest_artifact_rows_require_source_and_unique_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest = root / "review-bundle-manifest.txt"
            text = manifest.read_text(encoding="utf-8")
            text = text.replace(
                "artifact=ue4ss-package-runtime-trace-plan.md source=/tmp/ue4ss-package-runtime-trace-plan.md",
                "artifact=ue4ss-package-runtime-trace-plan.md\n"
                "artifact=ue4ss-package-runtime-trace-plan.md source=/tmp/duplicate-plan.md",
            )
            manifest.write_text(text, encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt artifact row is missing source: ue4ss-package-runtime-trace-plan.md",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt has duplicate artifact row: ue4ss-package-runtime-trace-plan.md",
            report["blockers"],
        )

    def test_manifest_artifact_rows_must_reference_existing_bundled_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest = root / "review-bundle-manifest.txt"
            text = manifest.read_text(encoding="utf-8")
            text += "artifact=missing-review-note.md source=/tmp/missing-review-note.md\n"
            manifest.write_text(text, encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt artifact row references missing bundled file: missing-review-note.md",
            report["blockers"],
        )

    def test_manifest_artifact_rows_must_be_covered_by_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(root / "operator-note.md", "# note\n")
            manifest = root / "review-bundle-manifest.txt"
            text = manifest.read_text(encoding="utf-8")
            text += "artifact=operator-note.md source=/tmp/operator-note.md\n"
            manifest.write_text(text, encoding="utf-8")
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt artifact row is missing from SHA256SUMS: operator-note.md",
            report["blockers"],
        )

    def test_manifest_artifact_rows_must_match_checksum_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(root / "ue4ss-package-next-action.md", "# tampered after checksum\n")
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt artifact row SHA256SUMS digest does not match bundled file: ue4ss-package-next-action.md",
            report["blockers"],
        )

    def test_blocked_trace_plan_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            payload["blockers"] = ["no package runtime trace seeds selected"]
            write(trace_plan_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json runtime trace plan has blocker: no package runtime trace seeds selected",
            report["blockers"],
        )

    def test_trace_plan_recommended_env_limit_must_match_seed_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            payload["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"] = "1"
            write(trace_plan_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json recommendedTraceEnv limit does not match hardware-safe selected trace seed count",
            report["blockers"],
        )

    def test_trace_plan_recommended_env_limit_may_be_capped_by_hardware_watchpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            payload["seedCount"] = 5
            payload["hardwareReadWatchpointLimit"] = 4
            payload["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"] = "4"
            write(trace_plan_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertNotIn(
            "ue4ss-package-runtime-trace-plan.json recommendedTraceEnv limit does not match hardware-safe selected trace seed count",
            report["blockers"],
        )

    def test_trace_plan_recommended_env_must_be_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            payload["recommendedTraceEnv"] = ["DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2"]
            write(trace_plan_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json recommendedTraceEnv must be an object",
            report["blockers"],
        )

    def test_trace_plan_recommended_env_rejects_bad_values(self):
        cases = (
            (
                {"DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,MissingAnchor"},
                "recommendedTraceEnv has unsupported trace anchor: MissingAnchor",
            ),
            (
                {"DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "MissingAnchor"},
                "recommendedTraceEnv has unsupported signature family: MissingAnchor",
            ),
            (
                {"DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "0"},
                "recommendedTraceEnv limit must be positive",
            ),
            (
                {"DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "later"},
                "recommendedTraceEnv hit index must be an integer or auto",
            ),
        )
        for values, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
                    payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
                    payload["recommendedTraceEnv"].update(values)
                    write(trace_plan_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(f"ue4ss-package-runtime-trace-plan.json {message}", report["blockers"])

    def test_trace_plan_recommended_env_anchors_must_match_selected_families(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            payload["recommendedTraceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_ANCHOR"] = "LoadPackage"
            write(trace_plan_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json recommendedTraceEnv anchors do not match selected trace seed families",
            report["blockers"],
        )

    def test_trace_plan_recommended_env_selected_families_must_match_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            payload["recommendedTraceEnv"]["selectedByFamily"] = {"LoadPackage": 2}
            write(trace_plan_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json recommendedTraceEnv selectedByFamily does not match seedSelection selectedByFamily",
            report["blockers"],
        )

    def test_trace_plan_recommended_env_selected_families_must_be_well_formed(self):
        cases = (
            (["LoadPackage"], "recommendedTraceEnv selectedByFamily must be a JSON object"),
            ({"": 1}, "recommendedTraceEnv selectedByFamily keys must be non-empty strings"),
            ({"LoadPackage": True}, "recommendedTraceEnv selectedByFamily values must be positive integers"),
            ({"LoadPackage": 0}, "recommendedTraceEnv selectedByFamily values must be positive integers"),
        )
        for selected_by_family, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
                    payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
                    payload["recommendedTraceEnv"]["selectedByFamily"] = selected_by_family
                    write(trace_plan_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(f"ue4ss-package-runtime-trace-plan.json {message}", report["blockers"])

    def test_manifest_recommended_trace_env_must_match_trace_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest = root / "review-bundle-manifest.txt"
            text = manifest.read_text(encoding="utf-8")
            text = text.replace("tracePlanRecommendedLimit=2", "tracePlanRecommendedLimit=1")
            manifest.write_text(text, encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt tracePlanRecommendedLimit does not match runtime trace plan recommendedTraceEnv DUNE_UE4SS_PACKAGE_TRACE_LIMIT",
            report["blockers"],
        )

    def test_next_action_trace_env_must_match_trace_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY"] = "StaticLoadClass"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY does not match runtime trace plan",
            report["blockers"],
        )

    def test_next_action_route_env_matches_requested_route_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            trace_plan = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            trace_plan["requestedRouteAddresses"] = ["0x1299f5fa", "0x12659bb6", "0x12661ecc"]
            write(trace_plan_path, trace_plan)
            next_action_path = root / "ue4ss-package-next-action.json"
            next_action = json.loads(next_action_path.read_text(encoding="utf-8"))
            route_env = "0x1299f5fa,0x12659bb6,0x12661ecc"
            next_action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS"] = route_env
            next_action["commands"] = [
                command.replace(
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto ",
                    f"DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS={route_env} ",
                )
                for command in next_action["commands"]
            ]
            write(next_action_path, next_action)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertNotIn(
            "ue4ss-package-next-action.json traceEnv DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS is not present in runtime trace plan",
            report["blockers"],
        )
        self.assertNotIn(
            "ue4ss-package-next-action.json commands include unexpected traceEnv DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS not present in runtime trace plan",
            report["blockers"],
        )

    def test_next_action_route_env_must_match_requested_route_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            trace_plan = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            trace_plan["requestedRouteAddresses"] = ["0x1299f5fa", "0x12659bb6"]
            write(trace_plan_path, trace_plan)
            next_action_path = root / "ue4ss-package-next-action.json"
            next_action = json.loads(next_action_path.read_text(encoding="utf-8"))
            next_action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS"] = "0x1299f5fa"
            next_action["commands"] = [
                command.replace(
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto ",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0x1299f5fa ",
                )
                for command in next_action["commands"]
            ]
            write(next_action_path, next_action)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS does not match runtime trace plan",
            report["blockers"],
        )

    def test_next_action_live_runbook_summary_must_match_bundled_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"].pop("remote", None)
            payload["liveTraceRunbook"]["container"] = "stale-container"
            payload["liveTraceRunbook"]["coordinatorFreshPreflightCommand"] = "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --trace-log /tmp/stale.log"
            payload["liveTraceRunbook"]["digestProvenanceFields"] = "staleDigestField"
            payload["liveTraceRunbook"]["commandCount"] = 99
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook remote does not match bundled stimulus trace runbook",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook container does not match bundled stimulus trace runbook",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook coordinatorFreshPreflightCommand does not match bundled stimulus trace runbook",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook digestProvenanceFields does not match bundled stimulus trace runbook",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook commandCount does not match bundled stimulus trace runbook",
            report["blockers"],
        )

    def test_next_action_live_runbook_route_slot_requirement_must_match_bundled_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["routeSlotTraceRequirement"] = {
                **ROUTE_SLOT_TRACE_REQUIREMENT,
                "requiredSlots": ["0x3a0"],
            }
            write(next_action_path, payload)
            self.refresh_checksums(root)

            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook routeSlotTraceRequirement does not match bundled stimulus trace runbook",
            report["blockers"],
        )

    def test_runtime_trace_plan_route_gdb_must_capture_required_route_slot_registers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            trace_plan = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            trace_plan["routeGdb"] = route_gdb(registers=["rbx"])
            write(trace_plan_path, trace_plan)
            self.refresh_checksums(root)

            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json routeGdb is missing required register print for r14",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json routeGdb is missing required object capture for r14",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json routeGdb is missing required vtable capture for r14",
            report["blockers"],
        )

    def test_runtime_route_slot_recovery_required_slots_must_match_bundled_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["routeHitCount"] = 1
            evidence["routeHits"] = [{"imageOffset": "0x129d58a2"}]
            evidence["routeSlotRecovery"] = {
                "ready": False,
                "routeHitCount": 1,
                "requiredSlots": ["0x3a0"],
                "presentSlots": ["0x3a0"],
                "missingSlots": [],
                "matchCount": 1,
                "matches": [{"slotOffset": "0x3a0"}],
                "blockers": ["missing route vtable static slot matches: 0x3d8"],
            }
            write(evidence_path, evidence)
            evidence_sha = file_sha(evidence_path)
            for rel_path in (
                "ue4ss-package-abi-review.json",
                "ue4ss-package-promotion-env.json",
            ):
                payload = json.loads((root / rel_path).read_text(encoding="utf-8"))
                payload["sourceEvidenceJsonSha256"] = evidence_sha
                write(root / rel_path, payload)
            manifest_path = root / "review-bundle-manifest.txt"
            lines = manifest_path.read_text(encoding="utf-8").splitlines()
            lines = [
                f"sourceEvidenceJsonSha256={evidence_sha}"
                if line.startswith("sourceEvidenceJsonSha256=")
                else line
                for line in lines
            ]
            write(manifest_path, "\n".join(lines) + "\n")
            self.refresh_checksums(root)

            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json routeSlotRecovery requiredSlots do not match bundled routeSlotTraceRequirement",
            report["blockers"],
        )

    def test_next_action_local_review_summary_path_must_match_bundled_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["localReviewSummaryJson"] = "build/server-current-anchor-prep/stale-review-summary.json"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook localReviewSummaryJson does not match bundled stimulus trace runbook",
            report["blockers"],
        )

    def test_live_runbook_top_level_local_review_summary_must_match_review_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["localReviewSummaryJson"] = "build/server-current-anchor-prep/stale-review-summary.json"
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json localReviewSummaryJson does not match reviewArtifacts localReviewSummaryJson",
            report["blockers"],
        )

    def test_live_runbook_digest_provenance_fields_must_be_current_even_when_summary_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            next_action = json.loads(next_action_path.read_text(encoding="utf-8"))
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            stale_fields = "sourceLogSha256,sourceEvidenceJsonSha256"
            next_action["liveTraceRunbook"]["digestProvenanceFields"] = stale_fields
            runbook["reviewArtifacts"]["digestProvenanceFields"] = stale_fields
            write(next_action_path, next_action)
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook digestProvenanceFields must be sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json reviewArtifacts digestProvenanceFields must be sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
            report["blockers"],
        )

    def test_live_runbook_local_review_summary_schema_must_be_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            next_action = json.loads(next_action_path.read_text(encoding="utf-8"))
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            stale_schema = "dune-ue4ss-package-live-stimulus-review-summary/v0"
            next_action["liveTraceRunbook"]["localReviewSummarySchemaVersion"] = stale_schema
            runbook["reviewArtifacts"]["localReviewSummarySchemaVersion"] = stale_schema
            write(next_action_path, next_action)
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json reviewArtifacts localReviewSummarySchemaVersion must be dune-ue4ss-package-live-stimulus-review-summary/v1",
            report["blockers"],
        )

    def test_live_runbook_local_review_summary_runbook_mode_must_be_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            next_action = json.loads(next_action_path.read_text(encoding="utf-8"))
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            stale_mode = "source-runbook-only"
            next_action["liveTraceRunbook"]["localReviewSummaryRunbookMode"] = stale_mode
            runbook["reviewArtifacts"]["localReviewSummaryRunbookMode"] = stale_mode
            write(next_action_path, next_action)
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json reviewArtifacts localReviewSummaryRunbookMode must be default-source-runbook;trace-log-override-effective-runbook",
            report["blockers"],
        )

    def test_live_runbook_review_artifact_paths_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["reviewArtifacts"].pop("evidenceJson")
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json reviewArtifacts evidenceJson must be a non-empty single-line string",
            report["blockers"],
        )

    def test_live_runbook_review_artifact_paths_must_match_standard_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["reviewArtifacts"]["evidenceJson"] = "/tmp/stale-runtime-trace-evidence.json"
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json reviewArtifacts evidenceJson must be /tmp/ue4ss-package-runtime-trace-evidence.json",
            report["blockers"],
        )

    def test_live_runbook_trace_env_must_keep_live_host_player_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["traceEnv"]["DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS"] = "true"
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json traceEnv DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS must be false",
            report["blockers"],
        )

    def test_manifest_trace_host_must_match_live_runbook_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            lines = [
                line
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
                if not line.startswith("traceHost=")
            ]
            write(manifest_path, "\n".join(lines) + "\n")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt traceHost must be kspls0 when bundled stimulus trace runbook remote is kspls0",
            report["blockers"],
        )

    def test_manifest_container_must_match_live_runbook_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8").replace(
                "container=dune_server-deep-desert-1",
                "container=dune_server-deep-desert-2",
            )
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt container must match bundled stimulus trace runbook container",
            report["blockers"],
        )

    def test_manifest_trace_log_must_match_live_runbook_trace_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8").replace(
                "traceLog=/tmp/trace.log",
                "traceLog=/tmp/stale-trace.log",
            )
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt traceLog must match bundled stimulus trace runbook traceLog",
            report["blockers"],
        )

    def test_next_action_live_runbook_source_path_must_match_manifest_artifact_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8").replace(
                "artifact=ue4ss-package-stimulus-trace-runbook.json source=/tmp/ue4ss-package-stimulus-trace-runbook.json",
                "artifact=ue4ss-package-stimulus-trace-runbook.json source=/tmp/stale-stimulus-trace-runbook.json",
            )
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook sourcePath does not match review-bundle-manifest.txt source for ue4ss-package-stimulus-trace-runbook.json",
            report["blockers"],
        )

    def test_live_runbook_commands_must_use_remote_wrapper_and_player_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["commands"] = [
                "scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                "scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log",
            ]
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json commands must use scripts/ue4ss-package-remote-trace.sh for remote live trace actions",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json commands must set DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false",
            report["blockers"],
        )

    def test_live_runbook_commands_must_keep_expected_trace_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["commands"] = [
                remote_trace_command("preflight"),
                remote_trace_command("arm"),
                remote_trace_command("status"),
                remote_trace_command("stop"),
            ]
            write(runbook_path, runbook)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["commandCount"] = 4
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json commands must run remote trace actions in print, preflight, arm, status, stop order",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json commands must include exactly one operator stimulus step",
            report["blockers"],
        )

    def test_live_runbook_commands_accept_shell_quoted_trace_log_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            trace_log = "/tmp/trace log; final.log"
            runbook["traceLog"] = trace_log
            runbook["commands"] = [
                quoted_remote_trace_command("print", trace_log),
                quoted_remote_trace_command("preflight", trace_log),
                quoted_remote_trace_command("arm", trace_log),
                "operator performs the approved client login/travel/map-entry package-load stimulus",
                quoted_remote_trace_command("status", trace_log),
                quoted_remote_trace_command("stop", trace_log),
            ]
            runbook["cleanupCommand"] = quoted_remote_trace_command("stop", trace_log)
            write(runbook_path, runbook)
            next_action_path = root / "ue4ss-package-next-action.json"
            next_action = json.loads(next_action_path.read_text(encoding="utf-8"))
            next_action["liveTraceRunbook"]["traceLog"] = trace_log
            write(next_action_path, next_action)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8").replace("traceLog=/tmp/trace.log", f"traceLog={trace_log}")
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertNotIn(
            "ue4ss-package-stimulus-trace-runbook.json parsed commands traceLog does not match live runbook traceLog",
            report["blockers"],
        )
        self.assertNotIn(
            "ue4ss-package-stimulus-trace-runbook.json commands must parse as env assignments followed by remote trace wrapper action remote container traceLog",
            report["blockers"],
        )

    def test_live_runbook_commands_must_parse_expected_remote_wrapper_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["commands"][0] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST=kspls0 "
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false "
                "scripts/ue4ss-package-remote-trace.sh print kspls0 dune_server-deep-desert-1 /tmp/trace.log extra"
            )
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json commands must parse as env assignments followed by remote trace wrapper action remote container traceLog",
            report["blockers"],
        )

    def test_live_runbook_commands_must_match_trace_log_after_shell_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["traceLog"] = "/tmp/trace.log"
            runbook["commands"][0] = (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST=kspls0 "
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false "
                "scripts/ue4ss-package-remote-trace.sh print kspls0 dune_server-deep-desert-1 '/tmp/trace.log stale'"
            )
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json parsed commands traceLog does not match live runbook traceLog",
            report["blockers"],
        )

    def test_live_runbook_cleanup_command_must_match_stop_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["cleanupCommand"] = remote_trace_command("stop", "/tmp/stale-cleanup.log")
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json cleanupCommand must match the stop command",
            report["blockers"],
        )

    def test_live_runbook_cleanup_command_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook.pop("cleanupCommand", None)
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json cleanupCommand must be a non-empty single-line string",
            report["blockers"],
        )

    def test_next_action_live_runbook_cleanup_command_must_match_bundled_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["cleanupCommand"] = remote_trace_command("stop", "/tmp/stale-cleanup.log")
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook cleanupCommand does not match bundled stimulus trace runbook",
            report["blockers"],
        )

    def test_next_action_live_runbook_cleanup_command_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"].pop("cleanupCommand", None)
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook cleanupCommand does not match bundled stimulus trace runbook",
            report["blockers"],
        )

    def test_next_action_live_runbook_command_count_must_be_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["commandCount"] = 0
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook commandCount must be a positive integer",
            report["blockers"],
        )

    def test_live_runbook_no_debugger_command_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook.pop("noDebuggerCheckCommand", None)
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json noDebuggerCheckCommand must be a non-empty single-line string",
            report["blockers"],
        )

    def test_live_runbook_operator_window_sequence_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            runbook_path = root / "ue4ss-package-stimulus-trace-runbook.json"
            runbook = json.loads(runbook_path.read_text(encoding="utf-8"))
            runbook["operatorWindow"]["sequence"] = ["preflight", "arm", "status"]
            write(runbook_path, runbook)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-stimulus-trace-runbook.json operatorWindow sequence must preserve bounded cleanup handoff",
            report["blockers"],
        )

    def test_next_action_live_runbook_no_debugger_command_must_match_bundled_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["noDebuggerCheckCommand"] = "ssh kspls0 true"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook noDebuggerCheckCommand does not match bundled stimulus trace runbook",
            report["blockers"],
        )

    def test_next_action_live_runbook_operator_window_must_match_bundled_runbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["liveTraceRunbook"]["operatorWindow"]["maxArmSeconds"] = 30
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json liveTraceRunbook operatorWindow does not match bundled stimulus trace runbook",
            report["blockers"],
        )

    def test_next_action_trace_env_must_be_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"] = ["DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2"]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-next-action.json traceEnv must be an object", report["blockers"])

    def test_next_action_commands_must_be_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [{"argv": ["scripts/ue4ss-package-runtime-trace.sh", "arm"]}]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-next-action.json commands entries must be strings", report["blockers"])

    def test_next_action_guidance_fields_must_be_strings(self):
        for key, value, message in (
            ("confidence", ["moderate"], "confidence must be a string"),
            ("reason", {"text": "runtime trace"}, "reason must be a string"),
            ("nextStep", ["capture a package frame"], "nextStep must be a string"),
        ):
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    next_action_path = root / "ue4ss-package-next-action.json"
                    payload = json.loads(next_action_path.read_text(encoding="utf-8"))
                    payload[key] = value
                    write(next_action_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(f"ue4ss-package-next-action.json {message}", report["blockers"])

    def test_next_action_pending_must_be_well_formed(self):
        cases = (
            (
                ["not-object"],
                "pending must be an object",
            ),
            (
                {"missingReviewFlags": "--reviewed-abi"},
                "pending missingReviewFlags must be a list",
            ),
            (
                {"missingNativeInvokeFlags": ["--final-native-call", 42]},
                "pending missingNativeInvokeFlags entries must be strings",
            ),
            (
                {"blockers": [{"message": "manual review required"}]},
                "pending blockers entries must be strings",
            ),
            (
                {"abiReviewBlockers": {"message": "abi mismatch"}},
                "pending abiReviewBlockers must be a list",
            ),
        )
        for value, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    next_action_path = root / "ue4ss-package-next-action.json"
                    payload = json.loads(next_action_path.read_text(encoding="utf-8"))
                    payload["pending"] = value
                    write(next_action_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(f"ue4ss-package-next-action.json {message}", report["blockers"])

    def test_next_action_trace_plan_blockers_must_be_strings(self):
        for value, message in (
            ("no package runtime trace seeds selected", "tracePlanBlockers must be a list"),
            (["no package runtime trace seeds selected", {"code": "missing-seeds"}], "tracePlanBlockers entries must be strings"),
        ):
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    next_action_path = root / "ue4ss-package-next-action.json"
                    payload = json.loads(next_action_path.read_text(encoding="utf-8"))
                    payload["tracePlanBlockers"] = value
                    write(next_action_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(f"ue4ss-package-next-action.json {message}", report["blockers"])

    def test_next_action_promotion_summary_errors_must_be_well_formed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["promotionSummaryErrors"] = [{"path": "/tmp/promotion-env.json", "error": ""}]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json promotionSummaryErrors[0].error must be a non-empty string",
            report["blockers"],
        )

    def test_next_action_commands_must_match_trace_plan_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                command.replace("DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2", "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=1")
                for command in payload["commands"]
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not include traceEnv DUNE_UE4SS_PACKAGE_TRACE_LIMIT from runtime trace plan",
            report["blockers"],
        )

    def test_next_action_trace_env_values_must_be_single_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY"] = "LoadPackage\nLoadObject"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY must be a non-empty single-line value",
            report["blockers"],
        )

    def test_next_action_commands_must_be_single_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"][0] = payload["commands"][0] + "\necho stale"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands entries must be non-empty single-line strings",
            report["blockers"],
        )

    def test_next_action_commands_reject_unplanned_trace_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                "DUNE_UE4SS_PACKAGE_TRACE_STALE_FLAG=1 " + command
                for command in payload["commands"]
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands include unexpected traceEnv DUNE_UE4SS_PACKAGE_TRACE_STALE_FLAG not present in runtime trace plan",
            report["blockers"],
        )

    def test_next_action_commands_must_be_shell_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT='2 scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertTrue(
            any(
                blocker.startswith("ue4ss-package-next-action.json command is not shell-parseable:")
                for blocker in report["blockers"]
            ),
            report["blockers"],
        )

    def test_next_action_commands_compare_parsed_trace_env_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                command.replace(
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT='2 stale'",
                )
                for command in payload["commands"]
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not include traceEnv DUNE_UE4SS_PACKAGE_TRACE_LIMIT from runtime trace plan",
            report["blockers"],
        )

    def test_next_action_process_pattern_must_match_manifest_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN"] = "ExampleGame-Linux-Shipping"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN does not match review-bundle-manifest.txt processPattern",
            report["blockers"],
        )

    def test_next_action_commands_must_reference_manifest_container_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                "scripts/ue4ss-package-runtime-trace.sh arm stale-container /tmp/trace.log",
                "scripts/ue4ss-package-runtime-trace.sh status stale-container /tmp/trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not reference review-bundle-manifest.txt container",
            report["blockers"],
        )

    def test_explicit_pid_neutral_container_label_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("container=dune_server-deep-desert-1", "container=pid-4242")
            text = text.replace(
                "processPattern=DuneSandboxServer-Linux-Shipping",
                "processPattern=DuneSandboxServer-Linux-Shipping\ntracePid=123",
            )
            write(manifest_path, text)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PID"] = "123"
            payload["commands"] = [
                command.replace("dune_server-deep-desert-1", "pid-4242").replace(
                    "scripts/ue4ss-package-runtime-trace.sh",
                    "DUNE_UE4SS_PACKAGE_TRACE_PID=123 scripts/ue4ss-package-runtime-trace.sh",
                )
                for command in payload["commands"]
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertTrue(report["ready"], report["blockers"])

    def test_explicit_pid_selector_is_accepted_for_manifest_container_when_trace_pid_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace(
                "processPattern=DuneSandboxServer-Linux-Shipping",
                "processPattern=DuneSandboxServer-Linux-Shipping\ntracePid=123",
            )
            write(manifest_path, text)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"].update(
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_PID": "123",
                    "DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN": "DuneSandboxServer-Linux-Shipping",
                    "DUNE_UE4SS_PACKAGE_TRACE_PLAN": "/tmp/external-plan.json",
                    "DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON": "/tmp/ue4ss-package-runtime-trace-plan.json",
                    "DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD": "/tmp/ue4ss-package-runtime-trace-plan.md",
                }
            )
            env_prefix = (
                "DUNE_UE4SS_PACKAGE_TRACE_PID=123 "
                "DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN=DuneSandboxServer-Linux-Shipping "
                "DUNE_UE4SS_PACKAGE_TRACE_PLAN=/tmp/external-plan.json "
                "DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON=/tmp/ue4ss-package-runtime-trace-plan.json "
                "DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD=/tmp/ue4ss-package-runtime-trace-plan.md "
            )
            payload["commands"] = [
                env_prefix + command.replace("dune_server-deep-desert-1", "pid-123")
                for command in payload["commands"]
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertTrue(report["ready"], report["blockers"])

    def test_each_replay_runtime_command_must_reference_manifest_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                "scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                "scripts/ue4ss-package-runtime-trace.sh status stale-container /tmp/trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not reference review-bundle-manifest.txt container",
            report["blockers"],
        )

    def test_next_action_commands_must_reference_manifest_trace_log_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                "scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/stale-trace.log",
                "scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/stale-trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not reference review-bundle-manifest.txt traceLog",
            report["blockers"],
        )

    def test_each_replay_runtime_command_must_reference_manifest_trace_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                "scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                "scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/stale-trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not reference review-bundle-manifest.txt traceLog",
            report["blockers"],
        )

    def test_arm_trace_next_action_requires_replay_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload.pop("commands", None)
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json arm-trace action is missing replay commands",
            report["blockers"],
        )

    def test_arm_trace_next_action_requires_replay_arm_and_status_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["commands"] = [
                "scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            missing_arm = self.module.verify_bundle(root)

            payload["commands"] = [
                "scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            missing_status = self.module.verify_bundle(root)

        self.assertFalse(missing_arm["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json arm-trace action is missing replay arm command",
            missing_arm["blockers"],
        )
        self.assertFalse(missing_status["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json arm-trace action is missing replay status command",
            missing_status["blockers"],
        )

    def test_plan_canary_next_action_requires_canary_planning_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = ["true"]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary action is missing plan-ue4ss-canary-env.py command",
            report["blockers"],
        )

    def test_plan_canary_next_action_requires_bundled_promotion_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json /tmp/ue4ss-package-promotion-env.json --format json"
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary command does not reference bundled promotion manifest",
            report["blockers"],
        )

    def test_plan_canary_next_action_accepts_bundled_top_level_promotion_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json"
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertTrue(report["ready"])

    def test_plan_canary_next_action_must_write_bundled_next_canary_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                next_canary_plan(),
            )
            write(root / "ue4ss-package-next-canary.env", "# env\n")
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
                handle.write("artifact=ue4ss-package-next-canary.env source=/tmp/ue4ss-package-next-canary.env\n")
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json >/tmp/stale-next-canary.json",
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json >/tmp/stale-next-canary.env",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary commands do not write bundled next-canary JSON source",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary commands do not write bundled next-canary env source",
            report["blockers"],
        )

    def test_plan_canary_next_action_requires_explicit_output_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                next_canary_plan(),
            )
            write(root / "ue4ss-package-next-canary.env", "# env\n")
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
                handle.write("artifact=ue4ss-package-next-canary.env source=/tmp/ue4ss-package-next-canary.env\n")
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json >/tmp/ue4ss-package-next-canary.json",
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json >/tmp/ue4ss-package-next-canary.env",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary JSON command is missing --format json",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary env command is missing --format env",
            report["blockers"],
        )

    def test_plan_canary_next_action_accepts_bundled_next_canary_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                next_canary_plan(),
            )
            write(root / "ue4ss-package-next-canary.env", "# env\n")
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
                handle.write("artifact=ue4ss-package-next-canary.env source=/tmp/ue4ss-package-next-canary.env\n")
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json >/tmp/ue4ss-package-next-canary.json",
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format env >/tmp/ue4ss-package-next-canary.env",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertTrue(report["ready"])

    def test_plan_canary_next_action_requires_bundled_next_canary_inventory_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                next_canary_plan({"evidenceInventoryJson": "legacy-inventory.json"}),
            )
            write(root / "ue4ss-package-next-canary.env", "# env\n")
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
                handle.write("artifact=ue4ss-package-next-canary.env source=/tmp/ue4ss-package-next-canary.env\n")
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json >/tmp/ue4ss-package-next-canary.json",
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format env >/tmp/ue4ss-package-next-canary.env",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-canary.json postCanaryVerification outputFiles evidenceInventoryJson must be ue4ss-evidence-inventory.json",
            report["blockers"],
        )

    def test_plan_canary_next_action_accepts_output_files_for_bundled_next_canary_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                next_canary_plan(),
            )
            write(root / "ue4ss-package-next-canary.env", "# env\n")
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
                handle.write("artifact=ue4ss-package-next-canary.env source=/tmp/ue4ss-package-next-canary.env\n")
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["outputFiles"] = {
                "nextCanaryJson": "/tmp/ue4ss-package-next-canary.json",
                "nextCanaryEnv": "/tmp/ue4ss-package-next-canary.env",
            }
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json >/tmp/ue4ss-package-next-canary.json",
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format env >/tmp/ue4ss-package-next-canary.env",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertTrue(report["ready"])

    def test_plan_canary_next_action_output_files_do_not_replace_replay_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                next_canary_plan(),
            )
            write(root / "ue4ss-package-next-canary.env", "# env\n")
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
                handle.write("artifact=ue4ss-package-next-canary.env source=/tmp/ue4ss-package-next-canary.env\n")
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["outputFiles"] = {
                "nextCanaryJson": "/tmp/ue4ss-package-next-canary.json",
                "nextCanaryEnv": "/tmp/ue4ss-package-next-canary.env",
            }
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json >/tmp/stale-next-canary.json",
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format env >/tmp/stale-next-canary.env",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary commands do not write bundled next-canary JSON source",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary commands do not write bundled next-canary env source",
            report["blockers"],
        )

    def test_plan_canary_next_action_output_files_must_be_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                next_canary_plan(),
            )
            write(root / "ue4ss-package-next-canary.env", "# env\n")
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
                handle.write("artifact=ue4ss-package-next-canary.env source=/tmp/ue4ss-package-next-canary.env\n")
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["outputFiles"] = "/tmp/ue4ss-package-next-canary.json"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json >/tmp/ue4ss-package-next-canary.json",
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format env >/tmp/ue4ss-package-next-canary.env",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary outputFiles must be an object",
            report["blockers"],
        )

    def test_plan_canary_next_action_output_files_require_bundled_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["outputFiles"] = {
                "nextCanaryJson": "/tmp/ue4ss-package-next-canary.json",
                "nextCanaryEnv": "/tmp/ue4ss-package-next-canary.env",
            }
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary outputFiles nextCanaryJson is present but ue4ss-package-next-canary.json is not bundled",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary outputFiles nextCanaryEnv is present but ue4ss-package-next-canary.env is not bundled",
            report["blockers"],
        )

    def test_plan_canary_next_action_output_files_must_match_bundled_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-next-canary.json",
                next_canary_plan(),
            )
            write(root / "ue4ss-package-next-canary.env", "# env\n")
            manifest = root / "review-bundle-manifest.txt"
            with manifest.open("a", encoding="utf-8") as handle:
                handle.write("artifact=ue4ss-package-next-canary.json source=/tmp/ue4ss-package-next-canary.json\n")
                handle.write("artifact=ue4ss-package-next-canary.env source=/tmp/ue4ss-package-next-canary.env\n")
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["outputFiles"] = {
                "nextCanaryJson": "/tmp/stale-next-canary.json",
                "nextCanaryEnv": "/tmp/stale-next-canary.env",
            }
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format json >/tmp/ue4ss-package-next-canary.json",
                "scripts/plan-ue4ss-canary-env.py --package-promotion-json ue4ss-package-promotion-env.json --format env >/tmp/ue4ss-package-next-canary.env",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary outputFiles nextCanaryJson does not match bundled next-canary JSON source",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary outputFiles nextCanaryEnv does not match bundled next-canary env source",
            report["blockers"],
        )

    def test_plan_canary_next_action_accepts_absolute_bundled_promotion_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                f"scripts/plan-ue4ss-canary-env.py --package-promotion-json {root / 'ue4ss-package-promotion-env.json'} --format json"
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertTrue(report["ready"])

    def test_plan_canary_next_action_accepts_bundled_promotion_dir_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-dir ue4ss-package-family-reviews --format json"
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertTrue(report["ready"])

    def test_plan_canary_next_action_rejects_external_promotion_dir_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["action"] = "plan-canary"
            payload["commands"] = [
                "scripts/plan-ue4ss-canary-env.py --package-promotion-dir /tmp/ue4ss-package-family-reviews --format json"
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json plan-canary command does not reference bundled promotion directory",
            report["blockers"],
        )

    def test_non_default_manifest_process_pattern_must_be_in_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace(
                "processPattern=DuneSandboxServer-Linux-Shipping",
                "processPattern=ExampleGame-Linux-Shipping",
            )
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv is missing DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN for non-default review-bundle processPattern",
            report["blockers"],
        )

    def test_next_action_commands_must_include_process_pattern_trace_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace(
                "processPattern=DuneSandboxServer-Linux-Shipping",
                "processPattern=ExampleGame-Linux-Shipping",
            )
            write(manifest_path, text)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN"] = "ExampleGame-Linux-Shipping"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not include traceEnv DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN from next action traceEnv",
            report["blockers"],
        )

    def test_manifest_trace_pid_must_be_in_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("processPattern=DuneSandboxServer-Linux-Shipping", "processPattern=DuneSandboxServer-Linux-Shipping\ntracePid=123")
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv is missing DUNE_UE4SS_PACKAGE_TRACE_PID for review-bundle-manifest.txt tracePid",
            report["blockers"],
        )

    def test_manifest_trace_pid_must_be_numeric(self):
        for trace_pid in ("not-a-pid", "0", "\u0660"):
            with self.subTest(trace_pid=trace_pid):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    manifest_path = root / "review-bundle-manifest.txt"
                    text = manifest_path.read_text(encoding="utf-8")
                    text = text.replace(
                        "processPattern=DuneSandboxServer-Linux-Shipping",
                        f"processPattern=DuneSandboxServer-Linux-Shipping\ntracePid={trace_pid}",
                    )
                    write(manifest_path, text)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    "review-bundle-manifest.txt tracePid must be numeric",
                    report["blockers"],
                )

    def test_next_action_trace_pid_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("processPattern=DuneSandboxServer-Linux-Shipping", "processPattern=DuneSandboxServer-Linux-Shipping\ntracePid=123")
            write(manifest_path, text)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PID"] = "1234"
            payload["commands"] = [
                "DUNE_UE4SS_PACKAGE_TRACE_PID=1234 scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                "DUNE_UE4SS_PACKAGE_TRACE_PID=1234 scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv DUNE_UE4SS_PACKAGE_TRACE_PID does not match review-bundle-manifest.txt tracePid",
            report["blockers"],
        )

    def test_manifest_trace_pid_must_match_runtime_evidence_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace(
                "processPattern=DuneSandboxServer-Linux-Shipping",
                "processPattern=DuneSandboxServer-Linux-Shipping\ntracePid=999",
            )
            write(manifest_path, text)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PID"] = "999"
            payload["commands"] = [
                (
                    "DUNE_UE4SS_PACKAGE_TRACE_PID=999 "
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject "
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 "
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage "
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto "
                    "scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log"
                ),
                (
                    "DUNE_UE4SS_PACKAGE_TRACE_PID=999 "
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject "
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 "
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage "
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto "
                    "scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log"
                ),
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt tracePid does not match runtime trace evidence pid",
            report["blockers"],
        )

    def test_next_action_commands_must_include_trace_pid_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("processPattern=DuneSandboxServer-Linux-Shipping", "processPattern=DuneSandboxServer-Linux-Shipping\ntracePid=123")
            write(manifest_path, text)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PID"] = "123"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not include traceEnv DUNE_UE4SS_PACKAGE_TRACE_PID from next action traceEnv",
            report["blockers"],
        )

    def test_manifest_trace_host_must_be_in_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"].pop("DUNE_UE4SS_PACKAGE_TRACE_HOST", None)
            payload["commands"] = [
                command.replace("DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0 ", "")
                for command in payload["commands"]
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv is missing DUNE_UE4SS_PACKAGE_TRACE_HOST for review-bundle-manifest.txt traceHost",
            report["blockers"],
        )

    def test_next_action_trace_host_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_HOST"] = "other-host"
            payload["commands"] = [
                "DUNE_UE4SS_PACKAGE_TRACE_HOST=other-host scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                "DUNE_UE4SS_PACKAGE_TRACE_HOST=other-host scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log",
            ]
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv DUNE_UE4SS_PACKAGE_TRACE_HOST does not match review-bundle-manifest.txt traceHost",
            report["blockers"],
        )

    def test_next_action_commands_must_include_trace_host_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("container=dune_server-deep-desert-1", "container=dune_server-deep-desert-1\ntraceHost=example-host")
            write(manifest_path, text)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_HOST"] = "example-host"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json commands do not include traceEnv DUNE_UE4SS_PACKAGE_TRACE_HOST from next action traceEnv",
            report["blockers"],
        )

    def test_next_action_trace_env_rejects_unplanned_keys_even_when_commands_omit_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            next_action_path = root / "ue4ss-package-next-action.json"
            payload = json.loads(next_action_path.read_text(encoding="utf-8"))
            payload["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_STALE_FLAG"] = "1"
            write(next_action_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-next-action.json traceEnv DUNE_UE4SS_PACKAGE_TRACE_STALE_FLAG is not present in runtime trace plan",
            report["blockers"],
        )

    def test_manifest_trace_labels_must_match_trace_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("signatureFamily=LoadPackage", "signatureFamily=StaticLoadClass")
            text = text.replace("hitIndex=auto", "hitIndex=1")
            text = text.replace("traceLog=/tmp/trace.log", "traceLog=/tmp/stale-trace.log")
            text = text.replace("sourceLogExists=True", "sourceLogExists=False")
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt signatureFamily does not match runtime trace plan",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt hitIndex does not match runtime trace plan",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt traceLog does not match runtime trace evidence sourceLog",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt sourceLogExists does not match runtime trace evidence sourceLogExists",
            report["blockers"],
        )

    def test_manifest_must_include_trace_pid_match_provenance_when_evidence_has_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            lines = [
                line
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
                if not line.startswith("tracePidMatchesRequested=")
            ]
            write(manifest_path, "\n".join(lines) + "\n")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt tracePidMatchesRequested is missing for runtime trace evidence tracePidMatchesRequested",
            report["blockers"],
        )

    def test_manifest_trace_plan_provenance_must_match_copied_trace_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("tracePlanSourceExternalPlan=/tmp/external-plan.json", "tracePlanSourceExternalPlan=/tmp/stale-plan.json")
            text = text.replace(
                "tracePlanPromotionAcceptanceSchema=dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "tracePlanPromotionAcceptanceSchema=old-schema",
            )
            text = text.replace("tracePlanBase=0x100000", "tracePlanBase=0x200000")
            text = text.replace("tracePlanExpectedBuildId=abc123", "tracePlanExpectedBuildId=stale123")
            text = text.replace("tracePlanRuntimeBuildId=abc123", "tracePlanRuntimeBuildId=stale456")
            text = text.replace("tracePlanSeedCount=2", "tracePlanSeedCount=99")
            text = text.replace("tracePlanSeedOffsets=LoadPackage@0x5ae6260,LoadObject@0x814c33", "tracePlanSeedOffsets=LoadPackage@0xdead")
            text = text.replace("tracePlanSelectedByFamily=LoadObject:1,LoadPackage:1", "tracePlanSelectedByFamily=LoadPackage:2")
            text = text.replace("tracePlanBlockerCount=0", "tracePlanBlockerCount=1")
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt tracePlanSourceExternalPlan does not match runtime trace plan sourceExternalPlan",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanPromotionAcceptanceSchema does not match runtime trace plan sourcePromotionAcceptanceSchemaVersion",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanBase does not match runtime trace plan base",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanExpectedBuildId does not match runtime trace plan expectedBuildId",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanRuntimeBuildId does not match runtime trace plan runtimeBuildId",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanSeedCount does not match runtime trace plan seedCount",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanSeedOffsets does not match runtime trace plan seeds",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanSelectedByFamily does not match runtime trace plan seedSelection selectedByFamily",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanBlockerCount does not match runtime trace plan blockers",
            report["blockers"],
        )

    def test_trace_plan_build_ids_must_have_safe_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["expectedBuildId"] = "abc 123"
            plan["runtimeBuildId"] = "../abc"
            write(plan_path, plan)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("tracePlanExpectedBuildId=abc123", "tracePlanExpectedBuildId=abc 123")
            text = text.replace("tracePlanRuntimeBuildId=abc123", "tracePlanRuntimeBuildId=../abc")
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json expectedBuildId must be hex, empty, or unknown",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json runtimeBuildId must be hex, empty, or unknown",
            report["blockers"],
        )

    def test_trace_plan_requires_current_promotion_acceptance_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["sourcePromotionAcceptanceSchemaVersion"] = "old-schema"
            write(plan_path, plan)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace(
                "tracePlanPromotionAcceptanceSchema=dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "tracePlanPromotionAcceptanceSchema=old-schema",
            )
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json sourcePromotionAcceptanceSchemaVersion must be dune-ue4ss-package-anchor-promotion-acceptance/v1",
            report["blockers"],
        )

    def test_runtime_trace_evidence_must_match_bundled_trace_plan_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["sourceTracePlanSchemaVersion"] = "old-plan-schema"
            evidence["sourcePromotionAcceptanceSchemaVersion"] = "old-acceptance-schema"
            evidence["sourceExternalPlan"] = "/tmp/stale-external-plan.json"
            evidence["sourceTracePlan"] = "/tmp/stale-runtime-trace-plan.json"
            write(evidence_path, evidence)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json sourceTracePlanSchemaVersion does not match runtime trace plan schemaVersion",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json sourcePromotionAcceptanceSchemaVersion does not match runtime trace plan sourcePromotionAcceptanceSchemaVersion",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json sourceExternalPlan does not match runtime trace plan sourceExternalPlan",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json sourceTracePlan does not reference bundled runtime trace plan artifact",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-runtime-trace-evidence.json sourceTracePlan does not match bundled runtime trace plan artifact source",
            report["blockers"],
        )

    def test_manifest_source_trace_plan_must_match_evidence_and_artifact_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace(
                "sourceTracePlan=/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlan=/tmp/stale-runtime-trace-plan.json",
            )
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt sourceTracePlan does not match runtime trace evidence sourceTracePlan",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt sourceTracePlan does not match bundled runtime trace plan artifact source",
            report["blockers"],
        )

    def test_trace_plan_blockers_must_be_string_list(self):
        cases = (
            ("not-array", "ue4ss-package-runtime-trace-plan.json blockers blockers must be a JSON array"),
            ([42], "ue4ss-package-runtime-trace-plan.json blockers blockers[0] must be a string"),
        )
        for blockers, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
                    payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
                    payload["blockers"] = blockers
                    write(trace_plan_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(message, report["blockers"])

    def test_trace_plan_seed_count_must_be_non_negative_integer(self):
        for seed_count in ({"count": 2}, True, -1):
            with self.subTest(seed_count=seed_count):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
                    payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
                    payload["seedCount"] = seed_count
                    write(trace_plan_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    "ue4ss-package-runtime-trace-plan.json seedCount must be a non-negative integer",
                    report["blockers"],
                )

    def test_trace_plan_selected_by_family_must_be_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
            payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
            payload["seedSelection"]["selectedByFamily"] = ["LoadPackage"]
            write(trace_plan_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-runtime-trace-plan.json seedSelection selectedByFamily must be a JSON object",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt tracePlanSelectedByFamily does not match runtime trace plan seedSelection selectedByFamily",
            report["blockers"],
        )

    def test_trace_plan_seeds_must_be_well_formed(self):
        cases = (
            ({"bad": "shape"}, "ue4ss-package-runtime-trace-plan.json seeds must be a JSON array"),
            ([[]], "ue4ss-package-runtime-trace-plan.json seeds[0] must be a JSON object"),
            (
                [{"name": ["LoadPackage"], "address": 1234}],
                "ue4ss-package-runtime-trace-plan.json seeds[0].name must be a string",
            ),
            (
                [{"name": "LoadPackage", "address": 1234}],
                "ue4ss-package-runtime-trace-plan.json seeds[0].address must be a string",
            ),
        )
        for seeds, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    trace_plan_path = root / "ue4ss-package-runtime-trace-plan.json"
                    payload = json.loads(trace_plan_path.read_text(encoding="utf-8"))
                    payload["seeds"] = seeds
                    write(trace_plan_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(message, report["blockers"])
                self.assertIn(
                    "review-bundle-manifest.txt tracePlanSeedOffsets does not match runtime trace plan seeds",
                    report["blockers"],
                )

    def test_manifest_image_provenance_must_match_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace("evidencePid=123", "evidencePid=456")
            text = text.replace("imageRangeSource=pid", "imageRangeSource=arguments")
            text = text.replace("imageBase=0x100000", "imageBase=0x200000")
            text = text.replace("imageStart=0x200000", "imageStart=0x300000")
            text = text.replace("imageEnd=0x7000000", "imageEnd=0x8000000")
            text = text.replace(
                "imagePath=/srv/dune/DuneSandboxServer-Linux-Shipping",
                "imagePath=/tmp/stale/DuneSandboxServer-Linux-Shipping",
            )
            text = text.replace("imagePerms=r-xp", "imagePerms=rw-p")
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt evidencePid does not match runtime trace evidence pid",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt imageRangeSource does not match runtime trace evidence imageRangeSource",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt imageBase does not match runtime trace evidence imageBase",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt imageStart does not match runtime trace evidence imageStart",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt imageEnd does not match runtime trace evidence imageEnd",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt imagePath does not match runtime trace evidence imagePath",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt imagePerms does not match runtime trace evidence imagePerms",
            report["blockers"],
        )

    def test_manifest_digest_provenance_must_match_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            evidence_json_sha256 = file_sha(root / "ue4ss-package-runtime-trace-evidence.json")
            trace_log_sha256 = file_sha(root / "trace.log")
            text = text.replace(f"sourceLogSha256={trace_log_sha256}", "sourceLogSha256=stale-log-sha256")
            text = text.replace(
                f"sourceEvidenceJsonSha256={evidence_json_sha256}",
                "sourceEvidenceJsonSha256=stale-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )
            write(manifest_path, text)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt sourceLogSha256 does not match runtime trace evidence sourceLogSha256",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt sourceEvidenceJsonSha256 does not match bundled runtime trace evidence JSON sha256",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt sourceEvidenceJsonSha256 does not match SHA256SUMS for runtime trace evidence JSON",
            report["blockers"],
        )

    def test_manifest_log_digest_must_match_bundled_trace_log_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            actual_trace_sha256 = self.add_bundled_trace_log_artifact(root)
            manifest_path = root / "review-bundle-manifest.txt"
            text = manifest_path.read_text(encoding="utf-8")
            text = text.replace(f"sourceLogSha256={actual_trace_sha256}", "sourceLogSha256=" + "0" * 64)
            write(manifest_path, text)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt sourceLogSha256 does not match runtime trace evidence sourceLogSha256",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt sourceLogSha256 does not match bundled runtime trace log sha256",
            report["blockers"],
        )
        self.assertIn(
            "review-bundle-manifest.txt sourceLogSha256 does not match SHA256SUMS for runtime trace log",
            report["blockers"],
        )

    def test_manifest_existing_source_log_requires_bundled_trace_log_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            (root / "trace.log").unlink()
            manifest_path = root / "review-bundle-manifest.txt"
            text = "\n".join(
                line
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
                if line != "artifact=trace.log source=/tmp/trace.log"
            )
            write(manifest_path, text + "\n")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "review-bundle-manifest.txt traceLog artifact is missing for existing runtime trace sourceLog",
            report["blockers"],
        )

    def test_invalid_copied_family_summary_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-family-reviews.json",
                {"readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"]},
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json has unsupported schemaVersion",
            report["blockers"],
        )

    def test_non_object_copied_family_summary_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            (root / "ue4ss-package-family-reviews.json").write_text("[]", encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-family-reviews.json must be a JSON object", report["blockers"])

    def test_non_array_copied_family_summary_errors_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "errors": {},
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-family-reviews.json errors must be a JSON array", report["blockers"])

    def test_non_array_copied_family_summary_ready_paths_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": {},
                    "manifests": [],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-family-reviews.json readyManifestPaths must be a JSON array", report["blockers"])

    def test_non_array_copied_family_summary_manifests_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": [],
                    "manifests": {},
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-family-reviews.json manifests must be a JSON array", report["blockers"])

    def test_non_object_copied_family_summary_manifest_row_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": [],
                    "manifests": [[]],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-family-reviews.json manifest row 0 must be a JSON object", report["blockers"])

    def test_non_object_bundled_review_priority_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            priority_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "review-priority.json"
            priority_path.write_text("[]", encoding="utf-8")
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews/LoadPackage/review-priority.json must be a JSON object",
            report["blockers"],
        )

    def test_copied_family_summary_ready_row_must_match_bundled_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadObject",
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x6000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row selectedHitSeed does not match bundled promotion manifest",
            report["blockers"],
        )

    def test_copied_family_summary_target_identity_must_match_bundled_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "tracePid": 4242,
                    "imageRangeSource": "pid",
                    "imageBase": "0x100000",
                    "imageStart": "0x200000",
                    "imageEnd": "0x7000000",
                    "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
                    "imagePerms": "r-xp",
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            row = {
                "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                "tracePid": 9999,
                "imageRangeSource": "arguments",
                "imageBase": "0x200000",
                "imageStart": "0x300000",
                "imageEnd": "0x8000000",
                "imagePath": "/tmp/stale/DuneSandboxServer-Linux-Shipping",
                "imagePerms": "rw-p",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "classRootReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
            }
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": [row["path"]],
                    "manifests": [row],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row tracePid does not match bundled promotion manifest",
            report["blockers"],
        )

    def test_copied_family_summary_duplicate_ready_paths_block_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            ready_path = "/tmp/stale-family-reviews/LoadPackage/promotion-env.json"
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": [ready_path, ready_path],
                    "manifests": [
                        {
                            "path": ready_path,
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json duplicate readyManifestPaths entry",
            report["blockers"],
        )

    def test_copied_family_summary_duplicate_ready_rows_block_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            ready_path = "/tmp/stale-family-reviews/LoadPackage/promotion-env.json"
            ready_row = {
                "path": ready_path,
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "classRootReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
            }
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": [ready_path],
                    "manifests": [ready_row, dict(ready_row)],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json duplicate ready package promotion summary row",
            report["blockers"],
        )

    def test_copied_family_summary_ready_row_must_be_listed_in_ready_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": [],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row is missing from readyManifestPaths",
            report["blockers"],
        )

    def test_copied_family_summary_ready_row_with_blockers_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                            "blockers": ["manual blocker left behind"],
                            "missingReviewFlags": ["--reviewed-abi"],
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row still has blockers",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row still has missing review flags",
            report["blockers"],
        )

    def test_copied_family_summary_ready_row_malformed_lists_block_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": True,
                    "nativeInvokeEnabled": True,
                    "finalNativeCallConfirmed": True,
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "sourceEvidence": "/tmp/trace.log",
                            "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": True,
                            "nativeInvokeEnabled": True,
                            "finalNativeCallConfirmed": True,
                            "blockers": {},
                            "missingReviewFlags": [False],
                            "abiReviewBlockers": {},
                            "missingNativeInvokeFlags": [False],
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row blockers must be a JSON array",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row missingReviewFlags[0] must be a string",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row abiReviewBlockers must be a JSON array",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row missingNativeInvokeFlags[0] must be a string",
            report["blockers"],
        )

    def test_copied_family_summary_row_missing_source_log_file_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": False,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "blockers": [],
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "sourceEvidence": "/tmp/trace.log",
                            "sourceLogExists": False,
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row sourceLog does not exist",
            report["blockers"],
        )

    def test_copied_family_summary_row_missing_source_log_exists_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "blockers": [],
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "sourceEvidence": "/tmp/trace.log",
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row is missing sourceLogExists",
            report["blockers"],
        )

    def test_copied_family_summary_row_missing_trace_pid_match_provenance_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "sourceEvidence": "/tmp/trace.log",
                            "sourceLogExists": True,
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row is missing runtime trace PID match provenance",
            report["blockers"],
        )

    def test_copied_family_summary_row_identity_fields_must_be_single_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "blockers": [],
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "sourceEvidence": "/tmp/trace.log\nstale",
                            "sourceLogExists": True,
                            "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping\nold",
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row sourceEvidence must be a non-empty single-line value",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row imagePath must be a non-empty single-line value",
            report["blockers"],
        )

    def test_copied_family_summary_row_requires_concrete_non_negative_hit_index(self):
        for hit_index in ("auto", True, -1):
            with self.subTest(hit_index=hit_index):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
                    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
                    payload.update(
                        {
                            "sourceEvidence": "/tmp/trace.log",
                            "sourceLogExists": True,
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                            "blockers": [],
                        }
                    )
                    write(promotion_path, payload)
                    write(
                        root / "ue4ss-package-family-reviews.json",
                        {
                            "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                            "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                            "manifests": [
                                {
                                    "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                                    "signatureFamily": "LoadPackage",
                                    "sourceEvidence": "/tmp/trace.log",
                                    "sourceLogExists": True,
                                    "hitIndex": hit_index,
                                    "selectedHitSeed": "LoadPackage",
                                    "callerImageOffset": "0x5000",
                                    "ripImageOffset": "0x4ff0",
                                    "readyForNonInvokingCanary": True,
                                    "targetImageReviewed": True,
                                    "tcharReviewed": True,
                                    "classRootReviewed": True,
                                    "abiReviewReady": True,
                                    "abiReviewed": True,
                                    "readyForNativeInvoke": False,
                                }
                            ],
                        },
                    )
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    "ue4ss-package-family-reviews.json ready summary row is missing concrete hitIndex",
                    report["blockers"],
                )

    def test_copied_family_summary_row_rejects_stale_session_flags(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
                    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
                    payload.update(
                        {
                            "sourceEvidence": "/tmp/trace.log",
                            "sourceLogExists": True,
                            "tracePidMatchesRequested": stale_value,
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                            "blockers": [],
                            "hit": {
                                "seed": "LoadPackage",
                                "callerImageOffset": "0x5000",
                                "ripImageOffset": "0x4ff0",
                                "traceAddressMatchesBase": True,
                                "traceLogHasArmed": stale_value,
                                "tracePidMatchesRequested": stale_value,
                            },
                        }
                    )
                    write(promotion_path, payload)
                    row = {
                        "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                        "signatureFamily": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceLogExists": True,
                        "tracePidMatchesRequested": stale_value,
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "readyForNonInvokingCanary": True,
                        "targetImageReviewed": True,
                        "tcharReviewed": True,
                        "classRootReviewed": True,
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNativeInvoke": False,
                        "hit": {
                            "seed": "LoadPackage",
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "traceAddressMatchesBase": True,
                            "traceLogHasArmed": stale_value,
                            "tracePidMatchesRequested": stale_value,
                        },
                    }
                    write(
                        root / "ue4ss-package-family-reviews.json",
                        {
                            "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                            "readyManifestPaths": [row["path"]],
                            "manifests": [row],
                        },
                    )
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    "ue4ss-package-family-reviews.json ready summary row trace log armed PID does not match requested runtime PID",
                    report["blockers"],
                )
                self.assertIn(
                    "ue4ss-package-family-reviews.json ready summary row embedded trace hit missing trace armed record; cannot prove runtime trace session",
                    report["blockers"],
                )
                self.assertIn(
                    "ue4ss-package-family-reviews.json ready summary row embedded trace hit trace log armed PID does not match requested runtime PID",
                    report["blockers"],
                )

    def test_copied_family_summary_row_rejects_missing_embedded_address_base_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "tracePidMatchesRequested": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "blockers": [],
                    "hit": {
                        "seed": "LoadPackage",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "traceAddressMatchesBase": True,
                        "traceLogHasArmed": True,
                        "tracePidMatchesRequested": True,
                    },
                }
            )
            write(promotion_path, payload)
            row = {
                "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                "signatureFamily": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                "tracePidMatchesRequested": True,
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "classRootReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
                "hit": {
                    "seed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "traceLogHasArmed": True,
                    "tracePidMatchesRequested": True,
                },
            }
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": [row["path"]],
                    "manifests": [row],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row embedded trace hit address does not match image base plus seed imageOffset",
            report["blockers"],
        )

    def test_copied_family_summary_row_env_keys_must_match_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                            "env": {
                                "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                            },
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json LoadPackage ready summary row env includes LoadClass package keys",
            report["blockers"],
        )

    def test_copied_family_summary_selected_seed_must_match_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadObject",
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row selectedHitSeed does not match bundled promotion manifest",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row selectedHitSeed does not match signatureFamily",
            report["blockers"],
        )

    def test_copied_family_summary_priority_must_match_bundled_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                            "reviewPriority": 9,
                            "reviewPriorityHitIndex": 1,
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row reviewPriority does not match bundled review priority",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row reviewPriorityHitIndex does not match bundled review priority",
            report["blockers"],
        )

    def test_bad_json_schema_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(root / "ue4ss-package-promotion-env.json", {"schemaVersion": "wrong"})
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn("ue4ss-package-promotion-env.json has unsupported schemaVersion", report["blockers"])

    def test_bad_review_priority_metadata_blocks_bundle(self):
        for rank, hit_index in (("0", "bad"), (True, True), (-1, -1)):
            with self.subTest(rank=rank, hit_index=hit_index):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    write(
                        root / "ue4ss-package-family-reviews" / "LoadPackage" / "review-priority.json",
                        {
                            "schemaVersion": "wrong",
                            "rank": rank,
                            "hitIndex": hit_index,
                            "signatureFamily": "StaticLoadClass",
                        },
                    )
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                rel = "ue4ss-package-family-reviews/LoadPackage/review-priority.json"
                self.assertFalse(report["ready"])
                self.assertIn(f"{rel} has unsupported schemaVersion", report["blockers"])
                self.assertIn(f"{rel} has invalid rank", report["blockers"])
                self.assertIn(f"{rel} has invalid hitIndex", report["blockers"])
                self.assertIn(f"{rel} signatureFamily does not match parent directory", report["blockers"])
                self.assertIn(f"{rel} signatureFamily does not match promotion manifest", report["blockers"])

    def test_bad_bundled_promotion_env_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            write(
                root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json",
                {
                    "schemaVersion": "wrong",
                    "signatureFamily": "StaticLoadClass",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(f"{rel} has unsupported schemaVersion", report["blockers"])
        self.assertIn(f"{rel} signatureFamily does not match parent directory", report["blockers"])

    def test_bundled_promotion_env_source_must_match_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/stale-trace.log",
                    "sourceLogExists": False,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(f"{rel} sourceEvidence does not match runtime trace evidence sourceLog", report["blockers"])
        self.assertIn(f"{rel} sourceLogExists does not match runtime trace evidence sourceLogExists", report["blockers"])

    def test_bundled_promotion_env_digest_must_match_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload["sourceEvidenceJsonSha256"] = "stale-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} sourceEvidenceJsonSha256 does not match runtime trace evidence sourceEvidenceJsonSha256",
            report["blockers"],
        )

    def test_bundled_promotion_env_offsets_must_match_selected_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0xdeadbeef",
                    "ripImageOffset": "0x4ff0",
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(f"{rel} callerImageOffset does not match selected runtime trace hit", report["blockers"])

    def test_bundled_promotion_selected_hit_must_match_trace_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence_payload["hits"][0]["traceAddressMatchesBase"] = False
            write(evidence_path, evidence_payload)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                }
            )
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} selected runtime trace hit address does not match image base plus seed imageOffset",
            report["blockers"],
        )

    def test_bundled_promotion_selected_hit_requires_trace_base_match_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence_payload["hits"][0].pop("traceAddressMatchesBase", None)
            write(evidence_path, evidence_payload)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                }
            )
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} selected runtime trace hit address does not match image base plus seed imageOffset",
            report["blockers"],
        )

    def test_bundled_promotion_selected_hit_requires_memory_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence_payload["hits"][0]["missingRequiredMemoryRegisters"] = ["rsi"]
            write(evidence_path, evidence_payload)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                }
            )
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} selected runtime trace hit is missing required memory registers: rsi",
            report["blockers"],
        )

    def test_bundled_promotion_selected_hit_rejects_malformed_missing_required_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence_payload["hits"][0]["missingRequiredMemoryRegisters"] = "rsi"
            write(evidence_path, evidence_payload)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                }
            )
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} selected runtime trace hit missingRequiredMemoryRegisters must be a JSON array",
            report["blockers"],
        )

    def test_bundled_promotion_selected_hit_rejects_malformed_registers(self):
        cases = (
            (["not-object"], "registers must be a JSON object"),
            ({"": "0x0"}, "registers contains an invalid register key"),
            ({"rsi": 42}, "registers.rsi must be a string"),
        )
        for registers, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
                    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                    evidence_payload["hits"][0]["registers"] = registers
                    write(evidence_path, evidence_payload)
                    promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
                    promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
                    promotion_payload.update(
                        {
                            "sourceEvidence": "/tmp/trace.log",
                            "sourceLogExists": True,
                            "hitIndex": 0,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                        }
                    )
                    write(promotion_path, promotion_payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
                self.assertFalse(report["ready"])
                self.assertIn(f"{rel} selected runtime trace hit {message}", report["blockers"])

    def test_bundled_promotion_selected_hit_rejects_malformed_register_memory(self):
        cases = (
            (["not-object"], "registerMemory must be a JSON object"),
            ({"": ["0x3:\t0x2f"]}, "registerMemory contains an invalid register key"),
            ({"rsi": "0x3:\t0x2f"}, "registerMemory.rsi must be a JSON array"),
            ({"rsi": ["0x3:\t0x2f", 42]}, "registerMemory.rsi[1] must be a string"),
        )
        for register_memory, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
                    evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                    evidence_payload["hits"][0]["registerMemory"] = register_memory
                    write(evidence_path, evidence_payload)
                    promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
                    promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
                    promotion_payload.update(
                        {
                            "sourceEvidence": "/tmp/trace.log",
                            "sourceLogExists": True,
                            "hitIndex": 0,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                        }
                    )
                    write(promotion_path, promotion_payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
                self.assertFalse(report["ready"])
                self.assertIn(f"{rel} selected runtime trace hit {message}", report["blockers"])

    def test_ready_bundled_promotion_with_blockers_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": ["manual blocker left behind"],
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(f"{rel} ready package promotion manifest still has blockers", report["blockers"])

    def test_ready_bundled_promotion_malformed_list_fields_block_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": "manual blocker left behind",
                    "missingReviewFlags": ["--reviewed-abi", 42],
                    "missingNativeInvokeFlags": "--allow-native-invoke",
                    "abiReview": {"ready": True, "blockers": [{"message": "bad role"}]},
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(f"{rel} blockers must be a JSON array", report["blockers"])
        self.assertIn(f"{rel} missingReviewFlags[1] must be a string", report["blockers"])
        self.assertIn(f"{rel} missingNativeInvokeFlags must be a JSON array", report["blockers"])
        self.assertIn(f"{rel} abiReview.blockers[0] must be a string", report["blockers"])

    def test_ready_bundled_promotion_embedded_abi_identity_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "tracePid": 4242,
                    "imageRangeSource": "pid",
                    "imageBase": "0x100000",
                    "imageStart": "0x200000",
                    "imageEnd": "0x7000000",
                    "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
                    "imagePerms": "r-xp",
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "signatureFamily": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "blockers": [],
                    "missingReviewFlags": [],
                    "missingNativeInvokeFlags": [],
                    "abiReview": {
                        "ready": True,
                        "blockers": [],
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceLogExists": True,
                        "tracePid": 9999,
                        "imageRangeSource": "pid",
                        "imageBase": "0x100000",
                        "imageStart": "0x200000",
                        "imageEnd": "0x7000000",
                        "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
                        "imagePerms": "r-xp",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "signatureFamily": "LoadPackage",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} abiReview.tracePid does not match promotion manifest tracePid",
            report["blockers"],
        )

    def test_ready_bundled_promotion_malformed_abi_argument_memory_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "abiReview": {
                        "ready": True,
                        "blockers": [],
                        "arguments": [
                            {"memory": {"lineCount": "many", "hints": []}},
                            {"memory": []},
                        ],
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} abiReview.arguments[0].memory.lineCount must be a non-negative integer",
            report["blockers"],
        )
        self.assertIn(
            f"{rel} abiReview.arguments[0].memory.hints must be a JSON object",
            report["blockers"],
        )
        self.assertIn(
            f"{rel} abiReview.arguments[1].memory must be a JSON object",
            report["blockers"],
        )

    def test_ready_top_level_promotion_missing_rip_offset_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "callerImageOffset": "0x5000",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                }
            )
            payload.pop("ripImageOffset", None)
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest is missing ripImageOffset",
            report["blockers"],
        )

    def test_ready_top_level_promotion_missing_trace_identity_blocks_bundle(self):
        for hit_index in ("auto", True, -1):
            with self.subTest(hit_index=hit_index):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    promotion_path = root / "ue4ss-package-promotion-env.json"
                    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
                    payload.update(
                        {
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "blockers": [],
                        }
                    )
                    payload.pop("sourceEvidence", None)
                    payload["hitIndex"] = hit_index
                    payload.pop("selectedHitSeed", None)
                    write(promotion_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    "ue4ss-package-promotion-env.json ready package promotion manifest is missing sourceEvidence",
                    report["blockers"],
                )
                self.assertIn(
                    "ue4ss-package-promotion-env.json ready package promotion manifest is missing concrete hitIndex",
                    report["blockers"],
                )
                self.assertIn(
                    "ue4ss-package-promotion-env.json ready package promotion manifest is missing selectedHitSeed",
                    report["blockers"],
                )

    def test_ready_top_level_promotion_embedded_hit_must_match_trace_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "hit": {
                        "seed": "LoadPackage",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "traceAddressMatchesBase": False,
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json embedded trace hit address does not match image base plus seed imageOffset",
            report["blockers"],
        )

    def test_ready_top_level_promotion_rejects_stale_session_flags(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    promotion_path = root / "ue4ss-package-promotion-env.json"
                    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
                    payload.update(
                        {
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "tracePidMatchesRequested": stale_value,
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "blockers": [],
                            "hit": {
                                "seed": "LoadPackage",
                                "callerImageOffset": "0x5000",
                                "ripImageOffset": "0x4ff0",
                                "traceAddressMatchesBase": True,
                                "traceLogHasArmed": stale_value,
                                "tracePidMatchesRequested": stale_value,
                            },
                        }
                    )
                    write(promotion_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    "ue4ss-package-promotion-env.json trace log armed PID does not match requested runtime PID",
                    report["blockers"],
                )
                self.assertIn(
                    "ue4ss-package-promotion-env.json embedded trace hit missing trace armed record; cannot prove runtime trace session",
                    report["blockers"],
                )
                self.assertIn(
                    "ue4ss-package-promotion-env.json embedded trace hit trace log armed PID does not match requested runtime PID",
                    report["blockers"],
                )

    def test_ready_top_level_promotion_missing_source_log_file_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "sourceLogExists": False,
                    "blockers": [],
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest sourceLog does not exist",
            report["blockers"],
        )

    def test_ready_top_level_promotion_missing_source_log_exists_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                }
            )
            payload.pop("sourceLogExists", None)
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest is missing sourceLogExists",
            report["blockers"],
        )

    def test_ready_top_level_promotion_missing_trace_pid_match_provenance_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                }
            )
            payload.pop("tracePidMatchesRequested", None)
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest is missing runtime trace PID match provenance",
            report["blockers"],
        )

    def test_ready_top_level_promotion_missing_trace_pid_blocks_bundle(self):
        for trace_pid in (None, 0):
            with self.subTest(trace_pid=trace_pid):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    promotion_path = root / "ue4ss-package-promotion-env.json"
                    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
                    payload.update(
                        {
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "tracePidMatchesRequested": True,
                            "blockers": [],
                        }
                    )
                    if trace_pid is None:
                        payload.pop("tracePid", None)
                    else:
                        payload["tracePid"] = trace_pid
                    write(promotion_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    "ue4ss-package-promotion-env.json ready package promotion manifest is missing concrete tracePid",
                    report["blockers"],
                )

    def test_ready_top_level_promotion_missing_acceptance_schema_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                }
            )
            payload.pop("promotionAcceptanceSchemaVersion", None)
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest is missing current package promotion acceptance schema",
            report["blockers"],
        )

    def test_ready_top_level_promotion_missing_abi_review_flags_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "blockers": [],
                }
            )
            payload.pop("abiReviewReady", None)
            payload.pop("abiReviewed", None)
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest is missing ABI review readiness",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest is missing reviewed ABI confirmation",
            report["blockers"],
        )

    def test_ready_top_level_promotion_embedded_hit_identity_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "hit": {
                        "seed": "LoadObject",
                        "callerImageOffset": "0x6000",
                        "ripImageOffset": "0x5ff0",
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json selectedHitSeed does not match embedded trace hit seed",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json embedded trace hit seed does not match signatureFamily",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json embedded trace hit callerImageOffset does not match manifest",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json embedded trace hit ripImageOffset does not match manifest",
            report["blockers"],
        )

    def test_ready_top_level_promotion_embedded_hit_requires_memory_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "hit": {
                        "seed": "LoadPackage",
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "traceAddressMatchesBase": True,
                        "missingRequiredMemoryRegisters": ["rsi"],
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json embedded trace hit is missing required memory registers: rsi",
            report["blockers"],
        )

    def test_ready_top_level_promotion_malformed_abi_argument_memory_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "abiReview": {
                        "ready": True,
                        "blockers": [],
                        "arguments": [{"memory": {"lineCount": -1}}],
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json abiReview.arguments[0].memory.lineCount must be a non-negative integer",
            report["blockers"],
        )

    def test_ready_top_level_promotion_seed_must_match_family_without_embedded_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadObject",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json selectedHitSeed does not match signatureFamily",
            report["blockers"],
        )

    def test_ready_native_top_level_promotion_requires_non_invoking_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": False,
                    "readyForNativeInvoke": True,
                    "nativeInvokeEnabled": True,
                    "finalNativeCallConfirmed": True,
                    "missingReviewFlags": [],
                    "missingNativeInvokeFlags": [],
                    "blockers": [],
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready native package promotion manifest is missing non-invoking canary readiness",
            report["blockers"],
        )

    def test_ready_family_promotion_missing_source_log_file_blocks_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "sourceLogExists": False,
                    "blockers": [],
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} ready package promotion manifest sourceLog does not exist",
            report["blockers"],
        )

    def test_copied_family_summary_runtime_trace_env_evidence_must_match_call_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                            "env": {
                                "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:caller=0x5000 rip=0x5ff0",
                            },
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json env evidence rip does not match ripImageOffset",
            report["blockers"],
        )

    def test_copied_family_summary_requires_runtime_trace_env_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "readyForNativeInvoke": False,
                    "env": {
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true",
                    },
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "sourceEvidence": "/tmp/trace.log",
                            "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": True,
                            "targetImageReviewed": True,
                            "tcharReviewed": True,
                            "classRootReviewed": True,
                            "abiReviewReady": True,
                            "abiReviewed": True,
                            "readyForNativeInvoke": False,
                            "env": {
                                "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true",
                            },
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready summary row is missing runtime trace env evidence",
            report["blockers"],
        )

    def test_copied_family_summary_native_ready_requires_non_invoking_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": False,
                    "readyForNativeInvoke": True,
                    "nativeInvokeEnabled": True,
                    "finalNativeCallConfirmed": True,
                    "missingReviewFlags": [],
                    "missingNativeInvokeFlags": [],
                    "blockers": [],
                }
            )
            write(promotion_path, payload)
            write(
                root / "ue4ss-package-family-reviews.json",
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                    "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                    "manifests": [
                        {
                            "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                            "signatureFamily": "LoadPackage",
                            "hitIndex": 0,
                            "selectedHitSeed": "LoadPackage",
                            "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "readyForNonInvokingCanary": False,
                            "readyForNativeInvoke": True,
                            "nativeInvokeEnabled": True,
                            "finalNativeCallConfirmed": True,
                            "missingReviewFlags": [],
                            "missingNativeInvokeFlags": [],
                            "blockers": [],
                        }
                    ],
                },
            )
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-family-reviews.json ready native summary row is missing non-invoking canary readiness",
            report["blockers"],
        )

    def test_ready_top_level_promotion_runtime_trace_env_evidence_must_match_call_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:caller=0x5000 rip=0x5ff0",
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence rip does not match ripImageOffset",
            report["blockers"],
        )

    def test_ready_top_level_promotion_requires_hex_image_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "5000",
                    "ripImageOffset": "0xnothex",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                            "runtime-trace:LoadPackage:caller=5000 rip=0xnothex "
                            "pid=123 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                        ),
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest has invalid callerImageOffset",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion manifest has invalid ripImageOffset",
            report["blockers"],
        )

    def test_ready_top_level_promotion_requires_runtime_trace_env_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true",
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json ready package promotion env is missing runtime trace evidence",
            report["blockers"],
        )

    def test_ready_top_level_promotion_runtime_trace_env_provenance_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                            "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0 "
                            "pid=999 evidenceJsonSha256=stale-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=stale-log-sha256"
                        ),
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence pid does not match tracePid",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence digest does not match sourceEvidenceJsonSha256",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence log digest does not match sourceLogSha256",
            report["blockers"],
        )

    def test_ready_top_level_promotion_runtime_trace_env_requires_exact_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                            "runtime-trace:LoadPackage:caller=0x50000 rip=0x4ff00 "
                            "pid=1234 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-stale "
                            "sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-stale"
                        ),
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence caller does not match callerImageOffset",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence rip does not match ripImageOffset",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence pid does not match tracePid",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence digest does not match sourceEvidenceJsonSha256",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence log digest does not match sourceLogSha256",
            report["blockers"],
        )

    def test_ready_top_level_promotion_runtime_trace_env_family_must_match_signature_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadObject:caller=0x5000 rip=0x4ff0",
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence family does not match signatureFamily",
            report["blockers"],
        )

    def test_ready_top_level_promotion_runtime_trace_env_seed_must_match_signature_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "signatureFamily": "LoadPackage",
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:seed=LoadObject caller=0x5000 rip=0x4ff0",
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json env evidence seed does not match signatureFamily",
            report["blockers"],
        )

    def test_ready_top_level_promotion_env_must_be_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "signatureFamily": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": ["DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI=true"],
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json package promotion env must be an object",
            report["blockers"],
        )

    def test_bundled_promotion_env_keys_must_match_signature_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "classRootReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0",
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true",
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(f"{rel} LoadPackage promotion env includes LoadClass package keys", report["blockers"])

    def test_bundled_promotion_env_values_must_be_scalar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "signatureFamily": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": True,
                    "targetImageReviewed": True,
                    "tcharReviewed": True,
                    "abiReviewReady": True,
                    "abiReviewed": True,
                    "blockers": [],
                    "env": {
                        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": {
                            "source": "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0"
                        },
                    },
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} package promotion env contains a non-scalar value",
            "\n".join(report["blockers"]),
        )

    def test_review_priority_hit_index_must_match_bundled_promotion_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            priority_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "review-priority.json"
            priority = json.loads(priority_path.read_text(encoding="utf-8"))
            priority["hitIndex"] = 0
            write(priority_path, priority)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion["hitIndex"] = 1
            write(promotion_path, promotion)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/review-priority.json"
        self.assertFalse(report["ready"])
        self.assertIn(f"{rel} hitIndex does not match promotion manifest", report["blockers"])

    def test_top_level_abi_review_source_must_match_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            payload = json.loads(abi_path.read_text(encoding="utf-8"))
            payload["sourceEvidence"] = "/tmp/stale-trace.log"
            write(abi_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json sourceEvidence does not match runtime trace evidence sourceLog",
            report["blockers"],
        )

    def test_top_level_abi_and_promotion_digest_must_match_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            abi_payload = json.loads(abi_path.read_text(encoding="utf-8"))
            abi_payload["sourceEvidenceJsonSha256"] = "stale-abi-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            write(abi_path, abi_payload)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload["sourceLogSha256"] = "stale-promotion-log-sha256"
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json sourceEvidenceJsonSha256 does not match runtime trace evidence sourceEvidenceJsonSha256",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json sourceLogSha256 does not match runtime trace evidence sourceLogSha256",
            report["blockers"],
        )

    def test_top_level_identity_uses_manifest_provenance_when_evidence_has_no_self_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence_payload.pop("sourceEvidenceJson", None)
            evidence_payload.pop("sourceEvidenceJsonSha256", None)
            write(evidence_path, evidence_payload)
            evidence_sha = self.module.sha256(evidence_path)
            manifest_path = root / "review-bundle-manifest.txt"
            manifest_lines = (
                f"sourceEvidenceJsonSha256={evidence_sha}"
                if line.startswith("sourceEvidenceJsonSha256=")
                else line
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
            )
            write(manifest_path, "\n".join(manifest_lines) + "\n")
            for rel in (
                "ue4ss-package-abi-review.json",
                "ue4ss-package-promotion-env.json",
                "ue4ss-package-family-reviews/LoadPackage/promotion-env.json",
            ):
                payload_path = root / rel
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                payload["sourceEvidenceJsonSha256"] = evidence_sha
                write(payload_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertTrue(report["ready"], report["blockers"])

    def test_top_level_abi_review_missing_source_log_file_blocks_bundle(self):
        for missing_value in (False, "false"):
            with self.subTest(missing_value=missing_value):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    abi_path = root / "ue4ss-package-abi-review.json"
                    payload = json.loads(abi_path.read_text(encoding="utf-8"))
                    payload["sourceLogExists"] = missing_value
                    write(abi_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    "ue4ss-package-abi-review.json sourceLog does not exist",
                    report["blockers"],
                )

    def test_top_level_abi_and_promotion_source_log_exists_must_match_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            abi_payload = json.loads(abi_path.read_text(encoding="utf-8"))
            abi_payload["sourceLogExists"] = False
            write(abi_path, abi_payload)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload["sourceLogExists"] = False
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json sourceLogExists does not match runtime trace evidence sourceLogExists",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json sourceLogExists does not match runtime trace evidence sourceLogExists",
            report["blockers"],
        )

    def test_top_level_abi_and_promotion_target_identity_must_match_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            abi_payload = json.loads(abi_path.read_text(encoding="utf-8"))
            abi_payload["tracePid"] = 9999
            write(abi_path, abi_payload)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload["imagePath"] = "/tmp/stale/DuneSandboxServer-Linux-Shipping"
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json tracePid does not match runtime trace evidence pid",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json imagePath does not match runtime trace evidence imagePath",
            report["blockers"],
        )

    def test_top_level_abi_review_caller_offset_must_match_selected_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            payload = json.loads(abi_path.read_text(encoding="utf-8"))
            payload["callerImageOffset"] = "0xdeadbeef"
            write(abi_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json callerImageOffset does not match selected runtime trace hit",
            report["blockers"],
        )

    def test_top_level_selected_hit_must_match_trace_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            payload["hits"][0]["traceAddressMatchesBase"] = False
            write(evidence_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json selected runtime trace hit address does not match image base plus seed imageOffset",
            report["blockers"],
        )

    def test_top_level_selected_hit_requires_trace_base_match_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            payload["hits"][0].pop("traceAddressMatchesBase", None)
            write(evidence_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json selected runtime trace hit address does not match image base plus seed imageOffset",
            report["blockers"],
        )

    def test_top_level_selected_hit_requires_memory_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            payload["hits"][0]["missingRequiredMemoryRegisters"] = ["rsi"]
            write(evidence_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json selected runtime trace hit is missing required memory registers: rsi",
            report["blockers"],
        )

    def test_top_level_selected_hit_rejects_malformed_registers(self):
        cases = (
            (["not-object"], "registers must be a JSON object"),
            ({"": "0x0"}, "registers contains an invalid register key"),
            ({"rsi": 42}, "registers.rsi must be a string"),
        )
        for registers, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
                    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                    payload["hits"][0]["registers"] = registers
                    write(evidence_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    f"ue4ss-package-abi-review.json selected runtime trace hit {message}",
                    report["blockers"],
                )

    def test_top_level_selected_hit_rejects_malformed_register_memory(self):
        cases = (
            (["not-object"], "registerMemory must be a JSON object"),
            ({"": ["0x3:\t0x2f"]}, "registerMemory contains an invalid register key"),
            ({"rsi": "0x3:\t0x2f"}, "registerMemory.rsi must be a JSON array"),
            ({"rsi": ["0x3:\t0x2f", 42]}, "registerMemory.rsi[1] must be a string"),
        )
        for register_memory, message in cases:
            with self.subTest(message=message):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self.make_bundle(root)
                    evidence_path = root / "ue4ss-package-runtime-trace-evidence.json"
                    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                    payload["hits"][0]["registerMemory"] = register_memory
                    write(evidence_path, payload)
                    self.refresh_checksums(root)
                    report = self.module.verify_bundle(root)

                self.assertFalse(report["ready"])
                self.assertIn(
                    f"ue4ss-package-abi-review.json selected runtime trace hit {message}",
                    report["blockers"],
                )

    def test_top_level_abi_review_selected_hit_seed_must_match_selected_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            payload = json.loads(abi_path.read_text(encoding="utf-8"))
            payload["selectedHitSeed"] = "LoadObject"
            write(abi_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json selectedHitSeed does not match ABI review",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-abi-review.json selectedHitSeed does not match selected runtime trace hit",
            report["blockers"],
        )

    def test_top_level_promotion_offset_must_match_abi_review_even_without_selected_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            abi_payload = json.loads(abi_path.read_text(encoding="utf-8"))
            abi_payload["hitIndex"] = 4
            abi_payload["callerImageOffset"] = "0x5000"
            write(abi_path, abi_payload)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload["hitIndex"] = 4
            promotion_payload["callerImageOffset"] = "0x6000"
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-promotion-env.json callerImageOffset does not match ABI review",
            report["blockers"],
        )

    def test_top_level_concrete_hit_index_must_exist_in_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            abi_payload = json.loads(abi_path.read_text(encoding="utf-8"))
            abi_payload["hitIndex"] = 4
            write(abi_path, abi_payload)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload["hitIndex"] = 4
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json selected runtime trace hit is missing for hitIndex 4",
            report["blockers"],
        )

    def test_bundled_promotion_concrete_hit_index_must_exist_in_trace_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 4,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(f"{rel} selected runtime trace hit is missing for hitIndex 4", report["blockers"])

    def test_top_level_identity_fields_must_be_single_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            abi_path = root / "ue4ss-package-abi-review.json"
            abi_payload = json.loads(abi_path.read_text(encoding="utf-8"))
            abi_payload["sourceEvidence"] = "/tmp/trace.log\nold"
            write(abi_path, abi_payload)
            promotion_path = root / "ue4ss-package-promotion-env.json"
            promotion_payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            promotion_payload["imagePath"] = "/srv/dune/DuneSandboxServer-Linux-Shipping\nold"
            write(promotion_path, promotion_payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        self.assertFalse(report["ready"])
        self.assertIn(
            "ue4ss-package-abi-review.json sourceEvidence must be a non-empty single-line value",
            report["blockers"],
        )
        self.assertIn(
            "ue4ss-package-promotion-env.json imagePath must be a non-empty single-line value",
            report["blockers"],
        )

    def test_bundled_promotion_identity_fields_must_be_single_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            promotion_path = root / "ue4ss-package-family-reviews" / "LoadPackage" / "promotion-env.json"
            payload = json.loads(promotion_path.read_text(encoding="utf-8"))
            payload.update(
                {
                    "sourceEvidence": "/tmp/trace.log",
                    "sourceLogExists": True,
                    "hitIndex": 0,
                    "selectedHitSeed": "LoadPackage",
                    "callerImageOffset": "0x5000\nold",
                    "ripImageOffset": "0x4ff0",
                }
            )
            write(promotion_path, payload)
            self.refresh_checksums(root)
            report = self.module.verify_bundle(root)

        rel = "ue4ss-package-family-reviews/LoadPackage/promotion-env.json"
        self.assertFalse(report["ready"])
        self.assertIn(
            f"{rel} callerImageOffset must be a non-empty single-line value",
            report["blockers"],
        )

    def test_markdown_reports_ready_and_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "missing"
            report = self.module.verify_bundle(root)
            rendered = self.module.markdown(report)

        self.assertIn("# UE4SS Package Review Bundle Verification", rendered)
        self.assertIn("Ready: `false`", rendered)
        self.assertIn("bundle directory does not exist", rendered)


if __name__ == "__main__":
    unittest.main()
