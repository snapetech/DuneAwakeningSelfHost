#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plan-ue4ss-package-next-action.py"
LOAD_PACKAGE_TRACE_EVIDENCE = (
    "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0 "
    "pid=123 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)


def load_module():
    spec = importlib.util.spec_from_file_location("package_next_action", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def remote_trace_command(action, trace_log="/tmp/trace.log"):
    return (
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_HOST=kspls0 "
        "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ALLOW_PLAYERS=false "
        f"scripts/ue4ss-package-remote-trace.sh {action} "
        f"kspls0 dune_server-deep-desert-1 {trace_log}"
    )


def route_gdb(route_address="0x129d58a2", registers=None):
    registers = registers or ["rbx", "r14"]
    register_prints = " ".join(f"{register}=%p" for register in registers)
    register_args = ", ".join(f"${register}" for register in registers)
    lines = [
        "set pagination off",
        'printf "UE4SS_PACKAGE_ROUTE_TRACE armed pid=%d base=0x%lx build_id=%s routes=%d\\n", 123, 0x100000, "abc123", 1',
        "break *0x12ad58a2",
        "commands",
        " silent",
        (
            f' printf "UE4SS_PACKAGE_ROUTE_TRACE_HIT imageOffset={route_address} '
            "addr=0x12ad58a2 rip=%p rdi=%p rsi=%p rdx=%p rcx=%p r8=%p r9=%p "
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
                f'   printf "UE4SS_PACKAGE_ROUTE_VTABLE_BEGIN reg={register}\\n"',
                f"   x/160gx *(void**){'$'}{register}",
                f'   printf "UE4SS_PACKAGE_ROUTE_VTABLE_END reg={register}\\n"',
                "  end",
                " end",
                f' printf "UE4SS_PACKAGE_ROUTE_OBJECT_END reg={register}\\n"',
            ]
        )
    lines.extend([" continue", "end", "continue"])
    return "\n".join(lines) + "\n"


class PackageNextActionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def trace_plan_provenance(self):
        return {
            "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
            "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
            "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
            "sourceExternalPlan": "/tmp/external-plan.json",
            **self.trace_digest_provenance(),
        }

    def trace_digest_provenance(self):
        return {
            "sourceEvidenceJson": "/tmp/ue4ss-package-runtime-trace-evidence.json",
            "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        }

    def write_bundle(self, root, promotion_ready=False, include_trace_plan=True):
        trace_env = {
            "DUNE_UE4SS_PACKAGE_TRACE_HOST": "kspls0",
            "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
            "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2",
            "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
            "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            "DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS": "0x129d58a2",
        }
        route_slot_trace_requirement = {
            "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "routeAddress": "0x129d58a2",
            "reviewField": "routeVtableStaticSlotMatches",
            "requiredSlots": ["0x3a0", "0x3d8"],
            "requiredRegisters": ["rbx", "r14"],
        }
        files = {
            "ue4ss-package-runtime-trace-evidence.json": {
                "schemaVersion": "dune-ue4ss-package-runtime-trace-evidence/v1",
                "sourceLog": "/tmp/trace.log",
                **self.trace_digest_provenance(),
                "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                "pid": 123,
                "tracePidMatchesRequested": True,
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
                **self.trace_digest_provenance(),
                "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                "hitIndex": 0,
                "signatureFamily": "LoadPackage",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForManualAbiReview": promotion_ready,
            },
            "ue4ss-package-promotion-env.json": {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceEvidence": "/tmp/trace.log",
                **self.trace_digest_provenance(),
                "sourceLogExists": True,
                "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "sourceExternalPlan": "/tmp/external-plan.json",
                "tracePidMatchesRequested": True,
                "tracePid": 123,
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForNonInvokingCanary": promotion_ready,
                "abiReviewReady": promotion_ready,
                "abiReviewed": promotion_ready,
                "targetImageReviewed": promotion_ready,
                "tcharReviewed": promotion_ready,
                "readyForNativeInvoke": False,
                "missingReviewFlags": [] if promotion_ready else ["--reviewed-abi"],
                "blockers": [] if promotion_ready else ["reviewed ABI evidence is required"],
                "env": (
                    {
                        "DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true",
                        "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": LOAD_PACKAGE_TRACE_EVIDENCE,
                    }
                    if promotion_ready
                    else {"DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "false"}
                ),
            },
            "ue4ss-package-next-action.json": {
                "schemaVersion": "dune-ue4ss-package-next-action/v1",
                "action": "arm-trace",
                "traceEnv": trace_env,
                "commands": [
                    "DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0 DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0x129d58a2 scripts/ue4ss-package-runtime-trace.sh preflight dune_server-deep-desert-1 /tmp/trace.log",
                    "DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0 DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0x129d58a2 scripts/ue4ss-package-runtime-trace.sh arm dune_server-deep-desert-1 /tmp/trace.log",
                    "DUNE_UE4SS_PACKAGE_TRACE_HOST=kspls0 DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject DUNE_UE4SS_PACKAGE_TRACE_LIMIT=2 DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX=auto DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0x129d58a2 scripts/ue4ss-package-runtime-trace.sh status dune_server-deep-desert-1 /tmp/trace.log",
                ],
                "liveTraceRunbook": {
                    "sourcePath": "/tmp/ue4ss-package-stimulus-trace-runbook.json",
                    "recommendedCandidate": "operator-client-map-entry",
                    "remote": "kspls0",
                    "container": "dune_server-deep-desert-1",
                    "traceLog": "/tmp/trace.log",
                    "coordinatorCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh",
                    "coordinatorFreshPreflightCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                    "coordinatorFreshTraceCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                    "cleanupCommand": remote_trace_command("stop"),
                    "noDebuggerCheckCommand": 'ssh kspls0 \'ps -eo pid,stat,comm,args | grep -E "gdb|ue4ss-package-runtime-trace" | grep -v grep || true; docker top dune_server-deep-desert-1 -eo pid,stat,comm 2>/dev/null | awk \'"\'"\'NR==1 || /DuneSandboxServ/\'"\'"\'\'',
                    "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                    "localReviewSummaryJson": "build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json",
                    "localReviewSummarySchemaVersion": "dune-ue4ss-package-live-stimulus-review-summary/v1",
                    "localReviewSummaryRunbookMode": "default-source-runbook;trace-log-override-effective-runbook",
                    "localReviewSummaryVerificationCommand": "scripts/verify-ue4ss-package-live-stimulus-summary.py build/server-current-anchor-prep/ue4ss-package-live-stimulus-review-summary.json --runbook-json build/server-current-anchor-prep/ue4ss-package-stimulus-trace-runbook.json --next-action-json build/server-current-anchor-prep/ue4ss-package-next-action.json",
                    "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                    "commandCount": 6,
                    "routeSlotTraceRequirement": route_slot_trace_requirement,
                    "operatorWindow": {
                        "maxArmSeconds": 120,
                        "cleanupRequired": True,
                        "sequence": [
                            "preflight",
                            "arm",
                            "operator-client-login-travel-map-entry",
                            "status",
                            "cleanupCommand",
                            "no-debugger-check",
                        ],
                    },
                },
            },
            "ue4ss-package-stimulus-trace-runbook.json": {
                "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
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
                "cleanupCommand": remote_trace_command("stop"),
                "coordinatorCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh",
                "coordinatorFreshPreflightCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                "coordinatorFreshTraceCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                "noDebuggerCheckCommand": 'ssh kspls0 \'ps -eo pid,stat,comm,args | grep -E "gdb|ue4ss-package-runtime-trace" | grep -v grep || true; docker top dune_server-deep-desert-1 -eo pid,stat,comm 2>/dev/null | awk \'"\'"\'NR==1 || /DuneSandboxServ/\'"\'"\'\'',
                "routeSlotTraceRequirement": route_slot_trace_requirement,
                "operatorWindow": {
                    "maxArmSeconds": 120,
                    "cleanupRequired": True,
                    "sequence": [
                        "preflight",
                        "arm",
                        "operator-client-login-travel-map-entry",
                        "status",
                        "cleanupCommand",
                        "no-debugger-check",
                    ],
                },
                "commands": [
                    remote_trace_command("print"),
                    remote_trace_command("preflight"),
                    remote_trace_command("arm"),
                    "operator performs the approved client login/travel/map-entry package-load stimulus",
                    remote_trace_command("status"),
                    remote_trace_command("stop"),
                ],
            },
            "ue4ss-package-runtime-trace-evidence.md": "# evidence\n",
            "ue4ss-package-abi-review.md": "# abi\n",
            "ue4ss-package-promotion-env.md": "# promotion\n",
            "ue4ss-package-next-action.md": "# next\n",
            "trace.log": "trace log bytes\n",
        }
        if include_trace_plan:
            files["ue4ss-package-runtime-trace-plan.json"] = {
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
                "requestedRouteAddresses": ["0x129d58a2"],
                "routeProbes": [
                    {
                        "address": "0x129d58a2",
                        "absoluteAddress": "0x12ad58a2",
                        "promotion": "non-promotable-route-probe",
                    }
                ],
                "routeGdb": route_gdb(),
                "blockers": [],
                "recommendedTraceEnv": trace_env,
            }
            files["ue4ss-package-runtime-trace-plan.md"] = "# plan\n"
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
            "evidencePid=123",
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
        ]
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, dict):
                path.write_text(json.dumps(content, sort_keys=True), encoding="utf-8")
            else:
                path.write_text(content, encoding="utf-8")
            manifest_lines.append(f"artifact={name} source=/tmp/{name}")
        trace_log_sha256 = hashlib.sha256((root / "trace.log").read_bytes()).hexdigest()
        for rel_path in (
            "ue4ss-package-runtime-trace-evidence.json",
            "ue4ss-package-abi-review.json",
            "ue4ss-package-promotion-env.json",
        ):
            path = root / rel_path
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["sourceLogSha256"] = trace_log_sha256
            env = payload.get("env")
            if isinstance(env, dict):
                for key, value in list(env.items()):
                    if isinstance(value, str):
                        env[key] = value.replace(
                            "sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                            f"sourceLogSha256={trace_log_sha256}",
                        )
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        evidence_json_sha256 = hashlib.sha256((root / "ue4ss-package-runtime-trace-evidence.json").read_bytes()).hexdigest()
        manifest_lines.insert(11, f"sourceEvidenceJsonSha256={evidence_json_sha256}")
        manifest_lines = [
            (
                f"sourceLogSha256={trace_log_sha256}"
                if line == "sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                else line
            )
            for line in manifest_lines
        ]
        (root / "review-bundle-manifest.txt").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
        checksum_rows = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                rel = path.relative_to(root).as_posix()
                checksum_rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}")
        (root / "SHA256SUMS").write_text("\n".join(checksum_rows) + "\n", encoding="utf-8")

    def refresh_bundle_checksums(self, root):
        checksum_rows = []
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                rel = path.relative_to(root).as_posix()
                checksum_rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}")
        (root / "SHA256SUMS").write_text("\n".join(checksum_rows) + "\n", encoding="utf-8")

    def write_family_review(self, root, family, rank, promotion_ready=False):
        family_dir = root / "ue4ss-package-family-reviews" / family
        family_dir.mkdir(parents=True, exist_ok=True)
        trace_log_sha256 = hashlib.sha256((root / "trace.log").read_bytes()).hexdigest()
        trace_digest_provenance = dict(self.trace_digest_provenance())
        trace_digest_provenance["sourceLogSha256"] = trace_log_sha256
        (family_dir / "review-priority.json").write_text(
            json.dumps(
                {
                    "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                    "rank": rank,
                    "signatureFamily": family,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (family_dir / "promotion-env.json").write_text(
            json.dumps(
                {
                    "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                    "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                    "sourceEvidence": "/tmp/trace.log",
                    **trace_digest_provenance,
                    "sourceLogExists": True,
                    "sourceTracePlan": "/tmp/ue4ss-package-runtime-trace-plan.json",
                    "sourceTracePlanSchemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                    "sourcePromotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                    "sourceExternalPlan": "/tmp/external-plan.json",
                    "tracePidMatchesRequested": True,
                    "tracePid": 123,
                    "signatureFamily": family,
                    "hitIndex": 0 if promotion_ready else "auto",
                    "selectedHitSeed": family,
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "readyForNonInvokingCanary": promotion_ready,
                    "abiReviewReady": promotion_ready,
                    "abiReviewed": promotion_ready,
                    "targetImageReviewed": promotion_ready,
                    "tcharReviewed": promotion_ready,
                    "classRootReviewed": promotion_ready,
                    "readyForNativeInvoke": False,
                    "missingReviewFlags": [] if promotion_ready else ["--reviewed-abi"],
                    "missingNativeInvokeFlags": ["--allow-native-invoke", "--final-native-call"],
                    "blockers": [] if promotion_ready else [f"{family} review is incomplete"],
                    "abiReview": {
                        "ready": promotion_ready,
                        "blockers": [] if promotion_ready else [f"{family} ABI review blocker"],
                    },
                    "env": (
                        {
                            (
                                "DUNE_PROBE_LOADER_LOAD_CLASS_PACKAGE_ABI_EVIDENCE"
                                if family == "StaticLoadClass"
                                else "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE"
                            ): (
                                f"runtime-trace:{family}:caller=0x5000 rip=0x4ff0 "
                                "pid=123 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
                                f"sourceLogSha256={trace_log_sha256}"
                            ),
                        }
                        if promotion_ready
                        else {}
                    ),
                    "nextStep": "feed promotion env into next lua-dispatch canary"
                    if promotion_ready
                    else "complete manual review",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def test_ready_promotion_summary_plans_canary_with_ready_summary(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        "sourceLogExists": True,
                        **self.trace_plan_provenance(),
                        "tracePidMatchesRequested": True,
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
                            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": LOAD_PACKAGE_TRACE_EVIDENCE,
                        },
                    }
                ],
            }
        )

        self.assertEqual(action["action"], "plan-canary")
        self.assertEqual(action["confidence"], "high")
        self.assertIn("/tmp/families/LoadPackage/promotion-env.json", action["readyManifestPaths"])
        self.assertEqual(
            action["outputFiles"],
            {
                "nextCanaryJson": "/tmp/ue4ss-package-next-canary.json",
                "nextCanaryEnv": "/tmp/ue4ss-package-next-canary.env",
            },
        )
        self.assertIn("--package-promotion-summary-json /tmp/family-summary.json", action["commands"][0])
        self.assertIn("--format json", action["commands"][0])
        self.assertIn("--format env", action["commands"][1])
        self.assertIn(">/tmp/ue4ss-package-next-canary.json", action["commands"][0])
        self.assertIn(">/tmp/ue4ss-package-next-canary.env", action["commands"][1])
        rendered = self.module.markdown(action)
        self.assertIn("Output files:", rendered)
        self.assertIn("`nextCanaryJson=/tmp/ue4ss-package-next-canary.json`", rendered)
        self.assertIn("`nextCanaryEnv=/tmp/ue4ss-package-next-canary.env`", rendered)

    def test_ready_promotion_summary_requires_source_path_before_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        "sourceLogExists": True,
                        "tracePid": 123,
                        "tracePidMatchesRequested": True,
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
                            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                                "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0 "
                                "pid=123 "
                                "evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
                                "sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                            ),
                        },
                    }
                ],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "ready package promotion summary is missing sourcePath",
        )
        self.assertNotIn("readyManifestPaths", action)
        self.assertNotIn("plan-ue4ss-canary-env.py", action["commands"][0])

    def test_ready_promotion_summary_rejects_invalid_canary_output_paths(self):
        base_summary = {
            "sourcePath": "/tmp/family-summary.json",
            "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
            "manifests": [
                {
                    "path": "/tmp/families/LoadPackage/promotion-env.json",
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
        }
        cases = (
            {"next_canary_json": " \t", "message": "next-canary-json must be a non-empty single-line path"},
            {"next_canary_env": "/tmp/next.env\n/tmp/other.env", "message": "next-canary-env must be a non-empty single-line path"},
        )
        for case in cases:
            with self.subTest(message=case["message"]):
                action = self.module.build_action(
                    promotion_summary=base_summary,
                    next_canary_json=case.get("next_canary_json", "/tmp/next.json"),
                    next_canary_env=case.get("next_canary_env", "/tmp/next.env"),
                )

                self.assertEqual(action["action"], "complete-review")
                self.assertEqual(action["commands"], [])
                self.assertIn(case["message"], [row["error"] for row in action["promotionSummaryErrors"]])
                self.assertNotIn("readyManifestPaths", action)

    def test_rejects_invalid_trace_and_canary_log_paths(self):
        trace_plan = {
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            }
        }
        cases = (
            {"trace_log": "", "message": "trace-log must be a non-empty single-line path"},
            {"canary_log": "/tmp/canary.log\n/tmp/other.log", "message": "canary-log must be a non-empty single-line path"},
        )
        for case in cases:
            with self.subTest(message=case["message"]):
                action = self.module.build_action(
                    trace_plan=trace_plan,
                    trace_log=case.get("trace_log", "/tmp/trace.log"),
                    canary_log=case.get("canary_log", "/tmp/canary.log"),
                )

                self.assertEqual(action["action"], "complete-review")
                self.assertEqual(action["commands"], [])
                self.assertIn(case["message"], [row["error"] for row in action["promotionSummaryErrors"]])
                self.assertNotIn("traceEnv", action)

    def test_ready_promotion_summary_requires_trace_pid_for_explicit_target_pid(self):
        base_row = {
            "path": "/tmp/families/LoadPackage/promotion-env.json",
            "signatureFamily": "LoadPackage",
            "hitIndex": 0,
            "selectedHitSeed": "LoadPackage",
            "sourceEvidence": "/tmp/trace.log",
            "sourceLogExists": True,
            **self.trace_plan_provenance(),
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
            "abiReviewBlockers": [],
        }
        cases = (
            ({}, "ready package promotion summary row is missing tracePid for explicit target PID"),
            ({"tracePid": 1234}, "ready package promotion summary row tracePid does not match explicit target PID"),
        )
        for patch, message in cases:
            with self.subTest(message=message):
                row = dict(base_row)
                row.update(patch)
                action = self.module.build_action(
                    promotion_summary={
                        "sourcePath": "/tmp/family-summary.json",
                        "readyManifestPaths": [row["path"]],
                        "manifests": [row],
                    },
                    target_pid="4242",
                )

                self.assertEqual(action["action"], "complete-review")
                self.assertIn(message, [item["error"] for item in action["promotionSummaryErrors"]])

    def test_ready_promotion_summary_allows_matching_explicit_target_pid(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        "sourceLogExists": True,
                        **self.trace_plan_provenance(),
                        "tracePidMatchesRequested": True,
                        "tracePid": 4242,
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
                        "abiReviewBlockers": [],
                        "env": {
                            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                                "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0 "
                                "pid=4242 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                            ),
                        },
                    }
                ],
            },
            target_pid="4242",
        )

        self.assertEqual(action["action"], "plan-canary")
        self.assertIn("/tmp/families/LoadPackage/promotion-env.json", action["readyManifestPaths"])

    def test_single_manifest_summary_preserves_trace_identity_fields(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                "tracePid": 4242,
                "imageRangeSource": "pid",
                "imageBase": "0x100000",
                "imageStart": "0x200000",
                "imageEnd": "0x7000000",
                "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping",
                "imagePerms": "r-xp",
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "classRootReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
                "env": {"DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true"},
                "hit": {
                    "seed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                },
            },
        )

        row = summary["manifests"][0]
        self.assertEqual(row["sourceEvidence"], "/tmp/trace.log")
        self.assertIs(row["sourceLogExists"], True)
        self.assertEqual(row["tracePid"], 4242)
        self.assertEqual(row["imageRangeSource"], "pid")
        self.assertEqual(row["imageBase"], "0x100000")
        self.assertEqual(row["imageStart"], "0x200000")
        self.assertEqual(row["imageEnd"], "0x7000000")
        self.assertEqual(row["imagePath"], "/srv/dune/DuneSandboxServer-Linux-Shipping")
        self.assertEqual(row["imagePerms"], "r-xp")
        self.assertEqual(row["callerImageOffset"], "0x5000")
        self.assertEqual(row["ripImageOffset"], "0x4ff0")
        self.assertEqual(row["env"]["DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI"], "true")
        self.assertEqual(row["hit"]["seed"], "LoadPackage")
        self.assertEqual(summary["readyManifestPaths"], ["/tmp/ue4ss-package-promotion-env.json"])

    def test_single_manifest_summary_rejects_wrong_family_env_keys(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "classRootReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
                "env": {"DUNE_PROBE_LOADER_CONFIRM_LOAD_CLASS_PACKAGE_ABI": "true"},
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "LoadPackage promotion env includes LoadClass package keys",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_missing_acceptance_schema(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
                "missingReviewFlags": [],
                "missingNativeInvokeFlags": ["--allow-native-invoke", "--final-native-call"],
                "blockers": [],
                "abiReview": {"ready": True, "blockers": []},
                "env": {"DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI": "true"},
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(summary["readyManifestPaths"], [])
        self.assertIn(
            "ready package promotion manifest is missing current package promotion acceptance schema",
            [item["error"] for item in action["promotionSummaryErrors"]],
        )

    def test_single_manifest_summary_rejects_unsupported_signature_family(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadAsset",
                "hitIndex": 0,
                "selectedHitSeed": "LoadAsset",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                "callerImageOffset": "0x5000",
                "ripImageOffset": "0x4ff0",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
                "env": {},
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "unsupported package promotion signatureFamily: LoadAsset",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_malformed_env(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                "env": ["DUNE_PROBE_LOADER_CONFIRM_LOAD_ASSET_PACKAGE_ABI=true"],
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn("package promotion env must be an object", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_non_scalar_env_value(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": {
                        "source": "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0"
                    },
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = "\n".join(row["error"] for row in action["promotionSummaryErrors"])
        self.assertIn("package promotion env contains a non-scalar value", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_malformed_abi_review_arguments(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                "abiReview": {
                    "ready": True,
                    "blockers": [],
                    "arguments": [{"memory": {"lineCount": "many", "hints": []}}],
                },
                "env": {},
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn("ready package promotion summary row still has blockers", errors)
        self.assertIn("abiReview.arguments[0].memory.lineCount must be a non-negative integer", errors)
        self.assertIn("abiReview.arguments[0].memory.hints must be a JSON object", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_embedded_hit_identity_drift(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
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
                    "seed": "LoadObject",
                    "callerImageOffset": "0x6000",
                    "ripImageOffset": "0x5ff0",
                    "traceAddressMatchesBase": False,
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn("selectedHitSeed does not match embedded trace hit seed", errors)
        self.assertIn("embedded trace hit seed does not match signatureFamily", errors)
        self.assertIn("embedded trace hit callerImageOffset does not match manifest", errors)
        self.assertIn("embedded trace hit ripImageOffset does not match manifest", errors)
        self.assertIn("embedded trace hit address does not match image base plus seed imageOffset", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_embedded_hit_missing_trace_base_match(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
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
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn("embedded trace hit address does not match image base plus seed imageOffset", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_stale_session_flags(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                "tracePidMatchesRequested": False,
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
                    "traceLogHasArmed": False,
                    "tracePidMatchesRequested": False,
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn("trace log armed PID does not match requested runtime PID", errors)
        self.assertIn("embedded trace hit missing trace armed record; cannot prove runtime trace session", errors)
        self.assertIn("embedded trace hit trace log armed PID does not match requested runtime PID", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_embedded_hit_missing_required_memory(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                "hit": {
                    "seed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "traceAddressMatchesBase": True,
                    "missingRequiredMemoryRegisters": ["rsi"],
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertIn(
            "embedded trace hit is missing required memory registers: rsi",
            [row["error"] for row in action["promotionSummaryErrors"]],
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_malformed_embedded_hit_missing_required_memory(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                "hit": {
                    "seed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "traceAddressMatchesBase": True,
                    "missingRequiredMemoryRegisters": "rsi",
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertIn(
            "embedded trace hit missingRequiredMemoryRegisters must be a JSON array",
            [row["error"] for row in action["promotionSummaryErrors"]],
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_malformed_embedded_hit_register_memory(self):
        cases = (
            (["not-object"], "embedded trace hit registerMemory must be a JSON object"),
            ({"": ["0x3:\t0x2f"]}, "embedded trace hit registerMemory contains an invalid register key"),
            ({"rsi": "0x3:\t0x2f"}, "embedded trace hit registerMemory.rsi must be a JSON array"),
            ({"rsi": ["0x3:\t0x2f", 42]}, "embedded trace hit registerMemory.rsi[1] must be a string"),
        )
        for register_memory, message in cases:
            with self.subTest(message=message):
                summary = self.module.summary_from_single_manifest(
                    "/tmp/ue4ss-package-promotion-env.json",
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "sourceLogSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
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
                        "hit": {
                            "seed": "LoadPackage",
                            "callerImageOffset": "0x5000",
                            "ripImageOffset": "0x4ff0",
                            "traceAddressMatchesBase": True,
                            "registerMemory": register_memory,
                        },
                    },
                )

                action = self.module.build_action(promotion_summary=summary)

                self.assertEqual(action["action"], "complete-review")
                self.assertIn(message, [row["error"] for row in action["promotionSummaryErrors"]])
                self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_seed_family_drift_without_embedded_hit(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn("selectedHitSeed does not match signatureFamily", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_runtime_trace_env_identity_drift(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
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
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "env evidence rip does not match ripImageOffset",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_runtime_trace_env_provenance_drift(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
                "tracePid": 123,
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
                    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                        "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0 "
                        "pid=999 evidenceJsonSha256=stale-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=stale-log-sha256"
                    ),
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)
        errors = [row["error"] for row in action["promotionSummaryErrors"]]

        self.assertEqual(action["action"], "complete-review")
        self.assertIn("env evidence pid does not match tracePid", errors)
        self.assertIn("env evidence digest does not match sourceEvidenceJsonSha256", errors)
        self.assertIn("env evidence log digest does not match sourceLogSha256", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_runtime_trace_env_prefix_collisions(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
                "tracePid": 123,
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
                    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                        "runtime-trace:LoadPackage:caller=0x50000 rip=0x4ff00 "
                        "pid=1234 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-stale "
                        "sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-stale"
                    ),
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)
        errors = [row["error"] for row in action["promotionSummaryErrors"]]

        self.assertEqual(action["action"], "complete-review")
        self.assertIn("env evidence caller does not match callerImageOffset", errors)
        self.assertIn("env evidence rip does not match ripImageOffset", errors)
        self.assertIn("env evidence pid does not match tracePid", errors)
        self.assertIn("env evidence digest does not match sourceEvidenceJsonSha256", errors)
        self.assertIn("env evidence log digest does not match sourceLogSha256", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_malformed_image_offsets(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
                "tracePid": 123,
                "callerImageOffset": "5000",
                "ripImageOffset": "0xnothex",
                "readyForNonInvokingCanary": True,
                "targetImageReviewed": True,
                "tcharReviewed": True,
                "classRootReviewed": True,
                "abiReviewReady": True,
                "abiReviewed": True,
                "readyForNativeInvoke": False,
                "env": {
                    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                        "runtime-trace:LoadPackage:caller=5000 rip=0xnothex "
                        "pid=123 evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa sourceLogSha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                    ),
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)
        errors = [row["error"] for row in action["promotionSummaryErrors"]]

        self.assertEqual(action["action"], "complete-review")
        self.assertIn("ready package promotion summary row has invalid callerImageOffset", errors)
        self.assertIn("ready package promotion summary row has invalid ripImageOffset", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_runtime_trace_env_family_drift(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
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
                    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadObject:caller=0x5000 rip=0x4ff0",
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "env evidence family does not match signatureFamily",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_single_manifest_summary_rejects_runtime_trace_env_seed_drift(self):
        summary = self.module.summary_from_single_manifest(
            "/tmp/ue4ss-package-promotion-env.json",
            {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                "signatureFamily": "LoadPackage",
                "hitIndex": 0,
                "selectedHitSeed": "LoadPackage",
                "sourceEvidence": "/tmp/trace.log",
                "sourceLogExists": True,
                **self.trace_plan_provenance(),
                "tracePidMatchesRequested": True,
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
                    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": "runtime-trace:LoadPackage:seed=LoadObject caller=0x5000 rip=0x4ff0",
                },
            },
        )

        action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "env evidence seed does not match signatureFamily",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_valid_direct_promotion_summary_uses_canary_summary_arg(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "family-summary.json"
            manifest_path = Path(tmp) / "families" / "LoadPackage" / "promotion-env.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceLogExists": True,
                        **self.trace_plan_provenance(),
                        "tracePidMatchesRequested": True,
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
                            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": LOAD_PACKAGE_TRACE_EVIDENCE,
                        },
                    }
                ),
                encoding="utf-8",
            )
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "readyManifestPaths": [str(manifest_path)],
                        "manifests": [
                            {
                                "path": str(manifest_path),
                                "signatureFamily": "LoadPackage",
                                "hitIndex": 0,
                                "selectedHitSeed": "LoadPackage",
                                "sourceEvidence": "/tmp/trace.log",
                                "sourceLogExists": True,
                                **self.trace_plan_provenance(),
                                "tracePidMatchesRequested": True,
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
                                    "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": LOAD_PACKAGE_TRACE_EVIDENCE,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_summary(path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "plan-canary")
        self.assertIn("--package-promotion-summary-json", action["commands"][0])
        self.assertNotIn("--promotion-summary-json", action["commands"][0])
        self.assertIn("--format json", action["commands"][0])
        self.assertIn("--format env", action["commands"][1])
        self.assertEqual(action["outputFiles"]["nextCanaryJson"], "/tmp/ue4ss-package-next-canary.json")
        self.assertEqual(action["outputFiles"]["nextCanaryEnv"], "/tmp/ue4ss-package-next-canary.env")

    def test_valid_direct_promotion_manifest_uses_canary_promotion_arg(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion-env.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceLogExists": True,
                        **self.trace_plan_provenance(),
                        "tracePidMatchesRequested": True,
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
                            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": LOAD_PACKAGE_TRACE_EVIDENCE,
                        },
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_manifest(path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "plan-canary")
        self.assertIn("--package-promotion-json", action["commands"][0])
        self.assertIn(str(path), action["commands"][0])
        self.assertNotIn("/tmp/ue4ss-package-family-reviews.json", action["commands"][0])
        self.assertIn("--format json", action["commands"][0])
        self.assertIn("--format env", action["commands"][1])
        self.assertEqual(action["outputFiles"]["nextCanaryJson"], "/tmp/ue4ss-package-next-canary.json")
        self.assertEqual(action["outputFiles"]["nextCanaryEnv"], "/tmp/ue4ss-package-next-canary.env")

    def test_direct_promotion_manifest_missing_source_log_file_blocks_canary_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion-env.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        **self.trace_plan_provenance(),
                        "sourceLogExists": False,
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
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_manifest(path)
            action = self.module.build_action(promotion_summary=summary)
            rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "ready package promotion summary row sourceLog does not exist",
        )
        self.assertIn("Promotion summary errors:", rendered)
        self.assertIn("ready package promotion summary row sourceLog does not exist", rendered)

    def test_direct_promotion_manifest_missing_source_log_exists_blocks_canary_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion-env.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        **self.trace_plan_provenance(),
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
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_manifest(path)
            action = self.module.build_action(promotion_summary=summary)
            rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "ready package promotion summary row is missing sourceLogExists",
        )
        self.assertIn("Promotion summary errors:", rendered)
        self.assertIn("ready package promotion summary row is missing sourceLogExists", rendered)

    def test_direct_promotion_manifest_missing_abi_review_flags_blocks_canary_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion-env.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                        "readyForNativeInvoke": False,
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_manifest(path)
            action = self.module.build_action(promotion_summary=summary)
            rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            [row["error"] for row in action["promotionSummaryErrors"][:2]],
            [
                "ready package promotion summary row is missing ABI review readiness",
                "ready package promotion summary row is missing reviewed ABI confirmation",
            ],
        )
        self.assertIn("ready package promotion summary row is missing ABI review readiness", rendered)

    def test_direct_promotion_manifest_missing_target_and_family_review_blocks_canary_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion-env.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceLogExists": True,
                        "callerImageOffset": "0x5000",
                        "ripImageOffset": "0x4ff0",
                        "abiReviewReady": True,
                        "abiReviewed": True,
                        "readyForNonInvokingCanary": True,
                        "readyForNativeInvoke": False,
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_manifest(path)
            action = self.module.build_action(promotion_summary=summary)
            rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            [row["error"] for row in action["promotionSummaryErrors"][:2]],
            [
                "ready package promotion summary row is missing reviewed target-image confirmation",
                "ready package promotion summary row is missing reviewed TCHAR confirmation",
            ],
        )
        self.assertIn("ready package promotion summary row is missing reviewed target-image confirmation", rendered)

    def test_direct_promotion_summary_row_must_match_manifest_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "families" / "LoadPackage" / "promotion-env.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceLogExists": True,
                        "tracePid": 123,
                        "tracePidMatchesRequested": True,
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
                ),
                encoding="utf-8",
            )
            summary_path = root / "family-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "readyManifestPaths": [str(manifest_path)],
                        "manifests": [
                            {
                                "path": str(manifest_path),
                                "signatureFamily": "LoadPackage",
                                "hitIndex": 0,
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
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_summary(summary_path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "summary row callerImageOffset does not match promotion manifest",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_direct_promotion_summary_priority_must_match_review_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "families" / "LoadPackage" / "promotion-env.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                ),
                encoding="utf-8",
            )
            (manifest_path.parent / "review-priority.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-review-priority/v1",
                        "signatureFamily": "LoadPackage",
                        "rank": 1,
                        "hitIndex": 0,
                    }
                ),
                encoding="utf-8",
            )
            summary_path = root / "family-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "readyManifestPaths": [str(manifest_path)],
                        "manifests": [
                            {
                                "path": str(manifest_path),
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
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_summary(summary_path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = [item["error"] for item in action["promotionSummaryErrors"]]
        self.assertIn("summary row reviewPriority does not match review priority", errors)
        self.assertIn("summary row reviewPriorityHitIndex does not match review priority", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_direct_promotion_summary_invalid_review_priority_blocks_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "families" / "LoadPackage" / "promotion-env.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                ),
                encoding="utf-8",
            )
            (manifest_path.parent / "review-priority.json").write_text("{", encoding="utf-8")
            summary_path = root / "family-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "readyManifestPaths": [str(manifest_path)],
                        "manifests": [
                            {
                                "path": str(manifest_path),
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
                                "reviewPriority": 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_summary(summary_path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertIn("invalid JSON in review priority", action["promotionSummaryErrors"][0]["error"])
        self.assertNotIn("readyManifestPaths", action)

    def test_direct_promotion_summary_manifest_env_family_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "families" / "LoadPackage" / "promotion-env.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                ),
                encoding="utf-8",
            )
            summary_path = root / "family-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "readyManifestPaths": [str(manifest_path)],
                        "manifests": [
                            {
                                "path": str(manifest_path),
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
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_summary(summary_path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "LoadPackage promotion env includes LoadClass package keys",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_direct_promotion_summary_ready_path_must_be_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_path = root / "families" / "LoadPackage" / "promotion-env.json"
            summary_path = root / "family-summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                        "readyManifestPaths": [str(missing_path)],
                        "manifests": [
                            {
                                "path": str(missing_path),
                                "signatureFamily": "LoadPackage",
                                "readyForNonInvokingCanary": True,
                                "targetImageReviewed": True,
                                "tcharReviewed": True,
                                "classRootReviewed": True,
                                "abiReviewReady": True,
                                "abiReviewed": True,
                                "readyForNativeInvoke": False,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_summary(summary_path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "ready manifest path is not readable from promotion summary",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_explicit_missing_promotion_summary_blocks_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "missing-summary.json"
            prearm_path = root / "ue4ss-package-prearm-readiness.json"
            prearm_path.write_text(
                json.dumps(
                    {
                        "ready": True,
                        "completionAuditNextClientGateClassification": {
                            "serverSideFallbackCandidate": "server-side-client-call-emulation",
                        },
                        "completionAuditNextRuntimeRootRecoveryPlan": {
                            "requiredLogPath": "/tmp/dune-server-probe-loader.log",
                            "runCommand": "scripts/canary-linux-server-loader.sh .env",
                        },
                    }
                ),
                encoding="utf-8",
            )
            summary = self.module.load_promotion_summary(summary_path)
            action = self.module.build_action(
                promotion_summary=summary,
                live_trace_runbook={
                    "sourcePath": "/tmp/ue4ss-package-stimulus-trace-runbook.json",
                    "recommendedCandidate": "operator-client-map-entry",
                    "remote": "kspls0",
                    "container": "dune_server-deep-desert-1",
                    "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry.log",
                    "coordinatorCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh",
                    "coordinatorFreshPreflightCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                    "coordinatorFreshTraceCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
                    "routeSlotTraceRequirement": {
                        "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                        "routeAddress": "0x129d58a2",
                        "reviewField": "routeVtableStaticSlotMatches",
                        "requiredSlots": ["0x3a0", "0x3d8"],
                        "requiredRegisters": ["rbx", "r14"],
                    },
                    "reviewArtifacts": {
                        "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                        "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                        "prearmReadinessJson": str(prearm_path),
                        "prearmReadinessMarkdown": "build/server-current-anchor-prep/ue4ss-package-prearm-readiness.md",
                        "prearmReadinessVerificationCommand": "scripts/verify-ue4ss-package-prearm-readiness.py --format json",
                    },
                    "operatorWindow": {
                        "maxArmSeconds": 120,
                        "cleanupRequired": True,
                        "sequence": [
                            "preflight",
                            "arm",
                            "operator-client-login-travel-map-entry",
                            "status",
                            "cleanupCommand",
                            "no-debugger-check",
                        ],
                    },
                    "cleanupCommand": "scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                    "noDebuggerCheckCommand": 'ssh kspls0 \'ps -eo pid,stat,comm,args | grep -E "gdb|ue4ss-package-runtime-trace" | grep -v grep || true; docker top dune_server-deep-desert-1 -eo pid,stat,comm 2>/dev/null | awk \'"\'"\'NR==1 || /DuneSandboxServ/\'"\'"\'\'',
                    "commands": [
                        "scripts/ue4ss-package-remote-trace.sh print kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                        "scripts/ue4ss-package-remote-trace.sh preflight kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                        "scripts/ue4ss-package-remote-trace.sh arm kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                        "operator performs the approved client login/travel/map-entry package-load stimulus",
                        "scripts/ue4ss-package-remote-trace.sh status kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                        "scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                    ],
                },
            )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "promotion summary file is not readable",
        )
        self.assertEqual(
            action["liveTraceRunbook"]["sourcePath"],
            "/tmp/ue4ss-package-stimulus-trace-runbook.json",
        )
        self.assertEqual(action["liveTraceRunbook"]["remote"], "kspls0")
        self.assertEqual(action["liveTraceRunbook"]["container"], "dune_server-deep-desert-1")
        self.assertEqual(action["liveTraceRunbook"]["commandCount"], 6)
        self.assertEqual(action["liveTraceRunbook"]["coordinatorCommand"], "scripts/run-ue4ss-package-live-stimulus-trace.sh")
        self.assertEqual(
            action["liveTraceRunbook"]["coordinatorFreshPreflightCommand"],
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --preflight-only --wait 30 --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
        )
        self.assertEqual(
            action["liveTraceRunbook"]["coordinatorFreshTraceCommand"],
            "scripts/run-ue4ss-package-live-stimulus-trace.sh --trace-log /tmp/ue4ss-package-runtime-trace-live-client-map-entry-$(date -u +%Y%m%dT%H%M%SZ).log",
        )
        self.assertEqual(
            action["liveTraceRunbook"]["routeSlotTraceRequirement"],
            {
                "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
                "routeAddress": "0x129d58a2",
                "reviewField": "routeVtableStaticSlotMatches",
                "requiredSlots": ["0x3a0", "0x3d8"],
                "requiredRegisters": ["rbx", "r14"],
            },
        )
        self.assertEqual(
            action["liveTraceRunbook"]["cleanupCommand"],
            "scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/trace.log",
        )
        self.assertIn("sourceEvidenceJson", action["liveTraceRunbook"]["digestProvenanceFields"])
        self.assertIn("sourceLogSha256", action["liveTraceRunbook"]["digestProvenanceFields"])
        self.assertIn("sourceEvidenceJsonSha256", action["liveTraceRunbook"]["digestProvenanceFields"])
        self.assertEqual(
            action["liveTraceRunbook"]["prearmReadinessJson"],
            str(prearm_path),
        )
        self.assertTrue(action["liveTraceRunbook"]["prearmReadinessReady"])
        self.assertEqual(
            action["liveTraceRunbook"]["completionAuditNextClientGateClassification"]["serverSideFallbackCandidate"],
            "server-side-client-call-emulation",
        )
        self.assertEqual(
            action["liveTraceRunbook"]["completionAuditNextRuntimeRootRecoveryPlan"]["requiredLogPath"],
            "/tmp/dune-server-probe-loader.log",
        )
        self.assertIn(
            "scripts/canary-linux-server-loader.sh",
            action["liveTraceRunbook"]["completionAuditNextRuntimeRootRecoveryPlan"]["runCommand"],
        )
        self.assertIn(
            "verify-ue4ss-package-prearm-readiness.py",
            action["liveTraceRunbook"]["prearmReadinessVerificationCommand"],
        )
        self.assertEqual(action["liveTraceRunbook"]["operatorWindow"]["maxArmSeconds"], 120)
        self.assertIn("ue4ss-package-runtime-trace", action["liveTraceRunbook"]["noDebuggerCheckCommand"])
        self.assertNotIn("readyManifestPaths", action)

    def test_explicit_invalid_promotion_summary_json_blocks_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "family-summary.json"
            summary_path.write_text("{", encoding="utf-8")
            summary = self.module.load_promotion_summary(summary_path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertIn("invalid JSON in promotion summary", action["promotionSummaryErrors"][0]["error"])
        self.assertNotIn("readyManifestPaths", action)

    def test_explicit_non_object_promotion_summary_json_blocks_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "family-summary.json"
            summary_path.write_text("[]", encoding="utf-8")
            summary = self.module.load_promotion_summary(summary_path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "promotion summary must be a JSON object",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_explicit_non_object_promotion_manifest_json_blocks_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "promotion-env.json"
            manifest_path.write_text("[]", encoding="utf-8")
            summary = self.module.load_promotion_manifest(manifest_path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "promotion manifest must be a JSON object",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_summary_errors_must_be_array(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "errors": {},
                "readyManifestPaths": [],
                "manifests": [],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "promotion summary errors must be a JSON array",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_summary_ready_paths_must_be_array(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": {},
                "manifests": [],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "promotion summary readyManifestPaths must be a JSON array",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_summary_manifests_must_be_array(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": [],
                "manifests": {},
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "promotion summary manifests must be a JSON array",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_summary_manifest_rows_must_be_objects(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": [],
                "manifests": [[]],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "promotion summary manifest row 0 must be a JSON object",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_summary_ready_path_without_ready_row_blocks_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
                        "signatureFamily": "LoadPackage",
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                    }
                ],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["confidence"], "high")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "ready manifest path is not backed by a ready manifest row",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_summary_ready_path_must_be_string(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": [123],
                "manifests": [],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["promotionSummaryErrors"][0]["error"], "invalid readyManifestPaths entry")

    def test_summary_ready_row_missing_from_ready_paths_blocks_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": [],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
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
                        "readyForNativeInvoke": False,
                    }
                ],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["confidence"], "high")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "ready manifest row is missing from readyManifestPaths",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_duplicate_ready_manifest_paths_block_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": [
                    "/tmp/families/LoadPackage/promotion-env.json",
                    "/tmp/families/LoadPackage/promotion-env.json",
                ],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
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
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["promotionSummaryErrors"][0]["error"], "duplicate readyManifestPaths entry")
        self.assertNotIn("readyManifestPaths", action)

    def test_duplicate_ready_summary_rows_block_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
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
                    },
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
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
                    },
                ],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["promotionSummaryErrors"][0]["error"], "duplicate ready package promotion summary row")
        self.assertNotIn("readyManifestPaths", action)

    def test_ready_summary_row_with_blockers_blocks_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
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
                        "blockers": ["manual blocker left behind"],
                    }
                ],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["confidence"], "high")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "ready package promotion summary row still has blockers",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_ready_summary_row_malformed_lists_block_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
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
                        "readyForNativeInvoke": True,
                        "nativeInvokeEnabled": True,
                        "finalNativeCallConfirmed": True,
                        "blockers": {},
                        "missingReviewFlags": [False],
                        "abiReviewBlockers": {},
                        "missingNativeInvokeFlags": [False],
                    }
                ],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["confidence"], "high")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn("ready package promotion summary row blockers must be a JSON array", errors)
        self.assertIn("ready package promotion summary row missingReviewFlags[0] must be a string", errors)
        self.assertIn("ready package promotion summary row abiReviewBlockers must be a JSON array", errors)
        self.assertIn("ready package promotion summary row missingNativeInvokeFlags[0] must be a string", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_ready_summary_row_without_trace_identity_blocks_canary_planning(self):
        for hit_index in ("auto", True, -1):
            with self.subTest(hit_index=hit_index):
                action = self.module.build_action(
                    promotion_summary={
                        "sourcePath": "/tmp/family-summary.json",
                        "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                        "manifests": [
                            {
                                "path": "/tmp/families/LoadPackage/promotion-env.json",
                                "signatureFamily": "LoadPackage",
                                "hitIndex": hit_index,
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
                    }
                )

                self.assertEqual(action["action"], "complete-review")
                self.assertEqual(
                    [row["error"] for row in action["promotionSummaryErrors"]],
                    [
                        "ready package promotion summary row is missing sourceEvidence",
                        "ready package promotion summary row is missing sourceEvidenceJson provenance",
                        "ready package promotion summary row is missing sourceEvidenceJsonSha256 provenance",
                        "ready package promotion summary row is missing sourceLogSha256 provenance",
                        "ready package promotion summary row is missing sourceLogExists",
                        "ready package promotion summary row is missing sourceTracePlan provenance",
                        "ready package promotion summary row is missing current sourceTracePlanSchemaVersion provenance",
                        "ready package promotion summary row is missing current sourcePromotionAcceptanceSchemaVersion provenance",
                        "ready package promotion summary row is missing sourceExternalPlan provenance",
                        "ready package promotion summary row is missing runtime trace PID match provenance",
                        "ready package promotion summary row is missing concrete hitIndex",
                        "ready package promotion summary row is missing selectedHitSeed",
                        "ready package promotion env is missing runtime trace evidence",
                    ],
                )
                self.assertNotIn("readyManifestPaths", action)

    def test_ready_summary_row_missing_trace_pid_match_provenance_blocks_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
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
            }
        )
        rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "complete-review")
        self.assertIn(
            "ready package promotion summary row is missing runtime trace PID match provenance",
            [row["error"] for row in action["promotionSummaryErrors"]],
        )
        self.assertNotIn("readyManifestPaths", action)
        self.assertIn("missing runtime trace PID match provenance", rendered)

    def test_ready_summary_row_rejects_stale_session_flags(self):
        for stale_value in (False, "false"):
            with self.subTest(stale_value=stale_value):
                action = self.module.build_action(
                    promotion_summary={
                        "sourcePath": "/tmp/family-summary.json",
                        "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                        "manifests": [
                            {
                                "path": "/tmp/families/LoadPackage/promotion-env.json",
                                "signatureFamily": "LoadPackage",
                                "hitIndex": 0,
                                "selectedHitSeed": "LoadPackage",
                                "sourceEvidence": "/tmp/trace.log",
                                "sourceLogExists": True,
                                "tracePidMatchesRequested": stale_value,
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
                        ],
                    }
                )

                self.assertEqual(action["action"], "complete-review")
                errors = [row["error"] for row in action["promotionSummaryErrors"]]
                self.assertIn("trace log armed PID does not match requested runtime PID", errors)
                self.assertIn("embedded trace hit missing trace armed record; cannot prove runtime trace session", errors)
                self.assertIn("embedded trace hit trace log armed PID does not match requested runtime PID", errors)
                self.assertNotIn("readyManifestPaths", action)

    def test_ready_native_summary_row_requires_non_invoking_readiness(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
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
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertIn(
            "ready native package promotion summary row is missing non-invoking canary readiness",
            [row["error"] for row in action["promotionSummaryErrors"]],
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_saved_summary_rejects_manifest_embedded_hit_identity_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            family_dir = root / "LoadPackage"
            family_dir.mkdir()
            manifest_path = family_dir / "promotion-env.json"
            manifest = {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                "blockers": [],
                "missingReviewFlags": [],
                "missingNativeInvokeFlags": [],
                "env": {},
                "hit": {
                    "seed": "LoadObject",
                    "callerImageOffset": "0x6000",
                    "ripImageOffset": "0x5ff0",
                    "traceAddressMatchesBase": False,
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            summary_path = root / "family-summary.json"
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "sourcePath": str(summary_path),
                "sourceArg": "--package-promotion-summary-json",
                "readyManifestPaths": [str(manifest_path)],
                "manifests": [
                    {
                        "path": str(manifest_path),
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
            }

            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn("embedded trace hit seed does not match signatureFamily", errors)
        self.assertIn("embedded trace hit callerImageOffset does not match manifest", errors)
        self.assertIn("embedded trace hit ripImageOffset does not match manifest", errors)
        self.assertIn("embedded trace hit address does not match image base plus seed imageOffset", errors)
        self.assertNotIn("readyManifestPaths", action)

    def test_saved_summary_rejects_manifest_embedded_hit_missing_required_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            family_dir = root / "LoadPackage"
            family_dir.mkdir()
            manifest_path = family_dir / "promotion-env.json"
            manifest = {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                "blockers": [],
                "missingReviewFlags": [],
                "missingNativeInvokeFlags": [],
                "env": {},
                "hit": {
                    "seed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "traceAddressMatchesBase": True,
                    "missingRequiredMemoryRegisters": ["rsi"],
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            summary_path = root / "family-summary.json"
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "sourcePath": str(summary_path),
                "sourceArg": "--package-promotion-summary-json",
                "readyManifestPaths": [str(manifest_path)],
                "manifests": [
                    {
                        "path": str(manifest_path),
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
            }

            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertIn(
            "embedded trace hit is missing required memory registers: rsi",
            [row["error"] for row in action["promotionSummaryErrors"]],
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_saved_summary_rejects_manifest_embedded_hit_malformed_register_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            family_dir = root / "LoadPackage"
            family_dir.mkdir()
            manifest_path = family_dir / "promotion-env.json"
            manifest = {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                "blockers": [],
                "missingReviewFlags": [],
                "missingNativeInvokeFlags": [],
                "env": {},
                "hit": {
                    "seed": "LoadPackage",
                    "callerImageOffset": "0x5000",
                    "ripImageOffset": "0x4ff0",
                    "traceAddressMatchesBase": True,
                    "registerMemory": {"rsi": ["0x3:\t0x2f", 42]},
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            summary_path = root / "family-summary.json"
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "sourcePath": str(summary_path),
                "sourceArg": "--package-promotion-summary-json",
                "readyManifestPaths": [str(manifest_path)],
                "manifests": [
                    {
                        "path": str(manifest_path),
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
            }

            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertIn(
            "embedded trace hit registerMemory.rsi[1] must be a string",
            [row["error"] for row in action["promotionSummaryErrors"]],
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_saved_summary_rejects_manifest_malformed_abi_argument_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            family_dir = root / "LoadPackage"
            family_dir.mkdir()
            manifest_path = family_dir / "promotion-env.json"
            manifest = {
                "schemaVersion": "dune-ue4ss-package-promotion-env/v1",
                "promotionAcceptanceSchemaVersion": "dune-ue4ss-package-anchor-promotion-acceptance/v1",
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
                "blockers": [],
                "missingReviewFlags": [],
                "missingNativeInvokeFlags": [],
                "env": {},
                "abiReview": {
                    "ready": True,
                    "blockers": [],
                    "arguments": [{"memory": {"lineCount": "many"}}],
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            summary_path = root / "family-summary.json"
            summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "sourcePath": str(summary_path),
                "sourceArg": "--package-promotion-summary-json",
                "readyManifestPaths": [str(manifest_path)],
                "manifests": [
                    {
                        "path": str(manifest_path),
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
            }

            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertIn(
            "abiReview.arguments[0].memory.lineCount must be a non-negative integer",
            [row["error"] for row in action["promotionSummaryErrors"]],
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_promotion_summary_errors_block_ready_canary_planning(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "errors": [{"path": "/tmp/families/LoadPackage/review-priority.json", "error": "invalid hitIndex"}],
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["confidence"], "high")
        self.assertEqual(action["promotionSummaryErrors"][0]["error"], "invalid hitIndex")
        self.assertNotIn("readyManifestPaths", action)
        self.assertIn("ue4ss-package-runtime-trace.sh status", action["commands"][0])

    def test_invalid_direct_promotion_summary_json_blocks_canary_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "not-a-summary.json"
            path.write_text(
                json.dumps({"readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"]}),
                encoding="utf-8",
            )

            summary = self.module.load_promotion_summary(path)
            action = self.module.build_action(promotion_summary=summary)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["confidence"], "high")
        self.assertEqual(
            action["promotionSummaryErrors"][0]["error"],
            "not a UE4SS package promotion directory summary",
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_blocked_promotion_summary_points_to_review_status(self):
        action = self.module.build_action(
            promotion_summary={
                "manifests": [
                    {
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                        "missingReviewFlags": ["--reviewed-abi", "--reviewed-tchar"],
                        "missingNativeInvokeFlags": ["--allow-native-invoke"],
                        "blockers": ["reviewed ABI evidence is required"],
                        "abiReviewBlockers": ["missing stack context"],
                    }
                ]
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["pending"]["signatureFamily"], "LoadPackage")
        self.assertIn("--reviewed-abi", action["pending"]["missingReviewFlags"])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage", action["commands"][0])
        self.assertIn("scripts/ue4ss-package-runtime-trace.sh status", action["commands"][0])

    def test_no_hit_promotion_summary_does_not_become_pending_review(self):
        action = self.module.build_action(
            promotion_summary={
                "manifests": [
                    {
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                        "missingReviewFlags": ["--reviewed-target-image", "--reviewed-abi"],
                        "missingNativeInvokeFlags": ["--allow-native-invoke"],
                        "blockers": ["no runtime trace hits available for package promotion"],
                    }
                ]
            },
            trace_plan={
                "sourcePath": "/tmp/current-runtime-trace-plan.json",
                "sourceExternalPlan": "/tmp/current-external-symbol-plan.json",
                "blockers": [],
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
            },
        )

        self.assertEqual(action["action"], "arm-trace")
        self.assertNotIn("pending", action)
        self.assertIn("ue4ss-package-runtime-trace.sh arm", action["commands"][1])

    def test_blocked_promotion_summary_malformed_lists_become_pending_blockers(self):
        action = self.module.build_action(
            promotion_summary={
                "manifests": [
                    {
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                        "missingReviewFlags": "--reviewed-abi",
                        "missingNativeInvokeFlags": ["--allow-native-invoke", 42],
                        "blockers": {"message": "review required"},
                        "abiReviewBlockers": [{"message": "missing stack"}],
                    }
                ]
            }
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["pending"]["missingReviewFlags"], [])
        self.assertEqual(action["pending"]["missingNativeInvokeFlags"], ["--allow-native-invoke"])
        self.assertIn("missingReviewFlags must be a JSON array", action["pending"]["blockers"])
        self.assertIn("missingNativeInvokeFlags[1] must be a string", action["pending"]["blockers"])
        self.assertIn("blockers must be a JSON array", action["pending"]["blockers"])
        self.assertIn("abiReview.abiReviewBlockers[0] must be a string", action["pending"]["abiReviewBlockers"])

    def test_blocked_review_status_command_can_emit_non_dune_process_pattern(self):
        action = self.module.build_action(
            promotion_summary={
                "manifests": [
                    {
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                        "missingReviewFlags": ["--reviewed-abi"],
                    }
                ]
            },
            container="example-game-server",
            process_pattern="ExampleGame-Linux-Shipping",
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN=ExampleGame-Linux-Shipping", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage", action["commands"][0])
        self.assertIn("example-game-server", action["commands"][0])

    def test_blocked_review_status_command_can_emit_explicit_target_pid(self):
        action = self.module.build_action(
            promotion_summary={
                "manifests": [
                    {
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                        "missingReviewFlags": ["--reviewed-abi"],
                    }
                ]
            },
            target_pid="4242",
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PID=4242", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY=LoadPackage", action["commands"][0])
        self.assertIn("pid-4242", action["commands"][0])
        self.assertNotIn("dune_server-deep-desert-1", action["commands"][0])

    def test_blocked_review_status_command_keeps_explicit_container_with_target_pid(self):
        action = self.module.build_action(
            promotion_summary={
                "manifests": [
                    {
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                        "missingReviewFlags": ["--reviewed-abi"],
                    }
                ]
            },
            container="example-game-server",
            target_pid="4242",
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PID=4242", action["commands"][0])
        self.assertIn("example-game-server", action["commands"][0])
        self.assertNotIn("pid-4242", action["commands"][0])

    def test_invalid_explicit_target_pid_does_not_emit_review_replay_command(self):
        for target_pid in ("not-a-pid", "0", "\u0660"):
            with self.subTest(target_pid=target_pid):
                action = self.module.build_action(
                    promotion_summary={
                        "manifests": [
                            {
                                "signatureFamily": "LoadPackage",
                                "hitIndex": 0,
                                "readyForNonInvokingCanary": False,
                                "readyForNativeInvoke": False,
                                "missingReviewFlags": ["--reviewed-abi"],
                            }
                        ]
                    },
                    target_pid=target_pid,
                )

                self.assertEqual(action["action"], "complete-review")
                self.assertEqual(action["confidence"], "high")
                self.assertEqual(action["promotionSummaryErrors"][0]["error"], "target PID must be numeric")
                self.assertEqual(action["commands"], [])

    def test_promotion_summary_errors_are_visible_in_next_action(self):
        action = self.module.build_action(
            promotion_summary={
                "errors": [
                    {
                        "path": "/tmp/families/LoadPackage/review-priority.json",
                        "error": "invalid review priority hitIndex",
                    }
                ],
                "manifests": [
                    {
                        "signatureFamily": "LoadPackage",
                        "hitIndex": "auto",
                        "readyForNonInvokingCanary": False,
                        "readyForNativeInvoke": False,
                        "missingReviewFlags": ["--reviewed-abi"],
                    }
                ],
            }
        )
        rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["promotionSummaryErrors"][0]["error"], "invalid review priority hitIndex")
        self.assertIn("Promotion summary errors:", rendered)
        self.assertIn("invalid review priority hitIndex", rendered)

    def test_trace_plan_recommendation_arms_shortest_runtime_trace(self):
        action = self.module.build_action(
            trace_plan={
                "sourcePath": "/tmp/current-runtime-trace-plan.json",
                "sourceExternalPlan": "/tmp/current-external-symbol-plan.json",
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                }
            }
        )

        self.assertEqual(action["action"], "arm-trace")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PLAN"], "/tmp/current-external-symbol-plan.json")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON"], "/tmp/current-runtime-trace-plan.json")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD"], "/tmp/current-runtime-trace-plan.md")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_LIMIT"], "2")
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAN=/tmp/current-external-symbol-plan.json", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON=/tmp/current-runtime-trace-plan.json", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD=/tmp/current-runtime-trace-plan.md", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage,LoadObject", action["commands"][0])
        self.assertIn("scripts/ue4ss-package-runtime-trace.sh preflight", action["commands"][0])
        self.assertIn("scripts/ue4ss-package-runtime-trace.sh arm", action["commands"][1])
        self.assertIn("scripts/ue4ss-package-runtime-trace.sh status", action["commands"][2])

    def test_trace_plan_route_probes_are_preserved_in_arm_commands(self):
        action = self.module.build_action(
            trace_plan={
                "sourcePath": "/tmp/current-runtime-trace-plan.json",
                "sourceExternalPlan": "/tmp/current-external-symbol-plan.json",
                "requestedRouteAddresses": ["0xf94711c", "0xf9492bc"],
                "routeProbes": [
                    {"address": "0xf94711c"},
                    {"address": "0xf9492bc"},
                ],
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "4",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
            }
        )

        self.assertEqual(action["action"], "arm-trace")
        self.assertEqual(
            action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS"],
            "0xf94711c,0xf9492bc",
        )
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0xf94711c,0xf9492bc", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_ROUTE_ADDRESS=0xf94711c,0xf9492bc", action["commands"][1])

    def test_loaded_trace_plan_recommendation_pins_loaded_plan_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_path = Path(temp_dir) / "runtime-trace-plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-runtime-trace-plan/v1",
                        "sourceExternalPlan": "/tmp/current-external-symbol-plan.json",
                        "recommendedTraceEnv": {
                            "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                            "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                            "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                            "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                        },
                        "blockers": [],
                    }
                ),
                encoding="utf-8",
            )

            action = self.module.build_action(trace_plan=self.module.load_trace_plan(plan_path))

        self.assertEqual(action["action"], "arm-trace")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PLAN"], "/tmp/current-external-symbol-plan.json")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON"], str(plan_path))
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PLAN_MD"], str(plan_path.with_suffix(".md")))
        self.assertIn(f"DUNE_UE4SS_PACKAGE_TRACE_PLAN_JSON={plan_path}", action["commands"][0])
        self.assertIn("ue4ss-package-runtime-trace.sh preflight", action["commands"][0])

    def test_trace_plan_blockers_refresh_trace_plan_instead_of_arming(self):
        action = self.module.build_action(
            trace_plan={
                "sourceExternalPlan": "/tmp/package-external-plan.json",
                "base": "0x100000",
                "blockers": ["no package runtime trace seeds selected"],
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
            }
        )
        rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "refresh-trace-plan")
        self.assertEqual(action["tracePlanBlockers"], ["no package runtime trace seeds selected"])
        self.assertIn("--external-plan /tmp/package-external-plan.json", action["commands"][0])
        self.assertIn("--anchor LoadPackage", action["commands"][0])
        self.assertIn("--limit 1", action["commands"][0])
        self.assertIn("--format json >/tmp/ue4ss-package-runtime-trace-plan.json", action["commands"][0])
        self.assertIn("--format markdown >/tmp/ue4ss-package-runtime-trace-plan.md", action["commands"][1])
        self.assertNotIn("ue4ss-package-runtime-trace.sh arm", action["commands"][0])
        self.assertNotIn("ue4ss-package-runtime-trace.sh arm", action["commands"][1])
        self.assertIn("Trace plan blockers:", rendered)
        self.assertIn("no package runtime trace seeds selected", rendered)

    def test_trace_plan_refresh_preserves_route_probe_addresses(self):
        action = self.module.build_action(
            trace_plan={
                "sourceExternalPlan": "/tmp/package-external-plan.json",
                "base": "0x100000",
                "requestedRouteAddresses": ["0xf94711c", "0xf9492bc"],
                "blockers": ["no package runtime trace seeds selected"],
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
            }
        )

        self.assertEqual(action["action"], "refresh-trace-plan")
        self.assertIn("--route-address 0xf94711c", action["commands"][0])
        self.assertIn("--route-address 0xf9492bc", action["commands"][0])
        self.assertIn("--route-address 0xf94711c", action["commands"][1])
        self.assertIn("--route-address 0xf9492bc", action["commands"][1])

    def test_no_hit_trace_history_pivots_to_package_anchor_recovery(self):
        trace_plan = {
            "sourceExternalPlan": "/tmp/package-external-plan.json",
            "base": "0x100000",
            "seeds": [
                {"name": "LoadPackage", "address": "0x5ae6260"},
                {"name": "LoadObject", "address": "0x814c33"},
            ],
            "blockers": [],
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            },
        }
        trace_history = [
            {
                "sourceLog": "/tmp/no-hit.log",
                "armedCount": 1,
                "hitCount": 0,
                "tracePlan": {"seeds": trace_plan["seeds"]},
            }
        ]

        action = self.module.build_action(trace_plan=trace_plan, trace_history=trace_history)
        rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "recover-package-anchor")
        self.assertIn("zero hits", action["reason"])
        self.assertIn("LoadPackage@0x5ae6260", action["traceNoHitExhaustion"]["plannedSeeds"])
        self.assertIn("LoadObject@0x814c33", action["traceNoHitExhaustion"]["coveredSeeds"])
        self.assertNotIn("ue4ss-package-runtime-trace.sh arm", " ".join(action["commands"]))
        self.assertIn("ue4ss-package-route-evidence.json", action["commands"][0])
        self.assertIn("ue4ss-package-external-symbol-plan.json", action["commands"][1])
        self.assertIn("external donor symbols or targeted runtime call-frame proof", action["nextStep"])
        self.assertIn("Runtime trace no-hit exhaustion:", rendered)
        self.assertIn("recover-package-anchor", rendered)

    def test_seed_no_hit_history_with_untried_method_probes_still_arms_trace(self):
        trace_plan = {
            "sourceExternalPlan": "/tmp/package-external-plan.json",
            "base": "0x100000",
            "seeds": [{"name": "LoadPackage", "address": "0x5ae6260"}],
            "methodProbes": [
                {
                    "owner": "vtable for FLinkerLoad",
                    "slotIndex": 31,
                    "address": "0x9b04600",
                }
            ],
            "blockers": [],
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            },
        }
        trace_history = [
            {
                "sourceLog": "/tmp/string-only-no-hit.log",
                "armedCount": 1,
                "hitCount": 0,
                "tracePlan": {"seeds": trace_plan["seeds"]},
            }
        ]

        action = self.module.build_action(trace_plan=trace_plan, trace_history=trace_history)

        self.assertEqual(action["action"], "arm-trace")
        self.assertIn("ue4ss-package-runtime-trace.sh arm", action["commands"][1])
        self.assertNotIn("traceNoHitExhaustion", action)

    def test_seed_and_method_no_hit_history_pivots_to_package_anchor_recovery(self):
        trace_plan = {
            "sourceExternalPlan": "/tmp/package-external-plan.json",
            "base": "0x100000",
            "seeds": [{"name": "LoadPackage", "address": "0x5ae6260"}],
            "methodProbes": [
                {
                    "owner": "vtable for FLinkerLoad",
                    "slotIndex": 31,
                    "address": "0x9b04600",
                }
            ],
            "blockers": [],
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            },
        }
        trace_history = [
            {
                "sourceLog": "/tmp/combined-no-hit.log",
                "armedCount": 1,
                "hitCount": 0,
                "tracePlan": {
                    "seeds": trace_plan["seeds"],
                    "methodProbes": trace_plan["methodProbes"],
                },
            }
        ]

        action = self.module.build_action(trace_plan=trace_plan, trace_history=trace_history)
        rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "recover-package-anchor")
        self.assertIn("vtable for FLinkerLoad:slot31@0x9b04600", action["traceNoHitExhaustion"]["plannedMethodProbes"])
        self.assertIn("vtable for FLinkerLoad:slot31@0x9b04600", action["traceNoHitExhaustion"]["coveredMethodProbes"])
        self.assertIn("planned method probe", rendered)

    def test_method_trace_hits_plan_route_review_before_rearming(self):
        trace_plan = {
            "sourceExternalPlan": "/tmp/package-external-plan.json",
            "base": "0x100000",
            "seeds": [{"name": "LoadPackage", "address": "0x5ae6260"}],
            "blockers": [],
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            },
        }
        trace_history = [
            {
                "sourceLog": "/tmp/combined-evidence.md",
                "armedCount": 1,
                "hitCount": 0,
                "methodHitCount": 1,
                "methodHits": [
                    {
                        "owner": "vtable for FLinkerLoad",
                        "slotIndex": "31",
                        "imageOffset": "0x9b04600",
                        "ripImageOffset": "0x9b04600",
                        "callerImageOffset": "0x9f01234",
                        "targetImageCaller": True,
                        "disassembly": ["push %rbp"],
                        "stack": ["0x1"],
                    }
                ],
            }
        ]

        action = self.module.build_action(trace_plan=trace_plan, trace_history=trace_history)
        rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "review-method-route")
        self.assertEqual(action["methodRouteEvidence"]["routeCount"], 1)
        self.assertEqual(action["methodRouteEvidence"]["bestRoute"]["callerImageOffset"], "0x9f01234")
        self.assertNotIn("ue4ss-package-runtime-trace.sh arm", " ".join(action["commands"]))
        self.assertIn("Method route candidates", rendered)

    def test_reviewed_non_promotable_method_routes_advance_to_anchor_recovery(self):
        trace_plan = {
            "sourceExternalPlan": "/tmp/package-external-plan.json",
            "base": "0x100000",
            "seeds": [{"name": "LoadPackage", "address": "0x5ae6260"}],
            "blockers": [],
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            },
        }
        trace_history = [
            {
                "sourceLog": "/tmp/combined-evidence.md",
                "armedCount": 1,
                "hitCount": 0,
                "methodHitCount": 1,
                "methodHits": [
                    {
                        "owner": "vtable for FLinkerLoad",
                        "slotIndex": "31",
                        "imageOffset": "0x9b04600",
                        "callerImageOffset": "0x9f01234",
                    }
                ],
            }
        ]
        route_evidence = {
            "sourcePath": "/tmp/route-evidence.json",
            "routes": [
                {
                    "id": "runtime-method-route-review",
                    "finding": "negative",
                    "metrics": {"nonPromotableRouteCount": 2},
                }
            ],
        }

        action = self.module.build_action(
            trace_plan=trace_plan,
            trace_history=trace_history,
            route_evidence=route_evidence,
        )

        self.assertEqual(action["action"], "recover-package-anchor")
        self.assertIn("non-promotable", action["reason"])
        self.assertIn("/tmp/route-evidence.json", action["commands"][0])
        self.assertNotIn("review-method-route", action["action"])

    def test_no_unreviewed_method_probes_pivots_to_external_static_recovery(self):
        trace_history = [
            {
                "sourceLog": "/tmp/combined-evidence.md",
                "armedCount": 1,
                "hitCount": 0,
                "methodHitCount": 1,
            }
        ]
        route_evidence = {
            "sourcePath": "/tmp/route-evidence.json",
            "routes": [
                {
                    "id": "runtime-method-route-review",
                    "finding": "negative",
                    "metrics": {"nonPromotableRouteCount": 2},
                }
            ],
        }
        method_probe_refinement = {
            "sourcePath": "/tmp/method-probe-refinement.json",
            "candidateCount": 0,
            "selectedCount": 0,
            "selectedAddresses": [],
        }
        live_trace_runbook = {
            "sourcePath": "/tmp/stimulus-trace-runbook.json",
            "recommendedCandidate": "operator-client-map-entry",
            "remote": "kspls0",
            "container": "dune_server-deep-desert-1",
            "traceLog": "/tmp/package-live.log",
            "reviewArtifacts": {
                "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
            },
            "cleanupCommand": (
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=StaticLoadObject "
                "scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/package-live.log"
            ),
            "commands": [
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=StaticLoadObject scripts/ue4ss-package-remote-trace.sh print kspls0 dune_server-deep-desert-1 /tmp/package-live.log",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=StaticLoadObject scripts/ue4ss-package-remote-trace.sh preflight kspls0 dune_server-deep-desert-1 /tmp/package-live.log",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=StaticLoadObject scripts/ue4ss-package-remote-trace.sh arm kspls0 dune_server-deep-desert-1 /tmp/package-live.log",
                "operator performs the approved client login/travel/map-entry package-load stimulus",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=StaticLoadObject scripts/ue4ss-package-remote-trace.sh status kspls0 dune_server-deep-desert-1 /tmp/package-live.log",
                "DUNE_UE4SS_PACKAGE_REMOTE_TRACE_ANCHOR=StaticLoadObject scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/package-live.log",
            ],
        }
        trace_plan = {
            "sourceExternalPlan": "/tmp/package-external-plan.json",
            "base": "0x100000",
            "seeds": [{"name": "LoadPackage", "address": "0x5ae6260"}],
            "blockers": [],
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            },
        }

        action = self.module.build_action(
            trace_plan=trace_plan,
            trace_history=trace_history,
            route_evidence=route_evidence,
            method_probe_refinement=method_probe_refinement,
            live_trace_runbook=live_trace_runbook,
        )

        self.assertEqual(action["action"], "recover-package-anchor")
        self.assertIn("no unreviewed call-bearing package method probes remain", action["reason"])
        self.assertEqual(action["methodProbeRefinement"]["selectedCount"], 0)
        self.assertIn("/tmp/method-probe-refinement.json", action["commands"][1])
        self.assertIn("ue4ss-package-source-abi-recovery.json", action["commands"][2])
        self.assertIn("ue4ss-package-static-metadata-recovery.json", action["commands"][3])
        self.assertIn("ue4ss-package-live-call-frame-recovery-plan.json", action["commands"][4])
        self.assertIn("ue4ss-package-server-replay-plan.json", action["commands"][5])
        self.assertIn("ue4ss-package-stimulus-plan.json", action["commands"][6])
        self.assertIn("ue4ss-package-stimulus-trace-runbook.json", action["commands"][7])
        self.assertIn("ue4ss-package-remote-trace.sh print", action["commands"][9])
        self.assertIn("ue4ss-package-remote-trace.sh arm", action["commands"][11])
        self.assertIn("operator performs", action["commands"][12])
        self.assertEqual(action["liveTraceRunbook"]["sourcePath"], "/tmp/stimulus-trace-runbook.json")
        self.assertEqual(action["liveTraceRunbook"]["remote"], "kspls0")
        self.assertEqual(action["liveTraceRunbook"]["container"], "dune_server-deep-desert-1")
        self.assertEqual(action["liveTraceRunbook"]["commandCount"], 6)
        self.assertIn("ue4ss-package-remote-trace.sh stop", action["liveTraceRunbook"]["cleanupCommand"])
        self.assertIn("sourceEvidenceJson", action["liveTraceRunbook"]["digestProvenanceFields"])
        self.assertIn("sourceLogSha256", action["liveTraceRunbook"]["digestProvenanceFields"])
        rendered = self.module.markdown(action)
        self.assertIn("Live trace runbook:", rendered)
        self.assertIn("remote: `kspls0`", rendered)
        self.assertIn("container: `dune_server-deep-desert-1`", rendered)
        self.assertIn("cleanup:", rendered)
        self.assertIn("ue4ss-package-remote-trace.sh stop", rendered)
        self.assertIn("sourceEvidenceJson", rendered)
        self.assertIn("sourceEvidenceJsonSha256", rendered)
        self.assertIn("classify the operator-selected client login/travel/map-entry package-load action", action["nextStep"])
        self.assertIn("replay/spoof the equivalent call server-side", action["nextStep"])

    def test_donor_target_validation_plans_signature_anchor_canary(self):
        donor_validation = {
            "sourcePath": "/tmp/donor-target-validation.json",
            "patterns": [
                {
                    "name": "StaticLoadObject",
                    "category": "package",
                    "status": "unique-unexpected",
                    "promotable": True,
                    "sourceProvenance": "external-donor",
                    "pattern": "e8 ?? ?? ?? ??",
                    "matches": [
                        {
                            "imageOffset": "0x1234",
                            "vaddr": "0x2234",
                        }
                    ],
                }
            ],
        }

        action = self.module.build_action(donor_target_validation=donor_validation)
        rendered = self.module.markdown(action)

        self.assertEqual(action["action"], "plan-signature-anchor-canary")
        self.assertEqual(action["donorTargetValidation"]["promotablePackagePatternCount"], 1)
        self.assertIn("--validation-json /tmp/donor-target-validation.json", action["commands"][0])
        self.assertIn("--anchor-signatures-file build/server-ue4ss-package-anchor-signatures.txt", action["commands"][1])
        self.assertIn("--signature-validation-json /tmp/donor-target-validation.json", action["commands"][1])
        self.assertIn("Donor target validation:", rendered)
        self.assertIn("StaticLoadObject", rendered)

    def test_donor_target_validation_without_target_offsets_does_not_skip_recovery(self):
        trace_plan = {
            "sourceExternalPlan": "/tmp/package-external-plan.json",
            "base": "0x100000",
            "seeds": [{"name": "LoadPackage", "address": "0x5ae6260"}],
            "blockers": [],
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            },
        }
        trace_history = [
            {
                "sourceLog": "/tmp/no-hit.log",
                "armedCount": 1,
                "hitCount": 0,
                "tracePlan": {"seeds": trace_plan["seeds"]},
            }
        ]
        donor_validation = {
            "patterns": [
                {
                    "name": "StaticLoadObject",
                    "category": "package",
                    "status": "unique-unexpected",
                    "promotable": True,
                    "matches": [{}],
                }
            ]
        }

        action = self.module.build_action(
            trace_plan=trace_plan,
            trace_history=trace_history,
            donor_target_validation=donor_validation,
        )

        self.assertEqual(action["action"], "recover-package-anchor")

    def test_partial_no_hit_trace_history_still_arms_remaining_trace_plan(self):
        trace_plan = {
            "sourceExternalPlan": "/tmp/package-external-plan.json",
            "base": "0x100000",
            "seeds": [
                {"name": "LoadPackage", "address": "0x5ae6260"},
                {"name": "LoadObject", "address": "0x814c33"},
            ],
            "blockers": [],
            "recommendedTraceEnv": {
                "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,LoadObject",
                "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "2",
                "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
            },
        }
        trace_history = [
            {
                "sourceLog": "/tmp/no-hit.log",
                "armedCount": 1,
                "hitCount": 0,
                "tracePlan": {"seeds": [{"name": "LoadPackage", "address": "0x5ae6260"}]},
            }
        ]

        action = self.module.build_action(trace_plan=trace_plan, trace_history=trace_history)

        self.assertEqual(action["action"], "arm-trace")
        self.assertIn("ue4ss-package-runtime-trace.sh arm", action["commands"][1])

    def test_malformed_trace_plan_blockers_refresh_trace_plan_instead_of_arming(self):
        cases = (
            ("not-array", "runtime trace plan blockers must be a JSON array"),
            ([42], "runtime trace plan blockers[0] must be a string"),
        )
        for blockers, message in cases:
            with self.subTest(message=message):
                action = self.module.build_action(
                    trace_plan={
                        "sourceExternalPlan": "/tmp/package-external-plan.json",
                        "base": "0x100000",
                        "blockers": blockers,
                        "recommendedTraceEnv": {
                            "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                            "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                            "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                            "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                        },
                    }
                )

                self.assertEqual(action["action"], "refresh-trace-plan")
                self.assertIn(message, action["tracePlanBlockers"])
                self.assertNotIn("traceEnv", action)
                self.assertNotIn("ue4ss-package-runtime-trace.sh arm", action["commands"][0])

    def test_malformed_trace_plan_refresh_inputs_use_safe_refresh_command(self):
        action = self.module.build_action(
            trace_plan={
                "sourceExternalPlan": ["not-a-path"],
                "base": {"addr": "0x100000"},
                "sourcePath": {"path": "/tmp/plan.json"},
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
            }
        )

        self.assertEqual(action["action"], "refresh-trace-plan")
        self.assertIn("runtime trace plan sourceExternalPlan must be a scalar", action["tracePlanBlockers"])
        self.assertIn("runtime trace plan base must be a scalar", action["tracePlanBlockers"])
        self.assertIn("runtime trace plan sourcePath must be a scalar", action["tracePlanBlockers"])
        self.assertIn("--external-plan build/server-ue4ss-package-external-symbol-plan.json", action["commands"][0])
        self.assertIn("--base 0x100000", action["commands"][0])
        self.assertIn(">/tmp/ue4ss-package-runtime-trace-plan.json", action["commands"][0])
        self.assertNotIn("not-a-path", action["commands"][0])
        self.assertNotIn("ue4ss-package-runtime-trace.sh arm", action["commands"][0])

    def test_malformed_trace_plan_recommended_env_refreshes_trace_plan(self):
        cases = (
            (
                ["DUNE_UE4SS_PACKAGE_TRACE_ANCHOR=LoadPackage"],
                "runtime trace plan recommendedTraceEnv must be an object",
            ),
            (
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
                "runtime trace plan anchor list is empty",
            ),
            (
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
                "runtime trace plan anchor list is empty",
            ),
            (
                {"DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage,MissingAnchor"},
                "unsupported runtime trace anchor: MissingAnchor",
            ),
            (
                {"DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "MissingAnchor"},
                "unsupported runtime trace signature family: MissingAnchor",
            ),
            (
                {"DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "0"},
                "runtime trace limit must be positive",
            ),
            (
                {"DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "later"},
                "runtime trace hit index must be an integer or auto",
            ),
            (
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                    "selectedByFamily": ["LoadPackage"],
                },
                "runtime trace plan recommendedTraceEnv selectedByFamily must be an object",
            ),
            (
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                    "selectedByFamily": {"": 1},
                },
                "runtime trace plan recommendedTraceEnv selectedByFamily keys must be non-empty strings",
            ),
            (
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                    "selectedByFamily": {"LoadPackage": True},
                },
                "runtime trace plan recommendedTraceEnv selectedByFamily values must be positive integers",
            ),
            (
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                    "selectedByFamily": {"LoadPackage": 0},
                },
                "runtime trace plan recommendedTraceEnv selectedByFamily values must be positive integers",
            ),
            (
                {
                    "TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
                "runtime trace plan recommendedTraceEnv key is not a supported trace env variable: TRACE_ANCHOR",
            ),
            (
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage\nLoadObject",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                },
                "runtime trace plan DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY must be a non-empty single-line value",
            ),
            (
                {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                    "DUNE_UE4SS_PACKAGE_TRACE_GDB": " \t",
                },
                "runtime trace plan DUNE_UE4SS_PACKAGE_TRACE_GDB must be a non-empty single-line value",
            ),
        )
        for recommended_env, message in cases:
            with self.subTest(message=message):
                action = self.module.build_action(
                    trace_plan={
                        "sourceExternalPlan": "/tmp/package-external-plan.json",
                        "base": "0x100000",
                        "recommendedTraceEnv": recommended_env,
                    }
                )

                self.assertEqual(action["action"], "refresh-trace-plan")
                self.assertIn(message, action["tracePlanBlockers"])
                self.assertNotIn("traceEnv", action)
                self.assertNotIn("ue4ss-package-runtime-trace.sh arm", action["commands"][0])

    def test_explicit_wrong_schema_trace_plan_does_not_arm_trace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "not-a-trace-plan.json"
            path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-evidence-inventory/v1",
                        "recommendedTraceEnv": {
                            "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                            "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                            "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                            "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                        },
                    }
                ),
                encoding="utf-8",
            )

            trace_plan = self.module.load_trace_plan(path)
            action = self.module.build_action(trace_plan=trace_plan)

        self.assertEqual(action["action"], "refresh-trace-plan")
        self.assertIn("not a UE4SS package runtime trace plan", action["tracePlanBlockers"])
        self.assertNotIn("traceEnv", action)
        self.assertEqual(len(action["commands"]), 2)
        self.assertIn("--format json", action["commands"][0])
        self.assertIn(str(path), action["commands"][0])
        self.assertIn("--format markdown", action["commands"][1])
        self.assertNotIn("ue4ss-package-runtime-trace.sh arm", action["commands"][0])

    def test_trace_plan_can_emit_non_dune_process_pattern(self):
        action = self.module.build_action(
            trace_plan={
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                }
            },
            container="example-game-server",
            process_pattern="ExampleGame-Linux-Shipping",
        )

        self.assertEqual(action["action"], "arm-trace")
        self.assertEqual(
            action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN"],
            "ExampleGame-Linux-Shipping",
        )
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN=ExampleGame-Linux-Shipping", action["commands"][0])
        self.assertIn("example-game-server", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN=ExampleGame-Linux-Shipping", action["commands"][1])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PROCESS_PATTERN=ExampleGame-Linux-Shipping", action["commands"][2])

    def test_trace_plan_can_emit_explicit_target_pid(self):
        action = self.module.build_action(
            trace_plan={
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                }
            },
            target_pid="4242",
        )

        self.assertEqual(action["action"], "arm-trace")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_PID"], "4242")
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PID=4242", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PID=4242", action["commands"][1])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_PID=4242", action["commands"][2])
        self.assertIn("pid-4242", action["commands"][0])
        self.assertIn("pid-4242", action["commands"][1])
        self.assertIn("pid-4242", action["commands"][2])
        self.assertNotIn("dune_server-deep-desert-1", action["commands"][0])

    def test_trace_plan_can_emit_explicit_trace_host(self):
        action = self.module.build_action(
            trace_plan={
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                }
            },
            trace_host="example-host",
            target_pid="4242",
        )

        self.assertEqual(action["action"], "arm-trace")
        self.assertEqual(action["traceEnv"]["DUNE_UE4SS_PACKAGE_TRACE_HOST"], "example-host")
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_HOST=example-host", action["commands"][0])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_HOST=example-host", action["commands"][1])
        self.assertIn("DUNE_UE4SS_PACKAGE_TRACE_HOST=example-host", action["commands"][2])

    def test_invalid_trace_selectors_do_not_emit_replay_commands(self):
        cases = (
            {"trace_host": " \t", "message": "trace-host must be a non-empty single-line value"},
            {"process_pattern": "ExampleGame\nOther", "message": "process-pattern must be a non-empty single-line value"},
        )
        for case in cases:
            with self.subTest(message=case["message"]):
                action = self.module.build_action(
                    trace_plan={
                        "recommendedTraceEnv": {
                            "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                            "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                            "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                            "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                        }
                    },
                    trace_host=case.get("trace_host", ""),
                    process_pattern=case.get("process_pattern", ""),
                )

                self.assertEqual(action["action"], "complete-review")
                self.assertEqual(action["commands"], [])
                self.assertIn(case["message"], [row["error"] for row in action["promotionSummaryErrors"]])
                self.assertNotIn("traceEnv", action)

    def test_invalid_explicit_target_pid_does_not_arm_trace(self):
        action = self.module.build_action(
            trace_plan={
                "recommendedTraceEnv": {
                    "DUNE_UE4SS_PACKAGE_TRACE_ANCHOR": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_LIMIT": "1",
                    "DUNE_UE4SS_PACKAGE_TRACE_SIGNATURE_FAMILY": "LoadPackage",
                    "DUNE_UE4SS_PACKAGE_TRACE_HIT_INDEX": "auto",
                }
            },
            target_pid="not-a-pid",
        )

        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["promotionSummaryErrors"][0]["path"], "--target-pid")
        self.assertEqual(action["commands"], [])
        self.assertNotIn("traceEnv", action)

    def test_review_bundle_ready_manifest_plans_canary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_bundle(root, promotion_ready=True)
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertEqual(action["action"], "plan-canary")
        self.assertTrue(verification["ready"])
        self.assertIn("--package-promotion-json", action["commands"][0])
        self.assertIn("ue4ss-package-promotion-env.json", action["commands"][0])
        self.assertIn("--format json", action["commands"][0])
        self.assertIn("--format env", action["commands"][1])
        self.assertEqual(action["outputFiles"]["nextCanaryJson"], "/tmp/ue4ss-package-next-canary.json")
        self.assertEqual(action["outputFiles"]["nextCanaryEnv"], "/tmp/ue4ss-package-next-canary.env")

    def test_review_bundle_root_uses_newest_timestamped_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "20260621T000000Z"
            newer = root / "20260622T000000Z"
            self.write_bundle(older, promotion_ready=False)
            self.write_bundle(newer, promotion_ready=True)
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertEqual(action["action"], "plan-canary")
        self.assertTrue(verification["ready"])
        self.assertEqual(verification["bundle"], str(newer))
        self.assertIn(str(newer / "ue4ss-package-promotion-env.json"), action["commands"][0])
        self.assertIn("--format json", action["commands"][0])
        self.assertIn("--format env", action["commands"][1])
        self.assertEqual(action["outputFiles"]["nextCanaryJson"], "/tmp/ue4ss-package-next-canary.json")
        self.assertEqual(action["outputFiles"]["nextCanaryEnv"], "/tmp/ue4ss-package-next-canary.env")

    def test_review_bundle_root_uses_highest_numeric_suffix_for_same_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "20260622T000000Z-9"
            newer = root / "20260622T000000Z-10"
            self.write_bundle(older, promotion_ready=False)
            self.write_bundle(newer, promotion_ready=True)
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertEqual(action["action"], "plan-canary")
        self.assertTrue(verification["ready"])
        self.assertEqual(verification["bundle"], str(newer))
        self.assertIn(str(newer / "ue4ss-package-promotion-env.json"), action["commands"][0])

    def test_review_bundle_trace_plan_arms_trace_when_manifest_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_bundle(root, promotion_ready=False)
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertEqual(action["action"], "complete-review")
        self.assertTrue(verification["ready"])
        self.assertEqual(action["pending"]["signatureFamily"], "LoadPackage")

    def test_review_bundle_derives_summary_from_family_dir_when_summary_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_bundle(root, promotion_ready=False)
            self.write_family_review(root, "StaticLoadClass", 1, promotion_ready=False)
            self.write_family_review(root, "LoadPackage", 0, promotion_ready=False)
            self.refresh_bundle_checksums(root)
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertTrue(verification["ready"])
        self.assertEqual(summary["sourceArg"], "--package-promotion-dir")
        self.assertIn("ue4ss-package-family-reviews", summary["sourcePath"])
        self.assertEqual(summary["manifests"][0]["signatureFamily"], "LoadPackage")
        self.assertEqual(action["action"], "complete-review")
        self.assertEqual(action["pending"]["signatureFamily"], "LoadPackage")

    def test_review_bundle_prefers_family_dir_over_copied_summary_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_bundle(root, promotion_ready=False)
            self.write_family_review(root, "LoadPackage", 0, promotion_ready=True)
            trace_log_sha256 = hashlib.sha256((root / "trace.log").read_bytes()).hexdigest()
            stale_summary = {
                "schemaVersion": "dune-ue4ss-package-promotion-dir-summary/v1",
                "sourcePath": "/tmp/ue4ss-package-family-reviews.json",
                "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/stale-family-reviews/LoadPackage/promotion-env.json",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log",
                        "sourceEvidenceJsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "sourceLogSha256": trace_log_sha256,
                        "sourceLogExists": True,
                        "tracePid": 123,
                        "tracePidMatchesRequested": True,
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
                            "DUNE_PROBE_LOADER_LOAD_ASSET_PACKAGE_ABI_EVIDENCE": (
                                "runtime-trace:LoadPackage:caller=0x5000 rip=0x4ff0 "
                                "pid=123 "
                                "evidenceJsonSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
                                f"sourceLogSha256={trace_log_sha256}"
                            ),
                        },
                    }
                ],
            }
            (root / "ue4ss-package-family-reviews.json").write_text(
                json.dumps(stale_summary, sort_keys=True),
                encoding="utf-8",
            )
            manifest_path = root / "review-bundle-manifest.txt"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest_text += "artifact=ue4ss-package-family-reviews.json source=/tmp/ue4ss-package-family-reviews.json\n"
            manifest_path.write_text(manifest_text, encoding="utf-8")
            self.refresh_bundle_checksums(root)
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertTrue(verification["ready"])
        self.assertEqual(summary["sourceArg"], "--package-promotion-dir")
        self.assertIn(str(root / "ue4ss-package-family-reviews"), action["commands"][0])
        self.assertNotIn("/tmp/stale-family-reviews", action["commands"][0])

    def test_review_bundle_invalid_copied_summary_blocks_bundle_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_bundle(root, promotion_ready=False)
            copied_summary = {
                "readyManifestPaths": ["/tmp/stale-family-reviews/LoadPackage/promotion-env.json"],
            }
            (root / "ue4ss-package-family-reviews.json").write_text(
                json.dumps(copied_summary, sort_keys=True),
                encoding="utf-8",
            )
            self.refresh_bundle_checksums(root)
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertFalse(verification["ready"])
        self.assertEqual(action["action"], "verify-bundle")
        self.assertIn(
            "ue4ss-package-family-reviews.json has unsupported schemaVersion",
            verification["blockers"],
        )

    def test_invalid_review_bundle_blocks_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_bundle(root, promotion_ready=True)
            (root / "ue4ss-package-next-action.md").write_text("# tampered\n", encoding="utf-8")
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertEqual(action["action"], "verify-bundle")
        self.assertFalse(action["bundleVerification"]["ready"])
        self.assertIn("checksum mismatch: ue4ss-package-next-action.md", action["bundleVerification"]["blockers"])

    def test_pid_match_bundle_failure_names_trace_status_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_bundle(root, promotion_ready=True)
            manifest = root / "review-bundle-manifest.txt"
            lines = [
                line
                for line in manifest.read_text(encoding="utf-8").splitlines()
                if not line.startswith("tracePidMatchesRequested=")
            ]
            manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.refresh_bundle_checksums(root)
            summary, trace_plan, verification = self.module.bundle_inputs(root)
            action = self.module.build_action(
                promotion_summary=summary,
                trace_plan=trace_plan,
                bundle_verification=verification,
            )

        self.assertEqual(action["action"], "verify-bundle")
        self.assertFalse(action["bundleVerification"]["ready"])
        self.assertIn("tracePidMatchesRequested", action["bundleVerification"]["blockers"][0])
        self.assertIn("rerun package trace status with a resolved target PID", action["nextStep"])
        self.assertIn("tracePidMatchesRequested=true", action["nextStep"])

    def test_trace_pid_mismatch_bundle_failure_names_trace_status_recovery(self):
        action = self.module.build_action(
            bundle_verification={
                "ready": False,
                "bundle": "/tmp/ue4ss-package-review-bundles/latest",
                "blockers": [
                    "review-bundle-manifest.txt tracePid does not match runtime trace evidence pid"
                ],
            }
        )

        self.assertEqual(action["action"], "verify-bundle")
        self.assertIn("rerun package trace status with a resolved target PID", action["nextStep"])
        self.assertIn("manifest tracePid matches runtime evidence pid", action["nextStep"])

    def test_player_guard_bundle_failure_names_zero_player_status_recovery(self):
        action = self.module.build_action(
            bundle_verification={
                "ready": False,
                "bundle": "/tmp/ue4ss-package-review-bundles/latest",
                "blockers": [
                    "review-bundle-manifest.txt playerGuardConnectedPlayers must be 0 for live kspls0 package trace evidence"
                ],
            }
        )

        self.assertEqual(action["action"], "verify-bundle")
        self.assertIn("rerun remote package trace status on kspls0", action["nextStep"])
        self.assertIn("playerGuardConnectedPlayers=0", action["nextStep"])

    def test_no_hit_only_bundle_failure_drives_recovery_not_bundle_rejection(self):
        action = self.module.build_action(
            bundle_verification={
                "ready": False,
                "bundle": "/tmp/ue4ss-package-review-bundles/latest",
                "blockers": [
                    "ue4ss-package-abi-review.json selected runtime trace hit is missing for hitIndex 0"
                ],
            },
            live_trace_runbook={
                "sourcePath": "/tmp/ue4ss-package-stimulus-trace-runbook.json",
                "recommendedCandidate": "operator-client-map-entry",
                "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry.log",
                "reviewArtifacts": {
                    "reviewBundleVerificationJson": "/tmp/ue4ss-package-review-bundle-verification.json",
                    "digestProvenanceFields": "sourceEvidenceJson,sourceLogSha256,sourceEvidenceJsonSha256",
                },
                "commands": [
                    "scripts/ue4ss-package-remote-trace.sh preflight kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                    "scripts/ue4ss-package-remote-trace.sh arm kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                    "operator performs the approved client login/travel/map-entry package-load stimulus",
                    "scripts/ue4ss-package-remote-trace.sh status kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                    "scripts/ue4ss-package-remote-trace.sh stop kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                ],
            },
            route_static_review={
                "sourcePath": "/tmp/ue4ss-package-route-129d58a2-static-review.json",
                "routeAddress": "0x129d58a2",
                "routeSourceAddress": "0xa056aa2",
                "finding": "non-promotable-route-probe",
                "routeShape": {"callsite": "call *0x3d8(%rax)"},
                "sourceShape": {"callsite": "call *0x3a0(%rax)"},
                "staticVtableTargetReview": {
                    "finding": "no-static-vtable-table-ref",
                    "wrapperStaticRefCount": 0,
                    "childHelperStaticRefCount": 0,
                    "callgraphNodeCount": 2,
                    "packageAnchorNodeCount": 0,
                    "streamableNodeCount": 0,
                    "implication": "route object vtable identity must be recovered from runtime object/vtable memory",
                },
                "artifacts": {
                    "routeVtableTargetsJson": "/tmp/route-vtable-targets.json",
                    "routeVtableTargetCallgraphJson": "/tmp/route-vtable-target-callgraph.json",
                },
            },
            current_runtime_evidence={
                "sourcePath": "/tmp/bundle/ue4ss-package-runtime-trace-evidence.json",
                "hitCount": 0,
                "routeHitCount": 2,
                "methodHitCount": 1873,
                "routeSlotRecoveryReady": False,
                "routeSlotRecoveryMissingSlots": ["0x3a0", "0x3d8"],
                "routeSlotRecoveryBlockers": ["missing route vtable static slot matches: 0x3a0, 0x3d8"],
                "routeHits": [
                    {
                        "hitIndex": 0,
                        "imageOffset": "0xa056aa2",
                        "callerImageOffset": "0x129d58a2",
                        "staticSlotMatchCount": 0,
                    }
                ],
            },
        )

        self.assertEqual(action["action"], "recover-package-anchor")
        self.assertIn("captured no package hit", action["reason"])
        self.assertIn(
            "ue4ss-package-abi-review.json selected runtime trace hit is missing for hitIndex 0",
            action["blockers"],
        )
        self.assertIn(
            "route-slot recovery: missing route vtable static slot matches: 0x3a0, 0x3d8",
            action["blockers"],
        )
        self.assertIn("client login/travel/map-entry", action["nextStep"])
        self.assertEqual(action["liveTraceRunbook"]["recommendedCandidate"], "operator-client-map-entry")
        self.assertEqual(action["routeSlotRecovery"]["routeAddress"], "0x129d58a2")
        self.assertEqual(action["routeSlotRecovery"]["staticVtableFinding"], "no-static-vtable-table-ref")
        self.assertEqual(action["routeSlotRecovery"]["requiredRouteTrace"]["reviewField"], "routeVtableStaticSlotMatches")
        self.assertEqual(action["routeSlotRecovery"]["requiredRouteTrace"]["slots"], ["0x3a0", "0x3d8"])
        self.assertEqual(action["routeSlotRecovery"]["requiredRouteTrace"]["registers"], ["rbx", "r14"])
        self.assertEqual(action["routeSlotRecovery"]["currentRuntimeEvidence"]["routeHitCount"], 2)
        self.assertEqual(action["routeSlotRecovery"]["currentRuntimeEvidence"]["routeSlotRecoveryMissingSlots"], ["0x3a0", "0x3d8"])
        self.assertEqual(action["routeSlotRecovery"]["currentRuntimeEvidence"]["routeHits"][0]["callerImageOffset"], "0x129d58a2")
        self.assertIn("verify-ue4ss-package-route-slot-recovery.py", action["routeSlotRecovery"]["verificationCommand"])
        rendered = self.module.markdown(action)
        self.assertIn("Route slot recovery", rendered)
        self.assertIn("routeVtableStaticSlotMatches", rendered)
        self.assertIn("current evidence: hits=`0` routeHits=`2` methodHits=`1873` routeSlotReady=`false`", rendered)
        self.assertIn("current missing slots: `0x3a0, 0x3d8`", rendered)
        self.assertIn("current route hit: hitIndex=`0` imageOffset=`0xa056aa2` callerImageOffset=`0x129d58a2`", rendered)
        self.assertIn("verify-ue4ss-package-route-slot-recovery.py", rendered)
        self.assertIn("ue4ss-package-live-call-frame-recovery-plan.json", action["commands"][1])
        self.assertIn("ue4ss-package-server-replay-plan.json", action["commands"][2])
        self.assertTrue(any("remote-trace.sh arm" in command for command in action["commands"]))

    def test_no_hit_bundle_recovery_flags_stale_embedded_route_slot_runbook(self):
        route_requirement = {
            "expectedTraceMarker": "UE4SS_PACKAGE_ROUTE_TRACE_HIT",
            "routeAddress": "0x129d58a2",
            "reviewField": "routeVtableStaticSlotMatches",
            "requiredSlots": ["0x3a0", "0x3d8"],
            "requiredRegisters": ["rbx", "r14"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / "ue4ss-package-stimulus-trace-runbook.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "dune-ue4ss-package-stimulus-trace-runbook/v1",
                        "traceInputs": {"routeAddress": "0xa056aa2"},
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            action = self.module.build_action(
                bundle_verification={
                    "ready": False,
                    "bundle": str(bundle),
                    "blockers": [
                        "ue4ss-package-abi-review.json selected runtime trace hit is missing for hitIndex 0"
                    ],
                },
                live_trace_runbook={
                    "sourcePath": "/tmp/ue4ss-package-stimulus-trace-runbook.json",
                    "recommendedCandidate": "operator-client-map-entry",
                    "traceLog": "/tmp/ue4ss-package-runtime-trace-live-client-map-entry.log",
                    "coordinatorCommand": "scripts/run-ue4ss-package-live-stimulus-trace.sh",
                    "routeSlotTraceRequirement": route_requirement,
                    "commands": [
                        "scripts/ue4ss-package-remote-trace.sh arm kspls0 dune_server-deep-desert-1 /tmp/trace.log",
                    ],
                },
                route_static_review={
                    "routeAddress": "0x129d58a2",
                    "routeShape": {"callsite": "call *0x3d8(%rax)"},
                    "sourceShape": {"callsite": "call *0x3a0(%rax)"},
                    "staticVtableTargetReview": {},
                },
            )

        self.assertEqual(action["action"], "recover-package-anchor")
        self.assertIn(
            "review bundle stimulus trace runbook routeSlotTraceRequirement is stale or missing",
            action["blockers"],
        )

    def test_no_hit_bundle_with_integrity_failure_still_blocks_bundle_use(self):
        action = self.module.build_action(
            bundle_verification={
                "ready": False,
                "bundle": "/tmp/ue4ss-package-review-bundles/latest",
                "blockers": [
                    "ue4ss-package-abi-review.json selected runtime trace hit is missing for hitIndex 0",
                    "checksum mismatch: ue4ss-package-next-action.md",
                ],
            }
        )

        self.assertEqual(action["action"], "verify-bundle")
        self.assertIn("fix or regenerate", action["nextStep"])

    def test_ready_summary_row_rejects_multiline_identity_fields(self):
        action = self.module.build_action(
            promotion_summary={
                "sourcePath": "/tmp/family-summary.json",
                "readyManifestPaths": ["/tmp/families/LoadPackage/promotion-env.json"],
                "manifests": [
                    {
                        "path": "/tmp/families/LoadPackage/promotion-env.json",
                        "signatureFamily": "LoadPackage",
                        "hitIndex": 0,
                        "selectedHitSeed": "LoadPackage",
                        "sourceEvidence": "/tmp/trace.log\nstale",
                        "sourceLogExists": True,
                        "imagePath": "/srv/dune/DuneSandboxServer-Linux-Shipping\nold",
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
            }
        )

        self.assertEqual(action["action"], "complete-review")
        errors = [row["error"] for row in action["promotionSummaryErrors"]]
        self.assertIn(
            "ready package promotion summary row sourceEvidence must be a non-empty single-line value",
            errors,
        )
        self.assertIn(
            "ready package promotion summary row imagePath must be a non-empty single-line value",
            errors,
        )
        self.assertNotIn("readyManifestPaths", action)

    def test_markdown_includes_commands_and_pending_flags(self):
        action = self.module.build_action(
            promotion_summary={
                "manifests": [
                    {
                        "signatureFamily": "LoadObject",
                        "hitIndex": "auto",
                        "missingReviewFlags": ["--reviewed-tchar"],
                    }
                ]
            }
        )
        rendered = self.module.markdown(action)

        self.assertIn("# UE4SS Package Next Action", rendered)
        self.assertIn("Action: `complete-review`", rendered)
        self.assertIn("missing review flag: `--reviewed-tchar`", rendered)
        self.assertIn("Commands:", rendered)


if __name__ == "__main__":
    unittest.main()
