# CPU Affinity and Cache-Aware Map Placement

DASH can keep latency-sensitive player-facing maps away from infrastructure and
optional-map scheduling contention. The feature is host-specific, disabled by
default, reversible, and does not increase the number of running containers or
their memory reservations.

Confidence is **high** that the generator correctly discovers Linux physical
cores and shared L3 domains. Confidence is **moderate** that the automatic split
is optimal for every processor and workload; use the documented overrides when
measurements support a different layout.

## Generate the host-local overlay

```bash
./scripts/generate-cpu-affinity.py --env-file .env
```

The generated `compose.cpu-affinity.yaml` is ignored by Git because CPU ids are
specific to one machine. The generator obtains the active service list from the
resolved Compose stack and uses Linux sysfs topology:

- on asymmetric cache systems such as X3D, the distinctly largest shared-L3
  domain is assigned to foreground maps;
- on symmetric multi-L3 systems, complete cache domains are divided with about
  one third reserved for background work; and
- on a single-L3 system, complete physical cores are split instead of splitting
  SMT siblings.

Foreground services default to `survival`, `overmap`, `deep-desert`, and
`deep-desert-pvp`. Infrastructure and optional maps share the background pool.
Override discovery in `.env` when required:

```dotenv
DUNE_CPU_AFFINITY_FOREGROUND_SERVICES=survival,overmap,deep-desert
DUNE_CPU_AFFINITY_FOREGROUND_CPUSET=0-7,16-23
DUNE_CPU_AFFINITY_BACKGROUND_CPUSET=8-15,24-31
```

Overrides are rejected if they are empty or reference an offline/unknown CPU.

## Preview and activate

```bash
./scripts/cpu-affinity.sh --env-file .env apply
```

Preview compares every running Compose container's current CPU set with the
generated target and changes nothing.

Production activation must run on `kspls0` (or the installation's configured
`DUNE_PRODUCTION_HOST`):

```bash
hostname
./scripts/cpu-affinity.sh --env-file .env apply --execute --persist \
  --confirm 'APPLY DUNE CPU AFFINITY'
```

Activation uses `docker update --cpuset-cpus`; it does not restart a container.
`--persist` atomically writes `DUNE_CPU_AFFINITY_ENABLED=true` after saving the
previous env file. `scripts/compose-files.sh` then includes the host-local
overlay whenever Compose creates or recreates a service, including dynamic map
starts.

`scripts/deploy-admin-panel.sh` also reapplies the live sets after recreating
the panel and ingress. This closes a Docker recreation edge where the admin
container can lose its overlay set. The post-deploy path remains hostname-
gated, writes a recovery record, and uses `docker update` without restarting
game maps.

Every execution records the previous and target CPU sets, overlay, env backup
when applicable, hostname, and changed count under
`backups/cpu-affinity/<UTC timestamp>/`.

## Disable and recover

Clear affinity from running containers and future Compose operations:

```bash
./scripts/cpu-affinity.sh --env-file .env clear --execute --persist \
  --confirm 'CLEAR DUNE CPU AFFINITY'
```

This passes an empty CPU set to Docker and writes
`DUNE_CPU_AFFINITY_ENABLED=false`. The generated overlay can remain on disk for
later reuse.

## Interaction with autoscaling

CPU affinity and autoscaling solve different problems:

- autoscaling reduces the number of running maps and therefore RAM/CPU use;
- affinity controls where the maps that are running may be scheduled; and
- the balanced profile remains the middle ground: only retained/on-demand maps
  run, foreground maps receive the latency-oriented CPU pool, and optional maps
  use the background pool.

Affinity does not reserve CPU time while a container is stopped. It narrows the
eligible CPUs for a running container but does not force those CPUs busy.

## Validation

```bash
./scripts/test-cpu-affinity.sh
./scripts/cpu-affinity.sh --env-file .env status
./scripts/compose-files.sh .env
```

The test covers asymmetric and symmetric L3 selection, foreground/background
mapping, dry-run behavior, production hostname enforcement, live application,
and persistent feature activation.
