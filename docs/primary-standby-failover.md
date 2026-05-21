# Primary to Standby Failover

Confidence high: use the standby as a cold Dune-service node with a hot
Postgres streaming replica. Confidence low that true zero-disconnect live player
handoff is supported by the self-hosted server stack.

Set the deployment-specific values in `.env`; do not bake site IPs, usernames,
or hostnames into scripts:

```sh
POSTGRES_REMOTE_REPLICA_HOST=<standby-host>
POSTGRES_REMOTE_REPLICA_ROOT=<standby-replica-root>
POSTGRES_REMOTE_REPLICATION_SLOT=<standby-slot>
DUNE_FAILOVER_PRIMARY_HOST=<current-primary-host>
DUNE_FAILOVER_PRIMARY_LAN_IP=<current-primary-lan-ip>
DUNE_FAILOVER_STANDBY_HOST=<standby-host>
DUNE_FAILOVER_STANDBY_LAN_IP=<standby-lan-ip>
DUNE_FAILOVER_ROUTER_SSH=<ssh-user>@<router-lan-ip>
DUNE_FAILOVER_PUBLIC_IP=<public-game-ip>
DUNE_STANDBY_REPO_ROOT=<repo-path-on-standby>
```

`EXTERNAL_ADDRESS` and `GAME_RMQ_PUBLIC_HOST` should keep advertising the public
game address. During failover, only the LAN destination behind that public
address changes.

## Standby Model

Mirror these runtime layers from the active primary to the standby:

- repo checkout, Compose files, scripts, docs, and config templates;
- `.env`;
- `config/`, including RabbitMQ TLS under `config/tls/rabbitmq`;
- `data/server-saved/`;
- RabbitMQ data and backup metadata for restore or forensic recovery;
- systemd units and required Docker images for the configured `DUNE_IMAGE_TAG`.

Do not rsync `data/postgres` to the standby. On the standby, Postgres state is
owned by the streaming replica under `POSTGRES_REMOTE_REPLICA_ROOT/data`.

RabbitMQ is mirrored as backup state only through `backup-state`/`restore-state`.
It is not live replicated, is not rsynced from its running data directory, and
must not be run active-active for the same `WORLD_UNIQUE_NAME`.

## Operator Commands

Read-only checks:

```sh
make failover-topology-status ENV_FILE=.env
make failover-bidirectional-audit ENV_FILE=.env
make standby-status ENV_FILE=.env
make cutover-network-status ENV_FILE=.env
make cutover-check ENV_FILE=.env
make failover-orchestrate ENV_FILE=.env ROLE=standby
```

Mirror non-Postgres runtime files:

```sh
make sync-standby-files ENV_FILE=.env
make sync-standby-images ENV_FILE=.env
```

Stage replacement RabbitMQ TLS material if `GAME_RMQ_PUBLIC_HOST` or
`EXTERNAL_ADDRESS` changed and the live certificate does not cover the public
address:

```sh
make rabbitmq-cert-stage ENV_FILE=.env
CONFIRM_INSTALL_STAGED_RMQ_CERT=yes make rabbitmq-cert-install-staged ENV_FILE=.env
```

Install staged TLS only during maintenance. It changes client-facing RabbitMQ
identity and requires recreating `game-rmq`, `gateway`, `director`,
`text-router`, and map containers so every process uses the same CA and server
certificate. Confidence high: do not apply this while players are connected.
Use `CONFIRM_RECREATE_RMQ_TLS_STACK=yes make rabbitmq-cert-recreate-stack
ENV_FILE=.env` after installing staged TLS.

Promote the configured standby after stopping or isolating writers on the old
primary:

```sh
CONFIRM_PROMOTE_STANDBY=yes make promote-standby ENV_FILE=.env
```

Move host-side public-address/reflection rules to the standby:

```sh
CONFIRM_HOST_NETWORK_FAILOVER=yes make host-network-failover ENV_FILE=.env
```

Move router forwards to the standby LAN IP:

```sh
CONFIRM_ROUTER_CUTOVER=yes make router-cutover ENV_FILE=.env TARGET="$DUNE_FAILOVER_STANDBY_LAN_IP"
```

Switch systemd role services so the promoted host owns the game stack, public
website/status services, and active timers while the old primary is disabled:

```sh
CONFIRM_FAILOVER_ROLE_SERVICES=yes make failover-role-services ENV_FILE=.env ROLE=standby
```

Cut back by reversing the target IP and role direction:

```sh
CONFIRM_ROUTER_CUTOVER=yes make router-cutover ENV_FILE=.env TARGET="$DUNE_FAILOVER_PRIMARY_LAN_IP"
CONFIRM_FAILOVER_ROLE_SERVICES=yes make failover-role-services ENV_FILE=.env ROLE=primary
make failover-orchestrate ENV_FILE=.env ROLE=primary
```

Postgres is not automatic in both directions. Confidence high: physical
streaming replication follows one writable timeline. After promoting the
standby, the old primary must not be restarted as a writer. Rebuild it as a new
standby from the promoted primary before any later cutback:

```sh
make rebuild-postgres-standby ENV_FILE=.env TARGET="$DUNE_FAILOVER_PRIMARY_HOST" ROOT="$POSTGRES_REMOTE_REPLICA_ROOT"
CONFIRM_REBUILD_POSTGRES_STANDBY=yes make rebuild-postgres-standby ENV_FILE=.env TARGET="$DUNE_FAILOVER_PRIMARY_HOST" ROOT="$POSTGRES_REMOTE_REPLICA_ROOT"
```

Run that from the host that currently owns the active promoted database. The
first command is a dry-run. The confirmed command moves stale target data aside
and starts a fresh `dune-postgres-replica` from the current active primary.

## Planned Cutover

1. Announce maintenance and wait for players to leave or accept a short
   interruption.
2. Run `make backup-state ENV_FILE=.env` on the current primary.
3. Run `make standby-status ENV_FILE=.env`. The slot should be active, the
   standby should report `pg_is_in_recovery() = true`, replay delay should be
   near zero, and the latest snapshot should be within the expected window.
4. If RabbitMQ TLS SANs are stale, run `make rabbitmq-cert-stage ENV_FILE=.env`,
   then install staged material during the maintenance window with
   `CONFIRM_INSTALL_STAGED_RMQ_CERT=yes make rabbitmq-cert-install-staged
   ENV_FILE=.env`.
5. Run `make sync-standby-files ENV_FILE=.env`.
6. Stop all Dune writers on the old primary: game servers, director, text
   router, gateway, admin mutations, bots, public status writers, and
   maintenance jobs. Disable timers that can write state.
7. Wait for replay to catch up. Re-run standby status and confirm replay delay
   is acceptable.
8. Create a Postgres failover seal with `make postgres-failover-seal
   ENV_FILE=.env`. This records the primary system identifier, timeline, current
   WAL LSN, and standby replay LSN.
9. Promote the standby with `CONFIRM_PROMOTE_STANDBY=yes make promote-standby
   ENV_FILE=.env`. The promotion script starts control-plane services first,
   then the 30 map services. Optional admin/bot services are controlled by
   `failover-role-services`.
10. Run `CONFIRM_HOST_NETWORK_FAILOVER=yes make host-network-failover
   ENV_FILE=.env` so the standby owns the public `/32`, relaxed reverse-path
   filtering, Dune bridge masquerade, and local self-host redirects for
   `GAME_RMQ_PUBLIC_PORT`, gameplay UDP, and IGW UDP.
11. Run `CONFIRM_ROUTER_CUTOVER=yes make router-cutover ENV_FILE=.env
   TARGET="$DUNE_FAILOVER_STANDBY_LAN_IP"` to flip router/NAT forwards for
   `GAME_RMQ_PUBLIC_PORT/tcp`, `GAME_UDP_PORT_RANGE/udp`, and
   `IGW_UDP_PORT_RANGE/udp`.
12. Run `CONFIRM_FAILOVER_ROLE_SERVICES=yes make failover-role-services
    ENV_FILE=.env ROLE=standby` so active-only systemd services and timers move
    to the promoted host.
13. Verify `current_alive_active=30 active_servers=30 partitions=30` from
    `scripts/status.sh`, then validate external login, map travel, and public
    website/status freshness.

The whole flow is wrapped by:

```sh
make failover-orchestrate ENV_FILE=.env ROLE=standby
make failover-orchestrate ENV_FILE=.env ROLE=standby APPLY=--apply
```

Dry-run first. The apply path promotes Postgres and moves live traffic.

## Coverage

The scripted cutover covers:

- promoted Postgres data path through `compose.failover-standby.yaml`;
- Dune Compose control-plane services and 30 map services;
- host public `/32`, rp_filter, bridge masquerade, and local reflection rules;
- AsusWRT `vts_rulelist` Dune forwards, when `DUNE_FAILOVER_ROUTER_SSH` points
  at a router that supports `nvram get/set vts_rulelist`;
- configured active-only systemd services and timers;
- configured website/status services and timers.

The public website is not part of the game Compose stack. Include its units in
`DUNE_STANDBY_WEBSITE_SERVICES` and `DUNE_STANDBY_WEBSITE_TIMERS` if it must move
with the game primary. If the website is intentionally active-active or hosted
elsewhere, leave those variables empty or set `DUNE_STANDBY_KEEP_WEBSITE_RUNNING=true`.
For bidirectional cutover, those service/timer units and their application files
must exist on both hosts; the dry-run for `make failover-role-services` reports
missing units before any role switch is applied.

For the Node-based live status site, set `DUNE_STATUS_ROOT`, `DUNE_STATUS_USER`,
`DUNE_STATUS_HOST`, and `DUNE_STATUS_PORT`, then install the unit on each host:

```sh
make install-dune-status-service ENV_FILE=.env
ssh "$POSTGRES_REMOTE_REPLICA_HOST" "cd '$DUNE_STANDBY_REPO_ROOT' && make install-dune-status-service ENV_FILE=.env"
```

Set `DUNE_STANDBY_EXTRA_SYNC_PATHS` to include external website/application
directories that live outside this repository, such as a separate DuneStatus
checkout. `make sync-standby-files` mirrors those paths after the DASH repo.

## Disaster Failover

If the primary is unavailable, promote the standby only after deciding the old
primary will not come back and write the same world state. Confidence high: any
transactions not replayed to the standby before the primary failure are lost.

After failover, rebuild a new standby from the promoted primary. Do not restart
the old primary Dune stack against stale Postgres data.

## Postgres Directionality

Confidence high: this setup is warm standby, not multi-primary. At any instant
there is one writable Postgres primary and one physical standby following that
primary's WAL timeline.

Before promotion:

```text
primary host postgres -> standby host dune-postgres-replica
```

After standby promotion:

```text
promoted standby postgres is writable
old primary data is stale and must stay stopped
```

To restore redundancy, rebuild the old primary as a standby from the promoted
host:

```sh
make postgres-cutback-proof ENV_FILE=.env TARGET=<old-primary-host> ROOT=<standby-root> SEAL_FILE=<seal-file>
make rebuild-postgres-standby ENV_FILE=.env TARGET=<old-primary-host> ROOT=<standby-root>
CONFIRM_REBUILD_POSTGRES_STANDBY=yes make rebuild-postgres-standby ENV_FILE=.env TARGET=<old-primary-host> ROOT=<standby-root>
```

`postgres-cutback-proof` checks the seal against target `pg_controldata`, verifies
the current primary has the same system identifier, confirms the target did not
advance past the sealed LSN, and runs or skips `pg_rewind --dry-run` according to
the target state. Rebuild/rewind remains separate from router cutback because it
is destructive to stale target state and must be confirmed separately.

## Live-Handoff Investigation

No repo evidence shows a supported primitive for migrating live client sockets
or authenticated sessions between hosts. Treat zero-disconnect handoff as an
experiment, not the failover baseline.

Test only in a cloned battlegroup or during maintenance. Stop immediately if a
test requires both hosts writing the same world state concurrently or advertising
the same battlegroup in a split-brain state.

For the quick-hiccup experiment that measures whether clients auto-recover after
a fast host swap, see `docs/handoff-experiment.md` and:

```sh
make handoff-experiment ENV_FILE=.env ROLE=standby
CONFIRM_HANDOFF_EXPERIMENT=yes make handoff-experiment ENV_FILE=.env ROLE=standby APPLY=--apply
```
