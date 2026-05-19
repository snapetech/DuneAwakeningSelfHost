# Benchmarking

Use this page to keep resource captures comparable. The first goal is not a perfect load test; it is a repeatable enough record to answer what changed between image tags, maps, runtime settings, and player counts.

## Capture Rules

- Record the image tag, host hardware, container runtime, map set, and player count.
- Capture an idle baseline before players join.
- Capture after each player-count step has been stable for at least five minutes.
- Keep `captures/` and `backups/` local.
- Note crashes, restarts, OOM kills, failed transitions, and client-visible latency symptoms.

## Suggested Steps

1. Start the core services and wait for health checks.
2. Start the service layer.
3. Start `survival`.
4. Run `./scripts/status.sh .env` and save the output locally.
5. Run `./scripts/capture-routing.sh .env baseline-idle`.
6. Run `./scripts/discover-player-state.sh .env` once per image tag when player/session schema changes are suspected.
7. Add players in small steps.
8. Run a new capture after each stable step.
9. Attempt one transition path at a time and capture before/after states.

## Template

```text
Date UTC:
DUNE_IMAGE_TAG:
Host CPU:
Host RAM:
Storage:
Kernel:
Container runtime:
Compose version:
Compose files:
World region:
External address type: LAN / public / tunnel

Services started:
Maps started:
Player count:
Duration:

Capture directories:

CPU summary:
Memory summary:
Restart/OOM summary:
Postgres notes:
RabbitMQ notes:
Routing notes:
Client symptoms:
Server log signatures:

Result:
Next action:
```

## What To Compare

Resource cost:

- CPU percent per service.
- RSS/memory per service.
- Restart count and OOM state.
- Network and block IO.
- RabbitMQ queue depth and consumers.
- Postgres readiness and query failures.

Routing:

- `farm_state.ready` and `farm_state.alive`.
- `farm_state.game_addr` and `farm_state.igw_addr`.
- `world_partition` entries per target map.
- RabbitMQ service users/connections for each map.
- Gateway/director/text-router handoff logs.

Player symptoms:

- Login time.
- Loading screen stalls.
- Failed transitions.
- Rubber-banding or delayed interactions.
- Disconnects or reconnect loops.

Player-count probes:

- `farm_state.connected_players`, when present.
- `get_online_player_controller_ids_on_farm()`.
- `get_all_online_or_recently_disconnected_player_online_state()`.
- `get_player_online_state_within_grace_period_for_each_server()`.
- `player_travel_state`, for transition-specific debugging.

Treat these as signals until they are compared against real client presence. The helper `scripts/discover-player-state.sh` exists to find candidate tables/functions without guessing schema details.
