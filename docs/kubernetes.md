# Kubernetes Deployment Notes

This repository runs the server with Docker Compose. These notes document how to move the same pod set into a normal Kubernetes cluster, but Kubernetes manifests are not currently maintained or tested here.

Use this as a design map, not as a supported production deployment.

## Scope

The official Steam package is already Kubernetes-oriented and includes an operator-driven `BattleGroup` flow. This repository flattens that behavior into explicit services, config files, env values, and helper scripts. A cluster deployment should preserve that explicitness unless you decide to reintroduce the official operator.

## Workload Mapping

| Compose service | Kubernetes shape | Notes |
| --- | --- | --- |
| `postgres` | `StatefulSet` + `PersistentVolumeClaim` + internal `Service` | Use Funcom's Postgres image. Keep data on durable storage. |
| `admin-rmq` | `StatefulSet` + `PersistentVolumeClaim` + internal `Service` | Management/debug ports should stay private. |
| `game-rmq` | `StatefulSet` + `PersistentVolumeClaim` + internal `Service` | Keep RabbitMQ private to the cluster. |
| `rmq-auth-shim` | `Deployment` + internal `Service` | Local compatibility shim for game-server S2S RabbitMQ users. |
| `db-init` | `Job` | Run after Postgres is ready and before Director/Gateway/Text Router. |
| `director` | `Deployment` | Mount `config/director.ini` from a `ConfigMap`. Restart after transfer-policy changes. |
| `text-router` | `Deployment` | Internal service, plus any ports required by the game routing path. |
| `gateway` | `Deployment` or small replica `Deployment` | Exposes public gateway path and registers with Funcom services. |
| game map services | one `Deployment` per fixed map partition, or generated `StatefulSet` style pods | Preserve stable `POD_IP`, `NODE_NAME`, map name, partition id, game port, and IGW port assumptions. |
| `admin-panel` | optional `Deployment` + private `Ingress` | Restrict to trusted LAN/VPN. Enable token auth unless the ingress is fully isolated to trusted operators. |

The Compose warm pool uses one long-running container per map partition. In Kubernetes, the nearest equivalent is one Deployment per fixed partition so each pod has explicit args, ports, config, and recovery behavior. A generator or Helm chart can reduce repetition, but the rendered output should stay inspectable.

## Images

Do not publish or mirror Funcom images in this repository.

Cluster nodes need access to the official images by one of these methods:

- Load the Steam-delivered image tarballs into every node's container runtime.
- Push the images to a private registry you control, if your license and Funcom's terms allow it.
- Use a single-node cluster where local image loading is enough.

Pin every workload to the exact `DUNE_IMAGE_TAG` being tested. Avoid `latest`.

## Config and Secrets

Use `ConfigMap` objects for non-secret config:

- `config/director.ini`
- `config/gateway.ini`
- `config/text-router.ini`
- `config/UserEngine.ini`
- `config/UserGame.ini`
- RabbitMQ config files that do not contain secrets

Use `Secret` objects for:

- `FLS_SECRET`
- `DUNE_SERVER_LOGIN_PASSWORD`
- Postgres passwords
- RabbitMQ HTTP auth secret
- RabbitMQ TLS key material
- Admin panel token

Mount secrets as files or inject them as env vars according to the container's existing entrypoint behavior. Keep generated Kubernetes YAML with real secrets out of git.

## Networking

The Compose layout uses a fixed Docker subnet so map containers can advertise stable internal addresses. Kubernetes pod IPs are also routable inside the cluster, but they are not stable across restarts.

For a cluster deployment, choose one of these approaches:

- Use pod IP injection through the downward API for `POD_IP` and let restarted pods re-register.
- Use one Service per map partition and pass stable service DNS names where the server supports names.
- Use host networking only if you fully understand the port collision and node scheduling constraints.

Public client UDP exposure must preserve the same game-port range used by the chosen farm layout:

- Single Survival: `7777/udp`
- Nine-map standing farm: `7777-7785/udp`
- Full 30-partition warm pool: `7777-7806/udp`

The IGW/S2S UDP range is exposed in Compose for debugging. Keep it cluster-internal unless live-client testing proves public exposure is required.

RabbitMQ and Postgres should be internal-only services.

## Storage

Use durable volumes for:

- Postgres data
- RabbitMQ data
- game server saved state

Backups should be Kubernetes-native equivalents of `scripts/backup-state.sh`: database dump plus optional RabbitMQ and server saved-state archives. Store backups outside the cluster storage class so a cluster failure does not take the backup with it.

## Startup Order

Kubernetes does not guarantee Compose-style ordering. Use readiness probes and Jobs:

1. Start Postgres and both RabbitMQ StatefulSets.
2. Wait for readiness.
3. Run the `db-init` Job.
4. Start `rmq-auth-shim`, `text-router`, `gateway`, and `director`.
5. Start game map pods.
6. Confirm `farm_state`, `active_server_ids`, RabbitMQ connections, and client reachability.

Avoid running database schema bootstrap concurrently from multiple pods.

## Operational Gaps

Before treating Kubernetes as supported, add:

- Rendered manifests or a Helm chart generated from the same service table as Compose.
- A cluster preflight that checks image availability, storage classes, secrets, UDP exposure, and node AVX2 support.
- Kubernetes versions of `status.sh`, `backup-state.sh`, `restore-state.sh`, and map recovery helpers.
- A test matrix for single-node, multi-node, and private-registry image distribution.
- Documentation for rolling image-tag upgrades and rollback.
