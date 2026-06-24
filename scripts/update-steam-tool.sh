#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/update-steam-tool.sh [env-file]

Refreshes or waits for the official Dune: Awakening Self-Hosted Server Steam
tool before DASH checks and loads the shipped Docker image tarballs.

Environment:
  DUNE_RESTART_STEAM_UPDATE_MODE        auto, client, steamcmd, or none. Default: auto.
  DUNE_RESTART_STEAM_CLIENT_TRIGGER     Send steam://validate/<appid>. Default: true.
  DUNE_RESTART_STEAM_CLIENT_WAIT_SECONDS
                                        Wait for local Steam package stability. Default: 900.
  DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS
                                        Minimum wait after client trigger. Default: 30.
  DUNE_STEAM_CLIENT_COMMAND             Steam client executable. Default: steam.
  DUNE_RESTART_STEAMCMD_UPDATE          Legacy SteamCMD enable flag. Default: true.
  DUNE_RESTART_STEAMCMD_REQUIRED        Fail if SteamCMD cannot run or update fails. Default: true.
  DUNE_STEAM_APP_ID                     Steam app id. Default: 4754530.
  DUNE_STEAM_FORCE_PLATFORM             SteamCMD platform override. Default: linux.
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

steam_update_mode="$(env_or_file DUNE_RESTART_STEAM_UPDATE_MODE)"
client_trigger="$(env_or_file DUNE_RESTART_STEAM_CLIENT_TRIGGER)"
client_wait_seconds="$(env_or_file DUNE_RESTART_STEAM_CLIENT_WAIT_SECONDS)"
client_min_wait_seconds="$(env_or_file DUNE_RESTART_STEAM_CLIENT_MIN_WAIT_SECONDS)"
steam_client_command="$(env_or_file DUNE_STEAM_CLIENT_COMMAND)"
steam_dir="$(env_or_file DUNE_STEAM_SERVER_DIR)"
app_id="$(env_or_file DUNE_STEAM_APP_ID)"
force_platform="$(env_or_file DUNE_STEAM_FORCE_PLATFORM)"

steam_update_mode="${steam_update_mode:-auto}"
client_trigger="${client_trigger:-true}"
client_wait_seconds="${client_wait_seconds:-900}"
client_min_wait_seconds="${client_min_wait_seconds:-30}"
steam_client_command="${steam_client_command:-steam}"
app_id="${app_id:-4754530}"
force_platform="${force_platform:-linux}"

case "$steam_update_mode" in
  auto|client|steamcmd|none) ;;
  *)
    printf 'fail: invalid DUNE_RESTART_STEAM_UPDATE_MODE: %s\n' "$steam_update_mode" >&2
    exit 64
    ;;
esac

if [[ "$steam_update_mode" == "none" ]]; then
  printf 'Steam package refresh disabled by DUNE_RESTART_STEAM_UPDATE_MODE=none\n'
  exit 0
fi

if [[ -z "$steam_dir" ]]; then
  printf 'fail: DUNE_STEAM_SERVER_DIR is empty\n' >&2
  exit 1
fi

if [[ ! -d "$steam_dir" ]]; then
  printf 'fail: DUNE_STEAM_SERVER_DIR does not exist: %s\n' "$steam_dir" >&2
  exit 1
fi

steam_client_running() {
  pgrep -u "$(id -u)" -f '/Steam/.*/steam|/steam( |$)' >/dev/null 2>&1
}

steam_appmanifest() {
  local dir="$steam_dir"
  while [[ "$dir" != "/" && -n "$dir" ]]; do
    if [[ "$(basename "$dir")" == "steamapps" ]]; then
      printf '%s/appmanifest_%s.acf\n' "$dir" "$app_id"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  if [[ "$steam_dir" == */steamapps/common/* ]]; then
    printf '%s/appmanifest_%s.acf\n' "${steam_dir%%/common/*}" "$app_id"
  fi
}

manifest_value() {
  local file="$1"
  local key="$2"
  awk -v key="$key" '$1 == "\"" key "\"" {gsub(/"/, "", $2); print $2; exit}' "$file" 2>/dev/null
}

run_steam_client_refresh() {
  local manifest state_flags bytes_to_download bytes_downloaded bytes_to_stage bytes_staged start now elapsed
  manifest="$(steam_appmanifest)"
  case "$client_trigger" in
    1|true|yes|on)
      if command -v "$steam_client_command" >/dev/null 2>&1; then
        printf 'Requesting Steam client validation for app %s\n' "$app_id"
        "$steam_client_command" "steam://validate/$app_id" >/dev/null 2>&1 || true
      else
        printf 'warn: Steam client command not found: %s\n' "$steam_client_command" >&2
      fi
      ;;
  esac

  start="$(date +%s)"
  while true; do
    if [[ -f "$manifest" ]]; then
      state_flags="$(manifest_value "$manifest" StateFlags)"
      bytes_to_download="$(manifest_value "$manifest" BytesToDownload)"
      bytes_downloaded="$(manifest_value "$manifest" BytesDownloaded)"
      bytes_to_stage="$(manifest_value "$manifest" BytesToStage)"
      bytes_staged="$(manifest_value "$manifest" BytesStaged)"
      now="$(date +%s)"
      elapsed=$((now - start))
      if [[ "$elapsed" -ge "$client_min_wait_seconds" &&
            "${state_flags:-4}" == "4" &&
            "${bytes_to_download:-0}" == "${bytes_downloaded:-0}" &&
            "${bytes_to_stage:-0}" == "${bytes_staged:-0}" ]]; then
        printf 'Steam client package appears stable for app %s after %ss\n' "$app_id" "$elapsed"
        return 0
      fi
      if [[ "$elapsed" -ge "$client_wait_seconds" ]]; then
        printf 'warn: timed out waiting for Steam client package stability for app %s; continuing with local package state\n' "$app_id" >&2
        return 0
      fi
    else
      now="$(date +%s)"
      elapsed=$((now - start))
      if [[ "$elapsed" -ge "$client_wait_seconds" ]]; then
        printf 'warn: Steam appmanifest not found for app %s: %s\n' "$app_id" "$manifest" >&2
        return 0
      fi
    fi
    sleep 5
  done
}

if [[ "$steam_update_mode" != "steamcmd" ]] && steam_client_running; then
  run_steam_client_refresh
  exit 0
fi

if [[ "$steam_update_mode" == "client" ]]; then
  printf 'warn: DUNE_RESTART_STEAM_UPDATE_MODE=client but no running Steam client was detected\n' >&2
  exit 0
fi

enabled="$(env_or_file DUNE_RESTART_STEAMCMD_UPDATE)"
case "${enabled:-true}" in
  1|true|yes|on) ;;
  *)
    printf 'SteamCMD package update disabled by DUNE_RESTART_STEAMCMD_UPDATE\n'
    exit 0
    ;;
esac

required="$(env_or_file DUNE_RESTART_STEAMCMD_REQUIRED)"
login="$(env_or_file DUNE_STEAM_LOGIN)"
password="$(env_or_file DUNE_STEAM_PASSWORD)"
steamcmd_command="$(env_or_file DUNE_STEAMCMD_COMMAND)"
validate="$(env_or_file DUNE_STEAMCMD_VALIDATE)"
timeout_seconds="$(env_or_file DUNE_STEAMCMD_TIMEOUT_SECONDS)"

required="${required:-true}"
login="${login:-anonymous}"
steamcmd_command="${steamcmd_command:-steamcmd}"
validate="${validate:-true}"
timeout_seconds="${timeout_seconds:-1800}"

if ! command -v "$steamcmd_command" >/dev/null 2>&1; then
  if [[ "$steamcmd_command" == "steamcmd" ]] && command -v steamcmd.sh >/dev/null 2>&1; then
    steamcmd_command="steamcmd.sh"
  elif [[ "$steamcmd_command" == "steamcmd" && -x /home/steam/steamcmd/steamcmd.sh ]]; then
    steamcmd_command="/home/steam/steamcmd/steamcmd.sh"
  fi
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
  "+@sSteamCmdForcePlatformType" "$force_platform"
  +force_install_dir "$steam_dir"
  "${login_args[@]}"
  "${app_update_args[@]}"
  +quit
)

printf 'Running SteamCMD app_update for app %s into %s as %s\n' "$app_id" "$steam_dir" "$login"
set +e
if command -v timeout >/dev/null 2>&1; then
  timeout "$timeout_seconds" "${cmd[@]}"
  rc=$?
else
  "${cmd[@]}"
  rc=$?
fi
set -e

if [[ "$rc" -eq 0 ]]; then
  exit 0
fi

case "$required" in
  1|true|yes|on)
    printf 'fail: SteamCMD app_update failed with exit code %s\n' "$rc" >&2
    exit "$rc"
    ;;
  *)
    printf 'warn: SteamCMD app_update failed with exit code %s; continuing with the package already on disk\n' "$rc" >&2
    exit 0
    ;;
esac
