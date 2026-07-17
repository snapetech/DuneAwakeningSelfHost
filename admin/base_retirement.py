#!/usr/bin/env python3
"""Preview-bound, recoverable retirement of live Dune bases."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import secrets


MAX_SCAN = 1000
OFFLINE_STATES = {"offline", "disconnected", "inactive"}


def _positive(value, label):
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _owners(value):
    if isinstance(value, str):
        value = json.loads(value or "[]")
    result = []
    for raw in value or []:
        if not isinstance(raw, dict):
            continue
        result.append({
            "playerId": int(raw["playerId"]) if raw.get("playerId") is not None else None,
            "rank": int(raw["rank"]) if raw.get("rank") is not None else None,
            "accountId": int(raw["accountId"]) if raw.get("accountId") is not None else None,
            "characterName": str(raw.get("characterName") or ""),
            "onlineStatus": str(raw.get("onlineStatus") or "unknown"),
        })
    return sorted(result, key=lambda row: (row["rank"] is None, row["rank"] or 0, row["playerId"] or 0))


def _normalize(row):
    owners = _owners(row.get("owners"))
    owner_refs = len({owner["playerId"] for owner in owners if owner["playerId"] is not None})
    matched = len({owner["playerId"] for owner in owners if owner["accountId"] is not None})
    online = len({owner["playerId"] for owner in owners if owner["accountId"] is not None and owner["onlineStatus"].lower() not in OFFLINE_STATES})
    if not owner_refs:
        status = "unknown-owner"
    elif not matched:
        status = "orphaned"
    elif matched < owner_refs:
        status = "partial-missing"
    else:
        status = "owned"
    normalized = {
        "totemId": int(row["totem_id"]),
        "ownerEntityId": int(row["owner_entity_id"]),
        "fglEntityCount": int(row.get("fgl_entity_count") or 0),
        "actorName": str(row.get("actor_name") or f"Base {row['totem_id']}"),
        "map": str(row.get("map") or ""),
        "partitionId": int(row["partition_id"]) if row.get("partition_id") is not None else None,
        "partitionServerId": str(row.get("partition_server_id") or ""),
        "activeServerId": str(row.get("active_server_id") or ""),
        "partitionActive": bool(row.get("active_server_id")),
        "buildingCount": int(row.get("building_count") or 0),
        "pieceCount": int(row.get("piece_count") or 0),
        "placeableCount": int(row.get("placeable_count") or 0),
        "owners": owners,
        "ownerReferenceCount": owner_refs,
        "matchedOwnerCount": matched,
        "onlineOwnerCount": online,
        "existingBackupCount": int(row.get("existing_backup_count") or 0),
        "lastBackupTimestamp": int(row.get("last_backup_timestamp") or 0),
        "packupCooldownReady": int(row.get("last_backup_timestamp") or 0) == 0,
        "nativeFunctionAvailable": bool(row.get("native_function_available")),
        "status": status,
        "contentHashes": {
            "pieces": str(row.get("piece_hash") or ""),
            "placeables": str(row.get("placeable_hash") or ""),
            "permissions": str(row.get("permission_hash") or ""),
        },
    }
    fingerprint_value = {key: value for key, value in normalized.items() if key != "contentHashes"}
    fingerprint_value["contentHashes"] = normalized["contentHashes"]
    normalized["fingerprint"] = hashlib.sha256(_canonical(fingerprint_value).encode()).hexdigest()
    return normalized


def scan(query, limit=500, totem_id=None):
    limit = max(1, min(int(limit), MAX_SCAN))
    totem = _positive(totem_id, "totem id") if totem_id is not None else None
    rows = query("""
        with base as (
          select t.id as totem_id,t.last_backup_timestamp,afe.owner_entity_id,afe.fgl_entity_count,
                 coalesce(nullif(pa.actor_name,''),'Base ' || t.id::text) as actor_name,
                 a.map,a.partition_id,wp.server_id as partition_server_id,asi.server_id as active_server_id,
                 (select count(distinct bi.building_id) from dune.building_instances bi where bi.owner_entity_id=afe.owner_entity_id) as building_count,
                 (select count(*) from dune.building_instances bi where bi.owner_entity_id=afe.owner_entity_id) as piece_count,
                 (select count(*) from dune.placeables p where p.owner_entity_id=afe.owner_entity_id and p.id<>t.id) as placeable_count,
                 (select count(distinct bbl.id) from dune.base_backup_linked_actors bbl where bbl.actor_id=t.id) as existing_backup_count,
                 to_regprocedure('dune.base_backup_save_from_totem(bigint,bigint)') is not null as native_function_available,
                 (select md5(coalesce(string_agg(to_jsonb(bi)::text,',' order by bi.building_id,bi.instance_id),'')) from dune.building_instances bi where bi.owner_entity_id=afe.owner_entity_id) as piece_hash,
                 (select md5(coalesce(string_agg(to_jsonb(p)::text,',' order by p.id),'')) from dune.placeables p where p.owner_entity_id=afe.owner_entity_id or p.id=t.id) as placeable_hash,
                 (select md5(coalesce(string_agg(to_jsonb(par)::text,',' order by par.player_id,par.rank),'')) from dune.permission_actor_rank par where par.permission_actor_id=t.id) as permission_hash
          from dune.totems t
          join lateral (
            select min(link.entity_id) as owner_entity_id,count(*) as fgl_entity_count
            from dune.actor_fgl_entities link where link.actor_id=t.id
          ) afe on afe.fgl_entity_count>0
          join dune.actors a on a.id=t.id
          left join dune.permission_actor pa on pa.actor_id=t.id
          left join dune.world_partition wp on wp.partition_id=a.partition_id
          left join dune.active_server_ids asi on asi.server_id=wp.server_id
          where (%s::bigint is null or t.id=%s::bigint)
        )
        select b.*,
               coalesce(jsonb_agg(distinct jsonb_build_object(
                 'playerId',par.player_id,'rank',par.rank,'accountId',ps.account_id,
                 'characterName',ps.character_name,'onlineStatus',coalesce(ps.online_status::text,'unknown')
               )) filter (where par.player_id is not null),'[]'::jsonb) as owners
        from base b
        left join dune.permission_actor_rank par on par.permission_actor_id=b.totem_id
        left join dune.player_state ps on ps.player_controller_id=par.player_id
        group by b.totem_id,b.last_backup_timestamp,b.owner_entity_id,b.fgl_entity_count,b.actor_name,b.map,b.partition_id,b.partition_server_id,
                 b.active_server_id,
                 b.building_count,b.piece_count,b.placeable_count,b.existing_backup_count,
                 b.native_function_available,b.piece_hash,b.placeable_hash,b.permission_hash
        order by b.piece_count desc,b.totem_id
        limit %s
    """, (totem, totem, limit))
    return [_normalize(row) for row in rows]


def recovery_player(query, player_id):
    player_id = _positive(player_id, "recovery player id")
    rows = query("""
        select ps.player_controller_id,ps.account_id,ps.character_name,
               coalesce(ps.online_status::text,'unknown') as online_status
        from dune.player_state ps where ps.player_controller_id=%s limit 1
    """, (player_id,))
    if not rows:
        raise ValueError("recovery player is not a current player_controller_id")
    row = rows[0]
    return {
        "playerId": int(row["player_controller_id"]),
        "accountId": int(row["account_id"]),
        "characterName": str(row.get("character_name") or ""),
        "onlineStatus": str(row.get("online_status") or "unknown"),
    }


def plan(query, totem_id, recovery_player_id=None):
    rows = scan(query, limit=1, totem_id=totem_id)
    if not rows:
        raise ValueError("base totem was not found")
    base = rows[0]
    if recovery_player_id in (None, ""):
        candidates = [owner for owner in base["owners"] if owner["accountId"] is not None and owner["rank"] == 1]
        if len(candidates) != 1:
            candidates = [owner for owner in base["owners"] if owner["accountId"] is not None]
        if len(candidates) != 1:
            raise ValueError("choose one current offline player_controller_id to own the recoverable base backup")
        recovery_player_id = candidates[0]["playerId"]
    recovery = recovery_player(query, recovery_player_id)
    blockers = []
    if base["partitionActive"]:
        blockers.append("target partition still has an assigned server; stop that map before archiving the base")
    if base["onlineOwnerCount"]:
        blockers.append("one or more matched base owners are not explicitly offline")
    if recovery["onlineStatus"].lower() not in OFFLINE_STATES:
        blockers.append("recovery player is not explicitly offline")
    if base["existingBackupCount"]:
        blockers.append("totem is already linked to a base backup")
    if base["fglEntityCount"] != 1:
        blockers.append("totem does not have exactly one FGL owner entity")
    if not base["nativeFunctionAvailable"]:
        blockers.append("current game database does not expose the required native base-backup function")
    if base["pieceCount"] + base["placeableCount"] <= 0:
        blockers.append("base has no building pieces or owned placeables to archive")
    return {
        "ok": True,
        "dryRun": True,
        "canExecute": not blockers,
        "base": base,
        "recoveryPlayer": recovery,
        "blockers": blockers,
        "expectedFingerprint": base["fingerprint"],
        "confirm": f"ARCHIVE BASE {base['totemId']}",
        "nativeFunction": "dune.base_backup_save_from_totem(bigint,bigint)",
        "gameRecoverable": True,
        "destructiveDelete": False,
        "backupRequired": True,
        "mapRestartRequired": True,
    }


def cooldown_plan(query, totem_id):
    rows = scan(query, limit=1, totem_id=totem_id)
    if not rows:
        raise ValueError("base totem was not found")
    base = rows[0]
    blockers = []
    if base["partitionActive"]:
        blockers.append("target partition still has an assigned server; stop that map before resetting the pack-up cooldown")
    if base["onlineOwnerCount"]:
        blockers.append("one or more matched base owners are not explicitly offline")
    if base["packupCooldownReady"]:
        blockers.append("base pack-up cooldown is already cleared")
    return {
        "ok": True,
        "dryRun": True,
        "canExecute": not blockers,
        "base": base,
        "blockers": blockers,
        "expectedFingerprint": base["fingerprint"],
        "confirm": f"RESET BASE COOLDOWN {base['totemId']}",
        "databaseColumn": "dune.totems.last_backup_timestamp",
        "previousTimestamp": base["lastBackupTimestamp"],
        "resultTimestamp": 0,
        "remainingSecondsKnown": False,
        "backupRequired": True,
        "mapMustBeStopped": True,
        "mapRestartRequired": True,
        "mapLifecycleInvoked": False,
    }


def _connection_query(conn, sql, params=()):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        names = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]
        return [dict(zip(names, row)) if not isinstance(row, dict) else row for row in cursor.fetchall()]


def _write_receipt(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ValueError("base retirement receipt directory cannot be a symbolic link")
    os.chmod(path.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def list_receipts(root, limit=100):
    root = pathlib.Path(root)
    rows = []
    candidates = [path for path in root.glob("*.json") if path.is_file() and not path.is_symlink()] if root.exists() and not root.is_symlink() else []
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[:max(1, min(int(limit), 500))]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "receiptId": value.get("receiptId"),
                "status": value.get("status"),
                "createdAt": value.get("createdAt"),
                "committedAt": value.get("committedAt"),
                "totemId": ((value.get("plan") or {}).get("base") or {}).get("totemId"),
                "baseBackupId": value.get("baseBackupId"),
                "path": path.name,
            })
        except (OSError, ValueError, json.JSONDecodeError):
            rows.append({"status": "invalid", "path": path.name})
    return rows


def archive(connect_fn, backup_fn, receipt_root, *, totem_id, recovery_player_id,
            expected_fingerprint, confirm, principal="owner-token"):
    totem_id = _positive(totem_id, "totem id")
    recovery_player_id = _positive(recovery_player_id, "recovery player id")
    expected_fingerprint = str(expected_fingerprint or "").strip().lower()
    if len(expected_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in expected_fingerprint):
        raise ValueError("a valid preview fingerprint is required")
    if str(confirm or "").strip() != f"ARCHIVE BASE {totem_id}":
        raise PermissionError(f"confirmation must be ARCHIVE BASE {totem_id}")
    conn = connect_fn()
    pending = None
    try:
        conn.autocommit = False
        with conn.cursor() as cursor:
            cursor.execute("set transaction isolation level serializable")
            cursor.execute("set local statement_timeout = '120s'")
            cursor.execute("select pg_advisory_xact_lock(%s)", (totem_id,))
            cursor.execute("select id from dune.totems where id=%s for update", (totem_id,))
            if cursor.fetchone() is None:
                raise ValueError("base totem was not found")
            cursor.execute("select id from dune.actors where id=%s for update", (totem_id,))
            cursor.execute("select wp.partition_id from dune.actors a join dune.world_partition wp on wp.partition_id=a.partition_id where a.id=%s for update of wp", (totem_id,))
            cursor.execute("select entity_id from dune.actor_fgl_entities where actor_id=%s for update", (totem_id,))
            owner_row = cursor.fetchone()
            if owner_row is None:
                raise ValueError("base totem has no FGL owner entity")
            owner_entity_id = int(owner_row[0])
            cursor.execute("select building_id,instance_id from dune.building_instances where owner_entity_id=%s for update", (owner_entity_id,))
            cursor.execute("select id from dune.placeables where owner_entity_id=%s or id=%s for update", (owner_entity_id, totem_id))
            cursor.execute("select actor_id from dune.permission_actor where actor_id=%s for update", (totem_id,))
            cursor.execute("select permission_actor_id from dune.permission_actor_rank where permission_actor_id=%s for update", (totem_id,))
            cursor.execute("select ps.player_controller_id from dune.player_state ps join dune.permission_actor_rank par on par.player_id=ps.player_controller_id where par.permission_actor_id=%s for update of ps", (totem_id,))
            cursor.execute("select player_controller_id from dune.player_state where player_controller_id=%s for update", (recovery_player_id,))
        locked_plan = plan(lambda sql, params=(): _connection_query(conn, sql, params), totem_id, recovery_player_id)
        if locked_plan["expectedFingerprint"] != expected_fingerprint:
            raise RuntimeError("base changed after preview; refresh and review the new fingerprint")
        if not locked_plan["canExecute"]:
            raise PermissionError("base archive is blocked: " + "; ".join(locked_plan["blockers"]))
        backup = backup_fn()
        if not backup or not backup.get("path") or int(backup.get("bytes") or 0) <= 0:
            raise RuntimeError("full database backup did not produce a non-empty artifact")
        receipt_root = pathlib.Path(receipt_root)
        receipt_id = secrets.token_hex(12)
        pending = receipt_root / f"pending-{receipt_id}.json"
        receipt = {
            "version": 1,
            "receiptId": receipt_id,
            "status": "pending",
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "principal": str(principal)[:128],
            "plan": locked_plan,
            "databaseBackup": backup,
        }
        _write_receipt(pending, receipt)
        with conn.cursor() as cursor:
            cursor.execute("select dune.base_backup_save_from_totem(%s,%s)", (recovery_player_id, totem_id))
            row = cursor.fetchone()
            backup_id = int(row[0]) if row else 0
            if backup_id <= 0:
                raise RuntimeError("native base backup function did not return an id")
        verification_rows = _connection_query(conn, """
            select bb.id,bb.player_id,
                   (select count(*) from dune.base_backup_linked_actors bbl where bbl.id=bb.id) as linked_actor_count,
                   (select count(*) from dune.permission_actor pa where pa.actor_id=%s) as permission_actor_count,
                   (select count(*) from dune.permission_actor_rank par where par.permission_actor_id=%s) as permission_rank_count,
                   exists(select 1 from dune.base_backup_linked_actors bbl where bbl.id=bb.id and bbl.actor_id=%s) as totem_linked
            from dune.base_backups bb where bb.id=%s and bb.player_id=%s
        """, (totem_id, totem_id, totem_id, backup_id, recovery_player_id))
        if not verification_rows:
            raise RuntimeError("native base backup verification could not find the created backup")
        verification = verification_rows[0]
        if int(verification.get("linked_actor_count") or 0) <= 0 or not verification.get("totem_linked") or int(verification.get("permission_actor_count") or 0) or int(verification.get("permission_rank_count") or 0):
            raise RuntimeError("native base backup verification failed; transaction was rolled back")
        conn.commit()
        receipt["status"] = "committed"
        receipt["committedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        receipt["baseBackupId"] = backup_id
        receipt["verification"] = verification
        final = receipt_root / f"base-{totem_id}-backup-{backup_id}-{receipt_id}.json"
        receipt_finalize_error = None
        try:
            _write_receipt(final, receipt)
            pending.unlink(missing_ok=True)
            receipt_path = final
            receipt_status = "committed"
        except Exception as exc:
            receipt_path = pending
            receipt_status = "pending-finalization-failed"
            receipt_finalize_error = str(exc)[:500]
        return {
            "ok": True,
            "committed": True,
            "baseBackupId": backup_id,
            "totemId": totem_id,
            "recoveryPlayerId": recovery_player_id,
            "databaseBackup": backup,
            "receipt": str(receipt_path),
            "receiptStatus": receipt_status,
            "receiptFinalizeError": receipt_finalize_error,
            "verification": verification,
            "gameRecoverable": True,
            "destructiveDelete": False,
            "mapRestartRequired": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_cooldown(connect_fn, backup_fn, receipt_root, *, totem_id,
                   expected_fingerprint, confirm, principal="owner-token"):
    totem_id = _positive(totem_id, "totem id")
    expected_fingerprint = str(expected_fingerprint or "").strip().lower()
    if len(expected_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in expected_fingerprint):
        raise ValueError("a valid preview fingerprint is required")
    if str(confirm or "").strip() != f"RESET BASE COOLDOWN {totem_id}":
        raise PermissionError(f"confirmation must be RESET BASE COOLDOWN {totem_id}")
    conn = connect_fn()
    pending = None
    try:
        conn.autocommit = False
        with conn.cursor() as cursor:
            cursor.execute("set transaction isolation level serializable")
            cursor.execute("set local statement_timeout = '120s'")
            cursor.execute("select pg_advisory_xact_lock(%s)", (totem_id,))
            cursor.execute("select id from dune.totems where id=%s for update", (totem_id,))
            if cursor.fetchone() is None:
                raise ValueError("base totem was not found")
            cursor.execute("select id from dune.actors where id=%s for update", (totem_id,))
            cursor.execute("select wp.partition_id from dune.actors a join dune.world_partition wp on wp.partition_id=a.partition_id where a.id=%s for update of wp", (totem_id,))
            cursor.execute("select permission_actor_id from dune.permission_actor_rank where permission_actor_id=%s for update", (totem_id,))
            cursor.execute("select ps.player_controller_id from dune.player_state ps join dune.permission_actor_rank par on par.player_id=ps.player_controller_id where par.permission_actor_id=%s for update of ps", (totem_id,))
        locked_plan = cooldown_plan(lambda sql, params=(): _connection_query(conn, sql, params), totem_id)
        if locked_plan["expectedFingerprint"] != expected_fingerprint:
            raise RuntimeError("base changed after preview; refresh and review the new fingerprint")
        if not locked_plan["canExecute"]:
            raise PermissionError("base cooldown reset is blocked: " + "; ".join(locked_plan["blockers"]))
        backup = backup_fn()
        if not backup or not backup.get("path") or int(backup.get("bytes") or 0) <= 0:
            raise RuntimeError("full database backup did not produce a non-empty artifact")
        receipt_root = pathlib.Path(receipt_root)
        receipt_id = secrets.token_hex(12)
        pending = receipt_root / f"pending-cooldown-{receipt_id}.json"
        receipt = {
            "version": 1,
            "receiptId": receipt_id,
            "operation": "base-packup-cooldown-reset",
            "status": "pending",
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "principal": str(principal)[:128],
            "plan": locked_plan,
            "databaseBackup": backup,
        }
        _write_receipt(pending, receipt)
        before = int(locked_plan["previousTimestamp"])
        with conn.cursor() as cursor:
            cursor.execute(
                "update dune.totems set last_backup_timestamp=0 where id=%s and last_backup_timestamp=%s returning last_backup_timestamp",
                (totem_id, before),
            )
            updated = cursor.fetchone()
            if updated is None or int(updated[0]) != 0:
                raise RuntimeError("base cooldown changed after locked preview; transaction was rolled back")
            cursor.execute("select last_backup_timestamp from dune.totems where id=%s", (totem_id,))
            verified = cursor.fetchone()
            if verified is None or int(verified[0]) != 0:
                raise RuntimeError("base cooldown reset verification failed; transaction was rolled back")
        conn.commit()
        verification = {"totemId": totem_id, "previousTimestamp": before, "lastBackupTimestamp": 0}
        receipt["status"] = "committed"
        receipt["committedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        receipt["verification"] = verification
        final = receipt_root / f"base-{totem_id}-cooldown-{receipt_id}.json"
        receipt_finalize_error = None
        try:
            _write_receipt(final, receipt)
            pending.unlink(missing_ok=True)
            receipt_path = final
            receipt_status = "committed"
        except Exception as exc:
            receipt_path = pending
            receipt_status = "pending-finalization-failed"
            receipt_finalize_error = str(exc)[:500]
        return {
            "ok": True,
            "committed": True,
            "totemId": totem_id,
            "databaseBackup": backup,
            "receipt": str(receipt_path),
            "receiptStatus": receipt_status,
            "receiptFinalizeError": receipt_finalize_error,
            "verification": verification,
            "mapRestartRequired": True,
            "mapLifecycleInvoked": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
