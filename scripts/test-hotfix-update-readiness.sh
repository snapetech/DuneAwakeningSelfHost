#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/scripts" "$work/bin"
cp "$repo_root/scripts/hotfix-auto-update-and-restart.sh" "$work/scripts/"
printf '#!/usr/bin/env bash\nprintf "kspls0\\n"\n' >"$work/bin/hostname"
printf '#!/usr/bin/env bash\nprintf "stage\\n" >>"$TEST_LOG"\n' >"$work/scripts/update-steam-tool.sh"
printf '#!/usr/bin/env bash\nprintf "check\\n" >>"$TEST_LOG"\nprintf "package server tags:\\n  dune_sb_1_4_10_0\\nstatus: update available\\n"\nexit 1\n' >"$work/scripts/check-steam-update.sh"
printf '#!/usr/bin/env bash\nprintf "apply\\n" >>"$TEST_LOG"\n' >"$work/scripts/update-owned-steam-build-and-restart.sh"
chmod +x "$work/bin/hostname" "$work/scripts"/*.sh
touch "$work/.env"

export TEST_LOG="$work/actions.log"
PATH="$work/bin:$PATH" DUNE_HOTFIX_UPDATE_LOCK_FILE="$work/lock" \
  DUNE_UPDATE_REQUIRE_READINESS_RECEIPT=true \
  bash "$work/scripts/hotfix-auto-update-and-restart.sh" "$work/.env" >"$work/safe.out"
grep -qx stage "$TEST_LOG"
grep -qx check "$TEST_LOG"
! grep -q apply "$TEST_LOG"
grep -q 'readiness receipt required' "$work/safe.out"

: >"$TEST_LOG"
PATH="$work/bin:$PATH" DUNE_HOTFIX_UPDATE_LOCK_FILE="$work/lock-legacy" \
  DUNE_UPDATE_REQUIRE_READINESS_RECEIPT=true \
  DUNE_HOTFIX_AUTO_APPLY_WITHOUT_READINESS=true \
  bash "$work/scripts/hotfix-auto-update-and-restart.sh" "$work/.env" >"$work/legacy.out"
grep -qx apply "$TEST_LOG"
! grep -q stage "$TEST_LOG"

printf 'hotfix update readiness tests passed\n'
