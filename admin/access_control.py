"""Hashed-token identities and capability authorization for the DASH admin API."""

import hashlib
import hmac
import json
import pathlib
import re


ROLE_CAPABILITIES = {
    "observer": {"read"},
    "operator": {"read", "operations.write"},
    "moderator": {"read", "operations.write", "players.write", "community.write", "moderation.write", "creator.write"},
    "administrator": {
        "read",
        "operations.write",
        "players.write",
        "economy.write",
        "world.write",
        "configuration.write",
        "infrastructure.write",
        "community.write",
        "moderation.write",
        "creator.write",
    },
    "owner": {"*"},
}

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,63}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def token_hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def validate_document(document):
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("admin access file must be a version 1 JSON object")
    users = document.get("users")
    if not isinstance(users, list):
        raise ValueError("admin access file users must be an array")
    seen = set()
    normalized = []
    for row in users:
        if not isinstance(row, dict):
            raise ValueError("each admin access user must be an object")
        user_id = str(row.get("id") or "").strip().lower()
        if not ID_PATTERN.fullmatch(user_id) or user_id in seen:
            raise ValueError(f"invalid or duplicate admin access id: {user_id!r}")
        seen.add(user_id)
        digest = str(row.get("tokenSha256") or "").strip().lower()
        if not HASH_PATTERN.fullmatch(digest):
            raise ValueError(f"user {user_id} requires a lowercase SHA-256 token digest")
        role = str(row.get("role") or "").strip().lower()
        if role not in ROLE_CAPABILITIES:
            raise ValueError(f"user {user_id} has unknown role: {role!r}")
        extra = row.get("capabilities") or []
        if not isinstance(extra, list) or any(not isinstance(item, str) or not item.strip() for item in extra):
            raise ValueError(f"user {user_id} capabilities must be non-empty strings")
        capabilities = ROLE_CAPABILITIES[role] | {item.strip() for item in extra}
        normalized.append({
            "id": user_id,
            "displayName": str(row.get("displayName") or user_id)[:128],
            "enabled": bool(row.get("enabled", True)),
            "role": role,
            "capabilities": sorted(capabilities),
            "tokenSha256": digest,
        })
    return normalized


def load_users(path):
    path = pathlib.Path(path)
    if not path.exists():
        return []
    return validate_document(json.loads(path.read_text(encoding="utf-8")))


def authenticate(path, token):
    if not token:
        return None
    candidate = token_hash(token)
    matched = None
    for user in load_users(path):
        equal = hmac.compare_digest(candidate, user["tokenSha256"])
        if equal and user["enabled"]:
            matched = {key: value for key, value in user.items() if key != "tokenSha256"}
    return matched


def principal_by_id(path, user_id):
    user_id = str(user_id or "").strip().lower()
    for user in load_users(path):
        if user["id"] == user_id and user["enabled"]:
            return {key: value for key, value in user.items() if key != "tokenSha256"}
    return None


def has_capability(principal, required):
    capabilities = set((principal or {}).get("capabilities") or [])
    return "*" in capabilities or required in capabilities


def authorize(principal, required):
    if not has_capability(principal, required):
        identity = (principal or {}).get("id", "unknown")
        raise PermissionError(f"admin identity {identity!r} lacks capability {required!r}")
    return principal


def required_capability(method, path):
    method = str(method or "GET").upper()
    path = str(path or "/").split("?", 1)[0]
    if method in {"GET", "HEAD", "OPTIONS"}:
        return "read"
    if path.endswith("/inspect") or path.endswith("/preview") or path in {
        "/api/ops/backups/verify",
        "/api/events/dry-run",
        "/api/admin/character-slots/plan",
        "/api/auth/logout",
    }:
        return "read"
    if path.startswith("/api/ops/database/") or path in {
        "/api/ops/backups/import",
        "/api/ops/backups/delete",
        "/api/ops/backups/restore",
        "/api/ops/restore-drill",
        "/api/ops/slo",
        "/api/ops/capacity",
        "/api/ops/desired-state",
        "/api/ops/updates",
    }:
        return "infrastructure.write"
    if path.startswith("/api/ops/") or path.startswith("/api/events"):
        return "operations.write"
    if path.startswith("/api/community/"):
        return "community.write"
    if path == "/api/moderation" or path.startswith("/api/moderation/"):
        return "moderation.write"
    if path.startswith("/api/creator/"):
        return "creator.write"
    if path.startswith("/api/settings/") or path.startswith("/api/presets/") or path == "/api/bootstrap" or path.startswith("/api/addons/"):
        return "configuration.write"
    if path.startswith("/api/admin/"):
        leaf = path[len("/api/admin/"):]
        if leaf.startswith(("artificial-exchange", "currency", "solari", "exchange", "vendor", "economy")):
            return "economy.write"
        if leaf.startswith(("guild", "marker", "landclaim", "landsraad", "faction", "world-state", "permission", "communinet", "tutorial", "base-retirement")):
            return "world.write"
        if leaf.startswith(("backup", "unsupported")):
            return "infrastructure.write"
        return "players.write"
    return "infrastructure.write"


def public_principal(principal):
    if not principal:
        return None
    return {key: principal.get(key) for key in ("id", "displayName", "role", "capabilities", "authMethod") if principal.get(key) is not None}
