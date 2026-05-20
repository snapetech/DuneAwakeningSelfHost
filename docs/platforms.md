# Platform Guide

DASH is developed on Linux because the official self-hosted server package ships as Linux containers. Other platforms can still operate the stack when they provide a real Linux Docker engine.

## Supported Baseline

Recommended baseline:

- x86_64 Linux host with AVX2.
- Docker Engine with the Compose plugin.
- Local filesystem with enough IOPS for Postgres plus the selected map count.
- Public inbound UDP/TCP forwarding for game traffic.
- Private LAN/VPN-only access for the admin panel.

Known-good operator shell tools:

```bash
docker compose version
jq --version
rg --version
openssl version
```

## Linux Distributions

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl jq ripgrep openssl rsync
```

Fedora/RHEL-family:

```bash
sudo dnf install -y jq ripgrep openssl rsync
```

Arch-family:

```bash
sudo pacman -S --needed jq ripgrep openssl rsync
```

Install Docker from your distribution or Docker's official packages. The helper scripts call `docker compose`, not the legacy `docker-compose` binary.

## Windows Operators

Do not try to run the game containers directly on native Windows. Use one of these patterns:

- Dedicated Linux server on the LAN.
- Windows workstation with SSH into a Linux server.
- WSL2 only for repo editing and operator shell work, with Docker Engine backed by a Linux VM.

The official Steam tool can be downloaded on a Windows machine, but the image tarballs and runtime should be moved to the Linux host. Do not commit Steam package files or copied image tarballs into this repo.

Path translation matters. Put the repo and runtime data on the Linux filesystem, not under a Windows-mounted path such as `/mnt/c/...`, because Postgres and high-churn container I/O perform poorly there.

## macOS Operators

Use macOS as an operator workstation, not as the recommended server host. Docker Desktop can run Linux containers, but host networking, port forwarding, filesystem performance, and long-running service management differ enough that a dedicated Linux host is simpler.

Recommended pattern:

```bash
ssh dune-host.example.lan
cd /srv/DuneAwakeningSelfHost
./scripts/status.sh .env
```

If you edit from macOS, commit only repo files. Keep `.env`, `data/`, backups, and Steam package contents on the Linux host.

## Podman

Some scripts accept:

```bash
CONTAINER_RUNTIME=podman
```

Podman compatibility is best-effort. Validate Compose networking, published UDP ports, container DNS, health checks, and volume ownership before trusting it for live operation.

## NAS and Virtualization Notes

NAS storage is fine for secondary backups. Avoid running live Postgres data over SMB/NFS unless you have already validated latency, locking semantics, and crash recovery. Prefer local SSD/NVMe for `data/postgres`.

Virtual machines work well when:

- CPU flags expose AVX2 to the guest.
- The VM has stable bridged networking or explicit port forwards.
- Disk cache/writeback policy is understood.
- Host shutdown hooks stop the stack cleanly or snapshots are crash-consistent.

## Portable Install Layout

A predictable Linux layout makes scripts and timers easier to reason about:

```text
/srv/DuneAwakeningSelfHost       repo checkout
/srv/dune-steam-server           optional Steam tool mirror
/srv/dune-backups                optional external local backup target
/etc/dash                        local-only secrets for backup tools
```

The repo itself assumes relative paths where possible. Installer scripts render absolute paths into systemd units so the checkout can live elsewhere.

Before startup on a new host, run:

```bash
./scripts/bootstrap-checklist.sh .env
```

It is read-only and reports missing tools, placeholder env values, and common packaging mistakes.
