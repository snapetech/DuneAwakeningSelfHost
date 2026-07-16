"""Guarded character-cosmetic catalog and persistent-state edits.

Cosmetic unlocks are stored inside a player pawn actor's JSON properties.  The
game schema exposes no first-party mutation routine for this surface, so every
write in this module is offline-only, row-locked, compare-and-swap verified,
and designed to be preceded by a full database backup by the caller.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import secrets


CATALOG_VERSION = 1
MAX_CATALOG_ITEMS = 5000
MAX_UNLOCKED_ITEMS = 10000
RECEIPT_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}$")
PROPERTY_PATH = (
    "CustomizationLibraryActorComponent",
    "m_UnlockedCustomizationSerializableList",
    "m_UnlockedCustomizationIds",
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _catalog_id(value):
    value = str(value or "")
    if not value or len(value) > 192 or any(ord(ch) < 32 for ch in value):
        raise ValueError("cosmetic id must be 1-192 printable characters")
    return value


def load_catalog(path):
    path = pathlib.Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != CATALOG_VERSION:
        raise ValueError("cosmetic catalog must be a version 1 object")
    rows = payload.get("items")
    if not isinstance(rows, list) or len(rows) > MAX_CATALOG_ITEMS:
        raise ValueError(f"cosmetic catalog items must be an array of at most {MAX_CATALOG_ITEMS} rows")
    seen = set()
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each cosmetic catalog row must be an object")
        cosmetic_id = _catalog_id(row.get("id"))
        if cosmetic_id in seen:
            raise ValueError(f"duplicate cosmetic id: {cosmetic_id}")
        seen.add(cosmetic_id)
        name = str(row.get("name") or cosmetic_id).strip()[:240]
        category = str(row.get("category") or "Other").strip()[:120]
        mode = str(row.get("unlockMode") or "customization").strip().lower()
        if mode not in {"customization", "inventory"}:
            raise ValueError(f"invalid unlockMode for {cosmetic_id}: {mode}")
        normalized.append({
            "id": cosmetic_id,
            "name": name or cosmetic_id,
            "category": category or "Other",
            "unlockMode": mode,
            "enabled": bool(row.get("enabled", True)),
            "source": str(row.get("source") or "operator-catalog")[:160],
            "confidence": str(row.get("confidence") or "unknown")[:32],
        })
    result = dict(payload)
    result["items"] = normalized
    result["counts"] = {
        "total": len(normalized),
        "customization": sum(1 for row in normalized if row["unlockMode"] == "customization"),
        "inventory": sum(1 for row in normalized if row["unlockMode"] == "inventory"),
        "enabled": sum(1 for row in normalized if row["enabled"]),
    }
    return result


def catalog_index(catalog):
    return {row["id"]: row for row in catalog.get("items", [])}


def _entries(properties):
    node = properties
    for key in PROPERTY_PATH:
        if not isinstance(node, dict) or key not in node:
            raise ValueError("player pawn does not expose the expected customization-library property path")
        node = node[key]
    if not isinstance(node, list):
        raise ValueError("player customization-library unlock collection is not an array")
    if len(node) > MAX_UNLOCKED_ITEMS:
        raise ValueError(f"player cosmetic collection exceeds the {MAX_UNLOCKED_ITEMS}-entry safety limit")
    for row in node:
        if not isinstance(row, dict) or not isinstance(row.get("m_CustomizationId"), str):
            raise ValueError("player cosmetic collection contains an unsupported entry")
    return node


def _replace_entries(properties, entries):
    updated = copy.deepcopy(properties)
    node = updated
    for key in PROPERTY_PATH[:-1]:
        node = node[key]
    node[PROPERTY_PATH[-1]] = entries
    return updated


def ids_from_entries(entries):
    return [row["m_CustomizationId"] for row in entries]


def plan_entries(entries, catalog, action, cosmetic_id=None):
    action = str(action or "").strip().lower()
    if action not in {"add", "remove", "unlock-all"}:
        raise ValueError("cosmetic action must be add, remove, or unlock-all")
    before = copy.deepcopy(entries)
    index = catalog_index(catalog)
    current_ids = ids_from_entries(before)
    if action in {"add", "remove"}:
        cosmetic_id = _catalog_id(cosmetic_id)
        row = index.get(cosmetic_id)
        if not row or not row.get("enabled") or row.get("unlockMode") != "customization":
            raise ValueError("cosmetic id is not an enabled customization entry in the reviewed catalog")
    if action == "add":
        after = before if cosmetic_id in current_ids else before + [{"m_CustomizationId": cosmetic_id}]
    elif action == "remove":
        after = [row for row in before if row["m_CustomizationId"] != cosmetic_id]
    else:
        after = copy.deepcopy(before)
        seen = set(current_ids)
        for row in catalog.get("items", []):
            if row.get("enabled") and row.get("unlockMode") == "customization" and row["id"] not in seen:
                after.append({"m_CustomizationId": row["id"]})
                seen.add(row["id"])
    before_ids = ids_from_entries(before)
    after_ids = ids_from_entries(after)
    before_set, after_set = set(before_ids), set(after_ids)
    return {
        "action": action,
        "cosmeticId": cosmetic_id,
        "before": before,
        "after": after,
        "beforeHash": _hash(before),
        "afterHash": _hash(after),
        "beforeCount": len(before),
        "afterCount": len(after),
        "added": sorted(after_set - before_set),
        "removed": sorted(before_set - after_set),
        "changed": before != after,
    }


PLAYER_SQL = """
    select ps.account_id, ps.character_name, ps.online_status::text,
           ps.player_pawn_id, a.properties
    from dune.player_state ps
    join dune.actors a on a.id=ps.player_pawn_id
    where ps.player_pawn_id=%s
"""


def inspect_player(query, pawn_id, catalog):
    pawn_id = int(pawn_id)
    if pawn_id <= 0:
        raise ValueError("player pawn id must be positive")
    rows = query(PLAYER_SQL, (pawn_id,))
    if len(rows) != 1:
        raise ValueError("player pawn was not found or is ambiguous")
    row = rows[0]
    entries = _entries(row["properties"])
    known = catalog_index(catalog)
    result_entries = []
    for entry in entries:
        cosmetic_id = entry["m_CustomizationId"]
        meta = known.get(cosmetic_id) or {}
        result_entries.append({
            "id": cosmetic_id,
            "name": meta.get("name", cosmetic_id),
            "category": meta.get("category", "Uncatalogued"),
            "catalogued": cosmetic_id in known,
        })
    return {
        "ok": True,
        "player": {key: row.get(key) for key in ("account_id", "character_name", "online_status", "player_pawn_id")},
        "entries": result_entries,
        "count": len(entries),
        "hash": _hash(entries),
        "offline": str(row.get("online_status") or "").lower() == "offline",
    }


def preview(query, pawn_id, catalog, action, cosmetic_id=None):
    status = inspect_player(query, pawn_id, catalog)
    raw = [{"m_CustomizationId": row["id"]} for row in status["entries"]]
    plan = plan_entries(raw, catalog, action, cosmetic_id)
    return {
        "ok": True,
        "dryRun": True,
        "player": status["player"],
        "offline": status["offline"],
        **{key: value for key, value in plan.items() if key not in {"before", "after"}},
    }


def _locked_row(cursor, pawn_id):
    cursor.execute(PLAYER_SQL + " for update of ps, a", (pawn_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("player pawn was not found")
    if isinstance(row, dict):
        return row
    columns = [item[0] for item in cursor.description]
    return dict(zip(columns, row))


def apply(connect, pawn_id, catalog, action, cosmetic_id=None):
    pawn_id = int(pawn_id)
    if pawn_id <= 0:
        raise ValueError("player pawn id must be positive")
    with connect() as connection:
        with connection.cursor() as cursor:
            row = _locked_row(cursor, pawn_id)
            if str(row.get("online_status") or "").lower() != "offline":
                raise PermissionError("cosmetic mutation requires the player to be Offline at the locked write point")
            properties = row["properties"]
            before_entries = _entries(properties)
            plan = plan_entries(before_entries, catalog, action, cosmetic_id)
            if plan["changed"]:
                updated = _replace_entries(properties, plan["after"])
                cursor.execute(
                    "update dune.actors set properties=%s::jsonb where id=%s and properties=%s::jsonb",
                    (_canonical(updated), pawn_id, _canonical(properties)),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("cosmetic compare-and-swap failed; actor state changed concurrently")
                cursor.execute("select properties from dune.actors where id=%s", (pawn_id,))
                verified_row = cursor.fetchone()
                verified_properties = verified_row["properties"] if isinstance(verified_row, dict) else verified_row[0]
                if _hash(_entries(verified_properties)) != plan["afterHash"]:
                    raise RuntimeError("cosmetic post-write verification failed")
            return {
                "ok": True,
                "dryRun": False,
                "player": {key: row.get(key) for key in ("account_id", "character_name", "online_status", "player_pawn_id")},
                **plan,
                "verified": True,
            }


def receipt_root(root):
    return pathlib.Path(root) / "cosmetics" / "receipts"


def write_receipt(root, result, backup, principal=None):
    directory = receipt_root(root)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    receipt_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(8)
    path = directory / f"{receipt_id}.json"
    payload = {
        "version": 1,
        "receiptId": receipt_id,
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "player": result["player"],
        "database": result.get("database"),
        "action": result["action"],
        "cosmeticId": result.get("cosmeticId"),
        "before": result["before"],
        "after": result["after"],
        "beforeHash": result["beforeHash"],
        "afterHash": result["afterHash"],
        "backup": backup,
        "principal": principal or {},
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {"id": receipt_id, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load_receipt(root, receipt_id):
    receipt_id = str(receipt_id or "").strip()
    if not RECEIPT_ID.fullmatch(receipt_id):
        raise ValueError("invalid cosmetic receipt id")
    path = receipt_root(root) / f"{receipt_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or payload.get("receiptId") != receipt_id:
        raise ValueError("invalid cosmetic receipt document")
    if _hash(payload.get("before")) != payload.get("beforeHash") or _hash(payload.get("after")) != payload.get("afterHash"):
        raise ValueError("cosmetic receipt hashes do not match its payload")
    return payload


def rollback(connect, root, receipt_id):
    receipt = load_receipt(root, receipt_id)
    pawn_id = int((receipt.get("player") or {}).get("player_pawn_id"))
    with connect() as connection:
        with connection.cursor() as cursor:
            row = _locked_row(cursor, pawn_id)
            if str(row.get("online_status") or "").lower() != "offline":
                raise PermissionError("cosmetic rollback requires the player to be Offline at the locked write point")
            properties = row["properties"]
            current = _entries(properties)
            if _hash(current) != receipt["afterHash"]:
                raise RuntimeError("cosmetic rollback refused because current state no longer matches the receipt's after hash")
            updated = _replace_entries(properties, receipt["before"])
            cursor.execute(
                "update dune.actors set properties=%s::jsonb where id=%s and properties=%s::jsonb",
                (_canonical(updated), pawn_id, _canonical(properties)),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("cosmetic rollback compare-and-swap failed")
            return {
                "ok": True,
                "dryRun": False,
                "action": "rollback",
                "receiptId": receipt_id,
                "player": {key: row.get(key) for key in ("account_id", "character_name", "online_status", "player_pawn_id")},
                "beforeHash": receipt["afterHash"],
                "afterHash": receipt["beforeHash"],
                "beforeCount": len(receipt["after"]),
                "afterCount": len(receipt["before"]),
                "verified": True,
            }


def list_receipts(root, limit=100):
    limit = max(1, min(int(limit), 500))
    directory = receipt_root(root)
    rows = []
    if not directory.exists():
        return rows
    for path in sorted(directory.glob("*.json"), reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.append({
                "id": payload.get("receiptId"),
                "createdAt": payload.get("createdAt"),
                "action": payload.get("action"),
                "cosmeticId": payload.get("cosmeticId"),
                "player": payload.get("player"),
                "database": payload.get("database"),
                "beforeCount": len(payload.get("before") or []),
                "afterCount": len(payload.get("after") or []),
                "afterHash": payload.get("afterHash"),
            })
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return rows
