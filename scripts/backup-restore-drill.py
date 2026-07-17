#!/usr/bin/env python3
"""Run or inspect a hardened, isolated DASH PostgreSQL restore rehearsal."""

import argparse
import json
import os
import pathlib
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "admin"))
import restore_drill


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", default=os.environ.get("ADMIN_WORKSPACE", str(REPO_ROOT)))
    result.add_argument("--host-workspace", default=os.environ.get("DUNE_RESTORE_DRILL_HOST_WORKSPACE") or os.environ.get("DUNE_RESTART_HOST_WORKSPACE"))
    result.add_argument("--source", help="Specific .dump path beneath workspace/backups; newest is selected by default")
    result.add_argument("--receipt-root", help="Receipt directory; defaults to backups/admin-panel/restore-drills")
    result.add_argument("--docker-socket", default=os.environ.get("DUNE_RESTORE_DRILL_DOCKER_SOCKET", os.environ.get("DUNE_RESTART_DOCKER_SOCKET", "/var/run/docker.sock")))
    result.add_argument("--image", default=os.environ.get("DUNE_RESTORE_DRILL_IMAGE", restore_drill.DEFAULT_IMAGE))
    result.add_argument("--max-backup-age-hours", type=float, default=float(os.environ.get("DUNE_RESTORE_DRILL_MAX_BACKUP_AGE_HOURS", "36")))
    result.add_argument("--max-restore-seconds", type=int, default=int(os.environ.get("DUNE_RESTORE_DRILL_MAX_RESTORE_SECONDS", "900")))
    result.add_argument("--readiness-seconds", type=int, default=int(os.environ.get("DUNE_RESTORE_DRILL_READINESS_SECONDS", "120")))
    result.add_argument("--command-timeout-seconds", type=int, default=int(os.environ.get("DUNE_RESTORE_DRILL_COMMAND_TIMEOUT_SECONDS", "900")))
    result.add_argument("--memory-mib", type=int, default=int(os.environ.get("DUNE_RESTORE_DRILL_MEMORY_MIB", "2048")))
    result.add_argument("--pgdata-mib", type=int, default=int(os.environ.get("DUNE_RESTORE_DRILL_PGDATA_MIB", "1536")))
    result.add_argument("--cpus", type=float, default=float(os.environ.get("DUNE_RESTORE_DRILL_CPUS", "2")))
    result.add_argument("--pids-limit", type=int, default=int(os.environ.get("DUNE_RESTORE_DRILL_PIDS_LIMIT", "128")))
    result.add_argument("--run-uid", type=int, default=int(os.environ.get("DUNE_HOST_UID", str(os.getuid()))))
    result.add_argument("--run-gid", type=int, default=int(os.environ.get("DUNE_HOST_GID", str(os.getgid()))))
    result.add_argument("--retention-count", type=int, default=int(os.environ.get("DUNE_RESTORE_DRILL_RECEIPT_RETENTION", "1000")))
    result.add_argument("--status", action="store_true", help="Read receipts without running a container")
    result.add_argument("--limit", type=int, default=20, help="Receipt count for --status")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    workspace = pathlib.Path(args.workspace).resolve()
    receipt_root = pathlib.Path(args.receipt_root).resolve() if args.receipt_root else workspace / "backups" / "admin-panel" / "restore-drills"
    if args.status:
        payload = restore_drill.status(receipt_root, args.limit)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("ok") else 1
    try:
        payload = restore_drill.run_drill(
            workspace,
            host_workspace=args.host_workspace or workspace,
            source=args.source,
            receipt_root=receipt_root,
            docker_socket=args.docker_socket,
            image=args.image,
            max_backup_age_seconds=max(1.0, args.max_backup_age_hours * 3600),
            max_restore_seconds=max(1, args.max_restore_seconds),
            readiness_seconds=max(5, args.readiness_seconds),
            command_timeout_seconds=max(30, args.command_timeout_seconds),
            memory_bytes=max(256, args.memory_mib) * 1024**2,
            pgdata_bytes=max(256, args.pgdata_mib) * 1024**2,
            cpu_count=max(0.25, args.cpus),
            pids_limit=max(32, args.pids_limit),
            run_uid=args.run_uid,
            run_gid=args.run_gid,
            retention_count=max(10, args.retention_count),
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
