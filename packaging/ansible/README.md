# DASH Ansible and Proxmox Packaging

This package provisions an Ubuntu/Debian x86_64 Compose host from an immutable
DASH source release. It verifies AVX2, requires a full Git commit plus source
archive SHA-256, keeps runtime state outside the release tree, installs a
guarded systemd unit, and leaves service startup disabled by default.

## Operator workflow

1. Copy `inventory.example.yml` and `group_vars/all.example.yml` outside the
   repository or rename them to private, ignored files.
2. Put `dash_env_content` in Ansible Vault. Do not place the FLS token, admin
   tokens, passwords, or private keys in inventory committed to Git.
3. Obtain the exact archive checksum independently:

   ```bash
   ref=<full-40-hex-commit>
   curl -fL "https://github.com/snapetech/DuneAwakeningSelfHost/archive/${ref}.tar.gz" -o /tmp/dash.tar.gz
   sha256sum /tmp/dash.tar.gz
   ```

4. Use an isolated controller environment, install the pinned collection plus
   its Proxmox API dependencies, and run a check first:

   ```bash
   cd packaging/ansible
   python3 -m venv .venv
   . .venv/bin/activate
   python3 -m pip install ansible-core -r requirements.txt
   ansible-galaxy collection install -r requirements.yml
   ansible-playbook -i inventory.private.yml site.yml --ask-vault-pass --check --diff
   ansible-playbook -i inventory.private.yml site.yml --ask-vault-pass
   ```

5. Place the operator-obtained official Steam server package at the configured
   `dash_steam_server_dir`. Enable `dash_load_images` only after the directory
   is verified. Enable `dash_initialize_database` once. Enable/start
   `dash.service` only after `bootstrap-checklist.sh` passes.

The role never downloads or redistributes Funcom images. It never restarts an
already-running farm during release installation. `dash.service` uses
`start-full-warm-pool.sh` and `stop-full-warm-pool.sh`, preserving DASH's
post-start hooks and adaptive map policy.

## Release rollback

Rollback only changes the `/opt/dash/current` symlink; it does not restart the
world:

```bash
sudo /usr/local/sbin/dash-install-release rollback \
  --confirm 'ROLL BACK DASH RELEASE'
sudo systemctl restart dash.service
```

Schedule the explicit service restart as maintenance and validate Landsraad
before and after it when Coriolis configuration changed.

## Proxmox

`proxmox-create-vm.yml` uses the supported
[`community.proxmox`](https://docs.ansible.com/ansible/latest/collections/community/proxmox/)
collection and a scoped Proxmox API token from environment variables. It
requires `cpu: host` so AVX2 reaches the guest, enables the guest agent,
imports the system disk with `community.proxmox.proxmox_disk`, sets its boot
order, and leaves the VM powered off. The example `local:import/...` source is
the Proxmox VE 9 import-content form. Override `dash_cloud_image_volume` with a
reviewed storage/path form supported by the target Proxmox release; do not
silently reinterpret the example on an older host. Review storage, bridge, VM
ID, memory, and cloud-image provenance before running:

```bash
export PROXMOX_API_HOST=pve.example.lan
export PROXMOX_API_USER='dash-automation@pve'
export PROXMOX_API_TOKEN_ID='ansible'
export PROXMOX_API_TOKEN_SECRET='...'
export DASH_VM_SSH_PUBLIC_KEY="$(<~/.ssh/dash-admin.pub)"
ansible-playbook proxmox-create-vm.yml
```

The playbook does not download the Ubuntu image. Stage and checksum the
official cloud image independently, give the API token only the required VM
and datastore privileges, and confirm that `scsi0` is absent before the first
run. It accepts only an Ed25519 public key, creates the `dash-admin` cloud-init
user, and uses DHCP unless `dash_vm_ipconfig0` is overridden. The disk task
uses `create: regular`; it creates a missing disk or updates safe options but
does not force replacement. Existing disk replacement is intentionally outside
this automation.

Use `../cloud-init/dash-host.yaml` as reviewed user-data. Replace its public
key placeholder before upload. It contains no secrets and performs no DASH or
Funcom download.
