# Troubleshooting

Start with:

```bash
./scripts/status.sh
```

The status helper prints container state, selected database rows, RabbitMQ connections, and recent high-signal logs with known token/password patterns redacted.

## Image Tarball Not Found

Symptom:

```text
missing image tar: ...
```

Check `DUNE_STEAM_SERVER_DIR` in `.env`. It must point at the official Steam tool install directory that contains `images/battlegroup` and `images/prerequisites`.

## Compose Config Fails

Run:

```bash
docker compose --env-file .env.example config --quiet
docker compose --env-file .env config
```

If `.env` is missing, run:

```bash
./scripts/populate-local-env.sh
```

## FLS Token Rejected

Symptoms often include logs mentioning invalid token, failed FLS registration, or account entitlement problems.

Check:

- `FLS_SECRET` is set in `.env`.
- The token came from the live Dune: Awakening account portal.
- The Steam account used for token generation owns the self-hosted server entitlement.
- `EXTERNAL_ADDRESS` is reachable by clients.

## RabbitMQ Auth Failures

Symptoms:

```text
ACCESS_REFUSED
PLAIN login refused
```

Check:

- `rmq-auth-shim` is running.
- `text-router` is running before game-server startup.
- `WORLD_UNIQUE_NAME` matches the expected service-user prefix.
- RabbitMQ ports are not exposed publicly.

The shim is a local compatibility workaround for `sg.<world>.<server-id>.game` and `sg.<world>.<server-id>.admin` users. Keep it paired with localhost-only RabbitMQ host bindings.

## Database Already Initialized

`db-init` is idempotent for an existing schema. If you need a fresh world, stop Compose and remove local runtime data:

```bash
docker compose --env-file .env down
rm -rf data/postgres data/rabbitmq data/server-saved
```

This deletes local server state.

## Survival Server Starts But Is Not Reachable

Check:

- Router/firewall forwards only `7777/udp` and `7888/udp`.
- `EXTERNAL_ADDRESS` matches the address clients should use.
- `./scripts/status.sh` shows `farm_state.ready` and non-empty game/IGW addresses.
- RabbitMQ and Postgres ports remain local-only.

## Permission Denied Under `data/postgres`

Postgres files are owned by the container user. This is normal. Avoid committing or manually editing `data/`.
