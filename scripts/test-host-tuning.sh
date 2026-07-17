#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
BIN="$TMP_DIR/bin"
ETC="$TMP_DIR/etc"
SYS="$TMP_DIR/sys"
PROC="$TMP_DIR/proc"
ENV_FILE="$TMP_DIR/test.env"
LOG="$TMP_DIR/runtime.log"
mkdir -p "$BIN" "$ETC" "$SYS/kernel/mm/transparent_hugepage" "$PROC/irq/200"
printf 'DUNE_HOST_TUNING_THP_MODE=never\n' >"$ENV_FILE"
printf '[always] madvise never\n' >"$SYS/kernel/mm/transparent_hugepage/enabled"
printf '[always] madvise never\n' >"$SYS/kernel/mm/transparent_hugepage/defrag"
printf ' 200: 1 2 IR-PCI enp0s1-rx-0\n' >"$PROC/interrupts"
printf '0-7\n' >"$PROC/irq/200/smp_affinity_list"

cat >"$BIN/sysctl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'sysctl %s\n' "$*" >>"$LOG"
if [[ "$1" == -n ]]; then
  case "$2" in
    net.core.rmem_max|net.core.wmem_max) echo 134217728 ;;
    net.core.netdev_max_backlog) echo 25000 ;;
    net.core.somaxconn) echo 4096 ;;
    *) echo 0 ;;
  esac
elif [[ "$1" == -p ]]; then exit 0
else echo "$1 = 1"
fi
EOF
cat >"$BIN/ip" <<'EOF'
#!/usr/bin/env bash
echo '1.1.1.1 via 192.0.2.1 dev enp0s1 src 192.0.2.2'
EOF
cat >"$BIN/ethtool" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == -g ]]; then
  printf 'Pre-set maximums:\nRX:\t4096\nTX:\t4096\nCurrent hardware settings:\nRX:\t256\nTX:\t256\n'
else printf 'ethtool %s\n' "$*" >>"$LOG"
fi
EOF
cat >"$BIN/systemctl" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == 'is-active --quiet irqbalance' ]]; then exit 3; fi
if [[ "$*" == 'is-active irqbalance' ]]; then echo inactive; exit 3; fi
printf 'systemctl %s\n' "$*" >>"$LOG"
EOF
cat >"$BIN/hostname" <<'EOF'
#!/usr/bin/env bash
echo kspls0
EOF
chmod +x "$BIN"/*
export PATH="$BIN:$PATH" LOG
export DUNE_HOST_TUNING_ETC_ROOT="$ETC" DUNE_HOST_TUNING_SYSFS_ROOT="$SYS"
export DUNE_HOST_TUNING_PROC_ROOT="$PROC" DUNE_HOST_TUNING_BACKUP_ROOT="$TMP_DIR/backups"
export DUNE_HOST_TUNING_TEST_MODE=true DUNE_HOST_TUNING_NIC_IRQ_CPUSET=8-15

render="$($ROOT_DIR/scripts/host-tuning.sh --env-file "$ENV_FILE" --render-sysctl)"
grep -q 'net.core.rmem_max = 134217728' <<<"$render"
grep -q 'net.core.netdev_max_backlog = 25000' <<<"$render"

preview="$($ROOT_DIR/scripts/host-tuning.sh --env-file "$ENV_FILE" plan --nic)"
grep -q 'Dry-run only' <<<"$preview"
[[ ! -e "$ETC/sysctl.d/99-dune-selfhost.conf" ]]

inode_before="$(stat -c '%d:%i' "$ENV_FILE")"
result="$($ROOT_DIR/scripts/host-tuning.sh --env-file "$ENV_FILE" apply --execute --persist --nic \
  --confirm 'APPLY DUNE HOST TUNING')"
[[ "$(stat -c '%d:%i' "$ENV_FILE")" == "$inode_before" ]]
grep -q 'Host tuning applied' <<<"$result"
grep -q '^never$' "$SYS/kernel/mm/transparent_hugepage/enabled"
grep -q '^8-15$' "$PROC/irq/200/smp_affinity_list"
grep -q 'ethtool -G enp0s1 rx 4096 tx 4096' "$LOG"
grep -q '^DUNE_HOST_TUNING_ENABLED=true$' "$ENV_FILE"
grep -q '^DUNE_HOST_TUNING_NIC_ENABLED=true$' "$ENV_FILE"
test -r "$ETC/systemd/system/dune-host-tuning.service"

echo "host tuning tests passed"
