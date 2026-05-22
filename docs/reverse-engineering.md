# Reverse Engineering Workflow

This repo now treats server behavior research as a promotion pipeline instead
of one-off poking.

## Evidence States

| State | Meaning |
| --- | --- |
| `candidate` | A string, asset name, log phrase, or public hint exists. |
| `loadable` | The server accepts the key, command, or route without parse/delivery errors. |
| `observable` | Logs, DB rows, RMQ delivery, or runtime state prove the surface was read or invoked. |
| `validated` | A controlled before/after test proves the gameplay or admin effect. |
| `admin-safe` | Dry-run, gate, audit, rollback, and operator docs exist. |

The machine-readable catalog is `research/surfaces.json`. Render or validate it:

```bash
python3 scripts/research_catalog.py --validate
python3 scripts/research_catalog.py --format markdown
python3 scripts/research_catalog.py --promotion-target admin-safe
```

## Collectors

All collectors are read-only unless their output is redirected by the operator.

```bash
scripts/research/extract-server-configs.sh .env deep-desert
scripts/research/extract-binary-strings.sh .env deep-desert 'Coriolis|Shifting|Spice'
python3 scripts/research/dump-db-surface.py .env
python3 scripts/research/snapshot-rmq-topology.py .env --broker admin
python3 scripts/research/index-server-logs.py data/server-saved/Logs
```

Store bulky run output under ignored paths such as
`backups/research/<timestamp>/` or `captures/research/<timestamp>/`. Do not
commit Funcom binaries, cooked assets, raw proprietary dumps, or secrets.

## Promotion Rules

- Binary strings are leads only until section, syntax, and runtime effect are
  proven.
- DB functions are not safe just because they exist; use dry-run and disposable
  characters before writes.
- RabbitMQ delivery is not command execution; require a response or server log
  proving the handler ran.
- Config keys that affect map lifecycle, Coriolis, wipes, travel, ownership, or
  inventory stay blocked until rollback is documented.
