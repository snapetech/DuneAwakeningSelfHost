# Network-Disconnect Teleport Runbook

This records the first verified online-adjacent teleport primitive found for DASH.
The mechanism is useful, but it is not a soft disconnect.

Confidence: high for the verified Survival/Hagga Basin teleport test on 2026-05-21. Confidence: moderate for automation and other maps until repeated.

Update 2026-05-24: the non-base logoff wait is a separate server-side logoff timer, not the reconnect grace period. The active build has runtime unsafe-location timer values of `30.0` seconds and `300.0` seconds. A guarded runtime patch script now sets both values to `0.0` on the active `kspls0` Survival and Deep Desert containers.

## Result

The working path is a targeted network timeout followed by a first-party offline DB move. A DB-only presence flip is not enough.

This is a verified teleport mechanism, not a verified soft-reconnect mechanism. The player can be dumped to a disconnected/server-offline style screen and may need to reconnect manually. Use it only when that UX is acceptable, or keep it behind an explicit operator confirmation until a native targeted kick/session-close path is found.

Verified sequence:

1. Identify the player's active UDP game endpoint from Survival logs or packet capture.
2. Drop that player's UDP game traffic inside the target map server network namespace long enough for Unreal to time out the `UNetConnection`.
3. Wait for Survival to update the player from `Online` to `LoggingOut`.
4. Wait for the logoff timer to finish and for `online_status='Offline'`.
5. Call `dune.admin_move_offline_player_to_partition(...)`.
6. Remove the network block.
7. Let the client reconnect or have the player reconnect manually.

The reconnect loaded the moved pawn position and the operator confirmed the character moved.

## Mechanism Notes

The safest verified packet scope is inside the target map server's network namespace, not a broad host or router outage. On the tested Survival server, two exact rules were enough to affect only the target client tuple:

```text
INPUT:  client_ip:client_port -> server_ip:7777
OUTPUT: server_ip:7777 -> client_ip:client_port
```

The tested `DROP` window hit the exact target packets and produced:

```text
UNetConnection::Tick: Connection TIMED OUT. Closing connection.
NetworkFailure: ConnectionTimeout
Updated player TEST_FLS_ID online status to LoggingOut
Updated player TEST_FLS_ID online status to Offline
```

Observed timing on 2026-05-21:

- `12s` targeted `DROP` reached the server timeout threshold and started logoff.
- Survival then kept the character in `LoggingOut` for roughly `30s`.
- The offline move helper succeeded after `online_status='Offline'`.

The 2026-05-24 runtime patch changes the unsafe-location wait target to `0.0` for the active process lifetime. With that patch applied, expected behavior is that unsafe-location disconnects become `Offline` immediately after the game enters `OnLeavingGame`, matching the base/safe-location path. Confidence: moderate-high until repeated live non-base logoff lines show `SetLeavingGameTimer ... to <same timestamp>` in both Hagga and Deep Desert.

Targeted `REJECT --reject-with icmp-port-unreachable` did hit packets but did not make the game session close during the tested window. Host-level `DOCKER-USER` and `FORWARD` rules missed the hairpin path in this deployment; the map server netns rules hit reliably.

## Verified Test Case

Date: 2026-05-21

Target:

- Character: `test player`
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

Setting only `[/Script/DuneSandbox.PlayerOnlineStateSettings]` reconnect grace values to `0` is also insufficient for immediate non-base despawn. Those settings remove reconnect/persistence grace, but live logs showed `ADunePlayerCharacter::SetLeavingGameTimer` still scheduling unsafe-location timers of roughly `30s` in Hagga and `5m` in Deep Desert before recording `logoff_persistence_end_time`.

Observed failures:

- Raw online actor transform updates were overwritten by the live Survival server.
- Updating `travel_return_info` alongside actor transforms did not move the live player.
- Flipping DB presence to `Offline`, calling the offline helper, then restoring `Online` did not move the player when the live connection remained active.
- Closing the player's RabbitMQ connections caused reconnects at the RabbitMQ layer but did not disconnect the game session.
- Guessed native GM/RabbitMQ command payloads were consumed or ignored and did not produce `PrintPos` or teleport behavior.
- Guessed `kick`, `RemoveSessionMember`, and `KickLobbyMember` payloads sent to the admin RPC route and the game server queue were routed or consumed but did not close the target game session.
- Targeted ICMP `REJECT` and conntrack flow deletion did not trigger a useful soft reconnect in the tested deployment.
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
unblock endpoint -> poll reconnect/final position
```

Use an advisory lock per account/FLS id. Always clean up network filters in a `finally` path.

The current verified block primitive is timeout-shaped. Name UI and audit events accordingly, for example `network-timeout-teleport`, not `soft-teleport`.

## Immediate Logoff Runtime Patch

The runtime patch is build-specific and process-local. It does not edit the shipped binary or config files, and it must be reapplied after Survival or Deep Desert restarts.

Status as of 2026-06-01: patched live for the current build. The old
data-pointer offsets moved in build `9bf5fbdef43a6d6d64459df973f3d252c01ab4ad`;
the current data-pointer offsets are:

- `0x16521698`: 30-second unsafe-location timer array.
- `0x165216b0`: 300-second unsafe-location timer array.

Live validation on `kspls0` found both pointers in `dune_server-survival-1` and
`dune_server-deep-desert-1`; before patch they contained:

```text
30 30 0 0
300 300 0 0
```

After applying `scripts/patch-logoff-timers-runtime.sh --host kspls0` they read:

```text
0 0 0 0
0 0 0 0
```

The target containers remained running after the data-pointer patch. Confidence
is high that the runtime values are patched to zero. Confidence is moderate-high
that this restores immediate unsafe-location logoff, pending a live player
disconnect proof showing no future `SetLeavingGameTimer` / persistence end time.

Ghidra showed the current call path:

- `ADunePlayerCharacter::OnLeavingGame`: Ghidra `0x0d60f270`, ELF/runtime offset `0x0d50f270`.
- `ADunePlayerCharacter::SetLeavingGameTimer`: Ghidra `0x0d60f810`, ELF/runtime offset `0x0d50f810`.
- Duration accessor called before `SetLeavingGameTimer`: Ghidra `0x13049050`, ELF/runtime offset `0x12f49050`.

The accessor at runtime offset `0x12f49050` returns a pointer-like duration
payload from either `object + 0x800` or `*(object + 0x320) + 0x138`. The
`SetLeavingGameTimer` helper then calls the float-duration reader at runtime
offset `0x0d510870`; that helper chooses between the two moved global pointers
above and reads their first float.

Follow-up validation on 2026-06-01 showed the data-pointer patch alone was not
enough for deliberate client "Exit to main" quits in Deep Desert. The client
still showed the five-minute warning, and a live quit at `2026.06.01-23.11.36`
recorded:

```text
SetLeavingGameTimer ... to 2026.06.01-23.16.11 - reason: OnLeavingGame
RecordLogoffPersistenceEndTime ... to 2026.06.01-23.16.11
```

The current script also patches `ADunePlayerCharacter::SetLeavingGameTimer`
itself at ELF/runtime offset `0x0d50f864`. The original instruction is:

```text
48 01 c1    add rax, rcx
```

That computes `deadline = now + rounded_duration`. The patched instruction is:

```text
48 89 c1    mov rax, rcx
```

That preserves the surrounding function and forces `deadline = now` for both
unsafe disconnects and deliberate exit quits. A live Deep Desert quit after this
clamp at `2026.06.01-23.19.25` recorded:

```text
SetLeavingGameTimer ... to 2026.06.01-23.19.25 - reason: OnLeavingGame
RecordLogoffPersistenceEndTime ... to 2026.06.01-23.19.25
```

The client-side dialog text still displayed the five-minute warning during that
test. Treat that warning as stale UI until client-side assets/config are found.
The server-side persistence deadline was immediate.

Additional validation on 2026-06-01 showed that clamping only the recorded
deadline still allowed the actual timer-manager callback to use the original
duration. A Deep Desert logout at `2026.06.01-23.28.18` recorded an immediate
deadline but stayed `LoggingOut` for roughly five minutes and flipped `Offline`
around `2026.06.01-23.35.07`.

The current script therefore also patches the timer-registration duration reload
inside `SetLeavingGameTimer` at ELF/runtime offset `0x0d50fcba`. The original
instruction is:

```text
c5 fa 10 45 d4    vmovss -0x2c(%rbp),%xmm0
```

That reloads the saved duration before the timer-manager call. The patched bytes
are:

```text
c5 f8 57 c0 90    vxorps %xmm0,%xmm0,%xmm0; nop
```

That forces the registered timer duration to `0.0`. Live dry-run verification on
`kspls0` after applying showed both `dune_server-survival-1` and
`dune_server-deep-desert-1` with:

```text
deadline clamp bytes: 48 89 c1
timer duration bytes: c5 f8 57 c0 90
```

Confidence is high that future `SetLeavingGameTimer` calls now schedule a zero
delay timer. A fresh login/quit test after this duration patch is still needed
to confirm the DB moves from `LoggingOut` to `Offline` immediately.

Rejected attempt: on 2026-06-01, a live runtime patch changed the accessor entry
at runtime offset `0x12f49050` from:

```text
55 48 89 e5 f6 87 a4 02 00 00 10 75 1a
```

to:

```text
31 c0 c3 ...
```

That is `xor eax,eax; ret`. It matched the expected bytes in
`dune_server-survival-1` and `dune_server-deep-desert-1`, but both processes
exited with signal `139` shortly afterward. The containers were recreated and
started again immediately. Do not reapply that code-return patch.

That failed code patch was reverted by recreating the two containers. The safe
current path is the data-pointer patch, not a return-value code patch.

Script:

```bash
./scripts/patch-logoff-timers-runtime.sh --host kspls0
```

Dry run:

```bash
./scripts/patch-logoff-timers-runtime.sh --host kspls0 --dry-run
```

The script guards against the wrong server build with the current expected ELF Build ID:

```text
f8298652f037c94b1c54264e06e8d020574d938b
```

It only targets these active production containers:

```text
dune_server-survival-1
dune_server-deep-desert-1
```

For the old 2026-05-24 build, it read two runtime float arrays through `gdb`. Before that patch, both containers had:

```text
30 30 0 0
300 300 0 0
```

After applying, both containers confirmed:

```text
0 0 0 0
0 0 0 0
```

Confidence: high that the memory values were changed. Confidence: moderate-high that these are the exact unsafe-location logoff durations, because the values are read by the duration function immediately before `ADunePlayerCharacter::SetLeavingGameTimer`. Final proof is a live disconnect outside a base showing no future timestamp in `LogLogOffSystem`.

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
- Do not call this a soft disconnect. It is a targeted hard timeout until a native session-close/kick path is proven.
- Only call the offline move helper after `dune.player_state.online_status='Offline'`.
- Snapshot original transform, partition, map, dimension, `server_id`, and actor ids before writing.
- Prefer same-partition moves first. Cross-partition and cross-map moves still need validation.
- Keep the network block scoped to the target endpoint and target map server namespace.
- Avoid broad UDP outages except as an emergency/manual test because they affect every player on that Survival process.
- Always remove packet rules even if the move fails. Verify the namespace rules are back to default before ending the operation.
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
- Find a cleaner targeted disconnect knob than network packet drop, preferably a native `UNetConnection::Close`, game-session kick, or Online Services `RemoveSessionMember`/`KickLobbyMember` path.
- Automate endpoint discovery from Survival logs or packet capture.
