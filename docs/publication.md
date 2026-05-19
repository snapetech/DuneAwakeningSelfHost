# Publication Notes

This repository is for original tooling around the official Dune: Awakening self-hosted server package. It is not a redistribution of the game server.

## Safe to Publish

- Compose and system orchestration written for this project.
- Helper scripts written for this project.
- Documentation and teardown notes.
- Sanitized config templates with placeholders.
- `.env.example` with non-secret defaults.

## Keep Local

- `.env` with FLS tokens, passwords, IPs, or real world identifiers.
- `config/tls/` private keys and generated certs.
- `data/` runtime state, Postgres data, RabbitMQ data, saved server data, logs, crash reports, and dumps.
- Steam-installed server package files.
- Funcom image tarballs or extracted container contents.
- Decompiled, reverse-engineered, or patched proprietary files.

## Before Pushing

Run:

```bash
make list-publishable
make validate
git status --short
git diff --cached --stat
```

Confirm that the staged files are limited to repository tooling and documentation. If a file came from Steam, Docker image exports, server runtime output, or a local secret generator, do not commit it.

## Licensing

Any license in this repository applies only to the original files in this repository. It does not grant rights to Funcom software, Dune: Awakening assets, Steam-delivered server packages, or third-party components bundled by Funcom.
