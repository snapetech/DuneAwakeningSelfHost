"""Isolated community credits, shop, delivery, and reward-track state.

This module never writes the Dune database.  A caller may claim queued deliveries
and pass them to a separately gated game-delivery adapter.  All money, stock, and
idempotency changes live in a dedicated SQLite database under backups/.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import sqlite3
import threading
import uuid


SCHEMA_VERSION = 2
MAX_LEDGER_AMOUNT = 1_000_000_000
MAX_PURCHASE_QUANTITY = 100
MAX_REWARDS = 100
ZERO_HASH = "0" * 64


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _positive_int(value, field, maximum=MAX_LEDGER_AMOUNT):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed <= 0 or parsed > maximum:
        raise ValueError(f"{field} must be between 1 and {maximum}")
    return parsed


def _identifier(value, field, maximum=128):
    text = str(value or "").strip()
    if not text or len(text) > maximum or any(ord(ch) < 32 for ch in text):
        raise ValueError(f"{field} must be 1-{maximum} printable characters")
    return text


def _rewards(value):
    if not isinstance(value, list) or not value or len(value) > MAX_REWARDS:
        raise ValueError(f"rewards must contain 1-{MAX_REWARDS} entries")
    normalized = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("each reward must be an object")
        kind = str(row.get("type") or "item").strip().lower()
        if kind != "item":
            raise ValueError("only item delivery is currently supported")
        template_id = _identifier(row.get("templateId", row.get("template_id")), "templateId", 256)
        count = _positive_int(row.get("count", row.get("stackSize", 1)), "count", 1_000_000)
        quality = int(row.get("qualityLevel", row.get("quality_level", 0)))
        if quality < 0 or quality > 100:
            raise ValueError("qualityLevel must be between 0 and 100")
        normalized.append({"type": "item", "templateId": template_id, "count": count, "qualityLevel": quality})
    return normalized


def _engagement_reward(value):
    if not isinstance(value, dict):
        raise ValueError("engagement reward must be an object")
    credits = int(value.get("credits", 0) or 0)
    if credits < 0 or credits > MAX_LEDGER_AMOUNT:
        raise ValueError("engagement reward credits are outside the supported range")
    items = value.get("items") or []
    if items:
        items = _rewards(items)
    track = value.get("track") or {}
    if not isinstance(track, dict):
        raise ValueError("engagement reward track must be an object")
    track_id = str(track.get("id") or "").strip()
    track_xp = int(track.get("xp", 0) or 0)
    if track_xp < 0 or track_xp > MAX_LEDGER_AMOUNT:
        raise ValueError("engagement reward track XP is outside the supported range")
    if bool(track_id) != bool(track_xp):
        raise ValueError("engagement reward track requires both id and positive xp")
    if track_id:
        track_id = _identifier(track_id, "engagement reward track id", 64)
    if not credits and not items and not track_xp:
        raise ValueError("engagement reward must grant credits, track XP, or items")
    return {
        "credits": credits,
        "items": items,
        "track": {"id": track_id, "xp": track_xp} if track_id else None,
    }


def engagement_config(config):
    raw = config.get("engagementRewards") or {}
    if not isinstance(raw, dict):
        raise ValueError("engagementRewards must be an object")
    result = {
        "enabled": bool(raw.get("enabled", False)),
        "maxObservationGapSeconds": max(1, min(int(raw.get("maxObservationGapSeconds", 120)), 3600)),
        "minimumMovementDistance": max(0.0, min(float(raw.get("minimumMovementDistance", 100.0)), 1_000_000.0)),
        "coordinatePrecision": max(1.0, min(float(raw.get("coordinatePrecision", 10.0)), 100_000.0)),
        "movementGraceSeconds": max(0, min(int(raw.get("movementGraceSeconds", 120)), 3600)),
        "hourly": {"enabled": False, "intervalSeconds": 3600, "maxRewardsPerSession": 0, "tiers": []},
        "daily": {"enabled": False, "repeatLast": False, "tiers": []},
        "weekly": {"enabled": False, "thresholds": []},
    }
    hourly = raw.get("hourly") or {}
    if not isinstance(hourly, dict):
        raise ValueError("engagementRewards.hourly must be an object")
    hourly_tiers = []
    previous = 0
    for row in hourly.get("tiers") or []:
        if not isinstance(row, dict):
            raise ValueError("hourly reward tiers must be objects")
        from_hour = _positive_int(row.get("fromHour"), "hourly fromHour", 1000)
        if from_hour <= previous:
            raise ValueError("hourly reward tiers must have increasing fromHour values")
        previous = from_hour
        hourly_tiers.append({"fromHour": from_hour, "reward": _engagement_reward(row.get("reward"))})
    result["hourly"] = {
        "enabled": bool(hourly.get("enabled", False)),
        "intervalSeconds": _positive_int(hourly.get("intervalSeconds", 3600), "hourly intervalSeconds", 86400),
        "maxRewardsPerSession": max(0, min(int(hourly.get("maxRewardsPerSession", 8)), 1000)),
        "tiers": hourly_tiers,
    }
    daily = raw.get("daily") or {}
    if not isinstance(daily, dict):
        raise ValueError("engagementRewards.daily must be an object")
    daily_tiers = []
    previous = 0
    for row in daily.get("tiers") or []:
        if not isinstance(row, dict):
            raise ValueError("daily reward tiers must be objects")
        day = _positive_int(row.get("day"), "daily day", 10000)
        if day <= previous:
            raise ValueError("daily reward tiers must have increasing day values")
        previous = day
        daily_tiers.append({"day": day, "reward": _engagement_reward(row.get("reward"))})
    result["daily"] = {
        "enabled": bool(daily.get("enabled", False)),
        "repeatLast": bool(daily.get("repeatLast", False)),
        "tiers": daily_tiers,
    }
    weekly = raw.get("weekly") or {}
    if not isinstance(weekly, dict):
        raise ValueError("engagementRewards.weekly must be an object")
    weekly_thresholds = []
    previous = 0
    for row in weekly.get("thresholds") or []:
        if not isinstance(row, dict):
            raise ValueError("weekly reward thresholds must be objects")
        active_seconds = _positive_int(row.get("activeSeconds"), "weekly activeSeconds", 604800)
        if active_seconds <= previous:
            raise ValueError("weekly reward thresholds must have increasing activeSeconds values")
        previous = active_seconds
        weekly_thresholds.append({"activeSeconds": active_seconds, "reward": _engagement_reward(row.get("reward"))})
    result["weekly"] = {"enabled": bool(weekly.get("enabled", False)), "thresholds": weekly_thresholds}
    if result["hourly"]["enabled"] and not hourly_tiers:
        raise ValueError("enabled hourly engagement rewards require tiers")
    if result["daily"]["enabled"] and not daily_tiers:
        raise ValueError("enabled daily engagement rewards require tiers")
    if result["weekly"]["enabled"] and not weekly_thresholds:
        raise ValueError("enabled weekly engagement rewards require thresholds")
    return result


def load_config(path):
    path = pathlib.Path(path)
    if not path.exists():
        return {"version": 1, "enabled": False, "currency": {"name": "Community Credits", "symbol": "CC"}, "offers": [], "tracks": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or int(value.get("version", 0)) != 1:
        raise ValueError("community rewards config must be a version 1 object")
    if not isinstance(value.get("offers", []), list) or not isinstance(value.get("tracks", []), list):
        raise ValueError("offers and tracks must be arrays")
    engagement = engagement_config(value)
    configured_tracks = {
        str(row.get("id") or "").strip()
        for row in value.get("tracks", [])
        if isinstance(row, dict) and bool(row.get("enabled", True))
    }
    engagement_tracks = {
        row["reward"]["track"]["id"]
        for section in (engagement["hourly"].get("tiers", []), engagement["daily"].get("tiers", []), engagement["weekly"].get("thresholds", []))
        for row in section
        if row["reward"].get("track")
    }
    missing_tracks = sorted(engagement_tracks - configured_tracks)
    if missing_tracks:
        raise ValueError(f"engagement rewards reference unavailable tracks: {', '.join(missing_tracks)}")
    return value


def verify_webhook(secret, timestamp, raw_body, signature, now_epoch=None, tolerance_seconds=300):
    secret = str(secret or "").encode()
    timestamp = str(timestamp or "").strip()
    signature = str(signature or "").strip().lower()
    if signature.startswith("sha256="):
        signature = signature[7:]
    if not secret or not timestamp or len(signature) != 64:
        return False
    try:
        event_epoch = int(timestamp)
    except ValueError:
        return False
    current = int(dt.datetime.now(dt.timezone.utc).timestamp()) if now_epoch is None else int(now_epoch)
    if abs(current - event_epoch) > int(tolerance_seconds):
        return False
    expected = hmac.new(secret, timestamp.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class Store:
    def __init__(self, database_path, config_path, now=utc_now, owner_uid=None, owner_gid=None):
        self.database_path = pathlib.Path(database_path)
        self.config_path = pathlib.Path(config_path)
        self.now = now
        self.lock = threading.RLock()
        self.owner_uid = None if owner_uid in (None, "") else int(owner_uid)
        self.owner_gid = None if owner_gid in (None, "") else int(owner_gid)

    def _fix_permissions(self):
        paths = [self.database_path.parent, self.database_path]
        paths.extend(pathlib.Path(str(self.database_path) + suffix) for suffix in ("-wal", "-shm"))
        for path in paths:
            if not path.exists():
                continue
            try:
                os.chmod(path, 0o700 if path == self.database_path.parent else 0o600)
                if self.owner_uid is not None or self.owner_gid is not None:
                    os.chown(path, self.owner_uid if self.owner_uid is not None else -1, self.owner_gid if self.owner_gid is not None else -1)
            except OSError:
                pass

    def connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.database_path.parent, 0o700)
        except OSError:
            pass
        conn = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys=on")
        conn.execute("pragma busy_timeout=10000")
        conn.execute("pragma journal_mode=wal")
        conn.execute("pragma synchronous=full")
        return conn

    @contextlib.contextmanager
    def transaction(self):
        with self.lock:
            conn = self.connect()
            try:
                conn.execute("begin immediate")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def initialize(self):
        with self.transaction() as conn:
            conn.executescript("""
                create table if not exists metadata(key text primary key, value text not null);
                create table if not exists accounts(
                    dune_account_id integer primary key,
                    discord_user_id text unique,
                    linked_at text,
                    created_at text not null
                );
                create table if not exists link_codes(
                    code_hash text primary key,
                    dune_account_id integer not null references accounts(dune_account_id),
                    expires_at text not null,
                    used_at text,
                    created_at text not null
                );
                create table if not exists wallets(
                    dune_account_id integer primary key references accounts(dune_account_id),
                    balance integer not null default 0 check(balance >= 0),
                    updated_at text not null
                );
                create table if not exists ledger(
                    id text primary key,
                    dune_account_id integer not null references accounts(dune_account_id),
                    delta integer not null check(delta != 0),
                    balance_after integer not null check(balance_after >= 0),
                    kind text not null,
                    reference text not null unique,
                    metadata_json text not null,
                    previous_hash text not null,
                    entry_hash text not null unique,
                    created_at text not null
                );
                create trigger if not exists ledger_no_update before update on ledger begin select raise(abort, 'ledger is append-only'); end;
                create trigger if not exists ledger_no_delete before delete on ledger begin select raise(abort, 'ledger is append-only'); end;
                create table if not exists offers(
                    id text primary key,
                    version integer not null,
                    name text not null,
                    description text not null,
                    kind text not null,
                    price integer not null check(price >= 0),
                    stock integer check(stock is null or stock >= 0),
                    enabled integer not null,
                    rewards_json text not null,
                    updated_at text not null
                );
                create table if not exists purchases(
                    id text primary key,
                    dune_account_id integer not null references accounts(dune_account_id),
                    offer_id text not null references offers(id),
                    offer_version integer not null,
                    quantity integer not null,
                    total integer not null,
                    status text not null,
                    idempotency_key text not null,
                    error text,
                    created_at text not null,
                    updated_at text not null,
                    unique(dune_account_id, idempotency_key)
                );
                create table if not exists deliveries(
                    id text primary key,
                    source_type text not null,
                    source_id text not null unique,
                    dune_account_id integer not null references accounts(dune_account_id),
                    rewards_json text not null,
                    status text not null,
                    attempts integer not null default 0,
                    claim_token text,
                    claimed_at text,
                    delivered_at text,
                    receipt_json text,
                    error text,
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists webhook_receipts(
                    provider text not null,
                    event_id text not null,
                    payload_sha256 text not null,
                    dune_account_id integer not null,
                    amount integer not null,
                    ledger_id text not null,
                    created_at text not null,
                    primary key(provider,event_id)
                );
                create table if not exists playtime_checkpoints(
                    dune_account_id integer primary key references accounts(dune_account_id),
                    observed_at integer not null,
                    was_online integer not null,
                    remainder_seconds integer not null default 0,
                    credited_intervals integer not null default 0
                );
                create table if not exists engagement_checkpoints(
                    dune_account_id integer primary key references accounts(dune_account_id),
                    observed_at integer not null,
                    was_online integer not null,
                    map_name text,
                    partition_id integer,
                    x real,
                    y real,
                    z real,
                    last_movement_at integer,
                    session_started_at integer,
                    session_active_seconds integer not null default 0,
                    rewarded_hours integer not null default 0
                );
                create table if not exists engagement_days(
                    dune_account_id integer not null references accounts(dune_account_id),
                    day text not null,
                    active_seconds integer not null default 0,
                    streak integer not null default 0,
                    first_activity_at integer not null,
                    last_activity_at integer not null,
                    primary key(dune_account_id,day)
                );
                create table if not exists engagement_weeks(
                    dune_account_id integer not null references accounts(dune_account_id),
                    week text not null,
                    active_seconds integer not null default 0,
                    first_activity_at integer not null,
                    last_activity_at integer not null,
                    primary key(dune_account_id,week)
                );
                create table if not exists engagement_claims(
                    id text primary key,
                    dune_account_id integer not null references accounts(dune_account_id),
                    kind text not null,
                    period_key text not null,
                    tier integer not null,
                    reward_json text not null,
                    delivery_id text unique,
                    ledger_id text,
                    created_at text not null,
                    unique(dune_account_id,kind,period_key,tier)
                );
                create trigger if not exists engagement_claims_no_update before update on engagement_claims begin select raise(abort, 'engagement claims are append-only'); end;
                create trigger if not exists engagement_claims_no_delete before delete on engagement_claims begin select raise(abort, 'engagement claims are append-only'); end;
                create table if not exists tracks(
                    id text not null,
                    version integer not null,
                    name text not null,
                    enabled integer not null,
                    starts_at text,
                    ends_at text,
                    levels_json text not null,
                    updated_at text not null,
                    primary key(id,version)
                );
                create table if not exists track_progress(
                    dune_account_id integer not null references accounts(dune_account_id),
                    track_id text not null,
                    track_version integer not null,
                    xp integer not null default 0 check(xp >= 0),
                    updated_at text not null,
                    primary key(dune_account_id,track_id,track_version),
                    foreign key(track_id,track_version) references tracks(id,version)
                );
                create table if not exists track_claims(
                    dune_account_id integer not null,
                    track_id text not null,
                    track_version integer not null,
                    level integer not null,
                    delivery_id text not null unique,
                    claimed_at text not null,
                    primary key(dune_account_id,track_id,track_version,level)
                );
            """)
            conn.execute("insert or replace into metadata(key,value) values('schema_version',?)", (str(SCHEMA_VERSION),))
        try:
            os.chmod(self.database_path, 0o600)
        except OSError:
            pass
        self._fix_permissions()
        self.sync_config()
        result = self.status()
        self._fix_permissions()
        return result

    def _ensure_account(self, conn, dune_account_id):
        account_id = _positive_int(dune_account_id, "duneAccountId", 9_223_372_036_854_775_807)
        now = self.now()
        conn.execute("insert or ignore into accounts(dune_account_id,created_at) values(?,?)", (account_id, now))
        conn.execute("insert or ignore into wallets(dune_account_id,balance,updated_at) values(?,0,?)", (account_id, now))
        return account_id

    def sync_config(self):
        config = load_config(self.config_path)
        now = self.now()
        offer_ids = set()
        track_keys = set()
        with self.transaction() as conn:
            for raw in config.get("offers", []):
                if not isinstance(raw, dict):
                    raise ValueError("offer entries must be objects")
                offer_id = _identifier(raw.get("id"), "offer id", 64)
                offer_ids.add(offer_id)
                version = _positive_int(raw.get("version", 1), "offer version", 1_000_000)
                price = int(raw.get("price", 0))
                if price < 0 or price > MAX_LEDGER_AMOUNT:
                    raise ValueError("offer price is outside the supported range")
                stock = raw.get("stock")
                stock = None if stock in (None, "") else int(stock)
                if stock is not None and stock < 0:
                    raise ValueError("offer stock cannot be negative")
                rewards = _rewards(raw.get("rewards"))
                conn.execute("""insert into offers(id,version,name,description,kind,price,stock,enabled,rewards_json,updated_at)
                    values(?,?,?,?,?,?,?,?,?,?) on conflict(id) do update set
                    version=excluded.version,name=excluded.name,description=excluded.description,kind=excluded.kind,
                    price=excluded.price,stock=case when offers.version=excluded.version then offers.stock else excluded.stock end,
                    enabled=excluded.enabled,rewards_json=excluded.rewards_json,updated_at=excluded.updated_at""",
                    (offer_id, version, _identifier(raw.get("name", offer_id), "offer name", 128), str(raw.get("description") or "")[:1000],
                     str(raw.get("kind") or "item")[:32], price, stock, int(bool(raw.get("enabled", True))), canonical(rewards), now))
            for raw in config.get("tracks", []):
                if not isinstance(raw, dict):
                    raise ValueError("track entries must be objects")
                track_id = _identifier(raw.get("id"), "track id", 64)
                version = _positive_int(raw.get("version", 1), "track version", 1_000_000)
                levels = raw.get("levels")
                if not isinstance(levels, list) or not levels:
                    raise ValueError("track levels must be a non-empty array")
                normalized = []
                previous_xp = -1
                for index, level in enumerate(levels, 1):
                    if not isinstance(level, dict):
                        raise ValueError("track levels must be objects")
                    xp = int(level.get("xp", 0))
                    if xp <= previous_xp:
                        raise ValueError("track level XP thresholds must increase")
                    previous_xp = xp
                    normalized.append({"level": index, "xp": xp, "rewards": _rewards(level.get("rewards"))})
                track_keys.add((track_id, version))
                conn.execute("""insert into tracks(id,version,name,enabled,starts_at,ends_at,levels_json,updated_at)
                    values(?,?,?,?,?,?,?,?) on conflict(id,version) do update set name=excluded.name,enabled=excluded.enabled,
                    starts_at=excluded.starts_at,ends_at=excluded.ends_at,levels_json=excluded.levels_json,updated_at=excluded.updated_at""",
                    (track_id, version, _identifier(raw.get("name", track_id), "track name", 128), int(bool(raw.get("enabled", True))),
                     raw.get("startsAt"), raw.get("endsAt"), canonical(normalized), now))
            if offer_ids:
                conn.execute("update offers set enabled=0 where id not in (%s)" % ",".join("?" * len(offer_ids)), tuple(sorted(offer_ids)))
            else:
                conn.execute("update offers set enabled=0")
        return {"ok": True, "offers": len(offer_ids), "tracks": len(track_keys), "enabled": bool(config.get("enabled", False))}

    def _append_ledger(self, conn, account_id, delta, kind, reference, metadata=None):
        delta = int(delta)
        if delta == 0 or abs(delta) > MAX_LEDGER_AMOUNT:
            raise ValueError("ledger delta is outside the supported range")
        reference = _identifier(reference, "reference", 256)
        kind = _identifier(kind, "kind", 64)
        row = conn.execute("select balance from wallets where dune_account_id=?", (account_id,)).fetchone()
        balance = int(row["balance"] if row else 0)
        after = balance + delta
        if after < 0:
            raise ValueError("insufficient community credits")
        last = conn.execute("select entry_hash from ledger order by rowid desc limit 1").fetchone()
        previous_hash = last["entry_hash"] if last else ZERO_HASH
        entry_id = str(uuid.uuid4())
        created_at = self.now()
        metadata_json = canonical(metadata or {})
        material = canonical({"id": entry_id, "account": account_id, "delta": delta, "balanceAfter": after, "kind": kind,
                              "reference": reference, "metadata": json.loads(metadata_json), "previousHash": previous_hash, "createdAt": created_at})
        entry_hash = hashlib.sha256(material.encode()).hexdigest()
        conn.execute("update wallets set balance=?,updated_at=? where dune_account_id=?", (after, created_at, account_id))
        conn.execute("insert into ledger values(?,?,?,?,?,?,?,?,?,?)",
                     (entry_id, account_id, delta, after, kind, reference, metadata_json, previous_hash, entry_hash, created_at))
        return {"id": entry_id, "balance": after, "delta": delta, "entryHash": entry_hash}

    def credit(self, dune_account_id, amount, kind, reference, metadata=None):
        amount = _positive_int(amount, "amount")
        with self.transaction() as conn:
            account_id = self._ensure_account(conn, dune_account_id)
            existing = conn.execute("select id,balance_after,delta,entry_hash from ledger where reference=?", (str(reference),)).fetchone()
            if existing:
                return dict(existing, balance=int(existing["balance_after"]), idempotent=True)
            return dict(self._append_ledger(conn, account_id, amount, kind, reference, metadata), idempotent=False)

    def create_link_code(self, dune_account_id, ttl_seconds=900):
        ttl = max(60, min(int(ttl_seconds), 86400))
        code = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12].upper()
        digest = hashlib.sha256(code.encode()).hexdigest()
        now_epoch = int(dt.datetime.now(dt.timezone.utc).timestamp())
        expires = dt.datetime.fromtimestamp(now_epoch + ttl, dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self.transaction() as conn:
            account_id = self._ensure_account(conn, dune_account_id)
            conn.execute("delete from link_codes where dune_account_id=? and used_at is null", (account_id,))
            conn.execute("insert into link_codes values(?,?,?,?,?)", (digest, account_id, expires, None, self.now()))
        return {"ok": True, "duneAccountId": account_id, "code": code, "expiresAt": expires}

    def redeem_link_code(self, discord_user_id, code):
        discord_id = _identifier(discord_user_id, "discordUserId", 64)
        digest = hashlib.sha256(str(code or "").strip().upper().encode()).hexdigest()
        with self.transaction() as conn:
            row = conn.execute("select * from link_codes where code_hash=?", (digest,)).fetchone()
            if not row or row["used_at"] or row["expires_at"] < self.now():
                raise ValueError("link code is invalid or expired")
            conflict = conn.execute("select dune_account_id from accounts where discord_user_id=?", (discord_id,)).fetchone()
            if conflict and int(conflict["dune_account_id"]) != int(row["dune_account_id"]):
                raise ValueError("Discord user is already linked to another account")
            now = self.now()
            conn.execute("update accounts set discord_user_id=?,linked_at=? where dune_account_id=?", (discord_id, now, row["dune_account_id"]))
            conn.execute("update link_codes set used_at=? where code_hash=?", (now, digest))
            return {"ok": True, "discordUserId": discord_id, "duneAccountId": int(row["dune_account_id"]), "linkedAt": now}

    def account_for_discord(self, discord_user_id):
        with contextlib.closing(self.connect()) as conn:
            row = conn.execute("select a.*,w.balance from accounts a join wallets w using(dune_account_id) where discord_user_id=?", (str(discord_user_id),)).fetchone()
            return dict(row) if row else None

    def linked_accounts(self):
        with contextlib.closing(self.connect()) as conn:
            return [dict(row) for row in conn.execute(
                "select a.dune_account_id,a.discord_user_id,a.linked_at,w.balance from accounts a join wallets w using(dune_account_id) where a.discord_user_id is not null order by a.dune_account_id"
            )]

    def purchase(self, dune_account_id, offer_id, quantity, idempotency_key):
        quantity = _positive_int(quantity, "quantity", MAX_PURCHASE_QUANTITY)
        idempotency_key = _identifier(idempotency_key, "idempotencyKey", 128)
        now = self.now()
        with self.transaction() as conn:
            account_id = self._ensure_account(conn, dune_account_id)
            existing = conn.execute("select * from purchases where dune_account_id=? and idempotency_key=?", (account_id, idempotency_key)).fetchone()
            if existing:
                return dict(existing, idempotent=True)
            offer = conn.execute("select * from offers where id=?", (str(offer_id),)).fetchone()
            if not offer or not offer["enabled"]:
                raise ValueError("offer is unavailable")
            if offer["stock"] is not None and int(offer["stock"]) < quantity:
                raise ValueError("offer is out of stock")
            purchase_id = str(uuid.uuid4())
            delivery_id = str(uuid.uuid4())
            total = int(offer["price"]) * quantity
            rewards = []
            for _ in range(quantity):
                rewards.extend(json.loads(offer["rewards_json"]))
            conn.execute("insert into purchases values(?,?,?,?,?,?,?,?,?,?,?)",
                         (purchase_id, account_id, offer["id"], offer["version"], quantity, total, "queued", idempotency_key, None, now, now))
            if total:
                self._append_ledger(conn, account_id, -total, "purchase", f"purchase:{purchase_id}", {"offerId": offer["id"], "quantity": quantity})
            if offer["stock"] is not None:
                conn.execute("update offers set stock=stock-? where id=?", (quantity, offer["id"]))
            conn.execute("insert into deliveries(id,source_type,source_id,dune_account_id,rewards_json,status,created_at,updated_at) values(?,?,?,?,?,'queued',?,?)",
                         (delivery_id, "purchase", purchase_id, account_id, canonical(rewards), now, now))
            result = conn.execute("select * from purchases where id=?", (purchase_id,)).fetchone()
            return dict(result, deliveryId=delivery_id, idempotent=False)

    def claim_delivery(self, delivery_id=None):
        with self.transaction() as conn:
            if delivery_id:
                row = conn.execute("select * from deliveries where id=? and status in ('queued','retry')", (str(delivery_id),)).fetchone()
            else:
                row = conn.execute("select * from deliveries where status in ('queued','retry') order by created_at limit 1").fetchone()
            if not row:
                return None
            token = secrets.token_hex(16)
            now = self.now()
            conn.execute("update deliveries set status='processing',attempts=attempts+1,claim_token=?,claimed_at=?,updated_at=? where id=?",
                         (token, now, now, row["id"]))
            claimed = dict(conn.execute("select * from deliveries where id=?", (row["id"],)).fetchone())
            claimed["rewards"] = json.loads(claimed.pop("rewards_json"))
            return claimed

    def complete_delivery(self, delivery_id, claim_token, receipt):
        with self.transaction() as conn:
            row = conn.execute("select * from deliveries where id=?", (str(delivery_id),)).fetchone()
            if not row or row["status"] != "processing" or not hmac.compare_digest(str(row["claim_token"] or ""), str(claim_token or "")):
                raise ValueError("delivery claim is stale or invalid")
            now = self.now()
            conn.execute("update deliveries set status='delivered',delivered_at=?,receipt_json=?,claim_token=null,error=null,updated_at=? where id=?",
                         (now, canonical(receipt or {}), now, row["id"]))
            if row["source_type"] == "purchase":
                conn.execute("update purchases set status='delivered',updated_at=? where id=?", (now, row["source_id"]))
            return {"ok": True, "deliveryId": row["id"], "status": "delivered", "deliveredAt": now}

    def release_delivery(self, delivery_id, claim_token, reason):
        with self.transaction() as conn:
            row = conn.execute("select * from deliveries where id=?", (str(delivery_id),)).fetchone()
            if not row or row["status"] != "processing" or not hmac.compare_digest(str(row["claim_token"] or ""), str(claim_token or "")):
                raise ValueError("delivery claim is stale or invalid")
            now = self.now()
            conn.execute("update deliveries set status='retry',error=?,claim_token=null,updated_at=? where id=?",
                         (str(reason or "retry requested")[:2000], now, row["id"]))
            return {"ok": True, "deliveryId": row["id"], "status": "retry"}

    def resolve_reconciliation(self, delivery_id, delivered, receipt=None, reason="manual reconciliation"):
        with self.transaction() as conn:
            row = conn.execute("select * from deliveries where id=? and status='reconciliation'", (str(delivery_id),)).fetchone()
            if not row:
                raise ValueError("delivery is not awaiting reconciliation")
            now = self.now()
            if delivered:
                conn.execute("update deliveries set status='delivered',delivered_at=?,receipt_json=?,error=null,updated_at=? where id=?",
                             (now, canonical(receipt or {"reconciled": True}), now, row["id"]))
                if row["source_type"] == "purchase":
                    conn.execute("update purchases set status='delivered',error=null,updated_at=? where id=?", (now, row["source_id"]))
                return {"ok": True, "deliveryId": row["id"], "status": "delivered", "refunded": False}
            refunded = False
            if row["source_type"] == "purchase":
                purchase = conn.execute("select * from purchases where id=?", (row["source_id"],)).fetchone()
                if purchase and purchase["status"] not in ("refunded", "delivered"):
                    if int(purchase["total"]):
                        self._append_ledger(conn, int(purchase["dune_account_id"]), int(purchase["total"]), "reconciliation-refund",
                                            f"refund:{purchase['id']}", {"deliveryId": row["id"], "reason": str(reason)[:1000]})
                    conn.execute("update offers set stock=stock+? where id=? and stock is not null", (purchase["quantity"], purchase["offer_id"]))
                    conn.execute("update purchases set status='refunded',error=?,updated_at=? where id=?", (str(reason)[:2000], now, purchase["id"]))
                    refunded = True
            conn.execute("update deliveries set status='failed',error=?,updated_at=? where id=?", (str(reason)[:2000], now, row["id"]))
            return {"ok": True, "deliveryId": row["id"], "status": "failed", "refunded": refunded}

    def fail_delivery(self, delivery_id, claim_token, error, definitive=True):
        with self.transaction() as conn:
            row = conn.execute("select * from deliveries where id=?", (str(delivery_id),)).fetchone()
            if not row or row["status"] != "processing" or not hmac.compare_digest(str(row["claim_token"] or ""), str(claim_token or "")):
                raise ValueError("delivery claim is stale or invalid")
            error = str(error or "delivery failed")[:2000]
            now = self.now()
            if not definitive:
                conn.execute("update deliveries set status='reconciliation',error=?,claim_token=null,updated_at=? where id=?", (error, now, row["id"]))
                return {"ok": False, "deliveryId": row["id"], "status": "reconciliation", "refunded": False}
            refunded = False
            if row["source_type"] == "purchase":
                purchase = conn.execute("select * from purchases where id=?", (row["source_id"],)).fetchone()
                if purchase and purchase["status"] not in ("refunded", "delivered"):
                    if int(purchase["total"]):
                        self._append_ledger(conn, int(purchase["dune_account_id"]), int(purchase["total"]), "delivery-refund",
                                            f"refund:{purchase['id']}", {"deliveryId": row["id"], "error": error})
                    conn.execute("update offers set stock=stock+? where id=? and stock is not null", (purchase["quantity"], purchase["offer_id"]))
                    conn.execute("update purchases set status='refunded',error=?,updated_at=? where id=?", (error, now, purchase["id"]))
                    refunded = True
            conn.execute("update deliveries set status='failed',error=?,claim_token=null,updated_at=? where id=?", (error, now, row["id"]))
            return {"ok": False, "deliveryId": row["id"], "status": "failed", "refunded": refunded}

    def ingest_webhook(self, provider, event_id, dune_account_id, amount, payload):
        provider = _identifier(provider, "provider", 32).lower()
        event_id = _identifier(event_id, "eventId", 128)
        amount = _positive_int(amount, "amount")
        digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
        with self.transaction() as conn:
            existing = conn.execute("select * from webhook_receipts where provider=? and event_id=?", (provider, event_id)).fetchone()
            if existing:
                if existing["payload_sha256"] != digest:
                    raise ValueError("webhook event id was reused with a different payload")
                return {"ok": True, "provider": existing["provider"], "eventId": existing["event_id"],
                        "duneAccountId": int(existing["dune_account_id"]), "amount": int(existing["amount"]),
                        "ledgerId": existing["ledger_id"], "idempotent": True}
            account_id = self._ensure_account(conn, dune_account_id)
            ledger = self._append_ledger(conn, account_id, amount, f"webhook-{provider}", f"webhook:{provider}:{event_id}", {"payloadSha256": digest})
            conn.execute("insert into webhook_receipts values(?,?,?,?,?,?,?)", (provider, event_id, digest, account_id, amount, ledger["id"], self.now()))
            return {"ok": True, "provider": provider, "eventId": event_id, "duneAccountId": account_id, "amount": amount,
                    "ledgerId": ledger["id"], "balance": ledger["balance"], "idempotent": False}

    def observe_playtime(self, dune_account_id, online, observed_epoch, interval_seconds, credits_per_interval, max_gap_seconds):
        observed = int(observed_epoch)
        interval = _positive_int(interval_seconds, "intervalSeconds", 86400)
        credits = _positive_int(credits_per_interval, "creditsPerInterval", 1_000_000)
        max_gap = max(interval, min(int(max_gap_seconds), 86400))
        with self.transaction() as conn:
            account_id = self._ensure_account(conn, dune_account_id)
            row = conn.execute("select * from playtime_checkpoints where dune_account_id=?", (account_id,)).fetchone()
            if not row:
                conn.execute("insert into playtime_checkpoints values(?,?,?,?,0)", (account_id, observed, int(bool(online)), 0))
                return {"ok": True, "credited": 0, "intervals": 0, "firstObservation": True}
            elapsed = max(0, min(observed - int(row["observed_at"]), max_gap)) if row["was_online"] else 0
            total = int(row["remainder_seconds"]) + elapsed
            intervals = total // interval
            remainder = total % interval
            credited = intervals * credits
            conn.execute("update playtime_checkpoints set observed_at=?,was_online=?,remainder_seconds=?,credited_intervals=credited_intervals+? where dune_account_id=?",
                         (observed, int(bool(online)), remainder, intervals, account_id))
            balance = None
            if credited:
                reference = f"playtime:{account_id}:{int(row['credited_intervals']) + intervals}"
                balance = self._append_ledger(conn, account_id, credited, "playtime", reference, {"seconds": intervals * interval})["balance"]
            return {"ok": True, "credited": credited, "intervals": intervals, "remainderSeconds": remainder, "balance": balance}

    @staticmethod
    def _location(value, precision=10.0):
        if not isinstance(value, dict):
            return {"map": None, "partitionId": None, "x": None, "y": None, "z": None}
        result = {
            "map": str(value.get("map") or "").strip() or None,
            "partitionId": None,
            "x": None,
            "y": None,
            "z": None,
        }
        if value.get("partitionId", value.get("partition_id")) not in (None, ""):
            result["partitionId"] = int(value.get("partitionId", value.get("partition_id")))
        for key in ("x", "y", "z"):
            if value.get(key) not in (None, ""):
                result[key] = round(float(value[key]) / float(precision)) * float(precision)
        return result

    @staticmethod
    def _movement_proven(previous, current, minimum_distance):
        if not previous.get("map") or not current.get("map"):
            return False, None
        if previous.get("map") != current.get("map") or previous.get("partitionId") != current.get("partitionId"):
            return True, None
        if any(previous.get(key) is None or current.get(key) is None for key in ("x", "y", "z")):
            return False, None
        distance = sum((float(current[key]) - float(previous[key])) ** 2 for key in ("x", "y", "z")) ** 0.5
        return distance >= float(minimum_distance), distance

    @staticmethod
    def _tier_for(rows, key, value):
        selected = None
        for row in rows:
            if int(row[key]) <= int(value):
                selected = row
            else:
                break
        return selected

    def _add_track_progress(self, conn, account_id, track_id, amount, reference):
        amount = _positive_int(amount, "amount")
        track = conn.execute("select * from tracks where id=? and enabled=1 order by version desc limit 1", (str(track_id),)).fetchone()
        if not track:
            raise ValueError(f"reward track {track_id!r} is unavailable")
        marker = f"track-progress:{track['id']}:{track['version']}:{_identifier(reference, 'reference', 128)}"
        if conn.execute("select 1 from metadata where key=?", (marker,)).fetchone():
            progress = conn.execute("select xp from track_progress where dune_account_id=? and track_id=? and track_version=?",
                                    (account_id, track["id"], track["version"])).fetchone()
            return {"ok": True, "xp": int(progress["xp"] if progress else 0), "idempotent": True}
        now = self.now()
        conn.execute("insert into track_progress values(?,?,?,?,?) on conflict(dune_account_id,track_id,track_version) do update set xp=xp+excluded.xp,updated_at=excluded.updated_at",
                     (account_id, track["id"], track["version"], amount, now))
        conn.execute("insert into metadata(key,value) values(?,?)", (marker, now))
        xp = conn.execute("select xp from track_progress where dune_account_id=? and track_id=? and track_version=?",
                          (account_id, track["id"], track["version"])).fetchone()["xp"]
        return {"ok": True, "trackId": track["id"], "version": track["version"], "xp": int(xp), "idempotent": False}

    def _grant_engagement_reward(self, conn, account_id, kind, period_key, tier, reward):
        existing = conn.execute(
            "select * from engagement_claims where dune_account_id=? and kind=? and period_key=? and tier=?",
            (account_id, kind, str(period_key), int(tier)),
        ).fetchone()
        if existing:
            return {"kind": kind, "periodKey": str(period_key), "tier": int(tier), "idempotent": True,
                    "deliveryId": existing["delivery_id"], "ledgerId": existing["ledger_id"]}
        source = f"engagement:{kind}:{account_id}:{period_key}:{int(tier)}"
        ledger_id = None
        balance = None
        if int(reward.get("credits", 0)):
            ledger = self._append_ledger(conn, account_id, int(reward["credits"]), f"engagement-{kind}", source,
                                         {"periodKey": str(period_key), "tier": int(tier)})
            ledger_id = ledger["id"]
            balance = ledger["balance"]
        track_result = None
        track = reward.get("track")
        if track:
            track_result = self._add_track_progress(conn, account_id, track["id"], track["xp"], source)
        delivery_id = None
        items = reward.get("items") or []
        if items:
            delivery_id = str(uuid.uuid4())
            conn.execute(
                "insert into deliveries(id,source_type,source_id,dune_account_id,rewards_json,status,created_at,updated_at) values(?,?,?,?,?,'queued',?,?)",
                (delivery_id, f"engagement-{kind}", source, account_id, canonical(items), self.now(), self.now()),
            )
        claim_id = str(uuid.uuid4())
        conn.execute(
            "insert into engagement_claims values(?,?,?,?,?,?,?,?,?)",
            (claim_id, account_id, kind, str(period_key), int(tier), canonical(reward), delivery_id, ledger_id, self.now()),
        )
        return {"id": claim_id, "kind": kind, "periodKey": str(period_key), "tier": int(tier),
                "credits": int(reward.get("credits", 0)), "balance": balance, "track": track_result,
                "deliveryId": delivery_id, "idempotent": False}

    def observe_engagement(self, dune_account_id, online, observed_epoch, location, policy=None):
        policy = engagement_config({"engagementRewards": policy or {}})
        observed = int(observed_epoch)
        current = self._location(location, policy["coordinatePrecision"])
        max_gap = int(policy["maxObservationGapSeconds"])
        grace = int(policy["movementGraceSeconds"])
        minimum_distance = float(policy["minimumMovementDistance"])
        with self.transaction() as conn:
            account_id = self._ensure_account(conn, dune_account_id)
            row = conn.execute("select * from engagement_checkpoints where dune_account_id=?", (account_id,)).fetchone()
            if not row:
                conn.execute(
                    "insert into engagement_checkpoints(dune_account_id,observed_at,was_online,map_name,partition_id,x,y,z,last_movement_at,session_started_at) values(?,?,?,?,?,?,?,?,?,?)",
                    (account_id, observed, int(bool(online)), current["map"], current["partitionId"], current["x"], current["y"], current["z"], None, observed if online else None),
                )
                return {"ok": True, "active": False, "activeSeconds": 0, "firstObservation": True, "rewards": []}
            if observed <= int(row["observed_at"]):
                return {"ok": True, "active": False, "activeSeconds": 0, "replay": True, "rewards": []}
            previous = {"map": row["map_name"], "partitionId": row["partition_id"], "x": row["x"], "y": row["y"], "z": row["z"]}
            moved, distance = self._movement_proven(previous, current, minimum_distance)
            last_movement_at = observed if moved else row["last_movement_at"]
            elapsed_raw = observed - int(row["observed_at"])
            elapsed = max(0, min(elapsed_raw, max_gap))
            continuous = bool(online) and bool(row["was_online"]) and elapsed_raw <= max_gap
            active = continuous and bool(last_movement_at) and observed - int(last_movement_at) <= grace
            active_seconds = elapsed if active else 0
            session_started = row["session_started_at"] if continuous else (observed if online else None)
            session_seconds = int(row["session_active_seconds"] if continuous else 0) + active_seconds
            rewarded_hours = int(row["rewarded_hours"] if continuous else 0)
            rewards = []
            if policy.get("enabled") and active_seconds:
                moment = dt.datetime.fromtimestamp(observed, dt.timezone.utc)
                day = moment.date().isoformat()
                iso = moment.isocalendar()
                week = f"{iso.year}-W{iso.week:02d}"
                day_row = conn.execute("select * from engagement_days where dune_account_id=? and day=?", (account_id, day)).fetchone()
                if day_row:
                    streak = int(day_row["streak"])
                    conn.execute("update engagement_days set active_seconds=active_seconds+?,last_activity_at=? where dune_account_id=? and day=?",
                                 (active_seconds, observed, account_id, day))
                else:
                    yesterday = (moment.date() - dt.timedelta(days=1)).isoformat()
                    prior = conn.execute("select streak from engagement_days where dune_account_id=? and day=?", (account_id, yesterday)).fetchone()
                    streak = int(prior["streak"] if prior else 0) + 1
                    conn.execute("insert into engagement_days values(?,?,?,?,?,?)", (account_id, day, active_seconds, streak, observed, observed))
                    daily = policy["daily"]
                    if daily["enabled"]:
                        tier_row = self._tier_for(daily["tiers"], "day", streak)
                        exact = tier_row and (daily["repeatLast"] or int(tier_row["day"]) == streak)
                        if exact:
                            rewards.append(self._grant_engagement_reward(conn, account_id, "daily", day, int(tier_row["day"]), tier_row["reward"]))
                week_row = conn.execute("select active_seconds from engagement_weeks where dune_account_id=? and week=?", (account_id, week)).fetchone()
                previous_week_seconds = int(week_row["active_seconds"] if week_row else 0)
                current_week_seconds = previous_week_seconds + active_seconds
                if week_row:
                    conn.execute("update engagement_weeks set active_seconds=?,last_activity_at=? where dune_account_id=? and week=?",
                                 (current_week_seconds, observed, account_id, week))
                else:
                    conn.execute("insert into engagement_weeks values(?,?,?,?,?)", (account_id, week, current_week_seconds, observed, observed))
                weekly = policy["weekly"]
                if weekly["enabled"]:
                    for threshold in weekly["thresholds"]:
                        seconds = int(threshold["activeSeconds"])
                        if previous_week_seconds < seconds <= current_week_seconds:
                            rewards.append(self._grant_engagement_reward(conn, account_id, "weekly", week, seconds, threshold["reward"]))
                hourly = policy["hourly"]
                if hourly["enabled"] and hourly["maxRewardsPerSession"]:
                    earned_hours = min(session_seconds // int(hourly["intervalSeconds"]), int(hourly["maxRewardsPerSession"]))
                    for hour in range(rewarded_hours + 1, earned_hours + 1):
                        tier_row = self._tier_for(hourly["tiers"], "fromHour", hour)
                        if tier_row:
                            rewards.append(self._grant_engagement_reward(conn, account_id, "hourly", str(session_started), hour, tier_row["reward"]))
                    rewarded_hours = max(rewarded_hours, earned_hours)
            conn.execute(
                "update engagement_checkpoints set observed_at=?,was_online=?,map_name=?,partition_id=?,x=?,y=?,z=?,last_movement_at=?,session_started_at=?,session_active_seconds=?,rewarded_hours=? where dune_account_id=?",
                (observed, int(bool(online)), current["map"], current["partitionId"], current["x"], current["y"], current["z"],
                 last_movement_at if online else None, session_started if online else None, session_seconds if online else 0,
                 rewarded_hours if online else 0, account_id),
            )
            return {"ok": True, "active": active, "activeSeconds": active_seconds, "moved": moved, "distance": distance,
                    "sessionActiveSeconds": session_seconds if online else 0, "rewards": rewards}

    def add_track_progress(self, dune_account_id, track_id, amount, reference):
        with self.transaction() as conn:
            account_id = self._ensure_account(conn, dune_account_id)
            return self._add_track_progress(conn, account_id, track_id, amount, reference)

    def claim_track_level(self, dune_account_id, track_id, level):
        level = _positive_int(level, "level", 10_000)
        now = self.now()
        with self.transaction() as conn:
            account_id = self._ensure_account(conn, dune_account_id)
            track = conn.execute("select * from tracks where id=? and enabled=1 order by version desc limit 1", (str(track_id),)).fetchone()
            if not track:
                raise ValueError("reward track is unavailable")
            levels = json.loads(track["levels_json"])
            if level > len(levels):
                raise ValueError("reward track level does not exist")
            progress = conn.execute("select xp from track_progress where dune_account_id=? and track_id=? and track_version=?",
                                    (account_id, track["id"], track["version"])).fetchone()
            if int(progress["xp"] if progress else 0) < int(levels[level - 1]["xp"]):
                raise ValueError("reward track level is not unlocked")
            existing = conn.execute("select delivery_id from track_claims where dune_account_id=? and track_id=? and track_version=? and level=?",
                                    (account_id, track["id"], track["version"], level)).fetchone()
            if existing:
                return {"ok": True, "deliveryId": existing["delivery_id"], "idempotent": True}
            delivery_id = str(uuid.uuid4())
            source_id = f"{account_id}:{track['id']}:{track['version']}:{level}"
            conn.execute("insert into deliveries(id,source_type,source_id,dune_account_id,rewards_json,status,created_at,updated_at) values(?,?,?,?,?,'queued',?,?)",
                         (delivery_id, "track-claim", source_id, account_id, canonical(levels[level - 1]["rewards"]), now, now))
            conn.execute("insert into track_claims values(?,?,?,?,?,?)", (account_id, track["id"], track["version"], level, delivery_id, now))
            return {"ok": True, "deliveryId": delivery_id, "idempotent": False}

    def verify_ledger(self):
        with contextlib.closing(self.connect()) as conn:
            rows = conn.execute("select * from ledger order by rowid").fetchall()
        previous = ZERO_HASH
        errors = []
        balances = {}
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            material = canonical({"id": row["id"], "account": row["dune_account_id"], "delta": row["delta"], "balanceAfter": row["balance_after"],
                                  "kind": row["kind"], "reference": row["reference"], "metadata": metadata,
                                  "previousHash": row["previous_hash"], "createdAt": row["created_at"]})
            expected = hashlib.sha256(material.encode()).hexdigest()
            prior_balance = balances.get(int(row["dune_account_id"]), 0)
            if row["previous_hash"] != previous or row["entry_hash"] != expected or int(row["balance_after"]) != prior_balance + int(row["delta"]):
                errors.append(str(row["id"]))
            previous = row["entry_hash"]
            balances[int(row["dune_account_id"])] = int(row["balance_after"])
        return {"ok": not errors, "entries": len(rows), "head": previous, "errors": errors[:100]}

    def status(self, account_id=None, limit=100):
        limit = max(1, min(int(limit), 500))
        config = load_config(self.config_path)
        with contextlib.closing(self.connect()) as conn:
            result = {
                "ok": True,
                "enabled": bool(config.get("enabled", False)),
                "engagementPolicy": engagement_config(config),
                "currency": config.get("currency") or {"name": "Community Credits", "symbol": "CC"},
                "offers": [dict(row, rewards=json.loads(row["rewards_json"])) for row in conn.execute("select * from offers order by kind,name")],
                "tracks": [dict(row, levels=json.loads(row["levels_json"])) for row in conn.execute("select * from tracks order by id,version desc")],
                "deliveryCounts": {row["status"]: row["count"] for row in conn.execute("select status,count(*) as count from deliveries group by status")},
                "engagement": {
                    "trackedAccounts": int(conn.execute("select count(*) from engagement_checkpoints").fetchone()[0]),
                    "activeToday": int(conn.execute("select count(*) from engagement_days where day=date('now') and active_seconds>0").fetchone()[0]),
                    "claims": {row["kind"]: int(row["count"]) for row in conn.execute("select kind,count(*) as count from engagement_claims group by kind")},
                },
                "ledger": self.verify_ledger(),
            }
            for rows in (result["offers"], result["tracks"]):
                for row in rows:
                    row.pop("rewards_json", None)
                    row.pop("levels_json", None)
            if account_id not in (None, ""):
                account_id = int(account_id)
                account = conn.execute("select a.*,w.balance from accounts a join wallets w using(dune_account_id) where dune_account_id=?", (account_id,)).fetchone()
                result["account"] = dict(account) if account else None
                result["purchases"] = [dict(row) for row in conn.execute("select * from purchases where dune_account_id=? order by created_at desc limit ?", (account_id, limit))]
                result["deliveries"] = [dict(row) for row in conn.execute("select id,source_type,source_id,status,attempts,error,created_at,updated_at,delivered_at from deliveries where dune_account_id=? order by created_at desc limit ?", (account_id, limit))]
                result["ledgerEntries"] = [dict(row) for row in conn.execute("select id,delta,balance_after,kind,reference,entry_hash,created_at from ledger where dune_account_id=? order by rowid desc limit ?", (account_id, limit))]
                result["progress"] = [dict(row) for row in conn.execute("select * from track_progress where dune_account_id=? order by track_id,track_version desc", (account_id,))]
                checkpoint = conn.execute("select * from engagement_checkpoints where dune_account_id=?", (account_id,)).fetchone()
                result["engagementCheckpoint"] = dict(checkpoint) if checkpoint else None
                result["engagementDays"] = [dict(row) for row in conn.execute("select * from engagement_days where dune_account_id=? order by day desc limit ?", (account_id, limit))]
                result["engagementWeeks"] = [dict(row) for row in conn.execute("select * from engagement_weeks where dune_account_id=? order by week desc limit ?", (account_id, limit))]
                result["engagementClaims"] = [dict(row, reward=json.loads(row["reward_json"])) for row in conn.execute(
                    "select * from engagement_claims where dune_account_id=? order by created_at desc limit ?", (account_id, limit))]
                for row in result["engagementClaims"]:
                    row.pop("reward_json", None)
            return result
