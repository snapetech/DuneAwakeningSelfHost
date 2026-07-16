# Active/Passive DASH HA Reference

This reference adds a fenced service VIP to DASH's existing hot Postgres
standby, file/image synchronization, failover seal, promotion, network cutover,
role-service, cutback-proof, and standby-rebuild tooling. It is active/passive,
not active/active. Confidence: high that two writers for one world are unsafe;
the Funcom stack and physical Postgres replication expose one writable world
timeline.

## Failure model

Keepalived is only the final traffic-ownership layer. It never promotes
Postgres, starts the world, or guesses whether the old primary is dead. The VIP
health check enters FAULT unless all of these are true:

- a private authority marker is bound to the local hostname;
- its short-lived epoch matches local configuration;
- its TTL has not expired;
- it records the SHA-256 of operator-provided fencing evidence;
- the configured guarded DASH service is active.

The authority tool records evidence but does not fence hardware. Fence the old
host using the hypervisor, PDU, switch/router isolation, or confirmed host
shutdown before granting the peer authority. A network partition without
fencing can otherwise produce two masters regardless of orchestration product.

## Installation

On each node:

1. Complete `docs/primary-standby-failover.md` and make
   `failover-bidirectional-audit` pass.
2. Install Keepalived from the distribution package.
3. Install `dash-vip-health.sh` as
   `/usr/local/libexec/dash-vip-health` mode `0755` and
   `dash-ha-authority.sh` as `/usr/local/sbin/dash-ha-authority` mode `0755`.
4. Render `keepalived.conf.example` with a dedicated RFC1918 service VIP, exact
   interface and unicast peer addresses, different priorities, and a site
   authentication value. Both nodes remain `state BACKUP`; `nopreempt` avoids
   an automatic failback.
5. Set `DASH_HA_EXPECTED_EPOCH` and `DASH_HA_SERVICE_UNIT` for the health script
   through a root-owned wrapper or Keepalived service environment. Keep the
   marker root-owned mode `0600`.
6. Point router/NAT rules at the service VIP. The VIP carries UDP and TCP; do
   not place gameplay UDP behind an HTTP/TCP-only proxy.

Use `DASH_HA_SERVICE_UNIT=dune-full-farm.service` if the existing production
unit owns the active farm. The Ansible package uses `dash.service` by default.

## Planned transfer

Dry-run the repository's normal orchestration first. During the maintenance
window:

1. Announce, backup, stop old writers, seal WAL, and confirm standby replay.
2. Fence the old host and save the hypervisor/PDU/router receipt to a local
   file. Revoke its marker if the filesystem is reachable.
3. Promote Postgres and activate role services using the existing guarded
   failover runbook.
4. Generate a unique epoch and place it in the new active node's root-owned HA
   environment.
5. Grant short-lived authority:

   ```bash
   sudo dash-ha-authority grant \
     --epoch cutover-20260715T120000Z-random \
     --fenced-host old-dash-host \
     --fence-evidence /root/fencing/receipt.txt \
     --ttl-seconds 3600 \
     --confirm 'GRANT DASH HA AUTHORITY'
   ```

6. Verify `dash-vip-health.sh`, Keepalived state, VIP ownership, external login,
   map travel, RMQ TLS, and `/api/status` database identity.
7. Renew authority only after rechecking fencing. The maximum accepted TTL is
   24 hours so stale local state cannot authorize the VIP indefinitely.

Rollback/cutback is another fenced transfer onto the current Postgres timeline;
it is not a symlink flip or automatic Keepalived preemption. Rebuild the old
primary as a standby before giving it authority again.

## Relationship to RKE2 peers

The bsmr/dapdsm peer distributes images and reconciles a multi-node
RKE2/HAProxy/Keepalived installation. DASH reaches the deploy/reconcile and
service-address outcomes with immutable release Ansible plus existing standby
reconciliation and this fenced VIP. It deliberately does not claim that
multiple active game control planes or automatic database promotion are safe.
Kubernetes scheduling cannot solve the single-writer world, static public
address, RabbitMQ identity, or external fencing contracts.
