#!/usr/bin/env python3
"""Canonical player identity reads and guarded orphan/character lifecycle writes."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import secrets


OFFLINE_STATES = {"offline", "disconnected", "inactive"}
CONFIRM_CLEANUP = "CLEAN ORPHAN PLAYER STATE"
MAX_SAMPLE = 100


def _positive(value, label="account id"):
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def canonical_lateral(account_expression, alias="ps"):
    """Return the one-row LATERAL join used by trusted internal SQL builders."""
    if account_expression not in {"a.id", "acc.id", "player_a.owner_account_id"}:
        raise ValueError("unsupported canonical player-state account expression")
    if alias not in {"ps", "owner_ps"}:
        raise ValueError("unsupported canonical player-state alias")
    return f"""
        join lateral (
          select ps2.*
          from dune.player_state ps2
          where ps2.account_id={account_expression}
          order by ps2.last_login_time desc nulls last, ps2.id desc
          limit 1
        ) {alias} on true
    """


def integrity(query, sample_limit=25):
    sample_limit = max(1, min(int(sample_limit), MAX_SAMPLE))
    summary_rows = query("""
        with counts as (
          select eps.account_id,count(*)::int as row_count
          from dune.encrypted_player_state eps
          group by eps.account_id
        )
        select
          (select count(*)::int from dune.encrypted_player_state) as player_state_rows,
          (select count(*)::int from dune.accounts) as account_rows,
          (select count(*)::int from counts where row_count>1) as duplicate_accounts,
          (select coalesce(sum(row_count-1),0)::int from counts where row_count>1) as duplicate_excess_rows,
          (select count(*)::int from dune.encrypted_player_state eps
             where not exists (select 1 from dune.accounts a where a.id=eps.account_id)) as orphan_rows,
          (select count(*)::int from dune.encrypted_player_state eps
             where eps.player_pawn_id is not null
               and not exists (select 1 from dune.actors a where a.id=eps.player_pawn_id)) as missing_pawn_references,
          (select count(*)::int from dune.encrypted_player_state eps
             where eps.player_controller_id is not null
               and not exists (select 1 from dune.actors a where a.id=eps.player_controller_id)) as missing_controller_references
    """)
    summary = dict(summary_rows[0]) if summary_rows else {}
    for key in (
        "player_state_rows", "account_rows", "duplicate_accounts", "duplicate_excess_rows",
        "orphan_rows", "missing_pawn_references", "missing_controller_references",
    ):
        summary[key] = int(summary.get(key) or 0)
    duplicates = query("""
        select ps.account_id,count(*)::int as row_count,
               max(ps.last_login_time) as newest_login,
               array_agg(ps.id order by ps.last_login_time desc nulls last,ps.id desc) as player_state_ids
        from dune.player_state ps
        join dune.accounts a on a.id=ps.account_id
        group by ps.account_id
        having count(*)>1
        order by count(*) desc,ps.account_id
        limit %s
    """, (sample_limit,))
    orphans = query("""
        select eps.id as player_state_id,eps.account_id,eps.player_controller_id,eps.player_pawn_id,
               eps.online_status::text as online_status,eps.last_login_time
        from dune.encrypted_player_state eps
        where not exists (select 1 from dune.accounts a where a.id=eps.account_id)
        order by eps.last_login_time desc nulls last,eps.id desc
        limit %s
    """, (sample_limit,))
    summary["healthy"] = not (summary["duplicate_accounts"] or summary["orphan_rows"])
    return {
        "ok": True,
        "readOnly": True,
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "summary": summary,
        "duplicates": [dict(row) for row in duplicates],
        "orphans": [dict(row) for row in orphans],
        "canonicalRule": "newest last_login_time, then highest player_state id",
        "repairable": {"orphanRows": summary["orphan_rows"]},
        "duplicatePolicy": "Reads select one canonical row; duplicates are reported but never deleted automatically.",
    }


def cleanup_plan(query):
    rows = query("""
        select count(*)::int as orphan_rows,
               coalesce(md5(string_agg(eps.id::text || ':' || eps.account_id::text,',' order by eps.id)),'') as orphan_digest,
               coalesce(min(eps.id),0) as first_id,coalesce(max(eps.id),0) as last_id
        from dune.encrypted_player_state eps
        where not exists (select 1 from dune.accounts a where a.id=eps.account_id)
    """)
    row = dict(rows[0]) if rows else {}
    evidence = {
        "orphanRows": int(row.get("orphan_rows") or 0),
        "orphanDigest": str(row.get("orphan_digest") or ""),
        "firstId": int(row.get("first_id") or 0),
        "lastId": int(row.get("last_id") or 0),
    }
    return {
        "ok": True,
        "dryRun": True,
        "canExecute": evidence["orphanRows"] > 0,
        "evidence": evidence,
        "expectedFingerprint": _sha256(evidence),
        "confirm": CONFIRM_CLEANUP,
        "backupRequired": True,
        "deletionScope": "Only encrypted_player_state rows whose account_id has no matching dune.accounts row.",
    }


def character_plan(query, account_id):
    account_id = _positive(account_id)
    rows = query("""
        select a.id as account_id,a.\"user\" as fls_id,a.funcom_id,a.platform_name,a.platform_id,
               ps.id as player_state_id,ps.character_name,ps.online_status::text as online_status,
               ps.life_state::text as life_state,ps.last_login_time,ps.player_controller_id,ps.player_pawn_id,
               (select count(*)::int from dune.encrypted_player_state eps where eps.account_id=a.id) as state_row_count,
               (select count(*)::int from dune.encrypted_player_state eps
                  where eps.account_id=a.id and lower(eps.online_status::text) not in ('offline','disconnected','inactive')) as non_offline_rows,
               to_regprocedure('dune.delete_account(text,text)') is not null as native_delete_available
        from dune.accounts a
        join lateral (
          select ps2.* from dune.player_state ps2
          where ps2.account_id=a.id
          order by ps2.last_login_time desc nulls last,ps2.id desc
          limit 1
        ) ps on true
        where a.id=%s
    """, (account_id,))
    if not rows:
        raise ValueError("account does not have a current character")
    row = dict(rows[0])
    evidence = {
        "accountId": account_id,
        "flsId": str(row.get("fls_id") or ""),
        "funcomId": str(row.get("funcom_id") or ""),
        "platformName": str(row.get("platform_name") or ""),
        "platformId": str(row.get("platform_id") or ""),
        "playerStateId": int(row["player_state_id"]),
        "characterName": str(row.get("character_name") or ""),
        "onlineStatus": str(row.get("online_status") or "unknown"),
        "lastLoginTime": row.get("last_login_time"),
        "playerControllerId": row.get("player_controller_id"),
        "playerPawnId": row.get("player_pawn_id"),
        "stateRowCount": int(row.get("state_row_count") or 0),
    }
    blockers = []
    if int(row.get("non_offline_rows") or 0):
        blockers.append("one or more player-state rows are not explicitly offline")
    if not row.get("native_delete_available"):
        blockers.append("dune.delete_account(text,text) is not available")
    if not evidence["flsId"]:
        blockers.append("account has no native FLS user id")
    return {
        "ok": True,
        "dryRun": True,
        "canExecute": not blockers,
        "accountId": account_id,
        "character": evidence,
        "blockers": blockers,
        "expectedFingerprint": _sha256(evidence),
        "confirm": f"DELETE CHARACTER {account_id}",
        "nativeFunction": "dune.delete_account(text,text)",
        "backupRequired": True,
        "restartRequired": False,
        "cleanupOrphansAfterNativeDelete": True,
        "irreversibleWithoutBackup": True,
    }


def _connection_query(conn, sql, params=()):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        names = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]
        return [dict(row) if isinstance(row, dict) else dict(zip(names, row)) for row in cursor.fetchall()]


def _write_receipt(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ValueError("player identity receipt directory cannot be a symbolic link")
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _begin_receipt(root, action, principal, backup, before):
    root = pathlib.Path(root)
    receipt_id = "player-identity-" + secrets.token_hex(16)
    payload = {
        "schemaVersion": 1,
        "receiptId": receipt_id,
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "pending",
        "action": action,
        "principal": str(principal or "owner-recovery")[:128],
        "backup": backup,
        "before": before,
    }
    payload["receiptSha256"] = _sha256(payload)
    path = root / f"pending-{receipt_id}.json"
    _write_receipt(path, payload)
    return path, payload


def _finalize_receipt(pending_path, payload, result):
    pending_path = pathlib.Path(pending_path)
    final = dict(payload)
    final.update({
        "status": "committed",
        "committedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "result": result,
    })
    final.pop("receiptSha256", None)
    final["receiptSha256"] = _sha256(final)
    final_path = pending_path.parent / f"{final['receiptId']}.json"
    try:
        _write_receipt(final_path, final)
        pending_path.unlink(missing_ok=True)
        return {"id": final["receiptId"], "path": str(final_path), "sha256": final["receiptSha256"], "status": "committed"}
    except Exception as exc:
        return {
            "id": final["receiptId"], "path": str(pending_path),
            "sha256": payload["receiptSha256"], "status": "pending-finalization-failed",
            "error": str(exc)[:1000],
        }


def cleanup_orphans(db_connect, create_backup, receipt_root, expected_fingerprint, confirm, principal=""):
    if str(confirm or "") != CONFIRM_CLEANUP:
        raise PermissionError(f"confirmation must be exactly {CONFIRM_CLEANUP!r}")
    preview = cleanup_plan(lambda sql, params=(): _standalone_query(db_connect, sql, params))
    if preview["expectedFingerprint"] != str(expected_fingerprint or ""):
        raise RuntimeError("orphan player-state evidence changed after preview; preview again")
    if not preview["canExecute"]:
        raise ValueError("there are no orphan player-state rows to clean")
    backup = create_backup()
    pending_path, pending = _begin_receipt(receipt_root, "cleanup-orphans", principal, backup, preview)
    conn = db_connect()
    try:
        conn.autocommit = False
        current = cleanup_plan(lambda sql, params=(): _connection_query(conn, sql, params))
        if current["expectedFingerprint"] != preview["expectedFingerprint"]:
            raise RuntimeError("orphan player-state evidence changed while acquiring the transaction")
        rows = _connection_query(conn, """
            delete from dune.encrypted_player_state eps
            where not exists (select 1 from dune.accounts a where a.id=eps.account_id)
            returning eps.id,eps.account_id
        """)
        after = cleanup_plan(lambda sql, params=(): _connection_query(conn, sql, params))
        if after["evidence"]["orphanRows"] != 0 or len(rows) != preview["evidence"]["orphanRows"]:
            raise RuntimeError("orphan cleanup post-write verification failed")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result = {"deletedRows": len(rows), "deletedIds": [int(row["id"]) for row in rows], "verifiedOrphansRemaining": 0}
    receipt = _finalize_receipt(pending_path, pending, result)
    return {"ok": True, "dryRun": False, "backup": backup, "receipt": receipt, **result}


def delete_character(db_connect, create_backup, receipt_root, account_id, reason, expected_fingerprint, confirm, principal=""):
    account_id = _positive(account_id)
    expected_confirm = f"DELETE CHARACTER {account_id}"
    if str(confirm or "") != expected_confirm:
        raise PermissionError(f"confirmation must be exactly {expected_confirm!r}")
    reason = " ".join(str(reason or "").split())
    if len(reason) < 3 or len(reason) > 500:
        raise ValueError("deletion reason must be between 3 and 500 characters")
    preview = character_plan(lambda sql, params=(): _standalone_query(db_connect, sql, params), account_id)
    if preview["expectedFingerprint"] != str(expected_fingerprint or ""):
        raise RuntimeError("character identity changed after preview; preview again")
    if not preview["canExecute"]:
        raise PermissionError("; ".join(preview["blockers"]))
    backup = create_backup()
    pending_path, pending = _begin_receipt(receipt_root, "delete-character", principal, backup, preview)
    conn = db_connect()
    try:
        conn.autocommit = False
        _connection_query(conn, "select pg_advisory_xact_lock(%s)", (account_id,))
        _connection_query(conn, """
            select eps.id
            from dune.encrypted_player_state eps
            join dune.encrypted_accounts ea on ea.id=eps.account_id
            where eps.account_id=%s
            order by eps.id
            for update of eps,ea
        """, (account_id,))
        current = character_plan(lambda sql, params=(): _connection_query(conn, sql, params), account_id)
        if current["expectedFingerprint"] != preview["expectedFingerprint"]:
            raise RuntimeError("character identity changed while acquiring transaction locks")
        if not current["canExecute"]:
            raise PermissionError("; ".join(current["blockers"]))
        deleted = _connection_query(conn, "select dune.delete_account(%s,%s) as deleted", (current["character"]["flsId"], reason))
        if not deleted or not deleted[0].get("deleted"):
            raise RuntimeError("native delete_account did not delete the selected character")
        orphans = _connection_query(conn, """
            delete from dune.encrypted_player_state eps
            where not exists (select 1 from dune.accounts a where a.id=eps.account_id)
            returning eps.id,eps.account_id
        """)
        verification = _connection_query(conn, """
            select
              exists(select 1 from dune.accounts where id=%s) as account_exists,
              exists(select 1 from dune.encrypted_player_state where account_id=%s) as player_state_exists,
              (select count(*)::int from dune.encrypted_player_state eps
                 where not exists (select 1 from dune.accounts a where a.id=eps.account_id)) as orphan_rows
        """, (account_id, account_id))[0]
        if verification.get("account_exists") or verification.get("player_state_exists") or int(verification.get("orphan_rows") or 0):
            raise RuntimeError("native character deletion post-write verification failed")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result = {
        "accountId": account_id,
        "characterName": preview["character"]["characterName"],
        "nativeDeleted": True,
        "orphanRowsCleaned": len(orphans),
        "verified": True,
        "restartRequired": False,
    }
    receipt = _finalize_receipt(pending_path, pending, result)
    return {"ok": True, "dryRun": False, "backup": backup, "receipt": receipt, **result}


def _standalone_query(db_connect, sql, params=()):
    conn = db_connect()
    try:
        return _connection_query(conn, sql, params)
    finally:
        conn.close()
