#!/usr/bin/env bash
set -euo pipefail
umask 077

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$repo_root/.env"
output=""
usage() { printf 'Usage: %s [--env-file PATH] [--output PATH] ENCRYPTED_ARCHIVE\n' "$0"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) env_file="$2"; shift 2 ;;
    --output) output="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --*) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
    *) [[ -z "${archive_arg:-}" ]] || { printf 'only one archive is accepted\n' >&2; exit 2; }; archive_arg="$1"; shift ;;
  esac
done
[[ -n "${archive_arg:-}" ]] || { usage >&2; exit 2; }
[[ "$env_file" == /* ]] || env_file="$repo_root/$env_file"
[[ -f "$env_file" ]] || { printf 'env file not found\n' >&2; exit 1; }
read_env() { sed -n "s/^${1}=//p" "$env_file" | tail -1; }
gpg_home="${DUNE_BACKUP_GPG_HOME:-$(read_env DUNE_BACKUP_GPG_HOME)}"
command -v gpg >/dev/null || { printf 'gpg is required\n' >&2; exit 1; }
command -v tar >/dev/null || { printf 'tar is required\n' >&2; exit 1; }

backups_root="$(realpath "$repo_root/backups")"
if [[ "$archive_arg" == /* ]]; then archive="$(realpath -e "$archive_arg")"; else archive="$(realpath -e "$repo_root/$archive_arg")"; fi
[[ -f "$archive" && "$archive" == "$backups_root/encrypted/"*.tar.gz.gpg ]] || { printf 'archive must be a .tar.gz.gpg file directly below backups/encrypted/\n' >&2; exit 1; }
mkdir -p "$backups_root/decrypted";chmod 700 "$backups_root/decrypted"
base="$(basename "$archive" .gpg)";[[ -n "$output" ]] || output="$backups_root/decrypted/$base";[[ "$output" == /* ]] || output="$repo_root/$output"
[[ "$(realpath -m "$(dirname "$output")")" == "$backups_root/decrypted" && "$output" == *.tar.gz && ! -e "$output" ]] || { printf 'output must be a new .tar.gz file directly below backups/decrypted/\n' >&2; exit 1; }

gpg_args=(--batch --no-tty)
if [[ -n "$gpg_home" ]]; then [[ "$gpg_home" == /* && -d "$gpg_home" ]] || exit 1;gpg_args+=(--homedir "$gpg_home");fi
temporary="$(mktemp "$backups_root/decrypted/.decrypt.XXXXXX.tar.gz")";trap 'rm -f "$temporary"' EXIT
gpg "${gpg_args[@]}" --yes --output "$temporary" --decrypt "$archive" >/dev/null
python3 - "$temporary" <<'PY'
import pathlib,sys,tarfile
with tarfile.open(sys.argv[1],"r:gz") as archive:
    for member in archive.getmembers():
        path=pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise SystemExit("unsafe archive member")
PY
chmod 600 "$temporary";mv "$temporary" "$output";trap - EXIT
printf 'decrypted and validated archive=%s restore_automatic=false\n' "$output"
