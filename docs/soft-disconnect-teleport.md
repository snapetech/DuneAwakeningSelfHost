# Network-Disconnect Teleport Runbook

This records the first verified online-adjacent teleport primitive found for DASH.

Confidence: high for TestPlayer on Survival/Hagga Basin on 2026-05-21. Confidence: moderate for automation and other maps until repeated.

## Result

The working path is a real network timeout followed by a first-party offline DB move. A DB-only presence flip is not enough.

Verified sequence:

1. Identify the player's active UDP game endpoint from Survival logs or packet capture.
2. Drop that player's UDP game traffic long enough for Unreal to time out the `UNetConnection`.
3. Wait for Survival to update the player from `Online` to `LoggingOut`.
4. Wait for the 30-second logoff timer to finish and for `online_status='Offline'`.
5. Call `dune.admin_move_offline_player_to_partition(...)`.
6. Optionally align controller/player-state actor rows to the pawn transform.
7. Remove the network block.
8. Let the client reconnect or have the player reconnect manually.

The reconnect loaded the moved pawn position and the operator confirmed the character moved.

## Verified Test Case

Date: 2026-05-21

Target:

- Character: `TestPlayer`
- FLS/user id: `TEST_FLS_ID`
- Server id: `o13FuZmcSvCCi5kuofbU5w`
- Map: `Survival_1`
- Partition: `1`
- Dimension: `0`
- Actor rows:
  - controller: `17`
  - player state: `18`
  - pawn: `19`

Observed real disconnect:

```text
2026-05-21 17:16:14 UTC: UNetConnection timed out for CLIENT_IP:CLIENT_PORT, FLS TEST_FLS_ID.
2026-05-21 17:16:14 UTC: player updated to LoggingOut.
2026-05-21 17:16:45 UTC: player updated to Offline.
```

Move staged while offline:

```text
before: X=100000.000 Y=100000.000 Z=9191.031
after:  X=100000.000 Y=112000.000 Z=9191.031
delta:  +12000 Y
```

Reconnect proof from Survival logs:

```text
Player TEST_FLS_ID attempting to log in with stored pawn info id=19 map=Survival_1, dimension=0, location=X=100000.000 Y=112000.000 Z=9191.031
Updated player TEST_FLS_ID online status to Online
Updated TEST_FLS_ID with 1 servers (X=100000.000 Y=112000.000 Z=8470.877): o13FuZmcSvCCi5kuofbU5w
```

Final DB state after reconnect:

```text
online_status=Online
server_id=o13FuZmcSvCCi5kuofbU5w
actor 17: X=100000.000 Y=112000.000 Z=9191.031 serial=1890
actor 18: X=100000.000 Y=112000.000 Z=9191.031 serial=1890
actor 19: X=100000.000 Y=112000.000 Z=9191.031 serial=1890
```

## What Did Not Work

DB-only presence manipulation is a false positive. Setting `dune.encrypted_player_state.online_status='Offline'` and `server_id=null` can trigger DASH/admin-bot presence automation, but it does not prove the client disconnected and does not make Survival release the live pawn.

Observed failures:

- Raw online actor transform updates were overwritten by the live Survival server.
- Updating `travel_return_info` alongside actor transforms did not move the live player.
- Flipping DB presence to `Offline`, calling the offline helper, then restoring `Online` did not move the player when the live connection remained active.
- Closing the player's RabbitMQ connections caused reconnects at the RabbitMQ layer but did not disconnect the game session.
- Guessed native GM/RabbitMQ command payloads were consumed or ignored and did not produce `PrintPos` or teleport behavior.
- Startup `-ExecCmds` executes console commands, but tested command names did not expose a useful online teleport route.

## First-Party SQL Contract

The useful function is:

```sql
dune.admin_move_offline_player_to_partition(
  in_fls_id text,
  in_target_partition_id bigint,
  in_target_location dune.vector
)
```

It explicitly requires:

```sql
dune.is_player_offline(in_fls_id) = true
```

If the player is still `Online` or `LoggingOut`, it raises:

```text
Player must be Offline
```

The function uses `dune.accounts.user` as the FLS/user id. It finds `player_state.player_pawn_id`, resolves the target partition from `dune.world_partition`, then updates the pawn actor transform/map/dimension/partition.

## Operational Shape

A production helper should use a guarded, auditable flow:

```text
resolve target -> snapshot player/actor state -> find active UDP endpoint -> block endpoint
poll for LoggingOut -> poll for Offline -> call admin_move_offline_player_to_partition
align related actor rows if desired -> unblock endpoint -> poll reconnect/final position
```

Use an advisory lock per account/FLS id. Always clean up network filters in a `finally` path.

Suggested gates:

```env
DUNE_ADMIN_MUTATIONS_ENABLED=true
DUNE_ADMIN_NETWORK_DISCONNECT_ENABLED=true
DUNE_ADMIN_NETWORK_DISCONNECT_TELEPORT_ENABLED=true
DUNE_CHAT_COMMAND_EXECUTE_NETWORK_TELEPORT=true
```

Suggested confirmation phrase:

```text
NETWORK DISCONNECT TELEPORT
```

## Safety Rules

- Do not treat admin-bot join/leave messages as proof of a real game disconnect.
- Only call the offline move helper after `dune.player_state.online_status='Offline'`.
- Snapshot original transform, partition, map, dimension, `server_id`, and actor ids before writing.
- Prefer same-partition moves first. Cross-partition and cross-map moves still need validation.
- Keep the network block scoped to the target endpoint when possible.
- Avoid broad UDP outages except as an emergency/manual test because they affect every player on that Survival process.
- Log the old/new coordinates, timeout time, offline time, unblock time, reconnect time, and final row state.

## Verification Query

```sql
with ps as (
  select *
  from dune.player_state
  where character_name = :character_name
)
select
  ps.online_status,
  ps.server_id,
  a.id,
  a.map,
  a.partition_id,
  a.dimension_index,
  (((a.transform).location).x)::numeric(14,3) as x,
  (((a.transform).location).y)::numeric(14,3) as y,
  (((a.transform).location).z)::numeric(14,3) as z,
  a.serial
from ps
join dune.actors a
  on a.id in (ps.player_controller_id, ps.player_state_id, ps.player_pawn_id)
order by a.id;
```

Expected shape after reconnect:

- `online_status='Online'`.
- `server_id` is the active map server id.
- Pawn row is at the target coordinate.
- Survival may update controller/player-state rows to match after login/save.

## Open Validation

- Repeat with a second player.
- Repeat on another map/partition.
- Validate cross-partition same-map movement.
- Validate cross-map movement.
- Find a cleaner targeted disconnect knob than network packet drop.
- Automate endpoint discovery from Survival logs or packet capture.
