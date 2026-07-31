#!/usr/bin/env python3
"""Shared durable registry for player base-recovery reminders.

The player-presence worker owns delivery and runtime status. This module owns
the small operator-managed registry so the CLI and admin panel use the same
records without duplicating their file format or validation rules.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
DEFAULT_MESSAGE = (
    "Mara, your base is preserved in the server's Base Reconstruction Tool backup. "
    "When you return, please contact a server admin so we can recover it for you."
)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def registry_path(path=None):
    if path:
        candidate = pathlib.Path(path)
    else:
        candidate = pathlib.Path(os.environ.get(
            "DUNE_PLAYER_PRESENCE_BASE_RECOVERY_REMINDERS_FILE",
            "backups/admin-bot/base-recovery-reminders.json",
        ))
    return candidate if candidate.is_absolute() else ROOT / candidate


def _positive_int(value, field):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def _field(raw, camel, snake):
    return raw.get(camel, raw.get(snake))


def normalize_reminder(raw):
    if not isinstance(raw, dict):
        raise ValueError("each base-recovery reminder must be an object")
    account_id = _positive_int(_field(raw, "accountId", "account_id"), "accountId")
    backup_id = _positive_int(_field(raw, "backupId", "backup_id"), "backupId")
    totem_id = _positive_int(_field(raw, "totemId", "totem_id"), "totemId")
    message = str(raw.get("message") or DEFAULT_MESSAGE).strip()
    if not message:
        raise ValueError("message must not be empty")
    if len(message.encode("utf-8")) > 4096:
        raise ValueError("message must be at most 4096 UTF-8 bytes")
    return {
        "accountId": account_id,
        "backupId": backup_id,
        "totemId": totem_id,
        "message": message,
        "enabled": bool(raw.get("enabled", True)),
        "createdAt": raw.get("createdAt") or raw.get("created_at") or now_iso(),
        "updatedAt": raw.get("updatedAt") or raw.get("updated_at") or now_iso(),
    }


def empty_registry():
    return {"schemaVersion": SCHEMA_VERSION, "reminders": {}}


def load_registry(path=None):
    target = registry_path(path)
    if not target.exists():
        return empty_registry()
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read reminder registry {target}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("base-recovery reminder registry must be an object")
    if int(document.get("schemaVersion", SCHEMA_VERSION)) != SCHEMA_VERSION:
        raise ValueError("unsupported base-recovery reminder registry schema")
    raw_reminders = document.get("reminders", {})
    if isinstance(raw_reminders, list):
        rows = raw_reminders
    elif isinstance(raw_reminders, dict):
        rows = list(raw_reminders.values())
    else:
        raise ValueError("base-recovery reminder registry reminders must be an object or array")
    reminders = {}
    for raw in rows:
        reminder = normalize_reminder(raw)
        reminders[str(reminder["accountId"])] = reminder
    return {"schemaVersion": SCHEMA_VERSION, "reminders": reminders}


def save_registry(document, path=None):
    target = registry_path(path)
    raw_collection = (document or {}).get("reminders", {})
    raw_rows = raw_collection.values() if isinstance(raw_collection, dict) else raw_collection
    reminders = {}
    for raw in raw_rows or []:
        reminder = normalize_reminder(raw)
        reminders[str(reminder["accountId"])] = reminder
    normalized = {"schemaVersion": SCHEMA_VERSION, "reminders": reminders}
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(target)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return normalized


def upsert_reminder(account_id, backup_id, totem_id, message=DEFAULT_MESSAGE, path=None):
    document = load_registry(path)
    key = str(_positive_int(account_id, "accountId"))
    prior = document["reminders"].get(key, {})
    reminder = normalize_reminder({
        "accountId": key,
        "backupId": backup_id,
        "totemId": totem_id,
        "message": message,
        "enabled": True,
        "createdAt": prior.get("createdAt") or now_iso(),
        "updatedAt": now_iso(),
    })
    document["reminders"][key] = reminder
    save_registry(document, path)
    return reminder


def remove_reminder(account_id, path=None):
    document = load_registry(path)
    key = str(_positive_int(account_id, "accountId"))
    removed = document["reminders"].pop(key, None)
    save_registry(document, path)
    return removed


def list_reminders(path=None):
    return sorted(load_registry(path)["reminders"].values(), key=lambda row: row["accountId"])


def config_fingerprint(reminder):
    payload = {
        "accountId": int(reminder["accountId"]),
        "backupId": int(reminder["backupId"]),
        "totemId": int(reminder["totemId"]),
        "message": str(reminder["message"]),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def status_sql(reminder):
    account_id = _positive_int(_field(reminder, "accountId", "account_id"), "accountId")
    backup_id = _positive_int(_field(reminder, "backupId", "backup_id"), "backupId")
    totem_id = _positive_int(_field(reminder, "totemId", "totem_id"), "totemId")
    return f"""
    select
      exists(
        select 1
        from dune.base_backups bb
        where bb.id = {backup_id}
      ) as backup_exists,
      exists(
        select 1
        from dune.permission_actor_rank par
        join dune.player_state ps on ps.player_controller_id = par.player_id
        where par.permission_actor_id = {totem_id}
          and ps.account_id = {account_id}
          and coalesce(par.rank, 0) > 0
      ) as owner_active,
      exists(
        select 1
        from dune.actor_state ast
        where ast.actor_id = {totem_id}
          and ast.state = 'BaseBackup'
      ) as totem_basebackup,
      exists(
        select 1
        from dune.totems t
        where t.id = {totem_id}
      ) as totem_exists;
    """


def parse_status_output(output):
    fields = str(output or "").strip().split("\t") if str(output or "").strip() else []
    if len(fields) != 4:
        return {"ok": False, "restored": False, "error": "base recovery status query returned an unexpected shape"}
    backup_exists, owner_active, totem_basebackup, totem_exists = [field.lower() == "t" for field in fields]
    return {
        "ok": True,
        "restored": (not backup_exists) and owner_active and totem_exists and not totem_basebackup,
        "backupExists": backup_exists,
        "ownerActive": owner_active,
        "totemBaseBackup": totem_basebackup,
        "totemExists": totem_exists,
    }


def merge_runtime(reminders, runtime_state):
    runtime = (runtime_state or {}).get("baseRecoveryReminders", {})
    online = (runtime_state or {}).get("onlinePlayers", {})
    rows = []
    for reminder in reminders:
        row = dict(reminder)
        state = runtime.get(str(reminder["accountId"]), {}) if isinstance(runtime, dict) else {}
        player = online.get(str(reminder["accountId"]), {}) if isinstance(online, dict) else {}
        row.update({
            "active": bool(state.get("active", reminder.get("enabled", True))),
            "restoredAt": state.get("restoredAt"),
            "lastStatus": state.get("lastStatus"),
            "lastStatusCheckedAt": state.get("lastStatusCheckedAt"),
            "lastAttemptAt": state.get("lastAttemptAt"),
            "lastSentAt": state.get("lastSentAt"),
            "lastSentSession": state.get("lastSentSession"),
            "online": str(reminder["accountId"]) in online,
            "playerName": player.get("name") if isinstance(player, dict) else None,
        })
        rows.append(row)
    return rows
