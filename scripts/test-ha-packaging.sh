#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
marker="$tmp/authority.json"
evidence="$tmp/fence.txt"
printf 'hypervisor reports old host powered off\n' > "$evidence"

if "$repo_root/packaging/ha/dash-ha-authority.sh" grant --marker "$marker" --epoch test-epoch-0001 --fenced-host old-host --fence-evidence "$evidence" --ttl-seconds 300 >/dev/null 2>&1; then
  echo 'HA grant accepted without confirmation' >&2; exit 1
fi
"$repo_root/packaging/ha/dash-ha-authority.sh" grant --marker "$marker" --epoch test-epoch-0001 --fenced-host old-host --fence-evidence "$evidence" --ttl-seconds 300 --confirm 'GRANT DASH HA AUTHORITY' >/dev/null
DASH_HA_SERVICE_UNIT=none "$repo_root/packaging/ha/dash-vip-health.sh" --marker "$marker" --epoch test-epoch-0001 >/dev/null
if DASH_HA_SERVICE_UNIT=none "$repo_root/packaging/ha/dash-vip-health.sh" --marker "$marker" --epoch wrong-epoch >/dev/null 2>&1; then
  echo 'HA health accepted wrong epoch' >&2; exit 1
fi
"$repo_root/packaging/ha/dash-ha-authority.sh" revoke --marker "$marker" --confirm 'REVOKE DASH HA AUTHORITY' >/dev/null
[[ ! -e "$marker" ]]

grep -Fq 'state BACKUP' "$repo_root/packaging/ha/keepalived.conf.example"
grep -Fq 'nopreempt' "$repo_root/packaging/ha/keepalived.conf.example"
grep -Fq 'track_script' "$repo_root/packaging/ha/keepalived.conf.example"
echo 'HA packaging tests passed'
