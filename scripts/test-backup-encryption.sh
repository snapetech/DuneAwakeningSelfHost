#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v gpg >/dev/null || { printf 'gpg is required for backup encryption tests\n' >&2; exit 1; }
temp="$(mktemp -d)";source_dir="$repo_root/backups/.encryption-test-$$";output="$repo_root/backups/encrypted/test-$$.tar.gz.gpg";decrypted="$repo_root/backups/decrypted/test-$$.tar.gz"
cleanup() { rm -rf "$temp" "$source_dir";rm -f "$output" "$output.json" "$decrypted"; }
trap cleanup EXIT
mkdir -p "$source_dir";printf 'fixture payload\n' > "$source_dir/payload.txt";chmod 700 "$temp"
GNUPGHOME="$temp/gnupg";mkdir -m 700 "$GNUPGHOME";export GNUPGHOME
gpg --batch --pinentry-mode loopback --passphrase '' --quick-gen-key 'DASH Backup Test <backup-test@example.invalid>' rsa2048 encr 1d >/dev/null 2>&1
fingerprint="$(gpg --batch --with-colons --list-keys | awk -F: '$1=="fpr" {print $10;exit}')";[[ "$fingerprint" =~ ^[A-Fa-f0-9]{40}$|^[A-Fa-f0-9]{64}$ ]]
env_file="$temp/test.env";printf 'DUNE_BACKUP_GPG_RECIPIENT=%s\nDUNE_BACKUP_GPG_HOME=%s\nDUNE_BACKUP_GPG_REQUIRE_VERIFY=false\n' "$fingerprint" "$GNUPGHOME" > "$env_file"
"$repo_root/scripts/encrypt-backup-archive.sh" --env-file "$env_file" --output "$output" "$source_dir" >/dev/null
[[ -s "$output" && -s "$output.json" && "$(stat -c %a "$output")" == 600 ]];! find "$repo_root/backups/encrypted" -maxdepth 1 -name '.plain.*' -print -quit | grep -q .
python3 - "$output.json" "$fingerprint" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]));assert value["format"]=="OpenPGP" and value["recipientFingerprint"]==sys.argv[2].upper() and value["plaintextRetained"] is False and len(value["ciphertextSha256"])==64
PY
"$repo_root/scripts/decrypt-backup-archive.sh" --env-file "$env_file" --output "$decrypted" "$output" >/dev/null
tar -xOzf "$decrypted" "$(basename "$source_dir")/payload.txt" | grep -qx 'fixture payload'
if "$repo_root/scripts/encrypt-backup-archive.sh" --env-file "$env_file" --output "$temp/escape.tar.gz.gpg" "$source_dir" >/dev/null 2>&1;then echo 'output confinement failed' >&2;exit 1;fi
printf 'backup encryption tests passed\n'
