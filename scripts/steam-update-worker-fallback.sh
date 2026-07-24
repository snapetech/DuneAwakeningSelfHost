#!/usr/bin/env bash
set -euo pipefail
env_file="${1:-.env}"
env_value() { local key="$1"; awk -F= -v key="$key" '$0 ~ "^[[:space:]]*" key "=" {sub(/^[^=]*=/, ""); gsub(/^['"'"']|['"'"']$/, ""); print; exit}' "$env_file"; }
value() { local key="$1" v; v="${!key-}"; [[ -n "$v" ]] || v="$(env_value "$key")"; printf '%s' "$v"; }
[[ "$(hostname -s)" == "kspls0" ]] || { echo 'fail: worker fallback must run on kspls0' >&2; exit 64; }
case "$(value DUNE_STEAM_UPDATE_WORKER_ENABLED)" in 1|true|yes|on) ;; *) echo 'worker fallback disabled'; exit 2 ;; esac
worker_host="$(value DUNE_STEAM_UPDATE_WORKER_HOST)"; worker_host="${worker_host:-kspld0}"
worker_dir="$(value DUNE_STEAM_UPDATE_WORKER_DIR)"; worker_dir="${worker_dir:-/home/keith/dune-steamcmd-worker}"
steam_dir="$(value DUNE_STEAM_SERVER_DIR)"
login="$(value DUNE_OWNED_STEAM_LOGIN)"; login="${login:-$(value DUNE_STEAM_LOGIN)}"; login="${login:-ksnape}"
app_id="$(value DUNE_STEAM_APP_ID)"; app_id="${app_id:-4754530}"
ssh_target="${DUNE_STEAM_UPDATE_WORKER_SSH_USER:-keith}@${worker_host}"
worker_install="/work${worker_dir#/home/keith}"
echo "SteamCMD local acquisition failed; using worker ${ssh_target}"
ssh "$ssh_target" "steamcmd +@sSteamCmdForcePlatformType linux +force_install_dir '$worker_install' +login '$login' +app_update 1070560 validate +app_update 1391110 validate +app_update '$app_id' validate +quit"
mkdir -p "$steam_dir/images/battlegroup" "$steam_dir/steamapps"
rsync -a "$ssh_target:$worker_dir/images/battlegroup/" "$steam_dir/images/battlegroup/"
rsync -a "$ssh_target:$worker_dir/steamapps/appmanifest_${app_id}.acf" "$steam_dir/steamapps/appmanifest_${app_id}.acf"
manifest="$steam_dir/steamapps/appmanifest_${app_id}.acf"
buildid="$(awk '$1 == "\"buildid\"" {gsub(/"/, "", $2); print $2; exit}' "$manifest")"
[[ "$buildid" =~ ^[0-9]+$ ]] || { echo 'fail: worker manifest has no valid buildid' >&2; exit 1; }
for image in server-rabbitmq.tar server-text-router.tar server-bg-director.tar server-gateway.tar server-db-utils.tar server.tar; do
  [[ -s "$steam_dir/images/battlegroup/$image" ]] || { echo "fail: worker package missing $image" >&2; exit 1; }
done
echo "worker package staged: app=${app_id} buildid=${buildid}"
