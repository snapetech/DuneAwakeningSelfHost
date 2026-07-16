#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
config="$tmp/sietches.json"
overlay="$tmp/compose.sietches.generated.yaml"
printf '%s\n' '{"partitions":{"32":{"display_name":"Sietch Alpha","password":"TestPassword"}}}' > "$config"

DUNE_SIETCH_TEST_ROWS=$'32\t1\tSietch Alpha' \
DUNE_SIETCH_CONFIG_FILE="$config" DUNE_SIETCH_OVERLAY_FILE="$overlay" \
  "$repo_root/scripts/sietches.sh" "$repo_root/.env.example" render >/dev/null

grep -q '^  sietch-32:$' "$overlay"
grep -q -- '-PartitionIndex=32' "$overlay"
grep -q '8001:8001/udp' "$overlay"
grep -q '8101:8101/udp' "$overlay"
grep -q '172.31.240.129' "$overlay"
grep -q 'TestPassword' "$overlay"
[[ "$(stat -c %a "$overlay")" == "600" ]]
docker compose --env-file "$repo_root/.env.example" -f "$repo_root/compose.yaml" -f "$repo_root/compose.allmaps.yaml" -f "$overlay" config --quiet

output="$($repo_root/scripts/sietches.sh "$repo_root/.env.example" set-active 3)"
grep -q 'plan: set Survival_1 active dimensions to 3' <<< "$output"
printf 'Sietch tests passed\n'
