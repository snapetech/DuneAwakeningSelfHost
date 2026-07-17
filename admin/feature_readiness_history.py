"""Tamper-evident transition history for the secret-safe feature matrix."""

from __future__ import annotations

import contextlib
import datetime as _datetime
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import sqlite3
import tempfile
import time


SCHEMA_VERSION = 1
STATES = {"ready", "canary-pending", "disabled", "partial", "blocked", "degraded", "external-blocked"}
PROBLEM_STATES = {"partial", "blocked", "degraded", "external-blocked"}
STATE_WEIGHT = {
    "ready": 0, "disabled": 0, "canary-pending": 1,
    "external-blocked": 2, "partial": 3, "blocked": 4, "degraded": 5,
}
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _iso(epoch):
    return _datetime.datetime.fromtimestamp(float(epoch), _datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded_text(value, label, limit):
    text = str(value or "").strip()
    if not text or len(text) > limit or any(ord(char) < 32 for char in text):
        raise ValueError(f"{label} is invalid")
    return text


def _snapshot(status):
    if not isinstance(status, dict) or status.get("schemaVersion") != "dash-feature-readiness/v1":
        raise ValueError("feature readiness status schema is invalid")
    features = status.get("features")
    if not isinstance(features, list) or not 1 <= len(features) <= 512:
        raise ValueError("feature readiness status must contain 1..512 features")
    states = []
    seen = set()
    for row in features:
        feature_id = str((row or {}).get("id") or "")
        state = str((row or {}).get("state") or "")
        if not ID_RE.fullmatch(feature_id) or feature_id in seen or state not in STATES:
            raise ValueError("feature readiness status contains an invalid feature id or state")
        seen.add(feature_id)
        states.append({"id": feature_id, "state": state, "active": bool(row.get("active"))})
    states.sort(key=lambda row: row["id"])
    summary = {state: sum(1 for row in states if row["state"] == state) for state in STATES}
    summary.update({
        "total": len(states),
        "active": sum(1 for row in states if row["active"]),
        "activeProblems": sum(1 for row in states if row["active"] and row["state"] in PROBLEM_STATES),
    })
    snapshot = {"schemaVersion": SCHEMA_VERSION, "overall": "ready" if summary["activeProblems"] == 0 else "attention", "summary": summary, "states": states}
    snapshot["sha256"] = hashlib.sha256(_canonical(snapshot).encode()).hexdigest()
    return snapshot


def _changes(previous, current):
    before = {row["id"]: row for row in (previous or {}).get("states", [])}
    after = {row["id"]: row for row in current["states"]}
    changes = []
    for feature_id in sorted(set(before) | set(after)):
        old = before.get(feature_id)
        new = after.get(feature_id)
        old_state = old["state"] if old else "absent"
        new_state = new["state"] if new else "absent"
        old_active = bool(old and old["active"])
        new_active = bool(new and new["active"])
        if old_state == new_state and old_active == new_active:
            continue
        if old is None:
            direction = "regression" if new_active and new_state in PROBLEM_STATES else "change"
        elif new is None:
            direction = "change"
        elif new_state == "ready" and old_state != "ready":
            direction = "improvement"
        elif old_active and old_state not in PROBLEM_STATES and new_active and new_state in PROBLEM_STATES:
            direction = "regression"
        elif old_state in PROBLEM_STATES and (not new_active or new_state not in PROBLEM_STATES):
            direction = "improvement"
        elif STATE_WEIGHT.get(new_state, 9) > STATE_WEIGHT.get(old_state, 9):
            direction = "regression"
        elif STATE_WEIGHT.get(new_state, 9) < STATE_WEIGHT.get(old_state, 9):
            direction = "improvement"
        else:
            direction = "change"
        changes.append({
            "id": feature_id, "from": old_state, "to": new_state,
            "activeBefore": old_active, "activeAfter": new_active, "direction": direction,
        })
    return changes


def _validate_snapshot(document):
    if not isinstance(document, dict) or set(document) != {"schemaVersion", "overall", "summary", "states", "sha256"}:
        raise ValueError("feature readiness history snapshot schema is invalid")
    expected = _snapshot({
        "schemaVersion": "dash-feature-readiness/v1",
        "features": document.get("states"),
    })
    if not hmac.compare_digest(_canonical(document), _canonical(expected)):
        raise ValueError("feature readiness history snapshot digest or summary is invalid")
    return expected


def _transition_kind(previous, current, changes):
    if previous is None:
        if changes:
            raise ValueError("feature readiness baseline cannot contain transitions")
        return "baseline"
    expected_changes = _changes(previous, current)
    if not hmac.compare_digest(_canonical(changes), _canonical(expected_changes)):
        raise ValueError("feature readiness transition set does not match its snapshots")
    if previous.get("sha256") == current.get("sha256"):
        raise ValueError("feature readiness history contains a duplicate adjacent snapshot")
    directions = {row["direction"] for row in changes}
    return "mixed" if {"regression", "improvement"} <= directions else "regression" if "regression" in directions else "improvement" if "improvement" in directions else "change"


class Store:
    def __init__(self, path, secret_file, *, owner_uid=None, owner_gid=None, now=time.time):
        self.path = pathlib.Path(path)
        self.secret_file = pathlib.Path(secret_file)
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None
        self.now = now

    def _secure(self):
        for directory in (self.path.parent, self.secret_file.parent):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)
            if os.geteuid() == 0 and self.owner_uid is not None and self.owner_gid is not None:
                os.chown(directory, self.owner_uid, self.owner_gid)
        for path in (self.path, self.secret_file):
            if path.exists():
                os.chmod(path, 0o600)
                if os.geteuid() == 0 and self.owner_uid is not None and self.owner_gid is not None:
                    os.chown(path, self.owner_uid, self.owner_gid)

    def _secret(self, create=True):
        self._secure()
        if not self.secret_file.exists() and create:
            descriptor, temporary = tempfile.mkstemp(prefix=self.secret_file.name + ".", dir=self.secret_file.parent)
            try:
                os.write(descriptor, secrets.token_hex(32).encode() + b"\n")
                os.fsync(descriptor)
                os.close(descriptor)
                descriptor = -1
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.secret_file)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                pathlib.Path(temporary).unlink(missing_ok=True)
        try:
            raw = self.secret_file.read_bytes().strip()
        except FileNotFoundError as exc:
            raise RuntimeError("feature readiness history HMAC secret is missing") from exc
        try:
            value = bytes.fromhex(raw.decode()) if len(raw) == 64 else raw
        except (UnicodeDecodeError, ValueError):
            value = raw
        if len(value) < 32 or self.secret_file.is_symlink() or self.secret_file.stat().st_mode & 0o077:
            raise RuntimeError("feature readiness history HMAC secret must be a private regular file with at least 32 bytes")
        return value

    @contextlib.contextmanager
    def connect(self, *, write=False):
        self._secure()
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("pragma busy_timeout=15000")
            if write:
                connection.execute("pragma journal_mode=wal")
                connection.execute("pragma synchronous=full")
                connection.execute("begin immediate")
            else:
                connection.execute("pragma query_only=on")
            yield connection
            if write:
                connection.commit()
        except Exception:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()
            self._secure()

    def initialize(self):
        self._secret(create=True)
        with self.connect(write=True) as connection:
            connection.executescript("""
                create table if not exists transitions (
                  sequence integer primary key autoincrement,
                  recorded_at real not null,
                  source text not null,
                  commit_id text not null,
                  kind text not null check(kind in ('baseline','regression','improvement','mixed','change')),
                  snapshot_sha256 text not null,
                  snapshot_json text not null,
                  changes_json text not null,
                  previous_hmac text,
                  event_hmac text not null unique
                );
                create trigger if not exists transitions_no_update before update on transitions
                begin select raise(abort,'feature readiness transitions are append-only'); end;
                create trigger if not exists transitions_no_delete before delete on transitions
                begin select raise(abort,'feature readiness transitions are append-only'); end;
                create table if not exists metadata (key text primary key, value text not null);
            """)
            connection.execute("insert into metadata(key,value) values('schema_version',?) on conflict(key) do nothing", (str(SCHEMA_VERSION),))
        return self.status(limit=20)

    @staticmethod
    def _event_payload(row):
        return {
            "sequence": int(row["sequence"]), "recordedAt": float(row["recorded_at"]),
            "source": row["source"], "commit": row["commit_id"], "kind": row["kind"],
            "snapshotSha256": row["snapshot_sha256"],
            "snapshot": json.loads(row["snapshot_json"]),
            "changes": json.loads(row["changes_json"]), "previousHmac": row["previous_hmac"],
        }

    def integrity(self):
        secret = self._secret(create=False)
        with self.connect() as connection:
            triggers = {row[0] for row in connection.execute("select name from sqlite_master where type='trigger'")}
            schema = connection.execute("select value from metadata where key='schema_version'").fetchone()
            database_ok = (
                connection.execute("pragma integrity_check").fetchone()[0] == "ok"
                and {"transitions_no_update", "transitions_no_delete"}.issubset(triggers)
                and schema is not None and schema[0] == str(SCHEMA_VERSION)
            )
            rows = connection.execute("select * from transitions order by sequence").fetchall()
        previous = None
        previous_snapshot = None
        for expected_sequence, row in enumerate(rows, 1):
            try:
                payload = self._event_payload(row)
                expected = hmac.new(secret, _canonical(payload).encode(), hashlib.sha256).hexdigest()
                snapshot = _validate_snapshot(payload["snapshot"])
                kind = _transition_kind(previous_snapshot, snapshot, payload["changes"])
            except (TypeError, ValueError, json.JSONDecodeError):
                return {"ok": False, "databaseOk": database_ok, "chainOk": False, "events": len(rows), "headSequence": len(rows), "headHmacSha256": ""}
            if row["sequence"] != expected_sequence or row["previous_hmac"] != previous or row["kind"] != kind or not hmac.compare_digest(row["event_hmac"], expected):
                return {"ok": False, "databaseOk": database_ok, "chainOk": False, "events": len(rows), "headSequence": len(rows), "headHmacSha256": ""}
            previous = row["event_hmac"]
            previous_snapshot = snapshot
        return {
            "ok": bool(database_ok), "databaseOk": database_ok, "chainOk": True,
            "events": len(rows), "headSequence": len(rows),
            "headHmacSha256": hashlib.sha256((previous or "").encode()).hexdigest() if previous else "",
        }

    def record(self, status, *, source="admin-evaluation", commit="unknown"):
        source = _bounded_text(source, "history source", 80)
        commit = _bounded_text(commit, "history commit", 80)
        if commit != "unknown" and not re.fullmatch(r"[0-9a-f]{7,64}", commit):
            raise ValueError("history commit must be unknown or a Git hex id")
        current = _snapshot(status)
        secret = self._secret(create=False)
        with self.connect(write=True) as connection:
            if connection.execute("pragma integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("feature readiness history database integrity check failed")
            triggers = {row[0] for row in connection.execute("select name from sqlite_master where type='trigger'")}
            schema = connection.execute("select value from metadata where key='schema_version'").fetchone()
            if not {"transitions_no_update", "transitions_no_delete"}.issubset(triggers) or schema is None or schema[0] != str(SCHEMA_VERSION):
                raise RuntimeError("feature readiness history append-only schema is invalid")
            rows = connection.execute("select * from transitions order by sequence").fetchall()
            previous_hmac = None
            previous_snapshot = None
            for expected_sequence, row in enumerate(rows, 1):
                payload = self._event_payload(row)
                expected = hmac.new(secret, _canonical(payload).encode(), hashlib.sha256).hexdigest()
                snapshot = _validate_snapshot(payload["snapshot"])
                kind = _transition_kind(previous_snapshot, snapshot, payload["changes"])
                if row["sequence"] != expected_sequence or row["previous_hmac"] != previous_hmac or row["kind"] != kind or not hmac.compare_digest(row["event_hmac"], expected):
                    raise RuntimeError("feature readiness history HMAC chain is invalid")
                previous_hmac = row["event_hmac"]
                previous_snapshot = snapshot
            if previous_snapshot and previous_snapshot.get("sha256") == current["sha256"]:
                return {"ok": True, "changed": False, "sequence": len(rows), "snapshotSha256": current["sha256"]}
            changes = _changes(previous_snapshot, current) if previous_snapshot else []
            kind = _transition_kind(previous_snapshot, current, changes)
            sequence = len(rows) + 1
            recorded_at = float(self.now())
            pseudo = {
                "sequence": sequence, "recorded_at": recorded_at, "source": source,
                "commit_id": commit, "kind": kind, "snapshot_sha256": current["sha256"],
                "snapshot_json": _canonical(current), "changes_json": _canonical(changes),
                "previous_hmac": previous_hmac,
            }
            payload = self._event_payload(pseudo)
            event_hmac = hmac.new(secret, _canonical(payload).encode(), hashlib.sha256).hexdigest()
            connection.execute(
                "insert into transitions(sequence,recorded_at,source,commit_id,kind,snapshot_sha256,snapshot_json,changes_json,previous_hmac,event_hmac) values(?,?,?,?,?,?,?,?,?,?)",
                (sequence, recorded_at, source, commit, kind, current["sha256"], _canonical(current), _canonical(changes), previous_hmac, event_hmac),
            )
        return {"ok": True, "changed": True, "sequence": sequence, "kind": kind, "changes": changes, "snapshotSha256": current["sha256"], "recordedAt": _iso(recorded_at)}

    def status(self, limit=100):
        limit = max(1, min(int(limit), 1000))
        integrity = self.integrity()
        with self.connect() as connection:
            rows = connection.execute("select * from transitions order by sequence desc limit ?", (limit,)).fetchall()
            kind_rows = connection.execute("select kind,count(*) as count from transitions group by kind").fetchall()
            last_regression = connection.execute("select max(recorded_at) from transitions where kind in ('regression','mixed')").fetchone()[0]
        events = []
        for row in rows:
            try:
                payload = self._event_payload(row)
                events.append({
                    "sequence": payload["sequence"], "recordedAt": _iso(payload["recordedAt"]),
                    "source": payload["source"], "commit": payload["commit"], "kind": payload["kind"],
                    "snapshotSha256": payload["snapshotSha256"], "summary": payload["snapshot"]["summary"],
                    "overall": payload["snapshot"]["overall"], "changes": payload["changes"],
                })
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                integrity["ok"] = False
                integrity["chainOk"] = False
        kinds = {kind: 0 for kind in ("baseline", "regression", "improvement", "mixed", "change")}
        for row in kind_rows:
            if row["kind"] in kinds:
                kinds[row["kind"]] = int(row["count"])
        return {
            "ok": bool(integrity["ok"]), "schemaVersion": SCHEMA_VERSION, "integrity": integrity,
            "summary": {**kinds, "events": integrity["events"], "lastRegressionAt": _iso(last_regression) if last_regression else None},
            "lastRegressionTimestamp": float(last_regression or 0), "latest": events[0] if events else None,
            "events": events,
        }

    def prometheus(self):
        status = self.status(limit=1000)
        summary = status["summary"]
        latest = status.get("latest") or {}
        return "\n".join([
            f"dash_feature_readiness_history_valid {1 if status['ok'] else 0}",
            f"dash_feature_readiness_history_events_total {int(summary['events'])}",
            f"dash_feature_readiness_history_regressions_total {int(summary['regression']) + int(summary['mixed'])}",
            f"dash_feature_readiness_history_improvements_total {int(summary['improvement']) + int(summary['mixed'])}",
            f"dash_feature_readiness_history_head_sequence {int((latest or {}).get('sequence') or 0)}",
            f"dash_feature_readiness_history_last_regression_timestamp_seconds {float(status.get('lastRegressionTimestamp') or 0):.6f}",
            "",
        ])


def verify_database(path, secret_file):
    store = Store(path, secret_file)
    if not pathlib.Path(path).is_file() or not pathlib.Path(secret_file).is_file():
        return {"ok": False, "error": "database or HMAC secret is missing"}
    return store.integrity()
