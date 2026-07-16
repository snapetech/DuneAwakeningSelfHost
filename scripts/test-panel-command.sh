#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf 'DUNE_TEST=true\n' > "$tmp/.env"

run() {
  DASH_PANEL_ROOT="$repo_root" \
  DASH_PANEL_STATE_ROOT="$tmp" \
  DASH_PANEL_ENV_FILE="$tmp/.env" \
  DASH_PANEL_COMMAND_DRY_RUN=true \
  "$repo_root/scripts/panel-command.sh" "$@"
}

run status | grep -Fq "$repo_root/scripts/status.sh $tmp/.env"
run map-start heighliner-dungeon | grep -Fq 'DUNE_RESTART_PHASE=start'
run map-stop deep-desert | grep -Fq 'DUNE_RESTART_PHASE=stop'
run map-restart survival | grep -Fq 'DUNE_RESTART_PHASE=restart'

if run shell >/dev/null 2>&1; then echo 'arbitrary command accepted' >&2; exit 1; fi
if run map-restart '../postgres' >/dev/null 2>&1; then echo 'unsafe service accepted' >&2; exit 1; fi
if SSH_ORIGINAL_COMMAND='status; id' DASH_PANEL_ROOT="$repo_root" DASH_PANEL_STATE_ROOT="$tmp" DASH_PANEL_ENV_FILE="$tmp/.env" DASH_PANEL_COMMAND_DRY_RUN=true "$repo_root/scripts/panel-command.sh" >/dev/null 2>&1; then
  echo 'shell metacharacters accepted' >&2; exit 1
fi

python3 - "$repo_root/packaging/pelican/egg-dash-remote-controller.json" "$repo_root/packaging/pelican/panel-client.py" <<'PY'
import importlib.util,json,sys
egg=json.load(open(sys.argv[1],encoding='utf-8'))
assert egg['meta']['version']=='PTDL_v2'
assert 'DASH_RELEASE_SHA256' in egg['scripts']['installation']['script']
spec=importlib.util.spec_from_file_location('panel_client',sys.argv[2])
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
for good in ('status','farm-stop','map-start survival'):
    assert module.validate_command(good)==good
for bad in ('status; id','map-start ../postgres','bash','map-start survival extra'):
    try: module.validate_command(bad)
    except ValueError: pass
    else: raise AssertionError(bad)
PY

echo 'panel command tests passed'
