# Build-Pinned CVar and INI Catalogue

DASH provides two complementary build-pinned setting indexes:

- `SERVER_CONFIG_KEY_INDEX.md` contains 2,242 raw INI key entries across 156
  sections from shipped `DefaultGame.ini`.
- `config/cvar-catalog.json` contains console registration candidates recovered
  from the local server ELF, with name, namespace, inferred type/default,
  decoded flags, help, server-relevance label, binary SHA-256, and build tag.

The checked-in CVar catalogue was generated from the locally staged build
`1988751` evidence binary with SHA-256
`0a93c24b41235a6750e23f88bb03c7a80252a65ec477b55c777474ad4882cc11`.
It has 7,028 unique dotted console registrations, 1,132 classified as
server-relevant. Registration recovery is static analysis: a row proves the
name/help/default/flag call-site candidate exists in that binary, not that it
is safe, non-cheat, config-loadable, or effective in the current build.

Search without loading the 2 MB JSON manually:

```bash
python3 scripts/query-cvar-catalog.py sandworm --server-only
python3 scripts/query-cvar-catalog.py --namespace Dune --flag CHEAT --json
```

Regenerate after every Funcom image update from an operator-owned extracted
server binary:

```bash
python3 scripts/build-cvar-catalog.py \
  /path/to/DuneSandboxServer-Linux-Shipping \
  --build-tag <steam-build-or-image-tag> \
  --output config/cvar-catalog.json
```

The builder requires GNU `objdump`, validates a 64-bit ELF, refuses an
implausibly small result, writes atomically, and binds output to the binary
SHA-256. It does not extract or distribute the executable. Its registration
analysis is adapted from the MIT-licensed Sponge tooling; attribution is in
`THIRD_PARTY_NOTICES.md`.

Use `SERVER_CONFIG_KEYS.md` and `docs/server-knobs-audit.md` for promoted or
reviewed settings. Do not paste arbitrary catalogue rows into live INI files:
`CHEAT`/`READONLY` flags, client/server symmetry, value types, and restart scope
still matter. Typed panel settings and gameplay presets remain allowlisted,
backup-first mutation paths.
