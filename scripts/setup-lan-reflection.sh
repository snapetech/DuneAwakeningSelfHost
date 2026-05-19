#!/usr/bin/env bash
set -euo pipefail

PUBLIC_IP="${DUNE_PUBLIC_IP:-24.109.206.134}"
LAN_IFACE="${DUNE_LAN_IFACE:-enp17s0}"
DUNE_BRIDGE_CIDR="${DUNE_BRIDGE_CIDR:-172.31.240.0/24}"
DUNE_DOCKER_NETWORK="${DUNE_DOCKER_NETWORK:-dune_server_default}"
GAME_RMQ_PUBLIC_PORT="${GAME_RMQ_PUBLIC_PORT:-31982}"
GAME_UDP_PORT_RANGE="${GAME_UDP_PORT_RANGE:-7777:7806}"
KNOCK_DUNE_TCP_COMMENT="knock-scanner dune tcp auto-block"

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

# Docker's raw table can block bridged container traffic before FORWARD accepts
# it, which breaks control-plane calls between game-rmq and auth/text services.
if ! iptables -t raw -C PREROUTING -s "$DUNE_BRIDGE_CIDR" -d "$DUNE_BRIDGE_CIDR" -m comment --comment "dune allow same-bridge raw control-plane" -j ACCEPT 2>/dev/null; then
    iptables -t raw -I PREROUTING 1 -s "$DUNE_BRIDGE_CIDR" -d "$DUNE_BRIDGE_CIDR" -m comment --comment "dune allow same-bridge raw control-plane" -j ACCEPT
fi

# Keep same-network container traffic working when the host FORWARD policy is
# DROP. RabbitMQ auth depends on game-rmq reaching rmq-auth-shim/text-router.
if command -v docker >/dev/null 2>&1; then
    network_id="$(docker network inspect "$DUNE_DOCKER_NETWORK" --format '{{.Id}}' 2>/dev/null || true)"
    if [ -n "$network_id" ]; then
        bridge_if="br-${network_id:0:12}"
        if ip link show "$bridge_if" >/dev/null 2>&1 \
            && ! iptables -C FORWARD -i "$bridge_if" -o "$bridge_if" -j ACCEPT 2>/dev/null; then
            iptables -I FORWARD 1 -i "$bridge_if" -o "$bridge_if" -j ACCEPT
        fi
    fi
fi

# The host knock-scanner sync can leave this as a broad Docker DROP for the
# Dune login port, even when its nftables block set is empty.
while iptables -C DOCKER-USER -p tcp --dport "$GAME_RMQ_PUBLIC_PORT" -m comment --comment "$KNOCK_DUNE_TCP_COMMENT" -j DROP 2>/dev/null; do
    iptables -D DOCKER-USER -p tcp --dport "$GAME_RMQ_PUBLIC_PORT" -m comment --comment "$KNOCK_DUNE_TCP_COMMENT" -j DROP
done

# Local clients on the Dune host itself also receive the public address from FLS.
# Redirect only this self-host address/port set; official servers are unaffected.
if ! iptables -t nat -C OUTPUT -p tcp -d "$PUBLIC_IP" --dport "$GAME_RMQ_PUBLIC_PORT" -j REDIRECT --to-ports "$GAME_RMQ_PUBLIC_PORT" 2>/dev/null; then
    iptables -t nat -A OUTPUT -p tcp -d "$PUBLIC_IP" --dport "$GAME_RMQ_PUBLIC_PORT" -j REDIRECT --to-ports "$GAME_RMQ_PUBLIC_PORT"
fi

if ! iptables -t nat -C OUTPUT -p udp -d "$PUBLIC_IP" --dport "$GAME_UDP_PORT_RANGE" -j REDIRECT 2>/dev/null; then
    iptables -t nat -A OUTPUT -p udp -d "$PUBLIC_IP" --dport "$GAME_UDP_PORT_RANGE" -j REDIRECT
fi

echo "Dune LAN reflection host side is active for ${PUBLIC_IP} on ${LAN_IFACE}; local self-host redirects cover tcp/${GAME_RMQ_PUBLIC_PORT} and udp/${GAME_UDP_PORT_RANGE}"
