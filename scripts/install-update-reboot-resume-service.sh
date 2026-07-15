#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
service_path="${2:-/etc/systemd/system/dune-update-reboot-resume.service}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template="$repo_root/config/systemd/dune-update-reboot-resume.service"
env_path="$env_file"
[[ "$env_path" == /* ]] || env_path="$repo_root/$env_path"
[[ -f "$env_path" ]] || { printf 'env file does not exist: %s\n' "$env_path" >&2; exit 1; }

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
sed \
  -e "s#/path/to/DuneAwakeningSelfHost#$repo_root#g" \
  -e "s#^ExecStart=.*#ExecStart=$repo_root/scripts/update-reboot-resume.sh resume $env_path#" \
  "$template" > "$tmp"

install_cmd=(install -m 0644 "$tmp" "$service_path")
[[ -w "$(dirname "$service_path")" ]] || install_cmd=(sudo "${install_cmd[@]}")
"${install_cmd[@]}"
if [[ "$(id -u)" -eq 0 ]]; then sudo_cmd=(); else sudo_cmd=(sudo); fi
"${sudo_cmd[@]}" systemctl daemon-reload
"${sudo_cmd[@]}" systemctl enable "$(basename "$service_path")"
printf 'installed and enabled %s\n' "$service_path"
