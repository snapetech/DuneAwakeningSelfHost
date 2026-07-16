#!/usr/bin/env python3
"""Add the example engagement policy to an existing private rewards config once."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import community_rewards  # noqa: E402


def load_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def referenced_track_ids(policy):
    found = set()
    for section_name, rows_name in (("hourly", "tiers"), ("daily", "tiers"), ("weekly", "thresholds")):
        section = policy.get(section_name) or {}
        for row in section.get(rows_name) or []:
            track = (row.get("reward") or {}).get("track") or {}
            if str(track.get("id") or "").strip():
                found.add(str(track["id"]).strip())
    return found


def validate_candidate(candidate):
    with tempfile.TemporaryDirectory(prefix="dash-engagement-upgrade-") as directory:
        root = Path(directory)
        config = root / "community-rewards.json"
        config.write_text(json.dumps(candidate), encoding="utf-8")
        community_rewards.Store(root / "validation.sqlite3", config).initialize()


def merge(active_path, example_path, backup_dir, dry_run=False, now=None):
    active_path = Path(active_path)
    example_path = Path(example_path)
    backup_dir = Path(backup_dir)
    active = load_object(active_path)
    example = load_object(example_path)
    if int(active.get("version", 0)) != int(example.get("version", 0)):
        raise ValueError("active and example community-rewards schema versions differ")
    policy = example.get("engagementRewards")
    if not isinstance(policy, dict) or not policy:
        raise ValueError("example config has no engagementRewards policy")
    if "engagementRewards" in active:
        return {"ok": True, "changed": False, "reason": "existing policy preserved", "path": str(active_path)}
    active_tracks = active.get("tracks", [])
    example_tracks = example.get("tracks", [])
    if not isinstance(active_tracks, list) or not isinstance(example_tracks, list):
        raise ValueError("active and example tracks must be arrays")
    active_by_id = {str(row.get("id") or "").strip(): row for row in active_tracks if isinstance(row, dict)}
    example_by_id = {str(row.get("id") or "").strip(): row for row in example_tracks if isinstance(row, dict)}
    tracks_added = []
    for track_id in sorted(referenced_track_ids(policy)):
        current = active_by_id.get(track_id)
        if current and not bool(current.get("enabled", True)):
            raise ValueError(f"engagement policy requires disabled operator track: {track_id}")
        if not current:
            if track_id not in example_by_id:
                raise ValueError(f"example engagement policy references missing track: {track_id}")
            active_tracks.append(example_by_id[track_id])
            tracks_added.append(track_id)
    active["engagementRewards"] = policy
    validate_candidate(active)
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"community-rewards-before-engagement-{stamp}.json"
    result = {"ok": True, "changed": not dry_run, "planned": bool(dry_run), "path": str(active_path), "backup": str(backup), "tracksAdded": tracks_added}
    if dry_run:
        return result
    backup_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    if backup.exists():
        raise FileExistsError(f"refusing to overwrite existing backup: {backup}")
    shutil.copy2(active_path, backup)
    os.chmod(backup, 0o600)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=active_path.parent, prefix=".community-rewards.", delete=False) as temporary:
            temporary_name = temporary.name
            json.dump(active, temporary, indent=2, ensure_ascii=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, active_path)
        directory_fd = os.open(active_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("active")
    parser.add_argument("example")
    parser.add_argument("backup_dir")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(merge(args.active, args.example, args.backup_dir, args.dry_run), sort_keys=True))


if __name__ == "__main__":
    main()
