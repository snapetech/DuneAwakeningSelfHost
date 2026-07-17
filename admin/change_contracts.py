"""Signed, short-lived blast-radius contracts for governed admin mutations."""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
import secrets
import threading
import time

import change_approvals


SCHEMA_VERSION = 1
TOKEN_PREFIX = "dash-change-v1"
MAX_TOKEN_BYTES = 24 * 1024
MIN_TTL_SECONDS = 30
MAX_TTL_SECONDS = 300


def _impact(*scopes, backup="conditional", reversibility="conditional",
            restart="none", player_disruption=False, map_lifecycle=False,
            safeguards=()):
    return {
        "scopes": list(scopes),
        "backup": backup,
        "reversibility": reversibility,
        "restartImpact": restart,
        "playerDisruption": bool(player_disruption),
        "mapLifecycle": bool(map_lifecycle),
        "safeguards": list(safeguards),
    }


# Every body-aware policy in change_approvals must have an impact contract.  The
# focused test suite intentionally fails if the two registries drift apart.
IMPACTS = {
    "/api/ops/backups/restore": _impact(
        "database", "saved-state", "configuration", "service-lifecycle",
        backup="required", reversibility="backup-restore", restart="full-farm",
        player_disruption=True, map_lifecycle=True,
        safeguards=("verified source backup", "automatic pre-restore backup", "stopped writers", "post-start hooks")),
    "/api/ops/database/row": _impact(
        "database", "game-state", backup="required", reversibility="backup-restore",
        safeguards=("primary-key predicate", "bounded row update", "database backup")),
    "/api/ops/database/password": _impact(
        "database", "credentials", "service-connectivity", backup="required",
        reversibility="manual-secret-rotation", restart="dependent-services",
        player_disruption=True, safeguards=("database backup", "coordinated credential update")),
    "/api/ops/database/query": _impact(
        "database", "game-state", backup="required", reversibility="unknown",
        safeguards=("single-statement parser", "explicit write confirmation", "database backup")),
    "/api/ops/updates": _impact(
        "software", "service-lifecycle", "game-build", backup="required",
        reversibility="release-rollback", restart="candidate-dependent",
        player_disruption=True, map_lifecycle=True,
        safeguards=("candidate-bound readiness receipt", "verified backup", "deployment assurance")),
    "/api/ops/restore-drill": _impact(
        "backup-proof", "disposable-container", backup="none", reversibility="automatic-cleanup",
        safeguards=("network none", "copied source", "bounded resources", "mandatory cleanup")),
    "/api/ops/rabbitmq-restore-drill": _impact(
        "backup-proof", "rabbitmq-copied-state", "disposable-container", backup="none",
        reversibility="automatic-cleanup",
        safeguards=("network none", "no published ports", "no live broker mounts", "sequential brokers", "mandatory cleanup")),
    "/api/ops/audit/reconcile": _impact(
        "audit-evidence", "privileged-request-lifecycle", backup="none",
        reversibility="append-only-correction",
        safeguards=("verified ledger chain", "open-request check", "explicit outcome", "append-only reconciliation evidence")),
    "/api/settings/env": _impact(
        "configuration", "credentials", "service-runtime", backup="required",
        reversibility="file-backup", restart="deferred-dependent-services",
        player_disruption=True, map_lifecycle=True,
        safeguards=("allowlisted keys", "secret redaction", "file backup")),
    "/api/admin/base-retirement": _impact(
        "world-state", "base", "database", backup="required",
        reversibility="native-base-backup", player_disruption=True,
        safeguards=("offline owner", "compare-and-swap fingerprint", "full database backup", "native base archive")),
    "/api/admin/character-slots/execute": _impact(
        "player-state", "account", "database", backup="required",
        reversibility="receipted-rollback", player_disruption=True,
        safeguards=("offline accounts", "locked recheck", "database backup", "rollback receipt")),
    "/api/admin/player-identity-integrity": _impact(
        "player-state", "account", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("canonical identity preview", "offline row locks", "fingerprint-bound target", "native delete function", "orphan-only cleanup predicate", "database backup", "post-write verification", "private receipt")),
    "/api/admin/blueprints": _impact(
        "player-state", "blueprint", "database", backup="required",
        reversibility="rollback-archive", player_disruption=True,
        safeguards=("schema validation", "transaction", "database backup", "post-write verification")),
    "/api/admin/cosmetics": _impact(
        "player-state", "cosmetics", "database", backup="required",
        reversibility="receipted-rollback", player_disruption=True,
        safeguards=("catalog validation", "database backup", "before/after digest", "rollback receipt")),
    "/api/presets/gameplay": _impact(
        "configuration", "world-rules", backup="required", reversibility="file-backup",
        restart="map-restart-required", player_disruption=True, map_lifecycle=True,
        safeguards=("typed preset", "configuration backup", "Coriolis/Landsraad invariant")),
    "/api/admin/player-maintenance": _impact(
        "player-state", "progression", "database", backup="required",
        reversibility="receipted-rollback", player_disruption=True,
        safeguards=("offline player", "compare-and-swap digest", "database backup", "rollback receipt")),
    "/api/admin/player-runtime-action": _impact(
        "player-runtime", "game-command", backup="none", reversibility="action-dependent",
        player_disruption=True, safeguards=("catalog-backed command", "online-state contract", "RabbitMQ authentication")),
    "/api/admin/player-recovery/offline-teleport": _impact(
        "player-state", "location", "database", backup="required",
        reversibility="manual-teleport", player_disruption=True,
        safeguards=("explicitly offline player", "bounded finite coordinates", "fingerprint-bound preview", "advisory and row locks", "full database backup", "native game function", "post-write verification", "private receipt", "isolated semantic restore proof")),
    "/api/admin/player-recovery/life-state": _impact(
        "player-state", "life-state", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("explicitly offline player", "dead-state allowlist", "fingerprint-bound preview", "advisory and row locks", "full database backup", "native game function", "post-write verification", "private receipt", "isolated semantic restore proof")),
    "/api/admin/character-backups": _impact(
        "player-state", "account", "character-transfer", "database", backup="required-for-restore",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("dual offline evidence", "private SHA-256 snapshot", "patch checksum binding", "fingerprint-bound preview", "advisory and row locks", "full database backup before restore", "native game functions", "exact orphan cleanup", "post-write identity verification", "private receipt", "isolated semantic restore proof")),
    "/api/admin/vehicle": _impact(
        "vehicle-state", "database", backup="required", reversibility="backup-restore",
        player_disruption=True, safeguards=("ownership validation", "database backup", "transaction")),
    "/api/admin/item": _impact(
        "player-state", "inventory", "economy", "database", backup="required",
        reversibility="item-delete", player_disruption=True,
        safeguards=("catalog validation", "ownership validation", "database backup", "post-write verification")),
    "/api/admin/item/delete": _impact(
        "player-state", "inventory", "economy", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("ownership validation", "bounded delete", "database backup")),
    "/api/admin/item/stack": _impact(
        "player-state", "inventory", "economy", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("ownership validation", "stack bounds", "database backup")),
    "/api/admin/currency": _impact(
        "player-state", "economy", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("currency allowlist", "bounded amount", "database backup", "transaction")),
    "/api/admin/solari/inventory": _impact(
        "player-state", "economy", "inventory", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("inventory ownership", "bounded amount", "database backup", "transaction")),
    "/api/admin/solari/bank": _impact(
        "player-state", "economy", "bank", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("account validation", "bounded amount", "database backup", "transaction")),
    "/api/admin/xp": _impact(
        "player-state", "progression", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("track validation", "bounded XP", "database backup", "transaction")),
    "/api/admin/bundle": _impact(
        "player-state", "inventory", "economy", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("atomic preflight", "database backup", "transaction", "post-write verification")),
    "/api/admin/landsraad": _impact(
        "world-state", "landsraad", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("term/task validation", "database backup", "transaction", "aggregate recomputation")),
    "/api/admin/faction-reputation": _impact(
        "player-state", "faction", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("faction validation", "bounded value", "database backup", "transaction")),
    "/api/admin/faction": _impact(
        "player-state", "faction", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("faction validation", "database backup", "transaction")),
    "/api/admin/journey": _impact(
        "player-state", "progression", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("journey validation", "database backup", "transaction")),
    "/api/admin/guild": _impact(
        "world-state", "guild", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("guild/member validation", "database backup", "transaction")),
    "/api/admin/marker": _impact(
        "world-state", "markers", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("bounded marker selection", "database backup", "transaction")),
    "/api/admin/landclaim": _impact(
        "world-state", "landclaim", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("claim validation", "database backup", "transaction")),
    "/api/admin/permission": _impact(
        "world-state", "permissions", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("actor validation", "permission bounds", "database backup", "transaction")),
    "/api/admin/access-code": _impact(
        "player-state", "access-control", "database", backup="required",
        reversibility="compensating-write", player_disruption=True,
        safeguards=("player validation", "database backup", "transaction")),
    "/api/admin/respawn-location": _impact(
        "player-state", "location", "database", backup="required",
        reversibility="backup-restore", player_disruption=True,
        safeguards=("player validation", "database backup", "transaction")),
    "/api/moderation": _impact(
        "player-access", "moderation", "game-command", backup="none",
        reversibility="policy-reversal", player_disruption=True,
        safeguards=("identity selectors", "expiry bounds", "enforcement history")),
    "/api/ops/services/control": _impact(
        "service-lifecycle", backup="conditional", reversibility="inverse-control",
        restart="targeted-service", player_disruption=True, map_lifecycle=True,
        safeguards=("project service allowlist", "stateful-service gate", "post-start hooks")),
    "/api/ops/memory": _impact(
        "resource-policy", "service-runtime", backup="automatic-state-file",
        reversibility="prior-policy", restart="action-dependent", player_disruption=True,
        map_lifecycle=True, safeguards=("bounded memory limits", "pressure guardrails", "retained prior policy")),
    "/api/ops/autoscaler": _impact(
        "resource-policy", "map-lifecycle", backup="automatic-state-file",
        reversibility="prior-policy", restart="dynamic-map-lifecycle", player_disruption=True,
        map_lifecycle=True, safeguards=("mode bounds", "pressure budget", "post-start hooks", "retained prior policy")),
    "/api/ops/restart": _impact(
        "service-lifecycle", "player-session", backup="conditional",
        reversibility="cancel-before-execution", restart="scheduled-farm-or-target",
        player_disruption=True, map_lifecycle=True,
        safeguards=("announcement cadence", "online-player visibility", "target-aware restart path", "post-start hooks")),
    "/api/admin/gm/execute": _impact(
        "game-command", "runtime-state", backup="none", reversibility="unknown",
        player_disruption=True, safeguards=("command catalog", "command authentication", "explicit confirmation")),
}

if set(IMPACTS) != set(change_approvals.POLICIES):
    missing = sorted(set(change_approvals.POLICIES) - set(IMPACTS))
    extra = sorted(set(IMPACTS) - set(change_approvals.POLICIES))
    raise RuntimeError(f"change contract impact registry drift: missing={missing} extra={extra}")
for _path, _metadata in IMPACTS.items():
    if not _metadata["scopes"] or len(_metadata["scopes"]) != len(set(_metadata["scopes"])):
        raise RuntimeError(f"change contract scopes are empty or duplicated: {_path}")
    if not _metadata["safeguards"]:
        raise RuntimeError(f"change contract safeguards are empty: {_path}")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def body_sha256(body):
    if not isinstance(body, dict):
        raise ValueError("change contract request body must be an object")
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def _b64encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value):
    if not isinstance(value, str) or not value:
        raise ValueError("change contract token segment is empty")
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def _iso(timestamp):
    return dt.datetime.fromtimestamp(float(timestamp), dt.timezone.utc).isoformat()


def _principal_id(principal):
    value = str((principal or {}).get("id") or "").strip()
    if not value or len(value) > 128 or any(ord(char) < 32 for char in value):
        raise PermissionError("change contracts require an authenticated operator identity")
    return value


def policy_revision():
    public = {
        path: {
            "risk": change_approvals.POLICIES[path][0],
            "label": change_approvals.POLICIES[path][1],
            "impact": IMPACTS[path],
        }
        for path in sorted(IMPACTS)
    }
    return hashlib.sha256(canonical(public).encode("utf-8")).hexdigest()


def public_policies():
    return [
        {
            "path": path,
            "risk": change_approvals.POLICIES[path][0],
            "label": change_approvals.POLICIES[path][1],
            "impact": IMPACTS[path],
        }
        for path in sorted(IMPACTS)
    ]


def _warnings(impact, body):
    warnings = []
    if impact["reversibility"] in {"unknown", "action-dependent"}:
        warnings.append("The exact operation may not have an automatic inverse.")
    if impact["mapLifecycle"]:
        warnings.append("This operation can affect game-map lifecycle or restart continuity.")
    if impact["playerDisruption"]:
        warnings.append("This operation can affect an active or returning player.")
    if impact["backup"] == "none":
        warnings.append("This runtime operation does not create a database backup.")
    if not str(body.get("confirm") or "").strip():
        warnings.append("No generic confirmation field is present; route-specific validation still applies.")
    return warnings


def contract_for(path, body, principal, capability, *, now=None, ttl_seconds=120):
    path = str(path or "").split("?", 1)[0]
    policy = change_approvals.policy_for(path, body)
    if not policy:
        return {"schemaVersion": SCHEMA_VERSION, "governed": False, "path": path}
    now = float(time.time() if now is None else now)
    ttl = max(MIN_TTL_SECONDS, min(int(ttl_seconds), MAX_TTL_SECONDS))
    impact = IMPACTS[path]
    dry_run = change_approvals._dry_run(body, default=True)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "governed": True,
        "contractId": "change-" + secrets.token_hex(16),
        "issuedAt": _iso(now),
        "expiresAt": _iso(now + ttl),
        "issuedAtEpoch": now,
        "expiresAtEpoch": now + ttl,
        "policyRevision": policy_revision(),
        "principalId": _principal_id(principal),
        "target": {
            "path": path,
            "capability": str(capability),
            "bodySha256": body_sha256(body),
            "action": str(body.get("action") or "").strip().lower() or None,
            "dryRun": bool(dry_run),
        },
        "change": {"label": policy["label"], "risk": policy["risk"]},
        "impact": impact,
        "warnings": _warnings(impact, body),
    }


def issue(path, body, principal, capability, secret, *, now=None, ttl_seconds=120):
    if not isinstance(secret, (bytes, bytearray)) or len(secret) != 32:
        raise ValueError("change contract signing secret must contain exactly 32 bytes")
    contract = contract_for(path, body, principal, capability, now=now, ttl_seconds=ttl_seconds)
    if not contract["governed"]:
        return {"contract": contract, "token": None}
    payload = canonical(contract).encode("utf-8")
    signature = hmac.new(bytes(secret), payload, hashlib.sha256).digest()
    token = f"{TOKEN_PREFIX}.{_b64encode(payload)}.{_b64encode(signature)}"
    if len(token.encode("ascii")) > MAX_TOKEN_BYTES:
        raise ValueError("change contract token exceeds the size limit")
    return {"contract": contract, "token": token}


def verify(token, path, body, principal, capability, secret, *, now=None):
    if not isinstance(secret, (bytes, bytearray)) or len(secret) != 32:
        raise ValueError("change contract signing secret must contain exactly 32 bytes")
    if not isinstance(token, str) or len(token.encode("utf-8")) > MAX_TOKEN_BYTES:
        raise PermissionError("a valid bounded change contract token is required")
    try:
        prefix, encoded_payload, encoded_signature = token.split(".")
        if prefix != TOKEN_PREFIX:
            raise ValueError("prefix")
        payload = _b64decode(encoded_payload)
        signature = _b64decode(encoded_signature)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise PermissionError("change contract token is malformed") from exc
    if _b64encode(payload) != encoded_payload:
        raise PermissionError("change contract token payload encoding is non-canonical")
    if _b64encode(signature) != encoded_signature:
        raise PermissionError("change contract signature is invalid")
    expected = hmac.new(bytes(secret), payload, hashlib.sha256).digest()
    if len(signature) != 32 or not hmac.compare_digest(signature, expected):
        raise PermissionError("change contract signature is invalid")
    try:
        contract = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PermissionError("change contract payload is invalid") from exc
    required = {
        "schemaVersion", "governed", "contractId", "issuedAt", "expiresAt",
        "issuedAtEpoch", "expiresAtEpoch", "policyRevision", "principalId",
        "target", "change", "impact", "warnings",
    }
    if not isinstance(contract, dict) or set(contract) != required or contract.get("schemaVersion") != SCHEMA_VERSION or contract.get("governed") is not True:
        raise PermissionError("change contract schema is invalid")
    current = float(time.time() if now is None else now)
    issued = float(contract["issuedAtEpoch"])
    expires = float(contract["expiresAtEpoch"])
    if issued > current + 10:
        raise PermissionError("change contract was issued in the future")
    if expires <= current:
        raise PermissionError("change contract has expired; review a fresh impact contract")
    if expires - issued > MAX_TTL_SECONDS or expires <= issued:
        raise PermissionError("change contract lifetime is invalid")
    fresh = contract_for(path, body, principal, capability, now=issued, ttl_seconds=round(expires - issued))
    comparisons = {
        "policy revision": contract.get("policyRevision") == fresh.get("policyRevision"),
        "operator": contract.get("principalId") == fresh.get("principalId"),
        "target": contract.get("target") == fresh.get("target"),
        "risk": contract.get("change") == fresh.get("change"),
        "impact": contract.get("impact") == fresh.get("impact"),
        "warnings": contract.get("warnings") == fresh.get("warnings"),
        "issue time": contract.get("issuedAt") == _iso(issued),
        "expiry time": contract.get("expiresAt") == _iso(expires),
    }
    failed = [name for name, ok in comparisons.items() if not ok]
    if failed:
        raise PermissionError("change contract no longer matches " + ", ".join(failed))
    return contract


class ReplayGuard:
    """Process-local atomic one-attempt consumption for reviewed contracts."""

    def __init__(self, clock=None):
        self.clock = clock or time.time
        self._consumed = {}
        self._lock = threading.Lock()

    def consume(self, contract):
        contract_id = str((contract or {}).get("contractId") or "")
        suffix = contract_id[7:] if contract_id.startswith("change-") else ""
        if len(suffix) != 32 or any(char not in "0123456789abcdef" for char in suffix):
            raise PermissionError("change contract ID is invalid")
        expires = float(contract.get("expiresAtEpoch") or 0)
        now = float(self.clock())
        with self._lock:
            self._consumed = {
                key: expiry for key, expiry in self._consumed.items()
                if float(expiry) > now
            }
            if contract_id in self._consumed:
                raise PermissionError("change contract was already consumed; review a fresh contract")
            self._consumed[contract_id] = expires
        return contract

    def size(self):
        with self._lock:
            return len(self._consumed)
