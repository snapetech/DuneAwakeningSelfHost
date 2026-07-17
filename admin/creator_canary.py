#!/usr/bin/env python3
"""Signed disposable runtime proof for DASH creator and modding capabilities."""

import datetime
import hashlib
import hmac
import io
import json
import os
import pathlib
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile

import addon_admin
import base_creator
import base_retirement
import cosmetics_admin
import gameplay_presets


SCHEMA = "dune-creator-modding-canary/v1"
RECEIPT_SCHEMA = 1
ID_PATTERN = re.compile(r"^creator-canary-[0-9a-f]{32}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
INPUT_FILES = (
    "admin/addon_admin.py",
    "admin/base_creator.py",
    "admin/base_retirement.py",
    "admin/cosmetics_admin.py",
    "admin/creator_canary.py",
    "admin/gameplay_presets.py",
    "config/UserGame.ini",
    "config/UserGame.deep-desert-coriolis.ini",
    "config/UserGame.deep-desert-pvp.ini",
    "config/cosmetic-catalog.json",
    "config/gameplay-presets.json",
)
CHECK_NAMES = (
    "inputsBound", "sourceInputsUnchanged", "liveBaseExport", "galleryRoundTrip",
    "retirementGuards", "presetApplyRollback", "landsraadPreserved",
    "cosmeticsPlanning", "addonInstall", "addonPermission",
    "addonRecovery", "temporaryStateRemoved",
)
ISOLATION_KEYS = (
    "temporaryStateCreated", "temporaryStateRemoved", "liveGalleryOpened",
    "liveConfigWritten", "gameDatabaseOpened", "playerDataWritten",
    "gameMapLifecycleInvoked", "externalNetworkCalled",
)
LOCK = threading.RLock()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def iso(epoch=None):
    epoch = time.time() if epoch is None else float(epoch)
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value):
    text = str(value or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("creator canary timestamp lacks a timezone")
    return parsed.timestamp()


def _file_sha256(path):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= 50 * 1024 * 1024:
        raise ValueError(f"creator canary input is not a bounded regular file: {path.name}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_manifest(root):
    root = pathlib.Path(root).resolve(strict=True)
    rows = []
    for relative in INPUT_FILES:
        candidate = root / relative
        if candidate.is_symlink():
            raise ValueError(f"creator canary input cannot be a symlink: {relative}")
        path = candidate.resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("creator canary input escapes the workspace") from exc
        rows.append({"path": relative, "sha256": _file_sha256(path), "bytes": path.stat().st_size})
    return {"files": rows, "sha256": hashlib.sha256(canonical(rows).encode()).hexdigest()}


def receipt_hash(receipt):
    return hashlib.sha256(canonical({key: value for key, value in receipt.items() if key != "receiptSha256"}).encode()).hexdigest()


def signed_document(receipt, secret, generated_at=None):
    receipt = json.loads(canonical(receipt))
    receipt["receiptSha256"] = receipt_hash(receipt)
    payload = {
        "schemaVersion": SCHEMA,
        "generatedAt": iso(generated_at),
        "signingKeyFingerprint": hashlib.sha256(secret).hexdigest(),
        "receipt": receipt,
    }
    return {**payload, "signature": hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()}


RECEIPT_FIELDS = {
    "schemaVersion", "id", "principalId", "startedAt", "completedAt",
    "durationMs", "inputsSha256", "checks", "evidence", "isolation",
    "ready", "receiptSha256",
}
EVIDENCE_FIELDS = {
    "inputFiles", "galleryDesigns", "galleryRatings", "presetId",
    "presetTarget", "cosmeticCatalogItems", "addonPermissions",
    "retirementBlockedConditions",
}


def verify_signed_document(document, secret, *, current_inputs_sha256=None, max_age_seconds=None, now=None):
    try:
        if not isinstance(document, dict) or set(document) != {
            "schemaVersion", "generatedAt", "signingKeyFingerprint", "receipt", "signature",
        }:
            raise ValueError("creator canary signed document fields are invalid")
        if document.get("schemaVersion") != SCHEMA:
            raise ValueError("creator canary schema is invalid")
        payload = {key: value for key, value in document.items() if key != "signature"}
        expected = hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(document.get("signature") or ""), expected):
            raise ValueError("creator canary signature is invalid")
        if not hmac.compare_digest(str(document.get("signingKeyFingerprint") or ""), hashlib.sha256(secret).hexdigest()):
            raise ValueError("creator canary signing key fingerprint differs")
        generated = epoch(document.get("generatedAt"))
        receipt = document.get("receipt")
        if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS or receipt.get("schemaVersion") != RECEIPT_SCHEMA:
            raise ValueError("creator canary receipt fields are invalid")
        if not ID_PATTERN.fullmatch(str(receipt.get("id") or "")):
            raise ValueError("creator canary receipt id is invalid")
        principal = str(receipt.get("principalId") or "")
        if not 1 <= len(principal) <= 128 or any(ord(char) < 32 for char in principal):
            raise ValueError("creator canary principal is invalid")
        started, completed = epoch(receipt.get("startedAt")), epoch(receipt.get("completedAt"))
        if not 0 <= completed - started <= 300:
            raise ValueError("creator canary execution interval is invalid")
        duration = receipt.get("durationMs")
        if isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= 300_000:
            raise ValueError("creator canary duration evidence is invalid")
        if abs(duration - round((completed - started) * 1000)) > 2000:
            raise ValueError("creator canary duration does not match timestamps")
        if abs(generated - completed) > 2:
            raise ValueError("creator canary signed time does not match completion")
        inputs_sha = str(receipt.get("inputsSha256") or "")
        if not HASH_PATTERN.fullmatch(inputs_sha):
            raise ValueError("creator canary input digest is invalid")
        checks = receipt.get("checks")
        if not isinstance(checks, dict) or set(checks) != set(CHECK_NAMES) or any(type(value) is not bool for value in checks.values()):
            raise ValueError("creator canary checks are invalid")
        evidence = receipt.get("evidence")
        if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
            raise ValueError("creator canary evidence fields are invalid")
        for key in ("inputFiles", "galleryDesigns", "galleryRatings", "cosmeticCatalogItems", "addonPermissions", "retirementBlockedConditions"):
            if isinstance(evidence.get(key), bool) or not isinstance(evidence.get(key), int) or not 0 <= evidence[key] <= 1_000_000:
                raise ValueError("creator canary evidence count is invalid")
        for key in ("presetId", "presetTarget"):
            value = str(evidence.get(key) or "")
            if not 1 <= len(value) <= 128 or any(ord(char) < 32 for char in value):
                raise ValueError("creator canary preset evidence is invalid")
        isolation = receipt.get("isolation")
        if not isinstance(isolation, dict) or set(isolation) != set(ISOLATION_KEYS) or any(type(value) is not bool for value in isolation.values()):
            raise ValueError("creator canary isolation fields are invalid")
        unsafe = any(isolation[key] for key in (
            "liveGalleryOpened", "liveConfigWritten", "gameDatabaseOpened",
            "playerDataWritten", "gameMapLifecycleInvoked", "externalNetworkCalled",
        ))
        isolation_ready = bool(isolation["temporaryStateCreated"] and isolation["temporaryStateRemoved"] and not unsafe)
        expected_ready = all(checks.values()) and isolation_ready
        if type(receipt.get("ready")) is not bool or receipt["ready"] is not expected_ready:
            raise ValueError("creator canary verdict is inconsistent")
        expected_hash = receipt_hash(receipt)
        if not HASH_PATTERN.fullmatch(str(receipt.get("receiptSha256") or "")) or not hmac.compare_digest(receipt["receiptSha256"], expected_hash):
            raise ValueError("creator canary receipt digest is invalid")
        inputs_current = current_inputs_sha256 is None or hmac.compare_digest(inputs_sha, str(current_inputs_sha256))
        reference = float(time.time() if now is None else now)
        if completed > reference + 300:
            raise ValueError("creator canary completion is implausibly in the future")
        age_seconds = max(0.0, reference - completed)
        age_current = max_age_seconds is None or age_seconds <= float(max_age_seconds)
        return {
            "ok": True, "signatureValid": True, "receiptValid": True,
            "receiptId": receipt["id"], "receiptSha256": receipt["receiptSha256"],
            "ready": receipt["ready"], "inputsCurrent": inputs_current,
            "ageCurrent": age_current, "ageSeconds": round(age_seconds, 3),
            "currentReady": bool(receipt["ready"] and inputs_current and age_current),
        }
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"ok": False, "signatureValid": False, "receiptValid": False, "currentReady": False, "error": str(exc)}


class Store:
    def __init__(self, evidence_root, secret, *, retention=200, max_age_seconds=7 * 86400, owner_uid=None, owner_gid=None):
        self.evidence_root = pathlib.Path(evidence_root)
        self.secret = bytes(secret)
        self.retention = max(10, min(int(retention), 2000))
        self.max_age_seconds = max(300, min(int(max_age_seconds), 90 * 86400))
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None

    def _secure(self, path):
        path = pathlib.Path(path)
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
        if os.geteuid() == 0 and self.owner_uid is not None:
            os.chown(path, self.owner_uid, self.owner_gid if self.owner_gid is not None else -1)

    def initialize(self):
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self._secure(self.evidence_root)
        for path in self._paths(initializing=True):
            self._secure(path)

    def _paths(self, initializing=False):
        if not initializing:
            self.initialize()
        return sorted(
            (path for path in self.evidence_root.glob("creator-canary-*.signed.json") if path.is_file() and not path.is_symlink()),
            key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True,
        )

    def _write(self, path, document):
        temporary = path.with_suffix(path.suffix + ".tmp-" + secrets.token_hex(8))
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(document, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._secure(temporary)
            temporary.replace(path)
            self._secure(path)
        finally:
            temporary.unlink(missing_ok=True)

    def record(self, receipt, completed_epoch):
        document = signed_document(receipt, self.secret, generated_at=completed_epoch)
        path = self.evidence_root / f"{receipt['id']}.signed.json"
        with LOCK:
            self.initialize()
            self._write(path, document)
            for stale in self._paths()[self.retention:]:
                stale.unlink(missing_ok=True)
        return {"document": document, "evidencePath": str(path), "verification": verify_signed_document(document, self.secret)}

    def status(self, inputs_sha256, limit=20, now=None):
        all_rows = []
        for path in self._paths():
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                verification = verify_signed_document(
                    document, self.secret, current_inputs_sha256=inputs_sha256,
                    max_age_seconds=self.max_age_seconds, now=now,
                )
                receipt = document.get("receipt") or {}
                row = {
                    "id": receipt.get("id"), "completedAt": receipt.get("completedAt"),
                    "durationMs": receipt.get("durationMs"), "ready": bool(receipt.get("ready")),
                    "inputsSha256": receipt.get("inputsSha256"), "checks": receipt.get("checks"),
                    "evidence": receipt.get("evidence"), "isolation": receipt.get("isolation"),
                    "receiptSha256": receipt.get("receiptSha256"), "file": path.name,
                    "verification": verification,
                }
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                row = {"id": path.stem, "ready": False, "file": path.name, "verification": {"ok": False, "currentReady": False, "error": str(exc)}}
            all_rows.append(row)
        rows = all_rows[:max(1, min(int(limit), self.retention))]
        latest = all_rows[0] if all_rows else None
        return {
            "ok": all((row.get("verification") or {}).get("ok") for row in all_rows),
            "currentReady": bool(latest and (latest.get("verification") or {}).get("currentReady")),
            "latest": latest, "receipts": rows, "retention": self.retention,
            "maxAgeSeconds": self.max_age_seconds,
            "summary": {"retained": len(all_rows), "returned": len(rows)},
        }

    def prometheus(self, inputs_sha256, now=None):
        status = self.status(inputs_sha256, now=now)
        latest = status.get("latest") or {}
        verification = latest.get("verification") or {}
        completed = epoch(latest["completedAt"]) if latest.get("completedAt") and verification.get("ok") else "NaN"
        return "\n".join([
            f"dash_creator_canary_collector_up {1 if status.get('ok') else 0}",
            f"dash_creator_canary_current_ready {1 if status.get('currentReady') else 0}",
            f"dash_creator_canary_last_completion_timestamp_seconds {completed}",
            f"dash_creator_canary_age_seconds {float(verification.get('ageSeconds') or 0):.3f}",
            f"dash_creator_canary_retained_receipts {int((status.get('summary') or {}).get('retained') or 0)}",
        ]) + "\n"


def _design():
    return {
        "format": base_creator.FORMAT,
        "source": {"kind": "canary"},
        "exportedAt": "2026-01-01T00:00:00Z",
        "anchor": {"x": 0, "y": 0, "z": 0},
        "pieceCount": 1, "placeableCount": 0,
        "pieces": [{"instanceId": 1, "buildingType": "Foundation", "relative": [0, 0, 0, 0, 0, 0, 1], "flags": 1, "health": 100}],
        "placeables": [], "gameRestoreSupported": False,
        "restoreNote": "synthetic canary",
    }


def _base_export():
    def query(sql, params=()):
        if "from dune.building_instances where building_id" in sql:
            return [
                {"instance_id": 1, "building_type": "Foundation", "transform": [0, 0, 0, 0, 0, 0, 1], "building_flags": 1, "health": 100, "owner_entity_id": 99},
                {"instance_id": 2, "building_type": "Wall", "transform": [100, 0, 0, 0, 0, 0, 1], "building_flags": 1, "health": 90, "owner_entity_id": 99},
            ]
        if "from dune.placeables" in sql:
            return []
        raise AssertionError("unexpected base export query")
    return base_creator.export_live_base(query, 44)


def _retirement_plan(*, blocked=False):
    row = {
        "totem_id": 44, "owner_entity_id": 99, "fgl_entity_count": 2 if blocked else 1,
        "actor_name": "Canary Base", "map": "Canary", "partition_id": 1,
        "partition_server_id": "server" if blocked else "", "active_server_id": "server" if blocked else "",
        "building_count": 1, "piece_count": 2, "placeable_count": 1,
        "existing_backup_count": 1 if blocked else 0,
        "last_backup_timestamp": 0 if blocked else 123456,
        "native_function_available": not blocked,
        "piece_hash": "a" * 32, "placeable_hash": "b" * 32, "permission_hash": "c" * 32,
        "owners": [{"playerId": 46, "rank": 1, "accountId": 9, "characterName": "Canary", "onlineStatus": "Online" if blocked else "Offline"}],
    }
    def query(sql, params=()):
        if "with base as" in sql:
            return [row]
        if "from dune.player_state ps where ps.player_controller_id" in sql:
            return [{"player_controller_id": 46, "account_id": 9, "character_name": "Canary", "online_status": "Online" if blocked else "Offline"}]
        raise AssertionError("unexpected retirement query")
    return base_retirement.plan(query, 44, 46)


def _cooldown_plan(*, blocked=False):
    row = {
        "totem_id": 44, "owner_entity_id": 99, "fgl_entity_count": 1,
        "actor_name": "Canary Base", "map": "Canary", "partition_id": 1,
        "partition_server_id": "server" if blocked else "", "active_server_id": "server" if blocked else "",
        "building_count": 1, "piece_count": 2, "placeable_count": 1,
        "existing_backup_count": 0, "last_backup_timestamp": 0 if blocked else 123456,
        "native_function_available": True,
        "piece_hash": "a" * 32, "placeable_hash": "b" * 32, "permission_hash": "c" * 32,
        "owners": [{"playerId": 46, "rank": 1, "accountId": 9, "characterName": "Canary", "onlineStatus": "Online" if blocked else "Offline"}],
    }
    def query(sql, params=()):
        if "with base as" in sql:
            return [row]
        raise AssertionError("unexpected cooldown query")
    return base_retirement.cooldown_plan(query, 44)


def _addon_fixture():
    addon_id = "dash-canary-addon"
    manifest_url = "https://raw.githubusercontent.com/Red-Blink/dune-docker-addons/main/canary-manifest.json"
    source_url = "https://github.com/Red-Blink/dune-docker-addons"
    download_url = "https://github.com/Red-Blink/dune-docker-addons/archive/canary.zip"
    local_manifest = {
        "schemaVersion": 1, "id": addon_id, "name": "DASH Canary", "description": "Disposable addon fixture",
        "author": "DASH", "version": "1.0.0", "type": "ui", "permissions": ["ops:read"],
        "entry": {"navigation": "Canary", "path": "index.html"},
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("addon.json", json.dumps(local_manifest))
        archive.writestr("index.html", "<!doctype html><title>DASH canary</title>")
    package = buffer.getvalue()
    remote_manifest = {
        "schemaVersion": 1, "id": addon_id, "name": "DASH Canary", "description": "Disposable addon fixture",
        "author": "DASH", "version": "1.0.0", "type": "ui", "permissions": ["ops:read"],
        "sourceUrl": source_url, "downloadUrl": download_url, "sha256": hashlib.sha256(package).hexdigest(),
    }
    index_url = "https://raw.githubusercontent.com/Red-Blink/dune-docker-addons/main/canary-index.json"
    index = {
        "schemaVersion": 1, "updatedAt": "2026-01-01T00:00:00Z",
        "addons": [{
            "id": addon_id, "name": "DASH Canary", "description": "Disposable addon fixture",
            "author": "DASH", "version": "1.0.0", "manifestUrl": manifest_url,
            "lifecycle": "active", "permissions": ["ops:read"],
        }],
    }
    payloads = {index_url: json.dumps(index).encode(), manifest_url: json.dumps(remote_manifest).encode(), download_url: package}
    def fetcher(url, maximum, timeout=10):
        if url not in payloads:
            raise ValueError("creator canary attempted an unexpected network fixture")
        value = payloads[url]
        if len(value) > int(maximum):
            raise ValueError("creator canary fixture exceeds requested bound")
        return value
    return addon_id, index_url, fetcher


def run_canary(root, receipt_store, *, principal_id="system", now=time.time):
    root = pathlib.Path(root).resolve(strict=True)
    inputs = input_manifest(root)
    started_epoch = float(now())
    checks = {name: False for name in CHECK_NAMES}
    evidence = {
        "inputFiles": len(inputs["files"]), "galleryDesigns": 0, "galleryRatings": 0,
        "presetId": "none", "presetTarget": "none", "cosmeticCatalogItems": 0,
        "addonPermissions": 0, "retirementBlockedConditions": 0,
    }
    temporary_created = False
    temporary_removed = False
    failure = None
    try:
        with tempfile.TemporaryDirectory(prefix="dash-creator-canary-") as directory:
            stage = pathlib.Path(directory)
            temporary_created = stage.is_dir()
            checks["inputsBound"] = len(inputs["files"]) == len(INPUT_FILES) and HASH_PATTERN.fullmatch(inputs["sha256"]) is not None

            exported = _base_export()
            checks["liveBaseExport"] = bool(
                exported.get("pieceCount") == 2 and exported.get("placeableCount") == 0
                and exported.get("anchor", {}).get("x") == 50.0
                and exported.get("gameRestoreSupported") is False
                and HASH_PATTERN.fullmatch(str(exported.get("sha256") or ""))
            )

            gallery = base_creator.Gallery(stage / "gallery" / "gallery.sqlite3").initialize()
            design_id = "creator-canary-design-000000000001"
            first = gallery.publish("Canary design", "Disposable", "canary", _design(), "private", design_id)
            rated = gallery.rate(design_id, "canary-rater", 5)
            updated = gallery.publish("Canary design updated", "Disposable", "canary", _design(), "public", design_id)
            listed = gallery.list(include_private=False)
            evidence["galleryDesigns"] = len(listed)
            evidence["galleryRatings"] = int(rated.get("rating_count") or 0)
            checks["galleryRoundTrip"] = bool(
                first.get("sha256") == updated.get("sha256")
                and updated.get("visibility") == "public"
                and evidence["galleryDesigns"] == 1 and evidence["galleryRatings"] == 1
                and gallery.path.stat().st_mode & 0o077 == 0
            )

            ready_plan = _retirement_plan(blocked=False)
            blocked_plan = _retirement_plan(blocked=True)
            ready_cooldown = _cooldown_plan(blocked=False)
            blocked_cooldown = _cooldown_plan(blocked=True)
            evidence["retirementBlockedConditions"] = (
                len(blocked_plan.get("blockers") or []) + len(blocked_cooldown.get("blockers") or [])
            )
            checks["retirementGuards"] = bool(
                ready_plan.get("canExecute") and ready_plan.get("gameRecoverable")
                and ready_plan.get("destructiveDelete") is False
                and not blocked_plan.get("canExecute")
                and ready_cooldown.get("canExecute")
                and ready_cooldown.get("databaseColumn") == "dune.totems.last_backup_timestamp"
                and ready_cooldown.get("remainingSecondsKnown") is False
                and ready_cooldown.get("mapLifecycleInvoked") is False
                and not blocked_cooldown.get("canExecute")
                and evidence["retirementBlockedConditions"] >= 8
            )

            config_stage = stage / "config"
            config_stage.mkdir(mode=0o700)
            for target in gameplay_presets.TARGETS:
                shutil.copy2(root / "config" / target, config_stage / target)
            preset_catalog = root / "config" / "gameplay-presets.json"
            selected = None
            for preset in gameplay_presets.load_catalog(preset_catalog)["presets"]:
                for target in sorted(gameplay_presets.TARGETS):
                    candidate = gameplay_presets.plan(config_stage, preset_catalog, preset["id"], target)
                    if candidate["changed"]:
                        selected = (preset["id"], target, candidate)
                        break
                if selected:
                    break
            if not selected:
                raise ValueError("active gameplay preset catalog has no effective disposable change")
            preset_id, preset_target, planned = selected
            original = (config_stage / preset_target).read_bytes()
            applied = gameplay_presets.apply(config_stage, preset_catalog, preset_id, preset_target, stage / "backups")
            rolled = gameplay_presets.rollback(config_stage, applied["backup"], stage / "backups")
            evidence["presetId"], evidence["presetTarget"] = preset_id, preset_target
            checks["presetApplyRollback"] = bool(
                planned.get("dryRun") and applied.get("idempotent") is False and rolled.get("ok")
                and (config_stage / preset_target).read_bytes() == original
            )
            checks["landsraadPreserved"] = gameplay_presets.validate_landsraad_cycle(config_stage) == ["UserGame.ini", "UserGame.deep-desert-coriolis.ini"]

            cosmetics = cosmetics_admin.load_catalog(root / "config" / "cosmetic-catalog.json")
            evidence["cosmeticCatalogItems"] = int((cosmetics.get("counts") or {}).get("total") or 0)
            cosmetic = next(row for row in cosmetics["items"] if row.get("enabled") and row.get("unlockMode") == "customization")
            before = [{"m_CustomizationId": "UnknownPreserved"}]
            added = cosmetics_admin.plan_entries(before, cosmetics, "add", cosmetic["id"])
            replay = cosmetics_admin.plan_entries(added["after"], cosmetics, "add", cosmetic["id"])
            removed = cosmetics_admin.plan_entries(added["after"], cosmetics, "remove", cosmetic["id"])
            unlocked = cosmetics_admin.plan_entries(before, cosmetics, "unlock-all")
            inventory_ids = {row["id"] for row in cosmetics["items"] if row.get("unlockMode") == "inventory"}
            checks["cosmeticsPlanning"] = bool(
                evidence["cosmeticCatalogItems"] > 0 and added.get("changed") and not replay.get("changed")
                and cosmetics_admin.ids_from_entries(removed["after"]) == ["UnknownPreserved"]
                and not (set(cosmetics_admin.ids_from_entries(unlocked["after"])) & inventory_ids)
            )

            addon_id, index_url, fetcher = _addon_fixture()
            addon_root = stage / "addons"
            installed = addon_admin.install(addon_root, addon_id, ["ops:read"], index_url=index_url, fetcher=fetcher)
            evidence["addonPermissions"] = len(installed["addon"].get("approvedPermissions") or [])
            checks["addonInstall"] = bool(installed.get("ok") and installed["addon"].get("enabled") is False and HASH_PATTERN.fullmatch(installed.get("sha256") or ""))
            enabled = addon_admin.set_enabled(addon_root, addon_id, True)
            permitted = addon_admin.assert_permission(addon_root, addon_id, "ops:read")
            content = addon_admin.content_path(addon_root, addon_id, "index.html")
            checks["addonPermission"] = bool(enabled["addon"].get("enabled") and permitted.get("id") == addon_id and content.is_file())
            removed_addon = addon_admin.remove(addon_root, addon_id)
            recovery_path = pathlib.Path(removed_addon["recoveryPath"])
            checks["addonRecovery"] = bool(removed_addon.get("ok") and recovery_path.is_dir() and not addon_admin.list_installed(addon_root)["addons"])
        temporary_removed = not pathlib.Path(directory).exists()
        checks["temporaryStateRemoved"] = temporary_removed
    except Exception as exc:
        failure = str(exc)[-1000:]
        temporary_removed = "directory" not in locals() or not pathlib.Path(directory).exists()
        checks["temporaryStateRemoved"] = temporary_removed

    try:
        checks["sourceInputsUnchanged"] = hmac.compare_digest(inputs["sha256"], input_manifest(root)["sha256"])
    except (OSError, ValueError):
        checks["sourceInputsUnchanged"] = False

    completed_epoch = float(now())
    isolation = {
        "temporaryStateCreated": temporary_created,
        "temporaryStateRemoved": temporary_removed,
        "liveGalleryOpened": False,
        "liveConfigWritten": False,
        "gameDatabaseOpened": False,
        "playerDataWritten": False,
        "gameMapLifecycleInvoked": False,
        "externalNetworkCalled": False,
    }
    ready = all(checks.values()) and temporary_created and temporary_removed and failure is None
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA,
        "id": "creator-canary-" + secrets.token_hex(16),
        "principalId": str(principal_id or "system")[:128],
        "startedAt": iso(started_epoch), "completedAt": iso(completed_epoch),
        "durationMs": int(round((completed_epoch - started_epoch) * 1000)),
        "inputsSha256": inputs["sha256"], "checks": checks,
        "evidence": evidence, "isolation": isolation, "ready": ready,
    }
    result = receipt_store.record(receipt, completed_epoch)
    result["error"] = failure
    return result
