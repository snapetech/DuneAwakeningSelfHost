#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/publish-github-release.sh TAG ASSET_DIR [OWNER/REPO]

Creates a draft GitHub Release for an existing remote tag, uploads every
finalized asset, verifies GitHub's recorded SHA-256 digests, and publishes the
release. Repository release immutability must already be enabled.
EOF
}

tag="${1:-}"
asset_dir="${2:-}"
repository="${3:-${GITHUB_REPOSITORY:-snapetech/DuneAwakeningSelfHost}}"
[[ -n "$tag" && -n "$asset_dir" ]] || { usage >&2; exit 2; }
[[ -d "$asset_dir" ]] || { printf 'asset directory not found: %s\n' "$asset_dir" >&2; exit 1; }
command -v gh >/dev/null || { printf 'gh is required\n' >&2; exit 1; }

immutable_error="$(mktemp)"
trap 'rm -f -- "$immutable_error"' EXIT
if enabled="$(gh api -H 'X-GitHub-Api-Version: 2026-03-10' \
  "repos/$repository/immutable-releases" --jq .enabled 2>"$immutable_error")"; then
  [[ "$enabled" == true ]] || {
    printf 'repository immutable releases are not enabled\n' >&2
    exit 1
  }
elif [[ "${GITHUB_ACTIONS:-}" == true ]] && grep -q '(HTTP 403)' "$immutable_error"; then
  # GITHUB_TOKEN has contents:write but cannot read repository administration
  # settings. The published release's immutable field is still asserted below.
  printf 'immutable-release preflight unavailable to GITHUB_TOKEN; enforcing post-publication assertion\n'
else
  cat "$immutable_error" >&2
  exit 1
fi
gh api "repos/$repository/git/ref/tags/$tag" >/dev/null
if gh release view "$tag" --repo "$repository" >/dev/null 2>&1; then
  printf 'release already exists: %s\n' "$tag" >&2
  exit 1
fi

notes="$asset_dir/RELEASE_NOTES.md"
[[ -f "$notes" ]] || { printf 'release notes are missing\n' >&2; exit 1; }
prerelease=()
latest=(--latest)
if [[ "$tag" == *-* ]]; then prerelease=(--prerelease); latest=(--latest=false); fi

gh release create "$tag" --repo "$repository" --verify-tag --draft \
  --title "DASH $tag" --notes-file "$notes" "${prerelease[@]}" "${latest[@]}"

mapfile -d '' assets < <(find "$asset_dir" -maxdepth 1 -type f -print0 | sort -z)
[[ ${#assets[@]} -gt 0 ]] || { printf 'no release assets found\n' >&2; exit 1; }
gh release upload "$tag" --repo "$repository" "${assets[@]}"

release_id="$(gh api "repos/$repository/releases/tags/$tag" --jq .id)"
remote_json="$(mktemp)"
trap 'rm -f -- "$immutable_error" "$remote_json"' EXIT
gh api --paginate "repos/$repository/releases/$release_id/assets?per_page=100" > "$remote_json"
python3 - "$asset_dir" "$remote_json" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1])
with open(sys.argv[2], encoding="utf-8") as handle:
    remote=json.load(handle)
expected={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file() and not path.is_symlink()}
observed={row.get("name"): str(row.get("digest") or "").removeprefix("sha256:") for row in remote}
if expected != observed:
    missing=sorted(set(expected)-set(observed))
    extra=sorted(set(observed)-set(expected))
    mismatched=sorted(name for name in set(expected)&set(observed) if expected[name] != observed[name])
    raise SystemExit(f"GitHub asset digest mismatch missing={missing} extra={extra} mismatched={mismatched}")
print(f"verified {len(expected)} uploaded asset digests")
PY

gh release edit "$tag" --repo "$repository" --draft=false "${prerelease[@]}" "${latest[@]}"
immutable="$(gh api -H 'X-GitHub-Api-Version: 2026-03-10' "repos/$repository/releases/tags/$tag" --jq .immutable)"
[[ "$immutable" == true ]] || { printf 'published release is not immutable\n' >&2; exit 1; }
gh release verify "$tag" --repo "$repository"
gh release view "$tag" --repo "$repository" --json url,tagName,isDraft,isPrerelease,publishedAt
