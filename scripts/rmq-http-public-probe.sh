#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: scripts/rmq-http-public-probe.sh enable|disable|status|install-systemd|uninstall-systemd [ENV_FILE]

Temporarily exposes the game RabbitMQ HTTP/management port advertised to FLS.
This is for server-browser ping investigation only. It creates transient
systemd socat proxies from DUNE_CURRENT_LAN_IP:GAME_RMQ_PUBLIC_HTTP_PORT and,
when locally assigned, EXTERNAL_ADDRESS:GAME_RMQ_PUBLIC_HTTP_PORT to the local
Docker bind at 127.0.0.1:GAME_RMQ_PUBLIC_HTTP_PORT, and adds/removes the
matching AsusWRT DuneRMQHTTP port forward.

Set CONFIRM_RMQ_HTTP_PUBLIC_PROBE=yes for enable/disable mutations.
USAGE
}

action="${1:-}"
env_file="${2:-.env}"
service_name="${DUNE_RMQ_HTTP_PUBLIC_SERVICE:-dune-rmq-http-public-proxy.service}"
public_service_name="${DUNE_RMQ_HTTP_PUBLIC_IP_SERVICE:-dune-rmq-http-public-ip-proxy.service}"
rule_name="${DUNE_RMQ_HTTP_PUBLIC_RULE_NAME:-DuneRMQHTTP}"
backup_dir="${DUNE_ROUTER_BACKUP_DIR:-backups/router-inspection}"

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

case "$action" in
  enable|disable|status|install-systemd|uninstall-systemd) ;;
  -h|--help|"")
    usage
    exit 2
    ;;
  *)
    usage
    exit 2
    ;;
esac

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

host="$(hostname)"
if [[ "$action" != "status" && "$host" != "kspls0" && "${DUNE_ALLOW_NON_PROD_RMQ_HTTP_PUBLIC_PROBE:-}" != "true" ]]; then
  printf 'refusing RMQ HTTP public probe mutation on host %s; run on kspls0\n' "$host" >&2
  exit 1
fi

router="${DUNE_FAILOVER_ROUTER_SSH:-${DUNE_ROUTER_SSH:-$(read_env DUNE_FAILOVER_ROUTER_SSH)}}"
target_ip="${DUNE_CURRENT_LAN_IP:-$(read_env DUNE_CURRENT_LAN_IP)}"
external_address="${EXTERNAL_ADDRESS:-$(read_env EXTERNAL_ADDRESS)}"
port="${GAME_RMQ_PUBLIC_HTTP_PORT:-$(read_env GAME_RMQ_PUBLIC_HTTP_PORT)}"
port="${port:-15673}"

if [[ -z "$target_ip" || -z "$port" ]]; then
  printf 'DUNE_CURRENT_LAN_IP and GAME_RMQ_PUBLIC_HTTP_PORT are required\n' >&2
  exit 1
fi

if [[ "$action" != "status" && "$action" != "install-systemd" && "$action" != "uninstall-systemd" && "${CONFIRM_RMQ_HTTP_PUBLIC_PROBE:-}" != "yes" ]]; then
  printf 'refusing %s without CONFIRM_RMQ_HTTP_PUBLIC_PROBE=yes\n' "$action" >&2
  exit 1
fi

backup_router() {
  [[ "${DUNE_RMQ_HTTP_PUBLIC_SKIP_ROUTER:-}" != "true" ]] || return 0
  [[ -n "$router" ]] || return 0
  mkdir -p "$backup_dir"
  local stamp backup_file
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_file="${backup_dir}/asuswrt-${stamp}-rmq-http-public-probe-${action}.txt"
  {
    printf 'router=%s\n' "$router"
    printf 'action=%s\n' "$action"
    printf 'target_ip=%s\n' "$target_ip"
    printf 'port=%s\n' "$port"
    printf 'vts_rulelist=%s\n' "$(ssh "$router" 'nvram get vts_rulelist')"
    ssh "$router" 'nvram get vts_enable_x; nvram get nat_redirect_enable; nvram get game_vts_rulelist' 2>/dev/null || true
  } > "$backup_file"
  printf 'router backup written: %s\n' "$backup_file"
}

systemctl_cmd() {
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl "$@"
  else
    sudo systemctl "$@"
  fi
}

systemd_run_cmd() {
  if [[ "$(id -u)" -eq 0 ]]; then
    systemd-run "$@"
  else
    sudo systemd-run "$@"
  fi
}

systemctl_daemon_reload() {
  systemctl_cmd daemon-reload
}

write_systemd_unit() {
  local script_path env_path repo_root unit_path
  script_path="$(readlink -f "$0")"
  env_path="$(readlink -f "$env_file")"
  repo_root="$(dirname "$(dirname "$script_path")")"
  unit_path="/etc/systemd/system/dune-rmq-http-public-probe.service"
  if [[ "$(id -u)" -eq 0 ]]; then
    cat > "$unit_path" <<EOF
[Unit]
Description=Dune RMQ HTTP public probe exposure
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$repo_root
ExecStart=/usr/bin/env CONFIRM_RMQ_HTTP_PUBLIC_PROBE=yes DUNE_RMQ_HTTP_PUBLIC_SKIP_ROUTER=true "$script_path" enable "$env_path"
ExecStop=/usr/bin/env CONFIRM_RMQ_HTTP_PUBLIC_PROBE=yes DUNE_RMQ_HTTP_PUBLIC_SKIP_ROUTER=true "$script_path" disable "$env_path"

[Install]
WantedBy=multi-user.target
EOF
  else
    sudo tee "$unit_path" >/dev/null <<EOF
[Unit]
Description=Dune RMQ HTTP public probe exposure
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$repo_root
ExecStart=/usr/bin/env CONFIRM_RMQ_HTTP_PUBLIC_PROBE=yes DUNE_RMQ_HTTP_PUBLIC_SKIP_ROUTER=true "$script_path" enable "$env_path"
ExecStop=/usr/bin/env CONFIRM_RMQ_HTTP_PUBLIC_PROBE=yes DUNE_RMQ_HTTP_PUBLIC_SKIP_ROUTER=true "$script_path" disable "$env_path"

[Install]
WantedBy=multi-user.target
EOF
  fi
  systemctl_daemon_reload
  systemctl_cmd enable dune-rmq-http-public-probe.service
  printf 'installed and enabled %s\n' "$unit_path"
}

remove_systemd_unit() {
  systemctl_cmd disable --now dune-rmq-http-public-probe.service >/dev/null 2>&1 || true
  if [[ "$(id -u)" -eq 0 ]]; then
    rm -f /etc/systemd/system/dune-rmq-http-public-probe.service
  else
    sudo rm -f /etc/systemd/system/dune-rmq-http-public-probe.service
  fi
  systemctl_daemon_reload
  printf 'removed dune-rmq-http-public-probe.service\n'
}

iptables_cmd() {
  if [[ "$(id -u)" -eq 0 ]]; then
    iptables "$@"
  else
    sudo iptables "$@"
  fi
}

game_rmq_container_ip() {
  local runtime="${CONTAINER_RUNTIME:-docker}" container="${DUNE_GAME_RMQ_CONTAINER:-dune_server-game-rmq-1}"
  "$runtime" inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$container" 2>/dev/null
}

host_has_address() {
  local address="$1"
  [[ -n "$address" ]] || return 1
  ip -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$address"
}

stop_proxy_unit() {
  local unit="$1"
  systemctl_cmd stop "$unit" >/dev/null 2>&1 || true
  systemctl_cmd reset-failed "$unit" >/dev/null 2>&1 || true
}

start_proxy_unit() {
  local unit="$1" bind_address="$2"
  stop_proxy_unit "$unit"
  systemd_run_cmd \
    --unit="$unit" \
    --description="/usr/bin/socat TCP-LISTEN:${port},bind=${bind_address},fork,reuseaddr TCP:127.0.0.1:${port}" \
    /usr/bin/socat "TCP-LISTEN:${port},bind=${bind_address},fork,reuseaddr" "TCP:127.0.0.1:${port}" >/dev/null
}

enable_dnat_rule() {
  local game_rmq_ip
  game_rmq_ip="$(game_rmq_container_ip)"
  if [[ -z "$game_rmq_ip" ]]; then
    printf 'WARN game-rmq container IP not found; DNAT rule skipped\n' >&2
    return 0
  fi
  iptables_cmd -t nat -C PREROUTING ! -i br-3286b5d961b4 -p tcp --dport "$port" -j DNAT --to-destination "${game_rmq_ip}:15672" 2>/dev/null \
    || iptables_cmd -t nat -I PREROUTING 1 ! -i br-3286b5d961b4 -p tcp --dport "$port" -j DNAT --to-destination "${game_rmq_ip}:15672"
}

disable_dnat_rule() {
  local game_rmq_ip
  game_rmq_ip="$(game_rmq_container_ip)"
  if [[ -z "$game_rmq_ip" ]]; then
    return 0
  fi
  while iptables_cmd -t nat -C PREROUTING ! -i br-3286b5d961b4 -p tcp --dport "$port" -j DNAT --to-destination "${game_rmq_ip}:15672" 2>/dev/null; do
    iptables_cmd -t nat -D PREROUTING ! -i br-3286b5d961b4 -p tcp --dport "$port" -j DNAT --to-destination "${game_rmq_ip}:15672"
  done
}

router_set_rule() {
  [[ "${DUNE_RMQ_HTTP_PUBLIC_SKIP_ROUTER:-}" != "true" ]] || {
    printf 'router rule skipped by DUNE_RMQ_HTTP_PUBLIC_SKIP_ROUTER=true\n'
    return 0
  }
  [[ -n "$router" ]] || {
    printf 'WARN DUNE_FAILOVER_ROUTER_SSH is unset; router rule skipped\n' >&2
    return 0
  }
  local current new rule
  current="$(ssh "$router" 'nvram get vts_rulelist')"
  rule="<${rule_name}>${port}>${target_ip}>${port}>TCP>"
  new="$(printf '%s' "$current" | sed -E "s#<${rule_name}>[0-9]+>[^>]+>[0-9]+>TCP>##g")"
  if [[ "$action" == "enable" ]]; then
    new="${new}${rule}"
  fi
  ssh "$router" "nvram set vts_rulelist='$new'; nvram commit; service restart_firewall"
  printf 'router vts_rulelist now:\n'
  ssh "$router" 'nvram get vts_rulelist'
}

case "$action" in
  enable)
    command -v socat >/dev/null || {
      printf 'socat is required on the host\n' >&2
      exit 1
    }
    backup_router
    start_proxy_unit "$service_name" "$target_ip"
    if host_has_address "$external_address" && [[ "$external_address" != "$target_ip" ]]; then
      start_proxy_unit "$public_service_name" "$external_address"
    else
      stop_proxy_unit "$public_service_name"
    fi
    enable_dnat_rule
    router_set_rule
    ;;
  disable)
    backup_router
    disable_dnat_rule
    stop_proxy_unit "$service_name"
    stop_proxy_unit "$public_service_name"
    router_set_rule
    ;;
  status)
    systemctl status dune-rmq-http-public-probe.service --no-pager -l || true
    printf '\n== transient proxy units ==\n'
    systemctl status "$service_name" --no-pager -l || true
    if host_has_address "$external_address"; then
      systemctl status "$public_service_name" --no-pager -l || true
    fi
    printf '\n== host listener ==\n'
    ss -ltnp 2>/dev/null | rg "(:|\\*)${port}\\b" || true
    printf '\n== host DNAT ==\n'
    iptables_cmd -t nat -S PREROUTING 2>/dev/null | rg "dport ${port}|--dport ${port}" || true
    if [[ -n "$router" ]]; then
      printf '\n== router rule ==\n'
      ssh "$router" 'nvram get vts_rulelist' | tr '<' '\n' | rg "^${rule_name}>|^DuneRMQ>" || true
    fi
    ;;
  install-systemd)
    write_systemd_unit
    systemctl_cmd restart dune-rmq-http-public-probe.service
    ;;
  uninstall-systemd)
    remove_systemd_unit
    ;;
esac
