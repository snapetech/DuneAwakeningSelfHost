"""Structured Dune item augment validation and stat construction.

Compatibility metadata and stat-shape behavior are adapted from RedBlink's
MIT-licensed implementation pinned in docs/red-blink-feature-parity-audit.md.
"""

import copy
import json
import pathlib
import re
import time

import psycopg2.extras


CATALOG_PATH = pathlib.Path(__file__).resolve().parents[1] / "config" / "augment-compatibility.json"
TEMPLATE_RE = re.compile(r"^[A-Za-z0-9_./:-]{1,256}$")


def load_catalog():
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("augments"), dict):
        raise ValueError("augment compatibility catalog is invalid")
    return data


def _normalize(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def item_kind(item):
    text = " ".join(str(item.get(key) or "") for key in ("templateId", "template_id", "name", "category", "source")).lower()
    category = str(item.get("category") or "").lower()
    if category == "schematics" or re.search(r"_schematic$|schematic", text):
        return "schematic"
    if category in ("armor", "clothing", "armor/combat") or re.search(r"social|garment|helmet|boots|gloves|stillsuit|still_suit|suit|top|bottom|shirt|pants|robe|cloak|hood|wearable|clothing|armor|chest|guard", text):
        return "clothing"
    if category in ("weapons", "weapon") or re.search(r"weapon|lasgun|spitdart|jabal|dmr|rifle|karpov|disruptor|smg|lmg|vulcan|drillshot|shotgun|scattergun|grda|rocket|missile|pistol|snubnose|rafiq|maula|melee|sword|blade|knife|dirk|rapier|kindjal|minotaur|dualblades|crysknife|dewreaper|ghola|hook", text):
        return "weapon"
    return "other"


def _item_tags(item, catalog):
    method = {_normalize(name): tags for name, tags in (catalog.get("methodItems") or {}).items()}
    aliases = {_normalize(name): tags for name, tags in (catalog.get("itemAliases") or {}).items()}
    name_tags = method.get(_normalize(item.get("name")))
    if name_tags:
        return [str(tag) for tag in name_tags]
    for key in ("templateId", "template_id", "itemId", "id"):
        tags = aliases.get(_normalize(item.get(key)))
        if tags:
            return [str(tag) for tag in tags]
    return []


def _tags_match(item_tags, augment_tags):
    return any(augment_tag == item_tag or item_tag.startswith(augment_tag + ".") for augment_tag in augment_tags for item_tag in item_tags)


def compatible_augments(item):
    catalog = load_catalog()
    kind = item_kind(item)
    tags = _item_tags(item, catalog)
    limit = 2 if kind == "clothing" else 3 if kind == "weapon" else 0
    rows = []
    if limit and tags:
        for template_id, entry in catalog["augments"].items():
            augment_tags = [str(tag) for tag in entry.get("tags") or []]
            if augment_tags and _tags_match(tags, augment_tags):
                rows.append({
                    "templateId": template_id,
                    "name": entry.get("name") or template_id,
                    "tags": augment_tags,
                    "gradeEffects": entry.get("gradeEffects") or {},
                    "effectSummary": entry.get("effectSummary") or "",
                })
    rows.sort(key=lambda row: (str(row["name"]).lower(), row["templateId"]))
    return {"kind": kind, "limit": limit, "itemTags": tags, "augments": rows, "supported": bool(limit and tags)}


def validate_selection(item, augment_ids, grade=1):
    if not isinstance(augment_ids, list):
        raise ValueError("augments must be an array")
    ids = []
    for raw in augment_ids:
        value = str(raw or "").strip()
        if not TEMPLATE_RE.fullmatch(value):
            raise ValueError("augment template ID is invalid")
        if value not in ids:
            ids.append(value)
    try:
        grade = int(grade)
    except (TypeError, ValueError) as exc:
        raise ValueError("augment grade must be an integer from 1 to 5") from exc
    if grade < 1 or grade > 5:
        raise ValueError("augment grade must be an integer from 1 to 5")
    compatibility = compatible_augments(item)
    if not compatibility["supported"]:
        raise ValueError("target item does not have a proven augment compatibility mapping")
    if not ids:
        raise ValueError("select at least one augment")
    if len(ids) > compatibility["limit"]:
        raise ValueError(f"target supports at most {compatibility['limit']} augments")
    allowed = {row["templateId"] for row in compatibility["augments"]}
    invalid = [value for value in ids if value not in allowed]
    if invalid:
        raise ValueError(f"incompatible augments: {', '.join(invalid)}")
    return ids, grade, compatibility


def _perfect_roll(payload, roll_count):
    payload = payload if isinstance(payload, dict) else {}
    current = payload.get("StatRolls")
    count = len(current) if isinstance(current, list) and current else max(1, roll_count)
    return {"StatRolls": [1] * count, "AppliedEffectIndices": payload.get("AppliedEffectIndices") if isinstance(payload.get("AppliedEffectIndices"), list) else []}


def _roll_count(entry):
    explicit = entry.get("rollCount", entry.get("statRollCount"))
    try:
        if int(explicit) > 0:
            return int(explicit)
    except (TypeError, ValueError):
        pass
    effects = [len(value) for value in (entry.get("gradeEffects") or {}).values() if isinstance(value, list) and value]
    if effects:
        return max(effects)
    return max(1, len(str(entry.get("effectSummary") or "").split(";")))


def slot_keystone_ids(compatibility):
    kind = compatibility.get("kind")
    if kind == "clothing":
        return [42, 43]
    if kind != "weapon":
        return []
    tags = [str(value) for value in compatibility.get("itemTags") or []]
    melee = any("meleeweapons" in value.lower() for value in tags)
    ranged = any("rangedweapons" in value.lower() for value in tags)
    if melee and not ranged:
        return [44, 45, 46]
    if ranged and not melee:
        return [47, 48, 49]
    return [44, 45, 46, 47, 48, 49]


def ensure_slot_keystones(cursor, player_controller_id, compatibility):
    ids = slot_keystone_ids(compatibility)
    if not ids:
        return {"supported": True, "insertedRows": 0, "keystoneIds": []}
    cursor.execute("""
        select to_regclass('dune.purchased_specialization_keystones') as purchased,
               to_regclass('dune.specialization_keystones_map') as mapping,
               to_regclass('dune.specialization_tracks') as tracks
    """)
    tables = cursor.fetchone() or {}
    if not tables.get("purchased") or not tables.get("mapping"):
        return {"supported": False, "insertedRows": 0, "keystoneIds": []}
    if tables.get("tracks"):
        cursor.execute("""
            insert into dune.specialization_tracks (player_id,track_type,xp_amount,level)
            values (%s,'Crafting'::dune.specializationtracktype,3100,19.338913)
            on conflict (player_id,track_type) do update
            set xp_amount=greatest(dune.specialization_tracks.xp_amount,excluded.xp_amount),
                level=greatest(dune.specialization_tracks.level,excluded.level)
        """, (player_controller_id,))
    cursor.execute("""
        insert into dune.purchased_specialization_keystones (player_id,keystone_id)
        select %s,id from dune.specialization_keystones_map where id=any(%s)
        on conflict do nothing
    """, (player_controller_id, ids))
    inserted = max(0, cursor.rowcount)
    cursor.execute("""
        select count(*)::int as count from dune.purchased_specialization_keystones
        where player_id=%s and keystone_id=any(%s)
    """, (player_controller_id, ids))
    verified = int((cursor.fetchone() or {}).get("count") or 0)
    if verified != len(ids):
        raise RuntimeError("augment slot keystone verification failed")
    return {"supported": True, "insertedRows": inserted, "keystoneIds": ids, "verified": True}


def build_stats(query_fn, item, augment_ids, grade=1, base_stats=None):
    ids, grade, compatibility = validate_selection(item, augment_ids, grade)
    catalog = load_catalog()
    rows = query_fn("""
        select distinct on (template_id) template_id,quality_level,stats
        from dune.items where template_id=any(%s) and stats ? 'FAugmentItemStats'
        order by template_id,id desc
    """, (ids,))
    observed = {str(row.get("template_id")): row for row in rows}
    patterns = [f"%{value}%" for value in ids]
    augmented_rows = query_fn("""
        select id,template_id,stats from dune.items
        where stats ? 'FAugmentedItemStats' and stats::text like any(%s)
        order by case when template_id=%s then 0 else 1 end,id desc limit 200
    """, (patterns, item.get("templateId") or item.get("template_id") or ""))
    inherited = {}
    for row in augmented_rows:
        payload = (row.get("stats") or {}).get("FAugmentedItemStats")
        payload = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], dict) else {}
        applied = payload.get("AppliedAugments") if isinstance(payload.get("AppliedAugments"), list) else []
        roll_data = payload.get("AppliedAugmentRollData") if isinstance(payload.get("AppliedAugmentRollData"), list) else []
        for index, applied_entry in enumerate(applied):
            applied_id = applied_entry if isinstance(applied_entry, str) else applied_entry.get("Name") if isinstance(applied_entry, dict) else None
            if applied_id in ids and applied_id not in inherited and index < len(roll_data):
                inherited[applied_id] = roll_data[index]
    payloads = []
    for template_id in ids:
        entry = catalog["augments"][template_id]
        source = observed.get(template_id, {})
        source_stats = source.get("stats") if isinstance(source.get("stats"), dict) else {}
        augment_stats = source_stats.get("FAugmentItemStats")
        payload = augment_stats[1] if isinstance(augment_stats, list) and len(augment_stats) > 1 and isinstance(augment_stats[1], dict) else inherited.get(template_id, {})
        payloads.append(_perfect_roll(payload, _roll_count(entry)))
    stats = copy.deepcopy(base_stats) if isinstance(base_stats, dict) else {}
    customization = stats.get("FCustomizationStats")
    first = customization[0] if isinstance(customization, list) and customization and isinstance(customization[0], list) else []
    first = [value for value in first if not (isinstance(value, str) and re.match(r"^T\d+_Augment_", value, re.I))]
    second = customization[1] if isinstance(customization, list) and len(customization) > 1 and isinstance(customization[1], dict) else {}
    stats["FCustomizationStats"] = [first, second]
    durability = stats.get("FItemStackAndDurabilityStats")
    if not isinstance(durability, list) or len(durability) < 2 or not isinstance(durability[1], dict) or not durability[1]:
        stats["FItemStackAndDurabilityStats"] = [[], {"CurrentDurability": 100, "MaxDurability": 100, "DecayedMaxDurability": 100}]
    if compatibility["kind"] == "weapon" and not isinstance(stats.get("FWeaponItemStats"), list):
        stats["FWeaponItemStats"] = [[], {"CurrentAmmo": 0}]
    stats["FAugmentedItemStats"] = [[], {
        "AppliedAugments": [{"Name": value} for value in ids],
        "AppliedAugmentQualities": [grade] * len(ids),
        "AppliedAugmentRollData": payloads,
    }]
    return {"stats": stats, "augments": ids, "grade": grade, "compatibility": compatibility, "observedRollSources": sorted(set(observed) | set(inherited))}


def apply_to_item(connect_fn, item_id, augment_ids, grade, item_metadata):
    try:
        item_id = int(item_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("item_id must be a positive integer") from exc
    if item_id <= 0:
        raise ValueError("item_id must be a positive integer")
    with connect_fn() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    select i.id,i.template_id,i.stats,inv.actor_id,ps.account_id,ps.character_name,
                           ps.player_controller_id,ps.online_status::text
                    from dune.items i join dune.inventories inv on inv.id=i.inventory_id
                    left join dune.player_state ps on ps.player_pawn_id=inv.actor_id or ps.player_controller_id=inv.actor_id
                    where i.id=%s for update of i
                """, (item_id,))
                item = cursor.fetchone()
                if not item:
                    raise ValueError("item not found")
                if not item.get("account_id"):
                    raise ValueError("item is not in a directly owned player inventory")
                if str(item.get("online_status") or "").lower() == "online":
                    raise ValueError("augment application requires the owner to be offline")
                metadata = dict(item_metadata or {}, templateId=item["template_id"], template_id=item["template_id"])

                def cursor_query(sql, params=None):
                    cursor.execute(sql, params or ())
                    return list(cursor.fetchall()) if cursor.description else []

                built = build_stats(cursor_query, metadata, augment_ids, grade, item.get("stats"))
                before = item.get("stats") or {}
                slot_unlocks = ensure_slot_keystones(cursor, item.get("player_controller_id"), built["compatibility"])
                cursor.execute("update dune.items set stats=%s::jsonb where id=%s", (json.dumps(built["stats"]), item_id))
                cursor.execute("select stats from dune.items where id=%s", (item_id,))
                after = cursor.fetchone()
                if not after or after.get("stats") != built["stats"]:
                    raise RuntimeError("augment post-write verification failed")
            conn.commit()
            return {"ok": True, "itemId": item_id, "templateId": item["template_id"], "accountId": item.get("account_id"), "characterName": item.get("character_name"), "before": before, "after": built["stats"], "augments": built["augments"], "grade": built["grade"], "slotUnlocks": slot_unlocks, "verified": True}
        except Exception:
            conn.rollback()
            raise


def grant_augmented_item(connect_fn, inventory_id, template_id, stack_size, quality_level, position_index, augment_ids, grade, item_metadata):
    with connect_fn() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    select inv.id,inv.actor_id,inv.max_item_count,ps.account_id,ps.character_name,
                           ps.player_controller_id,ps.online_status::text
                    from dune.inventories inv
                    left join dune.player_state ps on ps.player_pawn_id=inv.actor_id or ps.player_controller_id=inv.actor_id
                    where inv.id=%s for update of inv
                """, (inventory_id,))
                inventory = cursor.fetchone()
                if not inventory:
                    raise ValueError("inventory_id does not exist")
                if not inventory.get("account_id"):
                    raise ValueError("pre-augmented grants require a directly owned player inventory")
                if str(inventory.get("online_status") or "").lower() == "online":
                    raise ValueError("pre-augmented item grants require the owner to be offline")
                cursor.execute("select count(*)::int as count from dune.items where inventory_id=%s", (inventory_id,))
                count = int((cursor.fetchone() or {}).get("count") or 0)
                max_count = inventory.get("max_item_count")
                if max_count is not None and int(max_count) > 0 and count >= int(max_count):
                    raise ValueError("player inventory is full by item slot count")
                cursor.execute("select 1 from dune.items where inventory_id=%s and position_index=%s", (inventory_id, position_index))
                if cursor.fetchone():
                    raise ValueError("target inventory position is already occupied")

                def cursor_query(sql, params=None):
                    cursor.execute(sql, params or ())
                    return list(cursor.fetchall()) if cursor.description else []

                metadata = dict(item_metadata or {}, templateId=template_id, template_id=template_id)
                built = build_stats(cursor_query, metadata, augment_ids, grade, {})
                slot_unlocks = ensure_slot_keystones(cursor, inventory.get("player_controller_id"), built["compatibility"])
                cursor.execute("select dune.advance_items_id_sequencer(1) as item_id")
                item_id = int(cursor.fetchone()["item_id"])
                cursor.execute("""
                    select dune.save_item((%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)::dune.inventoryitem)
                """, (
                    item_id, inventory_id, stack_size, position_index, template_id, True,
                    int(time.time() * 1000), json.dumps(built["stats"]), quality_level, None,
                ))
                cursor.execute("select id,inventory_id,template_id,stack_size,quality_level,position_index,stats from dune.items where id=%s", (item_id,))
                inserted = cursor.fetchone()
                if not inserted or inserted.get("stats") != built["stats"] or int(inserted.get("inventory_id")) != int(inventory_id):
                    raise RuntimeError("pre-augmented item post-write verification failed")
            conn.commit()
            return {
                "ok": True,
                "item_id": item_id,
                "inventory_id": inventory_id,
                "template_id": template_id,
                "stack_size": stack_size,
                "quality_level": quality_level,
                "position_index": position_index,
                "account_id": inventory.get("account_id"),
                "character_name": inventory.get("character_name"),
                "augments": built["augments"],
                "augment_grade": built["grade"],
                "slot_unlocks": slot_unlocks,
                "item": inserted,
                "verified": True,
            }
        except Exception:
            conn.rollback()
            raise
