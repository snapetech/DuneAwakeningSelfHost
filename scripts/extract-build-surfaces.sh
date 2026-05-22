#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
service="${2:-deep-desert}"
out_root="${3:-build}"
if [[ -n "${COMPOSE:-}" ]]; then
  read -r -a compose_cmd <<<"$COMPOSE"
else
  compose_cmd=(docker compose)
fi

read_env() {
  local key="$1" value
  value="$(awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found=1} END {if (!found) exit 0}' "$env_file" 2>/dev/null | tail -1)"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

redact_file() {
  local path="$1"
  perl -0pi -e 's/(ServiceAuthToken=)[^\s",]+/${1}<redacted>/g;
                s/(ServerCommandsAuthToken=)[^\s",]*/${1}<redacted>/g;
                s/(DatabasePassword=)[^\s",]+/${1}<redacted>/g;
                s/(RMQ_HTTP_TOKEN_AUTH_SECRET=)[^\s",]+/${1}<redacted>/g;
                s/(FLS_SECRET[=])[^\s",]+/${1}<redacted>/g;
                s/(FuncomLiveServices__ServiceAuthToken=)[^\s",]+/${1}<redacted>/g;' "$path" 2>/dev/null || true
}

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

image_tag="$(read_env DUNE_IMAGE_TAG)"
image_tag="${image_tag:-unknown-build}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="${out_root}/${image_tag}"
mkdir -p "$out_dir/route-captures"

cat >"$out_dir/metadata.json" <<JSON
{
  "build": "$image_tag",
  "generatedAt": "$stamp",
  "envFile": "$env_file",
  "service": "$service"
}
JSON

printf 'writing build surface ledger: %s\n' "$out_dir"

if "${compose_cmd[@]}" --env-file "$env_file" config >"$out_dir/compose.config.yaml" 2>"$out_dir/compose.config.err"; then
  redact_file "$out_dir/compose.config.yaml"
else
  printf 'warn: compose config failed; see %s\n' "$out_dir/compose.config.err" >&2
fi

if scripts/research/extract-server-configs.sh "$env_file" "$service" >"$out_dir/server-configs.txt" 2>"$out_dir/server-configs.err"; then
  redact_file "$out_dir/server-configs.txt"
else
  printf 'warn: server config extraction failed; see %s\n' "$out_dir/server-configs.err" >&2
fi

if scripts/research/extract-binary-strings.sh "$env_file" "$service" >"$out_dir/binary-strings.txt" 2>"$out_dir/binary-strings.err"; then
  python3 scripts/score-binary-candidates.py "$out_dir/binary-strings.txt" --format json --output "$out_dir/binary-candidate-scores.json"
  python3 scripts/score-binary-candidates.py "$out_dir/binary-strings.txt" --format markdown --output "$out_dir/BINARY_CANDIDATE_SCORES.md"
else
  printf 'warn: binary string extraction failed; see %s\n' "$out_dir/binary-strings.err" >&2
fi

if python3 scripts/research/dump-db-surface.py "$env_file" >"$out_dir/pg-surface.json" 2>"$out_dir/pg-surface.err"; then
  python3 scripts/classify-db-functions.py "$out_dir/pg-surface.json" --format json --output "$out_dir/pg-procs.json"
  python3 scripts/classify-db-functions.py "$out_dir/pg-surface.json" --format markdown --output "$out_dir/DB_FUNCTION_SURFACE_INDEX.md"
  python3 scripts/classify-db-functions.py "$out_dir/pg-surface.json" --format matrix-markdown --output "$out_dir/DB_FUNCTION_COVERAGE_MATRIX.md"
else
  printf 'warn: DB surface dump failed; see %s\n' "$out_dir/pg-surface.err" >&2
fi

for broker in admin game; do
  if python3 scripts/research/snapshot-rmq-topology.py "$env_file" --broker "$broker" >"$out_dir/rabbitmq-${broker}-topology.json" 2>"$out_dir/rabbitmq-${broker}-topology.err"; then
    :
  else
    printf 'warn: %s RabbitMQ topology snapshot failed; see %s\n' "$broker" "$out_dir/rabbitmq-${broker}-topology.err" >&2
  fi
done

if python3 scripts/research/index-server-logs.py data/server-saved/Logs >"$out_dir/log-signatures.json" 2>"$out_dir/log-signatures.err"; then
  redact_file "$out_dir/log-signatures.json"
else
  printf 'warn: log signature index failed; see %s\n' "$out_dir/log-signatures.err" >&2
fi

python3 scripts/generate-surface-docs.py --format markdown --output "$out_dir/SURFACE_LEDGER.md"
python3 scripts/generate-discovery-queue.py --output "$out_dir/DISCOVERY_QUEUE.md"
python3 scripts/build-asset-reference-graph.py "$out_dir/server-configs.txt" "$out_dir/binary-strings.txt" "$out_dir/log-signatures.json" --format json --output "$out_dir/asset-reference-graph.json" 2>"$out_dir/asset-reference-graph.err" || true
python3 scripts/build-asset-reference-graph.py "$out_dir/server-configs.txt" "$out_dir/binary-strings.txt" "$out_dir/log-signatures.json" --format markdown --output "$out_dir/ASSET_REFERENCE_GRAPH.md" 2>>"$out_dir/asset-reference-graph.err" || true

printf 'done: %s\n' "$out_dir"
