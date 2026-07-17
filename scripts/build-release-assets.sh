#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build-release-assets.sh [--version TAG] [--ref COMMIT] [--output DIR]

Builds and verifies the complete DASH release asset set from an exact clean Git
commit. This includes the primary Linux x86_64 source bundle, SPDX SBOM, three
experimental loader bundles, checksums, verification receipts, release manifest,
and provenance. It performs a no-start installer smoke test.
EOF
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="v$(tr -d '\r\n' < "$root/VERSION")"
ref="$(git -C "$root" rev-parse HEAD)"
output="$root/dist/release"

while (($#)); do
  case "$1" in
    --version) version="${2:?missing --version value}"; shift 2 ;;
    --ref) ref="${2:?missing --ref value}"; shift 2 ;;
    --output) output="${2:?missing --output value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$output" != /* ]]; then output="$root/$output"; fi

[[ "$version" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$ ]] || {
  printf 'version must be a SemVer tag\n' >&2; exit 2;
}
[[ "$ref" =~ ^[0-9a-f]{40}$ ]] || { printf 'ref must be a full lowercase Git commit\n' >&2; exit 2; }
[[ "$(git -C "$root" rev-parse "$ref^{commit}")" == "$ref" ]] || { printf 'ref does not resolve exactly\n' >&2; exit 1; }
[[ "$(tr -d '\r\n' < "$root/VERSION")" == "${version#v}" ]] || { printf 'VERSION does not match requested tag\n' >&2; exit 1; }
if [[ -n "$(git -C "$root" status --porcelain --untracked-files=all)" ]]; then
  printf 'release builds require a clean worktree\n' >&2
  exit 1
fi

case "$output" in
  "$root"/dist/*|/tmp/*) ;;
  *) printf 'output must be under the repository dist/ directory or /tmp\n' >&2; exit 2 ;;
esac

rm -rf -- "$output"
mkdir -p "$output"
epoch="$(git -C "$root" show -s --format=%ct "$ref")"

python3 "$root/scripts/build-release.py" \
  --root "$root" --version "$version" --ref "$ref" --output-dir "$output"

SOURCE_DATE_EPOCH="$epoch" DUNE_LINUX_SERVER_LOADER_VERSION="$version" \
  "$root/scripts/package-linux-server-loader.sh"
SOURCE_DATE_EPOCH="$epoch" DUNE_LINUX_CLIENT_LOADER_VERSION="$version" \
  "$root/scripts/package-linux-client-loader.sh"
SOURCE_DATE_EPOCH="$epoch" DUNE_WINDOWS_CLIENT_LOADER_VERSION="$version" \
  "$root/scripts/package-windows-client-loader.sh"

for directory in "$root/dist/linux-server-loader" "$root/dist/linux-client-loader" "$root/dist/windows-client-loader"; do
  find "$directory" -maxdepth 1 -type f \
    \( -name "*-${version}-*.tar.gz" -o -name "*-${version}-*.tar.gz.sha256" -o -name "*-${version}-*.tar.gz.verification.json" \) \
    -exec cp -- {} "$output/" \;
done

notes="$root/docs/releases/${version}.md"
[[ -f "$notes" ]] || { printf 'release notes are missing: %s\n' "$notes" >&2; exit 1; }
cp -- "$notes" "$output/RELEASE_NOTES.md"

python3 "$root/scripts/finalize-release.py" finalize \
  --root "$root" --version "$version" --ref "$ref" --asset-dir "$output"
python3 "$root/scripts/finalize-release.py" verify \
  --version "$version" --ref "$ref" --asset-dir "$output"

smoke="$(mktemp -d)"
cleanup() { rm -rf -- "$smoke"; }
trap cleanup EXIT
archive="$output/dash-${version}-linux-x86_64.tar.gz"
archive_sha="$(sha256sum "$archive" | awk '{print $1}')"
"$root/scripts/install-release.sh" install \
  --ref "$ref" --sha256 "$archive_sha" --archive "$archive" \
  --prefix "$smoke/opt/dash" --state-root "$smoke/var/lib/dash" --activate >/dev/null
python3 - "$smoke/opt/dash/current/.dash-release.json" "$ref" "${version#v}" <<'PY'
import json,sys
path,commit,version=sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    value=json.load(handle)
if value.get("commit") != commit or value.get("releaseVersion") != version:
    raise SystemExit("installed release identity mismatch")
PY

printf 'release assets ready: %s\n' "$output"
