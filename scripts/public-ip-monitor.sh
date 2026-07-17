#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${1:-${ENV_FILE:-$repo_root/.env}}"
command="${2:-check}"
if [[ "$env_file" != /* ]]; then env_file="$repo_root/$env_file"; fi
state_dir="${DUNE_PUBLIC_IP_MONITOR_STATE_DIR:-$repo_root/backups/admin-panel}"
state_file="$state_dir/public-ip-monitor.state"
lock_file="$state_dir/public-ip-monitor.lock"

read_env() {
  local key="$1"
  sed -nE "s/^${key}=//p" "$env_file" 2>/dev/null | tail -n 1
}

bool_true() {
  case "${1,,}" in 1|true|yes|on) return 0 ;; *) return 1 ;; esac
}

valid_ipv4() {
  local ip="$1" part
  [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  IFS=. read -r -a parts <<< "$ip"
  for part in "${parts[@]}"; do
    [[ "$part" =~ ^[0-9]{1,3}$ ]] && ((10#$part <= 255)) || return 1
  done
}

write_file_value() {
  local file="$1" key="$2" value="$3" tmp
  tmp="$(mktemp "$(dirname "$file")/.public-ip-env.XXXXXX")"
  awk -F= -v key="$key" -v value="$value" '
    BEGIN { found=0 }
    $1 == key { print key "=" value; found=1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$file" > "$tmp"
  chmod --reference="$file" "$tmp" 2>/dev/null || chmod 600 "$tmp"
  mv "$tmp" "$file"
}

write_env_value() { write_file_value "$env_file" "$1" "$2"; }

detect_public_ip() {
  local override="${DUNE_PUBLIC_IP_MONITOR_DETECTED_IP:-$(read_env DUNE_PUBLIC_IP_MONITOR_DETECTED_IP)}" ip=""
  if [[ -n "$override" ]]; then printf '%s' "$override"; return; fi
  for url in https://api.ipify.org https://ifconfig.me/ip; do
    if command -v curl >/dev/null 2>&1; then
      ip="$(curl -4fsS --connect-timeout 4 --max-time 8 "$url" 2>/dev/null | tr -d '[:space:]' || true)"
      valid_ipv4 "$ip" && { printf '%s' "$ip"; return; }
    fi
  done
}

write_state() {
  local status="$1" detected="$2" configured="$3" detail="${4:-}" tmp
  mkdir -p "$state_dir"
  tmp="$(mktemp "$state_dir/.public-ip-state.XXXXXX")"
  {
    printf 'checked_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'status=%s\n' "$status"
    printf 'detected_ip=%s\n' "$detected"
    printf 'configured_ip=%s\n' "$configured"
    printf 'detail=%s\n' "$detail"
  } > "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$state_file"
}

status() {
  printf 'enabled=%s\n' "$(read_env DUNE_PUBLIC_IP_MONITOR_ENABLED)"
  printf 'allowed_host=%s\n' "$(read_env DUNE_PUBLIC_IP_MONITOR_ALLOWED_HOST)"
  printf 'external_address=%s\n' "$(read_env EXTERNAL_ADDRESS)"
  printf 'interval_minutes=%s\n' "$(read_env DUNE_PUBLIC_IP_MONITOR_INTERVAL_MINUTES)"
  [[ -f "$state_file" ]] && sed -n '1,20p' "$state_file"
}

restart_farm() {
  cd "$repo_root"
  export ENV_FILE="$env_file" DUNE_RESTART_TARGET=all DUNE_RESTART_ACTION=restart DUNE_RESTART_PHASE=restart
  "$repo_root/scripts/restart-target.sh" all
}

check_now() {
  local enabled allowed_host hostname_now configured detected rmq_host stamp backup dry_run pending_status staged_env staged_tls tls_backup
  enabled="$(read_env DUNE_PUBLIC_IP_MONITOR_ENABLED)"
  if ! bool_true "$enabled"; then
    write_state disabled "" "$(read_env EXTERNAL_ADDRESS)" "monitor disabled"
    printf 'public IP monitor is disabled\n'
    return 0
  fi
  allowed_host="$(read_env DUNE_PUBLIC_IP_MONITOR_ALLOWED_HOST)"
  hostname_now="$(hostname -s)"
  if [[ -z "$allowed_host" || "$allowed_host" != "$hostname_now" ]]; then
    write_state refused "" "$(read_env EXTERNAL_ADDRESS)" "allowed host mismatch"
    printf 'refusing public IP mutation: hostname=%s allowed_host=%s\n' "$hostname_now" "${allowed_host:-unset}" >&2
    return 77
  fi
  configured="$(read_env EXTERNAL_ADDRESS)"
  if ! valid_ipv4 "$configured"; then
    write_state skipped "" "$configured" "EXTERNAL_ADDRESS is not an IPv4 literal"
    printf 'EXTERNAL_ADDRESS=%s is not an IPv4 literal; DNS names do not need rewriting\n' "$configured"
    return 0
  fi
  detected="$(detect_public_ip)"
  if ! valid_ipv4 "$detected"; then
    write_state failed "$detected" "$configured" "public IPv4 detection failed"
    printf 'could not detect a valid public IPv4\n' >&2
    return 69
  fi
  if [[ "$detected" == "$configured" ]]; then
    pending_status="$(sed -nE 's/^status=//p' "$state_file" 2>/dev/null | tail -1 || true)"
    if [[ "$pending_status" == "restarting" ]]; then
      printf 'retrying the incomplete farm restart for public IP %s\n' "$configured"
      restart_farm
      write_state restarted "$detected" "$configured" "restart retry completed"
      return 0
    fi
    write_state current "$detected" "$configured" "no change"
    printf 'public IP unchanged: %s\n' "$configured"
    return 0
  fi
  dry_run="$(read_env DUNE_PUBLIC_IP_MONITOR_DRY_RUN)"
  if bool_true "$dry_run"; then
    write_state dry-run "$detected" "$configured" "change planned"
    printf 'dry-run: would update EXTERNAL_ADDRESS %s -> %s and restart the farm\n' "$configured" "$detected"
    return 0
  fi

  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup="$state_dir/public-ip-change-$stamp.env"
  install -m 600 "$env_file" "$backup"
  staged_env="$state_dir/.public-ip-$stamp.env"
  install -m 600 "$env_file" "$staged_env"
  write_file_value "$staged_env" EXTERNAL_ADDRESS "$detected"
  DUNE_ANNOUNCE_MESSAGE="Server address changed; the farm is restarting now." \
    DUNE_ANNOUNCE_JOB_ID="public-ip-$stamp" "$repo_root/scripts/announce.sh" || true
  rmq_host="$(read_env GAME_RMQ_PUBLIC_HOST)"
  if [[ -z "$rmq_host" || "$rmq_host" == "$configured" ]]; then
    write_file_value "$staged_env" GAME_RMQ_PUBLIC_HOST "$detected"
    staged_tls="$state_dir/.rabbitmq-tls-public-ip-$stamp"
    mkdir -m 700 "$staged_tls"
    RABBITMQ_TLS_DIR="$staged_tls" "$repo_root/scripts/generate-rabbitmq-cert.sh" "$staged_env" --force
    RABBITMQ_CERT_PATH="$staged_tls/server.crt" "$repo_root/scripts/check-rabbitmq-cert-sans.sh" "$staged_env"
    if [[ -d "$repo_root/config/tls/rabbitmq" ]]; then
      tls_backup="$state_dir/rabbitmq-tls-before-public-ip-$stamp"
      cp -a "$repo_root/config/tls/rabbitmq" "$tls_backup"
    fi
    install -d -m 700 "$repo_root/config/tls/rabbitmq"
    cp -a "$staged_tls/." "$repo_root/config/tls/rabbitmq/"
  fi
  write_env_value EXTERNAL_ADDRESS "$detected"
  if [[ -z "$rmq_host" || "$rmq_host" == "$configured" ]]; then write_env_value GAME_RMQ_PUBLIC_HOST "$detected"; fi
  rm -f "$staged_env"
  [[ -z "${staged_tls:-}" ]] || rm -rf "$staged_tls"
  write_state restarting "$detected" "$configured" "backup=$backup"
  restart_farm
  write_state restarted "$detected" "$detected" "backup=$backup"
}

mkdir -p "$state_dir"
exec 9>"$lock_file"
flock -n 9 || { printf 'public IP monitor is already running\n' >&2; exit 75; }
case "$command" in
  check) check_now ;;
  status) status ;;
  *) printf 'Usage: %s [ENV_FILE] <check|status>\n' "$0" >&2; exit 2 ;;
esac
