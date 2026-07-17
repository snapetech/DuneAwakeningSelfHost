"""Secret-safe credential posture, change detection, and backup coverage."""

import datetime
import hashlib
import hmac
import json
import os
import pathlib
import re
import sqlite3
import stat
import tarfile
import threading


TRUE_VALUES = {"1", "true", "yes", "on"}
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,63}")
ENV_RE = re.compile(r"[A-Z][A-Z0-9_]{1,127}")
ALLOWED_SOURCE_TYPES = {"env", "file", "env-or-file"}
ALLOWED_BACKUP_TYPES = {"env-copy", "env-or-config", "config-member", "direct-artifact", "none"}
ALLOWED_ROTATION_POLICIES = {"scheduled", "provider-managed", "retain-with-ledger", "stable-public-identity"}


def _utc(epoch):
    return datetime.datetime.fromtimestamp(float(epoch), datetime.timezone.utc).isoformat()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _bool(value):
    return str(value or "").strip().lower() in TRUE_VALUES


def load_catalog(path):
    document = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"schemaVersion", "credentials"}:
        raise ValueError("credential lifecycle catalog must contain only schemaVersion and credentials")
    if document["schemaVersion"] != 1 or not isinstance(document["credentials"], list):
        raise ValueError("unsupported credential lifecycle catalog schema")
    if not 1 <= len(document["credentials"]) <= 128:
        raise ValueError("credential lifecycle catalog requires 1..128 entries")
    seen = set()
    for row in document["credentials"]:
        required = {"id", "title", "category", "source", "requiredWhen", "minimumBytes", "placeholders", "rotationPolicy", "maximumAgeDays", "consumers", "backup", "documentation"}
        if not isinstance(row, dict) or set(row) not in (required, required | {"externalBlocker"}):
            raise ValueError("credential lifecycle entry has unexpected fields")
        credential_id = row["id"]
        if not isinstance(credential_id, str) or not ID_RE.fullmatch(credential_id) or credential_id in seen:
            raise ValueError("credential lifecycle IDs must be unique slugs")
        seen.add(credential_id)
        if not all(isinstance(row[key], str) and row[key].strip() for key in ("title", "category", "documentation")):
            raise ValueError(f"credential {credential_id} has invalid display metadata")
        source = row["source"]
        if not isinstance(source, dict) or source.get("type") not in ALLOWED_SOURCE_TYPES:
            raise ValueError(f"credential {credential_id} has invalid source")
        source_type = source["type"]
        allowed_source = {"type", "key"} if source_type == "env" else {"type", "pathKey", "defaultPath"} if source_type == "file" else {"type", "key", "fileKey"}
        if set(source) != allowed_source:
            raise ValueError(f"credential {credential_id} source fields are invalid")
        for key in ("key", "fileKey", "pathKey"):
            if key in source and (not isinstance(source[key], str) or not ENV_RE.fullmatch(source[key])):
                raise ValueError(f"credential {credential_id} has invalid {key}")
        if "defaultPath" in source and (not isinstance(source["defaultPath"], str) or pathlib.PurePosixPath(source["defaultPath"]).is_absolute() or ".." in pathlib.PurePosixPath(source["defaultPath"]).parts):
            raise ValueError(f"credential {credential_id} default path must be relative and confined")
        condition = row["requiredWhen"]
        if not isinstance(condition, dict) or not condition or not set(condition).issubset({"always", "allGates", "anyGates"}):
            raise ValueError(f"credential {credential_id} has invalid requiredWhen")
        if "always" in condition and condition["always"] is not True:
            raise ValueError(f"credential {credential_id} always condition must be true")
        for key in ("allGates", "anyGates"):
            if key in condition and (not isinstance(condition[key], list) or not condition[key] or any(not isinstance(gate, str) or not ENV_RE.fullmatch(gate) for gate in condition[key])):
                raise ValueError(f"credential {credential_id} has invalid {key}")
        if not isinstance(row["minimumBytes"], int) or not 8 <= row["minimumBytes"] <= 16384:
            raise ValueError(f"credential {credential_id} minimumBytes is invalid")
        if not isinstance(row["placeholders"], list) or any(not isinstance(value, str) or not value for value in row["placeholders"]):
            raise ValueError(f"credential {credential_id} placeholders are invalid")
        if row["rotationPolicy"] not in ALLOWED_ROTATION_POLICIES:
            raise ValueError(f"credential {credential_id} rotation policy is invalid")
        if "externalBlocker" in row and row["externalBlocker"] is not True:
            raise ValueError(f"credential {credential_id} externalBlocker must be true when present")
        if row["maximumAgeDays"] is not None and (not isinstance(row["maximumAgeDays"], int) or not 1 <= row["maximumAgeDays"] <= 3650):
            raise ValueError(f"credential {credential_id} maximumAgeDays is invalid")
        if not isinstance(row["consumers"], list) or not row["consumers"] or any(not isinstance(value, str) or not value.strip() for value in row["consumers"]):
            raise ValueError(f"credential {credential_id} consumers are invalid")
        backup = row["backup"]
        if not isinstance(backup, dict) or backup.get("type") not in ALLOWED_BACKUP_TYPES:
            raise ValueError(f"credential {credential_id} backup contract is invalid")
        expected_backup = {"type", "member"} if backup["type"] == "config-member" else {"type", "name"} if backup["type"] == "direct-artifact" else {"type"}
        if set(backup) != expected_backup:
            raise ValueError(f"credential {credential_id} backup fields are invalid")
    return document


def _required(condition, environment):
    if condition.get("always"):
        return True
    all_gates = condition.get("allGates") or []
    any_gates = condition.get("anyGates") or []
    return (not all_gates or all(_bool(environment.get(key)) for key in all_gates)) and (not any_gates or any(_bool(environment.get(key)) for key in any_gates))


def _confined_path(root, raw, default):
    root = pathlib.Path(root).resolve()
    value = str(raw or default or "").strip()
    if value.startswith("/workspace/"):
        candidate = root / value[len("/workspace/"):]
    elif pathlib.PurePosixPath(value).is_absolute():
        candidate = pathlib.Path(value)
    else:
        candidate = root / value
    if candidate.is_symlink():
        raise ValueError("credential path must not be a symlink")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("credential path escapes workspace") from exc
    return resolved


def _material(entry, root, environment, env_file):
    source = entry["source"]
    source_type = source["type"]
    if source_type == "env":
        value = str(environment.get(source["key"], ""))
        return value.encode("utf-8"), {"kind": "environment", "reference": source["key"], "path": pathlib.Path(env_file)}
    if source_type == "env-or-file":
        file_value = str(environment.get(source["fileKey"], "")).strip()
        if file_value:
            path = _confined_path(root, file_value, None)
            return path.read_bytes() if path.is_file() and not path.is_symlink() else b"", {"kind": "file", "reference": source["fileKey"], "path": path}
        value = str(environment.get(source["key"], ""))
        return value.encode("utf-8"), {"kind": "environment", "reference": source["key"], "path": pathlib.Path(env_file)}
    path = _confined_path(root, environment.get(source["pathKey"]), source["defaultPath"])
    return path.read_bytes() if path.is_file() and not path.is_symlink() else b"", {"kind": "file", "reference": source["pathKey"], "path": path}


def backup_evidence(backup_root):
    root = pathlib.Path(backup_root)
    candidates = []
    if root.is_dir():
        for path in root.iterdir():
            if path.is_dir() and not path.is_symlink() and (path / "manifest.txt").is_file():
                candidates.append(path)
    if not candidates:
        return {"available": False, "path": None, "createdAt": None, "env": False, "members": set(), "artifacts": set()}
    latest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    artifacts = {path.name for path in latest.iterdir() if path.is_file() and not path.is_symlink()}
    members = set()
    archive = latest / "config.tgz"
    if archive.is_file() and not archive.is_symlink():
        try:
            with tarfile.open(archive, "r:gz") as handle:
                count = 0
                for member in handle:
                    count += 1
                    if count > 10000:
                        raise ValueError("config backup has too many members")
                    if member.isfile():
                        members.add(member.name.lstrip("./"))
        except (OSError, ValueError, tarfile.TarError):
            members = set()
    manifest = {}
    for line in (latest / "manifest.txt").read_text(encoding="utf-8", errors="replace").splitlines()[:200]:
        if "=" in line:
            key, value = line.split("=", 1)
            manifest[key.strip()] = value.strip()
    env_name = pathlib.Path(manifest.get("env_archive") or ".env").name
    return {"available": True, "path": latest.name, "createdAt": _utc(latest.stat().st_mtime), "env": env_name in artifacts, "members": members, "artifacts": artifacts}


def _backup_covered(entry, evidence, source_meta):
    if not evidence.get("available"):
        return False
    contract = entry["backup"]
    kind = contract["type"]
    if kind == "none":
        return True
    if kind == "env-copy":
        return bool(evidence.get("env"))
    if kind == "config-member":
        return contract["member"] in evidence.get("members", set())
    if kind == "direct-artifact":
        return contract["name"] in evidence.get("artifacts", set())
    if source_meta["kind"] == "environment":
        return bool(evidence.get("env"))
    path = source_meta["path"]
    try:
        member = path.resolve().relative_to(pathlib.Path(source_meta["root"]).resolve()).as_posix()
    except (KeyError, ValueError):
        return False
    return member in evidence.get("members", set())


class ObservationStore:
    def __init__(self, database, key_path, anchor_path=None, *, owner_uid=None, owner_gid=None, clock=None):
        self.database = pathlib.Path(database)
        self.key_path = pathlib.Path(key_path)
        self.anchor_path = pathlib.Path(anchor_path) if anchor_path else self.database.with_suffix(".anchor.json")
        self.owner_uid = int(owner_uid) if owner_uid not in (None, "") else None
        self.owner_gid = int(owner_gid) if owner_gid not in (None, "") else None
        self.clock = clock or __import__("time").time
        self.lock = threading.RLock()

    def _secure(self, path, mode):
        path = pathlib.Path(path)
        os.chmod(path, mode)
        if os.geteuid() == 0 and (self.owner_uid is not None or self.owner_gid is not None):
            os.chown(path, self.owner_uid if self.owner_uid is not None else -1, self.owner_gid if self.owner_gid is not None else -1)

    def _key(self, create=True):
        if self.key_path.is_symlink():
            raise ValueError("credential lifecycle HMAC key must not be a symlink")
        created = False
        if not self.key_path.exists():
            if not create:
                raise ValueError("credential lifecycle HMAC key is missing")
            self.key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._secure(self.key_path.parent, 0o700)
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(os.urandom(32))
                handle.flush()
                os.fsync(handle.fileno())
            created = True
        if created or self.owner_uid is not None or self.owner_gid is not None:
            self._secure(self.key_path.parent, 0o700)
            self._secure(self.key_path, 0o600)
        if not self.key_path.is_file() or self.key_path.stat().st_mode & 0o077:
            raise ValueError("credential lifecycle HMAC key must be a private regular file")
        value = self.key_path.read_bytes()
        if len(value) < 32:
            raise ValueError("credential lifecycle HMAC key is too short")
        return value

    def _connect(self):
        if self.database.is_symlink():
            raise ValueError("credential lifecycle database must not be a symlink")
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._secure(self.database.parent, 0o700)
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            pragma journal_mode=WAL;
            pragma synchronous=FULL;
            create table if not exists observations (
              sequence integer primary key autoincrement,
              credential_id text not null,
              event_type text not null check(event_type in ('baseline','rotation')),
              observed_at real not null,
              material_hmac text not null,
              previous_event_hmac text,
              event_hmac text not null unique
            );
            create trigger if not exists credential_observations_no_update before update on observations begin select raise(abort, 'credential observations are append-only'); end;
            create trigger if not exists credential_observations_no_delete before delete on observations begin select raise(abort, 'credential observations are append-only'); end;
        """)
        self._secure(self.database, 0o600)
        for suffix in ("-wal", "-shm"):
            companion = pathlib.Path(str(self.database) + suffix)
            if companion.exists() and not companion.is_symlink():
                self._secure(companion, 0o600)
        return connection

    @staticmethod
    def _event_document(row):
        return {"sequence": int(row["sequence"]), "credentialId": row["credential_id"], "eventType": row["event_type"], "observedAt": float(row["observed_at"]), "materialHmac": row["material_hmac"], "previousEventHmac": row["previous_event_hmac"]}

    def _event_hmac(self, key, document):
        return hmac.new(key, _canonical(document), hashlib.sha256).hexdigest()

    @staticmethod
    def _anchor_document(sequence, event_hmac, updated_at):
        return {"schemaVersion": 1, "headSequence": int(sequence), "headEventHmac": event_hmac, "updatedAt": float(updated_at)}

    def _anchor_hmac(self, key, document):
        return hmac.new(key, b"anchor\x00" + _canonical(document), hashlib.sha256).hexdigest()

    def _write_anchor(self, key, sequence, event_hmac, updated_at):
        if self.anchor_path.is_symlink():
            raise ValueError("credential lifecycle head anchor must not be a symlink")
        self.anchor_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._secure(self.anchor_path.parent, 0o700)
        document = self._anchor_document(sequence, event_hmac, updated_at)
        payload = {**document, "anchorHmac": self._anchor_hmac(key, document)}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
        temporary = self.anchor_path.with_name(f".{self.anchor_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.anchor_path)
            self._secure(self.anchor_path, 0o600)
            directory = os.open(self.anchor_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _read_anchor(self, key):
        if self.anchor_path.is_symlink() or not self.anchor_path.is_file() or self.anchor_path.stat().st_mode & 0o077:
            raise ValueError("credential lifecycle head anchor must be a private regular file")
        if self.anchor_path.stat().st_size > 4096:
            raise ValueError("credential lifecycle head anchor is oversized")
        payload = json.loads(self.anchor_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"schemaVersion", "headSequence", "headEventHmac", "updatedAt", "anchorHmac"}:
            raise ValueError("credential lifecycle head anchor schema is invalid")
        document = {key_name: payload[key_name] for key_name in ("schemaVersion", "headSequence", "headEventHmac", "updatedAt")}
        if document["schemaVersion"] != 1 or not isinstance(document["headSequence"], int) or document["headSequence"] < 0:
            raise ValueError("credential lifecycle head anchor values are invalid")
        if document["headEventHmac"] is not None and (not isinstance(document["headEventHmac"], str) or not re.fullmatch(r"[0-9a-f]{64}", document["headEventHmac"])):
            raise ValueError("credential lifecycle head anchor event HMAC is invalid")
        if isinstance(document["updatedAt"], bool) or not isinstance(document["updatedAt"], (int, float)) or not hmac.compare_digest(str(payload["anchorHmac"]), self._anchor_hmac(key, document)):
            raise ValueError("credential lifecycle head anchor authentication failed")
        return document

    def _ensure_anchor(self, connection, key):
        if self.anchor_path.exists() or self.anchor_path.is_symlink():
            return
        count = int(connection.execute("select count(*) from observations").fetchone()[0])
        if count:
            raise ValueError("credential lifecycle head anchor is missing for a non-empty ledger")
        self._write_anchor(key, 0, None, float(self.clock()))

    def _verify(self, connection, key):
        previous = None
        events = 0
        rotations = 0
        for row in connection.execute("select * from observations order by sequence"):
            document = self._event_document(row)
            if document["previousEventHmac"] != previous or not hmac.compare_digest(row["event_hmac"], self._event_hmac(key, document)):
                raise ValueError(f"credential observation chain invalid at sequence {row['sequence']}")
            previous = row["event_hmac"]
            events += 1
            rotations += row["event_type"] == "rotation"
        integrity = connection.execute("pragma integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"credential observation database integrity failure: {integrity}")
        anchor = self._read_anchor(key)
        if anchor["headSequence"] != events or anchor["headEventHmac"] != previous:
            raise ValueError("credential lifecycle database head does not match the authenticated anchor")
        return {"ok": True, "events": events, "rotations": rotations, "headSequence": events, "headHmacPresent": bool(previous), "anchorValid": True, "anchorUpdatedAt": _utc(anchor["updatedAt"])}

    def observe(self, credential_id, material):
        key = self._key()
        material_hmac = hmac.new(key, b"material\x00" + credential_id.encode() + b"\x00" + material, hashlib.sha256).hexdigest()
        with self.lock:
            connection = self._connect()
            try:
                connection.execute("begin immediate")
                self._ensure_anchor(connection, key)
                self._verify(connection, key)
                latest = connection.execute("select * from observations where credential_id=? order by sequence desc limit 1", (credential_id,)).fetchone()
                if latest and hmac.compare_digest(latest["material_hmac"], material_hmac):
                    connection.commit()
                    return {"changed": False, "eventType": None, "lastChangedAt": float(latest["observed_at"])}
                previous = connection.execute("select event_hmac from observations order by sequence desc limit 1").fetchone()
                event_type = "rotation" if latest else "baseline"
                observed_at = float(self.clock())
                sequence = int(connection.execute("select coalesce(max(sequence),0)+1 from observations").fetchone()[0])
                document = {"sequence": sequence, "credentialId": credential_id, "eventType": event_type, "observedAt": observed_at, "materialHmac": material_hmac, "previousEventHmac": previous[0] if previous else None}
                event_hmac = self._event_hmac(key, document)
                connection.execute("insert into observations(sequence,credential_id,event_type,observed_at,material_hmac,previous_event_hmac,event_hmac) values(?,?,?,?,?,?,?)", (sequence, credential_id, event_type, observed_at, material_hmac, previous[0] if previous else None, event_hmac))
                connection.commit()
                self._write_anchor(key, sequence, event_hmac, observed_at)
                return {"changed": True, "eventType": event_type, "lastChangedAt": observed_at}
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def status(self):
        key = self._key()
        with self.lock:
            connection = self._connect()
            try:
                self._ensure_anchor(connection, key)
                status = self._verify(connection, key)
                latest = {row["credential_id"]: float(row["observed_at"]) for row in connection.execute("select credential_id, max(observed_at) observed_at from observations group by credential_id")}
                status["lastChangedAt"] = latest
                return status
            finally:
                connection.close()


def verify_database(database, key_path, anchor_path=None):
    store = ObservationStore(database, key_path, anchor_path=anchor_path)
    key = store._key(create=False)
    if store.database.is_symlink():
        raise ValueError("credential lifecycle database must not be a symlink")
    connection = sqlite3.connect(f"file:{pathlib.Path(database)}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return store._verify(connection, key)
    finally:
        connection.close()


def evaluate(catalog, root, environment, env_file, backup_root, store=None, *, now=None):
    now = float(now if now is not None else __import__("time").time())
    root = pathlib.Path(root).resolve()
    evidence = backup_evidence(backup_root)
    rows = []
    history_error = None
    history = {"ok": True, "events": 0, "rotations": 0, "headSequence": 0, "headHmacPresent": False, "lastChangedAt": {}}
    if store:
        try:
            history = store.status()
        except Exception as exc:
            history_error = str(exc)
            history = {"ok": False, "events": 0, "rotations": 0, "headSequence": 0, "headHmacPresent": False, "lastChangedAt": {}}
    for entry in catalog["credentials"]:
        required = _required(entry["requiredWhen"], environment)
        try:
            material, source_meta = _material(entry, root, environment, env_file)
            source_meta["root"] = root
            source_path = source_meta["path"]
            private = source_path.is_file() and not source_path.is_symlink() and not (source_path.stat().st_mode & 0o077)
            present = bool(material)
            placeholder = material.decode("utf-8", errors="ignore").strip() in entry["placeholders"]
            minimum_ok = len(material) >= entry["minimumBytes"]
            backup_covered = _backup_covered(entry, evidence, source_meta) if present else False
            last_changed = history.get("lastChangedAt", {}).get(entry["id"])
            if store and present and not placeholder and minimum_ok and private and not history_error:
                observation = store.observe(entry["id"], material)
                last_changed = observation["lastChangedAt"]
            age_days = max(0.0, (now - last_changed) / 86400.0) if last_changed else None
            max_age = entry["maximumAgeDays"]
            overdue = max_age is not None and age_days is not None and age_days > max_age
            due_soon = max_age is not None and age_days is not None and not overdue and age_days > max_age * 0.8
            findings = []
            if required and not present:
                findings.append("external-credential-pending" if entry.get("externalBlocker") else "missing")
            if present and placeholder:
                findings.append("placeholder")
            if present and not minimum_ok:
                findings.append("short-material")
            if present and not private:
                findings.append("insecure-source-permissions")
            if present and not backup_covered and entry["backup"]["type"] != "none":
                findings.append("backup-uncovered")
            if overdue:
                findings.append("rotation-overdue")
            elif due_soon:
                findings.append("rotation-due-soon")
            blocking = any(value not in {"rotation-due-soon", "external-credential-pending"} for value in findings)
            state = "not-required" if not required and not present else "external-pending" if "external-credential-pending" in findings else "missing" if not present else "attention" if findings else "ready"
            rows.append({
                "id": entry["id"], "title": entry["title"], "category": entry["category"], "required": required,
                "state": state, "ready": not blocking, "configured": present, "sourceKind": source_meta["kind"], "sourceReference": source_meta["reference"],
                "privatePermissions": private, "minimumBytes": entry["minimumBytes"], "minimumMaterialSatisfied": minimum_ok,
                "rotationPolicy": entry["rotationPolicy"], "maximumAgeDays": max_age, "observedAgeDays": round(age_days, 2) if age_days is not None else None,
                "ageEvidence": "tracked-material-change" if last_changed else "not-yet-observed", "backupCovered": backup_covered,
                "consumers": entry["consumers"], "documentation": entry["documentation"], "findings": findings,
            })
        except Exception as exc:
            rows.append({"id": entry["id"], "title": entry["title"], "category": entry["category"], "required": required, "state": "invalid-source", "ready": False, "configured": False, "sourceKind": entry["source"]["type"], "sourceReference": entry["source"].get("key") or entry["source"].get("pathKey"), "privatePermissions": False, "minimumBytes": entry["minimumBytes"], "minimumMaterialSatisfied": False, "rotationPolicy": entry["rotationPolicy"], "maximumAgeDays": entry["maximumAgeDays"], "observedAgeDays": None, "ageEvidence": "unavailable", "backupCovered": False, "consumers": entry["consumers"], "documentation": entry["documentation"], "findings": ["invalid-source"], "error": str(exc)[:300]})
    summary = {
        "total": len(rows), "required": sum(row["required"] for row in rows), "configured": sum(row["configured"] for row in rows),
        "ready": sum(row["ready"] for row in rows), "problems": sum(not row["ready"] for row in rows),
        "missing": sum("missing" in row["findings"] for row in rows), "insecurePermissions": sum("insecure-source-permissions" in row["findings"] for row in rows),
        "backupUncovered": sum("backup-uncovered" in row["findings"] for row in rows), "overdue": sum("rotation-overdue" in row["findings"] for row in rows),
        "dueSoon": sum("rotation-due-soon" in row["findings"] for row in rows),
        "externalPending": sum("external-credential-pending" in row["findings"] for row in rows),
    }
    if store and not history_error:
        try:
            history = store.status()
        except Exception as exc:
            history_error = str(exc)
            history = {"ok": False, "events": 0, "rotations": 0, "headSequence": 0, "headHmacPresent": False, "lastChangedAt": {}}
    public_history = {key: value for key, value in history.items() if key != "lastChangedAt"}
    return {"ok": summary["problems"] == 0 and public_history.get("ok", False), "generatedAt": _utc(now), "summary": summary, "credentials": rows, "history": public_history, "historyError": history_error, "latestBackup": {key: value for key, value in evidence.items() if key not in {"members", "artifacts"}}}


def metrics(result):
    summary = result.get("summary") or {}
    history = result.get("history") or {}
    values = {
        "dash_credential_lifecycle_ok": int(bool(result.get("ok"))),
        "dash_credential_lifecycle_total": summary.get("total", 0),
        "dash_credential_lifecycle_required": summary.get("required", 0),
        "dash_credential_lifecycle_problems": summary.get("problems", 0),
        "dash_credential_lifecycle_missing": summary.get("missing", 0),
        "dash_credential_lifecycle_insecure_permissions": summary.get("insecurePermissions", 0),
        "dash_credential_lifecycle_backup_uncovered": summary.get("backupUncovered", 0),
        "dash_credential_lifecycle_rotation_overdue": summary.get("overdue", 0),
        "dash_credential_lifecycle_rotation_due_soon": summary.get("dueSoon", 0),
        "dash_credential_lifecycle_history_valid": int(bool(history.get("ok"))),
        "dash_credential_lifecycle_rotations_total": history.get("rotations", 0),
    }
    return "".join(f"{key} {value}\n" for key, value in values.items())
