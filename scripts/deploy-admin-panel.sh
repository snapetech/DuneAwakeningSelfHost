#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-${DUNE_ENV_FILE:-.env}}"
container_runtime="${CONTAINER_RUNTIME:-docker}"

if [[ ! -f "$env_file" ]]; then
  printf 'env file not found: %s\n' "$env_file" >&2
  exit 1
fi

compose=("$container_runtime" compose)
IFS=':' read -ra compose_files <<< "${COMPOSE_FILES:-compose.yaml}"
for compose_file in "${compose_files[@]}"; do
  compose+=(-f "$compose_file")
done
compose+=(--env-file "$env_file")

python3 -m py_compile admin/admin_panel.py scripts/admin-chat-commands.py scripts/player-presence-announcer.py
python3 scripts/test-admin-panel-safe-surfaces.py

"${compose[@]}" up -d --no-deps --force-recreate admin-panel

deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  status="$("${compose[@]}" ps --format json admin-panel 2>/dev/null | python3 -c 'import json,sys
text=sys.stdin.read().strip()
if not text:
    print("")
    raise SystemExit
try:
    rows=[json.loads(line) for line in text.splitlines() if line.strip()]
except Exception:
    print("")
    raise SystemExit
print((rows[0].get("Health") or rows[0].get("State") or "").lower() if rows else "")
' || true)"
  if [[ "$status" == *healthy* || "$status" == *running* ]]; then
    break
  fi
  sleep 3
done

./scripts/check-admin-ingress.sh "$env_file"
printf 'OK: deployed admin-panel using %s\n' "$env_file"
