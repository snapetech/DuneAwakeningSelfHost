#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

bash -n scripts/install-release.sh scripts/test-install-release.sh \
  scripts/panel-command.sh scripts/test-panel-command.sh \
  packaging/ha/dash-ha-authority.sh packaging/ha/dash-vip-health.sh \
  scripts/test-ha-packaging.sh
python3 -m py_compile packaging/pelican/panel-client.py
python3 -m json.tool packaging/pelican/egg-dash-remote-controller.json >/dev/null
grep -q 'community.proxmox.proxmox_kvm:' packaging/ansible/proxmox-create-vm.yml
grep -q 'community.proxmox.proxmox_disk:' packaging/ansible/proxmox-create-vm.yml
grep -q 'sshkeys:' packaging/ansible/proxmox-create-vm.yml
grep -q 'create: regular' packaging/ansible/proxmox-create-vm.yml
if grep -R -q 'community.general.proxmox' packaging/ansible; then
  echo 'deprecated community.general Proxmox module reference found' >&2
  exit 1
fi

./scripts/test-install-release.sh
./scripts/test-panel-command.sh
./scripts/test-ha-packaging.sh

python3 - <<'PY'
from pathlib import Path
try:
    import yaml
except ImportError:
    print('PyYAML not installed; structural YAML checks only')
    yaml=None
paths=list(Path('packaging/ansible').rglob('*.yml')) + [Path('packaging/cloud-init/dash-host.yaml')]
for path in paths:
    text=path.read_text(encoding='utf-8')
    assert '\t' not in text, f'tab in YAML: {path}'
    assert text.strip(), f'empty YAML: {path}'
    if yaml is not None:
        list(yaml.safe_load_all(text))
print(f'packaging YAML checks passed ({len(paths)} files)')
PY

if command -v ansible-playbook >/dev/null 2>&1; then
  ansible-playbook -i 'localhost,' packaging/ansible/site.yml --syntax-check \
    -e 'dash_release_ref=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
    -e 'dash_release_sha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
    -e 'dash_env_content=DUNE_TEST=true'
else
  echo 'ansible-playbook not installed; syntax-check skipped'
fi

echo 'deployment packaging tests passed'
