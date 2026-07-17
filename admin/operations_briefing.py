#!/usr/bin/env python3
"""Signed, change-aware operator briefings compiled from existing DASH evidence."""

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


SCHEMA = "dune-operations-briefing/v1"
RECEIPT_SCHEMA = 1
ID_PATTERN = re.compile(r"^operations-briefing-[0-9a-f]{32}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_FIELDS = {"id", "title", "state", "healthy", "severity", "detail", "surface"}
ACTION_FIELDS = {"priority", "source", "title", "detail", "surface"}
CHANGE_FIELDS = {"source", "fromState", "toState", "direction"}
RECEIPT_FIELDS = {
    "schemaVersion", "id", "actor", "generatedAt", "sourceFingerprint",
    "previousReceiptId", "previousReceiptSha256", "state", "score", "summary",
    "sources", "actions", "changes", "receiptSha256",
}
SUMMARY_FIELDS = {"sources", "healthy", "attention", "critical", "informational", "actions", "changes"}
LOCK = threading.RLock()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def iso(value=None):
    value = time.time() if value is None else float(value)
    return datetime.datetime.fromtimestamp(value, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value):
    text = str(value or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("operations briefing timestamp lacks a timezone")
    return parsed.timestamp()


def bounded_text(value, maximum, label, *, allow_empty=False):
    value = str(value or "")
    if (not allow_empty and not value) or len(value) > maximum or any(ord(char) < 32 for char in value):
        raise ValueError(f"operations briefing {label} is invalid")
    return value


def normalize_sources(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError("operations briefing sources are invalid")
    normalized = []
    seen = set()
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != SOURCE_FIELDS:
            raise ValueError("operations briefing source fields are invalid")
        source_id = bounded_text(raw["id"], 80, "source id")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", source_id) or source_id in seen:
            raise ValueError("operations briefing source identity is invalid")
        seen.add(source_id)
        severity = str(raw["severity"])
        if severity not in ("critical", "warning", "informational"):
            raise ValueError("operations briefing source severity is invalid")
        if type(raw["healthy"]) is not bool:
            raise ValueError("operations briefing source verdict is invalid")
        normalized.append({
            "id": source_id,
            "title": bounded_text(raw["title"], 160, "source title"),
            "state": bounded_text(raw["state"], 100, "source state"),
            "healthy": raw["healthy"], "severity": severity,
            "detail": bounded_text(raw["detail"], 500, "source detail", allow_empty=True),
            "surface": bounded_text(raw["surface"], 160, "source surface"),
        })
    return sorted(normalized, key=lambda row: row["id"])


def source_fingerprint(sources):
    stable = [{key: row[key] for key in ("id", "state", "healthy", "severity")} for row in normalize_sources(sources)]
    return hashlib.sha256(canonical(stable).encode()).hexdigest()


def generation_policy(latest, current_source_fingerprint, current_ready, *, now=None,
                      refresh_seconds=24 * 3600, minimum_interval_seconds=300,
                      change_minimum_interval_seconds=15, force=False):
    """Choose whether to record now without hiding a changed source for a full poll cycle."""
    now = time.time() if now is None else float(now)
    latest = latest or {}
    generated_at = latest.get("generatedAt")
    latest_age = max(0.0, now - epoch(generated_at)) if generated_at else None
    previous_fingerprint = str(latest.get("sourceFingerprint") or "")
    current_fingerprint = str(current_source_fingerprint or "")
    source_changed = bool(
        latest and previous_fingerprint and current_fingerprint
        and not hmac.compare_digest(previous_fingerprint, current_fingerprint)
    )
    due = bool(not latest or not current_ready or latest_age is None or latest_age >= float(refresh_seconds))
    minimum = float(change_minimum_interval_seconds if source_changed else minimum_interval_seconds)
    cooldown = bool(latest_age is not None and latest_age < minimum)
    generate = bool(force or (due and not cooldown))
    retry_after = max(1, int(math.ceil(minimum - latest_age))) if due and cooldown and latest_age is not None else 0
    return {
        "due": due, "generated": generate, "cooldown": cooldown,
        "sourceChanged": source_changed, "latestAgeSeconds": latest_age,
        "minimumIntervalSeconds": int(minimum), "retryAfterSeconds": retry_after,
    }


def _direction(previous, current):
    if previous["healthy"] != current["healthy"]:
        return "improvement" if current["healthy"] else "regression"
    order = {"critical": 0, "warning": 1, "informational": 2}
    if order[current["severity"]] > order[previous["severity"]]:
        return "improvement"
    if order[current["severity"]] < order[previous["severity"]]:
        return "regression"
    return "changed"


def source_changes(sources, previous=None):
    sources = normalize_sources(sources)
    previous_sources = {row["id"]: row for row in ((previous or {}).get("sources") or []) if isinstance(row, dict) and row.get("id")}
    changes = []
    for row in sources:
        before = previous_sources.get(row["id"])
        if before and (before.get("state") != row["state"] or before.get("healthy") != row["healthy"] or before.get("severity") != row["severity"]):
            changes.append({
                "source": row["id"], "fromState": str(before.get("state") or "unknown")[:100],
                "toState": row["state"], "direction": _direction(before, row),
            })
    return changes


def compile_receipt(sources, *, actor="system:operations-briefing", previous=None, now=None):
    now = time.time() if now is None else float(now)
    sources = normalize_sources(sources)
    failures = [row for row in sources if not row["healthy"]]
    critical = [row for row in failures if row["severity"] == "critical"]
    warnings = [row for row in failures if row["severity"] == "warning"]
    informational = [row for row in failures if row["severity"] == "informational"]
    state = "critical" if critical else "attention" if warnings else "ready"
    score = max(0, 100 - 20 * len(critical) - 7 * len(warnings))
    actions = [{
        "priority": row["severity"], "source": row["id"], "title": row["title"],
        "detail": row["detail"], "surface": row["surface"],
    } for row in sorted(failures, key=lambda row: ({"critical": 0, "warning": 1, "informational": 2}[row["severity"]], row["id"]))]
    changes = source_changes(sources, previous)
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA, "id": "operations-briefing-" + secrets.token_hex(16),
        "actor": bounded_text(actor, 128, "actor"), "generatedAt": iso(now),
        "sourceFingerprint": source_fingerprint(sources), "state": state, "score": score,
        "previousReceiptId": (previous or {}).get("id"),
        "previousReceiptSha256": (previous or {}).get("receiptSha256"),
        "summary": {
            "sources": len(sources), "healthy": len(sources) - len(failures),
            "attention": len(warnings), "critical": len(critical),
            "informational": len(informational), "actions": len(actions), "changes": len(changes),
        },
        "sources": sources, "actions": actions, "changes": changes,
    }
    receipt["receiptSha256"] = hashlib.sha256(canonical(receipt).encode()).hexdigest()
    return receipt


def signed_document(receipt, secret):
    payload = {
        "schemaVersion": SCHEMA, "generatedAt": receipt["generatedAt"],
        "signingKeyFingerprint": hashlib.sha256(secret).hexdigest(), "receipt": receipt,
    }
    return {**payload, "signature": hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()}


def verify_signed_document(document, secret, *, current_source_fingerprint=None, max_age_seconds=None, now=None):
    try:
        if not isinstance(document, dict) or set(document) != {"schemaVersion", "generatedAt", "signingKeyFingerprint", "receipt", "signature"}:
            raise ValueError("operations briefing signed document fields are invalid")
        if document["schemaVersion"] != SCHEMA:
            raise ValueError("operations briefing schema is invalid")
        payload = {key: value for key, value in document.items() if key != "signature"}
        expected = hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(document.get("signature") or ""), expected):
            raise ValueError("operations briefing signature is invalid")
        if not hmac.compare_digest(str(document.get("signingKeyFingerprint") or ""), hashlib.sha256(secret).hexdigest()):
            raise ValueError("operations briefing signing key fingerprint differs")
        receipt = document.get("receipt")
        if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS or receipt.get("schemaVersion") != RECEIPT_SCHEMA:
            raise ValueError("operations briefing receipt fields are invalid")
        if not ID_PATTERN.fullmatch(str(receipt.get("id") or "")):
            raise ValueError("operations briefing receipt id is invalid")
        bounded_text(receipt["actor"], 128, "actor")
        generated = epoch(receipt["generatedAt"])
        if abs(generated - epoch(document["generatedAt"])) > 0.001:
            raise ValueError("operations briefing signed time differs")
        fingerprint = str(receipt.get("sourceFingerprint") or "")
        if not HASH_PATTERN.fullmatch(fingerprint):
            raise ValueError("operations briefing source fingerprint is invalid")
        sources = normalize_sources(receipt["sources"])
        previous_id = receipt.get("previousReceiptId")
        previous_hash = receipt.get("previousReceiptSha256")
        if (previous_id is None) != (previous_hash is None):
            raise ValueError("operations briefing previous receipt link is incomplete")
        if previous_id is not None and (not ID_PATTERN.fullmatch(str(previous_id)) or not HASH_PATTERN.fullmatch(str(previous_hash))):
            raise ValueError("operations briefing previous receipt link is invalid")
        if not hmac.compare_digest(fingerprint, source_fingerprint(sources)):
            raise ValueError("operations briefing source fingerprint differs")
        failures = [row for row in sources if not row["healthy"]]
        expected_critical = sum(row["severity"] == "critical" for row in failures)
        expected_warning = sum(row["severity"] == "warning" for row in failures)
        expected_info = sum(row["severity"] == "informational" for row in failures)
        expected_state = "critical" if expected_critical else "attention" if expected_warning else "ready"
        expected_score = max(0, 100 - 20 * expected_critical - 7 * expected_warning)
        if receipt.get("state") != expected_state or receipt.get("score") != expected_score:
            raise ValueError("operations briefing state or score is inconsistent")
        summary = receipt.get("summary")
        if not isinstance(summary, dict) or set(summary) != SUMMARY_FIELDS or any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000 for value in summary.values()):
            raise ValueError("operations briefing summary is invalid")
        expected_summary = {
            "sources": len(sources), "healthy": len(sources) - len(failures), "attention": expected_warning,
            "critical": expected_critical, "informational": expected_info,
            "actions": len(receipt.get("actions") or []), "changes": len(receipt.get("changes") or []),
        }
        if summary != expected_summary:
            raise ValueError("operations briefing summary is inconsistent")
        actions = receipt.get("actions")
        if not isinstance(actions, list) or len(actions) != len(failures):
            raise ValueError("operations briefing actions are invalid")
        expected_actions = {(row["id"], row["severity"], row["title"], row["detail"], row["surface"]) for row in failures}
        actual_actions = set()
        for action in actions:
            if not isinstance(action, dict) or set(action) != ACTION_FIELDS or action.get("priority") not in ("critical", "warning", "informational"):
                raise ValueError("operations briefing action fields are invalid")
            actual_actions.add((
                bounded_text(action["source"], 80, "action source"), action["priority"],
                bounded_text(action["title"], 160, "action title"),
                bounded_text(action["detail"], 500, "action detail", allow_empty=True),
                bounded_text(action["surface"], 160, "action surface"),
            ))
        if actual_actions != expected_actions:
            raise ValueError("operations briefing actions do not match sources")
        changes = receipt.get("changes")
        if not isinstance(changes, list) or len(changes) > len(sources):
            raise ValueError("operations briefing changes are invalid")
        seen_changes = set()
        source_by_id = {row["id"]: row for row in sources}
        for change in changes:
            if not isinstance(change, dict) or set(change) != CHANGE_FIELDS or change.get("direction") not in ("improvement", "regression", "changed"):
                raise ValueError("operations briefing change fields are invalid")
            change_source = bounded_text(change["source"], 80, "change source")
            if change_source in seen_changes or change_source not in source_by_id:
                raise ValueError("operations briefing change source is invalid")
            seen_changes.add(change_source)
            bounded_text(change["fromState"], 100, "previous state")
            to_state = bounded_text(change["toState"], 100, "current state")
            if to_state != source_by_id[change_source]["state"]:
                raise ValueError("operations briefing change current state is inconsistent")
        actual_hash = str(receipt.get("receiptSha256") or "")
        unsigned = {key: value for key, value in receipt.items() if key != "receiptSha256"}
        expected_hash = hashlib.sha256(canonical(unsigned).encode()).hexdigest()
        if not HASH_PATTERN.fullmatch(actual_hash) or not hmac.compare_digest(actual_hash, expected_hash):
            raise ValueError("operations briefing receipt digest is invalid")
        reference = time.time() if now is None else float(now)
        if generated > reference + 300:
            raise ValueError("operations briefing timestamp is implausibly in the future")
        age = max(0.0, reference - generated)
        age_current = max_age_seconds is None or age <= float(max_age_seconds)
        inputs_current = current_source_fingerprint is None or hmac.compare_digest(fingerprint, str(current_source_fingerprint))
        return {
            "ok": True, "signatureValid": True, "receiptValid": True,
            "receiptId": receipt["id"], "receiptSha256": actual_hash,
            "ageSeconds": round(age, 3), "ageCurrent": age_current,
            "sourcesCurrent": inputs_current, "currentReady": bool(age_current and inputs_current),
        }
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"ok": False, "signatureValid": False, "receiptValid": False, "currentReady": False, "error": str(exc)}


class Store:
    def __init__(self, evidence_root, secret, *, retention=100, max_age_seconds=36 * 3600, owner_uid=None, owner_gid=None):
        self.evidence_root = pathlib.Path(evidence_root)
        self.secret = bytes(secret)
        self.retention = max(10, min(int(retention), 5000))
        self.max_age_seconds = max(300, min(int(max_age_seconds), 30 * 86400))
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None

    def _secure(self, path):
        os.chmod(path, 0o700 if pathlib.Path(path).is_dir() else 0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(path, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)

    def initialize(self):
        if self.evidence_root.is_symlink():
            raise ValueError("operations briefing evidence root cannot be a symlink")
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        if self.evidence_root.is_symlink() or not self.evidence_root.is_dir():
            raise ValueError("operations briefing evidence root is invalid")
        self._secure(self.evidence_root)

    def paths(self):
        self.initialize()
        return sorted(
            (path for path in self.evidence_root.glob("operations-briefing-*.signed.json") if path.is_file() and not path.is_symlink()),
            key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True,
        )

    def _write(self, path, document):
        temporary = path.with_suffix(path.suffix + ".tmp-" + secrets.token_hex(8))
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(document, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            self._secure(temporary); temporary.replace(path); self._secure(path)
        finally:
            temporary.unlink(missing_ok=True)

    def latest_receipt(self):
        rows = self.paths()
        if not rows:
            return None
        try:
            document = json.loads(rows[0].read_text(encoding="utf-8"))
            verification = verify_signed_document(document, self.secret)
            return document.get("receipt") if verification.get("ok") else None
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def record(self, sources, *, actor, now=None):
        now = time.time() if now is None else float(now)
        with LOCK:
            previous = self.latest_receipt()
            receipt = compile_receipt(sources, actor=actor, previous=previous, now=now)
            document = signed_document(receipt, self.secret)
            path = self.evidence_root / f"{receipt['id']}.signed.json"
            self._write(path, document)
            for stale in self.paths()[self.retention:]:
                stale.unlink(missing_ok=True)
        return {"document": document, "evidencePath": str(path), "verification": verify_signed_document(document, self.secret)}

    def status(self, current_source_fingerprint=None, *, limit=20, now=None):
        all_rows = []
        for path in self.paths():
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                verification = verify_signed_document(
                    document, self.secret, current_source_fingerprint=current_source_fingerprint,
                    max_age_seconds=self.max_age_seconds, now=now,
                )
                receipt = document.get("receipt") or {}
                row = {**receipt, "file": path.name, "verification": verification}
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                row = {"id": path.stem, "state": "invalid", "score": 0, "file": path.name, "verification": {"ok": False, "currentReady": False, "error": str(exc)}}
            all_rows.append(row)
        for index in range(max(0, len(all_rows) - 1)):
            current = all_rows[index]
            previous = all_rows[index + 1]
            verification = current.get("verification") or {}
            if not verification.get("ok") or not (previous.get("verification") or {}).get("ok"):
                continue
            link_valid = bool(
                current.get("previousReceiptId") == previous.get("id")
                and current.get("previousReceiptSha256") == previous.get("receiptSha256")
            )
            changes_valid = current.get("changes") == source_changes(current.get("sources") or [], previous)
            verification["historyLinkValid"] = link_valid
            verification["changesValid"] = changes_valid
            if not link_valid or not changes_valid:
                verification.update({
                    "ok": False, "receiptValid": False, "currentReady": False,
                    "error": "operations briefing retained receipt chain or delta semantics are invalid",
                })
        latest = all_rows[0] if all_rows else None
        rows = all_rows[:max(1, min(int(limit), self.retention))]
        return {
            "ok": all((row.get("verification") or {}).get("ok") for row in all_rows),
            "currentReady": bool(latest and (latest.get("verification") or {}).get("currentReady")),
            "latest": latest, "briefings": rows, "retention": self.retention,
            "maxAgeSeconds": self.max_age_seconds,
            "summary": {"retained": len(all_rows), "returned": len(rows)},
        }


def prometheus(status, *, enabled=True, worker_running=False, last_error=False, runtime=None):
    runtime = runtime or {}
    latest = status.get("latest") or {}
    summary = latest.get("summary") or {}
    verification = latest.get("verification") or {}
    generated = epoch(latest["generatedAt"]) if latest.get("generatedAt") and verification.get("ok") else 0
    return "\n".join([
        f"dash_operations_briefing_enabled {1 if enabled else 0}",
        f"dash_operations_briefing_collector_up {1 if status.get('ok') and not last_error else 0}",
        f"dash_operations_briefing_worker_running {1 if worker_running else 0}",
        f"dash_operations_briefing_current {1 if status.get('currentReady') else 0}",
        f"dash_operations_briefing_score {int(latest.get('score') or 0)}",
        f"dash_operations_briefing_critical {int(summary.get('critical') or 0)}",
        f"dash_operations_briefing_attention {int(summary.get('attention') or 0)}",
        f"dash_operations_briefing_actions {int(summary.get('actions') or 0)}",
        f"dash_operations_briefing_last_generation_timestamp_seconds {generated}",
        f"dash_operations_briefing_age_seconds {float(verification.get('ageSeconds') or 0):.3f}",
        f"dash_operations_briefing_retained {int((status.get('summary') or {}).get('retained') or 0)}",
        f"dash_operations_briefing_refresh_pending {1 if runtime.get('refreshPending') else 0}",
        f"dash_operations_briefing_invalidations_total {int(runtime.get('invalidations') or 0)}",
        f"dash_operations_briefing_wakeups_total {int(runtime.get('wakeups') or 0)}",
        f"dash_operations_briefing_event_generations_total {int(runtime.get('eventGenerations') or 0)}",
    ]) + "\n"
