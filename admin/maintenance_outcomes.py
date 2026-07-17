#!/usr/bin/env python3
"""Signed, semantically verified maintenance execution outcome receipts."""

import datetime
import hashlib
import hmac
import json
import math
import os
import pathlib
import re
import secrets
import threading
import time


SCHEMA = "dune-maintenance-outcome/v1"
RECEIPT_SCHEMA = 1
RECEIPT_PATTERN = re.compile(r"^maintenance-outcome-[0-9a-f]{32}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
JOB_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TARGET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
OUTCOMES = frozenset(("passed", "failed", "deferred", "dry-run"))
POLICIES = frozenset(("current", "certified", "automatic"))
STAGE_NAMES = (
    "preflight", "disconnect", "stop", "backup", "update", "start",
    "online", "recovery", "reboot",
)
LOCK = threading.RLock()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def iso(value=None):
    stamp = float(time.time() if value is None else value)
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value):
    text = str(value or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("maintenance outcome timestamps must include a timezone")
    return parsed.timestamp()


def bounded_text(value, maximum, name, *, required=False):
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"maintenance outcome {name} is required")
    if len(text) > maximum or any(ord(character) < 32 for character in text):
        raise ValueError(f"maintenance outcome {name} is invalid")
    return text


def bounded_duration(value):
    if isinstance(value, bool):
        raise ValueError("maintenance stage duration is invalid")
    number = int(value or 0)
    if not 0 <= number <= 86_400_000:
        raise ValueError("maintenance stage duration is invalid")
    return number


def normalize_stage(value):
    if not isinstance(value, dict) or set(value) != {"required", "attempted", "ok", "durationMs", "returncode"}:
        raise ValueError("maintenance outcome stage fields are invalid")
    if any(type(value[key]) is not bool for key in ("required", "attempted", "ok")):
        raise ValueError("maintenance outcome stage booleans are invalid")
    required = value["required"]
    attempted = value["attempted"]
    ok = value["ok"]
    if not attempted and ok is not (not required):
        raise ValueError("an unattempted maintenance stage has an inconsistent verdict")
    duration = bounded_duration(value["durationMs"])
    returncode = value["returncode"]
    if returncode is not None and (isinstance(returncode, bool) or not isinstance(returncode, int) or not -255 <= returncode <= 255):
        raise ValueError("maintenance outcome stage return code is invalid")
    if not attempted and (duration != 0 or returncode is not None):
        raise ValueError("an unattempted maintenance stage cannot have execution evidence")
    return {"required": required, "attempted": attempted, "ok": ok, "durationMs": duration, "returncode": returncode}


def stage_from_result(value, *, required=False):
    attempted = isinstance(value, dict)
    if not attempted:
        return {"required": bool(required), "attempted": False, "ok": not bool(required), "durationMs": 0, "returncode": None}
    return normalize_stage({
        "required": bool(required),
        "attempted": True,
        "ok": bool(value.get("ok")),
        "durationMs": value.get("durationMs") or 0,
        "returncode": value.get("returncode") if isinstance(value.get("returncode"), int) and not isinstance(value.get("returncode"), bool) else None,
    })


def receipt_hash(receipt):
    return hashlib.sha256(canonical({key: value for key, value in receipt.items() if key != "receiptSha256"}).encode()).hexdigest()


def signed_document(receipt, secret, generated_at=None):
    receipt = json.loads(canonical(receipt))
    receipt["receiptSha256"] = receipt_hash(receipt)
    payload = {
        "schemaVersion": SCHEMA,
        "generatedAt": iso(generated_at),
        "signingKeyFingerprint": hashlib.sha256(secret).hexdigest(),
        "receipt": receipt,
    }
    return {**payload, "signature": hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()}


def _candidate(value):
    value = value if isinstance(value, dict) else {}
    expected = {"status", "fingerprint", "imageTag", "currentImageTag", "updateRequired"}
    if value and set(value) != expected:
        raise ValueError("maintenance outcome candidate fields are invalid")
    normalized = {}
    for key, maximum in (("status", 32), ("fingerprint", 64), ("imageTag", 128), ("currentImageTag", 128)):
        normalized[key] = bounded_text(value.get(key), maximum, f"candidate {key}") or None
    if normalized["fingerprint"] is not None and not HASH_PATTERN.fullmatch(normalized["fingerprint"]):
        raise ValueError("maintenance outcome candidate fingerprint is invalid")
    normalized["updateRequired"] = bool(value.get("updateRequired"))
    return normalized


def _readiness(value):
    value = value if isinstance(value, dict) else {}
    if value and set(value) != {"id", "sha256"}:
        raise ValueError("maintenance outcome readiness fields are invalid")
    receipt_id = bounded_text(value.get("id"), 128, "readiness receipt id") or None
    receipt_sha = bounded_text(value.get("sha256"), 64, "readiness receipt digest") or None
    if receipt_id is not None and not re.fullmatch(r"update-readiness-[0-9a-f]{32}", receipt_id):
        raise ValueError("maintenance outcome readiness receipt id is invalid")
    if receipt_sha is not None and not HASH_PATTERN.fullmatch(receipt_sha):
        raise ValueError("maintenance outcome readiness receipt digest is invalid")
    if (receipt_id is None) != (receipt_sha is None):
        raise ValueError("maintenance outcome readiness identity is incomplete")
    return {"id": receipt_id, "sha256": receipt_sha}


def _backup(value):
    if not isinstance(value, dict) or set(value) != {"required", "attempted", "verified", "path"}:
        raise ValueError("maintenance outcome backup fields are invalid")
    if any(type(value[key]) is not bool for key in ("required", "attempted", "verified")):
        raise ValueError("maintenance outcome backup booleans are invalid")
    path = bounded_text(value.get("path"), 512, "backup path") or None
    if value["verified"] and (not value["attempted"] or not path):
        raise ValueError("verified maintenance backup evidence is incomplete")
    if not value["attempted"] and path:
        raise ValueError("unattempted maintenance backup cannot have a path")
    return {"required": value["required"], "attempted": value["attempted"], "verified": value["verified"], "path": path}


def build_receipt(job, result, started_at, completed_at):
    if not isinstance(job, dict) or not isinstance(result, dict):
        raise ValueError("maintenance outcome job and result must be objects")
    started = float(started_at)
    completed = float(completed_at)
    if not math.isfinite(started) or not math.isfinite(completed) or not 0 <= completed - started <= 86400:
        raise ValueError("maintenance outcome execution interval is invalid")
    dry_run = bool(result.get("dryRun"))
    action = str(job.get("action") or result.get("action") or "restart").strip().lower()
    if action not in {"restart", "shutdown"}:
        raise ValueError("maintenance outcome action is invalid")
    requested_policy = str(job.get("updatePolicy") or "current").strip().lower()
    preflight = result.get("updatePreflight") if isinstance(result.get("updatePreflight"), dict) else {}
    effective_policy = str(preflight.get("effectivePolicy") or preflight.get("policy") or requested_policy).strip().lower()
    if result.get("updateSuppressedByBackupFailure"):
        effective_policy = "current"
    if requested_policy not in POLICIES or effective_policy not in POLICIES:
        raise ValueError("maintenance outcome update policy is invalid")
    ready = bool(result.get("ok"))
    deferred = bool(result.get("deferred"))
    outcome = "dry-run" if dry_run and ready else "deferred" if deferred and ready else "passed" if ready else "failed"
    backup_result = result.get("backup") if isinstance(result.get("backup"), dict) else None
    verification = (backup_result or {}).get("verification") if isinstance((backup_result or {}).get("verification"), dict) else {}
    backup_path = verification.get("path") or (backup_result or {}).get("path")
    if backup_path:
        backup_path = str(backup_path)
        marker = "/backups/"
        if marker in backup_path:
            backup_path = backup_path.split(marker, 1)[1]
    backup_required = bool(job.get("backup", True)) and not dry_run
    backup = {
        "required": backup_required,
        "attempted": backup_result is not None,
        "verified": bool(verification.get("ok")) or bool((backup_result or {}).get("verified")),
        "path": backup_path or None,
    }
    required = {
        "preflight": not dry_run,
        "disconnect": not dry_run and bool(job.get("requireSoftDisconnect", True)),
        "stop": not dry_run,
        "backup": backup_required,
        "update": not dry_run and isinstance(result.get("update"), dict) and not result.get("update", {}).get("skipped"),
        "start": not dry_run and action == "restart" and isinstance(result.get("stop"), dict) and bool(result["stop"].get("ok")),
        "online": not dry_run and action == "restart" and isinstance(result.get("start"), dict),
        "recovery": isinstance(result.get("recovery"), dict),
        "reboot": isinstance(result.get("reboot"), dict),
    }
    stages = {
        "preflight": stage_from_result(preflight if preflight else None, required=required["preflight"]),
        "disconnect": stage_from_result(result.get("disconnect"), required=required["disconnect"]),
        "stop": stage_from_result(result.get("stop"), required=required["stop"]),
        "backup": stage_from_result(backup_result, required=required["backup"]),
        "update": stage_from_result(result.get("update"), required=required["update"]),
        "start": stage_from_result(result.get("start"), required=required["start"]),
        "online": stage_from_result(result.get("online"), required=required["online"]),
        "recovery": stage_from_result(result.get("recovery"), required=required["recovery"]),
        "reboot": stage_from_result(result.get("reboot"), required=required["reboot"]),
    }
    warnings = result.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = [warnings]
    warnings = [bounded_text(value, 1000, "warning", required=True) for value in warnings[:32]]
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA,
        "id": "maintenance-outcome-" + secrets.token_hex(16),
        "jobId": bounded_text(job.get("id"), 128, "job id", required=True),
        "principalId": bounded_text(job.get("principalId") or "system", 128, "principal", required=True),
        "target": bounded_text(job.get("target"), 64, "target", required=True),
        "action": action,
        "requestedUpdatePolicy": requested_policy,
        "effectiveUpdatePolicy": effective_policy,
        "scheduledAt": iso(job.get("runAt") or started),
        "startedAt": iso(started),
        "completedAt": iso(completed),
        "durationMs": int(round((completed - started) * 1000)),
        "outcome": outcome,
        "ready": ready,
        "dryRun": dry_run,
        "deferred": deferred,
        "serviceRecovered": bool(result.get("serviceRecovered")),
        "updateAttempted": bool(stages["update"]["attempted"] and not result.get("update", {}).get("skipped")),
        "updateApplied": bool(result.get("updateApplied")),
        "candidateUpdateBlocked": bool(preflight.get("candidateUpdateBlocked") or result.get("updateSuppressedByBackupFailure")),
        "candidate": _candidate(preflight.get("candidate")),
        "readinessReceipt": _readiness({"id": preflight.get("receiptId"), "sha256": preflight.get("receiptSha256")}),
        "backup": _backup(backup),
        "stages": stages,
        "warnings": warnings,
        "recoveryExecuted": bool(stages["recovery"]["attempted"]),
        "gameDataMutationExecuted": False,
    }
    return receipt


EXPECTED_FIELDS = {
    "schemaVersion", "id", "jobId", "principalId", "target", "action",
    "requestedUpdatePolicy", "effectiveUpdatePolicy", "scheduledAt", "startedAt",
    "completedAt", "durationMs", "outcome", "ready", "dryRun", "deferred",
    "serviceRecovered", "updateAttempted", "updateApplied", "candidateUpdateBlocked",
    "candidate", "readinessReceipt", "backup", "stages", "warnings",
    "recoveryExecuted", "gameDataMutationExecuted", "receiptSha256",
}


def verify_signed_document(document, secret, now=None):
    try:
        if not isinstance(document, dict) or set(document) != {"schemaVersion", "generatedAt", "signingKeyFingerprint", "receipt", "signature"}:
            raise ValueError("maintenance outcome signed document fields are invalid")
        if document.get("schemaVersion") != SCHEMA:
            raise ValueError("maintenance outcome schema is invalid")
        payload = {key: value for key, value in document.items() if key != "signature"}
        expected_signature = hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(document.get("signature") or ""), expected_signature):
            raise ValueError("maintenance outcome signature is invalid")
        if not hmac.compare_digest(str(document.get("signingKeyFingerprint") or ""), hashlib.sha256(secret).hexdigest()):
            raise ValueError("maintenance outcome signing key fingerprint does not match")
        epoch(document.get("generatedAt"))
        receipt = document.get("receipt")
        if not isinstance(receipt, dict) or set(receipt) != EXPECTED_FIELDS or receipt.get("schemaVersion") != RECEIPT_SCHEMA:
            raise ValueError("maintenance outcome receipt fields are invalid")
        if not RECEIPT_PATTERN.fullmatch(str(receipt.get("id") or "")) or not JOB_PATTERN.fullmatch(str(receipt.get("jobId") or "")):
            raise ValueError("maintenance outcome receipt identity is invalid")
        bounded_text(receipt.get("principalId"), 128, "principal", required=True)
        if not TARGET_PATTERN.fullmatch(str(receipt.get("target") or "")) or receipt.get("action") not in {"restart", "shutdown"}:
            raise ValueError("maintenance outcome target or action is invalid")
        if receipt.get("requestedUpdatePolicy") not in POLICIES or receipt.get("effectiveUpdatePolicy") not in POLICIES:
            raise ValueError("maintenance outcome update policy is invalid")
        scheduled = epoch(receipt.get("scheduledAt"))
        started = epoch(receipt.get("startedAt"))
        completed = epoch(receipt.get("completedAt"))
        if scheduled > started + 300 or not 0 <= completed - started <= 86400:
            raise ValueError("maintenance outcome timestamps are invalid")
        duration = bounded_duration(receipt.get("durationMs"))
        if abs(duration - round((completed - started) * 1000)) > 2000:
            raise ValueError("maintenance outcome duration does not match its timestamps")
        for key in ("ready", "dryRun", "deferred", "serviceRecovered", "updateAttempted", "updateApplied", "candidateUpdateBlocked", "recoveryExecuted", "gameDataMutationExecuted"):
            if type(receipt.get(key)) is not bool:
                raise ValueError("maintenance outcome receipt booleans are invalid")
        expected_outcome = "dry-run" if receipt["dryRun"] and receipt["ready"] else "deferred" if receipt["deferred"] and receipt["ready"] else "passed" if receipt["ready"] else "failed"
        if receipt.get("outcome") not in OUTCOMES or receipt.get("outcome") != expected_outcome:
            raise ValueError("maintenance outcome verdict is inconsistent")
        if receipt["updateApplied"] and not receipt["updateAttempted"]:
            raise ValueError("maintenance outcome cannot apply an unattempted update")
        if receipt["gameDataMutationExecuted"] is not False:
            raise ValueError("maintenance outcome cannot claim a game-data mutation")
        if _candidate(receipt.get("candidate")) != receipt.get("candidate"):
            raise ValueError("maintenance outcome candidate is not canonical")
        if _readiness(receipt.get("readinessReceipt")) != receipt.get("readinessReceipt"):
            raise ValueError("maintenance outcome readiness identity is not canonical")
        backup = _backup(receipt.get("backup"))
        stages = receipt.get("stages")
        if not isinstance(stages, dict) or set(stages) != set(STAGE_NAMES):
            raise ValueError("maintenance outcome stages are invalid")
        normalized_stages = {name: normalize_stage(stages[name]) for name in STAGE_NAMES}
        if receipt["recoveryExecuted"] is not normalized_stages["recovery"]["attempted"]:
            raise ValueError("maintenance outcome recovery verdict is inconsistent")
        if backup["attempted"] is not normalized_stages["backup"]["attempted"] or (backup["verified"] and not normalized_stages["backup"]["ok"]):
            raise ValueError("maintenance outcome backup stage is inconsistent")
        warnings = receipt.get("warnings")
        if not isinstance(warnings, list) or len(warnings) > 32:
            raise ValueError("maintenance outcome warnings are invalid")
        for warning in warnings:
            bounded_text(warning, 1000, "warning", required=True)
        expected_hash = receipt_hash(receipt)
        if not HASH_PATTERN.fullmatch(str(receipt.get("receiptSha256") or "")) or not hmac.compare_digest(receipt["receiptSha256"], expected_hash):
            raise ValueError("maintenance outcome receipt digest is invalid")
        return {
            "ok": True, "signatureValid": True, "receiptValid": True,
            "receiptId": receipt["id"], "receiptSha256": receipt["receiptSha256"],
            "ready": receipt["ready"], "outcome": receipt["outcome"],
            "expired": False,
        }
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"ok": False, "signatureValid": False, "receiptValid": False, "error": str(exc)}


class Store:
    def __init__(self, evidence_root, secret, retention=400, owner_uid=None, owner_gid=None):
        self.evidence_root = pathlib.Path(evidence_root)
        self.secret = bytes(secret)
        self.retention = max(10, min(int(retention), 5000))
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None

    def _secure(self, path):
        os.chmod(path, 0o700 if pathlib.Path(path).is_dir() else 0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(path, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)

    def initialize(self):
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self._secure(self.evidence_root)
        for path in self.evidence_root.glob("maintenance-outcome-*.signed.json"):
            if path.is_file() and not path.is_symlink():
                self._secure(path)

    def _write(self, path, document):
        self.initialize()
        temporary = path.with_suffix(path.suffix + ".tmp-" + secrets.token_hex(8))
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(document, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._secure(temporary)
            temporary.replace(path)
            self._secure(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _paths(self):
        self.initialize()
        return sorted(
            (path for path in self.evidence_root.glob("maintenance-outcome-*.signed.json") if path.is_file() and not path.is_symlink()),
            key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True,
        )

    def _prune(self):
        for path in self._paths()[self.retention:]:
            path.unlink(missing_ok=True)

    def record(self, job, result, started_at, completed_at):
        receipt = build_receipt(job, result, started_at, completed_at)
        document = signed_document(receipt, self.secret, generated_at=completed_at)
        path = self.evidence_root / f"{receipt['id']}.signed.json"
        with LOCK:
            self._write(path, document)
            self._prune()
        return {"document": document, "evidencePath": str(path), "verification": verify_signed_document(document, self.secret)}

    def status(self, limit=100):
        limit = max(1, min(int(limit), self.retention))
        all_rows = []
        all_valid = True
        for path in self._paths():
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                verification = verify_signed_document(document, self.secret)
                receipt = document.get("receipt") or {}
                row = {
                    "id": receipt.get("id"), "jobId": receipt.get("jobId"),
                    "target": receipt.get("target"), "action": receipt.get("action"),
                    "outcome": receipt.get("outcome"), "ready": bool(receipt.get("ready")),
                    "startedAt": receipt.get("startedAt"), "completedAt": receipt.get("completedAt"),
                    "durationMs": receipt.get("durationMs"), "requestedUpdatePolicy": receipt.get("requestedUpdatePolicy"),
                    "effectiveUpdatePolicy": receipt.get("effectiveUpdatePolicy"), "updateApplied": bool(receipt.get("updateApplied")),
                    "candidateUpdateBlocked": bool(receipt.get("candidateUpdateBlocked")), "backup": receipt.get("backup"),
                    "serviceRecovered": bool(receipt.get("serviceRecovered")), "warnings": receipt.get("warnings") or [],
                    "receiptSha256": receipt.get("receiptSha256"), "file": path.name, "verification": verification,
                }
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                verification = {"ok": False, "error": str(exc)}
                row = {"id": path.stem, "file": path.name, "ready": False, "outcome": "invalid", "verification": verification}
            all_valid = all_valid and bool(verification.get("ok"))
            all_rows.append(row)
        rows = all_rows[:limit]
        latest = all_rows[0] if all_rows else None
        passed = sum(1 for row in all_rows if row.get("outcome") in {"passed", "dry-run", "deferred"} and (row.get("verification") or {}).get("ok"))
        return {
            "ok": all_valid, "schemaVersion": RECEIPT_SCHEMA, "retention": self.retention,
            "latest": latest, "receipts": rows,
            "summary": {"retained": len(all_rows), "returned": len(rows), "passed": passed, "failed": len(all_rows) - passed},
        }

    def prometheus(self):
        status = self.status(limit=self.retention)
        latest = status.get("latest") or {}
        completed = epoch(latest["completedAt"]) if latest.get("completedAt") and (latest.get("verification") or {}).get("ok") else "NaN"
        duration = float(latest.get("durationMs") or 0) / 1000.0
        backup = latest.get("backup") or {}
        return "\n".join([
            f"dash_maintenance_outcome_collector_up {1 if status['ok'] else 0}",
            f"dash_maintenance_outcome_latest_ready {1 if latest.get('ready') and (latest.get('verification') or {}).get('ok') else 0}",
            f"dash_maintenance_outcome_latest_backup_verified {1 if backup.get('verified') else 0}",
            f"dash_maintenance_outcome_latest_service_recovered {1 if latest.get('serviceRecovered') else 0}",
            f"dash_maintenance_outcome_latest_duration_seconds {duration:.6f}",
            f"dash_maintenance_outcome_last_completion_timestamp_seconds {completed}",
            f"dash_maintenance_outcome_retained_receipts {status['summary']['retained']}",
            f"dash_maintenance_outcome_retained_failures {status['summary']['failed']}",
        ]) + "\n"
