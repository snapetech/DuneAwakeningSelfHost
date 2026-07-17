#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

check_sha() {
  local expected="$1" path="$2" actual
  actual="$(sha256sum "$path" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || { printf 'checksum mismatch: %s\n' "$path" >&2; exit 1; }
}

check_sha 7c9813085183b8ecd78da3847ae3b5b4c9cc0f6232c6770a36afb0f861c8fe7d vendor/bin/busybox
check_sha b01914a4cbd8497d8550010c2d27d2030614d532aaca60e89a3929a734c451b5 vendor/bin/curl
check_sha 5942c9b0934e510ee61eb3e30273f1b3fe2590df93933a93d7c58b81d19c8ff5 vendor/bin/jq
check_sha ebeaf56f8a25e102e9419933423738b3a2a613a444fd749d695e15eba53f71f2 vendor/bin/rg
check_sha b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314 vendor/source/busybox-1.36.1.tar.bz2

busybox_version="$(vendor/bin/busybox 2>&1)"
curl_version="$(vendor/bin/curl --version)"
rg_version="$(vendor/bin/rg --version)"
printf '%s\n' "$busybox_version" | rg 'BusyBox v1\.36\.1' >/dev/null
printf '%s\n' "$curl_version" | rg 'curl 8\.17\.0.*OpenSSL/3\.5\.4.*zlib/1\.3\.1.*libssh2/1\.11\.1.*nghttp2/1\.65\.0' >/dev/null
[[ "$(vendor/bin/jq --version)" == jq-1.7.1 ]]
printf '%s\n' "$rg_version" | rg '^ripgrep 15\.1\.0' >/dev/null
tar -tjf vendor/source/busybox-1.36.1.tar.bz2 | rg '^busybox-1\.36\.1/(LICENSE|Makefile)$' >/dev/null
rg -q '^CONFIG_STATIC=y$' vendor/source/busybox-1.36.1.config
rg -q '^# CONFIG_TC is not set$' vendor/source/busybox-1.36.1.config

for license in \
  BUSYBOX-GPL-2.0.txt CURL.txt JQ-MIT.txt LIBSSH2.txt MUSL-MIT.txt NGHTTP2.txt \
  OPENSSL-APACHE-2.0.txt RIPGREP-MIT.txt RIPGREP-UNLICENSE.txt ZLIB.txt; do
  [[ -s "vendor/licenses/$license" ]] || { printf 'missing third-party license: %s\n' "$license" >&2; exit 1; }
done

bash -n vendor/build-busybox.sh
printf 'vendored release tool checks passed\n'
