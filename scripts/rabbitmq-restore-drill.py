#!/usr/bin/env python3
"""Run or inspect the networkless DASH RabbitMQ recovery rehearsal."""

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
import rabbitmq_restore_drill


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", default=os.environ.get("ADMIN_WORKSPACE", str(ROOT)))
    result.add_argument("--host-workspace", default=os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_HOST_WORKSPACE") or os.environ.get("DUNE_RESTORE_DRILL_HOST_WORKSPACE"))
    result.add_argument("--backup-set", help="Specific full backup directory beneath backups/")
    result.add_argument("--receipt-root")
    result.add_argument("--docker-socket", default=os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_DOCKER_SOCKET", "/var/run/docker.sock"))
    result.add_argument("--image", default=os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_IMAGE", rabbitmq_restore_drill.DEFAULT_IMAGE))
    result.add_argument("--max-backup-age-hours", type=float, default=float(os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_MAX_BACKUP_AGE_HOURS", "36")))
    result.add_argument("--readiness-seconds", type=int, default=int(os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_READINESS_SECONDS", "180")))
    result.add_argument("--memory-mib", type=int, default=int(os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_MEMORY_MIB", "1024")))
    result.add_argument("--cpus", type=float, default=float(os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_CPUS", "1")))
    result.add_argument("--pids-limit", type=int, default=int(os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_PIDS_LIMIT", "256")))
    result.add_argument("--run-uid", type=int, default=int(os.environ.get("DUNE_HOST_UID", str(os.getuid()))))
    result.add_argument("--run-gid", type=int, default=int(os.environ.get("DUNE_HOST_GID", str(os.getgid()))))
    result.add_argument("--retention", type=int, default=int(os.environ.get("DUNE_RABBITMQ_RESTORE_DRILL_RECEIPT_RETENTION", "1000")))
    result.add_argument("--status", action="store_true")
    result.add_argument("--limit", type=int, default=20)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    workspace = pathlib.Path(args.workspace)
    receipts = pathlib.Path(args.receipt_root) if args.receipt_root else workspace / "backups" / "admin-panel" / "rabbitmq-restore-drills"
    if args.status:
        payload = rabbitmq_restore_drill.status(receipts, args.limit)
    else:
        try:
            payload = rabbitmq_restore_drill.run_drill(
                workspace, host_workspace=args.host_workspace or workspace, backup_set=args.backup_set,
                receipt_root=receipts, docker_socket=args.docker_socket, image=args.image,
                max_backup_age_seconds=max(1, args.max_backup_age_hours * 3600),
                readiness_seconds=max(10, args.readiness_seconds), memory_bytes=max(256, args.memory_mib) * 1024**2,
                cpu_count=max(0.25, args.cpus), pids_limit=max(64, args.pids_limit),
                run_uid=args.run_uid, run_gid=args.run_gid, retention=max(10, args.retention),
            )
        except Exception as exc:
            payload = {"ok": False, "error": str(exc)}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
