# Swap-Warm Idle Maps

**Status: optional, off by default (`DUNE_SWAP_WARM_ENABLED=false`).** This is
an alternative idle policy for dynamic maps, not a replacement for the
autoscaler described in [`autoscaling-memory.md`](autoscaling-memory.md).
Choose it deliberately on hosts where physical RAM is the binding constraint
and NVMe swap capacity is abundant; the default stop/cold-start `dynamic`
policy remains the right choice everywhere else, and is what a fresh install
gets with no configuration.

The autoscaler's `dynamic` mode (see [`autoscaling-memory.md`](autoscaling-memory.md))
stops a map's container when nobody is using it and cold-boots a fresh Unreal
Engine process on demand. That cold boot is the dominant cost of a map
transition: the Capacity Intelligence ledger on this deployment measured
90-260 seconds for a normal single-map demand start, and considerably worse
during any moment of host contention. Full engine re-init, asset load, and
Director/RabbitMQ re-registration cannot be made much faster from the
orchestration side.

Swap-warm is a different idle strategy for maps that are not core always-on
maps: keep the container **running continuously**, and instead of killing it
on idle, shrink its resident memory via the Linux cgroup v2 `memory.high`
soft limit so the kernel reclaims (swaps out) the process's cold working set.
The process itself is never touched, never restarted, and never loses its
Director/RMQ registration. When a player arrives, the limit is lifted and the
kernel pages the working set back in through ordinary page faults as the
process resumes handling the map — bounded by NVMe page-fault latency, not by
Unreal Engine cold init.

## Why this works

`memory.high` is a soft limit: when a cgroup's usage exceeds it, the kernel
puts that cgroup under direct reclaim pressure (swapping anonymous pages,
evicting cache) but never OOM-kills it, unlike `memory.max`. This was
validated live against `harko-village` (an always-on map, zero players) on
`kspls0`: pre-squeeze RSS was 938MiB. Setting `memory.high=200M` dropped
resident memory to under 20MiB within 2 seconds, and it settled at a stable
111-116MiB over the next 21 seconds with 968MiB parked in swap — no thrashing,
no cycling, no errors in the container's logs. Restoring `memory.high=max`
left it at its reclaimed footprint rather than immediately reclaiming the
swapped pages, confirming pages come back lazily on actual use, not eagerly
on limit change.

This means most of an idle map's resident memory is genuinely cold (static
world/asset data the simulation loop does not touch every tick), not
continuously hot working set — at least for the map class tested. Maps under
`DUNE_AUTOSCALER_SIMULATION_REQUIRED_SERVICES` (persistent crafting/production
simulation, `survival` by default) are excluded from swap-warm entirely; they
must keep ticking and are not good squeeze candidates.

**Open validation item**: only one map class has been measured this way so
far. Before trusting swap-warm across the full dynamic-map catalog, watch
`backups/memory-squeeze/swap-warm-daemon.log` and `docker stats` after a few
real player transitions into different map types (dungeon instance, overland,
faction outpost) to confirm the same cold/hot split holds. If a specific map
shows continuous swap in/out cycling (`vmstat`'s `si`/`so` churning, or
`memory.current` failing to settle in `map-memory-squeeze.sh watch`), remove
it from `DUNE_SWAP_WARM_SERVICES` and leave it on ordinary `dynamic` stop/start
instead.

## Tradeoff

Squeezed maps still exist as running processes and still tick their idle
simulation loop — that costs some baseline CPU that a fully stopped container
would not, unlike today's stop-based `dynamic` mode. This deployment had
comfortable CPU headroom at measurement time (`vmstat` idle 67-80%), but watch
aggregate CPU after enabling the full fleet.

## Components

- `scripts/map-memory-squeeze.sh squeeze|restore|status|watch SERVICE` — the
  primitive. Resolves the container's cgroup v2 path
  (`/sys/fs/cgroup/system.slice/docker-<id>.scope`) and reads/writes
  `memory.high` directly. Requires cgroup v2 and root or passwordless sudo.
  Every action logs a timestamped before/after line to
  `backups/memory-squeeze/memory-squeeze.log` (override with
  `DUNE_MEMORY_SQUEEZE_LOG`) as well as stdout.
- `scripts/enable-swap-warm-fleet.sh [ENV_FILE]` — setup step. Moves every
  service in `DUNE_SWAP_WARM_SERVICES` from autoscaler mode `dynamic` to
  `always-on` through the existing `/api/ops/autoscaler` `set-mode` action, so
  the core autoscaler keeps them running instead of stopping them. Idempotent;
  safe to re-run after changing the service list. Batches the mode flips
  (`DUNE_SWAP_WARM_ENABLE_BATCH_SIZE`, default 4, `DUNE_SWAP_WARM_ENABLE_BATCH_PAUSE_SECONDS`,
  default 90s) so the autoscaler does not cold-boot every newly-always-on map
  at once -- see [`maintenance-updates.md`](maintenance-updates.md#restart-batching)
  for why that specific failure mode matters here. Logs to
  `backups/memory-squeeze/enable-swap-warm-fleet.log`.
- `scripts/disable-swap-warm-fleet.sh [ENV_FILE] [TARGET_MODE]` — full
  decommission, the counterpart to the above: restores any squeezed map and
  sets its mode back to `dynamic` (or another mode you choose), handing
  lifecycle fully back to the ordinary autoscaler. See
  [Enable, pause, and disable](#enable-pause-and-disable).
- `scripts/swap-warm-daemon.sh [ENV_FILE]` — the ongoing loop, installed via
  `make install-swap-warm-service ENV_FILE=.env` (renders
  `config/systemd/dune-swap-warm.service` for the current checkout, matching
  the existing `dune-map-watchdog.service` pattern). Every
  `DUNE_SWAP_WARM_POLL_SECONDS` (default 10) it re-reads
  `DUNE_SWAP_WARM_ENABLED` from `ENV_FILE` (no restart needed to flip it) and,
  while enabled, reads `scripts/capacity-intelligence.py status`, which
  already tracks `players`/`active`/`demanded` per map (the same signals the
  core autoscaler uses for dynamic starts). A map with any of those is "hot"
  and gets restored immediately if it was squeezed; a map idle for
  `DUNE_SWAP_WARM_RETENTION_SECONDS` (default 120) with none of those gets
  squeezed. Transitions are logged to
  `backups/memory-squeeze/swap-warm-daemon.log`.

This is deliberately layered on top of the existing autoscaler rather than
replacing it: container lifecycle (start/stop/health/Director registration)
stays fully owned by the already-tested autoscaler in `always-on` mode; the
daemon only ever touches `memory.high` for the services it's told to manage,
and never starts, stops, or recreates a container.

## Configuration

| Variable | Default | Meaning |
| --- | ---: | --- |
| `DUNE_SWAP_WARM_ENABLED` | `false` | Master switch. Re-read every daemon cycle; flipping it in `ENV_FILE` takes effect within one poll interval, no restart needed. |
| `DUNE_SWAP_WARM_SERVICES` | (empty) | Comma-separated map services to manage. Must not include always-on core maps or `DUNE_AUTOSCALER_SIMULATION_REQUIRED_SERVICES`. |
| `DUNE_SWAP_WARM_RETENTION_SECONDS` | `120` | Idle seconds before squeezing. Deliberately much shorter than `dynamic` mode's retention — squeeze/restore has no cold-boot penalty, so there is little reason to delay it. |
| `DUNE_SWAP_WARM_MIN_HOLD_SECONDS` | `1800` | Minimum time a map stays fully resident after being restored before it is eligible to be squeezed again, even if it goes idle again sooner. Prevents squeeze/restore flapping from brief, intermittent visits. Does not gate a map's first squeeze, only a re-squeeze after an actual restore. |
| `DUNE_SWAP_WARM_HIGH_MIB` | `256` | `memory.high` ceiling applied while squeezed. |
| `DUNE_SWAP_WARM_POLL_SECONDS` | `10` | Daemon reconcile cadence. |
| `DUNE_SWAP_WARM_ENABLE_BATCH_SIZE` | `4` | `enable-swap-warm-fleet.sh` mode-flip batch size. `0` disables batching. |
| `DUNE_SWAP_WARM_ENABLE_BATCH_PAUSE_SECONDS` | `180` | Pause between `enable-swap-warm-fleet.sh` batches. Must clear observed single-map cold-start time under load; a 90s pause was tried first and proved too short (see [Rollout evidence](#rollout-evidence-batch-pause-sizing) below). |
| `DUNE_MEMORY_SQUEEZE_LOG` | `backups/memory-squeeze/memory-squeeze.log` | Per-action log for the squeeze primitive. |
| `DUNE_SWAP_WARM_LOG` | `backups/memory-squeeze/swap-warm-daemon.log` | Daemon transition log. |

## Enable, Pause, And Disable

Turning this on is a three-step, deliberate opt-in -- nothing above changes
behavior on its own:

```bash
# 1. Install the (inert) daemon unit
make install-swap-warm-service ENV_FILE=.env

# 2. Set DUNE_SWAP_WARM_ENABLED=true and DUNE_SWAP_WARM_SERVICES=<list> in .env,
#    then hand the listed maps' lifecycle to always-on
sudo systemctl enable --now dune-swap-warm.service
./scripts/enable-swap-warm-fleet.sh .env
journalctl -u dune-swap-warm.service -f
```

Two different ways back out, for two different situations:

- **Pause** (fast, fully reversible, no container/mode changes): set
  `DUNE_SWAP_WARM_ENABLED=false` in `.env`. The running daemon notices within
  one poll interval, restores any currently-squeezed map to full residency,
  and idles. The managed maps stay `always-on` (fully resident, exactly like
  the core maps) until you re-enable or fully disable. Use this to rule out
  swap-warm as a cause during an incident without unwinding the whole setup.
- **Disable** (full decommission): `./scripts/disable-swap-warm-fleet.sh .env`
  restores any squeezed map and sets every managed service back to `dynamic`
  (or a target mode you pass as a second argument), returning them to the
  default stop-on-idle/cold-start-on-demand policy. Then, if you want the
  daemon gone entirely rather than idling:
  `sudo systemctl disable --now dune-swap-warm.service`.

### Rollout Evidence: Batch Pause Sizing

The first production rollout on `kspls0` (25 dynamic maps, `DUNE_SWAP_WARM_ENABLE_BATCH_SIZE=4`,
`DUNE_SWAP_WARM_ENABLE_BATCH_PAUSE_SECONDS=90`) logged 14 of 25 `set-mode`
calls as `FAILED: curl timeout` once several batches' maps were cold-booting
concurrently. Checking the persisted `backups/admin-panel/autoscaler.json`
afterward showed all 25 had actually reached `always-on` -- every mutation
succeeded server-side; the admin API's response just took longer than the
30-second client timeout while it also handled the concurrent Docker
reconciliation for multiple cold-booting maps. The default pause is now
180 seconds specifically because of this: at 90 seconds, a later batch's
`set-mode` request (which triggers that map's own autoscaler reconciliation)
can land while an earlier batch's maps are still mid-cold-boot, both
competing for the same host resources and slowing the admin API enough to
make an otherwise-successful mutation look failed. `enable-swap-warm-fleet.sh`
does not retry on timeout, so treat any `FAILED` line as needing a manual
mode check (`GET /api/ops/autoscaler` or the Infrastructure page) rather than
an automatic assumption of failure -- as happened here, the request likely
still went through.

## Design Decision: Why Not Grow `zram` Instead

The obvious-looking alternative -- make the host's `zram` device bigger
instead of adding NVMe swap capacity -- was considered and rejected for this
use case. `zram` is a compressed block device backed by **physical RAM**, not
disk: a page swapped into it still costs real memory (roughly a third to a
half of its uncompressed size, workload-dependent), just less than keeping it
fully resident. On a host where RAM is already the scarce resource -- the
entire reason this feature exists -- growing `zram`'s capacity means handing
more of that same scarce RAM to compressed-swap-cache, which works directly
against the goal of freeing RAM for other use. It was already observed
sitting at 100% utilization from ambient host load unrelated to Dune, which
confirms rather than argues against this: on a memory-constrained host, `zram`
saturates on its own and additional capacity would just consume more RAM to
hold it.

NVMe-backed disk swap has the opposite tradeoff: essentially unlimited cheap
capacity (hundreds of GB of free disk vs. tens of GB of free RAM), at the
cost of needing an actual page-in on first touch after being swapped out
instead of a RAM-speed decompression. The live validation in
[Why this works](#why-this-works) measured that page-in cost as acceptable
for this workload (stable, sub-second, no thrashing) -- so there is no
latency problem here that a bigger `zram` would actually be solving, only a
RAM cost it would be adding. `zram` is left at its existing size and priority
(highest, so it still absorbs what it can before anything spills to disk);
the dedicated NVMe swapfile below absorbs the rest.

## Dedicated Swap Capacity

A 128GiB swapfile (`/swapfile-dune-idle`, priority 10, alongside the existing
`/swapfile-dune` and `/swapfile-dune2`) was added on `kspls0` to give the
squeezed fleet headroom independent of the host's general-purpose swap. Linux
does not support routing a specific cgroup's swapped pages to a specific swap
device — all swap devices are one pool ordered by priority — so this is
capacity headroom, not per-container device isolation. The actual segregation
(which maps' memory gets pushed to swap at all) is entirely the `memory.high`
policy above, not the swap device layout. Sizing it: this host's dynamic-map
catalog is 25 services; at an observed idle footprint in the hundreds of MiB
to low GiB per map before squeezing, 128GiB is comfortable headroom even if
every managed map is squeezed simultaneously, without assuming a specific
per-map number that will drift as the catalog changes.

Persisted in `/etc/fstab`:

```
/swapfile-dune-idle none swap sw,pri=10 0 0
```
