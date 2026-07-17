"""HMAC-bound, two-person approvals for high-impact admin mutations."""

from __future__ import annotations

import datetime as dt
import contextlib
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import sqlite3
import time


SCHEMA_VERSION = 1
REQUEST_ID = re.compile(r"^approval-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}$")
MAX_BODY_BYTES = 32 * 1024 * 1024
MAX_SUMMARY_BYTES = 1000
RISK_ORDER = {"standard": 1, "high": 2, "critical": 3}
MODE_MINIMUM = {"all": 1, "high": 2, "critical": 3}
TERMINAL_STATES = {"consumed", "rejected", "cancelled", "expired"}
SECRET_KEY = re.compile(r"(password|secret|token|credential|authorization|archive_base64|private.?key)", re.I)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def utc_iso(timestamp):
    return dt.datetime.fromtimestamp(float(timestamp), dt.timezone.utc).isoformat()


def _truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _dry_run(body, default=True):
    value = body.get("dry_run", body.get("dryRun", default))
    return _truthy(value) if not isinstance(value, bool) else value


def _action(body):
    return str(body.get("action") or "").strip().lower()


def _always(_body):
    return True


def _non_dry(body):
    return not _dry_run(body, default=True)


def _actions(*names):
    allowed = set(names)
    return lambda body: _action(body) in allowed


def _actions_non_dry(*names):
    allowed = set(names)
    return lambda body: _action(body) in allowed and not _dry_run(body, default=True)


POLICIES = {
    # Critical: destructive recovery, arbitrary persistence, identity, or broad state.
    "/api/ops/backups/restore": ("critical", "Restore a backup set", _non_dry),
    "/api/ops/database/row": ("critical", "Edit an arbitrary database row", _always),
    "/api/ops/database/password": ("critical", "Rotate the game database password", _always),
    "/api/ops/database/query": ("critical", "Execute write-capable database SQL", lambda body: bool(str(body.get("confirm") or "").strip())),
    "/api/ops/updates": ("critical", "Apply a game or stack update", _actions("game-apply", "stack-apply", "auto-update-install")),
    "/api/settings/env": ("critical", "Change environment configuration", _always),
    "/api/admin/base-retirement": ("critical", "Archive and retire a player base", _actions("archive")),
    "/api/admin/character-slots/execute": ("critical", "Swap or restore a character slot", _non_dry),
    "/api/admin/blueprints": ("critical", "Import or delete a Solido blueprint", _actions_non_dry("import", "delete")),
    "/api/admin/cosmetics": ("critical", "Change or roll back persistent cosmetic state", _always),
    "/api/presets/gameplay": ("critical", "Apply or roll back a gameplay preset", _actions("apply", "rollback")),
    # High: persistent player, world, economy, or lifecycle mutations.
    "/api/admin/player-maintenance": ("high", "Change or roll back player progression/recovery state", _non_dry),
    "/api/admin/player-runtime-action": ("high", "Execute a native player runtime action", _non_dry),
    "/api/admin/player-recovery/offline-teleport": ("high", "Move an offline player", _non_dry),
    "/api/admin/vehicle": ("high", "Change persistent vehicle state", _non_dry),
    "/api/admin/item": ("high", "Grant or modify an item", lambda body: not _dry_run(body, default=False)),
    "/api/admin/item/delete": ("high", "Delete an owned item", _always),
    "/api/admin/item/stack": ("high", "Change item stack or quality", _always),
    "/api/admin/currency": ("high", "Change player currency", _always),
    "/api/admin/solari/inventory": ("high", "Change inventory Solari", _non_dry),
    "/api/admin/solari/bank": ("high", "Change bank Solari", _non_dry),
    "/api/admin/xp": ("high", "Change specialization XP", _always),
    "/api/admin/bundle": ("high", "Execute an economy bundle", _non_dry),
    "/api/admin/landsraad": ("high", "Change Landsraad state", _non_dry),
    "/api/admin/faction-reputation": ("high", "Change faction reputation", _non_dry),
    "/api/admin/faction": ("high", "Change player faction", _non_dry),
    "/api/admin/journey": ("high", "Change journey state", _non_dry),
    "/api/admin/guild": ("high", "Change guild state", _non_dry),
    "/api/admin/marker": ("high", "Change world markers", _non_dry),
    "/api/admin/landclaim": ("high", "Change landclaim state", _non_dry),
    "/api/admin/permission": ("high", "Change actor permissions", _non_dry),
    "/api/admin/access-code": ("high", "Change a player access code", _non_dry),
    "/api/admin/respawn-location": ("high", "Change a player respawn location", _non_dry),
    "/api/moderation": ("high", "Change moderation enforcement state", _actions("ban", "unban", "allowlist-policy")),
    # Standard: operational mutations that are normally reversible or scheduled.
    "/api/ops/services/control": ("standard", "Control a service", _always),
    "/api/ops/memory": ("standard", "Change map memory policy", _always),
    "/api/ops/autoscaler": ("standard", "Change autoscaler policy", _always),
    "/api/ops/restart": ("standard", "Schedule an executable restart", lambda body: _truthy(body.get("execute", False))),
    "/api/ops/restore-drill": ("standard", "Queue an isolated PostgreSQL recovery rehearsal", _always),
    "/api/ops/rabbitmq-restore-drill": ("standard", "Queue an isolated RabbitMQ recovery rehearsal", _always),
    "/api/admin/gm/execute": ("standard", "Execute a generic GM command", _always),
}
GOVERNED_PATHS = frozenset(POLICIES)


def policy_for(path, body):
    path = str(path or "").split("?", 1)[0]
    if not isinstance(body, dict):
        raise ValueError("approval target body must be an object")
    row = POLICIES.get(path)
    if not row or not row[2](body):
        return None
    risk, label, _predicate = row
    return {"path": path, "risk": risk, "label": label}


def policy_enabled(mode, risk):
    mode = str(mode or "critical").strip().lower()
    if mode not in MODE_MINIMUM:
        raise ValueError("dual-control policy must be critical, high, or all")
    return RISK_ORDER[str(risk)] >= MODE_MINIMUM[mode]


def public_policies(mode="critical"):
    rows = []
    for path, (risk, label, _predicate) in sorted(POLICIES.items()):
        rows.append({"path": path, "risk": risk, "label": label, "enforced": policy_enabled(mode, risk)})
    return rows


def normalized_body(body):
    if not isinstance(body, dict):
        raise ValueError("approval request body must be an object")
    clean = {key: value for key, value in body.items() if key not in {"approvalId", "approval_id"}}
    encoded = canonical(clean).encode("utf-8")
    if len(encoded) > MAX_BODY_BYTES:
        raise ValueError("approval request body exceeds 32 MiB")
    return clean, encoded


def redacted_body(value, key=""):
    if SECRET_KEY.search(str(key)):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(child): redacted_body(item, child) for child, item in value.items()}
    if isinstance(value, list):
        return [redacted_body(item, key) for item in value[:200]] + (["[truncated]"] if len(value) > 200 else [])
    if isinstance(value, str):
        return value[:2000] + ("…" if len(value) > 2000 else "")
    return value


def _actor(principal):
    actor_id = str((principal or {}).get("id") or "").strip()
    if not actor_id or len(actor_id) > 128 or any(ord(char) < 32 for char in actor_id):
        raise PermissionError("dual control requires an authenticated named identity")
    return {
        "id": actor_id,
        "displayName": str((principal or {}).get("displayName") or actor_id).strip()[:160],
    }


class Store:
    def __init__(self, path, key_path=None, ttl_seconds=900, owner_uid=None, owner_gid=None, clock=None):
        self.path = pathlib.Path(path)
        self.key_path = pathlib.Path(key_path or self.path.with_suffix(".key"))
        self.ttl_seconds = max(60, min(int(ttl_seconds), 3600))
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None
        self.clock = clock or time.time

    def _secure(self, path, mode):
        os.chmod(path, mode)
        if os.geteuid() == 0 and self.owner_uid is not None and self.owner_gid is not None:
            os.chown(path, self.owner_uid, self.owner_gid)

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._secure(self.path.parent, 0o700)
        if not self.key_path.exists():
            descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(secrets.token_bytes(32))
                handle.flush()
                os.fsync(handle.fileno())
        self._secure(self.key_path, 0o600)
        with contextlib.closing(self._connect()) as connection:
            connection.executescript("""
                create table if not exists approval_requests (
                    id text primary key,
                    created_at real not null,
                    expires_at real not null,
                    requester_id text not null,
                    requester_name text not null,
                    target_path text not null,
                    required_capability text not null,
                    risk text not null,
                    summary text not null,
                    body_hmac_sha256 text not null,
                    review_json text not null,
                    request_hmac_sha256 text not null,
                    state text not null,
                    approver_id text,
                    approver_name text,
                    approved_at real,
                    consumed_by text,
                    consumed_at real,
                    decided_at real,
                    state_hmac_sha256 text not null
                );
                create index if not exists approval_requests_state_expiry
                    on approval_requests(state, expires_at);
                create table if not exists approval_events (
                    sequence integer primary key autoincrement,
                    request_id text not null,
                    occurred_at real not null,
                    actor_id text not null,
                    action text not null,
                    previous_state text,
                    state text not null,
                    details_json text not null,
                    previous_hmac_sha256 text not null,
                    event_hmac_sha256 text not null
                );
            """)
        self._secure(self.path, 0o600)
        return self.status()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma busy_timeout=10000")
        return connection

    def _key(self):
        value = self.key_path.read_bytes()
        if len(value) != 32:
            raise RuntimeError("change-approval HMAC key must contain exactly 32 bytes")
        return value

    def body_hmac(self, body):
        _clean, encoded = normalized_body(body)
        return hmac.new(self._key(), b"body\0" + encoded, hashlib.sha256).hexdigest()

    @staticmethod
    def _request_payload(row):
        return {
            "schemaVersion": SCHEMA_VERSION,
            "id": row["id"], "createdAt": float(row["created_at"]), "expiresAt": float(row["expires_at"]),
            "requesterId": row["requester_id"], "requesterName": row["requester_name"],
            "targetPath": row["target_path"], "requiredCapability": row["required_capability"],
            "risk": row["risk"], "summary": row["summary"], "bodyHmacSha256": row["body_hmac_sha256"],
            "reviewBody": json.loads(row["review_json"]),
        }

    def _request_hmac(self, row):
        return hmac.new(self._key(), b"request\0" + canonical(self._request_payload(row)).encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _value(row, key):
        if isinstance(row, dict):
            return row.get(key)
        return row[key]

    @classmethod
    def _state_payload(cls, row):
        return {
            "schemaVersion": SCHEMA_VERSION,
            "id": cls._value(row, "id"), "state": cls._value(row, "state"),
            "approverId": cls._value(row, "approver_id"), "approverName": cls._value(row, "approver_name"),
            "approvedAt": cls._value(row, "approved_at"), "consumedBy": cls._value(row, "consumed_by"),
            "consumedAt": cls._value(row, "consumed_at"), "decidedAt": cls._value(row, "decided_at"),
        }

    def _state_hmac(self, row):
        return hmac.new(self._key(), b"state\0" + canonical(self._state_payload(row)).encode("utf-8"), hashlib.sha256).hexdigest()

    def _verify_request_row(self, row):
        if not hmac.compare_digest(str(row["request_hmac_sha256"]), self._request_hmac(row)):
            raise RuntimeError(f"change approval {row['id']} immutable record HMAC does not match")
        if not hmac.compare_digest(str(row["state_hmac_sha256"]), self._state_hmac(row)):
            raise RuntimeError(f"change approval {row['id']} state HMAC does not match")
        return row

    def _append_event(self, connection, request_id, actor_id, action, previous_state, state, details=None, occurred_at=None):
        occurred_at = float(self.clock() if occurred_at is None else occurred_at)
        previous = connection.execute("select event_hmac_sha256 from approval_events order by sequence desc limit 1").fetchone()
        previous_hmac = str(previous[0]) if previous else "0" * 64
        details_json = canonical(details or {})
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "requestId": request_id,
            "occurredAt": occurred_at,
            "actorId": actor_id,
            "action": action,
            "previousState": previous_state,
            "state": state,
            "details": json.loads(details_json),
            "previousHmacSha256": previous_hmac,
        }
        digest = hmac.new(self._key(), b"event\0" + canonical(payload).encode("utf-8"), hashlib.sha256).hexdigest()
        connection.execute(
            "insert into approval_events(request_id,occurred_at,actor_id,action,previous_state,state,details_json,previous_hmac_sha256,event_hmac_sha256) values (?,?,?,?,?,?,?,?,?)",
            (request_id, occurred_at, actor_id, action, previous_state, state, details_json, previous_hmac, digest),
        )
        return digest

    def _expire(self, connection, now):
        rows = connection.execute(
            "select * from approval_requests where state in ('pending','approved') and expires_at<=? order by created_at,id",
            (float(now),),
        ).fetchall()
        for row in rows:
            self._verify_request_row(row)
            updated = dict(row)
            updated.update({"state": "expired", "decided_at": float(now)})
            connection.execute("update approval_requests set state='expired',decided_at=?,state_hmac_sha256=? where id=? and state=?", (float(now), self._state_hmac(updated), row["id"], row["state"]))
            self._append_event(connection, row["id"], "system", "expire", row["state"], "expired", occurred_at=now)
        return len(rows)

    def create(self, principal, target_path, request_body, required_capability, risk, summary="", ttl_seconds=None):
        actor = _actor(principal)
        policy = policy_for(target_path, request_body)
        if not policy:
            raise ValueError("target request is not a governed mutation")
        if policy["risk"] != risk:
            raise ValueError("approval risk does not match the governed target")
        summary = str(summary or policy["label"]).strip()
        if not summary or len(summary.encode("utf-8")) > MAX_SUMMARY_BYTES:
            raise ValueError("approval summary must be 1-1000 UTF-8 bytes")
        ttl = self.ttl_seconds if ttl_seconds in (None, "") else max(60, min(int(ttl_seconds), 3600))
        now = float(self.clock())
        request_id = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("approval-%Y%m%dT%H%M%SZ-") + secrets.token_hex(8)
        digest = self.body_hmac(request_body)
        clean_body, _encoded = normalized_body(request_body)
        review_json = canonical(redacted_body(clean_body))
        with contextlib.closing(self._connect()) as connection:
            connection.execute("begin immediate")
            self._expire(connection, now)
            immutable = {
                "id": request_id, "created_at": now, "expires_at": now + ttl,
                "requester_id": actor["id"], "requester_name": actor["displayName"],
                "target_path": policy["path"], "required_capability": str(required_capability),
                "risk": risk, "summary": summary, "body_hmac_sha256": digest, "review_json": review_json,
            }
            request_hmac = self._request_hmac(immutable)
            mutable = {
                "id": request_id, "state": "pending", "approver_id": None, "approver_name": None,
                "approved_at": None, "consumed_by": None, "consumed_at": None, "decided_at": None,
            }
            state_hmac = self._state_hmac(mutable)
            connection.execute(
                "insert into approval_requests(id,created_at,expires_at,requester_id,requester_name,target_path,required_capability,risk,summary,body_hmac_sha256,review_json,request_hmac_sha256,state,state_hmac_sha256) values (?,?,?,?,?,?,?,?,?,?,?,?, 'pending',?)",
                (request_id, now, now + ttl, actor["id"], actor["displayName"], policy["path"], str(required_capability), risk, summary, digest, review_json, request_hmac, state_hmac),
            )
            self._append_event(connection, request_id, actor["id"], "request", None, "pending", {"targetPath": policy["path"], "risk": risk, "bodyHmacSha256": digest}, now)
            connection.commit()
        return self.get(request_id)

    def _get_row(self, connection, request_id):
        request_id = str(request_id or "").strip()
        if not REQUEST_ID.fullmatch(request_id):
            raise ValueError("invalid change approval id")
        row = connection.execute("select * from approval_requests where id=?", (request_id,)).fetchone()
        if row is None:
            raise ValueError("change approval was not found")
        return self._verify_request_row(row)

    @staticmethod
    def _public(row):
        return {
            "id": row["id"], "createdAt": utc_iso(row["created_at"]), "expiresAt": utc_iso(row["expires_at"]),
            "requester": {"id": row["requester_id"], "displayName": row["requester_name"]},
            "targetPath": row["target_path"], "requiredCapability": row["required_capability"],
            "risk": row["risk"], "summary": row["summary"], "bodyHmacSha256": row["body_hmac_sha256"],
            "reviewBody": json.loads(row["review_json"]),
            "state": row["state"],
            "approver": ({"id": row["approver_id"], "displayName": row["approver_name"]} if row["approver_id"] else None),
            "approvedAt": utc_iso(row["approved_at"]) if row["approved_at"] else None,
            "consumedBy": row["consumed_by"],
            "consumedAt": utc_iso(row["consumed_at"]) if row["consumed_at"] else None,
        }

    def get(self, request_id):
        now = float(self.clock())
        with contextlib.closing(self._connect()) as connection:
            connection.execute("begin immediate")
            self._expire(connection, now)
            row = self._get_row(connection, request_id)
            connection.commit()
        return self._public(row)

    def list(self, limit=200):
        limit = max(1, min(int(limit), 500))
        now = float(self.clock())
        with contextlib.closing(self._connect()) as connection:
            connection.execute("begin immediate")
            self._expire(connection, now)
            rows = connection.execute("select * from approval_requests order by created_at desc,id desc limit ?", (limit,)).fetchall()
            connection.commit()
        return [self._public(self._verify_request_row(row)) for row in rows]

    def approve(self, request_id, principal):
        actor = _actor(principal)
        now = float(self.clock())
        with contextlib.closing(self._connect()) as connection:
            connection.execute("begin immediate")
            self._expire(connection, now)
            row = self._get_row(connection, request_id)
            if row["state"] != "pending":
                raise RuntimeError(f"change approval is {row['state']}, not pending")
            if row["requester_id"] == actor["id"]:
                raise PermissionError("requester cannot approve their own change")
            updated = dict(row)
            updated.update({"state": "approved", "approver_id": actor["id"], "approver_name": actor["displayName"], "approved_at": now, "decided_at": now})
            connection.execute(
                "update approval_requests set state='approved',approver_id=?,approver_name=?,approved_at=?,decided_at=?,state_hmac_sha256=? where id=? and state='pending'",
                (actor["id"], actor["displayName"], now, now, self._state_hmac(updated), row["id"]),
            )
            self._append_event(connection, row["id"], actor["id"], "approve", "pending", "approved", occurred_at=now)
            connection.commit()
        return self.get(request_id)

    def reject(self, request_id, principal, reason=""):
        actor = _actor(principal)
        reason = str(reason or "").strip()[:1000]
        now = float(self.clock())
        with contextlib.closing(self._connect()) as connection:
            connection.execute("begin immediate")
            self._expire(connection, now)
            row = self._get_row(connection, request_id)
            if row["state"] != "pending":
                raise RuntimeError(f"change approval is {row['state']}, not pending")
            if row["requester_id"] == actor["id"]:
                raise PermissionError("requester must cancel rather than reject their own change")
            updated = dict(row)
            updated.update({"state": "rejected", "decided_at": now})
            connection.execute("update approval_requests set state='rejected',decided_at=?,state_hmac_sha256=? where id=? and state='pending'", (now, self._state_hmac(updated), row["id"]))
            self._append_event(connection, row["id"], actor["id"], "reject", "pending", "rejected", {"reason": reason}, now)
            connection.commit()
        return self.get(request_id)

    def cancel(self, request_id, principal):
        actor = _actor(principal)
        now = float(self.clock())
        with contextlib.closing(self._connect()) as connection:
            connection.execute("begin immediate")
            self._expire(connection, now)
            row = self._get_row(connection, request_id)
            if row["requester_id"] != actor["id"]:
                raise PermissionError("only the requester can cancel a change approval")
            if row["state"] not in {"pending", "approved"}:
                raise RuntimeError(f"change approval is {row['state']} and cannot be cancelled")
            updated = dict(row)
            updated.update({"state": "cancelled", "decided_at": now})
            connection.execute("update approval_requests set state='cancelled',decided_at=?,state_hmac_sha256=? where id=? and state=?", (now, self._state_hmac(updated), row["id"], row["state"]))
            self._append_event(connection, row["id"], actor["id"], "cancel", row["state"], "cancelled", occurred_at=now)
            connection.commit()
        return self.get(request_id)

    def consume(self, request_id, principal, target_path, request_body, required_capability, risk):
        actor = _actor(principal)
        digest = self.body_hmac(request_body)
        now = float(self.clock())
        with contextlib.closing(self._connect()) as connection:
            connection.execute("begin immediate")
            self._expire(connection, now)
            row = self._get_row(connection, request_id)
            if row["state"] != "approved":
                raise PermissionError(f"change approval is {row['state']}, not approved")
            if row["requester_id"] != actor["id"]:
                raise PermissionError("only the original requester can consume this approval")
            checks = {
                "target path": row["target_path"] == str(target_path),
                "request body": hmac.compare_digest(row["body_hmac_sha256"], digest),
                "capability": row["required_capability"] == str(required_capability),
                "risk": row["risk"] == str(risk),
            }
            failed = [name for name, valid in checks.items() if not valid]
            if failed:
                raise PermissionError("change approval does not match execution " + ", ".join(failed))
            updated_state = dict(row)
            updated_state.update({"state": "consumed", "consumed_by": actor["id"], "consumed_at": now, "decided_at": now})
            updated = connection.execute(
                "update approval_requests set state='consumed',consumed_by=?,consumed_at=?,decided_at=?,state_hmac_sha256=? where id=? and state='approved'",
                (actor["id"], now, now, self._state_hmac(updated_state), row["id"]),
            )
            if updated.rowcount != 1:
                raise RuntimeError("change approval was consumed concurrently")
            self._append_event(connection, row["id"], actor["id"], "consume", "approved", "consumed", {"bodyHmacSha256": digest}, now)
            connection.commit()
        return self.get(request_id)

    def verify(self):
        previous = "0" * 64
        checked = 0
        with contextlib.closing(self._connect()) as connection:
            requests = connection.execute("select * from approval_requests order by created_at,id").fetchall()
            rows = connection.execute("select * from approval_events order by sequence").fetchall()
        for row in requests:
            try:
                self._verify_request_row(row)
            except RuntimeError:
                return {"ok": False, "checked": checked, "failedRequestId": row["id"]}
        key = self._key()
        for row in rows:
            payload = {
                "schemaVersion": SCHEMA_VERSION,
                "requestId": row["request_id"], "occurredAt": row["occurred_at"],
                "actorId": row["actor_id"], "action": row["action"],
                "previousState": row["previous_state"], "state": row["state"],
                "details": json.loads(row["details_json"]), "previousHmacSha256": previous,
            }
            expected = hmac.new(key, b"event\0" + canonical(payload).encode("utf-8"), hashlib.sha256).hexdigest()
            if row["previous_hmac_sha256"] != previous or not hmac.compare_digest(row["event_hmac_sha256"], expected):
                return {"ok": False, "checked": checked, "failedSequence": row["sequence"]}
            previous = row["event_hmac_sha256"]
            checked += 1
        return {"ok": True, "checked": checked, "requestsChecked": len(requests), "headHmacSha256": previous}

    def status(self):
        now = float(self.clock())
        with contextlib.closing(self._connect()) as connection:
            connection.execute("begin immediate")
            self._expire(connection, now)
            counts = {row["state"]: int(row["count"]) for row in connection.execute("select state,count(*) as count from approval_requests group by state")}
            oldest = connection.execute("select min(created_at) from approval_requests where state='pending'").fetchone()[0]
            connection.commit()
        return {
            "ok": True, "counts": counts,
            "oldestPendingAgeSeconds": max(0, int(now - oldest)) if oldest is not None else 0,
            "ledger": self.verify(),
        }

    def prometheus(self, enabled=True):
        status = self.status()
        counts = status["counts"]
        lines = [
            f"dash_change_approval_enabled {1 if enabled else 0}",
            f"dash_change_approval_ledger_valid {1 if status['ledger']['ok'] else 0}",
            f"dash_change_approval_pending {counts.get('pending', 0)}",
            f"dash_change_approval_approved {counts.get('approved', 0)}",
            f"dash_change_approval_consumed_total {counts.get('consumed', 0)}",
            f"dash_change_approval_rejected_total {counts.get('rejected', 0)}",
            f"dash_change_approval_cancelled_total {counts.get('cancelled', 0)}",
            f"dash_change_approval_expired_total {counts.get('expired', 0)}",
            f"dash_change_approval_oldest_pending_age_seconds {status['oldestPendingAgeSeconds']}",
        ]
        return "\n".join(lines) + "\n"
