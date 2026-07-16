#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage:
  dash-ha-authority.sh status [--marker FILE]
  dash-ha-authority.sh revoke --confirm 'REVOKE DASH HA AUTHORITY' [--marker FILE]
  dash-ha-authority.sh grant --epoch EPOCH --fenced-host HOST --fence-evidence FILE \
    --ttl-seconds SECONDS --confirm 'GRANT DASH HA AUTHORITY' [--marker FILE]

Grant records operator-supplied fencing evidence; it does not perform fencing.
EOF
}

action="${1:-}"
[[ -n "$action" ]] || { usage >&2; exit 2; }
shift
marker="${DASH_HA_AUTHORITY_MARKER:-/var/lib/dash/ha/active-authority.json}"
epoch=""
fenced_host=""
evidence=""
ttl=""
confirm=""
while (($#)); do
  case "$1" in
    --marker) marker="${2:?missing marker}"; shift 2 ;;
    --epoch) epoch="${2:?missing epoch}"; shift 2 ;;
    --fenced-host) fenced_host="${2:?missing fenced host}"; shift 2 ;;
    --fence-evidence) evidence="${2:?missing evidence}"; shift 2 ;;
    --ttl-seconds) ttl="${2:?missing TTL}"; shift 2 ;;
    --confirm) confirm="${2:?missing confirmation}"; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done
[[ "$marker" == /* && "$marker" != / ]] || { printf 'marker must be an absolute non-root path\n' >&2; exit 2; }

case "$action" in
  status)
    if [[ -f "$marker" ]]; then
      python3 -m json.tool "$marker"
      health_command="${DASH_HA_HEALTH_COMMAND:-/usr/local/libexec/dash-vip-health}"
      if [[ ! -x "$health_command" && -x "$(dirname "$0")/dash-vip-health.sh" ]]; then
        health_command="$(dirname "$0")/dash-vip-health.sh"
      fi
      exec "$health_command" --marker "$marker"
    fi
    printf 'authority marker absent: %s\n' "$marker" >&2
    exit 1
    ;;
  revoke)
    [[ "$confirm" == 'REVOKE DASH HA AUTHORITY' ]] || { printf 'confirmation required\n' >&2; exit 77; }
    rm -f -- "$marker"
    printf 'authority revoked on %s\n' "$(hostname)"
    ;;
  grant)
    [[ "$confirm" == 'GRANT DASH HA AUTHORITY' ]] || { printf 'confirmation required\n' >&2; exit 77; }
    [[ "$epoch" =~ ^[A-Za-z0-9._-]{8,128}$ ]] || { printf 'epoch must be 8..128 safe characters\n' >&2; exit 2; }
    [[ "$fenced_host" =~ ^[A-Za-z0-9._-]{1,253}$ ]] || { printf 'invalid fenced host\n' >&2; exit 2; }
    [[ "$fenced_host" != "$(hostname)" ]] || { printf 'fenced host cannot be this host\n' >&2; exit 77; }
    [[ "$ttl" =~ ^[0-9]+$ && "$ttl" -ge 60 && "$ttl" -le 86400 ]] || { printf 'TTL must be 60..86400 seconds\n' >&2; exit 2; }
    [[ -f "$evidence" && -s "$evidence" ]] || { printf 'non-empty fencing evidence file is required\n' >&2; exit 77; }
    evidence_sha="$(sha256sum "$evidence" | awk '{print $1}')"
    issued="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    expires="$(date -u -d "+$ttl seconds" +%Y-%m-%dT%H:%M:%SZ)"
    mkdir -p -- "$(dirname -- "$marker")"
    temporary="${marker}.new.$$"
    python3 - "$temporary" "$epoch" "$(hostname)" "$fenced_host" "$evidence_sha" "$issued" "$expires" <<'PY'
import json,sys
path,epoch,host,fenced,evidence,issued,expires=sys.argv[1:]
with open(path,'w',encoding='utf-8') as out:
    json.dump({'version':1,'epoch':epoch,'activeHost':host,'fencedHost':fenced,
               'fenceEvidenceSha256':evidence,'issuedAt':issued,'expiresAt':expires},out,
              sort_keys=True,separators=(',',':'))
    out.write('\n')
PY
    chmod 0600 "$temporary"
    mv -f -- "$temporary" "$marker"
    printf 'authority granted host=%s epoch=%s expires=%s evidenceSha256=%s\n' "$(hostname)" "$epoch" "$expires" "$evidence_sha"
    ;;
  *) usage >&2; exit 2 ;;
esac
