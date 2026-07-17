#!/usr/bin/env python3
"""Isolated, signed end-to-end canaries for the Community Rewards subsystem."""

import datetime
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import tempfile
import threading
import time

import community_rewards


SCHEMA = "dune-community-rewards-canary/v1"
RECEIPT_SCHEMA = 1
ID_PATTERN = re.compile(r"^community-canary-[0-9a-f]{32}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CHECK_NAMES = (
    "catalogLoaded", "linkRoundTrip", "webhookSignature", "webhookReplay",
    "creditReplay", "purchaseReplay", "purchaseDelivery", "playtimeAccrual",
    "engagementMovement", "trackReplay", "trackDelivery", "ledgerIntegrity",
)
ISOLATION = {
    "temporaryDatabaseCreated": True,
    "temporaryStateRemoved": True,
    "liveCommunityDatabaseOpened": False,
    "gameDatabaseOpened": False,
    "gameDeliveryInvoked": False,
    "externalProviderCalled": False,
}
LOCK = threading.RLock()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def iso(epoch=None):
    epoch = time.time() if epoch is None else float(epoch)
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value):
    text = str(value or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("community canary timestamp lacks a timezone")
    return parsed.timestamp()


def file_sha256(path):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= 10 * 1024 * 1024:
        raise ValueError("community rewards policy must be a bounded regular file")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def receipt_hash(receipt):
    unsigned = {key: value for key, value in receipt.items() if key != "receiptSha256"}
    return hashlib.sha256(canonical(unsigned).encode()).hexdigest()


def signed_document(receipt, secret, generated_at=None):
    receipt = json.loads(canonical(receipt))
    receipt["receiptSha256"] = receipt_hash(receipt)
    payload = {
        "schemaVersion": SCHEMA,
        "generatedAt": iso(generated_at),
        "signingKeyFingerprint": hashlib.sha256(secret).hexdigest(),
        "receipt": receipt,
    }
    return {**payload, "signature": hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()}


RECEIPT_FIELDS = {
    "schemaVersion", "id", "principalId", "startedAt", "completedAt",
    "durationMs", "policySha256", "checks", "evidence", "isolation",
    "ready", "receiptSha256",
}
EVIDENCE_FIELDS = {
    "offers", "tracks", "ledgerEntries", "deliveriesCompleted",
    "purchaseIdempotent", "webhookIdempotent", "trackIdempotent",
}


def verify_signed_document(document, secret, *, current_policy_sha256=None, max_age_seconds=None, now=None):
    try:
        if not isinstance(document, dict) or set(document) != {
            "schemaVersion", "generatedAt", "signingKeyFingerprint", "receipt", "signature",
        }:
            raise ValueError("community canary signed document fields are invalid")
        if document.get("schemaVersion") != SCHEMA:
            raise ValueError("community canary schema is invalid")
        payload = {key: value for key, value in document.items() if key != "signature"}
        expected = hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(document.get("signature") or ""), expected):
            raise ValueError("community canary signature is invalid")
        if not hmac.compare_digest(str(document.get("signingKeyFingerprint") or ""), hashlib.sha256(secret).hexdigest()):
            raise ValueError("community canary signing key fingerprint differs")
        epoch(document.get("generatedAt"))
        receipt = document.get("receipt")
        if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS or receipt.get("schemaVersion") != RECEIPT_SCHEMA:
            raise ValueError("community canary receipt fields are invalid")
        if not ID_PATTERN.fullmatch(str(receipt.get("id") or "")):
            raise ValueError("community canary receipt id is invalid")
        principal = str(receipt.get("principalId") or "")
        if not 1 <= len(principal) <= 128 or any(ord(char) < 32 for char in principal):
            raise ValueError("community canary principal is invalid")
        started, completed = epoch(receipt.get("startedAt")), epoch(receipt.get("completedAt"))
        if not 0 <= completed - started <= 300:
            raise ValueError("community canary duration is invalid")
        duration = receipt.get("durationMs")
        if isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= 300_000:
            raise ValueError("community canary duration evidence is invalid")
        if abs(duration - round((completed - started) * 1000)) > 2000:
            raise ValueError("community canary duration does not match timestamps")
        policy_sha = str(receipt.get("policySha256") or "")
        if not HASH_PATTERN.fullmatch(policy_sha):
            raise ValueError("community canary policy digest is invalid")
        checks = receipt.get("checks")
        if not isinstance(checks, dict) or tuple(sorted(checks)) != tuple(sorted(CHECK_NAMES)) or any(type(value) is not bool for value in checks.values()):
            raise ValueError("community canary checks are invalid")
        evidence = receipt.get("evidence")
        if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
            raise ValueError("community canary evidence fields are invalid")
        for key in ("offers", "tracks", "ledgerEntries", "deliveriesCompleted"):
            if isinstance(evidence.get(key), bool) or not isinstance(evidence.get(key), int) or not 0 <= evidence[key] <= 1_000_000:
                raise ValueError("community canary evidence count is invalid")
        for key in ("purchaseIdempotent", "webhookIdempotent", "trackIdempotent"):
            if type(evidence.get(key)) is not bool:
                raise ValueError("community canary idempotency evidence is invalid")
        isolation = receipt.get("isolation")
        if not isinstance(isolation, dict) or set(isolation) != set(ISOLATION) or any(type(value) is not bool for value in isolation.values()):
            raise ValueError("community canary isolation proof fields are invalid")
        unsafe = any(isolation[key] for key in (
            "liveCommunityDatabaseOpened", "gameDatabaseOpened",
            "gameDeliveryInvoked", "externalProviderCalled",
        ))
        isolation_ready = bool(isolation["temporaryDatabaseCreated"] and isolation["temporaryStateRemoved"] and not unsafe)
        if type(receipt.get("ready")) is not bool or receipt["ready"] is not (all(checks.values()) and isolation_ready):
            raise ValueError("community canary verdict is inconsistent")
        expected_hash = receipt_hash(receipt)
        if not HASH_PATTERN.fullmatch(str(receipt.get("receiptSha256") or "")) or not hmac.compare_digest(receipt["receiptSha256"], expected_hash):
            raise ValueError("community canary receipt digest is invalid")
        policy_current = current_policy_sha256 is None or hmac.compare_digest(policy_sha, str(current_policy_sha256))
        age_seconds = max(0.0, float(time.time() if now is None else now) - completed)
        age_current = max_age_seconds is None or age_seconds <= float(max_age_seconds)
        return {
            "ok": True, "signatureValid": True, "receiptValid": True,
            "receiptId": receipt["id"], "receiptSha256": receipt["receiptSha256"],
            "ready": receipt["ready"], "policyCurrent": policy_current,
            "ageCurrent": age_current, "ageSeconds": round(age_seconds, 3),
            "currentReady": bool(receipt["ready"] and policy_current and age_current),
        }
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"ok": False, "signatureValid": False, "receiptValid": False, "currentReady": False, "error": str(exc)}


class Store:
    def __init__(self, evidence_root, secret, *, retention=200, max_age_seconds=7 * 86400, owner_uid=None, owner_gid=None):
        self.evidence_root = pathlib.Path(evidence_root)
        self.secret = bytes(secret)
        self.retention = max(10, min(int(retention), 2000))
        self.max_age_seconds = max(300, min(int(max_age_seconds), 90 * 86400))
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None

    def _secure(self, path):
        path = pathlib.Path(path)
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(path, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)

    def initialize(self):
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self._secure(self.evidence_root)
        for path in self._paths(initializing=True):
            self._secure(path)

    def _paths(self, initializing=False):
        if not initializing:
            self.initialize()
        return sorted(
            (path for path in self.evidence_root.glob("community-canary-*.signed.json") if path.is_file() and not path.is_symlink()),
            key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True,
        )

    def _write(self, path, document):
        temporary = path.with_suffix(path.suffix + ".tmp-" + secrets.token_hex(8))
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(document, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._secure(temporary)
            temporary.replace(path)
            self._secure(path)
        finally:
            temporary.unlink(missing_ok=True)

    def record(self, receipt, completed_epoch):
        document = signed_document(receipt, self.secret, generated_at=completed_epoch)
        path = self.evidence_root / f"{receipt['id']}.signed.json"
        with LOCK:
            self.initialize()
            self._write(path, document)
            for stale in self._paths()[self.retention:]:
                stale.unlink(missing_ok=True)
        return {"document": document, "evidencePath": str(path), "verification": verify_signed_document(document, self.secret)}

    def status(self, policy_sha256, limit=20, now=None):
        all_rows = []
        for path in self._paths():
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                verification = verify_signed_document(
                    document, self.secret, current_policy_sha256=policy_sha256,
                    max_age_seconds=self.max_age_seconds, now=now,
                )
                receipt = document.get("receipt") or {}
                row = {
                    "id": receipt.get("id"), "completedAt": receipt.get("completedAt"),
                    "durationMs": receipt.get("durationMs"), "ready": bool(receipt.get("ready")),
                    "policySha256": receipt.get("policySha256"), "checks": receipt.get("checks"),
                    "evidence": receipt.get("evidence"), "isolation": receipt.get("isolation"),
                    "receiptSha256": receipt.get("receiptSha256"), "file": path.name,
                    "verification": verification,
                }
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                row = {"id": path.stem, "ready": False, "file": path.name, "verification": {"ok": False, "currentReady": False, "error": str(exc)}}
            all_rows.append(row)
        rows = all_rows[:max(1, min(int(limit), self.retention))]
        latest = all_rows[0] if all_rows else None
        return {
            "ok": all((row.get("verification") or {}).get("ok") for row in all_rows),
            "currentReady": bool(latest and (latest.get("verification") or {}).get("currentReady")),
            "latest": latest, "receipts": rows, "retention": self.retention,
            "maxAgeSeconds": self.max_age_seconds,
            "summary": {"retained": len(all_rows), "returned": len(rows)},
        }

    def prometheus(self, policy_sha256, now=None):
        status = self.status(policy_sha256, now=now)
        latest = status.get("latest") or {}
        verification = latest.get("verification") or {}
        completed = epoch(latest["completedAt"]) if latest.get("completedAt") and verification.get("ok") else "NaN"
        return "\n".join([
            f"dash_community_canary_collector_up {1 if status.get('ok') else 0}",
            f"dash_community_canary_current_ready {1 if status.get('currentReady') else 0}",
            f"dash_community_canary_last_completion_timestamp_seconds {completed}",
            f"dash_community_canary_age_seconds {float(verification.get('ageSeconds') or 0):.3f}",
            f"dash_community_canary_retained_receipts {int((status.get('summary') or {}).get('retained') or 0)}",
        ]) + "\n"


def run_canary(config_path, receipt_store, *, principal_id="system", now=time.time):
    config_path = pathlib.Path(config_path)
    policy_sha = file_sha256(config_path)
    started_epoch = float(now())
    checks = {name: False for name in CHECK_NAMES}
    evidence = {
        "offers": 0, "tracks": 0, "ledgerEntries": 0, "deliveriesCompleted": 0,
        "purchaseIdempotent": False, "webhookIdempotent": False, "trackIdempotent": False,
    }
    temporary_removed = False
    temporary_database_created = False
    failure = None
    try:
        with tempfile.TemporaryDirectory(prefix="dash-community-canary-") as directory:
            root = pathlib.Path(directory)
            clock = [iso(started_epoch)]
            store = community_rewards.Store(root / "community.sqlite3", config_path, now=lambda: clock[0])
            initialized = store.initialize()
            temporary_database_created = store.database_path.is_file()
            offers = [row for row in initialized.get("offers", []) if row.get("enabled") and (row.get("stock") is None or int(row.get("stock") or 0) > 0)]
            tracks = [row for row in initialized.get("tracks", []) if row.get("enabled")]
            evidence["offers"], evidence["tracks"] = len(offers), len(tracks)
            checks["catalogLoaded"] = bool(initialized.get("enabled") and offers and tracks)
            if not checks["catalogLoaded"]:
                raise ValueError("active community policy requires at least one enabled in-stock offer and reward track")

            account_id = 9_223_372_036_854_770_000
            link = store.create_link_code(account_id)
            linked = store.redeem_link_code("dash-canary-discord", link["code"])
            checks["linkRoundTrip"] = linked.get("duneAccountId") == account_id and store.account_for_discord("dash-canary-discord") is not None

            webhook_payload = {"eventId": "dash-canary", "duneAccountId": account_id, "amount": 3}
            raw = canonical(webhook_payload).encode()
            webhook_secret = secrets.token_hex(32)
            timestamp = str(int(started_epoch))
            signature = hmac.new(webhook_secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
            checks["webhookSignature"] = community_rewards.verify_webhook(webhook_secret, timestamp, raw, signature, now_epoch=int(started_epoch))
            webhook = store.ingest_webhook("canary", "dash-canary", account_id, 3, webhook_payload)
            webhook_replay = store.ingest_webhook("canary", "dash-canary", account_id, 3, webhook_payload)
            evidence["webhookIdempotent"] = bool(webhook_replay.get("idempotent"))
            checks["webhookReplay"] = not webhook.get("idempotent") and evidence["webhookIdempotent"]

            offer = sorted(offers, key=lambda row: (int(row.get("price") or 0), row.get("id")))[0]
            credit_amount = max(1, int(offer.get("price") or 0) + 100)
            credit = store.credit(account_id, credit_amount, "canary", "canary:credit")
            credit_replay = store.credit(account_id, credit_amount, "canary", "canary:credit")
            checks["creditReplay"] = not credit.get("idempotent") and bool(credit_replay.get("idempotent"))
            purchase = store.purchase(account_id, offer["id"], 1, "canary:purchase")
            purchase_replay = store.purchase(account_id, offer["id"], 1, "canary:purchase")
            evidence["purchaseIdempotent"] = bool(purchase_replay.get("idempotent"))
            checks["purchaseReplay"] = not purchase.get("idempotent") and evidence["purchaseIdempotent"] and purchase_replay.get("id") == purchase.get("id")
            claimed = store.claim_delivery(purchase["deliveryId"])
            delivered = store.complete_delivery(claimed["id"], claimed["claim_token"], {"adapter": "synthetic", "gameWrite": False})
            checks["purchaseDelivery"] = delivered.get("status") == "delivered"
            evidence["deliveriesCompleted"] += int(checks["purchaseDelivery"])

            observed = int(started_epoch) + 10
            store.observe_playtime(account_id, True, observed, 60, 1, 120)
            accrued = store.observe_playtime(account_id, True, observed + 60, 60, 1, 120)
            accrued_replay = store.observe_playtime(account_id, True, observed + 60, 60, 1, 120)
            checks["playtimeAccrual"] = accrued.get("credited") == 1 and accrued_replay.get("credited") == 0

            engagement = community_rewards.engagement_config(community_rewards.load_config(config_path))
            precision = float(engagement.get("coordinatePrecision") or 10)
            minimum = float(engagement.get("minimumMovementDistance") or 0)
            policy = dict(engagement, enabled=True, hourly={"enabled": False}, daily={"enabled": False}, weekly={"enabled": False})
            store.observe_engagement(account_id, True, observed + 120, {"map": "Canary", "partitionId": 1, "x": 0, "y": 0, "z": 0}, policy)
            movement = store.observe_engagement(account_id, True, observed + 180, {"map": "Canary", "partitionId": 1, "x": minimum + precision * 2, "y": 0, "z": 0}, policy)
            checks["engagementMovement"] = bool(movement.get("active") and movement.get("moved") and int(movement.get("activeSeconds") or 0) == 60)

            track = sorted(tracks, key=lambda row: (row.get("id"), -int(row.get("version") or 0)))[0]
            threshold = int(track["levels"][0]["xp"])
            store.add_track_progress(account_id, track["id"], max(1, threshold), "canary:track")
            claim = store.claim_track_level(account_id, track["id"], 1)
            claim_replay = store.claim_track_level(account_id, track["id"], 1)
            evidence["trackIdempotent"] = bool(claim_replay.get("idempotent"))
            checks["trackReplay"] = not claim.get("idempotent") and evidence["trackIdempotent"] and claim_replay.get("deliveryId") == claim.get("deliveryId")
            track_delivery = store.claim_delivery(claim["deliveryId"])
            track_delivered = store.complete_delivery(track_delivery["id"], track_delivery["claim_token"], {"adapter": "synthetic", "gameWrite": False})
            checks["trackDelivery"] = track_delivered.get("status") == "delivered"
            evidence["deliveriesCompleted"] += int(checks["trackDelivery"])

            ledger = store.verify_ledger()
            evidence["ledgerEntries"] = int(ledger.get("entries") or 0)
            status = store.status(account_id)
            checks["ledgerIntegrity"] = bool(ledger.get("ok") and status.get("ledger", {}).get("ok") and status.get("deliveryCounts", {}).get("delivered") == 2)
        temporary_removed = not pathlib.Path(directory).exists()
    except Exception as exc:
        failure = str(exc)[-1000:]
        temporary_removed = "directory" not in locals() or not pathlib.Path(directory).exists()

    completed_epoch = float(now())
    isolation = dict(
        ISOLATION,
        temporaryDatabaseCreated=temporary_database_created,
        temporaryStateRemoved=temporary_removed,
    )
    ready = all(checks.values()) and isolation == ISOLATION and failure is None
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA,
        "id": "community-canary-" + secrets.token_hex(16),
        "principalId": str(principal_id or "system")[:128],
        "startedAt": iso(started_epoch), "completedAt": iso(completed_epoch),
        "durationMs": int(round((completed_epoch - started_epoch) * 1000)),
        "policySha256": policy_sha, "checks": checks, "evidence": evidence,
        "isolation": isolation, "ready": ready,
    }
    result = receipt_store.record(receipt, completed_epoch)
    result["error"] = failure
    return result
