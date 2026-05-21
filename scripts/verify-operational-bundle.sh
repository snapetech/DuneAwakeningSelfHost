#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/verify-operational-bundle.sh backups/operational-bundle-*.tgz

Structurally verifies a redacted operational handoff bundle.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

bundle="${1:-}"
if [[ -z "$bundle" || ! -f "$bundle" ]]; then
  printf 'bundle file required\n' >&2
  usage >&2
  exit 1
fi

case "$bundle" in
  backups/*) ;;
  *)
    printf 'refusing to verify bundle outside backups/: %s\n' "$bundle" >&2
    exit 1
    ;;
esac

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

tar -xzf "$bundle" -C "$tmp_dir"

required=(
  operational-report.txt
  operational-identity-check.txt
  backup-dry-run.txt
  compose-summary.txt
  manifest.txt
)

ok=true
for file in "${required[@]}"; do
  if [[ -f "$tmp_dir/$file" ]]; then
    printf 'OK file %s\n' "$file"
  else
    printf 'FAIL missing %s\n' "$file" >&2
    ok=false
  fi
done

if find "$tmp_dir" -type f \( -name '.env' -o -name '*.env' -o -name '*.key' -o -name '*.dump' -o -name '*.tgz' \) | grep -q .; then
  printf 'FAIL bundle contains forbidden file types\n' >&2
  find "$tmp_dir" -type f \( -name '.env' -o -name '*.env' -o -name '*.key' -o -name '*.dump' -o -name '*.tgz' \) >&2
  ok=false
else
  printf 'OK no forbidden file types\n'
fi

fls_key='FLS''_SECRET'
admin_key='DUNE_ADMIN''_TOKEN'
rmq_key='RMQ_HTTP_TOKEN_AUTH''_SECRET'
service_auth_key='ServiceAuth''Token'
private_key_pattern='PRIVATE'' KEY'
secret_pattern="(${fls_key}=(?!<).{4,}|${service_auth_key}=[A-Za-z0-9_.-]+|${admin_key}=(?!<).{4,}|${rmq_key}=(?!<).{4,}|BEGIN .*${private_key_pattern}|${private_key_pattern})"
if rg -n --pcre2 "$secret_pattern" "$tmp_dir" >/tmp/dash-bundle-secret-scan.$$; then
  printf 'FAIL possible secret material found\n' >&2
  cat /tmp/dash-bundle-secret-scan.$$ >&2
  rm -f /tmp/dash-bundle-secret-scan.$$
  ok=false
else
  rm -f /tmp/dash-bundle-secret-scan.$$
  printf 'OK no obvious secret material\n'
fi

if [[ -f "$tmp_dir/manifest.txt" ]]; then
  for marker in contains_env=false contains_tls_keys=false contains_database_dump=false contains_rabbitmq_state=false contains_raw_compose=false; do
    if grep -qx "$marker" "$tmp_dir/manifest.txt"; then
      printf 'OK manifest %s\n' "$marker"
    else
      printf 'FAIL manifest missing %s\n' "$marker" >&2
      ok=false
    fi
  done
fi

if [[ "$ok" == true ]]; then
  printf 'operational bundle verification complete: OK\n'
else
  printf 'operational bundle verification complete: FAILED\n' >&2
  exit 1
fi
