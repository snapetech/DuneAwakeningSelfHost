#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/backup-offsite.sh [env-file]

Creates a local DASH backup when requested, then syncs backups/ to an offsite or
onsite destination.

Configuration can come from the environment or from DUNE_BACKUP_REMOTE_ENV.

Modes:
  DUNE_BACKUP_OFFSITE_MODE=none    create/prune local backups only
  DUNE_BACKUP_OFFSITE_MODE=rclone  rclone sync backups/ DEST
  DUNE_BACKUP_OFFSITE_MODE=rsync   rsync -a --delete backups/ DEST/
  DUNE_BACKUP_OFFSITE_MODE=restic  restic backup backups/

Common knobs:
  DUNE_BACKUP_REMOTE_ENV=examples/backup/rclone-offsite.env
  DUNE_BACKUP_CREATE_LOCAL=true
  DUNE_BACKUP_INCLUDE_MAINTENANCE=true
  DUNE_BACKUP_KEEP_LOCAL_DAYS=7

rclone:
  DUNE_BACKUP_RCLONE_DEST=remote:path
  DUNE_BACKUP_KEEP_REMOTE_DAYS=30

rsync:
  DUNE_BACKUP_RSYNC_DEST=user@host:/path

restic:
  RESTIC_REPOSITORY=...
  RESTIC_PASSWORD or RESTIC_PASSWORD_FILE=...
  DUNE_BACKUP_RESTIC_TAGS=dash,dune,self-host
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

env_file="${1:-.env}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -n "${DUNE_BACKUP_REMOTE_ENV:-}" ]]; then
  if [[ ! -f "$DUNE_BACKUP_REMOTE_ENV" ]]; then
    printf 'backup config not found: %s\n' "$DUNE_BACKUP_REMOTE_ENV" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  . "$DUNE_BACKUP_REMOTE_ENV"
  set +a
fi

mode="${DUNE_BACKUP_OFFSITE_MODE:-none}"
create_local="${DUNE_BACKUP_CREATE_LOCAL:-true}"
include_maintenance="${DUNE_BACKUP_INCLUDE_MAINTENANCE:-true}"
keep_local_days="${DUNE_BACKUP_KEEP_LOCAL_DAYS:-0}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
log_dir="backups/offsite-logs"
mkdir -p "$log_dir"
log_file="${log_dir}/${timestamp}-${mode}.log"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$log_file"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf '%s is required for mode %s\n' "$1" "$mode" >&2
    exit 1
  fi
}

if [[ "$create_local" == "true" ]]; then
  log "creating local backup with scripts/backup-state.sh"
  ./scripts/backup-state.sh "$env_file" 2>&1 | tee -a "$log_file"
fi

if [[ ! -d backups ]]; then
  log "no backups directory exists; nothing to sync"
  exit 0
fi

case "$mode" in
  none|"")
    log "offsite mode is none; local backup phase complete"
    ;;
  rclone)
    require_command rclone
    dest="${DUNE_BACKUP_RCLONE_DEST:-}"
    if [[ -z "$dest" ]]; then
      printf 'DUNE_BACKUP_RCLONE_DEST is required for rclone mode\n' >&2
      exit 1
    fi
    log "syncing backups/ to rclone destination ${dest}"
    rclone sync backups "$dest" --create-empty-src-dirs 2>&1 | tee -a "$log_file"
    keep_remote_days="${DUNE_BACKUP_KEEP_REMOTE_DAYS:-0}"
    if [[ "$keep_remote_days" =~ ^[0-9]+$ && "$keep_remote_days" -gt 0 ]]; then
      log "pruning remote files older than ${keep_remote_days} days"
      rclone delete "$dest" --min-age "${keep_remote_days}d" 2>&1 | tee -a "$log_file"
      rclone rmdirs "$dest" --leave-root 2>&1 | tee -a "$log_file"
    fi
    ;;
  rsync)
    require_command rsync
    dest="${DUNE_BACKUP_RSYNC_DEST:-}"
    if [[ -z "$dest" ]]; then
      printf 'DUNE_BACKUP_RSYNC_DEST is required for rsync mode\n' >&2
      exit 1
    fi
    log "syncing backups/ to rsync destination ${dest}"
    rsync -a --delete backups/ "${dest%/}/" 2>&1 | tee -a "$log_file"
    ;;
  restic)
    require_command restic
    if [[ -z "${RESTIC_REPOSITORY:-}" ]]; then
      printf 'RESTIC_REPOSITORY is required for restic mode\n' >&2
      exit 1
    fi
    IFS=',' read -ra tags <<< "${DUNE_BACKUP_RESTIC_TAGS:-dash,dune}"
    tag_args=()
    for tag in "${tags[@]}"; do
      [[ -n "$tag" ]] && tag_args+=(--tag "$tag")
    done
    log "running restic backup for backups/"
    restic backup backups "${tag_args[@]}" 2>&1 | tee -a "$log_file"
    keep_daily="${DUNE_BACKUP_RESTIC_KEEP_DAILY:-14}"
    keep_weekly="${DUNE_BACKUP_RESTIC_KEEP_WEEKLY:-8}"
    keep_monthly="${DUNE_BACKUP_RESTIC_KEEP_MONTHLY:-6}"
    log "running restic forget policy"
    restic forget --prune --keep-daily "$keep_daily" --keep-weekly "$keep_weekly" --keep-monthly "$keep_monthly" "${tag_args[@]}" 2>&1 | tee -a "$log_file"
    ;;
  *)
    printf 'unknown DUNE_BACKUP_OFFSITE_MODE: %s\n' "$mode" >&2
    exit 1
    ;;
esac

if [[ "$include_maintenance" != "true" ]]; then
  log "DUNE_BACKUP_INCLUDE_MAINTENANCE=false; note that maintenance backups remain local-only unless another job syncs them"
fi

if [[ "$keep_local_days" =~ ^[0-9]+$ && "$keep_local_days" -gt 0 ]]; then
  log "pruning local backup directories older than ${keep_local_days} days"
  find backups -mindepth 1 -maxdepth 1 -type d \
    ! -name admin-panel \
    ! -name offsite-logs \
    -mtime +"$keep_local_days" \
    -print -exec rm -rf {} + 2>&1 | tee -a "$log_file"
fi

log "backup-offsite complete"
