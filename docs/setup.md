# Setup

This flow assumes you already installed the official Dune: Awakening Self-Hosted Server Steam tool and have Docker Compose available on the Linux host.

## 1. Create Local Env and TLS

```bash
./scripts/populate-local-env.sh
```

Edit `.env` after generation:

- Set `DUNE_STEAM_SERVER_DIR` to the Steam tool install path.
- Set `DUNE_IMAGE_TAG` to the image tag in the Steam package.
- Set `WORLD_NAME`, `WORLD_UNIQUE_NAME`, and `WORLD_REGION`.
- Paste the Funcom self-hosting token into `FLS_SECRET`.
- Set `EXTERNAL_ADDRESS` to the address clients should reach.

## 2. Run Preflight

```bash
./scripts/preflight.sh
```

This checks local commands, required env values, expected Steam image tarballs, and unsafe host bindings.

## 3. Load Official Images

```bash
./scripts/load-images.sh
```

The script expects Funcom's image tarballs under the official Steam package directory. It does not download or redistribute images.

## 4. Start Core State Services

```bash
docker compose --env-file .env up -d postgres admin-rmq game-rmq
```

## 5. Bootstrap Database

```bash
docker compose --env-file .env run --rm db-init
```

The bootstrap runs inside Funcom's `server-db-utils` image and uses the database setup modules bundled there.

## 6. Start Service Layer

```bash
docker compose --env-file .env up -d rmq-auth-shim text-router gateway director
./scripts/status.sh
```

## 7. Experimental Game Server

```bash
docker compose --env-file .env up -d survival
./scripts/status.sh
```

The direct game-server launch is still experimental. The remaining work is reproducing the exact map launch/runtime behavior normally synthesized by Funcom's Kubernetes operator.
