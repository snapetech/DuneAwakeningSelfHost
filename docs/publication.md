# Publication Notes

This repository is for original tooling around the official Dune: Awakening self-hosted server package. It is not a redistribution of the game server.

## Safe to Publish

- Compose and system orchestration written for this project.
- Helper scripts written for this project.
- Documentation and teardown notes.
- Sanitized config templates with placeholders.
- `.env.example` with non-secret defaults.
- The optional public static site package under `public-site/` and `examples/public-site/`.
- The documented static helpers under `vendor/` only with their exact upstream
  identities, license texts, hashes, and corresponding source obligations.

## Keep Local

- `.env` with FLS tokens, passwords, IPs, or real world identifiers.
- `config/tls/` private keys and generated certs.
- `data/` runtime state, Postgres data, RabbitMQ data, saved server data, logs, crash reports, and dumps.
- `backups/` and `captures/` runtime exports.
- Steam-installed server package files.
- Funcom image tarballs or extracted container contents.
- Decompiled, reverse-engineered, or patched proprietary files.
- Generated public-site runtime output if it contains real player names or site-specific hostnames.

## Before Pushing

Run:

```bash
make list-publishable
make validate
git status --short
git diff --cached --stat
```

Confirm that the staged files are limited to repository tooling and documentation. If a file came from Steam, Docker image exports, server runtime output, or a local secret generator, do not commit it.

For a tagged package, also run `make release-package` and follow
[`releases.md`](releases.md). The release builder refuses tracked private/runtime
paths, verifies every archive and sidecar, and smoke-installs the primary asset
without starting services.

## Licensing

Any license in this repository applies only to the original files in this repository. It does not grant rights to Funcom software, Dune: Awakening assets, Steam-delivered server packages, or third-party components bundled by Funcom. Vendored open-source helpers retain the licenses recorded in `vendor/licenses/` and `THIRD_PARTY_NOTICES.md`; BusyBox corresponding source and build inputs accompany its GPL-2.0-only binary.
