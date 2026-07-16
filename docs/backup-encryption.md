# Encrypted Backup Archives

DASH supports two established encryption outcomes:

- restic repository encryption for scheduled/offsite backup; and
- host-side recipient OpenPGP archives for portable verified backup sets.

The OpenPGP workflow never places the private recovery key in the admin
container. It verifies the source set, creates a mode-0600 temporary tarball,
encrypts to one exact fingerprint, removes plaintext, writes a ciphertext
SHA-256 receipt, and stages decryption without triggering restore.

## Key ownership

Generate the recovery key on a separate trusted machine or hardware-backed GPG
setup. Export only its public key to the Dune host. Keep at least two tested
copies of the private key and revocation certificate outside the server.

Example public-key import and fingerprint check:

```bash
gpg --import dash-backup-recovery-public.asc
gpg --with-colons --fingerprint <key selector> | awk -F: '$1=="fpr" {print $10}'
```

Use the complete 40-hex OpenPGP v4 or 64-hex v5 fingerprint. Names, email
addresses, short IDs, and 16-hex long IDs are rejected.

## Configuration

```dotenv
DUNE_BACKUP_ARCHIVE_ENCRYPTION_ENABLED=true
DUNE_BACKUP_GPG_RECIPIENT=<exact fingerprint>
DUNE_BACKUP_GPG_HOME=
DUNE_BACKUP_GPG_REQUIRE_VERIFY=true
DUNE_BACKUP_SYNC_ENCRYPTED_ONLY=false
```

Leave `DUNE_BACKUP_GPG_HOME` empty to use the operator account's normal GnuPG
home. If set, it must be an existing absolute host path. The public key is
enough for encryption. Decryption requires access to the matching private key.

The parity activator enables the feature gate but cannot select a recovery
recipient. Until a fingerprint is configured, the dashboard reports
`recipient required` and scheduled offsite sync behavior remains unchanged.

## Encrypt a verified set

```bash
scripts/verify-backup.sh backups/20260716T014011Z
scripts/encrypt-backup-archive.sh --env-file .env \
  backups/20260716T014011Z
```

Outputs are confined directly beneath `backups/encrypted/`:

```text
<backup>-<UTC timestamp>.tar.gz.gpg
<backup>-<UTC timestamp>.tar.gz.gpg.json
```

The JSON receipt records schema version, source set name, full recipient
fingerprint, format, ciphertext size/SHA-256, creation time, and
`plaintextRetained=false`. Both files are mode 0600; the directory is 0700.
The plaintext tarball exists only as a private temporary file and is removed on
success, error, or signal.

The script accepts only one existing directory beneath `backups/`, refuses the
encrypted/decrypted staging trees as sources, confines output to
`backups/encrypted/`, refuses overwrite, resolves symlinks, and runs
`verify-backup.sh` by default. Set `DUNE_BACKUP_GPG_REQUIRE_VERIFY=false` only
for synthetic test fixtures.

## Scheduled offsite encryption

`scripts/backup-offsite.sh` detects a newly created backup. When encryption is
enabled and a recipient is configured, it encrypts that verified set before
continuing.

To ensure rclone or rsync uploads only ciphertext and receipts:

```dotenv
DUNE_BACKUP_SYNC_ENCRYPTED_ONLY=true
```

Encrypted-only mode fails closed unless encryption and a recipient are both
configured. With the default `false`, existing offsite jobs retain their prior
source while also producing the encrypted artifact. Restic mode already uses
restic's repository encryption and does not need the OpenPGP layer unless a
portable archive is also desired.

## Decrypt and stage

```bash
scripts/decrypt-backup-archive.sh --env-file .env \
  backups/encrypted/<archive>.tar.gz.gpg
```

The output is confined to a new mode-0600 `.tar.gz` directly beneath
`backups/decrypted/`. Before publishing it, DASH validates that every tar member
is relative and contains no `..`, symlink, or hardlink entry. Decryption does
not import or restore anything.

After staging, inspect and deliberately import through the existing quarantine
workflow. Remove the decrypted staging archive when finished:

```bash
tar -tzf backups/decrypted/<archive>.tar.gz
rm -f backups/decrypted/<archive>.tar.gz
```

## Dashboard

Infrastructure → Backup Sets shows the encryption gate, recipient readiness
without the full fingerprint, verified-backup requirement, encrypted archive
inventory/receipts, and exact host encrypt/decrypt commands. Execution stays on
the host because its GnuPG keyring is intentionally outside the admin
container.

## Validation and recovery drill

```bash
make test-backup-encryption
bash -n scripts/encrypt-backup-archive.sh \
  scripts/decrypt-backup-archive.sh scripts/backup-offsite.sh
```

The test creates an isolated ephemeral GPG keyring, encrypts a fixture,
validates permissions/receipt/plaintext removal/output confinement, decrypts,
checks archive-member safety, and proves the payload round trip.

At least quarterly, decrypt one current production archive on a recovery host,
verify its receipt hash, inspect the tar, run the normal backup verifier after
safe extraction/import staging, and record the recovery time. An encrypted
archive without a tested private key is not a backup.
