# Host Kernel and NIC Tuning

DASH provides dry-run-first, reversible-evidence host tuning for Linux memory,
UDP networking, transparent hugepages, NIC rings, and IRQ placement. It does
not replace or overwrite Docker `daemon.json`, create swap, disable irqbalance,
or restart Docker/containers.

Confidence is **high** for the applied sysctl/THP/IRQ state and rollback
evidence. Confidence is **moderate** that every NIC benefits from maximum ring
sizes; keep `--nic` optional and compare softnet drops, latency, and driver
errors on unusual hardware.

## Inspect and plan

```bash
./scripts/host-tuning.sh --env-file .env status
./scripts/host-tuning.sh --env-file .env plan
./scripts/host-tuning.sh --env-file .env plan --nic
```

Status reports the relevant sysctls, THP mode, selected default-route NIC,
ring sizes, IRQ affinities, irqbalance state, and the background CPU pool from
`compose.cpu-affinity.yaml`.

The generated sysctl policy:

- keeps `vm.swappiness=10` and `vm.overcommit_memory=1`;
- uses dirty ratios `10/5` to reduce large writeback bursts;
- raises default UDP receive/send buffers to 8/4 MiB;
- never lowers an existing `rmem_max`, `wmem_max`, `somaxconn`, or
  `netdev_max_backlog` that already exceeds the DASH baseline; and
- raises softnet packet/time budgets to `600/4000`.

Override values with `DUNE_HOST_TUNING_*` environment variables when a measured
host-specific value is required.

## Apply and persist

Run on the production host:

```bash
hostname
sudo ./scripts/host-tuning.sh --env-file .env apply --execute --persist --nic \
  --confirm 'APPLY DUNE HOST TUNING'
```

The command verifies the configured production hostname, requires root and the
exact confirmation, then records before/after state under
`backups/host-tuning/<UTC timestamp>/`.

With `--nic`, it asks the driver for maximum supported RX/TX ring sizes and pins
all IRQs matching the selected NIC to the CPU-affinity background pool. If
irqbalance is active, IRQ pinning is skipped instead of fighting the daemon.
Ring tuning can still apply. The script never disables irqbalance.

With `--persist`, the command durably records these values in `.env`:

```dotenv
DUNE_HOST_TUNING_ENABLED=true
DUNE_HOST_TUNING_NIC_ENABLED=true
DUNE_HOST_TUNING_NIC=enp5s0
DUNE_HOST_TUNING_NIC_IRQ_CPUSET=0,1,2,3,16,17,18,19
```

It also installs and enables `dune-host-tuning.service`, a boot-time oneshot
that reapplies the managed sysctl file, THP mode, NIC rings, and IRQ placement.
No game container is restarted.

## Recovery

Every apply directory contains:

- `status.before.txt` and `status.after.txt`;
- the previous managed sysctl file if one existed;
- the previous systemd unit if one existed;
- `env.before`; and
- a manifest identifying the host, NIC, IRQ pool, and persistence state.

To remove the managed policy, first restore `env.before`, the saved sysctl/unit
files when present, or remove `/etc/sysctl.d/99-dune-selfhost.conf` and
`/etc/systemd/system/dune-host-tuning.service` when the backup proves they did
not previously exist. Then run:

```bash
sudo systemctl disable --now dune-host-tuning.service
sudo systemctl daemon-reload
sudo sysctl --system
```

Restore the THP mode and IRQ affinities recorded in `status.before.txt` if an
immediate runtime rollback is required. Clearing CPU container affinity is a
separate operation documented in [cpu-affinity.md](cpu-affinity.md).

Persistent values use the locked inode-preserving configuration writer. This
keeps the Admin container's `.env` bind mount live; see
[configuration-durability.md](configuration-durability.md).

## Validation

```bash
./scripts/test-host-tuning.sh
./scripts/host-tuning.sh --env-file .env status
systemctl status dune-host-tuning.service --no-pager
```

The automated test verifies larger-current-value preservation, dry-run state,
THP application, maximum NIC rings, IRQ background placement, persistent env
flags, backup creation, and systemd-unit generation against an isolated fake
host filesystem.
