#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/assured-control-plane-deploy.sh --manifest FILE --reason TEXT [--stage DIR] [--workspace DIR] [env-file]

Runs a production-host-only two-phase control-plane deployment. The workflow:
  1. verifies the exact commit/source manifest and a fresh pre-change backup;
  2. captures every game-map container plus strict always-on process continuity;
  3. deploys only admin-panel/admin-panel-ingress through the normal tested path;
  4. validates and seals reviewed desired state, then certifies all runbooks;
  5. creates and verifies a post-change backup;
  6. finalizes an HMAC-signed assurance receipt; and
  7. creates a second verified backup containing that signed receipt.

It never calls a game-map start, stop, restart, or raw Compose map lifecycle.
EOF
}

manifest=""
reason=""
env_file=".env"
stage=""
workspace=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) manifest="${2:-}"; shift 2 ;;
    --reason) reason="${2:-}"; shift 2 ;;
    --stage) stage="${2:-}"; shift 2 ;;
    --workspace) workspace="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --*) printf 'unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *) env_file="$1"; shift ;;
  esac
done

[[ -n "$manifest" && -f "$manifest" ]] || { printf 'a readable --manifest is required\n' >&2; exit 2; }
[[ ${#reason} -ge 10 && ${#reason} -le 1000 ]] || { printf -- '--reason must contain 10..1000 characters\n' >&2; exit 2; }
[[ -f "$env_file" ]] || { printf 'env file not found: %s\n' "$env_file" >&2; exit 2; }

required_host="${DUNE_PRODUCTION_HOST:-kspls0}"
actual_host="$(hostname -s 2>/dev/null || hostname)"
[[ "$actual_host" == "$required_host" ]] || { printf 'refusing assured production deployment on %s; required host is %s\n' "$actual_host" "$required_host" >&2; exit 1; }

code_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="${workspace:-$code_root}"
workspace="$(cd -- "$workspace" && pwd)"
if [[ -n "$stage" ]]; then
  stage="$(cd -- "$stage" && pwd)"
fi
cd "$workspace"

read_env() {
  awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print}' "$env_file" | tail -1 | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

token="$(read_env DUNE_ADMIN_TOKEN)"
[[ -n "$token" ]] || { printf 'DUNE_ADMIN_TOKEN is required\n' >&2; exit 1; }
admin_port="$(read_env DUNE_ADMIN_HOST_PORT)"
admin_port="${admin_port:-18080}"
admin_url="http://127.0.0.1:${admin_port}"
work="$(mktemp -d -p "${TMPDIR:-/tmp}" dash-assured-deploy.XXXXXX)"
chmod 700 "$work"
window_id=""
finished=false
apply_lock=""

cleanup() {
  local status=$?
  [[ -z "$apply_lock" ]] || rm -f "$apply_lock"
  if [[ $status -ne 0 && -n "$window_id" && "$finished" != true ]]; then
    python3 - "$window_id" "$reason" >"$work/cancel.json" <<'PY'
import json,sys
print(json.dumps({"action":"cancel","windowId":sys.argv[1],"reason":"Workflow aborted: " + sys.argv[2],"confirm":"CANCEL ASSURED CHANGE WINDOW"}))
PY
    curl -fsS --max-time 15 -H "Authorization: Bearer $token" -H 'Content-Type: application/json' --data-binary "@$work/cancel.json" "$admin_url/api/ops/deployment-assurance" >/dev/null 2>&1 || true
  fi
  rm -rf "$work"
  exit "$status"
}
trap cleanup EXIT

api_get() {
  curl -fsS --max-time "${2:-30}" -H "Authorization: Bearer $token" "$admin_url$1"
}

api_post_file() {
  curl -fsS --max-time "${2:-300}" -H "Authorization: Bearer $token" -H 'Content-Type: application/json' --data-binary "@$1" "$admin_url/api/ops/deployment-assurance"
}

verified_backup() {
  local output backup
  output="$(./scripts/backup-state.sh "$env_file")"
  printf '%s\n' "$output"
  backup="$(printf '%s\n' "$output" | sed -n 's/^backup complete: //p' | tail -1)"
  [[ -n "$backup" && -d "$backup" ]] || { printf 'could not identify created backup set\n' >&2; return 1; }
  ./scripts/verify-backup.sh "$backup"
  printf '%s\n' "${backup#backups/}"
}

if [[ -n "$stage" ]]; then
  python3 "$code_root/scripts/deployment-assurance.py" verify --manifest "$manifest" --workspace "$stage" >"$work/manifest-verification.json"
else
  python3 "$code_root/scripts/deployment-assurance.py" verify --manifest "$manifest" --workspace "$workspace" >"$work/manifest-verification.json"
fi
./scripts/validate-landsraad-coriolis-cycle.sh "$env_file"

pre_backup_output="$(verified_backup)"
printf '%s\n' "$pre_backup_output"
pre_backup="$(printf '%s\n' "$pre_backup_output" | tail -1)"

mkdir -p backups/deployments
chmod 700 backups/deployments
rollback_archive="backups/deployments/assured-source-before-$(date -u +%Y%m%dT%H%M%SZ).tgz"
python3 "$code_root/scripts/deployment-assurance.py" archive --manifest "$manifest" --workspace "$workspace" --output "$rollback_archive" >"$work/rollback.json"
rollback_sha="$(python3 - "$work/rollback.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d["sha256"])
PY
)"
rollback_relative="${rollback_archive#backups/}"

python3 - "$manifest" "$reason" "$pre_backup" "$rollback_relative" "$rollback_sha" "$([[ -n "$stage" ]] && printf true || printf false)" >"$work/start.json" <<'PY'
import json,sys
document=json.load(open(sys.argv[1],encoding="utf-8"))
print(json.dumps({"action":"start","commit":document["commit"],"reason":sys.argv[2],"manifest":document,"preChangeBackupPath":sys.argv[3],"sourceRollbackArchive":sys.argv[4],"sourceRollbackSha256":sys.argv[5],"staged":sys.argv[6]=="true","confirm":"START ASSURED CHANGE WINDOW"}))
PY
api_post_file "$work/start.json" 300 >"$work/start-response.json"
window_id="$(python3 - "$work/start-response.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); value=d.get("id","")
if not value.startswith("deployment-window-"): raise SystemExit("assurance start did not return a window id")
print(value)
PY
)"
printf 'assured change window: %s\n' "$window_id"

if [[ -n "$stage" ]]; then
  install -d -m 700 backups/deployment-assurance
  apply_lock="$workspace/backups/deployment-assurance/apply.lock"
  (umask 077; printf '%s\n' "$window_id" >"$apply_lock")
  python3 "$code_root/scripts/deployment-assurance.py" apply --manifest "$manifest" --source "$stage" --workspace "$workspace" >"$work/apply.json"
  rm -f "$apply_lock"
  apply_lock=""
fi
./scripts/deploy-admin-panel.sh "$env_file"
prometheus_id="$(docker ps -q --filter "label=com.docker.compose.project=dune_server" --filter "label=com.docker.compose.service=prometheus" | head -1)"
if [[ -n "$prometheus_id" ]]; then
  docker kill --signal HUP "$prometheus_id" >/dev/null
fi
./scripts/validate-landsraad-coriolis-cycle.sh "$env_file"

api_get /api/ops/desired-state 60 >"$work/desired.json"
desired_state="$(python3 - "$work/desired.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); print(d.get("state", "unknown"))
PY
)"
if [[ "$desired_state" != "attested" ]]; then
  python3 - "$reason" >"$work/seal.json" <<'PY'
import json,sys
print(json.dumps({"action":"seal","reason":"Assured deployment: " + sys.argv[1],"confirm":"SEAL DESIRED STATE"}))
PY
  curl -fsS --max-time 120 -H "Authorization: Bearer $token" -H 'Content-Type: application/json' --data-binary "@$work/seal.json" "$admin_url/api/ops/desired-state" >"$work/seal-response.json"
fi

api_get /api/ops/change-intelligence 60 >"$work/change.json"
python3 - "$work/change.json" >"$work/certify.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); policy=d["policy"]["response"]["policySha256"]
print(json.dumps({"policySha256":policy,"confirm":"CERTIFY INCIDENT RESPONSE READINESS"}))
PY
curl -fsS --max-time 300 -H "Authorization: Bearer $token" -H 'Content-Type: application/json' --data-binary "@$work/certify.json" "$admin_url/api/ops/change-intelligence/certify" >"$work/certify-response.json"
python3 - "$work/certify-response.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); s=d.get("summary") or {}
if not d.get("ready") or s.get("runbooksReady") != s.get("runbooksTotal"): raise SystemExit("fleet-wide readiness certification failed")
print(f"readiness certification: {s['runbooksReady']}/{s['runbooksTotal']} runbooks, {s['diagnosticsReady']}/{s['diagnosticsTotal']} diagnostics, {s['recoveryContractsReady']}/{s['recoveryContractsTotal']} recovery contracts")
PY

post_backup_output="$(verified_backup)"
printf '%s\n' "$post_backup_output"
post_backup="$(printf '%s\n' "$post_backup_output" | tail -1)"
python3 - "$window_id" "$post_backup" >"$work/finish.json" <<'PY'
import json,sys
print(json.dumps({"action":"finish","windowId":sys.argv[1],"backupPath":sys.argv[2],"confirm":"FINALIZE ASSURED CHANGE WINDOW"}))
PY
api_post_file "$work/finish.json" 600 >"$work/finish-response.json"
python3 - "$work/finish-response.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); receipt=(d.get("document") or {}).get("receipt") or {}; verification=d.get("verification") or {}
if not receipt.get("ready") or not verification.get("ok"): raise SystemExit("deployment assurance receipt failed")
failed=[key for key,value in (receipt.get("invariants") or {}).items() if not value]
if failed: raise SystemExit("deployment assurance invariants failed: " + ", ".join(failed))
print(json.dumps({"receiptId":receipt["id"],"commit":receipt["commit"],"ready":receipt["ready"],"receiptSha256":receipt["receiptSha256"],"evidencePath":d.get("evidencePath"),"invariants":receipt["invariants"]},indent=2,sort_keys=True))
PY
finished=true

final_backup_output="$(verified_backup)"
printf '%s\n' "$final_backup_output"
final_backup="$(printf '%s\n' "$final_backup_output" | tail -1)"

api_get /metrics/change-intelligence 30 | grep -q '^dash_deployment_assurance_latest_ready 1$'
printf 'OK: assured control-plane deployment complete; final evidence backup=%s\n' "$final_backup"
