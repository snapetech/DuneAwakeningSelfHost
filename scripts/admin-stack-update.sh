#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/admin-stack-update.sh [--check|--apply] [remote]

Checks or fast-forwards the current DASH branch from its configured upstream.
Apply requires a clean worktree, validates the candidate in a temporary Git
worktree, writes a pre-update Git bundle, and only then fast-forwards this tree.
EOF
}

mode=--check
remote="${DUNE_ADMIN_STACK_UPDATE_REMOTE:-origin}"
case "${1:-}" in
  --check|--apply) mode="$1"; shift ;;
  -h|--help) usage; exit 0 ;;
  "") ;;
  *) usage >&2; exit 64 ;;
esac
if [[ $# -gt 0 ]]; then
  remote="$1"
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
git rev-parse --is-inside-work-tree >/dev/null

branch="$(git symbolic-ref --quiet --short HEAD || true)"
[[ -n "$branch" ]] || { echo 'fail: stack update requires a branch checkout' >&2; exit 1; }
upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
if [[ -z "$upstream" ]]; then
  upstream="$remote/$branch"
fi

git fetch --prune "$remote"
target="$(git rev-parse "$upstream")"
current="$(git rev-parse HEAD)"
git merge-base --is-ancestor "$current" "$target" || {
  echo "fail: $upstream is not a fast-forward from $current" >&2
  exit 1
}

behind="$(git rev-list --count "$current..$target")"
echo "branch=$branch"
echo "upstream=$upstream"
echo "current=$current"
echo "target=$target"
echo "behind=$behind"
if [[ "$mode" == "--check" || "$behind" == "0" ]]; then
  echo "status=$([[ "$behind" == "0" ]] && echo current || echo update-available)"
  exit 0
fi

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo 'fail: stack apply requires a clean worktree' >&2
  exit 1
fi

state_dir="$repo_root/backups/admin-panel/stack-updates"
mkdir -p "$state_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
bundle="$state_dir/$stamp-$current.bundle"
git bundle create "$bundle" HEAD

candidate="$(mktemp -d "${TMPDIR:-/tmp}/dash-stack-candidate.XXXXXX")"
cleanup() {
  git worktree remove --force "$candidate" >/dev/null 2>&1 || true
  rm -rf "$candidate"
}
trap cleanup EXIT
git worktree add --detach "$candidate" "$target" >/dev/null
(
  cd "$candidate"
  make validate
)
git worktree remove --force "$candidate" >/dev/null
git merge --ff-only "$target"
echo "bundle=$bundle"
echo "status=updated"
echo "restart_required=true"
