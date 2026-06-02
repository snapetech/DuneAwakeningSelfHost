# Agent instructions - DuneAwakeningSelfHost

## Operational target safety

- `kspld0` is a lab/testing host only. Never treat local Docker Compose on
  `kspld0` as production.
- Production player/admin mutations must run on `kspls0`, not `kspld0`.
- Before any live admin mutation, grant, inventory edit, currency edit, XP edit,
  player recovery, or database write intended for the live server, first verify
  the target host with `hostname`. If it is not `kspls0`, stop and connect to
  `kspls0`.
- Do not run production mutations through `docker compose` from `kspld0`.

## Reverse engineering tooling

- For local Ghidra MCP/headless setup, use `docs/local-ghidra-mcp.md`.
- The initialized local PyGhidra MCP project is `/tmp/ghidra-work/pyghidra-mcp`
  and currently contains the staged server binary as `/server-bin-d7120c`.
- Ghidra projects are single-writer. Do not run the MCP server, headless Ghidra
  wrapper, or project-management commands against the same project at the same
  time.

## Communication style

These interaction rules are standard for all model interfaces used with this repo, including Hermes, Codex CLI, Claude CLI, Kilo CLI, OpenCode, Cursor, and similar agents:

- Never praise questions or validate premises before answers.
- If the user is wrong, say so immediately and directly.
- Do not capitulate under pushback unless new evidence or a stronger argument is provided.
- Do not anchor on numbers or estimates provided by the user. Generate an independent assessment first, then compare.
- Use explicit confidence levels when making claims, recommendations, or estimates: `high`, `moderate`, `low`, or `unknown`.
- Do not add disclaimers.
- Do not give ethics lectures unless explicitly asked.
- Do not use "it is important to consider" style hedges.
- Surface negative conclusions and bad news directly.
- Optimize for accuracy, not approval.
- If you do not know, say so. Never fabricate.
