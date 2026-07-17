#!/usr/bin/env python3
"""Fingerprint-bound, backup-first native offline player teleport."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import pathlib
import secrets


CONFIRM = "MOVE OFFLINE PLAYER"
NATIVE_FUNCTION = "dune.admin_move_offline_player_to_partition(text,bigint,vector)"
MAX_ABS_COORDINATE = 10_000_000.0

PLAYER_SQL = r"""
select eps.id as player_state_id, eps.account_id,
       dune.decrypt_user_data(eps.encrypted_character_name) as character_name,
       eps.online_status::text as online_status, eps.life_state::text as life_state,
       eps.server_id, eps.previous_server_partition_id,
       eps.player_controller_id, eps.player_state_id, eps.player_pawn_id,
       ea."user" as fls_id,
       dune.is_player_offline(ea."user") as native_offline,
       pawn.id as pawn_actor_id, pawn.class as pawn_class, pawn.map as pawn_map,
       pawn.partition_id as pawn_partition_id, pawn.dimension_index as pawn_dimension_index,
       ((pawn.transform).location).x as pawn_x,
       ((pawn.transform).location).y as pawn_y,
       ((pawn.transform).location).z as pawn_z,
       to_regprocedure('dune.admin_move_offline_player_to_partition(text,bigint,dune.vector)') is not null as native_function_available
from dune.encrypted_player_state eps
join dune.encrypted_accounts ea on ea.id=eps.account_id
left join dune.actors pawn on pawn.id=eps.player_pawn_id
where eps.account_id=%s
"""

PARTITION_SQL = r"""
select partition_id, server_id, map, dimension_index, label, blocked,
       dune.upgrade_map_name(map) as expected_pawn_map
from dune.world_partition
where partition_id=%s
"""


def _positive(value, label):
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def normalize_location(value):
    if not isinstance(value, dict):
        raise ValueError("location must be an object with finite x, y, and z coordinates")
    result = {}
    for axis in ("x", "y", "z"):
        try:
            coordinate = float(value.get(axis))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"location.{axis} must be a finite number") from exc
        if not math.isfinite(coordinate) or abs(coordinate) > MAX_ABS_COORDINATE:
            raise ValueError(f"location.{axis} must be finite and within +/-{int(MAX_ABS_COORDINATE)}")
        result[axis] = coordinate
    return result


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _row_dict(row, description=None):
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    names = [column.name if hasattr(column, "name") else column[0] for column in (description or ())]
    return dict(zip(names, row))


def _fetch_exact(query, sql, params, label):
    rows = query(sql, params)
    if not rows:
        raise ValueError(f"{label} was not found")
    if len(rows) != 1:
        raise RuntimeError(f"{label} is ambiguous")
    return dict(rows[0])


def _evidence(player, partition, location):
    return {
        "accountId": int(player["account_id"]),
        "playerStateId": int(player["player_state_id"]),
        "characterName": str(player.get("character_name") or ""),
        "onlineStatus": str(player.get("online_status") or "unknown"),
        "nativeOffline": bool(player.get("native_offline")),
        "lifeState": str(player.get("life_state") or "unknown"),
        "serverId": player.get("server_id"),
        "playerControllerId": player.get("player_controller_id"),
        "playerPawnId": player.get("player_pawn_id"),
        "nativeFunctionAvailable": bool(player.get("native_function_available")),
        "pawn": {
            "actorId": player.get("pawn_actor_id"), "class": player.get("pawn_class"),
            "map": player.get("pawn_map"), "partitionId": player.get("pawn_partition_id"),
            "dimensionIndex": player.get("pawn_dimension_index"),
            "location": {"x": player.get("pawn_x"), "y": player.get("pawn_y"), "z": player.get("pawn_z")},
        },
        "targetPartition": {
            "partitionId": int(partition["partition_id"]), "serverId": partition.get("server_id"),
            "map": partition.get("map"), "expectedPawnMap": partition.get("expected_pawn_map"),
            "dimensionIndex": partition.get("dimension_index"), "label": partition.get("label"),
            "blocked": bool(partition.get("blocked")),
        },
        "targetLocation": location,
    }


def plan(query, account_id, partition_id, location):
    account_id = _positive(account_id, "account_id")
    partition_id = _positive(partition_id, "partition_id")
    location = normalize_location(location)
    player = _fetch_exact(query, PLAYER_SQL, (account_id,), "account_id")
    partition = _fetch_exact(query, PARTITION_SQL, (partition_id,), "partition_id")
    evidence = _evidence(player, partition, location)
    blockers = []
    if evidence["onlineStatus"].lower() != "offline":
        blockers.append("player_state is not explicitly Offline")
    if not evidence["nativeOffline"]:
        blockers.append("dune.is_player_offline(fls_id) is false")
    if not evidence["playerPawnId"] or evidence["pawn"]["actorId"] != evidence["playerPawnId"]:
        blockers.append("active player pawn actor is missing")
    if not evidence["nativeFunctionAvailable"]:
        blockers.append("native offline teleport function is unavailable")
    if evidence["targetPartition"]["blocked"]:
        blockers.append("target world partition is blocked")
    return {
        "ok": True, "dryRun": True, "canExecute": not blockers,
        "accountId": account_id, "partitionId": partition_id,
        "plan": {
            "function": NATIVE_FUNCTION,
            "args": ["<private FLS identity>", partition_id, location],
            "player": {key: value for key, value in evidence.items() if key not in ("targetPartition", "targetLocation")},
            "targetPartition": evidence["targetPartition"],
            "currentActors": [evidence["pawn"]],
            "targetLocation": location,
            "executable": not blockers, "blockers": blockers,
            "note": "Strict-offline native pawn move; Online/network-timeout automation remains separate.",
        },
        "expectedFingerprint": _sha256(evidence),
        "confirm": CONFIRM,
        "executionGate": "DUNE_ADMIN_OFFLINE_TELEPORT_ENABLED",
        "backupRequired": True, "restartRequired": False, "relogRequired": True,
        "rollback": "Use a new guarded preview to move to the receipted prior partition/location, or restore the referenced full database backup.",
    }


def _connection_query(connection, sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        return [_row_dict(row, cursor.description) for row in cursor.fetchall()]


def _standalone_query(db_connect, sql, params=()):
    connection = db_connect()
    try:
        return _connection_query(connection, sql, params)
    finally:
        connection.close()


def _write(path, payload):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ValueError("offline teleport receipt directory cannot be a symbolic link")
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _begin_receipt(root, principal, backup, preview):
    identifier = "offline-teleport-" + secrets.token_hex(16)
    payload = {
        "schemaVersion": 1, "receiptId": identifier,
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "pending", "action": "offline-teleport",
        "principal": str(principal or "owner-recovery")[:128],
        "backup": backup, "preview": preview,
    }
    payload["receiptSha256"] = _sha256(payload)
    path = pathlib.Path(root) / f"pending-{identifier}.json"
    _write(path, payload)
    return path, payload


def _finalize(pending_path, payload, result):
    final = dict(payload)
    final.update({"status": "committed", "committedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "result": result})
    final.pop("receiptSha256", None)
    final["receiptSha256"] = _sha256(final)
    path = pathlib.Path(pending_path).parent / f"{final['receiptId']}.json"
    try:
        _write(path, final)
        pathlib.Path(pending_path).unlink(missing_ok=True)
        return {"id": final["receiptId"], "path": str(path), "sha256": final["receiptSha256"], "status": "committed"}
    except Exception as exc:
        return {"id": payload["receiptId"], "path": str(pending_path), "sha256": payload["receiptSha256"], "status": "pending-finalization-failed", "error": str(exc)[:1000]}


def _close(actual, expected, tolerance=1e-5):
    try:
        return abs(float(actual) - float(expected)) <= tolerance
    except (TypeError, ValueError):
        return False


def execute(db_connect, create_backup, receipt_root, account_id, partition_id,
            location, expected_fingerprint, confirm, principal=""):
    if str(confirm or "") != CONFIRM:
        raise PermissionError(f"confirmation must be exactly {CONFIRM!r}")
    preview = plan(lambda sql, params=(): _standalone_query(db_connect, sql, params), account_id, partition_id, location)
    if str(expected_fingerprint or "") != preview["expectedFingerprint"]:
        raise RuntimeError("offline teleport evidence changed after preview; preview again")
    if not preview["canExecute"]:
        raise ValueError("offline teleport is not executable: " + "; ".join(preview["plan"]["blockers"]))
    backup = create_backup()
    pending_path, pending = _begin_receipt(receipt_root, principal, backup, preview)
    connection = db_connect()
    try:
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (int(account_id),))
            cursor.execute("select player_pawn_id from dune.encrypted_player_state where account_id=%s for update", (int(account_id),))
            locked = _row_dict(cursor.fetchone(), cursor.description)
            if not locked or not locked.get("player_pawn_id"):
                raise RuntimeError("player-state/pawn disappeared while acquiring the teleport lock")
            cursor.execute("select id from dune.actors where id=%s for update", (locked["player_pawn_id"],))
            if cursor.fetchone() is None:
                raise RuntimeError("player pawn actor disappeared while acquiring the teleport lock")
            cursor.execute("select partition_id from dune.world_partition where partition_id=%s for share", (int(partition_id),))
            if cursor.fetchone() is None:
                raise RuntimeError("target partition disappeared while acquiring the teleport lock")
        current = plan(lambda sql, params=(): _connection_query(connection, sql, params), account_id, partition_id, location)
        if current["expectedFingerprint"] != preview["expectedFingerprint"]:
            raise RuntimeError("offline teleport evidence changed while acquiring the transaction; preview again")
        if not current["canExecute"]:
            raise RuntimeError("offline teleport became ineligible while acquiring the transaction")
        fls_rows = _connection_query(connection, "select ea.\"user\" as fls_id from dune.encrypted_accounts ea where ea.id=%s", (int(account_id),))
        if len(fls_rows) != 1 or not fls_rows[0].get("fls_id"):
            raise RuntimeError("private FLS identity could not be resolved under the teleport transaction")
        target = current["plan"]["targetPartition"]
        target_location = current["plan"]["targetLocation"]
        with connection.cursor() as cursor:
            cursor.execute(r"""
                select dune.admin_move_offline_player_to_partition(
                    %s, %s, row(%s,%s,%s)::dune.vector
                )
            """, (fls_rows[0]["fls_id"], int(partition_id), target_location["x"], target_location["y"], target_location["z"]))
            rows = cursor.fetchall()
            if len(rows) != 1:
                raise RuntimeError("native offline teleport did not return exactly once")
        after = plan(lambda sql, params=(): _connection_query(connection, sql, params), account_id, partition_id, location)
        pawn = after["plan"]["currentActors"][0]
        actual_location = pawn["location"]
        verified = (
            pawn["actorId"] == current["plan"]["currentActors"][0]["actorId"]
            and pawn["partitionId"] == int(partition_id)
            and pawn["dimensionIndex"] == target["dimensionIndex"]
            and str(pawn["map"] or "") == str(target["expectedPawnMap"] or "")
            and all(_close(actual_location[axis], target_location[axis]) for axis in ("x", "y", "z"))
            and after["plan"]["player"]["onlineStatus"].lower() == "offline"
            and after["plan"]["player"]["nativeOffline"]
        )
        if not verified:
            raise RuntimeError("native offline teleport returned but persisted pawn readback verification failed")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    result = {
        "ok": True, "dryRun": False, "accountId": int(account_id), "partitionId": int(partition_id),
        "nativeFunction": NATIVE_FUNCTION, "verified": True,
        "before": current["plan"]["currentActors"], "result": after["plan"]["currentActors"],
        "backup": backup, "restartRequired": False, "relogRequired": True,
        "rollback": {"priorPawn": current["plan"]["currentActors"][0], "guidance": preview["rollback"]},
    }
    result["receipt"] = _finalize(pending_path, pending, result)
    return result


def list_receipts(root, limit=50):
    root = pathlib.Path(root)
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.glob("offline-teleport-*.json"), reverse=True)[:max(1, min(int(limit), 500))]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected = payload.pop("receiptSha256", None)
            valid = bool(expected) and secrets.compare_digest(str(expected), _sha256(payload))
            rows.append({"id": payload.get("receiptId"), "createdAt": payload.get("createdAt"), "status": payload.get("status"), "accountId": ((payload.get("result") or {}).get("accountId")), "receiptHashValid": valid})
        except Exception as exc:
            rows.append({"id": path.stem, "status": "invalid", "receiptHashValid": False, "error": str(exc)[:500]})
    return rows
