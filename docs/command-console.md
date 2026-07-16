# Bounded Command Console

The Command Console gives authenticated operators a browser workflow for a
small set of reviewed host diagnostics. It is not a raw shell or terminal.
Operators select a committed command ID; they cannot provide command text,
arguments, environment variables, paths, stdin, pipes, redirects, or shell
substitutions.

## Command allowlist

The implementation and authoritative catalog are in
[`../admin/command_console.py`](../admin/command_console.py).

| Command ID | Operation | Timeout |
| --- | --- | --- |
| `landsraad-cycle` | Validate the seven-day Landsraad/Coriolis invariant from the exact committed config targets. | 20 seconds |
| `stack-status` | Read farm/database health and project services through existing bounded admin/Docker APIs. | 45 seconds |
| `rmq-health` | TCP-probe both RMQ services and read their project-container state. | 20 seconds |
| `inventory-audit` | Query duplicate, negative, and over-capacity inventory counts without repair. | 30 seconds |
| `storage-status` | Read workspace/backup/container storage metadata without cleanup. | 20 seconds |
| `cpu-affinity-status` | Read project-container CPU sets through the Docker API. | 20 seconds |

Every command maps to one exact native read-only handler in the admin process.
No subprocess or shell is created. The handlers reuse the already bounded
config parser, read-only SQL query layer, Docker socket API, TCP probes, and
backup inventory functions. A one-worker executor applies the command-specific
timeout, and the command ID is the only value passed into the dispatch layer.

## Output and audit behavior

The handler's structured JSON result is capped at 65,536 bytes. Before returning it, DASH
redacts values from environment keys that look like passwords, secrets, tokens,
credentials, authorization values, or private keys. It also redacts URL userinfo
passwords, Authorization header credentials, and PEM private-key blocks.

The output is returned to the requesting browser but is not persisted. The
normal admin audit receives only the command ID, principal ID, success state,
return code, timeout state, and duration. This keeps diagnostic output and any
unexpected runtime data out of retained audit/webhook records.

Timeouts return code `124`. Handler exceptions become redacted code `1`
receipts rather than escaping into an unstructured server error.

## Configuration and permissions

```dotenv
DUNE_COMMAND_CONSOLE_ENABLED=true
```

`GET /api/ops/console` lists the allowlist and its availability. Reading the
catalog requires the normal `read` capability. Executing
`POST /api/ops/console` requires `operations.write`; observer identities cannot
run commands. The endpoint accepts only:

```json
{"commandId":"landsraad-cycle"}
```

An unknown command ID fails closed. The feature does not use
`DUNE_ADMIN_MUTATIONS_ENABLED` because every catalog entry is explicitly
read-only. Adding a state-changing command requires a separate mutation gate,
confirmation phrase, rollback contract, tests, and documentation; none are
present in this catalog.

`scripts/enable-feature-parity.sh .env --execute` enables the console but does
not execute a command.

## Dashboard

Open **Command Console**, review the catalog, select a named diagnostic, and
choose **Run selected command**. The page displays the structured receipt and
redacted output for the current browser session. It never renders a free-form
terminal input.

## Validation

```bash
make test-command-console
python3 scripts/test-admin-panel-safe-surfaces.py
docker compose --env-file .env config >/dev/null
```

The focused suite verifies the fixed native catalog, exact-ID-only dispatch,
no subprocess/shell surface, unknown-command refusal, exception handling,
redaction, output truncation, and bounded timeout result.

For a production canary, run `landsraad-cycle` through the authenticated API,
verify a zero return code, and independently run:

```bash
scripts/validate-landsraad-coriolis-cycle.sh .env
```

No game-map restart is required to deploy or use the console.

Change Intelligence response plans may link to a catalog command. The
Infrastructure page opens Command Console and preselects only that exact fixed
ID. It does not run the command, add arguments, or weaken the
`operations.write` requirement. See
[`incident-response.md`](incident-response.md).
