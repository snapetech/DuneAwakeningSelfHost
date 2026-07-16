"""Receipted, compare-and-swap player progression JSON mutations."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import secrets
import stat


SCHEMA = "dash-player-progression-receipt/v1"
RECEIPT_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}$")
JSON_ACTIONS = {"add-intel", "unlock-recipe", "unlock-research"}
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_COLLECTION_ROWS = 10000
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
PATHS = {
    "intelPoints": ("TechKnowledgePlayerComponent", "m_TechKnowledgePoints"),
    "recipes": ("CraftingRecipesLibraryActorComponent", "m_KnownItemRecipes"),
    "research": ("TechKnowledgePlayerComponent", "m_TechKnowledge", "m_TechKnowledgeData"),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def state_hash(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _path_value(properties, path):
    node = properties
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"player pawn does not expose progression path {'.'.join(path)}")
        node = node[key]
    return node


def _replace_path(properties, path, value):
    updated = copy.deepcopy(properties)
    node = updated
    for key in path[:-1]:
        if not isinstance(node, dict) or not isinstance(node.get(key), dict):
            raise ValueError(f"player pawn does not expose progression path {'.'.join(path)}")
        node = node[key]
    node[path[-1]] = copy.deepcopy(value)
    return updated


def normalize_state(action, state, include_recipe=False):
    action = str(action or "").strip().lower()
    if action not in JSON_ACTIONS or not isinstance(state, dict):
        raise ValueError("progression state action or payload is invalid")
    expected = {
        "add-intel": {"intelPoints"},
        "unlock-recipe": {"recipes"},
        "unlock-research": {"research", "recipes"} if include_recipe else {"research"},
    }[action]
    if set(state) != expected:
        raise ValueError("progression state fields do not match the action")
    normalized = json.loads(canonical(state))
    if action == "add-intel":
        points = normalized.get("intelPoints")
        if type(points) is not int or not 0 <= points <= 1000000000:
            raise ValueError("progression Intel points are invalid")
    for key in expected - {"intelPoints"}:
        rows = normalized.get(key)
        if not isinstance(rows, list) or len(rows) > MAX_COLLECTION_ROWS:
            raise ValueError(f"progression {key} must be a bounded array")
    if len(canonical(normalized).encode("utf-8")) > MAX_STATE_BYTES:
        raise ValueError("progression affected state exceeds 4 MiB")
    return normalized


def capture_state(action, properties, include_recipe=False):
    action = str(action or "").strip().lower()
    if action == "add-intel":
        state = {"intelPoints": int(_path_value(properties, PATHS["intelPoints"]))}
    elif action == "unlock-recipe":
        state = {"recipes": _path_value(properties, PATHS["recipes"])}
    elif action == "unlock-research":
        state = {"research": _path_value(properties, PATHS["research"])}
        if include_recipe:
            state["recipes"] = _path_value(properties, PATHS["recipes"])
    else:
        raise ValueError("progression action does not use JSON state")
    return normalize_state(action, state, include_recipe=include_recipe)


def replace_state(action, properties, state, include_recipe=False):
    normalized = normalize_state(action, state, include_recipe=include_recipe)
    updated = copy.deepcopy(properties)
    for key, value in normalized.items():
        updated = _replace_path(updated, PATHS[key], value)
    return updated


PLAYER_SQL = """
    select ps.account_id, ps.character_name, ps.online_status::text,
           ps.player_pawn_id, a.properties
    from dune.player_state ps
    join dune.actors a on a.id=ps.player_pawn_id
    where ps.player_pawn_id=%s
"""


def _row(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    columns = [item[0] for item in cursor.description]
    return dict(zip(columns, row))


def apply(connect, pawn_id, action, expected_before, desired_after, include_recipe=False):
    pawn_id = int(pawn_id)
    if pawn_id <= 0:
        raise ValueError("player pawn id must be positive")
    before = normalize_state(action, expected_before, include_recipe=include_recipe)
    after = normalize_state(action, desired_after, include_recipe=include_recipe)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(PLAYER_SQL + " for update of ps, a", (pawn_id,))
            row = _row(cursor)
            if row is None:
                raise ValueError("player pawn was not found")
            if str(row.get("online_status") or "").lower() != "offline":
                raise PermissionError("progression mutation requires the player to be Offline at the locked write point")
            properties = row.get("properties")
            current = capture_state(action, properties, include_recipe=include_recipe)
            if state_hash(current) != state_hash(before):
                raise RuntimeError("progression mutation refused because affected state changed after preview")
            changed = before != after
            if changed:
                updated = replace_state(action, properties, after, include_recipe=include_recipe)
                cursor.execute(
                    "update dune.actors set properties=%s::jsonb where id=%s and properties=%s::jsonb",
                    (canonical(updated), pawn_id, canonical(properties)),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("progression compare-and-swap failed; actor state changed concurrently")
            cursor.execute("select properties from dune.actors where id=%s", (pawn_id,))
            verified = _row(cursor)
            if verified is None or state_hash(capture_state(action, verified["properties"], include_recipe=include_recipe)) != state_hash(after):
                raise RuntimeError("progression post-write verification failed")
            return {
                "ok": True,
                "dryRun": False,
                "action": action,
                "player": {key: row.get(key) for key in ("account_id", "character_name", "online_status", "player_pawn_id")},
                "before": before,
                "after": after,
                "beforeHash": state_hash(before),
                "afterHash": state_hash(after),
                "includeRecipe": bool(include_recipe),
                "changed": changed,
                "verified": True,
            }


def receipt_root(root):
    return pathlib.Path(root) / "progression" / "receipts"


def _secure(path, directory=False):
    path = pathlib.Path(path)
    os.chmod(path, 0o700 if directory else 0o600)
    if os.geteuid() == 0:
        os.chown(path, int(os.environ.get("DUNE_HOST_UID", os.getuid())), int(os.environ.get("DUNE_HOST_GID", os.getgid())))


def receipt_hash(payload):
    return state_hash({key: value for key, value in payload.items() if key != "receiptSha256"})


def write_receipt(root, result, database, target, backup, principal=None, rollback_of=None):
    before = normalize_state(result.get("action"), result.get("before"), include_recipe=bool(result.get("includeRecipe")))
    after = normalize_state(result.get("action"), result.get("after"), include_recipe=bool(result.get("includeRecipe")))
    if state_hash(before) != result.get("beforeHash") or state_hash(after) != result.get("afterHash"):
        raise ValueError("progression result hashes do not match receipt state")
    directory = receipt_root(root)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    _secure(directory, directory=True)
    receipt_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(8)
    payload = {
        "schemaVersion": SCHEMA,
        "receiptId": receipt_id,
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database": str(database),
        "player": result.get("player") or {},
        "action": result.get("action"),
        "target": str(target or "")[:256],
        "includeRecipe": bool(result.get("includeRecipe")),
        "before": before,
        "after": after,
        "beforeHash": result.get("beforeHash"),
        "afterHash": result.get("afterHash"),
        "changed": bool(result.get("changed")),
        "verified": bool(result.get("verified")),
        "backup": backup,
        "principal": principal or {},
        "rollbackOf": rollback_of,
    }
    payload["receiptSha256"] = receipt_hash(payload)
    path = directory / f"{receipt_id}.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    _secure(path)
    return {"id": receipt_id, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load_receipt(root, receipt_id):
    receipt_id = str(receipt_id or "").strip()
    if not RECEIPT_ID.fullmatch(receipt_id):
        raise ValueError("invalid progression receipt id")
    path = receipt_root(root) / f"{receipt_id}.json"
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RECEIPT_BYTES:
        raise ValueError("progression receipt must be a regular file no larger than 8 MiB")
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schemaVersion", "receiptId", "createdAt", "database", "player", "action", "target",
        "includeRecipe", "before", "after", "beforeHash", "afterHash", "changed", "verified",
        "backup", "principal", "rollbackOf", "receiptSha256",
    }
    if set(payload) != expected or payload.get("schemaVersion") != SCHEMA or payload.get("receiptId") != receipt_id:
        raise ValueError("invalid progression receipt document")
    include_recipe = bool(payload.get("includeRecipe"))
    before = normalize_state(payload.get("action"), payload.get("before"), include_recipe=include_recipe)
    after = normalize_state(payload.get("action"), payload.get("after"), include_recipe=include_recipe)
    if state_hash(before) != payload.get("beforeHash") or state_hash(after) != payload.get("afterHash"):
        raise ValueError("progression receipt state hashes do not match")
    if receipt_hash(payload) != payload.get("receiptSha256"):
        raise ValueError("progression receipt digest does not match")
    return payload


def preview_rollback(connect, root, receipt_id, database):
    receipt = load_receipt(root, receipt_id)
    if receipt.get("database") != str(database):
        raise PermissionError("progression receipt database does not match the active admin database")
    pawn_id = int((receipt.get("player") or {}).get("player_pawn_id") or 0)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(PLAYER_SQL, (pawn_id,))
            row = _row(cursor)
            if row is None:
                raise ValueError("progression receipt player pawn was not found")
            current = capture_state(receipt["action"], row.get("properties"), include_recipe=bool(receipt.get("includeRecipe")))
    current_hash = state_hash(current)
    return {
        "ok": True, "dryRun": True, "receiptId": receipt_id,
        "player": {key: row.get(key) for key in ("account_id", "character_name", "online_status", "player_pawn_id")},
        "action": receipt["action"], "target": receipt.get("target"),
        "currentHash": current_hash, "expectedHash": receipt["afterHash"],
        "eligible": str(row.get("online_status") or "").lower() == "offline" and current_hash == receipt["afterHash"],
        "changed": receipt.get("changed"),
    }


def rollback(connect, root, receipt_id, database):
    receipt = load_receipt(root, receipt_id)
    if receipt.get("database") != str(database):
        raise PermissionError("progression receipt database does not match the active admin database")
    pawn_id = int((receipt.get("player") or {}).get("player_pawn_id") or 0)
    result = apply(
        connect, pawn_id, receipt["action"], receipt["after"], receipt["before"],
        include_recipe=bool(receipt.get("includeRecipe")),
    )
    result.update({"receiptId": receipt_id, "target": receipt.get("target"), "rollbackOf": receipt_id})
    return result


def list_receipts(root, limit=100):
    limit = max(1, min(int(limit), 500))
    directory = receipt_root(root)
    if not directory.is_dir():
        return []
    rows = []
    for path in sorted(directory.glob("*.json"), reverse=True)[:limit]:
        try:
            payload = load_receipt(root, path.stem)
            rows.append({
                "id": payload["receiptId"], "createdAt": payload["createdAt"],
                "action": payload["action"], "target": payload.get("target"),
                "player": payload.get("player"), "changed": payload.get("changed"),
                "afterHash": payload.get("afterHash"), "rollbackOf": payload.get("rollbackOf"),
            })
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return rows
