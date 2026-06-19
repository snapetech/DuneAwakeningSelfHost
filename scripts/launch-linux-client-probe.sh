#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/launch-linux-client-probe.sh -- /path/to/DuneSandbox-Linux-Shipping [args...]

Environment:
  DUNE_LINUX_CLIENT_PRELOAD=/abs/path/libdune_client_probe_loader.so
  DUNE_CLIENT_PROBE_LOG=/tmp/dune-client-probe-loader.log
  DUNE_CLIENT_PROBE_SCAN_ENABLED=true
  DUNE_CLIENT_PROBE_SCAN_PRESETS=core,ue,client,cheat,brt,deep-desert
  DUNE_CLIENT_PROBE_SCAN_SIGNATURES_FILE=/path/to/client-signatures.txt
  DUNE_CLIENT_PROBE_PREP_DIR=/path/to/prepare-ue-anchor-canary output
  DUNE_CLIENT_PROBE_PREFLIGHT_ONLY=true

This wrapper supports native Linux ELF clients. If the target is a Windows/PE
client under Proton, it exits instead of pretending LD_PRELOAD can inject a .so.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
build_dir="${DUNE_LINUX_CLIENT_LOADER_BUILD_DIR:-$repo_root/build/linux-client-loader}"
loader="${DUNE_LINUX_CLIENT_PRELOAD:-$build_dir/libdune_client_probe_loader.so}"
prep_dir="${DUNE_CLIENT_PROBE_PREP_DIR:-${DUNE_LINUX_CLIENT_PROBE_PREP_DIR:-}}"
strict_verify="${DUNE_CLIENT_PROBE_STRICT_VERIFY:-${DUNE_LINUX_CLIENT_PROBE_STRICT_VERIFY:-false}}"
preflight_only="${DUNE_CLIENT_PROBE_PREFLIGHT_ONLY:-false}"

prep_anchor_env_path() {
  if [ -z "$prep_dir" ]; then
    return 0
  fi
  printf '%s/ue-anchors.env\n' "$prep_dir"
}

prep_verify_script_path() {
  if [ -z "$prep_dir" ]; then
    return 0
  fi
  if [ "$strict_verify" = "true" ]; then
    printf '%s/post-canary-verify-strict.sh\n' "$prep_dir"
  else
    printf '%s/post-canary-verify.sh\n' "$prep_dir"
  fi
}

validate_prep_dir() {
  local anchor_env verify_script
  if [ -z "$prep_dir" ]; then
    return 0
  fi
  anchor_env="$(prep_anchor_env_path)"
  verify_script="$(prep_verify_script_path)"
  if [ ! -d "$prep_dir" ]; then
    echo "missing prepared client canary dir: $prep_dir" >&2
    exit 2
  fi
  if [ ! -f "$anchor_env" ]; then
    echo "missing prepared client anchor env: $anchor_env" >&2
    exit 2
  fi
  if [ ! -x "$verify_script" ]; then
    echo "missing executable client post-canary verifier: $verify_script" >&2
    exit 2
  fi
}

load_prep_env() {
  local anchor_env
  if [ -z "$prep_dir" ]; then
    return 0
  fi
  anchor_env="$(prep_anchor_env_path)"
  set -a
  # shellcheck disable=SC1090
  . "$anchor_env"
  set +a
}

if [ "${1:-}" = "--" ]; then
  shift
fi

if [ "$#" -eq 0 ]; then
  usage
  exit 2
fi

target="$1"
resolved_target="$target"
if [ ! -e "$resolved_target" ]; then
  resolved_target="$(command -v "$target" || true)"
fi

if [ -z "$resolved_target" ] || [ ! -e "$resolved_target" ]; then
  echo "client executable not found: $target" >&2
  exit 1
fi

validate_prep_dir
load_prep_env

file_report=""
if command -v file >/dev/null 2>&1; then
  file_report="$(file -b "$resolved_target" || true)"
fi

if printf '%s\n' "$file_report" | grep -Eiq 'PE32|MS Windows|COFF executable'; then
  echo "refusing native Linux preload for Windows/PE client target: $resolved_target" >&2
  echo "file reports: $file_report" >&2
  echo "A Proton client needs a Windows DLL/proxy/injection path, not libdune_client_probe_loader.so." >&2
  exit 3
fi

if [ -n "$file_report" ] &&
   ! printf '%s\n' "$file_report" | grep -Eiq 'ELF .*executable|ELF .*shared object'; then
  if [ "${DUNE_CLIENT_PROBE_ALLOW_NON_ELF:-false}" != "true" ]; then
    echo "target does not look like a native Linux ELF executable: $resolved_target" >&2
    echo "file reports: $file_report" >&2
    exit 3
  fi
fi

if [ "$preflight_only" = "true" ]; then
  loader_readable=false
  if [ -r "$loader" ]; then
    loader_readable=true
  fi
  cat <<EOF
linux_client_probe_preflight=true
target=$resolved_target
target_file_report=$file_report
loader=$loader
loader_readable=$loader_readable
prep_dir=$prep_dir
prep_anchor_env=$(prep_anchor_env_path)
post_canary_verify_script=$(prep_verify_script_path)
would_set_ld_preload=$loader
would_exec=$*
EOF
  if [ "$loader_readable" != "true" ]; then
    echo "client preload library is not readable: $loader" >&2
    exit 1
  fi
  exit 0
fi

if [ ! -f "$loader" ]; then
  "$repo_root/scripts/build-linux-client-loader.sh" >/dev/null
fi

if [ ! -r "$loader" ]; then
  echo "client preload library is not readable: $loader" >&2
  exit 1
fi

if [ -z "${DUNE_CLIENT_PROBE_LOG+x}" ]; then
  export DUNE_CLIENT_PROBE_LOG=/tmp/dune-client-probe-loader.log
fi
if [ -z "${DUNE_CLIENT_PROBE_FORCE+x}" ]; then
  export DUNE_CLIENT_PROBE_FORCE=true
fi
if [ -z "${DUNE_CLIENT_PROBE_SCAN_ENABLED+x}" ]; then
  export DUNE_CLIENT_PROBE_SCAN_ENABLED=true
fi
if [ -z "${DUNE_CLIENT_PROBE_SCAN_PRESETS+x}" ]; then
  export DUNE_CLIENT_PROBE_SCAN_PRESETS=core,ue,client,cheat,brt,deep-desert
fi
if [ -z "${DUNE_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE+x}" ]; then
  export DUNE_CLIENT_PROBE_SCAN_MAX_HITS_PER_NEEDLE=16
fi
if [ -z "${DUNE_CLIENT_PROBE_SCAN_MAX_MAPPING_BYTES+x}" ]; then
  export DUNE_CLIENT_PROBE_SCAN_MAX_MAPPING_BYTES=268435456
fi
if [ -z "${DUNE_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS+x}" ]; then
  export DUNE_CLIENT_PROBE_SNAPSHOT_DELAY_SECONDS=0
fi

if [ -n "${LD_PRELOAD:-}" ]; then
  export LD_PRELOAD="$loader:$LD_PRELOAD"
else
  export LD_PRELOAD="$loader"
fi

exec "$@"
