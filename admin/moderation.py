#!/usr/bin/env python3
"""Isolated moderation, presence-history, and security-event persistence.

This database is intentionally separate from the Funcom game schema.  A ban is
an operator policy record; enforcement is performed by the admin worker through
the confirmed native KickPlayer notification and is recorded as a case event.
"""

import contextlib
import datetime
import hashlib
import ipaddress
import json
import math
import os
import pathlib
import re
import sqlite3
import uuid


SCHEMA_VERSION = 1
CASE_STATUSES = {"open", "investigating", "actioned", "closed", "appealed"}
CASE_SEVERITIES = {"info", "low", "medium", "high", "critical"}
SECURITY_SEVERITIES = {"info", "low", "medium", "high", "critical"}
IDENTITY_TYPES = {"account", "funcom", "platform"}


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _clean(value, limit=1000):
    value = str(value or "").strip()
    if not value:
        return ""
    return value[:limit]


def _int(value, label, minimum=None, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{label} must be at most {maximum}")
    return parsed


def _json(value):
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _row(row):
    if row is None:
        return None
    result = dict(row)
    for key in ("metadata", "evidence"):
        if key in result:
            try:
                result[key] = json.loads(result[key] or "{}")
            except (TypeError, json.JSONDecodeError):
                result[key] = {}
    return result


def redact_security_text(value, limit=500):
    """Retain useful event context without persisting raw network identities."""
    text = _clean(value, max(limit * 2, limit))
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"(?i)\b(?:token|secret|password|authorization)\s*[=:]\s*\S+", "<redacted-secret>", text)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<redacted-email>", text)
    # IPv4/IPv6 handling is deliberately conservative: tokens which parse as
    # addresses are removed, and common host:port IPv4 forms are covered first.
    text = re.sub(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?![\w.])", "<redacted-ip>", text)
    parts = []
    for token in text.split():
        candidate = token.strip("[](),;'")
        host = candidate.rsplit(":", 1)[0] if candidate.count(":") > 1 and candidate.rsplit(":", 1)[-1].isdigit() else candidate
        try:
            ipaddress.ip_address(host)
            parts.append(token.replace(candidate, "<redacted-ip>"))
        except ValueError:
            parts.append(token)
    return " ".join(parts)[:limit]


SECURITY_PATTERNS = (
    ("anti-cheat", "high", re.compile(r"(?i)battl.?eye|easy.?anti.?cheat|anti.?cheat")),
    ("cheat-signal", "high", re.compile(r"(?i)\bcheat(?:ing|er)?\b|integrity violation|tamper")),
    ("authentication", "medium", re.compile(r"(?i)auth(?:entication|orization)? (?:fail|reject|denied)|invalid ticket")),
    ("disconnect", "low", re.compile(r"(?i)\bkick(?:ed)?\b|disconnect(?:ed)?|connection rejected")),
    ("rate-limit", "medium", re.compile(r"(?i)rate.?limit|too many (?:requests|connections)|flood")),
)


def normalize_security_line(service, line):
    line = str(line or "").strip()
    if not line:
        return None
    for category, severity, pattern in SECURITY_PATTERNS:
        if pattern.search(line):
            if category == "disconnect" and re.search(r"(?i)\b(?:libcurl|LogHttp)\b", line):
                return None
            summary = redact_security_text(line)
            fingerprint = hashlib.sha256(f"{service}\0{line}".encode("utf-8", "replace")).hexdigest()
            return {
                "fingerprint": fingerprint,
                "category": category,
                "severity": severity,
                "source": _clean(service, 80),
                "summary": summary,
                "evidence": {"redacted": True},
            }
    return None


class Store:
    def __init__(self, path, *, owner_uid=None, owner_gid=None):
        self.path = pathlib.Path(path)
        self.owner_uid = self._owner(owner_uid)
        self.owner_gid = self._owner(owner_gid)

    @staticmethod
    def _owner(value):
        if value in (None, ""):
            return None
        return _int(value, "owner id", 0)

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys=on")
        connection.execute("pragma journal_mode=wal")
        connection.execute("pragma synchronous=full")
        connection.execute("pragma busy_timeout=30000")
        return connection

    @contextlib.contextmanager
    def transaction(self):
        connection = self._connect()
        try:
            connection.execute("begin immediate")
            yield connection
            connection.execute("commit")
        except Exception:
            connection.execute("rollback")
            raise
        finally:
            connection.close()
            self._fix_permissions()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.closing(self._connect()) as connection:
            connection.executescript("""
                create table if not exists metadata(key text primary key, value text not null);
                create table if not exists settings(key text primary key, value text not null, updated_at text not null);
                create table if not exists cases(
                    id text primary key, account_id integer, character_name text, funcom_id text, platform_id text,
                    category text not null, severity text not null, status text not null, summary text not null,
                    opened_by text not null, assigned_to text, created_at text not null, updated_at text not null,
                    closed_at text, metadata text not null default '{}'
                );
                create index if not exists cases_account_idx on cases(account_id, updated_at desc);
                create table if not exists case_events(
                    id integer primary key autoincrement, case_id text not null references cases(id),
                    event_type text not null, actor text not null, detail text not null,
                    created_at text not null, metadata text not null default '{}'
                );
                create index if not exists case_events_case_idx on case_events(case_id, id desc);
                create trigger if not exists case_events_no_update before update on case_events begin select raise(abort,'case events are append-only'); end;
                create trigger if not exists case_events_no_delete before delete on case_events begin select raise(abort,'case events are append-only'); end;
                create table if not exists bans(
                    id text primary key, case_id text not null references cases(id), account_id integer,
                    funcom_id text, platform_id text, reason text not null, starts_at text not null,
                    expires_at text, active integer not null check(active in (0,1)), created_by text not null,
                    created_at text not null, revoked_by text, revoked_at text, revoke_reason text
                );
                create index if not exists bans_active_idx on bans(active, account_id, funcom_id, platform_id);
                create table if not exists allowlist(
                    identity_type text not null, identity_value text not null, label text, added_by text not null,
                    created_at text not null, expires_at text, primary key(identity_type, identity_value)
                );
                create table if not exists presence_sessions(
                    id text primary key, account_id integer not null, character_name text, funcom_id text,
                    platform_id text, started_at text not null, last_seen_at text not null, ended_at text,
                    map text, partition_id text, samples integer not null default 0
                );
                create index if not exists presence_sessions_account_idx on presence_sessions(account_id, started_at desc);
                create unique index if not exists presence_one_open_idx on presence_sessions(account_id) where ended_at is null;
                create table if not exists heatmap_cells(
                    day text not null, hour integer not null, map text not null, cell_x integer not null,
                    cell_y integer not null, samples integer not null, first_seen_at text not null,
                    last_seen_at text not null, primary key(day,hour,map,cell_x,cell_y)
                );
                create table if not exists security_events(
                    id integer primary key autoincrement, fingerprint text not null unique, category text not null,
                    severity text not null, source text not null, account_id integer, summary text not null,
                    evidence text not null default '{}', observed_at text not null
                );
                create index if not exists security_events_time_idx on security_events(observed_at desc);
                create table if not exists enforcement_events(
                    id integer primary key autoincrement, ban_id text not null references bans(id), account_id integer,
                    action text not null, ok integer not null check(ok in (0,1)), detail text not null,
                    created_at text not null
                );
                create index if not exists enforcement_recent_idx on enforcement_events(ban_id, account_id, created_at desc);
                create table if not exists policy_enforcement_events(
                    id integer primary key autoincrement, policy text not null, account_id integer not null,
                    action text not null, ok integer not null check(ok in (0,1)), detail text not null,
                    created_at text not null
                );
                create index if not exists policy_enforcement_recent_idx on policy_enforcement_events(policy,account_id,created_at desc);
            """)
            connection.execute("insert into metadata(key,value) values('schema_version',?) on conflict(key) do update set value=excluded.value", (str(SCHEMA_VERSION),))
            connection.execute("insert into settings(key,value,updated_at) values('allowlist_enforcement','false',?) on conflict(key) do nothing", (utcnow(),))
            connection.execute("delete from security_events where category='disconnect' and (summary like '%libcurl%' or summary like '%LogHttp%')")
            for event in connection.execute("select id,summary from security_events").fetchall():
                cleaned = redact_security_text(event["summary"])
                if cleaned != event["summary"]:
                    connection.execute("update security_events set summary=? where id=?", (cleaned, event["id"]))
        self._fix_permissions()
        return self

    def _fix_permissions(self):
        for path, mode in ((self.path.parent, 0o700), (self.path, 0o600), (pathlib.Path(str(self.path) + "-wal"), 0o600), (pathlib.Path(str(self.path) + "-shm"), 0o600)):
            try:
                os.chmod(path, mode)
                if self.owner_uid is not None or self.owner_gid is not None:
                    os.chown(path, -1 if self.owner_uid is None else self.owner_uid, -1 if self.owner_gid is None else self.owner_gid)
            except FileNotFoundError:
                pass

    def add_case_event(self, connection, case_id, event_type, actor, detail, metadata=None):
        connection.execute(
            "insert into case_events(case_id,event_type,actor,detail,created_at,metadata) values(?,?,?,?,?,?)",
            (case_id, _clean(event_type, 80), _clean(actor, 128) or "system", _clean(detail, 4000), utcnow(), _json(metadata)),
        )

    def create_case(self, body, actor):
        severity = _clean(body.get("severity") or "medium", 16).lower()
        if severity not in CASE_SEVERITIES:
            raise ValueError("invalid case severity")
        summary = _clean(body.get("summary"), 500)
        if not summary:
            raise ValueError("case summary is required")
        case_id = str(uuid.uuid4())
        now = utcnow()
        account_id = body.get("accountId", body.get("account_id"))
        account_id = _int(account_id, "account id", 1) if account_id not in (None, "") else None
        row = (
            case_id, account_id, _clean(body.get("characterName"), 200), _clean(body.get("funcomId"), 200),
            _clean(body.get("platformId"), 200), _clean(body.get("category") or "conduct", 80), severity,
            "open", summary, _clean(actor, 128) or "operator", _clean(body.get("assignedTo"), 128),
            now, now, _json(body.get("metadata")),
        )
        with self.transaction() as connection:
            connection.execute("insert into cases(id,account_id,character_name,funcom_id,platform_id,category,severity,status,summary,opened_by,assigned_to,created_at,updated_at,metadata) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            self.add_case_event(connection, case_id, "opened", actor, summary, body.get("metadata"))
        return self.case(case_id)

    def case(self, case_id):
        with contextlib.closing(self._connect()) as connection:
            case = _row(connection.execute("select * from cases where id=?", (_clean(case_id, 64),)).fetchone())
            if not case:
                raise ValueError("moderation case not found")
            case["events"] = [_row(row) for row in connection.execute("select * from case_events where case_id=? order by id desc limit 500", (case["id"],))]
            case["bans"] = [_row(row) for row in connection.execute("select * from bans where case_id=? order by created_at desc", (case["id"],))]
            return case

    def update_case(self, case_id, body, actor):
        status = _clean(body.get("status"), 20).lower()
        if status and status not in CASE_STATUSES:
            raise ValueError("invalid case status")
        with self.transaction() as connection:
            current = connection.execute("select * from cases where id=?", (_clean(case_id, 64),)).fetchone()
            if not current:
                raise ValueError("moderation case not found")
            new_status = status or current["status"]
            assigned = _clean(body.get("assignedTo"), 128) if "assignedTo" in body else current["assigned_to"]
            summary = _clean(body.get("summary"), 500) if "summary" in body else current["summary"]
            closed_at = utcnow() if new_status == "closed" and current["status"] != "closed" else None if new_status != "closed" else current["closed_at"]
            connection.execute("update cases set status=?,assigned_to=?,summary=?,updated_at=?,closed_at=? where id=?", (new_status, assigned, summary, utcnow(), closed_at, case_id))
            self.add_case_event(connection, case_id, "updated", actor, _clean(body.get("note"), 4000) or f"status={new_status}", {"status": new_status, "assignedTo": assigned})
        return self.case(case_id)

    def add_note(self, case_id, note, actor, metadata=None):
        note = _clean(note, 4000)
        if not note:
            raise ValueError("case note is required")
        with self.transaction() as connection:
            if not connection.execute("select 1 from cases where id=?", (case_id,)).fetchone():
                raise ValueError("moderation case not found")
            self.add_case_event(connection, case_id, "note", actor, note, metadata)
            connection.execute("update cases set updated_at=? where id=?", (utcnow(), case_id))
        return self.case(case_id)

    def ban(self, case_id, body, actor):
        case = self.case(case_id)
        account_id = body.get("accountId", case.get("account_id"))
        account_id = _int(account_id, "account id", 1) if account_id not in (None, "") else None
        funcom_id = _clean(body.get("funcomId", case.get("funcom_id")), 200)
        platform_id = _clean(body.get("platformId", case.get("platform_id")), 200)
        if not any((account_id, funcom_id, platform_id)):
            raise ValueError("ban requires an account, Funcom, or platform identity")
        reason = _clean(body.get("reason") or case["summary"], 1000)
        duration_hours = body.get("durationHours")
        expires_at = None
        if duration_hours not in (None, "", 0, "0"):
            hours = _int(duration_hours, "duration hours", 1, 24 * 3650)
            expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)).isoformat()
        ban_id = str(uuid.uuid4())
        now = utcnow()
        with self.transaction() as connection:
            connection.execute("insert into bans(id,case_id,account_id,funcom_id,platform_id,reason,starts_at,expires_at,active,created_by,created_at) values(?,?,?,?,?,?,?,?,1,?,?)", (ban_id, case_id, account_id, funcom_id, platform_id, reason, now, expires_at, _clean(actor, 128) or "operator", now))
            connection.execute("update cases set status='actioned',updated_at=? where id=?", (now, case_id))
            self.add_case_event(connection, case_id, "ban-created", actor, reason, {"banId": ban_id, "expiresAt": expires_at})
        return {"ok": True, "ban": self.active_ban(account_id, funcom_id, platform_id), "case": self.case(case_id)}

    def unban(self, ban_id, actor, reason):
        reason = _clean(reason, 1000) or "revoked by operator"
        with self.transaction() as connection:
            ban = connection.execute("select * from bans where id=?", (_clean(ban_id, 64),)).fetchone()
            if not ban:
                raise ValueError("ban not found")
            if ban["active"]:
                connection.execute("update bans set active=0,revoked_by=?,revoked_at=?,revoke_reason=? where id=?", (_clean(actor, 128) or "operator", utcnow(), reason, ban_id))
                self.add_case_event(connection, ban["case_id"], "ban-revoked", actor, reason, {"banId": ban_id})
                connection.execute("update cases set updated_at=? where id=?", (utcnow(), ban["case_id"]))
        return {"ok": True, "banId": ban_id, "idempotent": not bool(ban["active"])}

    def active_ban(self, account_id=None, funcom_id="", platform_id="", now=None):
        now = now or utcnow()
        clauses, values = [], [now]
        if account_id not in (None, ""):
            clauses.append("account_id=?")
            values.append(int(account_id))
        if funcom_id:
            clauses.append("funcom_id=?")
            values.append(str(funcom_id))
        if platform_id:
            clauses.append("platform_id=?")
            values.append(str(platform_id))
        if not clauses:
            return None
        sql = f"select * from bans where active=1 and (expires_at is null or expires_at>?) and ({' or '.join(clauses)}) order by created_at desc limit 1"
        with contextlib.closing(self._connect()) as connection:
            return _row(connection.execute(sql, values).fetchone())

    def expire_bans(self):
        now = utcnow()
        with self.transaction() as connection:
            rows = list(connection.execute("select id,case_id from bans where active=1 and expires_at is not null and expires_at<=?", (now,)))
            for row in rows:
                connection.execute("update bans set active=0,revoked_by='system',revoked_at=?,revoke_reason='expired' where id=?", (now, row["id"]))
                self.add_case_event(connection, row["case_id"], "ban-expired", "system", "temporary ban expired", {"banId": row["id"]})
        return len(rows)

    def set_allowlist(self, identity_type, identity_value, label, actor, *, remove=False, expires_at=None):
        identity_type = _clean(identity_type, 16).lower()
        identity_value = _clean(identity_value, 200)
        if identity_type not in IDENTITY_TYPES or not identity_value:
            raise ValueError("allowlist identity type/value is invalid")
        with self.transaction() as connection:
            if remove:
                changed = connection.execute("delete from allowlist where identity_type=? and identity_value=?", (identity_type, identity_value)).rowcount
            else:
                connection.execute("insert into allowlist(identity_type,identity_value,label,added_by,created_at,expires_at) values(?,?,?,?,?,?) on conflict(identity_type,identity_value) do update set label=excluded.label,added_by=excluded.added_by,expires_at=excluded.expires_at", (identity_type, identity_value, _clean(label, 200), _clean(actor, 128) or "operator", utcnow(), expires_at or None))
                changed = 1
        return {"ok": True, "removed": remove, "changed": bool(changed)}

    def set_allowlist_enforcement(self, enabled):
        with self.transaction() as connection:
            connection.execute("insert into settings(key,value,updated_at) values('allowlist_enforcement',?,?) on conflict(key) do update set value=excluded.value,updated_at=excluded.updated_at", ("true" if enabled else "false", utcnow()))
        return {"ok": True, "allowlistEnforcement": bool(enabled)}

    def allowlisted(self, account_id=None, funcom_id="", platform_id="", now=None):
        now = now or utcnow()
        identities = [("account", str(account_id))] if account_id not in (None, "") else []
        identities += [("funcom", str(funcom_id))] if funcom_id else []
        identities += [("platform", str(platform_id))] if platform_id else []
        with contextlib.closing(self._connect()) as connection:
            for kind, value in identities:
                if connection.execute("select 1 from allowlist where identity_type=? and identity_value=? and (expires_at is null or expires_at>?)", (kind, value, now)).fetchone():
                    return True
        return False

    def allowlist_enforcement_enabled(self):
        with contextlib.closing(self._connect()) as connection:
            row = connection.execute("select value from settings where key='allowlist_enforcement'").fetchone()
            return bool(row and str(row["value"]).lower() == "true")

    def record_presence(self, players, *, cell_size=25000, observed_at=None):
        observed_at = observed_at or utcnow()
        moment = datetime.datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        day, hour = moment.date().isoformat(), moment.hour
        cell_size = _int(cell_size, "heatmap cell size", 1000, 1000000)
        online_ids = {int(player["account_id"]) for player in players}
        with self.transaction() as connection:
            open_rows = list(connection.execute("select id,account_id from presence_sessions where ended_at is null"))
            for row in open_rows:
                if int(row["account_id"]) not in online_ids:
                    connection.execute("update presence_sessions set ended_at=?,last_seen_at=? where id=?", (observed_at, observed_at, row["id"]))
            for player in players:
                account_id = int(player["account_id"])
                current = connection.execute("select id from presence_sessions where account_id=? and ended_at is null", (account_id,)).fetchone()
                session_id = current["id"] if current else str(uuid.uuid4())
                map_name = _clean(player.get("map") or player.get("actor_map") or player.get("farm_map") or "unknown", 120)
                if current:
                    connection.execute("update presence_sessions set character_name=?,funcom_id=?,platform_id=?,last_seen_at=?,map=?,partition_id=?,samples=samples+1 where id=?", (_clean(player.get("character_name"), 200), _clean(player.get("funcom_id"), 200), _clean(player.get("platform_id"), 200), observed_at, map_name, _clean(player.get("partition_id"), 200), session_id))
                else:
                    connection.execute("insert into presence_sessions(id,account_id,character_name,funcom_id,platform_id,started_at,last_seen_at,map,partition_id,samples) values(?,?,?,?,?,?,?,?,?,1)", (session_id, account_id, _clean(player.get("character_name"), 200), _clean(player.get("funcom_id"), 200), _clean(player.get("platform_id"), 200), observed_at, observed_at, map_name, _clean(player.get("partition_id"), 200)))
                try:
                    x, y = float(player.get("x")), float(player.get("y"))
                except (TypeError, ValueError):
                    continue
                if not (math.isfinite(x) and math.isfinite(y)):
                    continue
                cell_x, cell_y = math.floor(x / cell_size), math.floor(y / cell_size)
                connection.execute("insert into heatmap_cells(day,hour,map,cell_x,cell_y,samples,first_seen_at,last_seen_at) values(?,?,?,?,?,1,?,?) on conflict(day,hour,map,cell_x,cell_y) do update set samples=samples+1,last_seen_at=excluded.last_seen_at", (day, hour, map_name, cell_x, cell_y, observed_at, observed_at))
        return {"ok": True, "online": len(players), "observedAt": observed_at, "cellSize": cell_size}

    def ingest_security(self, events):
        inserted = 0
        with self.transaction() as connection:
            for event in events:
                severity = _clean(event.get("severity") or "medium", 16).lower()
                if severity not in SECURITY_SEVERITIES:
                    severity = "medium"
                changed = connection.execute("insert into security_events(fingerprint,category,severity,source,account_id,summary,evidence,observed_at) values(?,?,?,?,?,?,?,?) on conflict(fingerprint) do nothing", (_clean(event.get("fingerprint"), 64), _clean(event.get("category"), 80), severity, _clean(event.get("source"), 80), event.get("accountId"), redact_security_text(event.get("summary")), _json(event.get("evidence")), event.get("observedAt") or utcnow())).rowcount
                inserted += changed
        return inserted

    def record_enforcement(self, ban_id, account_id, ok, detail):
        with self.transaction() as connection:
            connection.execute("insert into enforcement_events(ban_id,account_id,action,ok,detail,created_at) values(?,?,'native-kick',?,?,?)", (ban_id, int(account_id), 1 if ok else 0, redact_security_text(detail, 1000), utcnow()))
            ban = connection.execute("select case_id from bans where id=?", (ban_id,)).fetchone()
            if ban:
                self.add_case_event(connection, ban["case_id"], "enforcement", "system", "native KickPlayer published" if ok else "native KickPlayer publish failed", {"banId": ban_id, "accountId": int(account_id), "ok": bool(ok), "detail": redact_security_text(detail, 500)})

    def recently_enforced(self, ban_id, account_id, cooldown_seconds):
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=max(1, int(cooldown_seconds)))).isoformat()
        with contextlib.closing(self._connect()) as connection:
            return bool(connection.execute("select 1 from enforcement_events where ban_id=? and account_id=? and created_at>=? order by id desc limit 1", (ban_id, int(account_id), cutoff)).fetchone())

    def record_policy_enforcement(self, account_id, ok, detail):
        with self.transaction() as connection:
            connection.execute("insert into policy_enforcement_events(policy,account_id,action,ok,detail,created_at) values('allowlist',?,'native-kick',?,?,?)", (int(account_id), 1 if ok else 0, redact_security_text(detail, 1000), utcnow()))

    def recently_policy_enforced(self, account_id, cooldown_seconds):
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=max(1, int(cooldown_seconds)))).isoformat()
        with contextlib.closing(self._connect()) as connection:
            return bool(connection.execute("select 1 from policy_enforcement_events where policy='allowlist' and account_id=? and created_at>=? order by id desc limit 1", (int(account_id), cutoff)).fetchone())

    def prune(self, retention_days):
        retention_days = _int(retention_days, "retention days", 1, 3650)
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=retention_days)).isoformat()
        cutoff_day = cutoff[:10]
        with self.transaction() as connection:
            security = connection.execute("delete from security_events where observed_at<?", (cutoff,)).rowcount
            sessions = connection.execute("delete from presence_sessions where ended_at is not null and ended_at<?", (cutoff,)).rowcount
            heatmap = connection.execute("delete from heatmap_cells where day<?", (cutoff_day,)).rowcount
            enforcement = connection.execute("delete from enforcement_events where created_at<?", (cutoff,)).rowcount
            policy_enforcement = connection.execute("delete from policy_enforcement_events where created_at<?", (cutoff,)).rowcount
        return {"securityEvents": security, "sessions": sessions, "heatmapCells": heatmap, "enforcementEvents": enforcement, "policyEnforcementEvents": policy_enforcement}

    def status(self, *, account_id=None, limit=200):
        limit = _int(limit, "limit", 1, 1000)
        now = utcnow()
        with contextlib.closing(self._connect()) as connection:
            settings = {row["key"]: row["value"] for row in connection.execute("select key,value from settings")}
            cases = [_row(row) for row in connection.execute("select * from cases where (? is null or account_id=?) order by updated_at desc limit ?", (account_id, account_id, limit))]
            bans = [_row(row) for row in connection.execute("select * from bans where (? is null or account_id=?) order by created_at desc limit ?", (account_id, account_id, limit))]
            allowlist = [_row(row) for row in connection.execute("select * from allowlist where expires_at is null or expires_at>? order by created_at desc limit ?", (now, limit))]
            sessions = [_row(row) for row in connection.execute("select * from presence_sessions where (? is null or account_id=?) order by started_at desc limit ?", (account_id, account_id, limit))]
            heatmap = [_row(row) for row in connection.execute("select * from heatmap_cells order by day desc,hour desc,samples desc limit ?", (limit,))]
            security = [_row(row) for row in connection.execute("select * from security_events order by observed_at desc limit ?", (limit,))]
            enforcement = [_row(row) for row in connection.execute("select * from enforcement_events order by created_at desc limit ?", (limit,))]
            policy_enforcement = [_row(row) for row in connection.execute("select * from policy_enforcement_events order by created_at desc limit ?", (limit,))]
            case_events = [_row(row) for row in connection.execute("select * from case_events order by id desc limit ?", (limit,))]
            counts = _row(connection.execute("select (select count(*) from cases where status<>'closed') as open_cases,(select count(*) from bans where active=1 and (expires_at is null or expires_at>?)) as active_bans,(select count(*) from presence_sessions where ended_at is null) as online_sessions,(select count(*) from security_events) as security_events", (now,)).fetchone())
        return {"schemaVersion": SCHEMA_VERSION, "settings": settings, "counts": counts, "cases": cases, "caseEvents": case_events, "bans": bans, "allowlist": allowlist, "sessions": sessions, "heatmap": heatmap, "securityEvents": security, "enforcementEvents": enforcement, "policyEnforcementEvents": policy_enforcement}
