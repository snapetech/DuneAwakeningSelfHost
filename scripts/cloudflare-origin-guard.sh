#!/usr/bin/env bash
set -euo pipefail

table_name="dune_cloudflare_origin_guard"
action="${1:-apply}"

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    printf 'error: cloudflare origin guard requires root\n' >&2
    exit 1
  fi
}

write_rules() {
  local name="$1"
  local mode="$2"
  cat <<EOF
table inet ${name} {
  set cloudflare_ipv4 {
    type ipv4_addr
    flags interval
    elements = { 173.245.48.0/20, 103.21.244.0/22, 103.22.200.0/22, 103.31.4.0/22, 141.101.64.0/18, 108.162.192.0/18, 190.93.240.0/20, 188.114.96.0/20, 197.234.240.0/22, 198.41.128.0/17, 162.158.0.0/15, 104.16.0.0/13, 104.24.0.0/14, 172.64.0.0/13, 131.0.72.0/22 }
  }

  set cloudflare_ipv6 {
    type ipv6_addr
    flags interval
    elements = { 2400:cb00::/32, 2606:4700::/32, 2803:f800::/32, 2405:b500::/32, 2405:8100::/32, 2a06:98c0::/29, 2c0f:f248::/32 }
  }

  chain input {
    type filter hook input priority -25; policy accept;

    iifname "lo" return
    ip saddr { 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16 } tcp dport { 80, 443 } return
    ip6 saddr { ::1/128, fc00::/7, fe80::/10 } tcp dport { 80, 443 } return
EOF
  if [[ "$mode" == "proxy" ]]; then
    cat <<'EOF'
    ip saddr @cloudflare_ipv4 tcp dport { 80, 443 } return
    ip6 saddr @cloudflare_ipv6 tcp dport { 80, 443 } return
EOF
  fi
  cat <<EOF
    meta nfproto ipv4 tcp dport { 80, 443 } counter drop comment "public web ingress must use Cloudflare"
    meta nfproto ipv6 tcp dport { 80, 443 } counter drop comment "public web ingress must use Cloudflare"
  }
}
EOF
}

apply_guard() {
  local mode="${1:-tunnel}"
  require_root
  command -v nft >/dev/null 2>&1 || {
    printf 'error: nft is required\n' >&2
    exit 1
  }

  local candidate="${table_name}_candidate_$$"
  local candidate_file rules_file
  candidate_file="$(mktemp)"
  rules_file="$(mktemp)"
  trap 'rm -f "${candidate_file:-}" "${rules_file:-}"' EXIT

  write_rules "$candidate" "$mode" >"$candidate_file"
  nft --check --file "$candidate_file"
  write_rules "$table_name" "$mode" >"$rules_file"

  if nft list table inet "$table_name" >/dev/null 2>&1; then
    nft delete table inet "$table_name"
  fi
  nft --file "$rules_file"
  nft list table inet "$table_name"
}

check_guard() {
  nft list table inet "$table_name" >/dev/null 2>&1 || {
    printf 'error: Cloudflare origin guard is not loaded\n' >&2
    exit 1
  }
  nft list table inet "$table_name" | grep -Fq 'public web ingress must use Cloudflare' || {
    printf 'error: Cloudflare origin guard does not contain the expected drop rule\n' >&2
    exit 1
  }
  printf 'ok: Cloudflare origin guard is loaded\n'
}

remove_guard() {
  require_root
  if nft list table inet "$table_name" >/dev/null 2>&1; then
    nft delete table inet "$table_name"
  fi
  printf 'ok: Cloudflare origin guard removed\n'
}

case "$action" in
  apply) apply_guard tunnel ;;
  apply-proxy) apply_guard proxy ;;
  check) check_guard ;;
  remove) remove_guard ;;
  *)
    printf 'usage: %s [apply|apply-proxy|check|remove]\n' "$0" >&2
    exit 2
    ;;
esac
