#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
prefix="$tmp/opt/dash"
state="$tmp/var/lib/dash"

make_archive() {
  local ref="$1" marker="$2" root
  root="$tmp/src-$ref/DuneAwakeningSelfHost-$ref"
  mkdir -p "$root/scripts" "$root/config"
  cp "$repo_root/scripts/install-release.sh" "$root/scripts/install-release.sh"
  printf 'services: {}\n' > "$root/compose.yaml"
  printf 'DUNE_TEST=%s\n' "$marker" > "$root/.env.example"
  printf '[Config]\nValue=%s\n' "$marker" > "$root/config/UserGame.ini"
  tar -czf "$tmp/$ref.tar.gz" -C "$tmp/src-$ref" "DuneAwakeningSelfHost-$ref"
}

ref_a="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ref_b="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
make_archive "$ref_a" one
make_archive "$ref_b" two
sha_a="$(sha256sum "$tmp/$ref_a.tar.gz" | awk '{print $1}')"
sha_b="$(sha256sum "$tmp/$ref_b.tar.gz" | awk '{print $1}')"

"$repo_root/scripts/install-release.sh" install --ref "$ref_a" --sha256 "$sha_a" --archive "$tmp/$ref_a.tar.gz" --prefix "$prefix" --state-root "$state" --activate >/dev/null
[[ "$(readlink -f "$prefix/current")" == "$prefix/releases/$ref_a" ]]
[[ -L "$prefix/current/.env" && -L "$prefix/current/data" && -L "$prefix/current/backups" ]]
grep -q 'Value=one' "$state/config-overrides/UserGame.ini"
printf '[Config]\nValue=operator\n' > "$state/config-overrides/UserGame.ini"

"$repo_root/scripts/install-release.sh" install --ref "$ref_b" --sha256 "$sha_b" --archive "$tmp/$ref_b.tar.gz" --prefix "$prefix" --state-root "$state" --activate >/dev/null
[[ "$(readlink -f "$prefix/current")" == "$prefix/releases/$ref_b" ]]
[[ "$(readlink -f "$prefix/previous")" == "$prefix/releases/$ref_a" ]]
grep -q 'Value=operator' "$prefix/current/config/UserGame.ini"

"$repo_root/scripts/install-release.sh" rollback --prefix "$prefix" --state-root "$state" --confirm 'ROLL BACK DASH RELEASE' >/dev/null
[[ "$(readlink -f "$prefix/current")" == "$prefix/releases/$ref_a" ]]
grep -q 'Value=operator' "$prefix/current/config/UserGame.ini"

if "$repo_root/scripts/install-release.sh" install --ref main --sha256 "$sha_a" --archive "$tmp/$ref_a.tar.gz" --prefix "$prefix" --state-root "$state" >/dev/null 2>&1; then
  echo 'mutable branch ref was accepted' >&2; exit 1
fi
if "$repo_root/scripts/install-release.sh" install --ref "$ref_a" --sha256 "$(printf '0%.0s' {1..64})" --archive "$tmp/$ref_a.tar.gz" --prefix "$prefix" --state-root "$state" >/dev/null 2>&1; then
  echo 'bad checksum was accepted' >&2; exit 1
fi

malicious_root="$tmp/malicious/DuneAwakeningSelfHost-$ref_a"
mkdir -p "$malicious_root/scripts" "$malicious_root/config"
printf 'services: {}\n' > "$malicious_root/compose.yaml"
printf 'DUNE_TEST=malicious\n' > "$malicious_root/.env.example"
ln -s /etc/passwd "$malicious_root/config/UserGame.ini"
tar -czf "$tmp/malicious.tar.gz" -C "$tmp/malicious" "DuneAwakeningSelfHost-$ref_a"
malicious_sha="$(sha256sum "$tmp/malicious.tar.gz" | awk '{print $1}')"
if "$repo_root/scripts/install-release.sh" install --ref "cccccccccccccccccccccccccccccccccccccccc" --sha256 "$malicious_sha" --archive "$tmp/malicious.tar.gz" --prefix "$prefix" --state-root "$state" >/dev/null 2>&1; then
  echo 'archive containing a symlink was accepted' >&2; exit 1
fi

echo 'release installer tests passed'
