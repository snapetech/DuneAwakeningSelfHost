# Character Transfers

Character-transfer policy is controlled by Director, not by the game-server login password.

The Compose-mounted Director config is:

```text
config/director.ini
```

The relevant section is `[ Battlegroup ]`.

## Current Default

This repository allows inbound transfers from public/official and private/self-hosted battlegroups:

```ini
IncomingCharacterTransfers=40
```

That requests the Director binary's combined public-and-private origin ruleset. Older local notes incorrectly mapped the rulesets as `0/1/2/3`; live testing showed those small values are undefined for the current enum and FLS rejects them during `CharacterTransfers_RequestTransfer`.

## Settings

These settings are exposed in the admin panel under Settings -> Director Character Transfers and are written to `config/director.ini` with a backup under `backups/admin-panel`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `ShouldDeleteOriginCharactersDuringTransfers` | `true` | Deletes the origin character after a successful transfer into this battlegroup. |
| `AcceptOutgoingCharacterTransfers` | `true` | Allows characters on this battlegroup to transfer out. |
| `IncomingCharacterTransfers` | `40` | Controls which origin server types may transfer characters into this battlegroup. |
| `ExportCharacterTimeout` | `900` | Seconds before the export query times out. |
| `ImportCharacterTimeout` | `900` | Seconds before the import query times out. |
| `FreeToTransferCharactersFrom` | `true` | Skips transfer token cost for transfers from this battlegroup. |
| `FreeToTransferCharactersTo` | `true` | Skips transfer token cost for transfers to this battlegroup. |
| `ValidateBeforeImportCharacterTimeout` | `180` | Seconds before canceling a transfer stuck in validation before import starts. |
| `ActiveTransfersResolveProcessFrequencySeconds` | `10` | Seconds between resolving unhandled active transfers. |
| `CharacterTransferDbFunctionTimeLogThresholdMs` | `10000` | Milliseconds before character-transfer DB function timing is logged. |

## Incoming Rulesets

The Director binary for build `1973075` exposes these inbound rulesets, and its config parser expects the numeric enum value:

```text
0 = Default
10 = DenyAll
20 = AllowFromPrivateOnly
30 = AllowFromOfficialOnly
40 = AllowFromPrivateAndOfficial
50 = AllowAll
```

Use `10` for a closed world, `20` to allow only private/self-hosted origins, `30` to allow only public/official origins, or `40` to request both. `50` is exposed as `AllowAll`; treat it as broader than the normal public/private split until verified.

Live official-origin transfer requests with `IncomingCharacterTransfers=2` failed against FLS with `INVALID_ARGUMENT` and `Could not parse ETransferOriginRuleset from int value`. Decompiling Director build `1973075` showed the valid enum value for official-only is `30`, not `2`; use the values above.

## Apply Changes

Changing transfer settings updates `config/director.ini`, but already-running Director processes do not pick up file changes automatically. Recreate Director after a change:

```bash
docker compose --env-file .env up -d --no-deps --force-recreate director
```

Then check service health:

```bash
./scripts/status.sh .env
```

## Monitor Attempts

When a tester is about to retry a transfer, run the transfer monitor on the live host before they click through:

```bash
scripts/monitor-character-transfers.sh --env-file .env --interval 2 --since 15m
```

It writes a timestamped evidence directory under `backups/character-transfer-monitor/` with:

- `config.txt`: active transfer settings, compose files, Director container state, and git status at monitor start.
- `events.log`: relevant Director/FLS transfer log lines plus transfer-state changes.
- `state.jsonl`: one `dune.character_transfer_imports` snapshot every polling interval.

The monitor is read-only. By default it redacts 16-hex player/FLS ids in Director logs; add `--full-ids` only when exact player correlation is required.

## Related Access Controls

`DUNE_SERVER_LOGIN_PASSWORD` restricts who can log into the battlegroup. It does not distinguish fresh characters from transferred/imported characters.

Network source-IP allowlisting can be done outside this repo at the router/firewall, but it is brittle for players with dynamic IP addresses.
