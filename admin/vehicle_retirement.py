#!/usr/bin/env python3
"""Preview-bound, recoverable retirement of parked player vehicles.

The current game exposes one ``VehicleBackup`` slot per character.  That slot
is not sufficient for an account that owns more than one abandoned vehicle, so
this workflow uses the game's first-party ``VehicleRecovery`` queue instead.
``store_recovered_vehicles_wiped_before_spawn`` preserves the actor, records
the owning character, removes its world permission rows, and lets the native
restore path recreate a rank-1 permission later.  A private pre-action
snapshot is still written before the native call so an operator can recover
the exact permissions, inventories, items, and modules if the game contract
changes.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import secrets


MAX_SCAN = 500
MAX_VEHICLES = 20
OFFLINE_STATES = {"offline", "disconnected", "inactive"}
NATIVE_FUNCTION = "dune.store_recovered_vehicles_wiped_before_spawn(bigint[],recoveredvehiclereason,boolean)"
NATIVE_RECOVERY_REASON = "Migrated"


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
    primary = [owner for owner in owners if owner["rank"] == 1]
    account_ids = sorted({owner["accountId"] for owner in primary if owner["accountId"] is not None})
    owner = primary[0] if len(primary) == 1 else {}
    actor_class = str(row.get("actor_class") or row.get("class") or "")
    class_short = actor_class.rsplit(".", 1)[-1]
    normalized = {
        "vehicleId": int(row["vehicle_id"]),
        "actorName": str(row.get("actor_name") or f"Vehicle {row['vehicle_id']}"),
        "class": actor_class,
        "classShort": class_short,
        "isOrnithopter": "ornithopter" in class_short.lower(),
        "map": str(row.get("map") or ""),
        "partitionId": int(row["partition_id"]) if row.get("partition_id") is not None else None,
        "dimension": int(row["dimension_index"]) if row.get("dimension_index") is not None else None,
        "transform": row.get("transform"),
        "actorState": str(row.get("actor_state") or ""),
        "partitionServerId": str(row.get("partition_server_id") or ""),
        "activeServerId": str(row.get("active_server_id") or ""),
        "partitionActive": bool(row.get("active_server_id")),
        "customizationId": str(row.get("customization_id") or "None"),
        "owners": owners,
        "primaryOwnerCount": len(primary),
        "primaryAccountIds": account_ids,
        "ownerPlayerId": int(owner["playerId"]) if owner.get("playerId") is not None else None,
        "ownerAccountId": int(owner["accountId"]) if owner.get("accountId") is not None else None,
        "ownerCharacterName": str(owner.get("characterName") or ""),
        "ownerOnlineStatus": str(owner.get("onlineStatus") or "unknown"),
        "backupExists": bool(row.get("backup_exists")),
        "recoveredExists": bool(row.get("recovered_exists")),
        "inventoryCount": int(row.get("inventory_count") or 0),
        "itemCount": int(row.get("item_count") or 0),
        "moduleCount": int(row.get("module_count") or 0),
        "contentHashes": {
            "actor": str(row.get("actor_hash") or ""),
            "permissions": str(row.get("permission_hash") or ""),
            "items": str(row.get("item_hash") or ""),
            "modules": str(row.get("module_hash") or ""),
        },
        "nativeFunctionAvailable": bool(row.get("native_function_available")),
    }
    fingerprint_value = dict(normalized)
    normalized["fingerprint"] = hashlib.sha256(_canonical(fingerprint_value).encode()).hexdigest()
    return normalized


def _vehicle_filter(vehicle_id=None, account_id=None):
    vehicle_id = _positive(vehicle_id, "vehicle id") if vehicle_id is not None else None
    account_id = _positive(account_id, "account id") if account_id is not None else None
    return vehicle_id, account_id


def scan(query, limit=100, vehicle_id=None, account_id=None):
    limit = max(1, min(int(limit), MAX_SCAN))
    vehicle_id, account_id = _vehicle_filter(vehicle_id, account_id)
    rows = query("""
        with vehicle_rows as (
          select v.id as vehicle_id,
                 coalesce(nullif(pa.actor_name,''),'Vehicle ' || v.id::text) as actor_name,
                 a.class as actor_class,a.map,a.partition_id,a.dimension_index,a.transform,
                 coalesce(ast.state::text,'') as actor_state,
                 wp.server_id as partition_server_id,asi.server_id as active_server_id,
                 coalesce(a.properties -> regexp_replace(a.class, '^.*\\.', '') ->> 'm_CustomizationId','None') as customization_id,
                 exists(select 1 from dune.backup_vehicles bv where bv.vehicle_id=v.id) as backup_exists,
                 exists(select 1 from dune.recovered_vehicles rv where rv.vehicle_id=v.id) as recovered_exists,
                 (select count(*) from dune.inventories i where i.actor_id=v.id) as inventory_count,
                 (select count(*) from dune.items i join dune.inventories inv on inv.id=i.inventory_id where inv.actor_id=v.id and coalesce(inv.inventory_type,0)=0) as item_count,
                 (select count(*) from dune.vehicle_modules vm where vm.vehicle_id=v.id) as module_count,
                 md5(to_jsonb(a)::text) as actor_hash,
                 (select md5(coalesce(string_agg(to_jsonb(par)::text,',' order by par.player_id,par.rank),'')) from dune.permission_actor_rank par where par.permission_actor_id=v.id) as permission_hash,
                 (select md5(coalesce(string_agg(to_jsonb(i)::text,',' order by i.id),'')) from dune.items i join dune.inventories inv on inv.id=i.inventory_id where inv.actor_id=v.id) as item_hash,
                 (select md5(coalesce(string_agg(to_jsonb(vm)::text,',' order by vm.id),'')) from dune.vehicle_modules vm where vm.vehicle_id=v.id) as module_hash,
                 to_regprocedure('dune.store_recovered_vehicles_wiped_before_spawn(bigint[],dune.recoveredvehiclereason,boolean)') is not null as native_function_available
          from dune.vehicles v
          join dune.actors a on a.id=v.id
          left join lateral (select pa.actor_name from dune.permission_actor pa where pa.actor_id=v.id order by pa.actor_name limit 1) pa on true
          left join dune.actor_state ast on ast.actor_id=v.id
          left join dune.world_partition wp on wp.partition_id=a.partition_id
          left join dune.active_server_ids asi on asi.server_id=wp.server_id
          where (%s::bigint is null or v.id=%s::bigint)
            and (%s::bigint is null or exists(
              select 1 from dune.permission_actor_rank par_account
              join dune.player_state ps_account on ps_account.player_controller_id=par_account.player_id
              where par_account.permission_actor_id=v.id and par_account.rank=1 and ps_account.account_id=%s::bigint
            ))
        )
        select vr.*,
               coalesce(jsonb_agg(distinct jsonb_build_object(
                 'playerId',par.player_id,'rank',par.rank,'accountId',ps.account_id,
                 'characterName',ps.character_name,'onlineStatus',coalesce(ps.online_status::text,'unknown')
               )) filter (where par.player_id is not null),'[]'::jsonb) as owners
        from vehicle_rows vr
        left join dune.permission_actor_rank par on par.permission_actor_id=vr.vehicle_id
        left join dune.player_state ps on ps.player_controller_id=par.player_id
        group by vr.vehicle_id,vr.actor_name,vr.actor_class,vr.map,vr.partition_id,vr.dimension_index,vr.transform,
                 vr.actor_state,vr.partition_server_id,vr.active_server_id,vr.customization_id,vr.backup_exists,
                 vr.recovered_exists,vr.inventory_count,vr.item_count,vr.module_count,vr.actor_hash,vr.permission_hash,
                 vr.item_hash,vr.module_hash,vr.native_function_available
        order by vr.vehicle_id
        limit %s
    """, (vehicle_id, vehicle_id, account_id, account_id, limit))
    return [_normalize(row) for row in rows]


def _ids(values):
    if isinstance(values, str):
        values = [part for part in values.split(",") if part.strip()]
    values = list(values or [])
    result = []
    for value in values:
        parsed = _positive(value, "vehicle id")
        if parsed not in result:
            result.append(parsed)
    if not result:
        raise ValueError("at least one vehicle id is required")
    if len(result) > MAX_VEHICLES:
        raise ValueError(f"at most {MAX_VEHICLES} vehicles may be archived together")
    return result


def plan(query, vehicle_ids, account_id=None, *, allow_inventory_wipe=False, require_ornithopters=True):
    vehicle_ids = _ids(vehicle_ids)
    account_id = _positive(account_id, "account id") if account_id is not None else None
    rows = scan(query, limit=MAX_VEHICLES, account_id=account_id)
    by_id = {row["vehicleId"]: row for row in rows}
    selected = [by_id[vehicle_id] for vehicle_id in vehicle_ids if vehicle_id in by_id]
    blockers = []
    missing = [vehicle_id for vehicle_id in vehicle_ids if vehicle_id not in by_id]
    if missing:
        blockers.append("vehicle(s) not found or not owned by the selected account: " + ", ".join(str(value) for value in missing))
    if account_id is None:
        accounts = sorted({value for row in selected for value in row["primaryAccountIds"]})
        if len(accounts) == 1:
            account_id = accounts[0]
        else:
            blockers.append("choose one account that owns every selected vehicle")
    if not selected:
        blockers.append("no selected vehicles are available")
    for row in selected:
        label = f"vehicle {row['vehicleId']} ({row['actorName']})"
        if row["primaryOwnerCount"] != 1 or row["ownerAccountId"] != account_id:
            blockers.append(f"{label} does not have exactly one rank-1 owner in account {account_id}")
        if row["ownerOnlineStatus"].lower() not in OFFLINE_STATES:
            blockers.append(f"{label} owner is not explicitly offline")
        if row["partitionActive"]:
            blockers.append(f"{label} partition still has an assigned active server; stop that map before archiving")
        if row["actorState"]:
            blockers.append(f"{label} already has actor state {row['actorState']}")
        if row["recoveredExists"]:
            blockers.append(f"{label} is already in vehicle recovery")
        if not row["nativeFunctionAvailable"]:
            blockers.append("current game database does not expose the native multi-vehicle recovery function")
        if require_ornithopters and not row["isOrnithopter"]:
            blockers.append(f"{label} is not an ornithopter")
    inventory_items = sum(row["itemCount"] for row in selected)
    target_label = "THOPTERS" if require_ornithopters else "VEHICLES"
    id_text = ",".join(str(value) for value in vehicle_ids)
    confirm = f"ARCHIVE {target_label} {id_text}"
    if inventory_items and allow_inventory_wipe:
        confirm += " AND WIPE VEHICLE INVENTORY"
    return {
        "ok": True,
        "dryRun": True,
        "canExecute": not blockers,
        "vehicles": selected,
        "vehicleIds": vehicle_ids,
        "accountId": account_id,
        "blockers": blockers,
        "inventoryItemCount": inventory_items,
        "inventoryWipeRequired": bool(inventory_items and allow_inventory_wipe),
        "inventoryPreserved": bool(inventory_items and not allow_inventory_wipe),
        "allowInventoryWipe": bool(allow_inventory_wipe),
        "nativeDeleteItems": bool(allow_inventory_wipe),
        "requireOrnithopters": bool(require_ornithopters),
        "expectedFingerprint": hashlib.sha256(_canonical(selected).encode()).hexdigest(),
        "confirm": confirm,
        "nativeFunction": NATIVE_FUNCTION,
        "nativeRecoveryReason": NATIVE_RECOVERY_REASON,
        "gameRecoverable": True,
        "destructiveDelete": False,
        "backupRequired": True,
        "mapRestartRequired": True,
    }


def _connection_query(conn, sql, params=()):
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        names = [column.name if hasattr(column, "name") else column[0] for column in cursor.description]
        return [dict(zip(names, row)) if not isinstance(row, dict) else row for row in cursor.fetchall()]


def _snapshot(conn, vehicle_ids):
    snapshot = []
    for vehicle_id in vehicle_ids:
        item = {"vehicleId": vehicle_id}
        for key, sql in {
            "actor": "select to_jsonb(a) as value from dune.actors a where a.id=%s",
            "vehicle": "select to_jsonb(v) as value from dune.vehicles v where v.id=%s",
            "permissionActors": "select coalesce(jsonb_agg(to_jsonb(pa) order by pa.actor_id),'[]'::jsonb) as value from dune.permission_actor pa where pa.actor_id=%s",
            "permissionRanks": "select coalesce(jsonb_agg(to_jsonb(par) order by par.player_id,par.rank),'[]'::jsonb) as value from dune.permission_actor_rank par where par.permission_actor_id=%s",
            "actorStates": "select coalesce(jsonb_agg(to_jsonb(ast) order by ast.actor_id),'[]'::jsonb) as value from dune.actor_state ast where ast.actor_id=%s",
            "inventories": "select coalesce(jsonb_agg(to_jsonb(i) order by i.id),'[]'::jsonb) as value from dune.inventories i where i.actor_id=%s",
            "items": "select coalesce(jsonb_agg(to_jsonb(item) order by item.id),'[]'::jsonb) as value from dune.items item join dune.inventories inv on inv.id=item.inventory_id where inv.actor_id=%s",
            "modules": "select coalesce(jsonb_agg(to_jsonb(vm) order by vm.id),'[]'::jsonb) as value from dune.vehicle_modules vm where vm.vehicle_id=%s",
        }.items():
            rows = _connection_query(conn, sql, (vehicle_id,))
            value = rows[0].get("value") if rows else None
            item[key] = value
        snapshot.append(item)
    return snapshot


def _write_receipt(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ValueError("vehicle retirement receipt directory cannot be a symbolic link")
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


def list_receipts(root, limit=100):
    root = pathlib.Path(root)
    paths = [path for path in root.glob("*.json") if path.is_file() and not path.is_symlink()] if root.exists() and not root.is_symlink() else []
    result = []
    for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)[:max(1, min(int(limit), 500))]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            result.append({
                "receiptId": value.get("receiptId"),
                "status": value.get("status"),
                "createdAt": value.get("createdAt"),
                "committedAt": value.get("committedAt"),
                "vehicleIds": value.get("vehicleIds") or ((value.get("plan") or {}).get("vehicleIds") or []),
                "accountId": value.get("accountId") or ((value.get("plan") or {}).get("accountId")),
                "path": path.name,
            })
        except (OSError, ValueError, json.JSONDecodeError):
            result.append({"status": "invalid", "path": path.name})
    return result


def archive(connect_fn, backup_fn, receipt_root, *, vehicle_ids, account_id,
            expected_fingerprint, confirm, principal="owner-token",
            allow_inventory_wipe=False, require_ornithopters=True):
    vehicle_ids = _ids(vehicle_ids)
    account_id = _positive(account_id, "account id")
    expected_fingerprint = str(expected_fingerprint or "").strip().lower()
    if len(expected_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in expected_fingerprint):
        raise ValueError("a valid preview fingerprint is required")
    target_label = "THOPTERS" if require_ornithopters else "VEHICLES"
    expected_confirm = f"ARCHIVE {target_label} {','.join(str(value) for value in vehicle_ids)}"
    supplied_confirm = str(confirm or "").strip()
    if not supplied_confirm.startswith(expected_confirm):
        raise PermissionError(f"confirmation must start with {expected_confirm}")
    conn = connect_fn()
    pending = None
    try:
        conn.autocommit = False
        with conn.cursor() as cursor:
            cursor.execute("set transaction isolation level serializable")
            cursor.execute("set local statement_timeout = '120s'")
            for vehicle_id in sorted(vehicle_ids):
                cursor.execute("select pg_advisory_xact_lock(%s)", (vehicle_id,))
            cursor.execute("select id from dune.vehicles where id = any(%s) for update", (vehicle_ids,))
            locked_vehicle_ids = {int(row[0]) for row in cursor.fetchall()}
            if locked_vehicle_ids != set(vehicle_ids):
                missing = sorted(set(vehicle_ids) - locked_vehicle_ids)
                raise ValueError("vehicle(s) not found: " + ", ".join(str(value) for value in missing))
            cursor.execute("select id from dune.actors where id = any(%s) for update", (vehicle_ids,))
            cursor.execute("select permission_actor_id from dune.permission_actor_rank where permission_actor_id = any(%s) for update", (vehicle_ids,))
            cursor.execute("select player_controller_id from dune.player_state where account_id=%s for update", (account_id,))
        locked_plan = plan(lambda sql, params=(): _connection_query(conn, sql, params), vehicle_ids, account_id, allow_inventory_wipe=allow_inventory_wipe, require_ornithopters=require_ornithopters)
        if locked_plan["expectedFingerprint"] != expected_fingerprint:
            raise RuntimeError("vehicle set changed after preview; refresh and review the new fingerprint")
        if supplied_confirm != locked_plan["confirm"]:
            raise PermissionError(f"confirmation must be exactly {locked_plan['confirm']}")
        if not locked_plan["canExecute"]:
            raise PermissionError("vehicle archive is blocked: " + "; ".join(locked_plan["blockers"]))
        backup = backup_fn()
        if not backup or not backup.get("path") or int(backup.get("bytes") or 0) <= 0:
            raise RuntimeError("full database backup did not produce a non-empty artifact")
        receipt_root = pathlib.Path(receipt_root)
        receipt_id = secrets.token_hex(12)
        pending = receipt_root / f"pending-{receipt_id}.json"
        inventory_snapshot = _snapshot(conn, vehicle_ids)
        receipt = {
            "version": 1,
            "receiptId": receipt_id,
            "operation": "vehicle-recovery-retirement",
            "status": "pending",
            "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "principal": str(principal)[:128],
            "vehicleIds": vehicle_ids,
            "accountId": account_id,
            "plan": locked_plan,
            "databaseBackup": backup,
            "inventorySnapshot": inventory_snapshot,
            "nativeInventoryWipe": bool(locked_plan["nativeDeleteItems"]),
            "nativeRecoveryReason": NATIVE_RECOVERY_REASON,
        }
        _write_receipt(pending, receipt)
        with conn.cursor() as cursor:
            cursor.execute(
                "select dune.store_recovered_vehicles_wiped_before_spawn(%s::bigint[],%s::dune.recoveredvehiclereason,%s)",
                (vehicle_ids, NATIVE_RECOVERY_REASON, bool(locked_plan["nativeDeleteItems"])),
            )
        verification = _connection_query(conn, """
            select v.id as vehicle_id,
                   exists(select 1 from dune.actors a where a.id=v.id) as actor_exists,
                   exists(select 1 from dune.recovered_vehicles rv join dune.player_state ps on ps.id=rv.character_id where rv.vehicle_id=v.id and ps.account_id=%s) as recovery_exists,
                   exists(select 1 from dune.actor_state ast where ast.actor_id=v.id and ast.state='VehicleRecovery') as vehicle_recovery_state,
                   (select count(*) from dune.permission_actor pa where pa.actor_id=v.id) as permission_actor_count,
                   (select count(*) from dune.permission_actor_rank par where par.permission_actor_id=v.id) as permission_rank_count,
                   (select count(*) from dune.items i join dune.inventories inv on inv.id=i.inventory_id where inv.actor_id=v.id and coalesce(inv.inventory_type,0)=0) as item_count_after
            from dune.vehicles v where v.id=any(%s) order by v.id
        """, (account_id, vehicle_ids))
        expected_item_counts = {int(vehicle["vehicleId"]): int(vehicle.get("itemCount") or 0) for vehicle in locked_plan["vehicles"]}
        if len(verification) != len(vehicle_ids) or any(
            not row.get("actor_exists")
            or not row.get("recovery_exists")
            or not row.get("vehicle_recovery_state")
            or int(row.get("permission_actor_count") or 0) != 0
            or int(row.get("permission_rank_count") or 0) != 0
            or int(row.get("item_count_after") or 0) != (0 if locked_plan["nativeDeleteItems"] else expected_item_counts.get(int(row["vehicle_id"]), -1))
            for row in verification
        ):
            raise RuntimeError("native vehicle recovery verification failed; transaction was rolled back")
        conn.commit()
        receipt["status"] = "committed"
        receipt["committedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        receipt["verification"] = verification
        final = receipt_root / f"vehicles-{ '-'.join(str(value) for value in vehicle_ids) }-{receipt_id}.json"
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
            "vehicleIds": vehicle_ids,
            "accountId": account_id,
            "databaseBackup": backup,
            "receipt": str(receipt_path),
            "receiptStatus": receipt_status,
            "receiptFinalizeError": receipt_finalize_error,
            "verification": verification,
            "inventorySnapshot": inventory_snapshot,
            "nativeInventoryWipe": bool(locked_plan["nativeDeleteItems"]),
            "nativeRecoveryReason": NATIVE_RECOVERY_REASON,
            "gameRecoverable": True,
            "destructiveDelete": False,
            "mapRestartRequired": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
