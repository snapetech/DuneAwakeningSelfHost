#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

buyer_controller_id="${DUNE_ARTIFICIAL_EXCHANGE_BUYER_CONTROLLER_ID:-0}"
populator_owner_id="${DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID:-0}"
populator_source_inventory_id="${DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_INVENTORY_ID:-0}"

printf '== build catalog ==\n'
python3 scripts/build-exchange-catalog.py

printf '\n== readiness ==\n'
ready_args=(--check-ready --settlement-limit 20)
if [[ "$buyer_controller_id" =~ ^[0-9]+$ ]] && [[ "$buyer_controller_id" -gt 0 ]]; then
  ready_args+=(--buyer-controller-id "$buyer_controller_id")
fi
python3 scripts/artificial-exchange-bot.py "${ready_args[@]}"

printf '\n== settlement report ==\n'
python3 scripts/artificial-exchange-bot.py --settlement-report --settlement-limit 20

printf '\n== buyer dry-run scan ==\n'
DUNE_ARTIFICIAL_EXCHANGE_ENABLED=true \
  python3 scripts/artificial-exchange-bot.py --dry-run --limit 20 --report-skips 20

printf '\n== populator dry-run plan ==\n'
if [[ "$populator_owner_id" =~ ^[0-9]+$ ]] && [[ "$populator_owner_id" -gt 0 ]] && [[ "$populator_source_inventory_id" =~ ^[0-9]+$ ]] && [[ "$populator_source_inventory_id" -gt 0 ]]; then
  DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_ENABLED=true \
    python3 scripts/artificial-exchange-bot.py --populate-once --populator-owner-id "$populator_owner_id" --populator-source-inventory-id "$populator_source_inventory_id" --limit 20
else
  printf 'skipped: set DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_OWNER_ID and DUNE_ARTIFICIAL_EXCHANGE_POPULATOR_SOURCE_INVENTORY_ID to dry-run populator planning\n'
fi

printf '\n== service render ==\n'
./scripts/test-artificial-exchange-service.sh

printf '\nartificial exchange smoke check passed\n'
