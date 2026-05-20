# Packaging and Distribution

DASH should be publishable without carrying private data or Funcom-owned artifacts.

## What Belongs In The Repo

Safe to include:

- Compose files.
- Original scripts.
- Documentation.
- Example env overlays with placeholder values.
- Systemd unit templates.
- Small static assets created for the admin panel.

Do not include:

- `.env`
- `data/`
- `backups/`
- `captures/`
- `config/tls/`
- Steam tool files.
- Funcom image tarballs.
- Runtime logs or database dumps.
- Real hostnames, public IPs, tokens, passwords, Discord-only private details, or player data.

## Example-First Packaging

Portable examples live under:

```text
examples/env/
examples/backup/
examples/ingress/
examples/firewall/
config/systemd/
public-site/
```

Operators should copy values from examples into their private `.env` or backup config. They should not use examples as complete replacements for `.env.example`, because `.env.example` remains the canonical list of supported keys.

## Release Checklist

Before publishing:

```bash
make validate
make public-site-check
git diff --check
./scripts/package-manifest.sh /tmp/dash-package-manifest.md
```

Then inspect:

```bash
git status --short --untracked-files=all
rg -n "FLS_SECRET[=].+|BEGIN .*PRIVATE[ ]KEY|PRIVATE[ ]KEY|password|token|secret" \
  --glob '!data/**' \
  --glob '!backups/**' \
  --glob '!captures/**' \
  --glob '!config/tls/**' \
  --glob '!.env'
```

The broad secret scan will produce some expected documentation/example hits. Confirm they are placeholders or warnings, not real values.

Use [`docs/release-template.md`](docs/release-template.md) for release notes or another-operator handoff notes.

## New Host Bootstrap Package

For another operator, the handoff should be:

1. Git repository URL.
2. Required Steam package install instructions.
3. A private `.env` generated from `.env.example`.
4. Optional copied local-only backup config under `/etc/dash` or outside the repo.
5. Router/firewall port list for the selected layout.
6. Restore-tested backup location and retention policy.
7. Optional public static site package from `public-site/` if the operator wants a public status/settings/map page.

The handoff should not include Funcom images or Steam files unless the recipient is entitled and obtains them through official channels.

## Platform Support Promise

Phrase support conservatively:

- Linux Docker Compose is the supported runtime.
- Windows and macOS are supported as operator workstations.
- Podman is best-effort.
- Kubernetes notes are architectural research, not the primary supported path.

This avoids implying that the project can make Funcom's Linux container stack run natively on non-Linux hosts.
