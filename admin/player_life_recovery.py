#!/usr/bin/env python3
"""Guarded native recovery of an offline player's persisted life state."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import secrets


CONFIRM = "RECOVER OFFLINE PLAYER LIFE STATE"
DEAD_STATES = frozenset({"Dead", "DeadByCoriolis", "DeadBySandworm"})
NATIVE_FUNCTION = "dune.update_death_location(actordescription,serverinfo,playerlifestate)"
SCHEMA_VERSION = 1


STATE_SQL = r"""
select eps.id as player_state_id,
       eps.account_id,
       dune.decrypt_user_data(eps.encrypted_character_name) as character_name,
       eps.online_status::text as online_status,
       eps.life_state::text as life_state,
       eps.server_id,
       eps.player_controller_id,
       eps.player_pawn_id,
       eps.death_location is not null as death_location_present,
       eps.death_location::text as death_location_text,
       ea."user" as fls_id,
       dune.is_player_offline(ea."user") as native_offline,
       pawn.id as pawn_actor_id,
       pawn.class as pawn_class,
       pawn.map as pawn_map,
       pawn.partition_id as pawn_partition_id,
       pawn.dimension_index as pawn_dimension_index,
       ((pawn.transform).location).x as pawn_x,
       ((pawn.transform).location).y as pawn_y,
       ((pawn.transform).location).z as pawn_z,
       to_regprocedure('dune.get_player_pawn(bigint)') is not null as get_player_pawn_available,
       to_regprocedure('dune.update_death_location(dune.actordescription,dune.serverinfo,dune.playerlifestate)') is not null as update_death_location_available
from dune.encrypted_player_state eps
join dune.encrypted_accounts ea on ea.id=eps.account_id
left join dune.actors pawn on pawn.id=eps.player_pawn_id
where eps.account_id=%s
"""


def _positive(value):
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("account_id must be a positive integer") from exc
    if value <= 0:
        raise ValueError("account_id must be a positive integer")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _row_dict(row, description=None):
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    names = [column.name if hasattr(column, "name") else column[0] for column in (description or ())]
    return dict(zip(names, row))


def _evidence(row):
    return {
        "playerStateId": int(row["player_state_id"]),
        "accountId": int(row["account_id"]),
        "characterName": str(row.get("character_name") or ""),
        "onlineStatus": str(row.get("online_status") or "unknown"),
        "nativeOffline": bool(row.get("native_offline")),
        "lifeState": str(row.get("life_state") or "unknown"),
        "serverId": row.get("server_id"),
        "playerControllerId": row.get("player_controller_id"),
        "playerPawnId": row.get("player_pawn_id"),
        "deathLocationPresent": bool(row.get("death_location_present")),
        "deathLocationDigest": hashlib.sha256(str(row.get("death_location_text") or "").encode()).hexdigest(),
        "pawn": {
            "actorId": row.get("pawn_actor_id"),
            "class": row.get("pawn_class"),
            "map": row.get("pawn_map"),
            "partitionId": row.get("pawn_partition_id"),
            "dimensionIndex": row.get("pawn_dimension_index"),
            "location": {"x": row.get("pawn_x"), "y": row.get("pawn_y"), "z": row.get("pawn_z")},
        },
        "nativeContract": {
            "getPlayerPawnAvailable": bool(row.get("get_player_pawn_available")),
            "updateDeathLocationAvailable": bool(row.get("update_death_location_available")),
        },
    }


def _plan_from_row(row):
    evidence = _evidence(row)
    blockers = []
    if evidence["onlineStatus"].lower() != "offline":
        blockers.append("player_state is not explicitly Offline")
    if not evidence["nativeOffline"]:
        blockers.append("dune.is_player_offline(fls_id) is false")
    if evidence["lifeState"] not in DEAD_STATES:
        if evidence["lifeState"] == "Alive":
            blockers.append("player is already Alive")
        else:
            blockers.append(f"unsupported current life state: {evidence['lifeState']}")
    if not evidence["playerPawnId"] or evidence["pawn"]["actorId"] != evidence["playerPawnId"]:
        blockers.append("active player pawn actor is missing")
    if not all(evidence["nativeContract"].values()):
        blockers.append("required first-party player life-state functions are unavailable")
    return {
        "ok": True,
        "dryRun": True,
        "canExecute": not blockers,
        "accountId": evidence["accountId"],
        "player": {key: value for key, value in evidence.items() if key != "deathLocationDigest"},
        "blockers": blockers,
        "expectedFingerprint": _sha256(evidence),
        "confirm": CONFIRM,
        "executionGate": "DUNE_ADMIN_PLAYER_LIFE_RECOVERY_ENABLED",
        "nativeFunction": NATIVE_FUNCTION,
        "transition": f"{evidence['lifeState']} -> Alive",
        "backupRequired": True,
        "restartRequired": False,
        "relogRequired": True,
        "rollback": "Restore the referenced full database backup; no synthetic re-kill is offered.",
        "scope": "Persisted offline life_state and death_location only; health, inventory, position, progression, and respawn locations are unchanged.",
    }


def plan(query, account_id):
    account_id = _positive(account_id)
    rows = query(STATE_SQL, (account_id,))
    if not rows:
        raise ValueError("account_id does not have an active player-state row")
    if len(rows) != 1:
        raise RuntimeError("account_id has ambiguous active player-state rows")
    return _plan_from_row(dict(rows[0]))


def _connection_query(connection, sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        return [_row_dict(row, cursor.description) for row in cursor.fetchall()]


def _write_exclusive(path, payload):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ValueError("player life-recovery receipt directory cannot be a symbolic link")
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
    receipt_id = "player-life-recovery-" + secrets.token_hex(16)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "receiptId": receipt_id,
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "pending",
        "action": "recover-offline-life-state",
        "principal": str(principal or "owner-recovery")[:128],
        "backup": backup,
        "preview": preview,
    }
    payload["receiptSha256"] = _sha256(payload)
    path = pathlib.Path(root) / f"pending-{receipt_id}.json"
    _write_exclusive(path, payload)
    return path, payload


def _finalize_receipt(pending_path, payload, result):
    final = dict(payload)
    final.update({
        "status": "committed",
        "committedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "result": result,
    })
    final.pop("receiptSha256", None)
    final["receiptSha256"] = _sha256(final)
    final_path = pathlib.Path(pending_path).parent / f"{final['receiptId']}.json"
    try:
        _write_exclusive(final_path, final)
        pathlib.Path(pending_path).unlink(missing_ok=True)
        return {"id": final["receiptId"], "path": str(final_path), "sha256": final["receiptSha256"], "status": "committed"}
    except Exception as exc:
        return {
            "id": payload["receiptId"], "path": str(pending_path),
            "sha256": payload["receiptSha256"], "status": "pending-finalization-failed",
            "error": str(exc)[:1000],
        }


def execute(db_connect, create_backup, receipt_root, account_id, expected_fingerprint,
            confirm, principal=""):
    account_id = _positive(account_id)
    if str(confirm or "") != CONFIRM:
        raise PermissionError(f"confirmation must be exactly {CONFIRM!r}")
    preview = plan(lambda sql, params=(): _standalone_query(db_connect, sql, params), account_id)
    if str(expected_fingerprint or "") != preview["expectedFingerprint"]:
        raise RuntimeError("player life-state evidence changed after preview; preview again")
    if not preview["canExecute"]:
        raise ValueError("player life-state recovery is not executable: " + "; ".join(preview["blockers"]))

    backup = create_backup()
    pending_path, pending = _begin_receipt(receipt_root, principal, backup, preview)
    connection = db_connect()
    try:
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (account_id,))
            cursor.execute(
                "select player_pawn_id from dune.encrypted_player_state where account_id=%s for update",
                (account_id,),
            )
            locked = _row_dict(cursor.fetchone(), cursor.description)
            if not locked:
                raise RuntimeError("player-state row disappeared while acquiring the recovery lock")
            pawn_id = locked.get("player_pawn_id")
            if not pawn_id:
                raise RuntimeError("player pawn disappeared while acquiring the recovery lock")
            cursor.execute("select id from dune.actors where id=%s for update", (pawn_id,))
            if cursor.fetchone() is None:
                raise RuntimeError("player pawn actor disappeared while acquiring the recovery lock")

        current = plan(lambda sql, params=(): _connection_query(connection, sql, params), account_id)
        if current["expectedFingerprint"] != preview["expectedFingerprint"]:
            raise RuntimeError("player life-state evidence changed while acquiring the transaction; preview again")
        if not current["canExecute"]:
            raise RuntimeError("player life-state recovery became ineligible while acquiring the transaction")

        with connection.cursor() as cursor:
            cursor.execute(r"""
                select dune.update_death_location(
                    native_pawn.description,
                    native_pawn.server_info,
                    'Alive'::dune.playerlifestate
                )
                from dune.get_player_pawn(%s) native_pawn
            """, (account_id,))
            native_rows = cursor.fetchall()
            if len(native_rows) != 1:
                raise RuntimeError("native life-state function did not resolve exactly one player pawn")

        after = plan(lambda sql, params=(): _connection_query(connection, sql, params), account_id)
        after_player = after["player"]
        before_player = current["player"]
        verified = (
            after_player["lifeState"] == "Alive"
            and not after_player["deathLocationPresent"]
            and after_player["onlineStatus"].lower() == "offline"
            and after_player["nativeOffline"]
            and after_player["playerStateId"] == before_player["playerStateId"]
            and after_player["playerPawnId"] == before_player["playerPawnId"]
        )
        if not verified:
            raise RuntimeError("native life-state function returned but persisted post-write verification failed")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    result = {
        "ok": True,
        "dryRun": False,
        "accountId": account_id,
        "nativeFunction": NATIVE_FUNCTION,
        "before": current["player"],
        "after": after_player,
        "verified": True,
        "backup": backup,
        "restartRequired": False,
        "relogRequired": True,
        "rollback": preview["rollback"],
        "scope": preview["scope"],
    }
    result["receipt"] = _finalize_receipt(pending_path, pending, result)
    return result


def _standalone_query(db_connect, sql, params=()):
    connection = db_connect()
    try:
        return _connection_query(connection, sql, params)
    finally:
        connection.close()


def list_receipts(root, limit=50):
    limit = max(1, min(int(limit), 500))
    root = pathlib.Path(root)
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.glob("player-life-recovery-*.json"), reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected = payload.pop("receiptSha256", None)
            valid = bool(expected) and secrets.compare_digest(str(expected), _sha256(payload))
            payload["receiptSha256"] = expected
            rows.append({
                "id": payload.get("receiptId"), "createdAt": payload.get("createdAt"),
                "committedAt": payload.get("committedAt"), "status": payload.get("status"),
                "accountId": ((payload.get("result") or {}).get("accountId")),
                "receiptHashValid": valid,
            })
        except Exception as exc:
            rows.append({"id": path.stem, "status": "invalid", "receiptHashValid": False, "error": str(exc)[:500]})
    return rows
