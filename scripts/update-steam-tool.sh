#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/update-steam-tool.sh [env-file]

Runs SteamCMD app_update for the official Dune: Awakening Self-Hosted Server
tool before DASH checks and loads the shipped Docker image tarballs.

Environment:
  DUNE_RESTART_STEAMCMD_UPDATE          Enable this script. Default: true.
  DUNE_RESTART_STEAMCMD_REQUIRED        Fail if SteamCMD cannot run. Default: false.
  DUNE_STEAM_APP_ID                     Steam app id. Default: 4754530.
  DUNE_STEAM_LOGIN                      Steam login user. Default: anonymous.
  DUNE_STEAM_PASSWORD                   Optional Steam password.
  DUNE_STEAMCMD_COMMAND                 SteamCMD executable. Default: steamcmd.
  DUNE_STEAMCMD_VALIDATE                Add validate to app_update. Default: true.
  DUNE_STEAMCMD_TIMEOUT_SECONDS         Timeout wrapper if timeout exists. Default: 1800.
USAGE
}

env_file="${1:-.env}"
case "$env_file" in
  -h|--help)
    usage
    exit 0
    ;;
esac

if [[ ! -f "$env_file" ]]; then
  printf 'fail: env file not found: %s\n' "$env_file" >&2
  exit 1
fi

get_env() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 ~ "^[[:space:]]*" key "=" {
      sub(/^[^=]*=/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$env_file" 2>/dev/null
}

env_or_file() {
  local key="$1"
  local value="${!key:-}"
  if [[ -n "$value" ]]; then
    printf '%s\n' "$value"
  else
    get_env "$key"
  fi
}

enabled="$(env_or_file DUNE_RESTART_STEAMCMD_UPDATE)"
case "${enabled:-true}" in
  1|true|yes|on) ;;
  *)
    printf 'SteamCMD package update disabled by DUNE_RESTART_STEAMCMD_UPDATE\n'
    exit 0
    ;;
esac

required="$(env_or_file DUNE_RESTART_STEAMCMD_REQUIRED)"
steam_dir="$(env_or_file DUNE_STEAM_SERVER_DIR)"
app_id="$(env_or_file DUNE_STEAM_APP_ID)"
login="$(env_or_file DUNE_STEAM_LOGIN)"
password="$(env_or_file DUNE_STEAM_PASSWORD)"
steamcmd_command="$(env_or_file DUNE_STEAMCMD_COMMAND)"
validate="$(env_or_file DUNE_STEAMCMD_VALIDATE)"
timeout_seconds="$(env_or_file DUNE_STEAMCMD_TIMEOUT_SECONDS)"

required="${required:-false}"
app_id="${app_id:-4754530}"
login="${login:-anonymous}"
steamcmd_command="${steamcmd_command:-steamcmd}"
validate="${validate:-true}"
timeout_seconds="${timeout_seconds:-1800}"

if [[ -z "$steam_dir" ]]; then
  printf 'fail: DUNE_STEAM_SERVER_DIR is empty\n' >&2
  exit 1
fi

if [[ ! -d "$steam_dir" ]]; then
  printf 'fail: DUNE_STEAM_SERVER_DIR does not exist: %s\n' "$steam_dir" >&2
  exit 1
fi

if ! command -v "$steamcmd_command" >/dev/null 2>&1; then
  message="SteamCMD command not found: $steamcmd_command"
  case "$required" in
    1|true|yes|on)
      printf 'fail: %s\n' "$message" >&2
      exit 127
      ;;
    *)
      printf 'warn: %s; continuing without forcing Steam package update\n' "$message" >&2
      exit 0
      ;;
  esac
fi

login_args=(+login "$login")
if [[ "$login" != "anonymous" && -n "$password" ]]; then
  login_args=(+login "$login" "$password")
fi

app_update_args=(+app_update "$app_id")
case "$validate" in
  1|true|yes|on) app_update_args+=(validate) ;;
esac

cmd=(
  "$steamcmd_command"
  +force_install_dir "$steam_dir"
  "${login_args[@]}"
  "${app_update_args[@]}"
  +quit
)

printf 'Running SteamCMD app_update for app %s into %s as %s\n' "$app_id" "$steam_dir" "$login"
if command -v timeout >/dev/null 2>&1; then
  timeout "$timeout_seconds" "${cmd[@]}"
else
  "${cmd[@]}"
fi
