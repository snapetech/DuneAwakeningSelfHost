#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/install-rabbitmq-restore-drill-timer.sh [ENV_FILE] [SERVICE_PATH] [TIMER_PATH]

Install and enable the weekly networkless RabbitMQ recovery-rehearsal timer.
Run as the normal DASH operator; the script uses sudo only for system unit files.
USAGE
}

if [[ $# -gt 3 ]]; then usage; exit 2; fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${1:-$repo_root/.env}"
service_path="${2:-/etc/systemd/system/dune-rabbitmq-restore-drill.service}"
timer_path="${3:-/etc/systemd/system/dune-rabbitmq-restore-drill.timer}"
[[ "$env_file" == /* ]] || env_file="$repo_root/$env_file"
[[ -f "$env_file" ]] || { printf 'env file does not exist: %s\n' "$env_file" >&2; exit 1; }
[[ -S /var/run/docker.sock ]] || { printf 'Docker socket is unavailable: /var/run/docker.sock\n' >&2; exit 1; }

env_value() { sed -n "s/^${1}=//p" "$env_file" | tail -1; }
operator="${DUNE_RABBITMQ_RESTORE_DRILL_SERVICE_USER:-${SUDO_USER:-$(id -un)}}"
[[ "$operator" != root ]] || { printf 'RabbitMQ restore-drill service must use a non-root DASH operator\n' >&2; exit 1; }
id "$operator" >/dev/null
operator_group="$(id -gn "$operator")"
socket_group="$(stat -c %G /var/run/docker.sock)"
if ! id -nG "$operator" | tr ' ' '\n' | grep -Fxq "$socket_group"; then
  printf 'operator %s is not a member of Docker socket group %s\n' "$operator" "$socket_group" >&2
  exit 1
fi

image="$(env_value DUNE_RABBITMQ_RESTORE_DRILL_IMAGE)"
if [[ -z "$image" ]]; then
  image_tag="$(env_value DUNE_IMAGE_TAG)"
  image="registry.funcom.com/funcom/self-hosting/seabass-server-rabbitmq:${image_tag:-2036754-0-shipping}"
fi
[[ "$image" =~ ^[A-Za-z0-9][A-Za-z0-9./_:@+-]{0,511}$ ]] || { printf 'invalid RabbitMQ image reference\n' >&2; exit 1; }

receipt_dir="$repo_root/backups/admin-panel/rabbitmq-restore-drills"
install_dir=(install -d -m 0700 -o "$operator" -g "$operator_group" "$receipt_dir")
if [[ ! -w "$(dirname "$receipt_dir")" ]]; then install_dir=(sudo "${install_dir[@]}"); fi
"${install_dir[@]}"

service_template="$repo_root/config/systemd/dune-rabbitmq-restore-drill.service"
timer_template="$repo_root/config/systemd/dune-rabbitmq-restore-drill.timer"
tmp_service="$(mktemp)"
tmp_timer="$(mktemp)"
trap 'rm -f "$tmp_service" "$tmp_timer"' EXIT

sed \
  -e "s#^User=.*#User=$operator#" \
  -e "s#^Group=.*#Group=$operator_group#" \
  -e "s#^SupplementaryGroups=.*#SupplementaryGroups=$socket_group#" \
  -e "s#/path/to/DuneAwakeningSelfHost#$repo_root#g" \
  -e "s#@RABBITMQ_IMAGE@#$image#g" \
  "$service_template" > "$tmp_service"
cp "$timer_template" "$tmp_timer"

install_unit() {
  local source="$1" target="$2"
  if [[ -w "$(dirname "$target")" ]]; then
    install -m 0644 "$source" "$target"
  else
    sudo install -m 0644 "$source" "$target"
  fi
}
install_unit "$tmp_service" "$service_path"
install_unit "$tmp_timer" "$timer_path"

systemctl_cmd=(systemctl)
[[ "$(id -u)" -eq 0 ]] || systemctl_cmd=(sudo systemctl)
"${systemctl_cmd[@]}" daemon-reload
"${systemctl_cmd[@]}" enable --now "$(basename "$timer_path")"
"${systemctl_cmd[@]}" list-timers "$(basename "$timer_path")" --all --no-pager
printf 'installed and enabled %s with service %s as %s\n' "$timer_path" "$service_path" "$operator"
