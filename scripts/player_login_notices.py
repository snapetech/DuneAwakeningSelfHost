#!/usr/bin/env python3
"""Durable one-shot private notices delivered by the player-presence worker."""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
DEFAULT_PATH = "backups/admin-bot/player-login-notices.json"
DEFAULT_MESSAGE = (
    "Server notice: the former base at your old claim was transferred to a new owner "
    "because it was inactive. A backup of the prior server state is available on request; "
    "please contact a server admin if you want to discuss recovery."
)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def registry_path(path=None):
    candidate = pathlib.Path(path or os.environ.get("DUNE_PLAYER_PRESENCE_LOGIN_NOTICES_FILE", DEFAULT_PATH))
    return candidate if candidate.is_absolute() else ROOT / candidate


def _positive_int(value, field):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def normalize_notice(raw):
    if not isinstance(raw, dict):
        raise ValueError("each player login notice must be an object")
    account_id = _positive_int(raw.get("accountId", raw.get("account_id")), "accountId")
    message = str(raw.get("message") or DEFAULT_MESSAGE).strip()
    if not message:
        raise ValueError("message must not be empty")
    if len(message.encode("utf-8")) > 4096:
        raise ValueError("message must be at most 4096 UTF-8 bytes")
    return {
        "accountId": account_id,
        "message": message,
        "enabled": bool(raw.get("enabled", True)),
        "createdAt": raw.get("createdAt") or raw.get("created_at") or now_iso(),
        "updatedAt": raw.get("updatedAt") or raw.get("updated_at") or now_iso(),
    }


def empty_registry():
    return {"schemaVersion": SCHEMA_VERSION, "notices": {}}


def load_registry(path=None):
    target = registry_path(path)
    if not target.exists():
        return empty_registry()
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read login-notice registry {target}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("player login notice registry must be an object")
    if int(document.get("schemaVersion", SCHEMA_VERSION)) != SCHEMA_VERSION:
        raise ValueError("unsupported player login notice registry schema")
    raw_notices = document.get("notices", {})
    if isinstance(raw_notices, list):
        rows = raw_notices
    elif isinstance(raw_notices, dict):
        rows = list(raw_notices.values())
    else:
        raise ValueError("player login notice registry notices must be an object or array")
    notices = {}
    for raw in rows:
        notice = normalize_notice(raw)
        notices[str(notice["accountId"])] = notice
    return {"schemaVersion": SCHEMA_VERSION, "notices": notices}


def save_registry(document, path=None):
    target = registry_path(path)
    raw_collection = (document or {}).get("notices", {})
    raw_rows = raw_collection.values() if isinstance(raw_collection, dict) else raw_collection
    notices = {}
    for raw in raw_rows or []:
        notice = normalize_notice(raw)
        notices[str(notice["accountId"])] = notice
    normalized = {"schemaVersion": SCHEMA_VERSION, "notices": notices}
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(target)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return normalized


def upsert_notice(account_id, message=DEFAULT_MESSAGE, path=None):
    document = load_registry(path)
    key = str(_positive_int(account_id, "accountId"))
    prior = document["notices"].get(key, {})
    notice = normalize_notice({
        "accountId": key,
        "message": message,
        "enabled": True,
        "createdAt": prior.get("createdAt") or now_iso(),
        "updatedAt": now_iso(),
    })
    document["notices"][key] = notice
    save_registry(document, path)
    return notice


def remove_notice(account_id, path=None):
    document = load_registry(path)
    key = str(_positive_int(account_id, "accountId"))
    removed = document["notices"].pop(key, None)
    save_registry(document, path)
    return removed


def list_notices(path=None):
    return sorted(load_registry(path)["notices"].values(), key=lambda row: row["accountId"])


def config_fingerprint(notice):
    payload = {
        "accountId": int(notice["accountId"]),
        "message": str(notice["message"]),
        "createdAt": str(notice.get("createdAt") or ""),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def merge_runtime(notices, runtime_state):
    runtime = (runtime_state or {}).get("playerLoginNotices", {})
    online = (runtime_state or {}).get("onlinePlayers", {})
    rows = []
    for notice in notices:
        row = dict(notice)
        state = runtime.get(str(notice["accountId"]), {}) if isinstance(runtime, dict) else {}
        player = online.get(str(notice["accountId"]), {}) if isinstance(online, dict) else {}
        row.update({
            "active": bool(state.get("active", notice.get("enabled", True))),
            "deliveredAt": state.get("deliveredAt"),
            "lastAttemptAt": state.get("lastAttemptAt"),
            "lastStatus": state.get("lastStatus"),
            "online": str(notice["accountId"]) in online,
            "playerName": player.get("name") if isinstance(player, dict) else None,
        })
        rows.append(row)
    return rows
