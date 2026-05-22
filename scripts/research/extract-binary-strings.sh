#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
service="${2:-deep-desert}"
pattern="${3:-m_|Command|Cheat|Subsystem|Coriolis|SandStorm|Shifting|Spice|Vehicle|Inventory|Admin}"
container_runtime="${CONTAINER_RUNTIME:-docker}"
compose=("$container_runtime" compose --env-file "$env_file")
binary="${DUNE_SERVER_BINARY_PATH:-/home/dune/server/DuneSandbox/Binaries/Linux/DuneSandboxServer-Linux-Shipping}"

"${compose[@]}" exec -T "$service" sh -lc "test -f '$binary' && if command -v strings >/dev/null 2>&1; then strings '$binary'; else grep -aEo '[[:print:]]{4,}' '$binary'; fi | grep -Ei '$pattern' | sort -u"
