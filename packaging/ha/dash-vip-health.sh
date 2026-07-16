#!/usr/bin/env bash
set -euo pipefail

marker="${DASH_HA_AUTHORITY_MARKER:-/var/lib/dash/ha/active-authority.json}"
expected_epoch="${DASH_HA_EXPECTED_EPOCH:-}"
service_unit="${DASH_HA_SERVICE_UNIT:-dash.service}"
while (($#)); do
  case "$1" in
    --marker) marker="${2:?missing marker}"; shift 2 ;;
    --epoch) expected_epoch="${2:?missing epoch}"; shift 2 ;;
    --service) service_unit="${2:?missing service}"; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ -f "$marker" ]] || { printf 'authority marker missing\n' >&2; exit 1; }
python3 - "$marker" "$(hostname)" "$expected_epoch" <<'PY'
import datetime,json,sys
path,host,expected=sys.argv[1:]
try:
    record=json.load(open(path,encoding='utf-8'))
    expires=datetime.datetime.fromisoformat(record['expiresAt'].replace('Z','+00:00'))
except (OSError,ValueError,KeyError,TypeError) as exc:
    raise SystemExit(f'invalid authority marker: {exc}')
if record.get('version') != 1 or record.get('activeHost') != host:
    raise SystemExit('authority marker is not bound to this host')
if expected and record.get('epoch') != expected:
    raise SystemExit('authority epoch does not match local HA configuration')
if expires <= datetime.datetime.now(datetime.timezone.utc):
    raise SystemExit('authority marker expired')
if not record.get('fenceEvidenceSha256'):
    raise SystemExit('authority marker lacks fencing evidence hash')
PY

if [[ "$service_unit" != none ]]; then
  systemctl is-active --quiet "$service_unit" || {
    printf 'active service unit is not running: %s\n' "$service_unit" >&2
    exit 1
  }
fi
printf 'DASH HA authority healthy host=%s service=%s\n' "$(hostname)" "$service_unit"
