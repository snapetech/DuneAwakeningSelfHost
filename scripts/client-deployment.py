#!/usr/bin/env python3
"""Transactional, checksum-bound deployment of DASH client artifacts."""

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import sys
import tempfile


CONFIRMATION = "MUTATE DUNE CLIENT FILES"
ADOPT_CONFIRMATION = "ADOPT EXISTING DUNE CLIENT FILES"
EXE_REL = pathlib.Path("DuneSandbox/Binaries/Win64/DuneSandbox-Win64-Shipping.exe")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SAFE_OVERLAY = re.compile(r"^zzz_dash_[A-Za-z0-9_.-]+\.(?:pak|sig)$")
FIXED_TARGETS = {
    "DuneSandbox/Binaries/Win64/version.dll",
    "DuneSandbox/Binaries/Win64/dune-win-client-probe.env",
    "DuneSandbox/Binaries/Win64/lua54.dll",
}
CLIENT_PROCESS_MARKERS = (
    b"DuneSandbox-Win64-Shipping.exe",
    b"DuneSandbox_BE.exe",
    b"DuneSandbox.exe",
)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def confined(root, relative):
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"target must be a confined relative path: {relative}")
    root = root.resolve()
    target = (root / relative).resolve(strict=False)
    if target != root and root not in target.parents:
        raise ValueError(f"target escapes game directory: {relative}")
    return target


def allowed_target(relative):
    value = relative.as_posix()
    if value in FIXED_TARGETS:
        return True
    prefix = "DuneSandbox/Content/Paks/"
    return value.startswith(prefix) and "/" not in value[len(prefix):] and bool(SAFE_OVERLAY.fullmatch(relative.name))


def parse_file(value):
    if "::" not in value:
        raise ValueError("--file must use SOURCE::RELATIVE_TARGET")
    source_text, relative_text = value.split("::", 1)
    source = pathlib.Path(source_text).expanduser().resolve()
    relative = pathlib.Path(relative_text)
    if not source.is_file() or not stat.S_ISREG(source.stat().st_mode):
        raise ValueError(f"source is not a regular file: {source}")
    if not allowed_target(relative):
        raise ValueError(f"target is not an allowed DASH client artifact path: {relative}")
    return source, relative


def game_root(path):
    root = pathlib.Path(path).expanduser().resolve()
    exe = confined(root, EXE_REL)
    if not exe.is_file():
        raise ValueError(f"Dune shipping executable not found: {exe}")
    return root, exe


def load_manifest(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or not isinstance(data.get("files"), list):
        raise ValueError(f"invalid deployment manifest: {path}")
    return data


def active_collisions(state_root, deployment_id, targets):
    collisions = []
    if not state_root.exists():
        return collisions
    wanted = {str(path) for path in targets}
    for manifest_path in state_root.glob("*/manifest.json"):
        if manifest_path.parent.name == deployment_id:
            continue
        try:
            manifest = load_manifest(manifest_path)
        except Exception:
            continue
        if manifest.get("status") != "installed":
            continue
        overlap = wanted.intersection(str(row.get("target", "")) for row in manifest["files"])
        for target in sorted(overlap):
            collisions.append({"deployment": manifest.get("deploymentId"), "target": target})
    return collisions


def build_plan(args):
    if not SAFE_ID.fullmatch(args.deployment):
        raise ValueError("deployment id must match [a-z0-9][a-z0-9_-]{0,63}")
    root, exe = game_root(args.game_dir)
    state_root = pathlib.Path(args.state_root).expanduser().resolve()
    if state_root == root or root in state_root.parents:
        raise ValueError("deployment state/backups must be outside the game directory")
    parsed = [parse_file(value) for value in args.file]
    if not parsed:
        raise ValueError("at least one --file is required")
    relative_seen = set()
    rows = []
    for source, relative in parsed:
        if relative.as_posix() in relative_seen:
            raise ValueError(f"duplicate target: {relative}")
        relative_seen.add(relative.as_posix())
        target = confined(root, relative)
        rows.append({
            "source": str(source),
            "relativeTarget": relative.as_posix(),
            "target": str(target),
            "sourceSha256": sha256(source),
            "sourceSize": source.stat().st_size,
            "currentExists": target.is_file(),
            "currentSha256": sha256(target) if target.is_file() else None,
        })
    collisions = active_collisions(state_root, args.deployment, [pathlib.Path(row["target"]) for row in rows])
    return {
        "schemaVersion": 1,
        "deploymentId": args.deployment,
        "gameRoot": str(root),
        "gameExecutable": str(exe),
        "gameExecutableSha256": sha256(exe),
        "stateRoot": str(state_root),
        "manifest": str(state_root / args.deployment / "manifest.json"),
        "files": rows,
        "collisions": collisions,
        "mutationRequired": any(row["sourceSha256"] != row["currentSha256"] for row in rows),
    }


def require_confirmation(value):
    if value != CONFIRMATION:
        raise ValueError(f"exact confirmation required: {CONFIRMATION}")


def running_client_processes(proc_root=pathlib.Path("/proc")):
    matches = []
    for cmdline_path in proc_root.glob("[0-9]*/cmdline"):
        try:
            cmdline = cmdline_path.read_bytes()
        except (OSError, PermissionError):
            continue
        if any(marker in cmdline for marker in CLIENT_PROCESS_MARKERS):
            matches.append({
                "pid": int(cmdline_path.parent.name),
                "command": cmdline.replace(b"\0", b" ").decode("utf-8", errors="replace").strip(),
            })
    return sorted(matches, key=lambda row: row["pid"])


def require_client_stopped():
    matches = running_client_processes()
    if matches:
        raise ValueError(f"Dune client processes are running; close the game before mutation: {matches}")


def locked(state_root):
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_root, 0o700)
    lock_path = state_root / ".lock"
    stream = lock_path.open("a+", encoding="utf-8")
    os.chmod(lock_path, 0o600)
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
    return stream


def copy_atomic(source, target, mode=0o644):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.dash-new-", dir=target.parent)
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, mode)
        with open(temporary, "rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def rollback_rows(rows, deployment_dir):
    for row in reversed(rows):
        target = pathlib.Path(row["target"])
        original = row["original"]
        if original["existed"]:
            backup = deployment_dir / original["backupRelative"]
            if not backup.is_file() or sha256(backup) != original["sha256"]:
                raise RuntimeError(f"backup verification failed: {backup}")
            copy_atomic(backup, target, original["mode"])
        elif target.exists():
            target.unlink()


def install(args):
    require_confirmation(args.confirm)
    require_client_stopped()
    plan = build_plan(args)
    if plan["collisions"]:
        raise ValueError(f"targets owned by another active deployment: {plan['collisions']}")
    state_root = pathlib.Path(plan["stateRoot"])
    deployment_dir = state_root / args.deployment
    manifest_path = deployment_dir / "manifest.json"
    with locked(state_root):
        if deployment_dir.exists():
            raise ValueError(f"deployment id already has state; choose a new id: {args.deployment}")
        deployment_dir.mkdir(parents=True, mode=0o700)
        backup_root = deployment_dir / "backups"
        rows = []
        for planned in plan["files"]:
            target = pathlib.Path(planned["target"])
            relative = pathlib.Path(planned["relativeTarget"])
            original = {"existed": target.is_file(), "sha256": None, "mode": None, "backupRelative": None}
            if target.is_file():
                original["sha256"] = sha256(target)
                original["mode"] = stat.S_IMODE(target.stat().st_mode)
                backup = backup_root / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                os.chmod(backup, 0o600)
                if sha256(backup) != original["sha256"]:
                    raise RuntimeError(f"backup verification failed: {backup}")
                original["backupRelative"] = str(backup.relative_to(deployment_dir))
            rows.append({**planned, "original": original, "installedSha256": planned["sourceSha256"]})
        manifest = {
            "schemaVersion": 1,
            "deploymentId": args.deployment,
            "status": "prepared",
            "createdAt": utc_now(),
            "gameRoot": plan["gameRoot"],
            "gameExecutable": plan["gameExecutable"],
            "gameExecutableSha256": plan["gameExecutableSha256"],
            "files": rows,
        }
        atomic_json(manifest_path, manifest)
        installed = []
        try:
            for row in rows:
                source, target = pathlib.Path(row["source"]), pathlib.Path(row["target"])
                installed.append(row)
                copy_atomic(source, target)
                if sha256(target) != row["installedSha256"]:
                    raise RuntimeError(f"installed checksum mismatch: {target}")
            manifest["status"] = "installed"
            manifest["installedAt"] = utc_now()
            atomic_json(manifest_path, manifest)
        except Exception:
            rollback_rows(installed, deployment_dir)
            manifest["status"] = "failed-rolled-back"
            manifest["failedAt"] = utc_now()
            atomic_json(manifest_path, manifest)
            raise
    return manifest


def adopt(args):
    if args.confirm != ADOPT_CONFIRMATION:
        raise ValueError(f"exact confirmation required: {ADOPT_CONFIRMATION}")
    if not SAFE_ID.fullmatch(args.deployment):
        raise ValueError("deployment id must match [a-z0-9][a-z0-9_-]{0,63}")
    root, exe = game_root(args.game_dir)
    state_root = pathlib.Path(args.state_root).expanduser().resolve()
    if state_root == root or root in state_root.parents:
        raise ValueError("deployment state/backups must be outside the game directory")
    rows = []
    seen = set()
    for value in args.installed:
        if "::" not in value:
            raise ValueError("--installed must use RELATIVE_TARGET::ORIGINAL_BACKUP_OR_ABSENT")
        relative_text, original_text = value.split("::", 1)
        relative = pathlib.Path(relative_text)
        if not allowed_target(relative):
            raise ValueError(f"target is not an allowed DASH client artifact path: {relative}")
        if relative.as_posix() in seen:
            raise ValueError(f"duplicate target: {relative}")
        seen.add(relative.as_posix())
        target = confined(root, relative)
        if not target.is_file():
            raise ValueError(f"installed target is missing: {target}")
        original_path = None if original_text == "ABSENT" else pathlib.Path(original_text).expanduser().resolve()
        if original_path is not None and not original_path.is_file():
            raise ValueError(f"original backup is missing: {original_path}")
        rows.append((relative, target, original_path))
    if not rows:
        raise ValueError("at least one --installed is required")
    collisions = active_collisions(state_root, args.deployment, [row[1] for row in rows])
    if collisions:
        raise ValueError(f"targets owned by another active deployment: {collisions}")
    deployment_dir = state_root / args.deployment
    manifest_path = deployment_dir / "manifest.json"
    with locked(state_root):
        if deployment_dir.exists():
            raise ValueError(f"deployment id already has state; choose a new id: {args.deployment}")
        deployment_dir.mkdir(parents=True, mode=0o700)
        manifest_rows = []
        for relative, target, original_path in rows:
            installed_hash = sha256(target)
            original = {"existed": original_path is not None, "sha256": None, "mode": None, "backupRelative": None}
            if original_path is not None:
                backup = deployment_dir / "backups" / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original_path, backup)
                os.chmod(backup, 0o600)
                original.update({"sha256": sha256(original_path), "mode": stat.S_IMODE(original_path.stat().st_mode),
                                 "backupRelative": str(backup.relative_to(deployment_dir))})
                if sha256(backup) != original["sha256"]:
                    raise RuntimeError(f"adopted backup verification failed: {backup}")
            manifest_rows.append({"source": "<adopted-current>", "relativeTarget": relative.as_posix(),
                                  "target": str(target), "sourceSha256": installed_hash,
                                  "sourceSize": target.stat().st_size, "currentExists": True,
                                  "currentSha256": installed_hash, "installedSha256": installed_hash,
                                  "original": original})
        manifest = {"schemaVersion": 1, "deploymentId": args.deployment, "status": "installed",
                    "createdAt": utc_now(), "adoptedAt": utc_now(), "gameRoot": str(root),
                    "gameExecutable": str(exe), "gameExecutableSha256": sha256(exe), "files": manifest_rows}
        atomic_json(manifest_path, manifest)
    return manifest


def verify_manifest(manifest, manifest_path):
    results = []
    for row in manifest["files"]:
        target = pathlib.Path(row["target"])
        actual = sha256(target) if target.is_file() else None
        results.append({"target": str(target), "expectedSha256": row["installedSha256"], "actualSha256": actual,
                        "ok": actual == row["installedSha256"]})
    exe = pathlib.Path(manifest["gameExecutable"])
    exe_actual = sha256(exe) if exe.is_file() else None
    return {"deploymentId": manifest["deploymentId"], "status": manifest["status"],
            "manifest": str(manifest_path), "files": results,
            "gameExecutableExpectedSha256": manifest["gameExecutableSha256"],
            "gameExecutableActualSha256": exe_actual,
            "gameExecutableUnchanged": exe_actual == manifest["gameExecutableSha256"],
            "ok": manifest["status"] == "installed" and exe_actual == manifest["gameExecutableSha256"] and all(row["ok"] for row in results)}


def manifest_for(args):
    state_root = pathlib.Path(args.state_root).expanduser().resolve()
    path = state_root / args.deployment / "manifest.json"
    if not path.is_file():
        raise ValueError(f"deployment manifest not found: {path}")
    return state_root, path, load_manifest(path)


def rollback(args):
    require_confirmation(args.confirm)
    require_client_stopped()
    state_root, manifest_path, manifest = manifest_for(args)
    if manifest.get("status") != "installed":
        raise ValueError(f"deployment is not installed: {manifest.get('status')}")
    check = verify_manifest(manifest, manifest_path)
    if not check["ok"]:
        raise ValueError("installed files drifted; refusing rollback until reviewed")
    deployment_dir = manifest_path.parent
    with locked(state_root):
        rollback_rows(manifest["files"], deployment_dir)
        for row in manifest["files"]:
            target = pathlib.Path(row["target"]); original = row["original"]
            actual = sha256(target) if target.is_file() else None
            expected = original["sha256"] if original["existed"] else None
            if actual != expected:
                raise RuntimeError(f"rollback verification failed: {target}")
        manifest["status"] = "rolled-back"
        manifest["rolledBackAt"] = utc_now()
        atomic_json(manifest_path, manifest)
    return manifest


def status(args):
    state_root = pathlib.Path(args.state_root).expanduser().resolve()
    paths = [state_root / args.deployment / "manifest.json"] if args.deployment else sorted(state_root.glob("*/manifest.json")) if state_root.exists() else []
    result = []
    for path in paths:
        if path.is_file():
            manifest = load_manifest(path)
            result.append(verify_manifest(manifest, path) if manifest.get("status") == "installed" else {
                "deploymentId": manifest.get("deploymentId"), "status": manifest.get("status"), "manifest": str(path), "ok": True})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default="backups/client-deployments")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "install"):
        child = sub.add_parser(action)
        child.add_argument("--game-dir", required=True)
        child.add_argument("--deployment", required=True)
        child.add_argument("--file", action="append", default=[], help="SOURCE::RELATIVE_TARGET")
        if action == "install": child.add_argument("--confirm", required=True)
    child = sub.add_parser("adopt")
    child.add_argument("--game-dir", required=True); child.add_argument("--deployment", required=True)
    child.add_argument("--installed", action="append", default=[], help="RELATIVE_TARGET::ORIGINAL_BACKUP_OR_ABSENT")
    child.add_argument("--confirm", required=True)
    child = sub.add_parser("verify"); child.add_argument("--deployment", required=True)
    child = sub.add_parser("rollback"); child.add_argument("--deployment", required=True); child.add_argument("--confirm", required=True)
    child = sub.add_parser("status"); child.add_argument("--deployment")
    args = parser.parse_args()
    try:
        if args.action == "plan": result = build_plan(args)
        elif args.action == "install": result = install(args)
        elif args.action == "adopt": result = adopt(args)
        elif args.action == "verify":
            _root, path, manifest = manifest_for(args); result = verify_manifest(manifest, path)
            if not result["ok"]: print(json.dumps(result, indent=2)); return 1
        elif args.action == "rollback": result = rollback(args)
        else: result = status(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"client-deployment: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
