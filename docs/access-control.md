# Access Control

The supported access-control knob found in the official server package is a battlegroup login password:

```ini
[ConsoleVariables]
Bgd.ServerLoginPassword="..."
```

This repository wires that setting through `.env` as:

```env
DUNE_SERVER_LOGIN_PASSWORD=
```

The live server build currently needs the value passed as a launch `-ini:` override for the Director/FLS password-protection flag to come up correctly:

```text
-ini:engine:[ConsoleVariables]:Bgd.ServerLoginPassword=${DUNE_SERVER_LOGIN_PASSWORD}
```

`scripts/run_server_safe.sh` also writes the value into the generated server config before launching the game process:

- `DuneSandbox/Saved/Config/LinuxServer/Engine.ini`
- `DuneSandbox/Saved/UserSettings/UserEngine.ini`

Operational caveat: Unreal logs the full startup command line. Treat local Docker logs as sensitive while this launch override is required.

## Admin Panel

The admin panel exposes `DUNE_SERVER_LOGIN_PASSWORD` under Settings -> Safe Env Settings. It is protected by the admin token like the rest of the settings API.

Changing the value updates `.env`, but it does not update already-running game-server processes. Recreate the game containers after a password change:

```bash
docker compose -f compose.yaml -f compose.allmaps.yaml --env-file .env up -d --force-recreate \
  survival overmap arrakeen harko-village \
  testing-hephaestus testing-carthag testing-waterfat deep-desert proces-verbal \
  lostharvest-ecolab-a lostharvest-ecolab-b lostharvest-forgottenlab art-of-kanly \
  dungeon-hephaestus dungeon-oldcarthag faction-outpost-atre faction-outpost-hark \
  heighliner-dungeon ecolab-green-089 ecolab-green-152 ecolab-green-024 \
  ecolab-green-195 ecolab-green-136 overland-m-01 overland-s-04 overland-s-06 \
  bandit-fortress overland-s-07 overland-s-08 dungeon-thepit
```

Then verify:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/status.sh .env
```

## Character Transfers

The login password is not the character-transfer policy. Director has separate inbound and outbound transfer controls in `config/director.ini`.

This repository currently defaults inbound character transfers to disabled:

```ini
[ Battlegroup ]
IncomingCharacterTransfers=0
```

The admin panel exposes the Director character-transfer settings under Settings -> Director Character Transfers. See `docs/character-transfers.md` for the full setting list and the inbound rulesets:

```text
0 = DenyAll
1 = AllowFromPrivateOnly
```

## Limitations

No native player allowlist/whitelist setting has been identified in the shipped config surface yet. Treat the login password as the primary supported login restriction.

Network-level source-IP allowlisting is possible at the router/firewall, but it is brittle for players with dynamic IP addresses and should be used only if password protection is not enough.
