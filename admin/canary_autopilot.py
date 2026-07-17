#!/usr/bin/env python3
"""Durable scheduling policy for DASH's isolated signed canaries."""

import datetime
import json
import os
import pathlib
import secrets
import time


SCHEMA = "dune-canary-autopilot-state/v1"
TARGETS = ("community", "creator-modding", "public-ip-repair")


def iso(value=None):
    value = time.time() if value is None else float(value)
    return datetime.datetime.fromtimestamp(value, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value):
    if value in (None, ""):
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("canary autopilot timestamp lacks a timezone")
    return parsed.timestamp()


def _target_state():
    return {
        "attempts": 0, "failures": 0, "consecutiveFailures": 0,
        "lastAttemptAt": None, "lastSuccessAt": None, "nextAttemptAt": None,
        "lastReceiptId": None, "lastError": None,
    }


def fresh_state(now=None):
    return {
        "schemaVersion": SCHEMA, "updatedAt": iso(now), "lastPollAt": None,
        "lastError": None, "attemptsTotal": 0, "failuresTotal": 0,
        "targets": {target: _target_state() for target in TARGETS}, "history": [],
    }


def validate_state(value):
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion", "updatedAt", "lastPollAt", "lastError",
        "attemptsTotal", "failuresTotal", "targets", "history",
    } or value.get("schemaVersion") != SCHEMA:
        raise ValueError("canary autopilot state fields are invalid")
    epoch(value["updatedAt"])
    epoch(value.get("lastPollAt"))
    if value.get("lastError") is not None and not isinstance(value["lastError"], str):
        raise ValueError("canary autopilot last error is invalid")
    for key in ("attemptsTotal", "failuresTotal"):
        if isinstance(value.get(key), bool) or not isinstance(value.get(key), int) or not 0 <= value[key] <= 10**12:
            raise ValueError("canary autopilot counter is invalid")
    targets = value.get("targets")
    if not isinstance(targets, dict) or tuple(sorted(targets)) != tuple(sorted(TARGETS)):
        raise ValueError("canary autopilot targets are invalid")
    expected = set(_target_state())
    for target in TARGETS:
        row = targets[target]
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError("canary autopilot target state fields are invalid")
        for key in ("attempts", "failures", "consecutiveFailures"):
            if isinstance(row.get(key), bool) or not isinstance(row.get(key), int) or not 0 <= row[key] <= 10**12:
                raise ValueError("canary autopilot target counter is invalid")
        for key in ("lastAttemptAt", "lastSuccessAt", "nextAttemptAt"):
            epoch(row.get(key))
        for key in ("lastReceiptId", "lastError"):
            if row.get(key) is not None and not isinstance(row[key], str):
                raise ValueError("canary autopilot target detail is invalid")
    history = value.get("history")
    if not isinstance(history, list) or len(history) > 5000:
        raise ValueError("canary autopilot history is invalid")
    for row in history:
        if not isinstance(row, dict) or set(row) != {
            "target", "trigger", "startedAt", "completedAt", "ready", "receiptId", "error",
        } or row.get("target") not in TARGETS or row.get("trigger") not in ("automatic", "manual"):
            raise ValueError("canary autopilot history row is invalid")
        epoch(row.get("startedAt")); epoch(row.get("completedAt"))
        if type(row.get("ready")) is not bool:
            raise ValueError("canary autopilot history verdict is invalid")
        for key in ("receiptId", "error"):
            if row.get(key) is not None and not isinstance(row[key], str):
                raise ValueError("canary autopilot history detail is invalid")
    return value


class Store:
    def __init__(self, path, *, retention=200, owner_uid=None, owner_gid=None):
        self.path = pathlib.Path(path)
        self.retention = max(10, min(int(retention), 5000))
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None

    def _secure(self, path):
        os.chmod(path, 0o700 if pathlib.Path(path).is_dir() else 0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(path, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)

    def initialize(self):
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("canary autopilot state path cannot be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.parent.is_symlink() or not self.path.parent.is_dir():
            raise ValueError("canary autopilot state parent is invalid")
        self._secure(self.path.parent)
        if not self.path.exists():
            self.save(fresh_state())
        elif self.path.is_symlink() or not self.path.is_file():
            raise ValueError("canary autopilot state must be a regular file")
        self._secure(self.path)

    def load(self):
        self.initialize()
        if not 1 <= self.path.stat().st_size <= 4 * 1024 * 1024:
            raise ValueError("canary autopilot state size is invalid")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("canary autopilot state cannot be decoded") from exc
        return validate_state(value)

    def save(self, value):
        validate_state(value)
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("canary autopilot state path cannot be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._secure(self.path.parent)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp-" + secrets.token_hex(8))
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                handle.write("\n")
                handle.flush(); os.fsync(handle.fileno())
            self._secure(temporary)
            temporary.replace(self.path)
            self._secure(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def poll(self, now=None):
        state = self.load()
        state["lastPollAt"] = iso(now)
        state["updatedAt"] = iso(now)
        state["lastError"] = None
        self.save(state)
        return state

    def record(self, target, *, trigger, started_at, completed_at, ready, receipt_id=None,
               error=None, base_backoff_seconds=900, max_backoff_seconds=86400):
        if target not in TARGETS or trigger not in ("automatic", "manual"):
            raise ValueError("canary autopilot result identity is invalid")
        state = self.load()
        row = state["targets"][target]
        row["attempts"] += 1; state["attemptsTotal"] += 1
        row["lastAttemptAt"] = iso(completed_at)
        row["lastReceiptId"] = str(receipt_id)[:200] if receipt_id else None
        if ready:
            row["consecutiveFailures"] = 0
            row["lastSuccessAt"] = iso(completed_at)
            row["nextAttemptAt"] = None
            row["lastError"] = None
        else:
            row["failures"] += 1; state["failuresTotal"] += 1
            row["consecutiveFailures"] += 1
            delay = min(int(max_backoff_seconds), int(base_backoff_seconds) * (2 ** min(row["consecutiveFailures"] - 1, 20)))
            row["nextAttemptAt"] = iso(float(completed_at) + max(1, delay))
            row["lastError"] = str(error or "canary did not produce a ready receipt")[:1000]
        state["history"].insert(0, {
            "target": target, "trigger": trigger, "startedAt": iso(started_at),
            "completedAt": iso(completed_at), "ready": bool(ready),
            "receiptId": row["lastReceiptId"], "error": row["lastError"],
        })
        state["history"] = state["history"][:self.retention]
        state["updatedAt"] = iso(completed_at)
        self.save(state)
        return state


def target_status(target, enabled, evidence, retry, *, refresh_before_seconds, now=None):
    now = time.time() if now is None else float(now)
    latest = (evidence or {}).get("latest") or {}
    verification = latest.get("verification") or {}
    max_age = max(300, int((evidence or {}).get("maxAgeSeconds") or 7 * 86400))
    age = float(verification.get("ageSeconds") or 0) if verification.get("ok") else None
    remaining = max(0.0, max_age - age) if age is not None else None
    current = bool((evidence or {}).get("currentReady"))
    due = False
    reason = "disabled"
    if enabled:
        if not latest:
            due, reason = True, "missing"
        elif not (evidence or {}).get("ok", False) or not verification.get("ok", False):
            due, reason = True, "evidence-invalid"
        elif not verification.get("ready", latest.get("ready", False)):
            due, reason = True, "failed"
        elif verification.get("policyCurrent") is False or verification.get("inputsCurrent") is False:
            due, reason = True, "input-drift"
        elif not verification.get("ageCurrent", False):
            due, reason = True, "expired"
        elif remaining is not None and remaining <= min(max_age, max(60, int(refresh_before_seconds))):
            due, reason = True, "expiring"
        else:
            reason = "current"
    next_attempt = epoch((retry or {}).get("nextAttemptAt"))
    backoff = bool(due and next_attempt is not None and now < next_attempt)
    return {
        "id": target, "enabled": bool(enabled), "currentReady": current,
        "due": due, "runnable": bool(due and not backoff), "reason": reason,
        "ageSeconds": age, "remainingSeconds": remaining,
        "refreshBeforeSeconds": min(max_age, max(60, int(refresh_before_seconds))),
        "nextAttemptAt": (retry or {}).get("nextAttemptAt"), "backoff": backoff,
        "attempts": int((retry or {}).get("attempts") or 0),
        "failures": int((retry or {}).get("failures") or 0),
        "consecutiveFailures": int((retry or {}).get("consecutiveFailures") or 0),
        "lastAttemptAt": (retry or {}).get("lastAttemptAt"),
        "lastSuccessAt": (retry or {}).get("lastSuccessAt"),
        "lastReceiptId": (retry or {}).get("lastReceiptId"),
        "lastError": (retry or {}).get("lastError"),
    }


def public_status(state, evidence_by_target, enabled_by_target, *, enabled=True,
                  running=False, refresh_before_seconds=86400, now=None):
    now = time.time() if now is None else float(now)
    targets = [target_status(
        target, enabled_by_target.get(target, False), evidence_by_target.get(target) or {},
        (state.get("targets") or {}).get(target) or {},
        refresh_before_seconds=refresh_before_seconds, now=now,
    ) for target in TARGETS]
    active = [row for row in targets if row["enabled"]]
    due = [row for row in active if row["due"]]
    return {
        "ok": True, "enabled": bool(enabled), "running": bool(running),
        "lastPollAt": state.get("lastPollAt"), "lastError": state.get("lastError"),
        "attemptsTotal": state.get("attemptsTotal", 0),
        "failuresTotal": state.get("failuresTotal", 0),
        "refreshBeforeSeconds": int(refresh_before_seconds),
        "summary": {
            "targets": len(active), "current": sum(1 for row in active if row["currentReady"]),
            "due": len(due), "runnable": sum(1 for row in due if row["runnable"]),
            "backoff": sum(1 for row in due if row["backoff"]),
        },
        "targets": targets, "history": state.get("history", []),
    }


def prometheus(status):
    summary = status.get("summary") or {}
    history = status.get("history") or []
    last_attempt = epoch(history[0].get("completedAt")) if history else 0
    last_success = max((epoch(row.get("completedAt")) or 0 for row in history if row.get("ready")), default=0)
    return "\n".join([
        f"dash_canary_autopilot_enabled {1 if status.get('enabled') else 0}",
        f"dash_canary_autopilot_collector_up {1 if status.get('ok') else 0}",
        f"dash_canary_autopilot_worker_running {1 if status.get('running') else 0}",
        f"dash_canary_autopilot_targets {int(summary.get('targets') or 0)}",
        f"dash_canary_autopilot_current {int(summary.get('current') or 0)}",
        f"dash_canary_autopilot_due {int(summary.get('due') or 0)}",
        f"dash_canary_autopilot_backoff {int(summary.get('backoff') or 0)}",
        f"dash_canary_autopilot_attempts_total {int(status.get('attemptsTotal') or 0)}",
        f"dash_canary_autopilot_failures_total {int(status.get('failuresTotal') or 0)}",
        f"dash_canary_autopilot_last_attempt_timestamp_seconds {last_attempt or 0}",
        f"dash_canary_autopilot_last_success_timestamp_seconds {last_success or 0}",
    ]) + "\n"
