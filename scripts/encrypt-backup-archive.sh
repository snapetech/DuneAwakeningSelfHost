#!/usr/bin/env bash
set -euo pipefail
umask 077

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="$repo_root/.env"
output=""

usage() { printf 'Usage: %s [--env-file PATH] [--output PATH] BACKUP_DIR\n' "$0"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) env_file="$2"; shift 2 ;;
    --output) output="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --*) printf 'unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *) [[ -z "${source_arg:-}" ]] || { printf 'only one backup directory is accepted\n' >&2; exit 2; }; source_arg="$1"; shift ;;
  esac
done
[[ -n "${source_arg:-}" ]] || { usage >&2; exit 2; }
[[ "$env_file" == /* ]] || env_file="$repo_root/$env_file"
[[ -f "$env_file" ]] || { printf 'env file not found: %s\n' "$env_file" >&2; exit 1; }

read_env() { sed -n "s/^${1}=//p" "$env_file" | tail -1; }
recipient="${DUNE_BACKUP_GPG_RECIPIENT:-$(read_env DUNE_BACKUP_GPG_RECIPIENT)}"
require_verify="${DUNE_BACKUP_GPG_REQUIRE_VERIFY:-$(read_env DUNE_BACKUP_GPG_REQUIRE_VERIFY)}";require_verify="${require_verify:-true}"
gpg_home="${DUNE_BACKUP_GPG_HOME:-$(read_env DUNE_BACKUP_GPG_HOME)}"
[[ "$recipient" =~ ^([A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})$ ]] || { printf 'DUNE_BACKUP_GPG_RECIPIENT must be an exact 40- or 64-hex fingerprint\n' >&2; exit 1; }
command -v gpg >/dev/null || { printf 'gpg is required\n' >&2; exit 1; }
command -v tar >/dev/null || { printf 'tar is required\n' >&2; exit 1; }

backups_root="$(realpath "$repo_root/backups")"
if [[ "$source_arg" == /* ]]; then source="$(realpath -e "$source_arg")"; else source="$(realpath -e "$repo_root/$source_arg")"; fi
[[ -d "$source" && "$source" == "$backups_root"/* && "$source" != "$backups_root/encrypted"* && "$source" != "$backups_root/decrypted"* ]] || { printf 'source must be one backup-set directory below backups/\n' >&2; exit 1; }

gpg_args=(--batch --no-tty)
if [[ -n "$gpg_home" ]]; then
  [[ "$gpg_home" == /* && -d "$gpg_home" ]] || { printf 'DUNE_BACKUP_GPG_HOME must be an existing absolute directory\n' >&2; exit 1; }
  gpg_args+=(--homedir "$gpg_home")
fi
canonical="$(gpg "${gpg_args[@]}" --with-colons --list-keys "$recipient" 2>/dev/null | awk -F: '$1=="fpr" {print toupper($10); exit}')"
[[ -n "$canonical" && "$canonical" == "${recipient^^}" ]] || { printf 'recipient fingerprint is not present in the selected GnuPG keyring\n' >&2; exit 1; }

if [[ "$require_verify" == "true" ]]; then "$repo_root/scripts/verify-backup.sh" "$source" >/dev/null; fi
stamp="$(date -u +%Y%m%dT%H%M%SZ)";mkdir -p "$backups_root/encrypted";chmod 700 "$backups_root/encrypted"
if [[ -z "$output" ]]; then output="$backups_root/encrypted/$(basename "$source")-$stamp.tar.gz.gpg"; elif [[ "$output" != /* ]]; then output="$repo_root/$output"; fi
output_parent="$(realpath -m "$(dirname "$output")")";[[ "$output_parent" == "$backups_root/encrypted" ]] || { printf 'output must be directly below backups/encrypted/\n' >&2; exit 1; }
[[ "$output" == *.tar.gz.gpg && ! -e "$output" ]] || { printf 'output must be a new .tar.gz.gpg file\n' >&2; exit 1; }

plain="$(mktemp "$backups_root/encrypted/.plain.XXXXXX.tar.gz")";cipher="$(mktemp "$backups_root/encrypted/.cipher.XXXXXX.gpg")"
cleanup() { rm -f "$plain" "$cipher"; }
trap cleanup EXIT
tar --sort=name --owner=0 --group=0 --numeric-owner -C "$(dirname "$source")" -czf "$plain" "$(basename "$source")"
gpg "${gpg_args[@]}" --yes --trust-model always --recipient "$canonical" --output "$cipher" --encrypt "$plain"
chmod 600 "$cipher";mv "$cipher" "$output"
sha256="$(sha256sum "$output" | awk '{print $1}')";size="$(stat -c %s "$output")";receipt="$output.json"
python3 - "$receipt" "$output" "$source" "$canonical" "$sha256" "$size" "$stamp" <<'PY'
import json,pathlib,sys
pathlib.Path(sys.argv[1]).write_text(json.dumps({"schemaVersion":1,"encryptedArchive":pathlib.Path(sys.argv[2]).name,"sourceBackup":str(pathlib.Path(sys.argv[3]).name),"recipientFingerprint":sys.argv[4],"ciphertextSha256":sys.argv[5],"sizeBytes":int(sys.argv[6]),"createdAt":sys.argv[7],"format":"OpenPGP","plaintextRetained":False},indent=2,sort_keys=True)+"\n")
PY
chmod 600 "$receipt";rm -f "$plain";trap - EXIT
printf 'encrypted archive=%s receipt=%s sha256=%s plaintext_retained=false\n' "$output" "$receipt" "$sha256"
