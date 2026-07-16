#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
SYSFS="$TMP_DIR/sysfs"
SERVICES="$TMP_DIR/services"
OVERLAY="$TMP_DIR/compose.cpu-affinity.yaml"
ENV_FILE="$TMP_DIR/test.env"
BIN="$TMP_DIR/bin"
LOG="$TMP_DIR/docker.log"
mkdir -p "$BIN"
printf 'survival\novermap\ndeep-desert\npostgres\narrakeen\n' >"$SERVICES"
printf 'DUNE_CPU_AFFINITY_FOREGROUND_SERVICES=survival,overmap,deep-desert\n' >"$ENV_FILE"

for cpu in 0 1 2 3 4 5 6 7; do
  core=$((cpu % 4))
  mkdir -p "$SYSFS/cpu$cpu/topology" "$SYSFS/cpu$cpu/cache/index3"
  printf '0\n' >"$SYSFS/cpu$cpu/topology/physical_package_id"
  printf '%s\n' "$core" >"$SYSFS/cpu$cpu/topology/core_id"
  if ((core < 2)); then
    printf '0-1,4-5\n' >"$SYSFS/cpu$cpu/cache/index3/shared_cpu_list"
    printf '96M\n' >"$SYSFS/cpu$cpu/cache/index3/size"
  else
    printf '2-3,6-7\n' >"$SYSFS/cpu$cpu/cache/index3/shared_cpu_list"
    printf '32M\n' >"$SYSFS/cpu$cpu/cache/index3/size"
  fi
done

python3 "$ROOT_DIR/scripts/generate-cpu-affinity.py" --env-file "$ENV_FILE" \
  --sysfs-root "$SYSFS" --services-from "$SERVICES" --output "$OVERLAY" >/dev/null
grep -A1 '^  survival:' "$OVERLAY" | grep -q '0,1,4,5'
grep -A1 '^  postgres:' "$OVERLAY" | grep -q '2,3,6,7'
grep -q 'asymmetric largest shared L3 domain' "$OVERLAY"

for cpu in 0 1 4 5; do printf '32M\n' >"$SYSFS/cpu$cpu/cache/index3/size"; done
SYMMETRIC_OVERLAY="$TMP_DIR/compose.symmetric.yaml"
python3 "$ROOT_DIR/scripts/generate-cpu-affinity.py" --env-file "$ENV_FILE" \
  --sysfs-root "$SYSFS" --services-from "$SERVICES" --output "$SYMMETRIC_OVERLAY" >/dev/null
grep -q 'symmetric multi-L3 topology' "$SYMMETRIC_OVERLAY"

cat >"$BIN/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$LOG"
if [[ "$1" == ps ]]; then printf 'aaa\nbbb\n'; exit 0; fi
if [[ "$1" == inspect ]]; then
  id="${@: -1}"
  if [[ "$*" == *'com.docker.compose.service'* ]]; then [[ "$id" == aaa ]] && echo survival || echo postgres
  elif [[ "$*" == *'{{.Name}}'* ]]; then echo "/test-$id"
  else [[ "$id" == aaa ]] && echo '' || echo '2,3,6,7'
  fi
  exit 0
fi
if [[ "$1" == update ]]; then exit 0; fi
exit 1
EOF
cat >"$BIN/hostname" <<'EOF'
#!/usr/bin/env bash
echo "${TEST_HOSTNAME:-kspld0}"
EOF
chmod +x "$BIN/docker" "$BIN/hostname"
export PATH="$BIN:$PATH" LOG

preview="$($ROOT_DIR/scripts/cpu-affinity.sh --env-file "$ENV_FILE" --overlay "$OVERLAY" --project test apply)"
grep -q 'Dry-run only' <<<"$preview"
! grep -q '^update ' "$LOG"

if "$ROOT_DIR/scripts/cpu-affinity.sh" --env-file "$ENV_FILE" --overlay "$OVERLAY" --project test apply \
  --execute --confirm 'APPLY DUNE CPU AFFINITY' >/dev/null 2>&1; then
  echo "CPU affinity accepted the lab hostname" >&2
  exit 1
fi

export TEST_HOSTNAME=kspls0 DUNE_CPU_AFFINITY_BACKUP_ROOT="$TMP_DIR/backups"
result="$($ROOT_DIR/scripts/cpu-affinity.sh --env-file "$ENV_FILE" --overlay "$OVERLAY" --project test apply \
  --execute --persist --confirm 'APPLY DUNE CPU AFFINITY')"
grep -q '1 container(s) updated' <<<"$result"
grep -q '^update --cpuset-cpus 0,1,4,5 aaa$' "$LOG"
grep -q '^DUNE_CPU_AFFINITY_ENABLED=true$' "$ENV_FILE"

echo "CPU affinity tests passed"
