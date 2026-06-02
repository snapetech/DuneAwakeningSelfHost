# Local Ghidra MCP

Confidence: high.

Use a local Ghidra MCP as operator tooling, not as an application framework
inside this repo. The repo-owned surface stays limited to repeatable scripts,
signatures, evidence docs, and wrappers. The MCP process should live in the
operator's local MCP config and should bind only to localhost.

## Decision

Confidence: high.

- Use `pyghidra-mcp` for local agent access when an MCP client needs direct
  Ghidra API access.
- Keep Ghidra scripts in `scripts/research/`.
- Keep large projects, imported binaries, decompiler caches, raw findings, and
  proprietary binary artifacts under ignored paths such as `/tmp/ghidra-work/`,
  `captures/`, or `backups/`.
- Do not commit Funcom binaries, cooked assets, raw Ghidra projects, raw
  proprietary dumps, or MCP client secrets.
- Do not expose a Ghidra MCP port beyond localhost unless the chosen MCP server
  has authentication enabled.

## Headless Wrapper

Confidence: high.

Use `scripts/research/run-ghidra-headless.sh` to run checked-in Ghidra scripts
against a staged binary. It defaults to:

- Ghidra runner: `/opt/ghidra/support/analyzeHeadless`
- work directory: `/tmp/ghidra-work`
- binary: `/tmp/ghidra-work/server-bin`
- project location: `/tmp/ghidra-work/project`
- project name: `DuneServer`
- script path: `scripts/research`

Examples:

```bash
scripts/research/run-ghidra-headless.sh --script DumpGmCommandSurface.java
scripts/research/run-ghidra-headless.sh --script FindLogoffTimers.java --analysis on
scripts/research/run-ghidra-headless.sh --script FindSmugglersRunMp.java --mode process
```

The wrapper imports the binary when the project is missing and processes the
existing program when the project already exists. In `auto` analysis mode it
runs analysis on first import and skips analysis for later process runs.

Use `--dry-run` to inspect the final `analyzeHeadless` invocation.

## Staging A Binary

Confidence: high.

For production binary capture, use the existing packaging script. It copies the
server binary and records checksum/build-id evidence for offline analysis:

```bash
scripts/research/extract-binary-for-ghidra.sh kspls0 /tmp/ghidra-work
```

This is a read-only extraction path. It does not make live server mutations.

For a lab/test binary, stage the binary manually under `/tmp/ghidra-work` and
preserve a checksum:

```bash
mkdir -p /tmp/ghidra-work
cp /path/to/DuneSandboxServer-Linux-Shipping /tmp/ghidra-work/server-bin
sha256sum /tmp/ghidra-work/server-bin > /tmp/ghidra-work/server-bin.sha256
```

## MCP Setup

Confidence: moderate. Exact client config keys vary by MCP host.

Install `pyghidra-mcp` outside this repo. A typical local command is:

```bash
uvx pyghidra-mcp --transport stdio --project-path /tmp/ghidra-work/pyghidra /tmp/ghidra-work/server-bin
```

For an MCP client that uses JSON-style server definitions, the local entry
should be shaped like this:

```json
{
  "mcpServers": {
    "pyghidra-mcp": {
      "command": "uvx",
      "args": [
        "pyghidra-mcp",
        "--transport",
        "stdio",
        "--project-path",
        "/tmp/ghidra-work/pyghidra",
        "/tmp/ghidra-work/server-bin"
      ],
      "env": {
        "GHIDRA_INSTALL_DIR": "/opt/ghidra"
      }
    }
  }
}
```

If using an HTTP transport, bind it to localhost only. Treat an unauthenticated
Ghidra MCP as full Ghidra API access to the loaded program.

## Agent Operating Rules

Confidence: high.

- Prefer checked-in scripts for repeatable investigations.
- Use MCP interactive access for navigation, decompilation, xrefs, string
  lookup, and focused context gathering.
- Record promoted findings in docs with build ID, binary checksum, function
  addresses, image-base notes, and confidence.
- Treat Ghidra decompiler output as evidence, not proof of runtime safety.
- Do not let an MCP mutate production state. Ghidra MCP access should touch only
  local analysis projects and staged binary files.
