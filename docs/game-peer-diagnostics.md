# Game Peer Diagnostics

`scripts/game-peer-diagnostics.py` reads Linux conntrack state on demand and
filters it to the configured Dune gameplay, observed IGW, and public RMQ ports.
Default output coarsens IPv4 to `/24` and IPv6 to `/64`. It writes no file and
the admin panel does not retain its output.

```bash
sudo python3 scripts/game-peer-diagnostics.py
```

Exact addresses are available only through an explicit local CLI confirmation:

```bash
sudo python3 scripts/game-peer-diagnostics.py --raw \
  --confirm 'SHOW RAW GAME PEER IPS'
```

Use raw mode for a live routing/NAT incident, then close the terminal/evidence
channel. Do not attach raw output to public issues or retain it in normal
metrics, moderation, heatmap, or dashboard history. The tool requires
`conntrack-tools` and root or `CAP_NET_ADMIN`; it performs no firewall/network
mutation.
