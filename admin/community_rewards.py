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


SCHEMA_VERSION = 1
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


def load_config(path):
    path = pathlib.Path(path)
    if not path.exists():
        return {"version": 1, "enabled": False, "currency": {"name": "Community Credits", "symbol": "CC"}, "offers": [], "tracks": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or int(value.get("version", 0)) != 1:
        raise ValueError("community rewards config must be a version 1 object")
    if not isinstance(value.get("offers", []), list) or not isinstance(value.get("tracks", []), list):
        raise ValueError("offers and tracks must be arrays")
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

    def add_track_progress(self, dune_account_id, track_id, amount, reference):
        amount = _positive_int(amount, "amount")
        with self.transaction() as conn:
            account_id = self._ensure_account(conn, dune_account_id)
            track = conn.execute("select * from tracks where id=? and enabled=1 order by version desc limit 1", (str(track_id),)).fetchone()
            if not track:
                raise ValueError("reward track is unavailable")
            # References share the immutable ledger namespace without changing the wallet.
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
                "currency": config.get("currency") or {"name": "Community Credits", "symbol": "CC"},
                "offers": [dict(row, rewards=json.loads(row["rewards_json"])) for row in conn.execute("select * from offers order by kind,name")],
                "tracks": [dict(row, levels=json.loads(row["levels_json"])) for row in conn.execute("select * from tracks order by id,version desc")],
                "deliveryCounts": {row["status"]: row["count"] for row in conn.execute("select status,count(*) as count from deliveries group by status")},
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
            return result
