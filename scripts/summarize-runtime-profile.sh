#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/summarize-runtime-profile.sh <captures/...-runtime-profile>

Prints a compact summary from a runtime profile created by profile-runtime.sh.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

profile_dir="${1:-}"
if [[ -z "$profile_dir" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -d "$profile_dir" ]]; then
  printf 'profile dir not found: %s\n' "$profile_dir" >&2
  exit 1
fi

printf '== profile ==\n%s\n\n' "$profile_dir"

if [[ -f "$profile_dir/container-stats.txt" ]]; then
  printf '== container stats ==\n'
  sed -n '/^NAME/,$p' "$profile_dir/container-stats.txt"
  printf '\n'
fi

if [[ -f "$profile_dir/image-sizes.txt" ]]; then
  printf '== image sizes ==\n'
  sed -n '4,$p' "$profile_dir/image-sizes.txt" | sort -h -k3
  printf '\n'
fi

if [[ -f "$profile_dir/container-memory-detail.txt" ]]; then
  printf '== memory high-water by container ==\n'
  awk '
    /^## / { container=$2; next }
    /hwm=/ {
      hwm=0
      for (i=1; i<=NF; i++) {
        if ($i ~ /^hwm=/) {
          split($i, a, "=")
          hwm=a[2]
        }
      }
      if (hwm > max[container]) max[container]=hwm
    }
    END {
      for (c in max) printf "%s hwm_kb=%s\n", c, max[c]
    }
  ' "$profile_dir/container-memory-detail.txt" | sort
  printf '\n'
fi

if [[ -f "$profile_dir/container-sockets.txt" ]]; then
  printf '== socket states by container ==\n'
  awk '
    /^## / { container=$2; next }
    $1 ~ /^(tcp|udp)/ {
      state=$6
      if ($1 == "udp") state="UDP"
      key=container " " state
      counts[key]++
    }
    END {
      for (key in counts) printf "%s count=%s\n", key, counts[key]
    }
  ' "$profile_dir/container-sockets.txt" | sort
  printf '\n'

  printf '== db socket candidates ==\n'
  rg ':(5432)[[:space:]]' "$profile_dir/container-sockets.txt" || true
  printf '\n'
fi
