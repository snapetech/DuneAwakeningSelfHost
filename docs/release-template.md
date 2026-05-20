# Release Template

Use this as the release-note body for a tagged DASH package or handoff build.

## Summary

- DASH version/tag:
- Official server image tag:
- Target layout:
- Tested host platform:
- Backup mode:

## Operator Impact

- What changed:
- Required operator action:
- Expected downtime:
- Rollback path:

## Validation

Paste command results:

```bash
make validate
./scripts/bootstrap-checklist.sh .env
./scripts/status.sh .env
```

For 30-map warm pool:

```bash
COMPOSE_FILES='compose.yaml:compose.allmaps.yaml' ./scripts/rmq-health.sh .env
./scripts/verify-rmq-auth-path.sh
```

Backup validation:

```bash
./scripts/backup-state.sh .env
./scripts/verify-backup.sh backups/<backup-id>
```

## Included Docs

- `README.md`
- `docs/setup.md`
- `docs/operator-handoff.md`
- `docs/platforms.md`
- `docs/backup-strategy.md`
- `docs/operations.md`
- `docs/troubleshooting.md`
- `docs/packaging.md`

## Private Data Excluded

Confirm these are not in the release:

- `.env`
- `data/`
- `backups/`
- `captures/`
- `config/tls/`
- Steam package files
- Funcom image tarballs
- real hostnames, public IPs, tokens, passwords, or player data

## Known Limitations

- Linux Docker Compose is the supported runtime path.
- Windows/macOS are operator workstation paths, not native server targets.
- Podman is best-effort.
- Native GM/cheat routes remain gated until verified against the live server build.
- Client travel must be validated from the live game client after server-side health is green.

## Upgrade Notes

1. Back up before pulling.
2. Pull the release.
3. Review `.env.example` for new keys.
4. Apply any needed private `.env` changes.
5. Run `make validate`.
6. Restart only the affected services.
7. Confirm server-side health and live-client join/travel.
