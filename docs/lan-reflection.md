# LAN Reflection / Internal Join

Dune self-hosting advertises one external address to Funcom/FLS and to clients.
For a public server this should normally stay set to the public WAN address:

```dotenv
EXTERNAL_ADDRESS=24.109.206.134
```

Do not switch this value between public and LAN addresses for day-to-day use.
That creates different behavior for internal and external players and can make
FLS/gateway diagnosis confusing.

## The Problem

When a player on the same LAN joins through the public server listing, the client
still tries to reach the public advertised address. Many home routers do not
support NAT hairpin/loopback correctly for UDP game traffic. The symptom is:

- the game hangs at `Connecting to Sietch`;
- the server containers are up and farm-ready;
- Docker has UDP publishes for `7777-7806`;
- host counters for those UDP ports stay at `0`;
- `tcpdump` on the LAN interface sees no packets for the public IP.

If the host never sees packets, this is not a Dune password, map readiness, or
Docker port-publish problem. The LAN path is not reaching the host.

## Standard Decision

Use one stable public advertised address and make LAN clients able to reach that
same address internally.

Preferred order:

1. Router NAT reflection/hairpin for UDP to the server host.
2. A LAN static route for the public `/32` to the server host.
3. A per-client route for the public `/32` to the server host.

Avoid changing `EXTERNAL_ADDRESS` for internal testing unless you are running a
LAN-only server.

## Router Static Route Mode

This keeps Dune configured for public play while allowing LAN clients to use the
same public server address.

On the router, add:

```text
Destination: 24.109.206.134
Prefix:      /32
Gateway:     192.168.50.148
Interface:   LAN
```

Then enable host-side reflection on the Dune host:

```bash
sudo ./scripts/setup-lan-reflection.sh
```

For persistence, install the provided systemd unit:

```bash
sudo install -m 0644 config/systemd/dune-lan-reflection.service /etc/systemd/system/dune-lan-reflection.service
sudo systemctl daemon-reload
sudo systemctl enable --now dune-lan-reflection.service
```

The script:

- adds the public `/32` to the LAN interface;
- disables strict reverse-path filtering for the LAN reflection path;
- ensures Dune container replies are masqueraded back through the LAN interface.
- redirects local same-host client traffic for `GAME_RMQ_PUBLIC_PORT` TCP and
  the gameplay UDP range back into the host-published services.

## Per-Client Route Mode

Use this when the router cannot add static routes and does not support UDP
hairpin NAT. Add the route on each LAN client that needs to play internally.

Linux:

```bash
sudo ip route add 24.109.206.134/32 via 192.168.50.148
```

Windows PowerShell as Administrator:

```powershell
route -p add 24.109.206.134 mask 255.255.255.255 192.168.50.148
```

macOS:

```bash
sudo route -n add -host 24.109.206.134 192.168.50.148
```

Host-side reflection must still be enabled on the Dune host.

## Validation

Watch for packets while attempting to join from the LAN:

```bash
sudo timeout 75 tcpdump -ni enp17s0 'host 24.109.206.134 and udp'
```

Check Docker's UDP counters:

```bash
sudo iptables -t nat -L DOCKER -n -v | rg 'dpt:(7777|7888|7778|7889)'
```

Interpretation:

- `0 packets captured` and Docker counters stay `0`: LAN routing/hairpin is not
  sending traffic to the Dune host.
- packets appear on `enp17s0` but Docker counters stay `0`: host firewall/NAT
  path is wrong.
- Docker counters increase but the client still hangs: Dune service discovery,
  map routing, or RabbitMQ/FLS state is the next layer to inspect.

## Notes

Forward public gameplay UDP to the Dune host for external players:

```text
7777-7806/udp -> 192.168.50.148
```

The current Compose layout also publishes IGW/S2S UDP ports `7888-7917` for
diagnostics. Keep those closed publicly unless client testing proves they are
required by the live routing path.

For live-client login, the game RabbitMQ endpoint advertised by Gateway must be
reachable from the client. In the public self-host layout that means forwarding
`GAME_RMQ_PUBLIC_PORT`, default `31982/tcp`, to the host. Keep RabbitMQ
management, Postgres, and admin panel ports private.
