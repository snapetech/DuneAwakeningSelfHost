# Pelican/Pterodactyl Remote Controller

The supplied egg gives Pelican or Pterodactyl operators a console for DASH
without nesting Funcom's stack in one container and without mounting the Wings
host Docker socket. The actual game farm remains on the supported Linux Compose
host. The panel container reaches a dedicated SSH account whose key is
restricted to `scripts/panel-command.sh`.

Supported console commands are `status`, `bootstrap-check`, `backup`,
`farm-start`, `farm-stop`, and exact `map-start`, `map-stop`, or `map-restart`
operations. Map operations use `restart-target.sh`, so start/restart retains
post-start health hooks and Landsraad guards. No arbitrary shell, arguments,
port forwarding, agent forwarding, file browser, database write, player write,
or update command is exposed.

## Host setup

Create a dedicated key and account. On the DASH host, put the public key in the
account's `authorized_keys` as one line, replacing the expected hostname and
key text:

```text
restrict,command="env -i HOME=/home/dash-panel PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin DASH_PANEL_EXPECTED_HOSTNAME=dash-01 DASH_PANEL_ROOT=/opt/dash/current DASH_PANEL_STATE_ROOT=/var/lib/dash /opt/dash/current/scripts/panel-command.sh" ssh-ed25519 AAAA... dash-pelican
```

The account needs read/execute access to the release, read access to the private
environment, write access to `/var/lib/dash/panel-command-audit.log`, and Docker
access for lifecycle commands. Do not grant sudo. `restrict` disables PTY,
forwarding, agent forwarding, and X11 forwarding on current OpenSSH. Keep
`AllowTcpForwarding no` and `PermitTunnel no` in a matching `sshd_config`
`Match User dash-panel` block as defense in depth.

Generate a pinned host-key file from a trusted console, compare the fingerprint
to the host, then place it in the panel server's `secrets/known_hosts`. Upload
the private key to `secrets/id_ed25519` and set mode `0600`. Never store the
private key as an egg variable.

## Egg installation

Import `egg-dash-remote-controller.json`. Set a full DASH commit and the exact
GitHub source archive SHA-256. The installer refuses branches, mutable tags,
non-GitHub sources, and checksum mismatches. It downloads only the DASH client;
it does not download Funcom content.

The panel's power Stop/Kill actions stop only the controller process. They do
not stop the game farm. Use the explicit `farm-stop` command for an intentional
world shutdown. This distinction prevents a panel node restart from taking the
game offline.

## Rotation and rollback

To rotate access, add a new forced-command public key, replace the panel's
private key, verify `status`, then remove the old key. To revoke the panel,
remove its authorized key. Release rollback occurs on the DASH host through
`install-release.sh`; the controller always resolves `/opt/dash/current` and
therefore follows the selected release without receiving broader filesystem
access.
