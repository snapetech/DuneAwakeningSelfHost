#!/usr/bin/env bash
set -euo pipefail

PUBLIC_IP="${DUNE_PUBLIC_IP:-24.109.206.134}"
LAN_IFACE="${DUNE_LAN_IFACE:-enp17s0}"
DUNE_BRIDGE_CIDR="${DUNE_BRIDGE_CIDR:-172.31.240.0/24}"

if ! ip link show "$LAN_IFACE" >/dev/null 2>&1; then
    echo "LAN interface not found: $LAN_IFACE" >&2
    exit 1
fi

# Let the Linux host own the public /32 on LAN as well. If LAN clients route this
# exact public IP to kspls0, Docker's existing published-port DNAT rules handle
# the same 7777/7888/77xx/78xx UDP ports as public clients.
ip addr replace "${PUBLIC_IP}/32" dev "$LAN_IFACE" label "${LAN_IFACE}:dune"

# Keep asymmetric route checks from rejecting same-LAN public-IP reflection.
sysctl -w "net.ipv4.conf.${LAN_IFACE}.rp_filter=0" >/dev/null
sysctl -w "net.ipv4.conf.all.rp_filter=0" >/dev/null

# Ensure reflected replies from containers are masqueraded back through kspls0.
if ! iptables -t nat -C POSTROUTING -s "$DUNE_BRIDGE_CIDR" -o "$LAN_IFACE" -j MASQUERADE 2>/dev/null; then
    iptables -t nat -I POSTROUTING 1 -s "$DUNE_BRIDGE_CIDR" -o "$LAN_IFACE" -j MASQUERADE
fi

echo "Dune LAN reflection host side is active for ${PUBLIC_IP} on ${LAN_IFACE}"
