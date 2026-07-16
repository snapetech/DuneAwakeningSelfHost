# Browser Bootstrap Console

The Admin `Bootstrap` page provides the browser first-run workflow included in
the Red-Blink parity target. Open `/bootstrap` after the admin panel and its
Postgres dependency have been created.

The page reports:

- required identity, Steam package, network, FLS, database, and admin-token
  settings without returning secret values;
- Dune database/schema reachability;
- RabbitMQ CA, certificate, and private-key presence;
- current project-labelled Compose services.

The Settings page is the browser form for the required values. Secret inputs
are blank on reads and are replaced only when an operator submits a value.

## Actions

| Action | Implementation | Mutation behavior |
| --- | --- | --- |
| Read-only preflight | `scripts/preflight.sh .env` | No mutation gate |
| Generate missing TLS | `scripts/generate-rabbitmq-cert.sh .env` | Refuses to overwrite existing TLS files |
| Initialize database | `scripts/bootstrap_db.py` in the Funcom DB-utils image | Idempotent when the schema already exists |
| Start/reconcile stack | `scripts/restart-target.sh all` with the start phase | Runs normal post-start health and runtime hooks |

The three mutating actions require:

```env
DUNE_ADMIN_BOOTSTRAP_MUTATIONS_ENABLED=true
```

and confirmation `RUN BOOTSTRAP`. They remain covered by admin-token,
same-origin, allowed-host, request-size, and audit controls.

The bootstrap console does not install Docker or download the proprietary
Funcom Steam package. Those are host prerequisites. On a completely empty
machine, complete the package/image prerequisite from [`setup.md`](setup.md),
create the admin/Postgres services, and then finish configuration and state
initialization in the browser.

If the normal stack already exists, bootstrap actions are still safe to use as
diagnostics: TLS generation refuses existing material, database initialization
detects the existing schema, and the stack action reconciles through repository
startup hooks.
