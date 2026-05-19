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

## 7. Single Survival Server

```bash
docker compose --env-file .env up -d survival
./scripts/status.sh
```

This starts only the `Survival_1` map. It is useful for proving the core service layer, token, RabbitMQ auth, and public game address before expanding the farm.

For a one-server test world, prune the unused generated `Survival_1` dimensions:

```bash
./scripts/single-survival-partition.sh .env
```

## 8. Expanded Standing Farm

The official Kubernetes template defines several single-dimension travel targets, and the Kubernetes operator normally starts some of them on demand. The Compose layout keeps one container for each target running so Director can assign every partition without Kubernetes.

Prepare the matching partition rows:

```bash
./scripts/full-world-partitions.sh .env
```

Start the full standing farm:

```bash
docker compose --env-file .env up -d \
  survival overmap arrakeen harko-village \
  testing-hephaestus testing-carthag testing-waterfat \
  deep-desert proces-verbal

./scripts/status.sh .env
```

Expected server-side status:

```text
farm_ready_alive=9 active_servers=9 partitions=9
```

This proves server-side registration and partition assignment. It does not by itself prove client travel; test login and each travel path from the live game client.

## 9. Admin Panel

```bash
docker compose --env-file .env up -d admin-panel
```

Open `http://127.0.0.1:18080`, or put a trusted LAN/VPN reverse proxy in front of it as `http://duneadmin.home`. See `docs/admin-panel.md`.
