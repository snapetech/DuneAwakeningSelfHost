# Public Static Site

DASH includes an optional public static site for server operators who want to publish server settings, coarse status, an active-player list, and a Hagga Basin player map without exposing the LAN admin panel.

The public site is deliberately boring from a security perspective:

- The browser only fetches static files.
- The renderer runs locally on the DASH host.
- The public web server never needs Docker, Postgres, RabbitMQ, `.env`, admin-token, or admin-panel access.
- Generated `players.json` omits Steam IDs, Steam persona names, Steam profile URLs, Funcom IDs, account IDs, controller IDs, pawn IDs, raw database rows, internal hostnames, ports, tokens, and raw coordinate JSON.

## What It Generates

```text
/status.html
/players.json
/hagga-pois.json
/hagga-map.svg
/hagga-basin.webp
```

The page JavaScript refreshes those files every 60 seconds inline. It does not reload the whole page.

## Files

```text
public-site/static/
public-site/scripts/
public-site/systemd/
public-site/dune-public-site.env.example
examples/public-site/
```

## Linux Quickstart

Run from the DASH repo on the host that can run `docker compose` against the Dune stack:

```bash
sudo STATIC_DIR=/srv/dash-public-site \
  ENV_FILE=/etc/dune-public-site.env \
  DUNE_PUBLIC_SITE_USER="$USER" \
  ./public-site/scripts/install-dune-public-site.sh
```

Edit the environment file:

```bash
sudoedit /etc/dune-public-site.env
```

Set at minimum:

```text
DUNE_ROOT=/opt/DuneAwakeningSelfHost
STATIC_DIR=/srv/dash-public-site
INDEX_FILE=/srv/dash-public-site/index.html
STATUS_FILE=/srv/dash-public-site/status.html
DUNE_DATABASE=dune_sb_1_4_0_0
```

Customize public text:

```bash
sudo PUBLIC_SITE_TITLE="Example Dune Awakening Server" \
  PUBLIC_SERVER_NAME="Example PVE Friendly Server" \
  PUBLIC_SERVER_DESCRIPTION="A friendly community PvE Dune Awakening server." \
  PUBLIC_SERVER_WHERE="Dune Awakening > Servers > Experimental > search Example." \
  STATIC_DIR=/srv/dash-public-site \
  /usr/local/sbin/configure-dune-public-site.sh
```

Render once and enable the timer:

```bash
sudo systemctl restart render-dune-static-status.service
sudo systemctl enable --now render-dune-static-status.timer
./public-site/scripts/validate-dune-public-site.sh /srv/dash-public-site
```

## Serve It

Use any static web server. Copyable examples:

```text
examples/public-site/caddy.Caddyfile
examples/public-site/nginx.conf
examples/public-site/compose.yaml
examples/public-site/rclone-sync.sh
```

Only these public paths are required:

```text
/
/style.css
/app.js
/status.html
/players.json
/hagga-pois.json
/hagga-map.svg
/hagga-basin.webp
```

Return `404` for everything else.

## Windows And macOS

Windows and macOS are reasonable static web hosts, but the renderer should normally run on the Linux DASH host that owns the Docker Compose stack.

Recommended pattern:

1. Run the renderer on the DASH host.
2. Sync `/srv/dash-public-site` to the Windows/macOS host with `rsync`, `scp`, Syncthing, SMB, or another sync tool.
3. Serve only the synced files.

Do not give a public IIS, nginx, Apache, or Caddy process permission to run Docker or read the DASH `.env`.

## Standby And Offsite Sync

For an SSH standby:

```text
SYNC_HOST=standby.example
SYNC_STATIC_ROOT=/srv
```

The render script uploads the generated site directory after each render. Object storage is also fine if it serves HTML, CSS, JS, JSON, SVG, and WebP with sane content types; see `examples/public-site/rclone-sync.sh`.

## Map Calibration

The renderer copies `admin/static/hagga-basin.webp` and projects player pawns using `DUNE_HAGGA_MAP_*` settings from `/etc/dune-public-site.env` or the DASH `.env`.

Defaults:

```text
DUNE_HAGGA_MAP_MIN_X=-457200
DUNE_HAGGA_MAP_MAX_X=355600
DUNE_HAGGA_MAP_MIN_Y=-457200
DUNE_HAGGA_MAP_MAX_Y=355600
DUNE_HAGGA_MAP_INVERT_X=false
DUNE_HAGGA_MAP_INVERT_Y=false
DUNE_HAGGA_MAP_IMAGE_MIN_U=0
DUNE_HAGGA_MAP_IMAGE_MAX_U=1
DUNE_HAGGA_MAP_IMAGE_MIN_V=0
DUNE_HAGGA_MAP_IMAGE_MAX_V=1
```

If markers drift, use two or more known in-game locations far apart from each other and adjust one calibration value at a time.

## Package A Copy

Create a portable tarball containing only the public-site package:

```bash
make public-site-check
./public-site/scripts/package-dune-public-site.sh /tmp/dash-public-site.tar.gz
```

Inspect the tarball before sharing. It should contain only `public-site/`, `examples/public-site/`, and this document.

## Optional GitLab Publishing

GitLab publishing is optional. The default install and maintenance path is still the local shell/systemd flow above. Use `.gitlab-ci.yml` only when you deliberately want a protected `gitlab.home` shell runner to validate and publish the static site.

The optional pipeline deliberately separates safe automation from live operations:

- `validate:public-site` runs `make public-site-check` and creates a package artifact.
- `deploy:public-site` is manual on the default branch and deploys only static-site files plus a fresh render.
- `observe:public-site` verifies no-store headers, `status.html` freshness, and `players.json` shape.
- `observe:server-health` is read-only and runs the existing health/RabbitMQ checks.

Runner requirements for this optional path:

```text
bash
curl
docker compose access to the DASH stack
jq
make
python3
systemctl permission to restart render-dune-static-status.service
write access to STATIC_DIR from /etc/dune-public-site.env
```

Recommended runner environment:

```text
PUBLIC_SITE_ENV_FILE=/etc/dune-public-site.env
PUBLIC_SITE_URL=https://dune.snape.tech
```

Keep game-state mutations out of scheduled GitLab jobs. Use manual jobs only for static publish and read-only checks unless a separate operator-approved runbook says otherwise. Do not treat this as a required install step for users who prefer direct shell/systemd operation.
