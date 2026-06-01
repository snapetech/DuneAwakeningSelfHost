#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/monitor-character-transfers.sh [options]

Continuously capture character-transfer evidence:
  - relevant Director/FLS log lines
  - dune.character_transfer_imports snapshots
  - active transfer config at monitor start

Options:
  --env-file FILE       Compose env file. Default: .env
  --interval SECONDS    DB polling interval. Default: 2
  --since DURATION      Initial docker logs window. Default: 15m
  --output-dir DIR      Output root. Default: backups/character-transfer-monitor
  --full-ids            Do not redact 16-hex player/FLS ids in Director logs.
  --once                Capture one DB snapshot and exit after writing config.
  -h, --help            Show this help.
EOF
}

env_file="${DUNE_ENV_FILE:-.env}"
interval=2
since="15m"
output_root="backups/character-transfer-monitor"
full_ids=false
once=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      env_file="${2:?--env-file requires a value}"
      shift 2
      ;;
    --interval)
      interval="${2:?--interval requires a value}"
      shift 2
      ;;
    --since)
      since="${2:?--since requires a value}"
      shift 2
      ;;
    --output-dir)
      output_root="${2:?--output-dir requires a value}"
      shift 2
      ;;
    --full-ids)
      full_ids=true
      shift
      ;;
    --once)
      once=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$interval" =~ ^[0-9]+$ ]] || [[ "$interval" -lt 1 ]]; then
  printf 'interval must be a positive integer\n' >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repo_root"

container_runtime="${CONTAINER_RUNTIME:-docker}"
if [[ -x "$script_dir/compose-files.sh" ]]; then
  COMPOSE_FILES="$("$script_dir/compose-files.sh" "$env_file")"
  export COMPOSE_FILES
fi

compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

db_name="${DUNE_DATABASE_NAME:-dune_sb_1_4_0_0}"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
run_dir="$output_root/$run_id"
mkdir -p "$run_dir"

events_log="$run_dir/events.log"
state_jsonl="$run_dir/state.jsonl"
config_log="$run_dir/config.txt"

log_event() {
  local source="$1" message="$2"
  printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$source" "$message" >> "$events_log"
}

redact_stream() {
  if [[ "$full_ids" == true ]]; then
    cat
  else
    perl -pe 's/\b([A-Fa-f0-9]{4})[A-Fa-f0-9]{8}([A-Fa-f0-9]{4})\b/$1...$2/g'
  fi
}

psql_transfer_state() {
  local sql
  if [[ "$full_ids" == true ]]; then
    sql="
select coalesce(jsonb_agg(jsonb_build_object(
  'fls_id', fls_id,
  'fls_id_redacted', left(fls_id, 4) || '...' || right(fls_id, 4),
  'transfer_state', transfer_state::text,
  'last_update_utc', to_char(last_update at time zone 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.MS\"Z\"'),
  'age_seconds', floor(extract(epoch from now() - last_update))::int
) order by last_update), '[]'::jsonb)::text
from dune.character_transfer_imports;"
  else
    sql="
select coalesce(jsonb_agg(jsonb_build_object(
  'fls_id_redacted', left(fls_id, 4) || '...' || right(fls_id, 4),
  'transfer_state', transfer_state::text,
  'last_update_utc', to_char(last_update at time zone 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.MS\"Z\"'),
  'age_seconds', floor(extract(epoch from now() - last_update))::int
) order by last_update), '[]'::jsonb)::text
from dune.character_transfer_imports;"
  fi

  "${compose[@]}" exec -T postgres psql -U dune -d "$db_name" -At -P pager=off -c "$sql"
}

capture_config() {
  {
    printf 'run_id=%s\n' "$run_id"
    printf 'started_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'hostname=%s\n' "$(hostname 2>/dev/null || true)"
    printf 'env_file=%s\n' "$env_file"
    printf 'compose_files=%s\n' "${COMPOSE_FILES:-compose.yaml}"
    printf 'database=%s\n' "$db_name"
    printf 'interval=%s\n' "$interval"
    printf 'since=%s\n' "$since"
    printf 'full_ids=%s\n' "$full_ids"
    printf '\n[git]\n'
    git rev-parse --short HEAD 2>/dev/null || true
    git status --short 2>/dev/null || true
    printf '\n[director transfer config]\n'
    grep -nE '^(ShouldDeleteOriginCharactersDuringTransfers|AcceptOutgoingCharacterTransfers|IncomingCharacterTransfers|ExportCharacterTimeout|ImportCharacterTimeout|FreeToTransferCharactersFrom|FreeToTransferCharactersTo|ValidateBeforeImportCharacterTimeout|ActiveTransfersResolveProcessFrequencySeconds|CharacterTransferDbFunctionTimeLogThresholdMs)=' config/director.ini 2>/dev/null || true
    printf '\n[director container]\n'
    "${compose[@]}" ps director 2>&1 || true
  } > "$config_log"
}

capture_state_once() {
  local state now
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if state="$(psql_transfer_state 2>&1)"; then
    printf '{"ts":"%s","ok":true,"rows":%s}\n' "$now" "$state" >> "$state_jsonl"
    log_event "db-state" "$state"
  else
    printf '{"ts":"%s","ok":false,"error":%s}\n' "$now" "$(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$state")" >> "$state_jsonl"
    log_event "db-error" "$state"
  fi
}

capture_config
log_event "monitor" "started run_dir=$run_dir"

if [[ "$once" == true ]]; then
  capture_state_once
  printf '%s\n' "$run_dir"
  exit 0
fi

log_pattern='CharacterTransfer:|character_transfer|CharacterTransfers_|TransferOriginRuleset|ImportCharacter|ReserveSpotForTransfer|ExportCharacter|CheckTransferStatus|FinalizeTransfer|CancelTransfer|ValidateTransferRequirements|SetTransferDataChecksum|ImportStatus|failed_|Failed|sb[0-9A-Z]{3}\$|INVALID|Could not parse|OutOfMemoryException|api/CharacterTransfers_'

(
  "${compose[@]}" logs -f --since "$since" director 2>&1 \
    | grep --line-buffered -E "$log_pattern" \
    | redact_stream \
    | while IFS= read -r line; do
        log_event "director" "$line"
      done
) &
log_pid=$!

cleanup() {
  log_event "monitor" "stopping"
  kill "$log_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

last_state=""
while true; do
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if state="$(psql_transfer_state 2>&1)"; then
    printf '{"ts":"%s","ok":true,"rows":%s}\n' "$now" "$state" >> "$state_jsonl"
    if [[ "$state" != "$last_state" ]]; then
      log_event "db-state-change" "$state"
      last_state="$state"
    fi
  else
    error_json="$(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$state")"
    printf '{"ts":"%s","ok":false,"error":%s}\n' "$now" "$error_json" >> "$state_jsonl"
    log_event "db-error" "$state"
  fi
  sleep "$interval"
done
