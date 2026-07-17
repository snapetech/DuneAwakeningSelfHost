#!/usr/bin/env python3
"""Durable, bounded Prometheus alert inbox for DASH operators."""

from __future__ import annotations

import datetime
import contextlib
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import threading
import time


SCHEMA = "dash-alert-inbox/v1"
ACTIVE_STATES = {"pending", "firing"}
BRIEFING_FEEDBACK_GLOB = "DashOperationsBriefing*"
SENSITIVE_KEY = re.compile(r"password|passwd|secret|token|credential|private.?key|authorization|cookie", re.I)
MAX_LABELS = 64
MAX_ANNOTATIONS = 32
MAX_KEY = 128
MAX_VALUE = 1000


def iso(epoch=None):
    return datetime.datetime.fromtimestamp(float(epoch if epoch is not None else time.time()), datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def bounded_mapping(value, maximum):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in sorted(value.items(), key=lambda row: str(row[0]))[:maximum]:
        key = str(key)[:MAX_KEY]
        result[key] = "[redacted]" if SENSITIVE_KEY.search(key) else str(item)[:MAX_VALUE]
    return result


def fingerprint(labels):
    canonical = json.dumps(labels, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_alert(raw):
    if not isinstance(raw, dict):
        raise ValueError("Prometheus alert row must be an object")
    raw_labels = raw.get("labels")
    if not isinstance(raw_labels, dict) or not raw_labels:
        raise ValueError("Prometheus alert row has no labels")
    if len(raw_labels) > MAX_LABELS:
        raise ValueError(f"Prometheus alert row exceeds {MAX_LABELS} labels")
    if any(len(str(key)) > MAX_KEY or len(str(value)) > MAX_VALUE for key, value in raw_labels.items()):
        raise ValueError("Prometheus alert label exceeds the identity length bound")
    labels = bounded_mapping(raw_labels, MAX_LABELS)
    if len(labels) != len(raw_labels):
        raise ValueError("Prometheus alert labels collide after normalization")
    annotations = bounded_mapping(raw.get("annotations"), MAX_ANNOTATIONS)
    state = str(raw.get("state") or "").strip().lower()
    if state not in ACTIVE_STATES:
        raise ValueError(f"unsupported Prometheus alert state: {state or 'missing'}")
    active_at = parse_iso(raw.get("activeAt"))
    if raw.get("activeAt") and active_at is None:
        raise ValueError("Prometheus alert activeAt is invalid")
    name = labels.get("alertname") or "unnamed-alert"
    severity = labels.get("severity", "unknown").lower()
    return {
        "fingerprint": fingerprint(labels),
        "name": name[:200],
        "severity": severity[:64],
        "state": state,
        "labels": labels,
        "annotations": annotations,
        "summary": str(annotations.get("summary") or annotations.get("description") or name)[:1000],
        "description": str(annotations.get("description") or "")[:4000],
        "activeAt": active_at,
        "activeAtIso": iso(active_at) if active_at is not None else None,
    }


class Store:
    def __init__(self, database, *, retention_days=90, history_limit=2000, owner_uid=None, owner_gid=None):
        self.database = pathlib.Path(database)
        self.retention_days = max(1, min(int(retention_days), 3650))
        self.history_limit = max(100, min(int(history_limit), 10000))
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None
        self._lock = threading.RLock()

    def _secure(self):
        if self.database.is_symlink():
            raise ValueError("alert inbox database must not be a symlink")
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database.parent.chmod(0o700)
        private_files = (self.database, pathlib.Path(str(self.database) + "-wal"), pathlib.Path(str(self.database) + "-shm"))
        for path in private_files:
            if path.is_symlink():
                raise ValueError("alert inbox database artifacts must not be symlinks")
            if path.exists():
                path.chmod(0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(self.database.parent, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)
            for path in private_files:
                if path.exists():
                    os.chown(path, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)

    def connect(self):
        self._secure()
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma journal_mode=WAL")
        connection.execute("pragma foreign_keys=ON")
        self._secure()
        return connection

    @contextlib.contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
            self._secure()

    def initialize(self):
        with self._lock, self.transaction() as db:
            db.executescript("""
                create table if not exists alerts (
                    fingerprint text primary key,
                    name text not null,
                    severity text not null,
                    state text not null,
                    labels_json text not null,
                    annotations_json text not null,
                    summary text not null,
                    description text not null,
                    active_at real,
                    first_seen real not null,
                    last_seen real not null,
                    resolved_at real,
                    generation integer not null default 1,
                    occurrences integer not null default 1,
                    acknowledged_at real,
                    acknowledged_by text,
                    acknowledgement_note text
                );
                create table if not exists transitions (
                    id integer primary key autoincrement,
                    fingerprint text not null,
                    generation integer not null,
                    transition text not null,
                    state text not null,
                    occurred_at real not null,
                    name text not null,
                    severity text not null,
                    summary text not null,
                    actor text,
                    note text
                );
                create index if not exists transitions_recent on transitions(occurred_at desc, id desc);
                create table if not exists metadata (key text primary key, value text not null);
            """)
        return self

    @staticmethod
    def _metadata(db):
        return {row["key"]: row["value"] for row in db.execute("select key,value from metadata")}

    @staticmethod
    def _set_metadata(db, **values):
        for key, value in values.items():
            db.execute(
                "insert into metadata(key,value) values(?,?) on conflict(key) do update set value=excluded.value",
                (key, str(value)),
            )

    @staticmethod
    def _transition(db, alert, transition, occurred_at, *, actor=None, note=None):
        cursor = db.execute(
            "insert into transitions(fingerprint,generation,transition,state,occurred_at,name,severity,summary,actor,note) values(?,?,?,?,?,?,?,?,?,?)",
            (
                alert["fingerprint"], int(alert["generation"]), transition, alert["state"], occurred_at,
                alert["name"], alert["severity"], alert["summary"], actor, note,
            ),
        )
        return {
            "id": int(cursor.lastrowid),
            "fingerprint": alert["fingerprint"], "generation": int(alert["generation"]),
            "transition": transition, "state": alert["state"], "occurredAt": iso(occurred_at),
            "name": alert["name"], "severity": alert["severity"], "summary": alert["summary"],
            "actor": actor, "note": note,
        }

    def record_poll_error(self, error, *, now=None):
        now = float(now if now is not None else time.time())
        with self._lock, self.transaction() as db:
            metadata = self._metadata(db)
            failures = int(metadata.get("consecutiveFailures", "0") or 0) + 1
            self._set_metadata(
                db, lastPollAt=now, lastError=str(error)[:1000], lastErrorAt=now,
                consecutiveFailures=failures,
            )

    def sync(self, response, *, now=None):
        now = float(now if now is not None else time.time())
        if not isinstance(response, dict) or response.get("status") != "success":
            raise ValueError("Prometheus alerts response is not successful")
        data = response.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("alerts"), list):
            raise ValueError("Prometheus alerts response is missing data.alerts")
        if len(data["alerts"]) > 5000:
            raise ValueError("Prometheus alerts response exceeds 5000 rows")
        normalized = [normalize_alert(row) for row in data["alerts"]]
        incoming = {row["fingerprint"]: row for row in normalized}
        if len(incoming) != len(normalized):
            raise ValueError("Prometheus alerts response contains duplicate bounded label identities")
        transitions = []
        with self._lock, self.transaction() as db:
            existing = {row["fingerprint"]: dict(row) for row in db.execute("select * from alerts")}
            for fp, alert in incoming.items():
                prior = existing.get(fp)
                labels_json = json.dumps(alert["labels"], sort_keys=True, separators=(",", ":"))
                annotations_json = json.dumps(alert["annotations"], sort_keys=True, separators=(",", ":"))
                if prior is None:
                    generation, occurrences = 1, 1
                    acknowledged_at = acknowledged_by = acknowledgement_note = None
                    first_seen = now
                    transition = alert["state"]
                elif prior["state"] == "resolved":
                    generation, occurrences = int(prior["generation"]) + 1, int(prior["occurrences"]) + 1
                    acknowledged_at = acknowledged_by = acknowledgement_note = None
                    first_seen = now
                    transition = "refiring"
                else:
                    generation, occurrences = int(prior["generation"]), int(prior["occurrences"])
                    acknowledged_at = prior["acknowledged_at"]
                    acknowledged_by = prior["acknowledged_by"]
                    acknowledgement_note = prior["acknowledgement_note"]
                    first_seen = float(prior["first_seen"])
                    transition = alert["state"] if prior["state"] != alert["state"] else None
                db.execute("""
                    insert into alerts(fingerprint,name,severity,state,labels_json,annotations_json,summary,description,active_at,first_seen,last_seen,resolved_at,generation,occurrences,acknowledged_at,acknowledged_by,acknowledgement_note)
                    values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    on conflict(fingerprint) do update set
                      name=excluded.name,severity=excluded.severity,state=excluded.state,labels_json=excluded.labels_json,
                      annotations_json=excluded.annotations_json,summary=excluded.summary,description=excluded.description,
                      active_at=excluded.active_at,first_seen=excluded.first_seen,last_seen=excluded.last_seen,resolved_at=null,
                      generation=excluded.generation,occurrences=excluded.occurrences,acknowledged_at=excluded.acknowledged_at,
                      acknowledged_by=excluded.acknowledged_by,acknowledgement_note=excluded.acknowledgement_note
                """, (
                    fp, alert["name"], alert["severity"], alert["state"], labels_json, annotations_json,
                    alert["summary"], alert["description"], alert["activeAt"], first_seen, now, None,
                    generation, occurrences, acknowledged_at, acknowledged_by, acknowledgement_note,
                ))
                if transition:
                    transitions.append(self._transition(db, dict(alert, generation=generation), transition, now))
            for fp, prior in existing.items():
                if fp in incoming or prior["state"] == "resolved":
                    continue
                db.execute("update alerts set state='resolved',resolved_at=?,last_seen=? where fingerprint=?", (now, now, fp))
                resolved = {
                    "fingerprint": fp, "generation": prior["generation"], "state": "resolved",
                    "name": prior["name"], "severity": prior["severity"], "summary": prior["summary"],
                }
                transitions.append(self._transition(db, resolved, "resolved", now))
            self._set_metadata(
                db, lastPollAt=now, lastSuccessAt=now, lastError="", consecutiveFailures=0,
                pollsTotal=int(self._metadata(db).get("pollsTotal", "0") or 0) + 1,
                transitionsTotal=int(self._metadata(db).get("transitionsTotal", "0") or 0) + len(transitions),
            )
            cutoff = now - self.retention_days * 86400
            db.execute("delete from transitions where occurred_at < ?", (cutoff,))
            db.execute("delete from alerts where state='resolved' and resolved_at < ?", (cutoff,))
            db.execute("delete from transitions where id not in (select id from transitions order by id desc limit ?)", (self.history_limit,))
        return {"ok": True, "schemaVersion": SCHEMA, "transitions": transitions, "observed": len(incoming)}

    def acknowledge(self, fp, actor, note="", *, now=None):
        now = float(now if now is not None else time.time())
        fp = str(fp or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", fp):
            raise ValueError("alert fingerprint must be 64 lowercase hex characters")
        actor = str(actor or "unknown")[:128]
        note = str(note or "")[:1000]
        with self._lock, self.transaction() as db:
            row = db.execute("select * from alerts where fingerprint=?", (fp,)).fetchone()
            if row is None:
                raise KeyError("alert fingerprint was not found")
            alert = dict(row)
            if alert["state"] not in ACTIVE_STATES:
                raise ValueError("resolved alerts cannot be acknowledged")
            if alert["acknowledged_at"] is not None:
                return {"ok": True, "idempotent": True, "alert": self._public_alert(alert)}
            db.execute(
                "update alerts set acknowledged_at=?,acknowledged_by=?,acknowledgement_note=? where fingerprint=?",
                (now, actor, note, fp),
            )
            alert.update(acknowledged_at=now, acknowledged_by=actor, acknowledgement_note=note)
            transition = self._transition(db, alert, "acknowledged", now, actor=actor, note=note)
            metadata = self._metadata(db)
            self._set_metadata(db, transitionsTotal=int(metadata.get("transitionsTotal", "0") or 0) + 1)
        return {"ok": True, "idempotent": False, "alert": self._public_alert(alert), "transition": transition}

    @staticmethod
    def _public_alert(row):
        row = dict(row)
        return {
            "fingerprint": row["fingerprint"], "name": row["name"], "severity": row["severity"],
            "state": row["state"], "summary": row["summary"], "description": row["description"],
            "labels": json.loads(row["labels_json"]), "annotations": json.loads(row["annotations_json"]),
            "activeAt": iso(row["active_at"]) if row["active_at"] is not None else None,
            "firstSeenAt": iso(row["first_seen"]), "lastSeenAt": iso(row["last_seen"]),
            "resolvedAt": iso(row["resolved_at"]) if row["resolved_at"] is not None else None,
            "generation": int(row["generation"]), "occurrences": int(row["occurrences"]),
            "acknowledged": row["acknowledged_at"] is not None,
            "acknowledgedAt": iso(row["acknowledged_at"]) if row["acknowledged_at"] is not None else None,
            "acknowledgedBy": row["acknowledged_by"], "acknowledgementNote": row["acknowledgement_note"],
        }

    def status(self, *, limit=200, now=None):
        now = float(now if now is not None else time.time())
        limit = max(1, min(int(limit), 1000))
        with self._lock, self.transaction() as db:
            metadata = self._metadata(db)
            counts = dict(db.execute("""
                select
                  count(*) filter(where state!='resolved') as active,
                  count(*) filter(where state='firing') as firing,
                  count(*) filter(where state='pending') as pending,
                  count(*) filter(where state!='resolved' and acknowledged_at is null) as unacknowledged,
                  count(*) filter(where state!='resolved' and severity='critical') as critical,
                  count(*) filter(where state!='resolved' and severity='warning') as warning
                from alerts
            """).fetchone())
            briefing_counts = dict(db.execute("""
                select
                  count(*) filter(where state!='resolved' and name not glob ?) as active,
                  count(*) filter(where state!='resolved' and acknowledged_at is null and name not glob ?) as unacknowledged,
                  count(*) filter(where state!='resolved' and severity='critical' and name not glob ?) as critical,
                  count(*) filter(where state!='resolved' and severity='warning' and name not glob ?) as warning,
                  count(*) filter(where state!='resolved' and name glob ?) as feedback_excluded
                from alerts
            """, (BRIEFING_FEEDBACK_GLOB,) * 5).fetchone())
            history_count = int(db.execute("select count(*) from transitions").fetchone()[0])
            active = [self._public_alert(row) for row in db.execute(
                "select * from alerts where state!='resolved' order by case severity when 'critical' then 0 when 'warning' then 1 else 2 end, first_seen asc limit ?",
                (limit,),
            )]
            history = [dict(row) for row in db.execute(
                "select id,fingerprint,generation,transition,state,occurred_at,name,severity,summary,actor,note from transitions order by id desc limit ?",
                (limit,),
            )]
        for row in history:
            row["occurredAt"] = iso(row.pop("occurred_at"))
        last_success = float(metadata.get("lastSuccessAt", "0") or 0)
        last_poll = float(metadata.get("lastPollAt", "0") or 0)
        summary = {
            "active": int(counts["active"] or 0), "firing": int(counts["firing"] or 0),
            "pending": int(counts["pending"] or 0), "unacknowledged": int(counts["unacknowledged"] or 0),
            "critical": int(counts["critical"] or 0), "warning": int(counts["warning"] or 0),
            "history": history_count,
        }
        briefing_summary = {
            "active": int(briefing_counts["active"] or 0),
            "unacknowledged": int(briefing_counts["unacknowledged"] or 0),
            "critical": int(briefing_counts["critical"] or 0),
            "warning": int(briefing_counts["warning"] or 0),
            "feedbackExcluded": int(briefing_counts["feedback_excluded"] or 0),
        }
        return {
            "ok": bool(last_success and not metadata.get("lastError")), "schemaVersion": SCHEMA,
            "summary": summary, "briefingSummary": briefing_summary, "alerts": active, "history": history,
            "collector": {
                "lastPollAt": iso(last_poll) if last_poll else None,
                "lastSuccessAt": iso(last_success) if last_success else None,
                "lastErrorAt": iso(float(metadata.get("lastErrorAt", "0") or 0)) if metadata.get("lastErrorAt") else None,
                "lastError": metadata.get("lastError") or None,
                "consecutiveFailures": int(metadata.get("consecutiveFailures", "0") or 0),
                "pollsTotal": int(metadata.get("pollsTotal", "0") or 0),
                "transitionsTotal": int(metadata.get("transitionsTotal", "0") or 0),
                "ageSeconds": max(0, now - last_success) if last_success else None,
            },
            "executionContract": {
                "failedPollsResolveNothing": True, "transitionNotificationsOnly": True,
                "acknowledgementDoesNotSilencePrometheus": True, "gameMutation": False,
                "briefingMetaAlertsExcludedFromBriefingScore": True,
            },
        }

    def prometheus(self, *, enabled=True, worker_running=True, stale_after_seconds=120, now=None):
        now = float(now if now is not None else time.time())
        status = self.status(limit=1, now=now)
        summary, collector = status["summary"], status["collector"]
        age = collector["ageSeconds"] if collector["ageSeconds"] is not None else 0
        collector_up = bool(status["ok"] and collector["ageSeconds"] is not None and age <= float(stale_after_seconds))
        values = {
            "dash_alert_inbox_enabled": bool(enabled),
            "dash_alert_inbox_collector_up": collector_up,
            "dash_alert_inbox_worker_running": bool(worker_running),
            "dash_alert_inbox_active": summary["active"],
            "dash_alert_inbox_firing": summary["firing"],
            "dash_alert_inbox_pending": summary["pending"],
            "dash_alert_inbox_unacknowledged": summary["unacknowledged"],
            "dash_alert_inbox_critical": summary["critical"],
            "dash_alert_inbox_warning": summary["warning"],
            "dash_alert_inbox_consecutive_failures": collector["consecutiveFailures"],
            "dash_alert_inbox_transitions_total": collector["transitionsTotal"],
            "dash_alert_inbox_last_success_timestamp_seconds": parse_iso(collector["lastSuccessAt"]) or 0,
            "dash_alert_inbox_age_seconds": age,
        }
        return "".join(f"{key} {1 if isinstance(value, bool) and value else 0 if isinstance(value, bool) else value}\n" for key, value in values.items())
