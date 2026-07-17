#!/usr/bin/env python3
"""Private native character-transfer snapshots and guarded restore."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import secrets
import stat


CAPTURE_CONFIRM = "CAPTURE CHARACTER BACKUP"
RESTORE_CONFIRM = "RESTORE CHARACTER BACKUP"
DELETE_CONFIRM = "DELETE CHARACTER BACKUP"
CAPTURE_FUNCTION = "dune.character_transfer_export(text)"
RESTORE_FUNCTION = "dune.character_transfer_import(jsonb,text,text)"
MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
SCHEMA_VERSION = 1

CAPTURE_STATE_SQL = r"""
select eps.id as player_state_row_id, eps.account_id,
       dune.decrypt_user_data(eps.encrypted_character_name) as character_name,
       eps.online_status::text as online_status,
       eps.player_controller_id, eps.player_state_id, eps.player_pawn_id,
       ea."user" as fls_id,
       dune.is_player_offline(ea."user") as native_offline,
       to_regprocedure('dune.character_transfer_export(text)') is not null as export_available,
       to_regprocedure('dune.character_transfer_import(jsonb,text,text)') is not null as import_available,
       case when to_regprocedure('dune._character_transfer_get_patches_checksum()') is not null
            then dune._character_transfer_get_patches_checksum() else null end as patches_checksum
from dune.encrypted_player_state eps
join dune.encrypted_accounts ea on ea.id=eps.account_id
where eps.account_id=%s
"""

RESTORE_STATE_SQL = r"""
select ea.id as account_id, eps.id as player_state_row_id,
       case when eps.id is null then null else dune.decrypt_user_data(eps.encrypted_character_name) end as character_name,
       eps.online_status::text as online_status,
       eps.player_controller_id, eps.player_state_id, eps.player_pawn_id,
       dune.is_player_offline(%s) as native_offline,
       to_regprocedure('dune.character_transfer_export(text)') is not null as export_available,
       to_regprocedure('dune.character_transfer_import(jsonb,text,text)') is not null as import_available,
       case when to_regprocedure('dune._character_transfer_get_patches_checksum()') is not null
            then dune._character_transfer_get_patches_checksum() else null end as patches_checksum
from (select 1) singleton
left join dune.encrypted_accounts ea on ea."user"=%s
left join dune.encrypted_player_state eps on eps.account_id=ea.id
"""


def _positive(value, label="account_id"):
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _sha256(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _row_dict(row, description=None):
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    names = [column.name if hasattr(column, "name") else column[0] for column in (description or ())]
    return dict(zip(names, row))


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


def _exact(rows, label):
    if not rows:
        raise ValueError(f"{label} was not found")
    if len(rows) != 1:
        raise RuntimeError(f"{label} is ambiguous")
    return dict(rows[0])


def _capture_evidence(row):
    return {
        "accountId": int(row["account_id"]),
        "playerStateRowId": int(row["player_state_row_id"]),
        "characterName": str(row.get("character_name") or ""),
        "onlineStatus": str(row.get("online_status") or "unknown"),
        "nativeOffline": bool(row.get("native_offline")),
        "playerControllerId": row.get("player_controller_id"),
        "playerStateActorId": row.get("player_state_id"),
        "playerPawnId": row.get("player_pawn_id"),
        "flsIdentityDigest": hashlib.sha256(str(row.get("fls_id") or "").encode()).hexdigest(),
        "patchesChecksum": str(row.get("patches_checksum") or ""),
        "nativeContract": {
            "exportAvailable": bool(row.get("export_available")),
            "importAvailable": bool(row.get("import_available")),
        },
    }


def plan_capture(query, account_id):
    account_id = _positive(account_id)
    evidence = _capture_evidence(_exact(query(CAPTURE_STATE_SQL, (account_id,)), "account_id"))
    blockers = []
    if evidence["onlineStatus"].lower() != "offline":
        blockers.append("player_state is not explicitly Offline")
    if not evidence["nativeOffline"]:
        blockers.append("dune.is_player_offline(fls_id) is false")
    if not evidence["nativeContract"]["exportAvailable"]:
        blockers.append("native character transfer export is unavailable")
    if not evidence["patchesChecksum"]:
        blockers.append("current character-transfer patch checksum is unavailable")
    return {
        "ok": True, "dryRun": True, "action": "capture", "canExecute": not blockers,
        "accountId": account_id, "character": evidence, "blockers": blockers,
        "expectedFingerprint": _sha256(evidence), "confirm": CAPTURE_CONFIRM,
        "executionGate": "DUNE_ADMIN_CHARACTER_BACKUPS_ENABLED",
        "nativeFunction": CAPTURE_FUNCTION, "databaseBackupRequired": False,
        "restartRequired": False, "relogRequired": False,
        "scope": "Native portable character, inventory, backed-up vehicle/base, and progression transfer data; placed world property is not captured.",
    }


def _snapshot_dir(root):
    path = pathlib.Path(root) / "snapshots"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("character backup directory cannot be a symbolic link")
    os.chmod(path, 0o700)
    return path


def _write_exclusive(path, payload):
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8") + b"\n"
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ValueError(f"character backup exceeds {MAX_SNAPSHOT_BYTES} bytes")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        pathlib.Path(path).unlink(missing_ok=True)
        raise


def _public_snapshot(envelope, *, verified=True):
    meta = envelope.get("metadata") or {}
    transfer = envelope.get("transfer") or {}
    return {
        "id": meta.get("id"), "createdAt": meta.get("createdAt"),
        "accountIdAtCapture": meta.get("accountIdAtCapture"),
        "characterName": meta.get("characterName"), "action": meta.get("action"),
        "reason": meta.get("reason"), "patchesChecksum": meta.get("patchesChecksum"),
        "bytes": meta.get("bytes"), "transferEntries": len(transfer.get("entries") or []),
        "snapshotSha256": meta.get("snapshotSha256"), "verified": bool(verified),
    }


def _load_snapshot(root, snapshot_id):
    snapshot_id = str(snapshot_id or "").strip()
    if not snapshot_id.startswith("character-") or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for ch in snapshot_id):
        raise ValueError("invalid character backup id")
    path = _snapshot_dir(root) / f"{snapshot_id}.json"
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except (FileNotFoundError, OSError) as exc:
        raise ValueError("character backup was not found or is unsafe") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > MAX_SNAPSHOT_BYTES:
            raise ValueError("character backup size or file type is invalid")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            raw = handle.read(MAX_SNAPSHOT_BYTES + 1)
    finally:
        if fd is not None:
            os.close(fd)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError("character backup exceeds its read bound")
    envelope = json.loads(raw.decode("utf-8"))
    if envelope.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("character backup schema is unsupported")
    meta = envelope.get("metadata") or {}
    transfer = envelope.get("transfer") or {}
    if meta.get("id") != snapshot_id or not envelope.get("flsId") or not isinstance(transfer.get("entries"), list):
        raise ValueError("character backup structure is invalid")
    claimed = meta.get("snapshotSha256")
    unsigned = dict(envelope)
    unsigned["metadata"] = dict(meta)
    unsigned["metadata"].pop("snapshotSha256", None)
    if not claimed or _sha256(unsigned) != claimed:
        raise ValueError("character backup SHA-256 verification failed")
    if transfer.get("_patches_checksum") != meta.get("patchesChecksum"):
        raise ValueError("character backup patch checksum metadata does not match its transfer payload")
    return path, envelope


def list_snapshots(root, account_id=None, limit=100):
    wanted = None if account_id in (None, "") else _positive(account_id)
    rows = []
    for path in sorted(_snapshot_dir(root).glob("character-*.json"), reverse=True):
        try:
            _, envelope = _load_snapshot(root, path.stem)
            public = _public_snapshot(envelope)
            if wanted is None or int(public.get("accountIdAtCapture") or 0) == wanted:
                rows.append(public)
        except Exception as exc:
            rows.append({"id": path.stem, "verified": False, "error": str(exc)[:500]})
        if len(rows) >= max(1, min(int(limit), 1000)):
            break
    return rows


def capture(db_connect, root, account_id, expected_fingerprint, confirm, *, principal="", reason="manual"):
    if str(confirm or "") != CAPTURE_CONFIRM:
        raise PermissionError(f"confirmation must be exactly {CAPTURE_CONFIRM!r}")
    preview = plan_capture(lambda sql, params=(): _standalone_query(db_connect, sql, params), account_id)
    if str(expected_fingerprint or "") != preview["expectedFingerprint"]:
        raise RuntimeError("character backup evidence changed after preview; preview again")
    if not preview["canExecute"]:
        raise ValueError("character backup is not executable: " + "; ".join(preview["blockers"]))
    connection = None
    try:
        connection = db_connect()
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (int(account_id),))
            cursor.execute("select id from dune.encrypted_player_state where account_id=%s for share", (int(account_id),))
            if cursor.fetchone() is None:
                raise RuntimeError("player state disappeared while acquiring the character backup lock")
        current = plan_capture(lambda sql, params=(): _connection_query(connection, sql, params), account_id)
        if current["expectedFingerprint"] != preview["expectedFingerprint"] or not current["canExecute"]:
            raise RuntimeError("character backup evidence changed while acquiring the transaction; preview again")
        fls_row = _exact(_connection_query(connection, 'select "user" as fls_id from dune.encrypted_accounts where id=%s', (int(account_id),)), "FLS identity")
        with connection.cursor() as cursor:
            cursor.execute("select dune.character_transfer_export(%s)", (fls_row["fls_id"],))
            transfer = cursor.fetchone()[0]
        connection.rollback()
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
    if isinstance(transfer, str):
        transfer = json.loads(transfer)
    if not isinstance(transfer, dict) or not isinstance(transfer.get("entries"), list):
        raise RuntimeError("native character transfer export returned an invalid payload")
    if transfer.get("_patches_checksum") != preview["character"]["patchesChecksum"]:
        raise RuntimeError("native character transfer export patch checksum changed during capture")
    snapshot_id = "character-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(8)
    transfer_bytes = len(_canonical(transfer))
    envelope = {
        "schemaVersion": SCHEMA_VERSION,
        "metadata": {
            "id": snapshot_id, "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "accountIdAtCapture": int(account_id), "characterName": preview["character"]["characterName"],
            "action": "manual", "reason": str(reason or "manual")[:500],
            "principal": str(principal or "owner-recovery")[:128],
            "patchesChecksum": str(transfer.get("_patches_checksum") or ""), "bytes": transfer_bytes,
        },
        "flsId": fls_row["fls_id"], "transfer": transfer,
    }
    envelope["metadata"]["snapshotSha256"] = _sha256(envelope)
    path = _snapshot_dir(root) / f"{snapshot_id}.json"
    _write_exclusive(path, envelope)
    return {"ok": True, "dryRun": False, "snapshot": _public_snapshot(envelope), "nativeFunction": CAPTURE_FUNCTION, "databaseTouched": False}


def _restore_evidence(query, root, snapshot_id):
    _, envelope = _load_snapshot(root, snapshot_id)
    fls_id = envelope["flsId"]
    row = _exact(query(RESTORE_STATE_SQL, (fls_id, fls_id)), "restore contract")
    current = {
        "accountId": row.get("account_id"), "playerStateRowId": row.get("player_state_row_id"),
        "characterName": str(row.get("character_name") or ""),
        "onlineStatus": str(row.get("online_status") or "absent"),
        "nativeOffline": bool(row.get("native_offline")),
        "playerControllerId": row.get("player_controller_id"),
        "playerStateActorId": row.get("player_state_id"), "playerPawnId": row.get("player_pawn_id"),
    }
    public = _public_snapshot(envelope)
    return envelope, row, {"snapshot": public, "current": current, "currentPatchesChecksum": str(row.get("patches_checksum") or ""),
        "nativeContract": {"exportAvailable": bool(row.get("export_available")), "importAvailable": bool(row.get("import_available"))}}


def plan_restore(query, root, snapshot_id):
    _, row, evidence = _restore_evidence(query, root, snapshot_id)
    blockers = []
    current = evidence["current"]
    if current["playerStateRowId"] is not None and current["onlineStatus"].lower() != "offline":
        blockers.append("current player_state is not explicitly Offline")
    if not current["nativeOffline"]:
        blockers.append("dune.is_player_offline(fls_id) is false")
    if not evidence["nativeContract"]["importAvailable"]:
        blockers.append("native character transfer import is unavailable")
    if evidence["snapshot"]["patchesChecksum"] != evidence["currentPatchesChecksum"]:
        blockers.append("snapshot patch checksum does not match the current game database")
    return {
        "ok": True, "dryRun": True, "action": "restore", "canExecute": not blockers,
        **evidence, "blockers": blockers, "expectedFingerprint": _sha256(evidence),
        "confirm": RESTORE_CONFIRM, "executionGate": "DUNE_ADMIN_CHARACTER_BACKUPS_ENABLED",
        "nativeFunction": RESTORE_FUNCTION, "databaseBackupRequired": True,
        "restartRequired": False, "relogRequired": True,
        "warning": "Restore fully replaces the current character for this private identity. Placed bases and parked world vehicles are not restored.",
        "rollback": "Restore the referenced full database backup.",
    }


def _receipt_dir(root):
    path = pathlib.Path(root) / "receipts"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("character backup receipt directory cannot be a symbolic link")
    os.chmod(path, 0o700)
    return path


def _begin_restore_receipt(root, receipt_id, principal, backup, snapshot):
    payload = {
        "schemaVersion": SCHEMA_VERSION, "receiptId": receipt_id,
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "status": "pending",
        "action": "restore-character-backup", "principal": str(principal or "owner-recovery")[:128],
        "snapshot": snapshot, "backup": backup,
    }
    payload["receiptSha256"] = _sha256(payload)
    path = _receipt_dir(root) / f"pending-{receipt_id}.json"
    _write_exclusive(path, payload)
    return path, payload


def _finalize_restore_receipt(root, pending_path, pending, status, result):
    payload = dict(pending)
    payload["status"] = status
    payload["finishedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload["result"] = result
    payload.pop("receiptSha256", None)
    payload = dict(payload)
    payload["receiptSha256"] = _sha256(payload)
    final = _receipt_dir(root) / f"{payload['receiptId']}.json"
    _write_exclusive(final, payload)
    pathlib.Path(pending_path).unlink(missing_ok=True)
    return {"id": payload["receiptId"], "path": str(final), "sha256": payload["receiptSha256"], "status": payload["status"]}


def restore(db_connect, create_backup, root, snapshot_id, expected_fingerprint, confirm, *, principal=""):
    if str(confirm or "") != RESTORE_CONFIRM:
        raise PermissionError(f"confirmation must be exactly {RESTORE_CONFIRM!r}")
    preview = plan_restore(lambda sql, params=(): _standalone_query(db_connect, sql, params), root, snapshot_id)
    if str(expected_fingerprint or "") != preview["expectedFingerprint"]:
        raise RuntimeError("character restore evidence changed after preview; preview again")
    if not preview["canExecute"]:
        raise ValueError("character restore is not executable: " + "; ".join(preview["blockers"]))
    _, envelope = _load_snapshot(root, snapshot_id)
    backup = create_backup()
    receipt_id = "character-restore-" + secrets.token_hex(16)
    pending_path, pending = _begin_restore_receipt(
        root, receipt_id, principal, backup, preview["snapshot"],
    )
    connection = None
    try:
        connection = db_connect()
        connection.autocommit = False
        lock_key = int.from_bytes(hashlib.sha256(envelope["flsId"].encode()).digest()[:8], "big", signed=True)
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (lock_key,))
            old = preview["current"]
            if old.get("accountId"):
                cursor.execute("select id from dune.encrypted_accounts where id=%s for update", (old["accountId"],))
            if old.get("playerStateRowId"):
                cursor.execute("select id from dune.encrypted_player_state where id=%s for update", (old["playerStateRowId"],))
            actor_ids = [value for value in (old.get("playerControllerId"), old.get("playerStateActorId"), old.get("playerPawnId")) if value]
            if actor_ids:
                cursor.execute("select id from dune.actors where id=any(%s) for update", (actor_ids,))
        current = plan_restore(lambda sql, params=(): _connection_query(connection, sql, params), root, snapshot_id)
        if current["expectedFingerprint"] != preview["expectedFingerprint"] or not current["canExecute"]:
            raise RuntimeError("character restore evidence changed while acquiring the transaction; preview again")
        with connection.cursor() as cursor:
            cursor.execute("select dune.character_transfer_import(%s::jsonb,%s,%s)", (
                json.dumps(envelope["transfer"], separators=(",", ":")), envelope["flsId"], envelope["metadata"]["characterName"],
            ))
            new_controller_id = cursor.fetchone()[0]
            old = preview["current"]
            orphan_state_deleted = 0
            if old.get("playerStateRowId") and old.get("accountId"):
                cursor.execute("""
                    delete from dune.encrypted_player_state
                    where id=%s and account_id=%s
                      and not exists (select 1 from dune.encrypted_accounts where id=%s)
                """, (old["playerStateRowId"], old["accountId"], old["accountId"]))
                orphan_state_deleted = cursor.rowcount
            actor_ids = [value for value in (old.get("playerControllerId"), old.get("playerStateActorId"), old.get("playerPawnId")) if value]
            orphan_actors_deleted = 0
            if actor_ids and old.get("accountId"):
                cursor.execute("""
                    delete from dune.actors
                    where id=any(%s) and owner_account_id=%s
                      and (class ilike '%%PlayerCharacter%%' or class ilike '%%PlayerController%%' or class ilike '%%PlayerState%%')
                      and not exists (select 1 from dune.encrypted_accounts where id=%s)
                """, (actor_ids, old["accountId"], old["accountId"]))
                orphan_actors_deleted = cursor.rowcount
            cursor.execute("""
                select ea.id as account_id, eps.id as player_state_row_id,
                       dune.decrypt_user_data(eps.encrypted_character_name) as character_name,
                       eps.player_controller_id, eps.online_status::text as online_status
                from dune.encrypted_accounts ea
                join dune.encrypted_player_state eps on eps.account_id=ea.id
                where ea."user"=%s
            """, (envelope["flsId"],))
            rows = [_row_dict(row, cursor.description) for row in cursor.fetchall()]
        verified = len(rows) == 1 and int(rows[0]["player_controller_id"]) == int(new_controller_id) and rows[0]["character_name"] == envelope["metadata"]["characterName"]
        if not verified:
            raise RuntimeError("native character restore post-write identity verification failed")
        connection.commit()
    except Exception as exc:
        if connection is not None:
            connection.rollback()
        try:
            _finalize_restore_receipt(
                root, pending_path, pending, "rolled-back",
                {"transactionCommitted": False, "error": str(exc)[:1000]},
            )
        except Exception:
            pass
        raise
    finally:
        if connection is not None:
            connection.close()
    result = {
        "newAccountId": rows[0]["account_id"], "newPlayerStateRowId": rows[0]["player_state_row_id"],
        "newPlayerControllerId": new_controller_id, "characterName": rows[0]["character_name"],
        "onlineStatus": rows[0]["online_status"], "identityVerified": True,
        "orphanStateRowsDeleted": orphan_state_deleted, "orphanPlayerActorsDeleted": orphan_actors_deleted,
    }
    try:
        receipt = _finalize_restore_receipt(root, pending_path, pending, "committed", result)
    except Exception as exc:
        receipt = {
            "id": receipt_id, "path": str(pending_path),
            "sha256": pending.get("receiptSha256"), "status": "pending-finalization-failed",
            "error": str(exc)[:1000],
        }
    return {"ok": True, "dryRun": False, "backup": backup, "snapshot": preview["snapshot"], "result": result, "receipt": receipt, "nativeFunction": RESTORE_FUNCTION, "restartRequired": False, "relogRequired": True}


def delete_snapshot(root, snapshot_id, confirm):
    if str(confirm or "") != DELETE_CONFIRM:
        raise PermissionError(f"confirmation must be exactly {DELETE_CONFIRM!r}")
    path, envelope = _load_snapshot(root, snapshot_id)
    public = _public_snapshot(envelope)
    path.unlink()
    return {"ok": True, "deleted": public}


def download(root, snapshot_id):
    _, envelope = _load_snapshot(root, snapshot_id)
    data = json.dumps(envelope["transfer"], indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    return data, f"{snapshot_id}.json", hashlib.sha256(data).hexdigest()
