# GM Command Proof Ledger

Confidence: moderate. This is the non-disruptive validation path for mapped GM
commands.

## Result So Far

Bad news: command names are mapped, but the native payload route is still not
fully proven. Confidence: high.

Good news: proving can proceed without touching players by separating route
proof, isolated admin movement, isolated target mutation, and destructive lab
tests. Confidence: high.

First safe-only execution attempt on `kspld0` failed before publish because the
local admin-RMQ broker was not reachable. Confidence: high. That means no player
impact occurred, and the next non-disruptive step is bringing up or selecting an
isolated broker/route, then rerunning only the safe probe set.

Second safe-only execution attempt on `kspls0` used the empty
`CB_Story_WaterFatManor7` / `testing-waterfat` route. Confidence: high.

- Host was verified as `kspls0`.
- Online roster before and after stayed at four players:
  `Anekeestia`, `Ashlander`, `Rack`, and `Lukano`.
- None of those players were on `testing-waterfat`.
- `PrintAllowedCommands` and `PrintPos` were published through admin-RMQ using
  narrow safe envelopes, then a bounded safe payload matrix.
- The route reported `InGameOrInTransitPlayerCount:0` during the matrix run.
- Queue state stayed clean: `CB_Story_WaterFatManor7_queue` had one consumer and
  zero ready/unacknowledged messages.
- `testing-waterfat` stayed running with restart count `0`, OOM false, exit `0`.
- Logs showed no `PrintAllowedCommands`, `PrintPos`, `ServerCommand`, command
  output, parser error, crash, or fatal line.

Conclusion: admin-RMQ delivery to an empty route is safe, but command execution
is still not proven. Confidence: high. The current running server command line
has `server.NotificationSystem.Enabled=false` and a blank
`ServerCommandsAuthToken`, so the negative result is expected. Confidence: high.

Use the proof runner:

```bash
python3 scripts/prove-gm-commands.py --format markdown
```

That command only generates the ledger. It does not publish anything.

## Non-Disruptive Proof Order

1. Safe route proof:
   `PrintAllowedCommands` and `PrintPos` are the only commands allowed for
   live-route smoke tests. Run with `--execute-safe` only after selecting the
   exact route and admin/test player.

2. Empty-route subsystem proof:
   Recreate only an empty target map with
   `DUNE_SERVER_NOTIFICATION_SYSTEM_ENABLED=true` and a private
   `DUNE_SERVER_COMMANDS_AUTH_TOKEN`. Then send only `PrintAllowedCommands` and
   `PrintPos` through the game-RMQ notification/server-command path. Do not use
   occupied routes.

3. Isolated admin session:
   Movement-mode and admin travel commands must be tested on an isolated
   admin/test character on an empty lab route or private map. This covers
   `Fly`, `Ghost`, `Walk`, `TeleportToExact`, `TeleportToMap`, travel helpers,
   patrol/sandworm/personal-marker teleports, and similar commands.

4. Isolated target mutation:
   Inventory grants, basic kit grants, vehicle spawn, and player-target
   teleports require a disposable test character or disposable spawned object.
   These do not run against normal players.

5. Destructive lab only:
   `DestroyTargetVehicle`, `DestroyTotem`, `DestroyPlaceable`,
   `DestroyEntireBuilding`, and `DestroyBuildingPiece` stay blocked for live
   routes. They can only be proven against disposable lab assets with rollback
   evidence.

6. Static rejected:
   `RemoveSessionMember`, `KickLobbyMember`, and `BattlEyeMegaKick` are not
   shipped dedicated-server GM commands for this build. They are static negative
   evidence only.

## Safe Probe Command

Example safe execution against a chosen route:

```bash
python3 scripts/prove-gm-commands.py \
  --route Survival_11 \
  --target-player SamplePlayer \
  --admin-player SamplePlayer \
  --execute-safe \
  --command PrintAllowedCommands \
  --command PrintPos \
  --format json
```

The script only executes commands in the safe probe set. Every other command
remains preview-only unless a separate lab-specific harness is added.

## Proof Status Terms

- `safe-route-probe`: may be run as a live smoke test because it should only
  print/log state.
- `isolated-admin-session`: requires an isolated admin/test character and empty
  route.
- `isolated-target-mutation`: requires a disposable target character/object.
- `destructive-lab-only`: blocked outside a disposable lab with rollback.
- `console-static-first`: requires exact argument mapping before execution.
- `static-rejected`: not a working shipped dedicated-server GM command.
