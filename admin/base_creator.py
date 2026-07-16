#!/usr/bin/env python3
"""Portable live-base exports plus an isolated community design gallery."""

import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import uuid


FORMAT = "dash-base/1"


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _id(value, label="id"):
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def list_live_bases(query, limit=500):
    limit = max(1, min(int(limit), 2000))
    return query("""
        select bi.building_id,bi.owner_entity_id,count(*)::int as piece_count,
               (select count(*)::int from dune.placeables p where p.owner_entity_id=bi.owner_entity_id) as placeable_count,
               min(bi.building_type) as sample_type,min(bi.health)::float8 as minimum_health
        from dune.building_instances bi
        group by bi.building_id,bi.owner_entity_id
        order by count(*) desc,bi.building_id limit %s
    """, (limit,))


def export_live_base(query, building_id):
    building_id = _id(building_id, "building id")
    pieces = query("""
        select instance_id,building_type,transform,building_flags,health::float8,owner_entity_id
        from dune.building_instances where building_id=%s order by instance_id
    """, (building_id,))
    if not pieces:
        raise ValueError("base building id was not found")
    owner_raw = pieces[0].get("owner_entity_id")
    owner = int(owner_raw) if owner_raw is not None else None
    placeables = [] if owner is None else query("""
        select p.id,p.building_type,coalesce(p.is_hologram,false) as is_hologram,
               to_jsonb(a.transform) as transform,a.map,a.partition_id,a.dimension_index
        from dune.placeables p join dune.actors a on a.id=p.id
        where p.owner_entity_id=%s order by p.id
    """, (owner,))
    locations = []
    normalized_pieces = []
    for row in pieces:
        transform = [float(value) for value in (row.get("transform") or [])]
        if len(transform) != 7:
            raise ValueError(f"building instance {row['instance_id']} has an unsupported transform")
        locations.append(transform[:3])
        normalized_pieces.append({"instanceId": int(row["instance_id"]), "buildingType": str(row["building_type"]), "transform": transform, "flags": int(row.get("building_flags") or 0), "health": float(row.get("health") or 0)})
    for row in placeables:
        location = ((row.get("transform") or {}).get("location") or {})
        if all(location.get(axis) is not None for axis in ("x", "y", "z")):
            locations.append([float(location["x"]), float(location["y"]), float(location["z"])])
    anchor = {axis: sum(point[index] for point in locations) / len(locations) for index, axis in enumerate(("x", "y", "z"))}
    for row in normalized_pieces:
        row["relative"] = [row["transform"][0] - anchor["x"], row["transform"][1] - anchor["y"], row["transform"][2] - anchor["z"], *row["transform"][3:]]
    normalized_placeables = []
    for row in placeables:
        transform = row.get("transform") or {}
        location, rotation = transform.get("location") or {}, transform.get("rotation") or {}
        relative = None
        if all(location.get(axis) is not None for axis in ("x", "y", "z")):
            relative = {"x": float(location["x"]) - anchor["x"], "y": float(location["y"]) - anchor["y"], "z": float(location["z"]) - anchor["z"], "qx": float(rotation.get("x") or 0), "qy": float(rotation.get("y") or 0), "qz": float(rotation.get("z") or 0), "qw": float(rotation.get("w") or 1)}
        normalized_placeables.append({"id": int(row["id"]), "buildingType": str(row["building_type"]), "hologram": bool(row.get("is_hologram")), "transform": transform, "relative": relative, "map": row.get("map"), "partitionId": row.get("partition_id"), "dimensionIndex": row.get("dimension_index")})
    archive = {"format": FORMAT, "source": {"kind": "live-base", "buildingId": building_id, "ownerEntityId": owner}, "exportedAt": utcnow(), "anchor": anchor, "pieceCount": len(normalized_pieces), "placeableCount": len(normalized_placeables), "pieces": normalized_pieces, "placeables": normalized_placeables, "gameRestoreSupported": False, "restoreNote": "Portable reconstruction data only; no proven server-side placement transaction exists."}
    archive["sha256"] = hashlib.sha256(_canonical(archive).encode()).hexdigest()
    return archive


def validate_design(value, *, max_components=10000):
    if not isinstance(value, dict) or value.get("format") != FORMAT:
        raise ValueError(f"design format must be {FORMAT}")
    pieces, placeables = value.get("pieces") or [], value.get("placeables") or []
    if not isinstance(pieces, list) or not isinstance(placeables, list) or len(pieces) + len(placeables) > max_components:
        raise ValueError("design components must be bounded arrays")
    for row in pieces:
        if not isinstance(row, dict) or not str(row.get("buildingType") or "").strip() or len(row.get("relative") or []) != 7:
            raise ValueError("every building piece requires a type and seven-value relative transform")
    return value


class Gallery:
    def __init__(self, path, owner_uid=None, owner_gid=None):
        self.path = pathlib.Path(path)
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("pragma journal_mode=wal"); db.execute("pragma synchronous=full"); db.execute("pragma foreign_keys=on")
        return db

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.closing(self.connect()) as db:
            db.executescript("""
              create table if not exists designs(id text primary key,name text not null,description text not null,author text not null,visibility text not null,archive text not null,sha256 text not null,created_at text not null,updated_at text not null);
              create table if not exists ratings(design_id text not null references designs(id) on delete cascade,rater text not null,rating integer not null check(rating between 1 and 5),created_at text not null,updated_at text not null,primary key(design_id,rater));
            """)
        self.fix_permissions(); return self

    def fix_permissions(self):
        for path, mode in ((self.path.parent, 0o700),(self.path,0o600),(pathlib.Path(str(self.path)+"-wal"),0o600),(pathlib.Path(str(self.path)+"-shm"),0o600)):
            try:
                os.chmod(path,mode)
                if self.owner_uid is not None or self.owner_gid is not None: os.chown(path,-1 if self.owner_uid is None else self.owner_uid,-1 if self.owner_gid is None else self.owner_gid)
            except FileNotFoundError: pass

    def publish(self, name, description, author, archive, visibility="private", design_id=None):
        archive = validate_design(archive)
        name = str(name or "").strip()[:160]
        if not name: raise ValueError("design name is required")
        visibility = str(visibility or "private").lower()
        if visibility not in ("private","unlisted","public"): raise ValueError("invalid visibility")
        design_id = str(design_id or uuid.uuid4())
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", design_id): raise ValueError("invalid design id")
        encoded, digest, now = _canonical(archive), hashlib.sha256(_canonical(archive).encode()).hexdigest(), utcnow()
        with contextlib.closing(self.connect()) as db:
            db.execute("begin immediate")
            db.execute("insert into designs(id,name,description,author,visibility,archive,sha256,created_at,updated_at) values(?,?,?,?,?,?,?,?,?) on conflict(id) do update set name=excluded.name,description=excluded.description,visibility=excluded.visibility,archive=excluded.archive,sha256=excluded.sha256,updated_at=excluded.updated_at",(design_id,name,str(description or "")[:2000],str(author or "operator")[:128],visibility,encoded,digest,now,now)); db.execute("commit")
        self.fix_permissions(); return self.get(design_id)

    def rate(self, design_id, rater, rating):
        rating=int(rating)
        if rating<1 or rating>5: raise ValueError("rating must be 1 through 5")
        now=utcnow()
        with contextlib.closing(self.connect()) as db:
            db.execute("insert into ratings(design_id,rater,rating,created_at,updated_at) values(?,?,?,?,?) on conflict(design_id,rater) do update set rating=excluded.rating,updated_at=excluded.updated_at",(design_id,str(rater)[:128],rating,now,now))
        return self.get(design_id)

    def get(self, design_id):
        with contextlib.closing(self.connect()) as db:
            row=db.execute("select d.*,count(r.rating) rating_count,coalesce(avg(r.rating),0) rating_average from designs d left join ratings r on r.design_id=d.id where d.id=? group by d.id",(design_id,)).fetchone()
        if not row: raise ValueError("design not found")
        result=dict(row); result["archive"]=json.loads(result["archive"]); return result

    def list(self, include_private=True, limit=200):
        with contextlib.closing(self.connect()) as db:
            rows=db.execute("select d.id,d.name,d.description,d.author,d.visibility,d.sha256,d.created_at,d.updated_at,count(r.rating) rating_count,coalesce(avg(r.rating),0) rating_average from designs d left join ratings r on r.design_id=d.id where (? or d.visibility<>'private') group by d.id order by d.updated_at desc limit ?",(1 if include_private else 0,max(1,min(int(limit),1000)))).fetchall()
        return [dict(row) for row in rows]
