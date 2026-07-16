# Retained Metrics

The optional metrics overlay provides the same retained Prometheus outcome as
the audited Red-Blink stack: Prometheus, node-exporter, cAdvisor, a Postgres
exporter, and the RabbitMQ Prometheus endpoints already enabled by DASH.

Start it with the normal world Compose files plus the overlay:

```bash
docker compose --env-file .env \
  -f compose.yaml -f compose.allmaps.yaml -f compose.metrics.yaml \
  up -d prometheus node-exporter cadvisor postgres-exporter
```

For persistent lifecycle integration, set `DUNE_METRICS_ENABLED=true`.
`scripts/compose-files.sh` then includes `compose.metrics.yaml`, and the normal
full-farm startup launches the four metrics services.

Prometheus binds only to localhost by default:

```text
http://127.0.0.1:19090
```

Configuration:

```env
DUNE_METRICS_BIND_ADDRESS=127.0.0.1
DUNE_METRICS_PROMETHEUS_PORT=19090
DUNE_METRICS_RETENTION_TIME=7d
DUNE_METRICS_RETENTION_SIZE=2GB
DUNE_METRICS_ENABLED=true
```

Image variables allow reviewed digest pins without editing Compose. The
Postgres password is supplied directly from `.env`; it is not written into the
Prometheus configuration. The Prometheus data volume is bounded by both time
and size retention.

`node-exporter` requires host PID visibility and a read-only root mount.
`cAdvisor` requires privileged host/container telemetry and read-only host
mounts. Neither exporter publishes a host port. Do not include this overlay on
a host where those observation privileges are outside the operator's trust
boundary.

Validate before deployment:

```bash
docker compose --env-file .env.example \
  -f compose.yaml -f compose.metrics.yaml config --quiet
```
