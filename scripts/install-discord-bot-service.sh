#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${1:-$root/.env}"
[[ "$env_file" == /* ]] || env_file="$root/$env_file"
[[ -f "$env_file" ]] || { printf 'env file does not exist: %s\n' "$env_file" >&2; exit 1; }

read_env() { sed -n "s/^${1}=//p" "$env_file" | tail -1; }
allowed_host="${DUNE_DISCORD_ALLOWED_HOST:-$(read_env DUNE_DISCORD_ALLOWED_HOST)}"
[[ -n "$allowed_host" ]] || {
  printf 'DUNE_DISCORD_ALLOWED_HOST must name the exact host allowed to install the bot service\n' >&2
  exit 77
}
current_host="$(hostname -s)"
[[ "$current_host" == "$allowed_host" ]] || {
  printf 'refusing Discord bot service install: hostname=%s required=%s\n' "$current_host" "$allowed_host" >&2
  exit 77
}

command -v systemctl >/dev/null 2>&1 || { printf 'systemctl is required\n' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { printf 'python3 is required\n' >&2; exit 1; }
install -d -m 700 "$root/backups/discord-bot"

unit="$(mktemp)"
trap 'rm -f "$unit"' EXIT
sed \
  -e "s#User=keith#User=$(id -un)#" \
  -e "s#Group=keith#Group=$(id -gn)#" \
  -e "s#/opt/DuneAwakeningSelfHost#$root#g" \
  -e "s#Environment=DUNE_DISCORD_BOT_ENV_FILE=.*#Environment=DUNE_DISCORD_BOT_ENV_FILE=$env_file#" \
  "$root/config/systemd/dune-discord-bot.service" > "$unit"

sudo install -m 644 "$unit" /etc/systemd/system/dune-discord-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now dune-discord-bot.service
sleep 1
sudo systemctl --no-pager --full status dune-discord-bot.service
"$root/scripts/discord-bot.py" --env-file "$env_file" --check || status=$?
status="${status:-0}"
if [[ "$status" == 3 ]]; then
  printf 'Discord bot is loaded and waiting for application/guild/bot/adapter credentials.\n'
elif [[ "$status" -ne 0 ]]; then
  exit "$status"
else
  printf 'Discord bot service is loaded with a complete credential set.\n'
fi
