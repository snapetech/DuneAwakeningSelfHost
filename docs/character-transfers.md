# Character Transfers

Character-transfer policy is controlled by Director, not by the game-server login password.

The Compose-mounted Director config is:

```text
config/director.ini
```

The relevant section is `[ Battlegroup ]`.

## Current Default

This repository allows inbound transfers from public/official battlegroups:

```ini
IncomingCharacterTransfers=2
```

That allows characters to transfer into this battlegroup from public/official origins.

## Settings

These settings are exposed in the admin panel under Settings -> Director Character Transfers and are written to `config/director.ini` with a backup under `backups/admin-panel`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `ShouldDeleteOriginCharactersDuringTransfers` | `true` | Deletes the origin character after a successful transfer into this battlegroup. |
| `AcceptOutgoingCharacterTransfers` | `true` | Allows characters on this battlegroup to transfer out. |
| `IncomingCharacterTransfers` | `2` | Controls which origin server types may transfer characters into this battlegroup. |
| `ExportCharacterTimeout` | `900` | Seconds before the export query times out. |
| `ImportCharacterTimeout` | `900` | Seconds before the import query times out. |
| `FreeToTransferCharactersFrom` | `false` | Skips transfer token cost for transfers from this battlegroup. |
| `FreeToTransferCharactersTo` | `false` | Skips transfer token cost for transfers to this battlegroup. |
| `ValidateBeforeImportCharacterTimeout` | `180` | Seconds before canceling a transfer stuck in validation before import starts. |
| `ActiveTransfersResolveProcessFrequencySeconds` | `10` | Seconds between resolving unhandled active transfers. |
| `CharacterTransferDbFunctionTimeLogThresholdMs` | `10000` | Milliseconds before character-transfer DB function timing is logged. |

## Incoming Rulesets

The Director binary for build `1968181` exposes these inbound rulesets, but its config parser expects a numeric enum value:

```text
0 = DenyAll
1 = AllowFromPrivateOnly
2 = AllowFromOfficialOnly
```

Use `0` for a closed world, `1` to allow only private/self-hosted origins, or `2` to allow only public/official origins.

The binary also contains `AllowFromPrivateAndOfficial`, but live transfer requests with `IncomingCharacterTransfers=3` have failed against FLS with `INVALID_ARGUMENT` because FLS cannot parse `TransferOriginRuleset: 3`. String values such as `DenyAll` are present in the binary but fail this build's settings reload with a `JsonException`.

## Apply Changes

Changing transfer settings updates `config/director.ini`, but already-running Director processes do not pick up file changes automatically. Recreate Director after a change:

```bash
docker compose --env-file .env up -d --force-recreate director
```

Then check service health:

```bash
./scripts/status.sh .env
```

## Related Access Controls

`DUNE_SERVER_LOGIN_PASSWORD` restricts who can log into the battlegroup. It does not distinguish fresh characters from transferred/imported characters.

Network source-IP allowlisting can be done outside this repo at the router/firewall, but it is brittle for players with dynamic IP addresses.
