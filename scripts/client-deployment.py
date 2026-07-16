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
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_STATUSES = {"prepared", "installed", "failed-rolled-back", "failed-rollback-required", "rolled-back"}
ATTENTION_STATUSES = {"prepared", "failed-rollback-required"}
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
        fsync_directory(path.parent)
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


def confined_no_symlinks(root, relative, label="target"):
    root = root.resolve()
    target = confined(root, relative)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"{label} path contains a symlink: {cursor}")
    return target


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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


def valid_sha256(value):
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def load_manifest(path):
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        raise ValueError(f"invalid deployment manifest path: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    label = f"invalid deployment manifest: {path}"
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise ValueError(label)
    deployment_id = data.get("deploymentId")
    if not isinstance(deployment_id, str) or not SAFE_ID.fullmatch(deployment_id) or path.parent.name != deployment_id:
        raise ValueError(f"{label}: invalid deployment identity")
    if data.get("status") not in MANIFEST_STATUSES:
        raise ValueError(f"{label}: invalid status")
    try:
        root = pathlib.Path(data["gameRoot"])
        executable = pathlib.Path(data["gameExecutable"])
    except (KeyError, TypeError):
        raise ValueError(f"{label}: invalid game paths") from None
    if not root.is_absolute() or executable != confined(root, EXE_REL):
        raise ValueError(f"{label}: executable is outside the recorded game root")
    if not valid_sha256(data.get("gameExecutableSha256")):
        raise ValueError(f"{label}: invalid executable checksum")
    rows = data.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{label}: files must be a non-empty list")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label}: invalid file row")
        try:
            relative = pathlib.Path(row["relativeTarget"])
            target = pathlib.Path(row["target"])
            original = row["original"]
        except (KeyError, TypeError):
            raise ValueError(f"{label}: incomplete file row") from None
        if not allowed_target(relative) or relative.as_posix() in seen:
            raise ValueError(f"{label}: unsafe or duplicate target {relative}")
        seen.add(relative.as_posix())
        if not target.is_absolute() or target != confined_no_symlinks(root, relative):
            raise ValueError(f"{label}: target does not match the recorded game root: {target}")
        if not valid_sha256(row.get("installedSha256")) or not isinstance(original, dict):
            raise ValueError(f"{label}: invalid installed/original metadata")
        if original.get("existed") is True:
            expected_backup = pathlib.Path("backups") / relative
            if (not valid_sha256(original.get("sha256")) or
                    not isinstance(original.get("mode"), int) or
                    not 0 <= original["mode"] <= 0o7777 or
                    original.get("backupRelative") != expected_backup.as_posix()):
                raise ValueError(f"{label}: invalid backup metadata for {relative}")
            confined(path.parent, expected_backup)
        elif original.get("existed") is False:
            if any(original.get(key) is not None for key in ("sha256", "mode", "backupRelative")):
                raise ValueError(f"{label}: unexpected backup metadata for {relative}")
        else:
            raise ValueError(f"{label}: invalid original-file state for {relative}")
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
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot safely evaluate active deployments: {exc}") from exc
        if manifest.get("status") != "installed":
            continue
        overlap = wanted.intersection(str(row.get("target", "")) for row in manifest["files"])
        for target in sorted(overlap):
            collisions.append({"deployment": manifest.get("deploymentId"), "target": target})
    return collisions


def plan_sha256(plan):
    payload = {key: value for key, value in plan.items() if key != "planSha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_reviewed_plan(args):
    if not args.reviewed_plan:
        missing = [name for name, value in (("--game-dir", args.game_dir),
                                            ("--deployment", args.deployment),
                                            ("--file", args.file),
                                            ("--expect-plan-sha256", args.expect_plan_sha256)) if not value]
        if missing:
            raise ValueError(f"install requires {' '.join(missing)} unless --reviewed-plan is used")
        return args
    if args.game_dir or args.deployment or args.file or args.expect_plan_sha256:
        raise ValueError("--reviewed-plan cannot be combined with --game-dir, --deployment, --file, or --expect-plan-sha256")
    path = pathlib.Path(args.reviewed_plan).expanduser().resolve()
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read reviewed plan {path}: {exc}") from exc
    if not isinstance(plan, dict) or plan.get("schemaVersion") != 1:
        raise ValueError(f"invalid reviewed plan: {path}")
    receipt = plan.get("planSha256")
    if not valid_sha256(receipt) or receipt != plan_sha256(plan):
        raise ValueError(f"reviewed plan checksum is invalid: {path}")
    try:
        files = [f"{row['source']}::{row['relativeTarget']}" for row in plan["files"]]
        game_dir = plan["gameRoot"]
        deployment = plan["deploymentId"]
        state_root = plan["stateRoot"]
    except (KeyError, TypeError):
        raise ValueError(f"reviewed plan is incomplete: {path}") from None
    if not files:
        raise ValueError(f"reviewed plan has no files: {path}")
    args.file = files
    args.game_dir = game_dir
    args.deployment = deployment
    args.state_root = state_root
    args.expect_plan_sha256 = receipt
    return args


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
        target = confined_no_symlinks(root, relative)
        if target.exists() and not target.is_file():
            raise ValueError(f"target exists but is not a regular file: {target}")
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
    plan = {
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
    plan["planSha256"] = plan_sha256(plan)
    return plan


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
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError(f"deployment lock is not a regular file: {lock_path}")
    stream = os.fdopen(descriptor, "a+", encoding="utf-8")
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
        fsync_directory(target.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_backups(rows, deployment_dir):
    results = []
    for row in rows:
        original = row["original"]
        if original["existed"]:
            backup = confined_no_symlinks(deployment_dir, pathlib.Path(original["backupRelative"]), "backup")
            actual = sha256(backup) if backup.is_file() else None
            results.append({"target": row["target"], "backup": str(backup),
                            "expectedSha256": original["sha256"], "actualSha256": actual,
                            "ok": actual == original["sha256"]})
        else:
            results.append({"target": row["target"], "backup": None,
                            "expectedSha256": None, "actualSha256": None, "ok": True})
    return results


def rollback_rows(rows, deployment_dir):
    backups = verify_backups(rows, deployment_dir)
    if not all(row["ok"] for row in backups):
        raise RuntimeError(f"backup verification failed: {[row for row in backups if not row['ok']]}")
    for row in reversed(rows):
        target = pathlib.Path(row["target"])
        original = row["original"]
        if original["existed"]:
            backup = deployment_dir / original["backupRelative"]
            copy_atomic(backup, target, original["mode"])
        elif target.exists():
            target.unlink()
            fsync_directory(target.parent)


def install(args):
    require_confirmation(args.confirm)
    require_client_stopped()
    plan = build_plan(args)
    if args.expect_plan_sha256 != plan["planSha256"]:
        raise ValueError(f"reviewed plan mismatch: expected {args.expect_plan_sha256}, current {plan['planSha256']}; run plan again")
    state_root = pathlib.Path(plan["stateRoot"])
    deployment_dir = state_root / args.deployment
    manifest_path = deployment_dir / "manifest.json"
    with locked(state_root):
        require_client_stopped()
        if deployment_dir.exists():
            raise ValueError(f"deployment id already has state; choose a new id: {args.deployment}")
        plan = build_plan(args)
        if args.expect_plan_sha256 != plan["planSha256"]:
            raise ValueError(f"reviewed plan changed while waiting for the deployment lock: expected {args.expect_plan_sha256}, current {plan['planSha256']}; review a new plan")
        if plan["collisions"]:
            raise ValueError(f"targets owned by another active deployment: {plan['collisions']}")
        deployment_dir.mkdir(parents=True, mode=0o700)
        backup_root = deployment_dir / "backups"
        rows = []
        try:
            for planned in plan["files"]:
                source = pathlib.Path(planned["source"])
                target = pathlib.Path(planned["target"])
                relative = pathlib.Path(planned["relativeTarget"])
                if not source.is_file() or sha256(source) != planned["sourceSha256"]:
                    raise RuntimeError(f"source changed after locked plan validation: {source}")
                current_exists = target.is_file()
                current_sha256 = sha256(target) if current_exists else None
                if current_exists != planned["currentExists"] or current_sha256 != planned["currentSha256"]:
                    raise RuntimeError(f"target changed after locked plan validation: {target}")
                original = {"existed": current_exists, "sha256": current_sha256,
                            "mode": None, "backupRelative": None}
                if current_exists:
                    original["mode"] = stat.S_IMODE(target.stat().st_mode)
                    backup = backup_root / relative
                    copy_atomic(target, backup, 0o600)
                    if sha256(backup) != original["sha256"]:
                        raise RuntimeError(f"backup verification failed: {backup}")
                    original["backupRelative"] = str(backup.relative_to(deployment_dir))
                rows.append({**planned, "original": original, "installedSha256": planned["sourceSha256"]})
        except Exception:
            shutil.rmtree(deployment_dir)
            fsync_directory(state_root)
            raise
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
                if not source.is_file() or sha256(source) != row["sourceSha256"]:
                    raise RuntimeError(f"source changed after locked plan validation: {source}")
                installed.append(row)
                copy_atomic(source, target)
                if sha256(target) != row["installedSha256"]:
                    raise RuntimeError(f"installed checksum mismatch: {target}")
            manifest["status"] = "installed"
            manifest["installedAt"] = utc_now()
            atomic_json(manifest_path, manifest)
        except Exception as install_error:
            try:
                rollback_rows(installed, deployment_dir)
            except Exception as rollback_error:
                manifest["status"] = "failed-rollback-required"
                manifest["failedAt"] = utc_now()
                atomic_json(manifest_path, manifest)
                raise RuntimeError(
                    f"installation failed ({install_error}); automatic rollback also failed ({rollback_error}); "
                    f"deployment requires manual recovery: {manifest_path}"
                ) from rollback_error
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
    require_client_stopped()
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
        target = confined_no_symlinks(root, relative)
        if not target.is_file():
            raise ValueError(f"installed target is missing: {target}")
        original_path = None if original_text == "ABSENT" else pathlib.Path(original_text).expanduser().resolve()
        if original_path is not None and not original_path.is_file():
            raise ValueError(f"original backup is missing: {original_path}")
        rows.append({"relative": relative, "target": target, "originalPath": original_path,
                     "installedSha256": sha256(target),
                     "originalSha256": sha256(original_path) if original_path is not None else None,
                     "originalMode": stat.S_IMODE(original_path.stat().st_mode) if original_path is not None else None})
    if not rows:
        raise ValueError("at least one --installed is required")
    deployment_dir = state_root / args.deployment
    manifest_path = deployment_dir / "manifest.json"
    with locked(state_root):
        require_client_stopped()
        if deployment_dir.exists():
            raise ValueError(f"deployment id already has state; choose a new id: {args.deployment}")
        collisions = active_collisions(state_root, args.deployment, [row["target"] for row in rows])
        if collisions:
            raise ValueError(f"targets owned by another active deployment: {collisions}")
        deployment_dir.mkdir(parents=True, mode=0o700)
        manifest_rows = []
        try:
            for row in rows:
                relative, target, original_path = row["relative"], row["target"], row["originalPath"]
                if not target.is_file() or sha256(target) != row["installedSha256"]:
                    raise RuntimeError(f"installed target changed while waiting for the deployment lock: {target}")
                original = {"existed": original_path is not None, "sha256": None, "mode": None, "backupRelative": None}
                if original_path is not None:
                    if not original_path.is_file() or sha256(original_path) != row["originalSha256"]:
                        raise RuntimeError(f"original backup changed while waiting for the deployment lock: {original_path}")
                    backup = deployment_dir / "backups" / relative
                    copy_atomic(original_path, backup, 0o600)
                    original.update({"sha256": row["originalSha256"], "mode": row["originalMode"],
                                     "backupRelative": str(backup.relative_to(deployment_dir))})
                    if sha256(backup) != original["sha256"]:
                        raise RuntimeError(f"adopted backup verification failed: {backup}")
                manifest_rows.append({"source": "<adopted-current>", "relativeTarget": relative.as_posix(),
                                      "target": str(target), "sourceSha256": row["installedSha256"],
                                      "sourceSize": target.stat().st_size, "currentExists": True,
                                      "currentSha256": row["installedSha256"], "installedSha256": row["installedSha256"],
                                      "original": original})
        except Exception:
            shutil.rmtree(deployment_dir)
            fsync_directory(state_root)
            raise
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
    backups = verify_backups(manifest["files"], manifest_path.parent)
    return {"deploymentId": manifest["deploymentId"], "status": manifest["status"],
            "manifest": str(manifest_path), "files": results, "backups": backups,
            "backupSetHealthy": all(row["ok"] for row in backups),
            "gameExecutableExpectedSha256": manifest["gameExecutableSha256"],
            "gameExecutableActualSha256": exe_actual,
            "gameExecutableUnchanged": exe_actual == manifest["gameExecutableSha256"],
            "ok": manifest["status"] == "installed" and exe_actual == manifest["gameExecutableSha256"] and
                  all(row["ok"] for row in results) and all(row["ok"] for row in backups)}


def verify_recoverable_rollback(manifest, manifest_path):
    backups = verify_backups(manifest["files"], manifest_path.parent)
    exe = pathlib.Path(manifest["gameExecutable"])
    exe_actual = sha256(exe) if exe.is_file() else None
    files = []
    for row in manifest["files"]:
        target = pathlib.Path(row["target"])
        actual = sha256(target) if target.is_file() else None
        original = row["original"]
        original_hash = original["sha256"] if original["existed"] else None
        allowed = [row["installedSha256"]]
        if original_hash not in allowed:
            allowed.append(original_hash)
        files.append({"target": str(target), "actualSha256": actual,
                      "allowedSha256": allowed, "ok": actual in allowed})
    return {"files": files, "backups": backups,
            "gameExecutableActualSha256": exe_actual,
            "gameExecutableUnchanged": exe_actual == manifest["gameExecutableSha256"],
            "ok": exe_actual == manifest["gameExecutableSha256"] and
                  all(row["ok"] for row in files) and all(row["ok"] for row in backups)}


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
    if manifest.get("status") not in {"installed", "prepared", "failed-rollback-required"}:
        raise ValueError(f"deployment is not installed: {manifest.get('status')}")
    deployment_dir = manifest_path.parent
    with locked(state_root):
        require_client_stopped()
        manifest = load_manifest(manifest_path)
        recovering = manifest.get("status") in {"prepared", "failed-rollback-required"}
        check = verify_recoverable_rollback(manifest, manifest_path) if recovering else verify_manifest(manifest, manifest_path)
        if not check["ok"]:
            detail = "recovery state" if recovering else "installed files"
            raise ValueError(f"{detail}, executable, or backups drifted; refusing rollback until reviewed")
        try:
            rollback_rows(manifest["files"], deployment_dir)
            for row in manifest["files"]:
                target = pathlib.Path(row["target"]); original = row["original"]
                actual = sha256(target) if target.is_file() else None
                expected = original["sha256"] if original["existed"] else None
                if actual != expected:
                    raise RuntimeError(f"rollback verification failed: {target}")
        except Exception as exc:
            manifest["status"] = "failed-rollback-required"
            manifest["rollbackFailedAt"] = utc_now()
            manifest["rollbackError"] = str(exc)
            atomic_json(manifest_path, manifest)
            raise RuntimeError(f"rollback incomplete; retry the same guarded rollback after review: {manifest_path}: {exc}") from exc
        manifest["status"] = "rolled-back"
        manifest["rolledBackAt"] = utc_now()
        manifest.pop("rollbackError", None)
        atomic_json(manifest_path, manifest)
    return manifest


def audit(args):
    state_root = pathlib.Path(args.state_root).expanduser().resolve()
    processes = running_client_processes()
    deployments = []
    issues = []
    owners = {}
    if state_root.exists() and not state_root.is_dir():
        issues.append({"code": "state-root-not-directory", "path": str(state_root),
                       "action": "move the conflicting path and rerun audit"})
    elif state_root.exists():
        mode = stat.S_IMODE(state_root.stat().st_mode)
        if mode & 0o077:
            issues.append({"code": "state-root-permissions", "path": str(state_root),
                           "mode": oct(mode), "action": f"chmod 700 {state_root}"})
        lock_path = state_root / ".lock"
        if lock_path.is_symlink() or (lock_path.exists() and not lock_path.is_file()):
            issues.append({"code": "invalid-lock-file", "path": str(lock_path),
                           "action": "remove the invalid lock only after confirming no deployment command is running"})
        elif lock_path.is_file() and stat.S_IMODE(lock_path.stat().st_mode) & 0o077:
            issues.append({"code": "private-state-permissions", "path": str(lock_path),
                           "mode": oct(stat.S_IMODE(lock_path.stat().st_mode)),
                           "action": f"chmod 600 {lock_path}"})
        for entry in sorted(state_root.iterdir()):
            if entry.name == ".lock":
                continue
            if entry.is_symlink():
                issues.append({"code": "unexpected-state-symlink", "path": str(entry),
                               "action": "remove the symlink after reviewing its destination"})
                continue
            if not entry.is_dir():
                issues.append({"code": "unexpected-state-entry", "path": str(entry),
                               "action": "review and move this entry outside the private state root"})
                continue
            entry_mode = stat.S_IMODE(entry.stat().st_mode)
            if entry_mode & 0o077:
                issues.append({"code": "private-state-permissions", "path": str(entry),
                               "mode": oct(entry_mode), "action": f"chmod 700 {entry}"})
            manifest_path = entry / "manifest.json"
            if not manifest_path.is_file():
                issues.append({"code": "orphan-state-directory", "path": str(entry),
                               "action": "review the directory; restore its manifest or archive it outside the state root"})
                continue
            manifest_mode = stat.S_IMODE(manifest_path.stat().st_mode)
            if manifest_mode & 0o077:
                issues.append({"code": "private-state-permissions", "path": str(manifest_path),
                               "mode": oct(manifest_mode), "action": f"chmod 600 {manifest_path}"})
            try:
                manifest = load_manifest(manifest_path)
                status_value = manifest["status"]
                detail = verify_manifest(manifest, manifest_path) if status_value == "installed" else None
                backup_detail = verify_backups(manifest["files"], manifest_path.parent)
                item = {"deploymentId": manifest["deploymentId"], "status": status_value,
                        "manifest": str(manifest_path), "requiresAttention": status_value in ATTENTION_STATUSES,
                        "backupSetHealthy": all(row["ok"] for row in backup_detail),
                        "ok": (detail["ok"] if detail else status_value in {"rolled-back", "failed-rolled-back"}) and
                              all(row["ok"] for row in backup_detail)}
                if detail:
                    item.update({"gameExecutableUnchanged": detail["gameExecutableUnchanged"],
                                 "installedFilesHealthy": all(row["ok"] for row in detail["files"]),
                                 "backupSetHealthy": detail["backupSetHealthy"]})
                for backup in backup_detail:
                    backup_path = pathlib.Path(backup["backup"]) if backup["backup"] else None
                    if backup_path and backup_path.is_file() and stat.S_IMODE(backup_path.stat().st_mode) & 0o077:
                        issues.append({"code": "private-state-permissions", "path": str(backup_path),
                                       "mode": oct(stat.S_IMODE(backup_path.stat().st_mode)),
                                       "action": f"chmod 600 {backup_path}"})
                deployments.append(item)
                if status_value == "installed":
                    for row in manifest["files"]:
                        owners.setdefault(row["target"], []).append(manifest["deploymentId"])
                if not item["ok"]:
                    if status_value in ATTENTION_STATUSES:
                        action = f"retry guarded rollback for {manifest['deploymentId']} after reviewing mixed file state"
                    elif status_value == "installed":
                        action = f"run verify --deployment {manifest['deploymentId']} and review reported drift"
                    else:
                        action = f"review the retained backup set for historical deployment {manifest['deploymentId']}"
                    issues.append({"code": "deployment-attention", "deploymentId": manifest["deploymentId"],
                                   "status": status_value, "action": action})
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                issues.append({"code": "invalid-manifest", "path": str(manifest_path), "error": str(exc),
                               "action": "quarantine or repair this manifest before any new deployment"})
    for target, deployment_ids in sorted(owners.items()):
        if len(deployment_ids) > 1:
            issues.append({"code": "duplicate-active-owner", "target": target,
                           "deployments": deployment_ids,
                           "action": "stop and reconcile the active manifests before mutation"})
    return {"schemaVersion": "dune-client-deployment-audit/v1", "stateRoot": str(state_root),
            "clientProcesses": processes, "clientRunning": bool(processes),
            "deployments": deployments, "issues": issues,
            "summary": {"deploymentCount": len(deployments),
                        "activeCount": sum(row["status"] == "installed" for row in deployments),
                        "attentionCount": len(issues)}, "ok": not issues}


def status(args):
    state_root = pathlib.Path(args.state_root).expanduser().resolve()
    paths = [state_root / args.deployment / "manifest.json"] if args.deployment else sorted(state_root.glob("*/manifest.json")) if state_root.exists() else []
    if args.deployment and not paths[0].is_file():
        raise ValueError(f"deployment manifest not found: {paths[0]}")
    result = []
    for path in paths:
        if path.is_file():
            manifest = load_manifest(path)
            result.append(verify_manifest(manifest, path) if manifest.get("status") == "installed" else {
                "deploymentId": manifest.get("deploymentId"), "status": manifest.get("status"),
                "manifest": str(path),
                "requiresAttention": manifest.get("status") in ATTENTION_STATUSES,
                "ok": manifest.get("status") in {"rolled-back", "failed-rolled-back"}})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default="backups/client-deployments",
                        help="private manifest/backup root outside the game directory (default: %(default)s)")
    sub = parser.add_subparsers(dest="action", required=True)
    child = sub.add_parser("plan")
    child.add_argument("--game-dir", required=True)
    child.add_argument("--deployment", required=True)
    child.add_argument("--file", action="append", default=[], metavar="SOURCE::TARGET",
                       help="reviewed source and allowed game-relative target; repeat for multiple files")
    child = sub.add_parser("install")
    child.add_argument("--reviewed-plan", help="reviewed JSON output from the plan command")
    child.add_argument("--game-dir")
    child.add_argument("--deployment")
    child.add_argument("--file", action="append", default=[], metavar="SOURCE::TARGET",
                       help="explicit-plan form; repeat for multiple files")
    child.add_argument("--expect-plan-sha256",
                       help="planSha256 from the reviewed, immediately preceding plan")
    child.add_argument("--confirm", required=True,
                       help=f"exact mutation confirmation: {CONFIRMATION!r}")
    child = sub.add_parser("adopt")
    child.add_argument("--game-dir", required=True); child.add_argument("--deployment", required=True)
    child.add_argument("--installed", action="append", default=[], help="RELATIVE_TARGET::ORIGINAL_BACKUP_OR_ABSENT")
    child.add_argument("--confirm", required=True,
                       help=f"exact adoption confirmation: {ADOPT_CONFIRMATION!r}")
    child = sub.add_parser("verify"); child.add_argument("--deployment", required=True)
    child = sub.add_parser("rollback"); child.add_argument("--deployment", required=True)
    child.add_argument("--confirm", required=True,
                       help=f"exact mutation confirmation: {CONFIRMATION!r}")
    child = sub.add_parser("status"); child.add_argument("--deployment")
    sub.add_parser("audit")
    args = parser.parse_args()
    try:
        if args.action == "plan": result = build_plan(args)
        elif args.action == "install": result = install(apply_reviewed_plan(args))
        elif args.action == "adopt": result = adopt(args)
        elif args.action == "verify":
            _root, path, manifest = manifest_for(args); result = verify_manifest(manifest, path)
            if not result["ok"]: print(json.dumps(result, indent=2)); return 1
        elif args.action == "rollback": result = rollback(args)
        elif args.action == "status": result = status(args)
        else:
            result = audit(args)
            if not result["ok"]:
                print(json.dumps(result, indent=2, sort_keys=True)); return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"client-deployment: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
