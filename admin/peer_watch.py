#!/usr/bin/env python3
"""Bounded, durable revision-drift watcher for the pinned DASH peer catalogue."""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


SCHEMA = "dash-peer-watch/v1"
PIN_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
ROW_PATTERN = re.compile(
    r"^\| \[([^\]]{1,200})\]\((https://[^)]+)\) \| `([0-9a-f]{40})` \|",
)
SECTION_PATTERN = re.compile(r"(?ms)^## Peer catalogue\s*$\n(.*?)(?=^## )")
ALLOWED_HOSTS = {"github.com", "git.unityailab.com"}
MAX_PEERS = 100
MAX_RESPONSE_BYTES = 1024 * 1024
STATES = {"current", "drifted", "error"}


def iso(epoch=None):
    return datetime.datetime.fromtimestamp(
        float(time.time() if epoch is None else epoch), datetime.timezone.utc,
    ).isoformat().replace("+00:00", "Z")


def catalog_sha256(peers):
    value = [{key: row[key] for key in ("id", "name", "url", "pinned", "provider")} for row in peers]
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_catalog(path):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("peer catalogue must be a regular non-symlink file")
    text = path.read_text(encoding="utf-8")
    section_match = SECTION_PATTERN.search(text)
    if section_match is None:
        raise ValueError("peer catalogue section is missing")
    rows = [line for line in section_match.group(1).splitlines() if line.startswith("| [")]
    if not rows:
        raise ValueError("peer catalogue contains no pinned primary repositories")
    peers = []
    seen_ids = set()
    seen_urls = set()
    for line in rows:
        match = ROW_PATTERN.match(line)
        if match is None:
            raise ValueError(f"peer catalogue row is malformed: {line[:200]}")
        name, raw_url, pinned = match.groups()
        parsed = urllib.parse.urlsplit(raw_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
            raise ValueError(f"peer URL is outside the fixed HTTPS host allowlist: {raw_url}")
        segments = [urllib.parse.unquote(value) for value in parsed.path.strip("/").split("/") if value]
        if len(segments) != 2 or any(not SEGMENT_PATTERN.fullmatch(value) for value in segments):
            raise ValueError(f"peer URL must contain exactly an owner and repository: {raw_url}")
        owner, repository = segments
        peer_id = f"{owner}/{repository}"
        normalized_url = f"https://{parsed.hostname}/{owner}/{repository}"
        if peer_id.lower() in seen_ids or normalized_url.lower() in seen_urls:
            raise ValueError(f"duplicate peer catalogue row: {peer_id}")
        if not PIN_PATTERN.fullmatch(pinned):
            raise ValueError(f"peer pin is invalid: {peer_id}")
        seen_ids.add(peer_id.lower())
        seen_urls.add(normalized_url.lower())
        peers.append({
            "id": peer_id,
            "name": name,
            "url": normalized_url,
            "pinned": pinned,
            "provider": "github" if parsed.hostname == "github.com" else "forgejo",
        })
    if len(peers) > MAX_PEERS:
        raise ValueError(f"peer catalogue exceeds {MAX_PEERS} repositories")
    return peers


def api_url(peer):
    owner, repository = peer["id"].split("/", 1)
    if peer["provider"] == "github":
        return f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repository)}/commits?per_page=1"
    if peer["provider"] == "forgejo":
        return f"https://git.unityailab.com/api/v1/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repository)}/commits?limit=1"
    raise ValueError("unsupported peer provider")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "peer API redirects are disabled", headers, fp)


def http_json(url, headers, timeout, maximum=MAX_RESPONSE_BYTES):
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        payload = response.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("peer API response exceeds 1 MiB")
    return json.loads(payload.decode("utf-8"))


def fetch_head(peer, *, token=None, timeout=15, fetch_json=http_json):
    headers = {
        "Accept": "application/vnd.github+json" if peer["provider"] == "github" else "application/json",
        "User-Agent": "DASH-Peer-Watch/1",
    }
    if token and peer["provider"] == "github":
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    payload = fetch_json(api_url(peer), headers, max(1, min(int(timeout), 60)), MAX_RESPONSE_BYTES)
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError("peer API response contains no default-branch commit")
    head = str(payload[0].get("sha") or payload[0].get("id") or "").lower()
    if not PIN_PATTERN.fullmatch(head):
        raise ValueError("peer API returned an invalid commit identity")
    return head


def collect(peers, *, token=None, timeout=15, fetch_json=http_json, now=None):
    observed_at = float(time.time() if now is None else now)
    result = []
    for peer in peers:
        row = {**peer, "observedAt": iso(observed_at)}
        try:
            row["head"] = fetch_head(peer, token=token, timeout=timeout, fetch_json=fetch_json)
            row["state"] = "current" if row["head"] == peer["pinned"] else "drifted"
            row["error"] = None
        except Exception as exc:
            row.update({"head": None, "state": "error", "error": str(exc)[:1000]})
        result.append(row)
    return result


def valid_peer_record(row):
    state = str(row["state"] or "")
    pinned = str(row["pinned"] or "")
    head = str(row["head"] or "")
    error = str(row["error"] or "")
    if state not in STATES or not PIN_PATTERN.fullmatch(pinned):
        return False
    if state == "current":
        return head == pinned and not error
    if state == "drifted":
        return bool(PIN_PATTERN.fullmatch(head) and head != pinned and not error)
    return not head and bool(error)


def verify_database(database):
    path = pathlib.Path(database)
    if path.is_symlink() or not path.is_file():
        return {"ok": False, "integrity": None, "schemaVersion": None, "peers": 0}
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        integrity = db.execute("pragma integrity_check").fetchone()[0]
        tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
        required = {"peers", "transitions", "metadata"}
        if not required <= tables:
            return {"ok": False, "integrity": integrity, "schemaVersion": None, "peers": 0}
        metadata = {row["key"]: row["value"] for row in db.execute("select key,value from metadata")}
        rows = list(db.execute("select pinned,head,state,error from peers"))
        schema = metadata.get("schemaVersion")
        try:
            last_success = float(metadata.get("lastSuccessAt", "0") or 0)
        except ValueError:
            last_success = 0
        valid = (
            integrity == "ok" and schema == SCHEMA and 0 < len(rows) <= MAX_PEERS
            and SHA256_PATTERN.fullmatch(metadata.get("catalogSha256", "")) is not None
            and last_success > 0 and all(valid_peer_record(row) for row in rows)
        )
        return {"ok": valid, "integrity": integrity, "schemaVersion": schema, "peers": len(rows)}
    finally:
        db.close()


class Store:
    def __init__(self, database, *, history_limit=5000, owner_uid=None, owner_gid=None):
        self.database = pathlib.Path(database)
        self.history_limit = max(100, min(int(history_limit), 50000))
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None
        self._lock = threading.RLock()

    def _secure(self):
        if self.database.is_symlink():
            raise ValueError("peer-watch database must not be a symlink")
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database.parent.chmod(0o700)
        artifacts = (self.database, pathlib.Path(str(self.database) + "-wal"), pathlib.Path(str(self.database) + "-shm"))
        for path in artifacts:
            if path.is_symlink():
                raise ValueError("peer-watch database artifacts must not be symlinks")
            if path.exists():
                path.chmod(0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(self.database.parent, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)
            for path in artifacts:
                if path.exists():
                    os.chown(path, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)

    def connect(self):
        self._secure()
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("pragma journal_mode=WAL")
        db.execute("pragma foreign_keys=ON")
        self._secure()
        return db

    @contextlib.contextmanager
    def transaction(self):
        db = self.connect()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
            self._secure()

    def initialize(self):
        with self._lock, self.transaction() as db:
            db.executescript("""
                create table if not exists peers (
                    id text primary key,
                    name text not null,
                    url text not null,
                    provider text not null,
                    pinned text not null,
                    head text,
                    state text not null,
                    first_seen real not null,
                    last_observed real not null,
                    first_drift_at real,
                    last_changed_at real not null,
                    error text
                );
                create table if not exists transitions (
                    id integer primary key autoincrement,
                    peer_id text not null,
                    transition text not null,
                    previous_state text,
                    state text not null,
                    pinned text not null,
                    head text,
                    occurred_at real not null,
                    error text
                );
                create index if not exists peer_transitions_recent on transitions(occurred_at desc,id desc);
                create table if not exists metadata (key text primary key,value text not null);
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

    def record_poll_error(self, error, *, now=None):
        now = float(time.time() if now is None else now)
        with self._lock, self.transaction() as db:
            metadata = self._metadata(db)
            failures = int(metadata.get("consecutiveFailures", "0") or 0) + 1
            self._set_metadata(db, lastPollAt=now, lastError=str(error)[:1000], lastErrorAt=now, consecutiveFailures=failures)

    def sync(self, peers, observations, *, now=None):
        now = float(time.time() if now is None else now)
        expected = {row["id"]: row for row in peers}
        incoming = {row["id"]: row for row in observations}
        if set(expected) != set(incoming) or len(incoming) != len(observations):
            raise ValueError("peer-watch observations do not exactly match the current catalogue")
        transitions = []
        with self._lock, self.transaction() as db:
            existing = {row["id"]: dict(row) for row in db.execute("select * from peers")}
            for peer_id in sorted(expected):
                peer = expected[peer_id]
                observed = incoming[peer_id]
                state = str(observed.get("state") or "")
                if state not in STATES:
                    raise ValueError("peer-watch observation state is invalid")
                head = observed.get("head")
                if head is not None and not PIN_PATTERN.fullmatch(str(head)):
                    raise ValueError("peer-watch observation head is invalid")
                prior = existing.get(peer_id)
                first_seen = float(prior["first_seen"]) if prior else now
                changed = not prior or prior["state"] != state or prior["pinned"] != peer["pinned"] or prior["head"] != head
                last_changed = now if changed else float(prior["last_changed_at"])
                first_drift = now if state == "drifted" and (not prior or prior["state"] != "drifted") else (prior["first_drift_at"] if prior and state == "drifted" else None)
                db.execute("""
                    insert into peers(id,name,url,provider,pinned,head,state,first_seen,last_observed,first_drift_at,last_changed_at,error)
                    values(?,?,?,?,?,?,?,?,?,?,?,?)
                    on conflict(id) do update set name=excluded.name,url=excluded.url,provider=excluded.provider,pinned=excluded.pinned,
                      head=excluded.head,state=excluded.state,last_observed=excluded.last_observed,
                      first_drift_at=excluded.first_drift_at,last_changed_at=excluded.last_changed_at,error=excluded.error
                """, (
                    peer_id, peer["name"], peer["url"], peer["provider"], peer["pinned"], head, state,
                    first_seen, now, first_drift, last_changed, observed.get("error"),
                ))
                if changed:
                    if prior is None:
                        transition = "discovered"
                    elif prior["pinned"] != peer["pinned"] and state == "current":
                        transition = "pin-updated"
                    elif state == "drifted":
                        transition = "drift-detected"
                    elif state == "error":
                        transition = "collection-error"
                    else:
                        transition = "current"
                    cursor = db.execute(
                        "insert into transitions(peer_id,transition,previous_state,state,pinned,head,occurred_at,error) values(?,?,?,?,?,?,?,?)",
                        (peer_id, transition, prior["state"] if prior else None, state, peer["pinned"], head, now, observed.get("error")),
                    )
                    transitions.append({"id": int(cursor.lastrowid), "peerId": peer_id, "transition": transition, "state": state})
            for peer_id in set(existing) - set(expected):
                db.execute("delete from peers where id=?", (peer_id,))
                cursor = db.execute(
                    "insert into transitions(peer_id,transition,previous_state,state,pinned,head,occurred_at,error) values(?,?,?,?,?,?,?,?)",
                    (peer_id, "catalog-removed", existing[peer_id]["state"], "current", existing[peer_id]["pinned"], existing[peer_id]["head"], now, None),
                )
                transitions.append({"id": int(cursor.lastrowid), "peerId": peer_id, "transition": "catalog-removed", "state": "current"})
            db.execute("delete from transitions where id not in (select id from transitions order by occurred_at desc,id desc limit ?)", (self.history_limit,))
            self._set_metadata(
                db, schemaVersion=SCHEMA, catalogSha256=catalog_sha256(peers), lastPollAt=now,
                lastSuccessAt=now, lastError="", consecutiveFailures=0,
            )
        return {"ok": True, "observed": len(observations), "transitions": transitions}

    def status(self, *, limit=200, now=None):
        now = float(time.time() if now is None else now)
        limit = max(1, min(int(limit), 1000))
        with self._lock, self.transaction() as db:
            integrity = db.execute("pragma integrity_check").fetchone()[0]
            metadata = self._metadata(db)
            state_counts = {
                row["state"]: int(row["total"])
                for row in db.execute("select state,count(*) as total from peers group by state")
            }
            peer_count = int(db.execute("select count(*) from peers").fetchone()[0])
            peers = [dict(row) for row in db.execute("select * from peers order by case state when 'drifted' then 0 when 'error' then 1 else 2 end,name limit ?", (limit,))]
            history = [dict(row) for row in db.execute("select * from transitions order by occurred_at desc,id desc limit ?", (limit,))]
            transition_count = int(db.execute("select count(*) from transitions").fetchone()[0])
            semantic_rows = list(db.execute("select pinned,head,state,error from peers"))
        for row in peers:
            row.update({
                "peerId": row.pop("id"), "observedHead": row.pop("head"),
                "firstSeenAt": iso(row.pop("first_seen")), "lastObservedAt": iso(row.pop("last_observed")),
                "firstDriftAt": iso(row.pop("first_drift_at")) if row.get("first_drift_at") is not None else None,
                "lastChangedAt": iso(row.pop("last_changed_at")),
            })
            row.pop("first_drift_at", None)
        for row in history:
            row["occurredAt"] = iso(row.pop("occurred_at"))
            row["peerId"] = row.pop("peer_id")
            row["previousState"] = row.pop("previous_state")
        last_success = float(metadata.get("lastSuccessAt", "0") or 0)
        summary = {state: state_counts.get(state, 0) for state in STATES}
        summary.update({"total": peer_count, "transitions": transition_count})
        return {
            "ok": bool(
                integrity == "ok" and metadata.get("schemaVersion") == SCHEMA
                and 0 < peer_count <= MAX_PEERS
                and SHA256_PATTERN.fullmatch(metadata.get("catalogSha256", ""))
                and last_success > 0 and all(valid_peer_record(row) for row in semantic_rows)
            ),
            "schemaVersion": SCHEMA,
            "catalogSha256": metadata.get("catalogSha256"),
            "summary": summary,
            "peers": peers,
            "history": history,
            "collector": {
                "lastPollAt": iso(float(metadata["lastPollAt"])) if metadata.get("lastPollAt") else None,
                "lastSuccessAt": iso(last_success) if last_success else None,
                "lastSuccessTimestamp": last_success,
                "ageSeconds": max(0, round(now - last_success, 3)) if last_success else None,
                "lastError": metadata.get("lastError") or None,
                "consecutiveFailures": int(metadata.get("consecutiveFailures", "0") or 0),
            },
        }

    def prometheus(self, *, enabled=True, worker_running=False, stale_after_seconds=86400, now=None):
        status = self.status(limit=MAX_PEERS, now=now)
        summary = status["summary"]
        collector = status["collector"]
        age = collector.get("ageSeconds")
        collector_up = status["ok"] and age is not None and age <= float(stale_after_seconds)
        values = {
            "dash_peer_watch_enabled": int(bool(enabled)),
            "dash_peer_watch_collector_up": int(collector_up),
            "dash_peer_watch_worker_running": int(bool(worker_running)),
            "dash_peer_watch_peers_total": summary["total"],
            "dash_peer_watch_current": summary["current"],
            "dash_peer_watch_drifted": summary["drifted"],
            "dash_peer_watch_errors": summary["error"],
            "dash_peer_watch_transitions_total": summary["transitions"],
            "dash_peer_watch_last_success_timestamp_seconds": collector.get("lastSuccessTimestamp") or 0,
            "dash_peer_watch_age_seconds": age or 0,
        }
        return "".join(f"{key} {value}\n" for key, value in values.items())
