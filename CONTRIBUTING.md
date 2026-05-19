# Contributing

This project tracks only original Linux host tooling for the official Dune: Awakening self-hosted server package.

Before opening a pull request:

```bash
make validate
git status --short
```

Do not commit runtime state, secrets, Funcom-distributed files, Steam package contents, image tarballs, or extracted proprietary content.

Good contributions include:

- Compose and service orchestration fixes.
- Safer bootstrap/status scripts.
- Documentation from reproducible local observations.
- Sanitized config templates.

When documenting behavior from a local server package, include the image tag and package version where possible.
