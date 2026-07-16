#!/usr/bin/env python3
"""Tamper-evident operational change timeline and incident correlation."""

from __future__ import annotations

import datetime as _datetime
import fnmatch
import hashlib
import hmac
import ipaddress
import json
import os
import pathlib
import re
import sqlite3
import time
import uuid


KINDS = {"change", "incident-open", "incident-resolved", "evidence", "observation"}
IMPACTS = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SENSITIVE_KEY = re.compile(r"(?:password|passwd|secret|token|cookie|authorization|private.?key|credential)", re.I)
IDENTITY_KEY = re.compile(r"(?:^|_)(?:account|fls|player|character|peer|client|target|subject)(?:_|$)", re.I)
ABSOLUTE_PATH = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
URL_CREDENTIALS = re.compile(r"(https?://)[^/@:\s]+:[^/@\s]+@", re.I)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _iso(epoch):
    return _datetime.datetime.fromtimestamp(float(epoch), _datetime.timezone.utc).isoformat()


def _epoch(value=None):
    if value is None:
        return time.time()
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return _datetime.datetime.fromisoformat(text).timestamp()


def _bounded_int(value, name, minimum, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def load_policy(path):
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if raw.get("schemaVersion") != 1:
        raise ValueError("change-intelligence policy schemaVersion must be 1")
    rules = raw.get("rules")
    if not isinstance(rules, list) or not 1 <= len(rules) <= 256:
        raise ValueError("change-intelligence rules must contain 1..256 entries")
    normalized = []
    for row in rules:
        if not isinstance(row, dict):
            raise ValueError("each change-intelligence rule must be an object")
        pattern = str(row.get("pattern") or "")
        kind = str(row.get("kind") or "")
        category = str(row.get("category") or "")
        impact = str(row.get("impact") or "")
        if not pattern or len(pattern) > 128 or kind not in KINDS or impact not in IMPACTS or not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", category):
            raise ValueError("invalid change-intelligence rule")
        normalized.append({"pattern": pattern, "kind": kind, "category": category, "impact": impact})
    return {
        "schemaVersion": 1,
        "maxEvents": _bounded_int(raw.get("maxEvents", 1000000), "maxEvents", 1000, 10000000),
        "maxPayloadBytes": _bounded_int(raw.get("maxPayloadBytes", 32768), "maxPayloadBytes", 1024, 1048576),
        "correlationWindowBeforeSeconds": _bounded_int(raw.get("correlationWindowBeforeSeconds", 3600), "correlationWindowBeforeSeconds", 60, 86400),
        "correlationWindowAfterSeconds": _bounded_int(raw.get("correlationWindowAfterSeconds", 1800), "correlationWindowAfterSeconds", 60, 86400),
        "statusEventLimit": _bounded_int(raw.get("statusEventLimit", 200), "statusEventLimit", 10, 1000),
        "candidateLimit": _bounded_int(raw.get("candidateLimit", 20), "candidateLimit", 1, 100),
        "capsuleEvidenceLimit": _bounded_int(raw.get("capsuleEvidenceLimit", 200), "capsuleEvidenceLimit", 10, 1000),
        "historyImportLimit": _bounded_int(raw.get("historyImportLimit", 10000), "historyImportLimit", 0, 100000),
        "rules": normalized,
    }


def read_secret(path):
    path = pathlib.Path(path)
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 64:
        raise ValueError("change-intelligence HMAC secret must contain at least 64 encoded characters")
    if path.stat().st_mode & 0o077:
        raise PermissionError("change-intelligence HMAC secret must not be group/world accessible")
    return value.encode("utf-8")


def _hmac_value(secret, value):
    return hmac.new(secret, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


def sanitize(value, secret, *, key="", depth=0):
    if depth > 6:
        return "<depth-limit>"
    if SENSITIVE_KEY.search(str(key)):
        return "<redacted>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {
            str(child_key)[:128]: sanitize(child, secret, key=str(child_key), depth=depth + 1)
            for child_key, child in list(value.items())[:64]
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize(child, secret, key=key, depth=depth + 1) for child in list(value)[:32]]
    text = str(value)[:2000]
    if IDENTITY_KEY.search(str(key)):
        return "hmac:" + _hmac_value(secret, text)
    if str(key).lower() in {"ip", "ipaddress", "remoteaddr", "remote_address"}:
        try:
            ipaddress.ip_address(text)
            return "hmac:" + _hmac_value(secret, text)
        except ValueError:
            pass
    if ABSOLUTE_PATH.match(text) and not text.startswith(("/api/", "/metrics/", "/health")):
        return "path-hmac:" + _hmac_value(secret, text)
    text = URL_CREDENTIALS.sub(r"\1<redacted>@", text)
    text = BEARER.sub(r"\1<redacted>", text)
    return text[:500] + ("...[truncated]" if len(text) > 500 else "")


def classify(action, event, policy):
    for rule in policy["rules"]:
        if fnmatch.fnmatchcase(action, rule["pattern"]):
            return dict(rule)
    method = str(event.get("method") or "").upper()
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return {"pattern": "<write-method>", "kind": "change", "category": "administration", "impact": "medium"}
    return {"pattern": "<default>", "kind": "observation", "category": "operations", "impact": "info"}


def incident_key(action, event, kind):
    if kind not in {"incident-open", "incident-resolved"}:
        return None
    if event.get("finding_id"):
        return "desired:" + str(event["finding_id"])[:128]
    if event.get("incident_id"):
        return "slo:" + str(event["incident_id"])[:128]
    return "event:" + hashlib.sha256((action + _canonical(event)).encode()).hexdigest()[:32]


def validate_incident_key(value):
    value = str(value or "").strip()
    if len(value) > 256 or not re.fullmatch(r"(?:slo|desired|event):[A-Za-z0-9_.:-]{1,224}", value):
        raise ValueError("invalid change-intelligence incident key")
    return value


def event_scope(action, event, secret):
    values = {"action:" + action}
    for key in ("path", "target", "service", "map", "category", "subject", "objective_id", "desired_state_action", "capacity_action", "slo_action"):
        value = event.get(key)
        if value is not None and str(value).strip():
            if key in {"target", "subject"}:
                normalized = "hmac:" + _hmac_value(secret, str(value).strip())
            else:
                normalized = sanitize(value, secret, key=key)
            values.add(f"{key}:{str(normalized)[:160]}")
    return sorted(values)


class Store:
    def __init__(self, database, policy_path, secret_path, owner_uid=None, owner_gid=None):
        self.database = pathlib.Path(database)
        self.policy_path = pathlib.Path(policy_path)
        self.secret_path = pathlib.Path(secret_path)
        self.policy = load_policy(self.policy_path)
        self.secret = read_secret(self.secret_path)
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None

    def _secure(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.database.parent, 0o700)
        if self.database.exists():
            os.chmod(self.database, 0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(self.database.parent, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)
            if self.database.exists():
                os.chown(self.database, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)

    def connect(self, readonly=False):
        self._secure()
        if readonly:
            connection = sqlite3.connect(f"file:{self.database}?mode=ro", uri=True, timeout=10)
        else:
            connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys=on")
        connection.execute("pragma busy_timeout=10000")
        if not readonly:
            connection.execute("pragma journal_mode=wal")
            connection.execute("pragma synchronous=full")
        return connection

    def initialize(self):
        connection = self.connect()
        try:
            connection.executescript("""
                create table if not exists events (
                  sequence integer primary key autoincrement,
                  id text not null unique,
                  occurred_at real not null,
                  ingested_at real not null,
                  action text not null,
                  kind text not null,
                  category text not null,
                  impact text not null,
                  ok integer not null check(ok in (0,1)),
                  actor text,
                  source text not null,
                  source_fingerprint text not null unique,
                  incident_key text,
                  is_change integer not null check(is_change in (0,1)),
                  scope_json text not null,
                  data_json text not null,
                  previous_signature text,
                  signature text not null
                );
                create index if not exists change_events_time on events(occurred_at);
                create index if not exists change_events_incident on events(incident_key,occurred_at);
                create index if not exists change_events_changes on events(is_change,occurred_at);
                create trigger if not exists change_events_no_update before update on events begin select raise(abort,'change-intelligence events are append-only'); end;
                create trigger if not exists change_events_no_delete before delete on events begin select raise(abort,'change-intelligence events are append-only'); end;
                create table if not exists metadata (key text primary key, value text not null);
            """)
            connection.execute("insert into metadata(key,value) values('schema_version','1') on conflict(key) do update set value=excluded.value")
            connection.commit()
        finally:
            connection.close()
        self._secure()
        return self.verify()

    def initialize_if_needed(self):
        if not self.database.exists():
            self.initialize()

    def _sign(self, document):
        return hmac.new(self.secret, _canonical(document).encode(), hashlib.sha256).hexdigest()

    def source_fingerprint(self, raw_event):
        if not isinstance(raw_event, dict):
            raise ValueError("change-intelligence source event must be an object")
        return _hmac_value(self.secret, _canonical(raw_event))

    def existing_source_fingerprints(self, values):
        values = list(dict.fromkeys(str(value) for value in values if value))
        if not values:
            return set()
        self.initialize_if_needed()
        connection = self.connect(readonly=True)
        try:
            found = set()
            for offset in range(0, len(values), 500):
                chunk = values[offset:offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                found.update(row["source_fingerprint"] for row in connection.execute(f"select source_fingerprint from events where source_fingerprint in ({placeholders})", chunk))
            return found
        finally:
            connection.close()

    @staticmethod
    def _document(row):
        return {
            "id": row["id"], "occurredAt": row["occurred_at"], "ingestedAt": row["ingested_at"],
            "action": row["action"], "kind": row["kind"], "category": row["category"],
            "impact": row["impact"], "ok": bool(row["ok"]), "actor": row["actor"], "source": row["source"],
            "sourceFingerprint": row["source_fingerprint"],
            "incidentKey": row["incident_key"], "isChange": bool(row["is_change"]),
            "scope": json.loads(row["scope_json"]), "data": json.loads(row["data_json"]),
            "previousSignature": row["previous_signature"],
        }

    def record(self, raw_event, *, source="admin-audit", ingested_at=None):
        if not isinstance(raw_event, dict):
            raise ValueError("change-intelligence event must be an object")
        action = str(raw_event.get("action") or "").strip()[:128]
        if not action or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", action):
            raise ValueError("change-intelligence action is invalid")
        classification = classify(action, raw_event, self.policy)
        occurred = _epoch(raw_event.get("ts"))
        ingested = _epoch(ingested_at)
        payload = sanitize({key: value for key, value in raw_event.items() if key not in {"action", "ts", "ok", "actor", "principal", "principal_id"}}, self.secret)
        encoded = _canonical(payload)
        if len(encoded.encode()) > self.policy["maxPayloadBytes"]:
            raise ValueError("change-intelligence payload exceeds maxPayloadBytes")
        actor = raw_event.get("actor") or raw_event.get("principal_id") or raw_event.get("principal")
        if isinstance(actor, dict):
            actor = actor.get("id")
        actor = str(actor).strip()[:128] if actor else None
        if actor and not re.fullmatch(r"[A-Za-z0-9_.:@/-]+", actor):
            actor = "hmac:" + _hmac_value(self.secret, actor)
        key = incident_key(action, raw_event, classification["kind"])
        source = str(source or "unknown").strip()[:128]
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]+", source):
            raise ValueError("change-intelligence source is invalid")
        scope = event_scope(action, raw_event, self.secret)
        source_fingerprint = self.source_fingerprint(raw_event)
        event_id = "change-" + uuid.uuid4().hex
        connection = self.connect()
        try:
            connection.execute("begin immediate")
            duplicate = connection.execute("select * from events where source_fingerprint=?", (source_fingerprint,)).fetchone()
            if duplicate:
                connection.rollback()
                result = self._public(duplicate)
                result.update({"duplicate": True, "pattern": classification["pattern"]})
                return result
            count = connection.execute("select count(*) from events").fetchone()[0]
            if count >= self.policy["maxEvents"]:
                raise RuntimeError("change-intelligence maxEvents reached; archive and rotate the ledger")
            prior = connection.execute("select signature from events order by sequence desc limit 1").fetchone()
            previous = prior["signature"] if prior else None
            document = {
                "id": event_id, "occurredAt": occurred, "ingestedAt": ingested,
                "action": action, "kind": classification["kind"], "category": classification["category"],
                "impact": classification["impact"], "ok": bool(raw_event.get("ok", True)),
                "actor": actor, "source": source, "sourceFingerprint": source_fingerprint,
                "incidentKey": key, "isChange": classification["kind"] == "change",
                "scope": scope, "data": payload, "previousSignature": previous,
            }
            signature = self._sign(document)
            connection.execute(
                "insert into events(id,occurred_at,ingested_at,action,kind,category,impact,ok,actor,source,source_fingerprint,incident_key,is_change,scope_json,data_json,previous_signature,signature) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, occurred, ingested, action, classification["kind"], classification["category"], classification["impact"], int(document["ok"]), actor, source, source_fingerprint, key, int(document["isChange"]), _canonical(scope), encoded, previous, signature),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        result = {"ok": True, "id": event_id, "occurredAt": _iso(occurred), **classification, "incidentKey": key, "signature": signature}
        if classification["kind"] == "incident-open":
            result["candidates"] = self.correlate(key)
        return result

    @staticmethod
    def _public(row):
        return {
            "sequence": row["sequence"], "id": row["id"], "occurredAt": _iso(row["occurred_at"]),
            "ingestedAt": _iso(row["ingested_at"]), "action": row["action"], "kind": row["kind"],
            "category": row["category"], "impact": row["impact"], "ok": bool(row["ok"]),
            "actor": row["actor"], "source": row["source"], "incidentKey": row["incident_key"], "isChange": bool(row["is_change"]),
            "scope": json.loads(row["scope_json"]), "data": json.loads(row["data_json"]),
            "signature": row["signature"],
        }

    def correlate(self, key):
        self.initialize_if_needed()
        key = validate_incident_key(key)
        connection = self.connect(readonly=True)
        try:
            incident = connection.execute("select * from events where incident_key=? and kind='incident-open' order by occurred_at desc limit 1", (str(key),)).fetchone()
            if not incident:
                return []
            before = self.policy["correlationWindowBeforeSeconds"]
            rows = connection.execute(
                "select * from events where is_change=1 and occurred_at<=? and occurred_at>=? order by occurred_at desc limit 1000",
                (incident["occurred_at"], incident["occurred_at"] - before),
            ).fetchall()
            incident_scope = set(json.loads(incident["scope_json"]))
            candidates = []
            for row in rows:
                age = max(0.0, incident["occurred_at"] - row["occurred_at"])
                overlap = sorted(incident_scope & set(json.loads(row["scope_json"])))
                recency = max(0.0, 1.0 - age / before)
                score = IMPACTS[row["impact"]] * 2.0 + recency * 2.0 + min(3, len(overlap)) * 1.5
                reasons = [f"{int(age)}s before incident", f"{row['impact']} impact"]
                if overlap:
                    reasons.append("shared scope: " + ", ".join(overlap[:3]))
                public = self._public(row)
                public.pop("data", None)
                public.pop("signature", None)
                candidates.append({**public, "ageSeconds": age, "score": round(score, 3), "reasons": reasons})
            candidates.sort(key=lambda row: (-row["score"], row["ageSeconds"], -row["sequence"]))
            return candidates[: self.policy["candidateLimit"]]
        finally:
            connection.close()

    def capsule(self, key):
        self.initialize_if_needed()
        key = validate_incident_key(key)
        connection = self.connect(readonly=True)
        try:
            rows = connection.execute("select * from events where incident_key=? order by occurred_at,sequence", (str(key),)).fetchall()
            if not rows:
                raise ValueError("change-intelligence incident does not exist")
            opened = next((row for row in reversed(rows) if row["kind"] == "incident-open"), None)
            if not opened:
                raise ValueError("change-intelligence incident has no open event")
            resolved = next((row for row in reversed(rows) if row["kind"] == "incident-resolved" and row["occurred_at"] >= opened["occurred_at"]), None)
            end = min(
                resolved["occurred_at"] if resolved else time.time(),
                opened["occurred_at"] + self.policy["correlationWindowAfterSeconds"],
            )
            followup = connection.execute(
                "select * from events where occurred_at>? and occurred_at<=? order by occurred_at,sequence limit ?",
                (opened["occurred_at"], end, self.policy["capsuleEvidenceLimit"]),
            ).fetchall()
            return {
                "ok": True, "incidentKey": key, "status": "resolved" if resolved else "open",
                "opened": self._public(opened), "resolved": self._public(resolved) if resolved else None,
                "candidateChanges": self.correlate(key), "followupEvidence": [self._public(row) for row in followup],
                "causalityClaimed": False,
                "interpretation": "Candidates are ranked temporal/scope correlations, not proof of causality.",
            }
        finally:
            connection.close()

    def status(self, limit=None):
        self.initialize_if_needed()
        limit = max(1, min(int(limit or self.policy["statusEventLimit"]), 1000))
        connection = self.connect(readonly=True)
        try:
            recent = connection.execute("select * from events order by occurred_at desc,sequence desc limit ?", (limit,)).fetchall()
            all_incident_rows = connection.execute("select * from events where incident_key is not null order by occurred_at,sequence").fetchall()
            total = connection.execute("select count(*) from events").fetchone()[0]
        finally:
            connection.close()
        incidents = {}
        for row in all_incident_rows:
            key = row["incident_key"]
            state = incidents.setdefault(key, {"incidentKey": key, "opened": None, "resolved": None})
            if row["kind"] == "incident-open":
                state["opened"] = self._public(row)
                state["resolved"] = None
            elif row["kind"] == "incident-resolved":
                state["resolved"] = self._public(row)
        incident_rows = []
        for state in incidents.values():
            if not state["opened"]:
                continue
            state["status"] = "resolved" if state["resolved"] else "open"
            incident_rows.append(state)
        incident_rows.sort(key=lambda row: row["opened"]["occurredAt"], reverse=True)
        relevant = [row for row in incident_rows if row["status"] == "open"]
        relevant.extend(row for row in incident_rows if row["status"] != "open" and row not in relevant and len(relevant) < limit)
        for state in relevant:
            state["candidateChanges"] = self.correlate(state["incidentKey"])
        integrity = self.verify()
        return {
            "ok": integrity["ok"], "state": "invalid" if not integrity["ok"] else "active",
            "eventCount": total, "openIncidents": [row for row in relevant if row["status"] == "open"],
            "incidents": relevant[:limit], "recentEvents": [self._public(row) for row in recent],
            "policy": self.policy, "integrity": integrity,
        }

    def verify(self):
        if not self.database.exists():
            return {"ok": False, "sqlite": "missing", "eventChainValid": False}
        connection = self.connect(readonly=True)
        try:
            integrity = connection.execute("pragma integrity_check").fetchone()[0]
            triggers = {row["name"] for row in connection.execute("select name from sqlite_master where type='trigger'")}
            required = {"change_events_no_update", "change_events_no_delete"}
            previous = None
            valid = True
            count = 0
            for row in connection.execute("select * from events order by sequence"):
                count += 1
                if row["previous_signature"] != previous or not hmac.compare_digest(self._sign(self._document(row)), row["signature"]):
                    valid = False
                previous = row["signature"]
            ok = integrity == "ok" and required.issubset(triggers) and valid
            return {"ok": ok, "sqlite": integrity, "appendOnlyTriggers": required.issubset(triggers), "eventChainValid": valid, "eventCount": count, "lastEventSignature": previous}
        except (sqlite3.Error, ValueError, json.JSONDecodeError, OSError) as exc:
            return {"ok": False, "sqlite": "error", "eventChainValid": False, "error": str(exc)}
        finally:
            connection.close()

    def metadata(self, key, default=None):
        self.initialize_if_needed()
        connection = self.connect(readonly=True)
        try:
            row = connection.execute("select value from metadata where key=?", (str(key),)).fetchone()
            return row["value"] if row else default
        finally:
            connection.close()

    def set_metadata(self, key, value):
        self.initialize_if_needed()
        connection = self.connect()
        try:
            connection.execute("insert into metadata(key,value) values(?,?) on conflict(key) do update set value=excluded.value", (str(key), str(value)))
            connection.commit()
        finally:
            connection.close()

    def backup(self, target):
        self.initialize_if_needed()
        target = pathlib.Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(target.parent, 0o700)
        source = self.connect(readonly=True)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
            destination.commit()
        finally:
            destination.close()
            source.close()
        os.chmod(target, 0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(target, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)
        verification = Store(target, self.policy_path, self.secret_path, self.owner_uid, self.owner_gid).verify()
        if not verification.get("ok"):
            target.unlink(missing_ok=True)
            raise RuntimeError(f"change-intelligence backup verification failed: {verification}")
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"path": str(target), "bytes": target.stat().st_size, "sha256": digest.hexdigest(), "integrity": verification}

    def prometheus(self):
        status = self.status(limit=10)
        events = status["recentEvents"]
        latest = _epoch(events[0]["occurredAt"]) if events else "NaN"
        with_candidates = sum(1 for row in status["openIncidents"] if row["candidateChanges"])
        return "\n".join([
            "# HELP dash_change_intelligence_collector_up Change timeline SQLite, triggers, and HMAC chain verify.",
            "# TYPE dash_change_intelligence_collector_up gauge",
            f"dash_change_intelligence_collector_up {1 if status['integrity']['ok'] else 0}",
            f"dash_change_intelligence_events_total {status['eventCount']}",
            f"dash_change_intelligence_open_incidents {len(status['openIncidents'])}",
            f"dash_change_intelligence_open_incidents_with_candidate_changes {with_candidates}",
            f"dash_change_intelligence_last_event_timestamp_seconds {latest}",
        ]) + "\n"
