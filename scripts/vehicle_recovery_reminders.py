#!/usr/bin/env python3
"""Shared durable registry for parked-vehicle recovery reminders."""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
MAX_VEHICLES = 20
DEFAULT_MESSAGE = (
    "Your parked ornithopters are preserved in the server's native vehicle recovery queue. "
    "When you return, please contact a server admin so we can recover them for you."
)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def registry_path(path=None):
    if path:
        candidate = pathlib.Path(path)
    else:
        candidate = pathlib.Path(os.environ.get(
            "DUNE_PLAYER_PRESENCE_VEHICLE_RECOVERY_REMINDERS_FILE",
            "backups/admin-bot/vehicle-recovery-reminders.json",
        ))
    return candidate if candidate.is_absolute() else ROOT / candidate


def _positive(value, field):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def _vehicle_ids(value):
    if isinstance(value, str):
        value = [part for part in value.split(",") if part.strip()]
    result = []
    for raw in value or []:
        parsed = _positive(raw, "vehicleId")
        if parsed not in result:
            result.append(parsed)
    if not result:
        raise ValueError("vehicleIds must contain at least one vehicle id")
    if len(result) > MAX_VEHICLES:
        raise ValueError(f"vehicleIds may contain at most {MAX_VEHICLES} ids")
    return result


def normalize_reminder(raw):
    if not isinstance(raw, dict):
        raise ValueError("each vehicle-recovery reminder must be an object")
    account_id = _positive(raw.get("accountId", raw.get("account_id")), "accountId")
    vehicle_ids = _vehicle_ids(raw.get("vehicleIds", raw.get("vehicle_ids")))
    message = str(raw.get("message") or DEFAULT_MESSAGE).strip()
    if not message:
        raise ValueError("message must not be empty")
    if len(message.encode("utf-8")) > 4096:
        raise ValueError("message must be at most 4096 UTF-8 bytes")
    return {
        "accountId": account_id,
        "vehicleIds": vehicle_ids,
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
        raise ValueError(f"could not read vehicle reminder registry {target}: {exc}") from exc
    if not isinstance(document, dict) or int(document.get("schemaVersion", SCHEMA_VERSION)) != SCHEMA_VERSION:
        raise ValueError("unsupported vehicle-recovery reminder registry schema")
    raw = document.get("reminders", {})
    rows = list(raw.values()) if isinstance(raw, dict) else raw if isinstance(raw, list) else None
    if rows is None:
        raise ValueError("vehicle-recovery reminder registry reminders must be an object or array")
    reminders = {}
    for item in rows:
        reminder = normalize_reminder(item)
        reminders[str(reminder["accountId"])] = reminder
    return {"schemaVersion": SCHEMA_VERSION, "reminders": reminders}


def save_registry(document, path=None):
    target = registry_path(path)
    raw = (document or {}).get("reminders", {})
    rows = raw.values() if isinstance(raw, dict) else raw
    reminders = {}
    for item in rows or []:
        reminder = normalize_reminder(item)
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


def upsert_reminder(account_id, vehicle_ids, message=DEFAULT_MESSAGE, path=None):
    document = load_registry(path)
    account_id = _positive(account_id, "accountId")
    key = str(account_id)
    prior = document["reminders"].get(key, {})
    reminder = normalize_reminder({
        "accountId": account_id,
        "vehicleIds": vehicle_ids,
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
    key = str(_positive(account_id, "accountId"))
    removed = document["reminders"].pop(key, None)
    save_registry(document, path)
    return removed


def list_reminders(path=None):
    return sorted(load_registry(path)["reminders"].values(), key=lambda row: row["accountId"])


def config_fingerprint(reminder):
    return json.dumps({
        "accountId": int(reminder["accountId"]),
        "vehicleIds": _vehicle_ids(reminder["vehicleIds"]),
        "message": str(reminder["message"]),
    }, sort_keys=True, separators=(",", ":"))


def status_sql(reminder):
    account_id = _positive(reminder["accountId"], "accountId")
    vehicle_ids = _vehicle_ids(reminder["vehicleIds"])
    ids_sql = "array[" + ",".join(str(value) for value in vehicle_ids) + "]::bigint[]"
    return f"""
    select jsonb_agg(jsonb_build_object(
      'vehicleId', target.vehicle_id,
      'actorExists', exists(select 1 from dune.actors a where a.id=target.vehicle_id),
      'backupExists', exists(
        select 1 from dune.backup_vehicles bv
        join dune.player_state ps on ps.id=bv.character_id
        where bv.vehicle_id=target.vehicle_id and ps.account_id={account_id}
      ),
      'vehicleBackupState', exists(
        select 1 from dune.actor_state ast
        where ast.actor_id=target.vehicle_id and ast.state='VehicleBackup'
      ),
      'recoveryExists', exists(
        select 1 from dune.recovered_vehicles rv
        join dune.player_state ps on ps.id=rv.character_id
        where rv.vehicle_id=target.vehicle_id and ps.account_id={account_id}
      ),
      'vehicleRecoveryState', exists(
        select 1 from dune.actor_state ast
        where ast.actor_id=target.vehicle_id and ast.state='VehicleRecovery'
      ),
      'ownerActive', exists(
        select 1 from dune.permission_actor_rank par
        join dune.player_state ps on ps.player_controller_id=par.player_id
        where par.permission_actor_id=target.vehicle_id and par.rank=1 and ps.account_id={account_id}
      ),
      'restored', (
        exists(select 1 from dune.actors a where a.id=target.vehicle_id)
        and not exists(
          select 1 from dune.backup_vehicles bv
          join dune.player_state ps on ps.id=bv.character_id
          where bv.vehicle_id=target.vehicle_id and ps.account_id={account_id}
        )
        and not exists(
          select 1 from dune.recovered_vehicles rv
          join dune.player_state ps on ps.id=rv.character_id
          where rv.vehicle_id=target.vehicle_id and ps.account_id={account_id}
        )
        and not exists(select 1 from dune.actor_state ast where ast.actor_id=target.vehicle_id)
        and exists(
          select 1 from dune.permission_actor_rank par
          join dune.player_state ps on ps.player_controller_id=par.player_id
          where par.permission_actor_id=target.vehicle_id and par.rank=1 and ps.account_id={account_id}
        )
      )
    ) order by target.vehicle_id)::text
    from unnest({ids_sql}) as target(vehicle_id);
    """


def parse_status_output(output):
    try:
        rows = json.loads(str(output or "").strip() or "[]")
    except json.JSONDecodeError:
        return {"ok": False, "restored": False, "error": "vehicle recovery status query returned invalid JSON", "vehicles": []}
    if not isinstance(rows, list):
        return {"ok": False, "restored": False, "error": "vehicle recovery status query returned an unexpected shape", "vehicles": []}
    return {"ok": True, "restored": bool(rows) and all(bool(row.get("restored")) for row in rows), "vehicles": rows}


def merge_runtime(reminders, runtime_state):
    runtime = (runtime_state or {}).get("vehicleRecoveryReminders", {})
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
