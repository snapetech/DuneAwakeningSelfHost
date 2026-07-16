"""Guarded Solido blueprint import/export support for DASH Admin.

The schema mapping and archive format are adapted from RedBlink's MIT-licensed
dune-awakening-selfhost-docker blueprint implementation, pinned in
docs/red-blink-feature-parity-audit.md. DASH adds dry-run planning, offline
execution, pre-write backup requirements at the route layer, strict bounds,
and post-write verification.
"""

import json
import math
import re

import psycopg2.extras


BLUEPRINT_TABLES = (
    "building_blueprints",
    "building_blueprint_instances",
    "building_blueprint_placeables",
    "building_blueprint_pentashields",
    "items",
    "inventories",
    "player_state",
)
MAX_BLUEPRINT_ROWS = 10000
MAX_BLUEPRINT_NAME = 120

STRUCTURAL_BUILDING_TYPES = {
    "Atreides_Outpost_Column", "Atreides_Outpost_Column_Corner",
    "Atreides_Outpost_Foundation", "Atreides_Outpost_Foundation_Round_Corner",
    "Atreides_Outpost_Foundation_Wedge", "Atreides_Outpost_Pillar_Bottom",
    "Atreides_Outpost_Pillar_Middle", "Atreides_Outpost_Pillar_Top",
    "Choam_Level2_Column", "Choam_Level2_Foundation", "Choam_Level2_Pillar_Bottom",
    "Choam_Shelter_Column_Corner_New", "Choam_Shelter_Column_New",
    "Harkonnen_Outpost_Column", "Harkonnen_Outpost_Foundation",
    "MTX_Neut_DesertMechanic_Center_Column", "MTX_Neut_DesertMechanic_Corner_Column",
    "MTX_Neut_DesertMechanic_Foundation", "MTX_Neut_DesertMechanic_Foundation_Wedge",
    "MTX_Neut_Gunner_Foundation", "MTX_Smug_Foundation", "MTX_Smug_Foundation_Full",
    "MTX_Smug_Foundation_Half", "MTX_Smug_Foundation_Quarter",
    "MTX_Smug_Foundation_Round_Corner", "MTX_Smug_Foundation_Wedge",
    "MTX_Smug_Pillar_Bottom", "MTX_Smug_Pillar_Middle", "MTX_Smug_Pillar_Top",
    "MTX_Smug_Column", "MTX_Smug_Corner_Column", "Watershippers_Foundation",
    "Watershippers_Foundation_Round_Corner", "Watershippers_Pillar_Bottom",
    "Watershippers_Pillar_Middle", "Watershippers_Pillar_Top",
    "Atre_Foundation_Full", "Hark_Foundation_Full", "Choam_Foundation_Full",
}


def _positive_int(value, label):
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _finite_number(value, label, default=0.0):
    if value in (None, ""):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or abs(result) > 100_000_000:
        raise ValueError(f"{label} is outside the supported coordinate range")
    return result


def _building_type(value):
    value = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_./:-]{1,256}", value):
        raise ValueError("building_type is missing or invalid")
    return value


def _name(value, fallback="Imported Blueprint"):
    value = re.sub(r"[_\\.]", " ", str(value or fallback))
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*\(\d+\)\s*$", "", value).strip() or fallback
    return value[:MAX_BLUEPRINT_NAME]


def _rows(value, label):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    if len(value) > MAX_BLUEPRINT_ROWS:
        raise ValueError(f"{label} exceeds the {MAX_BLUEPRINT_ROWS} row limit")
    if any(not isinstance(row, dict) for row in value):
        raise ValueError(f"every {label} row must be an object")
    return value


def _resolve_ids(rows, key, label):
    source_ids = []
    for row in rows:
        raw = row.get(key)
        if raw in (None, ""):
            source_ids.append(None)
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} id must be a non-negative integer") from exc
        if value < 0:
            raise ValueError(f"{label} id must be a non-negative integer")
        source_ids.append(value)
    offset = 1 if 0 in source_ids else 0
    reserved = set()
    mapping = {}
    for source_id in source_ids:
        if source_id is None:
            continue
        resolved = source_id + offset
        if resolved in reserved:
            raise ValueError(f"blueprint contains duplicate {label} id {source_id}")
        reserved.add(resolved)
        mapping[source_id] = resolved
    next_id = 1
    ids = []
    for source_id in source_ids:
        if source_id is not None:
            ids.append(source_id + offset)
            continue
        while next_id in reserved:
            next_id += 1
        ids.append(next_id)
        reserved.add(next_id)
        next_id += 1
    return ids, mapping


def validate_archive(payload, fallback_name=""):
    if not isinstance(payload, dict):
        raise ValueError("blueprint must be a JSON object")
    instances = _rows(payload.get("instances"), "instances")
    placeables = _rows(payload.get("placeables"), "placeables")
    pentashields = _rows(payload.get("pentashields"), "pentashields")
    if not instances and not placeables and not pentashields:
        raise ValueError("blueprint has no instances, placeables, or pentashields")
    if len(instances) + len(placeables) + len(pentashields) > MAX_BLUEPRINT_ROWS:
        raise ValueError(f"blueprint exceeds the {MAX_BLUEPRINT_ROWS} total row limit")

    instance_ids, _ = _resolve_ids(instances, "instance_id", "instance")
    placeable_ids, placeable_map = _resolve_ids(placeables, "placeable_id", "placeable")
    normalized_instances = []
    for index, row in enumerate(instances):
        building_type = _building_type(row.get("building_type"))
        normalized_instances.append({
            "instance_id": instance_ids[index],
            "building_type": building_type,
            "transform": [
                _finite_number(row.get("x"), "instance x"),
                _finite_number(row.get("y"), "instance y"),
                _finite_number(row.get("z"), "instance z"),
                _finite_number(row.get("rotation"), "instance rotation"),
            ],
            "provides_stability": bool(row.get("provides_stability", building_type in STRUCTURAL_BUILDING_TYPES)),
        })
    normalized_placeables = []
    for index, row in enumerate(placeables):
        normalized_placeables.append({
            "placeable_id": placeable_ids[index],
            "building_type": _building_type(row.get("building_type")),
            "transform": [
                _finite_number(row.get("x"), "placeable x"),
                _finite_number(row.get("y"), "placeable y"),
                _finite_number(row.get("z"), "placeable z"),
                _finite_number(row.get("rx"), "placeable rx"),
                _finite_number(row.get("ry"), "placeable ry"),
                _finite_number(row.get("rz"), "placeable rz"),
            ],
        })
    normalized_pentashields = []
    for row in pentashields:
        scale = row.get("scale")
        if not isinstance(scale, list) or len(scale) < 3:
            raise ValueError("pentashield scale must contain three integers")
        values = []
        for raw in scale[:3]:
            try:
                value = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("pentashield scale must contain three integers") from exc
            if value < -32768 or value > 32767:
                raise ValueError("pentashield scale values must fit smallint")
            values.append(value)
        try:
            source_id = int(row.get("placeable_id", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("pentashield placeable_id must be an integer") from exc
        normalized_pentashields.append({
            "placeable_id": placeable_map.get(source_id, source_id + (1 if 0 in placeable_map else 0)),
            "scale": values,
        })
    raw_name = payload.get("name") or payload.get("Name") or payload.get("blueprint_name") or fallback_name
    if not raw_name and normalized_instances:
        raw_name = normalized_instances[0]["building_type"]
    return {
        "schemaVersion": 1,
        "name": _name(raw_name),
        "instances": normalized_instances,
        "placeables": normalized_placeables,
        "pentashields": normalized_pentashields,
    }


def capabilities(query_fn):
    rows = query_fn("select name, to_regclass('dune.' || name) is not null as present from unnest(%s::text[]) name order by name", (list(BLUEPRINT_TABLES),))
    by_name = {str(row.get("name")): bool(row.get("present")) for row in rows}
    return {"supported": all(by_name.get(name, False) for name in BLUEPRINT_TABLES), "tables": by_name}


def list_blueprints(query_fn):
    return query_fn("""
        select bb.id, coalesce(bb.player_id::text, '') as owner_id,
               coalesce(ps.character_name, '') as owner_name,
               coalesce(bb.item_id, 0) as item_id,
               coalesce(inst.cnt, 0)::int as pieces,
               coalesce(plac.cnt, 0)::int as placeables,
               coalesce(shield.cnt, 0)::int as pentashields,
               coalesce(i.stats->'FBuildingBlueprintItemStats'->1->>'BuildingBlueprintName', '') as name
        from dune.building_blueprints bb
        left join dune.items i on i.id=bb.item_id
        left join lateral (select count(*) cnt from dune.building_blueprint_instances where building_blueprint_id=bb.id) inst on true
        left join lateral (select count(*) cnt from dune.building_blueprint_placeables where building_blueprint_id=bb.id) plac on true
        left join lateral (select count(*) cnt from dune.building_blueprint_pentashields where building_blueprint_id=bb.id) shield on true
        left join dune.player_state ps on ps.player_pawn_id=bb.player_id
        order by bb.id desc limit 2000
    """)


def export_blueprint(query_fn, blueprint_id):
    blueprint_id = _positive_int(blueprint_id, "blueprint_id")
    meta = query_fn("""
        select bb.id, bb.player_id, bb.item_id,
               coalesce(i.stats->'FBuildingBlueprintItemStats'->1->>'BuildingBlueprintName', '') as name
        from dune.building_blueprints bb join dune.items i on i.id=bb.item_id where bb.id=%s
    """, (blueprint_id,))
    if not meta:
        raise ValueError("blueprint not found")
    instances = query_fn("select instance_id,building_type,transform,provides_stability from dune.building_blueprint_instances where building_blueprint_id=%s order by instance_id", (blueprint_id,))
    placeables = query_fn("select placeable_id,building_type,transform from dune.building_blueprint_placeables where building_blueprint_id=%s order by placeable_id", (blueprint_id,))
    pentashields = query_fn("select placeable_id,scale from dune.building_blueprint_pentashields where building_blueprint_id=%s order by placeable_id", (blueprint_id,))
    def value(values, index):
        return (values or [])[index] if len(values or []) > index else 0
    return {
        "schemaVersion": 1,
        "name": meta[0].get("name") or f"Blueprint {blueprint_id}",
        "source": {"blueprintId": blueprint_id, "playerId": meta[0].get("player_id"), "itemId": meta[0].get("item_id")},
        "instances": [{"instance_id": row.get("instance_id"), "building_type": row.get("building_type"), "x": value(row.get("transform"), 0), "y": value(row.get("transform"), 1), "z": value(row.get("transform"), 2), "rotation": value(row.get("transform"), 3), "provides_stability": row.get("provides_stability")} for row in instances],
        "placeables": [{"placeable_id": row.get("placeable_id"), "building_type": row.get("building_type"), "x": value(row.get("transform"), 0), "y": value(row.get("transform"), 1), "z": value(row.get("transform"), 2), "rx": value(row.get("transform"), 3), "ry": value(row.get("transform"), 4), "rz": value(row.get("transform"), 5)} for row in placeables],
        "pentashields": [{"placeable_id": row.get("placeable_id"), "scale": list(row.get("scale") or [])[:3]} for row in pentashields],
    }


def plan_import(query_fn, player_pawn_id, payload, fallback_name=""):
    player_pawn_id = _positive_int(player_pawn_id, "player_pawn_id")
    archive = validate_archive(payload, fallback_name)
    player = query_fn("select player_pawn_id,character_name,online_status::text from dune.player_state where player_pawn_id=%s limit 1", (player_pawn_id,))
    if not player:
        raise ValueError("player pawn not found")
    inventory = query_fn("""
        select inv.id, inv.max_item_count, count(i.id)::int as used_slots
        from dune.inventories inv left join dune.items i on i.inventory_id=inv.id
        where inv.actor_id=%s and inv.inventory_type=0
        group by inv.id,inv.max_item_count order by inv.id limit 1
    """, (player_pawn_id,))
    if not inventory:
        raise ValueError("player backpack inventory not found")
    max_slots = int(inventory[0].get("max_item_count") or 40)
    used_slots = int(inventory[0].get("used_slots") or 0)
    if used_slots >= max_slots:
        raise ValueError(f"inventory full ({used_slots}/{max_slots} slots)")
    return {
        "ok": True, "dryRun": True, "playerPawnId": player_pawn_id,
        "player": player[0], "inventory": dict(inventory[0], available_slots=max_slots-used_slots),
        "archive": archive,
        "counts": {"instances": len(archive["instances"]), "placeables": len(archive["placeables"]), "pentashields": len(archive["pentashields"])},
    }


def _item_stats(blueprint_id, name):
    return {
        "FCustomizationStats": [[], {}],
        "FBuildingBlueprintItemStats": [[], {"PlayerBlueprintId": f"!!bbp#{blueprint_id}", "BuildingBlueprintName": name, "PlayerBaseBackupId": {}}],
        "FItemStackAndDurabilityStats": [[], {"DecayedMaxDurability": 0.0}],
    }


def import_blueprint(connect_fn, player_pawn_id, payload, fallback_name=""):
    player_pawn_id = _positive_int(player_pawn_id, "player_pawn_id")
    archive = validate_archive(payload, fallback_name)
    with connect_fn() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("select pg_advisory_xact_lock(%s)", (player_pawn_id,))
                cursor.execute("select character_name,online_status::text from dune.player_state where player_pawn_id=%s for update", (player_pawn_id,))
                player = cursor.fetchone()
                if not player:
                    raise ValueError("player pawn not found")
                if str(player.get("online_status") or "").lower() == "online":
                    raise ValueError("blueprint import requires the target player to be offline")
                cursor.execute("select id,max_item_count from dune.inventories where actor_id=%s and inventory_type=0 order by id limit 1 for update", (player_pawn_id,))
                inventory = cursor.fetchone()
                if not inventory:
                    raise ValueError("player backpack inventory not found")
                cursor.execute("select count(*)::int count,coalesce(max(position_index),-1)+1 next_position from dune.items where inventory_id=%s", (inventory["id"],))
                usage = cursor.fetchone()
                max_slots = int(inventory.get("max_item_count") or 40)
                if int(usage.get("count") or 0) >= max_slots:
                    raise ValueError(f"inventory full ({usage.get('count')}/{max_slots} slots)")
                base_name = archive["name"]
                name = base_name
                suffix = 1
                while True:
                    cursor.execute("""
                        select 1 from dune.items i join dune.building_blueprints bb on bb.item_id=i.id
                        where bb.player_id=%s and i.stats->'FBuildingBlueprintItemStats'->1->>'BuildingBlueprintName'=%s limit 1
                    """, (player_pawn_id, name))
                    if not cursor.fetchone():
                        break
                    suffix += 1
                    name = f"{base_name} ({suffix})"
                cursor.execute("""
                    insert into dune.items(inventory_id,stack_size,position_index,template_id,quality_level,stats)
                    values(%s,1,%s,'BuildingBlueprint_CopyDevice',0,%s::jsonb) returning id
                """, (inventory["id"], usage.get("next_position") or 0, json.dumps(_item_stats(0, name))))
                item_id = cursor.fetchone()["id"]
                cursor.execute("insert into dune.building_blueprints(item_id,player_id,building_blueprint_map) values(%s,%s,'') returning id", (item_id, player_pawn_id))
                blueprint_id = cursor.fetchone()["id"]
                cursor.execute("update dune.items set stats=%s::jsonb where id=%s", (json.dumps(_item_stats(blueprint_id, name)), item_id))
                for row in archive["instances"]:
                    cursor.execute("""
                        insert into dune.building_blueprint_instances(building_blueprint_id,instance_id,building_type,transform,hologram,provides_stability,health)
                        values(%s,%s,%s,%s::real[],true,%s,0)
                    """, (blueprint_id, row["instance_id"], row["building_type"], row["transform"], row["provides_stability"]))
                for row in archive["placeables"]:
                    cursor.execute("""
                        insert into dune.building_blueprint_placeables(building_blueprint_id,placeable_id,building_type,transform,hologram)
                        values(%s,%s,%s,%s::real[],true)
                    """, (blueprint_id, row["placeable_id"], row["building_type"], row["transform"]))
                for row in archive["pentashields"]:
                    cursor.execute("insert into dune.building_blueprint_pentashields(building_blueprint_id,placeable_id,scale) values(%s,%s,%s::smallint[])", (blueprint_id, row["placeable_id"], row["scale"]))
                cursor.execute("""
                    select bb.id,bb.item_id,
                      (select count(*) from dune.building_blueprint_instances where building_blueprint_id=bb.id)::int instances,
                      (select count(*) from dune.building_blueprint_placeables where building_blueprint_id=bb.id)::int placeables,
                      (select count(*) from dune.building_blueprint_pentashields where building_blueprint_id=bb.id)::int pentashields
                    from dune.building_blueprints bb where bb.id=%s
                """, (blueprint_id,))
                verified = cursor.fetchone()
                expected = (len(archive["instances"]), len(archive["placeables"]), len(archive["pentashields"]))
                observed = (verified.get("instances"), verified.get("placeables"), verified.get("pentashields")) if verified else ()
                if observed != expected:
                    raise RuntimeError(f"blueprint post-write verification failed: expected {expected}, observed {observed}")
            conn.commit()
            return {"ok": True, "blueprintId": blueprint_id, "itemId": item_id, "name": name, "playerPawnId": player_pawn_id, "counts": {"instances": expected[0], "placeables": expected[1], "pentashields": expected[2]}, "verified": True}
        except Exception:
            conn.rollback()
            raise


def delete_blueprint(connect_fn, blueprint_id):
    blueprint_id = _positive_int(blueprint_id, "blueprint_id")
    with connect_fn() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("select item_id,player_id from dune.building_blueprints where id=%s for update", (blueprint_id,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError("blueprint not found")
                cursor.execute("select online_status::text from dune.player_state where player_pawn_id=%s", (row.get("player_id"),))
                player = cursor.fetchone() or {}
                if str(player.get("online_status") or "").lower() == "online":
                    raise ValueError("blueprint deletion requires the owner to be offline")
                cursor.execute("delete from dune.building_blueprint_pentashields where building_blueprint_id=%s", (blueprint_id,))
                cursor.execute("delete from dune.building_blueprint_placeables where building_blueprint_id=%s", (blueprint_id,))
                cursor.execute("delete from dune.building_blueprint_instances where building_blueprint_id=%s", (blueprint_id,))
                cursor.execute("delete from dune.building_blueprints where id=%s", (blueprint_id,))
                if row.get("item_id"):
                    cursor.execute("delete from dune.items where id=%s", (row["item_id"],))
                cursor.execute("select 1 from dune.building_blueprints where id=%s", (blueprint_id,))
                if cursor.fetchone():
                    raise RuntimeError("blueprint deletion post-write verification failed")
            conn.commit()
            return {"ok": True, "blueprintId": blueprint_id, "itemId": row.get("item_id"), "verified": True}
        except Exception:
            conn.rollback()
            raise
