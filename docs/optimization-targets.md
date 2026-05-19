# Optimization Targets

This document tracks practical places to improve the self-host runtime before attempting any game-binary changes.

## Current Findings

- The game-server image is the storage outlier: `seabass-server:1963158-0-shipping` is about 10.3GB locally.
- Service-layer images are much smaller: gateway is about 104MB, DB utilities about 165MB, RabbitMQ about 274MB, text-router about 301MB, and director about 312MB.
- Idle runtime memory is dominated by the game-server container. A local `survival` instance has been observed around several GiB RSS while service-layer containers are small by comparison.
- A memory-detail profile observed the game process with a much higher high-water mark than current RSS. Do not set tight limits from a single idle sample.
- Image history shows the game image includes a roughly 4GB content layer, a roughly 1.2GB tooling/debug package layer, a 123MB Engine layer, and a 374MB binary/symbol layer.
- RabbitMQ runs twice, once for admin traffic and once for game traffic. That is probably correct for topology parity, but it is a measurable fixed overhead for small self-host worlds.
- The current single-server Compose world does not need the extra generated `Survival_1` dimensions. Pruning unassigned dimensions removes repeated director partition warnings and reduces noise during routing investigation.
- Runtime socket captures show repeated gateway-to-Postgres `TIME_WAIT` connections and at least one TextRouter-to-Postgres `CLOSE_WAIT` in the current local run. Treat these as candidates for connection-pooling or stale-connection investigation.

## Likely Wins

Memory:

- Use `compose.limits.example.yaml` as optional guardrails while profiling. The `survival` limit starts at 12Gi because that matches Funcom's official `Survival_1` workload limit.
- Tighten limits only after measuring startup, idle, one-player, and transition attempts. The game process can spike far above later idle RSS.
- Keep only the map processes actually needed for the test. Use the base nine-map farm or 30-partition warm pool deliberately; each extra game-server process has meaningful memory cost.
- Investigate Unreal command-line flags that disable unattended reporting, crash upload paths, or unused subsystems only if the image already exposes supported toggles.

Storage:

- Do not copy or rebuild Funcom images locally; load the official tarballs and keep orchestration separate.
- Keep backups and captures compressed and ignored.
- Profile writable container paths before deciding whether any volume can be made read-only or tmpfs-backed.
- Avoid persisting RabbitMQ state across disposable tests unless queue durability is needed for the scenario.
- A derived Docker image that deletes files will not reclaim base-layer size. Any local slimming experiment needs an export/import or squash-style flow and must remain local-only.

Network:

- Keep Postgres and RabbitMQ on the Compose network and bind debug/admin ports only to `127.0.0.1`.
- Keep public router forwarding limited to gameplay UDP ports.
- Capture socket state before changing peering/routing; the game advertises public client address and internal IGW/S2S address separately.
- Compare Docker bridge NAT with host networking only after routing parity is understood.
- Investigate gateway database connection churn before changing kernel TCP settings. If the app opens short-lived DB connections by design, sysctl tuning only masks the symptom.
- Watch TextRouter `CLOSE_WAIT` sockets over time. A stable single stale socket is noise; a growing count is a leak or failed close path.
- See `docs/network-investigation.md` for the current socket signatures and next DB/RabbitMQ checks.

Peering and routing:

- Treat `game_addr` and `igw_addr` separately. `game_addr` is the client-facing address; `igw_addr` is the server-to-server address.
- Broken Deep Desert, Arrakeen, Testing Station, or warm-pool travel should be investigated as registration and handoff failures before performance tuning.
- Capture RabbitMQ users, queues, director FLS calls, and `world_partition`/`farm_state` rows around every transition attempt.

## Profiling Command

```bash
./scripts/profile-runtime.sh .env
./scripts/summarize-runtime-profile.sh captures/YYYYMMDDTHHMMSSZ-runtime-profile
```

Profiles are written under `captures/`, which is ignored by git. Review before sharing because process and socket dumps can include paths, addresses, image digests, and world/service identifiers.

Live network watch:

```bash
./scripts/watch-network.sh .env
```

Optional memory guardrail run:

```bash
docker compose --env-file .env -f compose.yaml -f compose.limits.example.yaml up -d
```

## Do Not Do Yet

- Do not patch or redistribute Funcom binaries.
- Do not expose RabbitMQ or Postgres publicly.
- Do not remove service-layer components until their routing role is understood.
- Do not assume lower memory equals better behavior; validate login, farm readiness, and travel after every runtime change.
