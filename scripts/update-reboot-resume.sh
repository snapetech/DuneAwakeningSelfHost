#!/usr/bin/env bash
set -euo pipefail

action="${1:-}"
env_file="${2:-.env}"
job_id="${3:-}"
target="${4:-all}"
services="${5:-}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
checkpoint="$repo_root/backups/admin-panel/update-reboot-resume.env"
state_file="$repo_root/backups/admin-panel/restart-jobs.json"
expected_host="${DUNE_UPDATE_REBOOT_HOST:-kspls0}"

host_name() {
  if [[ -n "${DUNE_UPDATE_REBOOT_HOSTNAME_COMMAND:-}" ]]; then
    bash -c "$DUNE_UPDATE_REBOOT_HOSTNAME_COMMAND"
  elif [[ -r /proc/1/ns/uts ]] && command -v nsenter >/dev/null 2>&1; then
    nsenter -t 1 -u hostname
  else
    hostname
  fi
}

write_job_status() {
  local status="$1" error="${2:-}"
  [[ -f "$state_file" && -n "$job_id" ]] || return 0
  python3 - "$state_file" "$job_id" "$status" "$error" <<'PY'
import json, os, pathlib, sys, tempfile, time
path, job_id, status, error = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
state = json.loads(path.read_text(encoding="utf-8"))
for job in state.get("jobs", []):
    if job.get("id") == job_id:
        job["status"] = status
        job["lastError"] = error or None
        job["rebootResumedAt" if status in ("executed", "failed") else "rebootRequestedAt"] = time.time()
        break
fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(state, handle, indent=2, sort_keys=True)
os.replace(name, path)
PY
}

case "$action" in
  request)
    actual_host="$(host_name)"
    if [[ "$actual_host" != "$expected_host" ]]; then
      printf 'refusing update-triggered reboot: expected host %s, got %s\n' "$expected_host" "$actual_host" >&2
      exit 78
    fi
    mkdir -p "$(dirname "$checkpoint")"
    umask 077
    {
      printf 'JOB_ID=%q\n' "$job_id"
      printf 'TARGET=%q\n' "$target"
      printf 'SERVICES=%q\n' "$services"
      printf 'ENV_FILE=%q\n' "$env_file"
      printf 'REQUESTED_AT=%q\n' "$(date -u +%FT%TZ)"
    } > "$checkpoint"
    write_job_status awaiting_reboot
    sync "$checkpoint" "$state_file" 2>/dev/null || sync
    printf 'update reboot checkpoint armed for job %s; rebooting %s\n' "$job_id" "$actual_host"
    if [[ "${DUNE_UPDATE_REBOOT_DRY_RUN:-false}" == "true" ]]; then
      exit 0
    fi
    exec nsenter -t 1 -m -u -i -n -p -- systemctl reboot
    ;;
  resume)
    [[ -f "$checkpoint" ]] || exit 0
    # shellcheck disable=SC1090
    source "$checkpoint"
    job_id="$JOB_ID"
    target="$TARGET"
    services="$SERVICES"
    env_file="$ENV_FILE"
    actual_host="$(hostname)"
    if [[ "$actual_host" != "$expected_host" ]]; then
      printf 'refusing update reboot resume: expected host %s, got %s\n' "$expected_host" "$actual_host" >&2
      exit 78
    fi
    export ENV_FILE="$env_file" DUNE_RESTART_JOB_ID="$job_id" DUNE_RESTART_TARGET="$target"
    export DUNE_RESTART_SERVICES="$services" DUNE_RESTART_ACTION=restart DUNE_RESTART_PHASE=start
    if "$repo_root/scripts/restart-target.sh" "$target"; then
      write_job_status executed
      rm -f "$checkpoint"
      printf 'update reboot resume completed for job %s\n' "$job_id"
    else
      rc=$?
      write_job_status failed "post-reboot start phase failed with return code $rc"
      printf 'update reboot resume failed for job %s with return code %s\n' "$job_id" "$rc" >&2
      exit "$rc"
    fi
    ;;
  *)
    printf 'usage: %s {request|resume} [ENV_FILE] [JOB_ID] [TARGET] [SERVICES]\n' "$0" >&2
    exit 64
    ;;
esac
