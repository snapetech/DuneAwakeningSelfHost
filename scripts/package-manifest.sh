#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/package-manifest.sh [output-file]

Writes a publishable-file manifest for the current checkout. The manifest is
for review and release notes; it does not create an archive and does not include
ignored runtime data.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

output="${1:-}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf 'not inside a git worktree\n' >&2
  exit 1
fi

head="$(git rev-parse --short HEAD 2>/dev/null || printf unknown)"
branch="$(git branch --show-current 2>/dev/null || printf unknown)"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

emit() {
  cat <<EOF
# DASH Package Manifest

- generated_utc: ${timestamp}
- branch: ${branch}
- commit: ${head}

## Included Files

EOF
  git ls-files --cached --others --exclude-standard | sort | sed 's#^#- #'
  cat <<'EOF'

## Runtime Data Intentionally Excluded

- .env
- data/
- backups/
- captures/
- config/tls/
- Steam package files
- Funcom image tarballs
- runtime logs and dumps
- real tokens, passwords, public IPs, hostnames, and player data

## Review Commands

```bash
make validate
git status --short --untracked-files=all
git diff --check
```
EOF
}

if [[ -n "$output" ]]; then
  mkdir -p "$(dirname "$output")"
  emit > "$output"
  printf 'wrote package manifest: %s\n' "$output"
else
  emit
fi
